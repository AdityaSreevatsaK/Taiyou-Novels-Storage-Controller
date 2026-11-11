"""Offline, read-only contract tests for private catalogue metadata backfill."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import unittest
from zipfile import ZipFile

from taiyou_storage.genre_repair import (
    read_first_batch_metadata, plan_repair, from_registry, source_key, subject_genres,
)

URL = "https://novelfull.com/chaotic-sword-god.html"
ALT_URL = "https://novelfull.com/crazy-detective.html"


def book(ident="a" * 24, url=URL, **other):
    return {"id": ident, "epubPath": f"data/novels/{ident}/source.epub",
            "archivePath": f"data/novels/{ident}/original.zip",
            "metadata": {"id": ident, "title": "Sample", "author": "Author",
                         "sourceUrl": url, "personalTags": ["Favourite"],
                         "progress": 74, "currentChapter": "400",
                         "personalRating": 5, "personalReview": "Keep me", **other}}


def synthetic_artifact(url=URL):
    container = ('<container><rootfile full-path="OEBPS/content.opf"/></container>')
    package = ('<package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata>'
               '<dc:subject>Action</dc:subject><dc:subject>Martial Arts</dc:subject>'
               '<dc:subject>Last Update: 2026/11/08</dc:subject><dc:subject>Completed</dc:subject>'
               '<dc:description>A novel about progress.</dc:description></metadata></package>')
    epub = BytesIO()
    with ZipFile(epub, "w") as z:
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", package)
    outer = BytesIO()
    with ZipFile(outer, "w") as z:
        z.writestr("book/metadata.json", json.dumps({"source_url": url}))
        z.writestr("book/source.epub", epub.getvalue())
    return outer.getvalue()


class GenreRepairTests(unittest.TestCase):
    def test_opf_extraction_preserves_real_genres_ignoring_status_and_dates(self):
        found = read_first_batch_metadata(synthetic_artifact(), URL)
        self.assertEqual(found, {"genres": ["Action", "Martial Arts"],
                                 "status": "Completed", "description": "A novel about progress."})

    def test_rejects_other_novel_even_when_artifact_has_subjects(self):
        with self.assertRaisesRegex(ValueError, "source URL"):
            read_first_batch_metadata(synthetic_artifact(), ALT_URL)

    def test_preserve_personal_fields_and_existing_ids(self):
        original = {"version": 1, "books": [book()]}
        before = deepcopy(original)
        result, stats = plan_repair(original, {source_key(URL): read_first_batch_metadata(synthetic_artifact(), URL)})
        self.assertEqual(stats["tagged"], 1)
        self.assertEqual(result["books"][0]["metadata"]["sourceTags"], ["Action", "Martial Arts"])
        self.assertEqual(result["books"][0]["metadata"]["description"], "A novel about progress.")
        self.assertEqual(result["books"][0]["metadata"]["status"], "Completed")
        self.assertEqual(result["books"][0]["metadata"]["personalTags"], ["Favourite"])
        self.assertEqual(result["books"][0]["metadata"]["progress"], 74)
        self.assertEqual(result["books"][0]["metadata"]["personalReview"], "Keep me")
        self.assertEqual(result["books"][0]["id"], "a" * 24)
        self.assertEqual(original, before, "Preview must not mutate source document")

    def test_never_overwrites_existing_source_tags_or_descriptions(self):
        original = {"version": 1, "books": [book(sourceTags=["Handpicked"], description="Existing") ]}
        result, stats = plan_repair(original, {source_key(URL): {"genres": ["Comedy"], "description": "Different"}})
        self.assertEqual(result, original)
        self.assertEqual(stats["tagged"], 0)

    def test_duplicate_url_is_skipped_without_guessing_even_if_one_entry_is_tagged(self):
        duplicate = {"version": 1, "books": [book(), book("b" * 24, sourceTags=["Romance"])]}
        result, stats = plan_repair(duplicate, {source_key(URL): {"genres": ["Fantasy"]}})
        self.assertNotIn("sourceTags", result["books"][0]["metadata"])
        self.assertEqual(stats["ambiguous_source"], 1)
        self.assertEqual(stats["already_tagged"], 1)

    def test_unknown_or_absent_genres_do_not_create_empty_fields(self):
        result, stats = plan_repair({"version": 1, "books": [book()]}, {})
        self.assertNotIn("sourceTags", result["books"][0]["metadata"])
        self.assertEqual(stats["missing_genres"], 1)

    def test_registry_mapping_downloads_once_for_unique_full_novel(self):
        class FakeGH:
            def __init__(self): self.calls = []
            def first_batch(self, url, run_id):
                self.calls.append((url, run_id))
                return read_first_batch_metadata(synthetic_artifact(), url)
        gh = FakeGH()
        registry = {"novels": [{"url": URL, "downloads": [{"range": "all", "status": "complete", "run_id": 42}]}]}
        result, stats = from_registry({"version": 1, "books": [book()]}, registry, gh)
        self.assertEqual(gh.calls, [(URL, 42)])
        self.assertEqual(stats["tagged"], 1)
        self.assertEqual(result["books"][0]["metadata"]["sourceTags"], ["Action", "Martial Arts"])

    def test_source_normalisation_matches_only_same_site_and_path(self):
        self.assertEqual(source_key("https://www.novelfull.com/Chaotic-Sword-God.html?ref=x"),
                         source_key(URL))
        self.assertNotEqual(source_key(URL), source_key(ALT_URL))
        self.assertEqual(subject_genres(["In-Progress", "Mystery", "Last Update Year/Month: 2026/11"]), ["Mystery"])

if __name__ == "__main__":
    unittest.main()