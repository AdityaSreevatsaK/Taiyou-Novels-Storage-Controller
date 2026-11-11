"""Manual, privacy-preserving GitHub Actions for a private HF novel dataset.

Never upload private novel files or reports as GitHub Actions artifacts.
Destructive data clearing is deliberately unavailable from Actions.
Verified backup-first resets remain local and interactive.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

from .core import DEFAULT_REPO, normalized_title, validate_catalogue


class ActionError(ValueError):
    pass


def validate_repo(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
            r"[A-Za-z0-9][\w.-]{0,95}/[A-Za-z0-9][\w.-]{0,95}", value):
        raise ActionError("Invalid private backup dataset ID")
    if value == DEFAULT_REPO:
        raise ActionError("Source dataset cannot be used as its own backup")
    if value.split("/", 1)[0] != DEFAULT_REPO.split("/", 1)[0]:
        raise ActionError("Backup must belong to the same Hugging Face account")
    return value


def private_dataset(api, repo: str, token: str) -> str:
    info = api.dataset_info(repo, token=token)
    if info.private is not True or not info.sha:
        raise ActionError("Required dataset is missing, inaccessible, or not PRIVATE")
    return info.sha


def safe_paths(paths: list[str]) -> list[str]:
    if not isinstance(paths, list) or len(paths) > 20000:
        raise ActionError("Unrecognised file inventory size")
    result = []
    for name in paths:
        if not isinstance(name, str) or not name or name.startswith("/"):
            raise ActionError("Invalid path in private dataset")
        parts = name.split("/")
        if any(part in ("", ".", "..") or "\\" in part or ":" in part for part in parts):
            raise ActionError("Unsafe path in private dataset")
        result.append(name)
    if len(set(result)) != len(result):
        raise ActionError("Duplicate path in dataset inventory")
    return sorted(result)


def inventory(api, token: str) -> tuple[str, list[str]]:
    revision = private_dataset(api, DEFAULT_REPO, token)
    paths = safe_paths(api.list_repo_files(
        repo_id=DEFAULT_REPO, repo_type="dataset", revision=revision, token=token))
    return revision, paths


def load_catalogue(revision: str, token: str) -> tuple[list[dict], bytes]:
    from huggingface_hub import hf_hub_download
    source = hf_hub_download(repo_id=DEFAULT_REPO, repo_type="dataset",
                             filename="data/library.json", revision=revision, token=token)
    contents = Path(source).read_bytes()
    return validate_catalogue(json.loads(contents)), contents


def inspect(api, token: str) -> tuple[str, dict]:
    revision, paths = inventory(api, token)
    # Even with a damaged catalogue the user needs the source SHA to
    # safely initiate a backup/reset. Never emit novel names in public logs.
    try:
        books, _ = load_catalogue(revision, token)
    except Exception:
        return revision, {
            "catalogue_valid": False,
            "data_files": sum(p.startswith("data/") for p in paths),
            "novel_directories": len({
                match.group(1) for p in paths
                if (match := re.match(r"^data/novels/([0-9a-f]{24})/", p))
            }),
            "note": "Catalogue could not be validated; inspect privately before any reset",
        }
    counts = Counter(normalized_title(str(b["metadata"].get("title", "")))
                     for b in books)
    titles_repeated = sum(count - 1 for key, count in counts.items() if key and count > 1)
    id_set = {b["id"] for b in books}
    remote_novel_ids = {match.group(1) for path in paths
                        if (match := re.match(r"^data/novels/([0-9a-f]{24})/", path))}
    missing_epubs = sum(b["epubPath"] not in paths for b in books)
    missing_zips = sum(bool(b.get("archivePath")) and b["archivePath"] not in paths
                       for b in books)
    summary = {
        "catalogue_books": len(books),
        "data_files": sum(p.startswith("data/") for p in paths),
        "novel_directories": len(remote_novel_ids),
        "orphan_novel_directories": len(remote_novel_ids - id_set),
        "duplicate_normalised_titles": titles_repeated,
        "missing_epubs": missing_epubs,
        "missing_archives": missing_zips,
        "cover_files": sum(bool(re.match(r"^data/novels/[0-9a-f]{24}/cover\.(jpg|jpeg|png|webp)$", p))
                           for p in paths),
    }
    return revision, summary


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for piece in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(piece)
    return digest.hexdigest()


def ensure_backup_private(api, backup_repo: str, token: str) -> None:
    validate_repo(backup_repo)
    # Create as PRIVATE when it does not exist; never make a public backup.
    try:
        info = api.dataset_info(backup_repo, token=token)
    except Exception:
        api.create_repo(repo_id=backup_repo, repo_type="dataset",
                        private=True, exist_ok=True, token=token)
        info = api.dataset_info(backup_repo, token=token)
    if info.private is not True:
        raise ActionError("Backup repository is PUBLIC. No backup or deletion permitted")


def copy_to_private_backup(api, backup_repo: str, token: str,
                           revision: str, paths: list[str]) -> None:
    """Copy source files to private snapshot and verify every remote file hash."""
    from huggingface_hub import hf_hub_download
    ensure_backup_private(api, backup_repo, token)
    if not paths:
        raise ActionError("Empty source dataset; refusing destructive operation")
    prefix = f"snapshots/{revision}"
    with tempfile.TemporaryDirectory(prefix="hf-private-backup-") as folder:
        root = Path(folder)
        files = root / "files"
        files.mkdir()
        manifest = []
        for relative in paths:
            downloaded = Path(hf_hub_download(
                repo_id=DEFAULT_REPO, repo_type="dataset",
                filename=relative, revision=revision, token=token))
            destination = files.joinpath(*relative.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(downloaded, destination)
            manifest.append({"path": relative, "size": destination.stat().st_size,
                             "sha256": file_hash(destination)})
        (root / "manifest.json").write_text(json.dumps({
            "source_repo": DEFAULT_REPO, "source_revision": revision,
            "files": manifest,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Private backup transfer started (filenames suppressed).", flush=True)
        api.upload_folder(
            repo_id=backup_repo, repo_type="dataset", token=token,
            folder_path=str(root), path_in_repo=prefix,
            ignore_patterns=["**/.cache/**", ".cache/**"],
            commit_message=f"Verified source backup for revision {revision[:12]}")
        backup_sha = private_dataset(api, backup_repo, token)
        remote_files = set(api.list_repo_files(
            repo_id=backup_repo, repo_type="dataset", revision=backup_sha, token=token))
        expected = {f"{prefix}/files/{entry['path']}" for entry in manifest}
        expected.add(f"{prefix}/manifest.json")
        if not expected.issubset(remote_files):
            raise ActionError("Private backup file inventory is incomplete")
        for entry in manifest:
            remote = Path(hf_hub_download(
                repo_id=backup_repo, repo_type="dataset",
                filename=f"{prefix}/files/{entry['path']}",
                revision=backup_sha, token=token))
            if remote.stat().st_size != entry["size"] or file_hash(remote) != entry["sha256"]:
                raise ActionError("Private remote backup failed checksum verification")
        remote_manifest = Path(hf_hub_download(
            repo_id=backup_repo, repo_type="dataset",
            filename=f"{prefix}/manifest.json", revision=backup_sha,
            token=token)).read_bytes()
        if remote_manifest != (root / "manifest.json").read_bytes():
            raise ActionError("Private backup manifest verification failed")
    print(f"PRIVATE BACKUP VERIFIED: {len(paths)} files, source revision {revision}", flush=True)
    print("Backup is saved only in a PRIVATE Hugging Face dataset.")


def report_to_private_backup(api, backup_repo: str, token: str) -> None:
    """Write names and collision CSV reports privately, never to GitHub artifacts."""
    from huggingface_hub import CommitOperationAdd
    from .core import rows, conflicts
    ensure_backup_private(api, backup_repo, token)
    revision, _ = inventory(api, token)
    books, catalogue = load_catalogue(revision, token)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    location = f"reports/{timestamp}-{revision[:12]}"
    def as_csv(data, fields):
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)
        return io.BytesIO(output.getvalue().encode("utf-8-sig"))
    listing = rows(books)
    collisions = conflicts(books)
    api.create_commit(repo_id=backup_repo, repo_type="dataset", token=token,
                      operations=[
                          CommitOperationAdd(
                              path_in_repo=f"{location}/novels.csv",
                              path_or_fileobj=as_csv(
                                  listing, ["id", "title", "author", "chapters",
                                            "epub_path", "archive_path"])),
                          CommitOperationAdd(
                              path_in_repo=f"{location}/conflicts.csv",
                              path_or_fileobj=as_csv(
                                  collisions, ["type", "first_title", "first_id",
                                               "second_title", "second_id"])),
                          CommitOperationAdd(
                              path_in_repo=f"{location}/library.json",
                              path_or_fileobj=io.BytesIO(catalogue)),
                      ],
                      commit_message=f"Private storage reports for {revision[:12]}")
    print(f"PRIVATE reports saved: {len(listing)} book records, {len(collisions)} title conflicts.")
    print("Open the backup dataset to view names and details; none are posted in public artifacts.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Private HF storage GitHub Actions")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("inspect")
    for action in ("report", "backup"):
        p = commands.add_parser(action)
        p.add_argument("--backup-repo", required=True)
    args = parser.parse_args(argv)
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        print("ERROR: HF_STORAGE_CONTROLLER_TOKEN GitHub secret is not configured.", file=sys.stderr)
        return 1
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        if args.action == "inspect":
            revision, counts = inspect(api, token)
            for key, number in counts.items():
                print(f"{key}: {number}")
        elif args.action == "report":
            report_to_private_backup(api, args.backup_repo, token)
        elif args.action == "backup":
            revision, paths = inventory(api, token)
            copy_to_private_backup(api, args.backup_repo, token, revision, paths)
        return 0
    except ActionError as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 2
    except Exception as exc:
        # Do not leak URLs, novel titles, private file paths or API responses
        # into the logs of this PUBLIC GitHub repository.
        print(f"ERROR: Private storage operation failed ({type(exc).__name__}).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
