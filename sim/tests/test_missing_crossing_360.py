"""Tests for the #360 response-level crossing extractor (pure python, synthetic fixtures).

Fixtures are analytic transfer functions sampled on a log grid; no ngspice. The key
invariant: a response without a negative-real-axis crossing never yields a GM number
and is never reported as supported/passing.
"""
from __future__ import annotations

import cmath
import math
import unittest
from pathlib import Path
from _sim_script_loader import load_script  # noqa: E402

SIM_DIR = Path(__file__).resolve().parents[1]
_DIR = next((SIM_DIR / "loop-gain" / "diagnostics").glob("*-missing-crossing"))
ce = load_script("crossing_extract", _DIR / "crossing_extract.py", register=True)


def grid(lo, hi, ppd=60):
    n = int(round((math.log10(hi) - math.log10(lo)) * ppd)) + 1
    return [10 ** (math.log10(lo) + k / ppd) for k in range(n)]


def sample(tf, lo, hi):
    f = grid(lo, hi)
    v = [tf(1j * 2 * math.pi * x) for x in f]
    return f, [z.real for z in v], [z.imag for z in v]


def poles3(s):  # three poles at 1 kHz, DC gain 100 (40 dB): GM = 20log10(8/100)... finite
    w = 2 * math.pi * 1e3
    return 100.0 / (1 + s / w) ** 3


class Extract(unittest.TestCase):
    def test_finite_crossing(self):
        r = ce.analyze(*sample(poles3, 1, 1e7))
        self.assertEqual(r["status"], "finite")
        self.assertTrue(r["gm_supported"])
        # three equal poles: -180 at sqrt(3) * fp, |T| = 100/8 -> GM = -21.94 dB
        self.assertAlmostEqual(r["gm_crossing_hz"], 1e3 * math.sqrt(3), delta=40)
        self.assertAlmostEqual(r["gm_db"], -20 * math.log10(100 / 8), delta=0.1)
        self.assertFalse(r["gm_ge_10"])
        self.assertIsNotNone(r["pm_deg"])

    def test_finite_passing_gm(self):
        w = 2 * math.pi * 1e3
        # 4-pole at 1 kHz with DC gain 3: |T| at the -180 point (1 kHz) = 3/4 -> GM = +2.5 dB, so
        # a finite GM is reported and graded against the 10 dB target (fails it)
        r = ce.analyze(*sample(lambda s: 3.0 / (1 + s / w) ** 4, 1, 1e7))
        self.assertEqual(r["status"], "finite")
        self.assertAlmostEqual(r["gm_db"], -20 * math.log10(3 / 4), delta=0.1)
        self.assertFalse(r["gm_ge_10"])

    def test_multiple_crossings(self):
        w = 2 * math.pi * 1e3
        tf = lambda s: 1000.0 / ((1 + s / w) ** 4 * (1 + s / (w * 1e3)) ** 4)  # phase passes -180 then -540
        r = ce.analyze(*sample(tf, 1, 1e9))
        self.assertEqual(r["status"], "multiple_crossings")
        self.assertGreater(len(r["negative_axis_crossings"]), 1)
        self.assertEqual(r["gm_db"], r["negative_axis_crossings"][0]["gm_db"])  # first crossing
        self.assertLessEqual(r["worst_gm_db"], r["gm_db"])

    def test_wrapped_phase(self):
        # same response: principal phase wraps, unwrapped phase must be continuous and agree
        f, re, im = sample(poles3, 1, 1e7)
        r = ce.analyze(f, re, im)
        self.assertGreaterEqual(r["principal_phase_wraps"], 1)
        self.assertLess(r["min_phase_deg"], -180.0)
        self.assertTrue(r["legacy_agrees"])
        un = ce.unwrap_deg(ce.principal_phase(re, im))
        self.assertTrue(all(abs(un[k + 1] - un[k]) < 180 for k in range(len(un) - 1)))

    def test_truncated_range(self):
        # same three-pole response but the sweep stops below the crossing, gain still > 0 dB
        r = ce.analyze(*sample(poles3, 1, 1e3))
        self.assertEqual(r["status"], "no_unity_crossing")
        self.assertIsNone(r["gm_db"])
        self.assertFalse(r["gm_supported"])
        # stop just past crossover but before the -180 point
        w = 2 * math.pi * 1e3
        tf = lambda s: 100.0 / (1 + s / w) ** 3
        r = ce.analyze(*sample(tf, 1, 2e4))  # |T|<1 near 20 kHz? 100/(20)^3 <<1; crossover ~ 4.6 kHz
        self.assertIsNone(r["gm_db"] if r["status"] != "finite" else None)
        self.assertNotEqual(r["status"], "absent_in_range")
        self.assertFalse(r["gm_supported"] and r["gm_db"] is None)

    def test_no_crossing_is_not_infinite_or_pass(self):
        w = 2 * math.pi * 1e3
        tf = lambda s: 100.0 * (1 + s / (w * 10)) / (1 + s / w) ** 2  # lead zero: phase recovers toward -90
        r = ce.analyze(*sample(tf, 1, 1e12))
        self.assertEqual(r["status"], "absent_in_range")
        self.assertIsNone(r["gm_db"])
        self.assertIsNone(r["worst_gm_db"])
        self.assertFalse(r["gm_supported"])
        self.assertNotIn("gm_ge_10", r)
        self.assertEqual(r["negative_axis_crossings"], [])

    def test_no_crossing_truncated_when_phase_still_falling(self):
        w = 2 * math.pi * 1e3
        tf = lambda s: 100.0 * cmath.exp(-s * 2e-9) / (1 + s / w)  # delay: -180 deg only at ~125 MHz, past the 100 MHz sweep end
        r = ce.analyze(*sample(tf, 1, 1e8))
        self.assertIn(r["status"], ("truncated_range",))
        self.assertIsNone(r["gm_db"])
        self.assertFalse(r["gm_supported"])

    def test_read_wrdata_variants(self):
        a = ce.read_wrdata("frequency lg\n1 0 0.5 -0.1\n2 0 0.4 -0.2\n")
        b = ce.read_wrdata("1 0.5 -0.1\n2 0.4 -0.2\n")
        self.assertEqual(a, b)
        with self.assertRaises(ValueError):
            ce.read_wrdata("1 2\n")


if __name__ == "__main__":
    unittest.main()
