"""Unit tests for the shared X-card parser and its two callers (issue #252).

Standard library only; the reference generator's `klt` deck lookup is stubbed.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN_DIR))

from _netlist_common import XCard, _merge_continuations, parse_x_card  # noqa: E402


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLOCKS = _load("gen_ldo_blocks_t", "gen-ldo-blocks.py")
REF = _load("gen_ldo_ref_t", "gen-ldo-reference-netlist.py")
REF.resistor_models = lambda deck: {
    "res_high_po": (1000.0, 1.5),
    "res_xhigh_po": (2000.0, 2.5),
}

NMOS = "sky130_fd_pr__nfet_g5v0d10v5"
PMOS = "sky130_fd_pr__pfet_g5v0d10v5"
RHI = "sky130_fd_pr__res_high_po"
RXHI = "sky130_fd_pr__res_xhigh_po"
MODELS = {NMOS, PMOS, RHI, RXHI}

NETLIST = f"""* header
XM_A d g s b {NMOS}
+ L=0.5 W=2 mult=4
XM_B d2 g2 s2 b2 {PMOS} L=1 W=3
XR_1 a b bulk {RHI} L=10 W=0.69
XR_2 a2 b2 bulk2 {RXHI} L=5 W=0.69 extra=x=y
XM_A d3 g3 s3 b3 {NMOS} L=0.5 W=1
Xother a b c unknown_model W=1
C1 a b 1p
.end
"""


class ParseXCardTests(unittest.TestCase):
    def test_mos_card(self):
        card = parse_x_card(f"XM_A d g s b {NMOS} L=0.5 W=2 mult=4", MODELS)
        self.assertEqual(
            card,
            XCard("M_A", NMOS, ["d", "g", "s", "b"],
                  {"L": "0.5", "W": "2", "mult": "4"}),
        )

    def test_resistor_card(self):
        card = parse_x_card(f"XR_1 a b bulk {RHI} L=10 W=0.69", MODELS)
        self.assertEqual(card.model, RHI)
        self.assertEqual(card.nets, ["a", "b", "bulk"])
        self.assertEqual(card.params, {"L": "10", "W": "0.69"})

    def test_continuation_after_merge(self):
        lines = _merge_continuations([f"XM_A d g s b {NMOS}", "+ L=0.5 W=2"])
        card = parse_x_card(lines[0], MODELS)
        self.assertEqual(card.params, {"L": "0.5", "W": "2"})

    def test_unknown_model_is_explicit(self):
        card = parse_x_card("Xfoo a b c mystery W=1", MODELS)
        self.assertEqual(card, XCard("foo", None, [], {}))

    def test_model_must_be_in_caller_set(self):
        self.assertIsNone(parse_x_card(f"XM a b c d {NMOS} W=1", {PMOS}).model)

    def test_equals_in_value_and_raw_strings(self):
        card = parse_x_card(f"XM a b c d {NMOS} expr=a=b W=1e-6 flag", MODELS)
        self.assertEqual(card.params, {"expr": "a=b", "W": "1e-6"})

    def test_non_x_cards(self):
        for line in ("C1 a b 1p", "R1 a b 1k", "M1 d g s b nmos", "* x", "", "X"):
            self.assertIsNone(parse_x_card(line, MODELS))


class CallerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "n.spice"
        self.path.write_text(NETLIST)

    def test_layout_devices(self):
        devices, skipped = BLOCKS.parse_netlist(self.path)
        self.assertEqual([d["id"] for d in devices],
                         ["M_A", "M_B", "R_1", "R_2", "M_A__2"])
        self.assertEqual(devices[0]["w_total_um"], 8.0)
        self.assertEqual(devices[0]["nets"]["B"], "b")
        self.assertEqual(devices[2]["kind"], "res")
        self.assertEqual(devices[2]["length_um"], 10.0)
        self.assertEqual(skipped, ["Xother a b c unknown_model W=1", "C1 a b 1p"])

    def test_layout_net_count_errors(self):
        self.path.write_text(f"XM_A d g s {NMOS} L=1 W=1\n")
        with self.assertRaisesRegex(BLOCKS.GenError, "expected 4 MOS nets"):
            BLOCKS.parse_netlist(self.path)
        self.path.write_text(f"XR_1 a b {RHI} L=1 W=1\n")
        with self.assertRaisesRegex(BLOCKS.GenError, "expected 3 resistor nets"):
            BLOCKS.parse_netlist(self.path)

    def test_reference_text(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            text = REF.translate(self.path, "T", ["A"])
        self.assertIn("\nM_A d g s b nfet L=0.5U W=8U", text)
        self.assertIn("\nR_1 a b 14494.253623 res_high_po L=10U W=0.69U", text)
        self.assertIn("\nR_2 a2 b2 14495.253623 res_xhigh_po", text)
        # non-X cards are ignored silently; unknown X cards are reported
        self.assertIn("Xother", err.getvalue())
        self.assertNotIn("C1", err.getvalue())
        self.assertNotIn("C1", text)


if __name__ == "__main__":
    unittest.main()
