"""Offline regression coverage for remote inspection sidecars and migration."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import zipfile

from PIL import Image

from taiyou_storage.inspection import Snapshot, scan
from taiyou_storage.inspection_cli import run as inspect_run
from taiyou_storage.inspection_manifest import (
    _git_blob, build_manifest, local_artifact, manifest_bytes, manifest_path,
    match_artifact, read_manifest, upload_sidecar,
)
from taiyou_storage.manifest_backfill import apply, generate, plan, run as backfill_run
from taiyou_storage.core import StorageError

IDENT = "a" * 24
REV = "1" * 40


def make_epub() -> bytes:
    data = BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml",
                   '<container><rootfile full-path="OEBPS/content.opf"/></container>')
        z.writestr("OEBPS/content.opf", '<package><metadata/><manifest/><spine/></package>')
    return data.getvalue()


def make_zip(epub: bytes, gap=False) -> bytes:
    data = BytesIO()
    positions = (1, 3) if gap else (1, 2)
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("source.epub", epub)
        z.writestr("chapters.json", json.dumps([
            {"position": i, "file": f"chapter_{i}.txt"} for i in positions]))
        for i in positions:
            z.writestr(f"chapter_{i}.txt", "Chapter " + str(i))
    return data.getvalue()


def book(cover=True):
    root = "data/novels/" + IDENT
    meta = {"id": IDENT, "title": "Synthetic Book", "author": "Synthetic Writer",
            "chapterCount": 2, "sourceUrl": "https://example.com/novel"}
    if cover:
        meta["coverPath"] = root + "/cover.png"
    return {"id": IDENT, "metadata": meta, "epubPath": root + "/source.epub",
            "archivePath": root + "/original.zip"}


class Backend:
    def __init__(self, root: Path, cover=True):
        self.root = root
        self.repo = "AdityaSreevatsaK/Taiyous-Novels"
        self.books = [book(cover=cover)]
        self.calls = []
        self.rev = REV
        root.mkdir(parents=True, exist_ok=True)
        epub = make_epub()
        self.add("data/library.json", json.dumps({"version": 1, "books": self.books}).encode())
        self.add(self.books[0]["epubPath"], epub)
        self.add(self.books[0]["archivePath"], make_zip(epub))
        if cover:
            img = BytesIO()
            Image.new("RGB", (200, 260), (1, 35, 90)).save(img, format="PNG")
            self.add(self.books[0]["metadata"]["coverPath"], img.getvalue())

    def add(self, name: str, data: bytes) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def snapshot(self):
        files = {p.relative_to(self.root).as_posix(): p.stat().st_size
                 for p in self.root.rglob("*") if p.is_file()}
        identities = {name: {"size": size, "blob_id": _git_blob(self.root / name)}
                      for name, size in files.items()}
        return Snapshot(self.rev, files, identities)

    def download(self, name: str, revision: str):
        assert revision == self.rev
        self.calls.append(name)
        return self.root / name


class RemoteManifestTests(unittest.TestCase):
    def test_remote_inventory_uses_only_catalogue_and_sidecar(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp))
            value = generate(backend, backend.snapshot(), backend.books[0])
            backend.add(manifest_path(backend.books[0]), manifest_bytes(value))
            backend.calls.clear()
            found = scan(backend, "manifest")
            self.assertEqual(found["novels"][0]["verification_status"], "VERIFIED_RANGE")
            self.assertEqual(found["novels"][0]["chapter_ranges"], ["1-2"])
            self.assertEqual(found["novels"][0]["cover_status"], "AVAILABLE")
            self.assertEqual(set(backend.calls), {"data/library.json", manifest_path(backend.books[0])})
            self.assertNotIn("source.epub", " ".join(backend.calls))

    def test_zip_content_change_invalidates_sidecar(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp))
            backend.add(manifest_path(backend.books[0]),
                        manifest_bytes(generate(backend, backend.snapshot(), backend.books[0])))
            backend.add(backend.books[0]["archivePath"], make_zip(make_epub(), gap=True))
            backend.calls.clear()
            found = scan(backend, "manifest")
            self.assertEqual(found["novels"][0]["verification_status"], "UNVERIFIED")
            self.assertIn("INSPECTION_MANIFEST_STALE", [e["code"] for e in found["issues"]])
            self.assertNotIn(backend.books[0]["archivePath"], backend.calls)

    def test_missing_manifest_never_claims_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp))
            found = scan(backend, "manifest")
            self.assertEqual(found["novels"][0]["verification_status"], "UNVERIFIED")
            self.assertEqual(set(backend.calls), {"data/library.json"})

    def test_missing_remote_hash_refuses_size_only_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp))
            doc = generate(backend, backend.snapshot(), backend.books[0])
            raw = manifest_bytes(doc)
            with self.assertRaisesRegex(ValueError, "identity"):
                read_manifest(backend.books[0], raw,
                              backend.snapshot().files, {})

    def test_unlinked_cover_is_accepted_only_when_unique(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp), cover=False)
            buf = BytesIO()
            Image.new("RGB", (200, 250), (33, 44, 55)).save(buf, format="PNG")
            backend.add("data/novels/" + IDENT + "/cover.png", buf.getvalue())
            doc = generate(backend, backend.snapshot(), backend.books[0])
            self.assertEqual(doc["inspection"]["cover_status"], "AVAILABLE")
            read_manifest(backend.books[0], manifest_bytes(doc),
                          backend.snapshot().files, backend.snapshot().identities)

    def test_hash_matching_accepts_git_blob_and_lfs_pointer(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.epub"
            path.write_bytes(make_epub())
            item = local_artifact("x/source.epub", path)
            self.assertTrue(match_artifact(item, {
                "size": path.stat().st_size, "blob_id": item["git_blob_sha1"]}))
            self.assertTrue(match_artifact(item, {
                "size": path.stat().st_size, "blob_id": item["lfs_pointer_blob_sha1"]}))
            self.assertFalse(match_artifact(item, {"size": path.stat().st_size}))

    def test_upload_sidecar_can_verify_source_zip(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp))
            b = backend.books[0]
            source = backend.root / b["archivePath"]
            raw = upload_sidecar(b, source, (backend.root / b["epubPath"]).read_bytes())
            doc = json.loads(raw)
            self.assertEqual(doc["inspection"]["verification_status"], "VERIFIED_RANGE")
            self.assertEqual(doc["inspection"]["cover_status"], "UNVERIFIED")
            read_manifest(b, raw, backend.snapshot().files, backend.snapshot().identities)

    def test_remote_report_defaults_to_manifest_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp) / "dataset")
            doc = generate(backend, backend.snapshot(), backend.books[0])
            backend.add(manifest_path(backend.books[0]), manifest_bytes(doc))
            backend.calls.clear()
            self.assertEqual(inspect_run(["inventory", "--reports-dir", str(Path(temp) / "reports")],
                                         backend), 0)
            self.assertEqual(set(backend.calls), {"data/library.json", manifest_path(backend.books[0])})


class BackfillTests(unittest.TestCase):
    def test_preview_generates_and_resumes_without_new_binary_downloads(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp) / "dataset")
            reports = Path(temp) / "reports"
            snapshot, files, first = plan(backend, reports)
            self.assertEqual(len(files), 1)
            self.assertEqual(first["generated"], 1)
            self.assertTrue((reports / "manifest-backfill" / (IDENT + ".json")).exists())
            backend.calls.clear()
            again, files2, status = plan(backend, reports)
            self.assertEqual(status["reused_local"], 1)
            self.assertEqual(files, files2)
            self.assertEqual(backend.calls, ["data/library.json"])
            self.assertEqual(snapshot.revision, again.revision)

    def test_remote_valid_sidecar_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp) / "dataset")
            doc = generate(backend, backend.snapshot(), backend.books[0])
            backend.add(manifest_path(backend.books[0]), manifest_bytes(doc))
            _, entries, status = plan(backend, Path(temp) / "reports")
            self.assertEqual(entries, [])
            self.assertEqual(status["already_valid"], 1)

    def test_preview_never_invokes_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp) / "dataset")
            self.assertEqual(backfill_run(["--reports-dir", str(Path(temp) / "reports")],
                                          backend=backend), 0)
            self.assertNotIn(manifest_path(backend.books[0]), backend.snapshot().files)

    def test_commit_only_sidecars_with_parent_revision(self):
        class Api:
            def __init__(self):
                self.head = REV
                self.paths = []
                self.parents = []
            def dataset_info(self, repo, token):
                return SimpleNamespace(private=True, sha=self.head)
            def create_commit(self, **kwargs):
                self.parents.append(kwargs["parent_commit"])
                self.paths.extend(op.path_in_repo for op in kwargs["operations"])
                self.head = "2" * 40
                return SimpleNamespace(oid=self.head)

        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp))
            snapshot, selected, _ = plan(backend, Path(temp) / "reports")
            api = Api()
            self.assertEqual(apply(backend, snapshot, selected, api=api, token="test"), 1)
            self.assertEqual(api.parents, [REV])
            self.assertEqual(api.paths, [manifest_path(backend.books[0])])

    def test_concurrent_revision_drift_blocks_write(self):
        class Api:
            def dataset_info(self, repo, token):
                return SimpleNamespace(private=True, sha="9" * 40)
            def create_commit(self, **kwargs):
                raise AssertionError("Should not commit after drift")

        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp))
            snapshot, selected, _ = plan(backend, Path(temp) / "reports")
            with self.assertRaisesRegex(StorageError, "changed"):
                apply(backend, snapshot, selected, api=Api(), token="test")

    def test_windows_backfill_launcher_exists(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "17_backfill_inspection_manifests.cmd").read_text()
        self.assertIn("taiyou_storage.manifest_backfill", text)
        self.assertIn("%*", text)


if __name__ == "__main__":
    unittest.main()
