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

    def test_gate_requires_exact_revision_and_phrase(self):
        rev = "a" * 40
        verify_gate("clear", rev, rev,
                    "CLEAR DATA AdityaSreevatsaK/Taiyous-Novels")
        verify_gate("delete-repository", rev, rev,
                    "DELETE DATASET AdityaSreevatsaK/Taiyous-Novels")
        with self.assertRaises(ActionError):
            verify_gate("clear", rev, rev, "DELETE DATASET AdityaSreevatsaK/Taiyous-Novels")
        with self.assertRaises(ActionError):
            verify_gate("clear", rev, "b" * 40,
                        "CLEAR DATA AdityaSreevatsaK/Taiyous-Novels")
        with self.assertRaises(ActionError):
            verify_gate("delete-repository", rev, "bad",
                        "DELETE DATASET AdityaSreevatsaK/Taiyous-Novels")

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

    def test_backup_failure_never_deletes(self):
        api = FakeAPI()
        with patch("taiyou_storage.actions.copy_to_private_backup",
                   side_effect=ActionError("backup failed")):
            with self.assertRaises(ActionError):
                destructive(api, "clear", "AdityaSreevatsaK/Backup",
                            "token", api.sha,
                            "CLEAR DATA AdityaSreevatsaK/Taiyous-Novels")
        self.assertEqual(api.commits, [])
        self.assertEqual(api.deletes, [])

    def test_clear_only_after_backup_and_uses_commit_parent(self):
        api = FakeAPI()
        with patch("taiyou_storage.actions.copy_to_private_backup") as backup:
            destructive(api, "clear", "AdityaSreevatsaK/Backup",
                        "token", api.sha,
                        "CLEAR DATA AdityaSreevatsaK/Taiyous-Novels")
            backup.assert_called_once()
        self.assertEqual(len(api.commits), 1)
        self.assertEqual(api.commits[0]["parent_commit"], api.sha)
        self.assertEqual(api.deletes, [])

    def test_repo_delete_has_separate_confirmation(self):
        api = FakeAPI()
        with patch("taiyou_storage.actions.copy_to_private_backup"):
            destructive(api, "delete-repository", "AdityaSreevatsaK/Backup",
                        "token", api.sha,
                        "DELETE DATASET AdityaSreevatsaK/Taiyous-Novels")
        self.assertEqual(api.commits, [])
        self.assertEqual(len(api.deletes), 1)

    def test_concurrent_change_after_backup_aborts(self):
        api = FakeAPI()
        def move(*args):
            api.sha = "b" * 40
        with patch("taiyou_storage.actions.copy_to_private_backup",
                   side_effect=move):
            with self.assertRaisesRegex(ActionError, "changed during backup"):
                destructive(api, "delete-repository", "AdityaSreevatsaK/Backup",
                            "token", "a" * 40,
                            "DELETE DATASET AdityaSreevatsaK/Taiyous-Novels")
        self.assertEqual(api.deletes, [])


if __name__ == "__main__":
    unittest.main()
