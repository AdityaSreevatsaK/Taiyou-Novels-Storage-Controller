"""Offline safety tests for full-verified synthetic HF acceptance."""
from unittest.mock import patch
import os
import unittest

from taiyou_storage.disposable_full_verified_acceptance import (
    full_verified_acceptance, main,
)


class FullVerifiedSyntheticAcceptanceTests(unittest.TestCase):
    def test_no_production_dataset_or_same_destination_can_be_used(self):
        class NoNetwork:
            def __getattr__(self, name):
                raise AssertionError("HF must not be contacted")
        api = NoNetwork()
        for source, destination in [
            ("AdityaSreevatsaK/Taiyous-Novels", "AdityaSreevatsaK/Test"),
            ("AdityaSreevatsaK/Test", "AdityaSreevatsaK/Taiyous-Novels-Backup"),
            ("AdityaSreevatsaK/Taiyou-Backup-Acceptance-Source-1",
             "AdityaSreevatsaK/Taiyou-Backup-Acceptance-Source-1"),
            ("AdityaSreevatsaK/Random", "AdityaSreevatsaK/Other"),
            ("OwnerOne/Taiyou-Backup-Acceptance-Source-1",
             "OwnerTwo/Taiyou-Backup-Acceptance-Destination-1"),
        ]:
            with self.subTest(source=source, destination=destination):
                with self.assertRaises(ValueError):
                    full_verified_acceptance(api, source, destination, "synthetic")

    def test_requires_trusted_master_workflow(self):
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "another/unsafe-repo",
            "GITHUB_REF": "refs/heads/master",
            "HF_DISPOSABLE_TEST_TOKEN": "fake",
        }):
            self.assertEqual(main(), 2)

    def test_requires_disposable_token_only(self):
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "AdityaSreevatsaK/Taiyou-Novels-Storage-Controller",
            "GITHUB_REF": "refs/heads/master",
            "HF_DISPOSABLE_TEST_TOKEN": "",
        }):
            self.assertEqual(main(), 2)


if __name__ == "__main__":
    unittest.main()
