"""Tests for the #349 adaptive-compensation probe helpers (edit/parse/classify) and
the sense-path characterization parser, including invalid fixtures that must never
classify as valid.

Loaded by file path, like test_mitigation_probe.py. Pure-text fixtures; no ngspice.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR / "bin"))
_DIAG = next((SIM_DIR / "loop-gain" / "diagnostics").glob("*-adaptive-comp"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _DIAG / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ap = _load("adaptive_probe")
sp = _load("sense_probe")

NETLIST = """\
.subckt ldo_3v3in_1v8out VOUT VREF EN VIN
C_COMP VOUT EA_CZ 150p m=1
XR_CZ EA_CZ EA_OUT 0 sky130_fd_pr__res_xhigh_po W=0.42 L=52 mult=1 m=1
XM_SENSE CL_SNS EA_OUT VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=0.42 nf=1 ad=0.1218
+ as=0.1 ps=1 pd=1
XM_CLN1 CL_SNS CL_SNS AMP_ENN 0 sky130_fd_pr__nfet_g5v0d10v5 L=1 W=20 nf=1 ad=5.8
XM_CLN2 CL_CMP CL_SNS AMP_ENN 0 sky130_fd_pr__nfet_g5v0d10v5 L=1 W=1.6 nf=1 ad=0.464
.ends
"""

GOOD_ADAPTIVE = """PT1_OP
vseed = 1.798832e+00
ivin = 2.8235e-05
v(xldo.adapt_g) = 1.7e-02
v(xldo.ea_out) = 1.94
v(xldo.cl_sns) = 0.88
PT1_AC
fc = 1.5e+05
phc = -1.058e+02
gmdb = -2.0e+01
dcg = 6e+01
rbsw_over_ra = 6.0e-02
"""


class Edit(unittest.TestCase):
    def test_baseline_no_edit(self):
        out, notes = ap.edit_netlist(NETLIST, 0.0, 2.0, 0.0, 1.0)
        self.assertEqual(out, NETLIST)
        self.assertEqual(notes, [])

    def test_split_and_tap(self):
        out, notes = ap.edit_netlist(NETLIST, 0.4, 2.0, 4.0, 1.0)
        self.assertNotIn("XR_CZ EA_CZ EA_OUT", out)
        self.assertIn("XR_CZA EA_CZ RCZ_MID 0 sky130_fd_pr__res_xhigh_po W=0.42 L=20.8 ", out)
        self.assertIn("XR_CZB RCZ_MID EA_OUT 0 sky130_fd_pr__res_xhigh_po W=0.42 L=31.2 ", out)
        # series total length preserved: R_a + R_b = 52 um
        self.assertAlmostEqual(20.8 + 31.2, 52.0)
        self.assertIn("XM_CZSW RCZ_MID ADAPT_G EA_OUT VIN sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=2 ", out)
        self.assertIn("XM_CLN3 ADAPT_G CL_SNS AMP_ENN 0 sky130_fd_pr__nfet_g5v0d10v5 L=1 W=4 ", out)
        self.assertEqual(len(notes), 2)

    def test_tap_inserted_after_cln1_not_into_continuations(self):
        out, _ = ap.edit_netlist(NETLIST, 0.5, 2.0, 6.0, 1.0)
        lines = out.splitlines()
        i = next(k for k, l in enumerate(lines) if l.startswith("XM_CLN3"))
        self.assertTrue(lines[i - 1].startswith("XM_CLN1"))
        # M_SENSE continuation line stays attached to its card
        j = next(k for k, l in enumerate(lines) if l.startswith("XM_SENSE"))
        self.assertTrue(lines[j + 1].startswith("+ as=0.1"))

    def test_split_without_tap_rejected(self):
        with self.assertRaises(AssertionError):
            ap.edit_netlist(NETLIST, 0.5, 2.0, 0.0, 1.0)

    def test_missing_card_rejected(self):
        with self.assertRaises(AssertionError):
            ap.edit_netlist(NETLIST.replace("L=52", "L=51"), 0.5, 2.0, 6.0, 1.0)

    def test_ccomp_scale(self):
        out, _ = ap.edit_netlist(NETLIST, 0.0, 2.0, 0.0, 2.0)
        self.assertIn("C_COMP VOUT EA_CZ 300p", out)


class ParseClassify(unittest.TestCase):
    LEG = (0.33e-6, 0.01, 36.0, "0.33u/10m/50mA")

    def test_valid_adaptive_point(self):
        vals = ap.parse_legs(GOOD_ADAPTIVE, True)[1]
        r = ap.classify_ac(1, self.LEG, vals, 3.3, True, None)
        self.assertTrue(r["valid"], r["invalid_reasons"])
        self.assertAlmostEqual(r["pm_deg"], 74.2, places=3)
        self.assertAlmostEqual(r["gm_db"], 20.0, places=3)
        self.assertAlmostEqual(r["reff_over_ra"], 1.06, places=6)
        self.assertAlmostEqual(r["iq_a"], 2.8235e-5 - 1.798832 / 36.0, places=9)

    def test_missing_gain_margin_is_invalid(self):
        txt = GOOD_ADAPTIVE.replace("gmdb = -2.0e+01\n", "")
        r = ap.classify_ac(1, self.LEG, ap.parse_legs(txt, True)[1], 3.3, True, None)
        self.assertFalse(r["valid"])
        self.assertIn("no -180 deg phase crossing (GM missing)", r["invalid_reasons"])

    def test_missing_crossover_is_invalid(self):
        txt = GOOD_ADAPTIVE.replace("fc = 1.5e+05\n", "")
        r = ap.classify_ac(1, self.LEG, ap.parse_legs(txt, True)[1], 3.3, True, None)
        self.assertFalse(r["valid"])

    def test_non_regulating_is_invalid(self):
        txt = GOOD_ADAPTIVE.replace("vseed = 1.798832e+00", "vseed = 3.63e+00")
        r = ap.classify_ac(1, self.LEG, ap.parse_legs(txt, True)[1], 3.63, True, None)
        self.assertFalse(r["valid"])
        self.assertTrue(any("non-regulating" in x for x in r["invalid_reasons"]))

    def test_unprinted_op_is_invalid(self):
        r = ap.classify_ac(1, self.LEG, {}, 3.3, False, None)
        self.assertFalse(r["valid"])
        self.assertIn("operating point not printed", r["invalid_reasons"])

    def test_solver_diagnostic_invalidates_otherwise_good_point(self):
        vals = ap.parse_legs(GOOD_ADAPTIVE, True)[1]
        r = ap.classify_ac(1, self.LEG, vals, 3.3, True, "Warning: Dynamic gmin stepping failed")
        self.assertFalse(r["valid"])

    def test_adaptive_run_without_control_node_is_invalid(self):
        txt = GOOD_ADAPTIVE.replace("v(xldo.adapt_g) = 1.7e-02\n", "")
        r = ap.classify_ac(1, self.LEG, ap.parse_legs(txt, True)[1], 3.3, True, None)
        self.assertFalse(r["valid"])
        self.assertIn("ADAPT_G not printed", r["invalid_reasons"])

    def test_adaptive_run_without_ratio_is_invalid(self):
        txt = GOOD_ADAPTIVE.replace("rbsw_over_ra = 6.0e-02\n", "")
        r = ap.classify_ac(1, self.LEG, ap.parse_legs(txt, True)[1], 3.3, True, None)
        self.assertFalse(r["valid"])


class SenseParser(unittest.TestCase):
    OP = """LEG1_OP
v(vout) = 1.8024e+00
v(xldo.cl_sns) = 3.528e-01
v(xldo.adapt_g) = 3.2998e+00
i(vvin) = -1.3871e-05
i(v.xldo.vsnsmon) = -1.0e-09
"""

    def test_parses_hierarchical_names(self):
        d = sp.parse_legs(self.OP)[1]
        self.assertAlmostEqual(d["vout"], 1.8024)
        self.assertAlmostEqual(d["cl_sns"], 0.3528)
        self.assertAlmostEqual(d["ivin"], -1.3871e-05)

    def test_old_unprefixed_output_is_not_accepted(self):
        # the v0 parser bug: a bare `vout = ...` line must NOT parse as an op print
        d = sp.parse_legs("LEG1_OP\nvout = 1.8\ni(vvin) = -1e-5\n")[1]
        self.assertNotIn("vout", d)

    def test_unprinted_leg_invalid(self):
        r = sp.classify(1, {}, 3.3, 1e12, 0.0, None)
        self.assertFalse(r["valid"])

    def test_iq_sign(self):
        d = sp.parse_legs(self.OP)[1]
        r = sp.classify(1, d, 3.3, 1e12, 0.0, None)
        self.assertTrue(r["valid"])
        self.assertAlmostEqual(r["iq_a"], 1.3871e-05 - 0.0, places=9)

    def test_tap_mode_requires_adapt_g(self):
        d = sp.parse_legs(self.OP.replace("v(xldo.adapt_g) = 3.2998e+00\n", ""))[1]
        r = sp.classify(1, d, 3.3, 1e12, 6.0, None)
        self.assertFalse(r["valid"])


if __name__ == "__main__":
    unittest.main()
