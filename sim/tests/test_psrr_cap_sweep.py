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


class TestRequestShape(unittest.TestCase):
    BODY = ["* x", "COUT VOUT VESR 1u m=1", "RESR VESR 0 10m m=1", "RLOAD VOUT 0 1.8k m=1"]

    def test_direct_cap_added_once_next_to_resr(self):
        out = s.add_direct_cap(self.BODY)
        self.assertEqual(out[out.index("RESR VESR 0 10m m=1") + 1], "CDIR VOUT 0 0")
        with self.assertRaises(ValueError):
            s.add_direct_cap(out)
        with self.assertRaises(ValueError):
            s.add_direct_cap(["COUT VOUT VESR 1u"])

    def test_zero_esr_alters_open_series_branch(self):
        self.assertEqual(s.point_alters(0.33, 0.0, 0.01), {"COUT": 0.0, "RESR": 0.01, "CDIR": 0.33e-6})
        self.assertEqual(s.point_alters(4.7, 0.5, 0.01), {"COUT": 4.7e-6, "RESR": 0.5, "CDIR": 0.0})

    def test_steps_cover_every_point_and_load_with_explicit_alters(self):
        steps, smap = s.build_steps(MANIFEST)
        # 9 points + 1 repeat, x 2 loads, x (op, ac)
        self.assertEqual(len(steps), 40)
        self.assertEqual(len({st["name"] for st in steps}), 40)
        for st in steps:
            if st["analysis"]["kind"] == "op":
                self.assertEqual(set(st["alter"]), {"COUT", "RESR", "CDIR", "RLOAD"})
            else:
                self.assertEqual(st["analysis"]["args"], "lin 3 1e3 1e5")
        self.assertEqual(smap[-1]["tag"], "rep_c1u_esr10m")
        self.assertEqual({(e["c_uf"], e["esr_ohm"]) for e in smap[:-2]}, set(s.sweep_points(MANIFEST)))

    def test_parse_corner_reads_steps_and_reports_failures(self):
        steps, smap = s.build_steps(MANIFEST)
        meas, stat = [], []
        for st in steps:
            stat.append({"name": st["name"], "status": "ok"})
            for m in st["measurements"]:
                meas.append({"name": f"{st['name']}.{m['name']}", "value": 20.0 if m["name"] != "vseed" else 1.8})
        # one AC step fails at the 0.33 uF / 0 ohm / 50 mA point
        bad = "c0p33u_esr0m_50ma_ac"
        for x in stat:
            if x["name"] == bad:
                x["status"] = "error"
        for x in meas:
            if x["name"].startswith(bad + "."):
                x["value"] = None
        res, rep = s.parse_corner(MANIFEST, "tt_27c_3.30v", {"steps": stat, "measurements": meas})
        self.assertEqual(len(res), 9)
        self.assertEqual(len(rep), 1)
        badrow = next(r for r in res if (r["c_uf"], r["esr_ohm"]) == (0.33, 0.0))
        self.assertFalse(badrow["ok"])
        self.assertIsNone(badrow["metrics"]["psrr_100khz_50ma_db"])
        self.assertEqual(badrow["metrics"]["psrr_1khz_1ma_db"], 20.0)
        self.assertTrue(all(r["ok"] for r in res if r is not badrow))
        # a non-converged cell is reported to select_worst, never dropped
        full = res + [dict(r, corner_id=k) for k in ("ss_-40c_2.97v", "ff_125c_3.63v") for r in res
                      if r is not badrow] + [dict(badrow, corner_id=k) for k in ("ss_-40c_2.97v", "ff_125c_3.63v")]
        sel = s.select_worst(MANIFEST, full)
        self.assertIsNone(sel["psrr_1khz_1ma_db"]["finding"])
        self.assertEqual(len(sel["psrr_1khz_1ma_db"]["missing"]), 3)

    def test_absent_corner_makes_every_cell_not_ok(self):
        res, rep = s.parse_corner(MANIFEST, "tt_27c_3.30v", None)
        self.assertTrue(res and not any(r["ok"] for r in res))

    def test_job_that_never_ran_is_infrastructure_failure(self):
        refused = {"status": "error", "diagnostics": [
            {"code": "batch_job_failed", "message": "runner version mismatch -- the request was not run"}]}
        self.assertIn("batch_job_failed", s.job_not_run_reason(refused, has_engine_log=False))
        self.assertIn("no engine log", s.job_not_run_reason({"status": "error"}, has_engine_log=False))
        # a corner that ran (log present) is graded cell by cell, not aborted
        self.assertIsNone(s.job_not_run_reason(refused, has_engine_log=True))

    def test_independence_report(self):
        res = [{"corner_id": "a", "c_uf": 1.0, "esr_ohm": 0.01, "metrics": {M: 10.0}}]
        same = [{"corner_id": "a", "c_uf": 1.0, "esr_ohm": 0.01, "metrics": {M: 10.0}}]
        diff = [{"corner_id": "a", "c_uf": 1.0, "esr_ohm": 0.01, "metrics": {M: 10.1}}]
        self.assertTrue(s.independence_report(res, same, 1e-6)[0]["identical"])
        self.assertFalse(s.independence_report(res, diff, 1e-6)[0]["identical"])


if __name__ == "__main__":
    unittest.main()
