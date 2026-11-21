"""Preview-first cleanup of local files used by private HF inspection tools.

The new owned cache is safe to remove. For older scans, optional legacy mode
removes only cached novel EPUB/ZIP/cover entries from the specified private
dataset, using huggingface_hub's reference-aware delete_files strategy.
Unreferenced blobs may also be reclaimed; blobs still needed elsewhere survive.
Neither mode connects to or modifies the Hugging Face dataset.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import shutil
import sys

from .core import DEFAULT_REPO
from .console_summary import print_summary
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
        strategy = None
        legacy_count = 0
        legacy_estimate = "Not selected"
        if args.legacy_shared_cache:
            from huggingface_hub import scan_cache_dir
            info = scan_cache_dir(args.shared_cache_dir)
            targets = _legacy_targets(info, args.repo)
            legacy_count = len(targets)
            if legacy_count:
                if not hasattr(info, "delete_files"):
                    raise RuntimeError("Upgrade huggingface_hub to support safe per-file cache deletion")
                strategy = info.delete_files(*targets)
                legacy_estimate = strategy.expected_freed_size_str

        before = {
            "Owned inspection files": isolated_count,
            "Owned bytes": f"{isolated_size:,}",
            "Legacy cache entries": legacy_count,
            "Legacy potential space": legacy_estimate,
        }
        if not args.apply:
            print_summary("Local cache cleanup preview", before,
                          note="Local cache only. Nothing deleted; use --apply to confirm.",
                          status="PREVIEW")
            return 0
        if not (isolated_count or legacy_count):
            print_summary("Local cache cleanup completed", before,
                          note="No selected local files remain. Private HF data unchanged.",
                          status="NO CHANGES")
            return 0
        print_summary("Local cache cleanup preview", before,
                      note="Close running inspection tools before deleting local cache files.",
                      status="AWAITING CONFIRMATION")
        if not sys.stdin.isatty():
            raise RuntimeError("Deletion requires an interactive console")
        if input("Type DELETE LOCAL CACHE to confirm: ").strip() != "DELETE LOCAL CACHE":
            print_summary("Local cache cleanup cancelled", before,
                          note="No local or remote files deleted.", status="CANCELLED")
            return 0
        if isolated.exists():
            validate_owned_cache(isolated, args.repo)
            shutil.rmtree(isolated)
        if strategy is not None:
            strategy.execute()
        # Re-scan, rather than claiming that no shared references remain.
        legacy_remaining = 0
        if args.legacy_shared_cache:
            from huggingface_hub import scan_cache_dir
            legacy_remaining = len(_legacy_targets(
                scan_cache_dir(args.shared_cache_dir), args.repo))
        print_summary("Local cache cleanup completed", {
            "Owned files removed": isolated_count,
            "Owned bytes removed": f"{isolated_size:,}",
            "Legacy entries removed": legacy_count,
            "Legacy potential space": legacy_estimate,
            "Matching entries remaining": legacy_remaining,
        }, note=("The legacy figure is an estimate; shared HF blobs may be retained. "
                  "Private Hugging Face dataset unchanged."),
            status="COMPLETED")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
