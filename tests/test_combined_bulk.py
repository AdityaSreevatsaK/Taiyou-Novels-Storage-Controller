"""Combined novel + local cover workflow using a fully fake private HF dataset."""
from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import csv
import unittest

from PIL import Image

from tests.test_smoke_integration import (
    FakePrivateHub, REPO, fake_cloud, make_novel, quiet_run)
from taiyou_storage.upload import main as bulk_main


def prepare(root: Path, count: int = 10):
    novels = root / "novels"
    covers = root / "covers"
    novels.mkdir()
    covers.mkdir()
    for index in range(count):
        title = f"Example Cover Novel {index:02d}"
        make_novel(novels, f"novel-{index:02d}.zip", title,
                   f"https://example.com/{index:02d}")
        Image.new("RGB", (250, 350), (index * 11 % 255, 70, 90)).save(
            covers / (title + ".jpg"))
    return novels, covers


class CombinedBulkTests(unittest.TestCase):
    def test_ten_novels_and_covers_in_one_commit(self):
        with TemporaryDirectory() as folder, chdir(folder):
            root = Path(folder)
            novels, covers = prepare(root)
            hub = FakePrivateHub(root)
            with fake_cloud(hub):
                preview, output = quiet_run(bulk_main, [
                    str(novels), "--repo", REPO, "--covers-folder", str(covers)])
                self.assertEqual(preview, 0, output)
                self.assertIn("Matched local covers", output)
                self.assertIn("New covers", output)
                self.assertEqual(len(hub.commits), 0)
                result, output = quiet_run(bulk_main, [
                    str(novels), "--repo", REPO, "--covers-folder", str(covers),
                    "--apply"])
                self.assertEqual(result, 0, output)
                self.assertEqual(len(hub.commits), 1)
                self.assertEqual(len(hub.books()), 10)
                self.assertEqual(len([name for name in hub.files if name.endswith(".jpg")]), 10)
                self.assertEqual(len([name for name in hub.commits[0]
                                      if name.endswith("source.epub")]), 10)
                for book in hub.books():
                    cover_path = book["metadata"].get("coverPath")
                    self.assertTrue(cover_path, book)
                    self.assertIn(cover_path, hub.files)
                result, output = quiet_run(bulk_main, [
                    str(novels), "--repo", REPO, "--covers-folder", str(covers),
                    "--apply"])
                self.assertEqual(result, 0, output)
                self.assertIn("Unchanged covers", output)
                self.assertEqual(len(hub.commits), 1)

    def test_filenames_and_parent_folder_ids_match(self):
        from taiyou_storage.bulk_batch import discover_covers
        from taiyou_storage.upload import plan, read_novel
        with TemporaryDirectory() as folder:
            root = Path(folder)
            novels, covers = prepare(root, 2)
            local = [(p, *read_novel(p)) for p in novels.glob("*.zip")]
            items = plan([], local, {}, set())
            for image in list(covers.glob("*.jpg")):
                image.rename(covers / (image.stem.replace("Example Cover Novel", "unmatched") + ".jpg"))
            for item in items:
                subdir = covers / item["id"]
                subdir.mkdir()
                Image.new("RGB", (250, 350), (100, 80, 90)).save(subdir / "cover.png")
            _, errors = discover_covers(items, covers)
            self.assertEqual(len(errors), 2)  # unmatched root-level extras are not assigned
            self.assertEqual(sum("cover" in item for item in items), 2)

    def test_duplicate_and_unmatched_covers_block_all_writes(self):
        with TemporaryDirectory() as folder, chdir(folder):
            root = Path(folder)
            novels, covers = prepare(root, 2)
            Image.new("RGB", (250, 350)).save(covers / "Example Cover Novel 00.png")
            hub = FakePrivateHub(root)
            with fake_cloud(hub):
                result, output = quiet_run(bulk_main, [
                    str(novels), "--repo", REPO, "--covers-folder", str(covers),
                    "--apply"])
                self.assertEqual(result, 2, output)
                self.assertEqual(len(hub.commits), 0)
                with (root / "reports" / "bulk-upload-plan.csv").open(
                        newline="", encoding="utf-8-sig") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertTrue(any(row["state"] == "COVER_CONFLICT" for row in rows))

    def test_batch_size_five_makes_two_commits_and_resumes(self):
        with TemporaryDirectory() as folder, chdir(folder):
            root = Path(folder)
            novels, covers = prepare(root, 10)
            hub = FakePrivateHub(root)
            hub.fail_commit_number = 2
            with fake_cloud(hub):
                result, _ = quiet_run(bulk_main, [
                    str(novels), "--repo", REPO, "--covers-folder", str(covers),
                    "--batch-size", "5", "--apply"])
                self.assertEqual(result, 1)
                self.assertEqual(len(hub.commits), 1)
                self.assertEqual(len(hub.books()), 5)
                hub.fail_commit_number = None
                result, output = quiet_run(bulk_main, [
                    str(novels), "--repo", REPO, "--covers-folder", str(covers),
                    "--batch-size", "5", "--apply"])
                self.assertEqual(result, 0, output)
                self.assertEqual(len(hub.commits), 2)
                self.assertEqual(len(hub.books()), 10)


if __name__ == "__main__":
    unittest.main()
