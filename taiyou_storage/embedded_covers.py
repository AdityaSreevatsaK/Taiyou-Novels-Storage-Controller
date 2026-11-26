"""Extract only proven ZIP/OPF EPUB cover art for guarded bulk imports.

Never scrape external websites, guess from chapter illustrations, overwrite
an existing linked cover, or bypass the bulk revision-guarded commit.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET
import zipfile

from .upload import UploadError, validate_zip_budget

MAX_COVER = 12 * 1024 * 1024
EXTENSIONS = {".jpeg": ".jpg", ".jpg": ".jpg",
              ".png": ".png", ".webp": ".webp"}
NAMES = {"cover", "front", "book-cover"}


def _valid(data: bytes, extension: str) -> bool:
    from .inspection import valid_image
    return 0 < len(data) <= MAX_COVER and valid_image(data, extension)


def _checked_member(z: zipfile.ZipFile, name: str) -> tuple[bytes, str] | None:
    path = PurePosixPath(name)
    ext = EXTENSIONS.get(path.suffix.lower())
    if (not ext or path.is_absolute() or ".." in path.parts
            or name not in z.namelist()):
        return None
    member = z.getinfo(name)
    if (member.is_dir() or not 0 < member.file_size <= MAX_COVER):
        return None
    raw = z.read(member)
    return (raw, ext) if _valid(raw, ext) else None


def epub_declared_cover(epub: bytes) -> tuple[bytes, str] | None:
    """Resolve a single EPUB2 meta cover or EPUB3 manifest cover-image."""
    try:
        with zipfile.ZipFile(BytesIO(epub)) as z:
            validate_zip_budget(z, epub=True)
            metadata = z.getinfo("META-INF/container.xml")
            if not 0 < metadata.file_size <= 1024 * 1024:
                return None
            container = ET.fromstring(z.read(metadata))
            rootfile = next((node for node in container.iter()
                             if node.tag.rsplit("}", 1)[-1] == "rootfile"), None)
            opf = rootfile.get("full-path") if rootfile is not None else None
            if (not opf or PurePosixPath(opf).is_absolute()
                    or ".." in PurePosixPath(opf).parts
                    or opf not in z.namelist()
                    or z.getinfo(opf).file_size > 8 * 1024 * 1024):
                return None
            package = ET.fromstring(z.read(opf))
            items: dict[str, str] = {}
            references: set[str] = set()
            for node in package.iter():
                tag = node.tag.rsplit("}", 1)[-1]
                if tag == "item":
                    ident, href = node.get("id"), node.get("href")
                    if ident and href:
                        items[ident] = href
                        if "cover-image" in node.get("properties", "").split():
                            references.add(ident)
                elif tag == "meta" and node.get("name", "").casefold() == "cover":
                    if node.get("content"):
                        references.add(node.get("content"))
            # Conflicting cover declarations are not evidence for selection.
            declared = {items[ident] for ident in references if ident in items}
            if len(declared) != 1:
                return None
            href = next(iter(declared))
            if ("?" in href or "#" in href or "%" in href or
                    PurePosixPath(href).is_absolute()
                    or ".." in PurePosixPath(href).parts):
                return None
            folder = PurePosixPath(opf).parent
            name = str(folder / href) if str(folder) != "." else href
            return _checked_member(z, name)
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError,
            UploadError, ValueError, RuntimeError):
        return None


def zip_standalone_cover(path: Path) -> tuple[bytes, str] | None:
    """Only an unambiguous, explicitly named image beside source.epub."""
    try:
        with zipfile.ZipFile(path) as z:
            validate_zip_budget(z)
            epub_members = [i for i in z.infolist()
                            if not i.is_dir()
                            and PurePosixPath(i.filename).name.casefold() == "source.epub"]
            if len(epub_members) != 1:
                return None
            directory = PurePosixPath(epub_members[0].filename).parent
            candidates = [
                info.filename for info in z.infolist()
                if not info.is_dir()
                and PurePosixPath(info.filename).parent == directory
                and PurePosixPath(info.filename).stem.casefold() in NAMES
                and PurePosixPath(info.filename).suffix.lower() in EXTENSIONS
            ]
            if len(candidates) != 1:
                return None
            return _checked_member(z, candidates[0])
    except (OSError, zipfile.BadZipFile, UploadError, KeyError, ValueError):
        return None


def attach_embedded_covers(items: list[dict]) -> tuple[list[dict], int]:
    """Attach validated, immutable preview bytes; a local sidecar wins.

    The bulk upload revalidates the source ZIP's SHA-256 and the cover
    digest before committing. Missing or invalid art is not a novel conflict.
    """
    rows = []
    missing = 0
    for item in items:
        if item.get("state") == "CONFLICT":
            continue
        if item.get("cover"):
            continue
        existing_cover = (item.get("existing") or {}).get("metadata", {}).get("coverPath")
        if existing_cover:
            # Existing personal/source artwork must never be silently replaced.
            continue
        image = epub_declared_cover(item["epub"])
        provenance = "EPUB OPF-declared"
        if image is None:
            image = zip_standalone_cover(item["path"])
            provenance = "archive standalone"
        if image is None:
            missing += 1
            continue
        raw, extension = image
        item["cover"] = {
            "novel_id": item["id"],
            "destination": item["directory"] + "/cover" + extension,
            "extension": extension,
            "sha256": sha256(raw).hexdigest(),
            "bytes": raw,
            "kind": "embedded",
        }
        rows.append({"file": item["path"].name, "state": "COVER_EMBEDDED",
                     "reason": provenance + " image verified"})
    return rows, missing
