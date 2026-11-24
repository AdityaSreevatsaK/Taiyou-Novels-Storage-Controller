"""Live synthetic acceptance of explicit full-verified HF backup mode.

Creates two fresh private synthetic datasets. No production data or deletion.
All diagnostics are restricted to numeric counts by the GitHub output wrapper.
"""
from __future__ import annotations

from contextlib import ExitStack
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

from .disposable_backup_acceptance import (
    OWNER, create_private, private_revision, repositories, synthetic_files,
)


def full_verified_acceptance(api, source: str, destination: str, token: str) -> dict[str, int]:
    from huggingface_hub import CommitOperationAdd, hf_hub_download
    from . import actions
    from .core import validate_catalogue

    # Fail before ANY network I/O for malformed or production identifiers.
    if (source == destination or
            any("Taiyous-Novels" in name for name in (source, destination)) or
            not all("/Taiyou-Backup-Acceptance-" in name for name in (source, destination)) or
            not source.split("/", 1)[0] == destination.split("/", 1)[0] or
            "/Taiyou-Backup-Acceptance-Source-" not in source or
            "/Taiyou-Backup-Acceptance-Destination-" not in destination):
        raise ValueError("Only distinct synthetic private test datasets are permitted")

    initial = create_private(api, source, token)
    create_private(api, destination, token)
    fixture = synthetic_files()
    validate_catalogue(json.loads(fixture["data/library.json"]))
    api.create_commit(
        repo_id=source, repo_type="dataset", token=token, parent_commit=initial,
        operations=[
            CommitOperationAdd(path_in_repo=name, path_or_fileobj=BytesIO(content))
            for name, content in sorted(fixture.items())
        ],
        commit_message="Synthetic full-verified backup acceptance source",
    )
    source_revision = private_revision(api, source, token)
    paths = actions.safe_paths(api.list_repo_files(
        repo_id=source, repo_type="dataset", revision=source_revision, token=token))
    if not set(fixture).issubset(paths):
        raise ValueError("Synthetic source lacks required files")

    with ExitStack() as guards:
        # Overrides the legacy production-source name only inside this
        # isolated acceptance process. The normal CLI remains unchanged.
        guards.enter_context(patch.object(actions, "DEFAULT_REPO", source))
        actions.copy_to_private_backup(api, destination, token, source_revision, paths)

    destination_revision = private_revision(api, destination, token)
    prefix = f"snapshots/{source_revision}"
    manifest_bytes = Path(hf_hub_download(
        repo_id=destination, repo_type="dataset",
        filename=f"{prefix}/manifest.json",
        revision=destination_revision, token=token)).read_bytes()
    manifest = json.loads(manifest_bytes)
    if (manifest.get("source_repo") != source or
            manifest.get("source_revision") != source_revision or
            not isinstance(manifest.get("files"), list) or
            len(manifest["files"]) != len(paths)):
        raise ValueError("Private full-backup manifest is incomplete")

    recorded = {entry["path"]: entry for entry in manifest["files"]}
    if set(recorded) != set(paths):
        raise ValueError("Full-backup manifest inventory differs from source")
    for relative in paths:
        original = Path(hf_hub_download(
            repo_id=source, repo_type="dataset", filename=relative,
            revision=source_revision, token=token)).read_bytes()
        restored = Path(hf_hub_download(
            repo_id=destination, repo_type="dataset",
            filename=f"{prefix}/files/{relative}",
            revision=destination_revision, token=token)).read_bytes()
        digest = sha256(original).hexdigest()
        if (original != restored or
                digest != recorded[relative]["sha256"] or
                len(restored) != recorded[relative]["size"]):
            raise ValueError("Full-verified synthetic restore hash mismatch")
        if relative in fixture and original != fixture[relative]:
            raise ValueError("Synthetic source changed")
    if private_revision(api, source, token) != source_revision:
        raise ValueError("Source revision changed during verification")
    return {"Source files": len(paths), "Snapshot verified": 1,
            "Verified complete": 1}


def main() -> int:
    if (os.getenv("GITHUB_REPOSITORY") !=
            "AdityaSreevatsaK/Taiyou-Novels-Storage-Controller" or
            os.getenv("GITHUB_REF") != "refs/heads/master"):
        print("ERROR: Trusted Controller master required.", file=sys.stderr)
        return 2
    token = os.getenv("HF_DISPOSABLE_TEST_TOKEN", "").strip()
    if not token:
        print("ERROR: Disposable test credential unavailable.", file=sys.stderr)
        return 2
    try:
        import huggingface_hub
        if huggingface_hub.__version__ != "1.33.0":
            raise ValueError("Expected pinned HF client unavailable")
        api = huggingface_hub.HfApi()
        identity = api.whoami(token=token)
        owner = identity.get("name") if isinstance(identity, dict) else None
        source, destination = repositories(
            os.getenv("GITHUB_RUN_ID", ""),
            os.getenv("GITHUB_RUN_ATTEMPT", ""), owner=owner,
        )
        metrics = full_verified_acceptance(api, source, destination, token)
        for key, value in metrics.items():
            print(f"{key}: {value}")
        return 0
    except Exception as error:
        # Public GitHub logs must not include raw private HF error details.
        print(f"ERROR: Synthetic full-verified acceptance failed ({type(error).__name__}).",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
