"""Clean, privacy-safe GitHub Actions stdout and Markdown step summaries.

Run a non-interactive controller command, keep its full raw output only on the
ephemeral runner, and expose fixed labels with numeric values to PUBLIC logs.
Do not print private titles, files, URLs, tokens or raw exception text.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import os
import sys

TASKS = {
    "inspection": "Library inspection",
    "readiness": "Remote backup readiness",
    "backup": "Private dataset backup",
    "reports": "Private report export",
    "cover-import": "Cover upload",
    "novel-import": "Novel import",
    "bundle-check": "Novel bundle verification",
    "genre-repair": "Genre metadata repair",
}
METRICS = frozenset({
    "Total novels", "Standalone covers present", "Standalone covers absent",
    "Covers requiring attention", "Potential duplicate pairs", "Integrity findings",
    "High-severity findings", "Verified complete", "Verified ranges",
    "Incomplete coverage", "Unverified coverage", "Other cover listing concerns",
    "Source files", "Objects copied", "Previously verified objects reused",
    "Snapshot verified", "Full novel downloads", "Objects already verified",
    "Objects eligible for remote copy", "Acceptance stage", "Acceptance error code",
    "Acceptance token owner match", "Acceptance HTTP status",
    "Acceptance error origin", "Acceptance harness guard",
    "Verified novel ZIPs", "Verified ZIP bytes",
    "Total novels in library", "Covers in archive", "New covers",
    "Covers to update", "Covers to link", "Unchanged",
    "Missing or unmatched", "Conflicts detected", "Covers uploaded",
    "New novels to upload", "Existing novels to update", "Unchanged novels",
    "Matched local covers", "Updated covers", "Unchanged covers",
    "Local ZIPs found", "Equivalent ZIPs skipped", "HF commit batches",
    "New novels uploaded", "Existing novels updated", "Changes applied",
    "Novels reported", "Title conflicts reported", "Covers changed", "HF commits",
    "Novels updated", "Genres restored", "Descriptions restored",
    "Statuses restored", "Already tagged", "Unknown source",
    "Ambiguous source", "Missing genres",
})
# Strict numeric values are essential: never echo arbitrary command output.
METRIC_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z -]{0,65})\s*:\s*([0-9][0-9,]*)\s*$")


def safe_metrics(payload: str) -> list[tuple[str, str]]:
    """Extract only trusted numeric labels, deduplicating later updates."""
    values: dict[str, str] = {}
    for line in payload.splitlines():
        match = METRIC_LINE.fullmatch(line)
        if match and match.group(1).strip() in METRICS:
            values[match.group(1).strip()] = match.group(2)
    return list(values.items())


def format_summary(task: str, mode: str, code: int,
                   metrics: list[tuple[str, str]]) -> str:
    """Create a small standalone GitHub Actions Markdown result."""
    title = TASKS[task]
    result = "Failed" if code else ("Preview only" if mode == "preview" else "Completed")
    out = [f"### {title}", "",
           f"**Mode:** {mode.capitalize()}  ",
           f"**Result:** {result}", ""]
    if metrics:
        out.extend(["| Metric | Value |", "| --- | ---: |"])
        out.extend(f"| {key} | {value} |" for key, value in metrics)
        out.append("")
    out.append("Full private diagnostics are not published in GitHub Actions.")
    return "\n".join(out) + "\n"


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private-safe concise GitHub command output")
    parser.add_argument("--task", choices=tuple(TASKS), required=True)
    parser.add_argument("--mode", choices=("preview", "apply", "verify"),
                        default="verify")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    # Reject shell invocations and unrecognised binaries. No shell=True ever.
    if len(command) < 3 or command[:2] != [sys.executable, "-m"]:
        # Use portable 'python -m' in GitHub YAML.
        if len(command) < 3 or command[:2] != ["python", "-m"]:
            print("ERROR: Expected an approved Python module command.", file=sys.stderr)
            return 2
    if not command[2].startswith("taiyou_storage."):
        print("ERROR: Controller modules only.", file=sys.stderr)
        return 2
    root = Path(os.environ.get("RUNNER_TEMP", ".")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    log = root / f"taiyou-{args.task}-{args.mode}.log"
    print(f"[START] {TASKS[args.task]} | {args.mode.upper()}", flush=True)
    try:
        with log.open("w", encoding="utf-8") as output:
            result = subprocess.run(command, stdout=output,
                                    stderr=subprocess.STDOUT, check=False)
        # Limit reading and only parse fixed numeric information.
        with log.open(encoding="utf-8", errors="replace") as saved:
            metrics = safe_metrics(saved.read(2 * 1024 * 1024))
        code = result.returncode
    except (OSError, ValueError):
        metrics, code = [], 1
    summary = format_summary(args.task, args.mode, code, metrics)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as destination:
                destination.write(summary)
        except OSError:
            print("ERROR: Could not write GitHub summary.", file=sys.stderr)
            return 1
    for label, value in metrics:
        print(f"  {label}: {value}")
    if code:
        print(f"[END] {TASKS[args.task]} | FAILED (exit code {code})")
        print("::error::Operation stopped. Detailed diagnostics withheld from public logs.")
    else:
        ending = "PREVIEW ONLY" if args.mode == "preview" else "COMPLETED"
        print(f"[END] {TASKS[args.task]} | {ending}")
    return code


if __name__ == "__main__":
    raise SystemExit(run())
