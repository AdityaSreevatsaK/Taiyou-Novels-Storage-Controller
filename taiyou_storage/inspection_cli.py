"""Local-only CLI and reports for the private novel inspection toolkit."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import sys

from .core import DEFAULT_REPO
from .inspection import HFReadOnly, compare_retriever, scan

INVENTORY_COLUMNS = ["novel_id", "title", "author", "source_url",
                     "catalogue_chapter_count", "stored_chapter_count",
                     "chapter_ranges", "missing_chapters", "duplicate_positions", "epub_sha256",
                     "verification_status", "verification_reason"]
COVER_COLUMNS = ["novel_id", "title", "source_url", "cover_status", "cover_reason"]
ISSUE_COLUMNS = ["novel_id", "code", "severity", "evidence", "recommended_action"]
COMPARE_COLUMNS = ["title", "author", "source_url", "state", "hf_ids",
                   "reason", "download_recorded", "download_ranges"]
HEALTH_COLUMNS = ["metric", "value"]


def _atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(value, encoding="utf-8")
    tmp.replace(path)


def _json(path: Path, value: object) -> None:
    _atomic(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _csv(path: Path, records: list[dict], fields: list[str]) -> None:
    from io import StringIO
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow({key: "; ".join(map(str, v)) if isinstance(v, list) else v
                         for key, v in record.items() if key in fields})
    _atomic(path, "\ufeff" + buffer.getvalue())


def _load_records(path: Path) -> list[dict]:
    content = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(content, list):
        records = content
    elif isinstance(content, dict):
        records = content.get("novels", content.get("books", content.get("items", [])))
    else:
        raise ValueError("Expected JSON list or object containing novels/books/items")
    if not isinstance(records, list):
        raise ValueError("Invalid novel list: " + str(path))
    return [r for r in records if isinstance(r, dict)]


def health_report(result: dict, previous: dict | None = None) -> dict:
    books = result["novels"]
    issues = result["issues"]
    covers = [r.get("cover_status") for r in books]
    verified = sum(r.get("verification_status") == "VERIFIED_COMPLETE" for r in books)
    metrics = {
        "total_novels": len(books),
        "verified_complete": verified,
        "incomplete_chapter_coverage": sum(r.get("verification_status") == "INCOMPLETE" for r in books),
        "unknown_chapter_coverage": sum(r.get("verification_status") in ("UNVERIFIED", "VERIFIED_RANGE")
                                        for r in books),
        "verified_ranges_not_confirmed_complete": sum(r.get("verification_status") == "VERIFIED_RANGE"
                                                       for r in books),
        "missing_covers": covers.count("MISSING"),
        "broken_covers": covers.count("BROKEN"),
        "unverified_covers": covers.count("UNVERIFIED"),
        "embedded_only_covers": covers.count("EMBEDDED_ONLY"),
        "missing_metadata": sum(issue["code"] == "MISSING_METADATA" for issue in issues),
        "duplicate_candidates": len(result["duplicate_candidates"]),
        "broken_storage_references": sum(issue["code"] in {
            "MISSING_EPUB", "MISSING_ARCHIVE", "INVALID_CATALOGUE_PATH", "ORPHAN_NOVEL_DIRECTORY"}
                                         for issue in issues),
        "total_storage_bytes": result["total_storage_bytes"],
        "storage_size_verified": result["storage_size_verified"],
        "integrity_issues": len(issues),
    }
    old = (previous.get("metrics", {}) if isinstance(previous, dict) and
           previous.get("mode") == result["mode"] else {})
    changes = {key: (value - old[key]) for key, value in metrics.items()
               if isinstance(value, int) and not isinstance(value, bool) and
               isinstance(old.get(key), int) and not isinstance(old[key], bool)}
    return {"schema_version": 1, "revision": result["revision"], "mode": result["mode"],
            "scanned_at_utc": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics, "changes_since_previous_scan": changes}


def _render_html(health: dict, result: dict) -> str:
    h = health["metrics"]
    metrics = "".join("<tr><th>" + escape(k.replace("_", " ").title()) + "</th><td>" +
                      escape(str(v)) + "</td></tr>" for k, v in h.items())
    changes = "".join("<tr><th>" + escape(k.replace("_", " ").title()) +
                      "</th><td>" + escape(f"{v:+d}") + "</td></tr>"
                      for k, v in health["changes_since_previous_scan"].items())
    issues = "".join("<tr><td>" + escape(str(e.get("novel_id", ""))) + "</td><td>" +
                     escape(e["severity"]) + "</td><td>" + escape(e["code"]) +
                     "</td><td>" + escape(e["recommended_action"]) + "</td></tr>"
                     for e in result["issues"])
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Private Library Health</title><style>'
            'body{font:16px system-ui,sans-serif;max-width:1100px;margin:auto;padding:2rem;'
            'background:#f5f1e8;color:#252a27}table{width:100%;border-collapse:collapse;'
            'background:white;margin:1rem 0 2rem}th,td{padding:.65rem;text-align:left;'
            'border-bottom:1px solid #ddd;overflow-wrap:anywhere}h1,h2{color:#254e40}'
            'small{color:#555}</style></head><body><h1>Private Library Health</h1><p><small>'
            'Local report only. Never publish this file.</small></p><p>Revision: ' +
            escape(health["revision"]) + ' | Scan: ' + escape(health["mode"]) +
            '</p><h2>Summary</h2><table>' + metrics + '</table><h2>Changes since previous scan</h2>'
            '<table>' + (changes or '<tr><td>No previous scan</td></tr>') +
            '</table><h2>Integrity findings</h2><table><tr><th>Novel ID</th>'
            '<th>Severity</th><th>Issue</th><th>Recommended action</th></tr>' +
            (issues or '<tr><td colspan="4">No findings at this inspection depth</td></tr>') +
            '</table></body></html>')


def run(argv: list[str] | None = None, backend: HFReadOnly | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private, read-only HF novel inspection")
    parser.add_argument("command", choices=("inventory", "covers", "compare", "integrity", "health"))
    parser.add_argument("--repo", default=os.environ.get("HF_DATASET_REPO", DEFAULT_REPO))
    parser.add_argument("--mode", choices=("quick", "deep"))
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--workers", type=int, choices=range(1, 5), metavar="1..4", default=3)
    parser.add_argument("--registry", type=Path, help="Local Novel Retriever downloaded_novels.json")
    parser.add_argument("--planned", type=Path, action="append", default=[],
                        help="Local planned novel JSON; repeat for several lists")
    parser.add_argument("--retriever-root", type=Path,
                        help="Local Novel Retriever checkout containing downloaded_novels.json")
    args = parser.parse_args(argv)
    mode = args.mode or ("quick" if args.command == "compare" else "deep")
    directory = Path(args.reports_dir)
    try:
        client = backend if backend is not None else HFReadOnly(args.repo)
        result = scan(client, mode, directory / ".inspection-cache", args.workers)
        novels, issues = result["novels"], result["issues"]
        if args.command == "inventory":
            _csv(directory / "novel-inventory.csv", novels, INVENTORY_COLUMNS)
            _json(directory / "novel-inventory.json",
                  {"schema_version": 1, "revision": result["revision"], "mode": mode, "novels": novels})
        elif args.command == "covers":
            _csv(directory / "missing-covers.csv", novels, COVER_COLUMNS)
        elif args.command == "integrity":
            _csv(directory / "integrity-report.csv", issues, ISSUE_COLUMNS)
            _json(directory / "integrity-report.json",
                  {"schema_version": 1, "revision": result["revision"], "mode": mode, "issues": issues})
        elif args.command == "compare":
            registry_path = args.registry
            if registry_path is None and args.retriever_root:
                registry_path = args.retriever_root / "downloaded_novels.json"
            plans = list(args.planned)
            if args.retriever_root:
                candidate = args.retriever_root / "curated_novels.json"
                if candidate.exists() and candidate not in plans:
                    plans.append(candidate)
            if not registry_path and not plans:
                raise ValueError("Provide --registry, --planned, or --retriever-root pointing to a local checkout")
            registry = {"novels": _load_records(registry_path)} if registry_path else None
            planned = [record for file in plans for record in _load_records(file)]
            comparison = compare_retriever(novels, registry, planned)
            _csv(directory / "retriever-comparison.csv", comparison["records"], COMPARE_COLUMNS)
            _json(directory / "retriever-comparison.json",
                  {"revision": result["revision"], **comparison})
            _json(directory / "retriever-exclusions.json", comparison["exclusions"])
        elif args.command == "health":
            last_file = directory / "library-health.json"
            try:
                old = json.loads(last_file.read_text(encoding="utf-8")) if last_file.exists() else None
            except (OSError, ValueError):
                old = None
            health = health_report(result, old)
            _json(last_file, health)
            _csv(directory / "library-health.csv",
                 [{"metric": k, "value": v} for k, v in health["metrics"].items()], HEALTH_COLUMNS)
            _atomic(directory / "library-health.html", _render_html(health, result))
        print(f"Completed {mode} inspection at revision {result['revision'][:12]}; "
              f"{len(novels)} novels, {len(issues)} findings. Private reports: {directory}")
        print("Coverage is VERIFIED_COMPLETE only when source declares completion and files verify.")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
