"""Plan ID-only -> ID - Title folder migration; disposable private datasets only.

Default mode is read-only. Production migration is deliberately DISABLED until
the reader supports both layouts and a verified full backup exists.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

from .core import DEFAULT_REPO, validate_catalogue, write_csv
from .paths import book_dir, legacy_dir, readable_dir


class MigrationError(ValueError):
    pass


def plan_migration(books: list[dict], paths: set[str]) -> list[dict]:
    """Return a deterministic, non-destructive move plan, rejecting conflicts."""
    output = []
    reserved_destinations: set[str] = set()
    for book in books:
        book_id = book["id"]
        old_dir = book_dir(book)
        dest_dir = readable_dir(book_id, str(book["metadata"].get("title") or "Untitled"))
        current_files = sorted(p for p in paths if p.startswith(old_dir + "/"))
        status, reason = "MIGRATE", ""
        moves = []
        if old_dir != legacy_dir(book_id):
            status, reason = "ALREADY_READABLE", "Existing readable name remains stable"
        elif not current_files or book["epubPath"] not in current_files:
            status, reason = "CONFLICT", "Required source EPUB missing"
        elif (book.get("archivePath") and book["archivePath"] not in current_files):
            status, reason = "CONFLICT", "Declared original archive missing"
        else:
            cover = book["metadata"].get("coverPath") or book.get("coverPath")
            if cover and cover not in current_files:
                status, reason = "CONFLICT", "Declared cover image missing"
            else:
                for old in current_files:
                    new = dest_dir + old[len(old_dir):]
                    if new in paths or new in reserved_destinations:
                        status, reason = "CONFLICT", "Readable destination already exists"
                        moves = []
                        break
                    moves.append((old, new))
        if status == "MIGRATE":
            reserved_destinations.update(new for _, new in moves)
        output.append({
            "id": book_id, "title": str(book["metadata"].get("title") or ""),
            "old": old_dir, "new": dest_dir, "status": status,
            "reason": reason, "moves": moves,
        })
    return output


def apply_one(api, repo: str, token: str, item: dict, expected_sha: str) -> str:
    """Copy/delete each novel's files and update its catalogue in one HF commit."""
    if repo == DEFAULT_REPO:
        raise MigrationError("Production folder migration is not enabled")
    from huggingface_hub import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete, hf_hub_download

    info = api.dataset_info(repo, token=token)
    if info.private is not True or info.sha != expected_sha:
        raise MigrationError("Private dataset revision changed; re-run migration preview")

    files = set(api.list_repo_files(
        repo_id=repo, repo_type="dataset", revision=expected_sha, token=token))
    source = hf_hub_download(repo_id=repo, repo_type="dataset",
                             filename="data/library.json", revision=expected_sha, token=token)
    catalogue = json.loads(Path(source).read_text(encoding="utf-8"))
    books = validate_catalogue(catalogue)
    refreshed = {row["id"]: row for row in plan_migration(books, files)}
    current = refreshed.get(item["id"])
    if (not current or current["status"] != "MIGRATE" or
            current["old"] != item["old"] or current["new"] != item["new"] or
            current["moves"] != item["moves"]):
        raise MigrationError("Migration plan drift detected; re-run preview")
    target = next(b for b in books if b["id"] == item["id"])
    old, new = item["old"], item["new"]
    target["epubPath"] = new + "/source.epub"
    if target.get("archivePath"):
        target["archivePath"] = new + "/original.zip"
    for container in (target, target["metadata"]):
        cover = container.get("coverPath")
        if cover is not None:
            if not isinstance(cover, str) or not cover.startswith(old + "/"):
                raise MigrationError("Unexpected coverPath during migration")
            container["coverPath"] = new + cover[len(old):]
    validate_catalogue(catalogue)
    operations = [
        CommitOperationCopy(src_path_in_repo=src, path_in_repo=dst, src_revision=expected_sha)
        for src, dst in current["moves"]
    ]
    operations.extend(CommitOperationDelete(path_in_repo=src)
                      for src, _ in current["moves"])
    operations.append(CommitOperationAdd(
        path_in_repo="data/library.json",
        path_or_fileobj=(json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n").encode()))
    response = api.create_commit(
        repo_id=repo, repo_type="dataset", token=token, operations=operations,
        parent_commit=expected_sha,
        commit_message=f"Move novel folder to readable name: {item['id']}")
    new_sha = getattr(response, "oid", None)
    if not isinstance(new_sha, str) or not re.fullmatch(r"[a-f0-9]{40}", new_sha):
        raise MigrationError("Commit outcome uncertain; re-preview before retrying")
    return new_sha


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--report", default="reports/folder-migration-plan.csv")
    parser.add_argument("--apply", action="store_true",
                        help="Only supported on a disposable PRIVATE test dataset")
    parser.add_argument("--confirm-repo", default="",
                        help="When applying, repeat the complete private test dataset ID")
    args = parser.parse_args(argv)
    try:
        from huggingface_hub import HfApi, get_token
        from .core import load_remote
        api = HfApi()
        books, sha = load_remote(args.repo)
        info = api.dataset_info(args.repo)
        if info.private is not True or info.sha != sha:
            raise MigrationError("Unable to verify private dataset revision")
        files = set(api.list_repo_files(
            repo_id=args.repo, repo_type="dataset", revision=sha))
        rows = plan_migration(books, files)
        write_csv(Path(args.report), [
            {k: row[k] for k in ("id", "title", "old", "new", "status", "reason")}
            for row in rows], ["id", "title", "old", "new", "status", "reason"])
        counts = {state: sum(row["status"] == state for row in rows)
                  for state in ("MIGRATE", "ALREADY_READABLE", "CONFLICT")}
        print("Dataset:", args.repo, "Revision:", sha)
        print("Migration plan:", counts, "Report:", args.report)
        for row in rows:
            print(f"[{row['status']}] {row['title']}: "
                  f"{row['old']} -> {row['new']} ({len(row['moves'])} files)")
        if any(row["status"] == "CONFLICT" for row in rows):
            print("Unsafe migration plan: no writes allowed", file=sys.stderr)
            return 2
        if not args.apply:
            print("READ-ONLY. The production library cannot be migrated by this version.")
            return 0
        if args.repo == DEFAULT_REPO:
            raise MigrationError("Production migration is disabled until reader rollout and backup")
        if args.confirm_repo != args.repo:
            raise MigrationError("Repeat exact --repo using --confirm-repo for test migration")
        if not sys.stdin.isatty():
            raise MigrationError("Test migration requires an interactive terminal")
        if input("Migrate files in this DISPOSABLE test dataset? Type YES: ").strip() != "YES":
            print("Cancelled; no remote modifications")
            return 0
        token = get_token()
        if not token:
            raise MigrationError("No Hugging Face token configured")
        expected = sha
        for item in rows:
            if item["status"] == "MIGRATE":
                expected = apply_one(api, args.repo, token, item, expected)
                print("MIGRATED:", item["id"], "revision:", expected)
        print("Test migration completed. Validate reader before enabling production.")
        return 0
    except Exception as exc:
        print("ERROR:", type(exc).__name__ + ":", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
