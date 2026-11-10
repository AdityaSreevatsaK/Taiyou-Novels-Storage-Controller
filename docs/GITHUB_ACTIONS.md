# GitHub Actions: Private Hugging Face Storage Operations

This repository is **PUBLIC**. Treat workflow logs and artifacts as publicly accessible.
Do NOT upload novel ZIPs, EPUBs, covers, title reports or private backups
as GitHub Actions artifacts.

## One-time setup

In **GitHub > Taiyou-Novels-Storage-Controller > Settings > Secrets and variables
> Actions**, add a repository secret called **HF_STORAGE_CONTROLLER_TOKEN**.

This Hugging Face token must have read/write access to the source private dataset
AdityaSreevatsaK/Taiyous-Novels and to a separate PRIVATE backup dataset,
such as AdityaSreevatsaK/Taiyous-Novels-Backup. The backup dataset may be created
automatically as private if your token has that permission. To use full dataset
deletion, the token must also have the necessary Hugging Face delete permission.

For cover import directly from another GitHub repository's Actions run, add
**NOVEL_LIBRARY_ACTIONS_TOKEN** with permission to read Actions artifacts in
RichardDaffern/Novel_Library if the built-in GitHub token lacks cross-repo access.
The download workflow uses that token only for source-artifact retrieval.

Optionally create GitHub Environment **hf-destructive** and configure required
reviewers under Settings > Environments to add approval before either destructive
operation. Review policies depend on your GitHub plan/repository settings.

## Run workflows

Go to Actions and choose one of:

| Workflow | Result |
|---|---|
| HF - Inspect library (read only) | Displays source Git SHA, counts, possible duplicate titles and orphan-folder count; **no novel titles in public logs** |
| HF - Export novel names and conflicts PRIVATELY | Stores library.json, novels.csv and conflicts.csv in PRIVATE backup dataset under reports/ |
| HF - Back up entire dataset PRIVATELY | Copies every source file to snapshots/<SHA>/ in PRIVATE backup dataset, verifies each SHA-256 against remote copy; **no GitHub artifact** |
| HF - Upload covers from Novel_Library artifact | Downloads an existing cover-only Actions artifact by run ID, validates, previews, and uploads only if apply_changes is enabled |
| HF - CLEAR ALL data (backup first) | **Destructive:** full independent private backup and verification, then deletes all data/ files except a recreated empty library.json |
| HF - DELETE ENTIRE dataset repository (backup first) | **More destructive:** full independent private backup and verification, then deletes the whole Hugging Face DATASET repository, including its Git history |

For both destructive actions:
1. Run **HF - Inspect library** and copy its complete 40-character SOURCE REVISION.
2. Select the desired destructive workflow and paste the source revision.
3. Type its exact required phrase: either
   CLEAR DATA AdityaSreevatsaK/Taiyous-Novels
   or DELETE DATASET AdityaSreevatsaK/Taiyous-Novels.
4. For full repository deletion, also tick the irreversible history-loss acknowledgement.
5. The workflow creates/uses a **different, verified PRIVATE Hugging Face dataset**,
   copies **all** files there and verifies hashes before attempting deletion.
6. If the backup fails, is public, or the source revision changes: **NO deletion**.

**WARNING:** Full dataset repository deletion destroys the repository and its
history. The private backup contains a file snapshot, NOT the original Git history,
and must be restored into a newly created private dataset to recover the files.
An interrupted job may leave a partial private backup, but does not delete anything
until every file is verified. HF repository deletion has no conditional parent-commit
API, so avoid other writers during that operation.

## What remains local-only

- Bulk upload of ZIPs from a **Windows local folder**. GitHub Actions cannot see
  local files directly. To add remote bulk uploads, we must first define a safe
  Novel_Library artifact-to-archive converter and verify the exact artifact layout.
- Local ZIP sync status: requires local novel files.
- Restoring a whole library or removing an individual duplicate: not yet implemented.
- Full content-integrity auditing: planned.

Routine Python CI remains offline, has **no** Hugging Face credentials, and never
writes to either dataset. No scheduled destructive tasks are enabled.
