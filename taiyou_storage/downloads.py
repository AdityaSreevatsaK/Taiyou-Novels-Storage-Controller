"""Bounded, streaming downloads of private Hugging Face novel ZIPs.

Never fetch an entire dataset snapshot just to retrieve original ZIPs. Write
each archive atomically, report partial failures and keep all existing files.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Callable


def _safe_destination(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if (not parts or parts[0] != "data" or len(parts) < 4
            or any(part in ("", ".", "..") or "\\" in part or ":" in part for part in parts)
            or not relative.endswith("/original.zip")):
        raise ValueError("Refusing unsafe or unexpected novel archive path")
    # Refuse local symlinks so a checked-out folder cannot redirect downloads
    # outside the chosen destination. No directory is deleted by this tool.
    for directory in (root, *[root.joinpath(*parts[:i]) for i in range(1, len(parts))]):
        if directory.is_symlink():
            raise ValueError("Refusing symlinked download directory")
    destination = root.joinpath(*parts)
    if destination.is_symlink():
        raise ValueError("Refusing symlinked download target")
    return destination


def _fetch_one(record: dict, repo: str, revision: str, root: Path,
               downloader: Callable) -> dict:
    relative = record["archive_path"]
    destination = _safe_destination(root, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # A unique temporary name is essential when independent CLI processes
    # download the same novel concurrently.
    handle, temporary = tempfile.mkstemp(
        prefix="." + destination.name + ".", suffix=".part", dir=destination.parent)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(handle, "wb") as writer:
            source = Path(downloader(
                repo_id=repo, repo_type="dataset",
                filename=relative, revision=revision))
            with source.open("rb") as reader:
                while True:
                    chunk = reader.read(1024 * 1024)
                    if not chunk:
                        break
                    writer.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        # If an invalid path was introduced during a long network download,
        # fail closed rather than following a changed local symlink.
        if _safe_destination(root, relative) != destination:
            raise ValueError("Download destination changed unexpectedly")
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"id": record["id"], "title": record["title"],
            "path": relative, "sha256": digest.hexdigest(),
            "size": size}


def download_archives(books: list[dict], available: set[str], *,
                      repo: str, revision: str, root: Path,
                      downloader: Callable, workers: int = 3) -> tuple[list[dict], list[dict]]:
    """Return completed manifest entries and one status row for each book.

    Failure of one ZIP never corrupts existing ZIPs or discard earlier success.
    The caller must signal a nonzero exit for any missing/failed archive.
    """
    if not 1 <= workers <= 4:
        raise ValueError("Download workers must be between 1 and 4")
    root = Path(root)
    manifest = []
    rows = [None] * len(books)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for index, book in enumerate(books):
            relative = book.get("archive_path") or ""
            if not relative or relative not in available:
                rows[index] = {"id": book["id"], "title": book["title"],
                               "state": "MISSING", "path": relative,
                               "details": "Remote original.zip absent"}
                continue
            future = pool.submit(_fetch_one, book, repo, revision, root, downloader)
            futures[future] = (index, book)
        for future in as_completed(futures):
            index, book = futures[future]
            try:
                entry = future.result()
                manifest.append(entry)
                rows[index] = {"id": book["id"], "title": book["title"],
                               "state": "DOWNLOADED", "path": entry["path"], "details": ""}
            except Exception as exc:
                # Error details are written locally, not exposed in default
                # console logs. Other in-flight downloads may still finish.
                rows[index] = {"id": book["id"], "title": book["title"],
                               "state": "FAILED", "path": book["archive_path"],
                               "details": f"{type(exc).__name__}: {exc}"}
    return sorted(manifest, key=lambda item: item["path"]), rows
