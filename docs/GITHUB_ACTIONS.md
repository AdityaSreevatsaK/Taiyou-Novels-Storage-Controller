# GitHub Actions - Hugging Face storage controller

This GitHub repository is **PUBLIC**, but your novel dataset remains PRIVATE. Workflow logs must never display private novel contents or upload novel ZIPs, EPUBs, covers, notes or title reports as GitHub Actions artifacts.

## One-time setup

Open GitHub repository **Settings > Secrets and variables > Actions** and create a repository secret named `HF_STORAGE_CONTROLLER_TOKEN`. Use a Hugging Face token with permission to modify your private `AdityaSreevatsaK/Taiyous-Novels` dataset.

For the optional private reports/backup workflows, the token also needs access to a **separate PRIVATE** Hugging Face dataset, such as `AdityaSreevatsaK/Taiyous-Novels-Backup` (created automatically as private if allowed). This second dataset is **not needed for clearing data**.

The cover import workflow can use `NOVEL_LIBRARY_ACTIONS_TOKEN` if the standard GitHub token cannot read the `RichardDaffern/Novel_Library` Actions artifact.

## Clear dataset contents with one checkbox

1. Open [GitHub Actions](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions).
2. Choose **HF - CLEAR ALL data**.
3. Click **Run workflow**, tick the single acknowledgment checkbox, and run it.

No backup, source SHA, typed confirmation or extra dataset input is needed. The Action will be **skipped** unless its checkbox is checked. Nothing deletes automatically or on a schedule.

| Action | Exactly what gets deleted |
|---|---|
| **HF - CLEAR ALL data** | All files under `data/`, including novels, EPUBs, ZIPs, covers, personal reviews, reading progress and collections. The private dataset repository remains, with an empty `data/library.json`. Git/LFS history may still retain old blobs. |

**Warning:** This workflow does **not** create backups. Without other saved copies, deletion can be irreversible. The script still performs private-dataset identity and revision checks without requiring user input.

## Other available manual workflows

| Action | Purpose |
|---|---|
| **HF - Inspect library (read only)** | Counts books, folders, missing files and apparent duplicates, without exposing titles in public logs |
| **HF - Export novel names and conflicts PRIVATELY** | Saves sensitive book lists and conflicts in your separate private backup dataset |
| **HF - Back up entire dataset PRIVATELY** | Optional full private snapshot with SHA-256 verification |
| **HF - Upload covers from Novel_Library artifact** | Imports cover images from an existing source Actions artifact by run ID; preview by default |

The local `11_clear_hf_data.cmd` retains its own backup-first procedure; the **GitHub Actions clear-data command** is the checkbox-only alternative.

## Still local-only

- Uploading ZIP files that exist solely on your Windows computer.
- Comparing your local ZIP contents with Hugging Face.
- Repairing single-novel duplicates and restoring an entire library (not yet implemented).

CI remains offline and is never allowed to touch the real Hugging Face dataset.

**Full dataset-repository deletion has been removed from this controller.** The controller can clear its contents but does not offer a GitHub Action or CLI subcommand to delete the Hugging Face repository itself.
