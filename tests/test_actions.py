"""Offline security and correctness tests for public-repo HF maintenance actions."""
import unittest
from unittest.mock import patch

from taiyou_storage.actions import (
    ActionError, destructive, inspect, safe_paths, validate_repo, verify_gate,
)


class FakeAPI:
    def __init__(self):
        self.sha = "a" * 40
        self.paths = [
            ".gitattributes",
            "data/library.json",
            "data/novels/" + "1" * 24 + "/source.epub",
            "data/novels/" + "1" * 24 + "/original.zip",
        ]
        self.commits = []
        self.deletes = []

    def dataset_info(self, repo, token):
        return type("Info", (), {"private": True, "sha": self.sha})()

    def list_repo_files(self, repo_id, repo_type, revision, token):
        return list(self.paths)

    def create_commit(self, **kwargs):
        self.commits.append(kwargs)

    def delete_repo(self, **kwargs):
        self.deletes.append(kwargs)


class ActionSafetyTests(unittest.TestCase):
    def test_bad_backup_repo_blocked(self):
        for candidate in ("", "not-a-repo", "otherowner/backup",
                          "AdityaSreevatsaK/Taiyous-Novels"):
            with self.subTest(repo=candidate), self.assertRaises(ActionError):
                validate_repo(candidate)

    def test_path_traversal_blocked(self):
        for candidate in ("data/../secrets", "/data/book.zip",
                          "data//missing", "data/a\\b", "data/C:bad"):
            with self.subTest(path=candidate), self.assertRaises(ActionError):
                safe_paths([candidate])

    def test_duplicate_path_blocked(self):
        with self.assertRaises(ActionError):
            safe_paths(["data/library.json", "data/library.json"])

    def test_checkbox_requires_real_true(self):
        verify_gate("clear", True)
        verify_gate("delete-repository", True)
        for value in (False, None, "true", 1):
            with self.subTest(value=value), self.assertRaises(ActionError):
                verify_gate("clear", value)
        with self.assertRaises(ActionError):
            verify_gate("other", True)

    def test_no_checkbox_no_mutation(self):
        api = FakeAPI()
        for mode in ("clear", "delete-repository"):
            with self.assertRaises(ActionError):
                destructive(api, mode, "token", False)
        self.assertFalse(api.commits)
        self.assertFalse(api.deletes)

    def test_clear_without_backup(self):
        api = FakeAPI()
        with patch("taiyou_storage.actions.copy_to_private_backup") as backup:
            destructive(api, "clear", "token", True)
            backup.assert_not_called()
        self.assertEqual(api.commits[0]["parent_commit"], api.sha)
        self.assertFalse(api.deletes)
        names = [op.path_in_repo for op in api.commits[0]["operations"]]
        self.assertIn("data/library.json", names)
        self.assertNotIn(".gitattributes", names)

    def test_delete_repo_without_backup(self):
        api = FakeAPI()
        with patch("taiyou_storage.actions.copy_to_private_backup") as backup:
            destructive(api, "delete-repository", "token", True)
            backup.assert_not_called()
        self.assertEqual(len(api.deletes), 1)
        self.assertEqual(api.deletes[0]["repo_id"], "AdityaSreevatsaK/Taiyous-Novels")
        self.assertFalse(api.commits)

    def test_revision_race_prevents_clear(self):
        api = FakeAPI()
        original = api.dataset_info
        calls = 0
        def changed(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls >= 2:
                api.sha = "b" * 40
            return original(*args, **kwargs)
        with patch.object(api, "dataset_info", side_effect=changed):
            with self.assertRaisesRegex(ActionError, "changed during pre-delete"):
                destructive(api, "clear", "token", True)
        self.assertFalse(api.commits)

    def test_revision_race_prevents_dataset_delete(self):
        api = FakeAPI()
        original = api.dataset_info
        calls = 0
        def changed(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls >= 3:
                api.sha = "b" * 40
            return original(*args, **kwargs)
        with patch.object(api, "dataset_info", side_effect=changed):
            with self.assertRaisesRegex(ActionError, "changed before repository deletion"):
                destructive(api, "delete-repository", "token", True)
        self.assertFalse(api.deletes)

    def test_inspect_counts_only(self):
        api = FakeAPI()
        bookid = "1" * 24
        books = [
            {"id": bookid, "epubPath": f"data/novels/{bookid}/source.epub",
             "archivePath": f"data/novels/{bookid}/original.zip",
             "metadata": {"id": bookid, "title": "Private novel"}},
        ]
        with patch("taiyou_storage.actions.load_catalogue",
                   return_value=(books, b"{}")):
            revision, result = inspect(api, "token")
        self.assertEqual(revision, "a" * 40)
        self.assertEqual(result["catalogue_books"], 1)
        self.assertEqual(result["missing_epubs"], 0)
        self.assertNotIn("Private novel", str(result))

    def test_inspect_emits_revision_when_catalogue_corrupt(self):
        api = FakeAPI()
        with patch("taiyou_storage.actions.load_catalogue",
                   side_effect=ValueError("malformed source")):
            revision, result = inspect(api, "token")
        self.assertEqual(revision, api.sha)
        self.assertFalse(result["catalogue_valid"])
        self.assertEqual(result["data_files"], 3)
        self.assertNotIn("malformed source", str(result))


if __name__ == "__main__":
    unittest.main()
