"""Retriever completed export -> manifest check -> guarded Controller upload.

Offline only: simulated private HF and synthetic EPUB/chapter data.
"""
from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from taiyou_storage.cloud_import import BundleError, check_bundle
from taiyou_storage.core import sha256_file
from taiyou_storage.upload import main as upload_main
from tests.test_smoke_integration import FakePrivateHub, REPO, fake_cloud, make_novel, quiet_run


def retriever_bundle(root: Path, count: int = 4) -> Path:
    incoming = root / "incoming"
    novels = incoming / "novels"
    novels.mkdir(parents=True)
    rows = []
    for i in range(count):
        path = make_novel(
            novels, f"completed-{i:02d}.zip", f"Verified Synthetic Series {i:02d}",
            f"https://example.invalid/verified-{i:02d}"
        )
        rows.append({
            "title": f"Verified Synthetic Series {i:02d}",
            "file": "novels/" + path.name,
            "zip_sha256": sha256_file(path),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "github_artifact_id": 100 + i,
        })
    (incoming / "manifest.json").write_text(json.dumps({
        "exported_novels": count,
        "novels": rows,
        "duplicates_skipped": 0,
        "conflicting_editions": [],
        "invalid_archives": [],
        "unavailable_registry_books": [],
    }), encoding="utf8")
    return incoming


class RetrieverControllerHandoffTests(unittest.TestCase):
    def test_manifest_preview_apply_and_replay_are_idempotent(self):
        with TemporaryDirectory() as temp, chdir(temp):
            root = Path(temp)
            incoming = retriever_bundle(root, 4)
            evidence = check_bundle(incoming)
            self.assertEqual(evidence["Verified novel ZIPs"], 4)
            hub = FakePrivateHub(root)
            args = [str(incoming / "novels"), "--repo", REPO,
                    "--dedupe-local", "--covers-folder", str(incoming / "covers")]
            with fake_cloud(hub):
                preview, output = quiet_run(upload_main, args)
                self.assertEqual(preview, 0, output)
                self.assertIn("New novels to upload", output)
                self.assertEqual(hub.commits, [])
                applied, output = quiet_run(upload_main, args + ["--apply"])
                self.assertEqual(applied, 0, output)
                self.assertEqual(len(hub.commits), 1)
                self.assertEqual(len(hub.books()), 4)
                for book in hub.books():
                    self.assertRegex(book["id"], r"^[a-f0-9]{24}$")
                    self.assertIn(book["epubPath"], hub.files)
                    self.assertIn(book["archivePath"], hub.files)
                again, output = quiet_run(upload_main, args + ["--apply"])
                self.assertEqual(again, 0, output)
                self.assertEqual(len(hub.commits), 1)

    def test_interrupted_second_batch_replays_safely(self):
        with TemporaryDirectory() as temp, chdir(temp):
            root = Path(temp)
            incoming = retriever_bundle(root, 6)
            self.assertEqual(check_bundle(incoming)["Verified novel ZIPs"], 6)
            hub = FakePrivateHub(root)
            hub.fail_commit_number = 2
            args = [str(incoming / "novels"), "--repo", REPO,
                    "--dedupe-local", "--batch-size", "3"]
            with fake_cloud(hub):
                first, output = quiet_run(upload_main, args + ["--apply"])
                self.assertEqual(first, 1)
                self.assertEqual(len(hub.commits), 1)
                self.assertEqual(len(hub.books()), 3)
                hub.fail_commit_number = None
                resumed, output = quiet_run(upload_main, args + ["--apply"])
                self.assertEqual(resumed, 0, output)
                self.assertEqual(len(hub.commits), 2)
                self.assertEqual(len(hub.books()), 6)

    def test_tampered_manifest_stops_before_the_import(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = retriever_bundle(root)
            path = incoming / "novels" / "completed-00.zip"
            with path.open("ab") as stream:
                stream.write(b"tamper")
            with self.assertRaisesRegex(BundleError, "SHA-256"):
                check_bundle(incoming)

    def test_untrusted_cover_symlink_and_extraneous_file_are_rejected(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = retriever_bundle(root, 1)
            covers = incoming / "covers"
            covers.mkdir()
            (covers / "unknown.txt").write_text("not image", encoding="utf8")
            with self.assertRaises(BundleError):
                check_bundle(incoming)
            (covers / "unknown.txt").unlink()
            try:
                (covers / "escape.jpg").symlink_to(incoming / "manifest.json")
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unavailable on this platform")
            with self.assertRaisesRegex(BundleError, "Symlink"):
                check_bundle(incoming)


if __name__ == "__main__":
    unittest.main()
