"""Mocked offline tests: local ZIP deduplication must never weaken HF upload safety."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from taiyou_storage.local_dedupe import canonical_source, preflight, verified_remote_upgrade
from taiyou_storage.upload import (UploadError, main, matching_entry,
                                   merged_metadata, plan, read_novel)


def _fixture_writestr(archive: ZipFile, name: str, content) -> None:
    # Fixed ZIP timestamps keep EPUB-derived identities deterministic on Windows.
    archive.writestr(ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0)), content)


def sample(root: Path, filename: str, *, chapter: str = "An original chapter",
           url: str = "https://novelfull.com/example.html",
           timestamp: str = "2026-11-14T12:00:00Z",
           with_cover: bool = False, epub_cover_marker: bool = False) -> Path:
    original = io.BytesIO()
    with ZipFile(original, "w") as epub:
        _fixture_writestr(epub, "mimetype", "application/epub+zip")
        _fixture_writestr(epub, "META-INF/container.xml",
                      '<container><rootfile full-path="book.opf"/></container>')
        _fixture_writestr(epub, "book.opf",
                      '<package><metadata><title>Example</title><creator>Author</creator></metadata></package>')
        _fixture_writestr(epub, "chapter.xhtml", chapter)
        if epub_cover_marker:
            _fixture_writestr(epub, "OEBPS/cover.jpg", b"\xff\xd8\xff" + bytes(200))
    row = [{"position": 1, "file": "chapter_00001.txt",
            "sha256": hashlib.sha256(chapter.encode()).hexdigest()}]
    meta = {"title": "Example", "author": "Author", "source_url": url,
            "chapter_count": 1, "created_at_utc": timestamp}
    if with_cover:
        meta["cover_image"] = "cover.jpg"
    path = root / filename
    with ZipFile(path, "w") as archive:
        _fixture_writestr(archive, "novel/source.epub", original.getvalue())
        _fixture_writestr(archive, "novel/metadata.json", json.dumps(meta))
        _fixture_writestr(archive, "novel/chapters.json", json.dumps(row))
        _fixture_writestr(archive, "novel/chapter_00001.txt", chapter)
        if with_cover:
            _fixture_writestr(archive, "novel/cover.jpg", b"\xff\xd8\xff" + bytes(200))
    return path


def local(path):
    return (path, *read_novel(path))


def remote(ident="a" * 24, *, url="https://novelfull.com/example.html"):
    meta = {"id": ident, "title": "Example", "author": "Author",
            "sourceUrl": url, "progress": 58, "rating": 5, "comments": ["Loved it"],
            "personalTags": ["Favourite"], "collections": ["Cultivation"],
            "notes": "Reader note", "lastRead": 100}
    return {"id": ident, "metadata": meta,
            "epubPath": f"data/novels/{ident}/source.epub",
            "archivePath": f"data/novels/{ident}/original.zip"}


class LocalDeduplicationTests(unittest.TestCase):
    def test_canonical_source_matches_scribble_hub_series_alias(self):
        self.assertEqual(
            canonical_source("https://www.scribblehub.com/series/445037/example/"),
            canonical_source("https://scribblehub.com/series/445037/")
        )
        self.assertEqual(canonical_source("http://example.org/book"), "")

    def test_renamed_archives_deduplicated_by_content(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            old = sample(folder, "old.zip")
            new = sample(folder, "new-archive-name.zip",
                         timestamp="2026-11-16T12:00:00Z")
            chosen, duplicates, conflicts = preflight([local(old), local(new)], [])
            self.assertEqual(len(chosen), 1)
            self.assertEqual(chosen[0][0], new)
            self.assertEqual(len(duplicates), 1)
            self.assertEqual(conflicts, [])
            self.assertTrue(old.exists())

    def test_conflicting_chapter_editions_block_without_removing_files(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            original = sample(folder, "old.zip")
            changed = sample(folder, "changed.zip", chapter="Completely changed text")
            chosen, duplicates, conflicts = preflight([local(original), local(changed)], [])
            self.assertEqual(chosen, [])
            self.assertEqual(len(conflicts), 1)
            self.assertTrue(original.exists())
            self.assertTrue(changed.exists())

    def test_unverified_source_change_not_silently_imported(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            item = local(sample(folder, "new.zip", url="https://novelfull.com/other.html"))
            match = remote()
            with self.assertRaisesRegex(UploadError, "different canonical source URL"):
                matching_entry([match], item[1], item[2])

    def test_canonical_source_preserves_old_hf_id_despite_new_epub(self):
        with tempfile.TemporaryDirectory() as d:
            path = sample(Path(d), "cover-rewritten.zip")
            item = local(path)
            stored = remote()
            result = plan([stored], [item], {}, {stored["epubPath"], stored["archivePath"]})
            self.assertEqual(result[0]["id"], stored["id"])
            self.assertEqual(result[0]["reason"], "source-url")
            self.assertEqual(result[0]["state"], "UPDATE")

    def test_reader_owned_fields_cannot_be_overwritten_by_new_zip_metadata(self):
        original = remote()["metadata"]
        incoming = {
            "title": "Updated title", "progress": 0, "rating": 0,
            "comments": [], "personalTags": [], "collections": [],
            "notes": "", "lastRead": 0, "chapterCount": 200,
        }
        output = merged_metadata(original, incoming, original["id"])
        for key in ("progress", "rating", "comments", "personalTags",
                    "collections", "notes", "lastRead"):
            self.assertEqual(output[key], original[key])
        self.assertEqual(output["chapterCount"], 200)

    def test_duplicate_archive_in_optin_preview_makes_no_remote_writes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sample(root, "old.zip")
            sample(root, "new.zip", timestamp="2026-11-16T12:00:00Z")
            with (patch("taiyou_storage.core.load_remote", return_value=([], "a" * 40)),
                  patch("huggingface_hub.HfApi") as factory):
                factory.return_value.list_repo_files.return_value = [".gitattributes"]
                self.assertEqual(main([str(root), "--dedupe-local"]), 0)
                factory.return_value.create_commit.assert_not_called()

    def test_conflicts_in_optin_preview_block_apply(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sample(root, "old.zip")
            sample(root, "new.zip", chapter="Changed chapter text")
            with (patch("taiyou_storage.core.load_remote", return_value=([], "a" * 40)),
                  patch("huggingface_hub.HfApi") as factory):
                self.assertEqual(main([str(root), "--dedupe-local", "--apply"]), 2)
                factory.return_value.create_commit.assert_not_called()

    def test_cover_only_epub_change_allowed_against_existing_remote(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            old = sample(root, "remote.zip")
            new = sample(root, "new.zip", epub_cover_marker=True)
            self.assertTrue(verified_remote_upgrade(local(new), old))
            self.assertNotEqual(local(new)[2], local(old)[2])

    def test_changed_remote_chapter_requires_explicit_resolution(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            old = sample(root, "remote.zip", chapter="Previously saved chapter")
            new = sample(root, "new.zip", chapter="Unrelated replacement text")
            self.assertFalse(verified_remote_upgrade(local(new), old))

    def test_remote_edition_conflict_blocks_all_uploads(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            old = sample(root, "original.zip", chapter="Previously saved chapter")
            root2 = root / "incoming"
            root2.mkdir()
            sample(root2, "new.zip", chapter="Unrelated replacement text")
            remote_entry = remote()
            old_epub = root / "remote.epub"
            with ZipFile(old) as book:
                old_epub.write_bytes(book.read("novel/source.epub"))
            def fake_download(*args, **kwargs):
                return str(old if kwargs["filename"] == remote_entry["archivePath"] else old_epub)
            with (patch("taiyou_storage.core.load_remote",
                        return_value=([remote_entry], "a" * 40)),
                  patch("huggingface_hub.HfApi") as factory,
                  patch("huggingface_hub.hf_hub_download", side_effect=fake_download)):
                factory.return_value.list_repo_files.return_value = [
                    "data/library.json", remote_entry["archivePath"], remote_entry["epubPath"]]
                self.assertEqual(main([str(root2), "--dedupe-local", "--apply"]), 2)
                factory.return_value.create_commit.assert_not_called()

    def test_original_default_mode_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            paths = [local(sample(root, "old.zip")), local(sample(root, "new.zip"))]
            states = [item["state"] for item in plan([], paths, {}, set())]
            self.assertEqual(states, ["NEW", "CONFLICT"])

    def test_forged_chapter_hash_blocks_entire_preflight(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = sample(root, "bad.zip")
            with ZipFile(path, "r") as archive:
                data = {name: archive.read(name) for name in archive.namelist()}
            rows = json.loads(data["novel/chapters.json"])
            rows[0]["sha256"] = "0" * 64
            data["novel/chapters.json"] = json.dumps(rows).encode()
            with ZipFile(path, "w") as archive:
                for name, body in data.items():
                    archive.writestr(name, body)
            with self.assertRaisesRegex(UploadError, "checksum mismatch"):
                preflight([local(path)], [])


if __name__ == "__main__":
    unittest.main()
