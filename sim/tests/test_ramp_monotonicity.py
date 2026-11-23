"""PDK-free tests for the startup ramp-monotonicity checker (issue #309)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))
import ramp_monotonicity as rm  # noqa: E402
from _sim_script_loader import load_script  # noqa: E402

SET = {"t_enable_s": 1.0e-4, "v_low": 1.764, "max_dt_s": 2.0e-5, "min_samples": 20}


def ramp(dip=None, n=60, t0=0.0, dt=1.0e-5):
    """Cold-enable ramp: 0 V until 100 us, then a rise to 1.8 V. `dip` =
    (index, depth) subtracts a dip while still below the window."""
    t = [t0 + i * dt for i in range(n)]
    v = [0.0 if x < 1.0e-4 else min(1.8, (x - 1.0e-4) * 1.8 / 4.0e-4) for x in t]
    if dip:
        i, d = dip
        for k in (i, i + 1):
            v[k] -= d
    return t, v


class TestChecker(unittest.TestCase):
    def test_monotone_passes(self):
        r = rm.check_ramp_monotonicity(*ramp(), SET)
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["max_drawdown_v"], 0.0)
        self.assertGreaterEqual(r["n_window_samples"], 20)
        self.assertAlmostEqual(r["resolution_s"], 1e-5)

    def test_dip_before_settling_is_detected(self):
        t, v = ramp(dip=(30, 0.2))
        # the old scalar gates would pass: peak < 1.836 and settled floor >= 1.764
        self.assertLessEqual(max(v), 1.836)
        self.assertGreaterEqual(min(v[52:]), 1.764)
        r = rm.check_ramp_monotonicity(t, v, SET)
        self.assertEqual(r["status"], "FAIL")
        self.assertAlmostEqual(r["max_drawdown_v"], v[29] - v[30], places=9)
        a, b = r["worst_interval_s"]
        self.assertAlmostEqual(a, t[29], places=12)
        self.assertAlmostEqual(b, t[30], places=12)

    def test_tolerance_is_recorded_not_defaulted_up(self):
        r = rm.check_ramp_monotonicity(*ramp(), SET)
        self.assertEqual(r["settings"]["tolerance_v"], 0.0)

    def test_post_entry_dip_not_counted(self):
        t, v = ramp()
        v[-1] = 1.0  # after window entry: ripple/settling is another check
        self.assertEqual(rm.check_ramp_monotonicity(t, v, SET)["status"], "PASS")

    def test_invalid_traces_never_pass(self):
        t, v = ramp()
        cases = {
            "none": (None, None),
            "empty": ([], []),
            "length": (t, v[:-1]),
            "nan": (t, v[:10] + [float("nan")] + v[11:]),
            "inf": (t[:5] + [float("inf")] + t[6:], v),
            "unordered": (t[:20] + [t[20], t[19]] + t[22:], v),
            "duplicate_time": (t[:20] + [t[19]] + t[21:], v),
            "starts_after_enable": (t[15:], v[15:]),
            "never_enters": (t, [min(x, 1.5) for x in v]),
            "truncated_before_entry": (t[:15], v[:15]),
        }
        for name, (tt, vv) in cases.items():
            with self.subTest(name):
                r = rm.check_ramp_monotonicity(tt, vv, SET)
                self.assertEqual(r["status"], "INVALID")
                self.assertFalse(r["pass"])

    def test_insufficient_sampling_is_invalid(self):
        t, v = ramp(n=60, dt=1.0e-5)
        coarse = rm.check_ramp_monotonicity(t[::5], v[::5], SET)  # 50 us gaps
        self.assertEqual(coarse["status"], "INVALID")
        few = rm.check_ramp_monotonicity(*ramp(), {**SET, "min_samples": 500})
        self.assertEqual(few["status"], "INVALID")

    def test_missing_settings_invalid(self):
        s = dict(SET)
        del s["max_dt_s"]
        self.assertEqual(rm.check_ramp_monotonicity(*ramp(), s)["status"], "INVALID")

    def test_parse_trace(self):
        self.assertEqual(rm.parse_trace("0 0\n1e-5 1.5e-1\n"), ([0.0, 1e-5], [0.0, 0.15]))
        with self.assertRaises(ValueError):
            rm.parse_trace("0 0 0\n")
        with self.assertRaises(ValueError):
            rm.parse_trace("0 abc\n")


class TestLegs(unittest.TestCase):
    def test_four_independent_legs(self):
        legs = ["a", "b", "c", "d"]
        cfg = {**SET, "signal": "v(vout)", "legs": [{"id": x} for x in legs]}
        with tempfile.TemporaryDirectory() as d:
            for x in legs[:3]:
                t, v = ramp(dip=(30, 0.2) if x == "b" else None)
                Path(d, f"tt_27c_3.30v.{x}.trace.dat").write_text(
                    "".join(f"{a!r} {b!r}\n" for a, b in zip(t, v))
                )
            # leg d: file missing entirely
            res = rm.evaluate_legs(cfg, Path(d), "tt_27c_3.30v")
        self.assertEqual([r["leg"] for r in res], legs)
        self.assertEqual([r["status"] for r in res], ["PASS", "FAIL", "PASS", "INVALID"])
        self.assertTrue(res[0]["trace_sha256"])
        self.assertIsNone(res[3]["trace_sha256"])
        self.assertEqual(res[0]["settings"]["t_enable_s"], 1e-4)


class TestRampCheckRow(unittest.TestCase):
    """Issue #736: the per-leg condition as a corner check row -- one builder
    (moved here from batch_startup_ramp) shared by the local run_corner loop
    and the batch startup normalizer, so the two rows cannot drift."""

    @staticmethod
    def leg(res, leg_id="c330n_0ma_esr0"):
        res.update({"leg": leg_id, "trace_file": "f.trace.dat", "trace_sha256": None})
        return res

    def test_pass_row(self):
        row = rm.ramp_check(self.leg(rm.check_ramp_monotonicity(*ramp(), {**SET, "tolerance_v": 0.0})))
        self.assertEqual(row["name"], "ramp_drawdown_c330n_0ma_esr0_v")
        self.assertEqual(row["expr"], "ramp_monotonicity.max_drawdown(v(vout))")
        self.assertEqual(row["unit"], "V")
        self.assertEqual(row["value"], 0.0)
        self.assertIsNone(row["min"])
        self.assertEqual(row["max"], 0.0)  # the manifest's tolerance_v
        self.assertIs(row["pass"], True)
        self.assertEqual(row["reason"], "")

    def test_fail_row_carries_status_and_reasons(self):
        res = rm.check_ramp_monotonicity(*ramp(dip=(30, 0.2)), {**SET, "tolerance_v": 0.0})
        row = rm.ramp_check(self.leg(res))
        self.assertIs(row["pass"], False)
        self.assertEqual(row["value"], res["max_drawdown_v"])
        self.assertTrue(row["reason"].startswith("FAIL: "), row["reason"])

    def test_invalid_leg_never_passes(self):
        res = rm.invalid_result({**SET, "tolerance_v": 0.0}, ["trace unreadable: nope"])
        row = rm.ramp_check(self.leg(res))
        self.assertIs(row["pass"], False)
        self.assertIsNone(row["value"])
        self.assertEqual(row["reason"], "INVALID: trace unreadable: nope")


class TestWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cr = load_script("corner_run", BIN / "corner-run.py", register=True)
        cls.manifest = json.loads((BIN.parents[0] / "startup/experiment.json").read_text())

    def test_manifest_has_twelve_grid_legs_and_trace_per_tran(self):
        cfg = self.manifest["ramp_monotonicity"]
        ids = [leg["id"] for leg in cfg["legs"]]
        self.assertEqual(len(set(ids)), 12)
        # one ramp leg per declared window_grid leg (issue #336)
        self.assertEqual(ids, [leg["id"] for leg in self.manifest["window_grid"]["legs"]])
        template = self.manifest["window_grid"]["leg_analyses"]
        self.assertEqual(template.count("wrdata {corner_id}.{leg_id}.trace.dat v(vout)"), 1)
        self.assertEqual(sum(1 for ln in template if ln.startswith("tran ")), 1)
        self.assertEqual(cfg["tolerance_v"], 0.0)
        self.assertEqual(cfg["v_low"], 1.764)

    def test_deck_substitutes_corner_id(self):
        exp = self.cr.Experiment(dir=Path("."), raw=self.manifest)
        exp.measurements = []
        corner = self.cr.Corner("tt", 27.0, 3.3)
        pdk = type("P", (), {"lib_file": "x.lib"})()
        deck = self.cr.build_deck(exp, pdk, corner, [])
        self.assertIn("wrdata tt_27c_3.30v.c4u7_50ma_esr500m.trace.dat v(vout)", deck)
        self.assertNotIn("{corner_id}", deck)

    def test_batch_admits_ramp_manifest_only_with_its_block(self):
        # issue #336: the trace-returning batch shape admits the committed
        # startup manifest; without the ramp block it would qualify nothing
        # and refuses instead.
        exp = self.cr.Experiment(dir=Path("."), raw=self.manifest)
        exp.measurements = []
        self.cr.check_batch_supported(exp)
        no_ramp = {k: v for k, v in self.manifest.items() if k != "ramp_monotonicity"}
        with self.assertRaises(self.cr.HarnessError) as cm:
            self.cr.check_batch_supported(self.cr.Experiment(dir=Path("."), raw=no_ramp))
        self.assertIn("declares no ramp_monotonicity", str(cm.exception))

    def test_ramp_changes_input_fingerprint_only_when_present(self):
        from _record_common import pvt_input_sections

        with_ramp = pvt_input_sections(self.manifest, None)
        raw = {k: v for k, v in self.manifest.items() if k != "ramp_monotonicity"}
        self.assertIn("ramp_monotonicity", with_ramp)
        self.assertNotIn("ramp_monotonicity", pvt_input_sections(raw, None))


if __name__ == "__main__":
    unittest.main()
