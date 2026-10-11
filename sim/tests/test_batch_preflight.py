"""PDK-free unit coverage for sim/bin/batch-preflight.py (issue #356).

Canned klt responses only: nothing is submitted, no ngspice/xschem/PDK needed.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR / "bin"))
_spec = importlib.util.spec_from_file_location("batch_preflight", SIM_DIR / "bin" / "batch-preflight.py")
bp = importlib.util.module_from_spec(_spec)
sys.modules["batch_preflight"] = bp
_spec.loader.exec_module(bp)


class FakeCR:
    class HarnessError(RuntimeError):
        pass


def response(remote=None, diagnostics=None, status="pass", errored=0):
    return {
        "status": status,
        "errored": errored,
        "environment": {"remote": {"provider": "aws-batch-fleet", **(remote or {})}},
        "corners": [{"corner_id": "tt/1.8V/27C", "diagnostics": diagnostics or []}],
    }


ACCEPTED = response({
    "job_id": "klt-sim-aaa111", "state": "succeeded",
    "runner_klt_version": "0.7.0", "client_klt_version": "0.7.0",
    "runner_compatibility": "compatible",
})
MISMATCH = response(
    {
        "job_id": "klt-sim-bbb222", "state": "failed", "exit_code": "87",
        "runner_klt_version": "0.5.0", "client_klt_version": "0.7.0",
        "runner_compatibility": "mismatch",
        "runner_compatibility_warning": "runner 0.5.0 vs client 0.7.0",
    },
    [{"severity": "error", "code": "batch_job_failed", "runner_code": bp.MISMATCH_CODE}],
    status="error", errored=1,
)
OTHER = response(
    {"job_id": "klt-sim-ccc333", "state": "failed", "runner_compatibility": "compatible"},
    [{"severity": "error", "code": "batch_job_failed", "message": "spot interrupted"}],
    status="error", errored=1,
)


class TestClassify(unittest.TestCase):
    def test_accepted(self):
        code, info = bp.classify(ACCEPTED)
        self.assertEqual(code, 0)
        self.assertEqual(info["job_id"], "klt-sim-aaa111")

    def test_mismatch(self):
        code, info = bp.classify(MISMATCH)
        self.assertEqual(code, 3)
        self.assertEqual((info["runner_klt_version"], info["client_klt_version"]), ("0.5.0", "0.7.0"))
        self.assertIn("0.5.0", info["reason"])

    def test_mismatch_by_runner_code_only(self):
        r = response({"job_id": "klt-sim-d"}, [{"runner_code": bp.MISMATCH_CODE, "runner_klt_version": "0.5.0"}])
        code, info = bp.classify(r)
        self.assertEqual(code, 3)
        self.assertEqual(info["runner_klt_version"], "0.5.0")

    def test_other_failure(self):
        code, info = bp.classify(OTHER)
        self.assertEqual(code, 1)
        self.assertIn("spot interrupted", info["reason"])

    def test_no_job_id_is_not_accepted(self):
        self.assertEqual(bp.classify(response())[0], 1)

    def test_unusable_responses(self):
        for bad in (None, {}, {"error": "x"}, {"corners": "no"}):
            self.assertEqual(bp.classify(bad)[0], 1)


class TestMain(unittest.TestCase):
    def run_main(self, submit, argv=()):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = bp.main(list(argv), cr=FakeCR, submit=submit)
        return code, out.getvalue()

    def test_exit_codes_and_report(self):
        for resp, want in ((ACCEPTED, 0), (MISMATCH, 3), (OTHER, 1)):
            code, text = self.run_main(lambda cr, d, r=resp: r)
            self.assertEqual(code, want)
            self.assertIn(resp["environment"]["remote"]["job_id"], text)
            self.assertIn("runner klt", text)

    def test_harness_error_is_exit_1(self):
        def boom(cr, d):
            raise cr.HarnessError("klt sim produced no stdout")
        code, text = self.run_main(boom)
        self.assertEqual(code, 1)
        self.assertIn("no stdout", text)

    def test_json_flag(self):
        code, text = self.run_main(lambda cr, d: MISMATCH, ["--json"])
        last = json.loads(text.strip().splitlines()[-1])
        self.assertEqual((code, last["exit"]), (3, 3))

    def test_scratch_removed_and_no_experiment_writes(self):
        seen = []
        before = sorted(p.name for p in (SIM_DIR / "pdk-smoke").iterdir())
        self.run_main(lambda cr, d: seen.append(d) or ACCEPTED)
        self.assertFalse(seen[0].exists())
        self.assertEqual(before, sorted(p.name for p in (SIM_DIR / "pdk-smoke").iterdir()))


if __name__ == "__main__":
    unittest.main()
