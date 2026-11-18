"""Prevent retired maintenance workflows and public novel data exports from returning."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RETAINED = {
    "ci.yml", "hf-inspect.yml", "hf-private-backup.yml",
    "hf-private-reports.yml", "hf-restore-genres.yml",
    "hf-upload-covers-artifact.yml", "release.yml",
}
RETIRED = {
    "hf-migrate-readable-folders.yml",
    "one-shot-one-novel-pilot-20261114.yml",
    "one-shot-verify-private-backup-20261113.yml",
    "prune-reviewed-branches.yml",
    "prune-superseded-readable-branches-once.yml",
    "readable-folder-acceptance.yml",
    "readable-folder-preflight-once.yml",
    "readable-migration-readiness.yml",
}


class GitHubWorkflowCleanupTests(unittest.TestCase):
    def test_only_supported_workflows_remain(self):
        actual = {p.name for p in WORKFLOWS.glob("*.yml")}
        # Only this specifically reviewed, single-shot maintenance workflow
        # may temporarily coexist with the supported set. A follow-up PR
        # removes it and restores the strict seven-workflow assertion.
        one_shot = "one-shot-prune-seven-branches-20261118.yml"
        self.assertEqual(actual, RETAINED | {one_shot})
        cleanup = (WORKFLOWS / one_shot).read_text(encoding="utf-8")
        self.assertIn("branches: [master]", cleanup)
        self.assertIn("EXPECTED_MASTER", cleanup)
        self.assertIn("if os.environ.get(\"GH_REPO\") != REPO:", cleanup)
        self.assertIn("ONE_SHOT =", cleanup)
        self.assertIn("MERGED =", cleanup)
        self.assertNotIn("HF_TOKEN", cleanup)
        self.assertTrue(RETIRED.isdisjoint(actual))

    def test_private_checks_are_explicit_read_only_and_do_not_upload_artifacts(self):
        yml = (WORKFLOWS / "hf-inspect.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", yml)
        self.assertIn("refs/heads/master", yml)
        self.assertIn("contents: read", yml)
        self.assertIn("HF_INSPECTION_READ_TOKEN", yml)
        self.assertIn("HF_STORAGE_CONTROLLER_TOKEN", yml)
        self.assertIn("taiyou_storage.github_checks", yml)
        self.assertIn("default: manifest", yml)
        self.assertIn("          - deep", yml)
        self.assertNotIn("actions/upload-artifact", yml)
        self.assertNotIn("--apply", yml)
        self.assertNotIn("contents: write", yml)
        self.assertNotIn("taiyou_storage.reset", yml)

    def test_cover_import_uses_current_novel_retriever(self):
        yml = (WORKFLOWS / "hf-upload-covers-artifact.yml").read_text(encoding="utf-8")
        self.assertIn("repository: RichardDaffern/Novel-Retriever", yml)
        self.assertNotIn("RichardDaffern/Novel_Library", yml)

    def test_offline_ci_does_not_access_private_hf(self):
        yml = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("unittest discover", yml)
        self.assertNotIn("HF_STORAGE_CONTROLLER_TOKEN", yml)
        self.assertNotIn("HF_INSPECTION_READ_TOKEN", yml)

    def test_dependency_audit_runs_without_hugging_face_secrets(self):
        yml = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("dependency-audit:", yml)
        self.assertIn("python -m pip_audit -r requirements.txt", yml)
        self.assertIn("schedule:", yml)
        self.assertIn("contents: read", yml)
        self.assertNotIn("secrets.", yml)
        self.assertNotIn("actions/upload-artifact", yml)


if __name__ == "__main__":
    unittest.main()
