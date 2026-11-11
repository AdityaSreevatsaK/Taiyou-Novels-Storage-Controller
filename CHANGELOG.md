# Changelog

The Storage Controller uses semantic-style tags beginning with **v0.1.0**. This
is the first formal tag; previous development was merged to `master` without
versioned releases.

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
