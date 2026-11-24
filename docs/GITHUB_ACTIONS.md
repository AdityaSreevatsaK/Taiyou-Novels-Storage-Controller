# GitHub Actions: safe private library checks and maintenance

**Important:** The Storage Controller's code repository is public; the actual
Hugging Face dataset `AdityaSreevatsaK/Taiyous-Novels` must stay **private**.
Do not expose novel titles, source links, IDs, personal metadata, full reports,
ZIPs or EPUBs in public GitHub Actions logs, summaries or artifacts.

## One-click inspection checks

1. Open [Actions > HF - Run library checks (read only)](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/workflows/hf-inspect.yml).
2. Choose **Run workflow** on `master`.
3. Select **quick** (fastest), **manifest** (recommended), or **deep**, then select **Run workflow**.
4. After completion, open the run's **Summary** for numeric results.

The Action runs **one revision-pinned scan** and checks chapter inventory,
missing and suspicious covers, catalogue references, integrity issues, potential
duplicate novels and library health. It displays concise **counts only**.
It runs no Hugging Face writes and has GitHub permission `contents: read`.

- **Quick:** Reads the catalogue and a remote file listing only. Does not fetch\n  EPUBs, original ZIPs or any cover images; sizes and references are listing-level\n  evidence, not proof of readable chapters or images.\n- **Manifest:** Quickly reads catalogue, paths and small valid sidecars. Does
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

## Clean GitHub Actions summaries

Each manual maintenance Action uses `taiyou_storage.github_output` to show a short **start**, **allowlisted numeric metrics**, and **result**. The Actions summary displays a small Markdown table. Underlying private output stays inside the ephemeral runner, never in public logs or uploaded artifacts. A preview reports `Preview only`; apply is a separate explicit step. See [Output conventions](OUTPUT_CONVENTIONS.md). Hosted-runner setup and dependency-install output are controlled by GitHub.

## Automated dependency security checks

The existing `CI` workflow now runs a dedicated `pip-audit` job for the
production requirements and pinned dependency constraints on each PR/push,
plus a scheduled Monday scan. The audit uses no Hugging Face secrets and
fails if known security advisories are found. An advisory needs a reviewed
dependency update and full cross-platform regression tests; never suppress
a vulnerability merely to obtain a green badge.

## Retained workflows

The current active workflow inventory is enforced by `tests/test_github_workflow_cleanup.py`. Every private HF workflow that can inspect or mutate data must check both the exact repository (`AdityaSreevatsaK/Taiyou-Novels-Storage-Controller`) and `refs/heads/master` at the job level, and use the shared `hf-storage-controller` concurrency group. A `workflow_dispatch` event can otherwise run code from the selected branch. The concurrency group serialises these controller Actions only; it is not a lock against local commands, Reader writes or other repositories.

| Workflow | Purpose |
| --- | --- |
| **CI** | Automatic offline tests on Windows/Linux plus weekly and PR dependency vulnerability audit; never reads private HF |
| **HF - Run library checks (read only)** | Manual combined inspection, counts-only logs |
| **HF - Export novel names and conflicts PRIVATELY** | Manual export to a separate private HF backup dataset |
| **HF - Back up entire dataset PRIVATELY** | Remote-first private snapshot, verified using immutable object identities, with optional full-byte verification on a runner |
| **HF - Import Novel-Retriever bundle (cloud only)** | Pull a checked, complete export directly from another GitHub Actions run and upload it to PRIVATE HF without downloading it to Windows |
| **HF - Upload covers from Novel-Retriever artifact** | Manual preview, optional approved cover upload |
| **HF - Restore novel genres from original download artifacts** | Optional specialised historical repair |
| **Release - publish after green master CI** | Version-guarded code-only release |

## Verify cloud readiness without writing data

Use [**HF - Verify remote-first readiness (read only)**](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/workflows/hf-live-readiness.yml)
after configuring `HF_STORAGE_CONTROLLER_TOKEN` and an accessible **PRIVATE**
`AdityaSreevatsaK/Taiyous-Novels-Backup` dataset.

The workflow checks source/destination privacy, immutable file metadata,
remote cryptographic identities and conflicting existing copies. It also runs
a quick library catalogue audit. **No novel EPUBs or ZIPs are downloaded,
no HF commits or backups are created, and no private file paths or titles
are published in this public repository's Actions logs.** The first merge
of this workflow triggers one read-only readiness run on `master`; thereafter
it remains manually dispatchable.

A successful result confirms the available source and destination inventory
and credentials. It **does not prove storage-region compatibility** or
guarantee an actual server-side copy will succeed; that must be confirmed by
a separately authorised real backup, and any failure must stop without
silently switching to full downloads.

## Cloud-only novel import from Novel-Retriever

Use [**HF - Import Novel-Retriever bundle (cloud only)**](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/workflows/hf-cloud-import.yml) from the Storage Controller's Actions tab.

1. Run the Novel Retriever's **Export Completed Novels - Hugging Face Upload Bundle** workflow, or use the existing completed-104 export run.
2. Copy the **export run ID** from the Retriever's Actions URL. It must be the *export* run, not a per-novel download job.
3. On the Storage Controller's cloud import workflow, select `master` and enter the run ID. Choose `taiyou-completed-novels` or `taiyou-completed-104` according to the artifact's name.
4. Leave **apply_changes=false** for an initial preview. The workflow downloads the artifact **to the GitHub runner, not to your laptop**, verifies every book ZIP against the export manifest's SHA-256 and checks for edition conflicts.
5. Once the preview succeeds, rerun the same inputs with **apply_changes=true**. It uses the existing deduplicating, revision-guarded uploader, with atomic HF batches of 5 or 10 novels and optional matching images from the artifact's `covers/` directory.

Never publish the generated private preview reports or the novel artifact from this controller as GitHub Actions artifacts. Output contains only counts. This workflow uses the existing `HF_STORAGE_CONTROLLER_TOKEN` for **write** access to the private HF dataset and `NOVEL_LIBRARY_ACTIONS_TOKEN` when cross-repository GitHub artifact access needs explicit permission.

This bridge supports **completed consolidated exports only**, not arbitrary partially downloaded chapter batches or unverified individual artefacts. The bulk uploader can attach uniquely matched local or exported sidecar covers, but does not yet extract embedded ZIP/OPF-declared EPUB cover artwork into `coverPath` during the same import; see [open issue #54](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/54). An invalid, expired or conflicted export fails without touching Hugging Face. If a previous HF batch was committed but a later batch failed, rerun the same export: the controller skips already committed matching novels. Files remain available in the original Retriever export run until GitHub's artifact retention period ends.

No local download is required for exported Retriever novels. Files found **only on your Windows disk** must still be uploaded through the normal `01_bulk_upload.cmd` path.


## Disposable real-HF backup acceptance

[**HF - Disposable remote backup acceptance**](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/workflows/hf-disposable-backup-acceptance.yml)
is a gated test-only workflow. It uses only the repository Actions secret
`HF_DISPOSABLE_TEST_TOKEN`, **never** the production storage token. On its
initial merge to `master`, the workflow triggers once. It also supports manual
runs on trusted `master`.

The workflow creates two new **PRIVATE** run-specific synthetic datasets,
uploads only fictional EPUB/ZIP/cover/catalogue fixtures, stages a partial
copy, exercises actual `remote_backup()` recovery, verifies a zero-write
rerun, and independently SHA-256-checks every fixture plus the private
receipt. It does **not** access, alter or delete the production dataset, and
does not delete the disposable datasets afterwards.

The test token must have permission to create private datasets in the owner's
namespace. If the secret exists only in a GitHub Environment rather than as a
**repository Actions secret**, this workflow cannot access it and fails
without contacting HF. See [the isolated acceptance runbook](DISPOSABLE_BACKUP_ACCEPTANCE.md).
A green ordinary CI run does not substitute for a successful live synthetic run.

## Remote-first backups (no novel downloads to your laptop)

[**HF - Back up entire dataset PRIVATELY**](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/workflows/hf-private-backup.yml)
now offers two modes:

- **remote-first (default):** Copies source objects from the private novel
  dataset to a separate private backup dataset using Hugging Face
  `CommitOperationCopy` and a pinned source revision. This avoids downloading
  full novel files to the GitHub runner. Each batch is at most 40 source objects.
  It uses remote SHA-256/Xet/Git object identities **and sizes** to verify
  the complete backup before publishing a private verification receipt.
- **full-verified (fallback):** The historical two-way download, upload and
  independent SHA-256 verification. Large binary data are handled only by the
  temporary GitHub runner. This consumes more time, network and disk space,
  but supports environments where HF server-side copies fail or some object
  identity is unavailable.

**Cross-repository LFS compatibility:** the pinned `huggingface_hub==1.33.0`
client requires an Xet hash for server-side duplication of LFS objects.
An LFS object with a valid SHA-256 but no Xet hash is verifiable but not
copyable through `CommitOperationCopy`. Both the metadata-only readiness
check and remote-first backup now **fail before any backup commit** when such
source objects are detected. This is a deliberate fail-closed safeguard, not
a completed backup. Choose `full-verified` **explicitly** if you need to
transfer those files via the temporary cloud runner; no automatic fallback
is attempted.

Both modes keep the original source dataset unchanged, use the existing
`HF_STORAGE_CONTROLLER_TOKEN` Actions secret, and **never publish book bytes,
file names or detailed reports to public GitHub Actions**. The backup must be
PRIVATE and belong to the same Hugging Face owner; cross-repository server-side
copy requires both datasets to be in a compatible storage region. A remote
copy failure does **not** silently fall back to downloading the dataset.
Re-run a failed remote-first snapshot to reuse already verified destination
objects, or explicitly choose full-verified if needed.

A verified remote snapshot is an independent private copy of the files at
one immutable source revision, not a guarantee that the original EPUB contents
are semantically correct. Deep validation is a separate read-only check.
The verification receipt lives inside the PRIVATE backup dataset at
`snapshots/<revision>/verification.json`.

## Limits

- The current source-metadata parser and manual repair validator accept `Completed` and `Ongoing` only. Canonical `Hiatus` and `Dropped` support remains open in [issue #46](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/46); do not infer publication status from reading progress or chapter counts.

GitHub Actions cannot access ZIP files that exist only on your Windows
computer. New local uploads must first reach GitHub as a private permitted
artifact or be uploaded directly. Byte-level EPUB validation still requires
reading contents on an ephemeral cloud runner, although no files reach your
laptop. Remote backup and quick audits usually need only API metadata and
small JSON content, so they scale considerably better to large catalogues.
Any read/write operation that needs HF credentials requires Actions secrets.

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

**No GitHub Action can delete the Hugging Face repository or clear its production data.** Repository deletion is forbidden and is not implemented. To intentionally clear the private dataset's `data/` content tree, only the local `11_clear_hf_data.cmd` runs the complete backup-first, checksum-verified, revision-guarded process with multiple explicit confirmations. This is a content reset, not repository deletion.

Local-only operations include uploading ZIPs stored on your Windows computer,
comparing local ZIP bytes to the remote dataset, and deleting local cached
downloads. The GitHub Action cannot see local Windows files.

Never upload private reports, novel ZIPs or EPUBs as GitHub Actions artifacts.
