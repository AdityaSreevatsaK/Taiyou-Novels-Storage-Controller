# Readable-folder migration: production completion and independent audit

**Date:** 14 November 2026  
**Scope:** private Hugging Face dataset `AdityaSreevatsaK/Taiyous-Novels` and compatibility with the separately deployed reader. This is a public summary of counts and checks only; it deliberately excludes private novel titles, file names and personal data.

## Confirmed production operations

- One-novel production pilot: [run 43486112141](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/43486112141); the owner reported that the migrated book worked in the Library App.
- Complete migration: [run 43558185178](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/43558185178), success.
- Before the final write: **88** legacy folders, **1** readable folder, **0** conflicts. A complete, **221-file SHA-256-verified private backup** was made against source revision `258bea89d5c0dbfacfc6e3b8b01de52758a27283`.
- Final write: 11 successful batches of 8 novels each, **88** novel directories moved; remote old/new files verified byte-equivalent by SHA-256; all **89** stable IDs and personal sidecar paths preserved.
- Final migrated private revision: `5d168f6e6a46` (prefix shown in privacy-safe logs).

## Independent post-migration check

A separate **read-only** GitHub Actions run [43559055257](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/43559055257), using the configured private dataset token, reported:

| Check | Result |
| --- | --- |
| Catalogue book count | **89** |
| `MIGRATE` | **0** |
| `ALREADY_READABLE` | **89** |
| `CONFLICT` | **0** |
| Current catalogue revision | `5d168f6e6a46` |
| Storage Controller regression suite | **119 passing tests** |
| Production writes by this audit | **None** |

The one-shot audit workflow was removed from the proposed documentation changes after its successful execution, to avoid retaining an unnecessary trigger. The historical Actions run remains available as evidence.

## Compatibility and operating rules

- Canonical path pattern: `data/novels/<immutable-id> - <sanitised-title>/`.
- EPUB, original ZIP and cover paths come from each catalogue entry (`epubPath`, `archivePath`, and `metadata.coverPath`), not from reconstructing the current title.
- Keep **both readable and historical ID-only paths supported** for backwards compatibility, future imports and interrupted operations.
- Do not rename folders automatically when a book title changes.
- Import, cover upload, list, duplicate/conflict reports and backup utilities must respect the catalogue-declared folder. Use the regular preview modes before any future write.
- Keep the private backup dataset separate and private. Automatic full restore is not implemented.
- Avoid rerunning the apply-mode migration as a verification step; use `python -m taiyou_storage.migrate_production` with `HF_READABLE_MIGRATION_APPLY=false` and a read-only GitHub Actions workflow.

## Verification boundary

The successful migration checked each moved file and catalogue identity. The one-novel live reader pilot was manually accepted, and the deployed reader's automated suite passed previously. **A new exhaustive authenticated browser test covering multiple migrated EPUBs, covers, ZIP downloads, offline caching and progress across different devices was not executed during this post-migration audit.** It remains a manual acceptance check, not a reason to repeat the migration.

## Suggested smoke checks

1. In the live signed-in reader, open three or more previously migrated books; navigate chapters and reopen to confirm position.
2. Check actual covers and original ZIP downloads for books that have these assets.
3. Test one already-cached offline EPUB, without clearing any local storage.
4. In the Storage Controller, run previews for novel listing, duplicate/conflict detection and any pending new upload; confirm no old path is reconstructed from the title.
5. If any operation fails, record the book ID privately, stop data-changing operations and investigate against the retained private snapshot. Do not perform a dataset-wide reset.
