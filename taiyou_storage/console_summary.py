"""Consistent, concise output for local controller commands.

Detailed novel records belong in ignored reports or opt-in --verbose output.
Never suppress a failure, a confirmation requirement or a safety warning.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path


def print_start(title: str, *, mode: str = "RUN") -> None:
    """Announce the operation once; use fixed application-authored titles."""
    print()
    print(f"=== {title} ===")
    print(f"  Mode   : {mode.upper()}")
    print("  Status : Started")
    print()


def print_end(title: str, *, status: str = "COMPLETED",
              detail: str | None = None) -> None:
    """Close a command even when there are no numerical metrics."""
    print()
    print(f"=== {title} | END ===")
    print(f"  Result : {status.upper()}")
    if detail:
        print(f"  Note   : {detail}")
    print()


def print_summary(title: str, metrics: Mapping[str, object], *,
                  reports: Iterable[str | Path] = (), note: str | None = None,
                  status: str | None = None) -> None:
    """Show one labelled summary and an explicit result, not per-file chatter.

    The original heading and metric labels are retained for compatible
    launchers, tests and users. Preview status is never called an upload.
    """
    state = status or (
        "BLOCKED" if "blocked" in title.casefold() else
        "PREVIEW" if "preview" in title.casefold() else
        "COMPLETED"
    )
    print()
    print(f"=== {title} ===")
    width = max((len(str(label)) for label in metrics), default=0)
    for label, value in metrics.items():
        print(f"  {label:<{width}} : {value}")
    paths = tuple(reports)
    if paths:
        print("  Detailed reports:")
        for path in paths:
            print(f"    {path}")
    if note:
        print(f"  Note: {note}")
    print(f"  Result: {state}")
    print(f"=== End: {title} ===")
    print()
