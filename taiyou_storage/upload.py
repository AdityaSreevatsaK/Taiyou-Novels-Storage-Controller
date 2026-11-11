"""Conservative incremental uploader for the reader's v1 Hugging Face layout.

Updates only unambiguous novels, preserves stable IDs and personal metadata.
Remote writes require --apply. CI never uses network or credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

from .core import DEFAULT_REPO, normalized_title, validate_catalogue

MAX_ZIP = 120 * 1024 * 1024
MAX_EPUB = 120 * 1024 * 1024
MAX_JSON = 12 * 1024 * 1024


class UploadError(ValueError):
    pass


def _entry(z: zipfile.ZipFile, name: str):
    matches = [x for x in z.infolist() if not x.is_dir() and
               x.filename.replace("\\", "/").rsplit("/", 1)[-1].casefold() == name]
    if len(matches) > 1:
        raise UploadError("Duplicate archive entry: " + name)
    return matches[0] if matches else None


def _opf_metadata(epub: bytes) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(epub)) as z:
            if "mimetype" not in z.namelist() or "META-INF/container.xml" not in z.namelist():
                raise UploadError("Missing EPUB mimetype or container.xml")
            root = ET.fromstring(z.read("META-INF/container.xml"))
            rootfile = next((e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "rootfile"), None)
            opf = rootfile.get("full-path") if rootfile is not None else None
            if not opf or opf not in z.namelist() or z.getinfo(opf).file_size > 8 * 1024 * 1024:
                raise UploadError("EPUB package metadata missing or oversized")
            document = ET.fromstring(z.read(opf))
            fields = {}
            for e in document.iter():
                tag = e.tag.rsplit("}", 1)[-1]
                if tag in ("title", "creator", "language", "description", "source", "subject"):
                    value = " ".join("".join(e.itertext()).split()).strip()
                    if value:
                        fields.setdefault(tag, []).append(value)
            return {k: v[0] for k, v in fields.items()}
    except (OSError, zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        raise UploadError("Invalid EPUB: " + str(exc)) from exc


def read_novel(path: Path) -> tuple[dict, bytes, str]:
    if path.stat().st_size > MAX_ZIP:
        raise UploadError("ZIP exceeds 120MB")
    try:
        with zipfile.ZipFile(path) as z:
            info = _entry(z, "source.epub")
            if info is None or info.file_size > MAX_EPUB or info.file_size == 0:
                raise UploadError("Expected exactly one nonempty source.epub (max 120MB)")
            if z.testzip() is not None:
                raise UploadError("ZIP CRC validation failed")
            epub = z.read(info)
            meta_info = _entry(z, "metadata.json")
            metadata = {}
            if meta_info:
                if meta_info.file_size > MAX_JSON:
                    raise UploadError("metadata.json too large")
                metadata = json.loads(z.read(meta_info).decode("utf-8-sig"))
                if not isinstance(metadata, dict):
                    raise UploadError("metadata.json must be an object")
            ch_info = _entry(z, "chapters.json")
            chapters = None
            if ch_info:
                if ch_info.file_size > MAX_JSON:
                    raise UploadError("chapters.json too large")
                chapters = json.loads(z.read(ch_info).decode("utf-8-sig"))
                if not isinstance(chapters, list):
                    raise UploadError("chapters.json must be an array")
    except (OSError, zipfile.BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
        raise UploadError("Invalid archive: " + str(exc)) from exc
    info = _opf_metadata(epub)
    def choose(*values):
        return next((v.strip() for v in values if isinstance(v, str) and v.strip()), None)
    title = choose(metadata.get("title"), info.get("title"), path.stem)
    author = choose(metadata.get("author"), info.get("creator"), "Unknown author")
    if not title:
        raise UploadError("Missing title")
    book = {
        "title": title,
        "author": author,
        "language": choose(metadata.get("language"), info.get("language")),
        "description": choose(metadata.get("summary"), metadata.get("synopsis"),
                              metadata.get("description"), info.get("description")),
        "status": choose(metadata.get("status")),
        "sourceUrl": choose(metadata.get("source_url"), info.get("source")),
        "chapterCount": len(chapters) if chapters else metadata.get("chapter_count"),
        "sourceTags": metadata.get("tags") or metadata.get("genres") or [],
        "size": len(epub),
        "cloud": True,
        "metadataScanned": True,
        "originalFileName": path.name,
    }
    if isinstance(book["sourceTags"], str):
        book["sourceTags"] = [x.strip() for x in book["sourceTags"].split(",") if x.strip()]
    if not isinstance(book["sourceTags"], list):
        book["sourceTags"] = []
    if not isinstance(book["chapterCount"], int) or book["chapterCount"] <= 0:
        book.pop("chapterCount", None)
    book = {k: v for k, v in book.items() if v is not None}
    return book, epub, hashlib.sha256(path.read_bytes()).hexdigest()


def matching_entry(books: list[dict], meta: dict, epub: bytes) -> tuple[dict | None, str]:
    epub_id = hashlib.sha256(epub).hexdigest()[:24]
    ids = [b for b in books if b["id"] == epub_id]
    if len(ids) == 1:
        return ids[0], "epub-id"
    title = normalized_title(meta["title"])
    title_matches = [b for b in books if normalized_title(str(b["metadata"].get("title", ""))) == title]
    if not title_matches:
        return None, "new"
    same_author = [b for b in title_matches if
                   normalized_title(str(b["metadata"].get("author", ""))) ==
                   normalized_title(str(meta.get("author", "")))]
    if len(title_matches) == 1 and len(same_author) == 1:
        return same_author[0], "title-author"
    raise UploadError("CONFLICT: title exists with different or ambiguous author; manual review required")


def plan(books: list[dict], local: list[tuple[Path, dict, bytes, str]],
         remote_hashes: dict[str, str], remote_paths: set[str]) -> list[dict]:
    """Build a conservative plan; remote_hashes maps archive path to SHA256."""
    output = []
    assigned = {}
    for path, meta, epub, digest in local:
        try:
            entry, reason = matching_entry(books, meta, epub)
            chosen_id = entry["id"] if entry else hashlib.sha256(epub).hexdigest()[:24]
            if chosen_id in assigned:
                raise UploadError("CONFLICT: multiple local ZIPs target same novel: " + assigned[chosen_id])
            assigned[chosen_id] = path.name
            archive = f"data/novels/{chosen_id}/original.zip"
            epub_path = f"data/novels/{chosen_id}/source.epub"
            if entry:
                if entry["epubPath"] != epub_path or (entry.get("archivePath") not in (None, archive)):
                    raise UploadError("CONFLICT: existing catalogue paths unexpected")
                if remote_hashes.get(archive) == digest and epub_path in remote_paths:
                    state = "UNCHANGED"
                else:
                    state = "UPDATE"
            else:
                if archive in remote_paths or epub_path in remote_paths:
                    raise UploadError("CONFLICT: remote files exist without catalogue entry")
                state = "NEW"
            output.append({"path": path, "metadata": meta, "epub": epub,
                           "digest": digest, "id": chosen_id, "existing": entry,
                           "reason": reason, "state": state})
        except UploadError as exc:
            output.append({"path": path, "state": "CONFLICT", "reason": str(exc)})
    return output


def merged_metadata(old: dict | None, new: dict, chosen_id: str) -> dict:
    # Preserve all existing app/user-managed fields unless they are source-managed.
    result = dict(old or {})
    result.update(new)
    result["id"] = chosen_id
    result.setdefault("importedAt", int(time.time() * 1000))
    result.setdefault("progress", 0)
    result.setdefault("personalTags", [])
    return result


def apply_item(api, repo: str, token: str, item: dict) -> str:
    """One commit, optimistic concurrency, and re-plan on revision changes."""
    from huggingface_hub import CommitOperationAdd, hf_hub_download
    for attempt in range(3):
        info = api.dataset_info(repo, token=token)
        if info.private is not True:
            raise UploadError("Refusing to write to a public dataset")
        sha = info.sha
        files = set(api.list_repo_files(repo_id=repo, repo_type="dataset",
                                        revision=sha, token=token))
        if "data/library.json" in files:
            src = hf_hub_download(repo_id=repo, filename="data/library.json",
                                  repo_type="dataset", revision=sha, token=token)
            original = json.loads(Path(src).read_text(encoding="utf-8"))
            books = validate_catalogue(original)
        else:
            if any(path.startswith("data/") for path in files):
                raise UploadError(
                    "Catalogue is missing but data/ already contains files. "
                    "Refusing to initialise over orphaned data.")
            # First-ever upload: create the v1 catalogue and novel files
            # together in the same optimistic-concurrency-guarded commit.
            original = {"version": 1, "books": []}
            books = []
        entry, _ = matching_entry(books, item["metadata"], item["epub"])
        desired_id = entry["id"] if entry else hashlib.sha256(item["epub"]).hexdigest()[:24]
        if desired_id != item["id"]:
            raise UploadError("Remote identity changed since planning; re-run plan")
        archive = f"data/novels/{desired_id}/original.zip"
        epub_path = f"data/novels/{desired_id}/source.epub"
        if entry and (entry["epubPath"] != epub_path or entry.get("archivePath") not in (None, archive)):
            raise UploadError("Unexpected remote paths; refusing overwrite")
        if not entry and (archive in files or epub_path in files):
            raise UploadError("Orphaned remote files: manual review required")
        if entry and archive in files:
            cached = hf_hub_download(repo_id=repo, filename=archive, repo_type="dataset",
                                     revision=sha, token=token)
            if hashlib.sha256(Path(cached).read_bytes()).hexdigest() == item["digest"] and epub_path in files:
                return "UNCHANGED"
        updated = merged_metadata(entry["metadata"] if entry else None, item["metadata"], desired_id)
        if entry:
            entry["metadata"] = updated
            entry["archivePath"] = archive
        else:
            original["books"].append({"id": desired_id, "metadata": updated,
                                      "epubPath": epub_path, "archivePath": archive})
        payload = (json.dumps(original, ensure_ascii=False, indent=2) + "\n").encode()
        operations = [
            CommitOperationAdd(path_in_repo=archive, path_or_fileobj=str(item["path"])),
            CommitOperationAdd(path_in_repo=epub_path, path_or_fileobj=io.BytesIO(item["epub"])),
            CommitOperationAdd(path_in_repo="data/library.json", path_or_fileobj=io.BytesIO(payload)),
        ]
        try:
            api.create_commit(repo_id=repo, repo_type="dataset", token=token,
                              operations=operations, parent_commit=sha,
                              commit_message=f"{'Update' if entry else 'Add'} novel: {updated['title'][:70]}")
            return "UPDATED" if entry else "NEW"
        except Exception as exc:
            response = getattr(exc, "response", None)
            if getattr(response, "status_code", None) in (409, 412) and attempt < 2:
                continue
            raise
    raise UploadError("Dataset changed repeatedly; no commit was applied")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Safe incremental novel ZIP uploader")
    parser.add_argument("folder", nargs="?", default="novels")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Write changes to private HF dataset")
    args = parser.parse_args(argv)
    directory = Path(args.folder)
    if not directory.is_dir():
        print(f"Missing directory: {directory}", file=sys.stderr)
        return 1
    paths = sorted(directory.rglob("*.zip") if args.recursive else directory.glob("*.zip"))
    if not paths:
        print("No ZIP archives found", file=sys.stderr)
        return 1
    local, errors = [], 0
    for path in paths:
        try:
            meta, epub, digest = read_novel(path)
            local.append((path, meta, epub, digest))
        except (UploadError, OSError) as exc:
            errors += 1
            print(f"[INVALID] {path}: {exc}")
    if errors:
        print("Invalid ZIPs found: no remote writes performed", file=sys.stderr)
        return 1
    try:
        from huggingface_hub import HfApi, hf_hub_download
        from .core import load_remote
        api = HfApi()
        books, sha = load_remote(args.repo, allow_empty=True)
        files = set(api.list_repo_files(repo_id=args.repo, repo_type="dataset", revision=sha))
        if "data/library.json" not in files:
            print("[NEW PRIVATE DATASET] Initial library catalogue will be created on first upload.")
        hashes = {}
        for b in books:
            archive = b.get("archivePath")
            if archive and archive in files:
                cached = hf_hub_download(repo_id=args.repo, filename=archive, repo_type="dataset", revision=sha)
                hashes[archive] = hashlib.sha256(Path(cached).read_bytes()).hexdigest()
        instructions = plan(books, local, hashes, files)
        for item in instructions:
            print(f"[{item['state']}] {item['path'].name}: {item['reason']}")
        if any(item["state"] == "CONFLICT" for item in instructions):
            print("Conflicts found. All writes blocked.", file=sys.stderr)
            return 2
        if not args.apply:
            print("Preview only. Add --apply to perform updates.")
            return 0
        from huggingface_hub import get_token
        token = get_token()
        if not token:
            raise UploadError("No Hugging Face token configured")
        for item in instructions:
            if item["state"] != "UNCHANGED":
                print(f"[{apply_item(api, args.repo, token, item)}] {item['path'].name}")
        return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
