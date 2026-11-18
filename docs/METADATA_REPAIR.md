# Missing source metadata: audit and one-novel repair

Run `18_repair_novel_metadata.cmd` from the Storage Controller directory.
This tool works only with your **PRIVATE** Hugging Face dataset, and never
replaces any EPUB, original ZIP, cover, reading progress, personal tags,
ratings, reviews, collections or other personal metadata.

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
   one line, genre names separated by commas, and `Completed` or `Ongoing`.
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
