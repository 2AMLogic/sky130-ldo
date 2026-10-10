"""Unit tests for layout/bin/_cap_rail_plan.py (issue #254): stdlib only.

These cover the arithmetic a DRC/LVS run would not catch -- a capacitor sized
against the wrong law, a unit outside the PDK's range, plates assigned to the
wrong terminals, or a footprint compared against a moved limit are all
DRC-clean and can still LVS-match a reference built from the same mistake.
The drawn geometry itself is checked by the record's own klt drc / official
sky130A_mr.drc / klt lvs results.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN_DIR))

import _cap_rail_plan as plan  # noqa: E402

# The sky130 MiM law as the pinned klt deck states it (2.00 fF/um^2 +
# 0.19 fF/um); the generator reads it from the deck at run time, these tests
# only need representative coefficients.
AREA_F = 2.0e-15
PERIM_F = 0.19e-15


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NETLIST = """** sch_path: x
.subckt ldo VOUT VREF EN VIN
C_COMP VOUT EA_CZ 150p m=1
XR1 a b sky130_fd_pr__res_high_po W=0.42 L=10 mult=1 m=1
C_CL VIN CL_CMP 1p m=1
C_SS SS 0 10p m=1
C_TS VIN TS_CMP 1p m=1
* C_FAKE a b 1p
.ends
"""


class ParseCapacitors(unittest.TestCase):
    def test_reads_every_card_with_nets_and_value(self):
        caps = {c["name"]: c for c in plan.parse_capacitors(NETLIST)}
        self.assertEqual(sorted(caps), ["C_CL", "C_COMP", "C_SS", "C_TS"])
        self.assertEqual(caps["C_COMP"]["nets"], ["VOUT", "EA_CZ"])
        self.assertAlmostEqual(caps["C_COMP"]["value_f"], 150e-12)
        self.assertAlmostEqual(caps["C_SS"]["value_f"], 10e-12)

    def test_refuses_a_multiplier(self):
        with self.assertRaises(ValueError):
            plan.parse_capacitors("C1 a b 1p m=2\n")

    def test_parse_value(self):
        self.assertAlmostEqual(plan.parse_value("150p"), 1.5e-10)
        self.assertAlmostEqual(plan.parse_value("2.5f"), 2.5e-15)
        with self.assertRaises(ValueError):
            plan.parse_value("lots")


class Sizing(unittest.TestCase):
    def test_solve_inverts_the_unit_law(self):
        side = plan.solve_unit_side_um(1.2e-12, AREA_F, PERIM_F)
        self.assertAlmostEqual(plan.unit_cap_f(side, AREA_F, PERIM_F), 1.2e-12, delta=1e-18)

    def test_planned_value_is_within_grid_rounding_of_target(self):
        for value, rows, cols in ((150e-12, 5, 9), (10e-12, 2, 2), (1e-12, 1, 1)):
            sized = plan.size_capacitor("C", value, rows, cols, 2, AREA_F, PERIM_F)
            # One 5 nm grid step on a >= 15 um side moves C by < 0.1%.
            self.assertLess(abs(sized["planned_rel_error"]), 1e-3)
            self.assertAlmostEqual(sized["planned_total_f"], sized["unit_cap_per_layer_f"] * rows * cols * 2,
                                   delta=1e-20)

    def test_stacking_halves_the_per_level_charge(self):
        one = plan.size_capacitor("C", 4e-12, 2, 2, 1, AREA_F, PERIM_F)
        two = plan.size_capacitor("C", 4e-12, 2, 2, 2, AREA_F, PERIM_F)
        self.assertLess(two["unit_side_um"], one["unit_side_um"])
        self.assertAlmostEqual(two["per_layer_total_f"] * 2, one["per_layer_total_f"], delta=2e-14)

    def test_out_of_range_unit_is_refused(self):
        with self.assertRaises(ValueError):  # 150 pF in one stacked unit: > 30 um
            plan.size_capacitor("C", 150e-12, 1, 1, 2, AREA_F, PERIM_F)
        with self.assertRaises(ValueError):  # 1 fF units: < 2 um
            plan.size_capacitor("C", 1e-15, 1, 1, 1, AREA_F, PERIM_F)

    def test_snap_is_on_grid(self):
        self.assertAlmostEqual(plan.snap(1.0026), 1.005)
        self.assertAlmostEqual(plan.snap(28.6812) / plan.GRID_UM, round(28.6812 / plan.GRID_UM))


class Plates(unittest.TestCase):
    def test_outer_and_inner(self):
        self.assertEqual(plan.assign_plates(["VOUT", "EA_CZ"], "VOUT"), {"outer": "VOUT", "inner": "EA_CZ"})
        self.assertEqual(plan.assign_plates(["SS", "0"], "0"), {"outer": "0", "inner": "SS"})

    def test_rejects_a_net_the_capacitor_does_not_have(self):
        with self.assertRaises(ValueError):
            plan.assign_plates(["VIN", "CL_CMP"], "VOUT")


class Geometry(unittest.TestCase):
    def test_block_extent_adds_strap_and_tap(self):
        ext = plan.block_extent_um(2, 3, 20.0)
        self.assertAlmostEqual(ext["array_w_um"], 3 * 20.0 + 2 * plan.UNIT_GAP_UM)
        self.assertAlmostEqual(ext["array_h_um"], 2 * 20.0 + plan.UNIT_GAP_UM)
        self.assertAlmostEqual(ext["w_um"], ext["left_um"] + ext["array_w_um"] + ext["right_um"])
        self.assertAlmostEqual(ext["h_um"], ext["array_h_um"] + 2 * plan.PLATE_ENCLOSURE_UM)

    def test_strap_and_tap_clear_the_official_bottom_plate_rules(self):
        # capm.2b_a: other met3 >= 1.2 um from (capm & met3) sized 0.14.
        self.assertGreaterEqual(plan.STRAP_ISLAND_INNER_UM - 0.14, 1.2)
        self.assertGreaterEqual(plan.TAP_ISLAND_INNER_UM - 0.14, 1.2)
        # capm.2a / cap2m.2a: unit top plates >= 0.84 um apart.
        self.assertGreaterEqual(plan.UNIT_GAP_UM, 0.84)
        # capm.3 / cap2m.3: plate enclosure >= 0.14 um.
        self.assertGreaterEqual(plan.PLATE_ENCLOSURE_UM, 0.14)


class Footprint(unittest.TestCase):
    def test_limit_is_the_ratified_strict_row(self):
        self.assertEqual(plan.LIMIT_UM2, 0.1e6)

    def test_core_rectangle(self):
        core = plan.core_rectangle(315.78, 100.0, 2.0, 23.15, 101.12, 59.59)
        self.assertAlmostEqual(core["w_um"], 417.78)
        self.assertAlmostEqual(core["h_um"], 183.86)
        self.assertAlmostEqual(core["area_um2"], 417.78 * 183.86)
        self.assertTrue(core["below_limit"])

    def test_strict_comparison(self):
        # exactly at the limit is NOT below it
        core = plan.core_rectangle(1000.0, 0.0, 0.0, 0.0, 100.0, 0.0)
        self.assertFalse(core["below_limit"])

    def test_side_by_side_adds_every_block(self):
        self.assertAlmostEqual(plan.side_by_side_area_um2([1.0, 2.5], 10.0), 13.5)


class GeneratorPlan(unittest.TestCase):
    """The generator's fixed array shapes must keep every schematic value
    inside the PDK unit range (it would refuse to draw otherwise)."""

    def test_cap_plan_shapes_are_drawable(self):
        gen = _load("gen_cap_rail_demo", "gen-cap-rail-demo.py")
        caps = {c["name"]: c for c in plan.parse_capacitors(NETLIST)}
        self.assertEqual(set(gen.CAP_PLAN), set(caps))
        for name, cp in gen.CAP_PLAN.items():
            sized = plan.size_capacitor(name, caps[name]["value_f"], cp["rows"], cp["cols"], 2, AREA_F, PERIM_F)
            self.assertLessEqual(sized["unit_side_um"], plan.MAX_UNIT_SIDE_UM)
            self.assertIn(cp["outer"], caps[name]["nets"])


if __name__ == "__main__":
    unittest.main()
