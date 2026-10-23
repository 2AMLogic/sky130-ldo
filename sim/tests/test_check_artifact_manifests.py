"""Tests for scripts/check_artifact_manifests.py (issue #436)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

_p = Path(__file__).resolve().parents[2] / "scripts" / "check_artifact_manifests.py"
_spec = importlib.util.spec_from_file_location("check_artifact_manifests", _p)
chk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chk)


def entry(data: bytes, uri: str | None = None, name: str = "sim/b/x.log") -> dict:
    sha = hashlib.sha256(data).hexdigest()
    return {"sha256": sha, "size": len(data), "name": name, "kind": "evidence",
            "uri": uri if uri is not None else f"artifact:evidence/r/{sha[:2]}/{sha}"}


class CheckManifestsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "sim" / "b").mkdir(parents=True)
        (self.root / "manifests" / "artifacts").mkdir(parents=True)

    def manifest(self, *entries):
        (self.root / "manifests" / "artifacts" / "b-r.manifest.json").write_text(
            json.dumps({"schema_version": 1, "entries": list(entries)})
        )

    def track(self, rel: str, data: bytes):
        p = self.root / rel
        p.write_bytes(data)
        subprocess.run(["git", "-C", str(self.root), "add", rel], check=True)

    def test_good_manifest(self):
        self.track("sim/b/other.txt", b"unrelated")
        self.manifest(entry(b"stored bytes"))
        self.assertEqual(chk.check(self.root), [])

    def test_no_manifests_ok(self):
        self.assertEqual(chk.check(self.root), [])

    def test_non_artifact_uri_fails(self):
        self.manifest(entry(b"x", uri="https://example.invalid/x"))
        self.assertTrue(any("artifact:" in e for e in chk.check(self.root)))

    def test_bucket_identifier_fails(self):
        e = entry(b"x")
        e["note"] = "s3://bucket/key"
        self.manifest(e)
        self.assertTrue(any("s3://" in e for e in chk.check(self.root)))

    def test_committed_duplicate_bytes_fail(self):
        self.track("sim/b/dup.log", b"same bytes")
        self.manifest(entry(b"same bytes"))
        errs = chk.check(self.root)
        self.assertTrue(any("sim/b/dup.log" in e and "duplicate" in e for e in errs))

    def test_untracked_duplicate_ignored(self):
        (self.root / "sim" / "b" / "scratch.log").write_bytes(b"same bytes")
        self.manifest(entry(b"same bytes"))
        self.assertEqual(chk.check(self.root), [])

    def test_empty_object_not_matched(self):
        self.track("sim/b/empty", b"")
        self.manifest(entry(b""))
        self.assertEqual(chk.check(self.root), [])

    def test_bad_schema(self):
        (self.root / "manifests" / "artifacts" / "b-r.manifest.json").write_text(
            json.dumps({"schema_version": 2, "entries": [{"sha256": "zz"}]})
        )
        self.assertGreaterEqual(len(chk.check(self.root)), 3)


if __name__ == "__main__":
    unittest.main()
