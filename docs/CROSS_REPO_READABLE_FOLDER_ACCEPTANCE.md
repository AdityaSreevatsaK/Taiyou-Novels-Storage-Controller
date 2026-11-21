# Historical cross-repository readable-folder acceptance

> **Historical record only:** the synthetic acceptance completed on 13 November 2026. Its one-shot workflow (`readable-folder-acceptance.yml`), temporary branch and related readiness workflows were retired and are not present on current `master`. Do not try to dispatch, recreate or follow the old branch instructions below as a current procedure. This document preserves the test fixture contract and evidence for future engineers; any new live acceptance requires a fresh design and review.

This was an opt-in integration test for Storage Controller readable-folder support
and Taiyou's Personal Library Reader PR #4. Production data was **never accessed**.

## Pre-created dataset, no repository creation or deletion rights

Manually create **one empty, private Hugging Face dataset** named:

`AdityaSreevatsaK/Taiyou-Readable-Folder-Test`

Use Hugging Face > New > Dataset, choose the namespace `AdityaSreevatsaK`,
the exact name `Taiyou-Readable-Folder-Test`, and set **Private**.

Create a **fine-grained Hugging Face token** with read/write access to **this
one test dataset**. It must *not* grant access to `Taiyous-Novels` and does
*not* need permission to create or delete datasets.

Save the token in the GitHub repository **Taiyou-Novels-Storage-Controller**
under Settings > Secrets and variables > Actions > New repository secret:

`HF_DISPOSABLE_TEST_TOKEN`

The target `HF_DISPOSABLE_TEST_REPO` is hardcoded in GitHub Actions to
`AdityaSreevatsaK/Taiyou-Readable-Folder-Test`, and is also checked by
the Python runner before connecting to Hugging Face. No separate variable or
secret is required for the dataset name. Do not paste the secret in chat.

## What the historical acceptance workflow did

The retired workflow `.github/workflows/readable-folder-acceptance.yml` ran on the temporary branch `test/readable-folder-batch-acceptance-20261113`. It is **not** available from current `master` and cannot be rerun from this repository as documented here.

1. Historical contract verification ran Storage Controller Python tests and Reader TypeScript / dual-format gateway tests against a pinned Reader commit. Current controller CI independently runs Windows/Linux with Python 3.11 and 3.12.
2. Historical live Hub acceptance used the dedicated test-only token and refused to proceed if the pre-created private dataset was absent, public or contained unexpected files.

The historical second job uploaded only fictional materials to the existing private dataset and verified:

- ID-only and readable folder formats coexist with unchanged 24-character IDs.
- EPUB, original ZIP, cover PNG, auxiliary file and catalogue bytes are
  accessible and match their expected SHA-256 hashes.
- Two sequential revision-bound migration batches copy and remove three
  ID-only novels' files and updates `data/library.json` without altering any
  already-readable book.
- Cover, progress, review and collection metadata survive unchanged.
- A stale-parent update is refused.
- Explicit production migration prohibition still holds.
- **Cleanup deletes only the files created by this run**, using an exact,
  revision-bound list of paths. The private test dataset itself remains
  available for future integration tests.

### Failure and clean-up safeguards

The runner refuses writes if any data is present at the start. Its cleanup
refuses files outside the known synthetic fixture list or a changed/uncertain
commit revision. If the network disconnects during a commit, the script can
leave some synthetic data in the test dataset rather than guessing which files
are safe to remove. This is intentionally fail-closed: manually inspect and
clear **only the pre-created test dataset** before rerunning.

A failed workflow due to missing credentials or missing test dataset is an
**unexecuted acceptance gate**, not a passed migration. It cannot be
substituted with the production-scoped `HF_STORAGE_CONTROLLER_TOKEN`.

### Scope

The script **never** calls `create_repo` or `delete_repo`, never migrates
the production dataset, and never changes the Reader's production deployment.
The Reader's Cloudflare OAuth gateway remains separately gated: current
cross-repository tests mock the authenticated gateway rather than running
against a live disposable Cloudflare environment.

Reader PR #4 and the Storage Controller compatibility integration were historical preconditions for the migration. The production folder migration has since completed and was independently verified on 14 November 2026. This document does not authorise or recommend another production migration.


## Verified live acceptance, 13 November 2026

**PASS**: [Hugging Face integration run #43431262417](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/43431262417).

- The real private pre-created `AdityaSreevatsaK/Taiyou-Readable-Folder-Test` dataset was accessed with the dedicated repository-scoped secret.
- Synthetic legacy and readable EPUBs, archives, PNG covers, extra file, catalogue, personal reviews, reading progress and collections all passed SHA-256 comparisons.
- The actual Storage Controller performed a revision-bound folder copy/delete and catalogue update. Existing readable folders and immutable IDs were preserved.
- A stale-parent personal-data overwrite was rejected.
- The production migration guard refused the production dataset.
- **Cleanup succeeded:** the only synthetic files created by this acceptance run were removed; the pre-created private dataset remains.
- The cross-repository static validation job passed on the same workflow, and [CI #43431274374](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/43431274374) passed all four Windows/Linux × Python 3.11/3.12 jobs.

**Scope limitation:** This verifies the genuine Hugging Face migration transaction and Reader path/gateway contracts, but it is **not** a live Cloudflare Access/OAuth browser session against the disposable dataset. Reader deployment rollout and full production backup still require separate authorisation and verification before any production file migration.


## Consolidation onto current Storage Controller master

This historical workflow was based on the then-current `master` rather than the earlier PR #17 feature branch. It exercised `apply_migration_batch()` in consecutive commits with multiple legacy books while preserving already-readable books and personal sidecars. It validated the deployed Reader commit `45233f4` and reported success only after all synthetic files were removed. **At the time of this test**, production remained untouched pending a verified backup, authenticated gateway verification and separately authorised migration. The production folder migration subsequently completed on 14 November 2026; see [post-migration verification](POST_MIGRATION_VERIFICATION_2026-11-14.md).


## New production-style batch verification

The final consolidated acceptance run added two further synthetic legacy
books, while retaining an already-readable novel whose title no longer
matched its folder label. It verified:

- **Batch 1:** two legacy books moved in one atomic parent-guarded HF commit.
- **Batch 2:** a third legacy book moved in a second HF commit.
- Replanning after batch 1 reports finished books as already readable and the
  remaining legacy book as unmigrated.
- Every moved EPUB, ZIP, cover and auxiliary file matches its original SHA-256.
- Catalogue IDs, reading progress, personal tags, ratings, comments, reviews,
  and collection sidecars are preserved.
- Destination collision plans, repeated old batches, stale parent writes,
  and direct production-target use are blocked.
- Only owned synthetic paths are removed. The pre-created PRIVATE test dataset
  itself stays available and its original inventory is restored.

The historical Reader contract targeted deployed master SHA
`45233f4854b657d146965cf71a38142289411b18`. These are **real Hugging Face
dataset tests** and **mocked Reader gateway tests**. They do not establish
that a live OAuth-authenticated Cloudflare browser session can retrieve each
file type from the production reader; that remains a separate prerequisite.

The current production migration source and backup code remain protected by
an independent explicit confirmation; no production novel was moved in this
testing.
