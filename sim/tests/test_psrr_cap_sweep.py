"""PDK-free tests for sim/bin/psrr_cap_sweep.py (issue #314, Phase 1)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR / "bin"))
import psrr_cap_sweep as s  # noqa: E402

MANIFEST = s.load_manifest(SIM_DIR / "psrr-dc" / "cap-esr-sweep.json")
M = MANIFEST["metrics"][0]


def make(fn):
    """Full result set; fn(corner_id, c, esr) -> value for every metric."""
    out = []
    for corner, (c, r) in s.expected_cells(MANIFEST):
        out.append({"corner_id": corner, "c_uf": c, "esr_ohm": r, "ok": True,
                    "metrics": {m: fn(corner, c, r) for m in MANIFEST["metrics"]}})
    return out


class TestManifest(unittest.TestCase):
    def test_corners_match_quick_subset(self):
        exp = json.loads((SIM_DIR / "psrr-dc" / "experiment.json").read_text())
        self.assertEqual(MANIFEST["corners"], exp["quick_subset"])

    def test_metrics_exist_in_experiment(self):
        exp = json.loads((SIM_DIR / "psrr-dc" / "experiment.json").read_text())
        names = {m["name"] for m in exp["measurements"]}
        self.assertTrue(set(MANIFEST["metrics"]) <= names)

    def test_grid_size(self):
        self.assertEqual(len(s.sweep_points(MANIFEST)), 9)
        self.assertEqual(len(s.expected_cells(MANIFEST)), 27)


class TestSelection(unittest.TestCase):
    def test_worst_point_is_min_over_corners_and_points(self):
        def fn(corner, c, r):
            return 10.0 if (corner, c, r) == ("ss_-40c_2.97v", 4.7, 0.5) else 40.0 + c
        rep = s.select_worst(MANIFEST, make(fn))
        f = rep[M]["finding"]
        self.assertEqual((f["c_uf"], f["esr_ohm"], f["corner_id"]), (4.7, 0.5, "ss_-40c_2.97v"))
        self.assertEqual(rep[M]["missing"], [])

    def test_tie_breaks_low_c_then_low_esr(self):
        rep = s.select_worst(MANIFEST, make(lambda k, c, r: 30.0))
        f = rep[M]["finding"]
        self.assertEqual((f["c_uf"], f["esr_ohm"]), (0.33, 0.0))
        rep = s.select_worst(MANIFEST, make(lambda k, c, r: 30.0 if c >= 1.0 else 50.0))
        f = rep[M]["finding"]
        self.assertEqual((f["c_uf"], f["esr_ohm"]), (1.0, 0.0))
        rep = s.select_worst(MANIFEST, make(lambda k, c, r: 30.0 if r > 0 else 50.0))
        self.assertEqual((rep[M]["finding"]["c_uf"], rep[M]["finding"]["esr_ohm"]), (0.33, 0.01))

    def test_missing_point_gives_no_finding_and_is_reported(self):
        res = [r for r in make(lambda k, c, r: 40.0)
               if not (r["corner_id"] == "ff_125c_3.63v" and r["c_uf"] == 1.0 and r["esr_ohm"] == 0.01)]
        rep = s.select_worst(MANIFEST, res)
        self.assertIsNone(rep[M]["finding"])
        self.assertEqual(rep[M]["missing"], [{"corner_id": "ff_125c_3.63v", "c_uf": 1.0, "esr_ohm": 0.01}])

    def test_non_converged_or_nan_is_missing_not_dropped(self):
        res = make(lambda k, c, r: 40.0)
        res[0]["ok"] = False
        res[1]["metrics"][M] = float("nan")
        rep = s.select_worst(MANIFEST, res)
        self.assertIsNone(rep[M]["finding"])
        self.assertEqual(len(rep[M]["missing"]), 2)
        # other metrics: only the ok=False cell is missing
        self.assertEqual(len(rep[MANIFEST["metrics"][1]]["missing"]), 1)

    def test_zero_esr_point_is_selectable(self):
        rep = s.select_worst(MANIFEST, make(lambda k, c, r: 5.0 if r == 0 and c == 0.33 else 40.0))
        f = rep[M]["finding"]
        self.assertEqual((f["c_uf"], f["esr_ohm"]), (0.33, 0.0))


class TestNetlistPoint(unittest.TestCase):
    BODY = ["* x", "COUT VOUT VESR 1u m=1", "RESR VESR 0 10m m=1", "RLOAD VOUT 0 1.8k m=1"]

    def test_nonzero_esr(self):
        out = s.apply_cap_point(self.BODY, 4.7, 0.5)
        self.assertIn("COUT VOUT VESR 4.7u m=1", out)
        self.assertIn("RESR VESR 0 0.5 m=1", out)

    def test_zero_esr_is_topology_not_standin(self):
        out = s.apply_cap_point(self.BODY, 0.33, 0.0)
        self.assertIn("COUT VOUT 0 0.33u m=1", out)
        self.assertFalse(any(l.upper().startswith("RESR") for l in out))
        self.assertIn("RLOAD VOUT 0 1.8k m=1", out)

    def test_missing_cards_raise(self):
        with self.assertRaises(ValueError):
            s.apply_cap_point(["COUT VOUT VESR 1u"], 1, 1)
        with self.assertRaises(ValueError):
            s.apply_cap_point(["RESR VESR 0 10m"], 1, 1)


if __name__ == "__main__":
    unittest.main()
