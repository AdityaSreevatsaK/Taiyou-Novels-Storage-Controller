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


## 14. Windows launcher catalogue

For an AI agent asked to "add an option to the menu" or "fix the CMD", first inspect both the launcher and its Python entrypoint. CMD is only an interface; the real business rules belong in Python.

| File | Effective behaviour | Safety notes |
|---|---|---|
| `00_storage_menu.cmd` | Main Windows selection menu | Only working choices are shown; do not imply every numbered launcher is implemented |
| `01_bulk_upload.cmd` | Calls `python -m taiyou_storage.upload novels --interactive` through the Windows `py` launcher | Keeps preview and YES prompt in one process |
| `02_download_all.cmd` | Calls `taiyou_storage.cli download` | Downloads original ZIPs locally; does not erase cloud copies |
| `03_list_novels.cmd` | Calls `taiyou_storage.cli list` | Produces a local CSV containing private titles |
| `04_detect_conflicts.cmd` | Calls `taiyou_storage.cli conflicts` | Reports duplicate titles but does not merge them |
| `05_verify_integrity.cmd` | Placeholder | Do not advertise as a complete verification tool |
| `06_sync_status.cmd` | Calls `taiyou_storage.cli status` | EPUB-derived ID presence only, not full checksums |
| `07_backup_catalogue.cmd` | Calls `taiyou_storage.cli backup` | Backups only the catalogue, not all novel files |
| `08_restore_novel.cmd` | Placeholder | Do not advertise automatic restore |
| `09_delete_novel.cmd` | Placeholder | Do not replace with a full dataset reset |
| `10_upload_covers.cmd` | Detects/prompts for a cover ZIP and invokes `covers --interactive` | Uses safe path quoting and one-process human confirmation |
| `11_clear_hf_data.cmd` | Runs reset preview; then asks whether to initiate backup-first reset | Uses separate prompts and the Python reset's additional checks |

Use `py -m ...` on Windows where the launchers do so. On Linux CI, `python -m ...` is normal. On Windows, use `python -m pip` or `py -m pip` rather than assuming Unix shell semantics.

If modifying a launcher, preserve exit-code propagation, quoting for paths with spaces and surrounding double quotes, working-directory behaviour, and the clear distinction between preview and apply.

## 15. GitHub Actions architecture and safety boundaries

### 15.1 Workflow index

| Workflow file | Trigger | What it does |
|---|---|---|
| `.github/workflows/ci.yml` | Push to `master`, pull requests, manual dispatch | Offline Python test matrix, compile, dependency checks |
| `hf-inspect.yml` | Manual `workflow_dispatch` | Read-only private dataset inspection; prints counts only |
| `hf-private-backup.yml` | Manual | Copies and verifies private snapshot into a separate private HF dataset |
| `hf-private-reports.yml` | Manual | Writes sensitive reports to a separate private HF dataset |
| `hf-upload-covers-artifact.yml` | Manual with run ID and apply checkbox | Imports cover-only artifacts from Novel_Library |
| `hf-restore-genres.yml` | Manual with apply checkbox | Independent historical genre repair |
| `release.yml` | Completed successful `master` push CI workflow | Creates a guarded version tag and public code-only GitHub Release |
| `prune-reviewed-branches.yml` | A push to `master` changing **that exact workflow path** | Historical, allowlisted one-shot removal of audited merged branches |

There is **no active backup-free cloud-clearing workflow**. The old `hf-clear-data.yml` was deliberately deleted. Avoid reintroducing broad destruction capabilities through a new filename or different module.

### 15.2 Workflow least privilege

- Read-only Actions use `permissions: contents: read` unless explicitly justified otherwise.
- The release publisher needs `contents: write` to create tags and releases, but should never have HF secrets.
- The historical branch-cleanup workflow needs `contents: write` only for its narrowly allowlisted GitHub ref deletions. It has already run successfully as part of the project history; it should not be turned into a generic cleanup command.
- Private HF workflows receive secrets only in the relevant job steps.
- Avoid uploading `data/library.json`, CSV title lists, novel ZIPs, EPUBs or cover images as **public** Actions artifacts.
- Do not print raw exception payloads from APIs that might include private paths or authentication details; `actions.py` deliberately reduces exception logging.
- Workflows sharing `concurrency: group: hf-storage-controller` serialise certain manual HF activities, reducing simultaneous writes from that workflow group. This is **not** a global mutex against local scripts, other repos, the reader app or direct HF clients. Keep optimistic concurrency in application code.

### 15.3 Actions dependencies

`requirements.txt` uses `-c constraints.txt` so the tested Hugging Face Python dependency versions resolve consistently. Current `constraints.txt` pins the tested `huggingface_hub` and dependencies. GitHub Actions `uses:` references are pinned to immutable full commit SHAs (with comments showing the associated major tag).

Changing any pinned dependency must be intentional, with a passing multi-platform CI run. Blindly replacing pinned SHAs with mutable tags weakens reproducibility. Never assume a new major library version is API-compatible simply because `pip install` succeeds.

## 16. CI and automated testing strategy

### 16.1 Basic commands

```powershell
py -m pip install -r requirements.txt
py -m pip check
py -m compileall -q taiyou_storage tests
py -m unittest discover -s tests -v
```

The GitHub Actions matrix in `ci.yml` is:

- `ubuntu-latest` × Python `3.11`
- `ubuntu-latest` × Python `3.12`
- `windows-latest` × Python `3.11`
- `windows-latest` × Python `3.12`

**Verified milestone:** The `v0.1.0` branch history passed **87 offline tests** per environment. The test total is a historical fact, not a hard-coded target; new regression tests should increase it.

### 16.2 Test map

| Test module | Responsibilities |
|---|---|
| `tests/test_core.py` | Catalogue validation, normalised titles, CSV/conflict logic, remote load behaviour |
| `tests/test_upload.py` | Novel parsing, identity collisions, metadata preservation, unchanged/repair planning, guards against changed previews, ZIP budgets |
| `tests/test_covers.py` | Cover manifest formats, nested artifact ZIPs, source/title matching, safe image validation, preview and cancellation |
| `tests/test_cover_batches.py` | Batch sizing, atomicity, idempotence, interrupted/resumable cover uploads, 409/412/429 handling |
| `tests/test_reset.py` | Path validation, backup/reset preconditions, revision drift, private dataset requirements |
| `tests/test_actions.py` | Safe public Actions outputs, private backup/report checks, absence of backup-free clearing |
| `tests/test_genre_repair.py` | Genre filtering, source matching, add-only catalogue restoration safeguards |
| `tests/test_smoke_integration.py` | End-to-end synthetic novel uploads, EPUB repairs, cover-batch resume and reset-preview safety |

### 16.3 Synthetic end-to-end simulation

`tests/test_smoke_integration.py` contains a `FakePrivateHub` with:

- In-memory immutable snapshots, each identified by a different SHA.
- Revision-aware `dataset_info` and `list_repo_files`.
- Synthetic cached downloads from each revision.
- `create_commit` applying staged additions and rejecting stale `parent_commit` values.
- Controlled failure injection between cover batches.
- Synthetic ZIP/EPUB contents and simple cover images.
- Real CLI entrypoints invoked against mocked Hub integration points.

This is valuable because it tests **the whole flow between CLI, planners and revision checks**, not only individual helpers.

**Caveat:** The fake Hub cannot prove every live Hugging Face API behavior, authorisation nuance, network failure or Git LFS interaction. Never call a mock-only pass a production end-to-end certification.

### 16.4 Minimum regressions before merging

For **novel uploader changes**, cover at least:

- Brand-new private dataset initialisation.
- Existing book matched by stable ID.
- Same book with a newly generated EPUB but stable old ID.
- Same ZIP digest with corrupted or missing remote EPUB.
- Same ZIP and EPUB with stale source-managed catalogue metadata.
- Preservation of user progress, personal tags, ratings, notes and existing nonempty source genres.
- Two inputs targeting one existing book.
- Title collision with different/ambiguous authors.
- Changed local ZIP between preview and commit.
- Changed remote SHA between preview and commit.
- Multi-novel partial failure/re-preview reconciliation.
- Refusal of public or unknown/orphaned datasets.
- Archive count, expanded-byte, ratio and path-validation guards.

For **cover changes**, cover:

- NovelFull-style manifest, `results` manifest and outer ZIP wrappers.
- Exact source URL match, allowed unique-title fallback and ambiguous duplicate rejection.
- `NEW`/`LINK`/`UPDATE`/`UNCHANGED`/`MISSING`/`CONFLICT` statuses.
- Multiple covers for one book blocked.
- Changed bytes versus same remote bytes.
- Atomic binary+catalogue updates and no commit for unchanged covers.
- Multi-batch success, injected failure and rerun/resume.
- Long 429 stops, short 429 retries once, 409/412 abort.
- Missing/private/public dataset checks.
- Preview and interactive cancellation do not write.

For **reset/backup changes**, cover:

- Only proper `data/` paths can be selected for deletion.
- Path traversal and duplicate entries rejected.
- Revision and path inventory drift aborts deletion.
- No remote delete without verified backup and interactive confirmations.
- Incomplete/corrupted backup prevents delete.
- No GitHub Actions backup-free clearing workflow.
- Public backup repositories rejected.
- Only private reports generated, without sensitive CI output.

### 16.5 Additional live testing

**Operational advice:** A separately created **disposable private HF dataset** is suitable for live integration smoke testing *only when explicitly authorised*. Use synthetic novels and covers, an explicit `--repo` override, and a token restricted to the test dataset where possible. Confirm repo ID and privacy before every write.

Do **not**:

- Point a generic test's default dataset at production.
- Use the real private novel collection as test fixtures.
- Share real catalogue metadata in CI artifacts.
- Delete or reset production after a transient bug.
- Claim the public GitHub Actions inspect workflow can test live writes; it is read-only.

## 17. Release and maintenance lifecycle

### 17.1 Versioning

`VERSION` stores a plain version such as `0.1.0`. `CHANGELOG.md` and `docs/releases/vX.Y.Z.md` record public, code-only changes.

The **first formal release is `v0.1.0`**. Versioned tags use `vMAJOR.MINOR.PATCH`. The repository's release publisher runs only after a completed successful **push-triggered CI on `master`**, verifies the tested commit remains the current master SHA, checks the release notes exist, and refuses to move an existing tag to a different commit.

The release process deliberately publishes **no novel or cover assets**.

### 17.2 How to prepare a new version

1. Implement and test code on a feature/fix branch.
2. Update `VERSION` only when a new release is genuinely intended.
3. Add a corresponding section to `CHANGELOG.md`.
4. Add `docs/releases/vX.Y.Z.md` containing safe-to-publish notes.
5. Open a PR; let Windows/Linux Python CI pass.
6. Merge when authorised.
7. Verify the **exact merged master SHA** passes CI.
8. Verify the publisher creates the expected annotated tag and GitHub Release.
9. Confirm no sensitive data was attached.

If GitHub runners are queued, say that validation/release is **pending**, not successful. If the publisher fails after a tag is written, investigate the exact state before retrying; never force-move a release tag.

### 17.3 Branch hygiene

Past one-shot maintenance pruned merged and obsolete branches, leaving only `master` at the time of this documentation audit. A branch may still have technically unique history after a squash merge even when its changes are incorporated; use the **merged PR's exact recorded head SHA, current branch SHA and net diff** when deciding safety.

**Operational advice:** Preserve any branch with unmerged useful changes, active PRs, ambiguous ancestry, altered SHA or protected status. Do not repurpose the historical `prune-reviewed-branches.yml` as a broad recurring deletion job. Delete only branches specifically reviewed and proven redundant.

## 18. Operational failure reference

| Symptom / message | Likely condition | Safe first action |
|---|---|---|
| `Dataset is not private` | Wrong HF repo, insufficient access or public dataset | Verify repository ID, token permissions and private flag; do not write |
| `data/library.json` missing while `data/` contains files | Orphaned/unrecognised dataset | Stop; inspect and back up rather than initialising blindly |
| `CONFLICT: title exists...` | Ambiguous title/author matching | Review identities and source metadata manually |
| `CONFLICT: multiple local ZIPs...` | Two files target one stable ID | Remove the duplicate from that import batch after review |
| `UNCHANGED` despite a user complaint | Plan verifies same source bytes/metadata, but complaint may concern reader/app | Inspect reader behaviour; do not force a full dataset reset |
| `UPDATE` for same ZIP | EPUB or metadata differs, or matching remote artifact could not be verified | Inspect plan and preserve personal data; selective repair may be correct |
| `Local ZIP changed after preview` | Input changed while awaiting approval | Re-run preview on the final ZIP; no blind commit |
| `Dataset changed since preview` | Concurrent writer or app updated dataset | Re-fetch and re-preview; do not rebase the old approved plan |
| `Remote identity changed since planning` | Current catalogue no longer safely matches original plan | Stop and review ID/title/author; avoid creating duplicates |
| Missing EPUB with matching original ZIP | Corrupt/incomplete remote state | Let reconciling uploader replace only the EPUB and catalogue when safe |
| Cover `MISSING` | Cover has no matching existing book | Import the novel first or correct its source URL |
| Cover `CONFLICT` | Ambiguous title/URL or unexpected coverPath | Resolve identity; no partial writes should occur for a conflicted plan |
| Cover 429 with long wait | HF commit quota exhausted | Stop, let quota recover externally, re-run same ZIP later |
| Cover batch N fails after earlier batches | Partial completion across commits | Re-preview and resume, preserving already committed earlier batches |
| User cannot see uploaded cover | Reader or gateway does not yet serve `coverPath` properly | Inspect reader project; controller storage alone is not UI display |
| Genre repair reports missing sources | Historical GitHub artifacts expired or inaccessible | Diagnose token/artifact availability; never guess genres |
| `NOVEL_LIBRARY_ACTIONS_TOKEN` missing | Cross-repository artifact permission not configured | Configure appropriately if the user wants genre/cover artifact workflows |
| HF cache symlink warning on Windows | Cache is functional but may use extra space | Treat as cosmetic; launcher may suppress warning |
| Reset preview lists many files | All of `data/` will be affected by full reset | Cancel unless the user explicitly intends full backup-first deletion |
| Reset refused because remote SHA changed | Concurrent changes during backup/approval | Keep backup and re-evaluate the new dataset revision |
| CI queued | Hosted GitHub runner scheduling delay | Check run state; never claim success while queued |
| CI green but live operation fails | Differences between mock and real HF behaviour | Debug against disposable private test dataset, not production |
| Release tag absent | Release workflow not yet completed or failed | Check master CI and publisher run; do not create misleading links |

### 18.1 Information to gather when debugging

Prefer a **sanitised** report containing:

1. Which command or workflow was invoked and with what *nonsecret* flags.
2. Whether it was preview or apply mode.
3. Approximate number of novels/covers affected, not private titles.
4. The sanitized error class and stable code/message.
5. Whether a remote commit was confirmed before the error.
6. The repository branch/commit SHA (GitHub code only).
7. Relevant test case names and CI platform/version.
8. Whether the issue reproduces on a synthetic private test dataset.

Do not request private user content when a synthetic fixture or count-only report is enough.

### 18.2 Order of troubleshooting

```text
Is the action read-only or mutating?
       |
       +-- Read-only --> confirm repo identity, token, schema, revision
       |                     |
       |                     +-- fail --> inspect error safely; no write needed
       |
       +-- Mutating  --> verify explicit authorisation, backup needs,
                           target privacy, preview and current revision
                                  |
                                  +-- identity/metadata ambiguity --> stop
                                  |
                                  +-- remote drift --> re-preview
                                  |
                                  +-- partial success --> reconcile, do not reset
                                  |
                                  +-- genuine code regression --> reproduce offline,
                                                               add test, fix in PR,
                                                               confirm CI
```

## 19. Security, privacy and threat model

### 19.1 Assets to protect

- Private novel EPUBs and original ZIP archives.
- Cover image files and manifests where provenance or licensing matters.
- Catalogue entries, source identifiers and any user-managed metadata.
- HF credentials and GitHub Actions cross-repository tokens.
- Backup snapshots and private CSV reports.
- Reader-facing links between stable IDs and stored assets.
- The ability to recover from failed operations without erasing a library.

### 19.2 Risks and implemented mitigations

| Risk | Mitigation | Remaining concern |
|---|---|---|
| Accidental full cloud deletion | No public clear Action; local verified-backup reset with confirmations | The local reset remains deliberately destructive |
| Public exposure of private data | HF private dataset checks; private backup destination; suppressed public workflow logs | CLI output/files may contain titles; users must not publish them |
| Unexpected local archive contents | Size/count/expanded-data/CRC checks and traversal rejection | New ZIP-consuming code paths need their own safeguards |
| Duplicate/wrong book selection | Conservative ID/title/author match, cover URL match, conflict abort | Changed title+EPUB and ambiguous metadata still require manual review |
| Concurrent writes | Pinned revisions and `parent_commit` | Independent writers can race; app-level locking is not global |
| Silent corruption reported unchanged | Separate ZIP+EPUB+metadata checks | Full remote verification costs network bandwidth |
| HF quota exhaustion | Cover batching, bounded 429 retry, stop/resume | No guarantee of unlimited commits or free capacity |
| Supply-chain drift | Tested constraints and pinned Actions commits | Dependency updates still require review |
| Public CI leaking secrets | Environment secrets, no private artifacts, counts-only reports | Logs and exception handlers must remain conservative |
| Uncertainty after failed commit | Stop on malformed response/ambiguous outcome, re-preview | A failure can occur after a successful remote commit |

### 19.3 Privilege separation

A reader may require only read access through its own gateway, whereas a storage controller doing uploads needs scoped write access, a backup workflow may need write access to a different private repo, and historical genre repair needs GitHub artifact read access. Do not use an all-powerful token as a shortcut if a narrower token is possible.

### 19.4 Threat model limits

This controller is not a sandbox for executing untrusted novels or external binaries, an antivirus, or a comprehensive media parser. ZIP and image byte checks mitigate known malformed-file cases but cannot prove an input is harmless. Never run scripts embedded in novel downloads.

## 20. Concrete change playbooks for future agents

### 20.1 General development procedure

**Before editing:**

- Read the latest owner request, this file, README, related code/tests and relevant workflows.
- Fetch current `master` SHA and open PRs, and confirm the requested work has not already been merged.
- Identify exactly which component owns the requested behaviour (retriever, controller, reader, dataset).
- Write down invariants, affected file formats, privacy implications and failure/rollback semantics.
- Decide whether a live dataset operation is necessary. Default: **no**.

**During implementation:**

- Work on a clearly named separate branch for nontrivial changes.
- Make the smallest compatible change that fixes the problem.
- Keep mock/offline behaviour and existing working paths intact.
- Add regression tests for the original failure and at least one negative safety case.
- Avoid broad refactors, incompatible schema changes and unrelated workflow edits.
- Never put credentials, private archives or real catalogue exports into commits or PRs.

**Before merging:**

- Verify the changed branch head and current base SHA.
- Run compile checks and complete Python tests; require the intended CI matrix to pass.
- Read the PR diff, including any deleted security guards or changed GitHub Actions permissions.
- Distinguish simulated integration from genuine live HF testing in your report.
- Merge only when permitted by the owner's current request.
- Check the merged commit's CI run rather than relying solely on pre-merge tests.
- Update README, docs, version and release notes as applicable.

**After merging:**

- Report PR/commit, tested combinations and any remaining uncertainty.
- Do not claim an automation, tag, release or branch deletion succeeded before checking GitHub's actual result.
- Keep all HF production state intact unless a clearly scoped user-approved action was actually executed.

### 20.2 Adding a new local management command

1. Specify whether it is read-only, local-only, write-to-private-HF or destructive.
2. Add the Python command to `cli.py` or a dedicated module as appropriate.
3. Apply catalogue validation and privacy checks.
4. If it writes, support preview-first and optimistic concurrency.
5. Reuse safe path handling, streaming reads and report output.
6. Write unit and integration tests.
7. Add a Windows launcher only when the feature works.
8. Update `00_storage_menu.cmd` and README; do not show placeholders as functional.

### 20.3 Adding single-novel deletion (not yet implemented)

This would be a **new design task**, not a simple alias for `reset.py`:

- Define the owner and approval workflow, including what “delete” means for app and backup state.
- Identify the exact stable ID and all its referenced assets.
- Detect other references, shared data and potential orphan paths.
- Preserve personal data until an explicit deletion request and suitable backup/recovery plan exist.
- Preview the exact deletion set and require deliberate confirmation.
- Commit catalogue and file removals atomically, with a revision guard.
- Test that no unrelated novel is touched.
- Verify reader cache/synchronisation effects in the separate app project.

Do not implement it without explicit task approval.

### 20.4 Adding full restore (not yet implemented)

A restore workflow would need to validate the backup manifest, source identity, target dataset privacy, completeness, exact paths and SHA-256s before committing. It must define conflict handling for a nonempty target, rollback strategy, and revision checks. A mere download of `library.json` is not a full restore.

### 20.5 Supporting new downloader formats

- Obtain a synthetic sample with the same directory/manifest structure but without copyrighted content.
- Keep the original NovelFull-compatible format working.
- Add schema/size validation and cross-repo compatibility tests.
- Never guess identity or tags based on an unfamiliar manifest.
- Decide whether source metadata fields belong in the source-managed or user-managed layer.
- Coordinate any format changes with the separate Novel_Library repository.

### 20.6 Optimising remote downloads

Do not skip EPUB hashing to save bandwidth; that would recreate a known integrity defect. Consider only optimisations with verified equality semantics, such as a trustworthy immutable content digest source, caching keyed to a pinned revision, and a fallback path when a digest is unavailable. Cover and ZIP integrity must remain defensible.

### 20.7 Changing GitHub Actions

- Verify manual dispatch versus automatic triggers.
- Limit repository permissions and secrets by job/step.
- Preserve private catalogue/output confidentiality.
- Make apply intent explicit, never a default side effect.
- Avoid separate preview/apply runs silently relying on a stale approval plan.
- Confirm no change can delete the dataset without verified backup and explicit consent.
- Pin reviewed Action commits; test the resulting workflow behavior.
- Do not repurpose release/branch-pruning workflows for unrelated automation.

## 21. Design decisions and historical lessons

These are implementation lessons preserved from the repository history, not a list of currently open bugs:

1. **A ZIP can match while its EPUB is corrupted.** Hash ZIP, EPUB and verify metadata before `UNCHANGED`.
2. **Per-cover commits can hit quotas.** Group small updates into atomic, revision-guarded batches.
3. **A failed later batch must be resumable.** Re-preview the current dataset, do not blindly restart all commits or reset the library.
4. **Manual preview and application can drift.** Windows launchers use one-process confirmations; application still checks dataset revisions.
5. **An empty dataset is not the same as a missing catalogue over unknown existing data.** Guard initialisation.
6. **Source metadata and reader personal metadata coexist.** Preserve user fields and nonempty restored genres.
7. **Public GitHub workflows are the wrong place for detailed private catalogue output.** Use count-only logs and private HF report destinations.
8. **Backup-free clearing is unacceptable.** Use local verified-backup-first resets.
9. **Historical artifact data is incomplete and expires.** Genre repair must be additive and conservative.
10. **Mocks and Linux tests alone are not sufficient.** Keep both Windows and Linux Python CI and clearly separate live HF smoke testing.
11. **CI queue does not imply CI success.** Check final job conclusions and exact tested commit before publishing versioned releases.
12. **Squash-merged branches can have unique commit history but no unique useful changes.** Evaluate merged PR evidence before branch deletion.

## 22. Known limitations and non-implemented functionality

As observed in current source and documentation:

- Full single-book cloud deletion is not implemented in this repository.
- Automatic single-book restoration is not implemented.
- Automatic full dataset restoration is not implemented.
- Placeholder launcher `05` is not a complete whole-library integrity scanner.
- `cli status` only compares EPUB-derived IDs; it is not full remote byte verification.
- A multi-novel import or multi-batch cover job can partially succeed across commits.
- Novel matching cannot reliably recognise every simultaneous title/EPUB rename.
- Source metadata and personal state require coordination with the separately deployed reader.
- Uploading a cover to private storage does not itself guarantee the reader renders that cover.
- The reader's web-upload size limits and deployment configuration are outside this repository.
- The genre restoration workflow depends on external historical artifacts and cross-repository token configuration.
- There is no guarantee that expired historical GitHub artifacts remain available.
- Real Hugging Face API write behaviour has not been fully established by the offline CI suite.
- The project uses a version 1 catalogue; no independently versioned schema migration framework is implemented.
- There is no general-purpose central scheduler, distributed locking service or global transaction coordinator.

**Do not silently label any of these as implemented.** If a user requests one, scope it as a separate feature with tests, safety analysis and documentation.

## 23. Glossary

| Term | Precise meaning here |
|---|---|
| **Source ZIP** | Original pre-packaged local novel archive, generally produced by Novel_Library |
| **EPUB** | Reader-compatible publication container extracted from a ZIP and stored independently |
| **Catalogue** | Version 1 `data/library.json` mapping stable book IDs to metadata and blob paths |
| **Stable book ID** | 24-character lowercase hex key, originally derived from EPUB SHA-256 for a new book; preserved on later safe matches |
| **HF dataset** | Private Hugging Face Git repository storing the library, separate from the web reader |
| **Remote revision** | Full Hugging Face repository commit SHA used to pin reads and guard writes |
| **Optimistic concurrency** | Rejecting or stopping when `parent_commit`/expected revision no longer matches |
| **Source-managed metadata** | Title, author, genres, source URL, chapter count and similar fields derived from a novel package |
| **Personal metadata** | Reader/user-owned information such as progress, personal tags, ratings, reviews and notes |
| **`sourceTags`** | Source-site genres/categories extracted or historically restored |
| **`personalTags`** | User-defined app tagging metadata; distinct from `sourceTags` |
| **`coverPath`** | Catalogue metadata pointer to an image under the book's private dataset directory |
| **`NEW`** | Safely new novel or cover target |
| **`UPDATE`** | Safe matched target needs a change |
| **`UNCHANGED`** | Required digest, link and metadata checks pass for the relevant operation |
| **`LINK`** | Identical existing cover bytes need only a metadata pointer |
| **`MISSING`** | A cover has no matching existing novel |
| **`CONFLICT`** | Identity/path ambiguity requiring human review; no unsafe writes |
| **CRC** | ZIP member integrity check against the ZIP's stored checksum |
| **429** | Hugging Face rate/quota response; cover uploader only retries short bounded Retry-After once |
| **PR** | GitHub pull request, used for review and CI before merging |
| **Offline smoke test** | End-to-end execution against a synthetic private Hub simulation rather than real HF servers |
| **Private backup dataset** | Separate HF dataset destination for private snapshots and sensitive CSV reports |

## 24. Final agent checklist

Before claiming the Storage Controller task is finished, check each applicable box:

- [ ] I changed only this repository (unless the owner explicitly authorised another).
- [ ] I based decisions on the latest source and the specific relevant tests.
- [ ] I distinguished implemented facts from proposals and historical commentary.
- [ ] I have not changed or accessed the production private dataset unexpectedly.
- [ ] I preserved novel IDs, catalogue schema, personal data and existing source genres.
- [ ] I did not weaken private-dataset validation, archive checks or revision guards.
- [ ] I did not reintroduce backup-free deletion or uncontrolled release/cleanup automation.
- [ ] I maintained preview-only defaults and explicit write approval.
- [ ] I tested negative cases, partial failures and safe reruns where relevant.
- [ ] I kept novels, covers, personal data and all secrets out of public commits and logs.
- [ ] I verified the actual CI results for the exact branch/commit, not just the queued workflow.
- [ ] I have not claimed real HF live testing when only mock integration was performed.
- [ ] I kept READMEs, release notes and cross-repository contracts consistent with changed code.
- [ ] I supplied the actual merged PR/commit/release link only after verifying it exists.

---

### Provenance and update policy

This handbook was compiled from **the current contents of this GitHub repository**, including `taiyou_storage/*.py`, test suites, workflows, README files and the verified `v0.1.0` release. It is intentionally written with examples containing *synthetic* book names and data. It does **not** disclose the contents of the actual private Hugging Face dataset.

**Keep it current.** Any PR that changes a key path, data contract, CLI argument, security boundary, workflow, test architecture or release procedure should assess and update this document alongside the code. The code is authoritative when this explanatory file becomes stale.


## 25. Readable-folder layout and migration (added after v0.1.0)

For existing and new novels, use `taiyou_storage.paths` rather than hardcoding
`data/novels/<id>/...`. Both ID-only folders and validated
`data/novels/<id> - <sanitised-title>/...` are now supported. The folder
label is a historical display name and must not change automatically when
the novel is retitled. The stable 24-hex ID continues to own personal data.

New Storage Controller uploads use readable folders by default. The existing
`--legacy-new-folders` flag is a backwards-compatible opt-out.

**Production moves are a separate destructive-risk operation**, implemented
in `taiyou_storage.migrate_folders` and the gated
`taiyou_storage.migrate_production`. The normal folder migration CLI
only previews the production dataset and refuses direct production apply.
The manual production workflow additionally requires a successful real,
disposable private HF migration acceptance run, an actually deployed reader,
a complete verified snapshot in a **different private** dataset, unchanged
revision and explicit confirmation. Existing novel ZIP/EPUB/cover file copies,
deletes and catalogue edits are grouped into small atomic, revision-guarded
commits, and moved SHA-256 hashes are rechecked.

**Never claim the production dataset has been migrated solely because the
code or PR was merged.** Validate the actual HF dataset inventory after a
successful, explicitly triggered migration. A failure after some batches
requires re-preview and resume, not a full dataset reset.

See [the migration runbook](docs/READABLE_FOLDER_MIGRATION.md).
