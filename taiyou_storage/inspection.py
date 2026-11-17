"""Read-only, revision-pinned inspection of Taiyou's private HF dataset.

No HF mutation APIs are imported or called. All reports and caches stay local.
Quick mode establishes only listing-level facts; deep mode checks file bytes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from io import BytesIO
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET
import zipfile

from .core import DEFAULT_REPO, StorageError, normalized_title, sha256_file
from .paths import book_dir, validate_book_paths
from .inspection_manifest import manifest_path, read_manifest, MAX_SIDECAR_BYTES
from .upload import validate_zip_budget

MAX_IMAGE = 12 * 1024 * 1024
MAX_MANIFEST = 12 * 1024 * 1024
MAX_CATALOGUE = 32 * 1024 * 1024
MAX_WORKERS = 4
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
PLACEHOLDER = re.compile(r"(placeholder|generated|default.cover|no.cover|cover.unavailable)", re.I)
POSITION_KEYS = ("position", "chapter_number", "chapterNumber", "number")
FILE_KEYS = ("file", "filename", "path")


def canonical_url(value: object) -> str:
    """Conservative URL identity. No speculative cross-site equivalence."""
    if not isinstance(value, str):
        return ""
    try:
        url = urlsplit(value.strip())
        if url.scheme.lower() not in ("http", "https") or not url.hostname or url.username:
            return ""
        host = url.hostname.casefold().removeprefix("www.")
        port = (":" + str(url.port)) if url.port else ""
        path = url.path.rstrip("/") or "/"
        if path == "/" and not url.query:
            return ""  # A website homepage does not identify one book.
        return urlunsplit(("https", host + port, path, url.query, ""))
    except ValueError:
        return ""


def range_strings(values: list[int]) -> list[str]:
    unique = sorted(set(values))
    if not unique:
        return []
    result = []
    left = right = unique[0]
    for value in unique[1:]:
        if value == right + 1:
            right = value
        else:
            result.append(str(left) if left == right else f"{left}-{right}")
            left = right = value
    result.append(str(left) if left == right else f"{left}-{right}")
    return result


def chapter_positions(records: object, archive_names: set[str] | None = None,
                      complete: bool = False) -> dict:
    """Verify explicit positions, not enumeration order or total chapter count."""
    if not isinstance(records, list):
        return {"status": "UNVERIFIED", "ranges": [], "missing": [],
                "duplicates": [], "count": 0, "reason": "Manifest is not a chapter array"}
    positions, invalid, absent, verified = [], 0, 0, 0
    by_basename = defaultdict(list)
    if archive_names is not None:
        for name in archive_names:
            by_basename[PurePosixPath(name).name.casefold()].append(name)
    for entry in records:
        if not isinstance(entry, dict):
            invalid += 1
            continue
        number = next((entry[k] for k in POSITION_KEYS if k in entry), None)
        if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= 100_000:
            invalid += 1
            continue
        positions.append(number)
        filename = next((entry[k] for k in FILE_KEYS if k in entry), None)
        if archive_names is None:
            continue
        if not isinstance(filename, str) or not filename.strip():
            absent += 1
        else:
            filename = filename.replace("\\", "/")
            if filename.startswith("/") or ".." in PurePosixPath(filename).parts:
                absent += 1
                continue
            filename = filename.lstrip("./")
            matches = ([filename] if filename in archive_names
                       else by_basename.get(PurePosixPath(filename).name.casefold(), []))
            if len(matches) == 1:
                verified += 1
            else:
                absent += 1
    frequencies = Counter(positions)
    duplicates = sorted(n for n, count in frequencies.items() if count > 1)
    missing = [n for n in range(1, max(positions, default=0) + 1) if n not in frequencies]
    problems = bool(duplicates or missing or invalid or absent)
    status = ("INCOMPLETE" if problems else
              "VERIFIED_COMPLETE" if positions and complete and verified == len(positions) else
              "VERIFIED_RANGE" if positions and verified == len(positions) else "UNVERIFIED")
    detail = []
    if invalid:
        detail.append(f"{invalid} malformed chapter entries")
    if absent:
        detail.append(f"{absent} missing or unresolvable chapter files")
    if missing:
        detail.append("Chapter positions have gaps")
    if duplicates:
        detail.append("Chapter positions are duplicated")
    if status == "VERIFIED_RANGE":
        detail.append("Available range verified; end-of-novel not established")
    if status == "UNVERIFIED" and not detail:
        detail.append("No independently verified chapter files")
    return {"status": status, "ranges": range_strings(positions),
            "missing": range_strings(missing), "duplicates": duplicates,
            "count": verified, "manifest_entries": len(records),
            "reason": "; ".join(detail), "malformed": invalid, "absent_files": absent}


def inspect_archive(path: Path) -> dict:
    """Validate ZIP, source EPUB identity and downloader chapter positions."""
    with zipfile.ZipFile(path) as archive:
        validate_zip_budget(archive)
        if archive.testzip():
            raise ValueError("Archive CRC validation failed")
        entries = [item for item in archive.infolist() if not item.is_dir()]
        names = {item.filename for item in entries if item.file_size > 0}
        embedded = [item for item in entries
                    if PurePosixPath(item.filename).name.casefold() == "source.epub"]
        epub_digest = ""
        if len(embedded) == 1 and 0 < embedded[0].file_size <= 120 * 1024 * 1024:
            digest = hashlib.sha256()
            with archive.open(embedded[0]) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            epub_digest = digest.hexdigest()
        matches = [name for name in names if PurePosixPath(name).name.casefold() == "chapters.json"]
        if len(matches) > 1:
            raise ValueError("Multiple chapters.json manifests")
        if not matches:
            details = chapter_positions(None)
        else:
            item = archive.getinfo(matches[0])
            if item.file_size > MAX_MANIFEST:
                raise ValueError("Chapter manifest exceeds size limit")
            manifest = json.loads(archive.read(matches[0]).decode("utf-8-sig"))
            explicit_complete = isinstance(manifest, dict) and manifest.get("complete") is True
            records = manifest.get("chapters") if isinstance(manifest, dict) else manifest
            details = chapter_positions(records, names, complete=explicit_complete)
        details["embedded_epub_count"] = len(embedded)
        details["embedded_epub_sha256"] = epub_digest
        return details

def validate_epub(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        validate_zip_budget(archive, epub=True)
        names = set(archive.namelist())
        if "mimetype" not in names or "META-INF/container.xml" not in names:
            raise ValueError("EPUB lacks mimetype or container.xml")
        if archive.testzip():
            raise ValueError("EPUB CRC validation failed")
        if archive.getinfo("META-INF/container.xml").file_size > 1024 * 1024:
            raise ValueError("EPUB container.xml too large")
        root = ET.fromstring(archive.read("META-INF/container.xml"))
        entry = next((node for node in root.iter() if node.tag.endswith("rootfile")), None)
        opf = entry.get("full-path") if entry is not None else None
        if not opf or opf not in names:
            raise ValueError("EPUB package document missing")


def valid_image(data: bytes, suffix: str) -> bool:
    if not 0 < len(data) <= MAX_IMAGE or suffix.lower() not in IMAGE_SUFFIXES:
        return False
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG",
                                ".webp": "WEBP"}[suffix.lower()]:
                return False
            width, height = image.size
            if width < 80 or height < 100 or width * height > 30_000_000:
                return False
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
        return True
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return False


def embedded_cover(epub: Path) -> bool:
    """Require an explicit OPF cover declaration, not an arbitrary EPUB image."""
    with zipfile.ZipFile(epub) as z:
        validate_zip_budget(z, epub=True)
        if z.getinfo("META-INF/container.xml").file_size > 1024 * 1024:
            return False
        root = ET.fromstring(z.read("META-INF/container.xml"))
        entry = next((e for e in root.iter() if e.tag.endswith("rootfile")), None)
        opf = entry.get("full-path") if entry is not None else None
        if not opf or z.getinfo(opf).file_size > 8 * 1024 * 1024:
            return False
        package = ET.fromstring(z.read(opf))
        ids = set()
        hrefs = {}
        for element in package.iter():
            if element.tag.endswith("item"):
                ident, href = element.get("id"), element.get("href")
                if ident and href:
                    hrefs[ident] = href
                if "cover-image" in element.get("properties", "").split():
                    ids.add(ident)
            elif element.tag.endswith("meta") and element.get("name", "").lower() == "cover":
                ids.add(element.get("content"))
        base = PurePosixPath(opf).parent
        for ident in ids:
            href = hrefs.get(ident)
            if not href:
                continue
            full = str(base / href) if str(base) != "." else href
            if (".." in PurePosixPath(full).parts or full not in z.namelist()
                    or PLACEHOLDER.search(PurePosixPath(full).name)):
                continue
            item = z.getinfo(full)
            if item.file_size <= MAX_IMAGE and valid_image(z.read(full), PurePosixPath(full).suffix):
                return True
    return False


@dataclass
class Snapshot:
    revision: str
    files: dict[str, int | None]
    identities: dict[str, dict] = field(default_factory=dict)


class HFReadOnly:
    """The sole network boundary. Inject a fixture implementation for tests."""
    def __init__(self, repo: str = DEFAULT_REPO, token: str | None = None):
        self.repo, self.token = repo, token

    def snapshot(self) -> Snapshot:
        from huggingface_hub import HfApi
        api = HfApi()
        info = api.dataset_info(self.repo, token=self.token)
        if info.private is not True or not info.sha:
            raise StorageError("Dataset must be private and have an immutable revision")
        revision = info.sha
        files = {}
        identities = {}
        try:
            tree = api.list_repo_tree(repo_id=self.repo, repo_type="dataset",
                                      recursive=True, revision=revision, token=self.token)
            for entry in tree:
                path = getattr(entry, "path", None)
                if path and not path.endswith("/") and not entry.__class__.__name__.endswith("Folder"):
                    size = getattr(entry, "size", None)
                    files[path] = size
                    lfs = getattr(entry, "lfs", None)
                    digest = (lfs.get("sha256") if isinstance(lfs, dict)
                              else getattr(lfs, "sha256", None))
                    identities[path] = {
                        "size": size,
                        "blob_id": getattr(entry, "blob_id", None),
                        "sha256": digest,
                    }
        except (AttributeError, TypeError, NotImplementedError):
            files = {p: None for p in api.list_repo_files(
                repo_id=self.repo, repo_type="dataset", revision=revision, token=self.token)}
        return Snapshot(revision, files, identities)

    def download(self, name: str, revision: str) -> Path:
        from huggingface_hub import hf_hub_download
        return Path(hf_hub_download(repo_id=self.repo, repo_type="dataset",
                                    filename=name, revision=revision, token=self.token))


def _issue(ident: str, kind: str, severity: str, evidence: str, action: str) -> dict:
    return {"novel_id": ident, "code": kind, "severity": severity,
            "evidence": evidence, "recommended_action": action}


def _book_id(item: object) -> str:
    return str(item.get("id", "")) if isinstance(item, dict) else ""


def inspect_book(book: dict, files: dict, revision: str, backend: HFReadOnly,
                 mode: str, identities: dict[str, dict] | None = None) -> tuple[dict, list[dict]]:
    ident = _book_id(book)
    meta = book.get("metadata") if isinstance(book.get("metadata"), dict) else {}
    title = str(meta.get("title") or "")
    archive = book.get("archivePath")
    epub = book.get("epubPath")
    source = str(meta.get("sourceUrl") or "")
    row = {"novel_id": ident, "title": title, "author": str(meta.get("author") or ""),
           "source_url": source, "catalogue_chapter_count": meta.get("chapterCount"),
           "stored_chapter_count": None, "chapter_ranges": [], "missing_chapters": [],
           "duplicate_positions": [], "verification_status": "UNVERIFIED",
           "verification_reason": "Quick scan; chapters not inspected",
           "cover_status": "UNVERIFIED", "cover_reason": "Not checked",
           "epub_path": epub or "", "archive_path": archive or "", "epub_sha256": ""}
    issues = []
    try:
        folder = validate_book_paths(book)
    except (TypeError, KeyError, ValueError) as exc:
        issues.append(_issue(ident, "INVALID_CATALOGUE_PATH", "HIGH", str(exc),
                             "Repair the catalogue path after verifying the original files"))
        row["cover_reason"] = "Unsafe or malformed catalogue references"
        return row, issues
    if not title or not meta.get("author") or str(meta.get("author")).casefold() in ("unknown", "unknown author", "n/a") or not source:
        issues.append(_issue(ident, "MISSING_METADATA", "LOW", "Title or author absent",
                             "Recover verified source metadata"))
    if not isinstance(epub, str) or epub not in files:
        issues.append(_issue(ident, "MISSING_EPUB", "CRITICAL", str(epub),
                             "Restore source.epub from a verified backup"))
    if not archive or archive not in files:
        issues.append(_issue(ident, "MISSING_ARCHIVE", "HIGH", str(archive),
                             "Recover original.zip from a verified backup"))
    cover = meta.get("coverPath") or book.get("coverPath")
    candidates = sorted(p for p in files if p.startswith(folder + "/cover")
                        and PurePosixPath(p).suffix.casefold() in IMAGE_SUFFIXES
                        and PurePosixPath(p).parent.as_posix() == folder)
    provenance = str(meta.get("coverSource") or meta.get("coverOrigin") or "").casefold()
    generated = bool(meta.get("coverGenerated") or meta.get("generatedCover") or
                     meta.get("coverIsGenerated") or any(word in provenance for word in
                     ("placeholder", "generated", "fallback", "synthetic")))
    if cover and cover not in files:
        row["cover_status"], row["cover_reason"] = "BROKEN", "Referenced cover file is absent"
    elif generated or (cover and PLACEHOLDER.search(str(cover))):
        row["cover_status"], row["cover_reason"] = "UNVERIFIED", "Possible generated placeholder"
    elif mode in ("quick", "manifest"):
        row["cover_status"] = "UNVERIFIED"
        row["cover_reason"] = ("Standalone image exists but bytes not checked" if candidates
                               else "No standalone image; embedded cover not checked")
    else:
        try:
            chosen = cover if cover else candidates[0] if len(candidates) == 1 else ""
            if chosen and chosen in files:
                path = backend.download(chosen, revision)
                if path.stat().st_size > MAX_IMAGE:
                    raise ValueError("Cover exceeds maximum image size")
                if valid_image(path.read_bytes(), PurePosixPath(chosen).suffix):
                    row["cover_status"] = "AVAILABLE"
                    row["cover_reason"] = "Decoded standalone image" + (" (not linked)" if not cover else "")
                    if not cover:
                        issues.append(_issue(ident, "UNLINKED_COVER", "LOW", chosen,
                                             "Link this existing cover in the catalogue"))
                else:
                    row["cover_status"], row["cover_reason"] = "BROKEN", "Standalone image is corrupt or invalid"
            elif candidates:
                row["cover_status"], row["cover_reason"] = "UNVERIFIED", "Ambiguous standalone cover candidates"
            elif epub in files:
                row["cover_status"] = ("EMBEDDED_ONLY" if embedded_cover(backend.download(epub, revision))
                                       else "MISSING")
                row["cover_reason"] = ("Valid OPF-declared embedded cover" if row["cover_status"] == "EMBEDDED_ONLY"
                                        else "No valid standalone or declared embedded cover")
            else:
                row["cover_status"], row["cover_reason"] = "UNVERIFIED", "EPUB unavailable for embedded-cover check"
        except Exception as exc:
            row["cover_status"], row["cover_reason"] = "UNVERIFIED", f"Cover check failed: {type(exc).__name__}"
            issues.append(_issue(ident, "COVER_SCAN_FAILED", "MEDIUM", type(exc).__name__,
                                 "Retry the deep scan once remote access recovers"))
    if row["cover_status"] in {"MISSING", "BROKEN"}:
        issues.append(_issue(ident, "COVER_" + row["cover_status"], "MEDIUM",
                             row["cover_reason"], "Restore an authentic cover and repair its reference"))
    if mode == "manifest":
        sidecar = manifest_path(book)
        if sidecar not in files:
            row["verification_reason"] = "No remote inspection manifest; run the one-time backfill"
            issues.append(_issue(ident, "INSPECTION_MANIFEST_MISSING", "LOW", sidecar,
                                 "Backfill a verified sidecar without modifying the novel"))
        else:
            try:
                if isinstance(files[sidecar], int) and files[sidecar] > MAX_SIDECAR_BYTES:
                    raise ValueError("Sidecar exceeds size limit")
                stored = backend.download(sidecar, revision)
                if stored.stat().st_size > MAX_SIDECAR_BYTES:
                    raise ValueError("Sidecar exceeds size limit")
                values, saved_issues = read_manifest(
                    book, stored.read_bytes(), files, identities or {})
                row.update(values)
                issues.extend(saved_issues)
            except Exception as exc:
                row["verification_reason"] = "Manifest stale or unreadable: " + type(exc).__name__
                issues.append(_issue(ident, "INSPECTION_MANIFEST_STALE", "MEDIUM",
                                     type(exc).__name__,
                                     "Rebuild manifest against the current novel files"))
        if row["cover_status"] in {"MISSING", "BROKEN"} and not any(
                i["code"] == "COVER_" + row["cover_status"] for i in issues):
            issues.append(_issue(ident, "COVER_" + row["cover_status"], "MEDIUM",
                                 row["cover_reason"], "Restore an authentic cover"))
        return row, issues
    if mode != "deep":
        return row, issues
    if archive not in files:
        row["verification_reason"] = "Original archive missing; chapter range unknown"
    epub_valid = False
    if epub in files:
        try:
            epub_path = backend.download(epub, revision)
            validate_epub(epub_path)
            row["epub_sha256"] = sha256_file(epub_path)
            epub_valid = True
        except Exception as exc:
            issues.append(_issue(ident, "CORRUPT_EPUB", "HIGH", type(exc).__name__ + ": " + str(exc),
                                 "Restore or regenerate EPUB from verified source"))
    if archive in files:
        try:
            details = inspect_archive(backend.download(archive, revision))
            if details.get("embedded_epub_count") != 1 or not details.get("embedded_epub_sha256"):
                issues.append(_issue(ident, "MISSING_EMBEDDED_EPUB", "MEDIUM",
                                     "Original archive lacks one valid source.epub",
                                     "Check the original ZIP's EPUB provenance"))
            elif row["epub_sha256"] and details["embedded_epub_sha256"] != row["epub_sha256"]:
                issues.append(_issue(ident, "EPUB_ARCHIVE_MISMATCH", "HIGH",
                                     "Stored source.epub differs from original.zip embedded EPUB",
                                     "Compare both editions and restore the authoritative copy"))
            row.update({"stored_chapter_count": details.get("count"),
                        "chapter_ranges": details.get("ranges", []),
                        "missing_chapters": details.get("missing", []),
                        "duplicate_positions": details.get("duplicates", []),
                        "verification_status": details["status"],
                        "verification_reason": details.get("reason", "")})
            if details["status"] == "INCOMPLETE":
                issues.append(_issue(ident, "INCOMPLETE_CHAPTERS", "HIGH",
                                     row["verification_reason"] + "; gaps=" + str(row["missing_chapters"]),
                                     "Re-download the missing chapter positions and verify files"))
            if details["status"] == "UNVERIFIED":
                issues.append(_issue(ident, "CHAPTER_COVERAGE_UNKNOWN", "LOW",
                                     row["verification_reason"], "Obtain verified chapter manifest"))
            reported = meta.get("chapterCount")
            if isinstance(reported, int) and reported > 0 and details.get("manifest_entries") is not None:
                if reported != details["manifest_entries"]:
                    if row["verification_status"] == "VERIFIED_COMPLETE":
                        row["verification_status"] = "UNVERIFIED"
                        row["verification_reason"] = "Explicit completion conflicts with catalogue chapter count"
                    issues.append(_issue(ident, "CHAPTER_COUNT_MISMATCH", "MEDIUM",
                                         f"Catalogue={reported}, manifest={details['manifest_entries']}",
                                         "Verify the download and reconcile catalogue metadata"))
        except Exception as exc:
            row["verification_reason"] = "Archive inspection failed: " + type(exc).__name__
            issues.append(_issue(ident, "CORRUPT_OR_UNREADABLE_ARCHIVE", "HIGH",
                                 type(exc).__name__ + ": " + str(exc),
                                 "Retry or restore the original archive"))
    if any(issue["code"] == "EPUB_ARCHIVE_MISMATCH" for issue in issues):
        row["verification_status"] = "UNVERIFIED"
        row["verification_reason"] = "Stored EPUB differs from original archive"
    if not epub_valid and row["verification_status"] == "VERIFIED_COMPLETE":
        row["verification_status"] = "UNVERIFIED"
        row["verification_reason"] = "EPUB not validated; source archive alone cannot prove reader completeness"
    return row, issues


def duplicate_candidates(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for r in rows:
        author = normalized_title(r["author"])
        title = normalized_title(r["title"])
        source = canonical_url(r["source_url"])
        if source:
            grouped["source:" + source].append(r)
        digest = r.get("epub_sha256") or ""
        if re.fullmatch(r"[a-f0-9]{64}", digest):
            grouped["epub-sha256:" + digest].append(r)
        if title and author:
            grouped["title-author:" + title + "|" + author].append(r)
    matches = []
    seen = set()
    for key, group in grouped.items():
        for i, first in enumerate(group):
            for second in group[i + 1:]:
                pair = tuple(sorted((first["novel_id"], second["novel_id"])))
                if pair not in seen and pair[0] != pair[1]:
                    seen.add(pair)
                    matches.append({"first_id": pair[0], "second_id": pair[1],
                                    "reason": key.split(":", 1)[0], "review_required": True})
    return matches


def scan(backend: HFReadOnly, mode: str = "manifest", cache_root: Path | None = None,
         workers: int = 3) -> dict:
    if mode not in {"quick", "manifest", "deep"}:
        raise ValueError("mode must be quick, manifest or deep")
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError("workers must be between 1 and 4")
    snapshot = backend.snapshot()
    if "data/library.json" not in snapshot.files:
        raise StorageError("No data/library.json at pinned revision")
    catalogue = backend.download("data/library.json", snapshot.revision)
    if catalogue.stat().st_size > MAX_CATALOGUE:
        raise StorageError("Catalogue exceeds safety limit")
    payload = json.loads(catalogue.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("books"), list):
        raise StorageError("Unsupported catalogue format")
    books = payload["books"]
    results, problems = [], []
    def work(item):
        ident = _book_id(item)
        if not isinstance(item, dict):
            return ({"novel_id": ident, "title": "", "author": "", "source_url": "",
                     "verification_status": "UNVERIFIED", "cover_status": "UNVERIFIED"}, [
                         _issue(ident, "MALFORMED_BOOK", "HIGH", "Catalogue entry is not an object",
                                "Repair the catalogue record")])
        cached = None
        if cache_root is not None and mode == "deep":
            fingerprint = hashlib.sha256(("inspection-v2|" + snapshot.revision + "|" + ident + "|" +
                                           json.dumps(item, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()
            cached = cache_root / snapshot.revision / (fingerprint + ".json")
            if cached.exists():
                try:
                    return tuple(json.loads(cached.read_text(encoding="utf-8")))
                except (ValueError, OSError):
                    pass
        try:
            value = inspect_book(item, snapshot.files, snapshot.revision, backend, mode,
                                 snapshot.identities)
        except Exception as exc:
            value = ({"novel_id": ident, "title": "", "author": "", "source_url": "",
                      "verification_status": "UNVERIFIED", "cover_status": "UNVERIFIED"}, [
                          _issue(ident, "INSPECTION_FAILED", "HIGH", type(exc).__name__,
                                 "Retry the scan; do not assume this book is complete")])
        transient = {"INSPECTION_FAILED", "COVER_SCAN_FAILED", "CORRUPT_OR_UNREADABLE_ARCHIVE"}
        if cached is not None and not any(issue["code"] in transient for issue in value[1]):
            cached.parent.mkdir(parents=True, exist_ok=True)
            tmp = cached.with_suffix(".tmp")
            tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            tmp.replace(cached)
        return value
    interrupted = False
    executor = ThreadPoolExecutor(max_workers=workers)
    futures = {executor.submit(work, item): item for item in books}
    visited = set()
    try:
        for future in as_completed(futures):
            row, issues = future.result()
            results.append(row)
            problems.extend(issues)
            visited.add(future)
    except KeyboardInterrupt:
        interrupted = True
        for future in futures:
            if not future.done():
                future.cancel()
        for future, item in futures.items():
            if future in visited:
                continue
            if future.done() and not future.cancelled():
                try:
                    row, issues = future.result()
                    results.append(row)
                    problems.extend(issues)
                    visited.add(future)
                except BaseException:
                    pass
        for future, item in futures.items():
            if future in visited:
                continue
            meta = item.get("metadata", {}) if isinstance(item, dict) else {}
            ident = _book_id(item)
            results.append({"novel_id": ident, "title": str(meta.get("title") or ""),
                            "author": str(meta.get("author") or ""),
                            "source_url": str(meta.get("sourceUrl") or ""),
                            "verification_status": "UNVERIFIED", "cover_status": "UNVERIFIED",
                            "verification_reason": "Scan interrupted before verification",
                            "cover_reason": "Scan interrupted"})
            problems.append(_issue(ident, "SCAN_INTERRUPTED", "MEDIUM",
                                   "Book not verified at pinned revision",
                                   "Rerun the scan when connectivity is stable"))
    finally:
        executor.shutdown(wait=True, cancel_futures=interrupted)
    results.sort(key=lambda r: (normalized_title(r.get("title", "")), r.get("novel_id", "")))
    known_dirs = set()
    for item in books:
        try:
            known_dirs.add(book_dir(item))
        except (TypeError, KeyError, ValueError):
            pass
    disk_dirs = {"/".join(PurePosixPath(name).parts[:3]) for name in snapshot.files
                 if name.startswith("data/novels/") and len(PurePosixPath(name).parts) >= 4}
    for directory in sorted(disk_dirs - known_dirs):
        problems.append(_issue("", "ORPHAN_NOVEL_DIRECTORY", "HIGH", directory,
                               "Inspect the orphan and reconcile the catalogue without deleting it"))
    ids = [r["novel_id"] for r in results if r.get("novel_id")]
    for ident, count in Counter(ids).items():
        if count > 1:
            problems.append(_issue(ident, "DUPLICATE_ID", "HIGH", f"{count} catalogue entries",
                                   "Resolve duplicate catalogue references safely"))
    duplicates = duplicate_candidates(results)
    for match in duplicates:
        problems.append(_issue(match["first_id"], "SUSPICIOUS_DUPLICATE", "MEDIUM",
                               match["second_id"] + " (" + match["reason"] + ")",
                               "Manually compare editions before deciding whether to merge"))
    return {"schema_version": 1, "revision": snapshot.revision, "mode": mode,
            "total_storage_bytes": sum(size for size in snapshot.files.values() if isinstance(size, int)),
            "storage_size_verified": all(isinstance(v, int) for v in snapshot.files.values()),
            "novels": results, "issues": problems, "duplicate_candidates": duplicates,
            "interrupted": interrupted}


def compare_retriever(rows: list[dict], registry: dict | None,
                      planned: list[dict] | None) -> dict:
    """Conservative identity matching. Never publish this result to GitHub."""
    by_url, by_name, by_digest = defaultdict(set), defaultdict(set), defaultdict(set)
    identities = {}
    for row in rows:
        ident = row.get("novel_id", "")
        url = canonical_url(row.get("source_url"))
        identities[ident] = row
        if url:
            by_url[url].add(ident)
        digest = row.get("epub_sha256") or ""
        if re.fullmatch(r"[a-f0-9]{64}", digest):
            by_digest[digest].add(ident)
        title = normalized_title(row.get("title") or "")
        author = normalized_title(row.get("author") or "")
        if title and author:
            by_name[(title, author)].add(ident)
    def match(item):
        url = canonical_url(item.get("url") or item.get("source_url") or item.get("sourceUrl"))
        ids = by_url.get(url, set()) if url else set()
        digest = str(item.get("epub_sha256") or "")
        if re.fullmatch(r"[a-f0-9]{64}", digest) and by_digest.get(digest):
            matched = by_digest[digest]
            if len(matched) == 1:
                return "ALREADY_IN_HF", sorted(matched), "identical EPUB SHA-256"
            return "AMBIGUOUS", sorted(matched), "multiple identical EPUB content records"
        if len(ids) == 1:
            existing = identities[next(iter(ids))]
            author = normalized_title(str(item.get("author") or ""))
            stored_author = normalized_title(existing.get("author") or "")
            if author and stored_author and author != stored_author:
                return "AMBIGUOUS", sorted(ids), "source URL matches but author differs"
            return "ALREADY_IN_HF", sorted(ids), "source URL"
        if len(ids) > 1:
            return "AMBIGUOUS", sorted(ids), "multiple matching source URLs"
        title = normalized_title(str(item.get("title") or ""))
        author = normalized_title(str(item.get("author") or ""))
        if title and author and len(by_name.get((title, author), set())) == 1:
            candidates = sorted(by_name[(title, author)])
            if url and any(canonical_url(identities[ident].get("source_url")) not in ("", url)
                           for ident in candidates):
                return "AMBIGUOUS", candidates, "same title and author but different source URLs"
            return "ALREADY_IN_HF", candidates, "title and author"
        if title and author and len(by_name.get((title, author), set())) > 1:
            return "AMBIGUOUS", sorted(by_name[(title, author)]), "multiple title/author matches"
        if title and not author and any(t == title for t, _ in by_name):
            return "AMBIGUOUS", [], "same title but author missing"
        return "NOT_IN_HF", [], "no conservative match"
    output = []
    known = set()
    for group, records in (("download_registry", (registry or {}).get("novels", [])),
                           ("planned", planned or [])):
        for item in records:
            if not isinstance(item, dict):
                continue
            key = (canonical_url(item.get("url") or item.get("source_url") or ""),
                   normalized_title(str(item.get("title") or "")))
            if key in known:
                continue
            known.add(key)
            status, ids, reason = match(item)
            downloads = item.get("downloads") if isinstance(item.get("downloads"), list) else []
            completed = [d for d in downloads if isinstance(d, dict) and d.get("status") == "complete"]
            recorded = bool(completed)
            partial = recorded and all(str(d.get("range") or "all").casefold() != "all"
                                       for d in completed)
            output.append({"title": str(item.get("title") or ""), "author": str(item.get("author") or ""),
                           "source_url": str(item.get("url") or item.get("source_url") or ""),
                           "state": ("ALREADY_IN_HF" if status == "ALREADY_IN_HF" else
                                     "AMBIGUOUS" if status == "AMBIGUOUS" else
                                     "PARTIALLY_DOWNLOADED" if partial else
                                     "DOWNLOADED_NOT_UPLOADED" if recorded else "TO_DOWNLOAD"),
                           "hf_ids": ids, "reason": reason,
                           "download_recorded": recorded,
                           "download_ranges": [str(d.get("range") or "unknown") for d in completed]})
    # Hashes are local-only, intentionally without titles or novel IDs.
    hashes = sorted({hashlib.sha256(url.encode("utf-8")).hexdigest()
                     for row in rows if (url := canonical_url(row.get("source_url")))})
    return {"records": output,
            "exclusions": {"schema_version": 1, "algorithm": "sha256-canonical-url-v1",
                           "source_url_sha256": hashes,
                           "warning": "Private local file; hashes can be dictionary-guessed. Never commit."}}
