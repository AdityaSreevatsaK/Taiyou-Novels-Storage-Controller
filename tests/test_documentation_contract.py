"""Offline smoke checks for the permanent project and AI agent documentation map.

No network, Hugging Face credentials or private novel content are required.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = (
    "README.md",
    "AGENTS.md",
    "docs/README.md",
    "docs/PROJECT_VISION_AND_HISTORY.md",
    "docs/ARCHITECTURE.md",
    "docs/FAILURES_AND_LESSONS.md",
    "docs/OPERATIONS_AND_DEPLOYMENT.md",
    "docs/ROADMAP.md",
    "docs/AI_AGENT_PLAYBOOK.md",
    "docs/PROJECT_STATE.md",
    "docs/archive/AGENTS_PRE_2026-11-21.md",
)
NAVIGATION = CANONICAL[:-1]
# Check local Markdown targets only, not external docs or anchors.
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)")


class DocumentationContractTests(unittest.TestCase):
    def test_required_handover_documents_exist_and_are_substantive(self):
        for filename in CANONICAL:
            with self.subTest(file=filename):
                path = ROOT / filename
                self.assertTrue(path.is_file(), f"Missing handover file: {filename}")
                self.assertGreater(len(path.read_text(encoding="utf-8")), 500)

    def test_navigation_relative_links_resolve(self):
        """Prevent future docs refactors from silently breaking agent routing."""
        for filename in NAVIGATION:
            source = ROOT / filename
            text = source.read_text(encoding="utf-8")
            for raw in MARKDOWN_LINK.findall(text):
                link = raw.split("#", 1)[0].split(" ", 1)[0].strip("<>")
                if not link or "://" in link or link.startswith(
                    ("mailto:", "/", "#")
                ):
                    continue
                with self.subTest(source=filename, target=link):
                    self.assertTrue(
                        (source.parent / link).is_file(),
                        f"Broken Markdown link from {filename} to {link}",
                    )

    def test_agent_entrypoint_links_all_core_guides(self):
        agent = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for filename in CANONICAL[3:]:
            with self.subTest(file=filename):
                self.assertIn(Path(filename).name, agent)

    def test_agents_require_dynamic_live_state_refresh(self):
        agent = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for phrase in (
            "Mandatory dynamic project-state refresh",
            "git status --short --branch",
            "git log -20",
            "open PRs",
            "open issues",
            "Partially implemented",
            "Deprecated/retired",
            "Historical",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, agent)

    def test_project_state_is_dated_and_tracks_current_open_gaps(self):
        state = (ROOT / "docs/PROJECT_STATE.md").read_text(encoding="utf-8")
        for phrase in (
            "not a live status API",
            "a40c01173df425aa94c445e7e221fd61f8e7fb34",
            "issues/46",
            "issues/54",
            "Not inspected or changed during this documentation review",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, state)

    def test_roadmap_does_not_present_placeholder_commands_as_delivered(self):
        roadmap = (ROOT / "docs/ROADMAP.md").read_text(encoding="utf-8")
        for placeholder in ("08_restore_novel.cmd", "09_delete_novel.cmd"):
            self.assertIn(placeholder, roadmap)
        self.assertIn("placeholders", (ROOT / "AGENTS.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
