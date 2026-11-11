"""Offline security and correctness tests for public-repo HF maintenance actions."""
import unittest
from unittest.mock import patch

from taiyou_storage.actions import (
    ActionError, inspect, safe_paths, validate_repo, main,
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

    def test_unsafe_clear_subcommand_is_not_available(self):
        # Never provide a CI command that can clear data without a verified backup.
        with self.assertRaises(SystemExit) as ctx:
            main(["clear", "--yes"])
        self.assertNotEqual(ctx.exception.code, 0)
        import taiyou_storage.actions as actions
        self.assertFalse(hasattr(actions, "clear_data"))

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
