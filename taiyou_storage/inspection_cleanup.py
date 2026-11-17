"""Preview-first cleanup of local files used by private HF inspection tools.

The new owned cache is safe to remove. For older scans, optional legacy mode
removes only cached novel EPUB/ZIP/cover entries from the specified private
dataset, using huggingface_hub's reference-aware delete_files strategy.
Neither mode connects to or modifies the Hugging Face dataset.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import shutil
import sys

from .core import DEFAULT_REPO
from .inspection_cache import cache_usage, inspection_cache_dir, validate_owned_cache

NOVEL_NAMES = {"source.epub", "original.zip", "cover.jpg", "cover.jpeg", "cover.png", "cover.webp"}


def _legacy_targets(info, repo_id: str):
    """Only novel binaries and covers; never catalogue, manifests or other repos."""
    files = []
    for repo in info.repos:
        if repo.repo_type != "dataset" or repo.repo_id != repo_id:
            continue
        for revision in repo.revisions:
            for entry in revision.files:
                try:
                    relative = entry.file_path.relative_to(revision.snapshot_path)
                    parts = PurePosixPath(relative.as_posix()).parts
                    if (len(parts) >= 4 and parts[:2] == ("data", "novels")
                            and parts[-1].casefold() in NOVEL_NAMES):
                        files.append(entry)
                except (AttributeError, TypeError, ValueError):
                    pass
    return files


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview then safely delete local inspection downloads, NEVER HF novels")
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--repo", default=os.environ.get("HF_DATASET_REPO", DEFAULT_REPO))
    parser.add_argument("--legacy-shared-cache", action="store_true",
                        help="Also clean older novel files in global HF cache; can affect other local tools")
    parser.add_argument("--shared-cache-dir", type=Path,
                        help="Override older HF cache location (only with --legacy-shared-cache)")
    parser.add_argument("--apply", action="store_true",
                        help="Delete after interactive confirmation; preview is default")
    args = parser.parse_args(argv)
    if args.shared_cache_dir and not args.legacy_shared_cache:
        parser.error("--shared-cache-dir requires --legacy-shared-cache")
    try:
        isolated = inspection_cache_dir(args.reports_dir)
        if isolated.exists() or isolated.is_symlink():
            validate_owned_cache(isolated, args.repo)
            isolated_count, isolated_size = cache_usage(isolated)
        else:
            isolated_count, isolated_size = 0, 0
        print(f"Owned inspection cache: {isolated}")
        print(f"  {isolated_count} local files; {isolated_size:,} bytes on disk")
        strategy = None
        legacy_count = 0
        if args.legacy_shared_cache:
            from huggingface_hub import scan_cache_dir
            info = scan_cache_dir(args.shared_cache_dir)
            targets = _legacy_targets(info, args.repo)
            legacy_count = len(targets)
            if legacy_count:
                if not hasattr(info, "delete_files"):
                    raise RuntimeError("Upgrade huggingface_hub to support safe per-file cache deletion")
                strategy = info.delete_files(*targets)
            print(f"Legacy HF shared cache: {legacy_count} matching novel binary/cover entries")
            if strategy is not None:
                print(f"  Estimated space recoverable: {strategy.expected_freed_size_str}")
                print("  WARNING: these entries may also have been cached by other local tools.")
        else:
            print("Older shared-cache downloads were not selected.")
            print("  Add --legacy-shared-cache to preview those previous EPUB/ZIP/cover downloads.")
        if not args.apply:
            print("PREVIEW ONLY. No files have been deleted. Add --apply to delete after confirmation.")
            return 0
        if not (isolated_count or legacy_count):
            print("No selected local downloads to remove.")
            return 0
        if not sys.stdin.isatty():
            raise RuntimeError("Deletion requires an interactive console")
        print("Close all active novel inspection or migration processes before deleting cache files.")
        if input("Type DELETE LOCAL CACHE to confirm: ").strip() != "DELETE LOCAL CACHE":
            print("Cancelled; no files deleted.")
            return 0
        if isolated.exists():
            validate_owned_cache(isolated, args.repo)
            shutil.rmtree(isolated)
            print("Removed owned inspection download cache.")
        if strategy is not None:
            strategy.execute()
            print(f"Removed {legacy_count} selected legacy cache entries (shared blobs preserved).")
        print("Private Hugging Face dataset unchanged.")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
