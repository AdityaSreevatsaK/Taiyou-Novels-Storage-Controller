#!/usr/bin/env python3
"""Live readable-folder test against a PRE-CREATED, empty private dataset.

The operator creates the dedicated private test dataset once and grants the
HF_DISPOSABLE_TEST_TOKEN write access ONLY to that dataset. This runner never
calls create_repo or delete_repo, and never accesses production novel data.
It commits original synthetic fixtures, migrates their folder paths atomically,
checks immutable IDs and bytes, then removes ONLY its own fixture files.

This does NOT test the production-only Cloudflare OAuth gateway; its mocked
contract is tested separately in Taiyous-Personal-Library PR #4.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path

from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi, hf_hub_download
from taiyou_storage.core import DEFAULT_REPO, validate_catalogue
from taiyou_storage.migrate_folders import (MigrationError, apply_one, apply_migration_batch,
                                            group_migration_batches, plan_migration)
from taiyou_storage.paths import book_dir, legacy_dir, readable_dir

BOOK_ID = "a" * 24
OTHER_ID = "b" * 24
THIRD_ID = "c" * 24
FOURTH_ID = "d" * 24
# Explicitly reserved dataset, created manually through Hugging Face (PRIVATE).
# The token must be scoped for write access to THIS dataset only.
TEST_REPO = "AdityaSreevatsaK/Taiyou-Readable-Folder-Test"
ALLOWED_BASELINE_FILES = frozenset({".gitattributes", "README.md"})
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
    third_dir = legacy_dir(THIRD_ID)
    fourth_dir = legacy_dir(FOURTH_ID)
    third = {
        "id": THIRD_ID,
        "metadata": {
            "id": THIRD_ID, "title": "Third Synthetic Expedition",
            "author": "Fictional Author", "personalRating": 6,
            "personalTags": ["Third", "Retain"], "progress": 27,
            "comments": "Personal third-book notes must survive",
            "coverPath": third_dir + "/cover.png",
        },
        "epubPath": third_dir + "/source.epub",
        "archivePath": third_dir + "/original.zip",
    }
    fourth = {
        "id": FOURTH_ID,
        "metadata": {
            "id": FOURTH_ID, "title": "Fourth Synthetic Expedition",
            "author": "Fictional Author", "personalRating": 7,
            "personalTags": ["Fourth"], "progress": 11,
            "comments": "Fourth book stays attached to its ID",
            "coverPath": fourth_dir + "/cover.png",
        },
        "epubPath": fourth_dir + "/source.epub",
        "archivePath": fourth_dir + "/original.zip",
    }
    catalogue = {"version": 1, "books": [first, second, third, fourth]}
    validate_catalogue(catalogue)
    chapter = epub_bytes(first["metadata"]["title"])
    second_chapter = epub_bytes(second["metadata"]["title"])
    third_chapter = epub_bytes(third["metadata"]["title"])
    fourth_chapter = epub_bytes(fourth["metadata"]["title"])
    files = {
        first["epubPath"]: chapter,
        first["archivePath"]: archive_bytes(chapter),
        first["metadata"]["coverPath"]: PNG,
        old + "/extra.txt": b"synthetic extra file must not be lost",
        second["epubPath"]: second_chapter,
        second["metadata"]["coverPath"]: PNG,
        third["epubPath"]: third_chapter,
        third["archivePath"]: archive_bytes(third_chapter),
        third["metadata"]["coverPath"]: PNG,
        third_dir + "/extra.txt": b"other legacy book auxiliary file",
        fourth["epubPath"]: fourth_chapter,
        fourth["archivePath"]: archive_bytes(fourth_chapter),
        fourth["metadata"]["coverPath"]: PNG,
        "data/personal/reviews/" + BOOK_ID + ".json": encoded({
            "version": 1, "bookId": BOOK_ID, "rating": 9,
            "comments": "This must survive migration", "updatedAt": 1111,
        }),
        "data/personal/progress/" + BOOK_ID + ".json": encoded({
            "version": 1, "bookId": BOOK_ID, "progress": 73,
            "currentChapterIndex": 2, "updatedAt": 1111,
        }),
        "data/personal/reviews/" + THIRD_ID + ".json": encoded({
            "version": 1, "bookId": THIRD_ID, "rating": 6,
            "comments": "Third synthetic review persists", "updatedAt": 1111,
        }),
        "data/personal/progress/" + FOURTH_ID + ".json": encoded({
            "version": 1, "bookId": FOURTH_ID, "progress": 11,
            "currentChapterIndex": 1, "updatedAt": 1111,
        }),
        "data/personal/collections.json": encoded({
            "version": 1, "collections": [{
                "id": "synthetic", "name": "Test Series",
                "bookIds": [BOOK_ID, OTHER_ID, THIRD_ID, FOURTH_ID], "updatedAt": 1111,
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


def validate_test_repo(repo: str) -> str:
    """Reject all production, alternate and malformed repository names."""
    if repo != TEST_REPO or repo == DEFAULT_REPO:
        raise RuntimeError("BLOCKED: only the pre-created private test dataset "
                           + TEST_REPO + " is allowed")
    return repo


def cleanup_fixture(api: HfApi, repo: str, token: str, baseline: set[str],
                    owned_paths: set[str], last_owned_sha: str | None) -> None:
    """Delete ONLY fixture files, never the repository or pre-existing content.

    If another writer changes this dataset or a commit result is uncertain,
    refuse cleanup instead of possibly deleting someone else's files.
    """
    validate_test_repo(repo)
    info = api.dataset_info(repo, token=token)
    if info.private is not True or not info.sha:
        raise RuntimeError("Cleanup blocked: dataset is no longer verifiably private")
    present = set(api.list_repo_files(repo_id=repo, repo_type="dataset",
                                      revision=info.sha, token=token))
    additions = present - baseline
    if not additions:
        print("PASS disposable dataset already empty, no cleanup required")
        return
    if not additions.issubset(owned_paths):
        raise RuntimeError("Cleanup refused: files not owned by this test are present")
    if last_owned_sha is None or info.sha != last_owned_sha:
        raise RuntimeError("Cleanup refused: dataset revision changed or last commit is uncertain")
    result = api.create_commit(
        repo_id=repo, repo_type="dataset", token=token,
        parent_commit=info.sha,
        commit_message="Remove synthetic readable-folder acceptance files",
        operations=[CommitOperationDelete(path_in_repo=path)
                    for path in sorted(additions)],
    )
    check = api.dataset_info(repo, token=token)
    if check.private is not True or check.sha != result.oid:
        raise RuntimeError("Cleanup commit outcome uncertain; inspect test dataset")
    remaining = set(api.list_repo_files(repo_id=repo, repo_type="dataset",
                                         revision=check.sha, token=token))
    if remaining != baseline:
        raise RuntimeError("Cleanup incomplete: test dataset contents differ from baseline")
    print("PASS synthetic files removed; pre-created private test dataset retained")


def run() -> int:
    token = os.environ.get("HF_DISPOSABLE_TEST_TOKEN", "").strip()
    if not token.startswith("hf_"):
        raise RuntimeError("BLOCKED: a token scoped to the dedicated private test "
                           "dataset is required. Never use the production storage token.")
    repo = validate_test_repo(os.environ.get("HF_DISPOSABLE_TEST_REPO", "").strip())
    api = HfApi(token=token)
    info = api.dataset_info(repo, token=token)
    if info.private is not True or not info.sha:
        raise RuntimeError("BLOCKED: dedicated dataset is missing or not verifiably private")
    baseline = set(api.list_repo_files(repo_id=repo, repo_type="dataset",
                                       revision=info.sha, token=token))
    if not baseline.issubset(ALLOWED_BASELINE_FILES):
        raise RuntimeError("BLOCKED: private test dataset contains existing data. "
                           "Use an empty pre-created dataset; no files were changed.")

    catalogue, fixtures = create_fixture()
    # Allow removal of both old and migrated fixture files, but NOTHING else.
    planned_moves = plan_migration(catalogue["books"], set(fixtures))
    owned_paths = set(fixtures) | {new for row in planned_moves
                                  for _, new in row["moves"]}
    # A failed request can leave an ambiguous commit outcome. Never silently
    # delete files from a revision we cannot prove this run created.
    seed_attempted = False
    last_owned_sha: str | None = None
    try:
        current_sha = info.sha
        seed_attempted = True
        result = api.create_commit(
            repo_id=repo, repo_type="dataset", token=token,
            parent_commit=current_sha, commit_message="Seed synthetic mixed-format library",
            # Bytes (rather than io.BytesIO) let huggingface_hub negotiate
            # Xet transfer; the HTTP fallback for buffered objects can fail
            # on datasets configured for Xet-backed file storage.
            operations=[CommitOperationAdd(path_in_repo=path,
                                           path_or_fileobj=data)
                        for path, data in fixtures.items()],
        )
        current_sha = result.oid
        last_owned_sha = current_sha
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
        for ident in (BOOK_ID, THIRD_ID, FOURTH_ID):
            assert by_id[ident]["status"] == "MIGRATE"
        assert by_id[OTHER_ID]["status"] == "ALREADY_READABLE"
        assert len(by_id[BOOK_ID]["moves"]) == 4
        assert len(by_id[THIRD_ID]["moves"]) == 4
        assert len(by_id[FOURTH_ID]["moves"]) == 3
        planned_legacy = [by_id[ident] for ident in (BOOK_ID, THIRD_ID, FOURTH_ID)]
        groups = group_migration_batches(planned_legacy, max_books=2, max_operations=30)
        assert len(groups) == 2 and [len(group) for group in groups] == [2, 1]
        assert not any(dest in files_before for item in planned_legacy
                       for _, dest in item["moves"])
        print("PASS synthetic private dataset: mixed legacy/readable novels, three "
              "migration targets, original archives, covers and personal sidecars.")

        # Fail-closed collision preflight: a pre-existing file under a proposed
        # readable destination cannot be silently overwritten or ignored.
        occupied = set(files_before) | {
            readable_dir(FOURTH_ID, catalogue["books"][3]["metadata"]["title"]) + "/unexpected"
        }
        assert next(row for row in plan_migration(remotely_loaded["books"], occupied)
                    if row["id"] == FOURTH_ID)["status"] == "CONFLICT"

        # Batch 1 exercises TWO distinct legacy novels inside one HF commit.
        first_sha = apply_migration_batch(api, repo, token, groups[0], current_sha)
        last_owned_sha = first_sha
        midway = api.dataset_info(repo, token=token)
        assert midway.private is True and midway.sha == first_sha
        files_mid = set(api.list_repo_files(
            repo_id=repo, repo_type="dataset", revision=first_sha, token=token))
        mid_catalogue = json.loads(download(api, repo, token, "data/library.json", first_sha))
        mid_plan = {row["id"]: row
                    for row in plan_migration(mid_catalogue["books"], files_mid)}
        assert all(mid_plan[ident]["status"] == "ALREADY_READABLE"
                   for ident in (BOOK_ID, THIRD_ID, OTHER_ID))
        assert mid_plan[FOURTH_ID]["status"] == "MIGRATE"
        assert files_mid.isdisjoint({old for group in groups[:1] for item in group
                                     for old, _ in item["moves"]})
        assert all(dst in files_mid for item in groups[0] for _, dst in item["moves"])
        # Replaying the old preview cannot overwrite an already migrated book.
        try:
            apply_migration_batch(api, repo, token, groups[0], first_sha)
            raise AssertionError("Already completed batch unexpectedly recommitted")
        except MigrationError:
            pass
        assert api.dataset_info(repo, token=token).sha == first_sha
        print("PASS batch 1: two legacy novels migrated atomically; already-readable book "
              "unchanged; partial completion detected and re-preview is safe.")

        # Batch 2 is based on the newest parent revision, just like production.
        second_sha = apply_migration_batch(api, repo, token, groups[1], first_sha)
        last_owned_sha = second_sha
        latest = api.dataset_info(repo, token=token)
        assert latest.private is True and latest.sha == second_sha
        migrated_sha = second_sha
        files_after = set(api.list_repo_files(
            repo_id=repo, repo_type="dataset", revision=migrated_sha, token=token))
        expected = dict(fixtures)
        for item in planned_legacy:
            for old_path, new_path in item["moves"]:
                expected[new_path] = expected.pop(old_path)
        expected["data/library.json"] = download(api, repo, token, "data/library.json", migrated_sha)
        assert set(expected) == files_after - baseline, "Unexpected post-migration file inventory"
        assert all(old not in files_after for item in planned_legacy for old, _ in item["moves"])
        assert all(new in files_after for item in planned_legacy for _, new in item["moves"])
        for path, value in expected.items():
            actual = download(api, repo, token, path, migrated_sha)
            assert sha256(actual) == sha256(value), "SHA-256 mismatch: " + path
        converted = json.loads(expected["data/library.json"])
        assert validate_catalogue(converted) == converted["books"]
        after = {entry["id"]: entry for entry in converted["books"]}
        assert set(after) == {BOOK_ID, OTHER_ID, THIRD_ID, FOURTH_ID}
        assert after[OTHER_ID] == catalogue["books"][1]
        for before in catalogue["books"]:
            ident = before["id"]
            updated = after[ident]
            assert updated["id"] == before["id"]
            assert updated["metadata"] == {
                **before["metadata"],
                **({"coverPath": book_dir(updated) + "/cover.png"}
                   if before["metadata"].get("coverPath") else {})
            }
        assert all(row["status"] == "ALREADY_READABLE"
                   for row in plan_migration(converted["books"], files_after))
        print("PASS two consecutive production-style HF migration batches: all files "
              "verified by SHA-256, stable IDs, personal metadata, progress, ratings, "
              "comments, tags and collections preserved.")

        # Reject an outdated batch's parent, independent of original seed SHA.
        try:
            apply_migration_batch(api, repo, token, groups[1], first_sha)
            raise AssertionError("Stale migration commit unexpectedly succeeded")
        except MigrationError:
            pass
        assert api.dataset_info(repo, token=token).sha == migrated_sha

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
            apply_migration_batch(api, DEFAULT_REPO, token, groups[0], migrated_sha)
            raise AssertionError("Production migration must always be rejected")
        except MigrationError:
            pass
        print("PASS production dataset migration guard")
        print("PASS real disposable private HF production-style multi-batch migration integration")
        return 0
    finally:
        if seed_attempted:
            cleanup_fixture(api, repo, token, baseline, owned_paths, last_owned_sha)


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print("FAIL disposable readable-folder acceptance: " +
              type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(1)
