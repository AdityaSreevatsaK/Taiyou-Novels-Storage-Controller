"""Add source genres to an existing PRIVATE Hugging Face catalogue without touching novels.

Fetch only historical GitHub chapter-batch artifact *metadata*, never chapter prose.
Never guess book identities, merge duplicates, or overwrite personal fields.
Preview by default; --apply makes one optimistic, backup-first private commit.
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
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

from .core import DEFAULT_REPO, validate_catalogue

UPSTREAM_REPO = "RichardDaffern/Novel_Library"
GITHUB_API = f"https://api.github.com/repos/{UPSTREAM_REPO}"
STATUS = {"completed": "Completed", "complete": "Completed", "ongoing": "Ongoing",
          "in progress": "Ongoing", "in-progress": "Ongoing"}
NOISE = re.compile(r"^(?:last\s+update\b|updated\b|language\s*:|status\s*:)", re.I)
ARTIFACT_PATTERN = re.compile(r"^chapter-batch-([a-f0-9]{20})-(\d+)-(\d+)$")
MAX_ARCHIVE_BYTES = 30 * 1024 * 1024
MAX_EPUB_BYTES = 40 * 1024 * 1024


class GenreRepairError(ValueError):
    """Unsafe or unavailable metadata repair."""


def source_key(raw: str | None) -> str:
    if not isinstance(raw, str):
        return ""
    try:
        u = urlsplit(raw.strip())
    except ValueError:
        return ""
    if u.scheme not in ("https", "http") or not u.hostname:
        return ""
    host = u.hostname.lower().removeprefix("www.")
    return f"{host}/{u.path.strip('/').lower()}"


def subject_genres(subjects: list[str]) -> list[str]:
    found, seen = [], set()
    for subject in subjects:
        if not isinstance(subject, str):
            continue
        item = " ".join(subject.strip().split())
        key = item.casefold()
        if not item or len(item) > 100 or key in STATUS or NOISE.match(item) or key in seen:
            continue
        seen.add(key)
        found.append(item)
    return found[:50]


def read_first_batch_metadata(payload: bytes, expected_url: str) -> dict:
    """Parse only ZIP metadata.json and embedded source EPUB's XML package."""
    if not payload or len(payload) > MAX_ARCHIVE_BYTES:
        raise GenreRepairError("GitHub artifact outside permitted size range")
    with ZipFile(BytesIO(payload)) as archive:
        names = archive.namelist()
        manifests = [n for n in names if n.endswith("/metadata.json")]
        epubs = [n for n in names if n.endswith("/source.epub")]
        if len(manifests) != 1 or len(epubs) != 1:
            raise GenreRepairError("Batch must contain exactly one metadata.json and source.epub")
        m_info, epub_info = archive.getinfo(manifests[0]), archive.getinfo(epubs[0])
        if m_info.file_size > 2_000_000 or epub_info.file_size > MAX_EPUB_BYTES:
            raise GenreRepairError("Oversized batch metadata or EPUB")
        metadata = json.loads(archive.read(manifests[0]))
        if source_key(metadata.get("source_url")) != source_key(expected_url):
            raise GenreRepairError("Batch source URL does not match catalogue identity")
        epub = archive.read(epubs[0])
    with ZipFile(BytesIO(epub)) as book:
        container = ET.fromstring(book.read("META-INF/container.xml"))
        rootfile = next((node for node in container.iter() if node.tag.endswith("rootfile")), None)
        package_name = rootfile.get("full-path") if rootfile is not None else None
        if not package_name or package_name.startswith(("/", "../")) or ".." in package_name.split("/"):
            raise GenreRepairError("Invalid EPUB package path")
        if book.getinfo(package_name).file_size > 4_000_000:
            raise GenreRepairError("EPUB package XML too large")
        opf = ET.fromstring(book.read(package_name))
    fields: dict[str, list[str]] = {}
    for node in opf.iter():
        if not node.tag.startswith("{http://purl.org/dc/elements/1.1/}"):
            continue
        field = node.tag.rsplit("}", 1)[-1]
        if field in ("subject", "description") and node.text and node.text.strip():
            fields.setdefault(field, []).append(node.text.strip())
    subjects = fields.get("subject", [])
    genres = subject_genres(subjects)
    result = {"genres": genres}
    if fields.get("description"):
        result["description"] = fields["description"][0][:24000]
    for sub in subjects:
        if sub.casefold().strip() in STATUS:
            result["status"] = STATUS[sub.casefold().strip()]
            break
    return result


def plan_repair(catalogue: dict, sources: dict[str, dict]) -> tuple[dict, dict]:
    """Return a deep-copied catalogue plus count-only report, preserving every ID."""
    if catalogue.get("version") != 1 or not isinstance(catalogue.get("books"), list):
        raise GenreRepairError("Unsupported catalogue format")
    validate_catalogue(catalogue)
    cloned = json.loads(json.dumps(catalogue, ensure_ascii=False))
    totals = Counter(source_key(x["metadata"].get("sourceUrl")) for x in cloned["books"])
    stats = Counter()
    for row in cloned["books"]:
        old = row["metadata"]
        key = source_key(old.get("sourceUrl"))
        if old.get("sourceTags"):
            stats["already_tagged"] += 1
            continue
        if not key:
            stats["unknown_source"] += 1
            continue
        if totals[key] > 1:
            stats["ambiguous_source"] += 1
            continue
        source = sources.get(key) or {}
        genres = subject_genres(source.get("genres") or [])
        if not genres:
            stats["missing_genres"] += 1
            continue
        # Source-managed only; no changes to IDs, personalTags, progress,
        # reviews, statuses already set, original ZIPs or EPUB binaries.
        old["sourceTags"] = genres
        if not old.get("description") and source.get("description"):
            old["description"] = source["description"][:24000]
            stats["descriptions_added"] += 1
        if not old.get("status") and source.get("status") in ("Ongoing", "Completed"):
            old["status"] = source["status"]
            stats["statuses_added"] += 1
        stats["tagged"] += 1
    for metric in ("tagged", "already_tagged", "unknown_source", "ambiguous_source",
                   "missing_genres", "descriptions_added", "statuses_added"):
        stats.setdefault(metric, 0)
    stats["total_books"] = len(cloned["books"])
    return cloned, dict(stats)


class GithubMetadata:
    def __init__(self, token: str):
        if not token:
            raise GenreRepairError("A token with GitHub Actions artifact read access is required")
        import httpx
        self.client = httpx.Client(follow_redirects=True, timeout=90,
                                   headers={"Authorization": "Bearer " + token,
                                            "Accept": "application/vnd.github+json",
                                            "X-GitHub-Api-Version": "2022-11-28"})
        self.cached_runs: dict[int, list[dict]] = {}

    def close(self):
        self.client.close()

    def artifacts(self, run_id: int) -> list[dict]:
        if run_id in self.cached_runs:
            return self.cached_runs[run_id]
        result = []
        for page in range(1, 11):
            response = self.client.get(f"{GITHUB_API}/actions/runs/{run_id}/artifacts",
                                       params={"per_page": 100, "page": page})
            response.raise_for_status()
            batch = response.json()["artifacts"]
            result.extend(batch)
            if len(batch) < 100:
                break
        self.cached_runs[run_id] = result
        return result

    def first_batch(self, url: str, run_id: int) -> dict:
        key = sha256(url.encode("utf-8")).hexdigest()[:20]
        candidates = []
        for artifact in self.artifacts(run_id):
            match = ARTIFACT_PATTERN.fullmatch(artifact.get("name", ""))
            if match and match.group(1) == key and not artifact.get("expired"):
                candidates.append((int(match.group(2)), int(match.group(3)), artifact["id"]))
        if not candidates:
            return {}
        candidates.sort()
        _, _, artifact_id = candidates[0]
        response = self.client.get(f"{GITHUB_API}/actions/artifacts/{artifact_id}/zip")
        response.raise_for_status()
        return read_first_batch_metadata(response.content, url)


def from_registry(catalogue: dict, registry: dict, github: GithubMetadata) -> tuple[dict, dict]:
    records = {}
    for row in registry.get("novels", []):
        key = source_key(row.get("url"))
        complete = [d for d in row.get("downloads", [])
                    if d.get("status") == "complete" and d.get("range") == "all"]
        if key and complete:
            records[key] = (row["url"], int(complete[-1]["run_id"]))
    freq = Counter(source_key(b["metadata"].get("sourceUrl")) for b in catalogue["books"])
    candidates = {k for b in catalogue["books"]
                  if not b["metadata"].get("sourceTags")
                  for k in [source_key(b["metadata"].get("sourceUrl"))]
                  if k and freq[k] == 1 and k in records}
    found = {}
    errors = 0
    for key in sorted(candidates):
        url, run_id = records[key]
        try:
            details = github.first_batch(url, run_id)
        except Exception:
            # Never write guessed tags or copy a different novel's metadata.
            errors += 1
            continue
        if details.get("genres"):
            found[key] = details
    repaired, stats = plan_repair(catalogue, found)
    stats["artifact_read_errors"] = errors
    stats["eligible_sources"] = len(candidates)
    stats["sources_found"] = len(found)
    return repaired, stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit only additive source metadata to private dataset")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    args = parser.parse_args(argv)
    token = os.environ.get("HF_TOKEN", "").strip()
    gh_token = os.environ.get("NOVEL_LIBRARY_ACTIONS_TOKEN", "").strip()
    if not token or not gh_token:
        parser.error("HF_TOKEN and NOVEL_LIBRARY_ACTIONS_TOKEN environment secrets are required")
    from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download
    import httpx
    api = HfApi()
    client = GithubMetadata(gh_token)
    try:
        dataset = api.dataset_info(args.repo, token=token)
        if dataset.private is not True:
            raise GenreRepairError("Refusing to touch a nonprivate HF dataset")
        revision = dataset.sha
        local = hf_hub_download(repo_id=args.repo, repo_type="dataset",
                                filename="data/library.json", revision=revision, token=token)
        original = Path(local).read_bytes()
        catalogue = json.loads(original)
        validate_catalogue(catalogue)
        request = client.client.get("https://raw.githubusercontent.com/" +
                                     UPSTREAM_REPO + "/main/downloaded_novels.json")
        request.raise_for_status()
        registry = request.json()
        repaired, stats = from_registry(catalogue, registry, client)
        # Public CI logs contain counts only (no private titles, IDs or excerpts).
        print(json.dumps({"mode": "APPLY" if args.apply else "PREVIEW", **stats}, sort_keys=True))
        if not args.apply or not stats.get("tagged"):
            return 0
        if api.dataset_info(args.repo, token=token).sha != revision:
            raise GenreRepairError("Dataset changed during preview; refusing write")
        backup = "backups/genre-repair/" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + revision[:12] + ".json"
        result = json.dumps(repaired, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        api.create_commit(repo_id=args.repo, repo_type="dataset", token=token,
                          parent_commit=revision,
                          operations=[
                              CommitOperationAdd(path_in_repo=backup, path_or_fileobj=BytesIO(original)),
                              CommitOperationAdd(path_in_repo="data/library.json", path_or_fileobj=BytesIO(result)),
                          ], commit_message="Backfill verified source genres without changing novel files")
        print("Private genre repair committed with catalogue backup. No novel EPUBs or ZIPs were changed.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("Genre repair failed without a successful commit: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)