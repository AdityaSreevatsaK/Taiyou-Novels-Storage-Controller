"""Keep the public README brief and the main documentation links usable."""
from __future__ import annotations

from pathlib import Path
import re
import unittest
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
PAGES = (
    "README.md",
    "README.smart-upload.md",
    "docs/README.md",
    "docs/USER_GUIDE.md",
    "docs/SAFETY_AND_RECOVERY.md",
    "docs/SMART_UPLOAD.md",
)


class DocumentationNavigationTests(unittest.TestCase):
    def test_root_readme_is_an_entrypoint_not_a_handbook(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(text.splitlines()), 90)
        for phrase in (
            "## Get started", "## Common tools", "## Documentation",
            "docs/USER_GUIDE.md", "docs/SAFETY_AND_RECOVERY.md",
            "docs/README.md",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_guide_links_point_to_existing_local_files(self):
        for name in PAGES:
            page = ROOT / name
            with self.subTest(page=name):
                self.assertTrue(page.is_file())
                text = page.read_text(encoding="utf-8")
                for target in re.findall(r"\]\(([^)]+)\)", text):
                    if target.startswith(("https://", "http://", "mailto:", "#")):
                        continue
                    local = unquote(target.split("#", 1)[0].split("?", 1)[0])
                    if not local:
                        continue
                    destination = page.parent / local
                    with self.subTest(page=name, link=target):
                        self.assertTrue(
                            destination.is_file() or destination.is_dir(),
                            f"Broken local Markdown link in {name}: {target}",
                        )

    def test_legacy_smart_upload_link_redirects_to_docs(self):
        text = (ROOT / "README.smart-upload.md").read_text(encoding="utf-8")
        self.assertIn("docs/SMART_UPLOAD.md", text)
        self.assertTrue((ROOT / "docs/SMART_UPLOAD.md").is_file())


if __name__ == "__main__":
    unittest.main()
