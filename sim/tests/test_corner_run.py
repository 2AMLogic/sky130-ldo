"""Unit coverage for sim/bin/corner-run.py's pure helper functions.

PDK-free by design (no ngspice/xschem/volare required) so this runs on every
`npm run check:ci` invocation, including in CI where the sky130 PDK is not
installed -- see sim/selftest.sh stage 1/3.

corner-run.py is loaded by file path (not `import corner_run`) because the
CLI convention keeps the hyphenated `corner-run.py` filename, matching the
sibling sky130-bandgap repo's harness.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR / "bin"))  # corner-run.py imports _record_common (issue #46)
_spec = importlib.util.spec_from_file_location("corner_run", SIM_DIR / "bin" / "corner-run.py")
corner_run = importlib.util.module_from_spec(_spec)
sys.modules["corner_run"] = corner_run
_spec.loader.exec_module(corner_run)


class TestCornerId(unittest.TestCase):
    def test_id_format(self):
        c = corner_run.Corner(process="tt", temp_c=27.0, supply_v=1.8)
        self.assertEqual(c.id, "tt_27c_1.80v")

    def test_id_negative_temp(self):
        c = corner_run.Corner(process="ss", temp_c=-40.0, supply_v=1.62)
        self.assertEqual(c.id, "ss_-40c_1.62v")

    def test_id_non_integer_temp(self):
        c = corner_run.Corner(process="ff", temp_c=27.5, supply_v=1.98)
        self.assertEqual(c.id, "ff_27.5c_1.98v")


class TestFmtTemp(unittest.TestCase):
    def test_integer_temp_has_no_trailing_zero(self):
        self.assertEqual(corner_run.fmt_temp(125.0), "125")

    def test_negative_temp(self):
        self.assertEqual(corner_run.fmt_temp(-40.0), "-40")


class TestUniqueInOrder(unittest.TestCase):
    def test_dedupes_preserving_first_occurrence_order(self):
        self.assertEqual(
            corner_run.unique_in_order(["tt", "ss", "tt", "ff", "ss"]),
            ["tt", "ss", "ff"],
        )

    def test_empty(self):
        self.assertEqual(corner_run.unique_in_order([]), [])


class TestParseMeasurements(unittest.TestCase):
    def test_parses_meas_lines(self):
        log = "\n".join(
            [
                "some ngspice banner text",
                "meas_vgs = 6.306570e-01",
                "meas_isup = 1.169340e-06",
                "trailing noise",
            ]
        )
        self.assertEqual(
            corner_run.parse_measurements(log),
            {"vgs": 0.630657, "isup": 1.16934e-06},
        )

    def test_ignores_non_measurement_lines(self):
        self.assertEqual(corner_run.parse_measurements("no measurements here"), {})

    def test_handles_negative_values(self):
        log = "meas_delta = -3.5e-02"
        self.assertEqual(corner_run.parse_measurements(log), {"delta": -0.035})


class TestSignalName(unittest.TestCase):
    def test_known_signal(self):
        self.assertEqual(corner_run.signal_name(9), "SIGKILL")

    def test_unknown_signal_number(self):
        self.assertEqual(corner_run.signal_name(999), "signal 999")


class TestExitNote(unittest.TestCase):
    def test_timeout_note(self):
        note = corner_run.exit_note(-1, timed_out=True, killed_by_signal=None)
        self.assertIn("TIMEOUT", note)

    def test_signal_note(self):
        note = corner_run.exit_note(-9, timed_out=False, killed_by_signal=9)
        self.assertIn("SIGKILL", note)
        self.assertIn("OUTSIDE the harness", note)

    def test_clean_exit_has_no_note(self):
        self.assertEqual(corner_run.exit_note(0, timed_out=False, killed_by_signal=None), "")


class TestCsvHelpers(unittest.TestCase):
    def test_csv_list_strips_whitespace(self):
        self.assertEqual(corner_run.csv_list(" tt, ss ,ff"), ["tt", "ss", "ff"])

    def test_csv_floats(self):
        self.assertEqual(corner_run.csv_floats("1.62,1.8,1.98"), [1.62, 1.8, 1.98])


if __name__ == "__main__":
    unittest.main()
