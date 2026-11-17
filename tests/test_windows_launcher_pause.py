"""Windows launcher regression: diagnostics remain visible after each command."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WindowsLaunchersPauseTests(unittest.TestCase):
    def test_all_standalone_launchers_pause_before_exiting(self):
        launchers = sorted(ROOT.glob("[0-9][0-9]_*.cmd"))
        self.assertGreaterEqual(len(launchers), 18)
        for launcher in launchers:
            if launcher.name == "00_storage_menu.cmd":
                continue
            text = launcher.read_text(encoding="utf-8").lower()
            with self.subTest(launcher=launcher.name):
                self.assertIn("pause", text, "Standalone launcher must keep console visible")
                self.assertRegex(text, r"pause\s*\n(?:exit /b %result%|exit /b [01]|$)",
                                 "Final normal/failed exit must follow a pause")

    def test_inspection_scripts_preserve_error_code_and_allow_help(self):
        for index in (5, 12, 13, 14, 15, 16, 17):
            launcher = next(ROOT.glob(f"{index:02d}_*.cmd"))
            text = launcher.read_text(encoding="utf-8").lower()
            with self.subTest(launcher=launcher.name):
                self.assertIn('set "result=%errorlevel%"', text)
                self.assertIn('exit /b %result%', text)
                self.assertIn('if /i "%~1"=="--help" exit /b %result%', text)
                self.assertIn("pause", text)

    def test_storage_menu_calls_scripts_normally(self):
        menu = (ROOT / "00_storage_menu.cmd").read_text(encoding="utf-8").lower()
        self.assertIn('if "%choice%"=="13" call "%~dp013_audit_missing_covers.cmd"', menu)
        self.assertIn('if "%choice%"=="17" call "%~dp017_cleanup_inspection_downloads.cmd"', menu)


if __name__ == "__main__":
    unittest.main()
