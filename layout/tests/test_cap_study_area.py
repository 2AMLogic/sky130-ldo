"""Unit tests for the #319 capacitor study's area arithmetic and verdict rules
(layout/cap-study/_cap_study.py). Stdlib only.

The verdict rules carry the issue's central guard: missing evidence must never
become "no option fits" (outcome b) -- it is inconclusive (outcome c)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cap-study"))

import _cap_study as cs  # noqa: E402

TOTAL_F = 150e-12 + 10e-12 + 1e-12 + 1e-12


class AreaArithmetic(unittest.TestCase):
    def test_reproduces_246_cap_area(self):
        # #246 budget.json: 81000 um^2 at 2 fF/um^2, 40500 um^2 at 4 fF/um^2
        self.assertAlmostEqual(cs.area_for(TOTAL_F, 2e-15), 81000.0, places=6)
        self.assertAlmostEqual(cs.area_for(TOTAL_F, 4e-15), 40500.0, places=6)

    def test_reproduces_246_scenarios(self):
        d = 65400.3  # scenario D (no caps)
        self.assertAlmostEqual(cs.beside_total_um2(d, cs.area_for(TOTAL_F, 2e-15)), 146400.3, places=3)
        self.assertAlmostEqual(cs.beside_total_um2(d, cs.area_for(TOTAL_F, 4e-15)), 105900.3, places=3)

    def test_skew_corner(self):
        # ll lowers the MiM density, so the same 162 pF needs more area
        self.assertGreater(cs.area_for(TOTAL_F, 1.78e-15), cs.area_for(TOTAL_F, 2e-15))

    def test_bad_density(self):
        with self.assertRaises(ValueError):
            cs.area_for(TOTAL_F, 0.0)

    def test_interp(self):
        xs, ys = [-1.0, 0.0, 1.0], [1.0, 0.5, 2.0]
        self.assertAlmostEqual(cs.interp(xs, ys, -0.5), 0.75)
        self.assertAlmostEqual(cs.interp(xs, ys, 1.0), 2.0)
        self.assertIsNone(cs.interp(xs, ys, 1.5))  # never extrapolated past the measured sweep


class Verdicts(unittest.TestCase):
    def test_fits_needs_drawn_overlay_evidence(self):
        self.assertEqual(cs.fit_verdict(146400.0, True, True, True), "fits")
        self.assertNotEqual(cs.fit_verdict(50000.0, False, False, False), "fits")

    def test_does_not_fit_only_on_a_lower_bound_breach_without_overlay(self):
        self.assertEqual(cs.fit_verdict(113000.0, False, False, False), "does-not-fit")
        self.assertEqual(cs.fit_verdict(100000.0, False, False, False), "does-not-fit")  # strict '<'
        # overlay possible but unpriced -> not established, never a no-fit
        self.assertEqual(cs.fit_verdict(146400.0, False, True, False), "not-established")
        # lower bound under the limit, keep-out unknown -> not established
        self.assertEqual(cs.fit_verdict(86000.0, False, False, False), "not-established")

    def test_outcome_rules(self):
        all_no = {"a": "does-not-fit", "b": "does-not-fit"}
        self.assertEqual(cs.outcome(all_no, evidence_complete=True), "b")
        # the guard: missing evidence can never produce (b)
        self.assertEqual(cs.outcome(all_no, evidence_complete=False), "c")
        self.assertEqual(cs.outcome({"a": "fits", "b": "not-established"}, evidence_complete=False), "c")
        self.assertEqual(cs.outcome({"a": "fits", "b": "does-not-fit"}, evidence_complete=True), "a")
        self.assertEqual(cs.outcome({"a": "not-established"}, evidence_complete=True), "c")
        self.assertEqual(cs.outcome({}, evidence_complete=True), "c")

    def test_unmeasured_cells_are_not_numbers(self):
        u = cs.unmeasured("no run")
        self.assertTrue(cs.is_unmeasured(u))
        self.assertEqual(u["value"], "unmeasured")
        self.assertFalse(cs.is_unmeasured(cs.cell(1.0, "F", "file")))


if __name__ == "__main__":
    unittest.main()
