"""Batched, revision-guarded uploads of cover images.

All covers in a batch and their catalogue updates share ONE HF commit.
Reruns are idempotent: the catalogue and remote cover digests are rechecked.
429s with long/unknown reset times stop cleanly without repeated commit calls.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import time

from .core import validate_catalogue
from .covers import CoverError, EXTENSIONS, make_plan, match_book
from .paths import book_dir, COVER_SUFFIXES

DEFAULT_BATCH_SIZE = 20
MAX_BATCH_SIZE = 40
DEFAULT_BATCH_BYTES = 48 * 1024 * 1024
MAX_SHORT_RETRY = 30


def group_batches(items: list[dict], batch_size: int = DEFAULT_BATCH_SIZE,
                  max_bytes: int = DEFAULT_BATCH_BYTES) -> list[list[dict]]:
    """Keep commits comfortably below Hugging Face's recommended 50-100 files."""
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise CoverError(f"Batch size must be between 1 and {MAX_BATCH_SIZE}")
    if max_bytes <= 0:
        raise CoverError("Batch byte limit must be positive")
    result, current, size = [], [], 0
    for item in items:
        cover = item["cover"]
        weight = len(cover.data)
        if current and (len(current) >= batch_size or size + weight > max_bytes):
            result.append(current)
            current, size = [], 0
        current.append(item)
        size += weight
    if current:
        result.append(current)
    return result


def _short_retry_after(exc: Exception) -> float | None:
    """Use Retry-After only; generic API rate-limit headers are a DIFFERENT quota."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    value = headers.get("Retry-After") or headers.get("retry-after")
    try:
        delay = float(value)
    except (TypeError, ValueError):
        return None
    if not 0 < delay <= MAX_SHORT_RETRY:
        return None
    return delay


def _checked_catalogue(api, repo: str, token: str, expected_sha: str):
    from huggingface_hub import hf_hub_download

    info = api.dataset_info(repo, token=token)
    if info.private is not True or not info.sha:
        raise CoverError("Refusing to write to an unverified or public HF dataset")
    if info.sha != expected_sha:
        raise CoverError(
            "The HF dataset changed since preview/previous batch. "
            "Stop and rerun the same ZIP to recheck matches.")
    paths = set(api.list_repo_files(
        repo_id=repo, repo_type="dataset", revision=expected_sha, token=token))
    if "data/library.json" not in paths:
        raise CoverError("Remote catalogue is missing; no covers were written")
    downloaded = hf_hub_download(
        repo_id=repo, repo_type="dataset", filename="data/library.json",
        revision=expected_sha, token=token)
    catalogue = json.loads(Path(downloaded).read_text(encoding="utf-8"))
    books = validate_catalogue(catalogue)
    return catalogue, books, paths


def commit_cover_batch(api, repo: str, token: str, items: list[dict],
                       expected_sha: str, *, sleeper=time.sleep) -> tuple[str, list[str]]:
    """One atomic commit per batch, with catalogue metadata and cover files together.

    Returns (new revision, per-cover results). Does not retry non-429 errors:
    caller reruns preview if the outcome of a failed commit is ambiguous.
    """
    from huggingface_hub import CommitOperationAdd, hf_hub_download

    if not items:
        return expected_sha, []
    for attempt in range(2):
        catalogue, books, paths = _checked_catalogue(
            api, repo, token, expected_sha)
        covers = [item["cover"] for item in items]
        preliminary = make_plan(covers, books, {}, paths)
        if any(x["status"] in ("MISSING", "CONFLICT") for x in preliminary):
            raise CoverError(
                "A book is now missing or ambiguous in the catalogue; "
                "stop and rerun the preview")
        # Download only existing destination images, so SHA-256 comparison
        # can detect already-completed uploads and harmless reruns.
        hashes = {}
        for destination in sorted({
            x["destination"] for x in preliminary if x["destination"] in paths
        }):
            cached = Path(hf_hub_download(
                repo_id=repo, repo_type="dataset", filename=destination,
                revision=expected_sha, token=token))
            digest = hashlib.sha256()
            with cached.open("rb") as stream:
                for piece in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(piece)
            hashes[destination] = digest.hexdigest()
        current = make_plan(covers, books, hashes, paths)
        operations = []
        statuses = []
        for original, refreshed in zip(items, current):
            if (refreshed["status"] in ("MISSING", "CONFLICT") or
                    refreshed["book_id"] != original["book_id"] or
                    refreshed["destination"] != original["destination"]):
                raise CoverError(
                    "The remote cover match changed; stop and rerun preview")
            if refreshed["status"] == "UNCHANGED":
                statuses.append("UNCHANGED")
                continue
            cover = refreshed["cover"]
            book, _ = match_book(books, cover)
            if not book or book["id"] != refreshed["book_id"]:
                raise CoverError("Remote book identity changed; no commit made")
            directory = book_dir(book)
            destination = refreshed["destination"]
            if destination != f"{directory}/cover{cover.extension}":
                raise CoverError("Unexpected cover destination; refusing overwrite")
            old_path = book["metadata"].get("coverPath")
            if old_path and old_path not in {
                    f"{directory}/cover{suffix}" for suffix in COVER_SUFFIXES}:
                raise CoverError("Unexpected old cover path; refusing overwrite")
            book["metadata"]["coverPath"] = destination
            if refreshed["status"] != "LINK":
                operations.append(CommitOperationAdd(
                    path_in_repo=destination,
                    path_or_fileobj=io.BytesIO(cover.data)))
            statuses.append("LINKED" if refreshed["status"] == "LINK" else
                            ("UPDATED" if old_path else "UPLOADED"))
        if not operations and all(x == "UNCHANGED" for x in statuses):
            return expected_sha, statuses
        operations.append(CommitOperationAdd(
            path_in_repo="data/library.json",
            path_or_fileobj=io.BytesIO(
                (json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))))
        try:
            result = api.create_commit(
                repo_id=repo, repo_type="dataset", token=token,
                operations=operations, parent_commit=expected_sha,
                commit_message=f"Batch update {len(items)} novel covers")
        except Exception as exc:
            response = getattr(exc, "response", None)
            code = getattr(response, "status_code", None)
            if code == 429:
                delay = _short_retry_after(exc)
                if attempt == 0 and delay is not None:
                    print(f"Short HF rate-limit cooldown ({delay:.0f}s) before one retry.",
                          flush=True)
                    sleeper(delay)
                    # Never blindly retry an ambiguous commit outcome.
                    info = api.dataset_info(repo, token=token)
                    if info.private is not True or info.sha != expected_sha:
                        raise CoverError(
                            "Dataset changed after the rate-limit response; "
                            "rerun the ZIP to reconcile safely") from exc
                    continue
                raise CoverError(
                    "HF repository commit quota reached (HTTP 429). STOPPING "
                    "without retrying repeatedly. The quota may take about an "
                    "hour to reset. Rerun the SAME ZIP later; already uploaded "
                    "covers will be skipped automatically.") from exc
            if code in (409, 412):
                raise CoverError(
                    "Another process updated the dataset; rerun the ZIP preview. "
                    "No blind retry attempted.") from exc
            raise
        new_sha = getattr(result, "oid", None)
        if not isinstance(new_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", new_sha):
            raise CoverError(
                "Commit response lacked a valid revision. It may have succeeded; "
                "rerun the ZIP to verify and resume safely.")
        return new_sha, statuses
    raise CoverError("Short rate-limit retry was unsuccessful; rerun later")


def upload_batches(api, repo: str, token: str, changing: list[dict],
                   revision: str, *, batch_size: int = DEFAULT_BATCH_SIZE,
                   commit_pause: float = 2.0,
                   sleeper=time.sleep) -> tuple[int, int]:
    """Resume-safely upload all missing covers; return (commits, changed)."""
    if commit_pause < 0 or commit_pause > 60:
        raise CoverError("Commit pause must be between 0 and 60 seconds")
    groups = group_batches(changing, batch_size=batch_size)
    print(f"Batched cover upload: {len(changing)} pending cover(s), "
          f"{len(groups)} commit batch(es), max {batch_size} covers/batch.")
    total, commits, changed = len(changing), 0, 0
    processed = 0
    sha = revision
    for n, group in enumerate(groups, 1):
        if n > 1 and commit_pause:
            sleeper(commit_pause)
        print(f"Batch {n}/{len(groups)}: checking {len(group)} cover(s)...", flush=True)
        new_sha, statuses = commit_cover_batch(
            api, repo, token, group, sha, sleeper=sleeper)
        if new_sha != sha:
            commits += 1
        sha = new_sha
        for item, status in zip(group, statuses):
            processed += 1
            if status != "UNCHANGED":
                changed += 1
            print(f"[{processed}/{total}] {item['title']}: {status}", flush=True)
        print(f"Batch {n}/{len(groups)} complete; commits this run: {commits}.",
              flush=True)
    return commits, changed
