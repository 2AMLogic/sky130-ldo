"""PDK-free unit coverage for the post-layout PEX bench helpers (issue #296).

Covers the pure helpers in sim/pex-post-layout/bin/gen-pex-testbench.py and
render-pex-record.py. Both files are hyphenated, so they are loaded by path
(same pattern as test_corner_run.py).
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
PEX_BIN = SIM_DIR / "pex-post-layout" / "bin"
sys.path.insert(0, str(SIM_DIR / "bin"))  # render-pex-record imports _record_common


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PEX_BIN / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


gen = _load("gen_pex_testbench", "gen-pex-testbench.py")
render = _load("render_pex_record", "render-pex-record.py")


class ParseSubcktPinsTests(unittest.TestCase):
    def test_single_line(self):
        text = "* c\n.SUBCKT ldo_core VIN VOUT VREF EN\nR1 a b 1\n.ends\n"
        self.assertEqual(gen.parse_subckt_pins(text, "ldo_core"), ["VIN", "VOUT", "VREF", "EN"])

    def test_continuation_lines_preserve_order(self):
        text = ".SUBCKT ldo_core A B\n+ C D\n+ E\nR1 A B 1\n.ends\n"
        self.assertEqual(gen.parse_subckt_pins(text, "ldo_core"), ["A", "B", "C", "D", "E"])

    def test_continuation_stops_at_non_continuation(self):
        text = ".SUBCKT ldo_core A\n+ B\nR1 A B 1\n+ NOTPIN\n"
        self.assertEqual(gen.parse_subckt_pins(text, "ldo_core"), ["A", "B"])

    def test_case_insensitive_name_and_directive(self):
        self.assertEqual(gen.parse_subckt_pins(".subckt LDO_CORE x y\n", "ldo_core"), ["x", "y"])

    def test_selects_named_subckt(self):
        text = ".SUBCKT other P Q\n.ends\n.SUBCKT ldo_core A B\n.ends\n"
        self.assertEqual(gen.parse_subckt_pins(text, "ldo_core"), ["A", "B"])

    def test_missing_subckt_exits(self):
        with self.assertRaises(SystemExit) as ctx:
            gen.parse_subckt_pins(".SUBCKT other A B\n", "ldo_core")
        self.assertIn("no .SUBCKT ldo_core", str(ctx.exception))


class WrapPinsTests(unittest.TestCase):
    PINS = [f"NET_NUMBER_{i:02d}" for i in range(28)]

    def test_short_list_single_line(self):
        self.assertEqual(gen.wrap_pins(["A", "B"]), ".SUBCKT ldo_core A B")

    def test_lines_within_width_and_no_token_split(self):
        out = gen.wrap_pins(self.PINS)
        lines = out.splitlines()
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(len(line), 78)
        for line in lines[1:]:
            self.assertTrue(line.startswith("+ "))
        tokens = out.replace("+", " ").split()[2:]  # drop ".SUBCKT ldo_core"
        self.assertEqual(tokens, self.PINS)

    def test_width_boundary(self):
        # ".SUBCKT ldo_core" is 16 chars; " " + 8-char pin per addition.
        fits = gen.wrap_pins(["P0000001", "P0000002"], width=16 + 9 * 2)
        self.assertEqual(len(fits.splitlines()), 1)
        wraps = gen.wrap_pins(["P0000001", "P0000002"], width=16 + 9 * 2 - 1)
        self.assertEqual(wraps.splitlines(), [".SUBCKT ldo_core P0000001", "+ P0000002"])

    def test_oversize_pin_never_leaves_empty_header(self):
        out = gen.wrap_pins(["X" * 100, "Y"])
        self.assertEqual(out.splitlines()[0], ".SUBCKT ldo_core " + "X" * 100)

    def test_round_trips_through_parse(self):
        self.assertEqual(gen.parse_subckt_pins(gen.wrap_pins(self.PINS), "ldo_core"), self.PINS)

    def test_empty_pin_list(self):
        self.assertEqual(gen.wrap_pins([]), ".SUBCKT ldo_core")


class SchematicDeviceBodyTests(unittest.TestCase):
    NETLIST = (
        "** sch_path: x.sch\n"
        "**.subckt ldo_3v3in_1v8out VIN VOUT\n"
        "*.ipin VIN\n"
        "XM1 a b c d sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=10\n"
        "R1 a b 1k\n"
        "**.ends\n"
        ".end\n"
    )

    def test_strips_end_card_only(self):
        body = gen.schematic_device_body(self.NETLIST)
        self.assertNotIn(".end", [l.strip().lower() for l in body.splitlines()])
        for keep in ("**.subckt ldo_3v3in_1v8out VIN VOUT", "*.ipin VIN", "**.ends",
                     "XM1 a b c d sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=10", "R1 a b 1k"):
            self.assertIn(keep, body.splitlines())

    def test_end_match_is_case_and_whitespace_insensitive(self):
        self.assertEqual(gen.schematic_device_body("R1 a b 1\n  .END  \n"), "R1 a b 1")

    def test_does_not_strip_other_dot_end_cards(self):
        body = gen.schematic_device_body(".ends\n.endc\n.end\n")
        self.assertEqual(body.splitlines(), [".ends", ".endc"])

    def test_no_trailing_newline_added(self):
        self.assertFalse(gen.schematic_device_body("R1 a b 1\n.end\n").endswith("\n"))


class SummarizeDeltaTests(unittest.TestCase):
    def test_none_and_empty_inputs(self):
        self.assertIsNone(render.summarize_delta(None, None))
        self.assertIsNone(render.summarize_delta({}, {}))
        self.assertIsNone(render.summarize_delta({"delta": []}, None))
        self.assertIsNone(render.summarize_delta({"delta": None}, None))

    def test_rows_missing_name_or_value_skipped(self):
        resp = {"delta": [
            {"spec_row": None, "delta_pct": 1.0, "corner_id": "a"},
            {"spec_row": "vout", "delta_pct": None, "corner_id": "b"},
            {"delta_pct": 2.0, "corner_id": "c"},
        ]}
        self.assertIsNone(render.summarize_delta(resp, None))

    def test_absolute_aggregation_and_worst_corner(self):
        resp = {"delta": [
            {"spec_row": "vout", "delta_pct": -3.0, "corner_id": "ss"},
            {"spec_row": "vout", "delta_pct": 1.0, "corner_id": "tt"},
            {"spec_row": "vout", "delta_pct": 2.0, "corner_id": "ff"},
        ]}
        s = render.summarize_delta(resp, None)["vout"]
        self.assertEqual(s["row_count"], 3)
        self.assertEqual(s["abs_delta_pct_min"], 1.0)
        self.assertEqual(s["abs_delta_pct_median"], 2.0)
        self.assertEqual(s["abs_delta_pct_max"], 3.0)
        self.assertEqual(s["worst_corner"], "ss")  # sign ignored: |-3| is largest
        self.assertFalse(s["limits_declared"])

    def test_rounding_and_per_row_separation(self):
        resp = {"delta": [
            {"spec_row": "a", "delta_pct": 0.12349, "corner_id": "c1"},
            {"spec_row": "b", "delta_pct": 5.0, "corner_id": "c2"},
        ]}
        s = render.summarize_delta(resp, None)
        self.assertEqual(set(s), {"a", "b"})
        self.assertEqual(s["a"]["abs_delta_pct_max"], 0.123)
        self.assertEqual(s["b"]["worst_corner"], "c2")

    def test_limits_declared_flag(self):
        resp = {"delta": [
            {"spec_row": "a", "delta_pct": 1.0, "corner_id": "c"},
            {"spec_row": "b", "delta_pct": 1.0, "corner_id": "c"},
            {"spec_row": "d", "delta_pct": 1.0, "corner_id": "c"},
            {"spec_row": "e", "delta_pct": 1.0, "corner_id": "c"},
        ]}
        req = {"measurements": [
            {"name": "a", "limits": {"max": 1}},
            {"name": "b", "tolerance_pct": 2},
            {"name": "d", "limit": 3},
            {"name": "e"},
        ]}
        s = render.summarize_delta(resp, req)
        self.assertEqual({k: v["limits_declared"] for k, v in s.items()},
                         {"a": True, "b": True, "d": True, "e": False})

    def test_null_measurements_in_request(self):
        resp = {"delta": [{"spec_row": "a", "delta_pct": 1.0, "corner_id": "c"}]}
        self.assertFalse(render.summarize_delta(resp, {"measurements": None})["a"]["limits_declared"])


if __name__ == "__main__":
    unittest.main()
