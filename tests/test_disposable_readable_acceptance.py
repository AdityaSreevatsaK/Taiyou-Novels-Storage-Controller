"""Offline safety checks for the live disposable readable-folder acceptance runner.

No Hugging Face service is contacted. The real test remains credential-gated.
"""
from __future__ import annotations

import io
import json
import os
import unittest
import zipfile
from unittest.mock import patch
from types import SimpleNamespace

from scripts.verify_disposable_folder_migration import (
    BOOK_ID, OTHER_ID, TEST_REPO, cleanup_fixture, create_fixture,
    run, validate_test_repo,
)
from taiyou_storage.core import validate_catalogue
from taiyou_storage.migrate_folders import plan_migration
from taiyou_storage.paths import book_dir, legacy_dir


class DisposableRunnerOfflineTests(unittest.TestCase):
    def test_fixture_uses_only_fictional_books_and_valid_archives(self):
        catalogue, data = create_fixture()
        self.assertEqual(validate_catalogue(catalogue), catalogue["books"])
        self.assertEqual({book["id"] for book in catalogue["books"]}, {BOOK_ID, OTHER_ID})
        self.assertEqual(len(data), 10)
        for book in catalogue["books"]:
            self.assertEqual(book["metadata"]["author"], "Fictional Author")
            self.assertIn(book["epubPath"], data)
            with zipfile.ZipFile(io.BytesIO(data[book["epubPath"]])) as epub:
                self.assertEqual(epub.read("mimetype"), b"application/epub+zip")
                self.assertIn("OEBPS/chapter1.xhtml", epub.namelist())
            cover_path = book["metadata"]["coverPath"]
            self.assertTrue(data[cover_path].startswith(b"\x89PNG\r\n\x1a\n"))
        first = catalogue["books"][0]
        with zipfile.ZipFile(io.BytesIO(data[first["archivePath"]])) as archive:
            self.assertEqual(archive.read("source.epub"), data[first["epubPath"]])
        self.assertIn("data/personal/progress/" + BOOK_ID + ".json", data)
        self.assertIn("data/personal/reviews/" + BOOK_ID + ".json", data)
        self.assertIn("data/personal/collections.json", data)
        self.assertEqual(json.loads(data["data/personal/progress/" + BOOK_ID + ".json"])["progress"], 73)

    def test_only_legacy_book_is_planned_for_migration(self):
        catalogue, data = create_fixture()
        items = {item["id"]: item for item in plan_migration(catalogue["books"], set(data))}
        self.assertEqual(items[BOOK_ID]["status"], "MIGRATE")
        self.assertEqual(items[OTHER_ID]["status"], "ALREADY_READABLE")
        old = legacy_dir(BOOK_ID)
        moves = items[BOOK_ID]["moves"]
        self.assertEqual(len(moves), 4)
        self.assertTrue(all(src.startswith(old + "/") for src, _ in moves))
        self.assertTrue(all(dst.startswith(items[BOOK_ID]["new"] + "/") for _, dst in moves))
        self.assertNotEqual(book_dir(catalogue["books"][1]), legacy_dir(OTHER_ID))
        self.assertNotIn("data/library.json", [src for src, _ in moves])

    def test_only_single_precreated_dataset_is_ever_permitted(self):
        self.assertEqual(validate_test_repo(TEST_REPO), TEST_REPO)
        for repo in (
            "AdityaSreevatsaK/Taiyous-Novels",
            "AdityaSreevatsaK/Taiyou-Readable-Folder-Test-Extra",
            "OtherAccount/Taiyou-Readable-Folder-Test",
            "",
        ):
            with self.subTest(repo=repo), self.assertRaisesRegex(RuntimeError, "BLOCKED"):
                validate_test_repo(repo)
        with patch.dict(os.environ, {
            "HF_DISPOSABLE_TEST_TOKEN": "hf_fake_only_for_mock_tests",
            "HF_DISPOSABLE_TEST_REPO": "AdityaSreevatsaK/Taiyous-Novels",
        }):
            with patch("scripts.verify_disposable_folder_migration.HfApi") as hub:
                with self.assertRaisesRegex(RuntimeError, "BLOCKED"):
                    run()
                hub.assert_not_called()

    def test_nonempty_private_test_dataset_fails_before_any_write(self):
        with patch.dict(os.environ, {
            "HF_DISPOSABLE_TEST_TOKEN": "hf_mocked_test_only",
            "HF_DISPOSABLE_TEST_REPO": TEST_REPO,
        }):
            with patch("scripts.verify_disposable_folder_migration.HfApi") as factory:
                hub = factory.return_value
                hub.dataset_info.return_value = SimpleNamespace(private=True, sha="f" * 40)
                hub.list_repo_files.return_value = [
                    "README.md", "data/novels/do-not-touch/source.epub",
                ]
                with self.assertRaisesRegex(RuntimeError, "existing data"):
                    run()
                hub.create_commit.assert_not_called()
                hub.create_repo.assert_not_called()
                hub.delete_repo.assert_not_called()

    def test_cleanup_removes_only_owned_files_and_preserves_readme(self):
        class FakePrivateHub:
            def __init__(self):
                self.files = {".gitattributes", "README.md", "data/library.json",
                              "data/novels/" + BOOK_ID + "/source.epub"}
                self.sha = "f" * 40
                self.commits = []

            def dataset_info(self, repo, token=None):
                self._assert_repo(repo)
                return SimpleNamespace(private=True, sha=self.sha)

            def list_repo_files(self, repo_id, repo_type, revision, token=None):
                self._assert_repo(repo_id)
                assert repo_type == "dataset" and revision == self.sha
                return sorted(self.files)

            def create_commit(self, **kwargs):
                self._assert_repo(kwargs["repo_id"])
                assert kwargs["parent_commit"] == self.sha
                paths = [item.path_in_repo for item in kwargs["operations"]]
                self.commits.append(paths)
                assert all(type(item).__name__ == "CommitOperationDelete"
                           for item in kwargs["operations"])
                self.files.difference_update(paths)
                self.sha = "e" * 40
                return SimpleNamespace(oid=self.sha)

            @staticmethod
            def _assert_repo(repo):
                assert repo == TEST_REPO

        hub = FakePrivateHub()
        baseline = {"README.md", ".gitattributes"}
        owned = {"data/library.json", "data/novels/" + BOOK_ID + "/source.epub"}
        cleanup_fixture(hub, TEST_REPO, "fake-token", baseline, owned, "f" * 40)
        self.assertEqual(hub.files, baseline)
        self.assertEqual(len(hub.commits), 1)
        self.assertEqual(set(hub.commits[0]), owned)

    def test_cleanup_refuses_unknown_files_and_changed_revisions(self):
        class ProbeHub:
            def __init__(self, sha="f" * 40, extra=False):
                self.sha = sha
                self.files = ["README.md", "data/library.json"] + (
                    ["data/other-user/file"] if extra else []
                )
                self.writes = []

            def dataset_info(self, repo, token=None):
                return SimpleNamespace(private=True, sha=self.sha)

            def list_repo_files(self, repo_id, repo_type, revision, token=None):
                return list(self.files)

            def create_commit(self, **kwargs):
                self.writes.append(kwargs)

        baseline = {"README.md"}
        owned = {"data/library.json"}
        for hub, expected in [
            (ProbeHub(extra=True), "not owned"),
            (ProbeHub(sha="e" * 40), "revision changed"),
        ]:
            with self.subTest(reason=expected), self.assertRaisesRegex(RuntimeError, expected):
                cleanup_fixture(hub, TEST_REPO, "fake-token", baseline, owned, "f" * 40)
            self.assertEqual(hub.writes, [])

    def test_missing_dedicated_token_aborts_before_any_remote_operation(self):
        with patch.dict(os.environ, {"HF_DISPOSABLE_TEST_TOKEN": ""}):
            with patch("scripts.verify_disposable_folder_migration.HfApi") as hub:
                with self.assertRaisesRegex(RuntimeError, "BLOCKED"):
                    run()
                hub.assert_not_called()


if __name__ == "__main__":
    unittest.main()
