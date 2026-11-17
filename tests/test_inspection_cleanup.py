"""Cleanup must never delete HF data or unrelated local-cache entries."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from taiyou_storage.inspection_cache import (
    cache_usage, ensure_owned_cache, inspection_cache_dir, validate_owned_cache,
)
from taiyou_storage.inspection_cleanup import _legacy_targets, run

REPO = "AdityaSreevatsaK/Taiyous-Novels"


class CleanupTests(unittest.TestCase):
    def test_owned_cache_is_restricted_by_marker_and_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = inspection_cache_dir(Path(tmp))
            ensure_owned_cache(directory, REPO)
            validate_owned_cache(directory, REPO)
            with self.assertRaisesRegex(ValueError, "marker"):
                validate_owned_cache(directory, "other/dataset")
            (directory / "test").write_bytes(b"example")
            self.assertGreater(cache_usage(directory)[1], 0)

    def test_owned_cache_cannot_delete_unmarked_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = inspection_cache_dir(Path(tmp))
            directory.mkdir()
            (directory / "something").write_text("do not touch")
            with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="DELETE LOCAL CACHE"):
                self.assertEqual(run(["--reports-dir", tmp, "--apply"]), 1)
            self.assertTrue((directory / "something").exists())

    def test_preview_does_not_delete_owned_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = inspection_cache_dir(Path(tmp))
            ensure_owned_cache(directory, REPO)
            (directory / "download.zip").write_bytes(b"example")
            self.assertEqual(run(["--reports-dir", tmp]), 0)
            self.assertTrue((directory / "download.zip").exists())

    def test_apply_needs_exact_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = inspection_cache_dir(Path(tmp))
            ensure_owned_cache(directory, REPO)
            (directory / "download.zip").write_bytes(b"example")
            with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="no"):
                self.assertEqual(run(["--reports-dir", tmp, "--apply"]), 0)
            self.assertTrue(directory.is_dir())
            with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="DELETE LOCAL CACHE"):
                self.assertEqual(run(["--reports-dir", tmp, "--apply"]), 0)
            self.assertFalse(directory.exists())

    def test_legacy_selects_only_target_repo_novel_binaries(self):
        base = Path("cache/snapshots/abc")
        def item(name):
            return SimpleNamespace(file_path=base / name)
        wanted = [item("data/novels/abc/source.epub"),
                  item("data/novels/abc/original.zip"),
                  item("data/novels/abc/cover.jpg")]
        ignored = [item("data/novels/abc/inspection-manifest.json"),
                   item("data/library.json"), item("data/novels/abc/notes.txt")]
        info = SimpleNamespace(repos=[
            SimpleNamespace(repo_id=REPO, repo_type="dataset",
                            revisions=[SimpleNamespace(snapshot_path=base, files=wanted + ignored)]),
            SimpleNamespace(repo_id="other/private", repo_type="dataset",
                            revisions=[SimpleNamespace(snapshot_path=base,
                                                       files=[item("data/novels/q/source.epub")])])
        ])
        self.assertEqual(_legacy_targets(info, REPO), wanted)

    def test_legacy_preview_and_apply_use_hf_reference_safe_strategy(self):
        base = Path("cache/snapshots/abc")
        entry = SimpleNamespace(file_path=base / "data/novels/abc/source.epub")
        strategy = SimpleNamespace(expected_freed_size_str="5 MB", execute=MagicMock())
        info = SimpleNamespace(repos=[SimpleNamespace(
            repo_id=REPO, repo_type="dataset",
            revisions=[SimpleNamespace(snapshot_path=base, files=[entry])])],
            delete_files=MagicMock(return_value=strategy))
        with tempfile.TemporaryDirectory() as tmp:
            with patch("huggingface_hub.scan_cache_dir", return_value=info):
                self.assertEqual(run(["--reports-dir", tmp, "--legacy-shared-cache"]), 0)
                info.delete_files.assert_called_once_with(entry)
                strategy.execute.assert_not_called()
                with patch("sys.stdin.isatty", return_value=True), patch(
                        "builtins.input", return_value="DELETE LOCAL CACHE"):
                    self.assertEqual(run(["--reports-dir", tmp, "--legacy-shared-cache", "--apply"]), 0)
                strategy.execute.assert_called_once()

    def test_backfill_and_inspection_reuse_same_private_cache(self):
        self.assertEqual(inspection_cache_dir(Path("reports")),
                         Path("reports") / ".inspection-download-cache")

    def test_windows_cleanup_launcher(self):
        script = Path(__file__).resolve().parents[1] / "18_cleanup_inspection_downloads.cmd"
        text = script.read_text(encoding="utf-8")
        self.assertIn("taiyou_storage.inspection_cleanup", text)
        self.assertIn("%*", text)


if __name__ == "__main__":
    unittest.main()
