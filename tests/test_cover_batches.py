"""Offline regression tests for batched and resume-safe cover uploads."""
from hashlib import sha256
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from taiyou_storage.cover_batches import (
    MAX_SHORT_RETRY, commit_cover_batch, group_batches, upload_batches,
)
from taiyou_storage.covers import Cover, CoverError, make_plan

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24 + b"\x00\x00\x00\x00IEND\xaeB\x60\x82"


def book(index: int, *, linked: bool = False):
    ident = f"{index:024x}"
    url = f"https://novelfull.com/novel-{index}.html"
    metadata = {
        "id": ident, "title": f"Novel {index}",
        "sourceUrl": url, "author": "Author",
        "progress": index, "personalRating": 9,
        "personalTags": ["Favourite"],
    }
    if linked:
        metadata["coverPath"] = f"data/novels/{ident}/cover.png"
    return {
        "id": ident, "metadata": metadata,
        "epubPath": f"data/novels/{ident}/source.epub",
        "archivePath": f"data/novels/{ident}/original.zip",
    }


def cover(index: int):
    # Use different bytes and SHA256 for different books.
    data = PNG + bytes([index % 255])
    return Cover(
        f"Novel {index}", "NovelFull",
        f"https://novelfull.com/novel-{index}.html",
        f"NovelFull/novel-{index}.png", ".png", data,
        sha256(data).hexdigest(),
    )


class FakeHub:
    def __init__(self, root, books, *, present=()):
        self.root = Path(root)
        self.books = books
        self.sha = "a" * 40
        self.files = {
            "data/library.json":
                (json.dumps({"version": 1, "books": books}) + "\n").encode("utf-8"),
        }
        for n in present:
            ident = books[n - 1]["id"]
            self.files[f"data/novels/{ident}/cover.png"] = cover(n).data
        self.commits = []
        self.raise_on_commit = None
        self.is_private = True

    def dataset_info(self, repo, token):
        return SimpleNamespace(private=self.is_private, sha=self.sha)

    def list_repo_files(self, repo_id, repo_type, revision, token):
        if revision != self.sha:
            raise AssertionError("Stale revision used for file list")
        return list(self.files)

    def download(self, repo_id, repo_type, filename, revision, token=None):
        if revision != self.sha:
            raise AssertionError("Stale revision used for file download")
        if filename not in self.files:
            raise FileNotFoundError(filename)
        destination = self.root / str(len(self.commits)) / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.files[filename])
        return str(destination)

    def create_commit(self, **kwargs):
        if self.raise_on_commit:
            raise self.raise_on_commit
        if kwargs["parent_commit"] != self.sha:
            raise AssertionError("Commit against stale revision")
        before = self.sha
        paths = []
        for operation in kwargs["operations"]:
            path = operation.path_in_repo
            data = operation.path_or_fileobj
            self.files[path] = data.getvalue() if isinstance(data, io.BytesIO) else Path(data).read_bytes()
            paths.append(path)
        self.commits.append((before, paths))
        self.sha = f"{len(self.commits):040x}"
        self.books = json.loads(self.files["data/library.json"])["books"]
        return SimpleNamespace(oid=self.sha)


def proposed(books, indexes):
    images = [cover(i) for i in indexes]
    return make_plan(images, books, {}, set())


class CoverBatchTests(unittest.TestCase):
    def test_group_89_covers_into_five_batches(self):
        books = [book(n) for n in range(1, 90)]
        plan = proposed(books, range(1, 90))
        batches = group_batches(plan)
        self.assertEqual([len(x) for x in batches], [20, 20, 20, 20, 9])
        self.assertEqual(len(group_batches(plan, batch_size=40)), 3)

    def test_group_by_bytes_as_well_as_count(self):
        books = [book(n) for n in range(1, 6)]
        plan = proposed(books, range(1, 6))
        self.assertEqual([len(x) for x in group_batches(
            plan, batch_size=20, max_bytes=len(cover(1).data) * 2)],
            [2, 2, 1])
        with self.assertRaises(CoverError):
            group_batches(plan, batch_size=41)

    def test_three_covers_one_commit_atomic_catalogue(self):
        with TemporaryDirectory() as folder:
            books = [book(i) for i in range(1, 4)]
            hub = FakeHub(folder, books)
            plans = proposed(books, range(1, 4))
            with patch("huggingface_hub.hf_hub_download", side_effect=hub.download):
                new_sha, statuses = commit_cover_batch(
                    hub, "owner/private", "token", plans, hub.sha)
            self.assertEqual(statuses, ["UPLOADED"] * 3)
            self.assertEqual(new_sha, hub.sha)
            self.assertEqual(len(hub.commits), 1)
            self.assertEqual(len(hub.commits[0][1]), 4)  # 3 images + 1 catalogue
            for b in hub.books:
                self.assertEqual(b["metadata"]["coverPath"],
                                 f"data/novels/{b['id']}/cover.png")
                self.assertEqual(b["metadata"]["personalRating"], 9)
                self.assertEqual(b["metadata"]["personalTags"], ["Favourite"])
                self.assertEqual(b["metadata"]["progress"], int(b["id"], 16))

    def test_repeated_batch_skips_already_uploaded_images(self):
        with TemporaryDirectory() as folder:
            books = [book(i) for i in range(1, 4)]
            hub = FakeHub(folder, books)
            proposed_items = proposed(books, range(1, 4))
            with patch("huggingface_hub.hf_hub_download", side_effect=hub.download):
                commit_cover_batch(hub, "owner/private", "token", proposed_items, hub.sha)
                new_sha, statuses = commit_cover_batch(
                    hub, "owner/private", "token", proposed_items, hub.sha)
            self.assertEqual(statuses, ["UNCHANGED"] * 3)
            self.assertEqual(new_sha, hub.sha)
            self.assertEqual(len(hub.commits), 1)

    def test_partial_36_of_89_resumes_with_only_three_commits(self):
        with TemporaryDirectory() as folder:
            books = [book(i, linked=i <= 36) for i in range(1, 90)]
            hub = FakeHub(folder, books, present=range(1, 37))
            all_images = [cover(i) for i in range(1, 90)]
            hashes = {
                f"data/novels/{books[i-1]['id']}/cover.png": all_images[i-1].digest
                for i in range(1, 37)
            }
            initial = make_plan(all_images, books, hashes, set(hub.files))
            self.assertEqual(sum(x["status"] == "UNCHANGED" for x in initial), 36)
            pending = [x for x in initial if x["status"] in ("NEW", "LINK", "UPDATE")]
            self.assertEqual(len(pending), 53)
            with patch("huggingface_hub.hf_hub_download", side_effect=hub.download):
                commits, count = upload_batches(
                    hub, "owner/private", "token", pending, hub.sha,
                    commit_pause=0, sleeper=lambda _: None)
            self.assertEqual((commits, count), (3, 53))
            self.assertEqual(len(hub.commits), 3)
            self.assertEqual(sum("coverPath" in b["metadata"] for b in hub.books), 89)

    def test_link_existing_identical_image_without_reuploading(self):
        with TemporaryDirectory() as folder:
            books = [book(1)]
            hub = FakeHub(folder, books, present=[1])
            plans = proposed(books, [1])
            with patch("huggingface_hub.hf_hub_download", side_effect=hub.download):
                new_sha, statuses = commit_cover_batch(
                    hub, "owner/private", "token", plans, hub.sha)
            self.assertEqual(statuses, ["LINKED"])
            self.assertEqual(len(hub.commits), 1)
            self.assertEqual(hub.commits[0][1], ["data/library.json"])

    def test_concurrent_change_refuses_commit(self):
        with TemporaryDirectory() as folder:
            books = [book(1)]
            hub = FakeHub(folder, books)
            with patch("huggingface_hub.hf_hub_download", side_effect=hub.download):
                with self.assertRaisesRegex(CoverError, "changed"):
                    commit_cover_batch(
                        hub, "owner/private", "token", proposed(books, [1]), "b" * 40)
            self.assertFalse(hub.commits)

    def test_public_dataset_refused(self):
        with TemporaryDirectory() as folder:
            books = [book(1)]
            hub = FakeHub(folder, books)
            hub.is_private = False
            with patch("huggingface_hub.hf_hub_download", side_effect=hub.download):
                with self.assertRaisesRegex(CoverError, "public"):
                    commit_cover_batch(
                        hub, "owner/private", "token", proposed(books, [1]), hub.sha)
            self.assertFalse(hub.commits)

    def test_quota_429_stops_without_hour_long_sleep(self):
        with TemporaryDirectory() as folder:
            books = [book(1)]
            hub = FakeHub(folder, books)
            e = RuntimeError("429 quota: 128 commits per hour")
            e.response = SimpleNamespace(
                status_code=429, headers={"Retry-After": "3600"})
            hub.raise_on_commit = e
            sleeps = []
            with patch("huggingface_hub.hf_hub_download", side_effect=hub.download):
                with self.assertRaisesRegex(CoverError, "SAME ZIP later"):
                    commit_cover_batch(
                        hub, "owner/private", "token", proposed(books, [1]),
                        hub.sha, sleeper=sleeps.append)
            self.assertEqual(sleeps, [])
            self.assertEqual(hub.commits, [])

    def test_short_retry_after_is_bounded_to_one_retry(self):
        with TemporaryDirectory() as folder:
            books = [book(1)]
            hub = FakeHub(folder, books)
            e = RuntimeError("429")
            e.response = SimpleNamespace(
                status_code=429, headers={"Retry-After": "1"})
            hub.raise_on_commit = e
            sleeps = []
            with patch("huggingface_hub.hf_hub_download", side_effect=hub.download):
                with self.assertRaisesRegex(CoverError, "SAME ZIP later"):
                    commit_cover_batch(
                        hub, "owner/private", "token", proposed(books, [1]),
                        hub.sha, sleeper=sleeps.append)
            self.assertEqual(sleeps, [1.0])
            self.assertEqual(hub.commits, [])


if __name__ == "__main__":
    unittest.main()
