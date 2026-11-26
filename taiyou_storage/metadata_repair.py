"""Audit and safely repair missing source metadata in a PRIVATE Hugging Face catalogue.

Read-only by default. Only allow-listed source metadata fields can be added to
one uniquely identified book. Never upload EPUBs, covers, ZIPs, or personal data.
Changes require a fresh, matching preview, an interactive confirmation and a
revision-guarded single HF commit with an exact private catalogue backup.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from .core import DEFAULT_REPO, validate_catalogue, write_csv
from .console_summary import print_summary

REPORT_ROOT = Path("reports")
DEFAULT_INPUT = REPORT_ROOT / "metadata-repair.json"
DEFAULT_PREVIEW = REPORT_ROOT / "metadata-repair-preview.json"
DEFAULT_AUDIT = REPORT_ROOT / "missing-source-metadata.csv"
FIELDS = ("description", "sourceTags", "status")
MAX_PATCH_BYTES = 50_000
MAX_SYNOPSIS = 24_000

# Source publication state, never personal reading progress. Aliases are
# accepted only for explicitly reviewed source evidence, not inferred.
SOURCE_STATUS_ALIASES = {
    "completed": "Completed", "complete": "Completed",
    "ongoing": "Ongoing", "on going": "Ongoing",
    "in progress": "Ongoing", "in-progress": "Ongoing",
    "hiatus": "Hiatus", "on hiatus": "Hiatus",
    "on hold": "Hiatus", "on-hold": "Hiatus",
    "dropped": "Dropped", "discontinued": "Dropped",
    "cancelled": "Dropped", "canceled": "Dropped",
}


def normalise_source_status(value: object) -> str:
    """Canonicalise only explicitly supplied publication status evidence."""
    if not isinstance(value, str) or not value.strip():
        raise MetadataRepairError("Invalid source publication status")
    key = " ".join(value.casefold().split())
    result = SOURCE_STATUS_ALIASES.get(key)
    if result is None:
        raise MetadataRepairError("Unknown source publication status")
    return result



class MetadataRepairError(ValueError):
    """A proposed metadata-only change failed validation."""


def missing_fields(metadata: dict) -> list[str]:
    """Missing source fields, not missing personal tags or custom summaries."""
    return [field for field in FIELDS
            if not (isinstance(metadata.get(field), str) and metadata[field].strip()
                    if field != "sourceTags" else
                    isinstance(metadata.get(field), list) and bool(metadata[field]))]


def audit_catalogue(catalogue: dict) -> tuple[list[dict], dict]:
    """Pure, read-only audit. Missing fields do not prove the source offers them."""
    books = validate_catalogue(catalogue)
    report = []
    counts = Counter()
    for entry in books:
        meta = entry["metadata"]
        missing = missing_fields(meta)
        for field in missing:
            counts["missing_" + field] += 1
        if missing:
            report.append({
                "id": entry["id"], "title": str(meta.get("title") or ""),
                "author": str(meta.get("author") or ""),
                "source_url": str(meta.get("sourceUrl") or ""),
                "missing_fields": ",".join(missing),
            })
    stats = {"total_novels": len(books), "novels_missing_any": len(report)}
    stats.update({"missing_" + field: counts["missing_" + field] for field in FIELDS})
    return report, stats


def _report_path(path: Path) -> Path:
    """Keep private descriptions, titles and catalogue data under gitignored reports/."""
    root = REPORT_ROOT.resolve()
    target = Path(path).resolve()
    if not target.is_relative_to(root) or target == root:
        raise MetadataRepairError("Private metadata input/output must remain inside reports/")
    return target


def _source_key(url: str) -> str:
    """Only use genuine HTTPS book URLs for an exact source-identity match."""
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise MetadataRepairError("A valid sourceUrl is required")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise MetadataRepairError("Invalid sourceUrl") from exc
    host = (parsed.hostname or "").casefold()
    if (parsed.scheme != "https" or not host or port not in (None, 443)
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not parsed.path.startswith("/") or parsed.path == "/"):
        raise MetadataRepairError("Expected a plain public HTTPS book sourceUrl")
    return host.removeprefix("www.") + parsed.path.rstrip("/").casefold()


def validate_patch(document: object) -> dict:
    """Never accept arbitrary catalogue keys, paths, IDs or personal metadata."""
    if not isinstance(document, dict):
        raise MetadataRepairError("Repair JSON must be one object")
    allowed = {"id", "sourceUrl", *FIELDS}
    if set(document) - allowed:
        raise MetadataRepairError("Repair JSON contains unsupported fields")
    ident = document.get("id")
    if not isinstance(ident, str) or not re.fullmatch(r"[0-9a-f]{24}", ident):
        raise MetadataRepairError("A 24-character book id is required")
    _source_key(document.get("sourceUrl"))
    if not any(field in document for field in FIELDS):
        raise MetadataRepairError("No repair fields supplied")
    result = {"id": ident, "sourceUrl": document["sourceUrl"]}
    if "description" in document:
        value = document["description"]
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_SYNOPSIS:
            raise MetadataRepairError("description must be 1-24000 characters of text")
        result["description"] = value.strip()
    if "sourceTags" in document:
        genres = document["sourceTags"]
        if not isinstance(genres, list) or not (1 <= len(genres) <= 50):
            raise MetadataRepairError("sourceTags must be a nonempty list of up to 50 genres")
        result_tags = []
        seen = set()
        for tag in genres:
            if not isinstance(tag, str) or not (1 <= len(tag.strip()) <= 100):
                raise MetadataRepairError("Invalid source genre")
            value = " ".join(tag.split())
            if any(c in value for c in ("\n", "\r", "\x00")):
                raise MetadataRepairError("Invalid source genre characters")
            if value.casefold() not in seen:
                seen.add(value.casefold())
                result_tags.append(value)
        if not result_tags:
            raise MetadataRepairError("No source genres supplied")
        result["sourceTags"] = result_tags
    if "status" in document:
        result["status"] = normalise_source_status(document["status"])
    return result


def plan_repair(catalogue: dict, raw_patch: object) -> tuple[dict, list[str], dict]:
    """Never overwrite a populated field, even if a patch requests it.

    The ID and canonical source URL must both match exactly one catalogue row.
    All other fields and nested personal records stay byte-for-byte equivalent
    after JSON deserialisation.
    """
    validate_catalogue(catalogue)
    patch = validate_patch(raw_patch)
    books = [row for row in catalogue["books"] if row["id"] == patch["id"]]
    if len(books) != 1:
        raise MetadataRepairError("Book id does not match exactly one existing novel")
    original_meta = books[0]["metadata"]
    expected_source = _source_key(patch["sourceUrl"])
    if _source_key(original_meta.get("sourceUrl")) != expected_source:
        raise MetadataRepairError("Novel id and sourceUrl do not refer to the same book")
    if sum(_source_key(b["metadata"].get("sourceUrl")) == expected_source
           for b in catalogue["books"] if b["metadata"].get("sourceUrl")) != 1:
        raise MetadataRepairError("Duplicate source URLs; refusing ambiguous metadata repair")
    clone = json.loads(json.dumps(catalogue, ensure_ascii=False))
    candidate = next(b for b in clone["books"] if b["id"] == patch["id"])
    meta = candidate["metadata"]
    changed = []
    for field in FIELDS:
        if field not in patch:
            continue
        old = meta.get(field)
        new = patch[field]
        if old == new:
            continue
        if old not in (None, "", []):
            raise MetadataRepairError(f"{field} already has a value; manual review is required")
        meta[field] = new
        changed.append(field)
    return clone, changed, {"id": patch["id"], "title": original_meta.get("title") or ""}


def _load_patch(path: Path) -> tuple[dict, bytes]:
    location = _report_path(path)
    if not location.is_file() or location.stat().st_size > MAX_PATCH_BYTES:
        raise MetadataRepairError("Repair JSON is missing or too large")
    data = location.read_bytes()
    try:
        return validate_patch(json.loads(data.decode("utf-8-sig"))), data
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MetadataRepairError("Repair file is not valid UTF-8 JSON") from exc


def _load_private_catalogue(repo: str, token: str | None):
    from huggingface_hub import HfApi, hf_hub_download
    api = HfApi()
    info = api.dataset_info(repo, token=token)
    if info.private is not True or not info.sha:
        raise MetadataRepairError("A revisioned PRIVATE Hugging Face dataset is required")
    location = hf_hub_download(
        repo_id=repo, repo_type="dataset", filename="data/library.json",
        revision=info.sha, token=token,
    )
    original = Path(location).read_bytes()
    try:
        catalogue = json.loads(original.decode("utf-8-sig"))
        validate_catalogue(catalogue)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise MetadataRepairError("The remote private catalogue is invalid") from exc
    return api, info.sha, original, catalogue


def _save_private_json(path: Path, obj: dict) -> None:
    location = _report_path(path)
    location.parent.mkdir(parents=True, exist_ok=True)
    staged = location.with_suffix(location.suffix + ".tmp")
    try:
        staged.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staged.replace(location)
    finally:
        staged.unlink(missing_ok=True)


def _local_prepare(catalogue: dict) -> dict:
    query = input("Exact novel title or 24-character novel ID: ").strip()
    matching = [b for b in catalogue["books"]
                if b["id"] == query or str(b["metadata"].get("title") or "").casefold() == query.casefold()]
    if len(matching) != 1:
        raise MetadataRepairError("No unique matching novel. Use its exact ID instead.")
    book = matching[0]
    meta = book["metadata"]
    url = meta.get("sourceUrl")
    _source_key(url)
    print("Preparing missing source metadata for:", meta.get("title", ""))
    print("Leave any field blank to leave it unchanged.")
    description = input("Verified source synopsis (paste on one line): ").strip()
    genres = input("Verified source genres, comma-separated: ").strip()
    status = input("Publication status, Completed / Ongoing / Hiatus / Dropped / blank: ").strip()
    doc = {"id": book["id"], "sourceUrl": url}
    if description:
        doc["description"] = description
    if genres:
        doc["sourceTags"] = [x.strip() for x in genres.split(",") if x.strip()]
    if status:
        doc["status"] = status
    return validate_patch(doc)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "prepare", "preview", "apply"))
    parser.add_argument("--repo", default=os.environ.get("HF_DATASET_REPO", DEFAULT_REPO))
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args(argv)
    if os.environ.get("GITHUB_ACTIONS", "").casefold() == "true" and args.action != "audit":
        raise MetadataRepairError("Individual metadata edits must run locally, not in public GitHub Actions")
    token = os.environ.get("HF_TOKEN") or None  # HF CLI login also works.
    api, revision, original, catalogue = _load_private_catalogue(args.repo, token)
    if args.action == "audit":
        rows, counts = audit_catalogue(catalogue)
        target = _report_path(DEFAULT_AUDIT)
        write_csv(target, rows,
                  ["id", "title", "author", "source_url", "missing_fields"])
        # Only numeric counts reach stdout. The CSV is local, Git-ignored.
        reports = ([target] if os.environ.get("GITHUB_ACTIONS", "").casefold() != "true"
                   else [])
        print_summary("Source metadata audit", counts, reports=reports,
                      note="Read-only. Source metadata is not modified.",
                      status="COMPLETED")
        return 0
    if args.action == "prepare":
        patch = _local_prepare(catalogue)
        target = _report_path(args.input)
        if target.exists():
            raise MetadataRepairError("A repair draft already exists. Move/delete it after backup before preparing another.")
        plan_repair(catalogue, patch)
        _save_private_json(target, patch)
        print_summary("Source metadata draft prepared",
                      {"Draft created": "Yes"}, reports=[target],
                      note="Preview is required before any apply. Cloud unchanged.")
        return 0
    patch, payload = _load_patch(args.input)
    updated, changed, book = plan_repair(catalogue, patch)
    preview_file = _report_path(DEFAULT_PREVIEW)
    fingerprint = sha256(payload).hexdigest()
    if args.action == "preview":
        _save_private_json(preview_file, {
            "dataset": args.repo, "revision": revision,
            "patch_sha256": fingerprint, "id": patch["id"],
            "fields_to_add": changed,
        })
        print_summary("Source metadata repair preview", {
            "Novel": book["title"],
            "Fields to add": ", ".join(changed) if changed else "(none)",
        }, reports=[preview_file], note="Read-only; archives, covers and personal data unchanged.",
            status="PREVIEW")
        return 0
    if not preview_file.exists():
        raise MetadataRepairError("Run Preview first. A matching preview is mandatory.")
    try:
        prior = json.loads(preview_file.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MetadataRepairError("Invalid prior preview") from exc
    if (prior.get("dataset") != args.repo or prior.get("revision") != revision
            or prior.get("patch_sha256") != fingerprint or prior.get("id") != patch["id"]
            or prior.get("fields_to_add") != changed):
        raise MetadataRepairError("Catalogue, file or preview changed. Run Preview again.")
    if not changed:
        print("No fields need changing. No HF commit created.")
        return 0
    print("UPDATE PRIVATE CATALOGUE for:", book["title"])
    print("Add fields:", ", ".join(changed))
    if input("Type APPLY to commit this catalogue-only repair: ").strip() != "APPLY":
        print("Cancelled; no HF data changed.")
        return 1
    if api.dataset_info(args.repo, token=token).sha != revision:
        raise MetadataRepairError("Dataset revision changed. Run Preview again.")
    from huggingface_hub import CommitOperationAdd
    backup = ("backups/metadata-repair/" +
              datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") +
              "-" + revision[:12] + ".json")
    new_bytes = json.dumps(updated, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    api.create_commit(
        repo_id=args.repo, repo_type="dataset", token=token,
        parent_commit=revision,
        operations=[
            CommitOperationAdd(path_in_repo=backup, path_or_fileobj=BytesIO(original)),
            CommitOperationAdd(path_in_repo="data/library.json", path_or_fileobj=BytesIO(new_bytes)),
        ],
        commit_message="Add verified source metadata to one private novel",
    )
    preview_file.unlink(missing_ok=True)
    print_summary("Source metadata repair completed", {
        "Novels updated": 1,
        "Fields added": len(changed),
        "Private catalogue backup": "Created",
    }, note="EPUBs, ZIPs, covers and personal metadata unchanged.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Do not put private book content, remote filenames or credentials in logs.
        if isinstance(exc, MetadataRepairError):
            print("Metadata repair stopped: " + str(exc), file=sys.stderr)
        else:
            print("Metadata repair stopped: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
