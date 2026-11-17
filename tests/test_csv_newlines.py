"""Regression test for Windows CSV reports containing blank lines."""
from __future__ import annotations

import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from taiyou_storage.inspection_cli import _csv


class WindowsCSVLineEndingsTests(unittest.TestCase):
    def test_csv_serialisation_avoids_double_carriage_return(self):
        records = [
            {"title": "Example One", "cover_validation": "UNVERIFIED"},
            {"title": "Example Two", "cover_validation": "AVAILABLE"},
        ]
        fields = ["title", "cover_validation"]
        captured = []

        def capture(path: Path, content: str) -> None:
            captured.append(content)

        with patch("taiyou_storage.inspection_cli._atomic", side_effect=capture):
            _csv(Path("cover-audit.csv"), records, fields)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].count("\n"), 3)
        self.assertNotIn("\r", captured[0])
        # Windows text writes convert each LF to CRLF.
        windows_bytes = captured[0].replace("\n", "\r\n").encode("utf-8")
        self.assertNotIn(b"\r\r\n", windows_bytes)
        self.assertEqual(windows_bytes.count(b"\r\n"), 3)

    def test_saved_file_contains_no_blank_rows_and_preserves_data(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "missing-covers.csv"
            expected = [
                {"novel_id": "a" * 24, "title": "First, with comma"},
                {"novel_id": "b" * 24, "title": "Second"},
            ]
            _csv(path, expected, ["novel_id", "title"])
            with path.open(encoding="utf-8-sig", newline="") as stream:
                actual = list(csv.DictReader(stream))
            self.assertEqual(actual, expected)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                lines = list(csv.reader(stream))
            self.assertEqual(len(lines), 3)
            self.assertFalse(any(not any(cell.strip() for cell in row) for row in lines))


if __name__ == "__main__":
    unittest.main()
