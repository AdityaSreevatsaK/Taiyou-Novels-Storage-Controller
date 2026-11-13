"""Read-only catalogue operations and title collision detection."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
import zipfile
from pathlib import Path

from .paths import validate_book_paths

DEFAULT_REPO = "AdityaSreevatsaK/Taiyous-Novels"


class StorageError(ValueError):
    pass


def validate_catalogue(value: object) -> list[dict]:
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("books"), list):
        raise StorageError("Unsupported data/library.json schema")
    result = []
    seen = set()
    for item in value["books"]:
        if not isinstance(item, dict) or not isinstance(item.get("metadata"), dict):
            raise StorageError("Malformed book entry")
        ident = item.get("id")
        if not isinstance(ident, str) or not re.fullmatch(r"[a-f0-9]{24}", ident):
            raise StorageError("Invalid book ID")
        if ident in seen or item["metadata"].get("id") != ident:
            raise StorageError("Duplicated ID or mismatched metadata")
        try:
            validate_book_paths(item)
        except (ValueError, KeyError, TypeError) as exc:
            raise StorageError("Unexpected or unsafe novel storage path") from exc
        seen.add(ident)
        result.append(item)
    return result


def normalized_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"\w+", text, flags=re.UNICODE))


def rows(books: list[dict]) -> list[dict]:
    out = []
    for b in books:
        m = b["metadata"]
        out.append({"id": b["id"], "title": str(m.get("title") or ""),
                    "author": str(m.get("author") or ""),
                    "chapters": str(m.get("chapterCount") or ""),
                    "epub_path": b["epubPath"], "archive_path": b.get("archivePath") or ""})
    return sorted(out, key=lambda r: (normalized_title(r["title"]), r["id"]))


def conflicts(books: list[dict]) -> list[dict]:
    items = rows(books)
    out = []
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            ta, tb = a["title"].strip(), b["title"].strip()
            if not ta or not tb or a["id"] == b["id"]:
                continue
            kind = ("exact" if ta == tb else
                    "normalised" if normalized_title(ta) == normalized_title(tb) else None)
            if kind:
                out.append({"type": kind, "first_title": ta, "first_id": a["id"],
                            "second_title": tb, "second_id": b["id"]})
    return out


def write_csv(path: Path, data: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(data)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_epub_id(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        matching = [x for x in z.infolist() if not x.is_dir() and
                    x.filename.replace("\\", "/").split("/")[-1].lower() == "source.epub"]
        if len(matching) != 1:
            raise StorageError("Expected exactly one source.epub")
        if matching[0].file_size > 120 * 1024 * 1024:
            raise StorageError("EPUB exceeds size limit")
        return hashlib.sha256(z.read(matching[0])).hexdigest()[:24]


def load_remote(repo: str, token: str | None = None, *,
                allow_empty: bool = False) -> tuple[list[dict], str]:
    """Read an existing catalogue, optionally allowing a brand-new empty dataset.

    Only the novel uploader should set allow_empty=True. An absent catalogue
    does NOT mean an empty library if unrelated files already exist in data/.
    Missing repositories, private access failures and malformed catalogues
    must never be silently treated as empty.
    """
    from huggingface_hub import HfApi, hf_hub_download
    api = HfApi()
    info = api.dataset_info(repo, token=token)
    if info.private is not True:
        raise StorageError("Refusing to operate on a dataset that is not private")
    if not info.sha:
        raise StorageError("Could not determine dataset revision")
    paths = set(api.list_repo_files(
        repo_id=repo, repo_type="dataset", revision=info.sha, token=token))
    if "data/library.json" not in paths:
        if any(path.startswith("data/") for path in paths):
            raise StorageError(
                "Dataset contains data/ files but no data/library.json. "
                "Refusing automatic initialization: inspect or restore the existing files.")
        if not allow_empty:
            raise StorageError(
                "This private dataset has no data/library.json yet. "
                "Run the bulk uploader to initialize it with the first novel.")
        return [], info.sha
    file = hf_hub_download(repo_id=repo, repo_type="dataset", filename="data/library.json",
                           revision=info.sha, token=token)
    catalogue = json.loads(Path(file).read_text(encoding="utf-8"))
    return validate_catalogue(catalogue), info.sha
