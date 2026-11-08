"""Tests for the #370 fleet-confirmation driver helpers (pure python, no fleet, no ngspice)."""

from __future__ import annotations

import unittest
from pathlib import Path

from _sim_script_loader import load_script

SIM_DIR = Path(__file__).resolve().parents[1]
rc = load_script(
    "rcz_fleet_confirm", SIM_DIR / "bin" / "rcz-fleet-confirm.py", register=True
)


class Helpers(unittest.TestCase):
    def test_edit_rcz_scales_only_the_rcz_card(self):
        body = "XR_CZ EA_CZ EA_OUT 0 res W=0.42 L=52 mult=1 m=1\nXR_FB_A VOUT FB 0 res W=0.42 L=180 mult=1 m=1\n"
        out = rc.edit_rcz(body, 16)
        self.assertIn("L=832 ", out.splitlines()[0])
        self.assertIn("L=180 ", out.splitlines()[1])

    def test_grade_never_passes_missing_or_errored(self):
        self.assertFalse(
            rc.grade({"status": "error", "pm": 60.0, "gm": 20.0})["pm_pass"]
        )
        self.assertFalse(rc.grade({"status": "pass", "pm": None, "gm": 20.0})["valid"])
        self.assertFalse(
            rc.grade({"status": "pass", "pm": 60.0, "gm": None})["gm_pass"]
        )
        g = rc.grade({"status": "pass", "pm": 45.0, "gm": 10.0})
        self.assertTrue(g["pm_pass"] and g["gm_pass"])
        self.assertFalse(rc.grade({"status": "pass", "pm": 44.9, "gm": 9.9})["pm_pass"])


if __name__ == "__main__":
    unittest.main()
