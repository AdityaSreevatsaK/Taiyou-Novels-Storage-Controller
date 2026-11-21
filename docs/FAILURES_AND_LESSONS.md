# Failure register, root causes and lessons learnt

**Reviewed:** 21 November 2026. Historical incidents are not necessarily open defects. This is a learning and regression guide, not a claim that the live dataset currently has the named failures. Evidence ranges from committed fixes and CI tests to operator-reported symptoms; do not conflate them.

## Incidents and the regression rules they created

| Incident / historical symptom | Cause or risk | Remedy and permanent rule | Verification boundary |
| --- | --- | --- | --- |
| A novel reported `UNCHANGED` while its EPUB or other associated remote data was missing/different | Earlier equality logic considered too little of the package | Compare independently the original ZIP, extracted EPUB, catalogue metadata and declared remote references before skipping; add artifact-drift tests | The underlying test suite is synthetic; live HF states may still fail differently |
| Uploads treated a missing catalogue as an empty library | Existing remote `data/` files could be orphaned or overwritten | Permit initialisation only for a genuinely empty dataset. Reject malformed, inaccessible and partially populated remote state | Use fake remote listings to test mixed file sets |
| Updated imports dropped personal reading state or source genres | Merging new source metadata could overwrite reader-owned keys or blank missing `sourceTags` | Keep stable ID and old personal metadata; add missing source fields only with evidence; test ratings, progress, notes, comments, tags, collections and completion state | App rendering must be checked separately |
| Large cover imports hit 429 quotas or an interrupted batch | Too many tiny remote commits; uncertainty after partial success | Bounded grouped cover commits with revision guards; tolerate short known retries; stop and re-preview/resume when quota or commit outcome is uncertain | Test injected 409/412/429 and network faults |
| Double-click upload preview and subsequent apply disagreed | Dataset or local ZIP changed between planning and write | One-process interactive preview/confirmation; recheck the exact local content hash and HF parent revision | Human confirmation alone never replaces freshness checks |
| ZIP files accepted damaged EPUBs or potentially dangerous expansions | CRC alone cannot prove EPUB usability or safely constrain decompression | Validate ZIP member count/expanded sizes, EPUB structure, accepted paths and image decoding; guard against archive bombs/traversal | Maintain hostile synthetic archive cases |
| Cover import encountered path/manifest/quote or ambiguous title matching problems | Windows whitespace quoting, nested archive assumptions or title-only identity were unreliable | Preserve quoting/working directory; accept only verified package formats; bind cover to a unique existing book ID/source identity; refuse guesses | Do not infer that an uploaded image must appear in the reader |
| Missing genres/synopsis/status after historical Retriever assembly | Intermediate packages lost EPUB `dc:subject` or other provenance | Research source fields conservatively, back up catalogue, make additive-only identity-checked repair; avoid overwriting known values | Historical artifacts may expire; missing source evidence cannot be fabricated |
| Opaque numeric HF directories were hard to browse | ID-only storage paths lacked human-friendly labels | Human-readable suffixes with immutable ID, backwards-compatible `paths.py`, catalogue paths as authority and no automatic rename on title change | 14 Nov migration 89/89 and separate read-only audit recorded |
| Potentially destructive repository deletion / full data clear exposed through Actions | An accidental repository deletion and backup-free cloud clearing could destroy the entire library | Remove repository deletion entirely and retire public reset Actions; retain only local `data/` content clearing with a complete verified backup, fresh revision checks and multiple typed confirmations | Repository deletion is forbidden; local content reset is not a repository delete |
| Existing reader/controller write paths could race | One shared catalogue, multiple distinct write clients, no shared distributed lock | Revision-pinned reads plus `parent_commit`; reject unexpected writes and replan. Do not force the old plan | A GH workflow concurrency group is not a global mutex |
| Remote backup used heavy downloads or lacked proof of copy | Laptop/runner limits and weak copy-equality assumptions | Default to remote-first copy with **cryptographic identity and size**, private receipt and explicit full-verified fallback. No same-size-only certification | Readiness does not prove a server-side copy will work across storage regions |
| A cover/EPUB audit downloaded excessive data to Windows HF shared cache | Deep binary inspection and shared cache residency created disk pressure | Default to quick/manifest, isolate inspection cache under `reports/.inspection-download-cache`, require preview/typed local-only cleanup | Owned files and legacy shared-cache entries are different counts; recovered disk bytes may differ from estimates |
| Command and GitHub logs were extremely verbose | Raw per-book output obscured status and could expose private details | Fixed START/summary/END, count-only public Actions, private detailed reports, actionable failures and no fake success | Changes merged in PR #59, 21 November 2026 |
| A test passed, but the real HF operation still failed | Fake clients, HF Xet transport and region/revision semantics differ from mocked environments | Add real disposable **private** dataset tests when needed; keep tests synthetic by default; explicitly distinguish mocked and live acceptance | Never present CI-green as proof of every production path |
| One-time migration and cleanup workflows remained in Actions | Stale buttons could re-trigger completed, dangerous operations | Retire workflows after successful verified maintenance and keep dated procedures as **historical**, not runnable | Post-migration result should be rechecked using read-only audits only |
| Public GitHub Actions detail leaked sensitive metadata in principle | A public repository can expose all logs, summaries and artifacts | Allowlist **only** fixed numeric metrics; never publish novel identifiers, titles, detailed file paths, raw exceptions, tokens, EPUBs or reports | GitHub-controlled runner setup logs are outside the application wrapper |
| Code release/branch cleanup could race or falsely imply completion | Queued tests, mutable refs and squash merge histories can mislead | Check the exact head SHA and completed CI jobs; preserve branches with uncertain unique changes; release only code from green `master` | Scheduled CI starts and PR creation are **not** completion |

## Significant completed recovery: readable folders, November 2026

This was a deliberately protected data migration, not a routine upload. The 13 November disposable dataset acceptance validated dual-format paths, synthetic contents, SHA-256 equality, stale-parent refusal and cleanup. On 14 November the production run used a verified private 221-file backup, migrated 88 previously opaque folders in bounded batches and verified 89/89 readable folders with zero outstanding conflicts. See [verified production record](POST_MIGRATION_VERIFICATION_2026-11-14.md).

**Lesson:** migrations need separate production gates, byte-level proof, a resumable plan and an independent read-only audit. A later title edit must not rename the historical folder or alter IDs. One-off migration workflows are retired; do not resurrect their production apply paths merely to run tests.

## Other historical investigative evidence

The production-readiness and adversarial-failure reviews highlighted inconsistent protection across mutation paths, incomplete "unchanged" predicates, cover transaction uncertainty and gaps between mock tests and real HF behaviour. These were investigation findings and follow-up priorities, not evidence that every scenario was reproduced live. Review the current code and relevant regression tests rather than assuming all prior diagnoses still apply.

For user-facing operating instructions, read [Safety and recovery](SAFETY_AND_RECOVERY.md). For code-level failure sequences, the older [historical agent handbook](archive/AGENTS_PRE_2026-11-21.md) has more detailed cases but may contain obsolete workflow names and pre-migration paths.

## Current tracked implementation gaps (checked 21 November 2026)

These are open issues, not completed fixes:

- [#54: embedded cover extraction](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/54): normal upload can attach separately supplied local cover files, but does not yet extract authentic artwork from the novel ZIP/OPF-declared EPUB and publish `coverPath` in the same transaction.
- [#46: Hiatus / Dropped publication statuses](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/46): source parser and metadata patch validator currently support `Completed` and `Ongoing` only. Do not infer a status or alter a real book from issue text alone.

A separate workflow hardening gap was identified during this audit: three manual private-HF workflows lacked a repository/master job guard and common concurrency group. This documentation change adds those guards and a workflow regression test. Verify the actual merged YAML and passing CI before relying on them.

## Failure response protocol for future agents

1. **Classify first:** read-only observation, preview failure, validation failure, ambiguous identity, partial commit, uncertain commit or actual confirmed data corruption.
2. **Stop new writes:** do not run a broad reset to fix a partial upload, missing cover, stale catalogue or UI problem.
3. **Preserve evidence privately:** note non-secret command flags, a sanitised error class, count-based outcome, local report path and known remote revision.
4. **Check state at a pinned revision:** inspect catalogue/paths and known commit receipts before planning a rerun; separate reader-only symptoms from HF storage faults.
5. **Reproduce safely:** use fake HF clients and hostile synthetic ZIPs; if real transport semantics matter, use a disposable pre-created private dataset and a dedicated fine-grained test token.
6. **Repair minimally:** select only affected records/blobs, retain stable IDs and personal metadata; use current plan plus parent revision check.
7. **Protect recovery:** verify backup availability and content hashes before any destructive operation. A snapshot receipt is *not* proof that the original EPUB is semantically healthy.
8. **Test failure injection:** partial batch success, retryable/nonretryable HF errors, unexpected remote revision, renamed titles and missing/corrupted artifacts.
9. **Verify terminal state:** successful run **and** exact tested commit, numerical summary, clean inspection as appropriate; never treat a queued or preview-only run as a completed apply.
10. **Record the lesson:** add/adjust tests and the relevant architecture, operations and incident documentation with a linked commit or PR.

## Recurring misconceptions to prevent

- `README` and `AGENTS` are documentation, not a runtime truth source. The source/test contract wins if stale.
- Cover/metadata/genre repair is not an excuse to download a novel again or alter reading progress.
- A chapter-number count, a generated cover, or a file extension alone is not proof of valid content.
- A private HF backup dataset and the production HF dataset are different principals and must not be the same target.
- A successful dry run cannot be described as a successful write.
- Remote-first **readiness** is not a completed backup and cannot prove region copy support.
- A run's public log being count-only is intentional; detailed diagnostics belong in private local reports.
- Older Novel_Library references in documents refer to what is now primarily Novel-Retriever; check the actual current workflow source before dispatching anything.
