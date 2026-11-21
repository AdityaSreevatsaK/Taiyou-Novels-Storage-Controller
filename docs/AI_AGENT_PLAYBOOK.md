# AI agent implementation and maintenance playbook

**Audience:** any AI or human engineer beginning from a new session with only this public repository. **Updated:** 21 November 2026.

## Zero-context orientation (first five minutes)

1. **Confirm target:** `AdityaSreevatsaK/Taiyou-Novels-Storage-Controller`, default branch `master`. This is a *public code repository* controlling a separate *private novel HF dataset*. Do not infer current HF contents from docs.
2. **Read in order:** root [AGENTS.md](../AGENTS.md), [Vision and history](PROJECT_VISION_AND_HISTORY.md), [Architecture](ARCHITECTURE.md), this playbook, and [Incidents](FAILURES_AND_LESSONS.md).
3. **Read task-specific guides:** [User commands](USER_GUIDE.md), [Upload](SMART_UPLOAD.md), [Inspection](LIBRARY_INSPECTION.md), [Metadata](METADATA_REPAIR.md), [Safety](SAFETY_AND_RECOVERY.md), [Actions](GITHUB_ACTIONS.md), [Operations](OPERATIONS_AND_DEPLOYMENT.md), [Output](OUTPUT_CONVENTIONS.md), [Roadmap](ROADMAP.md).
4. **Inspect source and tests:** current `taiyou_storage/*.py` modules, call sites, relevant `tests/*.py`, corresponding numbered `.cmd` launcher and `.github/workflows/*.yml`, if applicable.
5. **Inspect the live Git state:** existing PRs, open branches, exact `master` commit SHA and CI status before making or merging a change. Read the latest user instruction and preserve all unspecified constraints.
6. **Read the [dated project-state ledger](PROJECT_STATE.md) only as a starting snapshot.** Re-verify every relevant entry against current files, Git refs, PRs, issues and tests.

**Authority order:** current explicit owner request > verified current code, tests and deployed cross-repo contracts > current operational guides > dated incidents/older handbook. A historical note alone never grants approval to run production operations.

## Mandatory live-state refresh before substantial work

Perform this sequence **at the start of every substantial task**, even if the previous agent claims it already did so. Repeat it before review/merge if the branch or base may have moved.

1. **Instructions:** locate every applicable `AGENTS.md`, including nested files under the target directory. The root instructions are not proof that no more-specific instructions exist.
2. **Local Git state:** in an available checkout, inspect `git status --short --branch`, `git branch --show-current`, `git rev-parse HEAD`, `git remote -v`, `git log -20 --date=short --pretty=format:"%h %ad %d %s"`, `git diff --stat`, `git diff` and `git diff --cached --stat`. Preserve unexplained uncommitted changes. Compare local HEAD with the current remote default branch. If no checkout exists, explicitly record that local working-tree state is unavailable and use remote GitHub refs/commits instead.
3. **Remote collaboration state:** verify repository default branch and HEAD SHA; inspect current branches, latest commits and changed files, open PRs, review threads, exact CI conclusions, open issues and relevant recent merged PRs. Do not assume old PRs, branches, Actions or issue statuses are current.
4. **Implementation reality:** inspect the exact source modules, imports/call sites, tests, dependency/config files, CMD entry points and active workflow YAML affected by the task. For cross-repository work, inspect the current producer and consumer contracts rather than copying a historical field list.
5. **Classify each relevant feature with evidence:**
   - **Implemented:** source path and relevant tests exist. State separately whether live integration acceptance exists.
   - **Partially implemented:** code covers some use cases, but a format, integration, acceptance or safety requirement remains open.
   - **Planned:** issue/roadmap only; do not describe as available.
   - **Deprecated/retired:** removed, disabled or replaced; do not dispatch or resurrect it without a new explicit decision.
   - **Historical:** a completed one-time migration/repair or dated test result, not a reusable operation.
6. **Reconcile contradictions:** user instructions define intent; current implementation/tests and deployed interfaces establish what actually runs. Prior conversations, AI summaries, archived handbooks and old PR bodies explain why, but are not proof of current implementation. Resolve doc/code contradictions deliberately.
7. **Maintain the ledger:** update [PROJECT_STATE.md](PROJECT_STATE.md) when the capability state, active workflows, issue list, repository layout or verification evidence changes. Record the exact baseline SHA and date. It remains a dated snapshot and must never replace the live-state refresh.
8. **Before merge:** re-check status/diff, changed files, base/head SHAs, reviews and every required job on the exact PR head. A queued job, green earlier commit, synthetic test, preview or successful merge is not a production write.

A useful current-state review is not a recitation of docs. It must answer: **what exists now, what is only partly done, what remains a proposal, what was retired, and what evidence supports each statement?**

## Scope and permission gates

| Action | Permitted baseline | Extra gate |
| --- | --- | --- |
| Read public repo, update docs or source in feature branch, run offline tests | Normal engineering work | Review exact current files and preserve compatibility |
| Run local read-only checks on private HF | Requires appropriate dataset read token and user-authorised access | Never publish private results |
| Run synthetic real-HF acceptance | Only pre-created private disposable test repo, dedicated **test-only** token, synthetic input, strict cleanup | Explicitly distinguish the test repo from production |
| Write to production HF | **Not a normal test** | Separate explicit user-authorised operation and normal preview/revision/backup guards |
| Delete/reset production content | **Never** from GitHub Actions | Only safeguarded local operation with verified complete backup and typed confirmations |
| Access Reader or Novel-Retriever repository | Separate repo task | Preserve boundaries, do not assume this repo grants change authority |
| Merge a completed PR | Only after requested changes, exact PR-head verification and green relevant CI | Do not hide test failures or changed target branch |

User authority to improve **code** or documentation is not blanket authority to apply new changes to **private production data**.

## Standard development loop

### Investigate

- State the observable problem and affected layer (CMD, Python planner, HF API, Reader, Retriever export, Actions wrapper).
- Identify **current** source, paths, data ownership and candidate regressions. Avoid treating a historic bug as active without evidence.
- Model negative states: bad ZIP/EPUB, duplicate source URL, renamed book, title mismatch with readable folder, orphaned data, corrupt/missing cover, stale parent revision, incomplete batch, private/public confusion, lost token, 429/quota and uncertain network outcome.
- Determine whether a change affects the catalogue, immutable IDs, sidecars, reader-owned fields or a separate repository. Do not patch the wrong layer.

### Plan

- Prefer a small, reviewable change on a **new feature branch**, grounded at the latest master SHA.
- Record invariants and the exact planned tests before modifying business logic.
- Keep source and personal metadata distinct; treat unknown fields as reader-owned unless verified otherwise.
- Do not replace checked APIs with global locks or unverified assumptions about serialised cloud executions.
- For a migration or destructive change, require private backup, explicit authorisation, rehearsal on a disposable dataset and independent verification. A docs-only task does **not** require production access.

### Implement

- Put validated business rules in Python, not duplicated across CMD launchers and YAML.
- Support existing legacy and readable folders using `paths.py` and the catalogue's **stored** paths, never regenerated display titles.
- Retain preview-by-default behaviour, unique identity checks, bounded commits, parent revisions and idempotent resume.
- Ensure `00`-`18` launchers keep established numbering, working-directory handling, quoted paths containing spaces, exit codes and double-click pause semantics.
- Keep public action logs restricted by `github_output.py` and fixed numeric allowlists. Provide START, numeric summary, clear END and a private report path when applicable; no per-book public dumps or fake success labels.
- For optional public metadata evidence, fetch *only* authorised exact HTTPS information pages, with existing allowlist/no redirects/no cookies/no chapter policy. Missing evidence should remain missing.

### Test

Run offline checks from repository root:

```powershell
py -m pip install -r requirements.txt
py -m pip check
py -m compileall -q taiyou_storage tests
py -m unittest discover -s tests -q
```

- Add focused tests that fail on the old behaviour and pass with the fix, including error/partial-success paths.
- Check on **Windows and Ubuntu**, Python **3.11 and 3.12**, through PR CI.
- Do not use production HF tokens to make CI pass. CI must be synthetic and credential-free.
- When a real HF API semantic must be verified, use *only* a pre-created private disposable dataset with `HF_DISPOSABLE_TEST_TOKEN` scoped to that dataset; do not create/delete repositories or touch production.
- Clearly report **not run**, **mock-only**, **live synthetic**, **preview only**, **merged** and **production-applied** separately.
- Validate the **exact** PR commit whose tests finished; a green older commit or queued run is not a pass.

### Review and merge

- Inspect the final diff for secrets, private book names, personally linked records, EPUB/ZIP content and unrelated edits.
- Check repository instructions on branch/PR style. Write PR description in **Markdown only**.
- Summarise impact, changed contracts, privacy constraints, tests, unverified live acceptance and rollback/resumption conditions.
- Confirm the base branch has not moved unexpectedly and any required workflow jobs are green before merging. Recheck changed files and final merged SHA.
- Do not claim deployment to Cloudflare or mutation of Hugging Face after merging a controller code-only PR.
- Update touched documentation and release information; only change `VERSION` when a release is explicitly intended.

## Change-specific checklists

### Upload/ZIP/catalogue

- Strict ZIP budget and CRC, EPUB parsing, source metadata and duplicate checks.
- Compare ZIP, extracted EPUB, catalogue fields and remote path/object existence before `UNCHANGED`.
- Preserve existing book ID, personal fields and non-empty verified source metadata.
- Check ambiguous title/source identity and changed local bytes after preview.
- Single-commit atomicity vs multi-batch partial success documented accurately.

### Covers

- Validate image integrity, manifest, extension and path containment.
- Unique existing novel match; cover importer never creates a new novel.
- Verify link and bytes; bounded commit group and retry only when safe.
- Test changed catalogue revision, quotas, partial completion, and Windows file paths with spaces.

### Inspect/cleanup

- Read-only pinned revision; quick/manifest/deep evidence correctly labelled.
- Private reports and cache never committed or publicly uploaded.
- If cleanup, show preview and typed consent; separate owned files, legacy HF cache **entries** and uncertain freed bytes.
- Ensure no local cleanup code calls HF remote delete.

### Metadata research and repair

- Audit per missing field and verify exact canonical source identity and author/title.
- Never invent genres, description or status. Review imported research individually as appropriate.
- Candidate approval bound to hash and current revision, private pre-change backup and catalogue-only guarded commit.
- Keep all app-owned fields, existing source fields and binaries intact.

### GitHub Actions

- Check workflow **actually exists** in `.github/workflows/`; historical migration files may be retired.
- For every HF workflow that can read/write private data, verify the exact repository and `refs/heads/master` job gate, least-privilege permissions, shared concurrency policy and secret scope. A `workflow_dispatch` trigger alone does not pin execution to master.
- Pin Actions dependencies, default to least privileges, scope secrets to applicable steps.
- Use `github_output.py` around noninteractive private operations with fixed task name/metric allowlist. Do not echo original command output or raw exception text.
- Distinguish verified **preview** from **apply**; do not publish sensitive GitHub artifacts.
- Remote backups require a separate private destination and cryptographic identity checks, not identical sizes only.

### Reader/Downloader integration

- Verify both ends of the catalogue path and artifact manifest contract using their latest source.
- Do not assume a Reader UI failure means a storage write failed.
- No implicit cross-repository deployment, scraping, app routing or OAuth changes from this repository.

## Session handover template

For tasks that require continuity across AI agent sessions, leave a **concise, verifiable** record in the issue/PR or repository doc where appropriate. Never commit private raw reports.

```text
Repository / base branch / exact SHA:
Goal and original user constraints:
Affected modules and cross-repository contracts:
Completed code and documentation changes:
Tests and exact CI URLs / job conclusions:
Remote HF access performed? none / read-only / synthetic-test / authorised production:
Known unresolved bugs, blockers and assumptions:
Remaining verification or deployment steps:
Rollback or safe retry instructions:
PR URL and merge state:
```

A handover is inaccurate if it reports intended actions as completed. Link evidence rather than copying confidential logs into the handover.

## Useful references

- [Dated project-state snapshot](PROJECT_STATE.md): last verified Git baseline, active workflow inventory, implemented/partial/planned/retired capability ledger and open tracked issues. Refresh it against live GitHub state before relying on it.

- [Historical detailed agent handbook](archive/AGENTS_PRE_2026-11-21.md) preserves the long pre-restructure engineering narrative. It contains **obsolete** descriptions of legacy paths, placeholder inspection and retired workflow names. Use only for history.
- [Failure register](FAILURES_AND_LESSONS.md) lists what went wrong and the guardrails now expected.
- [Operations guide](OPERATIONS_AND_DEPLOYMENT.md) covers local setup, GitHub Actions and authentication boundaries.
- [Project roadmap](ROADMAP.md) separates delivered functionality from potential future work.
