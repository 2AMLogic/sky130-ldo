"""Issue #511: thermal-staircase batch adapter. Headless, offline: translation,
round planning, response extraction and resume/refusal handling only. Not
evidence of remote execution."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR / "bin"))
sys.path.insert(0, str(SIM_DIR / "thermal"))
import batch_thermal_staircase as bts  # noqa: E402
import run_hysteresis as rh  # noqa: E402
from _record_common import bisect  # noqa: E402


def drive(scenario, flip, tol=0.3125):
    """Run plan() to completion against a monotone oracle; return (bracket, points asked)."""
    want_lowest = bts.SCENARIOS[scenario][1]
    oracle = (lambda T: T >= flip) if want_lowest else (lambda T: T <= flip)
    res, asked = {}, []
    for _ in range(50):
        p = bts.plan(res, scenario, tol)
        if "pending" in p:
            for T in p["pending"]:
                res[T] = oracle(T)
                asked.append(T)
            continue
        return p, asked
    raise AssertionError("did not converge")


class TestPlan(unittest.TestCase):
    def test_matches_local_bisect(self):
        for scen, flip in (("hot", 159.2), ("cold_exc", 172.3)):
            p, _ = drive(scen, flip)
            want_lowest = bts.SCENARIOS[scen][1]
            oracle = (lambda T: T >= flip) if want_lowest else (lambda T: T <= flip)
            grid_lo = 150 if scen == "hot" else 170
            lo, hi = bisect(oracle, grid_lo, grid_lo + 10, 0.3125, want_lowest)
            self.assertEqual(p["bracket"], [lo, hi])

    def test_deterministic_resume_from_partial_results(self):
        _, asked = drive("hot", 159.2)
        partial = {T: T >= 159.2 for T in asked[:-2]}
        again = bts.plan(partial, "hot", 0.3125)
        self.assertEqual(again["pending"], [asked[-2]])

    def test_round0_is_the_whole_grid(self):
        self.assertEqual(bts.plan({}, "hot", 0.3125), {"pending": bts.GRID})

    def test_bracket_end_failures_are_reported_not_asserted(self):
        self.assertIn("error", bts.plan({T: True for T in bts.GRID}, "hot", 0.3))
        self.assertIn("error", bts.plan({T: False for T in bts.GRID}, "hot", 0.3))
        self.assertIn("error", bts.plan({T: False for T in bts.GRID}, "cold_exc", 0.3))


class TestTranslation(unittest.TestCase):
    def test_request_shape_and_netlist(self):
        req = bts.build_request("/x.spice", "ss", [150.0], {"pdk": "sky130A", "lib": "l"}, ["a"], 900, 60)
        (st,) = req["analysis_steps"]
        self.assertEqual(st["analysis"]["args"], "400n 170u uic")
        self.assertEqual([m["spice"] for m in st["measurements"]][1],
                         ".meas tran ts_cmp_39 find v(xldo.ts_cmp) at=39u")
        self.assertEqual(req["corners"], {"process": ["ss"], "temperature_c": [150.0]})
        nl = bts.request_netlist(["R1 a b 1"], 2.97, -0.5e-6)
        self.assertEqual(nl[:3], [".param vsup=2.97", ".param ix_amp=-5e-07", ".param en_dip=vsup"])

    def test_held_predicates(self):
        self.assertTrue(bts.held("hot", 0.9, 0.9, 3.3))
        self.assertFalse(bts.held("hot", 0.9, 3.26, 3.3))
        self.assertTrue(bts.held("cold_exc", 3.2, 3.2, 3.3))
        self.assertFalse(bts.held("cold_exc", 3.2, 0.9, 3.3))

    def test_extract_values_flags_missing_and_nonfinite(self):
        ok = [{"name": f"tran1.{n}", "value": 1.0} for n in bts.CARDS]
        self.assertEqual(bts.extract_values(ok)[1], [])
        vals, why = bts.extract_values(ok[:2] + [{"name": "tran1.ts_cmp_90", "value": float("nan")}])
        self.assertTrue(why)


class TestRecords(unittest.TestCase):
    def test_points_are_exclusive_and_loaded_for_resume(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "points").mkdir()
            p = rh.point_path(out, "tt", 3.3, "hot", 150)
            rh.write_new_text(p, json.dumps({"process": "tt", "supply_v": 3.3, "scenario": "hot",
                                             "temp_c": 150, "held": False}))
            with self.assertRaises(FileExistsError):
                rh.write_new_text(p, "{}")
            self.assertEqual(list(rh.load_points(out)), [("tt", 3.3, "hot", 150)])

    def test_capacity_refused_report_records_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            n, fails = rh.ingest_report(Path(d), Path(d), {"corners": []}, "tt", 3.3, "hot", [150], None, None, "r")
            self.assertEqual(n, 0)
            self.assertIn("not a batch run", fails[0])

    def test_local_grid_refused(self):
        sys.argv = ["x", "--backend", "local"]
        with self.assertRaises(SystemExit):
            rh.main()


if __name__ == "__main__":
    unittest.main()
