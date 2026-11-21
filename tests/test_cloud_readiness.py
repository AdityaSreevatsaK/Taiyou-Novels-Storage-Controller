"""Read-only cloud readiness and GitHub workflow safety tests."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from taiyou_storage.actions import ActionError
from taiyou_storage.cloud_readiness import run
from taiyou_storage.remote_backup import preview_remote_backup, remote_backup
from tests.test_remote_backup import BACKUP, FakeHub

ROOT = Path(__file__).resolve().parents[1]


class CloudReadinessTests(unittest.TestCase):
    def test_metadata_preflight_does_not_copy_or_download(self):
        fake = FakeHub()
        result = preview_remote_backup(fake, BACKUP, fake.token)
        self.assertEqual(result["Source files"], 4)
        self.assertEqual(result["Objects eligible for remote copy"], 4)
        self.assertEqual(result["Full novel downloads"], 0)
        self.assertEqual(fake.commits, [])

    def test_after_backup_preflight_skips_verified_objects(self):
        fake = FakeHub()
        remote_backup(fake, BACKUP, fake.token, batch_size=2)
        n = len(fake.commits)
        result = preview_remote_backup(fake, BACKUP, fake.token)
        self.assertEqual(result["Objects eligible for remote copy"], 0)
        self.assertEqual(result["Objects already verified"], 4)
        self.assertEqual(len(fake.commits), n)

    def test_conflicting_existing_backup_blocks_preflight(self):
        fake = FakeHub()
        dest = "snapshots/" + fake.source_rev + "/files/data/library.json"
        fake.backup[dest] = b"X" * len(fake.source["data/library.json"])
        fake.snapshots[(BACKUP, fake.backup_rev)] = fake.backup.copy()
        with self.assertRaisesRegex(ActionError, "divergent"):
            preview_remote_backup(fake, BACKUP, fake.token)
        self.assertFalse(fake.commits)

    def test_invalid_backup_repo_fails_closed(self):
        fake = FakeHub()
        with self.assertRaises(ActionError):
            preview_remote_backup(fake, "untrusted-owner/potentially-public", fake.token)

    def test_missing_token_returns_error_without_api_access(self):
        with patch.dict(os.environ, {"HF_TOKEN": ""}):
            stderr = StringIO()
            with redirect_stderr(stderr):
                code = run([], api=FakeHub())
        self.assertEqual(code, 2)
        self.assertNotIn("data/novels", stderr.getvalue())

    def test_counts_only_output(self):
        fake = FakeHub()
        stdout = StringIO()
        with patch.dict(os.environ, {"HF_TOKEN": fake.token}):
            with redirect_stdout(stdout):
                code = run([], api=fake)
        self.assertEqual(code, 0)
        self.assertIn("Objects eligible for remote copy: 4", stdout.getvalue())
        self.assertNotIn("data/novels", stdout.getvalue())
        self.assertEqual(fake.commits, [])

    def test_workflow_never_writes_or_publishes_private_files(self):
        workflow = (ROOT / ".github/workflows/hf-live-readiness.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("branches: [master]", workflow)
        self.assertIn("refs/heads/master", workflow)
        self.assertIn("HF_STORAGE_CONTROLLER_TOKEN", workflow)
        self.assertIn("taiyou_storage.cloud_readiness", workflow)
        self.assertIn("taiyou_storage.github_checks --mode quick", workflow)
        self.assertNotIn("actions/upload-artifact", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn(" --apply", workflow)
        self.assertNotIn("taiyou_storage.reset", workflow)


if __name__ == "__main__":
    unittest.main()
