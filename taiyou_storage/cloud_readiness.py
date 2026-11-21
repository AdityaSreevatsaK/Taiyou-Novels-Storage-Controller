"""Read-only live readiness check for public-repository GitHub Actions.

Never print private novel paths, titles, raw HF exception messages or tokens.
No network calls other than pinned HF metadata listings are required.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
import sys

from .actions import ActionError
from .remote_backup import preview_remote_backup


def run(argv=None, *, api=None) -> int:
    parser = argparse.ArgumentParser(description="Private HF remote operations readiness")
    parser.add_argument("--backup-repo", default="AdityaSreevatsaK/Taiyous-Novels-Backup")
    args = parser.parse_args(argv)
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        print("ERROR: Private HF storage credential is not configured.", file=sys.stderr)
        return 2
    try:
        from huggingface_hub import HfApi
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            counts = preview_remote_backup(
                api if api is not None else HfApi(), args.backup_repo, token
            )
    except (ActionError, Exception):
        # Do not expose private API details in this PUBLIC code repository.
        print("ERROR: Read-only private HF backup preflight failed. "
              "Check the credential, destination privacy or remote object identities.",
              file=sys.stderr)
        return 1
    print("=== Private remote-backup readiness (no writes) ===")
    for key, number in counts.items():
        print(f"{key}: {number}")
    print("Preflight did not copy files, verify storage-region compatibility, "
          "or modify the backup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
