# Isolated Hugging Face remote-backup acceptance

This check exercises the existing Controller `remote_backup()` against synthetic
EPUB, ZIP, PNG and v1 catalogue data. It never accesses production Hugging Face
datasets. Its Python module is `taiyou_storage/disposable_backup_acceptance.py`.

## Execution

- Workflow: [HF - Disposable remote backup acceptance](../.github/workflows/hf-disposable-backup-acceptance.yml).
- Runs once automatically when that workflow is added/changed on `master`,
  or on an explicit `workflow_dispatch` from trusted `master`.
- Requires `HF_DISPOSABLE_TEST_TOKEN` as a **repository-level GitHub Actions
  secret** (not `HF_STORAGE_CONTROLLER_TOKEN`). If unavailable, it fails before
  contacting Hugging Face.
- The test credential must be permitted to create two private datasets and
  upload/copy synthetic test files. It must not be used for production.
- Creates private repositories with run-specific identifiers:
  `AdityaSreevatsaK/Taiyou-Backup-Acceptance-Source-<run>-A<attempt>`
  and `AdityaSreevatsaK/Taiyou-Backup-Acceptance-Destination-<run>-A<attempt>`.
  These names are generated from the trusted GitHub run context, never from inputs.
  Existing repositories are never overwritten.
- **Does not delete its private test datasets**. They remain available for
  independent inspection and may require later manual disposal.

## What the test proves

1. Both datasets are newly created private datasets with immutable revisions.
2. A synthetic library entry and representative EPUB, ZIP and cover are uploaded
   only into the disposable source.
3. Remote-first preflight uses remote object identities, not matching sizes.
4. A single copied file is staged to simulate a partial successful batch.
5. The actual Controller backup code resumes it without recopying the staged file.
6. A private completion receipt is written only after identity verification.
7. A full immediate rerun copies zero objects and makes zero new commits.
8. Pinned read-backs of the synthetic catalogue, EPUB, ZIP, PNG and marker from
   both datasets match independent SHA-256 digests.

The GitHub job prints only fixed allowlisted numeric counts via
`taiyou_storage.github_output`. It never uploads reports/artifacts or prints
private file paths, token values or Hugging Face exception details. It verifies
the repository and master branch context before using credentials.

## Limitations

This is *live synthetic test dataset* evidence, not proof a production
backup exists or that the region/object backends match production. A run can
fail because the token is missing at repository scope, lacks permissions,
the HF API refuses cross-repository server-side copy, or remote identities
are unavailable. Production remains unchanged in all cases.

The test temporarily replaces the Controller's hardcoded production source
name **only inside its acceptance subprocess** and passes the synthetic source
explicitly into `remote_backup()`. Normal CLI/Actions remain production-gated.
