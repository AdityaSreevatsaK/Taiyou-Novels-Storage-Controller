# Roadmap and open engineering questions

**As at 21 November 2026.** This is a **prioritised planning guide**, not authorisation to modify private datasets or to implement every proposal. Explicit owner instructions and observed current code override this roadmap. Dates are historical milestones, not delivery promises.

## Capabilities already delivered

- Public MIT controller with Windows CMD menu and Python 3.11/3.12 CI on Windows/Ubuntu.
- Smart incrementally reconciled ZIP/EPUB imports, local duplicate/conflict detection, original ZIP downloads and private catalogue exports.
- Immutable 24-character novel IDs; both readable and legacy folder support; 14 November 2026 production-readable migration completed, with the one-shot workflow retired.
- Validated covers, grouped guarded imports and resumable partial batch handling.
- Revision-pinned inspection with quick/manifest/deep modes, inventory, chapter evidence, missing-cover audit, health and integrity reporting, optional inspection sidecar backfill.
- Review-bound source metadata/genre recovery, additive catalogue-only changes and source identity checks.
- Remote-first private backup with remote identity verification, optional full-verified mode, private reporting and source/destination readiness checks.
- Completed consolidated Novel-Retriever export import through a manual GitHub runner.
- Local owned/legacy cache cleanup with typed approval; local-only full reset requiring verified backup; retired public destructive Actions.
- Consistent short START, counts, result and END in local commands and privacy-safe Actions summary tables.

A capability in this section is **not** evidence that the latest production HF dataset contains a given number of novels, covers or chapters.

## Proposed next priorities

| Priority | Candidate improvement | Why / acceptance evidence | Status |
| --- | --- | --- | --- |
| P0 | Maintain privacy, catalogue integrity and reader compatibility whenever new features arrive | No public data leaks, unsafe reset, identity drift or unguarded writes. Run cross-platform offline regression tests | **Permanent invariant**, not a new feature |
| P1 | Strengthen live-HF acceptance for new mutation paths and fault injection | Synthetic disposable private dataset exercises stale revisions, uncertain commit outcomes, network interruption, Xet objects and cross-batch resumes; production is untouched | **Proposed expansion**, not proof all tests exist |
| P1 | Audit every new writer for immutable-ID/source-versus-personal-field preservation | Test title/author changes, readable label mismatch, missing blobs, simultaneous reader writes and status/genre backfills; preserve unknown reader fields | **Ongoing maintenance need** |
| P1 | Keep public GitHub output clean and accurate as new commands are introduced | Fixed numeric labels; clear preview/apply distinction; exit codes, private diagnostics and current workflow coverage tests | **Adopted convention**, future maintenance |
| P2 | Validate backup restore procedures using separate private synthetic snapshots | Recovery instructions and safe rehydration tests that do not overwrite production; explicitly distinguish verification receipt from recoverability | **Proposed**, automatic full restore not implemented |
| P2 | Review safe **single-novel** restore/delete utility requirements | Narrowly scoped identity/path validation, complete backup, source revision, explicit approval, personal-state impact and testable rollback story | **Not implemented**, `08`/`09` remain placeholders |
| P2 | Improve integrity reporting and cache efficiency as the catalogue grows | Evidence-based audit, bounded concurrency, avoid repeated downloads, deterministic ignored reports, reasonable disk use | **Continuous optimisation**, no claim of current defect |
| P2 | Formalise versioned interfaces for Retriever export and Reader catalogue consumers | Fixture-driven contract tests for ZIP manifests, source status, cover paths, sidecars, reader APIs and path compatibility | **Proposed**, requires cross-repository coordination |
| P3 | Review whether an optional automation/scheduler helps | Only if explicitly requested; bound token scope and avoid unattended production writes or publication of private reports | **Idea**, no scheduler implemented |
| P3 | Consider a safer recovery operator UX | Guided preview, count-based risk summary and targeted safe replay rather than broad reset; never reduce confirmation requirements | **Idea**, not a confirmed product requirement |

## Current boundaries and deferred work

1. This is not a scraper or a replacement for `RichardDaffern/Novel-Retriever`. New source providers, retries and chapter acquisition belong in that repo.
2. This is not a web reader. UI, shelf, cover rendering, OAuth, caching, API fan-out and Cloudflare deployment belong in `Taiyous-Personal-Library`.
3. The separate manga ecosystem uses different data contracts. Do not broaden this controller to accept manga page manifests by accident.
4. `08_restore_novel.cmd` and `09_delete_novel.cmd` are deliberate explicit placeholders; the presence of a menu number is **not** a working feature.
5. Full automatic restore, per-library global transactions, distributed lock service, general scheduler and schema migration framework are **not implemented**.
6. The private dataset must not be used as a CI fixture. Real acceptance belongs in a *pre-created* private disposable dataset with restricted token and synthetic-only cleanup.
7. No production migration or backup-free data-clearing Action may be reintroduced by copying an old YAML workflow.
8. Do not expand source metadata research into authenticated scraping, chapter harvesting, redirect/captcha bypass or mass queries. Unsupported proof remains manual.
9. No paid cloud APIs or new deployment service are necessary for the current architecture.

## Open engineering questions to answer before future work

- **Reader contract:** Which current app-owned metadata and sidecar fields must survive a write, and is there an independently versioned shared fixture? Read the latest Reader source instead of assuming the 11 November field list is exhaustive.
- **Remote-copy reliability:** Does the destination region allow `CommitOperationCopy` for the exact object types encountered? Read-only readiness cannot answer that.
- **Partial writes:** If an HF API request times out after a successful server commit, how is the new revision discovered and reconciled without duplicate work?
- **Restore semantics:** Which single-book assets and user state would a restore need, how is identity confirmed, and who approves any destructive overwrite?
- **Scaling:** Which inspections cause material Xet/cache/disk costs, and can manifest evidence answer the question without deep downloads?
- **Cross-repository artifact lifecycle:** What happens when a Retriever run expires, export manifest changes or an earlier batch is only partly complete?
- **Release confidence:** Which workflows have live disposable-dataset tests versus fake-only coverage, and have all expected CI jobs finished on the exact PR SHA?

Do not resolve these with guesses or silently create code features. Write a scoped proposal/tests before implementation, and seek permission where production data access would be involved.

## How to maintain this roadmap

- Keep **delivered**, **investigation**, **proposed** and **deferred** clearly distinguished.
- Link future completed features to actual commits/PRs and tests, then move them from proposed to delivered.
- Do not carry forward a historical catalogue count as a real-time metric.
- Prioritise bugs/data-loss/security over convenience; a fast path must not skip validation or weaken private permissions.
- When a feature touches other repos, record owner, consumer contract, test evidence, permission scope and rollout/rollback before merging.
- The authoritative instructions for an agent doing implementation are in [AI Agent Playbook](AI_AGENT_PLAYBOOK.md); this document is strategic context only.
