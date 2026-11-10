"""Backup-first reset for private Hugging Face dataset files under data/.

No remote writes without interactive confirmation and verified local backup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys

from .core import DEFAULT_REPO

EMPTY_CATALOGUE = {"version": 1, "books": []}
MAX_FILES = 5000


class ResetError(ValueError):
    pass


def select_data_files(paths: list[str]) -> list[str]:
    """Select concrete paths under data/, never repository metadata files."""
    selected = []
    for path in paths:
        if not isinstance(path, str) or not path.startswith("data/"):
            continue
        parts = path.split("/")
        if (len(parts) < 3 and path != "data/library.json") or any(
                not part or part in (".", "..") or "\\" in part or ":" in part
                for part in parts):
            raise ResetError(f"Unsafe dataset file path: {path}")
        selected.append(path)
    if len(selected) > MAX_FILES or len(set(selected)) != len(selected):
        raise ResetError("Too many files or duplicate paths; refusing reset")
    return sorted(selected)


def verify_private(api, repo: str, token: str) -> str:
    info = api.dataset_info(repo, token=token)
    if info.private is not True or not info.sha:
        raise ResetError("Dataset must be confirmed PRIVATE and have a revision")
    return info.sha


def backup_data(repo: str, revision: str, files: list[str],
                token: str, root: Path) -> tuple[Path, dict]:
    """Download and verify every file at a pinned revision."""
    from huggingface_hub import hf_hub_download
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = root / f"before-reset-{stamp}-{revision[:12]}"
    dest.mkdir(parents=True, exist_ok=False)
    entries = []
    for index, relative in enumerate(files, 1):
        print(f"BACKUP [{index}/{len(files)}] {relative}", flush=True)
        cached = Path(hf_hub_download(
            repo_id=repo, repo_type="dataset", filename=relative,
            revision=revision, token=token))
        target = dest.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_name(target.name + ".part")
        digest = hashlib.sha256()
        length = 0
        try:
            with cached.open("rb") as reader, staging.open("wb") as writer:
                for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                    writer.write(chunk)
                    digest.update(chunk)
                    length += len(chunk)
            staging.replace(target)
        finally:
            staging.unlink(missing_ok=True)
        entries.append({"path": relative, "size": length, "sha256": digest.hexdigest()})
    manifest = {"repository": repo, "revision": revision, "createdAt": stamp,
                "count": len(entries), "files": entries}
    staged_manifest = dest / "manifest.json.part"
    staged_manifest.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    staged_manifest.replace(dest / "manifest.json")
    for entry in entries:
        target = dest.joinpath(*entry["path"].split("/"))
        if target.stat().st_size != entry["size"]:
            raise ResetError("Backup size verification failed: " + entry["path"])
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != entry["sha256"]:
            raise ResetError("Backup SHA-256 verification failed: " + entry["path"])
    return dest, manifest


def operations_for(paths: list[str]):
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete
    ops = [CommitOperationDelete(path_in_repo=p)
           for p in paths if p != "data/library.json"]
    ops.append(CommitOperationAdd(
        path_in_repo="data/library.json",
        path_or_fileobj=io.BytesIO(
            (json.dumps(EMPTY_CATALOGUE, indent=2) + "\n").encode("utf-8"))))
    return ops


def perform_reset(api, repo: str, token: str,
                  original_revision: str, original_paths: list[str]) -> None:
    current_revision = verify_private(api, repo, token)
    if current_revision != original_revision:
        raise ResetError("Dataset changed during backup; no reset performed")
    current_paths = select_data_files(api.list_repo_files(
        repo_id=repo, repo_type="dataset", revision=current_revision, token=token))
    if current_paths != original_paths:
        raise ResetError("Data paths changed; no reset performed")
    api.create_commit(
        repo_id=repo, repo_type="dataset", token=token,
        parent_commit=original_revision, operations=operations_for(current_paths),
        commit_message="Clear data tree after complete verified local backup")


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Reset private Hugging Face data/ safely")
    parser.add_argument("--repo", default=os.environ.get("HF_DATASET_REPO", DEFAULT_REPO))
    parser.add_argument("--backup-root", default="backups")
    parser.add_argument("--apply", action="store_true",
                        help="Interactive backup and confirmed deletion")
    args = parser.parse_args(argv)
    try:
        from huggingface_hub import HfApi, get_token
        token = get_token()
        if not token:
            raise ResetError("Authenticate with hf auth login")
        api = HfApi()
        revision = verify_private(api, args.repo, token)
        all_paths = api.list_repo_files(
            repo_id=args.repo, repo_type="dataset", revision=revision, token=token)
        if "data/library.json" not in all_paths:
            raise ResetError("Required data/library.json missing; unknown layout")
        paths = select_data_files(all_paths)
        print("\nPRIVATE DATASET RESET PREVIEW")
        print("Dataset:", args.repo)
        print("Revision:", revision)
        print("Files affected:", len(paths))
        print("ALL novel ZIPs, EPUBs, covers, progress, personal reviews and collections")
        print("stored under data/ will be removed. Dataset repository remains in place.")
        print("Git/LFS history may still contain previous content.")
        for path in paths:
            print(" -", path)
        if not args.apply:
            print("PREVIEW ONLY. No backups or changes were made.")
            return 0
        if not sys.stdin.isatty():
            raise ResetError("Reset requires an interactive console; CI cannot execute it")
        if input("Type FULL dataset repository ID to begin backup: ").strip() != args.repo:
            print("Cancelled: dataset ID did not match")
            return 2
        root = Path(args.backup_root)
        if root.is_symlink():
            raise ResetError("Refusing symlinked backup root")
        destination, manifest = backup_data(args.repo, revision, paths, token, root)
        if manifest["count"] != len(paths) or not manifest["files"]:
            raise ResetError("Backup incomplete; no files deleted")
        print("\nVERIFIED local backup:", destination.resolve())
        phrase = f"ERASE {len(paths)} FILES {revision[:12]}"
        if input("Type " + phrase + " to permanently clear current data/: ").strip() != phrase:
            print("Cancelled: backup preserved, no remote changes")
            return 2
        perform_reset(api, args.repo, token, revision, paths)
        print("DONE: private dataset data/ reset; empty library.json saved.")
        print("BACKUP:", destination.resolve())
        print("Cached books on other devices may remain until refreshed.")
        return 0
    except (ResetError, OSError, EOFError, ValueError, RuntimeError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
