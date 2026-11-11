# Smart novel ZIP uploader — technical notes

For getting started and choosing a Windows launcher, see the [main README](README.md).
The Python uploader defaults to read-only preview; use `--interactive` to
preview and confirm in one process, or `--apply` for an explicitly authorised
non-interactive write. Pass `--repo OWNER/PRIVATE-DATASET` to change target.

The controller:
- Validates ZIP CRC, EPUB structure, JSON, entry counts, expanded-size budgets and file-size limits.
- Matches existing catalogue entries by exact EPUB hash-derived ID, or by unique normalised title **and** author.
- Preserves an existing novel ID when EPUB content changes.
- Reconciles `original.zip`, `source.epub` and `data/library.json` in one optimistic-concurrency-checked commit, uploading only binary artifacts whose contents differ.
- Preserves existing personal metadata fields, including progress, ratings, personal tags and notes, where stored in book metadata. Missing source tags from older ZIPs do not erase existing nonempty source genres.
- Skips only when ZIP, EPUB and source-managed metadata are all equivalent; refuses ambiguous matches and public target datasets.
- Rechecks the remote catalogue immediately before each write; same-process Windows confirmation and revision-guarded multi-book application reject plan drift.
- Downloads and hashes only the remote artifacts corresponding to the novels supplied in the current local batch.

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
