"""Offline reliability tests for bounded, atomic Hugging Face ZIP downloads."""
from __future__ import annotations

from contextlib import chdir, redirect_stdout
import csv
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from taiyou_storage.cli import run as cli_run
from taiyou_storage.downloads import _safe_destination, download_archives


def item(number: int):
    ident = f"{number:024x}"
    relative = f"data/novels/{ident}/original.zip"
    return {"id": ident, "title": f"Private Novel {number}",
            "archive_path": relative}


def catalogue(number: int):
    book = item(number)
    return {"id": book["id"], "metadata": {"id": book["id"],
            "title": book["title"], "author": "Example"},
            "epubPath": f"data/novels/{book['id']}/source.epub",
            "archivePath": book["archive_path"]}


class DownloadReliabilityTests(unittest.TestCase):
    def test_parallel_streaming_and_manifest_hashes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.zip"
            payload = b"unit-test-data" * 250000
            source.write_bytes(payload)
            books = [item(i) for i in range(1, 7)]
            active, peak = 0, 0
            guard = threading.Lock()

            def download(**kwargs):
                nonlocal active, peak
                with guard:
                    active += 1
                    peak = max(peak, active)
                # A local mock of network work that ensures the worker cap
                # is exercised without contacting the private dataset.
                threading.Event().wait(0.015)
                with guard:
                    active -= 1
                return str(source)

            manifest, report = download_archives(
                books, {x["archive_path"] for x in books},
                repo="owner/private", revision="a" * 40,
                root=root / "downloads", downloader=download, workers=3)
            self.assertGreater(peak, 1)
            self.assertLessEqual(peak, 3)
            self.assertEqual(len(manifest), 6)
            self.assertEqual(len(report), 6)
            self.assertTrue(all(x["state"] == "DOWNLOADED" for x in report))
            for entry in manifest:
                self.assertEqual(entry["sha256"], sha256(payload).hexdigest())
                self.assertEqual(
                    (root / "downloads" / entry["path"]).read_bytes(), payload)
            self.assertFalse(list((root / "downloads").rglob("*.part")))

    def test_failed_download_preserves_existing_file_and_cleans_partial(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            book = item(1)
            target = root / book["archive_path"]
            target.parent.mkdir(parents=True)
            target.write_bytes(b"original safe file")

            def failed_download(**kwargs):
                raise OSError("simulated HF timeout")

            manifest, report = download_archives(
                [book], {book["archive_path"]},
                repo="owner/private", revision="a" * 40,
                root=root, downloader=failed_download)
            self.assertEqual(manifest, [])
            self.assertEqual(report[0]["state"], "FAILED")
            self.assertEqual(target.read_bytes(), b"original safe file")
            self.assertEqual(list(root.rglob("*.part")), [])

    def test_missing_remote_archive_reports_missing_without_download(self):
        book = item(2)
        with TemporaryDirectory() as tmp:
            manifest, report = download_archives(
                [book], set(), repo="owner/private", revision="a" * 40,
                root=Path(tmp), downloader=lambda **_: self.fail("Unexpected download"))
            self.assertEqual(manifest, [])
            self.assertEqual(report[0]["state"], "MISSING")

    def test_unsafe_paths_and_workers_are_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path in ("../original.zip", "/data/novels/id/original.zip",
                         "data/novels/../../original.zip",
                         "data/novels/id/source.epub"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    _safe_destination(root, path)
            with self.assertRaises(ValueError):
                download_archives([item(1)], set(), repo="owner/private",
                                  revision="a" * 40, root=root,
                                  downloader=lambda **_: None, workers=9)
            redirect = root / "redirect"
            try:
                redirect.symlink_to(root / "outside", target_is_directory=True)
            except (OSError, NotImplementedError):
                pass  # Windows runners may restrict unprivileged symlinks
            else:
                with self.assertRaises(ValueError):
                    _safe_destination(redirect, item(1)["archive_path"])

    def test_failed_archive_marks_manifest_incomplete_and_is_not_printed(self):
        with TemporaryDirectory() as tmp, chdir(tmp):
            books = [catalogue(1), catalogue(2), catalogue(3)]
            first, missing, failed = (item(i) for i in (1, 2, 3))
            source = Path(tmp) / "sample.zip"
            source.write_bytes(b"synthetic ZIP bytes")

            def downloader(**kwargs):
                if kwargs["filename"] == failed["archive_path"]:
                    raise ConnectionError("Synthetic private path secret")
                return str(source)

            with patch("taiyou_storage.cli.load_remote",
                       return_value=(books, "b" * 40)), \
                 patch("huggingface_hub.HfApi") as api, \
                 patch("huggingface_hub.hf_hub_download", side_effect=downloader), \
                 redirect_stdout(StringIO()) as output:
                api.return_value.list_repo_files.return_value = [
                    first["archive_path"], failed["archive_path"]]
                status = cli_run(["download", "--destination", "exports", "--workers", "2"])
            self.assertEqual(status, 2)
            report_path = Path("exports/download-report.csv")
            with report_path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([x["state"] for x in rows],
                             ["DOWNLOADED", "MISSING", "FAILED"])
            manifest = json.loads(Path("exports/manifest.json").read_text())
            self.assertFalse(manifest["complete"])
            self.assertEqual(manifest["missing"], 1)
            self.assertEqual(manifest["failed"], 1)
            self.assertEqual(len(manifest["files"]), 1)
            self.assertIn("Failed downloads", output.getvalue())
            self.assertNotIn("Synthetic private path secret", output.getvalue())
            self.assertNotIn("Private Novel", output.getvalue())
            self.assertTrue((Path("exports") / first["archive_path"]).exists())


if __name__ == "__main__":
    unittest.main()
