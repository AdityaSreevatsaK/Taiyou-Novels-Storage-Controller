# Taiyou Novels Storage Controller

Windows-friendly utilities for managing the private Hugging Face dataset **AdityaSreevatsaK/Taiyous-Novels**, used by Taiyou's Personal Library.

## Getting started

Install Python 3.11+, then run:

    py -m pip install -r requirements.txt
    hf auth login

Use a Hugging Face token with permission to write to your **private** dataset if you plan to upload. Double-click 00_storage_menu.cmd, or run any individual CMD utility. You can override the default dataset by setting HF_DATASET_REPO.

The utilities use the existing version 1 dataset catalogue (data/library.json). Local files in novels/, covers/, downloads/, backups/ and reports/ are ignored by Git. Do **not** commit tokens, archives, or copyrighted cover images to the public repository.

## Utilities

| Command | Purpose |
|---|---|
| 00_storage_menu.cmd | Choose a tool from a Windows menu |
| 01_bulk_upload.cmd | Preview and confirm within one revision-guarded run; upload new/changed novel ZIPs |
| 02_download_all.cmd | Download novel ZIP backups to downloads/ |
| 03_list_novels.cmd | Export catalogue to reports/novels.csv |
| 04_detect_conflicts.cmd | Detect exact/normalised duplicate titles |
| 05_verify_integrity.cmd | Reserved for future full integrity verification |
| 06_sync_status.cmd | Check local EPUB IDs against remote catalogue IDs |
| 07_backup_catalogue.cmd | Save a dated copy of the catalogue |
| 08_restore_novel.cmd | Reserved for future restore operation |
| 09_delete_novel.cmd | Reserved for future safe deletion |
| 10_upload_covers.cmd | Preview and confirm cover uploads within one revision-guarded run |
| 11_clear_hf_data.cmd | Preview and optionally clear the private HF dataset after verified full backup |

### Cover image uploads

Download **Downloaded_Covers.zip** or the GitHub Actions artifact ZIP from the Novel Retriever. It should contain a covers_manifest.json and a folder for each source website:

    Downloaded_Covers.zip
      NovelFull/martial-world-a1b2c3d4.jpg
      FreeWebNovel/...
      covers_manifest.json

Each manifest record includes title, website, source_url and cover_file. One record, a list, or {"covers": [...]} is accepted. The uploader also accepts an outer GitHub Actions ZIP containing the inner Downloaded_Covers.zip.

Launch 10_upload_covers.cmd and provide the ZIP path. Alternatively run:

    py -m taiyou_storage.covers "C:\Downloads\Downloaded_Covers.zip"
    py -m taiyou_storage.covers "C:\Downloads\Downloaded_Covers.zip" --interactive
    py -m taiyou_storage.covers "C:\Downloads\Downloaded_Covers.zip" --apply

**Default is preview only.** The command matches exact source URL first, falling back to a unique title only when the catalogue has no conflicting source URL. Conflicts block the entire upload. Missing novels are reported and skipped; no book is created.

Changed images are stored as data/novels/<existing-book-id>/cover.<jpg|png|webp> and the original book's metadata receives **coverPath**, preserving ID, EPUB, ZIP, progress, ratings and personal notes. An identical image with matching coverPath is skipped. Existing cover images of a *different extension* are not deleted automatically. Before the first write, a timestamped data/library.json backup is saved locally. A reports/cover-upload-plan.csv report is generated on every run.

**Reader integration:** covers are linked through metadata `coverPath`; whether images display depends on the Personal Library's current gateway, reader version and caching setup. Do not infer reader behavior from the Storage Controller alone.

## Safety and current limitations

- CI is offline and never touches your private Hugging Face dataset.
- The Windows novel/cover launchers preview and confirm in one process, rather than recomputing a different plan after the confirmation.
- For scripts, `--interactive` requires a terminal confirmation; `--apply` explicitly authorises changes without prompting.
- The novel uploader checks ZIP, EPUB and source-metadata equality before reporting `UNCHANGED`, and hashes only matching remote books.
- Local ZIP/EPUB validation bounds entry count and expanded data before expensive CRC verification.
- Existing novel IDs remain stable when an EPUB changes and the novel can be matched unambiguously.
- Title + EPUB changes together may require manual ID mapping; inspect novel upload previews.
- Archive validation and optimistic dataset revision checks reduce accidental overwrites but do not replace backups.
- An upload can partially complete if a later individual commit fails. Re-run the preview to reconcile.
- Only jpeg, png and webp covers are supported. Images are checked for basic file signatures and size limits.
- The controller does not download chapters or covers from source websites.

### Upload size compatibility with the web reader

The Storage Controller accepts novel ZIPs and embedded EPUBs up to **120 MiB**
each. The separately deployed Personal Library web upload API currently enforces
a different limit (**70 MiB per file / 75 MiB per request**). These are distinct
upload routes: if the browser rejects a valid large novel, use the local
Storage Controller rather than retrying the same oversized browser request.
The web API's constraints are not changed by this repository.

## Development

    python -m unittest discover -s tests -v

Windows and Linux CI run on Python 3.11 and 3.12.

## Licence

MIT. Applies to the controller code, not the novel texts or cover artwork.

### Cover manifest compatibility

The uploader accepts the actual Novel_Library `download_covers.py` summary manifest with `results` and `downloaded`/`skipped`/`failed` statuses. Failed rows are skipped because no image exists. You may supply `covers/novel-cover-images.zip`, or the `covers/` folder itself when it contains exactly one ZIP. The CMD launcher strips pasted surrounding double quotes before forwarding paths containing spaces.

### Database reset (destructive)

Run 11_clear_hf_data.cmd to preview the data/ files currently stored in your private HF dataset. Type YES to begin the backup-first reset; then enter the exact dataset repository ID. The controller downloads every data/ file at a pinned revision into a timestamped backups/before-reset-... directory and verifies SHA-256 checksums. It requires a second confirmation using a revision-bound phrase, checks that the dataset revision has not changed, and then commits the deletion of all data/ files while replacing data/library.json with a valid empty catalogue.

This clears **all** novels, EPUBs, archives, covers, user reviews, progress and collections stored under data/. It does not selectively remove duplicates. Non-data/ files and the Hugging Face dataset repository itself remain in place. Historical Git/LFS data may remain; this is not a storage-history purge. **Automatic restore is not yet available**, so retain the full local backup and your novel ZIPs. Close other reader clients before resetting to avoid stale cache or resynchronisation.

The command requires an interactive terminal. Normal execution is preview-only (`py -m taiyou_storage.reset`); explicit `--apply` and two manual confirmations are required for changes. CI tests never use dataset credentials or perform destructive operations; separate manually dispatched non-destructive Actions may use configured secrets.

## GitHub Actions (remote operations)

Open [Actions](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions) and select a workflow.

- **Read-only inspection**, **private novel lists/conflict reports**, **private verified backups**, and **cover uploads from Novel_Library artifacts** are available as separate manual Actions.
- The old **HF - CLEAR ALL data** Action was retired because it could erase the dataset without any verified backup.
- Full data clearing is available **only** via local `11_clear_hf_data.cmd`, which requires a verified backup, revision checks and two interactive confirmations.

The manual non-destructive GitHub workflows use `HF_STORAGE_CONTROLLER_TOKEN` where needed. No backup-free data-clearing entry point remains in GitHub Actions. Historic workflow-run records may still appear in the GitHub interface.

See [GitHub Actions setup and safety](docs/GITHUB_ACTIONS.md).

The **entire dataset-repository deletion Action** is also retired. Neither the repository itself nor its contents can be deleted through a GitHub Action in this controller.

### Fresh private dataset (first bulk upload)

After recreating `AdityaSreevatsaK/Taiyous-Novels`, the dataset may not contain
`data/library.json` yet. This is expected. Run `01_bulk_upload.cmd`: its
read-only preview detects a new, empty **private** dataset and shows new novels.
After your confirmation, the first upload creates the catalogue automatically.
Do not create an empty `library.json` manually. Existing files under `data/`
without a catalogue will block the operation for safety.

### Rate-limited, resumable cover upload

The cover importer now writes multiple cover files plus their corresponding
`data/library.json` updates in **one atomic HF commit** per batch (default:
20 covers, capped at 48 MiB per batch). This replaces the old per-cover
commit design that hit Hugging Face's hourly repository-commit quota.
For example, 89 typical-sized covers use about five commits instead of 89.

If a previous run stopped after 36 successful covers, **use the same ZIP**
and simply run `10_upload_covers.cmd` again. The preview hashes remote
covers, marks those 36 as `UNCHANGED`, and uploads only outstanding ones.
No reset or redownload is needed.

The uploader pauses for 2 seconds between commits by default, and honours
a short `Retry-After` response once (30 seconds or less). On a long or
unknown 429 commit quota, it stops cleanly rather than retrying for hours.
If Hugging Face already reports the quota exceeded, you must allow its
hourly quota to reset before retrying; batching cannot override a quota
already exhausted.

Optional CLI flags: `--batch-size 20` (1-40 covers) and
`--commit-pause 2` (0-60 seconds). The `10_upload_covers.cmd`
workflow still uses safe defaults and keeps the preview and YES confirmation.
Normal Windows Hugging Face cache-symlink warnings are cosmetic and can
be suppressed by the launcher without needing administrator permissions.
