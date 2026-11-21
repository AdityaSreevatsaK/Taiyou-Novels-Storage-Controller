"""Regression tests for concise, privacy-preserving controller output."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import os
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from taiyou_storage.console_summary import print_start, print_summary, print_end
from taiyou_storage.github_output import safe_metrics, format_summary, run as github_run

ROOT = Path(__file__).resolve().parents[1]


class OutputContractTests(unittest.TestCase):
    def test_local_output_has_start_summary_and_end(self):
        out = StringIO()
        with redirect_stdout(out):
            print_start("Novel audit", mode="preview")
            print_summary("Novel audit preview", {
                "Total novels": 700, "Conflicts detected": 0,
            }, reports=["reports/private.csv"], status="PREVIEW")
            print_end("Novel audit", status="COMPLETED")
        text = out.getvalue()
        for expected in ("Started", "700", "Detailed reports:",
                         "Result: PREVIEW", "Result : COMPLETED"):
            self.assertIn(expected, text)

    def test_blocked_not_called_success(self):
        out = StringIO()
        with redirect_stdout(out):
            print_summary("Bulk upload blocked", {"Conflicts detected": 1})
        self.assertIn("Result: BLOCKED", out.getvalue())

    def test_fixed_numeric_metric_allowlist_prevents_private_leaks(self):
        payload = ("Total novels: 352\nSource files: 1,295\n"
                   "Title: Private Novel 789\nToken: 123456789\n"
                   "data/novels/private.zip: 88\n"
                   "Total novels: 353\nConflicts detected: 0\n")
        metrics = safe_metrics(payload)
        self.assertEqual(metrics, [("Total novels", "353"),
                                   ("Source files", "1,295"),
                                   ("Conflicts detected", "0")])
        body = format_summary("backup", "preview", 0, metrics)
        self.assertIn("**Result:** Preview only", body)
        self.assertNotIn("Private Novel", body)
        self.assertNotIn("Token", body)

    def test_failed_action_ends_cleanly_without_private_stdout(self):
        with TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            captured = StringIO()
            def fail(command, *, stdout, stderr, check):
                stdout.write("Title: Secret Story\nTotal novels: 100\n"
                             "Traceback: private file contents\n")
                return SimpleNamespace(returncode=3)
            with (patch.dict(os.environ, {
                    "RUNNER_TEMP": tmp, "GITHUB_STEP_SUMMARY": str(summary)}),
                  patch("taiyou_storage.github_output.subprocess.run", side_effect=fail),
                  redirect_stdout(captured)):
                code = github_run(["--task", "novel-import", "--mode", "apply",
                                   "--", "python", "-m", "taiyou_storage.upload", "novels"])
            self.assertEqual(code, 3)
            self.assertIn("FAILED (exit code 3)", captured.getvalue())
            self.assertIn("**Result:** Failed", summary.read_text())
            self.assertNotIn("Secret Story", captured.getvalue())

    def test_success_shows_numeric_counts_and_final_status(self):
        with TemporaryDirectory() as tmp:
            captured = StringIO()
            def succeed(command, *, stdout, stderr, check):
                stdout.write("Total novels: 352\nPrivate Novel: Example\n")
                return SimpleNamespace(returncode=0)
            with (patch.dict(os.environ, {
                    "RUNNER_TEMP": tmp, "GITHUB_STEP_SUMMARY": str(Path(tmp) / "summary.md")}),
                  patch("taiyou_storage.github_output.subprocess.run", side_effect=succeed),
                  redirect_stdout(captured)):
                code = github_run(["--task", "inspection", "--mode", "verify",
                                   "--", "python", "-m", "taiyou_storage.github_checks",
                                   "--mode", "quick"])
            self.assertEqual(code, 0)
            self.assertIn("[START] Library inspection", captured.getvalue())
            self.assertIn("Total novels: 352", captured.getvalue())
            self.assertIn("[END] Library inspection | COMPLETED", captured.getvalue())
            self.assertNotIn("Private Novel", captured.getvalue())

    def test_shell_command_rejected(self):
        self.assertEqual(github_run(["--task", "inspection", "--",
                                     "bash", "-c", "cat /secret"]), 2)

    def test_launchers_share_start_end_contract(self):
        names = ["01_bulk_upload", "02_download_all", "03_list_novels",
                 "04_detect_conflicts", "05_verify_integrity", "06_sync_status",
                 "07_backup_catalogue", "10_upload_covers", "11_clear_hf_data",
                 "12_export_novel_inventory", "13_audit_missing_covers",
                 "14_compare_retriever_inventory", "15_library_health_report",
                 "16_backfill_inspection_manifests", "17_cleanup_inspection_downloads",
                 "18_repair_novel_metadata"]
        for name in names:
            with self.subTest(command=name):
                content = (ROOT / f"{name}.cmd").read_text(encoding="utf-8")
                self.assertIn("19_command_output.cmd", content)
                self.assertIn(' start "', content)
                self.assertIn(' end "', content)

    def test_actions_use_safe_summary(self):
        names = ["hf-inspect", "hf-private-backup", "hf-private-reports",
                 "hf-live-readiness", "hf-restore-genres",
                 "hf-upload-covers-artifact", "hf-cloud-import"]
        for name in names:
            with self.subTest(workflow=name):
                yml = (ROOT / ".github" / "workflows" / f"{name}.yml").read_text()
                self.assertIn("taiyou_storage.github_output", yml)
                self.assertNotIn("actions/upload-artifact", yml)


if __name__ == "__main__":
    unittest.main()
