"""Run all PRIVATE Hugging Face inspection checks on GitHub Actions safely.

This runner never uploads per-novel reports as public Actions artifacts, and
never prints private titles, IDs, URLs, filenames or raw exception messages.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from .inspection_cli import run as inspection_run


def _counts(report_dir: Path) -> dict[str, int]:
    inventory = json.loads((report_dir / "novel-inventory.json").read_text(encoding="utf-8"))
    integrity = json.loads((report_dir / "integrity-report.json").read_text(encoding="utf-8"))
    health = json.loads((report_dir / "library-health.json").read_text(encoding="utf-8"))
    if not isinstance(inventory.get("novels"), list) or not isinstance(integrity.get("issues"), list):
        raise ValueError("Invalid inspection report")
    novels, issues = inventory["novels"], integrity["issues"]
    metrics = health["metrics"]
    if metrics.get("total_novels") != len(novels) or metrics.get("integrity_issues") != len(issues):
        raise ValueError("Inconsistent inspection reports")
    covers = Counter(str(n.get("standalone_cover_status") or "UNKNOWN") for n in novels)
    statuses = Counter(str(n.get("verification_status") or "UNVERIFIED") for n in novels)
    severity = Counter(str(issue.get("severity") or "") for issue in issues)
    return {
        "Total novels": len(novels),
        "Standalone covers present": covers["PRESENT"],
        "Standalone covers absent": covers["ABSENT"],
        "Other cover listing concerns": sum(covers[k] for k in (
            "BROKEN_REFERENCE", "POSSIBLE_PLACEHOLDER", "MULTIPLE_FILES", "UNKNOWN")),
        "Potential duplicate pairs": int(metrics.get("duplicate_candidates", 0)),
        "Integrity findings": len(issues),
        "High-severity findings": severity["HIGH"],
        "Verified complete": statuses["VERIFIED_COMPLETE"],
        "Verified ranges": statuses["VERIFIED_RANGE"],
        "Incomplete coverage": statuses["INCOMPLETE"],
        "Unverified coverage": statuses["UNVERIFIED"],
    }


def run(argv: list[str] | None = None, *, backend=None) -> int:
    parser = argparse.ArgumentParser(description="Counts-only private HF checks for Actions")
    parser.add_argument("--mode", choices=("manifest", "deep"), default="manifest")
    args = parser.parse_args(argv)
    if backend is None and not os.environ.get("HF_TOKEN"):
        print("ERROR: Hugging Face read token not configured. No check was run.", file=sys.stderr)
        return 2

    # Keep detailed reports and raw errors only in an ephemeral local directory.
    # GitHub can expose workflow logs, step summaries and uploaded artifacts.
    root = os.environ.get("RUNNER_TEMP")
    with TemporaryDirectory(prefix="taiyou-private-checks-", dir=root) as temporary:
        reports = Path(temporary) / "reports"
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            code = inspection_run(["checks", "--mode", args.mode,
                                   "--reports-dir", str(reports)], backend=backend)
        if code:
            print("ERROR: Private library inspection failed. Sensitive details suppressed.",
                  file=sys.stderr)
            return code
        try:
            metrics = _counts(reports)
            issues = json.loads((reports / "integrity-report.json").read_text(encoding="utf-8"))["issues"]
            interrupted = any(issue.get("code") in {"SCAN_INTERRUPTED", "INSPECTION_FAILED"}
                              for issue in issues)
        except (OSError, KeyError, ValueError, TypeError):
            print("ERROR: Inspection reports could not be verified. Details withheld.",
                  file=sys.stderr)
            return 1

        print("=== Private library checks ===")
        print(f"Inspection mode: {args.mode}")
        for label, value in metrics.items():
            print(f"{label}: {value}")
        print("Detailed reports were kept on the ephemeral runner; no private artifacts uploaded.")
        step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary:
            # Strictly numeric values and fixed, controlled headings only.
            lines = ["## Private library checks", "",
                     f"Mode: `{args.mode}\`", "",
                     "| Check | Count |", "| --- | ---: |"]
            lines.extend(f"| {key} | {value} |" for key, value in metrics.items())
            lines.extend(["", "Results are counts only. No novel titles, IDs or files were published.",
                          "Manifest mode reports uncertain evidence as unverified, not complete.", ""])
            try:
                with open(step_summary, "a", encoding="utf-8") as out:
                    out.write("\n".join(lines) + "\n")
            except OSError:
                print("ERROR: GitHub step summary could not be written.", file=sys.stderr)
                return 1
        if interrupted:
            print("ERROR: The scan did not finish reliably; rerun the check.",
                  file=sys.stderr)
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(run())
