"""Issue #491: the one shared `klt sim` wrapper in `_record_common.run_klt_sim`.

Headless: subprocess.run and time.sleep are mocked; nothing is submitted.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import _record_common as rc  # noqa: E402


class Boom(Exception):
    pass


def done(rc_, out="", err=""):
    return subprocess.CompletedProcess(["klt"], rc_, stdout=out, stderr=err)


class RunKltSim(unittest.TestCase):
    def call(self, result, **kw):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        req = tmp / "r.json"
        req.write_text("{}")
        run = mock.Mock(side_effect=result if isinstance(result, list) else [result])
        with mock.patch.object(rc.subprocess, "run", run), mock.patch.object(rc.time, "sleep"):
            try:
                out, err = rc.run_klt_sim(
                    req, tmp / "out", "batch", tmp, klt_exe="/fake/klt", error_cls=Boom, **kw
                ), None
            except Boom as exc:
                out, err = None, str(exc)
        return out, err, run, tmp

    def test_success_persists_output_and_reports_meta(self):
        body = json.dumps({"corners": []})
        out, err, run, tmp = self.call(done(0, body, "job klt-sim-abc123"))
        self.assertIsNone(err)
        response, meta = out
        self.assertEqual(response, {"corners": []})
        self.assertEqual(meta["returncode"], 0)
        self.assertEqual(meta["job_ids_seen"], ["klt-sim-abc123"])
        self.assertEqual(meta["cmd"][:2], ["/fake/klt", "sim"])
        self.assertEqual((tmp / "out" / "klt.stdout").read_text(), body)
        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["env"]["PDK_ROOT"], str(tmp))

    def test_error_envelope_refused_unless_corners_not_required(self):
        envelope = json.dumps({"error": "bad request"})
        _, err, _, _ = self.call(done(2, envelope))
        self.assertIn("error envelope", err)
        out, err, _, _ = self.call(done(0, envelope), require_corners=False)
        self.assertIsNone(err)
        self.assertEqual(out[0], {"error": "bad request"})

    def test_empty_and_non_json_stdout_raise_error_cls(self):
        self.assertIn("no stdout", self.call(done(1, "", "boom"))[1])
        self.assertIn("non-JSON", self.call(done(0, "not json"))[1])

    def test_capacity_retry_only_when_requested(self):
        cap = "launch failed: 9 exceeds BATCH_MAX_CONCURRENT_INSTANCES=8"
        _, err, run, _ = self.call(done(1, "", cap))
        self.assertEqual(run.call_count, 1)
        self.assertIsNotNone(err)
        out, err, run, _ = self.call(
            [done(1, "", cap), done(0, json.dumps({"corners": []}))], retry_capacity=True
        )
        self.assertIsNone(err)
        self.assertEqual(run.call_count, 2)

    def test_extra_args_and_resolve_paths(self):
        _, _, run, _ = self.call(
            done(0, json.dumps({"corners": []})), extra_args=("--max-workers", "2"), resolve_paths=True
        )
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[-2:], ["--max-workers", "2"])
        self.assertTrue(Path(cmd[cmd.index("-o") + 1]).is_absolute())


if __name__ == "__main__":
    unittest.main()
