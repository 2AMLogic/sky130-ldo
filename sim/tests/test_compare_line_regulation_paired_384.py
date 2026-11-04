"""Issue #384: PDK-free controls for the paired line-regulation comparison.

These exercise the comparison logic only; they are not simulator evidence.
"""

from __future__ import annotations

import sys
import unittest

from test_corner_run import SIM_DIR

sys.path.insert(0, str(SIM_DIR / "bin"))
import compare_line_regulation_paired as cmp


def values() -> dict:
    v = {
        "vout_1ma_lo": 1.8005,
        "vout_1ma_hi": 1.80071,
        "vout_50ma_lo": 1.79872,
        "vout_50ma_hi": 1.79892,
    }
    for k in list(v):
        v[k + "_min"] = v[k + "_max"] = v[k]
    v.update(cmp.derive_slopes(v))
    return v


class CompareTests(unittest.TestCase):
    def run_cmp(self, local=None, re="46", le="46", rp=True, lp=True):
        remote = values()
        return cmp.compare(
            remote, local if local is not None else dict(remote), re, le, rp, lp
        )

    def test_identical_same_engine_is_equivalent(self):
        r = self.run_cmp()
        self.assertEqual(r["verdict"], "equivalent")
        self.assertTrue(r["equivalence_claimable"])
        self.assertEqual(len(r["rows"]), 14)

    def test_missing_value_is_unresolved(self):
        local = values()
        del local["vout_50ma_hi_min"]
        r = self.run_cmp(local)
        self.assertEqual(
            (r["verdict"], r["missing"]), ("unresolved", ["vout_50ma_hi_min"])
        )

    def test_non_finite_value_is_unresolved(self):
        local = values()
        local["vout_1ma_lo"] = float("nan")
        self.assertEqual(self.run_cmp(local)["verdict"], "unresolved")

    def test_tolerance_breach_is_rejected_not_widened(self):
        local = values()
        local["vout_50ma_hi_max"] += 2e-6
        r = self.run_cmp(local)
        self.assertEqual(
            (r["verdict"], r["breaches"]), ("rejected", ["vout_50ma_hi_max"])
        )

    def test_slope_breach_is_rejected(self):
        local = values()
        local["line_reg_1ma_mv_per_v"] += 0.02
        self.assertEqual(self.run_cmp(local)["breaches"], ["line_reg_1ma_mv_per_v"])

    def test_engine_mismatch_blocks_equivalence_claim(self):
        r = self.run_cmp(le="42")
        self.assertEqual(r["verdict"], "engine_mismatch")
        self.assertFalse(r["equivalence_claimable"])

    def test_unknown_remote_engine_blocks_equivalence_claim(self):
        self.assertFalse(self.run_cmp(re=None)["equivalence_claimable"])

    def test_matching_spec_failure_is_equivalent_but_not_compliance(self):
        r = self.run_cmp(rp=False, lp=False)
        self.assertEqual(r["verdict"], "equivalent")
        self.assertEqual(
            r["spec_verdicts"],
            {"remote_pass": False, "local_pass": False, "match": True},
        )

    def test_mismatched_spec_verdicts_are_unresolved(self):
        self.assertEqual(self.run_cmp(rp=True, lp=False)["verdict"], "unresolved")


if __name__ == "__main__":
    unittest.main()
