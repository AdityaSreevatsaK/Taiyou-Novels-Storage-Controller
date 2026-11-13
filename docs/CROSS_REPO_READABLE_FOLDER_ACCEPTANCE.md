# Cross-repository disposable Hugging Face folder acceptance

This is a separately gated integration test for:

- `Taiyou-Novels-Storage-Controller` feature branch `feature/readable-hf-folder-compatibility`
- `Taiyous-Personal-Library` draft PR #4, commit `1edff33d`

The test **never connects to the production `AdityaSreevatsaK/Taiyous-Novels` dataset**. It uses only synthetic EPUBs, archives, images and reading data.

## How to review

[Readable Folder Cross-Repo Acceptance workflow](../.github/workflows/readable-folder-acceptance.yml) runs automatically on changes to the `test/readable-folder-cross-repo-20261113` branch. It has two steps:

1. **Cross-repository contract:** Windows/Linux-compatible Storage Controller unit tests on Python 3.11; pinned Reader PR #4 TypeScript checks and its three dual-format regression files. GitHub's normal Storage Controller PR CI independently checks Windows/Linux and Python 3.11/3.12.
2. **Real Hub integration:** requires repository Actions secret `HF_DISPOSABLE_TEST_TOKEN`, from a *dedicated test account or narrowly scoped token* with permission to create/delete its own private datasets. It creates `<test-account>/taiyou-disposable-readable-e2e-<random>` as **Private**, then seeds one ID-only and one already-readable fictional book.

The live test validates:

- The original EPUB is structurally valid, the ZIP contains that EPUB, and covers and extra files are byte-identical.
- The pre-migration catalogue contains both folder formats with the correct immutable IDs.
- A revision-bound, single-commit file copy, old-file deletion and `data/library.json` path update.
- Preservation of SHA-256 contents of every EPUB, ZIP, cover, extra file, reading-progress sidecar, personal-review sidecar and collections file.
- No ID changes or mutation of an already-readable book; a book title may differ from the folder's label.
- Old ID-only files are absent after migration, while the new paths are present.
- A stale-parent write is rejected and cannot overwrite progress.
- Any attempt to run the production migration helper against the real production repo is rejected.
- The disposable test dataset is deleted in `finally` after the run. On cleanup failure, CI reports failure and a human should remove **only** the named test dataset.

## Required secret

Set `HF_DISPOSABLE_TEST_TOKEN` in **this Storage Controller repository's GitHub Actions secrets**. Do **not** use `HF_STORAGE_CONTROLLER_TOKEN` or a token restricted to the production novel dataset.

When the secret is absent, the live job fails explicitly as **BLOCKED: real Hugging Face test NOT executed**, rather than reporting an incorrect success. The cross-repository static job can pass without a token.

**The real test does not exercise the production-only Cloudflare OAuth gateway.** The Reader tests mock the authenticated gateway, but a true end-to-end OAuth-on-disposable-dataset test would require a dedicated protected Cloudflare staging gateway pointed only at an isolated test dataset.

Neither this workflow nor the migration script enables production folder migration. Reader PR #4 and the Storage Controller migration must be reviewed and deployed in the correct order before any separately approved production migration.
