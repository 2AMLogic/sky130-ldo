"""PDK-free unit coverage for sim/bin/batch-preflight.py (issues #356, #359).

Canned klt responses only: nothing is submitted, no ngspice/xschem/PDK needed.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import unittest
from pathlib import Path
from _sim_script_loader import load_script  # noqa: E402

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR / "bin"))
bp = load_script("batch_preflight", SIM_DIR / "bin" / "batch-preflight.py", register=True)


class FakeCR:
    class HarnessError(RuntimeError):
        pass


def smoke_corner(status="pass", diagnostics=None, **over):
    """A realistic completed klt corner for the tt / 27 C smoke point."""
    corner = {
        "corner_id": "tt_27C", "process": "tt", "temperature_c": 27.0, "status": status,
        "measurements": [{"name": "meas_vout", "value": 0.9, "status": status}],
        "diagnostics": [] if diagnostics is None else diagnostics,
    }
    corner.update(over)
    return corner


def response(remote=None, diagnostics=None, status="pass", errored=0, corners=None):
    return {
        "status": status,
        "errored": errored,
        "environment": {"remote": {"provider": "aws-batch-fleet", **(remote or {})}},
        "corners": [smoke_corner(diagnostics=diagnostics)] if corners is None else corners,
    }


DONE = {
    "job_id": "klt-sim-aaa111", "state": "done", "exit_code": "0",
    "runner_klt_version": "0.7.0", "client_klt_version": "0.7.0",
    "runner_compatibility": "compatible",
}
ACCEPTED = response(DONE)
# A completed electrical FAIL: klt exits 3, the fleet harness marks the job
# "failed" with exit_code "3", yet the report is complete and collected.
MEAS_FAIL = response(
    {**DONE, "job_id": "klt-sim-eee555", "state": "failed", "exit_code": "3"},
    status="fail", corners=[smoke_corner(status="fail")],
)
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
    {"job_id": "klt-sim-ccc333", "state": "failed", "exit_code": "1", "runner_compatibility": "compatible"},
    [{"severity": "error", "code": "batch_job_failed", "message": "spot interrupted"}],
    status="error", errored=1,
)


def with_remote(**over):
    return response({**DONE, **over})


def with_corners(corners, **kw):
    return response(DONE, corners=corners, **kw)


class TestClassify(unittest.TestCase):
    def assert_rejected(self, resp, needle=None):
        code, info = bp.classify(resp)
        self.assertEqual(code, 1, info)
        self.assertTrue(info["reason"], "every rejection carries a reason")
        self.assertLessEqual(len(info["reason"]), bp.REASON_MAX)
        if needle:
            self.assertIn(needle, info["reason"])
        return info

    def test_accepted(self):
        code, info = bp.classify(ACCEPTED)
        self.assertEqual(code, 0)
        self.assertEqual(info["job_id"], "klt-sim-aaa111")
        self.assertEqual(info["job_state"], "done")
        self.assertEqual(info["reason"], "")

    def test_completed_measurement_fail_is_compatible(self):
        # Compatibility-only contract: electrical grading is not this probe's job.
        code, info = bp.classify(MEAS_FAIL)
        self.assertEqual(code, 0, info)
        self.assertEqual(info["job_id"], "klt-sim-eee555")

    def test_benign_warning_diagnostics_accepted(self):
        diags = [{"severity": "warning", "code": "gmin_stepping", "message": "fine"},
                 {"severity": "info", "message": "note"}]
        self.assertEqual(bp.classify(response(DONE, diags))[0], 0)

    def test_integer_exit_code_and_diagnostics_absent(self):
        self.assertEqual(bp.classify(with_remote(exit_code=0))[0], 0)
        corner = smoke_corner()
        del corner["diagnostics"]
        self.assertEqual(bp.classify(with_corners([corner]))[0], 0)

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

    def test_mismatch_precedence_over_generic_failures(self):
        mm_diag = {"severity": "error", "runner_code": bp.MISMATCH_CODE}
        cases = {
            "remote mismatch, no corners list": {
                "environment": {"remote": {"runner_compatibility": "mismatch"}}},
            "remote mismatch, empty corners, running": response(
                {"runner_compatibility": "mismatch", "state": "running"}, corners=[]),
            "remote mismatch, malformed diagnostics": response(
                {"runner_compatibility": "mismatch", "state": "failed"},
                corners=[smoke_corner(diagnostics="oops")]),
            "runner code mismatch, wrong corner + junk entries": response(
                {"state": "failed", "exit_code": "87"},
                corners=[smoke_corner(process="ss", status="error",
                                      diagnostics=[mm_diag, "junk", {"runner_code": ["x"]}])],
                status="error", errored=1),
            "runner code mismatch, duplicate corners, no job id": response(
                {"state": "failed"},
                corners=[smoke_corner(diagnostics=[mm_diag]), smoke_corner()]),
        }
        for name, resp in cases.items():
            with self.subTest(name):
                self.assertEqual(bp.classify(resp)[0], 3)

    def test_other_failure(self):
        info = self.assert_rejected(OTHER, "spot interrupted")
        self.assertEqual(info["job_id"], "klt-sim-ccc333")

    def test_no_job_id_is_not_accepted(self):
        self.assert_rejected(response({k: v for k, v in DONE.items() if k != "job_id"}), "no remote job id")
        self.assert_rejected(with_remote(job_id=""), "no remote job id")

    def test_unusable_responses(self):
        for bad in (None, {}, {"error": "x"}, {"corners": "no"}, [], "x", 3):
            with self.subTest(bad=bad):
                self.assert_rejected(bad)

    def test_corner_cardinality_and_identity(self):
        cases = {
            "empty corners": ([], "no corners"),
            "wrong process": ([smoke_corner(process="ff")], "unexpected corner"),
            "wrong temperature": ([smoke_corner(temperature_c=125.0)], "unexpected corner"),
            "duplicate smoke corner": ([smoke_corner(), smoke_corner()], "2 times"),
            "smoke plus extra": ([smoke_corner(), smoke_corner(process="ss")], "unexpected corner"),
            "only corner_id, no identity": ([{"corner_id": "tt_27C", "status": "pass", "diagnostics": []}],
                                            "malformed corner"),
        }
        for name, (corners, needle) in cases.items():
            with self.subTest(name):
                self.assert_rejected(with_corners(corners), needle)

    def test_malformed_corner_entries(self):
        for bad in (None, "tt", 7, [], {"process": "tt", "temperature_c": "27", "status": "pass"},
                    {"process": "tt", "temperature_c": True, "status": "pass"},
                    {"process": "tt", "temperature_c": float("nan"), "status": "pass"},
                    {"process": "tt", "temperature_c": 27.0},
                    {"process": "tt", "temperature_c": 27.0, "status": None},
                    {"process": 1, "temperature_c": 27.0, "status": "pass"}):
            with self.subTest(bad=bad):
                self.assert_rejected(with_corners([bad]), "malformed corner")

    def test_nonterminal_or_failed_remote_state(self):
        for over in ({"state": "running"}, {"state": "interrupted"}, {"state": "queued"},
                     {"state": "timeout"}, {"state": "failed", "exit_code": "1"},
                     {"state": "failed", "exit_code": ""}, {"state": "failed", "exit_code": None},
                     {"state": "failed", "exit_code": True}, {"state": None}, {"state": ""},
                     {"state": "DONE"}):
            with self.subTest(over=over):
                self.assert_rejected(with_remote(**over), "not a terminal successful execution")
        no_state = {k: v for k, v in DONE.items() if k != "state"}
        self.assert_rejected(response(no_state), "not a terminal successful execution")

    def test_running_with_job_id_and_empty_corners(self):
        # The exact blind spot reported in #359.
        info = self.assert_rejected(response({"job_id": "klt-sim-r", "state": "running"}, corners=[]))
        self.assertIn("running", info["reason"])
        self.assertIn("no corners", info["reason"])

    def test_incomplete_corner_status(self):
        for status in ("error", "inconclusive", "skipped", "", "PASS"):
            with self.subTest(status=status):
                self.assert_rejected(with_corners([smoke_corner(status=status)]), "not a completed result")

    def test_error_diagnostics_reject_without_runner_code(self):
        cases = {
            "message only": ([{"severity": "error", "message": "ngspice aborted"}], "ngspice aborted"),
            "code only": ([{"severity": "error", "code": "sim_failed"}], "sim_failed"),
            "bare error": ([{"severity": "error"}], "error diagnostic with no message"),
            "non-string message": ([{"severity": "error", "message": {"x": 1}}], "error diagnostic"),
            "runner code, no severity": ([{"runner_code": "batch_job_failed"}], "batch_job_failed"),
        }
        for name, (diags, needle) in cases.items():
            with self.subTest(name):
                self.assert_rejected(response(DONE, diags), needle)

    def test_malformed_diagnostics_fail_not_raise(self):
        for diags in ("oops", {"severity": "error"}, 5, ["junk"], [None], [["severity", "error"]],
                      [{"runner_code": ["unhashable"]}], [{"runner_code": {"a": 1}}],
                      [{"runner_code": 87}]):
            with self.subTest(diags=diags):
                self.assert_rejected(with_corners([smoke_corner(diagnostics=diags)]))

    def test_top_level_error_rejected_even_with_clean_corner(self):
        self.assert_rejected(response(DONE, status="error"), "klt sim status")
        self.assert_rejected(response(DONE, errored=1), "klt sim status")

    def test_reason_is_bounded(self):
        diags = [{"severity": "error", "message": "x" * 2000}] * 3
        self.assert_rejected(response(DONE, diags))


class TestMain(unittest.TestCase):
    def run_main(self, submit, argv=()):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = bp.main(list(argv), cr=FakeCR, submit=submit)
        return code, out.getvalue()

    def test_exit_codes_and_report(self):
        for resp, want in ((ACCEPTED, 0), (MEAS_FAIL, 0), (MISMATCH, 3), (OTHER, 1)):
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

    def test_json_flag_incomplete_response(self):
        running = response({"job_id": "klt-sim-r", "state": "running"}, corners=[])
        code, text = self.run_main(lambda cr, d: running, ["--json"])
        last = json.loads(text.strip().splitlines()[-1])
        self.assertEqual((code, last["exit"]), (1, 1))
        self.assertIn("FAILED", text)
        self.assertIn("running", last["reason"])

    def test_malformed_response_does_not_raise(self):
        bad = with_corners([smoke_corner(diagnostics=[{"runner_code": ["x"]}, "junk"])])
        code, text = self.run_main(lambda cr, d: bad)
        self.assertEqual(code, 1)
        self.assertIn("reason", text)

    def test_keep_retains_scratch(self):
        seen = []
        try:
            code, text = self.run_main(lambda cr, d: seen.append(d) or ACCEPTED, ["--keep"])
            self.assertEqual(code, 0)
            self.assertTrue(seen[0].is_dir())
            self.assertIn(str(seen[0]), text)
        finally:
            for d in seen:
                shutil.rmtree(d, ignore_errors=True)

    def test_scratch_removed_and_no_experiment_writes(self):
        def snapshot():
            return sorted((str(p), p.stat().st_mtime_ns) for p in (SIM_DIR / "pdk-smoke").rglob("*"))

        running = response({"job_id": "klt-sim-r", "state": "running"}, corners=[])
        before = snapshot()
        for resp in (ACCEPTED, MEAS_FAIL, MISMATCH, OTHER, running):
            seen = []
            self.run_main(lambda cr, d, r=resp: seen.append(d) or r)
            self.assertFalse(seen[0].exists())
        self.assertEqual(before, snapshot())


if __name__ == "__main__":
    unittest.main()
