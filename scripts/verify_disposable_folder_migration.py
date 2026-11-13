#!/usr/bin/env python3
"""Live, disposable Hugging Face dataset acceptance for readable novel folders.

Creates ONLY a brand-new private synthetic dataset owned by the dedicated
HF_DISPOSABLE_TEST_TOKEN account. Performs an actual revision-bound copy,
delete, and catalogue rewrite through the Storage Controller's migration code,
checks both folder formats and the files' hashes, then deletes ONLY that
newly-created dataset. NEVER points at Taiyous-Novels or imports production data.

This does NOT test the production-only Cloudflare OAuth gateway; its mocked
contract is tested separately in Taiyous-Personal-Library PR #4.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import secrets
import sys
import zipfile
from pathlib import Path

from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download
from taiyou_storage.core import DEFAULT_REPO, validate_catalogue
from taiyou_storage.migrate_folders import MigrationError, apply_one, plan_migration
from taiyou_storage.paths import book_dir, legacy_dir, readable_dir

BOOK_ID = "a" * 24
OTHER_ID = "b" * 24
DATASET_PREFIX = "taiyou-disposable-readable-e2e-"
# A standard original 1x1 PNG, not a production novel's artwork.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/yn8AAAAASUVORK5CYII="
)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def epub_bytes(title: str) -> bytes:
    """Build a tiny, valid, entirely fictional EPUB without outside materials."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as epub:
        epub.writestr("mimetype", "application/epub+zip",
                      compress_type=zipfile.ZIP_STORED)
        epub.writestr("META-INF/container.xml",
                      '<?xml version="1.0" encoding="utf-8"?>'
                      '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"'
                      ' version="1.0"><rootfiles><rootfile '
                      'full-path="OEBPS/content.opf" '
                      'media-type="application/oebps-package+xml"/>'
                      '</rootfiles></container>')
        epub.writestr("OEBPS/content.opf",
                      '<?xml version="1.0" encoding="utf-8"?>'
                      '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"'
                      ' unique-identifier="uid"><metadata '
                      'xmlns:dc="http://purl.org/dc/elements/1.1/">'
                      '<dc:identifier id="uid">urn:taiyou:disposable:e2e</dc:identifier>'
                      '<dc:title>' + title + '</dc:title>'
                      '<dc:language>en</dc:language></metadata><manifest>'
                      '<item id="c1" href="chapter1.xhtml"'
                      ' media-type="application/xhtml+xml"/>'
                      '</manifest><spine><itemref idref="c1"/></spine></package>')
        epub.writestr("OEBPS/chapter1.xhtml",
                      '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
                      '<title>Sample chapter</title></head><body>'
                      '<h1>Chapter 1</h1><p>The fictional journey begins.</p>'
                      '</body></html>')
    return output.getvalue()


def archive_bytes(epub: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as book_zip:
        book_zip.writestr("source.epub", epub)
        book_zip.writestr("metadata.json", json.dumps(
            {"title": "A Synthetic Journey", "author": "Fictional Author"}))
    return output.getvalue()


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def create_fixture() -> tuple[dict, dict[str, bytes]]:
    # One ID-only book, one already-readable book. Metadata titles deliberately
    # need not match readable labels, because titles may change later.
    old = legacy_dir(BOOK_ID)
    other = readable_dir(OTHER_ID, "Already Readable 第二卷")
    first = {
        "id": BOOK_ID,
        "metadata": {
            "id": BOOK_ID, "title": "An Explorer's Journey: First Dawn",
            "author": "Fictional Author", "personalRating": 9,
            "personalTags": ["Keep"], "progress": 73,
            "comments": "Synthetic notes stay attached to an ID",
            "coverPath": old + "/cover.png",
        },
        "epubPath": old + "/source.epub",
        "archivePath": old + "/original.zip",
    }
    second = {
        "id": OTHER_ID,
        "metadata": {
            "id": OTHER_ID, "title": "Renamed after uploading",
            "author": "Fictional Author",
            "coverPath": other + "/cover.png",
        },
        "epubPath": other + "/source.epub",
    }
    catalogue = {"version": 1, "books": [first, second]}
    validate_catalogue(catalogue)
    chapter = epub_bytes(first["metadata"]["title"])
    second_chapter = epub_bytes(second["metadata"]["title"])
    files = {
        first["epubPath"]: chapter,
        first["archivePath"]: archive_bytes(chapter),
        first["metadata"]["coverPath"]: PNG,
        old + "/extra.txt": b"synthetic extra file must not be lost",
        second["epubPath"]: second_chapter,
        second["metadata"]["coverPath"]: PNG,
        "data/personal/reviews/" + BOOK_ID + ".json": encoded({
            "version": 1, "bookId": BOOK_ID, "rating": 9,
            "comments": "This must survive migration", "updatedAt": 1111,
        }),
        "data/personal/progress/" + BOOK_ID + ".json": encoded({
            "version": 1, "bookId": BOOK_ID, "progress": 73,
            "currentChapterIndex": 2, "updatedAt": 1111,
        }),
        "data/personal/collections.json": encoded({
            "version": 1, "collections": [{
                "id": "synthetic", "name": "Test Series",
                "bookIds": [BOOK_ID, OTHER_ID], "updatedAt": 1111,
            }],
        }),
        "data/library.json": encoded(catalogue),
    }
    return catalogue, files


def download(api: HfApi, repo: str, token: str, path: str, revision: str) -> bytes:
    result = hf_hub_download(
        repo_id=repo, repo_type="dataset",
        filename=path, revision=revision, token=token,
    )
    return Path(result).read_bytes()


def run() -> int:
    token = os.environ.get("HF_DISPOSABLE_TEST_TOKEN", "").strip()
    if not token.startswith("hf_"):
        raise RuntimeError("BLOCKED: dedicated HF_DISPOSABLE_TEST_TOKEN is unavailable. "
                           "Do not use HF_STORAGE_CONTROLLER_TOKEN or the production dataset.")

    api = HfApi(token=token)
    user = api.whoami(token=token).get("name", "")
    if not isinstance(user, str) or not user or "/" in user:
        raise RuntimeError("Cannot establish an isolated dataset namespace")
    dataset_name = DATASET_PREFIX + secrets.token_hex(5)
    repo = user + "/" + dataset_name
    if repo == DEFAULT_REPO or not repo.startswith(user + "/" + DATASET_PREFIX):
        raise RuntimeError("Unsafe target dataset name; no writes permitted")

    created = False
    try:
        api.create_repo(repo_id=repo, repo_type="dataset", private=True,
                        token=token, exist_ok=False)
        created = True
        info = api.dataset_info(repo, token=token)
        if info.private is not True or not info.sha:
            raise RuntimeError("Newly created dataset privacy could not be confirmed")

        catalogue, fixtures = create_fixture()
        current_sha = info.sha
        result = api.create_commit(
            repo_id=repo, repo_type="dataset", token=token,
            parent_commit=current_sha, commit_message="Seed synthetic mixed-format library",
            operations=[CommitOperationAdd(path_in_repo=path,
                                           path_or_fileobj=io.BytesIO(data))
                        for path, data in fixtures.items()],
        )
        current_sha = result.oid
        if not current_sha:
            raise RuntimeError("Seed commit did not return an immutable revision")
        verify = api.dataset_info(repo, token=token)
        if verify.private is not True or verify.sha != current_sha:
            raise RuntimeError("Seed commit revision or dataset privacy is inconsistent")
        files_before = set(api.list_repo_files(
            repo_id=repo, repo_type="dataset", revision=current_sha, token=token))
        assert set(fixtures).issubset(files_before), "Missing synthetic files after seed"
        for path, contents in fixtures.items():
            assert sha256(download(api, repo, token, path, current_sha)) == sha256(contents), path

        remotely_loaded = json.loads(download(api, repo, token, "data/library.json", current_sha))
        assert validate_catalogue(remotely_loaded) == catalogue["books"]
        planned = plan_migration(remotely_loaded["books"], files_before)
        by_id = {item["id"]: item for item in planned}
        assert by_id[BOOK_ID]["status"] == "MIGRATE"
        assert by_id[OTHER_ID]["status"] == "ALREADY_READABLE"
        assert len(by_id[BOOK_ID]["moves"]) == 4
        assert not set(dest for _, dest in by_id[BOOK_ID]["moves"]) & files_before
        print("PASS initial PRIVATE dataset: legacy and readable novels, EPUB, ZIP, cover, "
              "extra file and three personal sidecars verified by SHA-256")

        migrated_sha = apply_one(api, repo, token, by_id[BOOK_ID], current_sha)
        latest = api.dataset_info(repo, token=token)
        assert latest.private is True and latest.sha == migrated_sha
        files_after = set(api.list_repo_files(
            repo_id=repo, repo_type="dataset", revision=migrated_sha, token=token))
        expected = dict(fixtures)
        for old_path, new_path in by_id[BOOK_ID]["moves"]:
            expected[new_path] = expected.pop(old_path)
        expected["data/library.json"] = download(api, repo, token, "data/library.json", migrated_sha)
        assert set(expected).issubset(files_after), "Missing files after migration"
        assert not any(path.startswith(legacy_dir(BOOK_ID) + "/") for path in files_after)
        for path, value in expected.items():
            actual = download(api, repo, token, path, migrated_sha)
            assert sha256(actual) == sha256(value), "Bytes changed: " + path
        converted = json.loads(expected["data/library.json"])
        assert validate_catalogue(converted) == converted["books"]
        after = {entry["id"]: entry for entry in converted["books"]}
        assert after[BOOK_ID]["id"] == BOOK_ID and after[OTHER_ID] == catalogue["books"][1]
        assert book_dir(after[BOOK_ID]) == readable_dir(BOOK_ID, catalogue["books"][0]["metadata"]["title"])
        assert after[BOOK_ID]["metadata"]["progress"] == 73
        assert after[BOOK_ID]["metadata"]["personalRating"] == 9
        assert after[BOOK_ID]["metadata"]["personalTags"] == ["Keep"]
        assert after[BOOK_ID]["metadata"]["comments"] == "Synthetic notes stay attached to an ID"
        assert after[BOOK_ID]["metadata"]["coverPath"] == book_dir(after[BOOK_ID]) + "/cover.png"
        assert plan_migration(converted["books"], files_after)[0]["status"] == "ALREADY_READABLE"
        print("PASS revision-bound copy/delete/catalogue update: all files, both formats, "
              "metadata, notes, progress and collection bytes preserved")

        # A stale client cannot alter the dataset using a parent revision read
        # before the migration, even if its write looks otherwise valid.
        rejected = False
        try:
            api.upload_file(
                repo_id=repo, repo_type="dataset", token=token,
                path_in_repo="data/personal/progress/" + BOOK_ID + ".json",
                path_or_fileobj=encoded({"stale": True}),
                parent_commit=current_sha, commit_message="Reject stale synthetic client",
            )
        except Exception as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if code in (409, 412) or (code == 400 and "parent" in str(exc).lower()):
                rejected = True
            else:
                raise
        assert rejected, "A stale parent unexpectedly modified the disposable dataset"
        assert api.dataset_info(repo, token=token).sha == migrated_sha
        assert download(api, repo, token,
                        "data/personal/progress/" + BOOK_ID + ".json",
                        migrated_sha) == fixtures["data/personal/progress/" + BOOK_ID + ".json"]
        print("PASS stale-client conflict: no write committed after folder migration")

        try:
            apply_one(api, DEFAULT_REPO, token, by_id[BOOK_ID], migrated_sha)
            raise AssertionError("Production migration must always be rejected")
        except MigrationError:
            pass
        print("PASS production dataset migration guard")
        print("PASS real disposable private HF readable-folder migration integration")
        return 0
    finally:
        if created:
            # Never delete arbitrary datasets: only the one created by this run.
            if repo == DEFAULT_REPO or repo != user + "/" + dataset_name or not dataset_name.startswith(DATASET_PREFIX):
                raise RuntimeError("Refused unsafe cleanup target")
            api.delete_repo(repo_id=repo, repo_type="dataset", token=token)
            print("Disposable private test dataset deleted")


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print("FAIL disposable readable-folder acceptance: " +
              type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(1)
