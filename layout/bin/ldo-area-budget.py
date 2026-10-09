#!/usr/bin/env python3
"""Reproducible core-area budget and compaction-feasibility study (issue #246).

Reads ONLY existing evidence (the routed-layout record's `floorplan.json`, the
issue-#236 area record's `area.json`, and the current xschem schematic) and
writes a NEW study directory `layout/area-study/<record-id>/` holding
`budget.json` and `report.md`. Nothing under `sim/` or `layout/ldo-core/` is
touched (append-only evidence). No layout is generated, no simulation is run.

This is a GEOMETRIC ESTIMATE. It is not a DRC/LVS-verified claim and not a
statement that the < 0.1 mm^2 Area row is met. The ratified target is read as
a constant and never altered; resistor values and transistor dimensions are
inputs, never knobs.

Optional `--probe-klt` runs ONE single-unit `klt gen res_array` locally (no
grid, no parallelism) to measure the end-pad overhead of a resistor segment;
without it the recorded probe constants below are used.

Standard library only. Usage:
    python3 layout/bin/ldo-area-budget.py [--probe-klt] [--record-id ID]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
LIMIT_UM2 = 0.1e6  # ratified Area row: < 0.1 mm^2 (strict); never altered here
SCHEMATIC = REPO / "design" / "ldo_3v3in_1v8out.sch"

# Recorded single-unit res_array probe (klt 0.7.0+gb82427b30c96, sky130A,
# flavor=high, width_um=0.42, length_um=100, num=1, dummy=0): bbox
# x -0.25..101.03, y -1.09..1.51 -> overhead along the body 1.28 um, bbox
# height 2.6 um (2.2 um end pads); drc_hints min_spacing 0.5, foreign 0.4.
PROBE = {
    "klt_version": "0.7.0+gb82427b30c96",
    "unit_length_um": 100.0,
    "bbox_len_um": 101.28,
    "bbox_h_um": 2.6,
    "min_spacing_um": 0.5,
    "foreign_clearance_um": 0.4,
    "source": "recorded",
}
# Pin-era (klt 0.6.0+g040f3406b485) generator bbox for the same device was
# 0.42 um tall / L+0.84 long (see the historical gen.R_BIAS.json); the newer
# probe is the more conservative end-pad geometry and is used for estimates.

CAP_FF_PER_UM2 = {"single_mim_cap_mim_m3_1": 2.0, "stacked_two_mim_assumed": 4.0}
# 2 fF/um^2 is design/README.md's own figure for cap_mim_m3_1. The stacked
# value is an UNVERIFIED assumption (two MiM layers in parallel) used only as
# a labelled sensitivity.


def parse_schematic(path: Path) -> dict[str, dict]:
    txt = path.read_text()
    out: dict[str, dict] = {}
    for m in re.finditer(r"^C \{(?:sky130_fd_pr|devices)/(\w+)\.sym\}[^{]*\{(.*?)\}", txt, re.S | re.M):
        sym, attrs = m.group(1), m.group(2)
        if sym not in ("nfet_g5v0d10v5", "pfet_g5v0d10v5", "res_high_po", "res_xhigh_po", "capa"):
            continue
        kv = dict(re.findall(r"(\w+)=(\S+)", attrs))
        out[kv["name"]] = {"sym": sym, **{k: kv[k] for k in ("L", "W", "mult", "value") if k in kv}}
    return out


def num(s: str) -> float:
    mult = {"p": 1e-12, "f": 1e-15, "n": 1e-9, "u": 1e-6, "m": 1e-3}
    return float(s[:-1]) * mult[s[-1]] if s[-1] in mult else float(s)


def run_probe() -> dict:
    with tempfile.TemporaryDirectory() as td:
        params = {"length_um": 100, "width_um": 0.42, "num": 1, "dummy": 0, "flavor": "high"}
        out = subprocess.run(
            ["klt", "gen", "res_array", "--pdk", "sky130A", "--params", json.dumps(params),
             "--cell-name", "probe", "-o", f"{td}/probe.gds", "--format", "json"],
            check=True, capture_output=True, text=True).stdout
        d = json.loads(out)
        b = d["bbox_um"]
        return {"klt_version": d["provenance"]["klt_version"], "unit_length_um": 100.0,
                "bbox_len_um": round(b["x1"] - b["x0"], 4), "bbox_h_um": round(b["y1"] - b["y0"], 4),
                "min_spacing_um": d["drc_hints"]["min_spacing_um"],
                "foreign_clearance_um": d["drc_hints"].get("foreign_clearance_um", 0.4), "source": "live"}


def fold_bank(lengths: list[float], bank_w: float, probe: dict, optimistic: bool) -> dict:
    """Area of series-folded straight segments in a rectangle `bank_w` wide.
    Each logical resistor of body length L becomes N = ceil(L/(bank_w-ovh))
    equal segments of L/N, one row each. Row pitch = pad-bbox height + spacing
    (conservative) or body width + spacing (optimistic, pads staggered)."""
    ovh = probe["bbox_len_um"] - probe["unit_length_um"]
    pitch = (0.42 if optimistic else probe["bbox_h_um"]) + probe["min_spacing_um"]
    segs = [math.ceil(length / (bank_w - ovh)) for length in lengths]
    rows = sum(segs)
    h = rows * pitch
    return {"bank_width_um": bank_w, "segments_per_resistor": segs, "rows": rows,
            "row_pitch_um": pitch, "bank_height_um": round(h, 3), "bank_area_um2": round(bank_w * h, 1)}


def build(args: argparse.Namespace) -> dict:
    fp_path = REPO / args.floorplan
    ar_path = REPO / args.area
    fp = json.loads(fp_path.read_text())
    ar = json.loads(ar_path.read_text())
    probe = run_probe() if args.probe_klt else PROBE
    sch = parse_schematic(SCHEMATIC)
    devs = {d["id"]: d for d in fp["devices"]}
    mos = [d for d in fp["devices"] if d["kind"] == "mos"]
    res = [d for d in fp["devices"] if d["kind"] == "res"]

    W, H = float(ar["width_um"]), float(ar["height_um"])
    bbox_area = W * H
    bb = lambda d: (d["placed_bbox_um"]["x1"] - d["placed_bbox_um"]["x0"]) * (d["placed_bbox_um"]["y1"] - d["placed_bbox_um"]["y0"])  # noqa: E731
    occ_mos, occ_res = sum(bb(d) for d in mos), sum(bb(d) for d in res)

    ymin, ymax = float(ar["bbox_um"][1]), float(ar["bbox_um"][3])
    row_h = fp["row_height_um"]
    channel_h = -ymin  # routing channel below the row
    rails_h = ymax - row_h  # rail bands above the row (incl. gap)
    res_x1 = max(d["placed_bbox_um"]["x1"] for d in res)
    sub_tie_x = next(t["x_um"] for t in fp["routing"]["body_ties"] if t["kind"] == "substrate_tie")
    xmax = float(ar["bbox_um"][2])
    core_w = xmax - sub_tie_x  # MOS domain incl. substrate-tie slot (approx.)
    res_span_w = res_x1 - min(d["placed_bbox_um"]["x0"] for d in res)

    # current-schematic vs historical-geometry inventory
    cur_mos = {k: v for k, v in sch.items() if v["sym"].endswith("fet_g5v0d10v5")}
    cur_res = {k: v for k, v in sch.items() if v["sym"].startswith("res_")}
    cur_cap = {k: v for k, v in sch.items() if v["sym"] == "capa"}
    added = sorted(set(cur_mos) - set(devs))
    removed = sorted(k for k in devs if devs[k]["kind"] == "mos" and k not in cur_mos)
    changed = []
    for k, v in cur_mos.items():
        if k in devs:
            d = devs[k]
            wt = num(v["W"]) * num(v.get("mult", "1"))
            if abs(wt - d["w_total_um"]) > 1e-6 or abs(num(v["L"]) - d["l_um"]) > 1e-6:
                changed.append({"id": k, "schematic_w_total_um": wt, "layout_w_total_um": d["w_total_um"],
                                "schematic_l_um": num(v["L"]), "layout_l_um": d["l_um"]})
    added_area = 0.0
    added_rows = []
    for k in added:
        v = cur_mos[k]
        wt, l = num(v["W"]) * num(v.get("mult", "1")), num(v["L"])
        units = math.ceil(wt / 100.0)
        a = units * (l + 1.24 + 2.0) * (wt / units + 1.12)  # per-unit pitch + block gap; est. from M_TAIL/M_PASS
        added_area += a
        added_rows.append({"id": k, "w_total_um": wt, "l_um": l, "est_area_um2": round(a, 1)})

    removed_area = sum((bb(devs[k]) / 1.0) + (devs[k]["placed_bbox_um"]["y1"] - devs[k]["placed_bbox_um"]["y0"]) * 2.0 for k in removed)
    caps = {k: num(v["value"]) for k, v in cur_cap.items()}
    cap_total_f = sum(caps.values())

    # straight-resistor placement-only bound
    r_bias = devs["R_BIAS"]
    straight_w = r_bias["placed_bbox_um"]["x1"]
    h_budget = LIMIT_UM2 / straight_w
    reserv = channel_h + rails_h

    lengths_high = [d["length_um"] for d in res if d["flavor"] == "high"]
    lengths_xh = [d["length_um"] for d in res if d["flavor"] == "xhigh"]
    folds = []
    for bw in (50.0, 100.0, 200.0):
        for opt in (False, True):
            hi = fold_bank(lengths_high, bw, probe, opt)
            xh = fold_bank(lengths_xh, bw, probe, opt)
            folds.append({"optimistic_pitch": opt, "high": hi, "xhigh": xh,
                          "total_area_um2": round(hi["bank_area_um2"] + xh["bank_area_um2"], 1)})
    cons = next(f for f in folds if not f["optimistic_pitch"] and f["high"]["bank_width_um"] == 100.0)
    bank = cons["total_area_um2"]

    core_area = core_w * H
    scen = {
        "A_measured_current": bbox_area,
        "B_mos_core_only_current_reservations": core_area,
        "C_B_plus_folded_resistor_banks_conservative": core_area + bank,
        "D_C_plus_net_mos_change_to_current_schematic": core_area + bank + added_area - removed_area,
    }
    for name, dens in CAP_FF_PER_UM2.items():
        cap_um2 = cap_total_f * 1e15 / dens
        scen[f"E_D_plus_caps_beside_{name}"] = scen["D_C_plus_net_mos_change_to_current_schematic"] + cap_um2
    caps_overlay = {name: cap_total_f * 1e15 / d for name, d in CAP_FF_PER_UM2.items()}

    return {
        "schema_version": 1,
        "issue": 246,
        "units": {"length": "um", "area": "um^2 (mm^2 = um^2 / 1e6)", "capacitance": "F"},
        "limit_um2": LIMIT_UM2,
        "limit_comparison": "area < limit (strict); target unchanged, read only",
        "geometry_convention": "bounding rectangle (width x height) of placed blocks + routing channel + rail bands, from the measured top-cell bbox; device 'occupied' sums use each block's placed bbox (generator report), not drawn-polygon area",
        "sources": {
            "area_record": args.area, "area_record_gds_sha256": ar["gds"]["sha256"],
            "layout_record": ar["layout_record"], "floorplan_json": args.floorplan,
            "schematic": "design/ldo_3v3in_1v8out.sch",
            "schematic_git_last_commit": subprocess.run(["git", "-C", str(REPO), "log", "-1", "--format=%H", "--", "design/ldo_3v3in_1v8out.sch", "design/thermal_cmp_regen.sch"], capture_output=True, text=True).stdout.strip(),
            "repo_head": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        },
        "probe": probe,
        "measured": {"width_um": W, "height_um": H, "area_um2": bbox_area, "ratio_to_limit": bbox_area / LIMIT_UM2},
        "attribution": {
            "occupied_mos_bbox_sum_um2": round(occ_mos, 1), "occupied_res_bbox_sum_um2": round(occ_res, 3),
            "occupied_fill_fraction_of_bbox": (occ_mos + occ_res) / bbox_area,
            "resistor_span_width_um": res_span_w, "resistor_span_fraction_of_width": res_span_w / W,
            "r_bias_straight_width_um": straight_w, "r_bias_fraction_of_width": straight_w / W,
            "mos_core_width_um": core_w, "mos_core_fraction_of_width": core_w / W,
            "routing_channel_height_um": channel_h, "row_height_um": row_h, "rail_bands_height_um": rails_h,
            "height_split_fraction": {"channel": channel_h / H, "device_row": row_h / H, "rails": rails_h / H},
            "pass_device_bbox_um2": round(bb(devs["M_PASS"]), 1),
            "pass_device_w_total_um": devs["M_PASS"]["w_total_um"],
            "core_height_floor_from_reservations_um": reserv,
            "tap_slot_um": 4.0, "block_gap_um": fp.get("block_gap_um", 2.0),
        },
        "placement_only_straight_resistor": {
            "min_width_um": straight_w, "max_height_for_limit_um": h_budget,
            "channel_plus_rails_reservation_um": reserv, "reservation_exceeds_height_budget": reserv > h_budget,
            "area_if_current_height_um2": straight_w * H,
        },
        "inventory": {
            "layout_blocks": len(devs), "layout_mos": len(mos), "layout_res": len(res),
            "schematic_mos": len(cur_mos), "schematic_res": len(cur_res), "schematic_caps": len(cur_cap),
            "mos_added_since_layout": added, "mos_removed_since_layout": removed,
            "mos_size_changed": changed, "added_mos_est": added_rows, "added_mos_est_area_um2": round(added_area, 1), "removed_mos_area_um2": round(removed_area, 1),
            "caps_f": caps, "caps_total_f": cap_total_f,
            "caps_drawn_in_layout": False,
        },
        "fold_sweep": folds,
        "scenarios_um2": {k: round(v, 1) for k, v in scen.items()},
        "scenarios_mm2": {k: round(v / 1e6, 5) for k, v in scen.items()},
        "scenarios_pass_limit": {k: v < LIMIT_UM2 for k, v in scen.items()},
        "cap_area_um2": {k: round(v, 1) for k, v in caps_overlay.items()},
        "claims_verified": "none: all figures are geometric estimates; no DRC/LVS/PEX run on any compacted layout",
    }


def render(b: dict, rid: str) -> str:
    a, p, s, inv, src = b["attribution"], b["placement_only_straight_resistor"], b["scenarios_mm2"], b["inventory"], b["sources"]
    L = []
    w = L.append
    w(f"# LDO core area budget and compaction feasibility: {rid}\n")
    w("Issue #246 study. **Geometric estimate only** -- no DRC/LVS/PEX/simulation on any compacted layout; the ratified Area row (< 0.1 mm^2, strict) is unchanged and is not claimed met.\n")
    w("## Sources and conventions\n")
    w(f"- Measured area record: `{src['area_record']}` (GDS sha256 `{src['area_record_gds_sha256'][:16]}...`), from layout record `{src['layout_record']}`; per-device table `{src['floorplan_json']}`.")
    w(f"- Schematic: `{src['schematic']}`, last changed at `{src['schematic_git_last_commit'][:7]}`. Repo HEAD for this study: `{src['repo_head'][:7]}`.")
    w(f"- Resistor segment probe: klt `{b['probe']['klt_version']}` ({b['probe']['source']}); units um / um^2; area = bounding rectangle width x height (see `budget.json` `geometry_convention`).")
    w("- **Historical vs current**: the routed layout predates comparator integration (#230). The floorplan has "
      f"{inv['layout_mos']} MOS + {inv['layout_res']} resistors; the current schematic has {inv['schematic_mos']} MOS + {inv['schematic_res']} resistors + {inv['schematic_caps']} capacitors. "
      f"MOS not in the layout: {', '.join(inv['mos_added_since_layout']) or 'none'}; in layout but not in schematic: {', '.join(inv['mos_removed_since_layout']) or 'none'}; "
      f"sized differently: {', '.join(c['id'] for c in inv['mos_size_changed']) or 'none'}. #231 owns refreshing the layout.")
    w(f"- Observed: the layout's `M_PASS` is {a['pass_device_w_total_um']:.0f} um total width; `layout/ldo-core/floorplan.md` still quotes 2500 um (stale prose, not changed here).\n")
    w("## Where the 0.4468 mm^2 goes\n")
    w(f"- Footprint {b['measured']['width_um']} x {b['measured']['height_um']} um = {b['measured']['area_um2']/1e6:.4f} mm^2 ({b['measured']['ratio_to_limit']:.2f}x limit).")
    w(f"- Occupied device bboxes: MOS {a['occupied_mos_bbox_sum_um2']:.0f} um^2 + resistors {a['occupied_res_bbox_sum_um2']:.1f} um^2 = {a['occupied_fill_fraction_of_bbox']*100:.1f}% of the rectangle. A device-area sum is therefore NOT the footprint; the rest is spacing, tap slots, the routing channel, rail bands and empty corners.")
    w(f"- Width: the resistor span is {a['resistor_span_width_um']:.1f} um = {a['resistor_span_fraction_of_width']*100:.1f}% of the width; `R_BIAS` alone is {a['r_bias_straight_width_um']:.1f} um ({a['r_bias_fraction_of_width']*100:.1f}%). The MOS domain (substrate-tie slot through the pass device) is {a['mos_core_width_um']:.1f} um ({a['mos_core_fraction_of_width']*100:.1f}%).")
    hs = a["height_split_fraction"]
    w(f"- Height {b['measured']['height_um']} um = routing channel {a['routing_channel_height_um']:.2f} ({hs['channel']*100:.0f}%) + device row {a['row_height_um']:.2f} ({hs['device_row']*100:.0f}%, set by the pass device unit height) + rail bands {a['rail_bands_height_um']:.2f} ({hs['rails']*100:.0f}%, widths computed from the ratified dropout budget, `layout/ldo-core/floorplan.md`).")
    w(f"- Tap slots ({a['tap_slot_um']} um each) and block gaps ({a['block_gap_um']} um) are second-order here.\n")
    w("## Does placement alone reach < 0.1 mm^2?\n")
    w(f"No. The straight `R_BIAS` makes any single-rectangle floorplan at least {p['min_width_um']:.1f} um wide; < 0.1 mm^2 then requires a total height under {p['max_height_for_limit_um']:.1f} um. The channel + rail-band reservations alone are {p['channel_plus_rails_reservation_um']:.1f} um (before any device row), so the bound fails even with every other device free. Multi-row placement cannot split the resistor (the pinned generator draws one straight body per logical resistor), so row count does not reduce the 1500 um dimension. At the current height the straight-resistor rectangle would be {p['area_if_current_height_um2']/1e6:.3f} mm^2.\n")
    w("## Folded-resistor direction (separate NMOS/PMOS wells kept, existing rail sizing kept)\n")
    w("Model: each logical resistor is cut into N equal straight series segments (body lengths sum to the schematic L; W unchanged), stacked as rows in a bank per flavor (`high` / `xhigh` masks must not mix). Segment length overhead and pad height come from the single-unit probe; row pitch = pad bbox height + min spacing (conservative) or body width + spacing (optimistic, staggered pads, not claimed).\n")
    w("| bank width (um) | pitch | R_BIAS bank rows / area | xhigh bank rows / area | total (um^2) |\n|---|---|---|---|---|")
    for f in b["fold_sweep"]:
        w(f"| {f['high']['bank_width_um']:.0f} | {'optimistic' if f['optimistic_pitch'] else 'conservative'} | {f['high']['rows']} / {f['high']['bank_area_um2']:.0f} | {f['xhigh']['rows']} / {f['xhigh']['bank_area_um2']:.0f} | {f['total_area_um2']:.0f} |")
    w("\nThe resistors then cost roughly 0.01 mm^2, not 0.3 mm^2: the width problem is real but removable. Assumptions (all to be verified later): resistors sit on field oxide needing no well (only the existing substrate-tie reach), the 0.4 um foreign clearance and 0.5 um spacing from the generator hints suffice, series joints are short li1/met1 jogs, and the N-segment series string reproduces the original resistance within tolerance (joint/contact resistance and end-pad contribution are NOT yet evaluated; electrical requalification is required). `klt gen res_array` units are independent matched elements (`rows` re-arranges `num` units, it does not chain them in series), so the series connection must be routed by `gen-ldo-blocks.py` (a tool gap, filed generically as 2AMLogic/klayout-tools#2997). `klt lvs` `options.combine_devices` has handled series resistor arrays in past upstream work (fixed-offset corrections were issues #559/#1557 there); whether it folds this repo's pinned build's N-segment string to the schematic's single element is UNVERIFIED and is part of follow-up (a).\n")
    w("## Whole-footprint scenarios (current reservations, MOS domain re-used as measured)\n")
    names = {"A_measured_current": "A. Measured routed core (record)", "B_mos_core_only_current_reservations": "B. MOS domain only (no resistors, NO caps), full channel/rails height",
             "C_B_plus_folded_resistor_banks_conservative": "C. B + folded resistor banks (100 um, conservative; NO caps)",
             "D_C_plus_net_mos_change_to_current_schematic": "D. C + estimated net MOS change (12 added, 7 removed) to the current schematic",
             "E_D_plus_caps_beside_single_mim_cap_mim_m3_1": "E1. D + all four capacitors beside the core, 2 fF/um^2",
             "E_D_plus_caps_beside_stacked_two_mim_assumed": "E2. D + capacitors beside, 4 fF/um^2 (stacked MiM, unverified)"}
    w("| scenario (B-D omit the undrawn capacitors, so a 'yes' is not a pass claim) | mm^2 | < 0.1? |\n|---|---|---|")
    for k, n in names.items():
        w(f"| {n} | {s[k]:.4f} | {'yes' if b['scenarios_pass_limit'][k] else 'no'} |")
    ca = b["cap_area_um2"]
    w(f"\n**The dominant blocker is not the resistor.** The four capacitors (C_COMP 150 pF, C_SS 10 pF, C_CL 1 pF, C_TS 1 pF = {inv['caps_total_f']*1e12:.0f} pF) are not drawn in the measured layout (known gap, `layout/ldo-core/floorplan.md`), so the 0.4468 mm^2 figure omits them. At 2 fF/um^2 they need {ca['single_mim_cap_mim_m3_1']:.0f} um^2 ({ca['single_mim_cap_mim_m3_1']/1e6:.3f} mm^2) by themselves -- 81% of the limit -- and {ca['stacked_two_mim_assumed']:.0f} um^2 at an assumed 4 fF/um^2. `design/README.md` already notes MiM (met3-met4) can sit over the pass device, but the VIN rail's upper band uses met2+met3 above it, so overlaying needs a rail-level change that is not evaluated here. Placing capacitors beside the core fails in E1 and is marginal-to-failing in E2 (before any capacitor spacing/routing); only overlay on already-occupied core area, with the metal-stack conflict resolved, leaves a geometric path.\n")
    w("## Conclusion\n")
    w("1. Placement alone cannot reach the limit (straight R_BIAS width, rail+channel height).")
    w("2. Folded series resistors plus separate NMOS/PMOS wells replace the 2104 um resistor row with ~100 um banks (~0.007 mm^2) and, with the MOS domain unchanged, estimate ~0.06-0.07 mm^2 WITHOUT capacitors (scenarios C/D) -- a feasible-looking but unverified bounded path.")
    w("3. Capacitor area (0.081 mm^2 at 2 fF/um^2) is an evidenced blocker for any side-by-side plan; feasibility hinges on overlaying MiM above the core (met3/met4), which conflicts with the current upper rail band (met2+met3) and needs separate rail/MiM-level planning, or on a spec decision record -- not a loosened spec line here.")
    w("4. Nothing here is DRC/LVS/PEX verified.\n")
    w("## Bounded follow-up scope\n")
    w("- (a) Generate the series-folded resistor with the router (or a tool capability) and confirm LVS series folding (`combine_devices`) or extend the reference; verify DRC/LVS on a resistor-only test block; re-measure R by extraction and a single-corner check.")
    w("- (b) Add the four MiM capacitors (`klt gen cap_array` exists on the host klt 0.7.0, newer than this repo's pin 040f3406) and plan a rail-level change so the 150 pF MiM overlays the core; DRC/LVS it.")
    w("- (c) Refresh the layout to the current schematic (#231), re-mint the area record (append-only), then only compare against the limit. Final DRC/LVS and electrical qualification remain required.\n")
    w("## Reproduce\n")
    w("```bash\npython3 layout/bin/ldo-area-budget.py            # uses recorded probe constants\npython3 layout/bin/ldo-area-budget.py --probe-klt   # one local single-unit klt gen\n```\n")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--area", default="layout/ldo-core/reports/20261008-161046-f4fbb86/area.json")
    ap.add_argument("--floorplan", default="layout/ldo-core/reports/20260924-221821-a947aa8/floorplan.json")
    ap.add_argument("--probe-klt", action="store_true")
    ap.add_argument("--record-id", default=None)
    ap.add_argument("--out-root", default="layout/area-study")
    args = ap.parse_args()
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    rid = args.record_id or f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{head}"
    out = REPO / args.out_root / rid
    if out.exists():
        raise SystemExit(f"{out} exists; study records are append-only (pick a new --record-id)")
    b = build(args)
    out.mkdir(parents=True)
    (out / "budget.json").write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
    (out / "report.md").write_text(render(b, rid))
    print(out)


if __name__ == "__main__":
    main()
