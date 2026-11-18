# Using the Storage Controller

Run these commands from the repository root after installing the requirements and authenticating with Hugging Face. This guide covers the local utilities; use the [README](../README.md) for quick setup and the [documentation index](README.md) to explore specialised topics.

## Clear console summaries

Double-clicked Windows commands now show **short labelled results** rather than
a long list of every novel. For example, a cover audit reports the total number
of novels, existing standalone covers, missing standalone covers and items
needing attention, followed by the locations of the full private CSV reports.
The conflict checker shows the **number of conflicting pairs** and their types.

Detailed per-novel evidence remains in the locally ignored `reports/` folder
(or the chosen download/backup destination). The bulk uploader additionally
writes `reports/bulk-upload-plan.csv` with every proposed change, and the
download and local sync tools save itemised reports. **Always review the upload
plan before typing YES.** No changes to approval or destructive safeguards.

For per-record diagnostics, use `--verbose` with the underlying Python CLI
(for example, `py -m taiyou_storage.inspection_cli covers --verbose` or
`py -m taiyou_storage.cli conflicts --verbose`). Read-only manifest scans
only verify remote file listing or manifest evidence, not image pixels.

## Command reference

| Windows launcher | Purpose |
|---|---|
| **`01_bulk_upload.cmd`** | Preview, verify local duplicates, skip equivalent ZIPs, block conflicting editions, and incrementally upload novel ZIPs |
| `02_download_all.cmd` | Download existing original ZIPs to `downloads/` |
| `03_list_novels.cmd` | Export a local CSV of catalogue entries |
| `04_detect_conflicts.cmd` | Report exact/normalised duplicate titles |
| **`05_verify_integrity.cmd`** | Fast remote manifest verification by default; use `--mode deep` for byte-level archive/EPUB inspection |
| `06_sync_status.cmd` | Compare local EPUB-derived IDs with remote IDs; **not** full byte verification |
| `07_backup_catalogue.cmd` | Save a local copy of `data/library.json` |
| **`10_upload_covers.cmd`** | Import covers with preview, confirmation and resumable batches |
| **`11_clear_hf_data.cmd`** | **Destructive full reset** — verified backup and multiple confirmations required |
| `12_export_novel_inventory.cmd` | Chapter ranges and missing positions from verified sidecars, CSV and JSON |
| `13_audit_missing_covers.cmd` | Actionable `missing-covers.csv` plus full `cover-audit.csv`, distinguishing file presence from verified image integrity |
| `14_compare_retriever_inventory.cmd` | Compare local Retriever registry and produce private exclusion hashes |
| `15_library_health_report.cmd` | Local HTML dashboard, JSON and CSV |
| **`16_backfill_inspection_manifests.cmd`** | Preview and safely migrate existing books to tiny inspection manifests; explicit `--interactive` or `--apply` to write |
| **`17_cleanup_inspection_downloads.cmd`** | Preview and delete local-only inspection download cache; optionally target older shared HF novel files |
| **`18_repair_novel_metadata.cmd`** | Audit missing synopsis/genre/status fields; prepare, preview and safely confirm a one-novel catalogue-only repair |

`00_storage_menu.cmd` offers these working tools in a Windows menu. Launchers **08 and 09 are placeholders**; single-novel restoration and single-novel deletion are not implemented here.

## Reliable ZIP download exports

`02_download_all.cmd` downloads only the existing `original.zip` files
referenced by the private catalogue. The Python command works on Windows,
Linux and macOS:

```sh
python -m taiyou_storage.cli download --destination downloads --workers 3
```

Downloads stream in bounded, parallel transfers (1 to 4 workers). Transient
timeouts, HTTP 429 and selected server errors get at most two bounded retries;
authentication failures are not retried. Each ZIP is written into a unique
temporary file and atomically renamed after transfer.
Failed transfers never replace a previous complete ZIP. The console now
summarises downloaded, missing and failed files. See
`downloads/download-report.csv` for individual errors, and
`downloads/manifest.json` for SHA-256 hashes and `complete: true/false`.
A missing or failed ZIP produces a nonzero exit code; successful ZIPs are
preserved for retry. The script does not fetch the entire HF dataset or modify
any remote files.

**Privacy:** Keep exports under `downloads/` (ignored by Git), or outside the
public code checkout. If you select another destination inside the checkout,
do not commit private CSV/JSON reports.

## Repair missing synopsis, genre tags or publication status

Use `18_repair_novel_metadata.cmd` to **audit all** novels in the private
catalogue or **add missing verified fields to one** novel. Option 1 writes a
local Git-ignored CSV only. Options 2–4 prepare a private JSON draft, preview
the exact remote revision, then require typed confirmation to add fields. The
private HF commit includes an exact pre-change catalogue backup. ZIPs, EPUBs,
covers, progress, personal tags and ratings remain untouched.

For multiple missing entries, use the same launcher **options 5–9** or
**option 10** to import a prepared private JSON of researched metadata.
Imported entries require individual approval via option 6 before the
revision-checked preview (8) and apply (9). Option 7 cannot auto-approve
imported research. With options 5–9:
discover verified source fields from public book pages, review and approve
proposals, preview all approved edits, and make a single revision-guarded
catalogue-only commit. Source failures stay unresolved and can be repaired
individually after manual verification. No chapters are fetched.

See [Metadata repair](METADATA_REPAIR.md) for the step-by-step Windows
instructions and JSON format. This is independent of the historical genre
repair tool and does not download chapters.

## Import novel ZIPs

Each ZIP must contain exactly one valid **`source.epub`**. Optional `metadata.json`, `chapters.json` and chapter text files may sit alongside it or in a subfolder (such as `chapters/source.epub`).

```text
novels/
  example-novel.zip
    chapters/source.epub
    chapters/metadata.json
    chapters/chapters.json
    chapters/001.txt
```

```powershell
py -m taiyou_storage.upload novels                 # Preview only
py -m taiyou_storage.upload novels --interactive   # Preview and confirm
py -m taiyou_storage.upload novels --apply         # Explicit noninteractive upload
```

**New uploads now use readable Hugging Face folders by default:** `data/novels/<id> - <sanitised-title>/`. Existing novels keep their catalogue-declared path, whether ID-only or readable. Use `--legacy-new-folders` to opt out for an individual run. Your existing progress, personal metadata and stable IDs do not change.

**Production migration completed on 14 November 2026:** all 89 existing novels now use human-readable folders after a verified one-novel pilot and 88-novel final operation. All stable IDs, personal sidecar paths and per-file SHA-256 checks passed. See the [migration guide](READABLE_FOLDER_MIGRATION.md) and [post-migration verification](POST_MIGRATION_VERIFICATION_2026-11-14.md). The dedicated production migration Action was retired after the completed migration. Do not re-enable it without a new engineering review.

An existing novel is matched by EPUB-derived ID or by an unambiguous normalised title **and** author. A successful match preserves the stable novel ID and app/user metadata, including progress, ratings, notes and personal tags. Missing genres in an older ZIP do not erase nonempty existing source genres.

A novel is labelled **UNCHANGED** only when its original ZIP, stored EPUB and source-managed catalogue metadata all agree. Changed binaries and the catalogue are reconciled in a single revision-guarded commit. The preview hashes only matching remote novels from your current local batch, not the whole library.

The first upload can initialise a brand-new **private** dataset. If a dataset already contains `data/` objects but lacks `data/library.json`, the uploader **refuses** to initialise over potentially orphaned data. Changes to both title and EPUB may be impossible to identify confidently; review any possible duplicates manually.

The Windows `01_bulk_upload.cmd` automatically enables verified local deduplication; direct Python commands require `--dedupe-local` to enable it. See [smart upload details](SMART_UPLOAD.md) for matching caveats.

## Read-only library inspection

Run the **12–15** tools directly or via the menu. All reports remain in the ignored local `reports/` directory and must never be committed to this public repository. Use --mode quick for faster catalogue/file listing checks; default manifest mode avoids binary downloads; `--mode deep` validates EPUB, ZIP, chapter files and images. An older EPUB without a verified manifest remains `UNVERIFIED`, never assumed complete from its chapter count.

For the Retriever comparison, keep a local `Novel-Retriever` checkout next to this controller, or pass `--retriever-root PATH`. Automatic skipping in Retriever is a separate change. See [inspection guide](LIBRARY_INSPECTION.md) for evidence semantics, privacy and usage.

## Import covers

When uploading covers, the controller stages the validated images and updated
`data/library.json` in a temporary **local** directory and passes file paths
to Hugging Face. This supports its Xet upload path instead of triggering the
in-memory-buffer HTTP fallback. Staged files are removed after each batch,
including failed attempts; the existing revision checks, single-commit
catalogue/cover update and safe rerun behaviour are unchanged. Hugging Face
may still choose HTTP if Xet is disabled or unavailable in the environment.


Use `10_upload_covers.cmd` with `Downloaded_Covers.zip`, `novel-cover-images.zip` or its outer GitHub Actions artifact ZIP. The archive must include `covers_manifest.json` and JPEG, PNG or WebP images. The uploader understands the Novel Retriever's `results` manifests and skips failed rows.

```powershell
py -m taiyou_storage.covers "C:\Downloads\Downloaded_Covers.zip"                 # Preview only
py -m taiyou_storage.covers "C:\Downloads\Downloaded_Covers.zip" --interactive   # Preview and confirm
```

Covers are linked only to **existing** novels. Matching prefers the source URL; ambiguous titles block updates. Images follow each book's **catalogue-declared folder**, which may be readable or legacy; the catalogue's `metadata.coverPath` is updated. The uploader does not delete covers of another extension, create books or alter EPUBs/ZIPs.

- Default: **20 covers per atomic batch** (configurable up to 40). The cover files and catalogue changes commit together.
- If a later batch fails, earlier committed batches remain. **Re-run the same ZIP** to skip already completed covers and resume.
- A local catalogue backup is saved before writes; preview reports go to `reports/`.
- Short rate-limit delays are bounded; long/unknown Hugging Face 429 quotas stop rather than retrying indefinitely.

Cover display requires compatible `coverPath` handling and private image access in the separate reader app.

## Limits and validation

- Novel ZIP and embedded EPUB: **120 MiB each**, with additional entry-count, expansion and compression-ratio limits.
- Individual cover image: **12 MiB**; JPEG, PNG and WebP only.
- Browser uploads through the separate Personal Library web app have their own limits; a valid Storage Controller ZIP may exceed them.
- Some large imports need several commits. If an upload stops partway through, re-run the preview and review the remaining changes.

```powershell
py -m unittest discover -s tests -v
```

CI tests on **Windows and Linux, Python 3.11 and 3.12**, and runs a dependency vulnerability audit on pushes and PRs (also weekly). The verified integration suite covers idempotent uploads, corrupted EPUB repair, personal metadata, interrupted cover-batch resume and safe reset previews. **Live Hugging Face write integration is not part of CI.**

Dependencies use tested versions in [`constraints.txt`](../constraints.txt). See the [changelog](../CHANGELOG.md) and [release procedure](RELEASING.md). Code is MIT-licensed; novel texts and cover artwork are not.


**Scope:** These utilities manage prepared novels and private HF storage. Novel website downloads and the reader web app are maintained in separate repositories.
