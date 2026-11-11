# Restore missing source genres in Taiyou's Personal Library

## Why this is needed

Older `Novel_Library` chapter-batch EPUB assembly accidentally dropped original
FanFicFare `dc:subject` genres, completion status and (when missing from the
intermediate JSON) the synopsis. The app therefore correctly displays no
`sourceTags` for those novels. The downstream downloader is fixed separately.

## One-click private catalogue repair

In **AdityaSreevatsaK/Taiyou-Novels-Storage-Controller → Actions**, open
**HF - Restore novel genres from original download artifacts**.

1. Run with **apply_changes = false** to preview count-only totals.
2. Run again with **apply_changes = true** to update `data/library.json`.
3. Reload the library app and use **Refresh Cloud Library**.

Required GitHub repository secrets:
- `HF_STORAGE_CONTROLLER_TOKEN`: write permission to the private dataset
  `AdityaSreevatsaK/Taiyous-Novels`.
- `NOVEL_LIBRARY_ACTIONS_TOKEN`: read permission for GitHub Actions artifacts
  in `RichardDaffern/Novel_Library`.

The action fetches the downloader's **original first chapter-batch EPUB
metadata**, not chapter content from a novel website. It matches each existing
book by **unique, exact canonical source URL**, not title. It adds missing
`sourceTags` and, only where absent, `description` and `status`.
It never replaces EPUBs, original ZIP archives, covers, IDs, ratings,
progress, personalTags, notes or reviews. Existing nonempty sourceTags
are preserved. Ambiguous duplicate source URLs are skipped, not deleted.
An unchanged catalogue creates no commit. Otherwise it backs up the previous
`data/library.json` into a **private** `backups/genre-repair/` path and updates
only the catalogue in one optimistic-revision-checked Hugging Face commit.
No novel names, private catalogue or genre lists are uploaded as public
GitHub artifacts; workflow output includes counts only.

**Time-sensitive:** historical GitHub Actions artifacts are usually retained
for just seven days. Older expired artifacts cannot be recovered automatically;
these novels are reported as missing rather than assigned guessed tags.

This repair is independent of the cover uploader and normal novel uploader.
A duplicate Abe the Wizard is intentionally **not** deleted or merged.

## Local command

Set `HF_TOKEN` and `NOVEL_LIBRARY_ACTIONS_TOKEN` in the environment, then:

```powershell
py -3 -m taiyou_storage.genre_repair
py -3 -m taiyou_storage.genre_repair --apply
```

No `--apply` means read-only. Run offline tests with:

```powershell
py -3 -m unittest discover -s tests -p test_genre_repair.py -v
```