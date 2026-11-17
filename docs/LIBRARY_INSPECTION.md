# Private library inspection and integrity

All five launchers use one read-only inspection engine. Reports and revision caches
stay **local** inside the gitignored reports/ directory. Never commit, publish or
upload private reports to GitHub Actions artefacts.

## Windows commands

Install dependencies with: py -m pip install -r requirements.txt
Authenticate using: hf auth login

| Launcher | Local output |
| --- | --- |
| 13_export_novel_inventory.cmd --mode deep | novel-inventory.csv and .json |
| 14_audit_missing_covers.cmd | missing-covers.csv |
| 15_compare_retriever_inventory.cmd | retriever-comparison.csv, .json, retriever-exclusions.json |
| 05_verify_integrity.cmd | integrity-report.csv and .json |
| 16_library_health_report.cmd --mode deep | library-health.html, .json and .csv |

All output is written under reports/. Inventory, cover, integrity and health default to deep inspection; comparison defaults to quick.
Override with --mode quick or --mode deep. Other options: --repo OWNER/PRIVATE-DATASET,
--workers 1..4 and --reports-dir PATH.

The Retriever comparison expects a local sibling checkout at ../Novel-Retriever
by default. Use --retriever-root PATH to override. Alternatively run:

~~~powershell
py -m taiyou_storage.inspection_cli compare --registry "C:\Novel-Retriever\downloaded_novels.json" --planned "C:\Novel-Retriever\curated_novels.json"
~~~

Repeat --planned for additional JSON lists. A recorded complete download is
not proof that its GitHub Actions artefact has not expired.

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
