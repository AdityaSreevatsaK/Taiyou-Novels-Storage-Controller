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
| 01_bulk_upload.cmd | Preview changes and upload new/modified novel ZIPs after confirmation |
| 02_download_all.cmd | Download novel ZIP backups to downloads/ |
| 03_list_novels.cmd | Export catalogue to reports/novels.csv |
| 04_detect_conflicts.cmd | Detect exact/normalised duplicate titles |
| 05_verify_integrity.cmd | Reserved for future full integrity verification |
| 06_sync_status.cmd | Check local EPUB IDs against remote catalogue IDs |
| 07_backup_catalogue.cmd | Save a dated copy of the catalogue |
| 08_restore_novel.cmd | Reserved for future restore operation |
| 09_delete_novel.cmd | Reserved for future safe deletion |
| 10_upload_covers.cmd | Import cover images from Downloaded_Covers.zip, with preview and conflict checks |
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
    py -m taiyou_storage.covers "C:\Downloads\Downloaded_Covers.zip" --apply

**Default is preview only.** The command matches exact source URL first, falling back to a unique title only when the catalogue has no conflicting source URL. Conflicts block the entire upload. Missing novels are reported and skipped; no book is created.

Changed images are stored as data/novels/<existing-book-id>/cover.<jpg|png|webp> and the original book's metadata receives **coverPath**, preserving ID, EPUB, ZIP, progress, ratings and personal notes. An identical image with matching coverPath is skipped. Existing cover images of a *different extension* are not deleted automatically. Before the first write, a timestamped data/library.json backup is saved locally. A reports/cover-upload-plan.csv report is generated on every run.

**Reader integration is separate:** the current Taiyou's Personal Library uses generated text covers and its Cloudflare gateway does not yet allow image paths. The reader must be updated to consume coverPath and securely serve/cache the private image before actual covers will appear.

## Safety and current limitations

- CI is offline and never touches your private Hugging Face dataset.
- Novel and cover uploaders require explicit confirmation or --apply.
- Existing novel IDs remain stable when an EPUB changes and the novel can be matched unambiguously.
- Title + EPUB changes together may require manual ID mapping; inspect novel upload previews.
- Archive validation and optimistic dataset revision checks reduce accidental overwrites but do not replace backups.
- An upload can partially complete if a later individual commit fails. Re-run the preview to reconcile.
- Only jpeg, png and webp covers are supported. Images are checked for basic file signatures and size limits.
- The controller does not download chapters or covers from source websites.

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

The command requires an interactive terminal. Normal execution is preview-only (py -m taiyou_storage.reset); explicit --apply and two manual confirmations are required for changes. CI does not have credentials or execute destructive operations.

## GitHub Actions (remote operations)

Open [Actions](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions) and select a workflow.

- **HF - CLEAR ALL data**: manually run, tick its single confirmation checkbox, then click Run workflow. Deletes all `data/` contents (including novels, covers and personal notes) and recreates an empty catalogue. **Keeps** the private HF dataset repository.
- **HF - DELETE ENTIRE dataset repository**: manually run, tick its single confirmation checkbox, then click Run workflow. Deletes the **entire private Hugging Face dataset repository**, including history.
- **Optional backups** are available via the separate `HF - Back up entire dataset PRIVATELY` Action. Neither deletion Action creates or requires a backup.
- **Read-only inspection**, **private novel lists/conflict reports**, and **cover uploads from Novel_Library artifacts** have separate manual Actions.

You need the GitHub Actions secret `HF_STORAGE_CONTROLLER_TOKEN` with sufficient Hugging Face permissions. No SHA, backup dataset or typed phrase is required for deletion. Both Actions automatically verify the target is a private dataset and check its state internally. **Deletion is permanent if you have no other copies.** The local `11_clear_hf_data.cmd` is a separate backup-first command and has not been changed.

See [GitHub Actions setup and safety](docs/GITHUB_ACTIONS.md).
