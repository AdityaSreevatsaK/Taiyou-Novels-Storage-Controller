# Console and GitHub Actions output conventions

All controller operations should be **brief, clear and complete** by default.

## Default local command output

1. **START**: short operation name, scope and read-only/apply safety status.
2. **SUMMARY**: labelled counts of books, files, covers, warnings and conflicts.
3. **REPORT**: optional path to a private local CSV/JSON with details.
4. **END**: `PREVIEW`, `COMPLETED`, `NO CHANGES`, `CANCELLED`,
   `BLOCKED` or `FAILED`.

Example, with fictional counts:

```text
=== Local cache cleanup preview ===
  Owned inspection files : 700
  Owned bytes            : 2,317,036,432
  Legacy cache entries   : 208
  Legacy potential space : 1.9G
  Result                 : AWAITING CONFIRMATION
=== End: Local cache cleanup preview ===

Type DELETE LOCAL CACHE to confirm: ...
=== Local cache cleanup completed ===
  Owned files removed        : 700
  Owned bytes removed        : 2,317,036,432
  Legacy entries removed     : 208
  Matching entries remaining : 0
  Result                     : COMPLETED
=== End: Local cache cleanup completed ===
```

These counts are distinct: owned **files** and legacy **cache entries** are
not novel counts. Shared Hugging Face cache blobs might remain referenced,
so a displayed legacy **estimated** recovery amount is not guaranteed.

The common `19_command_output.cmd` handles start/final status for Windows
launchers. Python entrypoints use `console_summary.print_summary` for
consistent labelled metrics, report locations and a final state. Verbose
per-novel output must remain opt-in via `--verbose` where supported. Mandatory
conflict/safety prompts and typed confirmations are **never suppressed**.
Dangerous reset previews report affected **counts**, not thousands of paths.
All detailed private diagnostic reports remain outside Git version control.

## GitHub Actions output

The `taiyou_storage.github_output` runner wraps existing non-interactive
Python operations. It shows:

```text
[START] Library inspection | VERIFY
  Total novels: 352
  High-severity findings: 0
[END] Library inspection | COMPLETED
```

Each run also adds a small Markdown table to the **GitHub Actions step
summary**: task, mode, result and allowlisted numeric counts. Only fixed
numeric metric names are ever emitted. No titles, IDs, source links, local
paths, raw errors, EPUB text, tokens or private reports are published.

Full underlying command output is captured in `$RUNNER_TEMP` on the ephemeral
runner, not in a GitHub artifact, and is discarded when the runner is cleaned
up. On failure, the public log shows a concise failure status and exit code;
it must not echo raw private exception text or file names.

**Preview is not a successful upload.** If a workflow has preview and apply
steps, their endings are separately labelled and apply stays explicit.
GitHub's own checkout, dependency-install and hosted-runner diagnostics are
platform-controlled; this convention governs **application** logs.

## Implementation rules for future tools

- Prefer `print_summary` and the shared Actions wrapper instead of custom
  multi-page prints or ad-hoc JSON dumps.
- Avoid one line per novel/chapter/remote file unless the user enables verbose
  output. Use periodically updated **numeric progress** during long work.
- Never label a failed, cancelled or read-only operation as successfully applied.
- Provide a specific report location for actionable private detail.
- Protect irreversible operations with the original backup-first and typed
  confirmation checks.
- Preserve non-zero exit codes, warnings, GitHub workflow guards and existing
  data-integrity validation.
- Add output tests that check start, result, end, privacy filtering and the
  distinction between actual files deleted and HF reference/cache counts.
- When adding new Actions tasks, add a fixed task name and allowlisted metric
  labels in `github_output.py`; never echo arbitrary captured output.
