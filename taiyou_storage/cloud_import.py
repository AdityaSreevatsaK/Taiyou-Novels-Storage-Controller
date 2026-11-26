"""Validate a Novel-Retriever completed export before HF cloud import.

Reads the cross-repository GitHub Actions artifact on the temporary runner.
Never extracts novel ZIP payloads or sends reports/titles to public logs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys

from .core import sha256_file
from .upload import MAX_ZIP

MAX_FILES = 500
MAX_TOTAL_BYTES = 10 * 1024 ** 3
SHA256 = re.compile(r"^[a-f0-9]{64}$")


class BundleError(ValueError):
    pass


def check_bundle(root: Path) -> dict[str, int]:
    """Fail closed unless the manifest exactly enumerates verified local ZIPs."""
    root = root.resolve()
    manifest_path = root / "manifest.json"
    novels_dir = root / "novels"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise BundleError("Completed export manifest is missing")
    if manifest_path.stat().st_size > 10 * 1024 * 1024:
        raise BundleError("Manifest is unexpectedly large")
    if not novels_dir.is_dir() or novels_dir.is_symlink():
        raise BundleError("Completed export has no novels directory")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict):
        raise BundleError("Expected a completed export manifest")
    if manifest.get("conflicting_editions") or manifest.get("invalid_archives"):
        raise BundleError("Export contains conflicting or invalid novels")
    rows = manifest.get("novels")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_FILES:
        raise BundleError("No supported completed-book inventory")
    if manifest.get("exported_novels") != len(rows):
        raise BundleError("Manifest novel count differs from export")
    expected = set()
    size_total = 0
    for entry in rows:
        if not isinstance(entry, dict):
            raise BundleError("Malformed completed-book entry")
        filename = entry.get("file")
        digest = entry.get("zip_sha256") or entry.get("sha256")
        if (not isinstance(filename, str) or
                not SHA256.fullmatch(str(digest))):
            raise BundleError("Book lacks a trustworthy path or checksum")
        name = PurePosixPath(filename)
        if (len(name.parts) != 2 or name.parts[0] != "novels" or
                name.suffix.casefold() != ".zip" or
                any(part in (".", "..", "") or "\\" in part for part in name.parts)):
            raise BundleError("Unexpected book path in export")
        if filename in expected:
            raise BundleError("Export lists the same novel file twice")
        expected.add(filename)
        book = root / name.parts[0] / name.parts[1]
        if (not book.is_file() or book.is_symlink() or
                book.resolve().parent != novels_dir.resolve()):
            raise BundleError("Expected novel ZIP not found or is linked")
        size = book.stat().st_size
        if not 0 < size <= MAX_ZIP:
            raise BundleError("Novel ZIP exceeds uploader's safety budget")
        size_total += size
        if size_total > MAX_TOTAL_BYTES:
            raise BundleError("Export exceeds cloud runner's 10 GiB budget")
        if isinstance(entry.get("bytes"), int) and size != entry["bytes"]:
            raise BundleError("Export ZIP size does not match original manifest")
        if sha256_file(book) != digest:
            raise BundleError("Novel ZIP content differs from export SHA-256")

    present = set()
    for path in novels_dir.iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".zip":
            raise BundleError("Unexpected file in completed novels folder")
        present.add("novels/" + path.name)
    if present != expected:
        raise BundleError("Novel files and manifest list differ")
    # An exporter can optionally supply cover images in covers/. The main
    # controller will verify their image bytes and identity before uploading.
    # Non-empty unrecognised image filenames are conflicts, not guessed matches.
    covers_dir = root / "covers"
    if covers_dir.is_symlink() or (covers_dir.exists() and not covers_dir.is_dir()):
        raise BundleError("Invalid covers directory")
    if covers_dir.is_dir():
        for candidate in covers_dir.rglob("*"):
            if candidate.is_symlink():
                raise BundleError("Symlink inside completed cover export")
            if candidate.is_file():
                if (candidate.suffix.casefold() not in {".jpg", ".jpeg", ".png", ".webp"}
                        or not 0 < candidate.stat().st_size <= 12 * 1024 * 1024):
                    raise BundleError("Unexpected or oversized image in completed cover export")
    return {"Verified novel ZIPs": len(expected), "Verified ZIP bytes": size_total}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify completed Novel-Retriever ZIPs without publishing titles")
    parser.add_argument("artifact_root", type=Path)
    args = parser.parse_args(argv)
    try:
        result = check_bundle(args.artifact_root)
        for name, count in result.items():
            print(f"{name}: {count}")
        return 0
    except (BundleError, OSError, ValueError, KeyError):
        print("ERROR: Completed export integrity validation failed. No HF write allowed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
