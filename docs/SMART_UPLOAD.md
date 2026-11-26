# Smart novel ZIP uploader — technical notes

For getting started and choosing a Windows launcher, see the [main README](../README.md).
The Python uploader defaults to read-only preview; use `--interactive` to
preview and confirm in one process, or `--apply` for an explicitly authorised
non-interactive write. Pass `--repo OWNER/PRIVATE-DATASET` to change target.

The controller passes on-disk paths to Hugging Face for **all** commit
operations. Generated EPUB, catalogue and inspection-manifest files are staged
temporarily per batch commit; the original ZIP is used directly from disk.
This avoids the `BytesIO`-triggered Xet-to-HTTP fallback. Temporary staging
files are removed after success, failure or a revision-conflict retry. It does
not change the existing approval, private-repository and parent-revision checks.
Xet availability still depends on Hugging Face and your local environment.

- Validates ZIP CRC, EPUB structure, JSON, entry counts, expanded-size budgets and file-size limits.
- Matches existing catalogue entries by exact EPUB hash-derived ID, or by unique normalised title **and** author.
- Preserves an existing novel ID when EPUB content changes.
- Reconciles `original.zip`, `source.epub`, covers (when present) and `data/library.json` in atomic batches of up to 10 novels; uploads only binary artifacts whose contents differ.
- Preserves existing personal metadata fields, including progress, ratings, personal tags and notes, where stored in book metadata. Missing source tags from older ZIPs do not erase existing nonempty source genres.
- Skips only when ZIP, EPUB and source-managed metadata are all equivalent; refuses ambiguous matches and public target datasets.
- Reads the remote catalogue once per approved batch run, carrying forward verified in-memory changes; uses pinned revisions and HF parent-commit checks to reject concurrent modifications.
- Downloads and hashes only the remote artifacts corresponding to the novels supplied in the current local batch.

**Limitations:** A changed title and EPUB simultaneously cannot be matched reliably
without an explicit stable identifier and may be treated as a new novel. Never
use this tool for such renames until manual ID mapping is supported. Local duplicate
novels targeting the same book block the batch **unless** verified local deduplication is enabled, in which case equivalent packages are skipped and conflicting editions still block uploads. The initial matching
heuristic is conservative but not a guarantee against duplicates with different
titles; inspect previews before applying.

CI is completely offline. No Hugging Face dataset modifications occur during tests.

## Fast batching and automatic local covers

**Default Windows layout:**

```text
Taiyou-Novels-Storage-Controller/
  novels/
    Novel One.zip
    Novel Two.zip
  covers/
    Novel One.jpg
    Novel Two.png
```

Start `01_bulk_upload.cmd`. The uploader previews both folders, checks the
cover images, matches by exact normalised title, local ZIP basename or stable
24-character novel ID, then uploads the novels and their matched covers
**together in the same revision-guarded commit**. A nested
`covers/Novel One/cover.jpg` or `covers/<novel-id>/cover.png` is also valid.
Covers are optional. No images are downloaded from the internet automatically.
When no matching local sidecar is available, the uploader now extracts a
**genuine** cover from a validated source ZIP, preferring a single
EPUB2/EPUB3 OPF-declared image, then an unambiguous standalone `cover.*`
image alongside `source.epub` in the source ZIP. It rejects unsafe paths,
oversized/bad images, undeclared chapter illustrations and ambiguous candidates.
Missing/invalid embedded images do **not** block a valid novel import: they
remain unlinked, never replaced with stock artwork. An existing
`metadata.coverPath` is always retained and never silently replaced by
embedded artwork. A matched local `covers/` sidecar takes precedence.

The approved preview includes the extracted-artwork action and image digest.
The same revision-guarded batch commit contains the cover file and updated
`metadata.coverPath` alongside the ZIP, EPUB, inspection manifest and
catalogue. `--no-covers` skips both sidecars and embedded extraction.
A later replay can add a missing cover without re-uploading unchanged EPUB/ZIP
bytes. Existing 104 repaired covers are untouched.

Unmatched, ambiguous, duplicate, invalid or unexpectedly conflicting **local sidecar** covers
are shown as `COVER_CONFLICT` in `reports/bulk-upload-plan.csv`; **all writes
are blocked**. There is no fuzzy matching. Move unrelated covers out of
`covers/` or use `--no-covers` when you intend a novels-only upload. Existing
differently named cover references cannot be silently replaced.

The default `--batch-size 10` means ten new novels plus ten covers generally
require **one Hugging Face commit**, instead of ten. Each batch retains one
catalogue update, safe source-managed metadata merges, per-book inspection
sidecars and parent-commit concurrency protection. Bandwidth for the original
ZIP and EPUB bytes is still required, so wall-clock speed depends on file
size and network upload rates. Previous batches remain committed if a later
batch fails; re-run the same folders to resume.

Run explicitly:

```powershell
py -m taiyou_storage.upload novels --covers-folder covers --batch-size 10 --dedupe-local --interactive
```

Skip covers only when intentional:

```powershell
py -m taiyou_storage.upload novels --no-covers --interactive
```

## Consecutive commit revision checks

For a multi-novel upload, each successful batch `create_commit` returns an immutable
commit SHA. The next batch verifies the dataset **at that exact
revision**, instead of trusting a possibly delayed `main`-branch SHA response.
If Hugging Face has not yet indexed that specific commit, the uploader makes
four short, bounded read-only retries (no repeated writes).

Each actual write still passes `parent_commit` with the exact expected SHA.
A different writer advancing `main` causes the server to reject the write:
the uploader stops and asks for a fresh preview. It never silently rebases
an approved plan or overwrites another writer's changes.

Previously committed batches are preserved if a run stops. Re-run the same
ZIP set to skip completed items. No local ZIPs are deleted.

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
   rather than the outer bundle, in your local `novels/` folder.
3. Preview only:

~~~powershell
python -m taiyou_storage.upload novels --dedupe-local
~~~

4. On Windows, menu option **1** or `01_bulk_upload.cmd` performs
   this verified duplicate preflight. There is no separate second launcher.
5. The preview shows selected novels, skipped **DUPLICATE** packages and
   any **CONFLICT** entries. A conflict blocks all cloud writes, even if
   `--apply` was supplied. Conflicting editions require manual review.
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
