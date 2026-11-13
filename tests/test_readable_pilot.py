"""Safety tests for the deliberately ONE-novel production migration pilot.

All data is fictional and every Hugging Face operation is mocked.
"""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from taiyou_storage.migrate_folders import MigrationError, plan_migration
from taiyou_storage.migrate_production import (
    CONFIRM_PHRASE, execute, select_pilot_candidate,
)

BACKUP = "AdityaSreevatsaK/Taiyous-Novels-Backup"
FIRST = "a" * 24
SECOND = "b" * 24


def book(book_id: str) -> dict:
    folder = "data/novels/" + book_id
    return {
        "id": book_id,
        "metadata": {
            "id": book_id, "title": "Fictional Book " + book_id[0],
            "coverPath": folder + "/cover.png",
            "progress": 73, "personalTags": ["Keep"],
        },
        "epubPath": folder + "/source.epub",
        "archivePath": folder + "/original.zip",
    }


def paths(books: list[dict]) -> set[str]:
    files = {"data/library.json", "data/personal/collections.json"}
    for item in books:
        files.update((item["epubPath"], item["archivePath"]))
        if item["metadata"].get("coverPath"):
            files.add(item["metadata"]["coverPath"])
    return files


class OneNovelPilotTests(unittest.TestCase):
    def test_deterministic_selection_with_epub_original_zip_and_cover(self):
        books = [book(SECOND), book(FIRST)]
        plan = plan_migration(books, paths(books))
        self.assertEqual(select_pilot_candidate(plan, books)["id"], FIRST)
        self.assertEqual(select_pilot_candidate(list(reversed(plan)), books)["id"], FIRST)

    def test_missing_linked_cover_rejects_pilot_before_backup(self):
        item = book(FIRST)
        del item["metadata"]["coverPath"]
        catalogue = {"version": 1, "books": [item]}
        with patch("taiyou_storage.migrate_production._load",
                   return_value=(catalogue, "f" * 40, paths([item]))):
            with patch("taiyou_storage.migrate_production.copy_to_private_backup") as backup:
                with self.assertRaisesRegex(MigrationError, "EPUB, original ZIP and linked cover"):
                    execute(Mock(), "fake-token", BACKUP, apply=True,
                            confirmation=CONFIRM_PHRASE, pilot_only=True)
                backup.assert_not_called()

    def test_pilot_executes_only_one_commit_after_full_verified_backup(self):
        books = [book(SECOND), book(FIRST)]
        catalogue = {"version": 1, "books": books}
        before_paths = paths(books)
        initial_plan = plan_migration(books, before_paths)
        selected = select_pilot_candidate(initial_plan, books)
        self.assertEqual(selected["id"], FIRST)

        migrated = copy.deepcopy(catalogue)
        updated = next(item for item in migrated["books"] if item["id"] == FIRST)
        old = "data/novels/" + FIRST
        new = selected["new"]
        updated["epubPath"] = new + "/source.epub"
        updated["archivePath"] = new + "/original.zip"
        updated["metadata"]["coverPath"] = new + "/cover.png"
        final_paths = set(before_paths)
        for old_file, new_file in selected["moves"]:
            final_paths.remove(old_file)
            final_paths.add(new_file)

        api = Mock()
        api.dataset_info.side_effect = [
            SimpleNamespace(private=True, sha="f" * 40),
            SimpleNamespace(private=True, sha="e" * 40),
        ]
        api.list_repo_files.return_value = sorted(final_paths)
        with patch("taiyou_storage.migrate_production._load",
                   side_effect=[(catalogue, "f" * 40, before_paths),
                                (migrated, "e" * 40, final_paths)]), \
             patch("taiyou_storage.migrate_production.inventory",
                   return_value=("f" * 40, sorted(before_paths))), \
             patch("taiyou_storage.migrate_production.copy_to_private_backup") as backup, \
             patch("taiyou_storage.migrate_production.apply_migration_batch",
                   return_value="e" * 40) as apply, \
             patch("taiyou_storage.migrate_production.verify_moved_bytes") as hashes:
            result = execute(api, "fake-token", BACKUP, apply=True,
                             confirmation=CONFIRM_PHRASE, pilot_only=True)

        self.assertEqual(result["changed"], 1)
        self.assertEqual(result["MIGRATE"], 2)
        backup.assert_called_once_with(api, BACKUP, "fake-token",
                                       "f" * 40, sorted(before_paths))
        apply.assert_called_once()
        args, kwargs = apply.call_args
        self.assertEqual(args[1], "AdityaSreevatsaK/Taiyous-Novels")
        self.assertEqual(len(args[3]), 1)
        self.assertEqual(args[3][0]["id"], FIRST)
        self.assertTrue(kwargs["production_backup_verified"])
        hashes.assert_called_once()
        self.assertEqual(migrated["books"][0], catalogue["books"][0])
        self.assertEqual(len(final_paths), len(before_paths))

    def test_pilot_rejects_confirmation_failure_before_backup(self):
        books = [book(FIRST)]
        with patch("taiyou_storage.migrate_production._load",
                   return_value=({"version": 1, "books": books},
                                 "f" * 40, paths(books))):
            with patch("taiyou_storage.migrate_production.copy_to_private_backup") as backup:
                with self.assertRaisesRegex(MigrationError, "confirmation"):
                    execute(Mock(), "fake-token", BACKUP, apply=True,
                            confirmation="wrong", pilot_only=True)
                backup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
