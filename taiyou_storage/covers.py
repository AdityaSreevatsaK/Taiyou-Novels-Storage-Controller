"""Upload cover images from the Novel Retriever's GitHub Actions ZIP artifact.

No Hugging Face writes without --apply. Every cover belongs to an existing,
unambiguously matched catalogue record; this never creates novel records.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
from urllib.parse import urlsplit, urlunsplit
import zipfile

from .core import DEFAULT_REPO, normalized_title, validate_catalogue, write_csv
from .paths import book_dir, COVER_SUFFIXES

MAX_ARCHIVE = 512 * 1024 * 1024
MAX_IMAGE = 12 * 1024 * 1024
MAX_TOTAL = 350 * 1024 * 1024
MAX_COVERS = 2000
MAX_MANIFEST = 8 * 1024 * 1024
EXTENSIONS = {".jpg": ".jpg", ".jpeg": ".jpg", ".png": ".png", ".webp": ".webp"}


class CoverError(ValueError):
    """A problem with the input archive or an unsafe matching decision."""


@dataclass(frozen=True)
class Cover:
    title: str
    website: str
    source_url: str
    cover_file: str
    extension: str
    data: bytes
    digest: str


def source_key(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        addr = urlsplit(value.strip())
        if addr.scheme.lower() not in ("http", "https") or not addr.hostname:
            return ""
        host = addr.netloc.lower().removeprefix("www.")
        return urlunsplit(("", host, addr.path.rstrip("/") or "/", addr.query, ""))
    except ValueError:
        return ""


def check_image(data: bytes, extension: str) -> None:
    if not data or len(data) > MAX_IMAGE:
        raise CoverError("Cover image is empty or exceeds 12 MiB")
    if extension == ".jpg":
        good = data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
    elif extension == ".png":
        good = data.startswith(b"\x89PNG\r\n\x1a\n") and data.endswith(b"IEND\xaeB\x60\x82")
    elif extension == ".webp":
        good = len(data) >= 16 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        if good:
            good = int.from_bytes(data[4:8], "little") + 8 == len(data)
    else:
        good = False
    if not good:
        raise CoverError(f"Image bytes do not match a complete {extension} image")


def _manifest_records(obj: object) -> list[dict]:
    if isinstance(obj, list):
        records = obj
    elif isinstance(obj, dict) and "cover_file" in obj:
        records = [obj]
    elif isinstance(obj, dict) and "results" in obj:
        # Novel_Library/tools/download_covers.py emits a summary with "results".
        # Failed downloads lack cover_file and MUST NOT be treated as inputs.
        records = obj["results"]
        if not isinstance(records, list):
            raise CoverError("results must be an array")
        if len(records) > MAX_COVERS or any(not isinstance(x, dict) for x in records):
            raise CoverError("results is too large or contains invalid entries")
        records = [x for x in records if x.get("status") in ("downloaded", "skipped")]
    elif isinstance(obj, dict):
        records = next((obj[k] for k in ("covers", "novels", "items", "entries")
                        if k in obj), None)
    else:
        records = None
    if not isinstance(records, list):
        raise CoverError("Expected a manifest entry, list, or an object with results/covers")
    if not records or len(records) > MAX_COVERS or any(not isinstance(x, dict) for x in records):
        raise CoverError("No usable cover images found, or manifest contains invalid entries")
    return records


def _parse_zip(z: zipfile.ZipFile, nested: bool = False) -> list[Cover]:
    entries = [f for f in z.infolist() if not f.is_dir()]
    manifest_entries = [x for x in entries if x.filename.split("/")[-1] == "covers_manifest.json"]
    if not manifest_entries and not nested and len(entries) == 1 and entries[0].filename.lower().endswith(".zip"):
        inner = entries[0]
        if inner.file_size > MAX_ARCHIVE:
            raise CoverError("Nested cover ZIP exceeds 512 MiB")
        with zipfile.ZipFile(io.BytesIO(z.read(inner))) as nested_zip:
            return _parse_zip(nested_zip, nested=True)
    if len(manifest_entries) != 1:
        raise CoverError("Expected exactly one covers_manifest.json in the ZIP")
    manifest_info = manifest_entries[0]
    if manifest_info.file_size > MAX_MANIFEST:
        raise CoverError("Cover manifest exceeds 8 MiB")
    try:
        manifest = json.loads(z.read(manifest_info).decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise CoverError(f"Invalid covers_manifest.json: {exc}") from exc
    records = _manifest_records(manifest)
    prefix = str(PurePosixPath(manifest_info.filename).parent)
    prefix = "" if prefix == "." else prefix + "/"
    available = {x.filename: x for x in entries}
    output = []
    total_bytes = 0
    visited = set()
    for n, record in enumerate(records, 1):
        title, url, filename = (record.get(k) for k in ("title", "source_url", "cover_file"))
        website = record.get("website", "")
        if not isinstance(title, str) or not title.strip():
            raise CoverError(f"Entry {n}: title is required")
        if not isinstance(url, str) or not source_key(url):
            raise CoverError(f"Entry {n}: valid HTTP(S) source_url is required")
        if not isinstance(filename, str) or not filename or "\\" in filename:
            raise CoverError(f"Entry {n}: unsafe cover_file")
        relative = PurePosixPath(filename)
        if relative.is_absolute() or any(p in ("", ".", "..") for p in filename.split("/")):
            raise CoverError(f"Entry {n}: unsafe cover_file path")
        if filename in visited:
            raise CoverError(f"Cover file listed more than once: {filename}")
        visited.add(filename)
        entry_name = prefix + filename
        entry = available.get(entry_name)
        if entry is None:
            raise CoverError(f"Entry {n}: missing image {entry_name}")
        extension = EXTENSIONS.get(relative.suffix.lower())
        if extension is None or entry.file_size > MAX_IMAGE:
            raise CoverError(f"Entry {n}: unsupported or oversized image")
        total_bytes += entry.file_size
        if total_bytes > MAX_TOTAL:
            raise CoverError("Images in archive exceed 350 MiB in total")
        image = z.read(entry)
        check_image(image, extension)
        output.append(Cover(title.strip(), str(website or "").strip(), url.strip(),
                            filename, extension, image, hashlib.sha256(image).hexdigest()))
    return output


def read_covers_zip(path: Path) -> list[Cover]:
    if path.is_dir():
        options = sorted(x for x in path.iterdir() if x.is_file() and x.suffix.lower() == ".zip")
        if len(options) != 1:
            raise CoverError(f"Directory contains {len(options)} ZIP files; specify the exact ZIP filename")
        path = options[0]
    if not path.is_file():
        raise CoverError(f"Cover ZIP file not found: {path}")
    if path.stat().st_size > MAX_ARCHIVE:
        raise CoverError(f"Cover ZIP exceeds 512 MiB: {path}")
    try:
        with zipfile.ZipFile(path) as z:
            return _parse_zip(z)
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise CoverError(f"Cannot read ZIP: {exc}") from exc


def match_book(books: list[dict], cover: Cover) -> tuple[dict | None, str]:
    url = source_key(cover.source_url)
    by_url = [b for b in books if source_key(b["metadata"].get("sourceUrl", "")) == url]
    by_title = [b for b in books if normalized_title(b["metadata"].get("title", "")) ==
                normalized_title(cover.title)]
    if len(by_url) > 1:
        raise CoverError("CONFLICT: source URL belongs to multiple catalogue records")
    if len(by_url) == 1:
        matched = by_url[0]
        if any(b["id"] != matched["id"] for b in by_title):
            raise CoverError("CONFLICT: source URL and title point to different novels")
        return matched, "source-url"
    if len(by_title) > 1:
        raise CoverError("CONFLICT: multiple novels have this title")
    if not by_title:
        return None, "MISSING: novel not in the dataset catalogue"
    matched = by_title[0]
    stored_url = source_key(matched["metadata"].get("sourceUrl", ""))
    if stored_url and stored_url != url:
        raise CoverError("CONFLICT: title matches but catalogue source URL differs")
    author = cover.website  # Website is not author; never use it to disambiguate books.
    return matched, "unique-title"


def make_plan(covers: list[Cover], books: list[dict], remote_hashes: dict[str, str],
              remote_paths: set[str]) -> list[dict]:
    plan = []
    matched_ids = {}
    for cover in covers:
        item = {"cover": cover, "title": cover.title, "website": cover.website,
                "source_url": cover.source_url, "cover_file": cover.cover_file,
                "book_id": "", "destination": "", "status": "", "reason": ""}
        try:
            book, reason = match_book(books, cover)
            if book is None:
                item.update(status="MISSING", reason=reason)
            else:
                book_id = book["id"]
                if book_id in matched_ids:
                    raise CoverError("CONFLICT: multiple images target the same novel: " +
                                     matched_ids[book_id])
                matched_ids[book_id] = cover.cover_file
                directory = book_dir(book)
                dest = f"{directory}/cover{cover.extension}"
                current = book["metadata"].get("coverPath")
                if current and current not in {
                        f"{directory}/cover{suffix}" for suffix in COVER_SUFFIXES}:
                    raise CoverError("CONFLICT: unexpected existing coverPath")
                identical = remote_hashes.get(dest) == cover.digest
                if identical and current == dest:
                    status = "UNCHANGED"
                elif identical:
                    status = "LINK"
                elif current or dest in remote_paths:
                    status = "UPDATE"
                else:
                    status = "NEW"
                item.update(book_id=book_id, destination=dest, status=status, reason=reason)
        except CoverError as exc:
            item.update(status="CONFLICT", reason=str(exc))
        plan.append(item)
    return plan


REPORT_COLUMNS = ["status", "title", "website", "source_url", "cover_file",
                  "book_id", "destination", "reason"]


def save_report(items: list[dict], path: Path) -> None:
    write_csv(path, [{key: item.get(key, "") for key in REPORT_COLUMNS}
                     for item in items], REPORT_COLUMNS)


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import novel cover images into private HF dataset")
    parser.add_argument("archive", help="Downloaded_Covers.zip or the GitHub Actions artifact ZIP")
    parser.add_argument("--repo", default=os.environ.get("HF_DATASET_REPO", DEFAULT_REPO))
    parser.add_argument("--report", default="reports/cover-upload-plan.csv")
    parser.add_argument("--apply", action="store_true", help="Actually upload after preview")
    parser.add_argument("--interactive", action="store_true",
                        help="Preview and approve within one revision-guarded process")
    parser.add_argument("--batch-size", type=int, default=20,
                        help="Covers per HF commit (1-40; default 20)")
    parser.add_argument("--commit-pause", type=float, default=2.0,
                        help="Seconds between commit batches (default 2)")
    args = parser.parse_args(argv)
    try:
        covers = read_covers_zip(Path(args.archive))
        from huggingface_hub import HfApi, hf_hub_download, get_token
        from .core import load_remote
        books, revision = load_remote(args.repo)
        api = HfApi()
        remote_paths = set(api.list_repo_files(repo_id=args.repo, repo_type="dataset",
                                               revision=revision))
        possible = make_plan(covers, books, {}, remote_paths)
        paths_to_hash = {row["destination"] for row in possible
                         if row["destination"] in remote_paths}
        hashes = {}
        for destination in sorted(paths_to_hash):
            source = hf_hub_download(repo_id=args.repo, repo_type="dataset",
                                     filename=destination, revision=revision)
            digest = hashlib.sha256()
            with Path(source).open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            hashes[destination] = digest.hexdigest()
        items = make_plan(covers, books, hashes, remote_paths)
        save_report(items, Path(args.report))
        counts = {}
        for item in items:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
            print(f"[{item['status']}] {item['title']} -> {item['book_id'] or '-'} ({item['reason']})")
        print("Summary:", ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
        print("Report:", args.report)
        if any(item["status"] == "CONFLICT" for item in items):
            print("Conflicts found: NO images uploaded. Resolve first.", file=sys.stderr)
            return 2
        if not args.apply and not args.interactive:
            print("Preview only. Use --apply or --interactive for uploads.")
            return 0
        if args.interactive:
            if not sys.stdin.isatty():
                raise CoverError("Interactive approval requires a local console")
            if input("Upload exactly these cover changes? Type YES: ").strip() != "YES":
                print("Cancelled; no remote changes made.")
                return 0
        token = get_token()
        if not token:
            raise CoverError("Please configure an HF token using hf auth login")
        changing = [x for x in items if x["status"] in ("NEW", "UPDATE", "LINK")]
        if not changing:
            print("No image changes need uploading.")
            return 0
        remote_library = hf_hub_download(repo_id=args.repo, repo_type="dataset",
                                         filename="data/library.json", revision=revision, token=token)
        backup = Path("backups") / ("cover-upload-library-" +
                  datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" +
                  revision[:12] + ".json")
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(Path(remote_library).read_bytes())
        print("Catalogue backup:", backup)
        # A batch commits its cover files AND all corresponding catalogue edits
        # atomically. This avoids the Hub's hourly repository-commit quota.
        from .cover_batches import upload_batches
        try:
            commits, applied = upload_batches(
                api, args.repo, token, changing, revision,
                batch_size=args.batch_size, commit_pause=args.commit_pause)
        except Exception:
            print("STOPPED: successfully committed batches are preserved. "
                  "Rerun the SAME ZIP after resolving the error; already uploaded "
                  "covers will show UNCHANGED.", file=sys.stderr)
            raise
        print(f"Cover upload completed: {applied} changed in {commits} HF commit(s).")
        print("The reader needs coverPath support to display images.")
        return 0
    except (CoverError, OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
