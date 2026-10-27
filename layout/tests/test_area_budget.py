"""Sanity tests for layout/bin/ldo-area-budget.py (issue #246): stdlib only."""
import unittest
from pathlib import Path
from _layout_script_loader import load_script  # noqa: E402

ab = load_script("area_budget", Path(__file__).resolve().parent.parent / "bin" / "ldo-area-budget.py")


class FoldBank(unittest.TestCase):
    def test_body_length_is_conserved(self):
        r = ab.fold_bank([1500.0], 100.0, ab.PROBE, False)
        n = r["segments_per_resistor"][0]
        self.assertGreaterEqual(n * (100.0 - 1.28), 1500.0)
        self.assertLess((n - 1) * (100.0 - 1.28), 1500.0)

    def test_optimistic_never_larger(self):
        c = ab.fold_bank([1500.0, 52.0], 100.0, ab.PROBE, False)
        o = ab.fold_bank([1500.0, 52.0], 100.0, ab.PROBE, True)
        self.assertLessEqual(o["bank_area_um2"], c["bank_area_um2"])

    def test_num_suffixes(self):
        self.assertAlmostEqual(ab.num("150p"), 150e-12)
        self.assertEqual(ab.num("2.5"), 2.5)


class Limit(unittest.TestCase):
    def test_limit_unchanged(self):
        self.assertEqual(ab.LIMIT_UM2, 0.1e6)


if __name__ == "__main__":
    unittest.main()
