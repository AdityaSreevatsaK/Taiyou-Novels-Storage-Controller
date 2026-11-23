"""Offline safeguards for synthetic real-HF acceptance, never use credentials."""
import json
import os
from unittest.mock import patch
import unittest
from zipfile import ZipFile
from io import BytesIO

from taiyou_storage.core import validate_catalogue
from taiyou_storage.github_output import safe_metrics
from taiyou_storage.disposable_backup_acceptance import (
    acceptance, main, repositories, synthetic_files,
)


class DisposableBackupAcceptanceTests(unittest.TestCase):
    def test_fresh_names_are_private_test_names_not_production(self):
        src, dest = repositories("44930533208", "1")
        self.assertNotEqual(src, dest)
        self.assertTrue(src.startswith("AdityaSreevatsaK/Taiyou-Backup-Acceptance-Source-"))
        self.assertTrue(dest.startswith("AdityaSreevatsaK/Taiyou-Backup-Acceptance-Destination-"))
        self.assertNotIn("Taiyous-Novels", src + dest)

    def test_authenticated_owner_can_differ_from_github_owner(self):
        src, dest = repositories("45124530615", "2", owner="SeparateHFAccount")
        self.assertTrue(src.startswith("SeparateHFAccount/Taiyou-Backup-Acceptance-Source-"))
        self.assertTrue(dest.startswith("SeparateHFAccount/Taiyou-Backup-Acceptance-Destination-"))
        for bad_owner in ("", "bad/owner", "space owner", "../x", "!"):
            with self.subTest(owner=bad_owner), self.assertRaises(ValueError):
                repositories("45124530615", "2", owner=bad_owner)

    def test_unsafe_or_ambiguous_run_ids_are_rejected(self):
        for run, attempt in [("", "1"), ("0", "1"), ("../../prod", "1"),
                             ("12", "0"), ("12", "01"), ("12", "-1"),
                             ("1" * 40, "1")]:
            with self.subTest(run=run, attempt=attempt), self.assertRaises(ValueError):
                repositories(run, attempt)

    def test_catalogue_and_epub_zip_are_synthetic_and_valid(self):
        fixture = synthetic_files()
        books = validate_catalogue(json.loads(fixture["data/library.json"]))
        self.assertEqual(len(books), 1)
        self.assertEqual(len(fixture), 5)
        for name, payload in fixture.items():
            if name.endswith((".epub", ".zip")):
                with ZipFile(BytesIO(payload)) as archive:
                    self.assertIsNone(archive.testzip())
        self.assertEqual(sum(name.endswith(".png") for name in fixture), 1)

    def test_never_operate_on_production_or_same_destination(self):
        class NoCall:
            def __getattr__(self, name):
                raise AssertionError("No remote HF access allowed")
        with self.assertRaises(ValueError):
            acceptance(NoCall(), "AdityaSreevatsaK/Taiyous-Novels",
                       "AdityaSreevatsaK/Other", "synthetic-token")
        with self.assertRaises(ValueError):
            acceptance(NoCall(), "AdityaSreevatsaK/Example",
                       "AdityaSreevatsaK/Example", "synthetic-token")

    def test_public_logs_only_receive_numeric_failure_diagnostics(self):
        metrics = safe_metrics("Acceptance stage: 6\nAcceptance error code: 3\nPrivate file: hidden")
        self.assertEqual(metrics, [("Acceptance stage", "6"), ("Acceptance error code", "3")])

    def test_public_origin_and_guard_metrics_contain_only_numbers(self):
        metrics = safe_metrics(
            "Acceptance error origin: 1\nAcceptance harness guard: 0\n"
            "HF token: SECRET SHOULD NOT BE EXPOSED"
        )
        self.assertEqual(metrics, [
            ("Acceptance error origin", "1"), ("Acceptance harness guard", "0")
        ])

    def test_main_requires_trusted_master_context(self):
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "another/repo",
            "GITHUB_REF": "refs/heads/master",
            "HF_DISPOSABLE_TEST_TOKEN": "fake-token",
        }):
            self.assertEqual(main(), 2)

    def test_main_requires_dedicated_token(self):
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "AdityaSreevatsaK/Taiyou-Novels-Storage-Controller",
            "GITHUB_REF": "refs/heads/master",
            "HF_DISPOSABLE_TEST_TOKEN": "",
        }):
            self.assertEqual(main(), 2)


if __name__ == "__main__":
    unittest.main()
