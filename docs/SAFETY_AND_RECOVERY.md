# Data safety, backups and cache cleanup

**Important:** This GitHub code repository is public. Novel archives, catalogue exports, covers, personal notes, tokens and local reports belong only in private Hugging Face storage or Git-ignored local folders. The controller's destructive operations require explicit local confirmation.

## Inspection downloads and local cleanup

**Double-click `17_cleanup_inspection_downloads.cmd` or choose menu option 17:**
The script scans recent inspection downloads **and** earlier cached HF novel files,
shows what is eligible for deletion, and requires you to type
`DELETE LOCAL CACHE` before deleting anything. It never deletes files from HF.

Routine inventory, cover, integrity and health checks now default to small verified manifest files.
Full `--mode deep` checks and one-time backfills download novel content to
`reports/.inspection-download-cache/`, a **dedicated local** Hugging Face cache.
It is safe to clear after all inspections stop, but deep checks will need the files again.

~~~powershell
.\\17_cleanup_inspection_downloads.cmd
.\\17_cleanup_inspection_downloads.cmd --apply
~~~

For large novel EPUB/ZIP/cover files cached by older inspection scripts in the
**shared** Hugging Face cache, preview then clean only the specified private dataset's
novel binaries and covers:

~~~powershell
.\\17_cleanup_inspection_downloads.cmd --legacy-shared-cache
.\\17_cleanup_inspection_downloads.cmd --legacy-shared-cache --apply
~~~

Deletion requires a local interactive confirmation and **only affects your computer**.
The legacy option can also remove cache entries used by another local programme.
No Hugging Face remote data, novel exports, catalogue or Library data is deleted.
Never run cleanup while an inspection, upload or migration is active.

## Backups, reset and safety

The **full reset** removes **every file under `data/`** in your private dataset: novels, EPUBs, ZIPs, covers and any saved app data there. It is not intended for deleting a single novel or local download.

```powershell
py -m taiyou_storage.reset           # Read-only preview
py -m taiyou_storage.reset --apply   # Interactive, verified-backup-first reset
```

`11_clear_hf_data.cmd` provides the same backup-first workflow. The destructive path requires an interactive terminal, a complete SHA-256-verified local backup at a pinned dataset revision, and two explicit confirmations. It checks the dataset revision again before committing. **Keep the backup:** automatic restore is not implemented, and Git/LFS history may retain old files.

**No GitHub Action can clear or delete the dataset.** The old backup-free clear workflow and CLI command were retired.

## Recovery boundaries

- A catalogue backup saves `data/library.json` only; it is **not** a full copy of EPUBs, ZIPs, covers or personal sidecars.
- Use [`07_backup_catalogue.cmd`](../07_backup_catalogue.cmd) for a local catalogue copy; use the [private full-backup GitHub Action](GITHUB_ACTIONS.md) for a full separately stored private snapshot.
- A full reset does **not** provide an automated full-library restore command. Retain the verified backup and ask for a reviewed recovery process before attempting restoration.
- Local inspection cache deletion does not delete your private HF files, but older shared-cache entries might be needed by other local programmes. Close active operations first.
- Public Actions may show counts only; never upload per-novel reports as public artefacts. See [GitHub Actions and secrets](GITHUB_ACTIONS.md).
