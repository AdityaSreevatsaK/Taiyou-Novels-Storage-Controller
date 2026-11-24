# Project state snapshot

**Purpose:** a compact evidence-backed snapshot for agents and maintainers starting without prior conversation context.

> **This is a dated snapshot, not a live status API.** It was inspected against remote `master` at `a40c01173df425aa94c445e7e221fd61f8e7fb34` on **21 November 2026**. Before every substantial task, agents MUST refresh the live repository, Git and issue state as described in [AGENTS.md](../AGENTS.md) and [AI_AGENT_PLAYBOOK.md](AI_AGENT_PLAYBOOK.md). Never assume this file is still current.


## Dated follow-up: 23 November 2026 (proposed test-only acceptance)

After refreshing remote `master` at `d021faae16668fb8555df8c79293c2af2b75b1ba`
(no open PRs at the start of this follow-up, latest master CI and release
successful), a feature branch adds a **tenth**, guarded
`hf-disposable-backup-acceptance.yml` workflow and synthetic integration
harness. It consumes `HF_DISPOSABLE_TEST_TOKEN`, creates new isolated
private synthetic datasets, tests partial-copy recovery, identity validation,
idempotent rerun and independent SHA-256 read-back. The tests never use the
production source and do not delete the disposable datasets.

This is **proposed code and test infrastructure**, NOT live-HF acceptance
evidence. After merging, inspect the exact Actions run's conclusion, job
steps and allowlisted numeric summary, then update the evidence record.
If the token is unavailable, scoped to an environment, or lacks private
dataset creation permission, report the test as **blocked**, not passed.
All previous historical baseline observations below remain dated evidence,
not statements of the latest live GitHub state.

## Dated backup safety change: 24 November 2026 (proposed until merged)

The latest baseline checked for this work was `master`
`9cfb59b3cbb42f8a2cb993948952dee12698d1c0`. A targeted
safety change makes the remote-first backup and its read-only readiness
scan reject source LFS objects lacking an Xet hash **before** any
destination commit. Pinned `huggingface_hub==1.33.0` requires this hash
for cross-repository LFS duplication, even if a SHA-256 is available for
remote identity verification. The existing explicit `full-verified`
mode remains available. No production data changes are part of this
code change. This statement is proposed implementation, not evidence
that the live synthetic acceptance completed successfully.

## 24 November 2026: proposed full-verified disposable test

After the fail-fast remote-copy safety change merged on `master` at
`479eaed89e085e1fc5745db1a211a64363cd1177`, a separate test-only
workflow has been proposed for the already implemented explicit
`full-verified` backup path. It uses only `HF_DISPOSABLE_TEST_TOKEN` and
separate private synthetic datasets; it does not write to production. An
independent byte-and-manifest verification stage is included. **A planned
or CI-passing test is not a successful live acceptance test.** Confirm
the exact post-merge Actions run and its numeric verification metrics.

## Confirmed live synthetic HF backup acceptance: 24 November 2026

Fresh `master` at
`e5efbf20dc63de60874ee1457c040b380aafeeca` contains the
fail-fast remote-copy safeguard and separate full-verified synthetic
acceptance workflow. Master CI run
[#45436985001](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/45436985001)
and the code release workflow
[#45437129077](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/45437129077)
both concluded `success`. There were no production dataset mutations.

**Live synthetic results:**
- Remote-first test
  [#45435388468](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/45435388468)
  failed with two LFS files lacking Xet and the exact expected pinned-Hub
  cross-repository duplication error. Do **not** certify remote-first for
  this object class.
- Remote-first and read-only readiness now reject such LFS files before
  copying, delivered in
  [PR #67](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/pull/67)
  at `479eaed89e085e1fc5745db1a211a64363cd1177`.
- Explicit full-verified test
  [#45436984800](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/45436984800)
  concluded **success**, with 6 source objects, 1 verified private snapshot,
  1 completed independent per-object byte/SHA-256 and manifest recovery check.
  The source revision was unchanged. This proves synthetic live acceptance,
  not that a production backup exists or a production restore was exercised.

The disposable datasets remain private, retained for inspection, and are
not automatically deleted. Future agents must refresh GitHub and Hugging Face
evidence rather than treating these dated results as current production state.

## Repository baseline

| Item | Verified state at baseline |
| --- | --- |
| Repository | `AdityaSreevatsaK/Taiyou-Novels-Storage-Controller` |
| Visibility / default branch | Public / `master` |
| Baseline commit | [`a40c011`](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/commit/a40c01173df425aa94c445e7e221fd61f8e7fb34) |
| Code version at baseline | `0.1.0` (`VERSION`; first formal release tag `v0.1.0`) |
| Remote branches | `master` only |
| Open pull requests | None at audit start |
| Open tracked issues | [#46 publication-status taxonomy](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/46), [#54 embedded cover extraction](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/54) |
| Local working tree | Not available to this remote GitHub audit. Its cleanliness must not be inferred; inspect `git status` in any local checkout. |
| Private Hugging Face production data | **Not inspected or changed during this documentation review.** |

The repository tree contains one root `AGENTS.md` and no nested agent instruction files at this baseline. Agents must search again because nested instructions may be added later.

## Recent implementation history

The most recent relevant merged changes, in reverse chronological order:

| PR / commit | Delivered change | Current interpretation |
| --- | --- | --- |
| [#59](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/pull/59) | Consistent concise Windows command and GitHub Actions output | Implemented; retain the START / counts / END contract |
| [#58](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/pull/58) | Read-only live remote-backup readiness check | Implemented; readiness is not a completed backup |
| [#57](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/pull/57) | Cloud-only import of completed Novel-Retriever bundles | Implemented; requires a completed, manifest-verified export |
| [#56](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/pull/56) | Remote-first private snapshots with cryptographic object identity; explicit full-verified fallback | Implemented; region/copy limitations remain |
| [#55](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/pull/55) | Multi-novel atomic upload batches and discovery of matching local covers | Implemented for supplied local `covers/` files, **not** embedded ZIP/EPUB cover extraction |
| [#53](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/pull/53) | Retired the completed one-time 104-cover repair workflow | Historical workflow is not runnable |
| [#52](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/pull/52) | Recovered and verified 104 missing covers | One-time production repair completed; reusable cover importer remains |
| [#50](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/pull/50) | Recognised rigorously verified EPUB-only chapters during inspection | Implemented; strict evidence requirements remain |
| [#49](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/pull/49) | Distinguished optional source URLs from missing title/author metadata | Implemented; do not flag a valid book solely for having no source URL |

Earlier milestone: the readable-folder migration completed on 14 November 2026 (89/89 folders, zero conflicts, independent read-only verification); its one-shot production Actions were retired. See [the historical verification record](POST_MIGRATION_VERIFICATION_2026-11-14.md).

## Capability ledger

| Capability | State | Evidence / boundary |
| --- | --- | --- |
| Private HF novel catalogue and immutable 24-hex book IDs | **Implemented** | `core.py`, `paths.py`, upload and path tests; catalogue schema v1 |
| Legacy and readable novel folders | **Implemented** | `paths.py`, migration tests; both path forms remain supported |
| Local ZIP validation, smart reconciliation, duplicate/edition checks and revision-guarded upload | **Implemented** | `upload.py`, `local_dedupe.py`, tests; multi-batch writes are atomic per commit, not globally |
| Multi-novel batch upload (default 10) and automatic matching of local sidecar covers | **Implemented, bounded** | `bulk_batch.py`, `upload.py`; matches local `covers/` assets only |
| Extract a genuine embedded cover from each novel ZIP/EPUB and publish `coverPath` in the same bulk upload | **Not implemented; open issue #54** | Separate cover import exists, but does not satisfy the embedded-cover recurrence-prevention requirement |
| Manifest-based standalone cover import, explicit-ID cross-source matching and guarded cover batches | **Implemented** | `covers.py`, `cover_batches.py`, cover tests and `hf-upload-covers-artifact.yml` |
| One-time recovery of 104 standalone covers | **Completed historical operation** | PR #52 verified 104/104; temporary workflow retired by PR #53 |
| Quick / manifest / deep read-only inspection, chapter and cover evidence, health reports | **Implemented** | `inspection.py`, `inspection_cli.py`, `inspection_manifest.py`, `inspection_cache.py`; each mode provides a different evidence level |
| Local inspection-cache cleanup | **Implemented, local-only** | `inspection_cleanup.py`, `17_cleanup_inspection_downloads.cmd`; never deletes HF cloud objects |
| Source metadata audit, researched JSON import, review, preview and catalogue-only repair | **Implemented, constrained** | `metadata_repair.py`, `metadata_batch.py`; only missing allowlisted fields, identity/revision bound |
| Canonical `Hiatus` / `Dropped` publication statuses and aliases | **Not implemented; open issue #46** | Current validator/parser support `Completed` and `Ongoing` only; source publication state is separate from reading progress |
| Historical genre/source-field repair from old Retriever artifacts | **Implemented, specialised** | `genre_repair.py`, `hf-restore-genres.yml`; artifact retention and source evidence limit recovery |
| Completed Novel-Retriever cloud import | **Implemented** | `cloud_import.py`, `hf-cloud-import.yml`; SHA-256 manifest verification, preview-first, explicit apply |
| Remote-first and full-verified private backup | **Implemented** | `remote_backup.py`, `actions.py`, `hf-private-backup.yml`; read-only readiness does not prove a future copy will succeed |
| Read-only readiness and count-only private reports | **Implemented** | `cloud_readiness.py`, `hf-live-readiness.yml`, `hf-private-reports.yml` |
| Full clear of the HF repository itself | **Removed / forbidden** | Repository deletion is not a supported feature. The remaining guarded local reset clears only the `data/` content tree after a verified local backup and typed confirmations |
| Full `data/` content reset | **Implemented, highly destructive and local-only** | `reset.py`, `11_clear_hf_data.cmd`; no GitHub Action |
| Single-novel restore and delete commands | **Not implemented** | `08_restore_novel.cmd` and `09_delete_novel.cmd` are explicit placeholders |
| Automatic full restore | **Not implemented** | A private snapshot/receipt is not a restore implementation |
| Concise, privacy-filtered command and Action summaries | **Implemented** | `console_summary.py`, `github_output.py`, `console_output.bat`, output tests |

## Active GitHub Actions at baseline

The repository tree and workflow inventory test confirm these nine active YAML files:

- `ci.yml`: Windows/Ubuntu × Python 3.11/3.12 offline tests, dependency validation and vulnerability audit.
- `hf-inspect.yml`: read-only private library inspection.
- `hf-live-readiness.yml`: read-only remote backup readiness.
- `hf-private-backup.yml`: private remote-first or full-verified snapshot.
- `hf-private-reports.yml`: private inventory/conflict report export.
- `hf-cloud-import.yml`: completed Novel-Retriever export import.
- `hf-upload-covers-artifact.yml`: cover artifact preview and optional apply.
- `hf-restore-genres.yml`: historical source-field recovery.
- `release.yml`: code-only version/tag/release after green master CI.

Retired migration, one-time backup verification, one-time cover recovery and branch-pruning workflows are not active. Confirm actual files in `.github/workflows/` before dispatching anything.

**Branch-gate finding:** at the audit baseline, `hf-private-reports.yml`, `hf-restore-genres.yml` and `hf-upload-covers-artifact.yml` did not explicitly restrict their jobs to the repository's `master` ref or disable persisted checkout credentials. They already used the common HF workflow concurrency group. This documentation refresh adds the missing branch guard, disables persisted checkout credentials and adds regression tests. Verify the merged files before relying on this intended correction.

## Outstanding work and limitations

1. [Issue #54](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/54): extract and validate authentic cover art from ZIP/OPF-declared EPUBs during bulk upload, and update `coverPath` in the same guarded transaction. Local sidecar matching is only a partial solution.
2. [Issue #46](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/46): support verified `Hiatus` and `Dropped` source publication statuses across parser, validator, CLI and tests. Do not infer these values or modify any real book based on the issue text.
3. Verify the actual server-side HF copy path for the relevant storage regions/object types before relying on remote-first backups; readiness is metadata-only.
4. A live authenticated browser acceptance across multiple migrated books, cover display, ZIP download, offline cache and progress on multiple devices was not part of the 14 November migration audit. This belongs to the separate Reader project.
5. No automatic full restore or per-book restore/delete is available.
6. The Actions concurrency group cannot serialize local scripts, Reader writes or other repositories.

## Operator-reported local cache cleanup

The owner reported a completed local cleanup of **700 owned inspection-cache files** and **208 legacy shared-cache entries**, with zero matching entries remaining and no Hugging Face cloud deletion. The approximate reclaim estimate is not guaranteed physical disk recovery because shared cache objects may have other references. Treat this as an operator-reported historical result, not a live cache count.

## Evidence and safety boundary

This snapshot was built from the public repository tree, current source/tests, recent Git history, PRs and open issues. It did **not** inspect private HF contents, read local disk state or perform any production operation. The current source and tests must be re-read before any implementation decision.
