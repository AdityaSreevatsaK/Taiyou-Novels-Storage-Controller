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
