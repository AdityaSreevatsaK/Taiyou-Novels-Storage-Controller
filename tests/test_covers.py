"""Offline contract tests for cover ZIP parsing and safe matching."""
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from taiyou_storage.covers import Cover, CoverError, read_covers_zip, make_plan, match_book, source_key

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 24 +
       b"\x00\x00\x00\x00IEND\xaeB\x60\x82")


def existing(ident, title="Martial World", url="https://novelfull.com/martial-world.html", **metadata):
    return {"id": ident, "metadata": {"id": ident, "title": title, "author": "Author",
            "sourceUrl": url, "progress": 29, "personalRating": 8, **metadata},
            "epubPath": f"data/novels/{ident}/source.epub",
            "archivePath": f"data/novels/{ident}/original.zip"}


def cover(title="Martial World", url="https://novelfull.com/martial-world.html",
          filename="NovelFull/martial-world-deadbeef.png"):
    import hashlib
    return Cover(title, "NovelFull", url, filename, ".png",
                 PNG, hashlib.sha256(PNG).hexdigest())


def archive(path, records, extra=None, prefix="", nested=False):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as z:
        z.writestr(prefix + "covers_manifest.json", json.dumps(records))
        for name, content in (extra or {"NovelFull/martial-world-deadbeef.png": PNG}).items():
            z.writestr(prefix + name, content)
    if nested:
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("Downloaded_Covers.zip", target.getvalue())
    else:
        path.write_bytes(target.getvalue())


class CoverTests(unittest.TestCase):
    def test_simple_manifest_object(self):
        with TemporaryDirectory() as d:
            target = Path(d) / "covers.zip"
            archive(target, {"title": "Martial World", "website": "NovelFull",
                   "source_url": "https://novelfull.com/martial-world.html",
                   "cover_file": "NovelFull/martial-world-deadbeef.png"})
            items = read_covers_zip(target)
            self.assertEqual(items[0].digest, cover().digest)

    def test_manifest_list_and_artifact_wrapper(self):
        with TemporaryDirectory() as d:
            target = Path(d) / "artifact.zip"
            archive(target, [{"title": "Martial World", "website": "NovelFull",
                   "source_url": "https://novelfull.com/martial-world.html",
                   "cover_file": "NovelFull/martial-world-deadbeef.png"}],
                   prefix="Downloaded_Covers/", nested=True)
            self.assertEqual(len(read_covers_zip(target)), 1)


    def test_actual_retriever_results_manifest(self):
        with TemporaryDirectory() as d:
            target = Path(d) / "novel-cover-images.zip"
            archive(target, {
                "total": 3, "downloaded": 1, "skipped": 1, "failed": 1,
                "results": [
                    {"title": "Martial World", "website": "NovelFull",
                     "url": "https://novelfull.com/martial-world.html",
                     "source_url": "https://novelfull.com/martial-world.html",
                     "cover_file": "NovelFull/martial-world-deadbeef.png",
                     "status": "downloaded"},
                    {"title": "Unavailable", "website": "NovelFull",
                     "url": "https://novelfull.com/unavailable.html",
                     "source_url": "https://novelfull.com/unavailable.html",
                     "status": "failed", "error": "No cover image found"},
                    {"title": "Martial World", "website": "NovelFull",
                     "url": "https://novelfull.com/martial-world.html",
                     "source_url": "https://novelfull.com/martial-world.html",
                     "cover_file": "NovelFull/martial-world-deadbeef.png",
                     "status": "skipped"},
                ]})
            # One 'downloaded' and one 'skipped' entry deliberately refer to
            # the same file; the parser succeeds, later matching flags the
            # duplicate for manual review.
            parsed = read_covers_zip(target)
            self.assertEqual(len(parsed), 2)
            self.assertEqual(parsed[0].title, "Martial World")

    def test_results_with_failed_entries_only(self):
        with TemporaryDirectory() as d:
            target = Path(d) / "novel-cover-images.zip"
            archive(target, {"total": 1, "downloaded": 0, "skipped": 0,
                    "failed": 1, "results": [
                        {"title": "Unavailable", "source_url": "https://novelfull.com/unavailable.html",
                         "status": "failed", "error": "Not available"}]})
            with self.assertRaisesRegex(CoverError, "No usable cover"):
                read_covers_zip(target)

    def test_folder_path_with_single_zip(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            archive(root / "novel-cover-images.zip", {
                "total": 1, "downloaded": 1, "failed": 0, "skipped": 0,
                "results": [{"title": "Martial World", "website": "NovelFull",
                  "source_url": "https://novelfull.com/martial-world.html",
                  "cover_file": "NovelFull/martial-world-deadbeef.png",
                  "status": "downloaded"}]})
            self.assertEqual(len(read_covers_zip(root)), 1)
            (root / "extra.zip").write_bytes(b"")
            with self.assertRaisesRegex(CoverError, "specify the exact ZIP"):
                read_covers_zip(root)

    def test_block_zip_slip(self):
        with TemporaryDirectory() as d:
            target = Path(d) / "bad.zip"
            archive(target, {"title": "Martial World",
                   "source_url": "https://novelfull.com/martial-world.html",
                   "cover_file": "../private.png"})
            with self.assertRaises(CoverError):
                read_covers_zip(target)

    def test_reject_fake_image(self):
        with TemporaryDirectory() as d:
            target = Path(d) / "bad.zip"
            archive(target, {"title": "Martial World",
                   "source_url": "https://novelfull.com/martial-world.html",
                   "cover_file": "NovelFull/martial-world-deadbeef.png"},
                   extra={"NovelFull/martial-world-deadbeef.png": b"this is not a PNG"})
            with self.assertRaises(CoverError):
                read_covers_zip(target)

    def test_source_url_is_primary(self):
        book = existing("a" * 24, title="Old Martial World")
        found, reason = match_book([book], cover())
        self.assertEqual(found["id"], book["id"])
        self.assertEqual(reason, "source-url")

    def test_unique_title_fallback(self):
        book = existing("a" * 24, url="")
        found, reason = match_book([book], cover())
        self.assertEqual(reason, "unique-title")
        self.assertEqual(found["id"], book["id"])

    def test_source_url_conflict(self):
        book = existing("a" * 24, url="https://other.com/other-book")
        with self.assertRaises(CoverError):
            match_book([book], cover())

    def test_ambiguous_title_conflict(self):
        books = [existing("a" * 24, url=""), existing("b" * 24, url="")]
        with self.assertRaises(CoverError):
            match_book(books, cover())

    def test_source_url_points_to_other_book(self):
        books = [existing("a" * 24, title="Different", url=cover().source_url),
                 existing("b" * 24, title=cover().title, url="")]
        with self.assertRaises(CoverError):
            match_book(books, cover())

    def test_unmatched_is_missing_not_new_novel(self):
        self.assertEqual(make_plan([cover()], [], {}, set())[0]["status"], "MISSING")

    def test_new_and_no_mutations(self):
        book = existing("a" * 24)
        result = make_plan([cover()], [book], {}, set())
        self.assertEqual(result[0]["status"], "NEW")
        self.assertEqual(result[0]["destination"], f"data/novels/{book['id']}/cover.png")
        self.assertEqual(book["metadata"]["progress"], 29)
        self.assertNotIn("coverPath", book["metadata"])

    def test_skip_identical_existing_cover(self):
        book = existing("a" * 24, coverPath=f"data/novels/{'a'*24}/cover.png")
        c = cover()
        path = book["metadata"]["coverPath"]
        self.assertEqual(make_plan([c], [book], {path: c.digest}, {path})[0]["status"],
                         "UNCHANGED")

    def test_update_changed_image(self):
        book = existing("a" * 24, coverPath=f"data/novels/{'a'*24}/cover.png")
        path = book["metadata"]["coverPath"]
        self.assertEqual(make_plan([cover()], [book], {path: "different"}, {path})[0]["status"],
                         "UPDATE")

    def test_link_preuploaded_image(self):
        book = existing("a" * 24)
        c = cover()
        path = f"data/novels/{book['id']}/cover.png"
        self.assertEqual(make_plan([c], [book], {path: c.digest}, {path})[0]["status"], "LINK")

    def test_duplicate_images_conflict(self):
        book = existing("a" * 24)
        results = make_plan([cover(), cover(filename="NovelFull/second.png")],
                            [book], {}, set())
        self.assertEqual(results[1]["status"], "CONFLICT")

    def test_url_normalization(self):
        self.assertEqual(source_key("https://www.novelfull.com/martial-world.html/"),
                         source_key("http://novelfull.com/martial-world.html"))


if __name__ == "__main__":
    unittest.main()
