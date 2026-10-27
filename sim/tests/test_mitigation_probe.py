"""Tests for the #324 mitigation-screen probe helpers (parse/classify/edit).

Loaded by file path, like test_corner_run.py. Pure-text fixtures; no ngspice.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from _sim_script_loader import load_script  # noqa: E402

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR / "bin"))
_p = next((SIM_DIR / "loop-gain" / "diagnostics").glob("*-mitigation-screen/mitigation_probe.py"))
mp = load_script("mitigation_probe", _p, register=True)

GOOD = """PT1_OP
vseed = 1.798832210e+00
ivin = 2.760400000e-05
PT1_AC
fc = 1.782733000e+05
phc = -1.395229000e+02
gmdb = -1.751474000e+01
dcg = 6.29e+01
"""
NO_CROSS = """PT1_OP
vseed = 1.8e+00
ivin = 1.4e-05
PT1_AC
fc: no such vector
"""
NONREG = """PT3_OP
vseed = 3.63e+00
ivin = 1.0e-03
PT3_AC
fc = 1e3
phc = -100
gmdb = -20
"""


class ParseClassify(unittest.TestCase):
    def pt(self):
        return (1, 0.33e-6, 0.01, 36.0)

    def test_valid_point(self):
        vals = mp.parse_points(GOOD)[1]
        r = mp.classify(self.pt(), vals, 3.3, 36.0, 0.0, None)
        self.assertTrue(r["valid"])
        self.assertAlmostEqual(r["pm_deg"], 40.4771, places=3)
        self.assertAlmostEqual(r["gm_db"], 17.51474, places=4)
        # Iq = VIN current - external load current (bleed is not subtracted)
        self.assertAlmostEqual(r["iq_a"], 2.7604e-5 - 1.798832210 / 36.0, places=9)
        self.assertFalse(r["pm_ge_45"])

    def test_missing_crossing_is_invalid(self):
        vals = mp.parse_points(NO_CROSS)[1]
        r = mp.classify(self.pt(), vals, 3.3, 36.0, 0.0, None)
        self.assertFalse(r["valid"])
        self.assertNotIn("pm_ge_45", r)
        self.assertTrue(any("crossing" in x or "missing" in x for x in r["invalid_reasons"]))

    def test_non_regulating_is_invalid(self):
        vals = mp.parse_points(NONREG)[3]
        r = mp.classify((3, 0.33e-6, 0.01, 1e12), vals, 3.63, 1e12, 0.0, None)
        self.assertFalse(r["valid"])
        self.assertTrue(any("non-regulating" in x for x in r["invalid_reasons"]))

    def test_solver_diagnostic_invalidates(self):
        vals = mp.parse_points(GOOD)[1]
        r = mp.classify(self.pt(), vals, 3.3, 36.0, 0.0, "singular matrix")
        self.assertFalse(r["valid"])


class Edits(unittest.TestCase):
    NET = ("RLOAD VOUT 0 36 m=1\nC_COMP VOUT EA_CZ 150p m=1\n"
           "XR_CZ EA_CZ EA_OUT 0 sky130_fd_pr__res_xhigh_po W=0.42 L=52 mult=1 m=1\n")

    def test_edits(self):
        t, notes = mp.edit_netlist(self.NET, 3.0, 2.0, 0.5)
        self.assertIn("C_COMP VOUT EA_CZ 300p", t)
        self.assertIn("L=26 ", t)
        self.assertIn("RBLEED VOUT 0 600000", t)
        self.assertEqual(len(notes), 3)

    def test_no_edit_is_identity(self):
        t, notes = mp.edit_netlist(self.NET, 0.0, 1.0, 1.0)
        self.assertEqual(t, self.NET)
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()
