import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from taiyou_storage.core import StorageError, conflicts, normalized_title, rows, validate_catalogue, write_csv


def book(ident, title):
    return {"id": ident, "epubPath": f"data/novels/{ident}/source.epub",
            "archivePath": f"data/novels/{ident}/original.zip",
            "metadata": {"id": ident, "title": title, "author": "Test"}}


class CatalogueTests(unittest.TestCase):
    def test_schema_validation(self):
        a = book("a" * 24, "Novel")
        self.assertEqual(len(validate_catalogue({"version": 1, "books": [a]})), 1)

    def test_duplicate_id_rejected(self):
        a = book("a" * 24, "Novel")
        with self.assertRaises(StorageError):
            validate_catalogue({"version": 1, "books": [a, a]})

    def test_malformed_catalogue_rejected(self):
        with self.assertRaises(StorageError):
            validate_catalogue({"books": []})

    def test_name_normalisation(self):
        self.assertEqual(normalized_title("  MARTIAL—World "), normalized_title("martial world"))

    def test_conflict_types(self):
        data = [book("a" * 24, "Martial World"), book("b" * 24, "martial world"),
                book("c" * 24, "Martial World"), book("d" * 24, "Another Book")]
        output = conflicts(data)
        self.assertEqual(len(output), 3)
        self.assertEqual(sum(x["type"] == "exact" for x in output), 1)

    def test_csv_output(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "report.csv"
            write_csv(path, rows([book("a" * 24, "Novel")]),
                      ["id", "title", "author", "chapters", "epub_path", "archive_path"])
            self.assertIn("Novel", path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
