"""Regression checks for a single safe Windows upload entrypoint and renumbered tools."""
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RENAMED = {
    12: "export_novel_inventory",
    13: "audit_missing_covers",
    14: "compare_retriever_inventory",
    15: "library_health_report",
    16: "backfill_inspection_manifests",
    17: "cleanup_inspection_downloads",
}


class WindowsMenuNumberingTests(unittest.TestCase):
    def test_bulk_upload_uses_verified_deduplication_by_default(self):
        launcher = (ROOT / "01_bulk_upload.cmd").read_text(encoding="utf-8")
        self.assertIn("py -m taiyou_storage.upload novels --dedupe-local --interactive", launcher)
        self.assertNotIn(" --apply", launcher)
        self.assertIn("pause", launcher)
        self.assertFalse((ROOT / "12_bulk_upload_with_deduplication.cmd").exists())

    def test_renumbered_launchers_and_menu_are_consistent(self):
        menu = (ROOT / "00_storage_menu.cmd").read_text(encoding="utf-8")
        self.assertIn('if "%choice%"=="1" call "%~dp001_bulk_upload.cmd"', menu)
        self.assertNotIn('12_bulk_upload_with_deduplication.cmd', menu)
        for number, name in RENAMED.items():
            path = f"{number:02d}_{name}.cmd"
            with self.subTest(number=number, path=path):
                self.assertTrue((ROOT / path).is_file())
                self.assertIn(
                    f'if "%choice%"=="{number}" call "%~dp0{path}"', menu,
                )
                self.assertEqual(
                    len(re.findall(rf'if "%choice%"=="{number}" call ', menu)),
                    1,
                )
        self.assertEqual(len(list(ROOT.glob("[0-9][0-9]_*.cmd"))), 18)

    def test_deprecated_launcher_names_no_longer_exist(self):
        old = {
            13: "export_novel_inventory", 14: "audit_missing_covers",
            15: "compare_retriever_inventory", 16: "library_health_report",
            17: "backfill_inspection_manifests", 18: "cleanup_inspection_downloads",
        }
        for number, name in old.items():
            with self.subTest(name=name):
                self.assertFalse((ROOT / f"{number:02d}_{name}.cmd").exists())


if __name__ == "__main__":
    unittest.main()
