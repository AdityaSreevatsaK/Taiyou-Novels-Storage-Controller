# Releasing the Storage Controller

Release tags are **vMAJOR.MINOR.PATCH**, starting at **v0.1.0**. The
repository uses a lightweight automated publisher that runs only when the
**master-branch CI workflow succeeds**.

To propose a new release:

1. Update the version in `VERSION` (for example, `0.1.1`).
2. Add a corresponding entry in `CHANGELOG.md`.
3. Add `docs/releases/v0.1.1.md` with the public release notes.
4. Open a pull request and let the Windows/Linux Python CI matrix pass.
5. Merge into `master`. After that exact merge commit passes CI, the
   release publisher checks it is still the current `master`, creates an
   **annotated Git tag**, and publishes a GitHub Release with the note file.

The publisher is idempotent: it will never force-move an existing tag or
replace an existing release. If the workflow fails after creating a tag,
review the failure and re-run a successful CI workflow after correcting it.

Only code/documentation is included. Never attach private HF files,
novels, covers, credentials or catalogue exports to public GitHub Releases.
