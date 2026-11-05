"""Tests for the #370 stage-2 adaptive R_CZ driver helpers (pure python; no fleet, no ngspice)."""

from __future__ import annotations

import unittest
from pathlib import Path

from _sim_script_loader import load_script

SIM_DIR = Path(__file__).resolve().parents[1]
ra = load_script(
    "rcz_adaptive_370", SIM_DIR / "bin" / "rcz-adaptive-370.py", register=True
)

BODY = (
    "XR_CZ EA_CZ EA_OUT 0 sky130_fd_pr__res_xhigh_po W=0.42 L=52 mult=1 m=1\n"
    "XR_FB_A VOUT FB 0 sky130_fd_pr__res_xhigh_po W=0.42 L=180 mult=1 m=1\n"
    ".ends\n"
)


class Edits(unittest.TestCase):
    def test_candidate_splits_rcz_and_adds_switch(self):
        out = ra.edit_candidate(BODY, 11)
        self.assertIn("XR_CZ EA_CZ EA_MID", out)
        self.assertIn("XR_CX EA_MID EA_OUT", out)
        self.assertIn("L=780", out)
        self.assertIn(
            "XM_LLP GSW BIASP VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=11 ", out
        )
        self.assertIn("XR_FB_A VOUT FB 0", out)

    def test_candidates_differ_only_in_reference_length(self):
        a, b = ra.variant(BODY, "candA"), ra.variant(BODY, "candB")
        self.assertEqual(a.replace("L=11 ", "L=2.2 "), b)

    def test_instrumentation_resistor_lengths(self):
        self.assertIn("L=832", "\n".join(ra.probe_lines("rcz16")))
        self.assertIn("L=780", "\n".join(ra.probe_lines("candA")))
        self.assertNotIn("L=780", "\n".join(ra.probe_lines("baseline")))


class Grading(unittest.TestCase):
    def test_r_eff(self):
        v = {"g_rcz0": 1 / 3e5, "g_rcx": 1 / 4.5e6, "gds_sw": 0.0}
        self.assertAlmostEqual(ra.r_eff("candA", v), 4.8e6, delta=1)
        v["gds_sw"] = 1e-4
        self.assertLess(ra.r_eff("candA", v), 3.1e5)
        self.assertIsNone(ra.r_eff("candA", {"g_rcz0": 1e-6}))

    def test_regulating_and_iq(self):
        self.assertFalse(ra.regulating(None))
        self.assertFalse(ra.regulating(1.2))
        self.assertTrue(ra.regulating(1.8004))
        self.assertAlmostEqual(ra.iq_ua(14.5e-6 + 1e-3, 1e-3), 14.5)
        self.assertIsNone(ra.iq_ua(None, 0.0))

    def test_tran_missing_data_never_recovers(self):
        g = ra.grade_tran({"pre": 1.8, "vmin": None, "vmax": 1.8, "vfin": 1.8})
        self.assertFalse(g["valid"] or g["recovered"])

    def test_tran_in_band_and_unsettled(self):
        ok = ra.grade_tran({"pre": 1.8, "vmin": 1.79, "vmax": 1.805, "vfin": 1.8})
        self.assertTrue(ok["recovered"] and ok["rec_us"] == 0.0)
        bad = ra.grade_tran(
            {"pre": 1.8, "vmin": 1.7, "vmax": 1.8, "vfin": 1.75, "tlo": 2e-4}
        )
        self.assertTrue(bad["valid"] and not bad["recovered"])

    def test_tran_recovery_time_from_last_crossing(self):
        g = ra.grade_tran(
            {"pre": 1.8, "vmin": 1.7, "vmax": 1.8, "vfin": 1.8, "tlo": 100e-6 + 50e-6}
        )
        self.assertAlmostEqual(g["rec_us"], 50.0)
        self.assertAlmostEqual(g["peak_v"], 0.1)


if __name__ == "__main__":
    unittest.main()
