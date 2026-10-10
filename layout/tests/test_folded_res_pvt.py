"""Unit tests for the issue #263 PVT/mismatch helpers (stdlib only)."""
import json
import sys
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"
sys.path.insert(0, str(BIN))
import _folded_res_pvt as pvt  # noqa: E402

MATRIX = json.loads((BIN.parent / "folded-res-qual" / "pvt" / "matrix.json").read_text())
TOL = {"R_BIAS": 0.00246, "R_FB_A": 0.0160}


def fake_values(shift_per_seg):
    """Values where each N-segment j1 chain is (1 + shift_per_seg*(N-1)) x unsplit."""
    vals = {}
    for v in pvt.variants(MATRIX):
        base = 1.2e6 if v["device"] == "R_BIAS" else 1.0e6
        mult = {"noj": 1.0, "j1": 1.0, "j4": 1.0}[v["mode"]]
        vals[v["tag"]] = base * (1 + shift_per_seg * (v["segments"] - 1) * mult)
    return vals


class Deck(unittest.TestCase):
    def test_variant_count_and_unique_tags(self):
        vs = pvt.variants(MATRIX)
        self.assertEqual(len({v["tag"] for v in vs}), len(vs))
        # N=1 once; each N>=2 in three joint modes
        self.assertEqual(len(vs), 3 * (10 - 1) + 1 + 3 * (6 - 1) + 1)

    def test_segments_sum_to_schematic_length(self):
        deck = pvt.build_deck(MATRIX)
        self.assertIn("Xr_r_bias_n16_noj_15 ", deck)
        self.assertIn("l=93.75", deck)
        self.assertEqual(deck.count("RJr_r_bias_n4_j1_"), 3)
        self.assertEqual(deck.count("RJr_r_bias_n4_j4_"), 3)
        self.assertNotIn("RJr_r_bias_n4_noj_", deck)

    def test_requests_step_supply_by_index(self):
        r = pvt.det_request(MATRIX, "deck.cir")
        lens = {len(v) for v in r["corners"]["supply_v"].values()}
        self.assertEqual(lens, {3})
        self.assertEqual(len(r["measurements"]), len(pvt.variants(MATRIX)))


class Deterministic(unittest.TestCase):
    def test_worst_shift_and_verdict(self):
        pts = [("tt/x/27C", fake_values(0.0002)), ("ss/x/125C", fake_values(0.0001))]
        rows = pvt.det_shifts(pts, MATRIX, TOL)
        r = next(x for x in rows if x["device"] == "R_BIAS" and x["segments"] == 16 and x["mode"] == "j1")
        self.assertAlmostEqual(r["worst_shift"], 0.003, places=9)
        self.assertEqual(r["worst_point"], "tt/x/27C")
        self.assertEqual(r["verdict"], "NOT EQUIVALENT")
        r4 = next(x for x in rows if x["device"] == "R_BIAS" and x["segments"] == 4 and x["mode"] == "j1")
        self.assertEqual(r4["verdict"], "EQUIVALENT")

    def test_missing_base_is_loud(self):
        vals = fake_values(0.0)
        del vals["r_r_bias_n1_noj"]
        with self.assertRaises(ValueError):
            pvt.det_shifts([("tt/x/27C", vals)], MATRIX, TOL)

    def test_divider_common_shift_cancels(self):
        self.assertAlmostEqual(pvt.divider_vout_error(0.01, 3), 0.0, places=12)
        self.assertGreater(abs(pvt.divider_vout_error(0.01, 1)), 0.0)


class MonteCarlo(unittest.TestCase):
    def test_corner_id_split(self):
        self.assertEqual(pvt.split_corner_id("tt_mm/novdd/27C/mc12"), ("tt_mm", "novdd", "27C", "mc12"))
        self.assertEqual(pvt.split_corner_id("tt/a=1.0V/-40C"), ("tt", "a=1.0V", "-40C", None))

    def test_sigma_ratio_and_qualification(self):
        import random
        rnd = random.Random(1)
        pts = []
        for i in range(400):
            vals = {}
            for v in pvt.variants(MATRIX):
                base = 1.2e6 if v["device"] == "R_BIAS" else 1.0e6
                spread = 0.001 * (1.5 if v["segments"] == 16 else 1.0)
                vals[v["tag"]] = base * (1 + rnd.gauss(0, spread))
            pts.append((f"tt_mm/novdd/27C/mc{i}", vals))
        rows = pvt.mc_stats(pvt.mc_groups(pts), MATRIX, TOL)
        agg = pvt.mc_rollup(rows)
        self.assertTrue(agg[("R_BIAS", 4, "j1")]["m2"])
        self.assertFalse(agg[("R_BIAS", 16, "j1")]["m2"])
        det = pvt.det_shifts([("tt/x/27C", fake_values(0.0001))], MATRIX, TOL)
        quals = pvt.qualification(det, agg, MATRIX)
        q4 = next(q for q in quals if q["device"] == "R_BIAS" and q["segments"] == 4)
        self.assertTrue(q4["qualified"])
        q16 = next(q for q in quals if q["device"] == "R_BIAS" and q["segments"] == 16)
        self.assertFalse(q16["qualified"])
        self.assertTrue(q16["control"])

    def test_recommendation_excludes_controls_and_handles_none(self):
        quals = [
            {"device": "A", "segments": 2, "qualified": True, "control": False},
            {"device": "A", "segments": 4, "qualified": True, "control": False},
            {"device": "A", "segments": 16, "qualified": True, "control": True},
            {"device": "B", "segments": 2, "qualified": False, "control": False},
        ]
        self.assertEqual(pvt.recommendation(quals, "A"), 4)
        self.assertIsNone(pvt.recommendation(quals, "B"))


if __name__ == "__main__":
    unittest.main()
