"""One-shot live synthetic Novel-Retriever -> private HF acceptance.

Only run on trusted Controller master in GitHub Actions. Never uses
production HF datasets or the controller's production credential.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from .cloud_import import BundleError, check_bundle
from .core import sha256_file
from .upload import main as bulk_main

STAGE = 0


def import_repo(run_id: str, attempt: str, owner: str) -> str:
    if (not re.fullmatch(r"[1-9][0-9]{0,17}", run_id)
            or not re.fullmatch(r"[1-9][0-9]{0,5}", attempt)
            or not isinstance(owner, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", owner)):
        raise ValueError("Unsafe HF acceptance dataset parameters")
    return f"{owner}/Taiyou-Import-Acceptance-{run_id}-A{attempt}"


def run_acceptance(api, token: str, repo: str) -> dict[str, int]:
    from huggingface_hub import hf_hub_download
    from tests.test_retriever_controller_handoff import retriever_bundle
    from tests.test_embedded_covers import make_embedded_fixture

    if (not isinstance(repo, str)
            or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}/Taiyou-Import-Acceptance-[1-9][0-9]+-A[1-9][0-9]*",
                repo)
            or "Taiyous-Novels" in repo):
        raise ValueError("Only generated disposable HF datasets allowed")

    global STAGE
    with TemporaryDirectory(prefix="taiyou-private-import-acceptance-") as td:
        root = Path(td)
        incoming = retriever_bundle(root, 2)
        cover_novel = make_embedded_fixture(incoming / "novels")
        # Match the actual Retriever's dedupe-safe position/filename contract.
        chapter = b"Independent synthetic EPUB companion chapter."
        with ZipFile(cover_novel, "r") as archive:
            payload = {entry.filename: archive.read(entry)
                       for entry in archive.infolist() if not entry.is_dir()}
        payload["novel/chapters.json"] = json.dumps([{
            "position": 1, "file": "chapter_0001.txt",
            "sha256": sha256(chapter).hexdigest(), "title": "First"
        }]).encode()
        payload["novel/chapter_0001.txt"] = chapter
        with ZipFile(cover_novel, "w") as archive:
            for name, raw in sorted(payload.items()):
                archive.writestr(name, raw)
        manifest = json.loads((incoming / "manifest.json").read_text(encoding="utf8"))
        manifest["novels"].append({
            "file": "novels/" + cover_novel.name,
            "zip_sha256": sha256_file(cover_novel),
            "bytes": cover_novel.stat().st_size,
        })
        manifest["exported_novels"] += 1
        (incoming / "manifest.json").write_text(json.dumps(manifest), encoding="utf8")
        STAGE = 1
        counted = check_bundle(incoming)
        if counted["Verified novel ZIPs"] != 3:
            raise ValueError("Synthetic export inventory mismatch")
        STAGE = 2
        api.create_repo(repo_id=repo, repo_type="dataset", private=True,
                        exist_ok=False, token=token)
        initial = api.dataset_info(repo_id=repo, token=token)
        if initial.private is not True:
            raise ValueError("Test dataset is not private")
        os.environ["HF_TOKEN"] = token
        args = [str(incoming / "novels"), "--repo", repo,
                "--covers-folder", str(incoming / "covers"),
                "--dedupe-local", "--batch-size", "5",
                "--report", str(root / "reports" / "bulk-plan.csv")]
        # Suppress all untrusted raw filenames and HF exceptions, even if the
        # test runner itself is not wrapped by github_output.
        sink = StringIO()
        STAGE = 3
        with redirect_stdout(sink), redirect_stderr(sink):
            status = bulk_main(args)
        if status != 0:
            raise ValueError("Synthetic import preview refused")
        if api.dataset_info(repo_id=repo, token=token).sha != initial.sha:
            raise ValueError("Synthetic preview unexpectedly wrote to HF")
        STAGE = 4
        with redirect_stdout(sink), redirect_stderr(sink):
            status = bulk_main(args + ["--apply"])
        if status != 0:
            raise ValueError("Synthetic import apply refused")
        STAGE = 5
        committed = api.dataset_info(repo_id=repo, token=token)
        if committed.private is not True or committed.sha == initial.sha:
            raise ValueError("No private synthetic import commit")
        snapshot = set(api.list_repo_files(repo_id=repo, repo_type="dataset",
                                           revision=committed.sha, token=token))
        catalogue = json.loads(Path(hf_hub_download(
            repo_id=repo, repo_type="dataset", filename="data/library.json",
            revision=committed.sha, token=token)).read_bytes())
        books = catalogue.get("books")
        if (catalogue.get("version") != 1
                or not isinstance(books, list) or len(books) != 3
                or len({b["id"] for b in books}) != 3):
            raise ValueError("Invalid imported synthetic catalogue")
        covers = 0
        by_title = {b["metadata"]["title"]: b for b in books}
        for archive_file in (incoming / "novels").glob("*.zip"):
            from .upload import read_novel
            meta, epub, source_digest = read_novel(archive_file)
            book = by_title[meta["title"]]
            if book["archivePath"] not in snapshot or book["epubPath"] not in snapshot:
                raise ValueError("Missing imported novel files")
            original_zip = Path(hf_hub_download(
                repo_id=repo, repo_type="dataset",
                filename=book["archivePath"], revision=committed.sha,
                token=token)).read_bytes()
            imported_epub = Path(hf_hub_download(
                repo_id=repo, repo_type="dataset",
                filename=book["epubPath"], revision=committed.sha,
                token=token)).read_bytes()
            if (sha256(original_zip).hexdigest() != source_digest
                    or original_zip != archive_file.read_bytes()
                    or imported_epub != epub):
                raise ValueError("Novel archive or EPUB independent hash mismatch")
            cover = book["metadata"].get("coverPath")
            if cover:
                covers += 1
                if cover not in snapshot:
                    raise ValueError("Catalogue links absent cover")
                from .inspection import valid_image
                bytes_ = Path(hf_hub_download(
                    repo_id=repo, repo_type="dataset", filename=cover,
                    revision=committed.sha, token=token)).read_bytes()
                if not valid_image(bytes_, Path(cover).suffix):
                    raise ValueError("Imported cover image invalid")
        if covers != 1:
            raise ValueError("Embedded cover was not imported")
        STAGE = 6
        with redirect_stdout(sink), redirect_stderr(sink):
            status = bulk_main(args + ["--apply"])
        if status != 0:
            raise ValueError("Idempotent synthetic import replay refused")
        if api.dataset_info(repo_id=repo, token=token).sha != committed.sha:
            raise ValueError("Import replay unnecessarily committed changes")
        STAGE = 7
        return {"Verified novel ZIPs": 3, "New novels uploaded": 3,
                "Covers uploaded": covers, "Unchanged novels": 3,
                "Verified complete": 1}


def main() -> int:
    if (os.getenv("GITHUB_REPOSITORY") !=
            "AdityaSreevatsaK/Taiyou-Novels-Storage-Controller" or
            os.getenv("GITHUB_REF") != "refs/heads/master"):
        print("ERROR: Trusted controller master only.", file=sys.stderr)
        return 2
    token = os.getenv("HF_DISPOSABLE_TEST_TOKEN", "").strip()
    if not token:
        print("ERROR: Dedicated test credential unavailable.", file=sys.stderr)
        return 2
    global STAGE
    STAGE = 0
    try:
        import huggingface_hub
        if huggingface_hub.__version__ != "1.33.0":
            raise ValueError("Expected pinned HF client unavailable")
        api = huggingface_hub.HfApi()
        identity = api.whoami(token=token)
        owner = identity.get("name") if isinstance(identity, dict) else None
        repo = import_repo(os.getenv("GITHUB_RUN_ID", ""),
                           os.getenv("GITHUB_RUN_ATTEMPT", ""), owner)
        result = run_acceptance(api, token, repo)
        for key, value in result.items():
            print(f"{key}: {value}")
        print(f"Acceptance stage: {STAGE}")
        return 0
    except Exception as error:
        # The GitHub wrapper publishes only numeric stage and error class.
        print(f"Acceptance stage: {STAGE}")
        code = {"ValueError": 1, "HfHubHTTPError": 3,
                "RepositoryNotFoundError": 4, "TypeError": 5,
                "AttributeError": 6}.get(type(error).__name__, 99)
        print(f"Acceptance error code: {code}")
        print("ERROR: Disposable import acceptance failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
