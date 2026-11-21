# Architecture, codebase and technical contracts

**Reviewed against source on 21 November 2026.** This is the current high-level design map. For precise arguments and validation conditions inspect the referenced Python module and tests; this document is not an API specification.

## System at a glance

```text
Approved local ZIPs/covers         Novel-Retriever completed export
            |                                   |
  Windows CMD launchers             Manual cloud-import Action
            |                                   |
            +---------------+-------------------+
                            |
                       Python controller
        validate -> read pinned catalogue -> plan -> approve
                            |
                  private, revision-guarded
                   Hugging Face dataset
                  data/library.json (v1)
                  data/novels/<book folder>/*
                            |
               Separate Cloudflare/HF reader
              Taiyous-Personal-Library (not here)

  Separate PRIVATE HF backup dataset <--- remote-first/full backup
  Local ignored reports/cache       <--- inspections and diagnostics
```

This repository is **neither** a web API nor a frontend. There is no independent database, queue, global lock or deployed web service. A GitHub Action is an ephemeral execution environment, not persistent application hosting.

## Tech stack and runtime

| Layer | Implementation |
| --- | --- |
| Core business logic | Python 3.11/3.12; stdlib `argparse`, `json`, `zipfile`, `hashlib`, `pathlib`, CSV, EPUB/HTML parsing |
| HF transport and revisions | `huggingface_hub`, Git commit SHA/`parent_commit`, private dataset APIs, server-side `CommitOperationCopy` where supported |
| Archive/cover inspection | ZIP/EPUB validators, SHA-256 and Pillow image verification |
| Verified public metadata extraction | Beautiful Soup with restricted exact public book-page fetches |
| Local interface | `00_storage_menu.cmd` and numbered `01`-`18` Windows launchers; shared `console_output.bat` helper |
| Cloud runner | GitHub Actions with manual workflows and per-step fine-grained secrets |
| Dependency management | `requirements.txt` constrained by exact tested versions in `constraints.txt` |
| Test and release | Python `unittest` plus synthetic HF fakes; Windows and Ubuntu, Python 3.11/3.12; pinned Actions SHAs; `pip-audit`; gated `release.yml` |
| Reader integration | A **different** repository, Cloudflare Pages/Functions and HF OAuth, consuming the private catalogue and file paths |

Local prerequisites: Python, installed requirements, HF login/token with *the minimum required access*, Windows CMD for double-click usage, disk space for selected imports or deep scans. GitHub runners use their own environment and Actions secrets; a developer's laptop login is **not** automatically available to Actions.

### Dependencies and configuration

- Direct runtime dependencies are declared in `requirements.txt`: `huggingface_hub>=0.24,<2`, `Pillow>=13,<14` (strict image decoding) and `beautifulsoup4>=4.14,<5` (restricted public book-page metadata parsing).
- `constraints.txt` pins the tested direct and transitive versions. Update it deliberately and run the full Windows/Linux Python 3.11/3.12 matrix plus `pip-audit`; do not casually remove the constraints include.
- The default source is `AdityaSreevatsaK/Taiyous-Novels`. `HF_DATASET_REPO` can override the dataset in supported CLI paths; any override must still pass private-dataset and safety validation. `HF_TOKEN` or `hf auth login` supplies local authentication. GitHub Actions use repository secrets such as `HF_INSPECTION_READ_TOKEN`, `HF_STORAGE_CONTROLLER_TOKEN` and `NOVEL_LIBRARY_ACTIONS_TOKEN` only in the workflows that need them.
- No `pyproject.toml`, application server, database, queue or frontend build is part of this repository. The Python package is invoked with `python -m taiyou_storage.<module>`; Windows CMD files are convenience launchers.


## Codebase map

| Responsibility | Primary source | Comments |
| --- | --- | --- |
| Repo ID, catalogue validation, hashing, duplicate listing | `taiyou_storage/core.py` | HF source repo and schema-1 catalogue contract |
| Safe legacy/readable novel folder paths | `taiyou_storage/paths.py` | Book ID and current display title are distinct |
| Local list, conflict, status and catalogue backup | `taiyou_storage/cli.py` | Read-only catalogue operations and local files |
| Original ZIP download/export | `taiyou_storage/downloads.py` | Retrieves the catalogue-declared original archive paths |
| Novel ZIP and EPUB parsing, planning and upload | `taiyou_storage/upload.py` | Strong equality, edition ambiguity, Xet-compatible staging and guarded writes |
| Multi-novel batching and local cover discovery | `taiyou_storage/bulk_batch.py` | Up to 10 novel targets per atomic commit; matches only supplied local `covers/` assets |
| Local ZIP duplicate equivalence | `taiyou_storage/local_dedupe.py` | Opt-in verified duplicate skipping; materially different editions block the batch |
| Cover package parsing, matching and plans | `taiyou_storage/covers.py` | Never creates a novel entry |
| Cover commit batching and resumption | `taiyou_storage/cover_batches.py` | Separate cover-import transaction; quota/rate-limit handling, per-batch commit |
| Read-only revision-pinned inspection | `taiyou_storage/inspection.py` | Listing, sidecar and deep evidence differ |
| Inspection sidecars and local cache | `taiyou_storage/inspection_manifest.py`, `inspection_cache.py` | Validated lightweight evidence and revision-keyed cache |
| Local inventory, integrity, cover, comparison and HTML reports | `taiyou_storage/inspection_cli.py` | Reports and caches remain ignored |
| GitHub privacy-safe combined inspection | `taiyou_storage/github_checks.py` | Publishes numeric counts only |
| Optional inspection manifest backfill | `taiyou_storage/manifest_backfill.py` | **Mutating**, preview-only by default |
| Selective local cache deletion | `taiyou_storage/inspection_cleanup.py` | Never removes remote HF files |
| Local data-tree reset | `taiyou_storage/reset.py` | Clears only HF `data/` contents after verified local backup and typed confirmations; never deletes the repository |
| Manual private backup and report entry points | `taiyou_storage/actions.py` | No broad delete Action |
| Remote-first snapshot identity and copy | `taiyou_storage/remote_backup.py` | Source/destination immutable object identities |
| Read-only backup and source readiness | `taiyou_storage/cloud_readiness.py` | No actual copy verification until backup runs |
| Completed export verification | `taiyou_storage/cloud_import.py` | SHA-256-check exported bundle before any cloud import |
| One-novel source-metadata audit/repair | `taiyou_storage/metadata_repair.py` | Additive catalogue-only write with backup |
| Public source-page extraction | `taiyou_storage/metadata_source.py` | Strict allowlist, no chapter crawling or bypass |
| Research JSON import, approval and batch repair | `taiyou_storage/metadata_batch.py` | Hash/revision-bound candidate approval |
| Historical genre restoration | `taiyou_storage/genre_repair.py` | Optional and dependent on old artifact evidence |
| Concise local reporting | `taiyou_storage/console_summary.py` | Clear preview, complete, blocked or failed statuses |
| Restricted public Actions output | `taiyou_storage/github_output.py` | Fixed task/metric allowlist; raw private output stays on ephemeral runner |
| Historical folder migration | `taiyou_storage/migrate_folders.py`, `taiyou_storage/migrate_production.py`, `scripts/verify_disposable_folder_migration.py` | Retained source/tests for history; one-shot production workflows are retired |
| Windows command frontends | `00_storage_menu.cmd`, `01_bulk_upload.cmd` to `18_repair_novel_metadata.cmd` | Business logic belongs in Python, not CMD |
| Offline safety and functional regression | `tests/` | Use matching tests and full CI matrix for changes |

**Placeholders:** `08_restore_novel.cmd` and `09_delete_novel.cmd` explicitly return "Not implemented" and do not make HF changes. They must not be presented as working restore/delete functionality.

## HF schema and storage ownership

**Production:** private HF **dataset** `AdityaSreevatsaK/Taiyous-Novels`. The current root catalogue contract is:

```json
{
  "version": 1,
  "books": [
    {
      "id": "aaaaaaaaaaaaaaaaaaaaaaaa",
      "metadata": {
        "id": "aaaaaaaaaaaaaaaaaaaaaaaa",
        "title": "Fictional Example",
        "author": "Sample Author",
        "sourceTags": ["Fantasy"],
        "personalTags": [],
        "progress": 0,
        "status": "Completed"
      },
      "epubPath": "data/novels/aaaaaaaaaaaaaaaaaaaaaaaa - Fictional Example/source.epub",
      "archivePath": "data/novels/aaaaaaaaaaaaaaaaaaaaaaaa - Fictional Example/original.zip"
    }
  ]
}
```

This is **synthetic and illustrative**, not a complete catalogue entry or an example of current production data.

The **stable ID** is exactly 24 lowercase hexadecimal characters. New IDs initially derive from source EPUB content, but after creation are never regenerated just because a downloaded EPUB changes. Source-managed fields and reader-owned/personal fields coexist in `metadata`. Retain unknown or app-owned fields. Do not equate `sourceTags` (publisher/source genres) with `personalTags` (user choices); source publication status is not "finished reading".

Book folder rules:
- Legacy: `data/novels/<id>/source.epub`.
- Readable: `data/novels/<id> - <sanitised-label>/source.epub`.
- Newer novels normally use readable folders. The completed 14 November production migration moved the historical books.
- For **existing** books, use the stored `epubPath`, `archivePath` and `metadata.coverPath`/`coverPath`. **Do not rebuild a path from the current title.**
- An older folder label can legitimately differ from a subsequently edited novel title.
- Readable/legacy support is intentional; path traversal, wrong-ID references, unsupported cover extensions, and mismatched folder references must fail validation in `paths.py`.
- Other files may live under `data/`. A full reset touches more than just EPUBs and ZIPs, hence its exceptionally strong guardrails.

Do not copy the **manga** schema (`schemaVersion`, `mediaKind`, `entries`) into this **novel** repository. Its reader contract is `version` plus `books`.

## Important data flows

### 1. Local smart upload

1. Enumerate prepared ZIPs in `novels/`, validate CRC/ZIP budgets/EPUB structure, metadata and duplicate local candidates.
2. Read only the required remote catalogue and files from a pinned private revision; do not treat a corrupt or orphaned catalogue as a fresh empty library.
3. Match by strong identity and permitted stable-ID rules. Compare ZIP, EPUB and source metadata, not merely titles or one hash.
4. Emit the plan with `NEW`, `UPDATE`, `UNCHANGED` and `CONFLICT` plus private detail in `reports/`.
5. On approved apply, recheck local file hashes, current remote identity and dataset revision. Stage only necessary changes and commit guarded batches.
6. If some batches succeed and a later one fails, preserve successful commits, re-preview against latest revision and retry. No global rollback is promised.

See [Smart upload](SMART_UPLOAD.md).

### 2. Covers

Validate a local/retrieved cover archive, image integrity and unique book identity; do not invent novels. Group cover files and catalogue link changes into bounded atomic HF commits, using `cover_batches.py`. A short recoverable 429 may be retried within limits; long/unknown quotas and ambiguous matches stop. Verify and resume from the new revision. During normal novel upload, `bulk_batch.py` can also match **separately supplied local** images from `covers/` and include them in the novel batch. It does **not** yet extract embedded ZIP/OPF-declared EPUB artwork and create a standalone `coverPath` as part of that upload; this remains [open issue #54](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/54).

### 3. Inspections and local cleanup

`inspection.py` reads a pinned source revision. **Quick** uses catalogue plus remote listing; **manifest** uses lightweight evidence; **deep** downloads content on the executing device/runner and verifies bytes. A chapter count or range is not equivalent to complete readable EPUBs. A present cover path is not proof of a valid displayable cover. Local `reports/` and cache are private and Git-ignored. Cleanup `17` deletes only selected owned/legacy **local** cache entries with typed confirmation, never HF data.

### 4. Metadata recovery

Audit absent source fields without changing binary objects. Public book-page discovery is conservative; imported research JSON is not automatically source-verified. Bind candidates, reviewed approvals and final plan to ID, exact canonical source URL, content hashes and current dataset revision. Apply only missing allowlisted fields; back up the previous private catalogue. Preserve progress, personal metadata, source fields already present and all EPUB/ZIP/cover files.

The current parser and validator support canonical source publication states `Completed` and `Ongoing` only. `Hiatus` and `Dropped` aliases/canonicalisation remain open [issue #46](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/46); do not infer them from chapter counts or reading progress.

See [Metadata repair](METADATA_REPAIR.md).

### 5. GitHub cloud import and private backups

The cloud bridge downloads a **completed consolidated** Novel-Retriever artifact onto an ephemeral runner, verifies the export manifest's individual ZIP SHA-256/structure, then uses the same guarded uploader. A partially completed chapter batch is not an acceptable cloud import input.

Remote-first backups copy files into `snapshots/<source-revision>/files/` inside a **separate private HF dataset**, comparing actual remote cryptographic object identities and sizes before writing a private verification receipt at `snapshots/<revision>/verification.json`. Storage-region incompatibility or unavailable identities are a hard stop. Explicit `full-verified` mode transfers/validates file bytes via an ephemeral runner. Neither mode writes to the original source dataset.

## Current implementation gaps

- Embedded cover extraction during the regular ZIP/EPUB bulk upload is not implemented; matching local sidecar files in `covers/` is a narrower delivered capability ([#54](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/54)).
- Metadata status parsing and validation do not yet support `Hiatus` or `Dropped` ([#46](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/46)).
- `08_restore_novel.cmd` and `09_delete_novel.cmd` are placeholders. No automatic full restore exists.
- The historical migration code remains in the repository for traceability and tests; its production Actions are retired and must not be treated as runnable deployment tooling.

## Consistency and security model

- **Optimistic concurrency, not global locking:** apply uses `parent_commit`/revision guards. The reader, a local script or another repo can still modify the dataset concurrently.
- **Atomicity:** one HF commit, **not** the entire workflow. Preserve the distinction between partial completion and failure.
- **Repository privacy:** all production reads/writes validate a private dataset. Read-only operations cannot silently broaden into writes.
- **Data protection:** validate ZIP entry counts, expanded sizes, paths and image decoding; preserve app-owned fields.
- **Permissions:** GitHub workflows receive narrowly scoped HF and GitHub credentials only where needed. CI has no production token.
- **Public observability:** only allowlisted numeric labels, clear run states and small GitHub Step Summary tables. Full raw diagnostics are local or transient, not public artifacts.
- **Real integration checks:** use a pre-created, synthetic-only **private** disposable HF dataset with repository-specific permissions, no production-token reuse and exact cleanup rules. A mocked test does not prove a live transfer.

See [operations and deployment](OPERATIONS_AND_DEPLOYMENT.md), [safety](SAFETY_AND_RECOVERY.md), [failures](FAILURES_AND_LESSONS.md), and [agent playbook](AI_AGENT_PLAYBOOK.md).
