"""Server-side, resumable snapshot copy into a separate PRIVATE HF dataset.

Large EPUB/ZIP/image blobs are never downloaded by this controller. A copy is
marked verified only when remote source/destination object identities agree
at immutable revisions. Unsupported regions or missing identity fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import io
import json
import re

from .core import DEFAULT_REPO
from .actions import ActionError, ensure_backup_private, private_dataset, safe_paths

BATCH_SIZE = 40
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class RemoteIdentity:
    size: int
    sha256: str = ""
    xet_hash: str = ""
    blob_id: str = ""


def _tree(api, repo: str, sha: str, token: str) -> dict[str, RemoteIdentity]:
    """Read a pinned remote inventory without transferring object contents."""
    files = {}
    listing = api.list_repo_tree(
        repo_id=repo, repo_type="dataset", revision=sha,
        recursive=True, expand=True, token=token)
    for entry in listing:
        name = getattr(entry, "path", None)
        if (not isinstance(name, str) or
                entry.__class__.__name__.endswith("Folder")):
            continue
        if name in files:
            raise ActionError("Duplicate remote file path")
        size = getattr(entry, "size", None)
        if not isinstance(size, int) or size < 0:
            raise ActionError("Remote inventory lacks reliable file sizes")
        lfs = getattr(entry, "lfs", None)
        digest = (lfs.get("sha256") if isinstance(lfs, dict)
                  else getattr(lfs, "sha256", None))
        xet = getattr(entry, "xet_hash", None)
        blob = getattr(entry, "blob_id", None)
        files[name] = RemoteIdentity(
            size=size,
            sha256=digest if isinstance(digest, str) and HEX64.fullmatch(digest) else "",
            xet_hash=xet if isinstance(xet, str) and HEX64.fullmatch(xet) else "",
            blob_id=blob if isinstance(blob, str) and HEX40.fullmatch(blob) else "",
        )
    safe_paths(list(files))
    return files


def _identity_match(source: RemoteIdentity, destination: RemoteIdentity) -> bool:
    """Never treat same-size files as proven identical.

    Compare the strongest common HF cryptographic object identity. If both
    repositories have hashes of the same type, their values must agree.
    """
    if source.size != destination.size:
        return False
    for name in ("sha256", "xet_hash", "blob_id"):
        a, b = getattr(source, name), getattr(destination, name)
        if a and b:
            return a == b
    return False


def remote_backup(api, backup_repo: str, token: str, *, source_repo: str = DEFAULT_REPO,
                  batch_size: int = BATCH_SIZE) -> dict[str, int]:
    """Copy without local book downloads, verify all file identities remotely.

    Idempotent at a fixed source revision. Partial-copy retries skip proven
    matching files, and a changed original repo fails before certification.
    """
    from huggingface_hub import CommitOperationCopy, CommitOperationAdd

    if not 1 <= batch_size <= BATCH_SIZE:
        raise ActionError("Invalid remote copy batch size")
    if source_repo != DEFAULT_REPO:
        raise ActionError("Only the configured private production dataset is supported")
    if backup_repo == source_repo:
        raise ActionError("Source and backup cannot be the same dataset")
    source_rev = private_dataset(api, source_repo, token)
    source_files = _tree(api, source_repo, source_rev, token)
    if not source_files or "data/library.json" not in source_files:
        raise ActionError("Source data missing or invalid; refusing to certify backup")
    if not all(name in source_files for name in ("data/library.json",)):
        raise ActionError("Source catalogue not present")
    # No unverified binary objects may be silently certified.
    if any(not (item.sha256 or item.xet_hash or item.blob_id)
           for item in source_files.values()):
        raise ActionError("Source object hashes unavailable; use full-verified backup mode")
    ensure_backup_private(api, backup_repo, token)
    dest_rev = private_dataset(api, backup_repo, token)
    prefix = f"snapshots/{source_rev}/files/"
    dest_files = _tree(api, backup_repo, dest_rev, token)
    pending = []
    verified_existing = 0
    for source_path, fingerprint in sorted(source_files.items()):
        destination = prefix + source_path
        prior = dest_files.get(destination)
        if prior is None:
            pending.append((source_path, destination))
        elif _identity_match(fingerprint, prior):
            verified_existing += 1
        else:
            raise ActionError("Backup snapshot contains a conflicting remote object; stop")
    # Prevent later source mutation from being labelled the current backup.
    if private_dataset(api, source_repo, token) != source_rev:
        raise ActionError("Source changed during backup preflight; run again")

    copied = 0
    for offset in range(0, len(pending), batch_size):
        chunk = pending[offset:offset + batch_size]
        # Copies for Xet/LFS blobs are handled server-side by HF.
        # Small ordinary Git objects may be transferred internally by the API.
        ops = [CommitOperationCopy(
            src_path_in_repo=original, path_in_repo=destination,
            src_revision=source_rev, src_repo_id=source_repo)
            for original, destination in chunk]
        result = api.create_commit(
            repo_id=backup_repo, repo_type="dataset", token=token,
            parent_commit=dest_rev, operations=ops,
            commit_message=f"Private snapshot copy batch {(offset // batch_size) + 1}")
        new_rev = getattr(result, "oid", None)
        if not isinstance(new_rev, str) or not HEX40.fullmatch(new_rev):
            raise ActionError("Snapshot commit result uncertain; inspect before retry")
        dest_rev = new_rev
        copied += len(chunk)
    # One remote listing proves every source file is represented identically,
    # including entries created before a resumed workflow.
    if private_dataset(api, source_repo, token) != source_rev:
        raise ActionError("Source changed during snapshot; snapshot left unverified")
    dest_files = _tree(api, backup_repo, dest_rev, token)
    for original, fingerprint in source_files.items():
        result = dest_files.get(prefix + original)
        if result is None or not _identity_match(fingerprint, result):
            raise ActionError("Remote backup identity verification failed")
    if private_dataset(api, source_repo, token) != source_rev:
        raise ActionError("Source changed during verification")
    # Store a small private completion receipt only AFTER all files match.
    # Keep public GitHub logs to numeric counts, never paths or titles.
    receipt = {
        "schema_version": 1, "source_revision": source_rev,
        "source_repository": source_repo, "files": len(source_files),
        "verification": "same-size and matching remote cryptographic object identity",
        "mode": "remote-first",
    }
    receipt_name = f"snapshots/{source_rev}/verification.json"
    data = (json.dumps(receipt, sort_keys=True) + "\n").encode("utf-8")
    existing = dest_files.get(receipt_name)
    if existing is None:
        result = api.create_commit(
            repo_id=backup_repo, repo_type="dataset", token=token,
            parent_commit=dest_rev,
            operations=[CommitOperationAdd(
                path_in_repo=receipt_name, path_or_fileobj=io.BytesIO(data))],
            commit_message="Certify privately verified remote snapshot")
        dest_rev = getattr(result, "oid", None)
        if not isinstance(dest_rev, str) or not HEX40.fullmatch(dest_rev):
            raise ActionError("Verification receipt outcome uncertain")
    else:
        # Do not overwrite an existing receipt without proving it is the
        # same content. We refuse even if the size happens to match.
        import hashlib
        git_blob = hashlib.sha1(
            f"blob {len(data)}\\0".encode("ascii") + data).hexdigest()
        expected = RemoteIdentity(size=len(data), blob_id=git_blob)
        if not _identity_match(expected, existing):
            raise ActionError("Conflicting private completion receipt")
    # Confirm completion by metadata listing, not a binary download.
    if receipt_name not in _tree(api, backup_repo, dest_rev, token):
        raise ActionError("Private completion receipt missing")
    return {
        "Source files": len(source_files),
        "Objects copied": copied,
        "Previously verified objects reused": verified_existing,
        "Snapshot verified": 1,
        "Full novel downloads": 0,
    }
