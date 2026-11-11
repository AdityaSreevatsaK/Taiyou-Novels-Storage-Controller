# GitHub Actions - Hugging Face storage controller

This GitHub repository is **PUBLIC**, but your novel dataset remains PRIVATE. Workflow logs must never display private novel contents or upload novel ZIPs, EPUBs, covers, notes or title reports as GitHub Actions artifacts.

## One-time setup

Open GitHub repository **Settings > Secrets and variables > Actions** and create a repository secret named `HF_STORAGE_CONTROLLER_TOKEN`. Use a Hugging Face token with permission to modify your private `AdityaSreevatsaK/Taiyous-Novels` dataset.

For the optional private reports/backup workflows, the token also needs access to a **separate PRIVATE** Hugging Face dataset, such as `AdityaSreevatsaK/Taiyous-Novels-Backup` (created automatically as private if allowed). This second dataset is used only for private backups/reports; clearing data from Actions is disabled.

The cover import workflow can use `NOVEL_LIBRARY_ACTIONS_TOKEN` if the standard GitHub token cannot read the `RichardDaffern/Novel_Library` Actions artifact.

## Destructive operations are local and backup-first

The previous `HF - CLEAR ALL data` workflow has been removed because its checkbox-only
path could destroy every novel, cover and personal record without a backup.
The noninteractive `taiyou_storage.actions clear` command is also removed.

If you intentionally need to reset the complete private dataset, use
`11_clear_hf_data.cmd` on a Windows computer. It first previews all affected
files, downloads a complete backup at one immutable revision, checks each file's
SHA-256 checksum, requires two separate confirmations, and refuses to delete if
the remote revision or file inventory changes. Retain the verified local backup.

**Never use this full reset for deleting one novel or clearing downloads.**
It affects all `data/` objects, including novels, notes and progress.

## Other available manual workflows

| Action | Purpose |
|---|---|
| **HF - Inspect library (read only)** | Counts books, folders, missing files and apparent duplicates, without exposing titles in public logs |
| **HF - Export novel names and conflicts PRIVATELY** | Saves sensitive book lists and conflicts in your separate private backup dataset |
| **HF - Back up entire dataset PRIVATELY** | Optional full private snapshot with SHA-256 verification |
| **HF - Upload covers from Novel_Library artifact** | Imports cover images from an existing source Actions artifact by run ID; preview by default |

GitHub Actions can inspect, back up and import covers, but cannot clear the dataset.

## Still local-only

- Uploading ZIP files that exist solely on your Windows computer.
- Comparing your local ZIP contents with Hugging Face.
- Repairing single-novel duplicates and restoring an entire library (not yet implemented).

CI remains offline and is never allowed to touch the real Hugging Face dataset.

**All GitHub Actions destruction paths have been retired.** Only the local, interactive, backup-first reset can clear `data/`; it cannot delete the Hugging Face dataset repository.
