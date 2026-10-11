"""Unit tests for the #319 capacitor study's PDK/netlist/log parsers
(layout/cap-study/_cap_study.py). Stdlib only, small inline fixtures shaped
like the pinned PDK's own files -- no PDK install needed."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cap-study"))

import _cap_study as cs  # noqa: E402

PARAMS_CAP_LOW = """\
* corner file
.param sw_cap_mim_ca = {2e-15+corner_factor*-2.2000000000000002e-16} + process_mc_factor*MC_PR_SWITCH*GAUSS(0,0.027,1)
.param sw_cap_mim_dw = {1.5e-07+corner_factor*-9.5e-08} + process_mc_factor*MC_PR_SWITCH*AGAUSS(0,2.4e-08,1)
"""

MODELS_CAPACITORS = """\
.subckt  sky130_fd_pr__cap_mim_m3_1 c0 c1  mult=1
+ w=1 l=1
+
.param  wc = {w+sw_cap_mim_dw*1e6}
+ lc = {l+sw_cap_mim_dw*1e6}
+ carea = {sw_cap_mim_ca*wc*lc*(1+mismatch_factor*MC_MM_SWITCH*AGAUSS(0,1.0,1)*sw_mm_cmim/sqrt(wc*lc*mult))}
c1 c0  c1 c = {carea}
.ends sky130_fd_pr__cap_mim_m3_1
.subckt  sky130_fd_pr__cap_mim_m3_2 c0 c1  mult=1
+ w=1 l=1
c1 c0  c1 c = {2e-15*w*l}
.ends sky130_fd_pr__cap_mim_m3_2
"""

VPP_MODEL = """\
.subckt  sky130_fd_pr__cap_vpp_11p5x11p7_m1m2_noshield c0 c1 b
+
.param  mult = 1 presim_flag = 0.0
+
+ ctot_a = {74.6e-15*some_cell__cor+0.0283/sqrt(11.5*11.7*2*mult)*74.6e-15*some_cell__cor*MC_MM_SWITCH*AGAUSS(0,1.0,1)}
+ rat_m2 = 0.5767
+ rat_m1 = 0.4233
+ cap_m2 = {rat_m2*ctot_a}
.ends
"""

MAG = """\
magic
tech sky130A
magscale 1 2
<< metal1 >>
rect 0 0 2000 1000
<< metal2 >>
rect 100 -200 1900 1000
<< labels >>
rect 0 0 5000 5000
<< end >>
"""

VAR_MODEL = """\
.subckt  sky130_fd_pr__cap_var_lvt c0 c1 b w=5 l=0.5 vm=1
.param
+ sky130_fd_pr__cap_var_lvt__vgs_min = '-2.301'
+ sky130_fd_pr__cap_var_lvt__vgs_max = '-1*-2.301'
.ends
"""

NETLIST = """\
**.subckt tb
VVIN VIN 0 'vsup'
xldo VOUT VREF EN VIN ldo_3v3in_1v8out
COUT VOUT VESR 1u m=1
ILOAD VOUT 0 0
**.ends
.subckt ldo_3v3in_1v8out VOUT VREF EN VIN
C_COMP VOUT EA_CZ 150p m=1
C_SS SS 0 10p m=1
.ends
"""


class SpiceNumbers(unittest.TestCase):
    def test_suffixes(self):
        self.assertAlmostEqual(cs.spice_number("150p"), 1.5e-10)
        self.assertAlmostEqual(cs.spice_number("50m"), 0.05)
        self.assertAlmostEqual(cs.spice_number("1meg"), 1e6)
        self.assertAlmostEqual(cs.spice_number("2e-15"), 2e-15)
        with self.assertRaises(ValueError):
            cs.spice_number("abc")

    def test_eval_expr(self):
        self.assertAlmostEqual(cs.eval_expr("{2*x+1}", {"X": 3}), 7.0)
        self.assertAlmostEqual(cs.eval_expr("'-1*-2.301'", {}), 2.301)
        self.assertAlmostEqual(cs.eval_expr("74.6e-15*1.5", {}), 1.119e-13)
        self.assertAlmostEqual(cs.eval_expr("agauss(3,1,1)", {}), 3.0)  # nominal value
        with self.assertRaises(KeyError):
            cs.eval_expr("unknown_name", {})


class PdkFiles(unittest.TestCase):
    def test_corner_param(self):
        p = cs.parse_params(PARAMS_CAP_LOW)
        self.assertAlmostEqual(cs.eval_corner_param(p["sw_cap_mim_ca"]), 1.78e-15)
        self.assertAlmostEqual(cs.eval_corner_param(p["sw_cap_mim_dw"]), 5.5e-8)

    def test_mim_formula_check(self):
        self.assertTrue(cs.mim_subckt_formula_ok(MODELS_CAPACITORS, "sky130_fd_pr__cap_mim_m3_1"))
        # a subckt with a different law is not silently accepted
        self.assertFalse(cs.mim_subckt_formula_ok(MODELS_CAPACITORS, "sky130_fd_pr__cap_mim_m3_2"))
        self.assertAlmostEqual(cs.mim_cap_f(2e-15, 0.15, 10, 10), 2e-15 * 10.15 * 10.15)

    def test_vpp_ctot_and_rats(self):
        self.assertAlmostEqual(cs.vpp_ctot(VPP_MODEL, {"some_cell__cor": 1.0}), 74.6e-15)
        self.assertAlmostEqual(cs.vpp_ctot(VPP_MODEL, {"some_cell__cor": 1.19}), 74.6e-15 * 1.19)
        self.assertIsNone(cs.vpp_ctot(VPP_MODEL, {}))  # corner factor missing -> not a number
        self.assertEqual(cs.vpp_rat_sum(VPP_MODEL), 1.0)
        self.assertEqual(cs.vpp_name_dims("sky130_fd_pr__cap_vpp_11p5x11p7_m1m2_noshield"), (11.5, 11.7))

    def test_mag_bbox(self):
        bb = cs.mag_bbox(MAG)
        # magscale 1 2 -> 0.005 um per unit; labels are not geometry
        self.assertAlmostEqual(bb["w_um"], 10.0)
        self.assertAlmostEqual(bb["h_um"], 6.0)
        self.assertAlmostEqual(bb["area_um2"], 60.0)
        self.assertEqual(bb["levels"], ["met1", "met2"])
        self.assertIsNone(cs.mag_bbox(MAG.replace("<< metal1 >>", "use subcell x\n<< metal1 >>")))

    def test_var_soa(self):
        self.assertEqual(cs.var_soa(VAR_MODEL, "lvt"), {"vgs_min_v": -2.301, "vgs_max_v": 2.301})
        self.assertIsNone(cs.var_soa(VAR_MODEL, "hvt"))


class NetlistAndLogs(unittest.TestCase):
    def test_netlist_caps_only_dut(self):
        caps = cs.netlist_caps(NETLIST)
        self.assertEqual([c["name"] for c in caps], ["C_COMP", "C_SS"])  # COUT is the testbench's
        self.assertEqual(caps[0]["nets"], ["VOUT", "EA_CZ"])
        self.assertAlmostEqual(caps[1]["value_f"], 1e-11)

    def test_set_load(self):
        out = cs.set_load(NETLIST, "50m")
        self.assertIn("ILOAD VOUT 0 50m", out)
        with self.assertRaises(ValueError):
            cs.set_load(out + "ILOAD VOUT 0 1m\n", "0")

    def test_node_names(self):
        self.assertEqual(cs.node_ident("VOUT"), "vout")
        self.assertEqual(cs.node_ident("EA_CZ"), "xldo.ea_cz")
        self.assertEqual(cs.meas_name("v", "CL_CMP"), "v_cl_cmp")

    def test_c_from_vi(self):
        # 1 pF at 1 kHz: Im(V) = -1/(2 pi f C)
        import math
        vi = -1.0 / (2 * math.pi * 1e3 * 1e-12)
        self.assertAlmostEqual(cs.c_from_vi(vi, 1e3) / 1e-12, 1.0)
        self.assertIsNone(cs.c_from_vi(0.0, 1e3))
        self.assertIsNone(cs.c_from_vi(5.0, 1e3))  # inductive / not a capacitor
        self.assertIsNone(cs.c_from_vi(None, 1e3))


if __name__ == "__main__":
    unittest.main()
