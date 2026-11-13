"""Strict, backwards-compatible dataset folder paths for stored novels.

Book IDs are immutable. A readable directory is a DISPLAY label, not an ID,
and is deliberately not regenerated when a book title later changes.
"""
from __future__ import annotations

import re
import unicodedata

ID_RE = re.compile(r"^[a-f0-9]{24}$")
SAFE_LABEL_RE = re.compile(r"^[\w .,!'()+&-]{1,96}$", re.UNICODE)
BASE = "data/novels"
COVER_SUFFIXES = (".jpg", ".png", ".webp", ".jpeg")


def readable_label(title: str) -> str:
    """Build a bounded, Unicode-friendly HF path component from a title."""
    if not isinstance(title, str):
        raise ValueError("Novel title must be a string")
    title = unicodedata.normalize("NFKC", title)
    title = re.sub(r"[^\w .,!'()+&-]", " ", title, flags=re.UNICODE)
    title = re.sub(r"\.{2,}", ".", title)
    title = " ".join(title.split()).strip(" .")
    title = title[:96].rstrip(" .")
    return title if title else "Untitled"


def legacy_dir(book_id: str) -> str:
    if not isinstance(book_id, str) or not ID_RE.fullmatch(book_id):
        raise ValueError("Invalid 24-character novel ID")
    return f"{BASE}/{book_id}"


def readable_dir(book_id: str, title: str) -> str:
    return legacy_dir(book_id) + " - " + readable_label(title)


def folder_from_epub_path(book_id: str, path: str) -> str:
    """Return the book's actual validated directory for legacy or new layout.

    Never trust a user-controlled path or use partial prefix matching. The
    folder label need not equal the book's *current* title: titles can change
    without moving files.
    """
    prefix = legacy_dir(book_id)
    if not isinstance(path, str) or not path.endswith("/source.epub"):
        raise ValueError("Unexpected novel EPUB path")
    directory = path[:-len("/source.epub")]
    if directory == prefix:
        return directory
    if not directory.startswith(prefix + " - "):
        raise ValueError("EPUB path does not belong to the novel ID")
    label = directory[len(prefix) + 3:]
    if (not SAFE_LABEL_RE.fullmatch(label) or label != label.strip(" .")
            or ".." in label or "/" in label or "\\" in label):
        raise ValueError("Unsafe readable novel directory label")
    return directory


def book_dir(book: dict) -> str:
    return folder_from_epub_path(book["id"], book["epubPath"])


def book_file(book: dict, filename: str) -> str:
    if filename not in ("source.epub", "original.zip", "cover.jpg", "cover.png", "cover.webp", "cover.jpeg"):
        raise ValueError("Unexpected novel filename")
    return book_dir(book) + "/" + filename


def validate_book_paths(book: dict) -> str:
    """Check every explicitly declared path stays in exactly one book folder."""
    directory = book_dir(book)
    archive = book.get("archivePath")
    if archive is not None and archive != directory + "/original.zip":
        raise ValueError("Novel archive path does not match EPUB directory")
    cover = book.get("coverPath", book.get("metadata", {}).get("coverPath"))
    if cover is not None and cover not in {directory + "/cover" + suffix for suffix in COVER_SUFFIXES}:
        raise ValueError("Novel cover path does not match EPUB directory")
    metadata_cover = book.get("metadata", {}).get("coverPath")
    if metadata_cover is not None and metadata_cover not in {
            directory + "/cover" + suffix for suffix in COVER_SUFFIXES}:
        raise ValueError("Novel metadata cover path does not match EPUB directory")
    return directory
