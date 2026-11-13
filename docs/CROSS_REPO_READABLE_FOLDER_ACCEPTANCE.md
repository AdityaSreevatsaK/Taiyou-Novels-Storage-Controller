# Cross-repository readable-folder acceptance: pre-created private dataset

This is an opt-in integration test for Storage Controller readable-folder support
and Taiyou's Personal Library Reader PR #4. Production data is **never accessed**.

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

## Running acceptance

The workflow `.github/workflows/readable-folder-acceptance.yml`
executes two jobs on the `test/readable-folder-cross-repo-20261113`
branch and can be rerun via Actions.

1. **Contract verification**, without credentials: Storage Controller Python
   tests and Reader TypeScript and dual-format gateway tests at pinned
   Reader commit `1edff33d`. Existing CI also runs Windows/Linux with
   Python 3.11 and 3.12.
2. **Real Hub acceptance**: Require the dedicated test token. Refuse to
   continue if the dataset is absent, public or already contains files other
   than optional `README.md` and `.gitattributes`. No existing files
   will be overwritten.

The second job uploads only fictional materials to the existing private
dataset and then verifies:

- ID-only and readable folder formats coexist with unchanged 24-character IDs.
- EPUB, original ZIP, cover PNG, auxiliary file and catalogue bytes are
  accessible and match their expected SHA-256 hashes.
- One revision-bound, atomic migration copies and removes only the ID-only
  book's files and updates `data/library.json` without altering any
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

Reader PR #4 and the Storage Controller compatibility integration must be
reviewed before a separate, verified-backup production migration is considered.
