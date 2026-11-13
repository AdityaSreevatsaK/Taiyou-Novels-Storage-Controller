"""Offline safety checks for the live disposable readable-folder acceptance runner.

No Hugging Face service is contacted. The real test remains credential-gated.
"""
from __future__ import annotations

import io
import json
import os
import unittest
import zipfile
from unittest.mock import patch

from scripts.verify_disposable_folder_migration import (
    BOOK_ID, OTHER_ID, create_fixture, run,
)
from taiyou_storage.core import validate_catalogue
from taiyou_storage.migrate_folders import plan_migration
from taiyou_storage.paths import book_dir, legacy_dir


class DisposableRunnerOfflineTests(unittest.TestCase):
    def test_fixture_uses_only_fictional_books_and_valid_archives(self):
        catalogue, data = create_fixture()
        self.assertEqual(validate_catalogue(catalogue), catalogue["books"])
        self.assertEqual({book["id"] for book in catalogue["books"]}, {BOOK_ID, OTHER_ID})
        self.assertEqual(len(data), 10)
        for book in catalogue["books"]:
            self.assertEqual(book["metadata"]["author"], "Fictional Author")
            self.assertIn(book["epubPath"], data)
            with zipfile.ZipFile(io.BytesIO(data[book["epubPath"]])) as epub:
                self.assertEqual(epub.read("mimetype"), b"application/epub+zip")
                self.assertIn("OEBPS/chapter1.xhtml", epub.namelist())
            cover_path = book["metadata"]["coverPath"]
            self.assertTrue(data[cover_path].startswith(b"\x89PNG\r\n\x1a\n"))
        first = catalogue["books"][0]
        with zipfile.ZipFile(io.BytesIO(data[first["archivePath"]])) as archive:
            self.assertEqual(archive.read("source.epub"), data[first["epubPath"]])
        self.assertIn("data/personal/progress/" + BOOK_ID + ".json", data)
        self.assertIn("data/personal/reviews/" + BOOK_ID + ".json", data)
        self.assertIn("data/personal/collections.json", data)
        self.assertEqual(json.loads(data["data/personal/progress/" + BOOK_ID + ".json"])["progress"], 73)

    def test_only_legacy_book_is_planned_for_migration(self):
        catalogue, data = create_fixture()
        items = {item["id"]: item for item in plan_migration(catalogue["books"], set(data))}
        self.assertEqual(items[BOOK_ID]["status"], "MIGRATE")
        self.assertEqual(items[OTHER_ID]["status"], "ALREADY_READABLE")
        old = legacy_dir(BOOK_ID)
        moves = items[BOOK_ID]["moves"]
        self.assertEqual(len(moves), 4)
        self.assertTrue(all(src.startswith(old + "/") for src, _ in moves))
        self.assertTrue(all(dst.startswith(items[BOOK_ID]["new"] + "/") for _, dst in moves))
        self.assertNotEqual(book_dir(catalogue["books"][1]), legacy_dir(OTHER_ID))
        self.assertNotIn("data/library.json", [src for src, _ in moves])

    def test_missing_dedicated_token_aborts_before_any_remote_operation(self):
        with patch.dict(os.environ, {"HF_DISPOSABLE_TEST_TOKEN": ""}):
            with patch("scripts.verify_disposable_folder_migration.HfApi") as hub:
                with self.assertRaisesRegex(RuntimeError, "BLOCKED"):
                    run()
                hub.assert_not_called()


if __name__ == "__main__":
    unittest.main()
