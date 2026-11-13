# Human-readable Hugging Face novel folder migration

## Goal and invariants

The private dataset currently stores some novels as `data/novels/<id>/`. The new format is `data/novels/<id> - <sanitised-title>/`, so owners can recognise novels in the Hugging Face browser.

**Never change the 24-character book ID.** Reader progress, notes, ratings, tags, collections and other personal state remain keyed by that ID. Existing folder labels are historical display names: if a book is renamed later, its existing folder path stays unchanged.

The Storage Controller and Library App both accept *both formats* and can coexist during partial migrations. Novel EPUB, original ZIP, cover and additional files must stay together in the same folder. EPUB/ZIP/cover paths are read from the validated catalogue, not reconstructed from the current title.

## Status and safety

- Readable-path compatibility: implemented in controller and reader source.
- New web reader uploads: create readable directories after the reader's verified deployment.
- Read-only full-production migration plan: `python -m taiyou_storage.migrate_folders`.
- Actual production migration: **only** the dedicated manual GitHub workflow `HF - Safely migrate readable novel folders` can request this; default is preview-only.
- The standard local CLI `migrate_folders --apply` **refuses the production dataset**. It is solely for disposable testing.
- No work on the controller alone can prove the production Cloudflare reader is deployed.

## Mandatory gates before a production move

1. Latest reader `master` has passed the **production** `Deploy Application` workflow, with the exact master SHA deployed.
2. The latest `test/readable-folder-batch-acceptance-20261113` branch has a successful `Readable Folder Cross-Repo Acceptance` workflow at its **exact current head SHA**. This tests `apply_migration_batch()` in multiple commits against the **existing, pre-created private** Hugging Face test dataset `AdityaSreevatsaK/Taiyou-Readable-Folder-Test`. The workflow must restore that dataset to its original inventory without deleting the dataset.
3. The entire real dataset is inventoried and all catalogue entries are validated. Missing source EPUB/ZIP/cover, unexpected destination files and unsafe source paths abort *all* writes.
4. A different **private** Hugging Face dataset (default `AdityaSreevatsaK/Taiyous-Novels-Backup`) is accessible by the token with write rights. The complete original dataset must be copied into a revision-keyed snapshot and every copied file independently SHA-256 verified.
5. No remote change occurred during backup. The source SHA is rechecked before starting any migration.
6. Explicit workflow input `apply_changes=true` and exact phrase `MIGRATE READABLE NOVEL FOLDERS` are required.

If any gate fails, **do not bypass it**. Fix credentials/configuration and re-run the *read-only preview*.

## How the operation works

The production workflow's Python entrypoint is `taiyou_storage.migrate_production`.

- Read and validate the existing catalogue and dataset inventory, build an ID-preserving plan, and report **counts only** in public logs.
- Make and verify a **complete private backup**, including reviews/progress/collections under `data/personal/`, all novel files and other repository content.
- Group movable novels into bounded atomic commits (default at most 8 novels and 70 operations per commit, or fewer when needed). Live pre-production acceptance has verified two novels in one commit and a subsequent commit.
- For each group, re-read the current private dataset SHA, catalogue and paths. Reject drift, changed identity, missing files or destination collisions.
- Atomically copy each source file into its new labelled directory, remove the old path and update `data/library.json` in a single Hugging Face commit with `parent_commit` set.
- Verify the returned SHA matches the live dataset revision and every destination file exists while old paths are absent.
- Verify **SHA-256 equality for every moved file**, comparing immutable old and new remote revisions.
- Check final book IDs, catalogue count, folder statuses, and all `data/personal/` sidecar paths.

The private backup remains available after success. File moves are recoverable through the prior Hugging Face revision and verified private snapshot, but this project does **not** yet offer an automatic full restore.

## Failure and resume

The full library move is **not one transaction**; batches are separate commits. A failure can leave some novels readable and some legacy. This is expected and supported.

On failure:

1. Leave the dataset untouched. Never run the full reset.
2. Re-run read-only preview.
3. Already migrated entries must show `ALREADY_READABLE`, with unchanged IDs and contents.
4. Fix the blocker. A fresh complete private backup and latest-revision check must precede any new apply.
5. Resume only the remaining `MIGRATE` entries.

GitHub workflow public logs must never include real novel titles, original filenames, personal notes or catalogue content.

## Authentication blockers

The real disposable test uses the **manually created PRIVATE** dataset `AdityaSreevatsaK/Taiyou-Readable-Folder-Test`. `HF_DISPOSABLE_TEST_TOKEN` only needs **read/write permissions on that exact test dataset**. No repository creation or deletion permission is required. The runner refuses public, nonempty or other target datasets; it removes only its own synthetic files using a revision-guarded cleanup, retaining the test dataset.

For the production backup, `HF_STORAGE_CONTROLLER_TOKEN` requires **read access** to `Taiyous-Novels` and **write access** to the separate **PRIVATE** `AdityaSreevatsaK/Taiyous-Novels-Backup` dataset. The 13 November read-only check could not access that backup dataset; it must be created privately by the owner or its token permissions corrected. The backup helper can create a missing private repo only with appropriate creation rights, but widening a production token merely to bypass a permission error is not recommended.

Until the live disposable acceptance has **actually passed**, the production migration workflow intentionally refuses production writes.

## Useful files

- `taiyou_storage/paths.py`: sanitised labels, legacy/readable path validation.
- `taiyou_storage/migrate_folders.py`: preview, deterministic planning, bounded group commits.
- `taiyou_storage/migrate_production.py`: private snapshot and checksum verification orchestration.
- `tests/test_readable_folders.py` and `tests/test_readable_production_migration.py`: regression and abort-path tests.
- `.github/workflows/hf-migrate-readable-folders.yml`: manually approved backup-first production workflow.
- The reader's `src/lib/novel-paths.ts`: browser and Cloudflare gateway path contract.

Do not treat adding this documentation or merging controller code as proof that existing production folders have actually been renamed. Confirm the production Hugging Face dataset inventory after a successful live migration.


## Current coordination and production boundary

- Reader `master` `45233f4854b657d146965cf71a38142289411b18` passed the existing production `Deploy Application` run `43404544333` with dual-format support and readable-folder creation for new browser uploads.
- The earlier **read-only** production preview showed **89 legacy novel folders**, **zero collisions**, and no already-readable book folders. This is historical until the next read-only run refreshes it.
- Live private integration on the manually created test dataset has verified `apply_one()` (run `43431262417`) and the production-style `apply_migration_batch()` over two consecutive commits (see the latest successful run on the consolidation branch).
- The reader path/gateway tests are mocked. Successful deployment alone is **not proof** of an authenticated live EPUB/cover/archive browser session. An authenticated owner smoke test is required before production moves.
- **Never invoke production migration apply** as part of testing, consolidation or backup-readiness checks. It requires a separate, explicit approval.
