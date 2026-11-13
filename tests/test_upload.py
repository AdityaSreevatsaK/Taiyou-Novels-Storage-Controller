import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import zipfile

from taiyou_storage.upload import (
    read_novel, plan, merged_metadata, validate_zip_budget, UploadError,
    MAX_ZIP_ENTRIES, MAX_ZIP_EXPANDED,
)


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
            old["metadata"] = merged_metadata(old["metadata"], local[1], ident)
            output = plan([old], [local], {
                old["archivePath"]: local[3],
                old["epubPath"]: hashlib.sha256(local[2]).hexdigest(),
            }, {old["archivePath"], old["epubPath"]})
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


    def test_restored_genres_survive_zip_without_source_tags(self):
        ident = "a" * 24
        old = existing(ident)["metadata"]
        old["sourceTags"] = ["Cultivation", "Xianxia"]
        updated = merged_metadata(old, {"title": "Example", "sourceTags": []}, ident)
        self.assertEqual(updated["sourceTags"], ["Cultivation", "Xianxia"])

    def test_first_upload_initialises_catalogue_and_epub_atomically(self):
        from taiyou_storage.upload import apply_item
        with tempfile.TemporaryDirectory() as folder:
            local = local_tuple(fixture(Path(folder)))
            item = plan([], [local], {}, {".gitattributes"})[0]
            self.assertEqual(item["state"], "NEW")
            api = MagicMock()
            api.dataset_info.return_value = SimpleNamespace(
                private=True, sha="c" * 40)
            api.list_repo_files.return_value = [".gitattributes", "README.md"]
            with patch("huggingface_hub.hf_hub_download") as download:
                self.assertEqual(apply_item(api, "owner/private", "token", item), "NEW")
                download.assert_not_called()
            api.create_commit.assert_called_once()
            kwargs = api.create_commit.call_args.kwargs
            self.assertEqual(kwargs["parent_commit"], "c" * 40)
            by_path = {op.path_in_repo: op for op in kwargs["operations"]}
            novel_id = item["id"]
            self.assertIn(f"data/novels/{novel_id}/source.epub", by_path)
            self.assertIn(f"data/novels/{novel_id}/original.zip", by_path)
            catalogue = json.loads(by_path["data/library.json"].path_or_fileobj.getvalue())
            self.assertEqual(catalogue["version"], 1)
            self.assertEqual(len(catalogue["books"]), 1)
            self.assertEqual(catalogue["books"][0]["id"], novel_id)

    def test_missing_catalogue_with_remote_data_blocks_first_commit(self):
        from taiyou_storage.upload import apply_item
        with tempfile.TemporaryDirectory() as folder:
            local = local_tuple(fixture(Path(folder)))
            item = plan([], [local], {}, set())[0]
            api = MagicMock()
            api.dataset_info.return_value = SimpleNamespace(private=True, sha="c" * 40)
            api.list_repo_files.return_value = [
                "data/novels/aaaaaaaaaaaaaaaaaaaaaaaa/original.zip"]
            with self.assertRaisesRegex(UploadError, "orphaned data"):
                apply_item(api, "owner/private", "token", item)
            api.create_commit.assert_not_called()

    def test_interactive_rejection_makes_no_cloud_write(self):
        from taiyou_storage.upload import main
        with tempfile.TemporaryDirectory() as folder:
            fixture(Path(folder))
            with patch("taiyou_storage.core.load_remote", return_value=([], "a" * 40)), \
                    patch("huggingface_hub.HfApi") as api_type, \
                    patch("taiyou_storage.upload.sys.stdin") as stdin, \
                    patch("builtins.input", return_value="NO"):
                stdin.isatty.return_value = True
                api_type.return_value.list_repo_files.return_value = [".gitattributes"]
                self.assertEqual(main([folder, "--interactive"]), 0)
                api_type.return_value.create_commit.assert_not_called()

    def test_main_preview_on_brand_new_empty_dataset_never_writes(self):
        from taiyou_storage.upload import main, plan as actual_plan
        with tempfile.TemporaryDirectory() as folder:
            fixture(Path(folder))
            with patch("taiyou_storage.core.load_remote", return_value=([], "d" * 40)) as load, \
                    patch("huggingface_hub.HfApi") as factory, \
                    patch("taiyou_storage.upload.plan", wraps=actual_plan) as planner:
                api = factory.return_value
                api.list_repo_files.return_value = [".gitattributes", "README.md"]
                self.assertEqual(main([folder]), 0)
                self.assertIs(planner.call_args.kwargs["readable_new"], True)
                self.assertEqual(main([folder, "--legacy-new-folders"]), 0)
                self.assertIs(planner.call_args.kwargs["readable_new"], False)
                load.assert_called_with(
                    "AdityaSreevatsaK/Taiyous-Novels", allow_empty=True)
                api.create_commit.assert_not_called()


    def test_matching_archive_does_not_hide_corrupt_epub(self):
        with tempfile.TemporaryDirectory() as d:
            local = local_tuple(fixture(Path(d)))
            ident = hashlib.sha256(local[2]).hexdigest()[:24]
            old = existing(ident)
            old["metadata"] = merged_metadata(old["metadata"], local[1], ident)
            result = plan([old], [local], {
                old["archivePath"]: local[3],
                old["epubPath"]: hashlib.sha256(b"corrupted").hexdigest(),
            }, {old["archivePath"], old["epubPath"]})
            self.assertEqual(result[0]["state"], "UPDATE")

    def test_matching_artifacts_do_not_hide_catalogue_metadata_drift(self):
        with tempfile.TemporaryDirectory() as d:
            local = local_tuple(fixture(Path(d)))
            ident = hashlib.sha256(local[2]).hexdigest()[:24]
            old = existing(ident)
            old["metadata"] = merged_metadata(old["metadata"], local[1], ident)
            old["metadata"]["description"] = "stale"
            result = plan([old], [local], {
                old["archivePath"]: local[3],
                old["epubPath"]: hashlib.sha256(local[2]).hexdigest(),
            }, {old["archivePath"], old["epubPath"]})
            self.assertEqual(result[0]["state"], "UPDATE")

    def test_metadata_only_repair_uploads_catalogue_not_binary_artifacts(self):
        from taiyou_storage.upload import apply_item
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            local = local_tuple(fixture(root))
            ident = hashlib.sha256(local[2]).hexdigest()[:24]
            old = existing(ident)
            old["metadata"] = merged_metadata(old["metadata"], local[1], ident)
            old["metadata"]["description"] = "old"
            cat = root / "library.json"
            cat.write_text(json.dumps({"version": 1, "books": [old]}), encoding="utf-8")
            remote_epub = root / "remote.epub"
            remote_epub.write_bytes(local[2])
            item = plan([old], [local], {}, set())[0]
            api = MagicMock()
            api.dataset_info.return_value = SimpleNamespace(private=True, sha="a" * 40)
            api.list_repo_files.return_value = [
                "data/library.json", old["archivePath"], old["epubPath"]]
            def download(*args, **kwargs):
                name = kwargs["filename"]
                return str(cat if name == "data/library.json" else
                           local[0] if name == old["archivePath"] else remote_epub)
            with patch("huggingface_hub.hf_hub_download", side_effect=download):
                self.assertEqual(apply_item(api, "owner/private", "token", item), "UPDATED")
            ops = [x.path_in_repo for x in api.create_commit.call_args.kwargs["operations"]]
            self.assertEqual(ops, ["data/library.json"])

    def test_corrupt_remote_epub_is_reuploaded(self):
        from taiyou_storage.upload import apply_item
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            local = local_tuple(fixture(root))
            ident = hashlib.sha256(local[2]).hexdigest()[:24]
            old = existing(ident)
            old["metadata"] = merged_metadata(old["metadata"], local[1], ident)
            cat = root / "library.json"
            cat.write_text(json.dumps({"version": 1, "books": [old]}), encoding="utf-8")
            remote_epub = root / "remote.epub"
            remote_epub.write_bytes(b"stale")
            item = plan([old], [local], {}, set())[0]
            api = MagicMock()
            api.dataset_info.return_value = SimpleNamespace(private=True, sha="a" * 40)
            api.list_repo_files.return_value = [
                "data/library.json", old["archivePath"], old["epubPath"]]
            def download(*args, **kwargs):
                name = kwargs["filename"]
                return str(cat if name == "data/library.json" else
                           local[0] if name == old["archivePath"] else remote_epub)
            with patch("huggingface_hub.hf_hub_download", side_effect=download):
                self.assertEqual(apply_item(api, "owner/private", "token", item), "UPDATED")
            ops = [x.path_in_repo for x in api.create_commit.call_args.kwargs["operations"]]
            self.assertIn(old["epubPath"], ops)
            self.assertNotIn(old["archivePath"], ops)

    def test_zip_entry_budget_checked_before_decompression(self):
        info = SimpleNamespace(filename="chapter.txt", flag_bits=0,
                               file_size=1, compress_size=1, is_dir=lambda: False)
        z = SimpleNamespace(infolist=lambda: [info] * (MAX_ZIP_ENTRIES + 1))
        with self.assertRaisesRegex(UploadError, "Too many"):
            validate_zip_budget(z)

    def test_zip_expansion_budget_checked_before_decompression(self):
        info = SimpleNamespace(filename="chapter.txt", flag_bits=0,
                               file_size=MAX_ZIP_EXPANDED + 1,
                               compress_size=MAX_ZIP_EXPANDED + 1,
                               is_dir=lambda: False)
        with self.assertRaisesRegex(UploadError, "expanded data"):
            validate_zip_budget(SimpleNamespace(infolist=lambda: [info]))

    def test_preview_revision_drift_refuses_to_commit(self):
        from taiyou_storage.upload import apply_item
        with tempfile.TemporaryDirectory() as d:
            local = local_tuple(fixture(Path(d)))
            item = plan([], [local], {}, set())[0]
            api = MagicMock()
            api.dataset_info.return_value = SimpleNamespace(private=True, sha="b" * 40)
            with self.assertRaisesRegex(UploadError, "changed since preview"):
                apply_item(api, "owner/private", "token", item,
                           expected_revision="a" * 40, return_revision=True)
            api.create_commit.assert_not_called()

    def test_changed_local_zip_refuses_commit(self):
        from taiyou_storage.upload import apply_item
        with tempfile.TemporaryDirectory() as d:
            local = local_tuple(fixture(Path(d)))
            item = plan([], [local], {}, set())[0]
            item["path"].write_bytes(b"changed")
            api = MagicMock()
            api.dataset_info.return_value = SimpleNamespace(private=True, sha="a" * 40)
            api.list_repo_files.return_value = []
            with self.assertRaisesRegex(UploadError, "Local ZIP changed"):
                apply_item(api, "owner/private", "token", item)
            api.create_commit.assert_not_called()

    def test_invalid_archive_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "invalid.zip"
            path.write_bytes(b"broken")
            with self.assertRaises(UploadError):
                read_novel(path)
