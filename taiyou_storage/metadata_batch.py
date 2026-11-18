"""Review and batch-repair VERIFIED source metadata without downloading chapters.

Local workflow: discover -> review -> preview -> apply.
Each source receives at most one bounded public book-page GET, without retries.
Every proposed field has explicit source-page identity evidence. Unknown fields
are deferred for manual review. No private dataset changes until APPLY.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import time

from .core import DEFAULT_REPO, validate_catalogue, write_csv
from .metadata_repair import (
    FIELDS, MetadataRepairError, _load_private_catalogue,
    _report_path, _save_private_json, _source_key, missing_fields, plan_repair,
)
from .metadata_source import SourceUnavailable, checked_book_url, public_book_html, verified_metadata

CANDIDATES = Path("reports/metadata-batch-candidates.json")
REVIEW_CSV = Path("reports/metadata-batch-review.csv")
APPROVALS = Path("reports/metadata-batch-approvals.json")
PREVIEW = Path("reports/metadata-batch-preview.json")
MAX_NOVELS = 250
MAX_INPUT = 5 * 1024 * 1024
CSV_FIELDS = (
    "id", "title", "source_url", "missing_fields",
    "verified_fields", "unresolved_fields", "state", "reason",
)


def _json_bytes(path: Path) -> bytes:
    file = _report_path(path)
    if not file.is_file() or file.stat().st_size > MAX_INPUT:
        raise MetadataRepairError("Required private batch JSON file is missing or oversized")
    return file.read_bytes()


def _read_json(path: Path) -> tuple[dict, bytes]:
    payload = _json_bytes(path)
    try:
        obj = json.loads(payload.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise MetadataRepairError("Invalid private batch JSON file") from exc
    if not isinstance(obj, dict):
        raise MetadataRepairError("Expected a JSON object")
    return obj, payload


def _targets(catalogue: dict, audit: Path | None) -> list[dict]:
    """Optional uploaded CSV acts only as a selector, never an authority."""
    books = validate_catalogue(catalogue)
    missing = {b["id"]: b for b in books if missing_fields(b["metadata"])}
    if audit is None:
        selected = list(missing.values())
    else:
        source = _report_path(audit)
        if not source.is_file() or source.stat().st_size > MAX_INPUT:
            raise MetadataRepairError("Missing or oversized private audit CSV")
        selected = []
        seen = set()
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not {"id", "source_url", "missing_fields"}.issubset(reader.fieldnames):
                raise MetadataRepairError("Unsupported metadata-audit CSV headers")
            for line in reader:
                ident = line.get("id", "")
                if ident in seen or ident not in missing:
                    raise MetadataRepairError("Duplicate, stale or unknown book ID in audit CSV")
                seen.add(ident)
                book = missing[ident]
                if _source_key(line["source_url"]) != _source_key(book["metadata"].get("sourceUrl")):
                    raise MetadataRepairError("Audit CSV source URL does not match current catalogue")
                if set(line["missing_fields"].split(",")) != set(missing_fields(book["metadata"])):
                    raise MetadataRepairError("Audit CSV missing-field list is stale")
                selected.append(book)
        if not selected:
            raise MetadataRepairError("Audit CSV selected no novels")
    if len(selected) > MAX_NOVELS:
        raise MetadataRepairError("Too many novels in one discovery; split the audit")
    return selected


def discover_candidates(catalogue: dict, repo: str, revision: str, *,
                        audit: Path | None = None, fetcher=public_book_html,
                        sleeper=time.sleep) -> tuple[dict, list[dict]]:
    """Read-only discovery, one book page per selected novel.

    Unexpected access challenges, missing authors or unsuitable HTML return
    a review-needed row, never a verified repair field.
    """
    entries = _targets(catalogue, audit)
    proposals, rows = [], []
    for position, book in enumerate(entries):
        if position:
            sleeper(1)
        meta = book["metadata"]
        missing = missing_fields(meta)
        url = meta.get("sourceUrl", "")
        values, reason, state = {}, "", "REVIEW_REQUIRED"
        try:
            checked_book_url(url)
            source = verified_metadata(
                fetcher(url), url,
                str(meta.get("title") or ""), str(meta.get("author") or ""),
            )
            values = {field: source[field] for field in missing if source.get(field)}
            if values:
                state = "SOURCE_VERIFIED"
            else:
                reason = "No safely verified fields recognised"
        except SourceUnavailable as exc:
            # No source text is considered authoritative after any source or
            # identity failure. Report only a short safe, per-book reason.
            reason = str(exc)[:200]
        remaining = [field for field in missing if field not in values]
        if state == "SOURCE_VERIFIED" and remaining:
            reason = "Source page did not verify all missing fields"
        proposals.append({
            "id": book["id"],
            "sourceUrl": url,
            "title": str(meta.get("title") or ""),
            "author": str(meta.get("author") or ""),
            "missing": missing, "proposed": values,
            "state": state, "unresolved": remaining,
            "reason": reason,
        })
        rows.append({
            "id": book["id"], "title": str(meta.get("title") or ""),
            "source_url": url, "missing_fields": ",".join(missing),
            "verified_fields": ",".join(values), "unresolved_fields": ",".join(remaining),
            "state": state, "reason": reason,
        })
    document = {
        "version": 1, "dataset": repo, "revision": revision,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_policy": "one public book page; strict URL/title/author; no chapter requests",
        "items": proposals,
    }
    return document, rows


def _validate_candidates(data: dict, repo: str, revision: str) -> list[dict]:
    if (data.get("version") != 1 or data.get("dataset") != repo
            or data.get("revision") != revision or not isinstance(data.get("items"), list)):
        raise MetadataRepairError("Batch candidates belong to a different catalogue revision")
    if len(data["items"]) > MAX_NOVELS:
        raise MetadataRepairError("Too many batch candidates")
    seen = set()
    for item in data["items"]:
        if not isinstance(item, dict) or not {"id", "sourceUrl", "missing", "proposed", "state", "unresolved"}.issubset(item):
            raise MetadataRepairError("Invalid batch candidate")
        if item["id"] in seen:
            raise MetadataRepairError("Duplicate book in batch candidates")
        seen.add(item["id"])
        if not isinstance(item["proposed"], dict) or set(item["proposed"]) - set(FIELDS):
            raise MetadataRepairError("Unsupported candidate source metadata fields")
        if not isinstance(item["missing"], list) or not isinstance(item["unresolved"], list):
            raise MetadataRepairError("Invalid candidate field lists")
        if item["state"] not in ("SOURCE_VERIFIED", "REVIEW_REQUIRED"):
            raise MetadataRepairError("Invalid candidate verification state")
        if item["state"] != "SOURCE_VERIFIED" and item["proposed"]:
            raise MetadataRepairError("Unverified candidates cannot contain repairs")
        if set(item["proposed"]) - set(item["missing"]):
            raise MetadataRepairError("Proposal would change an already-present field")
        if set(item["missing"]) != set(item["proposed"]) | set(item["unresolved"]):
            raise MetadataRepairError("Candidate field coverage is inconsistent")
    return data["items"]


def plan_batch(catalogue: dict, candidates: dict, approvals: dict,
               repo: str, revision: str, candidates_hash: str) -> tuple[dict, list[dict]]:
    """Validate all approvals first; abort on any mismatch, never partially write."""
    validate_catalogue(catalogue)
    items = _validate_candidates(candidates, repo, revision)
    if (approvals.get("version") != 1 or approvals.get("revision") != revision
            or approvals.get("dataset") != repo
            or approvals.get("candidates_sha256") != candidates_hash):
        raise MetadataRepairError("Approvals do not match the candidates and current dataset")
    approved = approvals.get("approved_ids")
    if not isinstance(approved, list) or len(set(approved)) != len(approved):
        raise MetadataRepairError("Invalid or duplicate approval IDs")
    indexed = {item["id"]: item for item in items}
    result = json.loads(json.dumps(catalogue, ensure_ascii=False))
    changes = []
    for ident in approved:
        item = indexed.get(ident)
        if item is None or item["state"] != "SOURCE_VERIFIED" or not item["proposed"]:
            raise MetadataRepairError("An approved novel lacks verified source fields")
        live = [b for b in catalogue["books"] if b["id"] == ident]
        if len(live) != 1 or set(missing_fields(live[0]["metadata"])) != set(item["missing"]):
            raise MetadataRepairError("Candidate missing fields no longer match the catalogue")
        patch = {"id": ident, "sourceUrl": item["sourceUrl"], **item["proposed"]}
        result, filled, _ = plan_repair(result, patch)
        if not filled:
            raise MetadataRepairError("Approved novel makes no actual changes")
        changes.append({"id": ident, "fields": filled})
    return result, changes


def _candidate_payload(repo: str, revision: str) -> tuple[dict, bytes, list[dict]]:
    obj, payload = _read_json(CANDIDATES)
    return obj, payload, _validate_candidates(obj, repo, revision)


def _approval_payload(repo: str, revision: str, candidates_digest: str) -> tuple[dict, bytes]:
    obj, raw = _read_json(APPROVALS)
    if (obj.get("candidates_sha256") != candidates_digest
            or obj.get("revision") != revision or obj.get("dataset") != repo):
        raise MetadataRepairError("Approval file is stale or refers to another batch")
    return obj, raw


def review_candidates(repo: str, revision: str, approve_all: bool = False) -> int:
    data, payload, items = _candidate_payload(repo, revision)
    verified = [item for item in items if item["state"] == "SOURCE_VERIFIED" and item["proposed"]]
    if not verified:
        print("No safely verified source suggestions. All novels require manual review.")
        return 0
    print("Verified source suggestions:", len(verified))
    print("Review all details in reports/metadata-batch-candidates.json before approving.")
    print("No remote changes occur during this review.")
    ids = []
    if approve_all:
        phrase = f"APPROVE {len(verified)} VERIFIED"
        if input(f"Type {phrase} to approve ALL verified suggestions: ").strip() == phrase:
            ids = [item["id"] for item in verified]
    else:
        for item in verified:
            print("\nNovel:", item["title"])
            print("Source:", item["sourceUrl"])
            print("Proposed:", json.dumps(item["proposed"], ensure_ascii=False, indent=2))
            if item["unresolved"]:
                print("Still unresolved:", ", ".join(item["unresolved"]))
            if input("Type YES to approve this novel, otherwise skip: ").strip() == "YES":
                ids.append(item["id"])
    if not ids:
        print("No approvals recorded. No remote changes.")
        return 0
    _save_private_json(APPROVALS, {
        "version": 1, "dataset": repo, "revision": revision,
        "candidates_sha256": sha256(payload).hexdigest(),
        "approved_ids": ids,
    })
    print("Local approvals recorded:", len(ids))
    print("Next: preview, then apply. No HF data changed.")
    return 0


def _prepare_plan(catalogue: dict, repo: str, revision: str):
    candidates, data, _ = _candidate_payload(repo, revision)
    approvals, approval_bytes = _approval_payload(repo, revision, sha256(data).hexdigest())
    updated, changes = plan_batch(catalogue, candidates, approvals, repo,
                                  revision, sha256(data).hexdigest())
    return updated, changes, sha256(data).hexdigest(), sha256(approval_bytes).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("discover", "review", "preview", "apply"))
    parser.add_argument("--repo", default=os.environ.get("HF_DATASET_REPO", DEFAULT_REPO))
    parser.add_argument("--targets", type=Path, default=None,
                        help="Optional reports/missing-source-metadata.csv to select subset")
    parser.add_argument("--approve-all", action="store_true", help="Review: approve source-verified candidates after typed confirmation")
    args = parser.parse_args(argv)
    if os.environ.get("GITHUB_ACTIONS", "").casefold() == "true":
        raise MetadataRepairError("Private batch metadata workflow runs locally, not in GitHub Actions")
    if args.approve_all and args.action != "review":
        raise MetadataRepairError("--approve-all is only valid for review")
    if args.targets and args.action != "discover":
        raise MetadataRepairError("--targets is only valid for discover")
    token = os.environ.get("HF_TOKEN") or None
    api, revision, original, catalogue = _load_private_catalogue(args.repo, token)
    if args.action == "discover":
        # Avoid silently replacing a previously approved/previewed review.
        if any(_report_path(x).exists() for x in (CANDIDATES, APPROVALS, PREVIEW)):
            raise MetadataRepairError(
                "Existing batch review files found. Back them up and remove candidates, "
                "approvals and preview before starting a new discovery."
            )
        doc, rows = discover_candidates(catalogue, args.repo, revision, audit=args.targets)
        _save_private_json(CANDIDATES, doc)
        write_csv(_report_path(REVIEW_CSV), rows, list(CSV_FIELDS))
        ready = sum(x["state"] == "SOURCE_VERIFIED" for x in doc["items"])
        unresolved = sum(bool(x["unresolved"]) for x in doc["items"])
        print(json.dumps({
            "novels_checked": len(rows), "novels_with_verified_fields": ready,
            "novels_needing_review": unresolved, "mode": "READ ONLY",
        }, sort_keys=True))
        print("Local review CSV:", REVIEW_CSV)
        print("Local proposed source fields:", CANDIDATES)
        return 0
    if args.action == "review":
        return review_candidates(args.repo, revision, approve_all=args.approve_all)
    updated, changes, candidates_hash, approvals_hash = _prepare_plan(
        catalogue, args.repo, revision
    )
    if args.action == "preview":
        _save_private_json(PREVIEW, {
            "version": 1, "dataset": args.repo, "revision": revision,
            "candidates_sha256": candidates_hash,
            "approvals_sha256": approvals_hash,
            "changes": changes,
        })
        print("PREVIEW ONLY. Approved novels:", len(changes))
        print("Fields to add:", sum(len(item["fields"]) for item in changes))
        print("No HF data changed. Review local preview JSON before Apply.")
        return 0
    prior, _ = _read_json(PREVIEW)
    if (prior.get("version") != 1 or prior.get("dataset") != args.repo
            or prior.get("revision") != revision
            or prior.get("candidates_sha256") != candidates_hash
            or prior.get("approvals_sha256") != approvals_hash
            or prior.get("changes") != changes):
        raise MetadataRepairError("Preview no longer matches source, approvals or dataset revision")
    if not changes:
        print("No metadata changes approved. No HF commit created.")
        return 0
    expected = f"APPLY {len(changes)}"
    if input(f"Type {expected} to update ONLY the private catalogue: ").strip() != expected:
        print("Cancelled. No Hugging Face data changed.")
        return 1
    if api.dataset_info(args.repo, token=token).sha != revision:
        raise MetadataRepairError("Dataset revision changed; repeat discovery and review")
    from huggingface_hub import CommitOperationAdd
    backup = ("backups/metadata-repair/" +
              datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") +
              "-" + revision[:12] + ".json")
    data = json.dumps(updated, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    api.create_commit(
        repo_id=args.repo, repo_type="dataset", token=token, parent_commit=revision,
        operations=[
            CommitOperationAdd(path_in_repo=backup, path_or_fileobj=BytesIO(original)),
            CommitOperationAdd(path_in_repo="data/library.json", path_or_fileobj=BytesIO(data)),
        ],
        commit_message="Backfill reviewed source metadata for multiple existing novels",
    )
    PREVIEW.unlink(missing_ok=True)
    print("PRIVATE catalogue-only commit complete. Novels updated:", len(changes))
    print("Pre-change catalogue backed up in the same HF revision.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Private novel titles, catalogue contents and tokens must not leak to CI.
        print("Batch metadata repair stopped: " +
              (str(exc) if isinstance(exc, MetadataRepairError) else type(exc).__name__),
              file=sys.stderr)
        raise SystemExit(1)
