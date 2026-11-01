#!/usr/bin/env python3
"""Four-capacitor core-area budget for the DR-013 bias candidate (issue #467).

Extends `ldo-area-budget-4cap.py` (#459) without editing it or its record. The
DR-013 candidate replaces `R_BIAS` (res_high_po W=0.42 L=1500, straight floor
0.2765 mm^2) by `res_xhigh_po` W=0.42 L=211: a single straight resistor, no fold,
so the #263 fold gates (M1/M2, joint equivalence) do not apply to it. Everything
else -- the measured 48-MOS domain, the xhigh bank column, the #254 capacitor
blocks -- is the #459 input set, re-read from the same committed files.

Writes a NEW study directory `layout/area-study/<record-id>/` (`budget.json`,
`report.md`). No layout is drawn, no simulation is run. GEOMETRIC ESTIMATE only:
no DRC/LVS/PEX on a full core. The `< 0.1 mm^2` limit is a read-only constant.

Standard library only. Usage:
    python3 layout/bin/ldo-area-budget-dr013.py [--record-id ID]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("budget4cap", HERE / "ldo-area-budget-4cap.py")
b4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b4)

REPO = b4.REPO
CAND_L_UM = 211.0  # res_xhigh_po W=0.42 L=211: ~1.22 Mohm, matches res_high_po L=1500 (sim/bias-retopo grid)


def build() -> dict:
    base = b4.build()
    H = base["rectangle"]["height_um"]
    rect_w = base["rectangle"]["width_um"]
    n4 = base["resistors"]["r_bias_n4_strip"]
    seg_w = CAND_L_UM + b4.SEG_OVERHEAD_UM
    # Upper bound: charge the candidate the same strip height + gap and the full
    # rectangle width as the #459 N=4 strip (the real straight body is
    # seg_w wide, so the strip is conservative).
    strip_h = n4["height_um"]
    if seg_w > rect_w:
        raise SystemExit("candidate R_BIAS body wider than the core rectangle")
    strip_um2 = (strip_h + b4.CORE_GAP_UM) * rect_w
    rect_um2 = rect_w * H + strip_um2
    keepout = base["capacitors"]["met3_rail_keepout_um2"]
    usable = rect_um2 - keepout
    scen = {}
    for name, s in base["scenarios"].items():
        block = s["cap_block_um2"]
        fits = block <= usable
        total = rect_um2 if fits else rect_um2 + (block - usable)
        scen[name] = {"description": s["description"], "cap_block_um2": block, "overlay_usable_um2": round(usable, 1),
                      "fits_overlay": fits, "overlay_fill_fraction": block / usable, "total_um2": round(total, 1),
                      "total_mm2": round(total / 1e6, 5), "below_limit": total < b4.LIMIT_UM2,
                      "margin_fraction": (b4.LIMIT_UM2 - total) / b4.LIMIT_UM2}
    return {
        "schema_version": 1, "issue": 467, "decision_record": "DR-013",
        "limit_um2": b4.LIMIT_UM2, "limit_comparison": "area < limit (strict); target unchanged, read only",
        "candidate": {"r_bias": "res_xhigh_po W=0.42 L=%g (single straight body, no fold)" % CAND_L_UM,
                      "body_width_um": seg_w, "strip_height_um": strip_h, "gap_um": b4.CORE_GAP_UM,
                      "strip_charged_um2": round(strip_um2, 1),
                      "strip_model": "upper bound: full-width strip at the #459 N=4 strip height",
                      "fold_gates": "N/A: one segment, nothing to fold; #263 M1/M2/joint criteria compare folded vs unsplit"},
        "rectangle": {"width_um": rect_w, "height_um": H, "area_um2": round(rect_um2, 1), "area_mm2": round(rect_um2 / 1e6, 5)},
        "scenarios": scen,
        "baseline_459": {"record": "layout/area-study/20261028-study-459", "r_bias_straight_floor_mm2": base["resistors"]["r_bias_straight"]["area_at_current_height_mm2"],
                         "stacked_total_mm2": base["scenarios"]["caps_overlay_stacked_4fF_drawn"]["total_mm2"]},
        "sources": base["sources"],
        "sources_note": "inputs identical to #459 (same committed floorplan/area/cap-demo/fold records)",
        "claims_verified": "none: geometric estimate from committed records; no DRC/LVS/PEX on a full core with capacitors",
    }


def render(b: dict, rid: str) -> str:
    c = b["candidate"]
    out = [f"# LDO core area budget, DR-013 bias candidate: {rid}", "",
           "Issue #467 (DR-013). **Geometric estimate only** -- no DRC/LVS/PEX on a full core with capacitors. "
           "The ratified Area row (< 0.1 mm^2, strict) is unchanged and is not claimed met. "
           "Extends the #459 study (`layout/area-study/20261028-study-459`, not edited): same inputs, only `R_BIAS` changes.", "",
           "## Candidate", "",
           f"- `R_BIAS`: {c['r_bias']}; body {c['body_width_um']:.2f} um wide.",
           f"- Charged to the budget as a full-width strip of height {c['strip_height_um']:.2f} um + {c['gap_um']:g} um gap "
           f"= {c['strip_charged_um2']:.0f} um^2 ({c['strip_model']}).",
           f"- {c['fold_gates']}.",
           f"- Rectangle before capacitors: {b['rectangle']['width_um']:.2f} x {b['rectangle']['height_um']:.2f} um = "
           f"**{b['rectangle']['area_um2']:.0f} um^2 ({b['rectangle']['area_mm2']:.4f} mm^2)**.", "",
           "## Result", "",
           "| scenario | cap block um^2 | fills overlay | total mm^2 | margin | < 0.1? |", "|---|---|---|---|---|---|"]
    for k, s in b["scenarios"].items():
        out.append(f"| `{k}` | {s['cap_block_um2']:.0f} | {100 * s['overlay_fill_fraction']:.0f}% | {s['total_mm2']:.4f} | "
                   f"{100 * s['margin_fraction']:.1f}% | {'yes' if s['below_limit'] else 'NO'} |")
    out += ["", f"Reference (#459, N=4 fold, not qualified): {b['baseline_459']['stacked_total_mm2']} mm^2 stacked; "
            f"straight `res_high_po` floor {b['baseline_459']['r_bias_straight_floor_mm2']} mm^2.", "",
            "## Not established", "",
            "- A drawn full core with capacitors (DRC/LVS/PEX); MiM-over-MOS coupling; the real straight-body routing.",
            "- The area figure equals #459's because `R_BIAS` is charged the same full-width strip; the candidate removes the "
            "fold qualification dependency, it does not shrink the rectangle.", "",
            "## Reproduce", "", "```bash", f"python3 layout/bin/ldo-area-budget-dr013.py --record-id {rid}", "```", ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record-id", default=None)
    ap.add_argument("--out-root", default="layout/area-study")
    args = ap.parse_args()
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    rid = args.record_id or f"dr013-{head}"
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
