"""Offline regression tests for revision-pinned library inspection."""
from __future__ import annotations

from io import BytesIO, StringIO
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

from taiyou_storage.inspection import (
    HFReadOnly, Snapshot, canonical_url, chapter_positions, compare_retriever,
    duplicate_candidates, embedded_cover, inspect_archive, scan, valid_image,
)
from taiyou_storage.inspection_cli import cover_audit_rows, health_report, run

IDENT = "a" * 24
SECOND = "b" * 24


def image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (300, 400), (40, 80, 100)).save(buffer, format="PNG")
    return buffer.getvalue()


def epub_bytes(*, cover: bool = False) -> bytes:
    buffer = BytesIO()
    opf = ('<package xmlns="http://www.idpf.org/2007/opf"><metadata/>'
           '<manifest><item id="c" href="cover.png" media-type="image/png"'
           + (' properties="cover-image"' if cover else '') +
           '/></manifest><spine/></package>')
    container = ('<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/cover.png", image_bytes())
    return buffer.getvalue()


def archive_bytes(positions=(1, 2, 3), *, complete=False, manifest=True, cover=False) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("source.epub", epub_bytes(cover=cover))
        if manifest:
            chapters = [{"position": number, "file": f"chapter_{number}.txt"}
                        for number in positions]
            payload = {"complete": complete, "chapters": chapters} if complete else chapters
            z.writestr("chapters.json", json.dumps(payload))
            for n in set(positions):
                z.writestr(f"chapter_{n}.txt", f"chapter {n}")
    return buffer.getvalue()


def book(ident=IDENT, *, title="Synthetic Book", author="Synthetic Writer",
         source="https://novelfull.com/synthetic.html", cover=True):
    root = f"data/novels/{ident}"
    metadata = {"id": ident, "title": title, "author": author,
                "sourceUrl": source, "chapterCount": 3}
    if cover:
        metadata["coverPath"] = root + "/cover.png"
    return {"id": ident, "metadata": metadata,
            "epubPath": root + "/source.epub", "archivePath": root + "/original.zip"}


class FixtureBackend:
    def __init__(self, root, books=None, revision="1" * 40):
        self.root = Path(root)
        self.books = books if books is not None else [book()]
        self.revision = revision
        self.calls = []
        self.fail = set()
        self.root.joinpath("data").mkdir(parents=True, exist_ok=True)
        self.add("data/library.json", json.dumps({"version": 1, "books": self.books}).encode())

    def add(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def populate(self, *, positions=(1, 2, 3), cover=True, complete=False, manifest=True):
        prefix = f"data/novels/{IDENT}"
        self.add(prefix + "/source.epub", epub_bytes(cover=cover))
        self.add(prefix + "/original.zip", archive_bytes(positions, complete=complete, manifest=manifest, cover=cover))
        if cover:
            self.add(prefix + "/cover.png", image_bytes())
        return self

    def snapshot(self):
        files = {p.relative_to(self.root).as_posix(): p.stat().st_size
                 for p in self.root.rglob("*") if p.is_file()}
        return Snapshot(self.revision, files)

    def download(self, name, revision):
        assert revision == self.revision
        self.calls.append(name)
        if name in self.fail:
            raise ConnectionError("synthetic network failure")
        return self.root / name


class ChapterTests(unittest.TestCase):
    def test_complete_and_discontinuous(self):
        names = {"chapter_1.txt", "chapter_2.txt", "chapter_4.txt"}
        records = [{"position": n, "file": f"chapter_{n}.txt"} for n in (1, 2, 4)]
        result = chapter_positions(records, names, complete=True)
        self.assertEqual(result["ranges"], ["1-2", "4"])
        self.assertEqual(result["missing"], ["3"])
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_genuine_explicit_completion_required(self):
        rows = [{"position": i, "file": f"{i}.txt"} for i in (1, 2)]
        self.assertEqual(chapter_positions(rows, {"1.txt", "2.txt"})["status"], "VERIFIED_RANGE")
        self.assertEqual(chapter_positions(rows, {"1.txt", "2.txt"}, complete=True)["status"],
                         "VERIFIED_COMPLETE")
        self.assertEqual(chapter_positions(rows)["status"], "UNVERIFIED")

    def test_duplicate_malformed_and_missing_files(self):
        rows = [{"position": 1, "file": "1.txt"}, {"position": 1, "file": "1.txt"},
                {"position": 3, "file": "absent.txt"}, {"position": "4"},
                {"position": 0}, {"file": "none.txt"}]
        result = chapter_positions(rows, {"1.txt"})
        self.assertEqual(result["duplicates"], [1])
        self.assertEqual(result["missing"], ["2"])
        self.assertEqual(result["malformed"], 3)
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_archive_without_manifest_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "original.zip"
            path.write_bytes(archive_bytes(manifest=False))
            self.assertEqual(inspect_archive(path)["status"], "UNVERIFIED")

    def test_corrupt_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "original.zip"
            path.write_bytes(b"not a ZIP")
            with self.assertRaises(zipfile.BadZipFile):
                inspect_archive(path)


class CoverTests(unittest.TestCase):
    def test_real_and_broken_images(self):
        self.assertTrue(valid_image(image_bytes(), ".png"))
        self.assertFalse(valid_image(image_bytes(), ".jpg"))
        self.assertFalse(valid_image(b"broken", ".png"))
        self.assertFalse(valid_image(image_bytes()[:70], ".png"))

    def test_embedded_only_epub(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.epub"
            path.write_bytes(epub_bytes(cover=True))
            self.assertTrue(embedded_cover(path))
            path.write_bytes(epub_bytes(cover=False))
            self.assertFalse(embedded_cover(path))


class InspectionTests(unittest.TestCase):
    def test_deep_complete_and_original_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FixtureBackend(tmp).populate(complete=True)
            report = scan(backend, "deep", Path(tmp) / "cache")
            row = report["novels"][0]
            self.assertEqual(row["verification_status"], "VERIFIED_COMPLETE")
            self.assertEqual(row["cover_status"], "AVAILABLE")
            self.assertEqual(row["chapter_ranges"], ["1-3"])
            self.assertEqual(row["stored_chapter_count"], 3)

    def test_valid_but_wrong_epub_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FixtureBackend(tmp).populate(complete=True, cover=True)
            backend.add(f"data/novels/{IDENT}/source.epub", epub_bytes(cover=False))
            report = scan(backend, "deep")
            self.assertIn("EPUB_ARCHIVE_MISMATCH", {i["code"] for i in report["issues"]})
            self.assertEqual(report["novels"][0]["verification_status"], "UNVERIFIED")

    def test_deep_incomplete_and_corrupt_cover(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FixtureBackend(tmp).populate(positions=(1, 3))
            backend.add(f"data/novels/{IDENT}/cover.png", b"corrupted")
            report = scan(backend, "deep")
            row = report["novels"][0]
            self.assertEqual(row["verification_status"], "INCOMPLETE")
            self.assertEqual(row["cover_status"], "BROKEN")
            self.assertIn("INCOMPLETE_CHAPTERS", {i["code"] for i in report["issues"]})

    def test_embedded_only_and_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = book(cover=False)
            backend = FixtureBackend(tmp, [b]).populate(cover=False, manifest=False)
            backend.add(f"data/novels/{IDENT}/source.epub", epub_bytes(cover=True))
            result = scan(backend, "deep")
            self.assertEqual(result["novels"][0]["cover_status"], "EMBEDDED_ONLY")
            self.assertEqual(result["novels"][0]["verification_status"], "UNVERIFIED")

    def test_listing_only_does_not_claim_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FixtureBackend(tmp).populate(complete=True)
            result = scan(backend, "quick")
            self.assertEqual(result["novels"][0]["verification_status"], "UNVERIFIED")
            self.assertEqual(result["novels"][0]["cover_status"], "UNVERIFIED")
            self.assertNotIn("source.epub", backend.calls)

    def test_partial_network_failure_still_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FixtureBackend(tmp).populate()
            backend.fail.add(f"data/novels/{IDENT}/original.zip")
            result = scan(backend, "deep")
            self.assertEqual(result["novels"][0]["verification_status"], "UNVERIFIED")
            self.assertIn("CORRUPT_OR_UNREADABLE_ARCHIVE",
                          {issue["code"] for issue in result["issues"]})

    def test_interrupted_scan_preserves_unverified_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FixtureBackend(tmp).populate()
            with patch("taiyou_storage.inspection.as_completed", side_effect=KeyboardInterrupt):
                result = scan(backend, "deep")
            self.assertTrue(result["interrupted"])
            self.assertEqual(len(result["novels"]), 1)
            self.assertIn("SCAN_INTERRUPTED", {issue["code"] for issue in result["issues"]})

    def test_transient_error_not_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FixtureBackend(tmp).populate()
            archive = f"data/novels/{IDENT}/original.zip"
            cache = Path(tmp) / "cache"
            backend.fail.add(archive)
            first = scan(backend, "deep", cache)
            self.assertEqual(first["novels"][0]["verification_status"], "UNVERIFIED")
            backend.fail.clear()
            backend.calls.clear()
            second = scan(backend, "deep", cache)
            self.assertIn(archive, backend.calls)
            self.assertEqual(second["novels"][0]["verification_status"], "VERIFIED_RANGE")

    def test_duplicate_epub_hash_and_ambiguous_author(self):
        digest = "a" * 64
        rows = [
            {"novel_id": IDENT, "title": "First", "author": "A",
             "source_url": "https://novelfull.com/first.html", "epub_sha256": digest},
            {"novel_id": SECOND, "title": "Second", "author": "B",
             "source_url": "https://novelfull.com/second.html", "epub_sha256": digest},
        ]
        self.assertEqual(len(duplicate_candidates(rows)), 1)
        ambiguous = compare_retriever(rows[:1],
                                      {"novels": [{"url": rows[0]["source_url"], "author": "Other"}]}, [])
        self.assertEqual(ambiguous["records"][0]["state"], "AMBIGUOUS")

    def test_generated_cover_is_not_counted_as_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            novel = book()
            novel["metadata"]["coverGenerated"] = True
            backend = FixtureBackend(tmp, [novel]).populate()
            result = scan(backend, "deep")
            self.assertEqual(result["novels"][0]["cover_status"], "UNVERIFIED")

    def test_revision_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FixtureBackend(tmp).populate()
            cache = Path(tmp) / "cache"
            scan(backend, "deep", cache)
            backend.calls.clear()
            scan(backend, "deep", cache)
            self.assertEqual(backend.calls, ["data/library.json"])
            backend.revision = "2" * 40
            scan(backend, "deep", cache)
            self.assertGreater(len(backend.calls), 1)

    def test_orphan_and_broken_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FixtureBackend(tmp).populate()
            backend.add("data/novels/" + SECOND + "/original.zip", b"x")
            (backend.root / f"data/novels/{IDENT}/source.epub").unlink()
            result = scan(backend, "quick")
            self.assertTrue({"ORPHAN_NOVEL_DIRECTORY", "MISSING_EPUB"} <=
                            {issue["code"] for issue in result["issues"]})

    def test_query_parameters_prevent_false_url_collisions(self):
        first = canonical_url("https://example.com/book?id=1")
        second = canonical_url("https://example.com/book?id=2")
        self.assertNotEqual(first, second)
        self.assertEqual(canonical_url("https://example.com/"), "")

    def test_duplicate_identity_and_url(self):
        first = {"novel_id": IDENT, "title": "First", "author": "X",
                 "source_url": "https://novelfull.com/book.html"}
        second = {"novel_id": SECOND, "title": "Changed Title", "author": "Y",
                  "source_url": "http://www.novelfull.com/book.html/"}
        self.assertEqual(len(duplicate_candidates([first, second])), 1)
        self.assertEqual(canonical_url(first["source_url"]), canonical_url(second["source_url"]))

    def test_retriever_partial_download_needs_more_chapters(self):
        registry = {"novels": [{"url": "https://novelfull.com/partial.html",
                               "downloads": [{"status": "complete", "range": "1-20"}]}]}
        result = compare_retriever([], registry, [])
        self.assertEqual(result["records"][0]["state"], "PARTIALLY_DOWNLOADED")

    def test_comparison_states_and_exclusion_privacy(self):
        rows = [{"novel_id": IDENT, "title": "Synthetic Book",
                 "author": "Writer", "source_url": "https://novelfull.com/sample.html"}]
        registry = {"novels": [
            {"title": "Synthetic Book", "author": "Writer", "url": "https://novelfull.com/sample.html"},
            {"title": "New Novel", "author": "Writer", "url": "https://novelfull.com/new.html",
             "downloads": [{"status": "complete"}]},
            {"title": "Pending", "url": "https://novelfull.com/pending.html"}]}
        result = compare_retriever(rows, registry, [])
        self.assertEqual([r["state"] for r in result["records"]],
                         ["ALREADY_IN_HF", "DOWNLOADED_NOT_UPLOADED", "TO_DOWNLOAD"])
        encoded = json.dumps(result["exclusions"])
        self.assertNotIn("Synthetic Book", encoded)
        self.assertNotIn("sample.html", encoded)
        self.assertNotIn(IDENT, encoded)

    def test_reports_local_and_escaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FixtureBackend(Path(tmp) / "dataset").populate()
            reports = Path(tmp) / "reports"
            self.assertEqual(run(["inventory", "--mode", "deep", "--reports-dir", str(reports)], backend), 0)
            self.assertTrue((reports / "novel-inventory.json").exists())
            self.assertEqual(run(["covers", "--reports-dir", str(reports)], backend), 0)
            self.assertEqual(run(["integrity", "--reports-dir", str(reports)], backend), 0)
            self.assertEqual(run(["health", "--reports-dir", str(reports)], backend), 0)
            first = json.loads((reports / "library-health.json").read_text())
            self.assertEqual(first["metrics"]["total_novels"], 1)
            self.assertEqual(run(["health", "--reports-dir", str(reports)], backend), 0)
            second = json.loads((reports / "library-health.json").read_text())
            self.assertEqual(second["changes_since_previous_scan"]["total_novels"], 0)

    def test_missing_cover_csv_is_actionable_not_all_unverified(self):
        with tempfile.TemporaryDirectory() as tmp:
            novels = [book(IDENT, cover=True),
                      book(SECOND, title="No Standalone", cover=False)]
            backend = FixtureBackend(Path(tmp) / "dataset", novels).populate()
            backend.calls.clear()
            result = scan(backend, "manifest")
            complete, missing = cover_audit_rows(result["novels"])
            self.assertEqual(len(complete), 2)
            self.assertEqual(len(missing), 1)
            self.assertEqual(missing[0]["title"], "No Standalone")
            self.assertEqual(missing[0]["standalone_cover"], "ABSENT")
            present = next(r for r in complete if r["title"] == "Synthetic Book")
            self.assertEqual(present["standalone_cover"], "PRESENT")
            self.assertEqual(present["cover_validation"], "UNVERIFIED")
            reports = Path(tmp) / "reports"
            with patch("sys.stdout", new_callable=StringIO) as output:
                self.assertEqual(run(["covers", "--reports-dir", str(reports)], backend), 0)
            console = output.getvalue()
            self.assertIn("=== Cover audit ===", console)
            self.assertIn("Total novels", console)
            self.assertIn("Missing standalone cover files", console)
            self.assertIn("Standalone cover files present", console)
            self.assertIn("missing-covers.csv", console)
            self.assertNotIn("No Standalone", console)  # Details stay private in CSV
            with (reports / "missing-covers.csv").open(encoding="utf-8-sig", newline="") as stream:
                missing_records = list(csv.DictReader(stream))
            with (reports / "cover-audit.csv").open(encoding="utf-8-sig", newline="") as stream:
                all_records = list(csv.DictReader(stream))
            self.assertEqual(len(missing_records), 1)
            self.assertEqual(len(all_records), 2)
            self.assertIn("recommended_action", missing_records[0])
            self.assertNotIn("source.epub", backend.calls)
            self.assertNotIn("original.zip", backend.calls)

    def test_corrupt_standalone_cover_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FixtureBackend(tmp).populate()
            backend.add(f"data/novels/{IDENT}/cover.png", b"invalid-image")
            result = scan(backend, "deep")
            all_rows, attention = cover_audit_rows(result["novels"])
            self.assertEqual(len(all_rows), 1)
            self.assertEqual(len(attention), 1)
            self.assertEqual(attention[0]["cover_validation"], "BROKEN")
            self.assertIn("Replace", attention[0]["recommended_action"])

    def test_public_dataset_refused(self):
        from types import SimpleNamespace
        with patch("huggingface_hub.HfApi") as cls:
            cls.return_value.dataset_info.return_value = SimpleNamespace(private=False, sha="a" * 40)
            with self.assertRaisesRegex(ValueError, "private"):
                HFReadOnly().snapshot()

    def test_read_only_cloud_contract(self):
        import inspect
        from taiyou_storage import inspection
        source = inspect.getsource(inspection.HFReadOnly)
        self.assertNotIn("create_commit", source)
        self.assertNotIn("upload_file", source)
        self.assertNotIn("delete_file", source)


class WindowsLauncherTests(unittest.TestCase):
    def test_launchers_reference_local_engine(self):
        root = Path(__file__).resolve().parents[1]
        for number in ("05", "12", "13", "14", "15"):
            files = list(root.glob(number + "_*.cmd"))
            self.assertEqual(len(files), 1)
            content = files[0].read_text(encoding="utf-8").lower()
            self.assertIn("taiyou_storage.inspection_cli", content)
            self.assertIn("%*", content)
            self.assertNotIn("--apply", content)

    @unittest.skipUnless(sys.platform == "win32", "CMD execution only on Windows")
    def test_windows_launcher_help_runs_without_network(self):
        root = Path(__file__).resolve().parents[1]
        p = subprocess.run(["cmd", "/c", str(root / "12_export_novel_inventory.cmd"), "--help"],
                           capture_output=True, text=True, cwd=root, timeout=15)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("--mode", p.stdout)


if __name__ == "__main__":
    unittest.main()
