# Taiyou Novels Storage Controller

Windows-friendly utilities for managing **Taiyou's Personal Library** files in the private Hugging Face dataset **`AdityaSreevatsaK/Taiyous-Novels`**. This controller imports prepared novel ZIPs, uploads covers, checks the library and creates backups; it does **not** download novels from websites or host the reader.

> **Privacy:** This code repository is public, but the Hugging Face dataset must stay **private**. Never commit personal notes, novel ZIPs, cover images, catalogue exports or access tokens to GitHub.

## Quick start (Windows)

1. Install **Python 3.11 or 3.12** and open a terminal in this repository.
2. Install the tested dependencies and authenticate with Hugging Face:

   ```powershell
   py -m pip install -r requirements.txt
   hf auth login
   ```

3. Create a local `novels/` folder and put your prepared novel ZIP files inside.
4. Run **`00_storage_menu.cmd`** or launch **`01_bulk_upload.cmd`** directly.

The upload launchers preview the actual changes and require you to type **YES** before committing. A bare Python CLI invocation is **read-only by default**; `--apply` explicitly writes without a prompt, while `--interactive` previews and asks for confirmation within the same process.

**Different private dataset?** Pass `--repo OWNER/PRIVATE-DATASET` to the Python CLI. The catalogue-management, cover and reset tools also support the `HF_DATASET_REPO` environment variable. **The novel uploader does not read that environment variable**: it requires `--repo` for an override. Confirm the target in your preview.

## Available tools

| Windows launcher | Purpose |
|---|---|
| **`01_bulk_upload.cmd`** | Preview, confirm and incrementally upload novel ZIPs |
| `02_download_all.cmd` | Download existing original ZIPs to `downloads/` |
| `03_list_novels.cmd` | Export a local CSV of catalogue entries |
| `04_detect_conflicts.cmd` | Report exact/normalised duplicate titles |
| `06_sync_status.cmd` | Compare local EPUB-derived IDs with remote IDs; **not** full byte verification |
| `07_backup_catalogue.cmd` | Save a local copy of `data/library.json` |
| **`10_upload_covers.cmd`** | Import covers with preview, confirmation and resumable batches |
| **`11_clear_hf_data.cmd`** | **Destructive full reset** — verified backup and multiple confirmations required |

`00_storage_menu.cmd` offers these working tools in a Windows menu. Launchers **05, 08 and 09 are placeholders**; full-integrity audit, single-novel restoration and single-novel deletion are not implemented here.

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

An existing novel is matched by EPUB-derived ID or by an unambiguous normalised title **and** author. A successful match preserves the stable novel ID and app/user metadata, including progress, ratings, notes and personal tags. Missing genres in an older ZIP do not erase nonempty existing source genres.

A novel is labelled **UNCHANGED** only when its original ZIP, stored EPUB and source-managed catalogue metadata all agree. Changed binaries and the catalogue are reconciled in a single revision-guarded commit. The preview hashes only matching remote novels from your current local batch, not the whole library.

The first upload can initialise a brand-new **private** dataset. If a dataset already contains `data/` objects but lacks `data/library.json`, the uploader **refuses** to initialise over potentially orphaned data. Changes to both title and EPUB may be impossible to identify confidently; review any possible duplicates manually.

See [smart upload details](README.smart-upload.md) for compatibility and matching caveats.

## Import covers

Use `10_upload_covers.cmd` with `Downloaded_Covers.zip`, `novel-cover-images.zip` or its outer GitHub Actions artifact ZIP. The archive must include `covers_manifest.json` and JPEG, PNG or WebP images. The uploader understands the Novel Retriever's `results` manifests and skips failed rows.

```powershell
py -m taiyou_storage.covers "C:\Downloads\Downloaded_Covers.zip"                 # Preview only
py -m taiyou_storage.covers "C:\Downloads\Downloaded_Covers.zip" --interactive   # Preview and confirm
```

Covers are linked only to **existing** novels. Matching prefers the source URL; ambiguous titles block updates. Images go under `data/novels/<book-id>/cover.<ext>`, with the catalogue's `metadata.coverPath` updated. The uploader does not delete covers of another extension, create books or alter EPUBs/ZIPs.

- Default: **20 covers per atomic batch** (configurable up to 40). The cover files and catalogue changes commit together.
- If a later batch fails, earlier committed batches remain. **Re-run the same ZIP** to skip already completed covers and resume.
- A local catalogue backup is saved before writes; preview reports go to `reports/`.
- Short rate-limit delays are bounded; long/unknown Hugging Face 429 quotas stop rather than retrying indefinitely.

Cover display requires compatible `coverPath` handling and private image access in the separate reader app.

## Backups, reset and safety

The **full reset** removes **every file under `data/`** in your private dataset: novels, EPUBs, ZIPs, covers and any saved app data there. It is not intended for deleting a single novel or local download.

```powershell
py -m taiyou_storage.reset           # Read-only preview
py -m taiyou_storage.reset --apply   # Interactive, verified-backup-first reset
```

`11_clear_hf_data.cmd` provides the same backup-first workflow. The destructive path requires an interactive terminal, a complete SHA-256-verified local backup at a pinned dataset revision, and two explicit confirmations. It checks the dataset revision again before committing. **Keep the backup:** automatic restore is not implemented, and Git/LFS history may retain old files.

**No GitHub Action can clear or delete the dataset.** The old backup-free clear workflow and CLI command were retired.

## GitHub Actions

Manual workflows include:

| Workflow | Operation |
|---|---|
| **HF - Inspect library (read only)** | Private catalogue health/counts; no writes |
| **HF - Back up entire dataset PRIVATELY** | Verified snapshot to a separate **private** dataset |
| **HF - Export novel names and conflicts PRIVATELY** | Private CSV reports to that backup dataset |
| **HF - Upload covers from Novel_Library artifact** | Preview by default; opt-in cover import |
| **HF - Restore novel genres from original download artifacts** | Separate, opt-in historical metadata repair |

Refer to [Actions setup and security](docs/GITHUB_ACTIONS.md) for secrets and permissions, and [genre repair documentation](docs/GENRE_REPAIR.md) for that separate process. CI runs entirely offline and cannot write to the real novel dataset.

## Limits and validation

- Novel ZIP and embedded EPUB: **120 MiB each**, with additional entry-count, expansion and compression-ratio limits.
- Individual cover image: **12 MiB**; JPEG, PNG and WebP only.
- Browser uploads through the separate Personal Library web app have their own limits; a valid Storage Controller ZIP may exceed them.
- Some large imports need several commits. If an upload stops partway through, re-run the preview and review the remaining changes.

```powershell
py -m unittest discover -s tests -v
```

CI tests on **Windows and Linux, Python 3.11 and 3.12**. The verified integration suite covers idempotent uploads, corrupted EPUB repair, personal metadata, interrupted cover-batch resume and safe reset previews. **Live Hugging Face write integration is not part of CI.**

Dependencies use tested versions in [`constraints.txt`](constraints.txt). See the [changelog](CHANGELOG.md) for releases. Code is MIT-licensed; novel texts and cover artwork are not.
