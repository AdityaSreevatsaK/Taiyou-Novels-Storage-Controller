# Smart uploader: first release

Run `01_bulk_upload.cmd` to preview and explicitly confirm changes. Or run
`python -m taiyou_storage.upload novels` (read-only preview) and add `--apply`
to write updates.

The controller:
- Validates local ZIP CRC, EPUB structure, JSON and file-size limits.
- Matches existing catalogue entries by exact EPUB hash-derived ID, or by unique normalised title **and** author.
- Preserves an existing novel ID when EPUB content changes.
- Replaces `original.zip` and `source.epub` and updates `data/library.json` in one optimistic-concurrency-checked commit.
- Preserves existing personal metadata fields, including progress and ratings, where stored in book metadata.
- Skips byte-identical ZIPs, refuses ambiguous matches and refuses public target datasets.
- Rechecks the remote catalogue immediately before each write.

**Limitations:** A changed title and EPUB simultaneously cannot be matched reliably
without an explicit stable identifier and may be treated as a new novel. Never
use this tool for such renames until manual ID mapping is supported. Local duplicate
novels targeting the same book block the entire batch. The initial matching
heuristic is conservative but not a guarantee against duplicates with different
titles; inspect previews before applying.

CI is completely offline. No Hugging Face dataset modifications occur during tests.

## First upload to a newly recreated Hugging Face dataset

You do not need to manually create `data/library.json`. A newly created **PRIVATE**
dataset typically only contains `.gitattributes` and/or a README. Run
`01_bulk_upload.cmd` and review the `NEW PRIVATE DATASET` preview; on
confirmation the first novel upload creates the version 1 catalogue and novel
files atomically. Subsequent ZIPs append to it. If the dataset has any
`data/` files but no catalogue, the uploader refuses to initialise so it
cannot overwrite or orphan data. The dataset must be private and accessible
to your configured HF token.
