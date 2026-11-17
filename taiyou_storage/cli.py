"""Read-only management CLI for Taiyou's private Hugging Face dataset."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys

from .console_summary import print_summary
from .core import (DEFAULT_REPO, StorageError, conflicts, load_remote, local_epub_id,
                   rows, sha256_file, write_csv)


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Taiyou novels storage controller")
    parser.add_argument("--repo", default=os.environ.get("HF_DATASET_REPO", DEFAULT_REPO))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="Export catalogue CSV").add_argument("--output", default="reports/novels.csv")
    sub.add_parser("conflicts", help="Export exact/normalised title collisions").add_argument("--output", default="reports/conflicts.csv")
    sub.add_parser("backup", help="Save a dated copy of the catalogue")
    download = sub.add_parser("download", help="Download all remote original.zip archives")
    download.add_argument("--destination", default="downloads")
    download.add_argument("--workers", type=int, choices=range(1, 5), default=3,
                          metavar="1..4", help="Bound concurrent ZIP downloads (default 3)")
    sync = sub.add_parser("status", help="Compare local EPUB hash IDs to remote catalogue IDs")
    sync.add_argument("--folder", default="novels")
    for command_parser in sub.choices.values():
        command_parser.add_argument("--verbose", action="store_true",
                                    help="Show individual records as well as the summary")
    args = parser.parse_args(argv)
    try:
        books, revision = load_remote(args.repo)
        metrics = {"Total novels": len(books)}
        reports = []
        note = None
        if args.command == "list":
            data = rows(books)
            write_csv(Path(args.output), data, ["id", "title", "author", "chapters", "epub_path", "archive_path"])
            metrics["Catalogue entries exported"] = len(data)
            reports = [args.output]
            title = "Novel catalogue"
        elif args.command == "conflicts":
            data = conflicts(books)
            write_csv(Path(args.output), data, ["type", "first_title", "first_id", "second_title", "second_id"])
            metrics["Conflicts detected (pairs)"] = len(data)
            metrics["Exact-title pairs"] = sum(row["type"] == "exact" for row in data)
            metrics["Normalised-title pairs"] = sum(row["type"] == "normalised" for row in data)
            if args.verbose:
                for row in data:
                    print(f"[{row['type']}] {row['first_title']} <> {row['second_title']}")
            reports = [args.output]
            title = "Novel title conflicts"
        elif args.command == "backup":
            from huggingface_hub import hf_hub_download
            source = hf_hub_download(repo_id=args.repo, repo_type="dataset",
                                     filename="data/library.json", revision=revision)
            dest = Path("backups") / f"library-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{revision[:12]}.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(Path(source).read_bytes())
            metrics["Catalogue backup created"] = "Yes"
            reports = [dest]
            title = "Catalogue backup"
        elif args.command == "download":
            from huggingface_hub import HfApi, hf_hub_download
            from .downloads import download_archives
            api = HfApi()
            available = set(api.list_repo_files(
                repo_id=args.repo, repo_type="dataset", revision=revision))
            inventory = rows(books)
            manifest, download_rows = download_archives(
                inventory, available, repo=args.repo, revision=revision,
                root=Path(args.destination), downloader=hf_hub_download,
                workers=args.workers)
            if args.verbose:
                for row in download_rows:
                    print(f"[{row['state']}] {row['title']}: {row['details']}")
            failures = sum(row["state"] == "FAILED" for row in download_rows)
            missing = sum(row["state"] == "MISSING" for row in download_rows)
            root = Path(args.destination)
            root.mkdir(parents=True, exist_ok=True)
            # A partial run is clearly marked, never advertised as a complete
            # export. Already downloaded ZIP files remain available for retry.
            summary = {"repo": args.repo, "revision": revision,
                       "complete": not (failures or missing),
                       "expected_novels": len(inventory),
                       "missing": missing, "failed": failures, "files": manifest}
            manifest_path = root / "manifest.json"
            staged = root / ".manifest.json.part"
            try:
                staged.write_text(json.dumps(summary, ensure_ascii=False,
                                             indent=2) + "\n", encoding="utf-8")
                staged.replace(manifest_path)
            finally:
                staged.unlink(missing_ok=True)
            report_path = root / "download-report.csv"
            write_csv(report_path, download_rows,
                      ["id", "title", "state", "path", "details"])
            metrics.update({
                "Archives downloaded": len(manifest),
                "Archives missing": missing,
                "Failed downloads": failures,
                "Complete export": "Yes" if not (failures or missing) else "No",
            })
            reports = [manifest_path, report_path]
            title = "Novel ZIP download"
            note = ("Any missing or failed archive makes this an incomplete export. "
                    "Successful ZIPs are retained for retry.")
        elif args.command == "status":
            folder = Path(args.folder)
            if not folder.is_dir():
                raise StorageError(f"Local folder does not exist: {folder}")
            remote_ids = {b["id"] for b in books}
            matches = []
            for path in sorted(folder.glob("*.zip")):
                try:
                    ident = local_epub_id(path)
                    flag = "EPUB-ID-EXISTS" if ident in remote_ids else "EPUB-ID-NEW"
                    matches.append({"file": path.name, "epub_id": ident, "state": flag,
                                    "details": "ZIP contents not compared"})
                    if args.verbose:
                        print(f"[{flag}] {path.name} ({ident})")
                except Exception as exc:
                    matches.append({"file": path.name, "epub_id": "", "state": "INVALID",
                                    "details": str(exc)})
                    if args.verbose:
                        print(f"[INVALID] {path.name}: {exc}")
            report = Path("reports/local-sync-status.csv")
            write_csv(report, matches, ["file", "epub_id", "state", "details"])
            metrics.update({
                "Local ZIPs scanned": len(matches),
                "Matching EPUB IDs": sum(x["state"] == "EPUB-ID-EXISTS" for x in matches),
                "New EPUB IDs": sum(x["state"] == "EPUB-ID-NEW" for x in matches),
                "Invalid ZIPs": sum(x["state"] == "INVALID" for x in matches),
            })
            reports = [report]
            title = "Local sync status"
            note = "ID matches do not prove ZIP content equality."
        print_summary(title, metrics, reports=reports, note=note)
        if args.command == "download" and (failures or missing):
            return 2
        return 0
    except (StorageError, ValueError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
