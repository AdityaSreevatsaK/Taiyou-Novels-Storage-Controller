"""Offline safety and integration tests for one-book metadata-only repairs."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from taiyou_storage.metadata_repair import (
    MetadataRepairError, _report_path, audit_catalogue, main,
    missing_fields, plan_repair, validate_patch, normalise_source_status,
)

ID = "a" * 24
OTHER_ID = "b" * 24
URL = "https://freewebnovel.com/novel/synthetic-example"


def book(ident=ID, url=URL, **meta):
    return {
        "id": ident,
        "epubPath": f"data/novels/{ident}/source.epub",
        "archivePath": f"data/novels/{ident}/original.zip",
        "metadata": {
            "id": ident, "title": "Synthetic Novel", "author": "Example Author",
            "sourceUrl": url, "chapterCount": 304,
            "coverPath": f"data/novels/{ident}/cover.jpg",
            "personalTags": ["Favourite"], "progress": 65,
            "personalReview": "A personal note", "personalRating": 9,
            **meta,
        },
    }


def patch_data(**fields):
    return {"id": ID, "sourceUrl": URL, **fields}


class MetadataAuditTests(unittest.TestCase):
    def test_missing_fields_and_local_report_are_source_only(self):
        catalogue = {"version": 1, "books": [
            book(),
            book(OTHER_ID, "https://novelfull.com/other.html",
                 description="Source text", status="Completed", sourceTags=["Action"]),
        ]}
        rows, stats = audit_catalogue(catalogue)
        self.assertEqual(stats, {
            "total_novels": 2, "novels_missing_any": 1,
            "missing_description": 1, "missing_sourceTags": 1,
            "missing_status": 1,
        })
        self.assertEqual(len(rows), 1)
        self.assertIn("sourceTags", rows[0]["missing_fields"])
        self.assertNotIn("personalTags", rows[0]["missing_fields"])
        self.assertEqual(missing_fields(book(description="x")["metadata"]),
                         ["sourceTags", "status"])

    def test_missing_genres_are_not_replaced_with_personal_tags(self):
        self.assertIn("sourceTags", missing_fields(book(personalTags=["Comedy"])["metadata"]))

    def test_unsupported_catalogue_rejected(self):
        with self.assertRaises(ValueError):
            audit_catalogue({"version": 2, "books": []})


class OneBookMetadataRepairTests(unittest.TestCase):
    def test_add_only_source_fields_preserves_every_personal_and_file_field(self):
        catalog = {"version": 1, "books": [book(), book(OTHER_ID, "https://novelfull.com/other.html")]}
        before = deepcopy(catalog)
        repaired, changed, target = plan_repair(catalog, patch_data(
            description="A source synopsis", sourceTags=["Romance", "Drama"],
            status="Completed",
        ))
        self.assertEqual(changed, ["description", "sourceTags", "status"])
        self.assertEqual(target["id"], ID)
        self.assertEqual(repaired["books"][1], before["books"][1])
        for key, value in before["books"][0]["metadata"].items():
            self.assertEqual(repaired["books"][0]["metadata"][key], value)
        self.assertEqual(repaired["books"][0]["metadata"]["sourceTags"], ["Romance", "Drama"])
        self.assertEqual(catalog, before)

    def test_identity_must_match_both_id_and_unique_url(self):
        catalog = {"version": 1, "books": [book()]}
        for wrong in (
            {"id": OTHER_ID, "sourceUrl": URL, "status": "Completed"},
            {"id": ID, "sourceUrl": "https://evil.example/book", "status": "Completed"},
        ):
            with self.subTest(wrong=wrong), self.assertRaises(MetadataRepairError):
                plan_repair(catalog, wrong)
        dupe = {"version": 1, "books": [book(), book(OTHER_ID, URL)]}
        with self.assertRaisesRegex(MetadataRepairError, "Duplicate"):
            plan_repair(dupe, patch_data(status="Completed"))

    def test_populated_fields_cannot_be_overwritten(self):
        catalog = {"version": 1, "books": [book(status="Ongoing")]}
        with self.assertRaisesRegex(MetadataRepairError, "already has a value"):
            plan_repair(catalog, patch_data(status="Completed"))
        updated, changes, _ = plan_repair(catalog, patch_data(status="Ongoing"))
        self.assertEqual(changes, [])
        self.assertEqual(updated, catalog)

    def test_invalid_or_personal_fields_rejected(self):
        invalid = [
            patch_data(progress=0),
            patch_data(personalTags=["Replace"]),
            patch_data(epubPath="data/novels/evil.epub"),
            patch_data(sourceTags=[]),
            patch_data(description=""),
            patch_data(status="Finished"),
            patch_data(sourceTags=[""]),
            {"id": ID, "sourceUrl": URL},
            {"id": "not-a-hash", "sourceUrl": URL, "status": "Completed"},
            {"id": ID, "sourceUrl": "http://freewebnovel.com/novel/x", "status": "Completed"},
        ]
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(MetadataRepairError):
                validate_patch(candidate)

    def test_source_status_aliases_are_canonical_and_source_only(self):
        cases = {
            "completed": "Completed", " Completed ": "Completed",
            "on going": "Ongoing", "IN-PROGRESS": "Ongoing",
            "Hiatus": "Hiatus", "on hiatus": "Hiatus",
            " ON  HOLD ": "Hiatus", "discontinued": "Dropped",
            "Dropped": "Dropped", "cancelled": "Dropped",
        }
        for raw, canonical in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalise_source_status(raw), canonical)
                self.assertEqual(validate_patch(patch_data(status=raw))["status"], canonical)
        for invalid in (None, 42, "", "Finished", "paused forever", "unknown"):
            with self.subTest(invalid=invalid), self.assertRaises(MetadataRepairError):
                normalise_source_status(invalid)

    def test_hiatus_repair_preserves_every_personal_field_and_old_status(self):
        base = {"version": 1, "books": [
            book(), book(OTHER_ID, "https://novelfull.com/other.html",
                         status="AncientRawStatus")
        ]}
        before = deepcopy(base)
        result, changed, _ = plan_repair(base, patch_data(status="on hold"))
        self.assertEqual(changed, ["status"])
        self.assertEqual(result["books"][0]["metadata"]["status"], "Hiatus")
        self.assertEqual(result["books"][1]["metadata"]["status"], "AncientRawStatus")
        self.assertEqual(result["books"][0]["metadata"]["progress"], 65)
        self.assertEqual(result["books"][0]["metadata"]["personalReview"], "A personal note")
        self.assertEqual(result["books"][0]["metadata"]["personalTags"], ["Favourite"])
        self.assertEqual(result["books"][0]["epubPath"], before["books"][0]["epubPath"])
        self.assertEqual(base, before)

    def test_tags_deduplicate_case_insensitively(self):
        normalized = validate_patch(patch_data(sourceTags=["Romance", " romance ", "Drama"]))
        self.assertEqual(normalized["sourceTags"], ["Romance", "Drama"])

    def test_no_private_output_outside_reports(self):
        with TemporaryDirectory() as d:
            before = Path.cwd()
            try:
                os.chdir(d)
                with self.assertRaisesRegex(MetadataRepairError, "reports"):
                    _report_path(Path("outside-private.csv"))
                with self.assertRaisesRegex(MetadataRepairError, "reports"):
                    _report_path(Path("reports/../outside-private.csv"))
            finally:
                os.chdir(before)


class RepairTransactionTests(unittest.TestCase):
    def test_preview_then_confirm_creates_only_catalogue_and_private_backup(self):
        with TemporaryDirectory() as d:
            previous = Path.cwd()
            try:
                os.chdir(d)
                Path("reports").mkdir()
                document = patch_data(description="An original synopsis", sourceTags=["Adventure"])
                Path("reports/metadata-repair.json").write_text(json.dumps(document), encoding="utf-8")
                current = {"version": 1, "books": [book()]}
                original = json.dumps(current).encode("utf-8")
                class FakeAPI:
                    def __init__(self):
                        self.commits = []
                        self.revision = "rev00000001"
                    def dataset_info(self, *args, **kwargs):
                        return SimpleNamespace(sha=self.revision)
                    def create_commit(self, **kwargs):
                        self.commits.append(kwargs)
                api = FakeAPI()
                loader = (api, api.revision, original, current)
                with patch("taiyou_storage.metadata_repair._load_private_catalogue", return_value=loader), \
                     patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
                    self.assertEqual(main(["preview"]), 0)
                    self.assertEqual(api.commits, [])
                    with patch("builtins.input", return_value="APPLY"):
                        self.assertEqual(main(["apply"]), 0)
                self.assertEqual(len(api.commits), 1)
                commit = api.commits[0]
                self.assertEqual(commit["parent_commit"], api.revision)
                self.assertEqual(len(commit["operations"]), 2)
                self.assertEqual({op.path_in_repo for op in commit["operations"]},
                                 {"data/library.json", next(op.path_in_repo for op in commit["operations"]
                                 if op.path_in_repo.startswith("backups/metadata-repair/"))})
                self.assertFalse(Path("reports/metadata-repair-preview.json").exists())
                self.assertFalse("progress" in document)
            finally:
                os.chdir(previous)

    def test_stale_revision_or_changed_patch_blocks_apply(self):
        with TemporaryDirectory() as d:
            previous = Path.cwd()
            try:
                os.chdir(d)
                Path("reports").mkdir()
                Path("reports/metadata-repair.json").write_text(
                    json.dumps(patch_data(status="Completed")), encoding="utf-8")
                source = {"version": 1, "books": [book()]}
                api = SimpleNamespace(dataset_info=lambda *a, **k: SimpleNamespace(sha="new"))
                with patch("taiyou_storage.metadata_repair._load_private_catalogue",
                           side_effect=[(api, "old", b"{}", source), (api, "new", b"{}", source)]), \
                     patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
                    self.assertEqual(main(["preview"]), 0)
                    with self.assertRaisesRegex(MetadataRepairError, "changed"):
                        main(["apply"])
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
