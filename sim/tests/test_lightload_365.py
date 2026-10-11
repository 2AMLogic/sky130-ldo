"""Tests for the #365 light-load extraction/classification helpers (synthetic, no ngspice)."""
from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
_DIR = next((SIM_DIR / "loop-gain" / "diagnostics").glob("*-lightload-phase-dip"))
_spec = importlib.util.spec_from_file_location("lightload_extract", _DIR / "lightload_extract.py")
ll = importlib.util.module_from_spec(_spec)
sys.modules["lightload_extract"] = ll
_spec.loader.exec_module(ll)


def grid(lo, hi, ppd=30):
    n = int(round((math.log10(hi) - math.log10(lo)) * ppd)) + 1
    return [10 ** (math.log10(lo) + k / ppd) for k in range(n)]


def resp(tf, fr):
    v = [tf(1j * 2 * math.pi * f) for f in fr]
    return [x.real for x in v], [x.imag for x in v]


class Corners(unittest.TestCase):
    def test_two_poles_then_zero(self):
        fr = grid(0.01, 1e6)
        re, im = resp(lambda s: 1000 / ((1 + s / (2 * math.pi * 1)) * (1 + s / (2 * math.pi * 100)) *
                                        (1 + s / (2 * math.pi * 1e5)) ** -1), fr)
        c = ll.slope_corners(fr, ll.mag_db(re, im))
        kinds = [(round(math.log10(x["f_hz"])), x["kind"]) for x in c]
        self.assertIn((0, "pole-like"), kinds)
        self.assertIn((2, "pole-like"), kinds)
        self.assertIn((5, "zero-like"), kinds)

    def test_single_pole_has_no_zero(self):
        fr = grid(0.01, 1e5)
        re, im = resp(lambda s: 100 / (1 + s / (2 * math.pi * 10)), fr)
        c = ll.slope_corners(fr, ll.mag_db(re, im))
        self.assertFalse([x for x in c if x["kind"] == "zero-like"])

    def test_doublet_candidates_pair_within_a_decade(self):
        cs = [{"f_hz": 100.0, "kind": "pole-like"}, {"f_hz": 300.0, "kind": "zero-like"},
              {"f_hz": 1e6, "kind": "pole-like"}]
        d = ll.doublet_candidates(cs)
        self.assertEqual(d, [{"pole_like_hz": 100.0, "zero_like_hz": 300.0}])

    def test_no_doublet_when_same_kind_or_far(self):
        cs = [{"f_hz": 1.0, "kind": "pole-like"}, {"f_hz": 2.0, "kind": "pole-like"},
              {"f_hz": 1e5, "kind": "zero-like"}]
        self.assertEqual(ll.doublet_candidates(cs), [])


class PhaseDip(unittest.TestCase):
    def test_monotone_rolloff_has_no_dip(self):
        fr = grid(0.1, 1e5)
        re, im = resp(lambda s: 1000 / ((1 + s / 6.28) * (1 + s / 628)), fr)
        d = ll.phase_dip(fr, re, im)
        self.assertFalse(d["dip_present"])
        self.assertIsNotNone(d["fc_hz"])

    def test_lead_after_lag_is_a_dip(self):
        fr = grid(0.1, 1e6)
        tf = lambda s: 3000 * (1 + s / (2 * math.pi * 3e3)) / ((1 + s / 6.28) * (1 + s / (2 * math.pi * 100)))
        re, im = resp(tf, fr)
        d = ll.phase_dip(fr, re, im)
        self.assertGreater(d["recovery_after_min_deg"], 20.0)

    def test_no_unity_crossing_gives_none_not_number(self):
        fr = grid(1, 1e3)
        re, im = resp(lambda s: 0.1 / (1 + s), fr)
        self.assertIsNone(ll.phase_dip(fr, re, im)["fc_hz"])


class Parse(unittest.TestCase):
    def test_wrdata_nodes_header_and_columns(self):
        txt = "frequency a b\n1 1 0 2 0\n2 1 1 2 1\n"
        fr, cols = ll.read_wrdata_nodes(txt, 2)
        self.assertEqual(fr, [1.0, 2.0])
        self.assertEqual(cols[1], ([2.0, 2.0], [0.0, 1.0]))

    def test_wrdata_wrong_width_raises(self):
        with self.assertRaises(ValueError):
            ll.read_wrdata_nodes("1 1 0\n", 2)


class Transient(unittest.TestCase):
    def test_new_and_worse_violations(self):
        base = {"undershoot_rise_v__a": 0.10, "overshoot_rise_v__a": 0.20, "recovery_rise_us__a": 10.0,
                "settle_err_50ma_pct__a": 1.0}
        cand = {"undershoot_rise_v__a": 0.16, "overshoot_rise_v__a": 0.25, "recovery_rise_us__a": 12.0,
                "settle_err_50ma_pct__a": 9.0}
        kinds = {t["metric"]: t["kind"] for t in ll.transient_regressions(base, cand)}
        self.assertEqual(kinds, {"undershoot_rise_v__a": "new_violation", "overshoot_rise_v__a": "worse_violation"})

    def test_improved_violation_and_missing(self):
        base = {"recovery_rise_us__a": 90.0, "recovery_fall_us__a": 5.0}
        cand = {"recovery_rise_us__a": 40.0}
        kinds = {t["metric"]: t["kind"] for t in ll.transient_regressions(base, cand)}
        self.assertEqual(kinds["recovery_rise_us__a"], "improved_violation")
        self.assertEqual(kinds["recovery_fall_us__a"], "missing")


class Verdict(unittest.TestCase):
    ok = [{"valid": True, "pm_deg": 60.0, "worst_gm_db": 20.0}]

    def test_advance(self):
        self.assertEqual(ll.verdict(self.ok, [], [14.0, 28.0]), "advance")

    def test_iq_over_limit_rejects(self):
        self.assertEqual(ll.verdict(self.ok, [], [14.0, 30.5]), "reject")

    def test_missing_crossing_never_passes(self):
        bad = [{"valid": False, "pm_deg": 60.0, "worst_gm_db": 0.0}]
        self.assertEqual(ll.verdict(bad, [], [10.0]), "reject")

    def test_untested_transient_is_not_advance(self):
        self.assertEqual(ll.verdict(self.ok, None, [10.0]), "revise")

    def test_low_pm_or_transient_regression_revises(self):
        low = [{"valid": True, "pm_deg": 30.0, "worst_gm_db": 20.0}]
        self.assertEqual(ll.verdict(low, [], [10.0]), "revise")
        self.assertEqual(ll.verdict(self.ok, [{"kind": "new_violation"}], [10.0]), "revise")


if __name__ == "__main__":
    unittest.main()
