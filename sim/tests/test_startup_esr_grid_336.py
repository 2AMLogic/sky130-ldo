"""PDK-free headless tests for the startup C_out x load x ESR grid (issue #336).

Covers leg expansion, coordinate identity, order independence of the deck
blocks, per-leg trace naming, and the grid verdict's treatment of missing or
INVALID ramp traces. No ngspice/xschem/PDK is needed.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR / "bin"))
_spec = importlib.util.spec_from_file_location("corner_run", SIM_DIR / "bin" / "corner-run.py")
corner_run = importlib.util.module_from_spec(_spec)
sys.modules["corner_run"] = corner_run
_spec.loader.exec_module(corner_run)

COUTS = (0.33e-6, 4.7e-6)
LOADS = (1e12, 36)
ESRS = (0, 0.01, 0.5)


def load_exp():
    return corner_run.load_experiment(SIM_DIR / "startup")


class TestLegExpansion(unittest.TestCase):
    def setUp(self):
        self.exp = load_exp()
        self.legs = corner_run.window_legs(self.exp.raw)

    def test_grid_is_full_cross_product_of_declared_coordinates(self):
        got = {(l["cout_f"], l["rload_ohm"], l["esr_ohm"]) for l in self.legs}
        self.assertEqual(len(self.legs), 12)
        self.assertEqual(got, set(itertools.product(COUTS, LOADS, ESRS)))

    def test_leg_ids_unique_and_encode_their_coordinates(self):
        ids = [l["id"] for l in self.legs]
        self.assertEqual(len(set(ids)), len(ids))
        for l in self.legs:
            cout = "c330n" if l["cout_f"] == 0.33e-6 else "c4u7"
            load = "0ma" if l["rload_ohm"] == 1e12 else "50ma"
            esr = {0: "esr0", 0.01: "esr10m", 0.5: "esr500m"}[l["esr_ohm"]]
            self.assertEqual(l["id"], f"{cout}_{load}_{esr}")

    def test_pre_336_four_points_are_the_10mohm_legs(self):
        ten = [l for l in self.legs if l["esr_ohm"] == 0.01]
        self.assertEqual(len(ten), 4)

    def test_per_leg_measurements_cover_every_leg_with_unchanged_bounds(self):
        ms = [m for m in self.exp.measurements if m.leg is not None]
        self.assertEqual(len(ms), 3 * 12)
        for m in ms:
            self.assertTrue(m.name.endswith("__" + m.leg))
            leg = next(l for l in self.legs if l["id"] == m.leg)
            self.assertEqual((m.cout_f, m.esr_ohm), (leg["cout_f"], leg["esr_ohm"]))
        bounds = {m.name.split("__")[0]: (m.min, m.max) for m in ms}
        self.assertEqual(bounds["vpk_v"], (None, 1.836))
        self.assertEqual(bounds["vfloor_v"], (1.764, None))
        self.assertEqual(bounds["tramp_ms"], (None, None))

    def test_ramp_legs_are_exactly_the_grid_legs(self):
        ramp = [l["id"] for l in self.exp.raw["ramp_monotonicity"]["legs"]]
        self.assertEqual(ramp, [l["id"] for l in self.legs])


class TestDeckBlocks(unittest.TestCase):
    def setUp(self):
        self.exp = load_exp()
        self.legs = corner_run.window_legs(self.exp.raw)

    def block(self, leg_id, lines=None):
        lines = lines or corner_run.window_leg_lines(self.exp, corner_id="tt_27c_3.30v")
        start = next(i for i, l in enumerate(lines) if l.startswith(f"* --- window leg {leg_id}:"))
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("* --- window leg")), len(lines))
        return lines[start:end]

    def test_every_leg_block_resets_alters_everything_and_is_a_cold_tran(self):
        lines = corner_run.window_leg_lines(self.exp, corner_id="tt_27c_3.30v")
        self.assertEqual(lines.count("reset"), 12)
        for leg in self.legs:
            blk = self.block(leg["id"], lines)
            self.assertEqual(blk[1], "reset")
            self.assertEqual(blk[2], "save all")
            alters = [l.split("=")[0].strip() for l in blk if l.startswith("alter ")]
            self.assertEqual(alters, ["alter cout", "alter resr", "alter cdir", "alter rload"])
            self.assertEqual(sum(1 for l in blk if l.startswith("tran ")), 1)
            self.assertNotIn("uic", " ".join(blk))  # t=0 op point from EN=0, not a seeded state
            self.assertIn(f"wrdata tt_27c_3.30v.{leg['id']}.trace.dat v(vout)", blk)

    def test_coordinates_are_applied_to_the_right_elements(self):
        by = {l["id"]: self.block(l["id"]) for l in self.legs}
        z = by["c4u7_50ma_esr0"]
        self.assertIn("alter cdir = 4.7e-06", z)
        self.assertIn("alter cout = 0.0", z)  # series branch open: no stand-in resistor
        self.assertIn("alter rload = 36.0", z)
        hi = by["c330n_0ma_esr500m"]
        self.assertIn("alter resr = 0.5", hi)
        self.assertIn("alter cdir = 0.0", hi)
        self.assertIn("alter cout = 3.3e-07", hi)
        self.assertIn("alter rload = 1000000000000.0", hi)

    def test_reordered_execution_changes_order_only(self):
        ids = [l["id"] for l in self.legs]
        for order in (ids[::-1], ids[6:] + ids[:6]):
            fwd = corner_run.window_leg_lines(self.exp, ids, corner_id="c")
            alt = corner_run.window_leg_lines(self.exp, order, corner_id="c")
            self.assertNotEqual(fwd, alt)
            self.assertEqual(sorted(fwd), sorted(alt))
            for leg_id in ids:  # every leg block is byte-identical wherever it sits
                self.assertEqual(self.block(leg_id, fwd), self.block(leg_id, alt))

    def test_build_deck_substitutes_every_placeholder(self):
        pdk = mock.Mock(lib_file="/x/sky130.lib.spice")
        corner = corner_run.Corner("tt", 27.0, 3.3)
        deck = corner_run.build_deck(self.exp, pdk, corner, ["* body"])
        self.assertIsNone(re.search(r"\{(corner_id|leg_id|cout_esr_f|cout_dir_f|resr_f|rload_f)\}", deck))
        self.assertEqual(deck.count("\ntran 10u 4m"), 12)
        self.assertEqual(deck.count("\nwrdata "), 12)
        # per-leg measurements are evaluated inside their own leg block
        self.assertEqual(deck.count("let meas_vpk_v__"), 12)

    def test_schematic_carries_the_zero_esr_branch(self):
        sch = (SIM_DIR / "startup/testbench/tb_startup.sch").read_text()
        self.assertEqual(len(re.findall(r"name=CDIR\b", sch)), 1)
        self.assertRegex(sch, r"name=CDIR m=1 value=0 ")


class TestGridVerdict(unittest.TestCase):
    def setUp(self):
        self.exp = load_exp()
        self.corner = corner_run.Corner("tt", 27.0, 3.3)

    def result(self, drop=None, fail=None):
        checks = []
        for m in self.exp.measurements:
            if m.leg is None:
                continue
            val = {"vpk_v": 1.80, "vfloor_v": 1.79, "tramp_ms": 0.3}[m.name.split("__")[0]]
            checks.append({"name": m.name, "value": val, "pass": True})
        for leg in self.exp.raw["ramp_monotonicity"]["legs"]:
            checks.append({"name": f"ramp_drawdown_{leg['id']}_v", "value": 0.0, "pass": True})
        if drop:
            checks = [c for c in checks if c["name"] != drop]
        for c in checks:
            if c["name"] == fail:
                c.update(value=0.01, **{"pass": False, "reason": "FAIL: ramp not monotonic"})
        return {"corner_id": self.corner.id, "measurements": checks}

    def cov(self, **kw):
        return corner_run.grid_coverage(self.exp, [self.result(**kw)], [self.corner])

    def test_complete_passing_grid_counts_ramp_conditions(self):
        g = self.cov()
        self.assertEqual(g["conditions_expected"], 3 * 12 + 12)
        self.assertTrue(g["complete"] and g["pass"])

    def test_missing_ramp_trace_cannot_qualify_the_grid(self):
        g = self.cov(drop="ramp_drawdown_c4u7_50ma_esr500m_v")
        self.assertFalse(g["complete"] or g["pass"])
        self.assertEqual(g["failures"][0]["status"], "missing")
        self.assertEqual(g["failures"][0]["leg"], "c4u7_50ma_esr500m")

    def test_failing_ramp_leg_fails_the_grid(self):
        g = self.cov(fail="ramp_drawdown_c330n_0ma_esr0_v")
        self.assertFalse(g["pass"])
        self.assertEqual(g["failures"][0]["esr_ohm"], 0)

    def test_missing_leg_measurement_cannot_qualify_the_grid(self):
        g = self.cov(drop="vpk_v__c330n_50ma_esr500m")
        self.assertFalse(g["pass"])

    def test_declared_grid_without_results_is_not_qualified(self):
        g = corner_run.grid_coverage(self.exp, [], [self.corner])
        self.assertFalse(g["pass"])
        self.assertEqual(g["conditions_evaluated"], 0)


class TestRecordFingerprint(unittest.TestCase):
    def test_rload_axis_is_part_of_the_input_fingerprint(self):
        from _record_common import pvt_input_sections

        raw = json.loads((SIM_DIR / "startup/experiment.json").read_text())
        base = pvt_input_sections(raw, None)["analyses"]
        raw["window_grid"]["legs"][0]["rload_ohm"] = 99
        self.assertNotEqual(base, pvt_input_sections(raw, None)["analyses"])


if __name__ == "__main__":
    unittest.main()
