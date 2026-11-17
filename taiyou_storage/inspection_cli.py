"""Local-only CLI and reports for the private novel inspection toolkit."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import sys

from .core import DEFAULT_REPO
from .console_summary import print_summary
from .inspection import HFReadOnly, compare_retriever, scan
from .inspection_cache import inspection_cache_dir

INVENTORY_COLUMNS = ["novel_id", "title", "author", "source_url",
                     "catalogue_chapter_count", "stored_chapter_count",
                     "chapter_ranges", "missing_chapters", "duplicate_positions", "epub_sha256",
                     "verification_status", "verification_reason"]
COVER_COLUMNS = ["title", "standalone_cover", "cover_validation",
                 "recommended_action", "cover_reason", "source_url", "novel_id"]
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
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore",
                            lineterminator="\n")  # Avoid CRCRLF blank rows on Windows
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


def cover_audit_rows(novels: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separate an actionable missing-cover shortlist from the full audit.

    Listing evidence proves a file is present, not that the pixels decode.
    A missing standalone cover is NOT proof that an EPUB lacks an embedded cover.
    """
    full, attention = [], []
    for novel in novels:
        presence = novel.get("standalone_cover_status", "UNKNOWN")
        verified = novel.get("cover_status", "UNVERIFIED")
        is_attention = True
        if presence == "PRESENT" and verified in {"AVAILABLE", "UNVERIFIED"}:
            action = ("None; image decoded successfully" if verified == "AVAILABLE"
                      else "Cover file exists; optional deep scan validates image")
            is_attention = False
        elif presence == "ABSENT" and verified == "EMBEDDED_ONLY":
            action = "No standalone cover; extract verified embedded EPUB cover if needed"
        elif presence == "ABSENT":
            action = "No standalone cover; check EPUB or retrieve authentic cover"
        elif presence == "BROKEN_REFERENCE":
            action = "Repair the catalogue cover path or restore the referenced image"
        elif presence == "POSSIBLE_PLACEHOLDER":
            action = "Review provenance; replace generated or placeholder artwork"
        elif presence == "MULTIPLE_FILES":
            action = "Choose the authentic image and link it in the catalogue"
        elif verified == "BROKEN":
            action = "Replace the corrupt or unreadable cover image"
        else:
            action = "Review cover evidence or run --mode deep"
        entry = {
            "title": novel.get("title", ""),
            "standalone_cover": presence,
            "cover_validation": verified,
            "recommended_action": action,
            "cover_reason": novel.get("cover_reason", ""),
            "source_url": novel.get("source_url", ""),
            "novel_id": novel.get("novel_id", ""),
        }
        full.append(entry)
        if is_attention:
            attention.append(entry)
    return full, attention


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
    parser = argparse.ArgumentParser(description="Private HF novel inspection: lightweight manifests by default")
    parser.add_argument("command", choices=("inventory", "covers", "compare", "integrity", "health", "checks"))
    parser.add_argument("--repo", default=os.environ.get("HF_DATASET_REPO", DEFAULT_REPO))
    parser.add_argument("--mode", choices=("quick", "manifest", "deep"))
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--workers", type=int, choices=range(1, 5), metavar="1..4", default=3)
    parser.add_argument("--verbose", action="store_true",
                        help="Print individual findings in addition to saving complete reports")
    parser.add_argument("--registry", type=Path, help="Local Novel Retriever downloaded_novels.json")
    parser.add_argument("--planned", type=Path, action="append", default=[],
                        help="Local planned novel JSON; repeat for several lists")
    parser.add_argument("--retriever-root", type=Path,
                        help="Local Novel Retriever checkout containing downloaded_novels.json")
    args = parser.parse_args(argv)
    mode = args.mode or "manifest"
    directory = Path(args.reports_dir)
    try:
        client = backend if backend is not None else HFReadOnly(args.repo, cache_dir=inspection_cache_dir(directory))
        result = scan(client, mode, directory / ".inspection-cache", args.workers)
        novels, issues = result["novels"], result["issues"]
        reports = []
        metrics = {"Total novels": len(novels)}
        title = {"inventory": "Chapter inventory", "covers": "Cover audit",
                 "compare": "Novel Retriever comparison", "integrity": "Library integrity",
                 "health": "Library health", "checks": "Private library checks"}[args.command]
        if args.command in ("inventory", "checks"):
            _csv(directory / "novel-inventory.csv", novels, INVENTORY_COLUMNS)
            _json(directory / "novel-inventory.json",
                  {"schema_version": 1, "revision": result["revision"], "mode": mode, "novels": novels})
            coverage = Counter(row.get("verification_status", "UNVERIFIED") for row in novels)
            metrics.update({
                "Verified complete": coverage["VERIFIED_COMPLETE"],
                "Verified ranges": coverage["VERIFIED_RANGE"],
                "Incomplete chapter coverage": coverage["INCOMPLETE"],
                "Unverified chapter coverage": coverage["UNVERIFIED"],
                "Novels with detected chapter gaps": sum(bool(row.get("missing_chapters")) for row in novels),
            })
            reports += [directory / "novel-inventory.csv", directory / "novel-inventory.json"]
        if args.command in ("covers", "checks"):
            all_covers, attention = cover_audit_rows(novels)
            _csv(directory / "cover-audit.csv", all_covers, COVER_COLUMNS)
            _csv(directory / "missing-covers.csv", attention, COVER_COLUMNS)
            presence = Counter(row["standalone_cover"] for row in all_covers)
            metrics.update({
                "Standalone cover files present": presence["PRESENT"],
                "Missing standalone cover files": presence["ABSENT"],
                "Other cover issues to review": len(attention) - presence["ABSENT"],
                "Total requiring cover attention": len(attention),
            })
            reports += [directory / "missing-covers.csv", directory / "cover-audit.csv"]
        if args.command in ("integrity", "checks"):
            _csv(directory / "integrity-report.csv", issues, ISSUE_COLUMNS)
            _json(directory / "integrity-report.json",
                  {"schema_version": 1, "revision": result["revision"], "mode": mode, "issues": issues})
            severities = Counter(item.get("severity", "") for item in issues)
            metrics.update({
                "Integrity findings": len(issues),
                "High-severity findings": severities["HIGH"],
                "Other findings": len(issues) - severities["HIGH"],
                "Potential duplicate pairs": len(result["duplicate_candidates"]),
            })
            reports += [directory / "integrity-report.csv", directory / "integrity-report.json"]
        if args.command == "compare":
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
            states = Counter(item["state"] for item in comparison["records"])
            metrics.update({
                "Retriever entries compared": len(comparison["records"]),
                "Already in library": states["ALREADY_IN_HF"],
                "Downloaded, not uploaded": states["DOWNLOADED_NOT_UPLOADED"],
                "Partially downloaded": states["PARTIALLY_DOWNLOADED"],
                "Not yet downloaded": states["TO_DOWNLOAD"],
                "Ambiguous matches": states["AMBIGUOUS"],
            })
            reports += [directory / "retriever-comparison.csv",
                       directory / "retriever-comparison.json",
                       directory / "retriever-exclusions.json"]
        if args.command in ("health", "checks"):
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
            presence = Counter(row.get("standalone_cover_status", "UNKNOWN") for row in novels)
            metrics.update({
                "Integrity findings": health["metrics"]["integrity_issues"],
                "Potential duplicate pairs": health["metrics"]["duplicate_candidates"],
                "Missing standalone cover files": presence["ABSENT"],
                "Unverified chapter coverage": health["metrics"]["unknown_chapter_coverage"],
            })
            reports += [directory / "library-health.html",
                       directory / "library-health.csv",
                       directory / "library-health.json"]
        if args.command == "checks":
            # The combined check runs one immutable-revision scan and writes
            # the same detailed reports as the local individual utilities.
            # These counts are suitable for a public Actions job summary.
            metrics["Potential duplicate pairs"] = len(result["duplicate_candidates"])
            metrics["Integrity findings"] = len(issues)
            metrics["Missing standalone cover files"] = sum(
                row.get("standalone_cover_status") == "ABSENT" for row in novels)
            metrics["Covers requiring attention"] = len(attention)
        metrics["Inspection mode"] = mode
        if result.get("interrupted"):
            metrics["Scan interrupted"] = "Yes; results may be incomplete"
        if args.verbose:
            for issue in issues:
                print(f"[{issue['severity']}] {issue['code']} ({issue['novel_id']}): "
                      f"{issue['evidence']}")
            if args.command == "compare":
                for entry in comparison["records"]:
                    print(f"[{entry['state']}] {entry['title']}")
        print_summary(title, metrics, reports=reports,
                      note=("Remote presence is not verified image/EPUB integrity."
                            if mode != "deep" else
                            "Deep checks can still yield unverified evidence."))
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
