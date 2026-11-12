"""Issue #541: dependent cold-start / EN re-enable / amplitude rounds of the thermal
batch adapter. Headless, offline: point selection, request shape, record fields.
Not evidence of remote execution."""

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

RESET, TRIP = [159.0, 159.3125], [172.0, 172.3125]


def cmp_report(temps, values):
    """Minimal klt corner report: one passing corner per temperature, cards from `values`."""
    return {"environment": {"remote": {"job_id": "j1"}}, "corners": [
        {"temperature_c": T, "status": "pass", "artifacts": {"log": "x.log"},
         "measurements": [{"name": f"tran1.{n}", "value": v} for n, v in values.items()]} for T in temps]}


class TestDependentPoints(unittest.TestCase):
    def test_matches_local_formula(self):
        pts = bts.dependent_points(RESET, TRIP)
        rm, tm = sum(RESET) / 2, sum(TRIP) / 2
        want = sorted({round(x) for x in (rm - 8, rm - 1, rm + 2, (rm + tm) / 2, tm - 2, tm + 1, tm + 8)})
        self.assertEqual([T for lab, T in pts if lab == "cold"], want)
        self.assertEqual([T for lab, T in pts if lab == "en"], want)
        amp = {(lab, T) for lab, T in pts if lab not in ("cold", "en")}
        self.assertEqual(amp, {("hot_ix+0.25uA", 159.3125), ("hot_ix+0.25uA", 159.0),
                               ("hot_ix+1uA", 159.3125), ("hot_ix+1uA", 159.0),
                               ("cold_exc_ix-0.25uA", 172.0), ("cold_exc_ix-0.25uA", 172.3125),
                               ("cold_exc_ix-1uA", 172.0), ("cold_exc_ix-1uA", 172.3125)})

    def test_pure_function_of_brackets(self):
        self.assertEqual(bts.dependent_points(RESET, TRIP), bts.dependent_points(list(RESET), list(TRIP)))

    def test_labels_are_unique_per_temperature(self):
        pts = bts.dependent_points(RESET, TRIP)
        self.assertEqual(len(pts), len(set(pts)))


class TestScenarioParams(unittest.TestCase):
    def test_en_uses_the_dip_and_hot_disturbance(self):
        p = bts.scenario_params("en")
        self.assertEqual((p["ix_amp"], p["en_dip"]), (bts.IX_HOT, "0"))
        self.assertIn(f"ts_cmp_{bts.T_EN_LOW}", p["cards"])
        self.assertIn(f"ts_cmp_{bts.T_REEN}", p["cards"])

    def test_cold_has_no_disturbance(self):
        self.assertEqual(bts.scenario_params("cold")["ix_amp"], 0.0)

    def test_amplitude_label_roundtrip(self):
        for base, amp in (("hot", 0.25e-6), ("hot", 1.0e-6), ("cold_exc", -0.25e-6), ("cold_exc", -1.0e-6)):
            p = bts.scenario_params(bts.amp_label(base, amp))
            self.assertEqual(p["base"], base)
            self.assertAlmostEqual(p["ix_amp"], amp, places=12)

    def test_staircase_cards_unchanged_and_unknown_label_rejected(self):
        self.assertEqual(list(bts.scenario_params("hot")["cards"]), ["ts_cmp_19", "ts_cmp_39", "ts_cmp_90"])
        with self.assertRaises(ValueError):
            bts.scenario_params("bogus")

    def test_request_netlist_and_cards_for_en(self):
        p = bts.scenario_params("en")
        nl = bts.request_netlist(["R1 a b 1"], 3.3, p["ix_amp"], p["en_dip"])
        self.assertIn(".param en_dip=0", nl)
        req = bts.build_request("/x.spice", "tt", [150], {"pdk": "sky130A", "lib": "l"}, [], 900, 600, p["cards"])
        names = [m["spice"] for m in req["analysis_steps"][0]["measurements"]]
        self.assertIn(".meas tran ts_cmp_165 find v(xldo.ts_cmp) at=165u", names)
        self.assertIn(".meas tran ts_cmp_108 find v(xldo.ts_cmp) at=108u", names)

    def test_extract_requires_the_extended_cards(self):
        three = [{"name": f"tran1.{n}", "value": 1.0} for n in bts.CARDS]
        self.assertTrue(bts.extract_values(three, bts.CARDS_EXT)[1])  # EN cards missing -> point fails
        self.assertEqual(bts.extract_values(three)[1], [])


class TestIngest(unittest.TestCase):
    def ingest(self, label, values, temps=(160,)):
        d = tempfile.mkdtemp()
        rep = cmp_report(temps, values)
        from unittest import mock
        with mock.patch.object(rh.batch_dropout, "remote_completion_problem", return_value=None), \
             mock.patch.object(rh, "assert_klt_read_the_pinned_pdk"), \
             mock.patch.object(rh.batch_dropout, "corner_diagnostic_problems", return_value=[]), \
             mock.patch.object(rh.cr, "detect_solver_diagnostic", return_value=None), \
             mock.patch.object(Path, "read_text", return_value=""):
            n, fails = rh.ingest_report(Path(d), Path(d), rep, "tt", 3.3, label, list(temps), None, None, "r")
        return Path(d), n, fails

    def test_en_point_records_states(self):
        vals = {"ts_cmp_19": 3.3, "ts_cmp_39": 3.3, "ts_cmp_90": 0.1, "ts_cmp_108": 3.0, "ts_cmp_165": 3.3}
        out, n, fails = self.ingest("en", vals)
        self.assertEqual((n, fails), (1, []))
        rec = json.loads(rh.point_path(out, "tt", 3.3, "en", 160).read_text())
        self.assertTrue(rec["hold_tripped"])
        self.assertFalse(rec["after_en_reenable_tripped"])
        self.assertEqual(rec["ts_cmp_while_en_low_v"], 3.0)
        self.assertNotIn("held", rec)
        self.assertEqual(rec["en_dip"], "0")

    def test_missing_en_card_fails_the_point(self):
        vals = {"ts_cmp_19": 3.3, "ts_cmp_39": 3.3, "ts_cmp_90": 0.1}
        out, n, fails = self.ingest("en", vals)
        self.assertEqual(n, 0)
        self.assertIn("missing", fails[0])
        self.assertFalse(rh.point_path(out, "tt", 3.3, "en", 160).exists())

    def test_amplitude_point_has_held_and_unique_key(self):
        vals = {"ts_cmp_19": 3.3, "ts_cmp_39": 0.1, "ts_cmp_90": 0.1}
        out, n, _ = self.ingest("hot_ix+0.25uA", vals)
        self.assertEqual(n, 1)
        rec = json.loads(rh.point_path(out, "tt", 3.3, "hot_ix+0.25uA", 160).read_text())
        self.assertTrue(rec["held"])
        self.assertFalse(rh.point_path(out, "tt", 3.3, "hot", 160).exists())
        self.assertIn(("tt", 3.3, "hot_ix+0.25uA", 160), rh.load_points(out))


class TestCornerBrackets(unittest.TestCase):
    def test_none_until_both_staircases_done(self):
        self.assertIsNone(rh.corner_brackets({}, "tt", 3.3, 0.3125))

    def test_amplitude_points_do_not_leak_into_staircase(self):
        pts = {("tt", 3.3, "hot_ix+1uA", T): {"held": True} for T in bts.GRID}
        self.assertIsNone(rh.corner_brackets(pts, "tt", 3.3, 0.3125))

    def test_ff_uses_lowered_grid_top(self):
        # ff stops at 180 C (issue #231): a staircase that settles on the lowered grid
        # must count as bracketed, not wait for the unreachable 190 C point.
        pts = {}
        for T in bts.grid_for("ff"):
            pts[("ff", 3.3, "hot", T)] = {"held": T >= 160}
            pts[("ff", 3.3, "cold_exc", T)] = {"held": T <= 170}
        self.assertNotIn(190, bts.grid_for("ff"))
        self.assertEqual(rh.corner_brackets(pts, "ff", 3.3, 10.0), [[150, 160], [170, 180]])
        # a non-ff process still needs the full 190 C grid
        self.assertIsNone(rh.corner_brackets(
            {("tt", 3.3, sc, T): v for (_, _, sc, T), v in pts.items()}, "tt", 3.3, 10.0))

    def test_above_bound_only_for_lowered_process(self):
        self.assertTrue(rh.above_bound("ff", 188, None))
        self.assertFalse(rh.above_bound("ff", 180, None))
        self.assertFalse(rh.above_bound("tt", 188, None))
        self.assertFalse(rh.above_bound("ff", 188, {}))


if __name__ == "__main__":
    unittest.main()
