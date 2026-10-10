"""Unit tests for the issue #253 folded-resistor qualification helpers.

Stdlib only: no klt, KLayout, PDK or ngspice needed (the generator imports
`klayout.db` lazily, inside the functions that draw).
"""
import importlib.util
import sys
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"
sys.path.insert(0, str(BIN))
import _folded_res_analysis as fra  # noqa: E402

SPEC = importlib.util.spec_from_file_location("gen_folded", BIN / "gen-folded-res-qual.py")
gen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gen)


def ports(n, length=10.0, pitch=0.82):
    """res_array's boustrophedon port layout with rows == num."""
    out = []
    for i in range(n):
        y = 0.21 + i * pitch
        left, right = 0.21, length + 0.63
        a, b = (left, right) if i % 2 == 0 else (right, left)
        li1 = {"layer": 67, "datatype": 20, "name": None}
        out.append({"name": f"R{i}_A", "x_um": a, "y_um": y, "width_um": 0.42, "layer": li1})
        out.append({"name": f"R{i}_B", "x_um": b, "y_um": y, "width_um": 0.42, "layer": li1})
    return out


class SegmentLength(unittest.TestCase):
    def test_exact_split_sums_to_schematic_l(self):
        for total, n in ((1500.0, 16), (1500.0, 4), (180.0, 2)):
            self.assertAlmostEqual(gen.segment_length_um(total, n) * n, total, places=9)

    def test_off_grid_split_rejected(self):
        with self.assertRaises(gen.GenError):
            gen.segment_length_um(1500.0, 7)

    def test_zero_segments_rejected(self):
        with self.assertRaises(gen.GenError):
            gen.segment_length_um(1500.0, 0)


class StrapPlan(unittest.TestCase):
    def test_chain_joins_b_to_next_a(self):
        straps = gen.plan_series_straps(ports(4), 4)
        self.assertEqual([(s["from"], s["to"]) for s in straps],
                         [("R0_B", "R1_A"), ("R1_B", "R2_A"), ("R2_B", "R3_A")])
        for s in straps:
            self.assertLess(s["y0_um"], s["y1_um"])

    def test_misaligned_pads_fail_loudly(self):
        p = ports(2)
        p[2]["x_um"] += 1.0  # R1_A no longer above R0_B
        with self.assertRaises(gen.GenError):
            gen.plan_series_straps(p, 2)

    def test_single_segment_has_no_straps(self):
        self.assertEqual(gen.plan_series_straps(ports(1), 1), [])

    def test_chain_ends(self):
        a, b = gen.chain_ends(ports(4), 4)
        self.assertEqual((a["name"], b["name"]), ("R0_A", "R3_B"))


class Tolerance(unittest.TestCase):
    MG = "+ sw_mm_sky130_fd_pr__res_high_po = 2.060e-02 ; comment\n+ sw_mm_sky130_fd_pr__res_xhigh_po = 4.640e-02\n"
    LIB = ".param mismatch_factor=1\n"

    def test_three_sigma_of_unsplit(self):
        t = fra.tolerance("sky130_fd_pr__res_high_po", 0.42, 1500.0, self.MG, self.LIB)
        sigma = 0.0206 / (0.42 * 1500.0) ** 0.5
        self.assertAlmostEqual(t["sigma_frac"], sigma)
        self.assertAlmostEqual(t["tolerance_frac"], 3 * sigma)

    def test_param_name_not_prefix_matched(self):
        # the high_po lookup must not pick up a longer name sharing its prefix
        text = "+ sw_mm_sky130_fd_pr__res_high_po_head = 9.0\n+ sw_mm_sky130_fd_pr__res_high_po = 1.0\n"
        self.assertEqual(fra.read_param(text, "sw_mm_sky130_fd_pr__res_high_po"), 1.0)
        self.assertEqual(fra.read_param("x_sw_mm_a = 5\nsw_mm_a = 2\n", "sw_mm_a"), 2.0)

    def test_corner_sheet(self):
        line = (".param sw_sky130_fd_pr__res_high_po_rs = {325.0+corner_factor*-48.0} "
                "+ process_mc_factor*MC_PR_SWITCH*GAUSS(0,0.035,1)\n")
        c = fra.read_corner_sheet(line, "sky130_fd_pr__res_high_po")
        self.assertEqual(c, {"nominal": 325.0, "corner_delta": -48.0, "process_mc_sigma_frac": 0.035})

    def test_verdict_boundary(self):
        self.assertEqual(fra.verdict(0.002, 0.002), "EQUIVALENT")
        self.assertEqual(fra.verdict(-0.0021, 0.002), "NOT EQUIVALENT")


class OpDeck(unittest.TestCase):
    DEV = [{"schematic_device": "R_X", "model": "m", "l_um": 100.0, "w_um": 0.42,
            "op_v": 1.0, "sim_segments": [1, 2]}]

    def test_variants_and_chain(self):
        deck, variants = fra.build_op_deck("lib.spice", "tt", 27, self.DEV, {"R_X": 40.0})
        self.assertEqual([v["tag"] for v in variants], ["r_r_x_n1", "r_r_x_n2", "r_r_x_n2_j"])
        self.assertIn("Xr_r_x_n2_0 r_r_x_n2_0 r_r_x_n2_s0 0 m w=0.42 l=50", deck)
        self.assertIn("Xr_r_x_n2_1 r_r_x_n2_s0 0 0 m", deck)
        self.assertIn("RJr_r_x_n2_j_0 r_r_x_n2_j_j0 r_r_x_n2_j_s0 40", deck)
        self.assertEqual(deck.count("RJ"), 1)

    def test_parse_and_rows(self):
        _, variants = fra.build_op_deck("lib.spice", "tt", 27, self.DEV, {"R_X": 40.0})
        text = "r_r_x_n1 = 1.000000000000e+06\nr_r_x_n2 = 1.000500000000e+06\nr_r_x_n2_j = 1.000540000000e+06\n"
        rows = fra.electrical_rows(variants, fra.parse_op_output(text))
        by = {r["tag"]: r for r in rows}
        self.assertAlmostEqual(by["r_r_x_n2"]["delta_ohm"], 500.0)
        self.assertAlmostEqual(by["r_r_x_n2_j"]["delta_frac"], 5.4e-4)
        self.assertEqual(by["r_r_x_n1"]["delta_ohm"], 0.0)


class ExtractionBookkeeping(unittest.TestCase):
    def test_series_sum_carries_n_offsets(self):
        rho, off, L, W, n = 324.827244, 379.705147, 1500.0, 0.42, 16
        seg = [{"params": {"r_ohm": fra.deck_resistance(rho, off, L / n, W)}} for _ in range(n)]
        whole = fra.deck_resistance(rho, off, L, W)
        self.assertAlmostEqual(fra.extracted_sum(seg) - whole, (n - 1) * off, places=6)


class UnmergedMarkerControl(unittest.TestCase):
    def test_reports_only_rule_classes_the_merge_removes(self):
        control = {"licon.1": 16, "urpm.1a": 1, "urpm.2": 1}
        merged = {"licon.1": 16, "urpm.1a": 1}
        self.assertEqual(fra.added_rule_classes(control, merged), {"urpm.2": 1})

    def test_control_that_adds_nothing_is_empty(self):
        same = {"licon.1": 8}
        self.assertEqual(fra.added_rule_classes(same, same), {})
        self.assertEqual(fra.added_rule_classes({"x": 0}, {}), {})


if __name__ == "__main__":
    unittest.main()
