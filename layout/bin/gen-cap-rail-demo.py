#!/usr/bin/env python3
"""Draw the bounded MiM-capacitor + supply-rail overlay demonstrator (issue #254).

NOT the LDO core and NOT a full-core layout: this draws, inside the planned
core outline, only the geometry whose feasibility issue #254 asks about --

* the schematic's four capacitors (read from its own xschem netlist), each a
  parallel array of *stacked* MiM units (sky130 `cap_mim_m3_1` on met3/capm
  under `cap_mim_m3_2` on met4/capm2, same footprint), sized so the deck's
  extraction law reproduces the schematic value;
* the two load-current rails over the pass-device column, at the widths the
  unchanged #154 sizing rule computes from the ratified Load and Dropout rows,
  on the metal levels of the proposed assignment (see
  `layout/cap-rail-demo/README.md`), plus the two rails' sense tails and the
  VIN risers that must cross the VOUT rail;
* (not drawn, measured instead) the measured layout's own device-row
  routing under each block, as an area for the coupling estimate.

MOS devices, resistors and signal routing are not drawn (their footprint is
the measured one; see the README for every assumption). Positions of the rails
and risers are mapped from the measured layout record's own floorplan.json and
GDS, not restated.

Run under the pinned `klt`'s Python (needs `klayout.db` and
`klayout_tools.decks`); see `run-cap-rail-demo-flow.sh`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

BIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN_DIR))

import _cap_rail_plan as plan  # noqa: E402
from _spec_constants import read_spec_constants  # noqa: E402


def _load_gen_blocks():
    spec = importlib.util.spec_from_file_location("gen_ldo_blocks", BIN_DIR / "gen-ldo-blocks.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _load_gen_blocks()

# --- sky130 GDS layers ------------------------------------------------------
L = {
    "met1": (68, 20), "via1": (68, 44), "met2": (69, 20), "via2": (69, 44),
    "met3": (70, 20), "via3": (70, 44), "met4": (71, 20), "via4": (71, 44),
    "met5": (72, 20), "capm": (89, 44), "capm2": (97, 44),
    "met1_label": (68, 5), "met2_label": (69, 5), "boundary": (235, 4),
}

#: via1 is a fixed-size cut on sky130 (via.1a / via.1a_b: exactly 0.15 um).
VIA1 = 0.15
#: met1/met2 landing pads at a riser transition. 0.40 um, not the measured
#: layout's 0.30 um: 0.30 um leaves 0.05-0.075 um of enclosure, below the
#: official two-adjacent-edge enclosure rules (m2.5 / via2.5, 0.085 um) that
#: the curated klt deck documents as not modelled.
PAD = 0.40
VIA2 = 0.20
VIA3 = 0.20
VIA4 = 0.80
#: Via pitch inside a unit top plate. The PDK model's contact term assumes a
#: dense array; 2.0 / 3.0 um keeps the shape count modest while still putting
#: hundreds of vias on every 25-30 um plate.
VIA3_PITCH = 2.0
VIA4_PITCH = 3.0
VIA3_INSET = 0.5  # >= capm.4's 0.14
VIA4_INSET = 0.6  # >= cap2m.4's 0.2
#: Keep-out margin around the met3 VIN rail column (capm.11 0.5, capm.2b_a 1.2).
ZONE_KEEPOUT_UM = 2.0

#: Capacitor block plan: array shape, which net takes the outer plates, where
#: the block's lower-left corner goes (core coordinates), and where along the
#: block's height the inner-plate tap sits. The array shapes keep every unit
#: inside the PDK's 2..30 um range; positions put C_COMP over the MOS domain,
#: channel and resistor-bank column, C_SS over the pass device, and the two
#: VIN-referenced 1 pF capacitors over the VIN sense tail (whose met2 their
#: outer plates drop straight onto).
CAP_PLAN: dict[str, dict[str, Any]] = {
    "C_COMP": {"rows": 5, "cols": 9, "outer": "VOUT", "anchor": ("left", "bottom"), "tap_frac": 0.5},
    "C_SS": {"rows": 2, "cols": 2, "outer": "0", "anchor": ("right", "bottom"), "tap_frac": 0.5},
    "C_CL": {"rows": 1, "cols": 1, "outer": "VIN", "anchor": ("vin_tail", 0), "tap_frac": 0.85},
    "C_TS": {"rows": 1, "cols": 1, "outer": "VIN", "anchor": ("vin_tail", 1), "tap_frac": 0.85},
}
#: Gap between capacitor blocks and from the core edge.
BLOCK_GAP_UM = 3.0
EDGE_UM = 1.0


class Drawer:
    def __init__(self, cell_name: str) -> None:
        import klayout.db as db

        self.db = db
        self.layout = db.Layout()
        self.layout.dbu = 0.001
        self.cell = self.layout.create_cell(cell_name)
        self.idx = {k: self.layout.layer(*v) for k, v in L.items()}
        self.counts: dict[str, int] = {}

    def box(self, layer: str, x0: float, y0: float, x1: float, y1: float) -> None:
        x0, x1 = sorted((plan.snap(x0), plan.snap(x1)))
        y0, y1 = sorted((plan.snap(y0), plan.snap(y1)))
        if x1 - x0 <= 0 or y1 - y0 <= 0:
            raise ValueError(f"degenerate {layer} box {x0},{y0},{x1},{y1}")
        self.cell.shapes(self.idx[layer]).insert(self.db.DBox(x0, y0, x1, y1))
        self.counts[layer] = self.counts.get(layer, 0) + 1

    def square(self, layer: str, cx: float, cy: float, side: float) -> None:
        x0 = plan.snap(cx - side / 2.0)
        y0 = plan.snap(cy - side / 2.0)
        self.box(layer, x0, y0, x0 + side, y0 + side)

    def via_grid(self, layer: str, size: float, pitch: float, x0: float, y0: float, x1: float, y1: float) -> int:
        """Centred grid of `size` vias inside [x0,x1]x[y0,y1] (inclusive of size)."""
        nx = int((x1 - x0 - size) // pitch) + 1
        ny = int((y1 - y0 - size) // pitch) + 1
        if nx < 1 or ny < 1:
            return 0
        # Snap the origin once and step by an on-grid pitch, so every via is
        # exactly `size` wide (snapping both edges independently can widen a
        # via by one grid step -- a via3.1_b / via4.1_a violation).
        sx = plan.snap(x0 + ((x1 - x0) - ((nx - 1) * pitch + size)) / 2.0)
        sy = plan.snap(y0 + ((y1 - y0) - ((ny - 1) * pitch + size)) / 2.0)
        for i in range(nx):
            for j in range(ny):
                x = plan.snap(sx + i * pitch)
                y = plan.snap(sy + j * pitch)
                self.box(layer, x, y, x + size, y + size)
        return nx * ny

    def label(self, layer: str, text: str, x: float, y: float) -> None:
        self.cell.shapes(self.idx[layer]).insert(self.db.DText(text, self.db.DTrans(plan.snap(x), plan.snap(y))))

    def write(self, path: Path) -> None:
        self.layout.write(str(path))


def measured_riser_x(gds: Path, transition_y: float) -> list[float]:
    """x of every via2 the measured layout drew at the power-riser transition
    (one per VIN riser), read from the stream itself."""
    import klayout.db as db

    ly = db.Layout()
    ly.read(str(gds))
    top = ly.top_cell()
    region = db.Region(top.begin_shapes_rec(ly.layer(*L["via2"])))
    xs = []
    for poly in region.each():
        c = poly.bbox().center()
        if abs(c.y * ly.dbu - transition_y) < 0.01:
            xs.append(round(c.x * ly.dbu, 3))
    return sorted(xs)


def measured_routing_under(gds: Path, blocks: list[dict[str, Any]], x_off: float, y_off: float,
                           exclude_y_from: float, x_from: float) -> dict[str, dict[str, float]]:
    """Area of the measured layout's li1/met1/met2 under each block (core
    coordinates), counting only geometry below the power-riser transition
    (the device row, its gate risers and the channel) and right of `x_from`
    (the MOS domain: the measured resistor span is replaced by the folded
    banks in the plan, so its straight-resistor geometry is not counted). The
    rail region above the transition is drawn in this demonstrator itself and
    measured by extraction."""
    import klayout.db as db

    ly = db.Layout()
    ly.read(str(gds))
    top = ly.top_cell()
    dbu = ly.dbu
    clip = db.Region(db.Box(int(round(x_from / dbu)), -10**9, 10**9, int(round(exclude_y_from / dbu))))
    shift = db.Trans(db.Vector(int(round(-x_off / dbu)), int(round(y_off / dbu))))
    layers = {"li1": (67, 20), "met1": (68, 20), "met2": (69, 20)}
    regions = {k: (db.Region(top.begin_shapes_rec(ly.layer(*v))).merged() & clip).transformed(shift)
               for k, v in layers.items()}
    out: dict[str, dict[str, float]] = {}
    for b in blocks:
        box = db.Region(db.Box(int(round(b["x0_um"] / dbu)), int(round(b["y0_um"] / dbu)),
                               int(round(b["x1_um"] / dbu)), int(round(b["y1_um"] / dbu))))
        out[b["name"]] = {k: round((r & box).area() * dbu * dbu, 3) for k, r in regions.items()}
    return out


def overlap_coefficients(deck_name: str) -> dict[str, float]:
    """Adjacent-level overlap coefficients (F/um^2) from klt's parasitics deck."""
    from klayout_tools.decks import get_parasitics_deck

    names = ["li1", "met1", "met2", "met3", "met4", "met5"]
    deck = get_parasitics_deck(deck_name)
    return {f"{names[i]}-{names[i + 1]}": c * 1e-15 for i, c in enumerate(deck.metal_overlaps)}


def deck_constants(deck_name: str) -> dict[str, Any]:
    from klayout_tools.decks import get_extraction_deck

    deck = get_extraction_deck(deck_name)
    caps = {c.name: c for c in deck.capacitors}
    m3 = caps["sky130_fd_pr__model__cap_mim"]
    m4 = caps["sky130_fd_pr__model__cap_mim_m4"]
    if (m3.area_cap_f_um2, m3.perim_cap_f_um) != (m4.area_cap_f_um2, m4.perim_cap_f_um):
        raise SystemExit("the two sky130 MiM classes no longer share one area/perimeter law; "
                         "size_capacitor's equal split would be wrong")
    return {
        "mim_classes": [m3.name, m4.name],
        "area_f_um2": m3.area_cap_f_um2,
        "perim_f_um": m3.perim_cap_f_um,
        "provenance": f"{m3.provenance.source_repo}:{m3.provenance.source_path}@{m3.provenance.commit}",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--netlist", required=True, type=Path, help="xschem netlist of design/ldo_3v3in_1v8out.sch")
    ap.add_argument("--floorplan", required=True, type=Path, help="measured layout record's floorplan.json")
    ap.add_argument("--measured-gds", required=True, type=Path, help="measured layout record's routed GDS")
    ap.add_argument("--budget", required=True, type=Path, help="area-study budget.json (#246)")
    ap.add_argument("--spec", required=True, type=Path)
    ap.add_argument("--deck", default="sky130")
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--cell-name", default="cap_rail_demo")
    args = ap.parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    spec = read_spec_constants(args.spec)
    fp = json.loads(args.floorplan.read_text())
    budget = json.loads(args.budget.read_text())
    deck = deck_constants(args.deck)
    rho = GEN.rail_sheet_rho_ohm_sq(args.deck)
    min_w = GEN.metal_min_rule_um(args.deck, "width")

    # --- core outline (measured MOS domain + folded resistor-bank column) ----
    attr = budget["attribution"]
    bank = next(s for s in budget["fold_sweep"] if s["high"]["bank_width_um"] == 100.0 and not s["optimistic_pitch"])
    bank_w = bank["high"]["bank_width_um"]
    bank_h = bank["high"]["bank_height_um"] + bank["xhigh"]["bank_height_um"]
    bank_gap = attr["block_gap_um"]
    core = plan.core_rectangle(
        mos_domain_w_um=attr["mos_core_width_um"],
        bank_w_um=bank_w,
        bank_gap_um=bank_gap,
        channel_h_um=attr["routing_channel_height_um"],
        row_h_um=attr["row_height_um"],
        rail_band_h_um=attr["rail_bands_height_um"],
    )
    W, H = core["w_um"], core["h_um"]
    subtap_x = next(t["x_um"] for t in fp["routing"]["body_ties"] if t["kind"] == "substrate_tie")
    x_off = subtap_x - (bank_w + bank_gap)  # measured x -> core x
    y_off = attr["routing_channel_height_um"]  # measured y -> core y (channel below the row)

    def mx(x: float) -> float:
        return x - x_off

    def my(y: float) -> float:
        return y + y_off

    rails_rec = {r["net"]: r for r in fp["routing"]["power_rails"]["rails"]}
    transition_rec = fp["routing"]["power_rails"]["transition_y_um"]
    transition = my(transition_rec)
    riser_x_rec = measured_riser_x(args.measured_gds, transition_rec)
    vin_rec, vout_rec = rails_rec["VIN"], rails_rec["VOUT"]
    pass_risers = [mx(x) for x in riser_x_rec if vin_rec["hot_x0_um"] <= x <= vin_rec["hot_x1_um"]]
    side_risers = [mx(x) for x in riser_x_rec if subtap_x <= x < vin_rec["hot_x0_um"]]
    dropped_risers = [x for x in riser_x_rec if x < subtap_x]

    # --- rails: re-sized by the unchanged #154 rule, on the proposed levels --
    budget_v = GEN.POWER_RAIL_IR_SHARE * spec.dropout_target_v / 2
    levels = {"VOUT": (1, 2), "VIN": (2, 3)}
    tail_levels = {"VOUT": (1,), "VIN": (2,)}
    rails: dict[str, dict[str, Any]] = {}
    for net, rec in (("VOUT", vout_rec), ("VIN", vin_rec)):
        span = (rec["hot_x1_um"] - GEN.RAIL_END_MARGIN_UM) - (rec["hot_x0_um"] + GEN.RAIL_END_MARGIN_UM)
        sizing = GEN.power_rail_width_um(
            span_um=span, current_a=spec.full_load_a, budget_v=budget_v,
            rho_ohm_sq=GEN.parallel_sheet_rho(rho, levels[net]),
            max_w_um=GEN.POWER_RAIL_MAX_W_FRACTION_OF_ROW * fp["row_height_um"],
            min_w_um=GEN.TRUNK_W_UM,
        )
        # Sense tail moved onto one level; widened so its resistance per
        # length is no worse than the measured two-level tail's.
        old_rho = GEN.parallel_sheet_rho(rho, tuple(rec["levels"]))
        lvl = tail_levels[net][0]
        tail_w = max(rec["tail_width_um"] * rho[lvl] / old_rho, min_w.get(lvl, 0.0) + 0.02)
        tail_w = plan.snap(-(-tail_w // plan.GRID_UM) * plan.GRID_UM)  # round up
        rails[net] = {
            "net": net,
            "levels": list(levels[net]),
            "tail_levels": list(tail_levels[net]),
            "measured_levels": rec["levels"],
            "sizing": sizing,
            "measured_width_um": rec["sizing"]["width_um"],
            "y0_um": my(rec["y0_um"]),
            "y1_um": my(rec["y0_um"]) + sizing["width_um"],
            "hot_x0_um": mx(rec["hot_x0_um"]),
            "hot_x1_um": mx(rec["hot_x1_um"]),
            "tail_x0_um": EDGE_UM / 2,
            "tail_w_um": tail_w,
            "measured_tail_w_um": rec["tail_width_um"],
            "tail_r_per_um_ohm": rho[lvl] / tail_w,
            "measured_tail_r_per_um_ohm": old_rho / rec["tail_width_um"],
        }
    if rails["VIN"]["y0_um"] < rails["VOUT"]["y1_um"] + GEN.RAIL_GAP_UM - 1e-6:
        raise SystemExit("recomputed VOUT rail no longer fits under the measured VIN band")
    if rails["VIN"]["y1_um"] > H + 1e-6:
        raise SystemExit("recomputed VIN rail exceeds the core height")

    d = Drawer(args.cell_name)
    d.box("boundary", 0, 0, W, H)

    # VOUT band 0: met1+met2 hot segment, via1 stitched; tail on met1 only.
    vo = rails["VOUT"]
    d.box("met1", vo["hot_x0_um"], vo["y0_um"], vo["hot_x1_um"], vo["y1_um"])
    d.box("met2", vo["hot_x0_um"], vo["y0_um"], vo["hot_x1_um"], vo["y1_um"])
    d.via_grid("via1", VIA1, GEN.RAIL_VIA_PITCH_UM, vo["hot_x0_um"] + 0.2, vo["y0_um"] + 0.2,
               vo["hot_x1_um"] - 0.2, vo["y1_um"] - 0.2)
    d.box("met1", vo["tail_x0_um"], vo["y0_um"], vo["hot_x0_um"] + 0.5, vo["y0_um"] + vo["tail_w_um"])
    d.label("met2_label", "VOUT", (vo["hot_x0_um"] + vo["hot_x1_um"]) / 2, (vo["y0_um"] + vo["y1_um"]) / 2)

    # VIN band 1: met2+met3 hot segment, via2 stitched; tail on met2 only.
    vi = rails["VIN"]
    d.box("met2", vi["hot_x0_um"], vi["y0_um"], vi["hot_x1_um"], vi["y1_um"])
    d.box("met3", vi["hot_x0_um"], vi["y0_um"], vi["hot_x1_um"], vi["y1_um"])
    d.via_grid("via2", VIA2, GEN.RAIL_VIA_PITCH_UM, vi["hot_x0_um"] + 0.2, vi["y0_um"] + 0.2,
               vi["hot_x1_um"] - 0.2, vi["y1_um"] - 0.2)
    d.box("met2", vi["tail_x0_um"], vi["y0_um"], vi["hot_x0_um"] + 0.5, vi["y0_um"] + vi["tail_w_um"])
    d.label("met2_label", "VIN", (vi["hot_x0_um"] + vi["hot_x1_um"]) / 2, (vi["y0_um"] + vi["y1_um"]) / 2)

    # VIN risers. Pass-device risers cross the VOUT hot band on met3 (as in
    # the measured layout); every other VIN riser now crosses the met1-only
    # VOUT tail on met2 and lands on the met2-only VIN tail.
    pad = PAD
    for x in pass_risers:
        d.square("met1", x, transition, pad)
        d.square("via1", x, transition, VIA1)
        d.square("met2", x, transition, pad)
        d.square("via2", x, transition, VIA2)
        h = GEN.POWER_MET3_RISER_W_UM / 2
        d.box("met3", x - h, transition - h, x + h, vi["y1_um"])
    for x in side_risers:
        d.square("met1", x, transition, pad)
        d.square("via1", x, transition, VIA1)
        h = pad / 2  # as wide as the landing pad: keeps via1's m2.5 enclosure
        d.box("met2", x - h, transition - pad / 2, x + h, vi["y0_um"] + vi["tail_w_um"])

    # Keep-out: the met3 VIN rail column above the pass device.
    zone = {
        "x0_um": min(pass_risers) - GEN.POWER_MET3_RISER_W_UM / 2 - ZONE_KEEPOUT_UM,
        "y0_um": transition - pad / 2 - ZONE_KEEPOUT_UM,
        "x1_um": W,
        "y1_um": H,
    }

    # --- capacitors -----------------------------------------------------------
    caps = {c["name"]: c for c in plan.parse_capacitors(args.netlist.read_text())}
    if set(caps) != set(CAP_PLAN):
        raise SystemExit(f"schematic capacitors {sorted(caps)} != planned {sorted(CAP_PLAN)}")
    blocks: list[dict[str, Any]] = []
    vin_tail_slot = EDGE_UM
    for name, cp in CAP_PLAN.items():
        cap = caps[name]
        sz = plan.size_capacitor(name, cap["value_f"], cp["rows"], cp["cols"], 2,
                                 deck["area_f_um2"], deck["perim_f_um"])
        plates = plan.assign_plates(cap["nets"], cp["outer"])
        ext = plan.block_extent_um(cp["rows"], cp["cols"], sz["unit_side_um"])
        kind, pos = cp["anchor"]
        if kind == "left":
            bx, by = EDGE_UM, EDGE_UM
        elif kind == "right":
            bx, by = W - EDGE_UM - ext["w_um"], EDGE_UM
        else:  # straddle the VIN met2 tail, left to right
            bx = vin_tail_slot
            vin_tail_slot += ext["w_um"] + BLOCK_GAP_UM
            tail_mid = vi["y0_um"] + vi["tail_w_um"] / 2
            by = tail_mid - ext["bottom_um"] - 0.25 * ext["array_h_um"]
        bx, by = plan.snap(bx), plan.snap(by)
        blocks.append({**sz, "nets": cap["nets"], "plates": plates, "extent": ext,
                       "x0_um": bx, "y0_um": by, "x1_um": bx + ext["w_um"], "y1_um": by + ext["h_um"],
                       "tap_frac": cp["tap_frac"]})

    # Placement checks: inside the core, clear of each other and of the zone.
    def overlaps(a: dict[str, float], b: dict[str, float], gap: float) -> bool:
        return not (a["x1_um"] + gap <= b["x0_um"] or b["x1_um"] + gap <= a["x0_um"]
                    or a["y1_um"] + gap <= b["y0_um"] or b["y1_um"] + gap <= a["y0_um"])

    for i, b in enumerate(blocks):
        if b["x0_um"] < 0 or b["y0_um"] < 0 or b["x1_um"] > W or b["y1_um"] > H:
            raise SystemExit(f"{b['name']} leaves the core outline: {b}")
        if overlaps(b, zone, 0.0):
            raise SystemExit(f"{b['name']} intrudes on the met3 VIN rail column {zone}")
        for other in blocks[i + 1:]:
            if overlaps(b, other, BLOCK_GAP_UM - 1e-6):
                raise SystemExit(f"{b['name']} and {other['name']} are closer than {BLOCK_GAP_UM} um")

    e = plan.PLATE_ENCLOSURE_UM
    for b in blocks:
        s = b["unit_side_um"]
        ext = b["extent"]
        ax = b["x0_um"] + ext["left_um"]
        ay = b["y0_um"] + ext["bottom_um"]
        lx, ly = ext["array_w_um"], ext["array_h_um"]
        pitch = s + plan.UNIT_GAP_UM
        n_via3 = n_via4 = 0
        for i in range(b["rows"]):
            for j in range(b["cols"]):
                ux, uy = ax + j * pitch, ay + i * pitch
                d.box("capm", ux, uy, ux + s, uy + s)
                d.box("capm2", ux, uy, ux + s, uy + s)
                n_via3 += d.via_grid("via3", VIA3, VIA3_PITCH, ux + VIA3_INSET, uy + VIA3_INSET,
                                     ux + s - VIA3_INSET, uy + s - VIA3_INSET)
                n_via4 += d.via_grid("via4", VIA4, VIA4_PITCH, ux + VIA4_INSET, uy + VIA4_INSET,
                                     ux + s - VIA4_INSET, uy + s - VIA4_INSET)
        # Outer plates: met3 (bottom of the m3 MiM), met5 (top of the m4 MiM).
        d.box("met3", ax - e, ay - e, ax + lx + e, ay + ly + e)
        isl_x1 = ax - plan.STRAP_ISLAND_INNER_UM
        isl_x0 = isl_x1 - plan.STRAP_ISLAND_W_UM
        d.box("met5", isl_x0, ay - e, ax + lx + e, ay + ly + e)
        # Inner plate: met4 (top-plate landing of the m3 MiM, bottom of the m4 MiM).
        d.box("met4", ax - e, ay - e, ax + lx + e, ay + ly + e)
        # Outer-plate strap on the left edge (see _cap_rail_plan's note).
        d.box("met3", isl_x0, ay - e, isl_x1, ay + ly + e)
        m4_x1 = ax - e - plan.STRAP_M4_GAP_UM
        d.box("met4", isl_x0, ay - e, m4_x1, ay + ly + e)
        n_strap3 = d.via_grid("via3", VIA3, 1.0, isl_x0 + 0.1, ay - e + 0.2, isl_x0 + 0.5, ay + ly + e - 0.2)
        n_strap4 = d.via_grid("via4", VIA4, 1.6, m4_x1 - 0.2 - VIA4 - 0.3, ay - e + 0.4, m4_x1 - 0.3, ay + ly + e - 0.4)
        posts = []
        y = ay + 1.0
        while y <= ay + ly - 1.0 + 1e-9:
            posts.append(y)
            y += plan.STRAP_POST_PITCH_UM
        if not posts:
            posts = [ay + ly / 2]
        for py in posts:
            d.box("met2", isl_x1 - 0.6, py - 0.3, ax - 0.1, py + 0.3)
            d.square("via2", isl_x1 - 0.3, py, VIA2)  # under the met3 island
            d.square("via2", ax - 0.3, py, VIA2)  # under the met3 plate margin
        # Inner-plate tap on the right edge.
        ty = ay + b["tap_frac"] * ly
        tx0 = ax + lx + plan.TAP_ISLAND_INNER_UM
        th = plan.TAP_ISLAND_H_UM / 2
        d.box("met3", tx0, ty - th, tx0 + plan.TAP_ISLAND_W_UM, ty + th)
        d.box("met4", ax + lx + e, ty - th, tx0 + 0.6, ty + th)
        d.square("via3", tx0 + 0.3, ty, VIA3)
        d.box("met2", tx0 + plan.TAP_ISLAND_W_UM - 0.7, ty - 0.35, tx0 + plan.TAP_ISLAND_W_UM, ty + 0.35)
        d.square("via2", tx0 + plan.TAP_ISLAND_W_UM - 0.3, ty, VIA2)
        d.label("met2_label", b["plates"]["inner"], tx0 + plan.TAP_ISLAND_W_UM - 0.35, ty)
        # Outer-plate connection into the core.
        outer = b["plates"]["outer"]
        a_taps: list[dict[str, float]] = []
        if outer == "VOUT":
            # Via stacks down to the met1 VOUT tail in the vertical gaps
            # between unit columns, skipping any too close to a VIN met2 riser.
            ty0 = vo["y0_um"] + vo["tail_w_um"] / 2
            for j in range(1, b["cols"]):
                gx = ax + j * pitch - plan.UNIT_GAP_UM / 2
                if any(abs(gx - rx) < 1.0 for rx in side_risers):
                    continue
                d.square("via2", gx, ty0, VIA2)
                d.box("met2", gx - 0.3, ty0 - 0.3, gx + 0.3, ty0 + 0.3)  # 0.6 um: >=0.2 um around both vias
                d.square("via1", gx, ty0, VIA1)
                a_taps.append({"x_um": gx, "y_um": ty0, "to": "VOUT tail (met1)"})
            if not a_taps:
                raise SystemExit("C_COMP: no VOUT tail via stack could be placed")
        elif outer == "VIN":
            # The met2 VIN tail runs under the plate margin: via2 onto it.
            tyv = vi["y0_um"] + vi["tail_w_um"] / 2
            if not (ay - e < tyv < ay + ly + e):
                raise SystemExit(f"{b['name']}: VIN tail does not run under the block")
            for gx in (ax - 0.3, ax + lx + 0.3):
                d.square("via2", gx, tyv, VIA2)
                a_taps.append({"x_um": gx, "y_um": tyv, "to": "VIN tail (met2)"})
        else:
            # No drawn conductor for this net here: label the first strap
            # bridge (met2, already on the outer plate) with the net name.
            d.label("met2_label", outer, isl_x1 - 0.3, posts[0])
            a_taps.append({"x_um": isl_x1 - 0.3, "y_um": posts[0], "to": "labelled met2 pad"})
        b.update({"array_x0_um": ax, "array_y0_um": ay, "via3_top_plate": n_via3, "via4_top_plate": n_via4,
                  "strap_via3": n_strap3, "strap_via4": n_strap4, "strap_posts": len(posts),
                  "inner_tap": {"x_um": tx0 + plan.TAP_ISLAND_W_UM - 0.35, "y_um": ty}, "outer_taps": a_taps,
                  "block_area_um2": ext["w_um"] * ext["h_um"],
                  "mim_footprint_um2": b["units"] * s * s})

    # Device-row routing that would sit under each block is NOT drawn (a net
    # with no device extracts as dead metal and gets no parasitics). Instead
    # measure, from the measured layout's own stream mapped into core
    # coordinates, how much li1/met1/met2 lies under each block's outer
    # plate -- the area the deck's met2-met3 overlap coefficient applies to.
    under = measured_routing_under(args.measured_gds, blocks, x_off, y_off,
                                   exclude_y_from=transition_rec, x_from=subtap_x)
    for b in blocks:
        b["measured_routing_under_um2"] = under[b["name"]]

    gds = out / f"{args.cell_name}.gds"
    d.write(gds)

    # --- LVS reference: each schematic capacitor as its two MiM halves -------
    ports = ["VOUT", "VIN", "EA_CZ", "CL_CMP", "SS", "TS_CMP"]
    ref = [
        f"* LVS reference for `{args.cell_name}` (issue #254), generated by gen-cap-rail-demo.py",
        "* from design/ldo_3v3in_1v8out.sch's own xschem netlist. Each schematic capacitor is",
        "* drawn as stacked MiM units (cap_mim_m3_1 + cap_mim_m3_2 over the same footprint, in",
        "* parallel), so it is stated here as one element per MiM class carrying half the",
        "* schematic value. Values are the SCHEMATIC's, not the drawn geometry's.",
        f".SUBCKT {args.cell_name} {' '.join(ports)}",
    ]
    for b in blocks:
        n1, n2 = b["nets"]
        for cls in deck["mim_classes"]:
            suffix = "M3" if cls.endswith("cap_mim") else "M4"
            ref.append(f"{b['name']}_{suffix} {n1} {n2} {b['target_f'] / 2:.6e} {cls}")
    ref.append(f".ENDS {args.cell_name}")
    (out / "reference.spice").write_text("\n".join(ref) + "\n")

    mim_um2 = sum(b["mim_footprint_um2"] for b in blocks)
    block_um2 = sum(b["block_area_um2"] for b in blocks)
    usable_um2 = core["area_um2"] - (zone["x1_um"] - zone["x0_um"]) * (zone["y1_um"] - zone["y0_um"])
    summary = {
        "schema_version": 1,
        "issue": 254,
        "cell": args.cell_name,
        "gds": gds.name,
        "units": {"length": "um", "area": "um^2", "capacitance": "F"},
        "core": {**core, "bank_column": {"w_um": bank_w, "h_um": bank_h, "gap_um": bank_gap,
                                         "source": "budget.json fold_sweep, 100 um conservative"},
                 "x_offset_from_measured_um": x_off, "y_offset_from_measured_um": y_off,
                 "composition": {"mos_domain_w_um": attr["mos_core_width_um"],
                                 "channel_h_um": attr["routing_channel_height_um"],
                                 "row_h_um": attr["row_height_um"],
                                 "rail_bands_h_um": attr["rail_bands_height_um"]}},
        "deck": deck,
        "spec": {"full_load_a": spec.full_load_a, "dropout_target_v": spec.dropout_target_v,
                 "ir_share": GEN.POWER_RAIL_IR_SHARE, "ir_budget_per_rail_v": budget_v},
        "rails": rails,
        "risers": {"pass_met3": len(pass_risers), "side_met2": len(side_risers),
                   "not_drawn_outside_mos_domain": len(dropped_risers), "transition_y_um": transition},
        "met3_rail_zone": zone,
        "capacitors": blocks,
        "overlap_coefficients_f_um2": overlap_coefficients(args.deck),
        "totals": {"mim_footprint_um2": mim_um2, "cap_block_um2": block_um2,
                   "overlay_usable_um2": usable_um2, "cap_block_fraction_of_usable": block_um2 / usable_um2,
                   "effective_density_f_um2": sum(b["target_f"] for b in blocks) / block_um2,
                   "side_by_side_area_um2": plan.side_by_side_area_um2([b["block_area_um2"] for b in blocks],
                                                                       core["area_um2"])},
        "shape_counts": d.counts,
        "sources": {"netlist": str(args.netlist.name), "floorplan": str(args.floorplan),
                    "measured_gds": str(args.measured_gds), "budget": str(args.budget), "spec": str(args.spec)},
    }
    (out / "plan.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"gds": str(gds), "core_mm2": core["area_mm2"], "caps": [
        (b["name"], b["unit_side_um"], b["planned_total_f"]) for b in blocks]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
