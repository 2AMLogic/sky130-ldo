"""Tests for sim/bin/_evidence_store.py (issue #436): fake broker + stub klt."""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))
import _evidence_store as ev  # noqa: E402

STUB = """#!/usr/bin/env python3
import hashlib, json, os, sys
a = sys.argv[1:]
if a[:2] != ["artifact", "put"] or os.environ.get("STUB_NO_VERB"):
    sys.exit(2)
if "--help" in a:
    sys.exit(0)
if os.environ.get("STUB_FAIL_PUT"):
    print("broker refused", file=sys.stderr)
    sys.exit(1)
name = a[a.index("--name") + 1]
man = a[a.index("--manifest") + 1]
data = open(a[-1], "rb").read()
doc = json.load(open(man)) if os.path.exists(man) else {"schema_version": 1, "entries": []}
sha = hashlib.sha256(data).hexdigest()
doc["entries"].append({"sha256": sha, "size": len(data), "name": name, "kind": "evidence",
                       "uri": "artifact:evidence/x/" + sha[:2] + "/" + sha})
json.dump(doc, open(man, "w"))
"""


class _Ok(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.end_headers()

    def log_message(self, *a):
        pass


class EvidenceStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.klt = Path(self.tmp.name) / "klt"
        self.klt.write_text(STUB)
        self.klt.chmod(self.klt.stat().st_mode | stat.S_IXUSR)
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), _Ok)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        env = {ev.BROKER_ENV: self.url}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for k in ("STUB_NO_VERB", "STUB_FAIL_PUT"):
            os.environ.pop(k, None)

    def assertNothingWritten(self):
        self.assertFalse((self.root / "manifests").exists())
        self.assertFalse((self.root / "sim").glob("*") and any(
            p for p in (self.root / "sim").rglob("*") if p.is_file() and ".stage" not in p.parts
        ))

    def test_success_writes_manifest_and_summary(self):
        klt = ev.preflight(str(self.klt))
        run = ev.EvidenceRun(self.root, "bench", "rid", klt)
        run.stage_text("corners/rid/a.log", "hello\n")
        run.stage_text("records/rid.json", "")  # empty file is allowed
        entries = run.commit()
        manifest = json.loads(run.manifest_path.read_text())
        self.assertEqual(len(manifest["entries"]), 2)
        self.assertTrue(all(e["uri"].startswith("artifact:") for e in manifest["entries"]))
        names = {e["name"] for e in entries}
        self.assertEqual(names, {"sim/bench/corners/rid/a.log", "sim/bench/records/rid.json"})
        md = "\n".join(ev.render_summary(entries, run.manifest_rel()))
        self.assertIn(hashlib.sha256(b"hello\n").hexdigest(), md)
        self.assertNotIn(self.url, md)

    def test_broker_unset(self):
        del os.environ[ev.BROKER_ENV]
        with self.assertRaisesRegex(ev.EvidenceStoreError, "KLT_ARTIFACT_BROKER"):
            ev.preflight(str(self.klt))
        self.assertNothingWritten()

    def test_verb_missing(self):
        os.environ["STUB_NO_VERB"] = "1"
        with self.assertRaisesRegex(ev.EvidenceStoreError, "no `artifact put`"):
            ev.preflight(str(self.klt))

    def test_klt_missing(self):
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(ev.EvidenceStoreError, "klt not found"):
                ev.preflight()

    def test_broker_unreachable_does_not_leak_url(self):
        self.srv.shutdown()
        self.srv.server_close()
        with self.assertRaises(ev.EvidenceStoreError) as cm:
            ev.preflight(str(self.klt), timeout=2)
        self.assertNotIn(self.url, str(cm.exception))
        self.assertNothingWritten()

    def test_put_failure_commits_nothing(self):
        run = ev.EvidenceRun(self.root, "bench", "rid", str(self.klt))
        run.stage_text("records/rid.json", "{}\n")
        os.environ["STUB_FAIL_PUT"] = "1"
        with self.assertRaisesRegex(ev.EvidenceStoreError, "put failed"):
            run.commit()
        self.assertFalse(run.manifest_path.exists())
        self.assertFalse((self.root / "manifests").exists())

    def test_existing_manifest_refused(self):
        run = ev.EvidenceRun(self.root, "bench", "rid", str(self.klt))
        run.stage_text("records/rid.json", "{}\n")
        run.manifest_path.parent.mkdir(parents=True)
        run.manifest_path.write_text("{}")
        with self.assertRaisesRegex(ev.EvidenceStoreError, "append-only"):
            run.commit()


if __name__ == "__main__":
    unittest.main()
