# Changelog

The Storage Controller uses semantic-style tags beginning with **v0.1.0**. This
is the first formal tag; previous development was merged to `master` without
versioned releases.

## Unreleased

- Consolidate project vision, original design decisions, current architecture and
  module ownership, incidents/lessons, operational deployment and realistic roadmap.
- Add a current zero-context AI agent playbook and short root AGENTS.md; archive the
  old comprehensive handbook for historical provenance instead of losing details.
- Add a dated project-state ledger and mandatory live Git/source/PR/issue inspection instructions for future agents; classify implemented, partial, planned, deprecated and historical capabilities.
- Align architecture and roadmap with the current batch uploader, local cover matching, remote-first backup and cloud import implementation; explicitly track open embedded-cover extraction and Hiatus/Dropped status issues.
- Mark old migration acceptance instructions as historical, clarify that repository deletion is forbidden while the local `data/` content reset remains guarded, and enforce `master`/repository/concurrency guards on all private HF workflows.

- Add private, revision-pinned, read-only inventory, cover audit, Retriever comparison, integrity verification and HTML health report.
- Add offline regression tests, bounded concurrent deep scanning and revision-keyed local cache; no HF write operations.

### Post-v0.1.0 engineering additions (November 2026)

- Add revision-guarded multi-novel upload batches, local duplicate/edition detection and optional matching of separately supplied local `covers/` images.
- Add manifest-validated standalone cover artifact imports with unique source/book identity matching, bounded commits and safe resume after partial success.
- Complete and verify the one-time 104-cover recovery; retire its temporary workflow after completion.
- Recognise rigorously verified EPUB-only chapter layouts in read-only inspection; distinguish optional source URLs from missing required title/author data.
- Add additive source-metadata discovery, researched JSON import, review-bound batch approvals and catalogue-only repairs with private pre-change backup.
- Add cloud-only import of completed Novel-Retriever export bundles after manifest and per-ZIP SHA-256 verification.
- Add remote-first private HF snapshots using remote cryptographic object identities, plus an explicit full-verified runner fallback and a read-only readiness check.
- Standardise concise Windows START / summary / END output and allowlisted count-only GitHub Actions summaries.
- Complete the protected readable-folder production migration (89/89) and retire its one-shot workflows; retain dual-format path compatibility.

**Still incomplete:** automatic extraction of embedded ZIP/EPUB cover art during normal bulk upload ([#54](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/54)) and canonical `Hiatus` / `Dropped` source publication statuses ([#46](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/46)).

## [v0.1.0] — 2026-11-11

**First verified Storage Controller milestone.**

### Included
- Incremental import of novel ZIPs into a **private** Hugging Face dataset.
- Safe EPUB, ZIP and catalogue equality checks; selective repairs and stable
  book IDs with personal metadata and restored source genres preserved.
- Resumable, rate-limit-aware cover batches and cover-path catalogue updates.
- Local read-only catalogue utilities, backup-first reset, and manual private
  GitHub Actions for inspection, backups, reports and optional cover import.
- Validation for archive entry counts, expanded sizes, compression ratios,
  conflicting uploads, changed previews and concurrent remote revisions.
- Locked/tested dependencies and pinned GitHub Actions revisions.
- **87 offline tests** green on Windows and Linux with Python 3.11/3.12,
  including simulated end-to-end novel imports, EPUB repair, cover resume
  and read-only reset previews.

### Safety changes
- Removed the unsafe, backup-free dataset-clear GitHub Action and command.
- Full dataset reset remains local-only, interactive and verified-backup-first.
- Existing production Hugging Face data was **not modified during testing**.

### Known limitations
- Live Hugging Face API write integration was not part of the automated tests.
- Single-novel deletion, single-novel restore and full integrity verification
  remain future functionality.
- Historical genre restoration is an independent workflow and its missing
  external token configuration is **not** addressed in this release.
- Browser uploader limits and reader display of `coverPath` are governed by
  the separate Personal Library project.

Detailed [release notes](docs/releases/v0.1.0.md).
