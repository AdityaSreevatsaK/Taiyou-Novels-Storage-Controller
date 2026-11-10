"""Offline tests for private Hugging Face reset safety."""
import unittest
from unittest.mock import patch

from taiyou_storage.reset import (
    EMPTY_CATALOGUE, ResetError, operations_for, perform_reset,
    select_data_files,
)


class FakeAPI:
    def __init__(self, *, private=True, revision="1" * 40, paths=None):
        self.private = private
        self.revision = revision
        self.paths = paths if paths is not None else [
            "data/library.json",
            "data/novels/" + "a"*24 + "/original.zip",
        ]
        self.commits = []

    def dataset_info(self, repo, token):
        return type("Info", (), {"private": self.private, "sha": self.revision})()

    def list_repo_files(self, repo_id, repo_type, revision, token):
        return list(self.paths)

    def create_commit(self, **kwargs):
        self.commits.append(kwargs)


class ResetTests(unittest.TestCase):
    def test_only_data_files_are_selected(self):
        paths = [".gitattributes", "README.md", "data/library.json",
                 "data/novels/" + "a"*24 + "/original.zip",
                 "data/personal/reviews/" + "b"*24 + ".json"]
        self.assertEqual(len(select_data_files(paths)), 3)
        self.assertNotIn(".gitattributes", select_data_files(paths))

    def test_unsafe_paths_blocked(self):
        for path in ("data/../README.md", "data/novels/../notes.json",
                     "data/novels\\bad.zip", "data//broken.txt"):
            with self.subTest(path=path):
                with self.assertRaises(ResetError):
                    select_data_files([path])

    def test_duplicate_paths_blocked(self):
        with self.assertRaises(ResetError):
            select_data_files(["data/library.json", "data/library.json"])

    def test_very_large_reset_blocked(self):
        with self.assertRaises(ResetError):
            select_data_files(["data/n/" + str(n) for n in range(5001)])

    def test_operations_keep_empty_library(self):
        path = "data/novels/" + "a"*24 + "/source.epub"
        ops = operations_for(["data/library.json", path])
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0].path_in_repo, path)
        self.assertEqual(ops[-1].path_in_repo, "data/library.json")
        self.assertEqual(EMPTY_CATALOGUE, {"version": 1, "books": []})

    def test_concurrent_revision_change_aborts_without_commit(self):
        api = FakeAPI(revision="2" * 40)
        with self.assertRaisesRegex(ResetError, "changed during backup"):
            perform_reset(api, "owner/repo", "token", "1" * 40, sorted(api.paths))
        self.assertFalse(api.commits)

    def test_changed_paths_abort_without_commit(self):
        api = FakeAPI()
        with self.assertRaisesRegex(ResetError, "Data paths changed"):
            perform_reset(api, "owner/repo", "token", api.revision, ["data/library.json"])
        self.assertFalse(api.commits)

    def test_public_repo_refused(self):
        api = FakeAPI(private=False)
        with self.assertRaisesRegex(ResetError, "PRIVATE"):
            perform_reset(api, "owner/repo", "token", api.revision, sorted(api.paths))
        self.assertFalse(api.commits)

    def test_commit_revision_guarded(self):
        api = FakeAPI()
        perform_reset(api, "owner/repo", "token", api.revision, sorted(api.paths))
        self.assertEqual(len(api.commits), 1)
        self.assertEqual(api.commits[0]["parent_commit"], api.revision)
        self.assertEqual(api.commits[0]["repo_type"], "dataset")


if __name__ == "__main__":
    unittest.main()
