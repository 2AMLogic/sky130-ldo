"""Issue #666: the shared manifest measurement-expression evaluator.

Both batch adapters' expression grading (line-regulation `evaluate`,
startup-ramp `evaluate_measurement`) delegate to one recursive-descent
evaluator in `sim/bin/_meas_expr.py`, parameterised only by the reference
grammar and the error class. These are PDK-free unit checks of that unified
grammar, of the superset SPICE suffix table and of the per-adapter wiring;
the end-to-end adapter suites are test_batch_line_regulation_379.py and
test_batch_startup_ramp_336.py.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))
import batch_line_regulation as blr  # noqa: E402
import batch_startup_ramp as bsr  # noqa: E402

REFS = {"tran1.vout_lo", "tran1.vout_hi"}
CARDS = {"vpk", "vfloor", "vset", "tset"}


class TestSharedGrammar(unittest.TestCase):
    def test_line_regulation_expressions(self):
        vals = {"tran1.vout_lo": 1.8, "tran1.vout_hi": 1.806}
        self.assertAlmostEqual(blr.evaluate("tran1.vout_hi - tran1.vout_lo", vals, REFS), 0.006)
        self.assertAlmostEqual(blr.evaluate("abs(tran1.vout_lo - tran1.vout_hi)", vals, REFS), 0.006)
        self.assertAlmostEqual(blr.evaluate("(tran1.vout_lo + 1m) * 2", vals, REFS), 3.602)

    def test_startup_ramp_expressions(self):
        vals = {"vpk": 1.9, "vfloor": 0.2, "tset": 4.3e-4}
        self.assertAlmostEqual(bsr.evaluate_measurement("vpk - vfloor", vals), 1.7)
        self.assertAlmostEqual(bsr.evaluate_measurement("1000*(tset - 100u)", vals), 0.33, places=9)

    def test_missing_value_or_division_by_zero_is_never_guessed(self):
        half = {"tran1.vout_lo": 1.8}
        self.assertIsNone(blr.evaluate("tran1.vout_lo - tran1.vout_hi", half, REFS))
        self.assertIsNone(blr.evaluate("1/(tran1.vout_lo - tran1.vout_lo)", {"tran1.vout_lo": 1.8}, REFS))
        self.assertIsNone(bsr.evaluate_measurement("vpk - vset", {"vpk": 1.9, "vset": None}))
        self.assertIsNone(bsr.evaluate_measurement("vpk/(vfloor - vfloor)", {"vpk": 1.9, "vfloor": 0.2}))
        self.assertIsNone(bsr.evaluate_measurement("abs(vset - 1)", {"vset": None}))

    def test_references_match_case_insensitively(self):
        self.assertAlmostEqual(blr.evaluate("TRAN1.VOUT_LO", {"tran1.vout_lo": 1.8}, REFS), 1.8)
        self.assertAlmostEqual(bsr.evaluate_measurement("VPK", {"vpk": 1.9}), 1.9)


class TestSupersetSuffixTable(unittest.TestCase):
    def test_every_spice_suffix_parses_on_both_adapters(self):
        # the former line-regulation copy stopped at k and rejected t/g/meg/f
        # (the #666 parallel drift); the unified table is the additive superset
        for text, want in (("1t", 1e12), ("2g", 2e9), ("3meg", 3e6), ("4k", 4e3),
                           ("5m", 5e-3), ("6u", 6e-6), ("7n", 7e-9), ("8p", 8e-12),
                           ("9f", 9e-15), ("1.5", 1.5), ("2e3", 2e3)):
            self.assertAlmostEqual(blr.evaluate(text, {}, set()), want, msg=text)
            self.assertAlmostEqual(bsr.evaluate_measurement(text, {}), want, msg=text)

    def test_milli_and_mega_stay_distinct(self):
        self.assertAlmostEqual(blr.evaluate("1meg * 1m", {}, set()), 1e3)
        self.assertAlmostEqual(bsr.evaluate_measurement("1meg * 1m", {}), 1e3)


class TestAdapterWiring(unittest.TestCase):
    def test_each_adapter_raises_its_own_error_class(self):
        for bad in ("", "abs 1", "(1", "1 +", "sqrt(1)", "tran9.vout_lo", "vpk; 1", "1q"):
            with self.assertRaises(blr.EndpointTranslationError, msg=bad):
                blr.evaluate(bad, {}, REFS)
            with self.assertRaises(bsr.StartupRampError, msg=bad):
                bsr.evaluate_measurement(bad, {})
            with self.assertRaises(bsr.StartupRampError, msg=bad):
                bsr.evaluate_measurement(bad, {"vset": None})

    def test_shared_refusal_strings(self):
        cases = {"abs 1": "abs needs parentheses", "abs(1": "unbalanced parentheses",
                 "1 1": "trailing tokens", "": "must be one non-empty line",
                 "1q": "unsupported number"}
        for bad, text in cases.items():
            with self.assertRaises(blr.EndpointTranslationError) as ctx:
                blr.evaluate(bad, {}, REFS)
            self.assertIn(text, str(ctx.exception))
            with self.assertRaises(bsr.StartupRampError) as ctx:
                bsr.evaluate_measurement(bad, {})
            self.assertIn(text, str(ctx.exception))

    def test_reference_grammar_stays_per_adapter(self):
        # dotted `tranN.card` for the endpoint adapters, a bare card name for
        # the ramp adapter: each refuses the other's shape, never re-lexes it
        with self.assertRaises(blr.EndpointTranslationError):
            blr.evaluate("vpk", {}, {"vpk"})
        with self.assertRaises(bsr.StartupRampError):
            bsr.evaluate_measurement("tran1.vout_lo", {"tran1.vout_lo": 1.0})

    def test_nonfinite_is_none_on_line_regulation_and_passthrough_on_ramp(self):
        # documented divergence, preserved from the pre-#666 evaluators: the
        # endpoint grader records a non-finite result as missing, the ramp
        # grader hands the value to grade_bounds unchanged
        self.assertIsNone(blr.evaluate("1e308*1e3*1e3", {}, set()))
        self.assertEqual(bsr.evaluate_measurement("1e308*1e3*1e3", {}), math.inf)


if __name__ == "__main__":
    unittest.main()
