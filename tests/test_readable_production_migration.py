"""Production readable-migration safety gates.

All tests are offline and use fake private data. No actual dataset calls.
"""
import unittest
from unittest.mock import patch

from taiyou_storage.core import DEFAULT_REPO
from taiyou_storage.migrate_folders import MigrationError
from taiyou_storage.migrate_production import CONFIRM_PHRASE, execute

IDENT = "a" * 24
BACKUP = "AdityaSreevatsaK/Taiyous-Novels-Backup"
OLD = f"data/novels/{IDENT}"
BOOK = {
    "id": IDENT, "metadata": {"id": IDENT, "title": "Synthetic Voyage",
                              "progress": 55, "personalTags": ["Favourite"]},
    "epubPath": OLD + "/source.epub",
    "archivePath": OLD + "/original.zip",
}
FILES = {"data/library.json", OLD + "/source.epub", OLD + "/original.zip"}


class ProductionMigrationSafetyTests(unittest.TestCase):
    def test_preview_only_does_not_start_backup_or_commit(self):
        with patch("taiyou_storage.migrate_production._load",
                   return_value=({"version": 1, "books": [BOOK]}, "f" * 40, FILES)):
            with patch("taiyou_storage.migrate_production.copy_to_private_backup") as backup:
                result = execute(object(), "synthetic-token", BACKUP, apply=False)
                self.assertEqual(result["MIGRATE"], 1)
                backup.assert_not_called()

    def test_production_requires_verbatim_confirm_and_distinct_backup(self):
        with patch("taiyou_storage.migrate_production._load",
                   return_value=({"version": 1, "books": [BOOK]}, "f" * 40, FILES)):
            with patch("taiyou_storage.migrate_production.copy_to_private_backup") as backup:
                with self.assertRaisesRegex(MigrationError, "confirmation"):
                    execute(object(), "token", BACKUP, apply=True, confirmation="YES")
                backup.assert_not_called()
                with self.assertRaisesRegex(MigrationError, "Backup destination"):
                    execute(object(), "token", DEFAULT_REPO, apply=True,
                            confirmation=CONFIRM_PHRASE)
                backup.assert_not_called()

    def test_missing_authentication_and_collisions_abort_no_backup(self):
        with self.assertRaisesRegex(MigrationError, "TOKEN"):
            execute(None, "", BACKUP, apply=True, confirmation=CONFIRM_PHRASE)
        with patch("taiyou_storage.migrate_production._load",
                   return_value=({"version": 1, "books": [BOOK]}, "f" * 40,
                                 FILES | {f"data/novels/{IDENT} - Synthetic Voyage/other.txt"})):
            with patch("taiyou_storage.migrate_production.copy_to_private_backup") as backup:
                with self.assertRaisesRegex(MigrationError, "collision"):
                    execute(object(), "token", BACKUP, apply=True,
                            confirmation=CONFIRM_PHRASE)
                backup.assert_not_called()

    def test_backup_failure_prevents_any_migration_commit(self):
        with patch("taiyou_storage.migrate_production._load",
                   return_value=({"version": 1, "books": [BOOK]}, "f" * 40, FILES)):
            with patch("taiyou_storage.migrate_production.inventory",
                       return_value=("f" * 40, sorted(FILES))):
                with patch("taiyou_storage.migrate_production.copy_to_private_backup",
                           side_effect=RuntimeError("Backup failed")) as backup:
                    with patch("taiyou_storage.migrate_production.apply_migration_batch") as migrate:
                        with self.assertRaisesRegex(RuntimeError, "Backup failed"):
                            execute(object(), "token", BACKUP, apply=True,
                                    confirmation=CONFIRM_PHRASE)
                        backup.assert_called_once()
                        migrate.assert_not_called()

    def test_changed_revision_before_backup_refuses_migration(self):
        with patch("taiyou_storage.migrate_production._load",
                   return_value=({"version": 1, "books": [BOOK]}, "f" * 40, FILES)):
            with patch("taiyou_storage.migrate_production.inventory",
                       return_value=("e" * 40, sorted(FILES))):
                with patch("taiyou_storage.migrate_production.copy_to_private_backup") as backup:
                    with self.assertRaisesRegex(MigrationError, "changed"):
                        execute(object(), "token", BACKUP, apply=True,
                                confirmation=CONFIRM_PHRASE)
                    backup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
