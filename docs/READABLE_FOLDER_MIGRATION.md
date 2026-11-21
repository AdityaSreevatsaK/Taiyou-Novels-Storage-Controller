# Human-readable Hugging Face novel folder migration

> **Historical migration record:** Production folder migration was completed and
> verified on 14 November 2026. The one-shot pilot, acceptance, readiness and
> production migration GitHub Actions have since been retired. The steps below
> document the original safety gates and are **not current runnable Actions**.
> Current library checks use `HF - Run library checks (read only)`. Do not
> re-enable production migration without a separate engineering review.

## Goal and invariants

The private dataset historically stored novels as `data/novels/<id>/`. The migrated format is `data/novels/<id> - <sanitised-title>/`, so owners can recognise novels in the Hugging Face browser.

**Never change the 24-character book ID.** Reader progress, notes, ratings, tags, collections and other personal state remain keyed by that ID. Existing folder labels are historical display names: if a book is renamed later, its existing folder path stays unchanged.

The Storage Controller and Library App both accept *both formats* and can coexist during partial migrations. Novel EPUB, original ZIP, cover and additional files must stay together in the same folder. EPUB/ZIP/cover paths are read from the validated catalogue, not reconstructed from the current title.

## Status and safety

- Readable-path compatibility: implemented in controller and reader source.
- New web reader uploads: create readable directories after the reader's verified deployment.
- Read-only full-production migration plan: `python -m taiyou_storage.migrate_folders`.
- Actual production migration: **completed on 14 November 2026**; the former manual migration workflow was retired.
- The standard local CLI `migrate_folders --apply` **refuses the production dataset**. It is solely for disposable testing.
- No work on the controller alone can prove the production Cloudflare reader is deployed.

## Historical mandatory gates used for the completed production move (not a current runbook)

1. Latest reader `master` has passed the **production** `Deploy Application` workflow, with the exact master SHA deployed.
2. The latest `test/readable-folder-batch-acceptance-20261113` branch has a successful `Readable Folder Cross-Repo Acceptance` workflow at its **exact current head SHA**. This tests `apply_migration_batch()` in multiple commits against the **existing, pre-created private** Hugging Face test dataset `AdityaSreevatsaK/Taiyou-Readable-Folder-Test`. The workflow must restore that dataset to its original inventory without deleting the dataset.
3. The entire real dataset is inventoried and all catalogue entries are validated. Missing source EPUB/ZIP/cover, unexpected destination files and unsafe source paths abort *all* writes.
4. A different **private** Hugging Face dataset (default `AdityaSreevatsaK/Taiyous-Novels-Backup`) is accessible by the token with write rights. The complete original dataset must be copied into a revision-keyed snapshot and every copied file independently SHA-256 verified.
5. No remote change occurred during backup. The source SHA is rechecked before starting any migration.
6. Explicit workflow input `apply_changes=true` and exact phrase `MIGRATE READABLE NOVEL FOLDERS` are required.

These were the gates for the November 2026 migration. The one-shot workflow and temporary branch are now retired; do not attempt to satisfy this checklist by recreating or dispatching the old workflow.

## How the historical operation worked

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

## Historical failure and resume behaviour

The migration was **not one transaction**; batches were separate commits. The implementation could leave some novels readable and some legacy after an interrupted run, then re-plan against the latest revision. The production migration subsequently completed and was independently audited. Its one-shot workflow is retired, so do not try to resume it through the old Actions procedure.

For current novel uploads, use the active preview/replan/resume process in [Smart upload](SMART_UPLOAD.md). GitHub workflow public logs must never include real novel titles, original filenames, personal notes or catalogue content.

## Authentication blockers

The historical disposable test used the **manually created PRIVATE** dataset `AdityaSreevatsaK/Taiyou-Readable-Folder-Test`. The retired workflow used `HF_DISPOSABLE_TEST_TOKEN` scoped to that test dataset only; no repository creation or deletion permission was required. The historical runner refused public, nonempty or other target datasets and removed only its own synthetic files using revision-guarded cleanup. The old workflow is not available on current `master`; do not create or grant a token merely to follow this historical document.

For the production backup, `HF_STORAGE_CONTROLLER_TOKEN` requires **read access** to `Taiyous-Novels` and **write access** to the separate **PRIVATE** `AdityaSreevatsaK/Taiyous-Novels-Backup` dataset. Both permissions were verified for the completed 14 November production migration. The backup dataset must remain private; do not broaden token scopes unnecessarily.

The live disposable acceptance passed before production migration. The production migration workflow was retired after the verified 14 November completion. Any future migration would require a new scoped design, fresh approval, new tests and independently verified backup; this document does not authorise it.

## Useful files

- `taiyou_storage/paths.py`: sanitised labels, legacy/readable path validation.
- `taiyou_storage/migrate_folders.py`: preview, deterministic planning, bounded group commits.
- `taiyou_storage/migrate_production.py`: private snapshot and checksum verification orchestration.
- `tests/test_readable_folders.py` and `tests/test_readable_production_migration.py`: regression and abort-path tests.
- The former manually approved backup-first production workflow was retired after successful migration.
- The reader's `src/lib/novel-paths.ts`: browser and Cloudflare gateway path contract.

For the November 2026 migration, the production run and independent read-only audit above are the evidence that folders were renamed. For any future change, a code merge or documentation update alone is never proof of a live HF data change.


## Historical coordination and production boundary

- Reader `master` `45233f4854b657d146965cf71a38142289411b18` passed the existing production `Deploy Application` run `43404544333` with dual-format support and readable-folder creation for new browser uploads.
- The pre-migration **read-only** preview showed **89 legacy novel folders**, **zero collisions**, and no already-readable book folders. This is historical pre-migration evidence, not the current inventory.
- Live private integration on the manually created test dataset has verified `apply_one()` (run `43431262417`) and the production-style `apply_migration_batch()` over two consecutive commits (see the latest successful run on the consolidation branch).
- The reader path/gateway tests were mocked. The single-book production pilot was manually accepted, but an exhaustive authenticated multi-book browser smoke test for EPUBs, covers, ZIP downloads, offline caching and cross-device progress was not recorded. This remains a separate Reader verification gap; do not rerun the completed storage migration to address it.
- **Never invoke production migration apply** as part of testing, consolidation or backup-readiness checks. It requires a separate, explicit approval.


## Completed migration: 14 November 2026

The one-novel production pilot passed in run [43486112141](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/43486112141). The final workflow [43558185178](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/43558185178) succeeded with the remaining **88 novels in 11 batches**, each verifying every moved file by SHA-256. It preserved **all 89 stable novel IDs** and all personal sidecar paths, with a **221-file private snapshot** verified before writes. At the start of this final run, the production preview showed 88 legacy and 1 readable novel, with zero conflicts. The run's end-state validation required every book to be readable. Final private dataset revision prefix: `5d168f6e6a46`.

The post-migration audit is recorded in [POST_MIGRATION_VERIFICATION_2026-11-14.md](POST_MIGRATION_VERIFICATION_2026-11-14.md). Do not rerun the write-mode workflow merely to check status. Use read-only preview. Both legacy and readable path formats remain supported for backwards compatibility; future title edits must not automatically rename existing folders.
