"""Concise Windows-friendly console summaries, with full local report files."""
from __future__ import annotations

from collections import OrderedDict
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import csv
import tempfile
import unittest
from unittest.mock import patch

from taiyou_storage.cli import run as management_run
from taiyou_storage.console_summary import print_summary


def _book(ident: str, title: str):
    return {
        "id": ident,
        "metadata": {"id": ident, "title": title, "author": "Sample Author"},
        "epubPath": f"data/novels/{ident}/source.epub",
        "archivePath": f"data/novels/{ident}/original.zip",
    }


class ConsoleSummaryTests(unittest.TestCase):
    def test_consistent_labelled_counts_and_report_paths(self):
        output = StringIO()
        with redirect_stdout(output):
            print_summary("Cover audit", OrderedDict([
                ("Total novels", 161),
                ("Missing standalone cover files", 10),
                ("Conflicts detected", 5),
            ]), reports=["reports/missing-covers.csv"])
        text = output.getvalue()
        self.assertIn("=== Cover audit ===", text)
        self.assertIn("Total novels", text)
        self.assertIn("161", text)
        self.assertIn("Missing standalone cover files", text)
        self.assertIn("10", text)
        self.assertIn("Conflicts detected", text)
        self.assertIn("5", text)
        self.assertIn("reports/missing-covers.csv", text)

    def test_conflicts_summary_suppresses_titles_but_saves_full_report(self):
        books = [_book("a" * 24, "First Novel"),
                 _book("b" * 24, "first novel"),
                 _book("c" * 24, "Another Novel")]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conflicts.csv"
            with patch("taiyou_storage.cli.load_remote",
                       return_value=(books, "a" * 40)):
                output = StringIO()
                with redirect_stdout(output):
                    result = management_run(["conflicts", "--output", str(path)])
                self.assertEqual(result, 0)
            self.assertIn("Conflicts detected (pairs)", output.getvalue())
            self.assertIn("Total novels", output.getvalue())
            self.assertNotIn("First Novel", output.getvalue())
            with path.open(encoding="utf-8-sig", newline="") as stream:
                records = list(csv.DictReader(stream))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["type"], "normalised")

    def test_verbose_conflicts_prints_details(self):
        books = [_book("a" * 24, "Same Title"), _book("b" * 24, "Same Title")]
        with tempfile.TemporaryDirectory() as tmp:
            output = StringIO()
            with patch("taiyou_storage.cli.load_remote",
                       return_value=(books, "b" * 40)), redirect_stdout(output):
                self.assertEqual(management_run([
                    "conflicts", "--output", str(Path(tmp) / "c.csv"), "--verbose",
                ]), 0)
            self.assertIn("Same Title", output.getvalue())

    def test_novel_listing_prints_summary_and_saves_rows(self):
        books = [_book("a" * 24, "Private Book"),
                 _book("b" * 24, "Other Private Book")]
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "novels.csv"
            output = StringIO()
            with patch("taiyou_storage.cli.load_remote",
                       return_value=(books, "c" * 40)), redirect_stdout(output):
                self.assertEqual(management_run(["list", "--output", str(dest)]), 0)
            self.assertIn("Total novels", output.getvalue())
            self.assertIn("Catalogue entries exported", output.getvalue())
            self.assertNotIn("Private Book", output.getvalue())
            with dest.open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 2)


if __name__ == "__main__":
    unittest.main()
