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

The **data-tree reset** removes **every file under `data/`** in your private dataset: novels, EPUBs, ZIPs, covers and any saved app data there. It is not intended for deleting a single novel or local download. Deleting the Hugging Face repository itself is forbidden and is not implemented; the reset only creates a commit deleting selected `data/` files.

```powershell
py -m taiyou_storage.reset           # Read-only preview
py -m taiyou_storage.reset --apply   # Interactive, verified-backup-first reset
```

`11_clear_hf_data.cmd` provides the same backup-first workflow. The destructive path requires an interactive terminal, a complete SHA-256-verified local backup at a pinned dataset revision, and two explicit confirmations. It checks the dataset revision again before committing. **Keep the backup:** automatic restore is not implemented, and Git/LFS history may retain old files.

**No GitHub Action can clear production data or delete the repository.** The old backup-free clear workflow/command were retired; the remaining content reset is local-only and backup-first.

## Verified private backup and recovery review (no automatic restore)

**Proof already available, synthetic only:** the independent
[full-verified acceptance run #45436984800](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/45436984800)
successfully copied six synthetic objects to a separate **private**
disposable HF dataset, verified its private manifest at a pinned
revision, independently re-read all objects, checked their lengths,
SHA-256 and byte equivalence, and confirmed the original synthetic
source revision was unchanged. This did **not** back up or restore
the production novel dataset.

For any future **production** backup, the operator must separately
authorise that data-changing operation, verify the destination dataset
is private and distinct from the source, and choose the
[retained private backup workflow](GITHUB_ACTIONS.md) explicitly.
The default remote-first mode rejects source LFS files lacking Xet
metadata before creating a partial copy; `full-verified` is the
previously validated synthetic alternative, but it downloads original
bytes onto the temporary cloud runner and may take substantial
time, disk space and bandwidth. No mode may silently fall back or
overwrite a conflicting private snapshot.

Before calling an actual private snapshot *recoverable*:

1. Record the immutable production **source SHA** and independent
   backup **destination SHA** in a private operator record.
2. Confirm the backup manifest or receipt lists exactly the
   expected original `data/` files and any required sidecars,
   excluding no personal-state assets.
3. Compare independent SHA-256 hashes for each original and
   destination object at those pinned revisions. If a receipt uses
   remote object identities, confirm the identity types are
   comparable and never accept equal sizes alone.
4. Rehydrate representative EPUBs, ZIP archives, covers, catalogue,
   and personal-state documents **into an isolated disposable
   location**, and verify their exact bytes and safe paths without
   editing production.
5. Confirm private access controls and unchanged original
   source revision. Preserve all reports privately.

Until all checks pass, a metadata-only readiness report or
`Snapshot verified` count is **not** an independently verified
production restore. There is still no automatic whole-library
restore; an actual recovery requires a separately reviewed,
revision-guarded restoration procedure. Do not reset or delete
production to test recovery.

## Recovery boundaries

- A catalogue backup saves `data/library.json` only; it is **not** a full copy of EPUBs, ZIPs, covers or personal sidecars.
- Use [`07_backup_catalogue.cmd`](../07_backup_catalogue.cmd) for a local catalogue copy; use the [private full-backup GitHub Action](GITHUB_ACTIONS.md) for a full separately stored private snapshot.
- A full reset does **not** provide an automated full-library restore command. Retain the verified backup and ask for a reviewed recovery process before attempting restoration.
- Local inspection cache deletion does not delete your private HF files, but older shared-cache entries might be needed by other local programmes. Close active operations first.
- Public Actions may show counts only; never upload per-novel reports as public artefacts. See [GitHub Actions and secrets](GITHUB_ACTIONS.md).
