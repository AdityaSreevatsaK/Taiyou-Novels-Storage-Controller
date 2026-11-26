"""Synthetic OPF/ZIP cover extraction and complete guarded batch integration."""
from contextlib import chdir
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from PIL import Image

from taiyou_storage.embedded_covers import (
    attach_embedded_covers, epub_declared_cover, zip_standalone_cover,
)
from taiyou_storage.upload import main as upload_main, plan, read_novel
from tests.test_smoke_integration import FakePrivateHub, REPO, fake_cloud, quiet_run


def image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (220, 320), (155, 90, 70)).save(buffer, format="PNG")
    return buffer.getvalue()


def make_embedded_fixture(root: Path, *, mode: str = "epub",
                          invalid: bool = False,
                          href: str = "Images/cover.png",
                          two_zip_covers: bool = False) -> Path:
    """A novel with a genuine EPUB3 cover declaration or outer cover."""
    ep = BytesIO()
    declared = ("<manifest><item id='cover-art' href='" + href +
                "' properties='cover-image' media-type='image/png'/></manifest>")
    opf = ("<package><metadata><title>Synthetic Embedded Cover</title>"
           "<creator>Test Author</creator></metadata>"
           + declared + "</package>")
    with ZipFile(ep, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml",
                   '<container><rootfile full-path="OEBPS/content.opf"/></container>')
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/chapter.xhtml",
                   "<html><body>Original synthetic text.</body></html>")
        if mode == "epub":
            z.writestr("OEBPS/Images/cover.png",
                       b"not a valid image" if invalid else image_bytes())
    path = root / "synthetic.zip"
    with ZipFile(path, "w") as z:
        z.writestr("novel/source.epub", ep.getvalue())
        z.writestr("novel/metadata.json",
                   json.dumps({"title": "Synthetic Embedded Cover",
                               "author": "Test Author",
                               "source_url": "https://example.invalid/test"}))
        z.writestr("novel/chapters.json",
                   json.dumps([{"title": "One", "file": "chapter.xhtml"}]))
        if mode == "zip":
            z.writestr("novel/cover.png",
                       b"not a valid image" if invalid else image_bytes())
            if two_zip_covers:
                z.writestr("novel/cover.jpg", b"not a valid image")
    return path


class EmbeddedCoverParsingTests(unittest.TestCase):
    def test_epub3_cover_is_valid_and_image_identical(self):
        with TemporaryDirectory() as temp:
            path = make_embedded_fixture(Path(temp))
            _, epub, _ = read_novel(path)
            cover = epub_declared_cover(epub)
            self.assertIsNotNone(cover)
            self.assertEqual(cover[0], image_bytes())
            self.assertEqual(cover[1], ".png")

    def test_zip_standalone_fallback_and_ambiguous_cover_rejected(self):
        with TemporaryDirectory() as temp:
            path = make_embedded_fixture(Path(temp), mode="zip")
            self.assertEqual(zip_standalone_cover(path)[0], image_bytes())
            make_embedded_fixture(Path(temp), mode="zip", two_zip_covers=True)
            self.assertIsNone(zip_standalone_cover(path))

    def test_invalid_image_or_traversal_never_becomes_cover(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for kwargs in ({"invalid": True},
                           {"href": "../Images/cover.png"},
                           {"mode": "zip", "invalid": True}):
                with self.subTest(kwargs=kwargs):
                    path = make_embedded_fixture(root, **kwargs)
                    _, epub, digest = read_novel(path)
                    item = plan([], [(path, read_novel(path)[0], epub, digest)],
                                {}, set())[0]
                    rows, missing = attach_embedded_covers([item])
                    self.assertEqual(rows, [])
                    self.assertEqual(missing, 1)
                    self.assertNotIn("cover", item)

    def test_never_overwrite_existing_cover_or_explicit_sidecar(self):
        with TemporaryDirectory() as temp:
            path = make_embedded_fixture(Path(temp))
            meta, epub, digest = read_novel(path)
            items = plan([], [(path, meta, epub, digest)], {}, set())
            item = items[0]
            fake_existing = {"metadata": {"coverPath": item["directory"] + "/cover.jpg"}}
            item["existing"] = fake_existing
            rows, missing = attach_embedded_covers(items)
            self.assertEqual((len(rows), missing), (0, 0))
            self.assertNotIn("cover", item)
            item["existing"] = None
            item["cover"] = {"novel_id": item["id"], "kind": "local-sidecar"}
            attach_embedded_covers(items)
            self.assertEqual(item["cover"]["kind"], "local-sidecar")

    def test_missing_cover_does_not_block_novel_import(self):
        with TemporaryDirectory() as temp:
            path = make_embedded_fixture(Path(temp), mode="zip", invalid=True)
            meta, epub, digest = read_novel(path)
            items = plan([], [(path, meta, epub, digest)], {}, set())
            rows, missing = attach_embedded_covers(items)
            self.assertEqual(rows, [])
            self.assertEqual(missing, 1)


class EmbeddedCoverIntegrationTests(unittest.TestCase):
    def test_atomic_upload_preview_idempotence_and_existing_book_cover_only(self):
        with TemporaryDirectory() as temp, chdir(temp):
            root = Path(temp)
            novels = root / "novels"
            novels.mkdir()
            make_embedded_fixture(novels)
            hub = FakePrivateHub(root)
            args = [str(novels), "--repo", REPO]
            with fake_cloud(hub):
                # First store original EPUB/ZIP without artwork.
                status, out = quiet_run(upload_main, args + ["--no-covers", "--apply"])
                self.assertEqual(status, 0, out)
                self.assertEqual(len(hub.commits), 1)
                original = hub.books()[0]
                book_id = original["id"]
                self.assertFalse(original["metadata"].get("coverPath"))

                status, out = quiet_run(upload_main, args)
                self.assertEqual(status, 0, out)
                self.assertIn("Extracted embedded covers", out)
                self.assertIn("Covers to link", out)
                self.assertEqual(len(hub.commits), 1)
                status, out = quiet_run(upload_main, args + ["--apply"])
                self.assertEqual(status, 0, out)
                self.assertEqual(len(hub.commits), 2)
                updated = hub.books()[0]
                self.assertEqual(updated["id"], book_id)
                cover_path = updated["metadata"]["coverPath"]
                self.assertTrue(cover_path.endswith("/cover.png"))
                self.assertEqual(hub.files[cover_path], image_bytes())
                self.assertIn(cover_path, hub.commits[-1])
                self.assertIn("data/library.json", hub.commits[-1])
                status, out = quiet_run(upload_main, args + ["--apply"])
                self.assertEqual(status, 0, out)
                self.assertEqual(len(hub.commits), 2)

    def test_remote_unlinked_different_cover_blocks_all_writes(self):
        with TemporaryDirectory() as temp, chdir(temp):
            root = Path(temp)
            novels = root / "novels"
            novels.mkdir()
            path = make_embedded_fixture(novels)
            meta, epub, digest = read_novel(path)
            item = plan([], [(path, meta, epub, digest)], {}, set(), readable_new=True)[0]
            target = item["directory"] + "/cover.png"
            hub = FakePrivateHub(root)
            hub.inject(target, b"different existing cover contents")
            with fake_cloud(hub):
                status, out = quiet_run(upload_main, [str(novels), "--repo", REPO, "--apply"])
                self.assertEqual(status, 2, out)
                self.assertEqual(hub.commits, [])
                self.assertNotIn("data/library.json", hub.files)

    def test_true_new_novel_and_cover_share_one_commit(self):
        with TemporaryDirectory() as temp, chdir(temp):
            root = Path(temp)
            novels = root / "novels"
            novels.mkdir()
            make_embedded_fixture(novels, mode="zip")
            hub = FakePrivateHub(root)
            with fake_cloud(hub):
                status, output = quiet_run(upload_main,
                    [str(novels), "--repo", REPO, "--apply"])
                self.assertEqual(status, 0, output)
                self.assertEqual(len(hub.commits), 1)
                book = hub.books()[0]
                self.assertIn(book["metadata"]["coverPath"], hub.files)
                self.assertIn("source.epub", " ".join(hub.commits[0]))
                self.assertIn("original.zip", " ".join(hub.commits[0]))
                self.assertIn("data/library.json", hub.commits[0])

if __name__ == "__main__":
    unittest.main()
