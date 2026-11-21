# Project vision, evolution and design decisions

**Last reviewed:** 21 November 2026. **Repository:** AdityaSreevatsaK/Taiyou-Novels-Storage-Controller. **Status:** living product context with dated historical evidence. The source code, current tests and deployed reader contract take precedence over historical plans.

## Original vision

Taiyou's Personal Library needed a reliable, Windows-friendly way to move *already acquired and packaged* novel EPUB/ZIP files, metadata and covers into a **private** Hugging Face dataset, while keeping a separate reader application simple. The owner wanted double-click commands rather than having to operate HF APIs manually, with a safe review of what would be new, changed, conflicting or already present. Personal reading state must survive successive downloads and metadata corrections.

The initial product idea evolved from a simple bulk uploader into a storage maintenance/control plane: catalogue health, deduplication, original-archive recovery, cover attachment, metadata repairs, reversible evidence-based maintenance, private backups, remote checks and reports. The controller remains **a storage utility, not the novel retriever or the reading application**.

### Non-negotiable product principles

1. **Private by design:** public MIT code, private HF dataset, no personal catalogue exports, novel bytes, source URLs or tokens in Git commits, CI logs or public artifacts.
2. **Personal information is durable:** immutable 24-hex IDs, progress, reviews, comments, ratings, tags, collections and other app-owned fields must not be lost to source-metadata updates.
3. **Preview before mutation:** show actions and reasons; destructive actions require more stringent approval, verified backups and fresh revision checks.
4. **Reconcile rather than overwrite:** identify source and edition ambiguity, protect original ZIP/EPUB/cover, skip verified unchanged records and repair missing parts selectively.
5. **Useful on Windows:** a numbered CMD launcher set and short console summaries with optional private detailed reports; Python contains the business logic.
6. **Cloud execution where helpful:** manual GitHub Actions for inspection, backup and verified completed Retriever bundles reduce laptop downloads without granting broad public data access.
7. **Fail closed:** uncertainty about source identity, private visibility, catalogue validity, remote revision, or commit outcome must stop writes.
8. **Bounded and resumable operations:** individual HF commits have limited size and scope, and already committed batches remain valid if a later batch fails.

## Evolution and decisions

| Period | Problem or brainstorm | Decision and result |
| --- | --- | --- |
| 7-10 November 2026 | Manual local ZIPs, covers and a private HF repository needed repeatable ingestion | Build Python plus double-click Windows commands; use `data/library.json` as catalogue and `source.epub` plus `original.zip` per novel |
| 10-11 November | Re-imports, ambiguous editions, absent metadata and unsafe delete operations | Add checked equality for ZIP, EPUB and metadata; stable-ID matching; conflict reports; remove backup-free GitHub destructive workflows; verified backup before reset |
| 11 November | Cover uploads throttled or stalled; production-readiness audit found gaps in guards | Bounded revision-guarded cover batches, conservative retries, archive-size and ZIP entry limits, cross-platform tests and dependency pinning; first versioned release `v0.1.0` |
| 13-14 November | Opaque ID-only folders hard to inspect directly in HF browser | Choose `<id> - <sanitised title>` for readable folder labels, **preserving immutable IDs and catalogue-owned paths**, with dual-format support; test against synthetic books in a disposable private dataset before protected production migration |
| 14 November | Production folder migration | Verified 89/89 readable folders, 0 conflicts, 221-file SHA-256-verified private backup and independent read-only post-migration audit; retired one-shot migration Actions |
| 17 November | Existing inspection/download commands were insufficient for library-scale verification | Add common revision-pinned read-only inspector, quick/manifest/deep evidence levels, chapter inventory, cover audit, health report, local Retriever comparison and owned cache cleanup |
| 18 November | Earlier Retriever packages omitted source genres/synopses/status even though personal fields were intact | Add additive, source-identity-checked metadata audit and repair, researched JSON import, review/approval digests and one revision-guarded catalogue commit with a private backup |
| 20-21 November | Uploading many completed downloads through a local machine was inefficient | Introduce cloud-only import of verified completed Novel-Retriever export artifacts, bounded resumable uploads, read-only cloud readiness and remote-first private HF snapshots with cryptographic object verification |
| 21 November | Hundreds of log lines obscured outcomes and risked leaking private details | Standardise START/summary/END output for Windows commands, fixed numeric allowlists and GitHub Step Summary tables; preserve detailed private diagnostics and safety prompts |

The November migration audit is recorded in [post-migration verification](POST_MIGRATION_VERIFICATION_2026-11-14.md); the test dataset boundaries are in [cross-repository acceptance history](CROSS_REPO_READABLE_FOLDER_ACCEPTANCE.md). Historical novel and cover counts describe specific snapshots, **not the current live catalogue size**.

## Brainstorms, alternatives and trade-offs

| Choice | Alternatives discussed or encountered | Why the accepted approach matters |
| --- | --- | --- |
| HF private **dataset** as source of truth | Public static assets, app-owned binary store, separate server/database | Preserves existing reader integration, revision history, privacy and no always-on storage server |
| Python logic with Windows CMD launchers | Complex desktop app, web administrator, Windows-only Python implementation | Easy double-click use while keeping testable cross-platform code and CI |
| Immutable IDs and catalogue paths | Recompute IDs on new EPUB, use title as identity, rename folder whenever title changes | Prevents disruption of reading state and keeps links valid after novel/title updates |
| Original archive **and** extracted EPUB | Retain only a ZIP or only EPUB | Keeps source provenance/recovery while allowing direct reader access |
| Strong hash/source matching | Title-only matching or trusting "same ZIP" | A same ZIP can coexist with missing/corrupt EPUB or stale metadata; conflicts should be inspected, not guessed |
| Batches with per-commit atomicity | One gigantic commit, one cover per commit, all-or-nothing illusion | Smaller guarded operations reduce quota/timeout risk; a later failure is explicitly partial, then resumed |
| Remote-first snapshot plus full-verified fallback | Always download the complete dataset to a Windows laptop | Avoids laptop disk pressure when HF supports server-side copy; fallback is explicit, never silent |
| Count-only public logs with private local reports | Detailed public per-book output, JSON dumps | Clear terminal UX while protecting catalogue and personal data |
| Separate Retriever, controller and Reader repositories | One application handling scraping, storage and UI | Domain boundaries and independent release/permission models |

Earlier exploratory designs considered abstract storage adapters and a generic framework. The **implemented** code is an HF-specific private-dataset controller. Do not describe mock/in-memory clients as a production-pluggable provider interface. Likewise, a proposal to simplify deletion to a checkbox was not retained: the current safety requirement is backup-first, revision-guarded and typed confirmation. Historical requests to remove the full-dataset clearing menu option do not override the **current** local-only, guarded reset implementation; assess the latest explicit owner decision before changing it.

## Ecosystem boundaries

- **Source acquisition:** [RichardDaffern/Novel-Retriever](https://github.com/RichardDaffern/Novel-Retriever), formerly Novel_Library, prepares files and completed export bundles. This controller does **not** scrape chapters or circumvent source access.
- **Storage authority:** private HF dataset `AdityaSreevatsaK/Taiyous-Novels`.
- **Reader and UI:** [Taiyous-Personal-Library](https://github.com/AdityaSreevatsaK/Taiyous-Personal-Library), deployed separately through Cloudflare Pages/Functions with HF OAuth. The controller does not own themes, reading progress UX, shelf filters or reader API fan-out.
- **Backups:** independent private HF destination, normally `AdityaSreevatsaK/Taiyous-Novels-Backup`, and local backup files for a full reset.
- **Manga:** a separate Manga Storage Controller follows some analogous conventions; manga schema and page manifests **must not** be applied to novel `version: 1, books: [...]` data.

A cross-repository change is not complete when its local tests pass. Validate both producer and consumer contracts, including reader paths, metadata fields and permissions.

## Intended user experience

1. Prepare authorised novel ZIPs and optional covers in the expected local folder, or use a **complete, verified** Novel-Retriever export on an ephemeral GitHub runner.
2. Preview with a short count-based summary: new, update, unchanged, blocked/conflicted.
3. Inspect private reports where detail is needed and confirm approved mutations.
4. Commit through restricted HF APIs with current-revision checks, bounded batches and stable IDs.
5. Verify catalogue/file consistency, check the reader independently, and retain private recovery evidence.

## Historical evidence and epistemic status

- [v0.1.0 release](releases/v0.1.0.md) records the first production hardening.
- [migration verification](POST_MIGRATION_VERIFICATION_2026-11-14.md) records an executed production change.
- [genre repair](GENRE_REPAIR.md) records the failure in older source metadata extraction.
- [output conventions](OUTPUT_CONVENTIONS.md) records the most recent UX/observability decision.
- [AGENTS historical archive](archive/AGENTS_PRE_2026-11-21.md) preserves older detailed engineering context, including sections that were accurate only at their stated date.

Do **not** extrapolate historical migration counts, repaired-title counts, CI test totals or successful GitHub Actions into claims about today's private dataset state. Read-only live inspections establish current evidence; they are not required for documentation-only changes.
