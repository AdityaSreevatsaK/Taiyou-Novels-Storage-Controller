"""Offline tests for private Hugging Face reset safety."""
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
from io import StringIO
import contextlib

from taiyou_storage.reset import (
    EMPTY_CATALOGUE, ResetError, operations_for, perform_reset, run,
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

    def test_reset_preview_does_not_download_or_modify_remote_data(self):
        api = FakeAPI()
        with patch("huggingface_hub.HfApi", return_value=api), \
             patch("huggingface_hub.get_token", return_value="fake-token"), \
             patch("taiyou_storage.reset.backup_data") as backup, \
             contextlib.redirect_stdout(StringIO()):
            self.assertEqual(run([]), 0)
        backup.assert_not_called()
        self.assertFalse(api.commits)

    def test_reset_rejects_noninteractive_mode_before_backup(self):
        api = FakeAPI()
        with patch("huggingface_hub.HfApi", return_value=api), \
             patch("huggingface_hub.get_token", return_value="fake-token"), \
             patch("taiyou_storage.reset.backup_data") as backup, \
             patch("sys.stdin.isatty", return_value=False), \
             contextlib.redirect_stderr(StringIO()), \
             contextlib.redirect_stdout(StringIO()):
            self.assertEqual(run(["--apply"]), 1)
        backup.assert_not_called()
        self.assertFalse(api.commits)

    def test_wrong_dataset_confirmation_cannot_start_backup(self):
        api = FakeAPI()
        with patch("huggingface_hub.HfApi", return_value=api), \
             patch("huggingface_hub.get_token", return_value="fake-token"), \
             patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", return_value="WRONG DATASET"), \
             patch("taiyou_storage.reset.backup_data") as backup, \
             contextlib.redirect_stdout(StringIO()):
            self.assertEqual(run(["--apply"]), 2)
        backup.assert_not_called()
        self.assertFalse(api.commits)

    def test_wrong_final_phrase_preserves_verified_local_backup(self):
        api = FakeAPI()
        with TemporaryDirectory() as folder:
            source = Path(folder) / "backup"
            source.mkdir()
            with patch("huggingface_hub.HfApi", return_value=api), \
                 patch("huggingface_hub.get_token", return_value="fake-token"), \
                 patch("sys.stdin.isatty", return_value=True), \
                 patch("builtins.input", side_effect=[
                     "AdityaSreevatsaK/Taiyous-Novels", "NO, DO NOT ERASE"]), \
                 patch("taiyou_storage.reset.backup_data",
                       return_value=(source, {"count": len(api.paths),
                                              "files": [{"path": "synthetic"}]})), \
                 contextlib.redirect_stdout(StringIO()):
                self.assertEqual(run(["--apply"]), 2)
            self.assertTrue(source.exists())
        self.assertFalse(api.commits)

    def test_commit_revision_guarded(self):
        api = FakeAPI()
        perform_reset(api, "owner/repo", "token", api.revision, sorted(api.paths))
        self.assertEqual(len(api.commits), 1)
        self.assertEqual(api.commits[0]["parent_commit"], api.revision)
        self.assertEqual(api.commits[0]["repo_type"], "dataset")


if __name__ == "__main__":
    unittest.main()
