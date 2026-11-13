"""Tests for the shared batch-fleet campaign core, sim/bin/_fleet_campaign.py
(issue #574). Pure python: nothing is netlisted, nothing is submitted."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR / "bin"))
import _fleet_campaign as fc  # noqa: E402

PDK = {"variant": "sky130A", "ngspice_lib": "libs.tech/combined/sky130.lib.spice"}


def resp(job="job-1", status="pass", corners=2):
    return {
        "status": status,
        "corner_count": corners,
        "environment": {"remote": {"job_id": job}},
        "corners": [
            {
                "process": "tt",
                "temperature_c": 27.0,
                "status": "pass",
                "measurements": [{"name": "pm", "value": 60.0}],
            }
        ],
    }


class SubmitAll(unittest.TestCase):
    """The failed-submit branch is the one that had drifted between the three
    copies, so it is the one pinned here."""

    def _run(self, results, workers=2):
        jobs = [(k, {"leg": k}, Path(f"/nonexistent/{k}.json")) for k in results]
        errors: list = []
        buf = io.StringIO()
        with mock.patch.object(fc, "submit", lambda k, rp, out, env: results[k]):
            with contextlib.redirect_stdout(buf):
                got = list(
                    fc.submit_all(jobs, Path("/nonexistent"), {}, workers, errors)
                )
        return got, errors, buf.getvalue()

    def test_failed_submit_is_recorded_and_never_yielded(self):
        got, errors, printed = self._run(
            {
                "ok": {"key": "ok", "resp": resp()},
                "bad": {"key": "bad", "error": "batch_no_capacity"},
            }
        )
        self.assertEqual([k for k, _m, _r, _j in got], ["ok"])
        self.assertEqual(errors, [{"key": "bad", "error": "batch_no_capacity"}])
        self.assertIn(
            "bad: SUBMIT FAILED (no local fallback): batch_no_capacity", printed
        )
        self.assertNotIn("ok: SUBMIT FAILED", printed)

    def test_error_text_is_truncated_in_the_status_line_only(self):
        got, errors, printed = self._run({"bad": {"key": "bad", "error": "x" * 900}})
        self.assertEqual(got, [])
        self.assertEqual(len(errors[0]["error"]), 900)  # the record keeps it all
        self.assertIn("x" * 300 + "\n", printed)
        self.assertNotIn("x" * 301, printed)

    def test_every_submit_can_fail_without_raising(self):
        got, errors, _ = self._run(
            {k: {"key": k, "error": "refused"} for k in ("a", "b", "c")}
        )
        self.assertEqual(got, [])
        self.assertEqual([e["key"] for e in errors], ["a", "b", "c"])

    def test_yields_in_job_order_with_meta_and_job_id(self):
        got, errors, printed = self._run(
            {
                "a": {"key": "a", "resp": resp("J1")},
                "b": {"key": "b", "resp": resp("J2")},
            }
        )
        self.assertEqual(
            [(k, m["leg"], j) for k, m, _r, j in got],
            [("a", "a", "J1"), ("b", "b", "J2")],
        )
        self.assertEqual(errors, [])
        self.assertIn("a: pass (2 corners) job J1", printed)

    def test_missing_remote_block_yields_a_none_job_id(self):
        r = resp()
        del r["environment"]
        got, _errors, _ = self._run({"a": {"key": "a", "resp": r}})
        self.assertIsNone(got[0][3])


class Request(unittest.TestCase):
    def test_default_shape_keeps_analysis_and_measurements_inline(self):
        req = fc.base_request(
            Path("/n/x.spice"),
            PDK,
            [("ss", 125.0), ("tt", -40.0)],
            {"kind": "ac"},
            [{"name": "pm"}],
        )
        self.assertEqual(
            list(req),
            [
                "netlist",
                "engine",
                "models",
                "corners",
                "analysis",
                "measurements",
                "options",
                "batch",
            ],
        )
        # process order follows PROCESS, temperatures sort numerically
        self.assertEqual(
            req["corners"], {"process": ["tt", "ss"], "temperature_c": [-40.0, 125.0]}
        )

    def test_shape_replaces_the_pair_and_lands_after_options(self):
        """The `analysis_steps` callers used to build an `op` request and pop it
        back out; `shape=` replaces that, in the same emitted key order."""
        req = fc.base_request(
            Path("/n/x.spice"),
            PDK,
            [("tt", 27.0)],
            shape={"analysis_steps": [{"name": "op_0"}]},
        )
        self.assertEqual(
            list(req),
            [
                "netlist",
                "engine",
                "models",
                "corners",
                "options",
                "batch",
                "analysis_steps",
            ],
        )
        self.assertNotIn("analysis", req)
        self.assertNotIn("measurements", req)


class NetlistEdits(unittest.TestCase):
    BODY = ".subckt inner a b\nR1 a b 1k\n.ends\n.subckt ldo vin vout\nR2 vin vout 1k\n.ends\n"

    def test_probe_goes_inside_the_last_subckt(self):
        out = fc.insert_loop_gain_probe(self.BODY).splitlines()
        self.assertEqual(out[out.index(fc.LOOP_GAIN_PROBE) + 1], ".ends")
        self.assertEqual(out.index(fc.LOOP_GAIN_PROBE), len(out) - 2)

    def test_sub_line_rewrites_exactly_one_card(self):
        body = "RLOAD VOUT 0 36 m=1\nRLOADX VOUT 0 36 m=1\n"
        self.assertEqual(
            fc.sub_line(body, "RLOAD", "RLOAD VOUT 0 1.8k m=1"),
            "RLOAD VOUT 0 1.8k m=1\nRLOADX VOUT 0 36 m=1\n",
        )

    def test_sub_line_exits_when_the_card_is_missing(self):
        with self.assertRaises(SystemExit):
            fc.sub_line("R1 a b 1k\n", "RLOAD", "RLOAD VOUT 0 36 m=1")

    def test_loop_transfer_meas_is_the_four_klt_metrics(self):
        self.assertEqual(
            [(m["name"], m["transfer"]["metric"]) for m in fc.LOOP_TRANSFER_MEAS],
            [
                ("pm", "phase_margin_deg"),
                ("gm", "gain_margin_db"),
                ("fc", "unity_crossing_hz"),
                ("dc", "low_frequency_magnitude"),
            ],
        )


class Preamble(unittest.TestCase):
    def test_worker_cap_is_the_host_rule(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as cm:
                fc.preamble(fc.MAX_WORKERS + 1, Path(d) / "new")
            self.assertIn("no more than 2 workers", str(cm.exception))

    def test_refuses_to_overwrite_an_existing_record(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as cm:
                fc.preamble(2, Path(d))
            self.assertIn("refusing to overwrite", str(cm.exception))

    def test_resume_may_reuse_an_existing_record_dir(self):
        with tempfile.TemporaryDirectory() as d:
            pdk, pdk_root, env = fc.preamble(2, Path(d), allow_existing=True)
            self.assertEqual(pdk["variant"], "sky130A")
            self.assertEqual(env["PDK_ROOT"], pdk_root)


class Rows(unittest.TestCase):
    def test_corner_base_carries_meta_then_the_shared_fields(self):
        row = fc.corner_base(
            "k1",
            {"design": "candA", "leg": "0.33u/10m/0mA"},
            {"process": "ss", "temperature_c": 125.0, "status": "fail"},
            "J9",
        )
        self.assertEqual(
            row,
            {
                "design": "candA",
                "leg": "0.33u/10m/0mA",
                "key": "k1",
                "process": "ss",
                "temp_c": 125.0,
                "status": "fail",
                "job_id": "J9",
            },
        )
        self.assertEqual(list(row)[:2], ["design", "leg"])


if __name__ == "__main__":
    unittest.main()
