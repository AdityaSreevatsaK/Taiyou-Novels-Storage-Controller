# Taiyou Novels Storage Controller

Windows-friendly tools for managing a **private Hugging Face novel library**. Import prepared novel ZIPs, add covers, inspect catalogue health, export archives and make backups.

> **Privacy:** This GitHub repository is public. Your [Hugging Face dataset](https://huggingface.co/datasets/AdityaSreevatsaK/Taiyous-Novels) must remain **private**. Never commit downloaded novels, catalogue exports, personal data or tokens.

## Get started

1. Install **Python 3.11 or 3.12**, then clone or download this repository.
2. From the repository directory, install dependencies and authenticate:

   ```powershell
   py -m pip install -r requirements.txt
   hf auth login
   ```

3. Put prepared novel ZIPs in `novels/`.
4. Double-click **`00_storage_menu.cmd`**, or run **`01_bulk_upload.cmd`** to preview and approve a bulk upload.

The uploader safely skips verified duplicate ZIPs, blocks conflicting editions and preserves existing personal metadata. **Nothing is uploaded until you confirm.**

## Common tools

| Launcher | What it does |
| --- | --- |
| `01_bulk_upload.cmd` | Incremental bulk upload with verified deduplication and approval |
| `02_download_all.cmd` | Download original ZIP archives to `downloads/` |
| `05_verify_integrity.cmd` | Check the private library without modifying it |
| `10_upload_covers.cmd` | Preview and import novel cover images |
| `13_audit_missing_covers.cmd` | Export missing-cover and cover-audit reports |
| `15_library_health_report.cmd` | Generate a local HTML health report |
| `17_cleanup_inspection_downloads.cmd` | Preview and confirm local inspection-cache cleanup |
| `11_clear_hf_data.cmd` | **Full library reset. Destructive; requires a verified backup and typed confirmations.** |

Use the menu for additional catalogue, conflict, chapter, sync and comparison utilities. All commands show **concise count-based summaries**; detailed reports remain in local Git-ignored folders. See the [full command reference](docs/USER_GUIDE.md).

## Run checks on GitHub

Use [**HF - Run library checks (read only)**](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/workflows/hf-inspect.yml) to run a private-library audit from GitHub Actions. Choose **manifest** for lightweight checks or **deep** for downloaded-content inspection. Public logs show counts only, never novel titles or reports.

## Documentation

| Topic | Guide |
| --- | --- |
| All tools and how-to guides | [User guide](docs/USER_GUIDE.md) |
| Safe uploads and duplicate handling | [Smart upload](docs/SMART_UPLOAD.md) |
| Inspection, chapter and cover evidence | [Library inspection](docs/LIBRARY_INSPECTION.md) |
| Backups, cache cleanup and full reset | [Safety and recovery](docs/SAFETY_AND_RECOVERY.md) |
| GitHub Actions and credentials | [Actions guide](docs/GITHUB_ACTIONS.md) |

Browse the [**documentation index**](docs/README.md) for migration history, genre repair and release procedures.

## Development

```powershell
py -m unittest discover -s tests -v
```

CI checks Windows and Linux on Python 3.11/3.12 and audits Python dependencies. It does **not** write to your private dataset. See [CHANGELOG.md](CHANGELOG.md) and [AGENTS.md](AGENTS.md).

Code is MIT-licensed. Novel texts and cover artwork are not.
