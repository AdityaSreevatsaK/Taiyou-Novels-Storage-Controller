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

from .core import DEFAULT_REPO, normalized_title, sha256_file, validate_catalogue
from .paths import book_dir, legacy_dir, readable_dir, folder_from_epub_path

MAX_ZIP = 120 * 1024 * 1024
MAX_EPUB = 120 * 1024 * 1024
MAX_JSON = 12 * 1024 * 1024
MAX_ZIP_ENTRIES = 30000
MAX_ZIP_EXPANDED = 2 * 1024 * 1024 * 1024
MAX_EPUB_ENTRIES = 20000
MAX_EPUB_EXPANDED = 512 * 1024 * 1024
MAX_ENTRY_COMPRESSION_RATIO = 10000


class UploadError(ValueError):
    pass


def validate_zip_budget(z: zipfile.ZipFile, *, epub: bool = False) -> None:
    """Reject pathological archives before any member is decompressed."""
    max_entries = MAX_EPUB_ENTRIES if epub else MAX_ZIP_ENTRIES
    max_bytes = MAX_EPUB_EXPANDED if epub else MAX_ZIP_EXPANDED
    members = z.infolist()
    if len(members) > max_entries:
        raise UploadError("Too many ZIP/EPUB entries")
    total = 0
    for member in members:
        name = member.filename.replace("\\", "/")
        if (name.startswith("/") or any(part == ".." for part in name.split("/"))
                or member.flag_bits & 1):
            raise UploadError("Unsafe or encrypted ZIP/EPUB member")
        if member.is_dir():
            continue
        if member.file_size < 0 or member.compress_size < 0:
            raise UploadError("Invalid ZIP/EPUB member size")
        total += member.file_size
        if total > max_bytes:
            raise UploadError("ZIP/EPUB expanded data exceeds safety budget")
        if member.file_size > max(1, member.compress_size) * MAX_ENTRY_COMPRESSION_RATIO:
            raise UploadError("Suspicious ZIP/EPUB compression ratio")


def _entry(z: zipfile.ZipFile, name: str):
    matches = [x for x in z.infolist() if not x.is_dir() and
               x.filename.replace("\\", "/").rsplit("/", 1)[-1].casefold() == name]
    if len(matches) > 1:
        raise UploadError("Duplicate archive entry: " + name)
    return matches[0] if matches else None


def _opf_metadata(epub: bytes) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(epub)) as z:
            validate_zip_budget(z, epub=True)
            if "mimetype" not in z.namelist() or "META-INF/container.xml" not in z.namelist():
                raise UploadError("Missing EPUB mimetype or container.xml")
            if z.getinfo("META-INF/container.xml").file_size > 1024 * 1024:
                raise UploadError("EPUB container metadata too large")
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
            validate_zip_budget(z)
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
    return book, epub, sha256_file(path)


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
         remote_hashes: dict[str, str], remote_paths: set[str], *,
         readable_new: bool = False) -> list[dict]:
    """Build a conservative plan; remote_hashes maps archive and EPUB paths to SHA256."""
    output = []
    assigned = {}
    for path, meta, epub, digest in local:
        try:
            entry, reason = matching_entry(books, meta, epub)
            chosen_id = entry["id"] if entry else hashlib.sha256(epub).hexdigest()[:24]
            if chosen_id in assigned:
                raise UploadError("CONFLICT: multiple local ZIPs target same novel: " + assigned[chosen_id])
            assigned[chosen_id] = path.name
            directory = book_dir(entry) if entry else (
                readable_dir(chosen_id, meta["title"]) if readable_new else legacy_dir(chosen_id))
            archive = f"{directory}/original.zip"
            epub_path = f"{directory}/source.epub"
            if entry:
                if entry["epubPath"] != epub_path or (entry.get("archivePath") not in (None, archive)):
                    raise UploadError("CONFLICT: existing catalogue paths unexpected")
                merged = merged_metadata(entry["metadata"], meta, chosen_id)
                if (remote_hashes.get(archive) == digest and
                        remote_hashes.get(epub_path) == hashlib.sha256(epub).hexdigest() and
                        entry["metadata"] == merged and entry.get("archivePath") == archive):
                    state = "UNCHANGED"
                else:
                    state = "UPDATE"
            else:
                if archive in remote_paths or epub_path in remote_paths:
                    raise UploadError("CONFLICT: remote files exist without catalogue entry")
                state = "NEW"
            output.append({"path": path, "metadata": meta, "epub": epub,
                           "digest": digest, "id": chosen_id, "existing": entry,
                           "directory": directory, "reason": reason, "state": state})
        except UploadError as exc:
            output.append({"path": path, "state": "CONFLICT", "reason": str(exc)})
    return output


def merged_metadata(old: dict | None, new: dict, chosen_id: str) -> dict:
    # Preserve all existing app/user-managed fields unless they are source-managed.
    result = dict(old or {})
    result.update(new)
    # Older ZIPs may omit source genres that were safely backfilled later.
    # Missing/empty incoming tags must not erase already verified genres.
    if old and old.get("sourceTags") and not new.get("sourceTags"):
        result["sourceTags"] = old["sourceTags"]
    result["id"] = chosen_id
    result.setdefault("importedAt", int(time.time() * 1000))
    result.setdefault("progress", 0)
    result.setdefault("personalTags", [])
    return result


def apply_item(api, repo: str, token: str, item: dict, *,
               expected_revision: str | None = None,
               return_revision: bool = False) -> str | tuple[str, str]:
    """Validate all stored artifacts, then atomically reconcile any drift.

    When given expected_revision, refuse concurrent plan drift rather than
    silently rebasing operations a user approved against an older revision.
    """
    from huggingface_hub import CommitOperationAdd, hf_hub_download
    for attempt in range(3 if expected_revision is None else 1):
        info = api.dataset_info(repo, token=token)
        if info.private is not True or not info.sha:
            raise UploadError("Refusing to write to an unverified or public dataset")
        sha = info.sha
        if expected_revision is not None and sha != expected_revision:
            raise UploadError("Dataset changed since preview; re-run the upload plan")
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
            original = {"version": 1, "books": []}
            books = []
        entry, _ = matching_entry(books, item["metadata"], item["epub"])
        desired_id = entry["id"] if entry else hashlib.sha256(item["epub"]).hexdigest()[:24]
        if desired_id != item["id"]:
            raise UploadError("Remote identity changed since planning; re-run plan")
        directory = book_dir(entry) if entry else item.get("directory", legacy_dir(desired_id))
        try:
            folder_from_epub_path(desired_id, directory + "/source.epub")
        except ValueError as exc:
            raise UploadError("Invalid planned directory") from exc
        archive = f"{directory}/original.zip"
        epub_path = f"{directory}/source.epub"
        if entry and (entry["epubPath"] != epub_path or
                      entry.get("archivePath") not in (None, archive)):
            raise UploadError("Unexpected remote paths; refusing overwrite")
        if item.get("directory", directory) != directory:
            raise UploadError("Planned directory changed; re-run preview")
        if not entry and (archive in files or epub_path in files):
            raise UploadError("Orphaned remote files: manual review required")
        if sha256_file(item["path"]) != item["digest"]:
            raise UploadError("Local ZIP changed after preview; re-run the upload plan")
        archive_ok = False
        if entry and archive in files:
            cached = hf_hub_download(repo_id=repo, filename=archive, repo_type="dataset",
                                     revision=sha, token=token)
            archive_ok = sha256_file(Path(cached)) == item["digest"]
        epub_ok = False
        if entry and epub_path in files:
            cached = hf_hub_download(repo_id=repo, filename=epub_path, repo_type="dataset",
                                     revision=sha, token=token)
            epub_ok = sha256_file(Path(cached)) == hashlib.sha256(item["epub"]).hexdigest()
        updated = merged_metadata(entry["metadata"] if entry else None,
                                  item["metadata"], desired_id)
        metadata_ok = bool(entry and entry["metadata"] == updated and
                           entry.get("archivePath") == archive)
        if archive_ok and epub_ok and metadata_ok:
            return ("UNCHANGED", sha) if return_revision else "UNCHANGED"
        if entry:
            entry["metadata"] = updated
            entry["archivePath"] = archive
        else:
            original["books"].append({"id": desired_id, "metadata": updated,
                                      "epubPath": epub_path, "archivePath": archive})
        operations = []
        if not archive_ok:
            operations.append(CommitOperationAdd(
                path_in_repo=archive, path_or_fileobj=str(item["path"])))
        if not epub_ok:
            operations.append(CommitOperationAdd(
                path_in_repo=epub_path, path_or_fileobj=io.BytesIO(item["epub"])))
        operations.append(CommitOperationAdd(
            path_in_repo="data/library.json",
            path_or_fileobj=io.BytesIO(
                (json.dumps(original, ensure_ascii=False, indent=2) + "\n").encode())))
        try:
            result = api.create_commit(
                repo_id=repo, repo_type="dataset", token=token,
                operations=operations, parent_commit=sha,
                commit_message=f"{'Update' if entry else 'Add'} novel: {updated['title'][:70]}")
            status = "UPDATED" if entry else "NEW"
            if return_revision:
                new_sha = getattr(result, "oid", None)
                if not isinstance(new_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", new_sha):
                    raise UploadError(
                        "Commit response lacked a valid revision; re-preview "
                        "before attempting remaining books")
                return status, new_sha
            return status
        except Exception as exc:
            response = getattr(exc, "response", None)
            if (expected_revision is None and
                    getattr(response, "status_code", None) in (409, 412) and attempt < 2):
                continue
            raise
    raise UploadError("Dataset changed repeatedly; no commit was applied")

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Safe incremental novel ZIP uploader")
    parser.add_argument("folder", nargs="?", default="novels")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--readable-folders", action="store_true",
                        help="Create new novels in ID - Title directories on a disposable private test dataset only")
    parser.add_argument("--apply", action="store_true", help="Write changes to private HF dataset")
    parser.add_argument("--interactive", action="store_true",
                        help="Preview and approve in one revision-guarded process")
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
        # Only compare remote artifacts for the novels in this local batch.
        relevant_paths = set()
        for _, meta, epub, _ in local:
            try:
                existing, _ = matching_entry(books, meta, epub)
            except UploadError:
                continue  # A conflict will be shown explicitly in the plan.
            if existing:
                directory = book_dir(existing)
                relevant_paths.add(f"{directory}/original.zip")
                relevant_paths.add(f"{directory}/source.epub")
        hashes = {}
        for remote_path in sorted(relevant_paths & files):
            cached = hf_hub_download(repo_id=args.repo, filename=remote_path,
                                     repo_type="dataset", revision=sha)
            hashes[remote_path] = sha256_file(Path(cached))
        instructions = plan(books, local, hashes, files,
                            readable_new=args.readable_folders)
        for item in instructions:
            print(f"[{item['state']}] {item['path'].name}: {item['reason']}")
        if any(item["state"] == "CONFLICT" for item in instructions):
            print("Conflicts found. All writes blocked.", file=sys.stderr)
            return 2
        if not args.apply and not args.interactive:
            print("Preview only. Add --apply or --interactive to perform updates.")
            return 0
        if args.readable_folders and args.repo == DEFAULT_REPO:
            raise UploadError("Readable folder writes to production are blocked until the reader migration is deployed")
        if args.interactive:
            if not sys.stdin.isatty():
                raise UploadError("Interactive approval requires a local console")
            if input("Apply exactly this plan? Type YES: ").strip() != "YES":
                print("Cancelled; no remote changes made.")
                return 0
        from huggingface_hub import get_token
        token = get_token()
        if not token:
            raise UploadError("No Hugging Face token configured")
        if api.dataset_info(args.repo, token=token).sha != sha:
            raise UploadError("Dataset changed since preview; no writes performed")
        expected = sha
        for item in instructions:
            if item["state"] != "UNCHANGED":
                status, expected = apply_item(
                    api, args.repo, token, item,
                    expected_revision=expected, return_revision=True)
                print(f"[{status}] {item['path'].name}")
        return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
