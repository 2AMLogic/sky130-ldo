"""Issue #381: PDK-free controls for the paired load-regulation comparison.

These exercise the comparison logic only; they are not simulator evidence.
"""

from __future__ import annotations

import sys
import unittest

from test_corner_run import SIM_DIR

sys.path.insert(0, str(SIM_DIR / "bin"))
import compare_load_regulation_paired as cmp


def values() -> dict:
    v = {"vout_0ma": 1.802385, "vout_50ma": 1.798832}
    v.update({k + s: v[k] for k in list(v) for s in ("_min", "_max")})
    v.update(cmp.derive(v))
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
        self.assertEqual(len(r["rows"]), 8)

    def test_engine_mismatch_never_claimable(self):
        r = self.run_cmp(le="42")
        self.assertEqual(r["verdict"], "engine_mismatch")
        self.assertFalse(r["equivalence_claimable"])

    def test_missing_and_non_finite_are_unresolved(self):
        local = values()
        del local["vout_50ma_min"]
        self.assertEqual(self.run_cmp(local)["verdict"], "unresolved")
        local = values()
        local["vout_0ma"] = float("nan")
        self.assertEqual(self.run_cmp(local)["verdict"], "unresolved")

    def test_tolerance_breach_is_rejected_not_widened(self):
        local = values()
        local["vout_50ma_max"] += 2e-6
        r = self.run_cmp(local)
        self.assertEqual((r["verdict"], r["breaches"]), ("rejected", ["vout_50ma_max"]))

    def test_derived_tolerance_breach(self):
        local = values()
        local["load_reg_v"] += 3e-6
        self.assertEqual(self.run_cmp(local)["breaches"], ["load_reg_v"])

    def test_verdict_mismatch_is_unresolved(self):
        self.assertEqual(self.run_cmp(lp=False)["verdict"], "unresolved")

    def test_derive(self):
        d = cmp.derive(values())
        self.assertAlmostEqual(d["load_reg_v"], 0.003553, places=9)
        self.assertAlmostEqual(d["load_reg_pct"], 0.197389, places=5)


if __name__ == "__main__":
    unittest.main()
