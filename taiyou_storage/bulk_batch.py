"""Atomic multi-novel batches and optional local cover discovery.

This module uses the bulk uploader's validated preview. It never silently
guesses cover identity or modifies local input ZIPs. Each batch stages one
catalogue and commits with Hugging Face optimistic concurrency.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from .core import normalized_title, sha256_file, validate_catalogue
from .paths import book_dir, folder_from_epub_path
from .upload import UploadError, _pinned_dataset_info, matching_entry, merged_metadata

IMAGE_EXTENSIONS = {".jpg": ".jpg", ".jpeg": ".jpg",
                    ".png": ".png", ".webp": ".webp"}
MAX_COVER_BYTES = 12 * 1024 * 1024
MAX_BATCH_SIZE = 10


def discover_covers(instructions: list[dict], folder: Path) -> tuple[list[dict], list[dict]]:
    """Attach unambiguous existing image files to the EXACT local upload targets.

    Supported:
    - covers/Novel Title.jpg
    - covers/novel-zip-filename.png
    - covers/<24-hex novel ID>.webp
    - covers/Novel Title/cover.jpg
    - covers/<24-hex novel ID>/cover.jpg

    An image with no unique match stays unresolved, never assigned by guess.
    """
    if not folder.exists():
        return [], []
    if not folder.is_dir():
        return [], [{"file": str(folder), "state": "COVER_CONFLICT",
                     "reason": "Covers path is not a directory"}]
    alias_map: dict[str, list[dict]] = {}
    id_map = {}
    for item in instructions:
        if item["state"] == "CONFLICT":
            continue
        id_map[item["id"]] = item
        for alias in {normalized_title(item["metadata"]["title"]),
                      normalized_title(item["path"].stem)}:
            if alias:
                alias_map.setdefault(alias, []).append(item)

    candidates, problems, seen = [], [], {}
    for path in sorted(p for p in folder.rglob("*") if p.is_file()
                       and p.suffix.lower() in IMAGE_EXTENSIONS):
        relative = path.relative_to(folder)
        if len(relative.parts) > 3:
            problems.append({"file": str(relative), "state": "COVER_CONFLICT",
                             "reason": "Cover is nested too deeply"})
            continue
        key = path.stem if path.stem.casefold() not in {"cover", "front", "book-cover"} else (
            relative.parent.name if len(relative.parts) > 1 else "")
        match = re.match(r"^([a-f0-9]{24})(?:\b|$)", key)
        selected = [id_map[match.group(1)]] if match and match.group(1) in id_map else (
            alias_map.get(normalized_title(key), []) if key else [])
        if len(selected) != 1:
            problems.append({"file": str(relative), "state": "COVER_CONFLICT",
                             "reason": ("Ambiguous novel title" if selected else
                                        "No exact novel title, ZIP basename or ID match")})
            continue
        item = selected[0]
        if item["id"] in seen:
            problems.append({"file": str(relative), "state": "COVER_CONFLICT",
                             "reason": "Multiple covers for the same novel: " + seen[item["id"]]})
            continue
        seen[item["id"]] = str(relative)
        if path.stat().st_size < 1 or path.stat().st_size > MAX_COVER_BYTES:
            problems.append({"file": str(relative), "state": "COVER_CONFLICT",
                             "reason": "Cover is empty or larger than 12 MiB"})
            continue
        from .inspection import valid_image
        ext = IMAGE_EXTENSIONS[path.suffix.lower()]
        if not valid_image(path.read_bytes(), ext):
            problems.append({"file": str(relative), "state": "COVER_CONFLICT",
                             "reason": "Image could not be fully decoded"})
            continue
        dest = item["directory"] + "/cover" + ext
        old_path = (item["existing"] or {}).get("metadata", {}).get("coverPath")
        if old_path and old_path != dest:
            problems.append({"file": str(relative), "state": "COVER_CONFLICT",
                             "reason": "Different coverPath already linked; review manually"})
            continue
        cover = {"path": path, "sha256": sha256_file(path),
                 "destination": dest, "extension": ext, "novel_id": item["id"]}
        item["cover"] = cover
        candidates.append({"file": str(relative), "state": "COVER_MATCHED",
                           "reason": item["metadata"]["title"]})
    return candidates, problems


def cover_status(item: dict, remote_files: set[str],
                 remote_hashes: dict[str, str]) -> str:
    cover = item.get("cover")
    if not cover:
        return "NONE"
    dest = cover["destination"]
    linked = (item.get("existing") or {}).get("metadata", {}).get("coverPath") == dest
    identical = remote_hashes.get(dest) == cover["sha256"]
    if identical:
        return "UNCHANGED" if linked else "LINK"
    if dest in remote_files or linked:
        return "UPDATE"
    return "NEW"


def commit_batch(api, repo: str, token: str, items: list[dict], *,
                 revision: str, catalogue: dict,
                 remote_files: set[str], remote_hashes: dict[str, str]
                 ) -> tuple[dict, str, dict]:
    """One revision-guarded commit for up to ten approved novel/cover changes.

    No repeated per-book remote catalogue reads, and no optimistic retries
    after an external writer conflict. A failing batch leaves its input
    catalogue unchanged; previously committed batches remain resumable.
    """
    from huggingface_hub import CommitOperationAdd
    if not 1 <= len(items) <= MAX_BATCH_SIZE:
        raise UploadError("Batch must contain 1 to 10 novel entries")
    _pinned_dataset_info(api, repo, token, revision)
    proposed = deepcopy(catalogue)
    validate_catalogue(proposed)
    books = proposed["books"]
    counters = {"new": 0, "updated": 0, "covers": 0}
    staged_ops = []
    with TemporaryDirectory(prefix="taiyou-bulk-batch-") as staging:
        workspace = Path(staging)
        for index, item in enumerate(items):
            if item["state"] not in {"NEW", "UPDATE", "UNCHANGED"}:
                raise UploadError("Blocked or invalid item cannot be applied")
            if sha256_file(item["path"]) != item["digest"]:
                raise UploadError("Local novel ZIP changed after preview")
            cover = item.get("cover")
            if cover:
                if "bytes" in cover:
                    raw = cover["bytes"]
                    if (not isinstance(raw, bytes) or
                            hashlib.sha256(raw).hexdigest() != cover["sha256"]):
                        raise UploadError("Embedded cover changed after preview")
                    from .inspection import valid_image
                    if not valid_image(raw, cover["extension"]):
                        raise UploadError("Embedded cover is no longer valid")
                elif sha256_file(cover["path"]) != cover["sha256"]:
                    raise UploadError("Local cover changed after preview")
            entry, _ = matching_entry(books, item["metadata"], item["epub"])
            chosen_id = (entry["id"] if entry else
                         hashlib.sha256(item["epub"]).hexdigest()[:24])
            if chosen_id != item["id"]:
                raise UploadError("Novel identity changed since preview")
            directory = book_dir(entry) if entry else item["directory"]
            if directory != item["directory"]:
                raise UploadError("Novel directory changed since preview")
            folder_from_epub_path(chosen_id, directory + "/source.epub")
            archive = directory + "/original.zip"
            epub_path = directory + "/source.epub"
            if entry and (entry["epubPath"] != epub_path or
                          entry.get("archivePath") not in {None, archive}):
                raise UploadError("Unexpected existing novel paths")
            if not entry and (archive in remote_files or epub_path in remote_files):
                raise UploadError("Uncatalogued files already exist in destination")
            updated = merged_metadata(
                entry["metadata"] if entry else None, item["metadata"], chosen_id)
            if cover:
                if cover["novel_id"] != chosen_id or cover["destination"] != directory + "/cover" + cover["extension"]:
                    raise UploadError("Cover identity or destination changed")
                existing_path = entry["metadata"].get("coverPath") if entry else None
                if existing_path and existing_path != cover["destination"]:
                    raise UploadError("Cover path changed; manual review required")
                updated["coverPath"] = cover["destination"]
            remote_archive_ok = remote_hashes.get(archive) == item["digest"]
            remote_epub_ok = remote_hashes.get(epub_path) == hashlib.sha256(item["epub"]).hexdigest()
            old_meta = entry["metadata"] if entry else None
            changed = (not entry or old_meta != updated or
                       entry.get("archivePath") != archive or
                       not remote_archive_ok or not remote_epub_ok)
            if changed:
                if not remote_archive_ok:
                    staged_ops.append(CommitOperationAdd(
                        path_in_repo=archive, path_or_fileobj=str(item["path"])))
                if not remote_epub_ok:
                    staged_epub = workspace / f"{index}.epub"
                    staged_epub.write_bytes(item["epub"])
                    staged_ops.append(CommitOperationAdd(
                        path_in_repo=epub_path, path_or_fileobj=str(staged_epub)))
                if entry:
                    entry["metadata"] = updated
                    entry["archivePath"] = archive
                    counters["updated"] += 1
                else:
                    books.append({"id": chosen_id, "metadata": updated,
                                  "epubPath": epub_path, "archivePath": archive})
                    counters["new"] += 1
                from .inspection_manifest import manifest_path, upload_sidecar
                planned_book = {"id": chosen_id, "metadata": updated,
                                "epubPath": epub_path, "archivePath": archive}
                sidecar = workspace / f"{index}.json"
                sidecar.write_bytes(upload_sidecar(planned_book, item["path"], item["epub"]))
                staged_ops.append(CommitOperationAdd(
                    path_in_repo=manifest_path(planned_book),
                    path_or_fileobj=str(sidecar)))
            if cover and remote_hashes.get(cover["destination"]) != cover["sha256"]:
                if "bytes" in cover:
                    staged_cover = workspace / f"{index}{cover['extension']}"
                    staged_cover.write_bytes(cover["bytes"])
                    path_or_fileobj = str(staged_cover)
                else:
                    path_or_fileobj = str(cover["path"])
                staged_ops.append(CommitOperationAdd(
                    path_in_repo=cover["destination"],
                    path_or_fileobj=path_or_fileobj))
                counters["covers"] += 1

        if not staged_ops:
            return catalogue, revision, counters
        catalogue_path = workspace / "library.json"
        catalogue_path.write_text(json.dumps(proposed, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
        staged_ops.append(CommitOperationAdd(
            path_in_repo="data/library.json", path_or_fileobj=str(catalogue_path)))
        try:
            response = api.create_commit(
                repo_id=repo, repo_type="dataset", token=token,
                operations=staged_ops, parent_commit=revision,
                commit_message=f"Upload {len(items)} novel/cover changes")
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (409, 412):
                raise UploadError("Remote dataset changed during batch. Earlier batches remain; re-preview.") from exc
            raise
        new_revision = getattr(response, "oid", None)
        if not isinstance(new_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", new_revision):
            raise UploadError("HF commit completed without a valid revision; check remote before retrying")
        return proposed, new_revision, counters
