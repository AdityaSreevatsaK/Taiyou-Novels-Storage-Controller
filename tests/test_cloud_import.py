"""Offline security checks for cloud-only Retriever artefact import."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory

from taiyou_storage.cloud_import import BundleError, check_bundle, main
from taiyou_storage.core import sha256_file

ROOT = Path(__file__).resolve().parents[1]


def make_bundle(root: Path, count: int = 2):
    novels = root / "novels"
    novels.mkdir(parents=True, exist_ok=True)
    records = []
    for i in range(count):
        filename = f"novel-{i:02d}.zip"
        path = novels / filename
        path.write_bytes(b"synthetic-validity-checked-by-real-uploader" + bytes([i]))
        records.append({
            "file": "novels/" + filename, "zip_sha256": sha256_file(path),
            "bytes": path.stat().st_size, "title": f"Private Title {i}",
        })
    manifest = {
        "exported_novels": count, "novels": records,
        "conflicting_editions": [], "invalid_archives": [],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


class CloudImportTests(unittest.TestCase):
    def test_valid_completed_export_checks_all_hashes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            make_bundle(root, 3)
            result = check_bundle(root)
            self.assertEqual(result["Verified novel ZIPs"], 3)
            self.assertTrue(result["Verified ZIP bytes"] > 0)
            self.assertNotIn("Private Title", str(result))
            self.assertEqual(main([str(root)]), 0)

    def test_missing_export_fails(self):
        with TemporaryDirectory() as temp:
            self.assertNotEqual(main([temp]), 0)

    def test_modified_zip_fails(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            make_bundle(root)
            (root / "novels" / "novel-00.zip").write_bytes(b"modified")
            with self.assertRaisesRegex(BundleError, "SHA-256"):
                check_bundle(root)

    def test_unmanifested_book_fails(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            make_bundle(root)
            (root / "novels" / "extra.zip").write_bytes(b"unlisted")
            with self.assertRaisesRegex(BundleError, "differ"):
                check_bundle(root)

    def test_conflicting_editions_block(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            data = make_bundle(root)
            data["conflicting_editions"] = [{"secret": "private title"}]
            (root / "manifest.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(BundleError, "conflicting"):
                check_bundle(root)

    def test_traversal_fails(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            data = make_bundle(root)
            data["novels"][0]["file"] = "novels/../private.zip"
            (root / "manifest.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(BundleError, "Unexpected book path"):
                check_bundle(root)

    def test_symlink_fails_closed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            make_bundle(root)
            try:
                (root / "novels" / "novel-00.zip").unlink()
                (root / "novels" / "novel-00.zip").symlink_to(root / "manifest.json")
            except (OSError, NotImplementedError):
                self.skipTest("Symlink creation not permitted")
            with self.assertRaises(BundleError):
                check_bundle(root)

    def test_public_workflow_has_manual_apply_and_no_public_reports(self):
        yml = (ROOT / ".github/workflows/hf-cloud-import.yml").read_text(encoding="utf8")
        self.assertIn("workflow_dispatch:", yml)
        self.assertIn("apply_changes", yml)
        self.assertIn("default: false", yml)
        self.assertIn("HF_STORAGE_CONTROLLER_TOKEN", yml)
        self.assertIn("RichardDaffern/Novel-Retriever", yml)
        self.assertIn("NOVEL_LIBRARY_ACTIONS_TOKEN", yml)
        self.assertIn("--dedupe-local", yml)
        self.assertIn("taiyou_storage.cloud_import", yml)
        self.assertIn("refs/heads/master", yml)
        self.assertNotIn("actions/upload-artifact", yml)
        self.assertNotIn("taiyou_storage.reset", yml)


if __name__ == "__main__":
    unittest.main()
