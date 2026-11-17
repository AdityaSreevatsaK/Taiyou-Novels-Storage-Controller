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


## Verified deduplication for mixed old and new ZIPs

**Windows default:** `01_bulk_upload.cmd` always enables `--dedupe-local`.
Verified-equivalent local ZIPs are skipped, and conflicting editions block the
entire batch. This applies to ordinary uploads as well as mixed old/new exports.
The uploader never deletes your local ZIPs.

**Advanced Python CLI:** direct invocation without `--dedupe-local` still
rejects duplicate local ZIPs. Pass the flag explicitly to use the same verified
preflight as the Windows launcher.

1. Keep a safe copy of the original ZIPs; no local files are deleted.
2. Extract the outer Retriever export ZIP. Put the individual novel ZIPs,
   rather than the outer bundle, in your local \`novels/\` folder.
3. Preview only:

~~~powershell
python -m taiyou_storage.upload novels --dedupe-local
~~~

4. On Windows, menu option **1** or `01_bulk_upload.cmd` performs
   this verified duplicate preflight. There is no separate second launcher.
5. The preview shows selected novels, skipped **DUPLICATE** packages and
   any **CONFLICT** entries. A conflict blocks all cloud writes, even if
   \`--apply\` was supplied. Conflicting editions require manual review.
6. Only after reviewing the complete plan and verifying the private target
   dataset, explicitly apply:

~~~powershell
python -m taiyou_storage.upload novels --dedupe-local --interactive
~~~

The preflight prioritises canonical HTTPS novel source identity, then exact
normalised title and author; equivalent EPUB bytes or verified TXT chapter
checksums are required to skip an old ZIP. Different chapter content is not
silently replaced. The remote catalogue's existing novel ID and personal
metadata remain authoritative. Cover-only EPUB changes do not generate new
remote identities when the canonical source URL matches. Ratings, comments,
progress, personal tags, collections and notes cannot be set by archive
metadata during source updates.

Existing private dataset checks, unexpected paths, missing catalogue
protection, revision guards, local ZIP digests, manual approval and
all-or-nothing batch conflict checks remain enabled. The feature is
read-only in normal preview and does not modify the Novel Retriever repository.
