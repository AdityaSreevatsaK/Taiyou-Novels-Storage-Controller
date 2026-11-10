import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from taiyou_storage.upload import read_novel, plan, merged_metadata, UploadError


def fixture(folder, name="example.zip", title="Example", author="Author", synopsis="First", chapter="text"):
    epub = io.BytesIO()
    with zipfile.ZipFile(epub, "w") as e:
        e.writestr("mimetype", "application/epub+zip")
        e.writestr("META-INF/container.xml",
                   '<container><rootfile full-path="book.opf"/></container>')
        e.writestr("book.opf", f'<package><metadata><title>{title}</title><creator>{author}</creator></metadata></package>')
        e.writestr("chapter.xhtml", chapter)
    p = folder / name
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("novel/source.epub", epub.getvalue())
        z.writestr("novel/metadata.json", json.dumps({"title": title, "author": author, "synopsis": synopsis}))
    return p


def existing(ident, title="Example", author="Author"):
    return {"id": ident, "metadata": {"id": ident, "title": title, "author": author,
            "personalTags": ["Favourite"], "progress": 33, "rating": 5},
            "epubPath": f"data/novels/{ident}/source.epub",
            "archivePath": f"data/novels/{ident}/original.zip"}


def local_tuple(path):
    meta, epub, digest = read_novel(path)
    return path, meta, epub, digest


class UploadTests(unittest.TestCase):
    def test_metadata_change_updates_existing_id(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first = local_tuple(fixture(root, synopsis="First"))
            ident = hashlib.sha256(first[2]).hexdigest()[:24]
            old = existing(ident)
            archive = old["archivePath"]
            second = local_tuple(fixture(root, synopsis="Revised"))
            output = plan([old], [second], {archive: first[3]}, {archive, old["epubPath"]})
            self.assertEqual(output[0]["state"], "UPDATE")
            self.assertEqual(output[0]["id"], ident)

    def test_epub_change_keeps_id(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first = local_tuple(fixture(root, chapter="first"))
            ident = hashlib.sha256(first[2]).hexdigest()[:24]
            old = existing(ident)
            second = local_tuple(fixture(root, chapter="corrected"))
            output = plan([old], [second], {old["archivePath"]: first[3]},
                          {old["archivePath"], old["epubPath"]})
            self.assertEqual((output[0]["state"], output[0]["id"]), ("UPDATE", ident))

    def test_unchanged_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            local = local_tuple(fixture(Path(d)))
            ident = hashlib.sha256(local[2]).hexdigest()[:24]
            old = existing(ident)
            output = plan([old], [local], {old["archivePath"]: local[3]},
                          {old["archivePath"], old["epubPath"]})
            self.assertEqual(output[0]["state"], "UNCHANGED")

    def test_conflicting_same_title_different_author(self):
        with tempfile.TemporaryDirectory() as d:
            local = local_tuple(fixture(Path(d), author="Different"))
            old = existing("a" * 24)
            result = plan([old], [local], {}, set())
            self.assertEqual(result[0]["state"], "CONFLICT")

    def test_local_duplicates_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            local = [local_tuple(fixture(root, "one.zip")), local_tuple(fixture(root, "two.zip"))]
            states = [x["state"] for x in plan([], local, {}, set())]
            self.assertEqual(states, ["NEW", "CONFLICT"])

    def test_personal_fields_preserved(self):
        old = existing("a" * 24)["metadata"]
        updated = merged_metadata(old, {"title": "Example", "description": "New"}, "a" * 24)
        self.assertEqual(updated["rating"], 5)
        self.assertEqual(updated["personalTags"], ["Favourite"])
        self.assertEqual(updated["progress"], 33)

    def test_invalid_archive_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "invalid.zip"
            path.write_bytes(b"broken")
            with self.assertRaises(UploadError):
                read_novel(path)
