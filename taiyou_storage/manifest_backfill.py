"""Resumable, opt-in one-time backfill of private HF inspection sidecars.

Default is a local preview. --apply alone enables writes, which use
revision-guarded, sidecar-only commits. No original novel file is overwritten.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

from .console_summary import print_summary
from .core import DEFAULT_REPO, StorageError, validate_catalogue
from .inspection import (HFReadOnly, MAX_CATALOGUE, IMAGE_SUFFIXES, inspect_book,
                         Snapshot)
from .inspection_manifest import (build_manifest, local_artifact, manifest_bytes,
                                  manifest_path, read_manifest)
from .inspection_cache import inspection_cache_dir
from .paths import book_dir

BLOCKED_ISSUES = {
    "INSPECTION_FAILED", "CORRUPT_EPUB", "CORRUPT_OR_UNREADABLE_ARCHIVE",
    "COVER_SCAN_FAILED", "INVALID_CATALOGUE_PATH",
}


def _catalogue(backend: HFReadOnly, snapshot: Snapshot) -> list[dict]:
    if "data/library.json" not in snapshot.files:
        raise StorageError("No catalogue at pinned revision")
    path = backend.download("data/library.json", snapshot.revision)
    if path.stat().st_size > MAX_CATALOGUE:
        raise StorageError("Catalogue exceeds size limit")
    return validate_catalogue(json.loads(path.read_text(encoding="utf-8-sig")))


def _cover_for(book: dict, snapshot: Snapshot) -> str | None:
    meta = book["metadata"]
    folder = book_dir(book)
    cover = meta.get("coverPath") or book.get("coverPath")
    if cover:
        return cover if cover in snapshot.files else None
    candidates = [name for name in snapshot.files
                  if name.startswith(folder + "/cover")
                  and PurePosixPath(name).parent.as_posix() == folder
                  and PurePosixPath(name).suffix.casefold() in IMAGE_SUFFIXES]
    return candidates[0] if len(candidates) == 1 else None


def generate(backend: HFReadOnly, snapshot: Snapshot, book: dict) -> dict:
    """Validate a single book deeply and reuse HF cached blobs for hashing."""
    row, issues = inspect_book(book, snapshot.files, snapshot.revision,
                               backend, "deep", snapshot.identities)
    failures = set(i["code"] for i in issues) & BLOCKED_ISSUES
    if failures:
        raise ValueError("Cannot establish reliable evidence: " + ", ".join(sorted(failures)))
    paths = {"epub": book["epubPath"], "archive": book.get("archivePath")}
    cover = _cover_for(book, snapshot)
    if cover:
        paths["cover"] = cover
    evidence = {}
    for kind, remote_path in paths.items():
        if remote_path and remote_path in snapshot.files:
            local = backend.download(remote_path, snapshot.revision)
            evidence[kind] = local_artifact(
                remote_path, local, snapshot.identities.get(remote_path))
    # A missing, corrupt or ambiguous cover is not proof of an AVAILABLE cover.
    if row["cover_status"] == "AVAILABLE" and "cover" not in evidence:
        row["cover_status"], row["cover_reason"] = (
            "UNVERIFIED", "Cover has no unambiguous file provenance")
    if row["verification_status"] != "UNVERIFIED" and not {"archive", "epub"} <= evidence.keys():
        row["verification_status"] = "UNVERIFIED"
        row["verification_reason"] = "Original files are missing"
    return build_manifest(book, row, issues, evidence)


def plan(backend: HFReadOnly, reports: Path, *, limit: int = 0,
         force: bool = False, verbose: bool = False) -> tuple[Snapshot, list[tuple[str, bytes]], dict]:
    """Reuse validated local drafts and existing sidecars after interruptions."""
    snapshot = backend.snapshot()
    books = _catalogue(backend, snapshot)
    selected, statuses, failures = [], Counter(), []
    drafts = reports / "manifest-backfill"
    drafts.mkdir(parents=True, exist_ok=True)
    for book in books:
        if limit and len(selected) >= limit:
            break
        try:
            sidecar = manifest_path(book)
            if sidecar in snapshot.files and not force:
                existing = backend.download(sidecar, snapshot.revision)
                if existing.stat().st_size <= 512 * 1024:
                    try:
                        read_manifest(book, existing.read_bytes(), snapshot.files,
                                      snapshot.identities)
                        statuses["already_valid"] += 1
                        continue
                    except (ValueError, TypeError, KeyError):
                        pass  # Stale, unreadable, or unverified identity: rebuild
            draft = drafts / (book["id"] + ".json")
            manifest = None
            if draft.exists() and not force:
                try:
                    raw = draft.read_bytes()
                    read_manifest(book, raw, snapshot.files, snapshot.identities)
                    manifest = raw
                    statuses["reused_local"] += 1
                except (ValueError, TypeError, OSError, KeyError):
                    pass
            if manifest is None:
                manifest = manifest_bytes(generate(backend, snapshot, book))
                draft.write_bytes(manifest)
                statuses["generated"] += 1
            selected.append((sidecar, manifest))
        except (Exception, KeyboardInterrupt) as exc:
            if isinstance(exc, KeyboardInterrupt):
                raise
            statuses["failed"] += 1
            failures.append({"novel_id": str(book.get("id", "")),
                             "error": f"{type(exc).__name__}: {exc}"})
            if verbose:
                print(f"[UNVERIFIED] {book.get('id', '')}: {type(exc).__name__}: {exc}",
                      file=sys.stderr)
    from .core import write_csv
    write_csv(drafts / "failures.csv", failures, ["novel_id", "error"])
    statuses["books"] = len(books)
    statuses["pending"] = len(selected)
    return snapshot, selected, dict(statuses)


def apply(backend: HFReadOnly, snapshot: Snapshot, selected: list[tuple[str, bytes]],
          *, batch_size: int = 10, api=None, token: str | None = None) -> int:
    """Only add sidecars; parent commit prevents lost updates."""
    from huggingface_hub import CommitOperationAdd, HfApi, get_token
    api = api or HfApi()
    token = token or get_token()
    if not token:
        raise StorageError("Hugging Face write token required for --apply")
    info = api.dataset_info(backend.repo, token=token)
    if info.private is not True or info.sha != snapshot.revision:
        raise StorageError("Dataset changed after preview or is not private; re-run")
    expected = snapshot.revision
    committed = 0
    for offset in range(0, len(selected), batch_size):
        chunk = selected[offset: offset + batch_size]
        operations = [CommitOperationAdd(path_in_repo=path, path_or_fileobj=body)
                      for path, body in chunk]
        result = api.create_commit(
            repo_id=backend.repo, repo_type="dataset", token=token,
            operations=operations, parent_commit=expected,
            commit_message="Backfill verified novel inspection manifests")
        new_sha = getattr(result, "oid", None)
        if not isinstance(new_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", new_sha):
            raise StorageError("Commit revision not returned: check remote state before retrying")
        expected = new_sha
        committed += len(chunk)
        print(f"[APPLIED] {committed}/{len(selected)} manifests")
    return committed


def run(argv: list[str] | None = None, backend: HFReadOnly | None = None,
        api=None, token: str | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private HF inspection manifest migration")
    parser.add_argument("--repo", default=os.environ.get("HF_DATASET_REPO", DEFAULT_REPO))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit new manifests; use 1 for a safe pilot, 0 for all")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--verbose", action="store_true",
                        help="Show per-novel inspection errors; also saved in reports")
    parser.add_argument("--force", action="store_true",
                        help="Rebuild even currently valid sidecars")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true",
                       help="Explicitly upload manifests, never original EPUBs or ZIPs")
    group.add_argument("--interactive", action="store_true",
                       help="Preview and require typed YES before sidecar uploads")
    args = parser.parse_args(argv)
    if args.limit < 0 or not 1 <= args.batch_size <= 20:
        parser.error("--limit must be >=0 and --batch-size must be 1..20")
    try:
        client = backend if backend is not None else HFReadOnly(args.repo, cache_dir=inspection_cache_dir(args.reports_dir))
        snapshot, selected, status = plan(client, args.reports_dir,
                                           limit=args.limit, force=args.force,
                                           verbose=args.verbose)
        print_summary("Inspection manifest backfill", {
            "Total novels": status["books"],
            "Existing valid manifests": status.get("already_valid", 0),
            "New manifests generated": status.get("generated", 0),
            "Local drafts reused": status.get("reused_local", 0),
            "Manifests ready to upload": status["pending"],
            "Failed inspections": status.get("failed", 0),
        }, reports=[args.reports_dir / "manifest-backfill" / "failures.csv"],
            note="Sidecars only; EPUBs and ZIPs unchanged. Review before applying.",
            status="PREVIEW")
        if not args.apply and not args.interactive:
            return 0 if not status.get("failed") else 2
        if status.get("failed"):
            print("Some novels could not be inspected; refusing partial unattended writes.",
                  file=sys.stderr)
            return 2
        if args.interactive:
            if not sys.stdin.isatty() or input("Upload only these manifests? Type YES: ").strip() != "YES":
                print("Cancelled; HF dataset unchanged")
                return 0
        committed = apply(client, snapshot, selected, batch_size=args.batch_size,
                          api=api, token=token)
        print_summary("Manifest backfill completed", {
            "Manifests uploaded": committed,
            "Failed inspections": 0,
        }, reports=[args.reports_dir / "manifest-backfill" / "failures.csv"],
            note="Original novels and catalogue unchanged.")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
