# Private library inspection and integrity

Launchers 05 and 13 to 16 use one read-only inspection engine. Launcher 17 is a separate explicit-write migration. Reports and revision caches
stay **local** inside the gitignored reports/ directory. Never commit, publish or
upload private reports to GitHub Actions artefacts.

## Windows commands

Install dependencies with: py -m pip install -r requirements.txt
Authenticate using: hf auth login

| Launcher | Local output |
| --- | --- |
| 13_export_novel_inventory.cmd --mode deep | novel-inventory.csv and .json |
| 14_audit_missing_covers.cmd | missing-covers.csv (attention only) and cover-audit.csv (all novels) |
| 15_compare_retriever_inventory.cmd | retriever-comparison.csv, .json, retriever-exclusions.json |
| 05_verify_integrity.cmd | integrity-report.csv and .json |
| 16_library_health_report.cmd --mode deep | library-health.html, .json and .csv |

All output is written under reports/. Every inspection command now defaults to **manifest** mode,
which downloads only the catalogue and small per-novel inspection manifests. It does not download
EPUBs, ZIPs or cover images. Override with --mode quick, --mode manifest or --mode deep.
Use --mode deep for a new byte-level verification; remote checks cannot replace it. Other options: --repo OWNER/PRIVATE-DATASET,
--workers 1..4 and --reports-dir PATH.

The Retriever comparison expects a local sibling checkout at ../Novel-Retriever
by default. Use --retriever-root PATH to override. Alternatively run:

~~~powershell
py -m taiyou_storage.inspection_cli compare --registry "C:\Novel-Retriever\downloaded_novels.json" --planned "C:\Novel-Retriever\curated_novels.json"
~~~

Repeat --planned for additional JSON lists. A recorded complete download is not proof that its GitHub Actions artefact has not expired.
A registry entry covering only a limited chapter range is reported as
PARTIALLY_DOWNLOADED instead of being mistaken for a complete download.

## Evidence and interpretation

Quick mode pins the HF revision, reads the catalogue and lists files. It
cannot prove an EPUB, ZIP or image is valid. Deep mode checks ZIP/EPUB CRC,
the downloaded chapters.json positions and referenced chapter files, and
decodes JPEG/PNG/WebP covers. A valid OPF-declared embedded cover is also
recognised.

VERIFIED_COMPLETE requires an explicit source manifest completion assertion,
no missing or repeated positions, and all chapter files verified. Bare-list
manifests can establish VERIFIED_RANGE, never prove end-of-novel completion.
INCOMPLETE means a manifest has gaps, duplicate positions, malformed entries
or missing referenced chapter files. UNVERIFIED means coverage cannot be
established, for example an older EPUB without chapters.json.

The catalogue chapterCount and a novel's publication status are only hints,
never proof of available chapter positions. The explicit complete flag is
source-provided evidence, not a guarantee that the source website has published
its final chapter. Inspect download provenance before trusting that assertion.

AVAILABLE requires a valid decoded standalone cover. EMBEDDED_ONLY means a
verified OPF-declared image within the EPUB without a standalone cover.
MISSING means no usable image found, BROKEN means the referenced image is
absent or corrupt, and UNVERIFIED means insufficient evidence. Placeholder
indicators are never accepted as authentic covers. Image authenticity
cannot always be proven from pixels without trustworthy provenance.

## Retriever exclusions and privacy

retriever-exclusions.json contains SHA-256 fingerprints of canonical source
URLs only, not titles, IDs or personal metadata. Canonicalisation uses HTTPS,
lower-case hosts, strips www., the fragment and trailing slash, and preserves identifying query parameters. The format
is versioned and suitable for a future **separately reviewed** Retriever
change to compare hashes locally and avoid duplicate downloads.

The exclusion file and comparison reports are **private** and must not be
committed to either public repository. Even hashed public URLs can be
dictionary-guessed. URLs absent from the catalogue cannot be safely excluded.

## Read-only guarantees and limits

The scanner uses only HF dataset_info, list_repo_tree/list_repo_files and
hf_hub_download. It refuses non-private datasets. No HF write API is invoked.
Concurrent downloads are capped at four; the scan is pinned to one immutable
revision; cached deep results are separated by revision and source record.
Transient failures produce unresolved findings rather than false completeness.
The tooling never repairs, deletes, uploads or triggers downloads.

Scans are local-only. CI uses fixtures and mocked Hugging Face calls; it does
not access the live dataset or write any reports to GitHub Actions artefacts.

## Local download cache cleanup

Inspection and one-time backfill now use a dedicated, marked Hub cache at
`reports/.inspection-download-cache/`. Shared Hugging Face caches are no longer
used by these inspections; uploading novellas and unrelated programmes retain
their own caching behaviour.

Use `18_cleanup_inspection_downloads.cmd` to preview the size and
`18_cleanup_inspection_downloads.cmd --apply` to request local interactive
deletion. The cleaner refuses an unmarked directory or another dataset's marker.

Files downloaded by **older versions** of the inspection scripts may be
inside the shared HF cache. Run:

~~~powershell
.\\18_cleanup_inspection_downloads.cmd --legacy-shared-cache
.\\18_cleanup_inspection_downloads.cmd --legacy-shared-cache --apply
~~~

This extra flag precisely selects cached `data/novels/**/source.epub`,
`original.zip` and `cover.{jpg,jpeg,png,webp}` for the selected dataset.
It uses the HF library's `delete_files` strategy so a shared blob is preserved
when other snapshot entries refer to it. **It cannot identify which programme
originally downloaded those cache entries**, so other local tools may need to
re-download them. It never deletes the shared catalogue, sidecar manifests,
another dataset, untracked exports or any files on HF.

Both modes default to dry run and require typing `DELETE LOCAL CACHE` before
deletion. Stop all inspection/upload processes first. An `hf_xet` shared chunk
cache is separately managed by Hugging Face and is not erased by this tool.

## Understanding the cover audit

`14_audit_missing_covers.cmd` produces two different local reports:

- **missing-covers.csv:** only novels requiring attention because a standalone
  cover is absent, its catalogue reference is broken, a placeholder is suspected,
  multiple candidates conflict, or the checked image is corrupt.
- **cover-audit.csv:** every novel, including those with a known cover file that
  simply has not been byte-validated.

The **standalone_cover** column is based on file listing evidence. `PRESENT`
means Hugging Face contains a likely cover file, but does not guarantee that it
is a genuine or readable image. `ABSENT` means no standalone image was found;
there could still be a valid embedded EPUB cover. The separate
**cover_validation** column is `UNVERIFIED` until a trustworthy inspection
manifest or optional `--mode deep` establishes more evidence.
The **recommended_action** column tells you what to do next.

Routine cover audits use remote file metadata and small manifests only; they
do **not** need to download every novel. For byte-level image/EPUB inspection,
run `14_audit_missing_covers.cmd --mode deep`. A deep check does download
relevant files to the isolated inspection cache.
