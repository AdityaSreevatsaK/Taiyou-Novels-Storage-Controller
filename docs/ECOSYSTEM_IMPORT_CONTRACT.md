# Novel Retriever → Controller → Library: import contract

**Verified 26 November 2026.** This document distinguishes the **producer
contract**, the **Controller validation and upload contract**, and what was
actually verified on a **synthetic disposable HF dataset**. It is not proof
that real novels were downloaded, imported or displayed in production.

## Producer: `RichardDaffern/Novel-Retriever`

The maintained completed-export code `tools/export_completed_github_novels.py`
produces a `manifest.json` at the artefact root and individual importable
novel ZIP packages in `novels/`. The manifest contains:

- `exported_novels`: exact selected ZIP count
- `novels[]`: `file` (`novels/<filename>.zip`), `zip_sha256` and `bytes`
- `conflicting_editions` and `invalid_archives`: must both be empty
- Additional provenance, warning and unavailable-book data, which do not
  authorise import of unverified material

The export pipeline may embed a genuine source cover in EPUB and/or include
an unambiguous `cover.*` in the inner ZIP. An export is a completed-book
candidate, not a confirmed Hugging Face import. Never import incomplete
chapter batches or an unreviewed archive edition.

## Controller: private HF import

The retained `.github/workflows/hf-cloud-import.yml` requires an exact
**export run ID**, an approved artefact family, and an explicitly selected
`apply_changes` flag which defaults to `false`.

`taiyou_storage.cloud_import.check_bundle` fails closed on malformed
manifest, duplicate or missing ZIPs, checksum or size mismatches, excess
counts, invalid paths, unmanifested ZIPs, or unsafe cover-tree contents.
`taiyou_storage.upload` also validates original ZIP and EPUB structure,
chapter index, edition uniqueness, and stable identity. An optional cover
must be a verified local sidecar, an OPF-declared genuine EPUB image or an
unambiguous standalone image in the ZIP; it is uploaded with the private
catalogue in the same revision-guarded batch. Missing artwork is not a
reason to invent an image.

The private dataset uses schema v1 `data/library.json`, immutable
24-lowercase-hex IDs, stored `epubPath`/`archivePath` and optional
`metadata.coverPath`. Legacy ID-only and modern readable folders are
supported. Never construct an existing file path from a changed title.
No import may overwrite owner-managed progress, ratings, notes, tags,
collections, comments or private personal-state records.

Source publication state is distinct from reading progress. The canonical
values are `Completed`, `Ongoing`, `Hiatus`, `Dropped`, aligned to
`Taiyous-Personal-Library/src/lib/publication-status.ts`. The Controller
normalises verified aliases only on new source metadata proposals.
Unrecognised historical status strings remain untouched.

## Reader: `AdityaSreevatsaK/Taiyous-Personal-Library`

The Reader consumes the private HF dataset via its authenticated gateway,
not Controller GitHub Actions artefacts. Its Cloudflare deployment, login,
in-browser EPUB rendering, offline caches and personal-state reconciliation
are **independent** of a successful Controller upload. Verify those through
the Reader's own source, tests and deployment before claiming an imported
book is visible and readable.

## Verified integration evidence

- [PR #70](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/pull/70):
  source publication taxonomy; offline CI passed
- [PR #71](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/pull/71):
  embedded validated covers in atomic batch; offline CI passed
- [PR #72](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/pull/72):
  producer-shaped bundle validation, synthetic fake-HF preview, apply,
  tamper detection, interrupted-batch retry and idempotent replay
- [Live synthetic import #45836547414](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/45836547414):
  **success**, 3 ZIPs verified and privately uploaded, 1 cover uploaded,
  independent ZIP/EPUB/cover read-back, rerun with zero new commits
- [Live synthetic full-verified backup #45436984800](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/actions/runs/45436984800):
  **success**, 6 synthetic source objects and 1 independently verified
  private snapshot

**Not verified by those runs:** downloading an artefact from an actual
Retriever workflow into the Controller, a real production HF import,
a production full snapshot or an authenticated multi-device browser
inspection of newly imported books. Never promote synthetic evidence
to these production outcomes.

## Operational cautions

Retriever's 26 November `Library - Bulk Download` run
[#45833724138](https://github.com/RichardDaffern/Novel-Retriever/actions/runs/45833724138)
failed in its *preparation* job because the submitted batch contained
**17 new titles**, exceeding the workflow's maximum **10 per run**.
No title downloads from that run were proven. Split authorised acquisition
requests into batches within that limit and separately verify actual rights,
chapter completeness and completed-export artefact availability.
This failure is not a Storage Controller cloud-import regression.

Keep all private novel artefacts, verified archive manifests, personal
records and tokens out of public GitHub logs and repositories. The
Controller's production apply remains opt-in, never automatic.
