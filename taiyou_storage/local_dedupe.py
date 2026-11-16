"""Opt-in, read-only preflight for mixing old and new single-novel ZIPs.

No files are deleted or overwritten. Ambiguous identities, differing chapters
and mismatched source URLs must remain upload-blocking conflicts.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit
from zipfile import ZipFile

from .core import normalized_title
from .upload import UploadError, validate_zip_budget, _entry


def canonical_source(value: str | None) -> str:
    """Conservative stable identity; do not treat arbitrary titles as URLs."""
    if not isinstance(value, str):
        return ""
    try:
        parts = urlsplit(value.strip())
        if (parts.scheme.lower() != "https" or not parts.hostname or
                parts.username or parts.password or parts.port not in (None, 443)):
            return ""
        host = parts.hostname.casefold().removeprefix("www.")
        path = parts.path.rstrip("/") or "/"
        if host == "scribblehub.com":
            series = re.fullmatch(r"/series/([0-9]+)(?:/[^/?#]+)?", path)
            if series:
                path = "/series/" + series.group(1)
        return urlunsplit(("https", host, path, parts.query, ""))
    except (ValueError, AttributeError):
        return ""


def _title_author(meta: dict) -> tuple[str, str] | None:
    title = normalized_title(str(meta.get("title") or ""))
    author = normalized_title(str(meta.get("author") or ""))
    return (title, author) if title and author and author != "unknown author" else None


def inspect_zip(path: Path, meta: dict, epub: bytes) -> dict:
    """Check chapter files and their recorded hashes, never trust filenames."""
    with ZipFile(path) as archive:
        validate_zip_budget(archive)
        manifest = _entry(archive, "chapters.json")
        data = _entry(archive, "metadata.json")
        names = [item.filename.replace("\\", "/") for item in archive.infolist()]
        raw = json.loads(archive.read(data)) if data else {}
        if not isinstance(raw, dict):
            raise UploadError("Local ZIP metadata.json must be an object")
        chapters = None
        if manifest:
            if manifest.file_size > 12 * 1024 * 1024:
                raise UploadError("Oversized chapter manifest")
            rows = json.loads(archive.read(manifest))
            if not isinstance(rows, list) or not rows:
                raise UploadError("Empty or invalid chapters.json")
            prefix = manifest.filename.replace("\\", "/").rsplit("/", 1)
            directory = prefix[0] + "/" if len(prefix) == 2 else ""
            chapters = {}
            for row in rows:
                if not isinstance(row, dict):
                    raise UploadError("Invalid chapter row in ZIP")
                number, name = row.get("position"), row.get("file")
                if (type(number) is not int or number < 1 or
                        not isinstance(name, str) or
                        not re.fullmatch(r"chapter_[A-Za-z0-9_-]+\.txt", name)):
                    raise UploadError("Invalid chapter position or filename")
                full = directory + name
                if number in chapters or full not in names:
                    raise UploadError("Duplicate chapter position or missing TXT")
                # Validate content even if older manifests have no checksums.
                chapter_bytes = archive.read(full)
                if not chapter_bytes:
                    raise UploadError("Empty chapter TXT")
                fingerprint = sha256(chapter_bytes).hexdigest()
                if row.get("sha256") and row["sha256"] != fingerprint:
                    raise UploadError("Chapter manifest checksum mismatch")
                chapters[number] = fingerprint
            if raw.get("chapter_count") not in (None, len(chapters)):
                raise UploadError("Local chapter count contradicts metadata")
        cover = raw.get("cover_image")
        image_present = False
        if isinstance(cover, str) and cover in ("cover.jpg", "cover.png", "cover.webp"):
            match = _entry(archive, cover)
            if match and 100 <= match.file_size <= 8 * 1024 * 1024:
                header = archive.read(match)[:16]
                image_present = (header.startswith(b"\xff\xd8\xff") if cover.endswith(".jpg")
                                 else header.startswith(b"\x89PNG\r\n\x1a\n") if cover.endswith(".png")
                                 else header.startswith(b"RIFF") and header[8:12] == b"WEBP")
    return {
        "chapters": chapters, "count": len(chapters) if chapters is not None
        else int(meta.get("chapterCount") or 0),
        "epub_hash": sha256(epub).hexdigest(),
        "cover": image_present,
        "created": raw.get("created_at_utc") or "",
        "url": canonical_source(meta.get("sourceUrl")),
        "title_author": _title_author(meta),
    }


def _equivalence(a: dict, b: dict) -> bool:
    chapters_a, chapters_b = a["chapters"], b["chapters"]
    if chapters_a is not None and chapters_b is not None:
        if (all(chapters_b.get(p) == h for p, h in chapters_a.items())
                or all(chapters_a.get(p) == h for p, h in chapters_b.items())):
            return True
        return False
    # Legacy archives with no chapter manifest can be dropped only if the
    # whole EPUB is byte-identical, not on title or chapter count alone.
    return a["epub_hash"] == b["epub_hash"]


def _rank(row: dict):
    try:
        timestamp = datetime.fromisoformat(row["created"].replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, OverflowError):
        timestamp = 0
    return (row["count"], timestamp, bool(row["cover"]), row["epub_hash"])



def verified_remote_upgrade(local_item: tuple, remote_archive: Path) -> bool:
    """Allow cover/metadata-only revisions or an append-only chapter upgrade.

    Any changed existing chapter, truncated edition, unknown manifest, or
    inconsistent remote identity is a conflict. Never alter the remote copy.
    """
    from .upload import read_novel
    path, meta, epub, _ = local_item
    remote_meta, remote_epub, _ = read_novel(Path(remote_archive))
    original = inspect_zip(Path(remote_archive), remote_meta, remote_epub)
    candidate = inspect_zip(Path(path), meta, epub)
    if original["url"] and candidate["url"] and original["url"] != candidate["url"]:
        return False
    if (original["title_author"] and candidate["title_author"] and
            original["title_author"] != candidate["title_author"]):
        return False
    if original["epub_hash"] == candidate["epub_hash"]:
        # Matching EPUBs do not excuse contradictory TXT chapter manifests.
        if original["chapters"] is not None and candidate["chapters"] is not None:
            return original["chapters"] == candidate["chapters"]
        return True
    old, new = original["chapters"], candidate["chapters"]
    if old is None or new is None or len(new) < len(old):
        return False
    return all(new.get(position) == digest for position, digest in old.items())

def preflight(local: list[tuple], books: list[dict]) -> tuple[list[tuple], list[dict], list[dict]]:
    """Select one validated ZIP per real book and report every skipped/conflict.

    Union by exact source URL or exact title/author, but only deduplicate
    content proven equivalent. Any disagreement blocks the whole batch.
    """
    if not local:
        return [], [], []
    fingerprints = []
    for item in local:
        path, meta, epub, _ = item
        fingerprints.append(inspect_zip(Path(path), meta, epub))
    roots = list(range(len(local)))
    def find(i):
        while roots[i] != i:
            roots[i] = roots[roots[i]]
            i = roots[i]
        return i
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            roots[rb] = ra
    for i in range(len(local)):
        for j in range(i + 1, len(local)):
            a, b = fingerprints[i], fingerprints[j]
            if ((a["url"] and a["url"] == b["url"]) or
                    (a["title_author"] and a["title_author"] == b["title_author"])):
                union(i, j)
    groups = defaultdict(list)
    for i in range(len(local)):
        groups[find(i)].append(i)
    selected, skipped, conflicts = [], [], []
    for group in groups.values():
        preferred = max(group, key=lambda i: (_rank(fingerprints[i]),
                                              str(local[i][0]).casefold()))
        best = fingerprints[preferred]
        has_conflict = False
        for i in group:
            if i == preferred:
                continue
            candidate = fingerprints[i]
            if ((candidate["url"] and best["url"] and candidate["url"] != best["url"])
                    and (candidate["title_author"] != best["title_author"])):
                has_conflict = True
                conflicts.append({"file": str(local[i][0]), "against": str(local[preferred][0]),
                                  "reason": "Source URL and title/author disagree"})
            elif not _equivalence(candidate, best):
                has_conflict = True
                conflicts.append({"file": str(local[i][0]), "against": str(local[preferred][0]),
                                  "reason": "Different or unverifiable chapter contents"})
            elif (candidate["url"] == best["url"] and candidate["url"] and
                  candidate["title_author"] and best["title_author"] and
                  candidate["title_author"] != best["title_author"]):
                has_conflict = True
                conflicts.append({"file": str(local[i][0]), "against": str(local[preferred][0]),
                                  "reason": "Same source URL but author/title disagree"})
            else:
                skipped.append({"file": str(local[i][0]),
                                "preferred": str(local[preferred][0]),
                                "reason": "Equivalent EPUB or verified chapters"})
        if not has_conflict:
            selected.append(local[preferred])
    # Existing remote catalogue remains authoritative. The unchanged plan()
    # will check all selected records, path collisions and remote revisions.
    return selected, skipped, conflicts
