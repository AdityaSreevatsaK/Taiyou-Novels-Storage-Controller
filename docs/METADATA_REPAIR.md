# Missing source metadata: audit and one-novel repair

Run `18_repair_novel_metadata.cmd` from the Storage Controller directory.
This tool works only with your **PRIVATE** Hugging Face dataset, and never
replaces any EPUB, original ZIP, cover, reading progress, personal tags,
ratings, reviews, collections or other personal metadata.

## Current publication-status support

The Controller accepts canonical **`Completed`**, **`Ongoing`**, **`Hiatus`** and **`Dropped`** source publication statuses. Reviewed aliases such as `on going`, `on hiatus`, `on hold` and `discontinued` are normalised to canonical spellings during metadata repair or verified page parsing. Unknown historical status strings in existing catalogue entries remain readable and are not rewritten. An unrecognised status in a new repair proposal is rejected.

Publication status describes the source novel, not the reader's personal completion state. Never infer it from chapter count, EPUB contents, progress, `completedAt`, genres or an unverified listing. The issue is a code/contract task and does not authorise changing any production novel's status.

## Use an existing research JSON for multiple novels

If you already have a metadata research package, for example the file
`novel_metadata_verified_patches_18.json` generated after reviewing the
19-novel missing-metadata audit, you do **not** need to run automated
discovery again.

1. Download the researched file privately, rename it
   **`metadata-batch-import.json`**, and put it in the local
   **`reports/`** folder of the Storage Controller. Do **not** commit
   the file to GitHub. The file uses this strict allow-listed structure:

   ```json
   {
     "version": 1,
     "items": [
       {
         "id": "aaaaaaaaaaaaaaaaaaaaaaaa",
         "sourceUrl": "https://freewebnovel.com/novel/example-book",
         "description": "A verified or independently researched summary.",
         "sourceTags": ["Fantasy", "Romance"],
         "status": "Completed"
       }
     ]
   }
   ```

2. Double-click **`18_repair_novel_metadata.cmd`** and choose
   **10: Import researched source metadata JSON**. No novel websites are
   queried during import. The controller matches every submitted ID with
   the existing private catalogue, checks its source URL is unique, and
   rejects fields already filled in. It rejects the *entire* file if any
   book identity or field is invalid.
3. Open `reports/metadata-batch-review.csv` and
   `reports/metadata-batch-candidates.json`. Imported suggestions are
   explicitly marked **`RESEARCH_REVIEW`**, not automatically verified.
4. Choose **6: Review and approve each imported novel** after checking
   its data against the original source. **Option 7: Approve all verified**
   deliberately does NOT approve manually imported research.
5. Choose **8: Preview**. The tool checks the exact candidate and approval
   file hashes and current private Hugging Face catalogue revision.
6. Choose **9: Apply**, review the change count and type
   `APPLY N` when prompted. The one commit updates only
   `data/library.json` and saves the previous catalogue to a **private**
   backup. No EPUB, original ZIP, cover or reading data is replaced.
7. Use **Refresh Cloud Library** in the app.

If a particular novel is absent from the research package (for example a
dead link), it remains untouched for later manual verification. The import
cannot infer missing source information and never overwrites any already
populated field. A *source listing* status may reflect availability on
that site, not the original novel's publication or translation status.

**Note:** Options 5 (live discovery) and 10 (researched JSON import) both
create a candidate review. The programme refuses to overwrite existing
candidate, approval or preview files. Finish the current review, or back
up and remove all three local files before starting a new one.

## Bulk repair multiple novels without re-downloading chapters

The Windows launcher also offers a separate multi-novel flow, designed for
an audit such as a 19-book missing-metadata report.

1. Update the Storage Controller from `master`. Double-click
   `18_repair_novel_metadata.cmd` and choose **5: Discover all**.
   The command reads your **private** live `data/library.json`, then attempts
   **one public book-information page per missing novel**. It never requests
   chapters, other books, mirrors or locked pages. It uses no login bypass,
   automated retries or private GitHub artefacts.
2. Inspect the local **`reports/metadata-batch-review.csv`**.
   Each book shows which fields are source-verified and which need manual
   review. For details, open the Git-ignored
   **`reports/metadata-batch-candidates.json`**. Source-site structural
   changes, blocked pages, mismatched titles/authors and absent fields are
   left unresolved, not guessed.
3. Choose **6: Review individually** to inspect and approve book by book,
   **or 7: Approve all verified** after reviewing the JSON/CSV. Option 7
   still requires a typed count-specific confirmation. Neither option writes
   to Hugging Face. All approvals are stored in
   `reports/metadata-batch-approvals.json`, tied to the current source
   candidates and dataset revision.
4. Choose **8: Preview**. The controller validates all approvals against
   the current *private dataset revision*, matching every book's immutable ID,
   exact source URL and still-missing fields. The reviewed plan is stored in
   `reports/metadata-batch-preview.json`; no cloud writes occur.
5. Choose **9: Apply**. Confirm with the exact phrase `APPLY N` shown
   on-screen. The controller rejects a stale or altered preview, then makes
   **one atomic, parent-revision-guarded HF commit** containing only an
   updated `data/library.json` plus a **private backup of the previous
   catalogue**, under `backups/metadata-repair/`.
6. Click **Refresh Cloud Library** in your reader.

All existing EPUBs, archive ZIPs, covers, chapter text, reading progress,
ratings, reviews and personal tags remain unchanged. This only fixes the
reader's indexed source metadata; older EPUBs and ZIPs are not rewritten.

**If a page or field is unresolved:** verify the source manually and use
the one-book repair (options 2–4) for that novel. No unverifiable metadata
is automatically inserted. In particular, no source status is inferred from
chapter count or historical upload completion.

**Important privacy rule:** the public code repository and its CI must never
contain real catalogue exports, novel titles from your private dataset,
metadata proposals, notes or tokens. Keep the generated reports and repair
JSON exclusively in the local, Git-ignored `reports/` directory.

### Advanced batch commands

```powershell
py -m taiyou_storage.metadata_batch discover
py -m taiyou_storage.metadata_batch review
py -m taiyou_storage.metadata_batch review --approve-all
py -m taiyou_storage.metadata_batch preview
py -m taiyou_storage.metadata_batch apply
```

Discovery normally finds all currently incomplete catalogue entries itself.
If you want to restrict it to a **fresh** audit CSV, put the CSV in
`reports/missing-source-metadata.csv` and use:

```powershell
py -m taiyou_storage.metadata_batch discover --targets reports/missing-source-metadata.csv
```

The CSV is used **only to select existing books**, never as authority for
their identity or metadata values. Discovery refuses to replace an existing
batch candidate/approval/preview. Back up and remove those local files before
starting a new batch, so earlier decisions cannot be silently lost.

The parser currently recognises public FreeWebNovel and NovelFull book pages.
Scribble Hub support is conservative and a missing/moved/access-blocked page
remains unresolved. Exact title and author must be verified, even if genres
appear in a sidebar. A structurally unsupported page never produces an
automatic repair candidate.

## First: audit your library (read only)

1. Run `18_repair_novel_metadata.cmd` and choose **1**.
2. A private local CSV appears in `reports/missing-source-metadata.csv`.
   It lists the novels missing a source synopsis (`description`), imported
   genre tags (`sourceTags`) or publication status (`status`).
3. Review the CSV. A missing field does **not** mean the original website
   actually provides it. Only add information verified from the novel's source.

The local `reports/` folder is Git-ignored. **Never commit** the CSV,
any repair JSON, a catalogue backup or personal information to the public
GitHub repository. GitHub Actions must not publish these files as artefacts.

## Repair one novel without downloading it again

1. Choose **2: Prepare JSON for one novel**. Enter the *exact* novel title
   or its unique 24-character ID. Paste the source's actual synopsis on
   one line, genre names separated by commas, and `Completed`, `Ongoing`, `Hiatus` or `Dropped`.
   Leave fields blank to keep them unchanged.
2. The tool saves **`reports/metadata-repair.json` locally**, with the
   novel's immutable ID and full source URL for double identity verification.
   It will **not** overwrite a previous draft: move/delete that draft
   after backing it up before preparing another.
3. Choose **3: Preview JSON**. The tool checks the private catalogue's current
   immutable revision, unique ID and exact source URL, as well as field types.
   It records the preview at `reports/metadata-repair-preview.json`.
   No cloud data is modified.
4. Choose **4: Apply previewed repair**. Review the listed additions, then
   type **`APPLY`**. If the patch or catalogue revision changed, the
   operation refuses to write and requires a fresh preview.
5. The controller makes *one* Hugging Face commit containing **only**
   `data/library.json` and an exact private pre-change backup under
   `backups/metadata-repair/`. It adds only previously missing fields.
   Existing nonempty source metadata cannot be overwritten.
6. Open the novel library app and use **Refresh Cloud Library**.

No source website, GitHub Actions artefact, chapter downloader or read-only
audit is needed to repair already obtained novel metadata. This process does
not alter the older source EPUB or original ZIP's embedded metadata; it updates
the catalogue fields read by the library application.

## Import a prepared repair JSON instead

Put a small file at `reports/metadata-repair.json` with this shape, where
the ID and URL match an existing **single** book:

```json
{
  "id": "aaaaaaaaaaaaaaaaaaaaaaaa",
  "sourceUrl": "https://freewebnovel.com/novel/example-book",
  "description": "Paste the verified source synopsis here.",
  "sourceTags": ["Fantasy", "Romance"],
  "status": "Completed"
}
```

Only `id`, `sourceUrl`, `description`, `sourceTags` and `status`
are permitted. Omit any field you do not want to fill; do not use empty
strings or empty arrays. Run **3: Preview** and **4: Apply**.

**Advanced commands:**

```powershell
py -m taiyou_storage.metadata_repair audit
py -m taiyou_storage.metadata_repair prepare
py -m taiyou_storage.metadata_repair preview
py -m taiyou_storage.metadata_repair apply
```

The controller supports `hf auth login` or local `HF_TOKEN` credentials
with permission to write the private dataset. The tool refuses public target
datasets and does not allow individual edits inside a public Actions runner.
Every operation is failure-closed and preview is the default safety boundary.

## Related historical repair

The optional `HF - Restore novel genres from original download artifacts`
workflow (see [Genre repair](GENRE_REPAIR.md)) may also backfill missing
synopsis or status **even when source genres already exist**. It depends on
temporary, original GitHub Actions artefacts. It does not guess missing
source information. For a verified manual correction of one specific novel,
use option 18 instead.
