#!/usr/bin/env python3
"""Generate the resistor-only folded-series qualification blocks (issue #253).

The #246 area study (`layout/area-study/20261009-study-246/report.md`) found
that the straight `R_BIAS` body alone makes the LDO core >= 1500.8 um wide,
and proposed folding each long resistor into N equal straight series segments
stacked as rows of a bank. This script draws that proposal -- in isolation,
never inside the full core -- so its DRC, LVS and electrical behaviour can be
qualified before any floorplan change.

For every case in `layout/folded-res-qual/cases.json` it writes up to four
GDS streams, each its own top cell:

* ``<case>_unsplit`` -- the schematic resistor drawn exactly as the current
  core flow draws it (`klt gen res_array`, ``num=1``, full schematic ``L``).
  The baseline the folded bank is compared against.
* ``<case>_folded``  -- ``klt gen res_array`` with ``num=N, rows=N`` (one
  ``L/N`` segment per row; `res_array`'s boustrophedon order alternates the
  A/B ends row to row) plus caller-owned li1 series straps joining segment
  ``i``'s B pad to segment ``i+1``'s A pad. `res_array` itself never chains
  its units (they are independent matched elements); the series connection
  is the generic gap #246 already filed as 2AMLogic/klayout-tools#2997, so
  it is drawn here with `klayout.db` rather than re-filed.
* ``<case>_broken``  -- the folded bank with one series strap deliberately
  omitted: the LVS negative control (an open chain must not match).
* ``<case>_unmerged`` -- the folded bank (all straps) with the per-row
  psdm/rpm/urpm markers left exactly as `res_array` draws them, i.e. without
  `fill_bank_markers`. The DRC control that shows *why* the folded stream
  merges its markers: the PDK signoff runset is expected to flag marker
  spacing between rows here and not on ``<case>_folded``.

Each stream also gets one substrate tie (a `tap` square with a licon + li1
pad, the same idiom `gen-ldo-blocks.py`'s `body_tie` uses) labelled ``SUB``,
so the resistor bulk lands on a drawn, named net, and li1 labels ``A``/``B``
on the two chain-end pads.

Logical resistance is preserved by construction: every segment keeps the
schematic ``W`` and the segment body lengths sum to the schematic ``L``. No
schematic value is changed. Whether that *drawn* equality also means
*electrical* equality is exactly what the rest of the flow measures.

Runs under `layout/.venv` (needs `klayout.db`, a `klt` dependency).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from _record_common import run_klt_json

#: li1 drawing / label, licon, tap -- sky130 GDS layer numbers, the same ones
#: `gen-ldo-blocks.py` draws its routing and body ties on.
LI1 = (67, 20)
LI1_LABEL = (67, 5)
LICON = (66, 44)
TAP = (65, 44)

#: Substrate tie geometry -- copied from `gen-ldo-blocks.py`'s `body_tie`
#: (1.5 um tap square, one 0.17 um licon, 0.42 um li1 pad).
TAP_SIDE_UM = 1.5
LICON_UM = 0.17
TIE_PAD_UM = 0.42
#: Clearance from the bank's bounding box to the tie's tap square.
TIE_GAP_UM = 1.0

#: Implant / resistor-marker layers `res_array` draws per unit body on sky130
#: (psdm, rpm for `high`, urpm for `xhigh`). Drawn per row they leave a
#: row-pitch slot between adjacent bodies that the PDK's own signoff deck
#: flags (rpm/urpm minimum width and spacing) -- see `fill_bank_markers`.
BANK_MARKER_LAYERS = [(94, 20), (86, 20), (79, 20)]


class GenError(RuntimeError):
    pass


def segment_length_um(total_l_um: float, segments: int) -> float:
    """Equal-segment body length. Rejects a split that is not exact on the
    0.005 um manufacturing grid, so the drawn sum always equals the
    schematic ``L`` rather than drifting by a rounding residue per segment."""
    if segments < 1:
        raise GenError(f"segments must be >= 1, got {segments}")
    seg = total_l_um / segments
    grid = 0.005
    if abs(round(seg / grid) * grid - seg) > 1e-9:
        raise GenError(
            f"L={total_l_um} um / N={segments} = {seg} um is not on the "
            f"{grid} um grid -- pick an N that divides L exactly"
        )
    return round(seg / grid) * grid


def plan_series_straps(ports: list[dict[str, Any]], segments: int) -> list[dict[str, Any]]:
    """Pair segment ``i``'s B pad with segment ``i+1``'s A pad.

    `res_array` names its pads ``R<i>_A``/``R<i>_B``. With ``rows=num`` each
    row holds exactly one unit and the boustrophedon order puts ``R<i>_B``
    and ``R<i+1>_A`` at the same x on adjacent rows -- asserted here rather
    than assumed, so a future generator that orders units differently fails
    loudly instead of drawing a diagonal short.
    """
    by_name = {p["name"]: p for p in ports}
    straps: list[dict[str, Any]] = []
    for i in range(segments - 1):
        b = by_name[f"R{i}_B"]
        a = by_name[f"R{i + 1}_A"]
        if abs(b["x_um"] - a["x_um"]) > 1e-6:
            raise GenError(
                f"R{i}_B (x={b['x_um']}) and R{i + 1}_A (x={a['x_um']}) are not "
                "vertically aligned -- res_array's row order is not the "
                "boustrophedon this strap plan assumes"
            )
        if b["layer"]["layer"] != LI1[0] or a["layer"]["layer"] != LI1[0]:
            raise GenError("res_array pads are not on li1 -- strap plan assumes li1 pads")
        straps.append(
            {
                "joint": i,
                "from": f"R{i}_B",
                "to": f"R{i + 1}_A",
                "x_um": b["x_um"],
                "y0_um": min(a["y_um"], b["y_um"]),
                "y1_um": max(a["y_um"], b["y_um"]),
                "pad_w_um": min(a["width_um"], b["width_um"]),
            }
        )
    return straps


def chain_ends(ports: list[dict[str, Any]], segments: int) -> tuple[dict, dict]:
    by_name = {p["name"]: p for p in ports}
    return by_name["R0_A"], by_name[f"R{segments - 1}_B"]


def fill_bank_markers(layout: Any, bank: Any, top: Any) -> list[dict[str, Any]]:
    """Merge each per-row marker layer into one rectangle over the bank.

    Only fills the slots *between* rows (every row shares one x span), so it
    adds no marker over anything that is not already a resistor body's row,
    and it never touches the body layers the extraction deck recognises a
    device by (poly 66/20 + id marker 66/13), so extraction is unchanged.
    Returns the boxes drawn, for geometry.json.
    """
    import klayout.db as kdb

    drawn: list[dict[str, Any]] = []
    for ln, dt in BANK_MARKER_LAYERS:
        idx = layout.find_layer(ln, dt)
        if idx is None:
            continue
        region_bbox = bank.dbbox_per_layer(idx)
        if region_bbox.empty():
            continue
        top.shapes(idx).insert(region_bbox)
        drawn.append(
            {
                "layer": f"{ln}/{dt}",
                "x0": region_bbox.left,
                "y0": region_bbox.bottom,
                "x1": region_bbox.right,
                "y1": region_bbox.top,
            }
        )
    return drawn


def compose(
    src_gds: Path,
    out_gds: Path,
    cell_name: str,
    ports: list[dict[str, Any]],
    segments: int,
    straps: list[dict[str, Any]],
    bank_bbox: dict[str, float],
    merge_markers: bool = False,
) -> dict[str, Any]:
    """Wrap the generated bank in ``cell_name`` with straps, tie and labels."""
    import klayout.db as kdb

    layout = kdb.Layout()
    layout.read(str(src_gds))
    bank = layout.top_cell()
    top = layout.create_cell(cell_name)
    top.insert(kdb.DCellInstArray(bank.cell_index(), kdb.DTrans()))

    li1 = layout.layer(*LI1)
    li1_label = layout.layer(*LI1_LABEL)
    licon = layout.layer(*LICON)
    tap = layout.layer(*TAP)

    strap_area = 0.0
    for s in straps:
        half = s["pad_w_um"] / 2.0
        box = kdb.DBox(s["x_um"] - half, s["y0_um"] - half, s["x_um"] + half, s["y1_um"] + half)
        top.shapes(li1).insert(box)
        strap_area += box.width() * box.height()

    markers = fill_bank_markers(layout, bank, top) if merge_markers else []

    pre_tie = top.dbbox()

    a_end, b_end = chain_ends(ports, segments)
    top.shapes(li1_label).insert(kdb.DText("A", kdb.DTrans(kdb.DVector(a_end["x_um"], a_end["y_um"]))))
    top.shapes(li1_label).insert(kdb.DText("B", kdb.DTrans(kdb.DVector(b_end["x_um"], b_end["y_um"]))))

    # Substrate tie below the bank, left-aligned with it.
    tx = bank_bbox["x0"] + TAP_SIDE_UM / 2.0
    ty = bank_bbox["y0"] - TIE_GAP_UM - TAP_SIDE_UM / 2.0
    half_tap = TAP_SIDE_UM / 2.0
    top.shapes(tap).insert(kdb.DBox(tx - half_tap, ty - half_tap, tx + half_tap, ty + half_tap))
    top.shapes(licon).insert(
        kdb.DBox(tx - LICON_UM / 2, ty - LICON_UM / 2, tx + LICON_UM / 2, ty + LICON_UM / 2)
    )
    top.shapes(li1).insert(
        kdb.DBox(tx - TIE_PAD_UM / 2, ty - TIE_PAD_UM / 2, tx + TIE_PAD_UM / 2, ty + TIE_PAD_UM / 2)
    )
    top.shapes(li1_label).insert(kdb.DText("SUB", kdb.DTrans(kdb.DVector(tx, ty))))

    # Rename the generated bank cell so the streams of a case never
    # share a cell name, then write only the composed hierarchy.
    bank.name = f"{cell_name}_bank"
    layout.write(str(out_gds))

    full = top.dbbox()
    return {
        "top_cell": cell_name,
        "bbox_without_tie_um": {
            "x0": pre_tie.left, "y0": pre_tie.bottom, "x1": pre_tie.right, "y1": pre_tie.top,
        },
        "bbox_with_tie_um": {"x0": full.left, "y0": full.bottom, "x1": full.right, "y1": full.top},
        "merged_marker_boxes": markers,
        "strap_count": len(straps),
        "strap_li1_area_um2": round(strap_area, 6),
        "tie": {"x_um": tx, "y_um": ty, "tap_side_um": TAP_SIDE_UM},
        "chain_ends": {"A": a_end["name"], "B": b_end["name"]},
    }


def bbox_dims(bbox: dict[str, float]) -> dict[str, float]:
    w = bbox["x1"] - bbox["x0"]
    h = bbox["y1"] - bbox["y0"]
    return {"width_um": round(w, 6), "height_um": round(h, 6), "area_um2": round(w * h, 6)}


def generate_case(klt: str, pdk: str, out_dir: Path, case: dict[str, Any]) -> dict[str, Any]:
    name = case["name"]
    flavor = case["flavor"]
    total_l = float(case["l_um"])
    w = float(case["w_um"])
    n = int(case["segments"])
    seg_l = segment_length_um(total_l, n)
    scratch = out_dir / "gen"
    scratch.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "case": name,
        "schematic_device": case["schematic_device"],
        "flavor": flavor,
        "schematic_l_um": total_l,
        "schematic_w_um": w,
        "segments": n,
        "segment_l_um": seg_l,
        "drawn_body_l_sum_um": round(seg_l * n, 6),
        "variants": {},
    }

    # --- unsplit baseline (exactly what the core flow draws) --------------
    unsplit_params = {"length_um": total_l, "width_um": w, "num": 1, "dummy": 0, "flavor": flavor}
    un_raw = scratch / f"{name}_unsplit_raw.gds"
    un_rep = run_klt_json(
        klt, "gen", "res_array", "--pdk", pdk, "--cell-name", f"{name}_unsplit_raw",
        "--params", json.dumps(unsplit_params), "-o", str(un_raw),
        error_cls=GenError,
    )
    (scratch / f"gen.{name}_unsplit.json").write_text(json.dumps(un_rep, indent=2))
    un_meta = compose(un_raw, out_dir / f"{name}_unsplit.gds", f"{name}_unsplit",
                      un_rep["ports"], 1, [], un_rep["bbox_um"])
    result["variants"]["unsplit"] = {
        "gds": f"{name}_unsplit.gds",
        "klt_gen_params": unsplit_params,
        "device_bbox_um": un_rep["bbox_um"],
        "device_bbox": bbox_dims(un_rep["bbox_um"]),
        **un_meta,
    }

    # --- folded bank + its open-chain negative control --------------------
    folded_params = {"length_um": seg_l, "width_um": w, "num": n, "rows": n, "dummy": 0, "flavor": flavor}
    fo_raw = scratch / f"{name}_folded_raw.gds"
    fo_rep = run_klt_json(
        klt, "gen", "res_array", "--pdk", pdk, "--cell-name", f"{name}_folded_raw",
        "--params", json.dumps(folded_params), "-o", str(fo_raw),
        error_cls=GenError,
    )
    (scratch / f"gen.{name}_folded.json").write_text(json.dumps(fo_rep, indent=2))
    straps = plan_series_straps(fo_rep["ports"], n)

    fo_meta = compose(fo_raw, out_dir / f"{name}_folded.gds", f"{name}_folded",
                      fo_rep["ports"], n, straps, fo_rep["bbox_um"],
                      merge_markers=True)
    result["variants"]["folded"] = {
        "gds": f"{name}_folded.gds",
        "klt_gen_params": folded_params,
        "device_bbox_um": fo_rep["bbox_um"],
        "device_bbox": bbox_dims(fo_rep["bbox_um"]),
        "straps": straps,
        **fo_meta,
    }

    if n >= 2:
        dropped = (n - 1) // 2
        broken_straps = [s for s in straps if s["joint"] != dropped]
        br_meta = compose(fo_raw, out_dir / f"{name}_broken.gds", f"{name}_broken",
                          fo_rep["ports"], n, broken_straps, fo_rep["bbox_um"],
                          merge_markers=True)
        result["variants"]["broken"] = {
            "gds": f"{name}_broken.gds",
            "klt_gen_params": folded_params,
            "omitted_joint": dropped,
            "device_bbox_um": fo_rep["bbox_um"],
            "device_bbox": bbox_dims(fo_rep["bbox_um"]),
            **br_meta,
        }
        um_meta = compose(fo_raw, out_dir / f"{name}_unmerged.gds", f"{name}_unmerged",
                          fo_rep["ports"], n, straps, fo_rep["bbox_um"],
                          merge_markers=False)
        result["variants"]["unmerged"] = {
            "gds": f"{name}_unmerged.gds",
            "klt_gen_params": folded_params,
            "device_bbox_um": fo_rep["bbox_um"],
            "device_bbox": bbox_dims(fo_rep["bbox_um"]),
            "straps": straps,
            **um_meta,
        }
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--klt", required=True)
    ap.add_argument("--pdk-variant", default="sky130A")
    ap.add_argument("--cases", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    args = ap.parse_args()

    cases = json.loads(args.cases.read_text())["cases"]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = {"schema": "sky130-ldo.folded-res-qual.geometry/1", "cases": []}
    try:
        for case in cases:
            out["cases"].append(generate_case(args.klt, args.pdk_variant, args.out_dir, case))
    except GenError as exc:
        print(f"gen-folded-res-qual.py: {exc}", file=sys.stderr)
        return 1
    (args.out_dir / "geometry.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"gen-folded-res-qual.py: wrote {len(cases)} case(s) to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
