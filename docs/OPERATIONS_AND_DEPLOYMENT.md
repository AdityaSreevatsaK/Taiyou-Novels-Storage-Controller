# Operations, deployment and verification

**Current as of 21 November 2026.** The controller is a Python/Windows tool with optional GitHub Actions runners, **not** an always-running deployed service. The separately hosted Reader has its own Cloudflare deployment and is not deployed from this repository.

## Runtime environments

| Environment | Purpose | What persists |
| --- | --- | --- |
| Local Windows PC | Menu, bulk uploads, backups, detailed inspection, cache cleanup, local reset | User's `novels/`, `downloads/`, ignored `reports/`, local HF cache and login |
| GitHub Actions | Cross-platform CI; manual private read/write workflows; completed export bridge | Git code and **count-only** job summaries; ephemeral private runner files discarded |
| Private Hugging Face source dataset | Authoritative novel catalogue and blobs | `data/library.json`, original ZIPs, EPUBs, optional covers and sidecars |
| Separate private HF backup dataset | Verified remote snapshots and private reports | `snapshots/<revision>/...` and private verification receipts |
| Separate Cloudflare Pages/Functions Reader | Authenticated web reading UX | Reader code/deployment; not modified here |

## Local setup

1. Install Python **3.11 or 3.12** and clone the public repository on Windows.
2. From its root, run `py -m pip install -r requirements.txt`, then `py -m pip check`.
3. Authenticate using `hf auth login` under the **correct** Hugging Face account, with a fine-grained token for the **private** `AdityaSreevatsaK/Taiyous-Novels` dataset. Prefer a read-only token for audits; use dataset-scoped write permission only for intended uploads/repairs. Do not commit tokens or paste them into logs.
4. Place prepared ZIPs in `novels/` for the bulk uploader. Source website downloading is outside this repository.
5. Double-click `00_storage_menu.cmd`. Each launcher is individually executable from its repository folder. Paths with spaces must remain quoted.
6. Run a **preview** before any mutation and examine the optional itemised private report under `reports/`. Explicitly approve only reviewed changes.

Main menu: `01` upload, `02` download all, `03` list, `04` conflicts, `05` verify integrity, `06` local sync, `07` catalogue backup, `08` restore placeholder, `09` delete placeholder, `10` covers, `11` **full reset**, `12` inventory, `13` missing covers, `14` compare Retriever inventory, `15` health report, `16` inspection-sidecar backfill, `17` **local** inspection cache cleanup, `18` source metadata audit/repair. See [User guide](USER_GUIDE.md) for exact flags and output files.

Read-only inspection mode differences: `quick` remote metadata/listings, `manifest` small trusted sidecars, `deep` full binary validation with local/runner disk impact. Use the lightest mode that can answer the question. `17` deletes **only** selected local cache files with typed approval.

## GitHub Actions workflows

Open the repository **Actions** tab and choose the supported manual workflow on `master`. Private HF workflows are intended to run only from this repository's `master` branch; the workflow jobs must enforce both the repository identity and `refs/heads/master`, rather than relying on the operator to select the correct ref. They also share the `hf-storage-controller` Actions concurrency group to reduce overlap between controller workflows. This does **not** lock out local scripts, the Reader, or other repositories.

| Workflow file | Mode and outcome | Security boundary |
| --- | --- | --- |
| `ci.yml` | Push/PR/manual test matrix and vulnerability audit, plus scheduled audit | No HF production secrets |
| `hf-inspect.yml` | Read-only `quick`, `manifest` or `deep` private check | Public numerical counts only, no HF writes |
| `hf-live-readiness.yml` | Read-only source/backup access and cryptographic inventory preflight | Does **not** create or validate a completed backup |
| `hf-private-backup.yml` | Explicit private `remote-first` snapshot or `full-verified` fallback | Separate PRIVATE backup, never the source as destination |
| `hf-private-reports.yml` | Private inventory/conflict reports to separate private destination | No private CSV in public GH artifacts |
| `hf-cloud-import.yml` | Verify a **completed** Novel-Retriever export, preview, opt-in apply | Runner-staged data and manifest checks, guarded HF write |
| `hf-upload-covers-artifact.yml` | Preview then opt-in import of verified cover export | Unique matching and bounded cover commits |
| `hf-restore-genres.yml` | Optional historical missing-source-fields repair | Source proof and additive catalogue change |
| `release.yml` | Code-only release after successful current `master` CI | No private HF assets or tokens |

See [GitHub Actions guide](GITHUB_ACTIONS.md) for exact workflow input names. **No active GitHub Action may delete the HF repository or clear production data.** The repository-delete operation is forbidden; the remaining local reset clears only the `data/` content tree after a complete verified local backup and typed confirmations. One-shot readable-folder migration and 104-cover recovery workflows have been retired. A similarly named historical YAML path in older docs is **not** an executable option.

The active workflow inventory is tested by `tests/test_github_workflow_cleanup.py`. Any HF workflow that can read or write private data must be restricted to the exact repository and `master` ref, use least-privilege permissions, share the controller concurrency group, and avoid public artifacts containing private records. Re-check the actual YAML before every dispatch because workflow names and guards can change.

### Secrets and least privilege

Store credentials only in **Settings > Secrets and variables > Actions**, and only for workflows that need them:

- `HF_INSPECTION_READ_TOKEN`: preferred fine-grained **read-only** access to the production private dataset for inspection.
- `HF_STORAGE_CONTROLLER_TOKEN`: scoped write access to the production private dataset and, for backup/report tasks, the separate private destination. The inspection Action may fall back to it, but do not use broad permissions unnecessarily.
- `NOVEL_LIBRARY_ACTIONS_TOKEN`: GitHub artifact read permission when cross-repository Novel-Retriever export or cover retrieval requires it.
- `HF_DISPOSABLE_TEST_TOKEN`: **only** the pre-created private `AdityaSreevatsaK/Taiyou-Readable-Folder-Test` dataset for isolated live HF integration. This token **must not** access production.

Never place secrets into CLI arguments printed by CI, test output, public JSON summaries or Markdown reports. Real reader OAuth, Cloudflare deployment credentials, and other repositories' tokens are outside this controller's ownership.

## Safe routine playbooks

### Import a complete downloaded novel locally

- Preview `01_bulk_upload.cmd`. Resolve `CONFLICT` rather than overriding a matching title/ID.
- Confirm the exact proposed new/updated/unchanged count and affected local files privately.
- Apply through its approval gate; after any partial failure, re-preview against the latest HF revision.
- Optionally run `05_verify_integrity.cmd` or `15_library_health_report.cmd` and check one novel in the Reader separately.

### Import a complete Retriever export via cloud

- Obtain a finished *consolidated export* workflow run ID and correct completed-artifact name from **Novel-Retriever**, not a per-chapter job.
- Dispatch `hf-cloud-import.yml` as preview-only; its bundle validation checks SHA-256 and structure.
- Only after a successful preview, opt into apply. An expired, incomplete or changed export must fail without HF updates.
- Public output shows numerical results; private bundle details are not published as GH artifacts.

### Back up the private dataset

- Select `hf-private-backup.yml` with the distinct private backup destination.
- Prefer `remote-first`; this verifies source/destination remote cryptographic identities and avoids novel downloads to Windows.
- If HF cannot copy server-side due to region/identity constraints, stop and explicitly select `full-verified`. Never silently downgrade verification or certify by equal file size.
- Verify the private snapshot receipt and current exact source revision. For **destructive local reset**, follow the independent full local verified-backup process in [Safety and recovery](SAFETY_AND_RECOVERY.md). A snapshot receipt is not a substitute for every reset-specific guard.

### Investigate incomplete metadata or missing covers

- Use source-metadata audit/repair or cover audit in read-only mode first.
- The normal uploader can attach uniquely matched **local sidecar images** from `covers/`; it does not yet extract authentic embedded ZIP/EPUB artwork and publish a standalone `coverPath` in the same upload ([open issue #54](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/54)).
- Metadata parser and validator currently support only `Completed` and `Ongoing`; `Hiatus` and `Dropped` are tracked as incomplete work in [issue #46](https://github.com/AdityaSreevatsaK/Taiyou-Novels-Storage-Controller/issues/46).
- Research missing fields from authorised source information pages; review exact unique book ID/source URL before change. A proposed import JSON is not automatically verified.
- Make only additive changes, with preview hash, private pre-change catalogue backup and current HF revision checks.
- If the reader does not display data that is present in HF, debug the **Reader's separate** gateway/cache/UI before rewriting storage.

### Clear local inspection downloads

- Close other inspections, run `17_cleanup_inspection_downloads.cmd`, review owned inspection files separately from legacy HF cache **entries**, and type `DELETE LOCAL CACHE` only for intended local files.
- Never report estimated legacy shared-cache bytes as guaranteed disk recovery. Cloud files remain unchanged.

### Full reset (extraordinary, local only)

The local `11_clear_hf_data.cmd` can affect the entire `data/` namespace, including files other than normal novel archives. Requires a complete **verified local backup**, live private-target/revision checks, accurate preview and all typed confirmations. The procedure must stop on any mismatch or uncertain result. There is **no automatic full restore**. A generic checkbox or GitHub Action does not authorise deletion.

## Development, CI and deployment

Run from repo root:

```powershell
py -m pip install -r requirements.txt
py -m pip check
py -m compileall -q taiyou_storage tests
py -m unittest discover -s tests -q
```

CI then checks the exact PR head on **Windows and Ubuntu** with Python **3.11 and 3.12**, and performs a dependency vulnerability audit. These tests should require **no HF access** and use synthetic, private-like fake clients for risky operations. The repository is public MIT code only; novel text/cover artwork remain outside that licence. Check workflow **conclusions**, not merely scheduled/queued status.

Deployment of controller changes means merging code to `master`, and the user pulling/re-running their local checkout or dispatching a manual Action on that branch. There is **no application server restart or Cloudflare publish step** here. `release.yml` publishes a code-only version when `VERSION`, `CHANGELOG.md`, release notes and guarded green `master` CI satisfy [Releasing](RELEASING.md); documentation-only PRs do not need a new release version unless explicitly requested.

### Practical failure triage

| Observation | Safe response |
| --- | --- |
| 401/403/404 for HF | Verify account, private dataset identity and token permissions without exposing token; do not initialise an empty catalogue |
| Concurrent/stale revision (409/412 or precondition mismatch) | Stop, pin new snapshot, rebuild and re-approve plan |
| Partial HF batch committed | Preserve successful batches, inspect remote state and resume; do not reset |
| 429 or Xet transport issue | Respect bounded retry policy and environmental limits; avoid inventing success |
| EPUB/path/cover conflict | Inspect private evidence; never force by title alone |
| Public log has no per-book details | Expected by design; use private Windows reports or a strictly authorised private destination |
| GitHub Actions test job queued | No completion claim until all expected jobs finish on the exact SHA |
| Reader missing content after verified storage write | Investigate the separate reader's catalogue refresh, auth gateway, paths, cache and deployment |

## Operator and agent finish criteria

A change is *implemented* when code/docs are on the proposed branch. It is *merged* when GitHub reports an actual merge commit. It is *verified* when the expected CI job conclusions are successful for the relevant SHA. It is *live applied* **only** when an authorised real HF operation has completed and the remote result has been independently confirmed. Keep these states separate in final reports.

Related: [Architecture](ARCHITECTURE.md), [Incidents](FAILURES_AND_LESSONS.md), [Agent playbook](AI_AGENT_PLAYBOOK.md), [Dated project state](PROJECT_STATE.md), [Output rules](OUTPUT_CONVENTIONS.md).
