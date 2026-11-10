"""Read-only management CLI for Taiyou's private Hugging Face dataset."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys

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
    sync = sub.add_parser("status", help="Compare local EPUB hash IDs to remote catalogue IDs")
    sync.add_argument("--folder", default="novels")
    args = parser.parse_args(argv)
    try:
        books, revision = load_remote(args.repo)
        print(f"Dataset: {args.repo} (revision {revision}) | catalogue: {len(books)} books")
        if args.command == "list":
            data = rows(books)
            write_csv(Path(args.output), data, ["id", "title", "author", "chapters", "epub_path", "archive_path"])
            print(f"Saved {len(data)} rows to {args.output}")
        elif args.command == "conflicts":
            data = conflicts(books)
            write_csv(Path(args.output), data, ["type", "first_title", "first_id", "second_title", "second_id"])
            print(f"Saved {len(data)} collisions to {args.output}")
        elif args.command == "backup":
            from huggingface_hub import hf_hub_download
            source = hf_hub_download(repo_id=args.repo, repo_type="dataset",
                                     filename="data/library.json", revision=revision)
            dest = Path("backups") / f"library-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{revision[:12]}.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(Path(source).read_bytes())
            print(f"Backed up to {dest}")
        elif args.command == "download":
            from huggingface_hub import HfApi, hf_hub_download
            api = HfApi()
            available = set(api.list_repo_files(repo_id=args.repo, repo_type="dataset", revision=revision))
            manifest = []
            for b in rows(books):
                path = b["archive_path"]
                if not path or path not in available:
                    print(f"[MISSING] {b['title']} ({b['id']}): no original.zip")
                    continue
                destination = Path(args.destination) / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                remote_file = hf_hub_download(repo_id=args.repo, repo_type="dataset",
                                              filename=path, revision=revision)
                # Write via a temporary file to avoid leaving a partial archive.
                tmp = destination.with_suffix(destination.suffix + ".part")
                tmp.write_bytes(Path(remote_file).read_bytes())
                tmp.replace(destination)
                digest = sha256_file(destination)
                manifest.append({"id": b["id"], "title": b["title"], "path": path, "sha256": digest})
                print(f"[DOWNLOADED] {b['title']}")
            manifest_path = Path(args.destination) / "manifest.json"
            manifest_path.write_text(json.dumps({"repo": args.repo, "revision": revision,
                "files": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"Manifest saved to {manifest_path}")
        elif args.command == "status":
            folder = Path(args.folder)
            if not folder.is_dir():
                raise StorageError(f"Local folder does not exist: {folder}")
            remote_ids = {b["id"] for b in books}
            for path in sorted(folder.glob("*.zip")):
                try:
                    ident = local_epub_id(path)
                    flag = "EPUB-ID-EXISTS" if ident in remote_ids else "EPUB-ID-NEW"
                    print(f"[{flag}] {path.name} ({ident}); cannot infer ZIP content equality")
                except Exception as exc:
                    print(f"[INVALID] {path.name}: {exc}")
            print("Note: status is not yet a complete incremental ZIP comparison.")
        return 0
    except (StorageError, ValueError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
