"""Revision-bound, small inspection sidecars. Never trust size-only evidence.

Schema v1 records verified results and fingerprints of the *original bytes*.
For remote checks, an LFS SHA-256 or Git blob ID must match. An Xet hash is
not interchangeable with a SHA-256 digest. Absence of strong HF identity
means UNVERIFIED rather than an optimistic claim.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from .core import sha256_file
from .paths import book_dir

MANIFEST_FILENAME = "inspection-manifest.json"
MAX_SIDECAR_BYTES = 512 * 1024
VERSION = 1
ROW_FIELDS = (
    "stored_chapter_count", "chapter_ranges", "missing_chapters",
    "duplicate_positions", "verification_status", "verification_reason",
    "cover_status", "cover_reason", "epub_sha256",
)
COVER_STATES = {"AVAILABLE", "EMBEDDED_ONLY", "BROKEN", "MISSING", "UNVERIFIED"}
CHAPTER_STATES = {"VERIFIED_COMPLETE", "VERIFIED_RANGE", "INCOMPLETE", "UNVERIFIED"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def manifest_path(book: dict) -> str:
    return book_dir(book) + "/" + MANIFEST_FILENAME


def catalogue_signature(book: dict) -> str:
    """Avoid invalidating an archive inspection for changed personal notes."""
    meta = book.get("metadata", {})
    selected = {
        "id": book.get("id"), "epub": book.get("epubPath"),
        "archive": book.get("archivePath"),
        "cover": meta.get("coverPath") or book.get("coverPath"),
        "chapter_count": meta.get("chapterCount"),
        "cover_generated": any(bool(meta.get(k)) for k in (
            "coverGenerated", "generatedCover", "coverIsGenerated")),
        "cover_origin": meta.get("coverSource") or meta.get("coverOrigin"),
    }
    return hashlib.sha256(json.dumps(selected, sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def _git_blob(path: Path) -> str:
    digest = hashlib.sha1()
    digest.update(f"blob {path.stat().st_size}\0".encode("ascii"))
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def local_artifact(path: str, local: Path, remote_identity: dict | None = None) -> dict:
    """Create strong provenance for a known local file at one pinned revision."""
    size = local.stat().st_size
    if size < 1:
        raise ValueError("Empty inspection artifact: " + path)
    result = {
        "path": path, "size": size, "sha256": sha256_file(local),
        "git_blob_sha1": _git_blob(local),
    }
    if remote_identity:
        blob_id = remote_identity.get("blob_id")
        if isinstance(blob_id, str) and GIT_SHA.fullmatch(blob_id):
            result["hf_blob_id"] = blob_id
    return result


def build_manifest(book: dict, row: dict, issues: list[dict],
                   artifacts: dict[str, dict]) -> dict:
    ident = book["id"]
    if not re.fullmatch(r"[a-f0-9]{24}", ident):
        raise ValueError("Invalid novel ID")
    for key, descriptor in artifacts.items():
        if key not in {"epub", "archive", "cover"}:
            raise ValueError("Unexpected artifact type")
        if not isinstance(descriptor, dict) or not SHA256.fullmatch(
                str(descriptor.get("sha256", ""))):
            raise ValueError("Artifact lacks verified SHA-256")
    values = {key: row.get(key) for key in ROW_FIELDS}
    if values["verification_status"] not in CHAPTER_STATES:
        raise ValueError("Invalid chapter status")
    if values["cover_status"] not in COVER_STATES:
        raise ValueError("Invalid cover status")
    return {
        "schema_version": VERSION, "novel_id": ident,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "catalogue_signature": catalogue_signature(book),
        "artifacts": artifacts,
        "inspection": values,
        "issues": [dict(issue) for issue in issues if issue.get("novel_id") == ident],
    }


def manifest_bytes(value: dict) -> bytes:
    body = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(body) > MAX_SIDECAR_BYTES:
        raise ValueError("Inspection manifest exceeds size limit")
    return body


def match_artifact(evidence: dict, remote: dict) -> bool:
    """Match HF-backed cryptographic identity; file size alone never suffices."""
    if not isinstance(evidence, dict) or not isinstance(remote, dict):
        return False
    if (not isinstance(evidence.get("size"), int) or
            evidence["size"] != remote.get("size")):
        return False
    digest = remote.get("sha256")
    if digest and SHA256.fullmatch(str(digest)) and digest == evidence.get("sha256"):
        return True
    blob_id = remote.get("blob_id")
    if blob_id and GIT_SHA.fullmatch(str(blob_id)):
        return blob_id in {evidence.get("hf_blob_id"), evidence.get("git_blob_sha1")}
    return False


def read_manifest(book: dict, raw: bytes, remote_files: dict[str, int | None],
                  identities: dict[str, dict]) -> tuple[dict, list[dict]]:
    """Validate sidecar at the CURRENT revision, then return vetted evidence."""
    if len(raw) > MAX_SIDECAR_BYTES:
        raise ValueError("Sidecar too large")
    value = json.loads(raw.decode("utf-8-sig"))
    if (not isinstance(value, dict) or value.get("schema_version") != VERSION or
            value.get("novel_id") != book["id"] or
            value.get("catalogue_signature") != catalogue_signature(book)):
        raise ValueError("Manifest version, book ID or catalogue signature changed")
    results = value.get("inspection")
    if not isinstance(results, dict) or results.get("verification_status") not in CHAPTER_STATES:
        raise ValueError("Invalid chapter inspection evidence")
    if results.get("cover_status") not in COVER_STATES:
        raise ValueError("Invalid cover inspection evidence")
    evidence = value.get("artifacts")
    if not isinstance(evidence, dict):
        raise ValueError("Missing artifact evidence")
    expected = {"epub": book.get("epubPath"), "archive": book.get("archivePath")}
    meta = book.get("metadata", {})
    cover = meta.get("coverPath") or book.get("coverPath")
    if cover:
        expected["cover"] = cover
    for name, entry in evidence.items():
        if name not in expected or not isinstance(entry, dict) or entry.get("path") != expected[name]:
            raise ValueError("Manifest references a different novel artifact")
        path = entry["path"]
        if path not in remote_files:
            raise ValueError("Manifest references deleted artifact")
        identity = dict(identities.get(path, {}))
        identity.setdefault("size", remote_files[path])
        if not match_artifact(entry, identity):
            raise ValueError("Artifact identity changed or HF hash unavailable: " + name)
    if results["verification_status"] != "UNVERIFIED" and not {"archive", "epub"} <= evidence.keys():
        raise ValueError("Chapter evidence is missing required original files")
    if results["cover_status"] == "AVAILABLE" and "cover" not in evidence:
        raise ValueError("Cover validation lacks cryptographic provenance")
    if results["cover_status"] == "EMBEDDED_ONLY" and "epub" not in evidence:
        raise ValueError("Embedded cover validation lacks EPUB evidence")
    findings = value.get("issues", [])
    if not isinstance(findings, list) or any(
            not isinstance(item, dict) or item.get("novel_id") != book["id"] for item in findings):
        raise ValueError("Invalid saved issues")
    return {key: results.get(key) for key in ROW_FIELDS}, findings
