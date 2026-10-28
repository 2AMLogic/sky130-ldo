#!/usr/bin/env python3
"""Four-capacitor core-area budget for the CURRENT schematic (issue #459).

Prices the present topology (48 MOS + 5 resistors + C_COMP/C_CL/C_SS/C_TS)
against the ratified Area row from committed evidence only, and writes a NEW
study directory `layout/area-study/<record-id>/` with `budget.json` and
`report.md`. Nothing under `sim/` or `layout/ldo-core/` is touched; no layout is
drawn, no simulation is run, no klt call is made. The `< 0.1 mm^2` limit is a
read-only constant.

Inputs (all committed):
  - current routed floorplan  (MOS domain measured, all 48 MOS drawn)
  - its area record            (measured footprint, capacitors undrawn)
  - #254 cap-rail demonstrator (drawn stacked-MiM blocks, met3 rail keep-out)
  - #253 folded-resistor geometry and #263 PVT/mismatch record
  - the xschem schematic       (device inventory, capacitor values)

This is a GEOMETRIC ESTIMATE, not a DRC/LVS/PEX-verified result.

Standard library only. Usage:
    python3 layout/bin/ldo-area-budget-4cap.py [--record-id ID]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
LIMIT_UM2 = 0.1e6  # ratified Area row: < 0.1 mm^2 (strict); never altered here
SCHEMATIC = "design/ldo_3v3in_1v8out.sch"

FLOORPLAN = "layout/ldo-core/reports/20261022-231908-56dd87fe/floorplan.json"
AREA = "layout/ldo-core/reports/20261023-170539-a8292e91/area.json"
CAP_DEMO = "layout/cap-rail-demo/reports/20261010-033947-80bc87e/summary.json"
FOLD_GEOM = "layout/folded-res-qual/reports/20261010-033502-704005c/geometry.json"
FOLD_PVT = "layout/folded-res-qual/pvt-reports/20261017-031511-76e0ba72/record.md"

# Single-unit res_array probe constants (klt 0.7.0, flavor xhigh/high, W 0.42):
# bbox length overhead 1.28 um, pad bbox height 2.6 um, min spacing 0.5 um.
# Same recorded constants as ldo-area-budget.py (#246).
SEG_OVERHEAD_UM = 1.28
PAD_BBOX_H_UM = 2.6
MIN_SPACING_UM = 0.5
BANK_WIDTH_UM = 100.0  # #246 / #254 folded-resistor bank column width
CORE_GAP_UM = 2.0  # gap between the MOS domain and the bank column / strip
# Capacitor densities priced (fF per um^2 of MiM footprint): single MiM level
# (extraction law 2.00 fF/um^2) and the stacked pair drawn in #254 (~2x).
DENSITY_SINGLE = 2.0
DENSITY_STACKED_NOMINAL = 4.0


def num(s: str) -> float:
    mult = {"p": 1e-12, "f": 1e-15, "n": 1e-9, "u": 1e-6, "m": 1e-3}
    return float(s[:-1]) * mult[s[-1]] if s[-1] in mult else float(s)


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


def fold_rows(lengths: list[float], bank_w: float) -> dict:
    """Series-fold each body of length L into N=ceil(L/(bank_w-overhead)) rows.
    Conservative pitch = pad bbox height + min spacing (#246)."""
    segs = [math.ceil(length / (bank_w - SEG_OVERHEAD_UM)) for length in lengths]
    pitch = PAD_BBOX_H_UM + MIN_SPACING_UM
    height = sum(segs) * pitch
    return {"bank_width_um": bank_w, "segments_per_resistor": segs, "rows": sum(segs),
            "row_pitch_um": pitch, "bank_height_um": round(height, 3), "bank_area_um2": round(bank_w * height, 1)}


def cap_block_um2(footprint_um2: float, overhead: float) -> float:
    return footprint_um2 * overhead


def build() -> dict:
    fp = json.loads((REPO / FLOORPLAN).read_text())
    ar = json.loads((REPO / AREA).read_text())
    demo = json.loads((REPO / CAP_DEMO).read_text())
    geom = json.loads((REPO / FOLD_GEOM).read_text())
    sch = parse_schematic(REPO / SCHEMATIC)

    # --- inventory: the floorplan must be the CURRENT schematic's MOS set ---
    sch_mos = {k for k, v in sch.items() if v["sym"].endswith("fet_g5v0d10v5")}
    sch_res = {k for k, v in sch.items() if v["sym"].startswith("res_")}
    caps = {k: num(v["value"]) for k, v in sch.items() if v["sym"] == "capa"}
    devs = {d["id"]: d for d in fp["devices"]}
    fp_mos = {k for k, d in devs.items() if d["kind"] == "mos"}
    fp_res = {k for k, d in devs.items() if d["kind"] == "res"}
    if sch_mos != fp_mos or sch_res != fp_res:
        raise SystemExit(f"floorplan is not the current schematic: MOS only in sch {sorted(sch_mos - fp_mos)}, "
                         f"only in layout {sorted(fp_mos - sch_mos)}; res diff {sorted(sch_res ^ fp_res)}")
    if sorted(caps) != ["C_CL", "C_COMP", "C_SS", "C_TS"]:
        raise SystemExit(f"unexpected capacitor set {sorted(caps)}")
    cap_total_f = sum(caps.values())

    # --- measured core (caps undrawn) and MOS domain ---
    W, H = float(ar["width_um"]), float(ar["height_um"])
    xmax = float(ar["bbox_um"][2])
    sub_tie_x = next(t["x_um"] for t in fp["routing"]["body_ties"] if t["kind"] == "substrate_tie")
    mos_x0 = min(d["placed_bbox_um"]["x0"] for d in devs.values() if d["kind"] == "mos")
    if sub_tie_x > mos_x0:
        raise SystemExit("substrate tie lies inside the MOS row; MOS-domain width model invalid")
    core_w = xmax - sub_tie_x
    mos_domain_um2 = core_w * H

    # --- resistors ---
    xh = [devs[k]["length_um"] for k in sorted(fp_res) if devs[k]["flavor"] == "xhigh"]
    rbias_len = devs["R_BIAS"]["length_um"]
    bank = fold_rows(xh, BANK_WIDTH_UM)  # feedback + compensation resistors, bank column
    n4 = next(c for c in geom["cases"] if c["case"] == "rbias_n4")["variants"]["folded"]["device_bbox_um"]
    strip_w, strip_h = n4["x1"] - n4["x0"], n4["y1"] - n4["y0"]
    rbias_straight_w = devs["R_BIAS"]["placed_bbox_um"]["x1"]

    # --- rectangle with folded resistors (R_BIAS N=4 strip) ---
    rect_w = core_w + CORE_GAP_UM + BANK_WIDTH_UM
    if strip_w > rect_w:
        raise SystemExit("R_BIAS N=4 strip wider than the core rectangle")
    if bank["bank_height_um"] > H:
        raise SystemExit("resistor bank taller than the core height")
    rect_no_strip_um2 = rect_w * H
    strip_um2 = (strip_h + CORE_GAP_UM) * rect_w
    rect_um2 = rect_no_strip_um2 + strip_um2

    # --- capacitor blocks, drawn in #254 (stacked MiM) ---
    t = demo["totals"]
    keepout = (lambda z: (z["x1_um"] - z["x0_um"]) * (z["y1_um"] - z["y0_um"]))(demo["met3_rail_zone"])
    stacked_block = t["cap_block_um2"]
    stacked_fp = t["mim_footprint_um2"]
    overhead = stacked_block / stacked_fp
    stacked_density = cap_total_f * 1e15 / stacked_fp  # measured effective, fF/um^2 of footprint
    single_block = demo["single_mim_level_counterfactual"]["block_area_um2"]

    usable = rect_um2 - keepout
    scen: dict[str, dict] = {}

    def scenario(name: str, block: float, desc: str) -> None:
        fits = block <= usable
        total = rect_um2 if fits else rect_um2 + (block - usable)
        scen[name] = {"description": desc, "cap_block_um2": round(block, 1), "overlay_usable_um2": round(usable, 1),
                      "fits_overlay": fits, "overlay_fill_fraction": block / usable,
                      "total_um2": round(total, 1), "total_mm2": round(total / 1e6, 5), "below_limit": total < LIMIT_UM2,
                      "margin_fraction": (LIMIT_UM2 - total) / LIMIT_UM2}

    scenario("caps_overlay_stacked_4fF_drawn", stacked_block,
             f"stacked MiM as drawn in #254 (effective {stacked_density:.2f} fF/um^2 of footprint, block overhead x{overhead:.3f})")
    scenario("caps_overlay_nominal_4fF", cap_block_um2(cap_total_f * 1e15 / DENSITY_STACKED_NOMINAL, overhead),
             "nominal 4 fF/um^2 footprint density with the same block overhead")
    scenario("caps_overlay_single_2fF_drawn_counterfactual", single_block,
             "single MiM level (2 fF/um^2), #254 counterfactual block area, overlay attempted")
    scenario("caps_overlay_single_2fF_nominal", cap_block_um2(cap_total_f * 1e15 / DENSITY_SINGLE, overhead),
             "nominal 2 fF/um^2 footprint density with the stacked-block overhead")

    # --- sensitivity of the verdict to the capacitor budget (drawn stacked) ---
    # Largest total C whose block still fits the overlay, and the largest for
    # which rectangle + overflow stays below the limit.
    fit_c_f = usable / overhead * stacked_density * 1e-15
    limit_block = usable + (LIMIT_UM2 - rect_um2)
    limit_c_f = limit_block / overhead * stacked_density * 1e-15
    c_comp = caps["C_COMP"]
    sensitivity = {
        "dominant_capacitor": "C_COMP", "c_comp_fraction_of_total": c_comp / cap_total_f,
        "max_total_c_that_fits_overlay_pf": round(fit_c_f * 1e12, 1),
        "max_total_c_below_limit_pf": round(limit_c_f * 1e12, 1),
        "headroom_factor_overlay": round(fit_c_f / cap_total_f, 3),
        "headroom_factor_below_limit": round(limit_c_f / cap_total_f, 3),
        "scales_with": "capacitor total at fixed density; rectangle area is unchanged until the overlay is full",
    }

    # --- R_BIAS sensitivity: straight body forces the single-rectangle width ---
    straight_um2 = rbias_straight_w * H
    straight = {
        "min_width_um": rbias_straight_w, "area_at_current_height_um2": round(straight_um2, 1),
        "area_at_current_height_mm2": round(straight_um2 / 1e6, 5),
        "max_height_for_limit_um": LIMIT_UM2 / rbias_straight_w,
        "channel_plus_rail_bands_um": round(H - fp["row_height_um"], 3),
        "fails_regardless_of_caps": True,
    }

    pvt = {"record": FOLD_PVT,
           "rbias_n4": "deterministic worst +0.2226 % < 0.2462 % (ok), M1 ok, M2 sigma ratio 1.1316 > 1.1 (FAIL); not QUALIFIED; j4 sensitivity flips the verdict",
           "rbias_any_n": "no segment count 2..16 is QUALIFIED (M2 fails at N=2: 1.1114; N>=5 fails the deterministic criterion)",
           "r_fb_a": "qualified N=2..6 (R_FB_A); R_FB_B/C fold identically so the divider ratio is preserved to first order",
           "r_cz": "52 um body < bank width: one row, unfolded"}

    return {
        "schema_version": 1, "issue": 459, "parent": 458,
        "units": {"length": "um", "area": "um^2 (mm^2 = um^2 / 1e6)", "capacitance": "F"},
        "limit_um2": LIMIT_UM2, "limit_comparison": "area < limit (strict); target unchanged, read only",
        "geometry_convention": "bounding rectangle width x height, as in the area record",
        "sources": {
            "floorplan": FLOORPLAN, "area_record": AREA, "area_record_gds_sha256": ar["gds"]["sha256"],
            "cap_demo": CAP_DEMO, "folded_geometry": FOLD_GEOM, "folded_pvt": FOLD_PVT, "schematic": SCHEMATIC,
            "schematic_git_last_commit": subprocess.run(
                ["git", "-C", str(REPO), "log", "-1", "--format=%H", "--", SCHEMATIC],
                capture_output=True, text=True).stdout.strip(),
            "repo_head": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        },
        "inventory": {"mos": len(sch_mos), "resistors": len(sch_res), "capacitors_f": caps, "caps_total_f": cap_total_f,
                      "floorplan_matches_schematic": True, "caps_drawn_in_core_layout": False},
        "measured_core_no_caps": {"width_um": W, "height_um": H, "area_um2": W * H, "ratio_to_limit": W * H / LIMIT_UM2},
        "mos_domain": {"x_from_substrate_tie_um": sub_tie_x, "width_um": core_w, "height_um": H,
                       "area_um2": round(mos_domain_um2, 1),
                       "source": "measured: all 48 MOS drawn in the current floorplan (no estimate of added/removed MOS)"},
        "resistors": {"xhigh_bank": bank, "r_bias_n4_strip": {"width_um": strip_w, "height_um": strip_h, "gap_um": CORE_GAP_UM,
                                                              "added_area_um2": round(strip_um2, 1)},
                      "r_bias_straight": straight, "qualification": pvt},
        "rectangle": {"width_um": rect_w, "height_um": H, "without_rbias_strip_um2": round(rect_no_strip_um2, 1),
                      "with_rbias_n4_strip_um2": round(rect_um2, 1), "with_rbias_n4_strip_mm2": round(rect_um2 / 1e6, 5),
                      "assumption": "MOS domain + 2 um + 100 um resistor-bank column; R_BIAS N=4 strip spans the width; caps overlay occupied core area"},
        "capacitors": {"met3_rail_keepout_um2": round(keepout, 1), "stacked_block_um2_drawn": stacked_block,
                       "stacked_footprint_um2_drawn": stacked_fp, "block_overhead_factor": overhead,
                       "effective_density_ff_per_um2": stacked_density,
                       "single_level_block_um2_counterfactual": single_block},
        "scenarios": scen, "sensitivity_to_capacitor_budget": sensitivity,
        "verdict": {
            "geometric_budget_mm2": scen["caps_overlay_stacked_4fF_drawn"]["total_mm2"],
            "feasible_under_limit_if": "R_BIAS is folded at N=4 (caps overlaid; stacked MiM ~4 fF/um^2 as drawn in #254 gives the full margin)",
            "not_feasible_if": ["R_BIAS stays straight (floor %.4f mm^2 at the current height)" % (straight_um2 / 1e6)],
            "thin_margin_if": "only a single MiM level (2 fF/um^2) is allowed: 0.094-0.096 mm^2",
            "open_gate": "R_BIAS N=4 fold is not QUALIFIED by the #263 record (M2 sigma-ratio gate)",
        },
        "claims_verified": "none: geometric estimate from committed records; no DRC/LVS/PEX on a full core with capacitors",
    }


def render(b: dict, rid: str) -> str:
    L: list[str] = []
    w = L.append
    m, mos, r, rect, c = b["measured_core_no_caps"], b["mos_domain"], b["resistors"], b["rectangle"], b["capacitors"]
    s, sens, v, src = b["scenarios"], b["sensitivity_to_capacitor_budget"], b["verdict"], b["sources"]
    st = r["r_bias_straight"]
    w(f"# LDO core area budget with all four capacitors: {rid}\n")
    w("Issue #459 (part of #458, T1 item 5 `area`). **Geometric estimate only** -- no DRC/LVS/PEX on a full core with capacitors; the ratified Area row (< 0.1 mm^2, strict) is unchanged and is not claimed met.\n")
    w("## Sources\n")
    w(f"- Current routed floorplan `{src['floorplan']}`: {b['inventory']['mos']} MOS + {b['inventory']['resistors']} resistors, identical to the current schematic's device set (checked by the script); the MOS domain is **measured**, not estimated.")
    w(f"- Area record `{src['area_record']}` (GDS sha256 `{src['area_record_gds_sha256'][:16]}...`): {m['width_um']:.2f} x {m['height_um']:.2f} um = {m['area_um2']/1e6:.4f} mm^2, capacitors undrawn.")
    w(f"- Capacitors: `{src['cap_demo']}` (#254 drawn stacked-MiM blocks, DRC/LVS clean on that demonstrator only). Resistors: `{src['folded_geometry']}` (#253) and `{src['folded_pvt']}` (#263). Schematic `{src['schematic']}` at `{src['schematic_git_last_commit'][:7]}`; repo HEAD `{src['repo_head'][:7]}`.\n")
    w("## Budget\n")
    w("| item | um^2 | basis |\n|---|---|---|")
    w(f"| MOS domain ({mos['width_um']:.2f} x {mos['height_um']:.2f} um, substrate tie through pass device) | {mos['area_um2']:.0f} | measured, all 48 MOS |")
    w(f"| 2 um gap + {r['xhigh_bank']['bank_width_um']:.0f} um bank column (width {rect['width_um']:.2f} um total) | {rect['without_rbias_strip_um2']-mos['area_um2']:.0f} | folded `R_FB_A/B/C`, `R_CZ`: {r['xhigh_bank']['rows']} rows, bank height {r['xhigh_bank']['bank_height_um']:.1f} um <= core height |")
    w(f"| `R_BIAS` N=4 strip ({r['r_bias_n4_strip']['width_um']:.2f} x {r['r_bias_n4_strip']['height_um']:.2f} um + 2 um gap, full width) | {r['r_bias_n4_strip']['added_area_um2']:.0f} | #253 geometry |")
    w(f"| **Rectangle before capacitors** | **{rect['with_rbias_n4_strip_um2']:.0f}** ({rect['with_rbias_n4_strip_mm2']:.4f} mm^2) | |")
    w(f"| Met3 rail keep-out above the pass device (no MiM) | {c['met3_rail_keepout_um2']:.0f} | #254 |")
    w(f"| Overlay area usable for MiM | {s['caps_overlay_stacked_4fF_drawn']['overlay_usable_um2']:.0f} | rectangle - keep-out |\n")
    w("Capacitors C_COMP 150 pF, C_SS 10 pF, C_CL 1 pF, C_TS 1 pF (162 pF) are overlaid on occupied core area, so they add nothing to the rectangle while they fit.\n")
    w("## Result at 2 and 4 fF/um^2\n")
    w("| scenario | cap block um^2 | fills overlay | total mm^2 | margin | < 0.1? |\n|---|---|---|---|---|---|")
    for k, d in s.items():
        w(f"| `{k}`: {d['description']} | {d['cap_block_um2']:.0f} | {d['overlay_fill_fraction']*100:.0f}% | {d['total_mm2']:.4f} | {d['margin_fraction']*100:.1f}% | {'yes' if d['below_limit'] else 'no'} |")
    w("\nThe 4 fF/um^2 rows are the stacked met3-met4-met5 pair drawn and extracted in #254 (measured effective "
      f"{c['effective_density_ff_per_um2']:.2f} fF/um^2 of footprint; block overhead x{c['block_overhead_factor']:.3f} for straps/taps). "
      "The 2 fF/um^2 rows are the single-MiM-level case: the block exceeds the overlay (114-117%) and the overflow lands beside the core, which still leaves the total just under the limit (margin 3.8-5.6%).\n")
    w("## Sensitivity\n")
    w(f"- Dominant capacitor: `C_COMP` = {sens['c_comp_fraction_of_total']*100:.0f}% of the capacitance. The rectangle does not move with capacitor value until the overlay is full.")
    w(f"- At the drawn stacked density the overlay holds {sens['max_total_c_that_fits_overlay_pf']:.0f} pF ({sens['headroom_factor_overlay']:.2f}x the 162 pF); the total stays below 0.1 mm^2 up to {sens['max_total_c_below_limit_pf']:.0f} pF ({sens['headroom_factor_below_limit']:.2f}x).")
    w(f"- `R_BIAS` straight (no fold): the rectangle is at least {st['min_width_um']:.1f} um wide; at the current {m['height_um']:.2f} um height that is {st['area_at_current_height_mm2']:.4f} mm^2, and the limit would need a height under {st['max_height_for_limit_um']:.1f} um while channel + rail bands alone are {st['channel_plus_rail_bands_um']:.1f} um. This fails with or without capacitors.\n")
    w("## Verdict\n")
    w(f"**Feasible under 0.1 mm^2 on paper: {v['geometric_budget_mm2']:.4f} mm^2** ({s['caps_overlay_stacked_4fF_drawn']['margin_fraction']*100:.1f}% margin), with all four capacitors, folded resistors and the measured current MOS domain. It holds only if:\n")
    w("1. the capacitors are overlaid on the core. At the drawn stacked density (~4 fF/um^2) the margin is 16.9%; at 2 fF/um^2 (single level) the overflow beside the core still keeps the total under the limit but the margin shrinks to 3.8-5.6%, thin for an estimate with no full-core routing; and")
    w("2. `R_BIAS` is folded to N=4 segments. #263 does **not** qualify that fold: the deterministic and mean-shift gates pass (worst +0.2226 % < 0.2462 %), but the mismatch gate M2 fails (sigma ratio 1.1316 > 1.1, already 1.1114 at N=2), and the 4x-joint sensitivity flips the deterministic verdict. No `R_BIAS` segment count is QUALIFIED. With `R_BIAS` straight the measured floor is "
      f"{st['area_at_current_height_mm2']:.4f} mm^2.\n")
    w("So the answer is a conditional go, not a floor above 0.1 mm^2: the floor is set by the `R_BIAS` fold qualification, which is a design question (accept the N=4 fold's mismatch, or re-topologise the bias) and not an area measurement. No decision record is drafted here because the area itself does not force one; if the `R_BIAS` fold is finally rejected the floor becomes the straight-resistor figure above and a floor DR is then required. The Area row is unchanged. Nothing here is DRC/LVS/PEX verified for the full core.\n")
    w("## Not established\n")
    w("- A drawn full core with capacitors: the layout still omits them, and the overlay is checked only in the #254 demonstrator.")
    w("- Electrical requalification (loop stability, PSRR, start-up) with MiM parasitics and folded-resistor joints.")
    w("- MiM-over-MOS routing and coupling in the real core (the demonstrator has no MOS); the bank column height was checked against the core height only.\n")
    w("## Reproduce\n")
    w(f"```bash\npython3 layout/bin/ldo-area-budget-4cap.py --record-id {rid}   # reads only the committed inputs above\n```\n")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record-id", default=None)
    ap.add_argument("--out-root", default="layout/area-study")
    args = ap.parse_args()
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    rid = args.record_id or f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{head}"
    out = REPO / args.out_root / rid
    if out.exists():
        raise SystemExit(f"{out} exists; study records are append-only (pick a new --record-id)")
    b = build()
    out.mkdir(parents=True)
    (out / "budget.json").write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
    (out / "report.md").write_text(render(b, rid))
    print(out)


if __name__ == "__main__":
    main()
