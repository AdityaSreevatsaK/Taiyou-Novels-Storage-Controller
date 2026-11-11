import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
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


    def test_new_private_dataset_can_be_previewed_for_initial_upload(self):
        from taiyou_storage.core import load_remote
        with patch("huggingface_hub.HfApi") as factory, \
                patch("huggingface_hub.hf_hub_download") as download:
            api = factory.return_value
            api.dataset_info.return_value = SimpleNamespace(private=True, sha="a" * 40)
            api.list_repo_files.return_value = [".gitattributes", "README.md"]
            self.assertEqual(load_remote("owner/new-private", allow_empty=True),
                             ([], "a" * 40))
            download.assert_not_called()
            with self.assertRaisesRegex(StorageError, "no data/library.json"):
                load_remote("owner/new-private")
            download.assert_not_called()

    def test_orphaned_data_is_not_treated_as_empty(self):
        from taiyou_storage.core import load_remote
        with patch("huggingface_hub.HfApi") as factory, \
                patch("huggingface_hub.hf_hub_download") as download:
            api = factory.return_value
            api.dataset_info.return_value = SimpleNamespace(private=True, sha="b" * 40)
            api.list_repo_files.return_value = [
                ".gitattributes", "data/novels/123456789012345678901234/original.zip"]
            with self.assertRaisesRegex(StorageError, "Refusing automatic initialization"):
                load_remote("owner/partial", allow_empty=True)
            download.assert_not_called()

    def test_public_empty_dataset_is_rejected(self):
        from taiyou_storage.core import load_remote
        with patch("huggingface_hub.HfApi") as factory:
            factory.return_value.dataset_info.return_value = SimpleNamespace(
                private=False, sha="a" * 40)
            with self.assertRaisesRegex(StorageError, "not private"):
                load_remote("owner/public", allow_empty=True)
            factory.return_value.list_repo_files.assert_not_called()

    def test_missing_or_inaccessible_repo_is_not_silently_initialised(self):
        from taiyou_storage.core import load_remote
        with patch("huggingface_hub.HfApi") as factory:
            factory.return_value.dataset_info.side_effect = RuntimeError("Not found")
            with self.assertRaisesRegex(RuntimeError, "Not found"):
                load_remote("owner/missing", allow_empty=True)

    def test_csv_output(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "report.csv"
            write_csv(path, rows([book("a" * 24, "Novel")]),
                      ["id", "title", "author", "chapters", "epub_path", "archive_path"])
            self.assertIn("Novel", path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
