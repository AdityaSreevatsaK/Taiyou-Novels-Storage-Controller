"""Short, consistent terminal summaries for Windows and Python entrypoints.

Full per-novel details belong in private local CSV/JSON reports. Never print
private book titles here unless --verbose explicitly requests them.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path


def print_summary(title: str, metrics: Mapping[str, object], *,
                  reports: Iterable[str | Path] = (), note: str | None = None) -> None:
    print()
    print(f"=== {title} ===")
    width = max((len(str(label)) for label in metrics), default=0)
    for label, value in metrics.items():
        print(f"  {label:<{width}} : {value}")
    paths = tuple(reports)
    if paths:
        print("  Reports:")
        for path in paths:
            print(f"    {path}")
    if note:
        print(f"  Note: {note}")
    print()
