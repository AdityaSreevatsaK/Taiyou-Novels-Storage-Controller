"""Private, one-shot Hugging Face acceptance of the real remote-first backup.

Creates only two uniquely named PRIVATE synthetic datasets on a trusted master
workflow runner. No production HF calls, repository deletions or public artefacts.
"""
from __future__ import annotations

from contextlib import ExitStack
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sys
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

OWNER = "AdityaSreevatsaK"
PREFIX = "Taiyou-Backup-Acceptance"
BOOK_ID = "b" * 24
STAGE = 0


def stage(number: int) -> None:
    """Record a non-sensitive numeric phase for safe GitHub diagnostics."""
    global STAGE
    STAGE = number


def repositories(run_id: str, attempt: str, *, owner: str = OWNER) -> tuple[str, str]:
    """Names never come from workflow inputs, and cannot select production."""
    if not re.fullmatch(r"[1-9][0-9]{0,17}", run_id):
        raise ValueError("Invalid GitHub run ID")
    if not re.fullmatch(r"[1-9][0-9]{0,5}", attempt):
        raise ValueError("Invalid GitHub attempt")
    if not isinstance(owner, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", owner):
        raise ValueError("Invalid authenticated HF username")
    suffix = f"{run_id}-A{attempt}"
    return (f"{owner}/{PREFIX}-Source-{suffix}",
            f"{owner}/{PREFIX}-Destination-{suffix}")


def synthetic_files() -> dict[str, bytes]:
    import base64
    epub = BytesIO()
    with ZipFile(epub, "w") as book:
        book.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        book.writestr("META-INF/container.xml",
                      "<?xml version='1.0'?><container version='1.0' xmlns='urn:oasis:names:tc:opendocument:xmlns:container'><rootfiles><rootfile full-path='OEBPS/content.opf' media-type='application/oebps-package+xml'/></rootfiles></container>",
                      compress_type=ZIP_DEFLATED)
        book.writestr("OEBPS/content.opf",
                      "<?xml version='1.0'?><package xmlns='http://www.idpf.org/2007/opf' unique-identifier='uid' version='2.0'><metadata xmlns:dc='http://purl.org/dc/elements/1.1/'><dc:identifier id='uid'>synthetic-backup-acceptance</dc:identifier><dc:title>Acceptance Fixture</dc:title><dc:language>en</dc:language></metadata><manifest><item id='chapter' href='chapter.xhtml' media-type='application/xhtml+xml'/></manifest><spine><itemref idref='chapter'/></spine></package>",
                      compress_type=ZIP_DEFLATED)
        book.writestr("OEBPS/chapter.xhtml",
                      "<html xmlns='http://www.w3.org/1999/xhtml'><head><title>Test</title></head><body><p>Fictional acceptance data only.</p></body></html>",
                      compress_type=ZIP_DEFLATED)
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as outer:
        outer.writestr("source.epub", epub.getvalue())
    cover_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+nvxkAAAAASUVORK5CYII=")
    folder = f"data/novels/{BOOK_ID} - Acceptance Fixture"
    cover = f"{folder}/cover.png"
    catalogue = {"version": 1, "books": [{
        "id": BOOK_ID,
        "metadata": {"id": BOOK_ID, "title": "Acceptance Fixture",
                     "author": "Synthetic", "status": "Ongoing",
                     "coverPath": cover},
        "epubPath": f"{folder}/source.epub",
        "archivePath": f"{folder}/original.zip",
        "coverPath": cover
    }]}
    return {
        "data/library.json": (json.dumps(catalogue, sort_keys=True) + "\n").encode(),
        f"{folder}/source.epub": epub.getvalue(),
        f"{folder}/original.zip": archive.getvalue(),
        cover: cover_bytes,
        "data/acceptance-marker.json": b'{"synthetic_only":true}\n',
    }


def private_revision(api, repo: str, token: str) -> str:
    info = api.dataset_info(repo_id=repo, token=token)
    if (info.private is not True or not isinstance(info.sha, str)
            or not re.fullmatch(r"[0-9a-f]{40}", info.sha)):
        raise ValueError("Synthetic dataset privacy or revision verification failed")
    return info.sha


def create_private(api, repo: str, token: str) -> str:
    # No overwrite, no deletion. A rerun uses a fresh run-attempt suffix.
    api.create_repo(repo_id=repo, repo_type="dataset", private=True,
                    exist_ok=False, token=token)
    return private_revision(api, repo, token)


def acceptance(api, source: str, destination: str, token: str) -> dict[str, int]:
    from huggingface_hub import CommitOperationAdd, CommitOperationCopy, hf_hub_download
    from taiyou_storage.core import validate_catalogue
    import taiyou_storage.actions as actions
    import taiyou_storage.remote_backup as backup

    if (source == destination or "Taiyous-Novels" in source
            or "Taiyous-Novels" in destination):
        raise ValueError("Production or identical datasets forbidden")
    stage(1)
    initial = create_private(api, source, token)
    stage(2)
    create_private(api, destination, token)
    fixture = synthetic_files()
    validate_catalogue(json.loads(fixture["data/library.json"]))
    stage(3)
    api.create_commit(
        repo_id=source, repo_type="dataset", token=token, parent_commit=initial,
        operations=[CommitOperationAdd(path_in_repo=name,
                                       path_or_fileobj=BytesIO(data))
                    for name, data in sorted(fixture.items())],
        commit_message="Isolated synthetic backup acceptance source",
    )
    src_rev = private_revision(api, source, token)

    # Scoped to this test process. Production entry points are not changed.
    # source_repo MUST be explicit because its function default is bound
    # to production at definition time.
    with ExitStack() as guards:
        guards.enter_context(patch.object(actions, "DEFAULT_REPO", source))
        guards.enter_context(patch.object(backup, "DEFAULT_REPO", source))
        stage(4)
        before = backup.preview_remote_backup(api, destination, token)
        if before["Objects eligible for remote copy"] < len(fixture):
            raise ValueError("Synthetic preflight inventory unexpectedly incomplete")
        # Stage one legitimate copy, simulating an interrupted first batch.
        stage(5)
        dst_rev = private_revision(api, destination, token)
        api.create_commit(
            repo_id=destination, repo_type="dataset", token=token,
            parent_commit=dst_rev,
            operations=[CommitOperationCopy(
                src_path_in_repo="data/library.json",
                path_in_repo=f"snapshots/{src_rev}/files/data/library.json",
                src_revision=src_rev, src_repo_id=source,
                src_repo_type="dataset")],
            commit_message="Synthetic partial-copy recovery acceptance",
        )
        stage(6)
        first = backup.remote_backup(api, destination, token,
                                     source_repo=source, batch_size=2)
        if (first["Snapshot verified"] != 1 or
                first["Previously verified objects reused"] != 1):
            raise ValueError("Partial resume or verification failed")
        dst_before_rerun = private_revision(api, destination, token)
        stage(7)
        again = backup.remote_backup(api, destination, token,
                                      source_repo=source, batch_size=2)
        dst_after_rerun = private_revision(api, destination, token)
        if again["Objects copied"] != 0 or dst_before_rerun != dst_after_rerun:
            raise ValueError("Snapshot retry was not idempotent")
        stage(8)
        post = backup.preview_remote_backup(api, destination, token)
        if post["Objects eligible for remote copy"] != 0:
            raise ValueError("Snapshot remains incomplete")

    stage(9)
    receipt = json.loads(Path(hf_hub_download(
        repo_id=destination, repo_type="dataset",
        filename=f"snapshots/{src_rev}/verification.json",
        revision=dst_after_rerun, token=token)).read_bytes())
    if (receipt.get("source_repository") != source or
            receipt.get("source_revision") != src_rev or
            receipt.get("files") != first["Source files"]):
        raise ValueError("Completion receipt conflicts with synthetic source")

    stage(10)
    for name, expected in fixture.items():
        src = Path(hf_hub_download(repo_id=source, repo_type="dataset",
                                  filename=name, revision=src_rev,
                                  token=token)).read_bytes()
        dst = Path(hf_hub_download(repo_id=destination, repo_type="dataset",
                                  filename=f"snapshots/{src_rev}/files/{name}",
                                  revision=dst_after_rerun, token=token)).read_bytes()
        if sha256(src).digest() != sha256(dst).digest() or src != expected:
            raise ValueError("Independent snapshot SHA-256 mismatch")
    if private_revision(api, source, token) != src_rev:
        raise ValueError("Source revision changed")
    stage(11)
    return first


def main() -> int:
    if (os.getenv("GITHUB_REPOSITORY") !=
            "AdityaSreevatsaK/Taiyou-Novels-Storage-Controller" or
            os.getenv("GITHUB_REF") != "refs/heads/master"):
        print("ERROR: Trusted Controller master runner required.", file=sys.stderr)
        return 2
    token = os.getenv("HF_DISPOSABLE_TEST_TOKEN", "").strip()
    if not token:
        print("ERROR: HF_DISPOSABLE_TEST_TOKEN is unavailable to the workflow.",
              file=sys.stderr)
        return 2
    stage(0)
    try:
        import huggingface_hub
        if huggingface_hub.__version__ != "1.33.0":
            raise ValueError("Expected pinned Hugging Face client not installed")
        api = huggingface_hub.HfApi()
        stage(1)
        identity = api.whoami(token=token)
        owner = identity.get("name") if isinstance(identity, dict) else None
        if not isinstance(owner, str):
            raise ValueError("HF token identity unavailable")
        source, destination = repositories(
            os.getenv("GITHUB_RUN_ID", ""), os.getenv("GITHUB_RUN_ATTEMPT", ""),
            owner=owner)
        print(f"Acceptance token owner match: {int(owner == OWNER)}")
        result = acceptance(api, source, destination, token)
        print(f"Acceptance stage: {STAGE}")
        for key, value in result.items():
            # Only numeric metrics, never novel names, dataset IDs or URLs.
            print(f"{key}: {value}")
        print("Verified complete: 1")
        return 0
    except Exception as error:
        # Public GitHub job logs must never contain private HF error bodies.
        print(f"Acceptance stage: {STAGE}")
        code = {"ValueError": 1, "HTTPError": 2, "HfHubHTTPError": 3, "RepositoryNotFoundError": 4, "TypeError": 5, "AttributeError": 6, "ConnectionError": 7}.get(type(error).__name__, 99)
        print(f"Acceptance error code: {code}")
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int) and 100 <= status <= 599:
            print(f"Acceptance HTTP status: {status}")
        print(f"ERROR: Synthetic HF acceptance failed ({type(error).__name__}).",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
