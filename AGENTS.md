# AGENTS.md: Taiyou Novels Storage Controller

**Last reviewed:** 21 November 2026. **Repository:** `AdityaSreevatsaK/Taiyou-Novels-Storage-Controller`. **Primary branch:** `master`. **Purpose:** dependable Windows-first management of a **PRIVATE** Hugging Face novel dataset, with guarded local operations and limited manual GitHub Actions.

> This file is the **current agent entry point**, not a substitute for reading code/tests. The former detailed handbook is preserved at [docs/archive/AGENTS_PRE_2026-11-21.md](docs/archive/AGENTS_PRE_2026-11-21.md) for history. It contains some obsolete features and paths; **do not** execute old workflow procedures based on that archive.

## Read this first

| Question | Current guide |
| --- | --- |
| Why does this project exist, and how did decisions evolve? | [Vision, original brainstorming and history](docs/PROJECT_VISION_AND_HISTORY.md) |
| What is the runtime architecture, data contract and code map? | [Architecture and technical contracts](docs/ARCHITECTURE.md) |
| What must an autonomous coding agent do and verify? | [AI agent playbook](docs/AI_AGENT_PLAYBOOK.md) |
| What failures created the safeguards? | [Failure register and lessons](docs/FAILURES_AND_LESSONS.md) |
| How is it run, secured, tested and deployed? | [Operations and deployment](docs/OPERATIONS_AND_DEPLOYMENT.md) |
| What is implemented versus future proposal? | [Roadmap](docs/ROADMAP.md) |
| Exact command behaviour and maintenance procedures? | [Documentation index](docs/README.md), [User guide](docs/USER_GUIDE.md), [Safety](docs/SAFETY_AND_RECOVERY.md), [Actions](docs/GITHUB_ACTIONS.md) |
| Required console and GitHub logging style? | [Output conventions](docs/OUTPUT_CONVENTIONS.md) |

**Authority order:** latest explicit user instruction; verified current source/tests and cross-repo runtime contract; current operational guides; historical notes. Never rely on a historical count, plan or mock CI result as proof of the present private HF dataset.

## Mission and boundaries

- **Owns:** prepared novel ZIP/EPUB ingestion, immutable IDs, catalogue reconciliation, covers, private metadata recovery, verified private snapshots, read-only inspection, safe cache cleanup and local Windows command UX.
- **Does not own:** chapter acquisition/scraping (separate `RichardDaffern/Novel-Retriever`), Reader UX/OAuth/Cloudflare deployment (separate `Taiyous-Personal-Library`), or manga-specific data models.
- **Production source:** `AdityaSreevatsaK/Taiyous-Novels`, a **private HF dataset**, not a public code repo or HF Space.
- **Public code:** MIT-licensed repository, but private novels, covers, personal notes, catalogue exports, detailed reports and credentials must **never** be published.
- **Current catalogue:** `data/library.json` with `{"version": 1, "books": [...]}`. Book IDs are immutable 24-character lowercase hex strings; the Reader may own additional metadata keys.
- **Current folders:** readable `data/novels/<id> - <sanitised title>/` and legacy `data/novels/<id>/` are both supported. Use the **stored** book `epubPath`/`archivePath`/`coverPath`; never reconstruct existing paths from the current title. The 14 November 2026 production migration is finished and its one-shot Actions are retired.

## Hard safety invariants

1. **Never test production mutations.** Offline CI uses synthetic fake HF clients. Real HF acceptance, if specifically necessary, uses a pre-created separate private test dataset and a token scoped only to it. Keep production untouched for code/documentation tasks.
2. **Fail closed:** refuse public/inaccessible/ambiguous datasets, malformed or orphaned catalogues, stale revisions, identity conflicts and uncertain remote commit results.
3. **Preview before write:** preserve explicit approval, current-revision/`parent_commit` guards, local content hash checks, bounded batches and safe resume after partial commits. A preview is **not** a successful upload.
4. **Keep reader data:** preserve IDs, progress, personal tags, ratings, notes, reviews, comments, collections, existing valid source genres/status and unknown app-owned fields. Do not conflate "source novel completed" with "finished reading".
5. **Archive/content integrity:** validate ZIP CRC, entry count/expanded-size limits, EPUB structure, image decoding and safe paths. `UNCHANGED` requires proof for all relevant ZIP, EPUB, metadata and remote references, not a single digest.
6. **No unsafe deletion:** `08_restore_novel.cmd` and `09_delete_novel.cmd` remain **nonworking placeholders**. The only full-dataset reset is guarded **local** `11_clear_hf_data.cmd` with complete verified backup, private-target/revision checks and multiple typed confirmations. Never recreate a GitHub Action that clears production.
7. **Public GitHub logs are privacy-sensitive:** no novel title, book ID, source URL, ZIP/EPUB payload, personal record, private path, full report, token or raw exception. Use `taiyou_storage.github_output`, fixed numeric allowlists and `GITHUB_STEP_SUMMARY`.
8. **Local command output is concise:** `console_output.bat` and `console_summary.py` provide START, labelled counts/report, and explicit END state; detailed records go in ignored `reports/` or optional verbose mode. Never suppress warnings, approvals or non-zero exit status.
9. **No boundary crossing:** if Reader or Retriever contract changes are needed, inspect/coordinate those repositories explicitly. This repository does not deploy them.

## Current code map

| Layer | Files |
| --- | --- |
| Remote schema and paths | `taiyou_storage/core.py`, `paths.py` |
| Import and cover reconciliation | `upload.py`, `covers.py`, `cover_batches.py` |
| Read-only inspection and local reports | `inspection.py`, `inspection_cli.py`, `github_checks.py` |
| Private backup and cloud runner | `actions.py`, `remote_backup.py`, `cloud_readiness.py`, `cloud_import.py` |
| Metadata and research | `metadata_repair.py`, `metadata_batch.py`, `metadata_source.py`, `genre_repair.py` |
| Dangerous and local maintenance | `reset.py`, `manifest_backfill.py`, `inspection_cleanup.py` |
| Console and Actions summaries | `console_summary.py`, `github_output.py`, `console_output.bat` |
| User entry points | `00_storage_menu.cmd` and numbered `01`-`18` CMD launchers |
| Tests and automation | `tests/`, `.github/workflows/`, `requirements.txt` + `constraints.txt` |

Read the **actual module, call sites and tests** before modifying behaviour. Do not copy paths or old workflow names from the archived handbook.

## Agent working contract

1. Read the relevant docs and the latest target code, tests and current PR/branch state. Identify desired behaviour, safety invariants and accepted constraints.
2. Use a fresh feature branch from the exact `master` head. Make a scoped, reviewable change, not a rewritten architecture by default.
3. Add tests for normal, negative, ambiguous, stale revision, partial-success and failure paths. No production HF access in CI.
4. Run `py -m pip check`, `py -m compileall -q taiyou_storage tests` and `py -m unittest discover -s tests -q`. CI must pass on Windows and Ubuntu with Python 3.11/3.12 and dependency vulnerability checks.
5. Validate the exact PR head and completed CI job conclusions before merge. Do not equate "queued" or "started" with "passed".
6. Document affected user commands, data contracts, workflows, risks and runbooks in the same change. Prefer linking to one current source rather than duplicating stale instructions.
7. Keep PR titles and descriptions in **Markdown**, with test evidence, security implications and honest boundaries between code merged versus live HF applied.
8. Do not tag/release unless version/change notes and the code-only release process in [Releasing](docs/RELEASING.md) require it.

See the full [AI Agent Playbook](docs/AI_AGENT_PLAYBOOK.md) for investigative, implementation, validation, PR and future-session handover procedures.

## Current limitations agents must not disguise

- Restore single novel and delete single novel launchers are placeholders. Automatic full restore does not exist.
- Atomicity is **per HF commit**, not across an entire multi-batch upload. Resumption must reconcile earlier successes.
- GitHub's workflow concurrency is **not** a global lock against local scripts, reader or other clients.
- A remote-first backup readiness scan is **not** proof that an actual server-side copy can succeed. Cryptographic verification is mandatory for completed snapshots; no automatic fallback to downloading.
- Quick/manifest inspections give **limited evidence**; only deep inspection checks the relevant file bytes.
- This repository does not operate a continuously deployed service. GitHub Actions and the separate Cloudflare Reader are different systems.
- The historical folder migration has already completed. Never re-run its apply steps merely for verification.
- A synthetic/CI test pass is not a real production HF write validation, and a code merge is not a live dataset update.

## Privacy and documentation upkeep

Only commit **synthetic** examples to the public repo. Store real local metadata/audit reports in Git-ignored directories, and detailed remote reports in separate **private** storage. Do not paste credentials or unredacted HF errors into PRs or public CI.

Before finishing a task, update whichever of these living docs changed: [Architecture](docs/ARCHITECTURE.md), [Vision/history](docs/PROJECT_VISION_AND_HISTORY.md), [Incidents](docs/FAILURES_AND_LESSONS.md), [Operations](docs/OPERATIONS_AND_DEPLOYMENT.md), [Roadmap](docs/ROADMAP.md), and relevant feature guides. Record actual evidence (commit SHA, exact CI conclusion, executed synthetic/live test type). Archive historical material rather than silently deleting unique decisions.

**Final rule:** source and current tests define existing behaviour; these docs preserve why it exists and how to extend it safely.
