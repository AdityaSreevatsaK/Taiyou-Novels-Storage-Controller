"""Offline end-to-end smoke tests for the public Storage Controller.

Exercise actual upload, cover and reset-preview entrypoints against a fake
private HF dataset. Never use credentials or touch an external service.
"""
from contextlib import contextmanager, redirect_stdout, chdir
from copy import deepcopy
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import json
import unittest
import zipfile

from taiyou_storage.core import validate_catalogue
from taiyou_storage.upload import main as upload_main, read_novel
from taiyou_storage.covers import run as covers_run
from taiyou_storage.reset import run as reset_run

REPO = "test-owner/private-storage-smoke"
PNG_END = b"IEND\xaeB\x60\x82"


def make_novel(folder: Path, filename: str, title: str, source_url: str) -> Path:
    epub_buffer = BytesIO()
    with zipfile.ZipFile(epub_buffer, "w") as epub:
        epub.writestr("mimetype", "application/epub+zip")
        epub.writestr("META-INF/container.xml",
                      '<container><rootfile full-path="book.opf"/></container>')
        epub.writestr(
            "book.opf",
            "<package><metadata><title>" + title +
            "</title><creator>Smoke Author</creator></metadata></package>")
        epub.writestr("chapter.xhtml", "<p>Only synthetic test content.</p>")
    target = folder / filename
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("chapters/source.epub", epub_buffer.getvalue())
        archive.writestr("chapters/metadata.json", json.dumps({
            "title": title, "author": "Smoke Author",
            "description": "Synthetic fixture", "source_url": source_url,
            "tags": ["Cultivation"],
        }))
        archive.writestr("chapters/chapters.json", json.dumps([
            {"title": "First chapter", "file": "chapters/001.txt"},
        ]))
        archive.writestr("chapters/001.txt", "Only synthetic test content.")
    return target


def make_cover_archive(path: Path, records: list[tuple[str, str]]) -> Path:
    manifest = []
    with zipfile.ZipFile(path, "w") as archive:
        for index, (title, url) in enumerate(records):
            name = "NovelFull/cover-%d.png" % index
            image = b"\x89PNG\r\n\x1a\n" + bytes([index + 1]) * 24 + PNG_END
            archive.writestr(name, image)
            manifest.append({
                "title": title, "source_url": url, "website": "NovelFull",
                "cover_file": name,
            })
        archive.writestr("covers_manifest.json", json.dumps(manifest))
    return path


class FakePrivateHub:
    """Revisioned in-memory Hub with immutable snapshots and commit CAS."""

    def __init__(self, root: Path):
        self.root = root
        self.sha = "a" * 40
        self.sequence = 0
        self.snapshots = {self.sha: {".gitattributes": b""}}
        self.commits = []
        self.downloads = []
        self.fail_commit_number = None

    @property
    def files(self):
        return self.snapshots[self.sha]

    def dataset_info(self, repo, token=None):
        self.assert_repo(repo)
        return SimpleNamespace(private=True, sha=self.sha)

    def assert_repo(self, repo):
        if repo != REPO:
            raise AssertionError("Unexpected HF repository: " + str(repo))

    def list_repo_files(self, repo_id, repo_type, revision, token=None):
        self.assert_repo(repo_id)
        if repo_type != "dataset":
            raise AssertionError("Not a dataset")
        return sorted(self.snapshots[revision])

    def download(self, repo_id, repo_type, filename, revision, token=None):
        self.assert_repo(repo_id)
        if repo_type != "dataset":
            raise AssertionError("Not a dataset")
        self.downloads.append(filename)
        content = self.snapshots[revision][filename]
        local = self.root / "fake_hf_cache" / revision / filename
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(content)
        return str(local)

    def load_remote(self, repo, token=None, *, allow_empty=False):
        self.assert_repo(repo)
        if "data/library.json" not in self.files:
            if any(name.startswith("data/") for name in self.files) or not allow_empty:
                raise AssertionError("Unexpected absent catalogue")
            return [], self.sha
        source = json.loads(self.files["data/library.json"])
        return validate_catalogue(source), self.sha

    def _new_revision(self, files):
        self.sequence += 1
        self.sha = "%040x" % self.sequence
        self.snapshots[self.sha] = files

    def inject(self, name, content):
        """Simulate an external writer/corruption without running the uploader."""
        updated = dict(self.files)
        updated[name] = content
        self._new_revision(updated)

    def create_commit(self, **kwargs):
        self.assert_repo(kwargs["repo_id"])
        if kwargs["repo_type"] != "dataset":
            raise AssertionError("Wrong repository type")
        if kwargs.get("parent_commit") != self.sha:
            raise AssertionError("Missing or stale parent revision")
        if (self.fail_commit_number is not None and
                len(self.commits) + 1 == self.fail_commit_number):
            raise RuntimeError("Simulated HF failure before committing")
        updated = dict(self.files)
        names = []
        for operation in kwargs["operations"]:
            name = operation.path_in_repo
            names.append(name)
            if type(operation).__name__ == "CommitOperationDelete":
                updated.pop(name, None)
            else:
                source = operation.path_or_fileobj
                if isinstance(source, (str, Path)):
                    updated[name] = Path(source).read_bytes()
                else:
                    updated[name] = source.getvalue()
        self.commits.append(names)
        self._new_revision(updated)
        return SimpleNamespace(oid=self.sha)

    def books(self):
        return deepcopy(json.loads(self.files["data/library.json"])["books"])


@contextmanager
def fake_cloud(hub):
    with patch("huggingface_hub.HfApi", return_value=hub), \
            patch("huggingface_hub.hf_hub_download", side_effect=hub.download), \
            patch("huggingface_hub.get_token", return_value="test-only-token"), \
            patch("taiyou_storage.core.load_remote", side_effect=hub.load_remote):
        yield


def quiet_run(function, arguments):
    stream = StringIO()
    with redirect_stdout(stream):
        result = function(arguments)
    return result, stream.getvalue()


class EndToEndSmokeTests(unittest.TestCase):
    def test_new_novels_preview_apply_idempotence_and_corrupted_epub_repair(self):
        with TemporaryDirectory() as folder, chdir(folder):
            root = Path(folder)
            novels = root / "novels"
            novels.mkdir()
            first = make_novel(novels, "novel-a.zip", "Smoke Novel A",
                               "https://novelfull.com/smoke-novel-a.html")
            make_novel(novels, "novel-b.zip", "Smoke Novel B",
                       "https://novelfull.com/smoke-novel-b.html")
            hub = FakePrivateHub(root)
            with fake_cloud(hub):
                result, output = quiet_run(upload_main, [str(novels), "--repo", REPO])
                self.assertEqual(result, 0)
                self.assertEqual(output.count("[NEW]"), 2)
                self.assertEqual(len(hub.commits), 0)

                with patch("taiyou_storage.upload.sys.stdin") as stdin, \
                        patch("builtins.input", return_value="YES"):
                    stdin.isatty.return_value = True
                    result, _ = quiet_run(upload_main, [
                        str(novels), "--repo", REPO, "--interactive"])
                self.assertEqual(result, 0)
                self.assertEqual(len(hub.commits), 2)
                books = hub.books()
                self.assertEqual(len(books), 2)
                self.assertEqual(len([p for p in hub.files if p.endswith("source.epub")]), 2)

                hub.downloads.clear()
                result, output = quiet_run(upload_main, [str(novels), "--repo", REPO])
                self.assertEqual(result, 0)
                self.assertEqual(output.count("[UNCHANGED]"), 2)
                self.assertEqual(len(hub.commits), 2)
                self.assertEqual(len(hub.downloads), 4)
                self.assertEqual(
                    set(hub.downloads),
                    {p for p in hub.files if p.endswith(("source.epub", "original.zip"))})

                book_a = next(b for b in books if b["metadata"]["title"] == "Smoke Novel A")
                catalogue = json.loads(hub.files["data/library.json"])
                for b in catalogue["books"]:
                    if b["id"] == book_a["id"]:
                        b["metadata"]["personalRating"] = 9
                        b["metadata"]["personalTags"] = ["Favourite"]
                        b["metadata"]["progress"] = 21
                hub.inject("data/library.json", json.dumps(catalogue).encode())
                hub.inject(book_a["epubPath"], b"corrupted remote EPUB")

                result, output = quiet_run(upload_main, [str(novels), "--repo", REPO])
                self.assertEqual(result, 0)
                self.assertIn("[UPDATE] novel-a.zip", output)
                initial_commits = len(hub.commits)
                result, _ = quiet_run(upload_main, [
                    str(novels), "--repo", REPO, "--apply"])
                self.assertEqual(result, 0)
                self.assertEqual(len(hub.commits), initial_commits + 1)
                self.assertIn(book_a["epubPath"], hub.commits[-1])
                self.assertNotIn(book_a["archivePath"], hub.commits[-1])
                restored = next(b for b in hub.books() if b["id"] == book_a["id"])
                self.assertEqual(restored["metadata"]["personalRating"], 9)
                self.assertEqual(restored["metadata"]["personalTags"], ["Favourite"])
                self.assertEqual(restored["metadata"]["progress"], 21)
                with zipfile.ZipFile(first) as archive:
                    expected = archive.read("chapters/source.epub")
                self.assertEqual(hub.files[book_a["epubPath"]], expected)

    def test_cover_batches_resume_after_failure_without_duplicate_commits(self):
        with TemporaryDirectory() as folder, chdir(folder):
            root = Path(folder)
            novels = root / "novels"
            novels.mkdir()
            records = [
                ("Smoke Novel A", "https://novelfull.com/smoke-novel-a.html"),
                ("Smoke Novel B", "https://novelfull.com/smoke-novel-b.html"),
            ]
            for index, (title, url) in enumerate(records):
                make_novel(novels, "novel-%d.zip" % index, title, url)
            cover_zip = make_cover_archive(root / "covers.zip", records)
            hub = FakePrivateHub(root)
            with fake_cloud(hub):
                result, _ = quiet_run(upload_main, [str(novels), "--repo", REPO, "--apply"])
                self.assertEqual(result, 0)
                baseline = len(hub.commits)
                args = [str(cover_zip), "--repo", REPO,
                        "--report", str(root / "cover-report.csv"),
                        "--batch-size", "1", "--commit-pause", "0"]
                result, output = quiet_run(covers_run, args)
                self.assertEqual(result, 0)
                self.assertIn("NEW=2", output)
                self.assertEqual(len(hub.commits), baseline)

                hub.fail_commit_number = baseline + 2
                result, _ = quiet_run(covers_run, args + ["--apply"])
                self.assertEqual(result, 1)
                self.assertEqual(len(hub.commits), baseline + 1)
                self.assertEqual(sum("coverPath" in b["metadata"] for b in hub.books()), 1)

                hub.fail_commit_number = None
                result, output = quiet_run(covers_run, args + ["--apply"])
                self.assertEqual(result, 0)
                self.assertIn("UNCHANGED", output)
                self.assertEqual(len(hub.commits), baseline + 2)
                self.assertEqual(sum("coverPath" in b["metadata"] for b in hub.books()), 2)

                count_before = len(hub.commits)
                result, output = quiet_run(covers_run, args)
                self.assertEqual(result, 0)
                self.assertIn("UNCHANGED=2", output)
                self.assertEqual(len(hub.commits), count_before)

    def test_full_reset_preview_never_deletes_data(self):
        with TemporaryDirectory() as folder, chdir(folder):
            root = Path(folder)
            novels = root / "novels"
            novels.mkdir()
            make_novel(novels, "novel.zip", "Smoke Novel A",
                       "https://novelfull.com/smoke-novel-a.html")
            hub = FakePrivateHub(root)
            with fake_cloud(hub):
                result, _ = quiet_run(upload_main, [str(novels), "--repo", REPO, "--apply"])
                self.assertEqual(result, 0)
                original = dict(hub.files)
                count = len(hub.commits)
                with patch("builtins.input", side_effect=AssertionError("Prompted in preview")):
                    result, output = quiet_run(reset_run, ["--repo", REPO])
                self.assertEqual(result, 0)
                self.assertIn("PREVIEW ONLY", output)
                self.assertEqual(hub.files, original)
                self.assertEqual(len(hub.commits), count)


if __name__ == "__main__":
    unittest.main()
