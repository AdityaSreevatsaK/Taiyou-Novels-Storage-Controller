"""Synthetic tests: safe public book-page parsing and multi-novel HF repair."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from taiyou_storage.metadata_batch import (
    CANDIDATES, APPROVALS, PREVIEW, _targets, discover_candidates,
    main, plan_batch,
)
from taiyou_storage.metadata_repair import MetadataRepairError, _save_private_json
from taiyou_storage.metadata_source import (
    SourceUnavailable, checked_book_url, verified_metadata,
)

FREE = "https://freewebnovel.com/novel/sample-fantasy"
NOVEL = "https://novelfull.com/abe-the-wizard.html"
NOT_AVAILABLE = "https://www.scribblehub.com/series/445037/not-available/"
ID1, ID2, ID3 = "a" * 24, "b" * 24, "c" * 24
ABOUT = ("After unexpectedly arriving in a new world, a young scholar tries to "
         "understand a magical relic and gradually becomes involved in its mysteries.")
FREE_HTML = f"""<html><title>Sample Fantasy Novel</title><body>
<nav><a href="/genre/Yaoi">Yaoi</a><a href="/sort/completed-novel">Completed Novels</a></nav>
<h3>Sample Fantasy</h3><a href="/author/test-writer">Test Writer</a>
<a href="/genre/Fantasy">Fantasy</a> <a href="/genre/Romance">Romance</a>
<a href="/latest-release">OnGoing</a><h1>Sample Fantasy</h1>
<h4>SUMMARY</h4><p>{ABOUT}</p><a href="/other">See all</a>
<h3>Chapter List</h3><a href="{FREE}/chapter-1">Chapter 1</a>
<aside><a href="/genre/Harem">Harem</a></aside>
</body></html>"""
NOVEL_HTML = f"""<html><body><nav><a href="/genre/Adult">Adult</a></nav>
<div class="info"><h3>Abe the Wizard</h3>
<ul class="info-meta"><li>Author: <a href="/author/test">The Mass Of Eating Melon Seeds</a></li>
<li>Genre: <a href="/genre/Fantasy">Fantasy</a> <a href="/genre/Action">Action</a></li>
<li>Status: <a href="/status/Completed">Completed</a></li></ul></div>
<div class="desc-text">{ABOUT}</div>
<div class="hot-books"><a href="/genre/Harem">Harem</a></div></body></html>"""


def record(ident, title, author, url, **fields):
    return {
        "id": ident,
        "epubPath": f"data/novels/{ident}/source.epub",
        "archivePath": f"data/novels/{ident}/original.zip",
        "metadata": {
            "id": ident, "title": title, "author": author, "sourceUrl": url,
            "sourceTags": [], "progress": 74, "personalTags": ["Keep"],
            "personalRating": 10, "coverPath": f"data/novels/{ident}/cover.jpg",
            **fields,
        },
    }


def catalogue():
    return {"version": 1, "books": [
        record(ID1, "Sample Fantasy", "Test Writer", FREE),
        record(ID2, "Abe the Wizard", "The Mass Of Eating Melon Seeds", NOVEL,
               description="Existing synopsis"),
        record(ID3, "Missing Source", "Someone", NOT_AVAILABLE),
    ]}


class PublicSourceTests(unittest.TestCase):
    def test_freewebnovel_scoped_fields_and_summary(self):
        data = verified_metadata(FREE_HTML, FREE, "Sample Fantasy", "Test Writer")
        self.assertEqual(data, {
            "description": ABOUT, "sourceTags": ["Fantasy", "Romance"], "status": "Ongoing",
        })
        self.assertNotIn("Yaoi", data["sourceTags"])
        self.assertNotIn("Harem", data["sourceTags"])

    def test_novelfull_scoped_genres_and_status(self):
        result = verified_metadata(
            NOVEL_HTML, NOVEL, "Abe the Wizard", "The Mass Of Eating Melon Seeds"
        )
        self.assertEqual(result["sourceTags"], ["Fantasy", "Action"])
        self.assertEqual(result["status"], "Completed")
        self.assertEqual(result["description"], ABOUT)
        self.assertNotIn("Adult", result["sourceTags"])

    def test_mismatching_title_and_author_fail_without_suggestions(self):
        with self.assertRaisesRegex(SourceUnavailable, "author"):
            verified_metadata(FREE_HTML, FREE, "Sample Fantasy", "Other writer")
        with self.assertRaisesRegex(SourceUnavailable, "heading"):
            verified_metadata(FREE_HTML, FREE, "Another book", "Test Writer")
        with self.assertRaisesRegex(SourceUnavailable, "author"):
            verified_metadata(NOVEL_HTML, NOVEL, "Abe the Wizard", "Incorrect Author")

    def test_challenge_and_unexpected_urls_fail_closed(self):
        for url in (
            "http://freewebnovel.com/novel/sample-fantasy",
            "https://freewebnovel.com/novel/sample-fantasy/chapter-2",
            "https://freewebnovel.com.evil.test/novel/sample-fantasy",
            "https://novelfull.com/chapter-1",
            "https://scribblehub.com/series/12/book/?abc=1",
            "https://169.254.169.254/latest/meta-data/",
        ):
            with self.subTest(url=url), self.assertRaises(SourceUnavailable):
                checked_book_url(url)
        with self.assertRaises(SourceUnavailable):
            verified_metadata(
                "<title>Just a moment...</title><h1>Sample Fantasy</h1>",
                FREE, "Sample Fantasy", "Test Writer",
            )


class MetadataBatchTests(unittest.TestCase):
    def test_discover_checks_only_existing_book_urls_once_and_flags_failures(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if url == FREE: return FREE_HTML
            if url == NOVEL: return NOVEL_HTML
            raise SourceUnavailable("Source returned HTTP 404")
        original = catalogue()
        before = deepcopy(original)
        data, rows = discover_candidates(
            original, "private/test", "test-revision", fetcher=fetch,
            sleeper=lambda seconds: None,
        )
        self.assertEqual(calls, [FREE, NOVEL, NOT_AVAILABLE])
        self.assertEqual(original, before)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["state"], "SOURCE_VERIFIED")
        self.assertEqual(rows[0]["unresolved_fields"], "")
        self.assertEqual(rows[1]["verified_fields"], "sourceTags,status")
        self.assertEqual(rows[2]["state"], "REVIEW_REQUIRED")
        self.assertEqual(rows[2]["unresolved_fields"], "description,sourceTags,status")
        self.assertEqual(data["items"][2]["proposed"], {})

    def test_stale_csv_rejected_before_source_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = Path.cwd()
            try:
                os.chdir(tmp)
                Path("reports").mkdir()
                f = Path("reports/missing-source-metadata.csv")
                f.write_text("id,source_url,missing_fields\n" +
                             f"{ID1},{FREE},sourceTags\n", encoding="utf-8")
                with self.assertRaisesRegex(MetadataRepairError, "stale"):
                    _targets(catalogue(), f)
                self.assertEqual(len(_targets(catalogue(), None)), 3)
            finally:
                os.chdir(before)

    def test_batch_plan_adds_only_missing_fields_for_approved_records(self):
        source = catalogue()
        data, _ = discover_candidates(source, "private/test", "rev", fetcher=lambda url:
                  {FREE: FREE_HTML, NOVEL: NOVEL_HTML}[url]
                  if url != NOT_AVAILABLE else (_ for _ in ()).throw(SourceUnavailable("404")),
                  sleeper=lambda _: None)
        digest = "sha256-placeholder"
        approval = {
            "version": 1, "dataset": "private/test", "revision": "rev",
            "candidates_sha256": digest,
            "approved_ids": [ID1, ID2],
        }
        result, changes = plan_batch(source, data, approval, "private/test", "rev", digest)
        self.assertEqual(changes, [
            {"id": ID1, "fields": ["description", "sourceTags", "status"]},
            {"id": ID2, "fields": ["sourceTags", "status"]},
        ])
        self.assertEqual(source["books"][0]["metadata"]["progress"], 74)
        self.assertEqual(result["books"][0]["metadata"]["sourceTags"], ["Fantasy", "Romance"])
        self.assertEqual(result["books"][0]["metadata"]["status"], "Ongoing")
        self.assertEqual(result["books"][1]["metadata"]["description"], "Existing synopsis")
        self.assertEqual(result["books"][2], source["books"][2])
        for previous, updated in zip(source["books"], result["books"]):
            self.assertEqual(previous["epubPath"], updated["epubPath"])
            self.assertEqual(previous["archivePath"], updated["archivePath"])
            self.assertEqual(previous["metadata"]["coverPath"], updated["metadata"]["coverPath"])
            self.assertEqual(previous["metadata"]["personalTags"], updated["metadata"]["personalTags"])
            self.assertEqual(previous["metadata"]["personalRating"], updated["metadata"]["personalRating"])

    def test_ambiguous_or_unverified_approvals_block_entire_plan(self):
        source = catalogue()
        data, _ = discover_candidates(source, "private/test", "rev",
            fetcher=lambda u: FREE_HTML if u == FREE else (_ for _ in ()).throw(SourceUnavailable("404")),
            sleeper=lambda _: None)
        approvals = {
            "version": 1, "dataset": "private/test", "revision": "rev",
            "candidates_sha256": "abc", "approved_ids": [ID1, ID3],
        }
        with self.assertRaisesRegex(MetadataRepairError, "lacks verified"):
            plan_batch(source, data, approvals, "private/test", "rev", "abc")
        approvals["approved_ids"] = [ID1, ID1]
        with self.assertRaisesRegex(MetadataRepairError, "duplicate"):
            plan_batch(source, data, approvals, "private/test", "rev", "abc")
        approvals["approved_ids"] = [ID1]
        with self.assertRaisesRegex(MetadataRepairError, "different catalogue revision"):
            plan_batch(source, data, approvals, "private/test", "new", "abc")

    def test_every_update_has_private_backup_and_catalogue_only(self):
        with tempfile.TemporaryDirectory() as temp:
            old = Path.cwd()
            try:
                os.chdir(temp)
                Path("reports").mkdir()
                current = catalogue()
                original = json.dumps(current).encode("utf-8")
                document, rows = discover_candidates(
                    current, "private/test", "abc123",
                    fetcher=lambda u: {FREE: FREE_HTML, NOVEL: NOVEL_HTML}[u]
                    if u != NOT_AVAILABLE else (_ for _ in ()).throw(SourceUnavailable("404")),
                    sleeper=lambda _: None,
                )
                _save_private_json(CANDIDATES, document)
                candidate_raw = CANDIDATES.read_bytes()
                _save_private_json(APPROVALS, {
                    "version": 1, "dataset": "private/test", "revision": "abc123",
                    "candidates_sha256": sha256(candidate_raw).hexdigest(),
                    "approved_ids": [ID1, ID2],
                })
                class FakeApi:
                    def __init__(self):
                        self.commits = []
                        self.sha = "abc123"
                    def dataset_info(self, *args, **kwargs):
                        return SimpleNamespace(sha=self.sha)
                    def create_commit(self, **kwargs):
                        self.commits.append(kwargs)
                api = FakeApi()
                with patch("taiyou_storage.metadata_batch._load_private_catalogue",
                           return_value=(api, "abc123", original, current)), \
                     patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
                    self.assertEqual(main(["preview", "--repo", "private/test"]), 0)
                    self.assertEqual(api.commits, [])
                    with patch("builtins.input", return_value="APPLY 2"):
                        self.assertEqual(main(["apply", "--repo", "private/test"]), 0)
                self.assertEqual(len(api.commits), 1)
                commit = api.commits[0]
                self.assertEqual(commit["parent_commit"], "abc123")
                self.assertEqual(len(commit["operations"]), 2)
                names = [op.path_in_repo for op in commit["operations"]]
                self.assertIn("data/library.json", names)
                self.assertEqual(sum(path.startswith("backups/metadata-repair/")
                                     for path in names), 1)
                self.assertFalse(PREVIEW.exists())
            finally:
                os.chdir(old)

    def test_changed_approval_or_remote_revision_blocks_apply(self):
        with tempfile.TemporaryDirectory() as temp:
            old = Path.cwd()
            try:
                os.chdir(temp)
                Path("reports").mkdir()
                source = catalogue()
                document, _ = discover_candidates(
                    source, "private/test", "abc123",
                    fetcher=lambda u: FREE_HTML if u == FREE
                    else (_ for _ in ()).throw(SourceUnavailable("unreachable")),
                    sleeper=lambda _: None,
                )
                _save_private_json(CANDIDATES, document)
                _save_private_json(APPROVALS, {
                    "version": 1, "dataset": "private/test", "revision": "abc123",
                    "candidates_sha256": sha256(CANDIDATES.read_bytes()).hexdigest(),
                    "approved_ids": [ID1],
                })
                api = SimpleNamespace(dataset_info=lambda *a, **k: SimpleNamespace(sha="DIFFERENT"))
                with patch("taiyou_storage.metadata_batch._load_private_catalogue",
                           return_value=(api, "abc123", b"{}", source)), \
                     patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
                    self.assertEqual(main(["preview", "--repo", "private/test"]), 0)
                    APPROVALS.write_text(APPROVALS.read_text() + " ", encoding="utf-8")
                    with self.assertRaisesRegex(MetadataRepairError, "Preview"):
                        main(["apply", "--repo", "private/test"])
                    self.assertEqual(main(["preview", "--repo", "private/test"]), 0)
                    with patch("builtins.input", return_value="APPLY 1"):
                        with self.assertRaisesRegex(MetadataRepairError, "revision"):
                            main(["apply", "--repo", "private/test"])
            finally:
                os.chdir(old)

    def test_public_actions_can_never_discover_or_apply(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            for action in ("discover", "review", "preview", "apply"):
                with self.subTest(action=action), self.assertRaisesRegex(MetadataRepairError, "locally"):
                    main([action])


if __name__ == "__main__":
    unittest.main()
