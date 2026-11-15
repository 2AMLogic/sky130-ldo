"""Issue #375: PDK-free controls for the paired dropout comparison.

These exercise the comparison logic only; they are not simulator evidence.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from test_corner_run import SIM_DIR

sys.path.insert(0, str(SIM_DIR / "bin"))
import compare_dropout_paired as cmp


def values() -> dict:
    v = {"dropout_vin_x": 2.161658, "vout_at_max_vin_v": 1.798832}
    v.update(cmp.derive(v))
    return v


class CompareTests(unittest.TestCase):
    def run_cmp(self, local=None, re="46", le="47", rp=False, lp=False):
        remote = values()
        return cmp.compare(
            remote, local if local is not None else dict(remote), re, le, rp, lp
        )

    def test_identical_same_engine_is_equivalent(self):
        r = self.run_cmp(le="46")
        self.assertEqual(r["verdict"], "equivalent")
        self.assertEqual(len(r["rows"]), 3)

    def test_engine_mismatch_never_claimable(self):
        r = self.run_cmp()
        self.assertEqual(r["verdict"], "engine_mismatch")
        self.assertFalse(r["equivalence_claimable"])

    def test_missing_and_non_finite_are_unresolved(self):
        local = values()
        del local["vout_at_max_vin_v"]
        self.assertEqual(self.run_cmp(local)["verdict"], "unresolved")
        local = values()
        local["dropout_vin_x"] = float("nan")
        self.assertEqual(self.run_cmp(local)["verdict"], "unresolved")

    def test_tolerance_breach_is_rejected_not_widened(self):
        local = values()
        local["vout_at_max_vin_v"] += 2e-6
        r = self.run_cmp(local, le="46")
        self.assertEqual((r["verdict"], r["breaches"]), ("rejected", ["vout_at_max_vin_v"]))

    def test_raw_card_shift_breaches_both_it_and_the_derived_value(self):
        local = values()
        local["dropout_vin_x"] += 2e-6
        local.update(cmp.derive(local))
        self.assertEqual(self.run_cmp(local, le="46")["breaches"], ["dropout_vin_x", "dropout_v"])

    def test_derived_tolerance_breach(self):
        local = values()
        local["dropout_v"] += 2e-6
        self.assertEqual(self.run_cmp(local, le="46")["breaches"], ["dropout_v"])

    def test_verdict_mismatch_is_unresolved(self):
        self.assertEqual(self.run_cmp(le="46", lp=True)["verdict"], "unresolved")

    def test_derive(self):
        d = cmp.derive(values())
        self.assertAlmostEqual(d["dropout_v"], 0.397658, places=9)
        self.assertIsNone(cmp.derive({})["dropout_v"])
        self.assertIsNone(cmp.derive({"dropout_vin_x": float("inf")})["dropout_v"])

    def test_load_local_reads_meas_and_print_lines_last_wins(self):
        log = (
            "dropout_vin_x         =  2.161660e+00 at=  6.923000e-03\n"
            "vout_at_max_vin_v     =  1.798832e+00 from=  5.50000e-03 to=  6.00000e-03\n"
            "meas_dropout_v = 3.976580e-01\n"
            "dropout_vin_x = 2.1616580000e+00\n"
        )
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "local").mkdir()
            (Path(t) / "local" / "ngspice.log").write_text(log)
            v = cmp.load_local(Path(t))
        self.assertEqual(v["dropout_vin_x"], 2.161658)
        self.assertEqual(v["vout_at_max_vin_v"], 1.798832)
        self.assertAlmostEqual(v["dropout_v"], 0.397658, places=9)

    def test_load_remote_reads_one_response_and_its_engine(self):
        def resp(engine):
            return {
                "environment": {"engine_version": engine},
                "corners": [{
                    "measurements": [
                        {"name": "dropout.dropout_vin_x", "value": 2.161658},
                        {"name": "dropout.vout_at_max_vin_v", "value": 1.798832},
                        {"name": "dropout.dropout_v", "value": 0.397658},
                    ]}],
            }

        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / "remote" / "v3.30").mkdir(parents=True)
            (d / "remote" / "v3.30" / "response.json").write_text(json.dumps(resp("46")))
            v, eng, all_engines = cmp.load_remote(d)
        self.assertEqual((eng, all_engines), ("46", ["46"]))
        self.assertEqual(v["dropout_vin_x"], 2.161658)
        self.assertAlmostEqual(v["dropout_v"], 0.397658, places=9)

    def test_load_remote_with_no_response_raises(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "remote").mkdir()
            with self.assertRaises(SystemExit):
                cmp.load_remote(Path(t))


if __name__ == "__main__":
    unittest.main()
