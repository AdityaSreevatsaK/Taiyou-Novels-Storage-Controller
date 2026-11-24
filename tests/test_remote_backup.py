"""Offline remote-first private backup tests. No Hugging Face credentials."""
from __future__ import annotations

from hashlib import sha1, sha256
import json
from types import SimpleNamespace
import unittest

from taiyou_storage.actions import ActionError
from taiyou_storage.core import DEFAULT_REPO
from taiyou_storage.remote_backup import RemoteIdentity, _identity_match, remote_backup, preview_remote_backup

BACKUP = "AdityaSreevatsaK/Taiyous-Novels-Backup"


def git_blob(data: bytes) -> str:
    return sha1(f"blob {len(data)}".encode() + bytes([0]) + data).hexdigest()


class FakeHub:
    def __init__(self):
        self.token = "test-token"
        self.source_rev = "a" * 40
        self.backup_rev = "b" * 40
        self.counter = 20
        self.source = {
            ".gitattributes": b"xet default",
            "data/library.json": json.dumps({"version": 1, "books": []}).encode(),
            "data/novels/aaaaaaaaaaaaaaaaaaaaaaaa/source.epub": b"synthetic book" * 256,
            "data/novels/aaaaaaaaaaaaaaaaaaaaaaaa/original.zip": b"synthetic ZIP" * 128,
        }
        self.backup = {}
        self.snapshots = {
            (DEFAULT_REPO, self.source_rev): self.source.copy(),
            (BACKUP, self.backup_rev): self.backup.copy()
        }
        self.commits = []
        self.fail_at = None
        self.change_source_on_commit = False
        self.xet_missing = False

    def dataset_info(self, repo, token):
        assert token == self.token
        if repo == DEFAULT_REPO:
            return SimpleNamespace(private=True, sha=self.source_rev)
        assert repo == BACKUP
        return SimpleNamespace(private=True, sha=self.backup_rev)

    def list_repo_tree(self, *, repo_id, repo_type, revision, recursive, expand, token):
        assert repo_type == "dataset" and recursive and expand and token == self.token
        for path, content in self.snapshots[(repo_id, revision)].items():
            # Simulate Xet/LFS for binary blobs and Git metadata for text.
            is_binary = path.endswith((".epub", ".zip"))
            yield SimpleNamespace(
                path=path, size=len(content), blob_id=git_blob(content),
                lfs={"sha256": sha256(content).hexdigest()} if is_binary else None,
                xet_hash=(None if self.xet_missing or not is_binary
                          else sha256(b'xet:' + content).hexdigest()))

    def create_commit(self, *, repo_id, repo_type, token, parent_commit,
                      operations, commit_message):
        assert repo_id == BACKUP and repo_type == "dataset"
        assert token == self.token and parent_commit == self.backup_rev
        if self.fail_at is not None and len(self.commits) + 1 == self.fail_at:
            raise ConnectionError("Synthetic interruption before commit")
        next_files = self.backup.copy()
        for operation in operations:
            if type(operation).__name__ == "CommitOperationCopy":
                assert operation.src_repo_id == DEFAULT_REPO
                assert operation.src_revision in {
                    "a" * 40, self.source_rev}
                next_files[operation.path_in_repo] = self.snapshots[
                    (operation.src_repo_id, operation.src_revision)
                ][operation.src_path_in_repo]
            else:
                next_files[operation.path_in_repo] = operation.path_or_fileobj.getvalue()
        self.counter += 1
        self.backup_rev = f"{self.counter:040x}"
        self.backup = next_files
        self.snapshots[(BACKUP, self.backup_rev)] = next_files.copy()
        self.commits.append([op.path_in_repo for op in operations])
        if self.change_source_on_commit:
            self.source_rev = "c" * 40
            self.snapshots[(DEFAULT_REPO, self.source_rev)] = dict(self.source)
        return SimpleNamespace(oid=self.backup_rev)


class RemoteBackupTests(unittest.TestCase):
    def test_remote_copy_verifies_every_object_without_downloading(self):
        hub = FakeHub()
        summary = remote_backup(hub, BACKUP, hub.token, batch_size=2)
        self.assertEqual(summary["Source files"], 4)
        self.assertEqual(summary["Objects copied"], 4)
        self.assertEqual(summary["Full novel downloads"], 0)
        self.assertEqual(summary["Snapshot verified"], 1)
        self.assertEqual(len(hub.commits), 3)
        self.assertIn(f"snapshots/{'a' * 40}/verification.json", hub.backup)
        self.assertEqual(len(hub.backup), 5)
        repeated = remote_backup(hub, BACKUP, hub.token, batch_size=2)
        self.assertEqual(repeated["Objects copied"], 0)
        self.assertEqual(repeated["Previously verified objects reused"], 4)
        self.assertEqual(len(hub.commits), 3)

    def test_partial_failure_is_resumeable_with_immutable_source_revision(self):
        hub = FakeHub()
        hub.fail_at = 2
        with self.assertRaises(ConnectionError):
            remote_backup(hub, BACKUP, hub.token, batch_size=2)
        self.assertEqual(len(hub.commits), 1)
        self.assertNotIn(f"snapshots/{'a' * 40}/verification.json", hub.backup)
        hub.fail_at = None
        result = remote_backup(hub, BACKUP, hub.token, batch_size=2)
        self.assertEqual(result["Objects copied"], 2)
        self.assertEqual(result["Previously verified objects reused"], 2)
        self.assertEqual(result["Snapshot verified"], 1)

    def test_uncopyable_lfs_without_xet_fails_before_any_remote_commit(self):
        hub = FakeHub()
        hub.xet_missing = True
        with self.assertRaisesRegex(ActionError, "without Xet"):
            preview_remote_backup(hub, BACKUP, hub.token)
        with self.assertRaisesRegex(ActionError, "without Xet"):
            remote_backup(hub, BACKUP, hub.token, batch_size=2)
        self.assertEqual(hub.commits, [])

    def test_regular_git_files_do_not_need_xet(self):
        hub = FakeHub()
        listing = {item.path: item for item in hub.list_repo_tree(
            repo_id=DEFAULT_REPO, repo_type="dataset",
            revision=hub.source_rev, recursive=True, expand=True, token=hub.token)}
        self.assertIsNone(listing["data/library.json"].lfs)
        self.assertIsNone(listing["data/library.json"].xet_hash)
        result = preview_remote_backup(hub, BACKUP, hub.token)
        self.assertEqual(result["Source files"], 4)

    def test_same_size_but_different_bytes_fail_closed(self):
        hub = FakeHub()
        name = f"snapshots/{'a' * 40}/files/data/library.json"
        hub.backup[name] = b"Z" * len(hub.source["data/library.json"])
        hub.snapshots[(BACKUP, hub.backup_rev)] = hub.backup.copy()
        with self.assertRaisesRegex(ActionError, "conflicting remote object"):
            remote_backup(hub, BACKUP, hub.token)
        self.assertEqual(hub.commits, [])

    def test_source_changes_prevent_false_certification(self):
        hub = FakeHub()
        hub.change_source_on_commit = True
        with self.assertRaisesRegex(ActionError, "Source changed"):
            remote_backup(hub, BACKUP, hub.token, batch_size=2)
        self.assertFalse(any("verification.json" in paths for paths in hub.commits))

    def test_unknown_object_identity_refuses_size_only(self):
        a = RemoteIdentity(size=100, sha256="")
        b = RemoteIdentity(size=100, blob_id="")
        self.assertFalse(_identity_match(a, b))
        self.assertFalse(_identity_match(RemoteIdentity(100, blob_id="a"*40),
                                         RemoteIdentity(100, blob_id="b"*40)))
        self.assertTrue(_identity_match(RemoteIdentity(100, blob_id="a"*40),
                                        RemoteIdentity(100, blob_id="a"*40)))

    def test_cli_defaults_to_remote_mode_and_does_not_expose_paths(self):
        from taiyou_storage.actions import main
        from unittest.mock import patch
        from contextlib import redirect_stdout
        from io import StringIO
        with (patch("huggingface_hub.HfApi", return_value=FakeHub()),
              patch.dict("os.environ", {"HF_TOKEN": "test-token"})):
            buffer = StringIO()
            with redirect_stdout(buffer):
                code = main(["backup", "--backup-repo", BACKUP])
        self.assertEqual(code, 0)
        self.assertRegex(buffer.getvalue(), r"Snapshot verified[ ]+: 1")
        self.assertNotIn("data/novels/", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
