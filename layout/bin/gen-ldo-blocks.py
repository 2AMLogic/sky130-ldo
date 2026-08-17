#!/usr/bin/env python3
"""Generate and compose the sky130 LDO core-regulation-loop layout skeleton
(issue #15) from `klt gen` device blocks, one block per active device in
`design/ldo_3v3in_1v8out.sch` (issue #14) -- see `layout/ldo-core/floorplan.md`
for the grouping/placement rationale this script implements.

Standard library only (matches `layout/bin/render-record.py` and
`sim/bin/corner-run.py`'s no-extra-runtime-dependency convention).

Scope (matching the `2AMLogic/sky130-bandgap`-issue-#15 precedent cited by
this repo's own issue #15): a DRC-clean **placed floorplan skeleton**, one
`klt gen` block per schematic device, positioned by function group via
`klt gen-compose`'s `placement.strategy: "explicit"`. No inter-block routing
and no LVS -- LVS is issue #17's job (the extracted-vs-schematic netlist
compare needs its own reference netlist and the flavor-blindness/tap-net
caveats `layout/README.md` already documents), matching this repo's own
#16 (DRC)/#17 (LVS) split.

`C_COMP` (the schematic's Miller compensation cap) has no corresponding
`klt gen` device generator at this repo's pinned `klt` commit -- there is no
capacitor-array family member alongside `mos_array`/`res_array` despite
`klt extract` recognising a MiM `CapacitorDevice` class. Its value is a
placeholder pending DR-002 in the schematic itself (see
`design/README.md`), so omitting its physical layout here is a documented
gap, not silently dropped scope -- see
https://github.com/2AMLogic/klayout-tools/issues/1117 (filed per
CLAUDE.md's friction protocol) and layout/ldo-core/floorplan.md's "Known
gap" section.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Device specs, transcribed 1:1 from design/ldo_3v3in_1v8out.sch's device
# instances (model/L/W/nf for MOS, model/W/L for resistors). `group` decides
# floorplan row membership -- see floorplan.md.
# ---------------------------------------------------------------------------

MOS_DEVICES: list[dict[str, Any]] = [
    # -- bias/enable-gated reference chain --
    {"id": "M_BIASN1", "group": "bias_enable", "flavor": "nfet", "w_um": 4, "l_um": 1, "fingers": 1},
    {"id": "M_ENN", "group": "bias_enable", "flavor": "nfet", "w_um": 10, "l_um": 0.5, "fingers": 1},
    {"id": "M_BIASN2", "group": "bias_enable", "flavor": "nfet", "w_um": 4, "l_um": 1, "fingers": 1},
    {"id": "M_BIASP1", "group": "bias_enable", "flavor": "pfet", "w_um": 10, "l_um": 1, "fingers": 2},
    {"id": "M_ENP2", "group": "bias_enable", "flavor": "pfet", "w_um": 10, "l_um": 0.5, "fingers": 1},
    # -- 5T OTA error amplifier + its own EN-gated ground return --
    {"id": "M_TAIL", "group": "error_amp", "flavor": "pfet", "w_um": 20, "l_um": 1, "fingers": 4},
    {"id": "M_IN1", "group": "error_amp", "flavor": "pfet", "w_um": 10, "l_um": 1, "fingers": 2},
    {"id": "M_IN2", "group": "error_amp", "flavor": "pfet", "w_um": 10, "l_um": 1, "fingers": 2},
    {"id": "M_MIR1", "group": "error_amp", "flavor": "nfet", "w_um": 10, "l_um": 0.5, "fingers": 2},
    {"id": "M_MIR2", "group": "error_amp", "flavor": "nfet", "w_um": 10, "l_um": 0.5, "fingers": 2},
    {"id": "M_ENN2", "group": "error_amp", "flavor": "nfet", "w_um": 10, "l_um": 0.5, "fingers": 1},
    {"id": "M_ENP", "group": "error_amp", "flavor": "pfet", "w_um": 10, "l_um": 0.5, "fingers": 1},
    # -- output stage: the series pass device --
    {"id": "M_PASS", "group": "output_pass", "flavor": "pfet", "w_um": 100, "l_um": 0.5, "fingers": 25},
]

# res_array's own `flavor` selects the recognised sheet-rho device class
# (see `klt gen --list`'s res_array.flavor description, issue #463
# upstream) -- 'high' maps to res_high_po (R_BIAS), 'xhigh' to res_xhigh_po
# (R_FB_*), matching the schematic's own `model=` fields exactly.
RES_DEVICES: list[dict[str, Any]] = [
    # R_BIAS: single unit, W=0.42 L=1500 res_high_po. Not a matched pair,
    # so dummy=0 -- no common-centroid group to protect.
    {
        "id": "R_BIAS",
        "group": "bias_resistor",
        "flavor": "high",
        "length_um": 1500,
        "width_um": 0.42,
        "num": 1,
        "dummy": 0,
    },
    # R_FB_A/R_FB_B/R_FB_C: three identical W=0.42 L=180 res_xhigh_po unit
    # resistors in series (the divider string) -- one res_array block with
    # num=3 is the more faithful physical rendering of "three identical
    # unit resistors in series" than three separate single-unit blocks,
    # and it is what the divider's own 2:1 ratio construction (two units
    # VOUT->FB, one unit FB->GND) already assumes. dummy=1 (default)
    # protects the matching this divider's ratio accuracy depends on.
    {
        "id": "R_FB",
        "group": "fb_resistor",
        "flavor": "xhigh",
        "length_um": 180,
        "width_um": 0.42,
        "num": 3,
        "dummy": 1,
    },
]

# Row order (bottom to top) and, within each row, left-to-right block order.
# Mirrors design/README.md's own device grouping (bias generator, error
# amplifier, output stage) plus a separate "resistor farm" for the two
# feedback/bias resistor blocks -- see floorplan.md for why those are kept
# out of the compact MOS rows.
ROW_ORDER: list[str] = [
    "bias_resistor",
    "fb_resistor",
    "bias_enable",
    "error_amp",
    "output_pass",
]

ROW_MEMBERS: dict[str, list[str]] = {
    "bias_resistor": ["R_BIAS"],
    "fb_resistor": ["R_FB"],
    "bias_enable": ["M_BIASN1", "M_ENN", "M_BIASN2", "M_BIASP1", "M_ENP2"],
    "error_amp": ["M_TAIL", "M_IN1", "M_IN2", "M_MIR1", "M_MIR2", "M_ENN2", "M_ENP"],
    "output_pass": ["M_PASS"],
}

BLOCK_SPACING_UM = 5.0
ROW_SPACING_UM = 20.0


def _run_klt(klt: str, *args: str) -> dict[str, Any]:
    proc = subprocess.run(
        [klt, *args, "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


def generate_blocks(
    klt: str, pdk_variant: str, out_dir: Path
) -> dict[str, dict[str, Any]]:
    """Run `klt gen` for every device spec, writing `<id>.gds`/`gen.<id>.json`
    to `out_dir`. Returns {id: generator_report}."""
    reports: dict[str, dict[str, Any]] = {}
    for spec in MOS_DEVICES:
        params = {
            "w_um": spec["w_um"],
            "l_um": spec["l_um"],
            "fingers": spec["fingers"],
            "rows": 1,
            "cols": 1,
            "dummy": 0,
            "flavor": spec["flavor"],
            "gate_contact": True,
        }
        report = _run_klt(
            klt,
            "gen",
            "mos_array",
            "--pdk",
            pdk_variant,
            "--cell-name",
            spec["id"],
            "--params",
            json.dumps(params),
            "-o",
            str(out_dir / f"{spec['id']}.gds"),
        )
        (out_dir / f"gen.{spec['id']}.json").write_text(json.dumps(report, indent=2))
        reports[spec["id"]] = report

    for spec in RES_DEVICES:
        params = {
            "length_um": spec["length_um"],
            "width_um": spec["width_um"],
            "num": spec["num"],
            "dummy": spec["dummy"],
            "flavor": spec["flavor"],
        }
        report = _run_klt(
            klt,
            "gen",
            "res_array",
            "--pdk",
            pdk_variant,
            "--cell-name",
            spec["id"],
            "--params",
            json.dumps(params),
            "-o",
            str(out_dir / f"{spec['id']}.gds"),
        )
        (out_dir / f"gen.{spec['id']}.json").write_text(json.dumps(report, indent=2))
        reports[spec["id"]] = report

    return reports


def compute_floorplan(
    reports: dict[str, dict[str, Any]],
) -> tuple[list[str], dict[str, dict[str, float]], dict[str, Any]]:
    """Row-pack every block per ROW_ORDER/ROW_MEMBERS. Returns
    (order, origins_um, floorplan_summary) -- `origins_um` is the
    `placement.origins_um` value `klt gen-compose`'s `"explicit"` strategy
    expects (an *offset* added to each block's own reported bbox_um, not an
    anchor for its (x0, y0) corner -- see gen_compose.py's
    `resolve_explicit_offsets` docstring)."""
    order: list[str] = []
    origins_um: dict[str, dict[str, float]] = {}
    row_summaries: list[dict[str, Any]] = []

    y_base = 0.0
    for row_name in ROW_ORDER:
        members = ROW_MEMBERS[row_name]
        x_cursor: float | None = None
        row_height = 0.0
        row_blocks: list[str] = []
        for block_id in members:
            bbox = reports[block_id]["bbox_um"]
            width = bbox["x1"] - bbox["x0"]
            height = bbox["y1"] - bbox["y0"]
            if x_cursor is None:
                origin_x = -bbox["x0"]
            else:
                origin_x = (x_cursor + BLOCK_SPACING_UM) - bbox["x0"]
            origin_y = y_base - bbox["y0"]
            origins_um[block_id] = {"x": origin_x, "y": origin_y}
            x_cursor = origin_x + bbox["x1"]
            row_height = max(row_height, height)
            order.append(block_id)
            row_blocks.append(block_id)
            _ = width  # (kept for readability of the packing above)
        row_summaries.append(
            {
                "row": row_name,
                "blocks": row_blocks,
                "y_base_um": y_base,
                "height_um": row_height,
                "width_um": (x_cursor if x_cursor is not None else 0.0),
            }
        )
        y_base += row_height + ROW_SPACING_UM

    floorplan_summary = {
        "row_order": ROW_ORDER,
        "block_spacing_um": BLOCK_SPACING_UM,
        "row_spacing_um": ROW_SPACING_UM,
        "rows": row_summaries,
    }
    return order, origins_um, floorplan_summary


def build_compose_request(
    out_dir: Path,
    pdk_variant: str,
    order: list[str],
    origins_um: dict[str, dict[str, float]],
    cell_name: str,
) -> dict[str, Any]:
    return {
        "schema": "klt.gen_compose.request/1",
        "pdk": {"variant": pdk_variant},
        "blocks": [
            {"id": block_id, "generator_report": f"gen.{block_id}.json"}
            for block_id in order
        ],
        "placement": {
            "strategy": "explicit",
            "order": order,
            "origins_um": origins_um,
        },
        "options": {
            "cell_name": cell_name,
            "output": str(out_dir / f"{cell_name}.gds"),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--klt", required=True)
    ap.add_argument("--pdk-variant", required=True)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--cell-name", default="ldo_core")
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    reports = generate_blocks(args.klt, args.pdk_variant, out_dir)
    order, origins_um, floorplan_summary = compute_floorplan(reports)
    (out_dir / "floorplan.json").write_text(json.dumps(floorplan_summary, indent=2))

    request = build_compose_request(
        out_dir, args.pdk_variant, order, origins_um, args.cell_name
    )
    request_path = out_dir / "compose.request.json"
    request_path.write_text(json.dumps(request, indent=2))

    compose_report = _run_klt(args.klt, "gen-compose", str(request_path))
    (out_dir / "compose.json").write_text(json.dumps(compose_report, indent=2))

    print(json.dumps({"floorplan": floorplan_summary, "compose": compose_report}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
