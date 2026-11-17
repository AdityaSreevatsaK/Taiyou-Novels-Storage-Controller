# GitHub Actions: safe private library checks and maintenance

**Important:** The Storage Controller's code repository is public; the actual
Hugging Face dataset `AdityaSreevatsaK/Taiyous-Novels` must stay **private**.
Do not expose novel titles, source links, IDs, personal metadata, full reports,
ZIPs or EPUBs in public GitHub Actions logs, summaries or artifacts.

## One-click inspection checks

1. Open [Actions > HF - Run library checks (read only)](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/workflows/hf-inspect.yml).
2. Choose **Run workflow** on `master`.
3. Select **manifest** (recommended) or **deep**, then select **Run workflow**.
4. After completion, open the run's **Summary** for numeric results.

The Action runs **one revision-pinned scan** and checks chapter inventory,
missing and suspicious covers, catalogue references, integrity issues, potential
duplicate novels and library health. It displays concise **counts only**.
It runs no Hugging Face writes and has GitHub permission `contents: read`.

- **Manifest:** Quickly reads catalogue, paths and small valid sidecars. Does
  not fetch every EPUB or ZIP. An unverified cover or chapter range stays
  `UNVERIFIED` rather than being presented as valid.
- **Deep:** Downloads EPUB/ZIP/image contents to an ephemeral runner to check
  them. This is slower and can use significant temporary disk space.
- **Details:** Complete CSV/JSON/HTML reports are created **temporarily inside
  the runner** and automatically discarded. They are **not downloadable from
  GitHub** because per-novel reports can reveal private information. Run the
  matching Windows commands to keep detailed reports on your own computer.
- **Failure:** Authentication, malformed reports and interrupted or failed
  scans fail the workflow. Raw private errors are suppressed from public logs.
  Other findings appear as counts, not automatic data repairs.

### Required repository secret

Go to **Settings > Secrets and variables > Actions** in this GitHub repository.

Prefer a fine-grained Hugging Face token with **read-only access to only**
`AdityaSreevatsaK/Taiyous-Novels`, stored as `HF_INSPECTION_READ_TOKEN`.
For compatibility, this Action falls back to your existing
`HF_STORAGE_CONTROLLER_TOKEN` if the new read-only secret is absent.

The existing storage token is also needed for optional manual **write** workflows
such as the private backup, private report export, cover upload or historical
genre repair. It must never be exposed in logs. For backups and private report
exports, grant access to a **separate private** backup dataset (for example,
`AdityaSreevatsaK/Taiyous-Novels-Backup`).

The cover workflow uses artifacts from `RichardDaffern/Novel-Retriever` and
accepts `NOVEL_LIBRARY_ACTIONS_TOKEN` when cross-repository GitHub artifact
permissions are needed.

## Retained workflows

| Workflow | Purpose |
| --- | --- |
| **CI** | Automatic offline tests on Windows and Linux; never reads private HF |
| **HF - Run library checks (read only)** | Manual combined inspection, counts-only logs |
| **HF - Export novel names and conflicts PRIVATELY** | Manual export to a separate private HF backup dataset |
| **HF - Back up entire dataset PRIVATELY** | Manual snapshot and checksum verification |
| **HF - Upload covers from Novel-Retriever artifact** | Manual preview, optional approved cover upload |
| **HF - Restore novel genres from original download artifacts** | Optional specialised historical repair |
| **Release - publish after green master CI** | Version-guarded code-only release |

## Retired workflows

The readable-folder migration was **completed and verified on 14 November
2026**. Its production migration Action, acceptance/preflight/readiness Actions,
one-shot pilots and verification jobs, and one-time branch-pruning Actions have
been removed to declutter the Actions tab and prevent stale operations.

Historical migration procedures remain documented in
`docs/READABLE_FOLDER_MIGRATION.md`. The Python implementation and offline
regression tests remain available for engineering reference. Do **not** attempt
production migration from a retired workflow.

## Destructive operations and local-only work

**No GitHub Action can clear or delete the novel dataset.** To intentionally
reset the entire private library, only the local `11_clear_hf_data.cmd` runs
the complete backup-first, checksum-verified, revision-guarded process with
multiple explicit confirmations.

Local-only operations include uploading ZIPs stored on your Windows computer,
comparing local ZIP bytes to the remote dataset, and deleting local cached
downloads. The GitHub Action cannot see local Windows files.

Never upload private reports, novel ZIPs or EPUBs as GitHub Actions artifacts.
