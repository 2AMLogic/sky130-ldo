"""PDK-free unit tests for `gen-ldo-blocks.py`'s pure planners (issue #265).

Covers `plan_units`, `mos_voltage_flavor`, `order_devices`, `plan_placement`
and `assign_tracks`. A regression in any of them (an off-by-one unit count,
colliding tracks, a wrong voltage flavor, overlapping blocks) is DRC/LVS-silent
until a full `klt` + PDK run, so it is pinned here with plain `python3`.

Each family has a negative control: a doctored input that must fail.

Not covered here (needs `klt` / generated block reports): `generate_blocks`,
`route_composed_cell`, `build_compose_request`. `collect_terminals` is pure but
needs a fabricated block-report shape; it is exercised indirectly through the
synthetic `nets` dicts handed to `assign_tracks`.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN_DIR))


def _load_gen_module():
    spec = importlib.util.spec_from_file_location(
        "gen_ldo_blocks_placement", BIN_DIR / "gen-ldo-blocks.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _load_gen_module()


class PlanUnitsTest(unittest.TestCase):
    def test_exact_multiple_does_not_gain_a_unit(self) -> None:
        self.assertEqual(GEN.plan_units(GEN.MAX_UNIT_W_UM), (1, GEN.MAX_UNIT_W_UM))
        self.assertEqual(GEN.plan_units(2 * GEN.MAX_UNIT_W_UM)[0], 2)
        self.assertEqual(GEN.plan_units(2500.0), (25, 100.0))

    def test_just_over_the_cap_adds_a_unit(self) -> None:
        units, unit_w = GEN.plan_units(GEN.MAX_UNIT_W_UM + 0.01)
        self.assertEqual(units, 2)
        self.assertLessEqual(unit_w, GEN.MAX_UNIT_W_UM)

    def test_float_noise_below_the_guard_is_absorbed(self) -> None:
        # Within the 1e-9 guard of an exact multiple: still one unit.
        self.assertEqual(GEN.plan_units(GEN.MAX_UNIT_W_UM + 1e-11)[0], 1)

    def test_tiny_widths_are_one_unit(self) -> None:
        for w in (0.42, 1e-3, 1e-12):
            self.assertEqual(GEN.plan_units(w), (1, w))

    def test_total_width_is_conserved_and_units_capped(self) -> None:
        for w in (0.5, 99.9, 100.0, 100.5, 250.0, 333.3, 2500.0, 2500.7):
            units, unit_w = GEN.plan_units(w)
            self.assertAlmostEqual(units * unit_w, w, places=9)
            self.assertLessEqual(unit_w, GEN.MAX_UNIT_W_UM + 1e-9)
            self.assertEqual(units, max(1, math.ceil(w / GEN.MAX_UNIT_W_UM - 1e-9)))

    def test_negative_control_wrong_unit_count_breaks_conservation(self) -> None:
        units, unit_w = GEN.plan_units(250.0)
        self.assertEqual(units, 3)
        # An off-by-one count (floor instead of ceil) must be detectable.
        self.assertNotAlmostEqual((units - 1) * unit_w, 250.0, places=6)
        self.assertGreater(250.0 / (units - 1), GEN.MAX_UNIT_W_UM)


class MosVoltageFlavorTest(unittest.TestCase):
    def test_high_voltage_models_get_the_hvi_marker(self) -> None:
        for model in ("sky130_fd_pr__pfet_g5v0d10v5", "sky130_fd_pr__nfet_g5v0d10v5"):
            self.assertEqual(GEN.mos_voltage_flavor(model), "hvi")

    def test_every_recognised_mos_model_has_a_flavor(self) -> None:
        self.assertEqual(set(GEN.MOS_MODELS), set(GEN.MOS_VOLTAGE_FLAVORS))

    def test_core_01v8_models_are_not_silently_classified(self) -> None:
        # The design instantiates no 1.8 V core devices, so the table has no
        # row for them: they must hard-fail rather than default to a marker.
        for model in ("sky130_fd_pr__pfet_01v8", "sky130_fd_pr__nfet_01v8"):
            self.assertNotIn(model, GEN.MOS_MODELS)
            with self.assertRaises(GEN.GenError):
                GEN.mos_voltage_flavor(model)

    def test_negative_control_unknown_model_raises(self) -> None:
        for model in ("", "bogus", "pfet_g5v0d10v5"):
            with self.assertRaises(GEN.GenError):
                GEN.mos_voltage_flavor(model)


def _dev(name, kind, flavor, group, index, block_id=None):
    return {
        "name": name,
        "id": block_id or name.lower(),
        "kind": kind,
        "flavor": flavor,
        "group": group,
        "index": index,
    }


def _synthetic_devices():
    g = GEN.GROUP_ORDER
    # Deliberately shuffled: PMOS first, resistor in the middle.
    return [
        _dev("MP1", "mos", "pfet", g[0], 0),
        _dev("MN1", "mos", "nfet", g[0], 1),
        _dev("R1", "res", "high", g[0], 2),
        _dev("MN2", "mos", "nfet", g[-1], 3),
        _dev("MP2", "mos", "pfet", g[-1], 4),
    ]


def _reports(devices, width=10.0, height=20.0):
    return {
        d["id"]: {"bbox_um": {"x0": -1.0, "y0": -2.0, "x1": width - 1.0, "y1": height - 2.0}}
        for d in devices
    }


class OrderAndPlacementTest(unittest.TestCase):
    def test_order_is_res_then_nmos_then_pmos(self) -> None:
        ordered = GEN.order_devices(_synthetic_devices())
        kinds = []
        for d in ordered:
            kinds.append("res" if d["kind"] == "res" else d["flavor"])
        self.assertEqual(kinds, ["res", "nfet", "nfet", "pfet", "pfet"])

    def test_order_is_deterministic_under_input_permutation(self) -> None:
        devices = _synthetic_devices()
        expected = [d["name"] for d in GEN.order_devices(devices)]
        self.assertEqual(expected, [d["name"] for d in GEN.order_devices(devices[::-1])])
        self.assertEqual(expected, [d["name"] for d in GEN.order_devices(list(devices))])

    def test_negative_control_unsorted_input_is_not_row_order(self) -> None:
        devices = _synthetic_devices()
        self.assertNotEqual(
            [d["name"] for d in devices],
            [d["name"] for d in GEN.order_devices(devices)],
        )

    def test_placement_has_no_overlap_and_honours_gaps(self) -> None:
        devices = GEN.order_devices(_synthetic_devices())
        plan = GEN.plan_placement(devices, _reports(devices))
        self.assertEqual(plan["order"], [d["id"] for d in devices])
        boxes = [plan["placed_bboxes_um"][b] for b in plan["order"]]
        for left, right in zip(boxes, boxes[1:]):
            self.assertGreaterEqual(right["x0"] - left["x1"], GEN.BLOCK_GAP_UM - 1e-9)
        for box in boxes:
            self.assertEqual(box["y0"], 0.0)
        self.assertGreaterEqual(plan["row_width_um"], boxes[-1]["x1"])

    def test_placement_is_deterministic(self) -> None:
        a_devs = GEN.order_devices(_synthetic_devices())
        b_devs = GEN.order_devices(_synthetic_devices())
        a = GEN.plan_placement(a_devs, _reports(a_devs))
        b = GEN.plan_placement(b_devs, _reports(b_devs))
        self.assertEqual(a, b)

    def test_tap_slots_and_well_span(self) -> None:
        devices = GEN.order_devices(_synthetic_devices())
        plan = GEN.plan_placement(devices, _reports(devices))
        boxes = plan["placed_bboxes_um"]
        first_n = next(d for d in devices if d["flavor"] == "nfet" and d["kind"] == "mos")
        first_p = next(d for d in devices if d["flavor"] == "pfet")
        last_p = [d for d in devices if d["flavor"] == "pfet"][-1]
        self.assertLess(plan["subtap_x_um"], boxes[first_n["id"]]["x0"])
        self.assertLess(plan["nwtap_x_um"], boxes[first_p["id"]]["x0"])
        self.assertLess(plan["nwell_x0_um"], plan["nwtap_x_um"])
        self.assertGreater(plan["nwell_x1_um"], boxes[last_p["id"]]["x1"])

    def test_negative_control_no_pmos_span_raises(self) -> None:
        devices = [d for d in GEN.order_devices(_synthetic_devices()) if d["flavor"] != "pfet"]
        with self.assertRaises(GEN.GenError):
            GEN.plan_placement(devices, _reports(devices))

    def test_negative_control_missing_report_raises(self) -> None:
        devices = GEN.order_devices(_synthetic_devices())
        reports = _reports(devices)
        del reports[devices[0]["id"]]
        with self.assertRaises(KeyError):
            GEN.plan_placement(devices, reports)


def _term(x):
    return {"x_um": x}


class AssignTracksTest(unittest.TestCase):
    def test_tracks_ordered_by_leftmost_terminal_and_pitch_spaced(self) -> None:
        nets = {
            "c": [_term(30.0)],
            "a": [_term(50.0), _term(5.0)],
            "b": [_term(12.0), _term(40.0)],
        }
        tracks = GEN.assign_tracks(nets, {}, {})
        self.assertEqual(sorted(tracks, key=tracks.get, reverse=True), ["a", "b", "c"])
        self.assertAlmostEqual(tracks["a"], GEN.CHANNEL_TOP_UM)
        values = sorted(tracks.values(), reverse=True)
        self.assertEqual(len(set(values)), len(values))
        for hi, lo in zip(values, values[1:]):
            self.assertAlmostEqual(hi - lo, GEN.TRACK_PITCH_UM)

    def test_ties_break_by_net_name(self) -> None:
        nets = {"zz": [_term(1.0)], "aa": [_term(1.0)]}
        tracks = GEN.assign_tracks(nets, {}, {})
        self.assertGreater(tracks["aa"], tracks["zz"])

    def test_power_nets_are_excluded_and_do_not_consume_a_track(self) -> None:
        nets = {"vin": [_term(0.0)], "sig": [_term(10.0)]}
        tracks = GEN.assign_tracks(nets, {}, {"vin": {}})
        self.assertNotIn("vin", tracks)
        self.assertEqual(tracks, {"sig": GEN.CHANNEL_TOP_UM})

    def test_negative_control_power_net_not_excluded_if_unlisted(self) -> None:
        nets = {"vin": [_term(0.0)], "sig": [_term(10.0)]}
        tracks = GEN.assign_tracks(nets, {}, {})
        self.assertIn("vin", tracks)
        self.assertNotEqual(tracks["sig"], GEN.CHANNEL_TOP_UM)

    def test_body_net_on_a_routed_or_power_net_is_fine(self) -> None:
        nets = {"gnd": [_term(0.0)], "sig": [_term(1.0)]}
        GEN.assign_tracks(nets, {"MN1": "sig"}, {})
        GEN.assign_tracks(nets, {"MN1": "gnd"}, {"gnd": {}})

    def test_negative_control_unrouted_body_net_raises(self) -> None:
        nets = {"sig": [_term(1.0)]}
        with self.assertRaises(GEN.GenError):
            GEN.assign_tracks(nets, {"MN1": "ghost"}, {})


if __name__ == "__main__":
    unittest.main()
