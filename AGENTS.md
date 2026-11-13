# AGENTS.md — Taiyou Novels Storage Controller: Engineering and Agent Handbook

> **Scope:** This file documents this repository and provides safe working instructions for AI coding agents. It is deliberately much more detailed than the user-facing `README.md`. Read the code and tests before making changes; this handbook describes the implementation observed on the 13 November 2026 review, not an alternative specification or an excuse to skip verification.
>
> **Repository:** `AdityaSreevatsaK/Taiyou-Novels-Storage-Controller`
>
> **Production branch:** `master`
>
> **First tagged release:** `v0.1.0`
>
> **Main private data repository:** Hugging Face dataset `AdityaSreevatsaK/Taiyous-Novels`
>
> **Primary audience:** AI engineering agents, maintainers, reviewers, and future contributors who need to understand the system without reading every historical conversation.
>
> **Important distinction:** This file is public in a GitHub *code* repository. Never put actual private novel titles from the dataset, unpublished manuscripts, access tokens, private catalogue contents, personal ratings/comments, downloaded novel archives, or private URLs in this document or GitHub CI logs.

---

## 0. Reading order and source-of-truth hierarchy

An agent beginning work in this repository should:

1. Read this file to learn the architecture, workflows, constraints, and failure modes.
2. Read `README.md` for the supported user experience and commands.
3. Read the specific `taiyou_storage/*.py` module being changed, including all of its call sites and associated tests.
4. Read the relevant GitHub Actions YAML and detailed docs if a workflow is involved.
5. Prefer **executable source code and tests** over an older description whenever they differ.
6. Read the active branch and current `master` SHAs before performing any GitHub modification.
7. Keep all existing working features intact; make changes in a separate branch, add regression tests, and confirm CI before merging.
8. Do not assume that a successful mocked test proves that a live Hugging Face read/write operation works.
9. Do not run a real `--apply` operation against the owner's primary dataset as a smoke test. Use synthetic data and a separate, disposable **private** test dataset only with explicit permission.
10. Treat the owner’s current instructions about scope, release timing, and exclusions as more important than the historical preferences described below.

**Other useful documents:** [README](README.md), [smart upload details](README.smart-upload.md), [GitHub Actions security](docs/GITHUB_ACTIONS.md), [historical genre repair](docs/GENRE_REPAIR.md), [release process](docs/RELEASING.md), [changelog](CHANGELOG.md), and [v0.1.0 notes](docs/releases/v0.1.0.md).

### 0.1 Verified versus inferred information

In this document, statements introduced as **Implemented** describe code found in this repository. **Operational advice** describes safe maintenance practice, which is not necessarily enforced by software. **Known limitation** indicates a currently missing or deliberately out-of-scope capability. Do not silently convert a recommendation into a claim that a feature already exists.

## 1. Mission and ecosystem context

### 1.1 Why this exists

The Storage Controller is a small Python, Windows-friendly management layer around a **private Hugging Face dataset**. The dataset stores a personal novel library that is consumed by a separately deployed web reader. The controller is designed to:

- Import pre-packaged novels from local ZIP files.
- Preserve stable novel IDs and user-owned metadata as novel source data changes.
- Store both original ZIP backups and separately accessible EPUB files.
- Associate downloaded cover images with existing novels.
- Preview imports, detect ambiguous matches, and avoid unnecessary overwrites.
- Provide local catalogue exports, backups, download utilities, and limited status checks.
- Provide carefully scoped, manually triggered GitHub Actions for private inspection, backup, reports, covers, and a separate historical metadata repair.
- Make dangerous dataset-wide resets possible **only** after a verified local backup and explicit interactive confirmations.

This repository has **no web interface**, reader, general download crawler, scheduled ingestion service, database server, or commercial cloud dependency. It operates on an existing Hugging Face dataset and on local files.

### 1.2 High-level ecosystem

```text
Novel source websites
       |
       v
RichardDaffern/Novel_Library  (separate downloader/retriever repository)
       |  prepared ZIPs and cover artifacts
       |
       +--> local Windows folder: novels/*.zip
       |          |
       |          v
       |    Taiyou-Novels-Storage-Controller
       |      - validate and match
       |      - preview/reconcile
       |      - guarded HF commits
       |          |
       +--> downloaded cover ZIP --------------------+
                                                    |
                                                    v
                                  PRIVATE Hugging Face dataset
                                  AdityaSreevatsaK/Taiyous-Novels
                                  - data/library.json
                                  - data/novels/<id>/source.epub
                                  - data/novels/<id>/original.zip
                                  - data/novels/<id>/cover.<ext>
                                                    |
                                                    v
                           Taiyous-Personal-Library (separate web reader)
                           - renders library and reads EPUBs
                           - owns reader UI, access controls and app state
```

Related repositories and services:

| Component | Role | Change from this repository? |
|---|---|---|
| `RichardDaffern/Novel_Library` | Downloads/assembles novels and cover artifacts. Also provides historical GitHub Actions artifacts used by genre restoration. | **No.** Independent implementation, tests and workflows. |
| `AdityaSreevatsaK/Taiyou-Novels-Storage-Controller` | This repository: local and GitHub Actions storage-management tools. | Yes, within the approved task. |
| `AdityaSreevatsaK/Taiyous-Novels` on Hugging Face | Private authoritative storage for the novel files and catalogue. | **Never modify inadvertently.** Explicit approval and scoped credentials required. |
| `AdityaSreevatsaK/Taiyous-Personal-Library` | Separate reader web application. | **No.** Do not assume its deployment, limits, UI or data persistence can be changed here. |
| A separate **private** Hugging Face backup dataset | Destination for optional private snapshots and reports. The default example in workflows is `AdityaSreevatsaK/Taiyous-Novels-Backup`. | Only the manual backup/report workflows should create or write there. |

The source downloader, controller and reader have separate responsibilities. Do not couple them by importing code directly between GitHub repositories or silently altering their formats. Agree a versioned cross-repository contract before changing an interface.

### 1.3 Non-goals

- Scraping/downloading entire novels from source websites.
- Circumventing access controls, logins, rate limits or paywalls.
- Hosting the reader or serving public EPUB endpoints.
- Managing the website's OAuth, email OTP, Cloudflare Access, gateway or UI.
- Deleting a single novel from the cloud via this controller (placeholder only).
- Automatically restoring a previously deleted entire dataset (not implemented).
- Silently merging duplicates or renaming stable IDs.
- Automatically restoring genres unless the separate, expressly requested workflow is invoked.

## 2. Repository layout and responsibilities

```text
Taiyou-Novels-Storage-Controller/
├── AGENTS.md                         # This agent-oriented engineering handbook
├── README.md                         # Concise user-facing setup and guidance
├── README.smart-upload.md            # Technical novel uploader reference
├── CHANGELOG.md                      # Version history
├── VERSION                            # Current release version; e.g. 0.1.0
├── requirements.txt                   # Hugging Face dependency with constraints
├── constraints.txt                    # Tested resolved dependency versions
├── .gitignore                         # Protect local data/cache/credentials
├── LICENSE
├── 00_storage_menu.cmd                # Windows interactive launcher menu
├── 01_bulk_upload.cmd                 # Novel preview + single-process confirmation
├── 02_download_all.cmd                # Download ZIP archives
├── 03_list_novels.cmd                 # Export novel list
├── 04_detect_conflicts.cmd            # Export duplicate titles
├── 05_verify_integrity.cmd            # PLACEHOLDER, not implemented
├── 06_sync_status.cmd                 # Compare local EPUB IDs
├── 07_backup_catalogue.cmd            # Back up catalogue only
├── 08_restore_novel.cmd               # PLACEHOLDER, not implemented
├── 09_delete_novel.cmd                # PLACEHOLDER, not implemented
├── 10_upload_covers.cmd               # Cover import confirmation launcher
├── 11_clear_hf_data.cmd               # Full backup-first reset launcher
├── taiyou_storage/
│   ├── __init__.py
│   ├── core.py                        # Catalogue validation, IDs, CSV, remote load
│   ├── cli.py                         # Read-only/local catalogue management CLI
│   ├── upload.py                      # ZIP parsing, matching, novel upload
│   ├── covers.py                      # Cover ZIP parsing, matching, preview CLI
│   ├── cover_batches.py               # Guarded, resumable cover commits
│   ├── reset.py                       # Backup-verified destructive local reset
│   ├── actions.py                     # Manual privacy-safe HF GitHub Actions
│   └── genre_repair.py                # Separate historical source-genre repair
├── docs/
│   ├── GITHUB_ACTIONS.md
│   ├── GENRE_REPAIR.md
│   ├── RELEASING.md
│   ├── covers_manifest.example.json
│   └── releases/v0.1.0.md
├── tests/
│   ├── test_core.py
│   ├── test_upload.py
│   ├── test_covers.py
│   ├── test_cover_batches.py
│   ├── test_reset.py
│   ├── test_actions.py
│   ├── test_genre_repair.py
│   └── test_smoke_integration.py
└── .github/workflows/
    ├── ci.yml
    ├── hf-inspect.yml
    ├── hf-private-backup.yml
    ├── hf-private-reports.yml
    ├── hf-upload-covers-artifact.yml
    ├── hf-restore-genres.yml
    ├── release.yml
    └── prune-reviewed-branches.yml  # Historical one-shot branch cleanup
```

The `prune-reviewed-branches.yml` file remains in the repository after its one-time execution, but its path-limited push trigger is **not** a recurring cleanup mechanism. Do not change or re-trigger it casually.

## 3. Core architectural decisions

### 3.1 Private Hugging Face dataset as storage backend

**Implemented:** Python code uses `huggingface_hub` (`HfApi`, `hf_hub_download`, `CommitOperationAdd` and where applicable `CommitOperationDelete`) for remote operations. This is a **dataset repository** (`repo_type="dataset"`), not a Hugging Face Space or a conventional SQL database.

- `core.DEFAULT_REPO = "AdityaSreevatsaK/Taiyous-Novels"`.
- The catalogue lives in `data/library.json` at schema version `1`.
- All novel blobs reside under `data/novels/<id>/`.
- The Hugging Face dataset's immutable revision SHA is a critical consistency token.
- Every data-modifying operation must first establish that the dataset is **private**.
- Uploads use optimistic concurrency (`parent_commit`) instead of blind, unguarded overwrites.
- Remote downloads for consistency checks use pinned revisions when supported.

### 3.2 Catalogue is both index and reader contract

The reader discovers novels through `data/library.json`, not by directly listing ZIPs. The catalogue links each stable book ID to its stored EPUB, original archive and optional cover. A novel file can exist without being discoverable by the reader if its catalogue entry is missing, so **orphan detection is a safety requirement**.

Do not change the shape of `library.json` only because it would be convenient for one uploader. Check the reader contract and migrate existing private records safely if the schema needs to change.

### 3.3 Atomicity is per Hugging Face commit

An HF commit can update multiple related files and their catalogue entries together. That is the unit of atomicity implemented here:

- **Novel upload:** one commit per novel, including `library.json` and only the ZIP/EPUB files that need replacing.
- **Cover upload:** one commit per group of covers, including all corresponding catalogue edits.
- **Genre repair:** one commit for the catalogue change plus a private pre-change catalogue copy.
- **Reset:** one revision-checked commit removing the `data/` contents while writing a valid empty catalogue.

**Not implemented:** an all-or-nothing transaction over an entire multi-novel import or multiple cover batches. If a later commit fails, earlier successful commits remain. Recovery is by re-previewing and reconciling, not by assuming a rollback.

### 3.4 Local-first management; offline tests

Primary manual operations are intended for a Windows user with Python and CMD launchers. Unit and synthetic integration tests must not require Hugging Face credentials or paid external services. GitHub CI uses Windows and Linux to detect platform-specific issues.

## 4. Remote storage layout and schema

### 4.1 Expected paths

```text
HF dataset repo (PRIVATE)
├── .gitattributes                      # HF repository-managed metadata, if present
├── README.md                           # Optional HF repository-level README
└── data/
    ├── library.json                    # Version 1 library catalogue
    └── novels/
        ├── aaaaaaaaaaaaaaaaaaaaaaaa/
        │   ├── source.epub             # Reader-accessible EPUB
        │   ├── original.zip            # Original imported download ZIP
        │   └── cover.jpg               # Optional; .png or .webp also possible
        └── bbbbbbbbbbbbbbbbbbbbbbbb/
            ├── source.epub
            └── original.zip
```

There can be additional private files under `data/` owned by other services. **Full reset affects all of them**, not just `data/novels/`.

### 4.2 Catalogue example

The JSON below is **illustrative** with fictional IDs and values. The strict validator only requires a valid schema marker, a list of book objects, a 24-character lowercase hexadecimal ID, matching metadata ID, and canonical EPUB path. Individual metadata fields may be absent or extended by the reader.

```json
{
  "version": 1,
  "books": [
    {
      "id": "aaaaaaaaaaaaaaaaaaaaaaaa",
      "metadata": {
        "id": "aaaaaaaaaaaaaaaaaaaaaaaa",
        "title": "Synthetic Example Novel",
        "author": "Example Author",
        "language": "en",
        "description": "Fictional example only.",
        "status": "Completed",
        "sourceUrl": "https://example.org/novel/fictional",
        "chapterCount": 100,
        "sourceTags": ["Cultivation", "Fantasy"],
        "size": 1234567,
        "cloud": true,
        "metadataScanned": true,
        "originalFileName": "fictional.zip",
        "importedAt": 1790000000000,
        "progress": 0,
        "personalTags": [],
        "personalRating": 0,
        "coverPath": "data/novels/aaaaaaaaaaaaaaaaaaaaaaaa/cover.jpg"
      },
      "epubPath": "data/novels/aaaaaaaaaaaaaaaaaaaaaaaa/source.epub",
      "archivePath": "data/novels/aaaaaaaaaaaaaaaaaaaaaaaa/original.zip"
    }
  ]
}
```

**Code-derived required invariants** (`core.validate_catalogue`):

1. Top-level object contains `version == 1` and `books` is a list.
2. Every book is an object with a `metadata` object.
3. Each `id` matches `[a-f0-9]{24}`, with no duplicate IDs.
4. Each `metadata.id` equals its containing entry's `id`.
5. Each `epubPath` is exactly `data/novels/<id>/source.epub`.

**Additional operational conventions**, validated by the relevant upload code rather than all by `validate_catalogue`:

- Canonical archive path: `data/novels/<id>/original.zip`.
- Canonical cover path: `data/novels/<id>/cover.<ext>`, with extension from the supported set.
- `metadata.coverPath` is a reference to the cover object; the mere presence of the cover file does not guarantee it is linked or visible.
- `metadata.sourceTags` are original-source genre categories, **not** the user's `personalTags`.
- The reader may maintain fields such as progress, notes, ratings, comments or collections that the controller must not casually overwrite.
- The catalogue validator **does not check remote blob existence or its SHA-256**; inspection or reconciliation must do this separately.

### 4.3 Novel ID semantics and compatibility

For an entirely new novel, `upload.py` derives its initial 24-hex book ID from the first 24 characters of the SHA-256 digest of the **EPUB bytes**:

```python
novel_id = hashlib.sha256(epub_bytes).hexdigest()[:24]
```

After a book exists, its **stable catalogue ID is authoritative**. If an updated EPUB has different bytes but matches the same title and author unambiguously, the uploader keeps the existing ID. Consequently, a current book ID **need not equal the digest of the current EPUB**.

Never regenerate all IDs from EPUB digests. That could break reader progress, ratings, cover links, collections and app data keyed by ID.

### 4.4 Source-managed versus personal metadata

The normal uploader builds a source-metadata record containing some or all of:

`title`, `author`, `language`, `description`, `status`, `sourceUrl`,
`chapterCount`, `sourceTags`, `size`, `cloud`,
`metadataScanned` and `originalFileName`.

Then `merged_metadata(old, new, chosen_id)` starts with existing metadata, overlays the new source-managed fields, enforces the chosen ID, and fills defaults for `importedAt`, `progress` and `personalTags`. It explicitly retains existing nonempty `sourceTags` when the incoming ZIP's genres are empty or missing.

**Important subtlety:** Preservation is implemented by overlaying source fields on the original dictionary, *not* by validating a separately maintained allowlist of personal fields. Changing the extraction/merge keys can accidentally overwrite app-owned data. If adding a new key, confirm who owns it; test preservation of ratings, reading progress, tags, comments, status, source genres and any currently deployed reader fields.

### 4.5 Handling absent or damaged catalogues

`core.load_remote(repo, allow_empty=False)`:

- Verifies the dataset is private and has a revision SHA.
- Lists remote repository files at that revision.
- Reads and validates `data/library.json` when present.
- Fails if the catalogue is absent, except when `allow_empty=True` and no files exist anywhere under `data/`.
- Never treats an inaccessible, public, damaged or orphaned dataset as a harmless empty library.

**Only** the novel upload entrypoint normally sets `allow_empty=True`. Do not make the absence of `library.json` a reason to delete or overwrite unknown remote files.

## 5. Novel input format, parsing and validation

### 5.1 What the user supplies

A local folder holds one or more `*.zip` files, generally produced by the separate Novel Library downloader. The ZIP needs one `source.epub` anywhere in its directory tree; `metadata.json` and `chapters.json` are optional but useful.

```text
novels/
  example.zip
    chapters/
      source.epub
      metadata.json
      chapters.json
      001.txt
      002.txt
      ...
```

The uploader searches for file **basenames**, not only ZIP root paths, so `chapters/source.epub` is valid. A duplicate file with the same target basename triggers an error. The generated EPUB must contain:

- `mimetype`
- `META-INF/container.xml`
- An EPUB package metadata XML file referenced by the container's `rootfile` element.

### 5.2 Metadata precedence

`upload.read_novel` extracts information from `metadata.json` and the EPUB OPF package:

| Field | Preferred origin | Fallback/notes |
|---|---|---|
| `title` | `metadata.json.title` | OPF `dc:title`, then ZIP filename stem |
| `author` | `metadata.json.author` | OPF `dc:creator`, then `Unknown author` |
| `language` | `metadata.json.language` | OPF `dc:language` |
| `description` | `summary` | `synopsis`, `description`, then OPF description |
| `status` | `metadata.json.status` | No invented completion status |
| `sourceUrl` | `metadata.json.source_url` | OPF source |
| `chapterCount` | Length of parsed `chapters.json` if nonempty | `metadata.json.chapter_count` |
| `sourceTags` | `metadata.json.tags` | `metadata.json.genres`, otherwise empty |
| `size` | Actual embedded EPUB byte length | Not inferred from chapter count |
| `originalFileName` | Input ZIP basename | Useful for audit/provenance |

Only string/list shape normalisation implemented in the parser should be assumed; do not treat arbitrary downloader metadata as clean or verified.

### 5.3 Archive protections

As of the verified code:

| Boundary | Implemented limit |
|---|---|
| Input novel ZIP compressed file size | 120 × 1,024² bytes |
| Embedded `source.epub` | 120 × 1,024² bytes |
| `metadata.json` or `chapters.json` uncompressed member | 12 × 1,024² bytes each |
| Outer ZIP entries | 30,000 |
| Outer ZIP aggregate expanded content | 2 GiB |
| EPUB entries | 20,000 |
| EPUB aggregate expanded content | 512 MiB |
| Individual member's expansion ratio | 10,000:1 |
| EPUB `container.xml` | 1 MiB |
| EPUB package metadata XML | 8 MiB |

`validate_zip_budget` runs **before** expensive outer ZIP CRC validation (`testzip`). It rejects unsafe member paths with traversal components, absolute paths and encrypted members, alongside abnormal entry counts, expanded sizes and ratios. The outer archive is CRC-checked before further parsing. `sha256_file` streams the file in 1 MiB chunks instead of reading the entire ZIP just to calculate a digest.

These checks reduce exposure to archive bombs; they are **not** a substitute for careful resource budgets on every new ZIP-consuming path. `covers.py` and the historical genre-repair parser have different parsing and limit implementations; do not assume `validate_zip_budget` automatically covers those modules.

## 6. Novel matching and planning

### 6.1 Identity matching algorithm

`upload.matching_entry(books, meta, epub)` follows these rules:

1. Calculate `sha256(epub)[:24]` and find a catalogue entry with exactly that ID.
2. If found, match with reason `epub-id`.
3. Otherwise normalise the incoming title using Unicode NFKC, case-folding and word extraction via `core.normalized_title`.
4. Find catalogue records whose normalised title matches.
5. If no title matches, classify as a potentially `new` novel.
6. If exactly one title and exactly one matching normalised **author** exist, match with reason `title-author`.
7. Otherwise raise a `CONFLICT` requiring manual review.

The normal novel uploader **does not** use source URL as its matching key. This differs from cover matching and genre restoration.

**Failure cases to consider:**

- Different novels sharing a title but with different authors.
- A title changed at the same time the EPUB bytes changed.
- Multiple local ZIPs resolving to the same stored ID.
- An existing archivePath/epubPath pointing outside the canonical book directory.
- An orphaned ZIP or EPUB that exists without a catalogue entry.
- A novel whose original ZIP matches but whose stored EPUB or metadata does not.

Do not bypass a collision simply because the owner likely intended a certain title. Surface the ambiguity.

### 6.2 Planning statuses

`upload.plan` produces one item for each local ZIP:

| `state` | Meaning |
|---|---|
| `NEW` | No safe existing match and no conflicting remote target paths |
| `UPDATE` | Safe matched novel, but at least ZIP, EPUB or source-managed metadata differs or cannot be verified |
| `UNCHANGED` | Archive digest, EPUB digest, merged metadata and canonical archive path all match |
| `CONFLICT` | Unsafe/ambiguous identity, inconsistent canonical paths, or duplicate local targets |

The main entrypoint **aborts the entire batch** if any planned item is `CONFLICT`; it does not proceed with otherwise valid items in that input batch. A validation failure in any supplied local ZIP also blocks remote writes.

### 6.3 Why two remote hashes matter

A former bug treated a matching `original.zip` digest plus existence of `source.epub` as proof the novel had not changed. That was unsafe: the EPUB could be missing the right bytes and the catalogue metadata could have drifted. Current code compares:

1. SHA-256 of the stored `original.zip`.
2. SHA-256 of the stored `source.epub` against the local ZIP's embedded EPUB.
3. The current metadata against `merged_metadata(old, incoming, ID)`.
4. Canonical catalogue archive path.

**Agent invariant:** Do not restore the old ZIP-only equality shortcut. Tests should explicitly cover matching ZIP + corrupt EPUB and matching binaries + stale catalogue metadata.

### 6.4 Performance choice

Preview downloads and hashes only those remote ZIP and EPUB paths that correspond to the novels in the **local input batch**. It does not download the entire existing library to compute all hashes. For the selected novels it still downloads the full artifacts to verify bytes, which can be expensive. Any optimisation must preserve correctness for both EPUBs and archives; mere file existence is insufficient.

## 7. Applying novel changes

The public command is:

```powershell
py -m taiyou_storage.upload novels                  # Preview-only
py -m taiyou_storage.upload novels --interactive    # Preview and type YES
py -m taiyou_storage.upload novels --apply          # Explicit noninteractive write
py -m taiyou_storage.upload novels --repo OWNER/PRIVATE-DATASET
```

Use `--recursive` only when scanning nested folders is intended. The Windows `01_bulk_upload.cmd` launcher runs `--interactive`, keeping the approved preview and application in one process instead of running a second independent planner after confirmation.

### 7.1 Write sequence (`upload.main` and `apply_item`)

1. Parse **all** local ZIPs and fail if any are invalid.
2. Read current private dataset catalogue and SHA, or verify a genuinely empty new private dataset.
3. Select and hash the relevant remote binary paths.
4. Build and print the complete plan; block conflicts.
5. With `--interactive`, require a console and exact `YES`.
6. Require a Hugging Face access token for writes.
7. Recheck that the remote revision still matches the preview.
8. For every `NEW` or `UPDATE`, re-read the latest pinned catalogue and verify stable identity and paths.
9. Recompute the local ZIP digest; reject an archive changed since preview.
10. Compare remote binary digests and merged metadata again.
11. Submit only needed ZIP/EPUB additions plus the modified catalogue with `parent_commit` equal to the expected SHA.
12. Read the new 40-hex commit object ID from the Hub response, and use it as the expected revision for the next item.

The user may see `[NEW]`/`[UPDATE]` in the preview and `[NEW]`/`[UPDATED]` or `[UNCHANGED]` during application. Do not infer that the dataset changed simply because a preview says `UPDATE`; verify an actual successful commit.

### 7.2 Optimistic concurrency and uncertain outcomes

When an explicit `expected_revision` is supplied, `apply_item` refuses a different revision and does **not** retry by silently rebasing the user's approved plan. The helper has a legacy direct-call retry path for 409/412 conflicts only when `expected_revision` is absent; do not remove revision guarantees from the normal user-facing batch flow.

A successful HF commit without a valid 40-character commit SHA in its response is treated as an uncertain outcome: the process stops and instructs a new preview. **Do not retry a potentially successful write blindly.**

### 7.3 Partial completion

Two novels in a batch are two commits, not one combined transaction. If the first succeeded and the second fails, the first is retained. The safe recovery procedure is:

1. Leave the dataset alone; never clear it as a response to a partial failure.
2. Re-run the **preview** against the latest private revision.
3. Confirm successfully committed novels now classify as `UNCHANGED`.
4. Resolve any changed local input or conflicted ID.
5. Apply only what the updated plan says is needed.

This reconciler pattern is a core design principle throughout the repository.

