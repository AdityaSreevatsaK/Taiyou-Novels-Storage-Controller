"""Readable-folder compatibility and reversible-by-history test migration.

All fixtures use synthetic novels and a simulated private Hub. No external
service or production dataset is contacted.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from taiyou_storage.core import StorageError, validate_catalogue
from taiyou_storage.covers import Cover, make_plan
from taiyou_storage.migrate_folders import MigrationError, apply_one, plan_migration
from taiyou_storage.paths import (
    book_dir, folder_from_epub_path, legacy_dir, readable_dir, readable_label)
from taiyou_storage.upload import apply_item, plan


BOOK_ID = "a" * 24
TEST_REPO = "test-user/disposable-private-library"


def entry(title="The Martial World: Eternal Road", *, readable=False, cover=False):
    folder = readable_dir(BOOK_ID, title) if readable else legacy_dir(BOOK_ID)
    meta = {
        "id": BOOK_ID, "title": title, "author": "Synthetic Author",
        "personalTags": ["On Hold"], "personalRating": 5,
        "progress": 73, "comments": "Keep my reader notes",
    }
    if cover:
        meta["coverPath"] = folder + "/cover.png"
    return {
        "id": BOOK_ID, "metadata": meta,
        "epubPath": folder + "/source.epub",
        "archivePath": folder + "/original.zip",
    }


class CopyAwareFakeHub:
    def __init__(self, root: Path, book: dict):
        self.root = root
        self.sha = "f" * 40
        folder = book_dir(book)
        self.files = {
            "data/library.json": json.dumps({"version": 1, "books": [book]}).encode(),
            folder + "/source.epub": b"synthetic EPUB",
            folder + "/original.zip": b"synthetic archive",
            folder + "/cover.png": b"synthetic PNG",
            folder + "/extra.txt": b"preserve this extra file",
        }
        self.commits = []

    def dataset_info(self, repo, token=None):
        assert repo == TEST_REPO
        return SimpleNamespace(private=True, sha=self.sha)

    def list_repo_files(self, repo_id, repo_type, revision, token=None):
        assert repo_id == TEST_REPO and repo_type == "dataset"
        assert revision == self.sha
        return list(self.files)

    def download(self, repo_id, repo_type, filename, revision, token=None):
        assert repo_id == TEST_REPO and revision == self.sha
        file = self.root / "cache" / filename
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(self.files[filename])
        return str(file)

    def create_commit(self, **kwargs):
        assert kwargs["repo_id"] == TEST_REPO
        assert kwargs["parent_commit"] == self.sha
        next_files = dict(self.files)
        ops = kwargs["operations"]
        for operation in ops:
            kind = type(operation).__name__
            if kind == "CommitOperationCopy":
                next_files[operation.path_in_repo] = self.files[operation.src_path_in_repo]
            elif kind == "CommitOperationDelete":
                next_files.pop(operation.path_in_repo, None)
            else:
                data = operation.path_or_fileobj
                next_files[operation.path_in_repo] = (
                    data.getvalue() if hasattr(data, "getvalue") else
                    Path(data).read_bytes() if isinstance(data, (str, Path)) else data)
        self.files = next_files
        self.commits.append([type(o).__name__ for o in ops])
        self.sha = "e" * 40
        return SimpleNamespace(oid=self.sha)


class ReadablePathTests(unittest.TestCase):
    def test_readable_slug_and_id_do_not_depend_on_url_safety(self):
        folder = readable_dir(BOOK_ID, "Martial World: Part 1 / Onward? (Final)")
        self.assertEqual(folder, f"data/novels/{BOOK_ID} - Martial World Part 1 Onward (Final)")
        self.assertEqual(folder_from_epub_path(BOOK_ID, folder + "/source.epub"), folder)

    def test_unicode_and_long_titles_are_bounded(self):
        title = "修仙之路 " + "A" * 200 + "/..\\"
        slug = readable_label(title)
        self.assertTrue(slug.startswith("修仙之路"))
        self.assertLessEqual(len(slug), 96)
        self.assertNotIn("/", slug)
        self.assertNotIn("\\", slug)
        self.assertNotIn("..", slug)

    def test_reject_id_mismatch_or_traversal_in_all_layouts(self):
        book = entry()
        for path in [
            f"data/novels/{'b'*24}/source.epub",
            f"data/novels/{BOOK_ID} - ../source.epub",
            f"data/novels/{BOOK_ID} - Evil/../source.epub",
            f"data/novels/{BOOK_ID} - Evil/source.epub/other",
            f"data/novels/{BOOK_ID} - Evil/other.epub",
            f"data/novels/{BOOK_ID} - Stuff/../../source.epub",
        ]:
            with self.subTest(path=path), self.assertRaises(StorageError):
                validate_catalogue({"version": 1, "books": [{**book, "epubPath": path}]})

    def test_archive_and_cover_cannot_cross_folders(self):
        current = entry(readable=True, cover=True)
        wrong = legacy_dir(BOOK_ID)
        for changed in [
            {**current, "archivePath": wrong + "/original.zip"},
            {**current, "metadata": {**current["metadata"], "coverPath": wrong + "/cover.png"}},
        ]:
            with self.assertRaises(StorageError):
                validate_catalogue({"version": 1, "books": [changed]})

    def test_old_and_readable_catalogue_are_both_valid(self):
        for readable in (False, True):
            book = entry(readable=readable, cover=True)
            result = validate_catalogue({"version": 1, "books": [book]})
            self.assertEqual(result[0]["id"], BOOK_ID)

    def test_title_edit_does_not_rename_existing_folder(self):
        book = entry(readable=True)
        previous = book_dir(book)
        book["metadata"]["title"] = "A New Novel Title"
        self.assertEqual(book_dir(book), previous)
        validate_catalogue({"version": 1, "books": [book]})


class MigrationTests(unittest.TestCase):
    def test_preview_plan_moves_all_files_not_only_epub_and_zip(self):
        book = entry(cover=True)
        folder = book_dir(book)
        paths = {folder + "/" + f for f in ("source.epub", "original.zip", "cover.png", "extra.txt")}
        result = plan_migration([book], paths)
        self.assertEqual(result[0]["status"], "MIGRATE")
        self.assertEqual(len(result[0]["moves"]), 4)
        self.assertTrue(all(p.startswith(readable_dir(BOOK_ID, book["metadata"]["title"]))
                            for _, p in result[0]["moves"]))

    def test_conflicting_destination_and_missing_files_abort(self):
        book = entry(cover=True)
        folder = book_dir(book)
        only_epub = {folder + "/source.epub"}
        self.assertEqual(plan_migration([book], only_epub)[0]["status"], "CONFLICT")
        all_files = only_epub | {folder + "/original.zip", folder + "/cover.png"}
        destination = readable_dir(BOOK_ID, book["metadata"]["title"])
        self.assertEqual(
            plan_migration([book], all_files | {destination + "/cover.png"})[0]["status"],
            "CONFLICT")

    def test_renamed_already_readable_folder_is_not_renamed_again(self):
        book = entry(readable=True)
        book["metadata"]["title"] = "Another title"
        self.assertEqual(
            plan_migration([book], {book["epubPath"]})[0]["status"], "ALREADY_READABLE")

    def test_production_migration_is_impossible_even_via_python_api(self):
        with self.assertRaisesRegex(MigrationError, "Production"):
            apply_one(None, "AdityaSreevatsaK/Taiyous-Novels", "token",
                      {"id": BOOK_ID}, "f" * 40)

    def test_one_atomic_copy_delete_and_catalogue_rewrite_preserves_metadata(self):
        book = entry(cover=True)
        with TemporaryDirectory() as tmp:
            hub = CopyAwareFakeHub(Path(tmp), book)
            plan_item = plan_migration([book], set(hub.files))[0]
            originals = dict(hub.files)
            with patch("huggingface_hub.hf_hub_download", side_effect=hub.download):
                new_sha = apply_one(hub, TEST_REPO, "test-token", plan_item, hub.sha)
            self.assertEqual(new_sha, "e" * 40)
            self.assertEqual(len(hub.commits), 1)
            self.assertEqual(hub.commits[0].count("CommitOperationCopy"), 4)
            self.assertEqual(hub.commits[0].count("CommitOperationDelete"), 4)
            self.assertEqual(hub.commits[0].count("CommitOperationAdd"), 1)
            upgraded = json.loads(hub.files["data/library.json"])["books"][0]
            self.assertEqual(upgraded["id"], BOOK_ID)
            self.assertEqual(upgraded["metadata"]["progress"], 73)
            self.assertEqual(upgraded["metadata"]["personalTags"], ["On Hold"])
            self.assertEqual(upgraded["metadata"]["personalRating"], 5)
            self.assertEqual(upgraded["metadata"]["comments"], "Keep my reader notes")
            self.assertEqual(upgraded["metadata"]["coverPath"], book_dir(upgraded) + "/cover.png")
            for source, destination in plan_item["moves"]:
                self.assertNotIn(source, hub.files)
                self.assertEqual(hub.files[destination], originals[source])
            self.assertEqual(
                plan_migration([upgraded], set(hub.files))[0]["status"], "ALREADY_READABLE")

    def test_revision_drift_refuses_all_writes(self):
        book = entry()
        with TemporaryDirectory() as tmp:
            hub = CopyAwareFakeHub(Path(tmp), book)
            item = plan_migration([book], set(hub.files))[0]
            with self.assertRaisesRegex(MigrationError, "revision changed"):
                apply_one(hub, TEST_REPO, "token", item, "a" * 40)
            self.assertEqual(hub.commits, [])

    def test_uploaded_new_book_uses_opt_in_readable_path_and_stable_id(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "synthetic.zip"
            path.write_bytes(b"synthetic ZIP fixture")
            epub = b"synthetic EPUB"
            book_id = hashlib.sha256(epub).hexdigest()[:24]
            meta = {"title": "A Knight's Return", "author": "Synthetic Author"}
            local = [(path, meta, epub, hashlib.sha256(path.read_bytes()).hexdigest())]
            decisions = plan([], local, {}, set(), readable_new=True)
            self.assertEqual(decisions[0]["state"], "NEW")
            self.assertEqual(decisions[0]["directory"], readable_dir(book_id, meta["title"]))
            self.assertIn("A Knight's Return", decisions[0]["directory"])
            self.assertEqual(plan([], local, {}, set())[0]["directory"], legacy_dir(book_id))
            hub = CopyAwareFakeHub(root, entry())
            hub.files = {}
            with patch("huggingface_hub.hf_hub_download", side_effect=hub.download):
                status = apply_item(hub, TEST_REPO, "test-token", decisions[0])
            self.assertEqual(status, "NEW")
            created = json.loads(hub.files["data/library.json"])["books"][0]
            self.assertEqual(created["id"], book_id)
            self.assertEqual(book_dir(created), decisions[0]["directory"])

    def test_cover_plan_uses_readable_directory(self):
        book = entry(readable=True)
        image = b"synthetic image bytes"
        cover = Cover(book["metadata"]["title"], "NovelFull",
                      "https://example.org/fiction", "cover.png", ".png",
                      image, hashlib.sha256(image).hexdigest())
        plan_rows = make_plan([cover], [book], {}, set())
        self.assertEqual(plan_rows[0]["status"], "NEW")
        self.assertEqual(plan_rows[0]["destination"], book_dir(book) + "/cover.png")


if __name__ == "__main__":
    unittest.main()
