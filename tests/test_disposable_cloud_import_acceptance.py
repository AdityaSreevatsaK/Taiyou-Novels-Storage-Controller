"""Security guards for real synthetic cloud-import acceptance."""
import os
import unittest
from unittest.mock import patch

from taiyou_storage.disposable_cloud_import_acceptance import (
    import_repo, main, run_acceptance,
)


class DisposableCloudImportTests(unittest.TestCase):
    def test_test_dataset_is_generated_from_trusted_run_context(self):
        repo = import_repo("45835247560", "1", "SafeOwner")
        self.assertEqual(repo, "SafeOwner/Taiyou-Import-Acceptance-45835247560-A1")
        self.assertNotIn("Taiyous-Novels", repo)

    def test_production_or_malformed_targets_fail_without_network(self):
        class NoNetwork:
            def __getattr__(self, name):
                raise AssertionError("No HF calls permitted")
        for name in ("AdityaSreevatsaK/Taiyous-Novels",
                     "AdityaSreevatsaK/Taiyous-Novels-Backup",
                     "AdityaSreevatsaK/Unexpected",
                     "owner/Taiyou-Import-Acceptance-zero-A1"):
            with self.subTest(repo=name), self.assertRaises(ValueError):
                run_acceptance(NoNetwork(), "fake-token", name)
        for run, attempt, owner in (
                ("", "1", "Owner"), ("../../secret", "1", "Owner"),
                ("123", "0", "Owner"), ("123", "01", "Owner"),
                ("123", "1", "Owner/Bad"), ("123", "1", "")):
            with self.subTest(run=run), self.assertRaises(ValueError):
                import_repo(run, attempt, owner)

    def test_requires_master_from_controller(self):
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "Another/Repo",
            "GITHUB_REF": "refs/heads/master",
            "HF_DISPOSABLE_TEST_TOKEN": "fake",
        }):
            self.assertEqual(main(), 2)

    def test_requires_disposable_token(self):
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "AdityaSreevatsaK/Taiyou-Novels-Storage-Controller",
            "GITHUB_REF": "refs/heads/master",
            "HF_DISPOSABLE_TEST_TOKEN": "",
        }):
            self.assertEqual(main(), 2)


if __name__ == "__main__":
    unittest.main()
