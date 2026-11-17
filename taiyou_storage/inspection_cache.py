"""Owned, isolated Hugging Face download cache for private inspections.

Standard HF caching is shared with unrelated tools. New inspections use a
marked cache under reports/, so the cleaner can remove exactly this cache.
"""
from __future__ import annotations

import json
from pathlib import Path

MARKER = ".taiyou-inspection-cache.json"
FORMAT = "taiyou-inspection-only-v1"
FOLDER = ".inspection-download-cache"


def inspection_cache_dir(reports: Path) -> Path:
    return Path(reports) / FOLDER


def validate_owned_cache(cache: Path, repo: str) -> None:
    if cache.is_symlink() or not cache.is_dir():
        raise ValueError("Inspection cache must be an ordinary directory")
    marker = cache / MARKER
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("Refusing to delete unmarked or linked cache")
    data = json.loads(marker.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != FORMAT or data.get("repo") != repo:
        raise ValueError("Inspection cache marker does not match repository")


def ensure_owned_cache(cache: Path, repo: str) -> Path:
    cache = Path(cache)
    if cache.exists() or cache.is_symlink():
        validate_owned_cache(cache, repo)
    else:
        if cache.parent.is_symlink():
            raise ValueError("Reports directory must not be a symlink")
        cache.mkdir(parents=True, exist_ok=False)
        (cache / MARKER).write_text(
            json.dumps({"format": FORMAT, "repo": repo}, indent=2) + "\n",
            encoding="utf-8",
        )
    return cache


def cache_usage(cache: Path) -> tuple[int, int]:
    """Count file bytes in the owned directory without following symlinks."""
    count, size = 0, 0
    if not cache.is_dir():
        return count, size
    for item in cache.rglob("*"):
        if item.is_file() and not item.is_symlink():
            count += 1
            size += item.stat().st_size
    return count, size
