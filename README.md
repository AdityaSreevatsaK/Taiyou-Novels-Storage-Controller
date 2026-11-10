# Taiyou Novels Storage Controller

Windows-friendly utilities for managing the private Hugging Face dataset `AdityaSreevatsaK/Taiyous-Novels`, used by Taiyou's Personal Library.

## Safety and status

The current foundation includes **read-only** remote listing, title conflict reports, full downloads and local comparison. It does **not** yet replace the original bulk uploader or change remote files. Smart upload/replacement will be added only after validating compatibility with the reader's existing `data/library.json` schema and ensuring novel IDs stay stable.

## Quick start (Windows)

Install Python 3.11+, then run `py -m pip install -r requirements.txt` and `hf auth login` with a token permitted to read the private dataset. Double-click `00_storage_menu.cmd`, or run any individually named `.cmd` utility. All utilities use the dataset ID above by default; override with `HF_DATASET_REPO`.

Each download creates a local manifest of SHA-256 digests. Files in `downloads/`, `novels/`, `backups/` and `reports/` are excluded from Git.

## Actions

| Utility | Current behaviour |
|---|---|
| 01_bulk_upload.cmd | Disabled until safe updating is implemented |
| 02_download_all.cmd | Downloads all `data/novels/**/original.zip` files, preserving remote paths |
| 03_list_novels.cmd | Writes list of titles/IDs/authors/chapters to a CSV |
| 04_detect_conflicts.cmd | Reports exact/normalised/possible title collisions in the remote catalogue |
| 05_verify_integrity.cmd | Planned |
| 06_sync_status.cmd | Checks local ZIP files for errors and compares EPUB hash IDs to the remote catalogue; **not** a full content sync |
| 07_backup_catalogue.cmd | Saves a dated snapshot of `data/library.json` |
| 08_restore_novel.cmd | Planned |
| 09_delete_novel.cmd | Planned |

Use `python -m taiyou_storage.cli --help` for direct invocation and options.

## Development

`python -m unittest discover -s tests -v`

CI tests run without Hugging Face credentials or access to the private dataset. They execute on Windows and Linux with Python 3.11 and 3.12. No files are published from CI.

## Licence

MIT. This licence covers the controller code, not the novels stored in the private dataset.
