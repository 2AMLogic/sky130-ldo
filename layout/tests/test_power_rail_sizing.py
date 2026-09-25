"""Unit tests for the load-current conductor sizing `gen-ldo-blocks.py` does
(issue #154).

These cover the parts of the power-rail path that are pure arithmetic or pure
schematic bookkeeping -- the parts a DRC/LVS run would *not* catch, because a
rail sized against the wrong current, or drawn on the wrong net, is DRC-clean
and LVS-matching either way. The drawn geometry itself is checked by
`layout/bin/run-ldo-layout-flow.sh`'s own `klt drc` record, not from here.

Run under the repo's plain `python3` (no `klt`): everything exercised here is
either standard library or, for the deck-reading helpers, skipped when
`klayout_tools` is not importable.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parents[1] / "bin"
REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "spec" / "target-spec.md"

sys.path.insert(0, str(BIN_DIR))


def _load_gen_module():
    spec = importlib.util.spec_from_file_location(
        "gen_ldo_blocks", BIN_DIR / "gen-ldo-blocks.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _load_gen_module()

from _spec_constants import SpecError, read_spec_constants  # noqa: E402


class SpecConstantsTest(unittest.TestCase):
    def test_reads_the_ratified_rows(self) -> None:
        constants = read_spec_constants(SPEC_PATH)
        # Not asserted as literals for their own sake: these are the numbers
        # every drawn power conductor's width is computed from, so a spec edit
        # that moves them should surface here rather than silently resize the
        # layout.
        self.assertEqual(constants.full_load_a, 0.05)
        self.assertEqual(constants.dropout_target_v, 0.3)
        self.assertEqual(constants.dropout_at_a, constants.full_load_a)

    def test_rejects_a_spec_whose_two_rows_disagree(self) -> None:
        text = SPEC_PATH.read_text().replace(
            "| Dropout @ 50 mA |", "| Dropout @ 25 mA |", 1
        )
        with tempfile.TemporaryDirectory() as tmp:
            doctored = Path(tmp) / "target-spec.md"
            doctored.write_text(text)
            with self.assertRaises(SpecError):
                read_spec_constants(doctored)

    def test_rejects_a_spec_with_no_load_row(self) -> None:
        text = SPEC_PATH.read_text().replace("| Load |", "| Loud |", 1)
        with tempfile.TemporaryDirectory() as tmp:
            doctored = Path(tmp) / "target-spec.md"
            doctored.write_text(text)
            with self.assertRaises(SpecError):
                read_spec_constants(doctored)


class PowerNetIdentificationTest(unittest.TestCase):
    @staticmethod
    def _mos(name: str, w_total: float, nets: dict[str, str]) -> dict:
        return {"kind": "mos", "id": name, "name": name, "w_total_um": w_total,
                "nets": nets}

    def test_picks_the_widest_devices_drain_and_source(self) -> None:
        devices = [
            self._mos("M_PASS", 5000.0,
                      {"D": "VOUT", "G": "EA_OUT", "S": "VIN", "B": "VIN"}),
            self._mos("M_SENSE", 50.0,
                      {"D": "CL_SNS", "G": "EA_OUT", "S": "VIN", "B": "VIN"}),
            {"kind": "res", "id": "R_FB_A", "name": "R_FB_A",
             "nets": {"A": "VOUT", "B": "FB", "W": "0"}},
        ]
        power = GEN.identify_power_nets(devices)
        self.assertEqual(set(power), {"VOUT", "VIN"})
        self.assertEqual(power["VOUT"]["terminal"], "D")
        self.assertEqual(power["VIN"]["terminal"], "S")
        self.assertEqual(power["VOUT"]["device"], "M_PASS")

    def test_refuses_an_ambiguous_pass_device(self) -> None:
        devices = [
            self._mos("M_A", 100.0, {"D": "N1", "G": "G1", "S": "VIN", "B": "VIN"}),
            self._mos("M_B", 90.0, {"D": "N2", "G": "G2", "S": "VIN", "B": "VIN"}),
        ]
        with self.assertRaises(GEN.GenError):
            GEN.identify_power_nets(devices)


class RailSizingTest(unittest.TestCase):
    def test_width_meets_the_declared_ir_budget_exactly_when_unclamped(self) -> None:
        sizing = GEN.power_rail_width_um(
            span_um=100.0,
            current_a=0.05,
            budget_v=0.0075,
            rho_ohm_sq=0.0625,
            max_w_um=1000.0,
            min_w_um=0.30,
        )
        self.assertFalse(sizing["width_clamped"])
        self.assertAlmostEqual(sizing["ir_drop_v"], 0.0075, places=9)
        self.assertAlmostEqual(sizing["resistance_ohm"], 0.15, places=9)
        # W = rho * L / R_budget
        self.assertAlmostEqual(sizing["width_um"], 0.0625 * 100.0 / 0.15, places=9)

    def test_doubling_the_current_doubles_the_width(self) -> None:
        base = GEN.power_rail_width_um(100.0, 0.05, 0.0075, 0.0625, 1e6, 0.30)
        twice = GEN.power_rail_width_um(100.0, 0.10, 0.0075, 0.0625, 1e6, 0.30)
        self.assertAlmostEqual(twice["width_um"], 2.0 * base["width_um"], places=9)

    def test_clamping_is_reported_not_silent(self) -> None:
        sizing = GEN.power_rail_width_um(
            span_um=2000.0,
            current_a=0.05,
            budget_v=0.0075,
            rho_ohm_sq=0.0625,
            max_w_um=10.0,
            min_w_um=0.30,
        )
        self.assertTrue(sizing["width_clamped"])
        self.assertEqual(sizing["width_um"], 10.0)
        self.assertGreater(sizing["required_width_um"], sizing["width_um"])
        self.assertGreater(sizing["ir_drop_v"], sizing["ir_budget_v"])

    def test_a_signal_scale_span_never_goes_below_the_minimum(self) -> None:
        sizing = GEN.power_rail_width_um(0.5, 0.05, 0.0075, 0.0625, 1e6, 0.30)
        self.assertEqual(sizing["width_um"], 0.30)

    def test_parallel_sheet_rho_is_the_parallel_combination(self) -> None:
        self.assertAlmostEqual(
            GEN.parallel_sheet_rho([12.8, 0.125, 0.125, 0.047], (1, 2)),
            0.0625,
            places=9,
        )
        self.assertAlmostEqual(
            GEN.parallel_sheet_rho([12.8, 0.125, 0.125, 0.047], (2, 3)),
            1.0 / (1.0 / 0.125 + 1.0 / 0.047),
            places=9,
        )

    def test_missing_sheet_rho_is_an_error_not_a_zero(self) -> None:
        with self.assertRaises(GEN.GenError):
            GEN.parallel_sheet_rho([12.8, 0.125, None, 0.047], (2, 3))


class DeckConstantsTest(unittest.TestCase):
    """The deck readers, when `klt` happens to be importable."""

    def setUp(self) -> None:
        try:
            import klayout_tools.decks  # noqa: F401
        except ImportError:
            self.skipTest("klayout_tools not importable (run under layout/.venv)")

    def test_sheet_rho_and_min_widths_come_from_the_deck(self) -> None:
        rho = GEN.rail_sheet_rho_ohm_sq("sky130")
        self.assertGreater(rho[0], rho[1])  # li1 is far more resistive than met1
        widths = GEN.metal_min_rule_um("sky130", "width")
        spaces = GEN.metal_min_rule_um("sky130", "space")
        for level in (1, 2, 3):
            self.assertIn(level, widths)
            self.assertIn(level, spaces)
        # met3's minimum width is coarser than met1's -- the reason the rail
        # tail cannot just reuse the signal-trunk width on every level.
        self.assertGreater(widths[3], widths[1])


if __name__ == "__main__":
    unittest.main()
