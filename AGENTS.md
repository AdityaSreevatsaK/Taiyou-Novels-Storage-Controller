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


## 8. Cover import: input contract and validation

### 8.1 Supported inputs and sources

`covers.read_covers_zip` accepts:

- A ZIP file directly containing a manifest and the referenced images.
- The Novel Retriever's `Downloaded_Covers.zip` or `novel-cover-images.zip`.
- A GitHub Actions outer ZIP containing a single nested cover ZIP.
- A directory containing **exactly one** ZIP (not a directory full of unrelated archives).

The manifest must include exactly one file whose basename is `covers_manifest.json`. An image record is conceptually:

```json
{
  "title": "Synthetic Example Novel",
  "website": "NovelFull",
  "source_url": "https://example.org/novel/fictional",
  "cover_file": "NovelFull/synthetic-example.jpg"
}
```

The parser supports several manifest shapes: a single record object; an array; an object with one of `covers`, `novels`, `items` or `entries` lists; and the downloader's `results` format. For the `results` format, **only** rows with status `downloaded` or `skipped` are considered for importing. Rows with status `failed` are ignored rather than treated as missing-image failures. See `docs/covers_manifest.example.json` for a bundled illustration.

The `cover_file` is a path **inside** the ZIP, not a local filesystem path or an instruction to fetch an Internet URL. It must be relative, without backslashes or `..` traversal. Each referenced filename may appear at most once in the accepted manifest.

### 8.2 Cover archive and image limits

| Constraint | Implemented value |
|---|---|
| Total cover ZIP file size | 512 MiB |
| Nested cover ZIP declared expanded member size | 512 MiB |
| Image count / manifest records | Up to 2,000 |
| Manifest JSON uncompressed size | 8 MiB |
| Individual image size | 12 MiB |
| Sum of referenced uncompressed image sizes | 350 MiB |
| Supported extensions | `.jpg`, `.jpeg`, `.png`, `.webp` |
| Canonical remote extensions | `.jpg`, `.png`, `.webp` |

`covers.check_image` verifies basic file signatures and ending markers. It is a **lightweight byte-format sanity check**, not image decoding or malware scanning. For example, JPEG is required to begin with its expected marker and end with the JPEG end-of-image marker. Do not overstate the current image-verification strength.

### 8.3 Matching existing novels

`covers.source_key` normalises valid HTTP(S) source URLs for comparison by:

- Lowercasing the host and removing a leading `www.`.
- Keeping the source path (apart from a trailing slash) and query string.
- Rejecting unrecognised schemes or URLs without a valid host.

This normaliser is **not identical** to the one in `genre_repair.py`. Do not automatically unify them: identity and historical-artefact matching rules need deliberate, regression-tested decisions.

`covers.match_book` tries, in order:

1. Find a **unique exact normalised source URL**.
2. Reject if the URL resolves to multiple catalogue books.
3. Reject if a URL-matched book conflicts with another book matching the title.
4. If the URL does not match, permit a **unique normalised title** only if the book does not already specify a conflicting source URL.
5. A novel absent from the catalogue is `MISSING` and cannot receive a cover.
6. Multiple books with the same title are a `CONFLICT` without a safe URL match.

The manifest's `website` field is **not** an author field and must never be used to disambiguate title collisions as though it were an author.

### 8.4 Cover planning statuses

`covers.make_plan` returns:

| `status` | Meaning | User-visible action |
|---|---|---|
| `NEW` | No matching remote destination image and no existing cover link | Upload image and link it |
| `UPDATE` | Existing linked/destination cover bytes differ, or other safe replacement needed | Update destination and catalogue link |
| `LINK` | Identical destination image already exists but metadata has no matching `coverPath` | Update catalogue link without re-uploading bytes |
| `UNCHANGED` | Identical remote image and `coverPath` already point to it | Skip |
| `MISSING` | Input cover does not match any catalogue book | Report and skip; do not create book |
| `CONFLICT` | Ambiguous/inconsistent input or existing path | Abort entire upload before any commits |

Two cover records targeting the same book are a conflict, even if they have different image names. Missing covers are not silently created as new novels.

### 8.5 Cover preview CLI

```powershell
py -m taiyou_storage.covers "C:\Downloads\Downloaded_Covers.zip"
py -m taiyou_storage.covers "C:\Downloads\Downloaded_Covers.zip" --interactive
py -m taiyou_storage.covers "C:\Downloads\Downloaded_Covers.zip" --apply
py -m taiyou_storage.covers "C:\Downloads\Downloaded_Covers.zip" --batch-size 20 --commit-pause 2
```

By default:

1. Parse/validate all cover images.
2. Read the private catalogue.
3. Match covers and identify *only* relevant already-existing destinations.
4. Hash those remote images in streamed 1 MiB chunks.
5. Recompute `NEW`/`UPDATE`/`LINK`/`UNCHANGED`/`MISSING`/`CONFLICT` statuses.
6. Write a CSV report to `reports/cover-upload-plan.csv`.
7. Display the plan and stop without writing to Hugging Face.

With `--interactive`, prompt for exact `YES` in the same process. With `--apply`, opt into writing without an interactive prompt.

Before the first cover write, the CLI locally saves the original `data/library.json` under `backups/cover-upload-library-<UTC>-<SHA>.json`. This is a **catalogue backup**, not a guaranteed full dataset backup of every EPUB and cover.

The Windows `10_upload_covers.cmd` launcher handles paths with surrounding pasted quotes, can discover common cover ZIP paths, suppresses the harmless Windows HF cache-symlink warning, and calls `--interactive`.

## 9. Cover batching, concurrency and recovery

### 9.1 Why cover batching exists

Uploading one cover per Hugging Face commit led to repository-commit quota issues (HTTP 429) for sizeable libraries. `cover_batches.py` groups cover uploads so several images and their matching `library.json` edits share **one commit**. The default batch size is `20` covers, the maximum count is `40`, and the default byte budget is `48 MiB` per batch.

`group_batches(items, batch_size, max_bytes)` considers both image count and total covered bytes when building groups. This grouping is a runtime safety/performance decision, not a promise that an entire collection will always use an exact number of commits.

### 9.2 Transaction steps for one batch

`commit_cover_batch(api, repo, token, items, expected_sha)`:

1. Confirms the target dataset is private.
2. Confirms the current remote SHA matches the expected revision.
3. Downloads and validates the current catalogue at that revision.
4. Rematches the batch's cover images to the **current** catalogue and checks for missing/ambiguous records.
5. Downloads and hashes only destination covers that already exist.
6. Builds a refreshed plan and refuses changed IDs or destinations.
7. Validates the existing `coverPath` stays within the correct novel directory and has a permitted extension.
8. Adds only changed images; metadata-only `LINK` operations do not need a binary upload.
9. Adds a single updated `data/library.json` to the same commit as the changed images.
10. Calls `api.create_commit(..., parent_commit=expected_sha)` and reads the new revision SHA.

If every cover is truly unchanged, the function returns without committing.

### 9.3 Quota and concurrency behaviour

- **HTTP 429:** inspect `Retry-After`. A short, valid delay of up to **30 seconds** may be honoured **once**.
- **Long or unknown 429:** stop cleanly; do not retry indefinitely or sleep for an hour in CI.
- **HTTP 409/412:** treat as concurrent remote modification and stop rather than blindly overwriting.
- **Unknown response/commit outcome:** if the commit SHA is missing or malformed, stop, because the operation might already have succeeded.
- **Revision changed while waiting to retry:** stop and re-preview rather than treating a previous plan as current.
- **Pause between successful batches:** `upload_batches` defaults to **2 seconds**, configurable from 0 to 60.

### 9.4 Recovery after a partially completed batch sequence

Imagine 89 covers, with the first 36 imported successfully and an error on a later commit. The correct action is **not to reset the dataset**. Reuse the **same cover ZIP**:

1. Rerun the preview on the current private revision.
2. Previously imported covers should appear `UNCHANGED` if bytes and catalogue links match.
3. Remaining covers should appear `NEW`, `UPDATE` or `LINK`.
4. Resolve any conflict or changed catalogue identity before writing.
5. Restart the remaining safe batches.

This behaviour has dedicated regression tests in `tests/test_cover_batches.py` and end-to-end synthetic coverage in `tests/test_smoke_integration.py`. Do not regress the ability to resume after an interrupted sequence.

## 10. Read-only and local catalogue utilities

`taiyou_storage.cli` is a command-driven management CLI. It reads the private catalogue and writes **local output files** but does not edit the private cloud dataset.

```powershell
py -m taiyou_storage.cli list
py -m taiyou_storage.cli conflicts
py -m taiyou_storage.cli backup
py -m taiyou_storage.cli download
py -m taiyou_storage.cli status --folder novels
py -m taiyou_storage.cli --repo OWNER/PRIVATE-DATASET list
```

| CLI subcommand | Behaviour | Typical local output |
|---|---|---|
| `list` | Convert catalogue entries to a sorted CSV list | `reports/novels.csv` |
| `conflicts` | Find exact and normalised-title duplicates with distinct IDs | `reports/conflicts.csv` |
| `backup` | Download a revision-pinned copy of the catalogue only | `backups/library-<UTC>-<SHA>.json` |
| `download` | Download available original novel ZIPs from listed catalogue entries | `downloads/data/novels/<id>/original.zip` plus `downloads/manifest.json` |
| `status` | Derive EPUB hash IDs from local ZIPs and compare with current catalogue IDs | Prints `EPUB-ID-EXISTS` / `EPUB-ID-NEW` |

`core.rows` sorts rows by normalised title, then ID. `core.conflicts` detects exact and normalised-title duplicate pairs. This is **reporting**, not automatic record deduplication.

`core.local_epub_id` hashes the embedded EPUB. It does not compare an entire local ZIP to remote `original.zip` nor inspect actual remote EPUB byte equality. Its status output must not be misrepresented as a full integrity check.

**Local download detail:** The `download` subcommand writes to a `.part` staging file, renames it when complete, hashes the resulting local archive and records its digest. As implemented it downloads each listed remote original ZIP when invoked; it is not a resumable sync engine guaranteed to skip already downloaded files.

## 11. Full reset: destructive, local-only, verified-backup-first

### 11.1 This is a dangerous administrative function

`taiyou_storage.reset` can remove **all** files under `data/` of a chosen private Hugging Face dataset while preserving the HF repository itself and writing a valid empty `data/library.json`.

It must **never** be used as an answer to:

- A duplicate novel.
- A broken cover image.
- A single file that was downloaded onto the user's PC.
- A partial batch upload.
- A stale app cache.
- One missing chapter.
- A mismatch between the reader and the catalogue.

The three placeholder launchers `05_verify_integrity.cmd`, `08_restore_novel.cmd` and `09_delete_novel.cmd` do **not** implement safer alternatives. Do not tell the user otherwise.

### 11.2 Read-only preview

```powershell
py -m taiyou_storage.reset
```

The reset preview confirms private dataset access, records its current SHA, checks for `data/library.json`, selects a validated list of paths under `data/` and prints the affected paths. It performs no remote deletion and creates no backup until `--apply` is supplied.

Although this preview is read-only for the cloud, it **prints paths**, which may contain private identifiers. Do not copy its output into a public GitHub Actions log or public issue.

### 11.3 Full apply safety sequence

```powershell
py -m taiyou_storage.reset --apply
```

This operation:

1. Requires `hf auth login` / an accessible Hugging Face token.
2. Requires a **private** dataset and a valid SHA.
3. Requires an interactive terminal; it cannot be driven by the ordinary GitHub CI.
4. Requires the user to type the **full target dataset repository ID**.
5. Rejects symlinked backup roots.
6. Downloads **every validated path under `data/`** at the pinned SHA to `backups/before-reset-<UTC>-<SHA>/`.
7. Generates a manifest with each file's size and SHA-256.
8. Re-reads local saved files and verifies their sizes and SHA-256 digests.
9. Requires a second exact confirmation: `ERASE <file_count> FILES <revision_prefix>`.
10. Re-reads the remote dataset revision and file inventory; refuses if either changed.
11. Submits a single revision-guarded HF commit deleting the selected `data/` paths **except** the catalogue, then replacing `data/library.json` with `{"version": 1, "books": []}`.
12. Leaves files outside `data/` and the dataset repository itself intact.

`reset.select_data_files` validates path shapes, rejects duplicates and unsafe traversal, and caps the affected file count at **5,000**. `reset.backup_data` uses staged `.part` writes and streamed hashing.

### 11.4 Recoverability limitations

A successful local backup is necessary but not equivalent to an implemented automated restore procedure. **No automatic full restore exists.** HF Git/LFS history may retain old blobs after reset, but it must not be relied upon as the sole backup strategy.

**Agent rules:**

- Never add a one-checkbox, no-backup clear workflow.
- Never create a public GitHub Action that can delete the full HF dataset repository.
- Never change reset from interactive to non-interactive just for convenience.
- Never omit or weaken hash, path, revision or confirmation checks.
- Never run reset against the user's private production dataset as part of testing.

## 12. Manual GitHub Actions: inspection, backup, reports and covers

### 12.1 General privacy rule

This GitHub repository is public. GitHub Actions logs and artifacts can be visible to people who must **not** see the contents of the private novel dataset. All workflows with dataset access must treat both the novel files and the catalogue metadata as sensitive.

`actions.py` is deliberately narrower than `reset.py`: it supports only `inspect`, `report` and `backup`. There is **no** `actions clear` command. The former no-backup cloud deletion workflow was removed after a production-readiness audit.

### 12.2 `HF - Inspect library (read only)`

Entrypoint:

```bash
python -m taiyou_storage.actions inspect
```

The workflow supplies `HF_TOKEN` from the GitHub secret `HF_STORAGE_CONTROLLER_TOKEN`. `actions.inspect` obtains a private revision and validated path list, loads the catalogue, then emits **counts only**:

- Number of catalogue books.
- Number of files under `data/`.
- Number of novel directories and orphan directories.
- Number of duplicate normalised titles.
- Counts of missing EPUBs and original ZIP archives.
- Number of cover files.

If the catalogue is damaged, the inspection returns a restricted count-only error summary and the revision rather than dumping titles into public logs.

**Limit:** This is a lightweight catalogue/file-inventory check. It does not download and rehash every EPUB, inspect source chapters, or guarantee that the reader UI renders the collection correctly.

### 12.3 `HF - Back up entire dataset PRIVATELY`

Entrypoint:

```bash
python -m taiyou_storage.actions backup --backup-repo OWNER/PRIVATE-BACKUP-DATASET
```

The backup:

- Requires that the separate backup dataset ID is valid, **different** from the source and under the same HF account.
- Creates the destination only as **private**, if it does not already exist and the token permits creation.
- Refuses to use a public destination.
- Takes a source inventory pinned to a specific SHA, including files outside `data/` when present.
- Downloads files locally to a temporary folder, calculating sizes and SHA-256s.
- Uploads into `snapshots/<source_revision>/files/...` and an adjacent `manifest.json`.
- Re-lists the destination and re-downloads every backed-up file to compare its size and SHA-256.
- Verifies the uploaded manifest matches the source manifest.
- Prints count/revision information rather than private novel contents in public CI logs.

A backup workflow is **not automatically run before every other manual Action**. The full local reset still has its own independent verified-backup-first requirement.

### 12.4 `HF - Export novel names and conflicts PRIVATELY`

Entrypoint:

```bash
python -m taiyou_storage.actions report --backup-repo OWNER/PRIVATE-BACKUP-DATASET
```

This copies a timestamped report group under `reports/<UTC>-<SHA>/` in the **private backup dataset**, containing:

- `novels.csv`
- `conflicts.csv`
- `library.json`

Only counts are printed publicly. Do **not** convert this to a public GitHub Actions artifact or paste its private content into a public issue.

### 12.5 `HF - Upload covers from Novel_Library artifact`

The separate workflow `hf-upload-covers-artifact.yml`:

1. Accepts a Novel_Library **source GitHub Actions run ID**.
2. Downloads the `novel-cover-images` artifact using the configured GitHub access token.
3. Packages the source cover files into a local ZIP.
4. Runs the cover importer in preview mode, suppressing sensitive details from public logs.
5. Optionally invokes `--apply` when the workflow's explicit `apply_changes` input is true.

**Nuance:** The workflow invokes preview and apply as **separate CLI processes**, so the apply process recomputes and checks the current state; within batches, revision checks still protect consistency. Do not claim this workflow has the same single-process human confirmation semantics as the Windows CMD cover launcher.

### 12.6 Source, backup and artifact credentials

| Credential/environment key | Consumer | Responsibility |
|---|---|---|
| `HF_STORAGE_CONTROLLER_TOKEN` (GitHub Actions secret) | Manual HF workflows | Authenticate to private Hugging Face storage |
| `HF_TOKEN` | Python code running in Actions | Environment variable populated from the secret |
| `NOVEL_LIBRARY_ACTIONS_TOKEN` | Cross-repo artifact access and genre repair | GitHub token with read access to the relevant Novel_Library Actions artifacts |
| `HF_DATASET_REPO` | `cli.py`, `covers.py`, `reset.py` | Optional target override |
| `--repo` | Novel uploader and other applicable CLI entrypoints | Explicit target repository selection |
| `BACKUP_REPO` / `--backup-repo` | Private backup and report workflows | Distinct private backup dataset |
| Hugging Face CLI local login | Windows utilities | Local authentication; do not store credentials in repo files |

Never create or hard-code an actual token, secret string or credential in source, tests, documentation, logs or PR comments. If a workflow fails because of a missing secret, the code should not silently fall back to an unsafe public operation.

## 13. Historical source-genre restoration

### 13.1 Purpose and scope

`genre_repair.py` is an **independent specialised workflow**, not a normal step of each novel upload. It exists because older Novel_Library chapter-batch assemblies could lose source genres (`dc:subject`), status and sometimes descriptions. It tries to recover that source metadata from original GitHub Actions artifacts while preserving the existing catalogue and novel binaries.

The owner previously requested that an unrelated genre-restoration failure not be included in audit remediation. **Do not silently "fix" or execute this workflow during unrelated storage work**. This does not prevent documenting what the code currently does.

### 13.2 Data sources and identity

The repair reads:

- The private dataset's existing `data/library.json`.
- The upstream Novel Library registry at `RichardDaffern/Novel_Library`, `main/downloaded_novels.json`.
- Only eligible downloaded **first chapter-batch artifact metadata**, identified by historical run IDs and artifact names.

The artifact name pattern is `chapter-batch-<20-hex-source-hash>-<start>-<end>`. The code selects the earliest available matching range from a completed all-range registry record. It parses the artifact ZIP's `metadata.json` and embedded EPUB package metadata, **not full chapter prose**.

`genre_repair.source_key` normalises source URLs differently from the cover importer: host/path case-normalised, `www.` stripped, and query parameters not included. If refactoring, preserve the safety reason for matching exclusively on a **unique source identity** and add tests for URL corner cases.

### 13.3 Fields it may change

A conservative plan is created by `plan_repair`:

- If `sourceTags` is already nonempty, leave the entry alone.
- Skip missing/invalid source URLs.
- Skip duplicate source URL identities.
- Skip novel identities with no verified historical genres.
- Add `sourceTags` only when missing.
- Add a missing `description` only when a verified historical description exists.
- Add an absent `status` only when the verified historical status is `Ongoing` or `Completed`.
- Preserve all book IDs, archive paths, EPUBs, cover metadata, personal tags, progress, notes, reviews and ratings.

### 13.4 Applying and auditing

```powershell
py -m taiyou_storage.genre_repair           # Preview / count report
py -m taiyou_storage.genre_repair --apply   # Explicit private catalogue update
```

The code requires **both** `HF_TOKEN` and `NOVEL_LIBRARY_ACTIONS_TOKEN`, checks the dataset is private, computes only count-level public statistics, and refuses an intervening dataset revision change. A successful apply commits a backup of the previous catalogue at `backups/genre-repair/<UTC>-<SHA>.json` plus the updated `data/library.json`, without uploading/rewriting the EPUBs and original ZIPs.

Historical artifact expiry is a real limitation. Missing/expired artifacts are **not** grounds to invent genres based on titles or guessed website categories.

### 13.5 Dedicated tests

The relevant tests are in `tests/test_genre_repair.py`. They should cover noisy `dc:subject` filtering, source identity, duplicate safeguards, absent/expired artifacts, preservation of personal metadata and add-only updates. This feature should be changed only as a separately scoped request.

