"""Verified, backup-first production migration to human-readable folders.

This is intentionally NOT invoked by the normal storage CLI or routine CI.
Live production writes require a separately approved workflow dispatch, a
successful disposable private HF migration test and a verified deployed reader.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

from .actions import copy_to_private_backup, inventory, validate_repo
from .core import DEFAULT_REPO, validate_catalogue
from .migrate_folders import (
    MigrationError, apply_migration_batch, group_migration_batches, plan_migration,
)


CONFIRM_PHRASE = "MIGRATE READABLE NOVEL FOLDERS"


def select_pilot_candidate(work: list[dict], books: list[dict]) -> dict:
    """Choose ONE complete, linked EPUB/ZIP/cover book, without logging private titles."""
    indexed = {book["id"]: book for book in books}
    eligible = []
    for row in work:
        if row["status"] != "MIGRATE":
            continue
        book = indexed[row["id"]]
        cover = book["metadata"].get("coverPath") or book.get("coverPath")
        archive = book.get("archivePath")
        moved = {old for old, _ in row["moves"]}
        if book["epubPath"] in moved and archive and archive in moved and cover and cover in moved:
            eligible.append(row)
    if not eligible:
        raise MigrationError("No safe pilot candidate with EPUB, original ZIP and linked cover")
    # Deterministic selection by stable ID, independent of catalogue ordering.
    return min(eligible, key=lambda row: row["id"])


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def verify_moved_bytes(repo: str, token: str, moves: list[tuple[str, str]],
                       before_sha: str, after_sha: str) -> None:
    """Verify every moved blob from immutable old and new HF revisions."""
    from huggingface_hub import hf_hub_download
    for old, new in moves:
        old_file = Path(hf_hub_download(
            repo_id=repo, repo_type="dataset", filename=old,
            revision=before_sha, token=token))
        new_file = Path(hf_hub_download(
            repo_id=repo, repo_type="dataset", filename=new,
            revision=after_sha, token=token))
        if sha256_path(old_file) != sha256_path(new_file):
            raise MigrationError("Source/destination SHA-256 mismatch; STOP and recover from backup")


def _load(api, token: str) -> tuple[dict, str, set[str]]:
    from huggingface_hub import hf_hub_download
    info = api.dataset_info(DEFAULT_REPO, token=token)
    if info.private is not True or not re.fullmatch(r"[a-f0-9]{40}", info.sha or ""):
        raise MigrationError("Primary novel dataset is not verified PRIVATE at a valid revision")
    sha = info.sha
    files = set(api.list_repo_files(
        repo_id=DEFAULT_REPO, repo_type="dataset", revision=sha, token=token))
    if "data/library.json" not in files:
        raise MigrationError("Missing production catalogue; no migration")
    source = Path(hf_hub_download(
        repo_id=DEFAULT_REPO, repo_type="dataset",
        filename="data/library.json", revision=sha, token=token))
    catalogue = json.loads(source.read_text(encoding="utf-8"))
    validate_catalogue(catalogue)
    return catalogue, sha, files


def execute(api, token: str, backup_repo: str, *, apply: bool,
            confirmation: str = "", pilot_only: bool = False) -> dict[str, int]:
    """Plan and optionally execute only after a full, privately verified backup."""
    if not token:
        raise MigrationError("HF_STORAGE_CONTROLLER_TOKEN is missing")
    if backup_repo == DEFAULT_REPO:
        raise MigrationError("Backup destination cannot be the production dataset")
    validate_repo(backup_repo)
    catalogue, original_sha, files = _load(api, token)
    work = plan_migration(catalogue["books"], files)
    counts = {name: sum(row["status"] == name for row in work)
              for name in ("MIGRATE", "ALREADY_READABLE", "CONFLICT")}
    print("PRIVATE catalogue revision:", original_sha[:12])
    print("Novel folder migration PREVIEW (counts only):", counts)
    if counts["CONFLICT"]:
        raise MigrationError("Unsafe source catalogue or destination folder collision; no writes")
    if not apply or not counts["MIGRATE"]:
        return counts
    if confirmation != CONFIRM_PHRASE:
        raise MigrationError("Exact explicit migration confirmation is missing")
    pilot = select_pilot_candidate(work, catalogue["books"]) if pilot_only else None
    # Keep this as the ONLY entrypoint for production migration writes. The
    # backup function verifies every source file's SHA against the PRIVATE
    # destination dataset, including progress, notes and collection sidecars.
    complete_sha, all_paths = inventory(api, token)
    if complete_sha != original_sha or set(all_paths) != files:
        raise MigrationError("Dataset changed before complete backup; abort")
    print("Creating complete, checksum-verified PRIVATE snapshot before any file move.")
    copy_to_private_backup(api, backup_repo, token, original_sha, all_paths)
    current = api.dataset_info(DEFAULT_REPO, token=token)
    if current.private is not True or current.sha != original_sha:
        raise MigrationError("Source revision changed during backup; no migration")
    groups = [[pilot]] if pilot is not None else group_migration_batches(work)
    changed = 0
    for index, group in enumerate(groups, 1):
        before = current.sha
        after = apply_migration_batch(
            api, DEFAULT_REPO, token, group, before,
            production_backup_verified=True)
        updated = api.dataset_info(DEFAULT_REPO, token=token)
        if updated.private is not True or updated.sha != after:
            raise MigrationError("HF commit response did not match live revision; STOP")
        changes = [movement for row in group for movement in row["moves"]]
        latest_paths = set(api.list_repo_files(
            repo_id=DEFAULT_REPO, repo_type="dataset", revision=after, token=token))
        if any(old in latest_paths or new not in latest_paths for old, new in changes):
            raise MigrationError("Remote migration inventory mismatch; STOP")
        verify_moved_bytes(DEFAULT_REPO, token, changes, before, after)
        changed += len(group)
        print(f"PASS batch {index}/{len(groups)}: {len(group)} novels, "
              f"{len(changes)} files, every moved SHA-256 verified.")
        current = updated
        if index < len(groups):
            time.sleep(2)
    final, final_sha, final_files = _load(api, token)
    remaining = plan_migration(final["books"], final_files)
    if pilot is None:
        if any(row["status"] != "ALREADY_READABLE" for row in remaining):
            raise MigrationError("Some books remain in the old format; re-preview before retry")
    else:
        initial_status = {row["id"]: row["status"] for row in work}
        final_status = {row["id"]: row["status"] for row in remaining}
        if (changed != 1 or final_status.get(pilot["id"]) != "ALREADY_READABLE"
                or any(final_status.get(book_id) != status
                       for book_id, status in initial_status.items()
                       if book_id != pilot["id"])):
            raise MigrationError("Pilot changed more than the selected novel or did not complete")
        before_by_id = {book["id"]: book for book in catalogue["books"]}
        after_by_id = {book["id"]: book for book in final["books"]}
        if any(after_by_id[book_id] != before
               for book_id, before in before_by_id.items() if book_id != pilot["id"]):
            raise MigrationError("Pilot unexpectedly changed another catalogue entry")
    if len(final["books"]) != len(catalogue["books"]):
        raise MigrationError("Catalogue entry count changed unexpectedly")
    if {b["id"] for b in final["books"]} != {b["id"] for b in catalogue["books"]}:
        raise MigrationError("Stable IDs changed during migration")
    original_sidecars = {path for path in files if path.startswith("data/personal/")}
    if original_sidecars != {path for path in final_files if path.startswith("data/personal/")}:
        raise MigrationError("Personal progress/review/collection file paths changed")
    print(f"PASS: {changed} production novel folders renamed, "
          f"{len(final['books'])} stable novel IDs preserved, current revision {final_sha[:12]}.")
    print("All files remain backed up in a different PRIVATE HF dataset.")
    return {**counts, "changed": changed}


def main() -> int:
    token = os.environ.get("HF_TOKEN", "").strip()
    backup = os.environ.get(
        "HF_MIGRATION_BACKUP_REPO", "AdityaSreevatsaK/Taiyous-Novels-Backup").strip()
    apply = os.environ.get("HF_READABLE_MIGRATION_APPLY") == "true"
    confirm = os.environ.get("HF_READABLE_MIGRATION_CONFIRM", "")
    pilot_only = os.environ.get("HF_READABLE_MIGRATION_PILOT_ONE") == "true"
    try:
        from huggingface_hub import HfApi
        execute(HfApi(token=token), token, backup, apply=apply,
                confirmation=confirm, pilot_only=pilot_only)
        return 0
    except Exception as exc:
        # Public GitHub Actions logs must not contain novel names, source
        # directories, private API responses or exception details.
        print(f"STOPPED: production migration ({type(exc).__name__}). "
              "Review the private dataset and rerun the preview.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
