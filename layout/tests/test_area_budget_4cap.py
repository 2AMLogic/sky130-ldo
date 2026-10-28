"""Sanity tests for layout/bin/ldo-area-budget-4cap.py (issue #459): stdlib only."""
import unittest
from pathlib import Path
from _layout_script_loader import load_script  # noqa: E402

ab = load_script("area_budget_4cap", Path(__file__).resolve().parent.parent / "bin" / "ldo-area-budget-4cap.py")


class Budget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = ab.build()

    def test_limit_unchanged(self):
        self.assertEqual(ab.LIMIT_UM2, 0.1e6)

    def test_all_four_caps_priced(self):
        self.assertEqual(sorted(self.b["inventory"]["capacitors_f"]), ["C_CL", "C_COMP", "C_SS", "C_TS"])

    def test_both_densities_reported(self):
        s = self.b["scenarios"]
        self.assertTrue(any("4fF" in k for k in s) and any("2fF" in k for k in s))

    def test_lower_density_never_smaller(self):
        s = self.b["scenarios"]
        self.assertGreaterEqual(s["caps_overlay_single_2fF_nominal"]["total_um2"],
                                s["caps_overlay_nominal_4fF"]["total_um2"])

    def test_straight_rbias_fails(self):
        self.assertGreater(self.b["resistors"]["r_bias_straight"]["area_at_current_height_um2"], ab.LIMIT_UM2)


if __name__ == "__main__":
    unittest.main()
