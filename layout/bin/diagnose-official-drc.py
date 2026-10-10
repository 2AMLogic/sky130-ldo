#!/usr/bin/env python3
"""Attribute the PDK's official-deck (`sky130A_mr.drc`) markers on a routed
ldo-core layout to a rule family, an owning block / local routing routine, and
a measured geometric cause (issue #260).

Run under layout/.venv (needs `klayout.db`). Reads `<cell>.gds` and the
`mr-drc.lyrdb` the layout flow just wrote, and writes
`official-drc-diagnosis.json` next to them. Everything in the JSON is measured
from the GDS in this record: the lyrdb gives the markers, and an independent
geometry census (shape sizes per block cell, enclosure probes, region
differences) says what produced them. Nothing here relaxes or waives a rule.

The deck renumbers cells in its markers (`mos_array$47`), so a marker's owning
block is NOT read from that name. Block-owned families (licon.1, rpm/urpm) are
attributed by censusing each placed block cell's own shapes; locally routed
families (via.1a_b, m2.5, via2.5, nwell.9) are attributed by the marker's
coordinates in the top cell, which is where the router draws.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import klayout.db as kdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_drc import parse_lyrdb  # noqa: E402

LAYERS = {
    "licon": (66, 44), "mcon": (67, 44), "via1": (68, 44), "via2": (69, 44),
    "met1": (68, 20), "met2": (69, 20), "met3": (70, 20),
    "nwell": (64, 20), "hvi": (75, 20), "rpm": (86, 20), "urpm": (79, 20),
}
ENCLOSURE_STEP_UM = 0.005
ENCLOSURE_MAX_UM = 0.2


def _size_hist(shapes_iter, dbu: float) -> dict[str, int]:
    hist: Counter[str] = Counter()
    for s in shapes_iter:
        b = s.bbox()
        hist[f"{b.width() * dbu:.3f}x{b.height() * dbu:.3f}"] += 1
    return dict(sorted(hist.items(), key=lambda kv: -kv[1]))


def _enclosure(metal: kdb.Region, via: kdb.Box, dbu: float) -> dict[str, float]:
    """Enclosure of `via` by `metal` on each side, probed outward in 5nm steps
    (a side is "enclosed by d" if the via grown by d on that side only is still
    entirely metal)."""
    out: dict[str, float] = {}
    steps = int(ENCLOSURE_MAX_UM / ENCLOSURE_STEP_UM)
    for side in ("left", "right", "bottom", "top"):
        d_ok = -1.0
        for i in range(0, steps + 1):
            d = int(round(i * ENCLOSURE_STEP_UM / dbu))
            g = kdb.Box(
                via.left - (d if side == "left" else 0),
                via.bottom - (d if side == "bottom" else 0),
                via.right + (d if side == "right" else 0),
                via.top + (d if side == "top" else 0),
            )
            if (kdb.Region(g) - metal).is_empty():
                d_ok = i * ENCLOSURE_STEP_UM
            else:
                break
        out[side] = round(d_ok, 3)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gds", required=True, type=Path)
    ap.add_argument("--lyrdb", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--max-samples", type=int, default=3)
    args = ap.parse_args()

    markers = parse_lyrdb(args.lyrdb)  # fail-closed on a bad report
    layout = kdb.Layout()
    layout.read(str(args.gds))
    dbu = layout.dbu
    top = layout.top_cell()
    lidx = {n: layout.layer(*ln) for n, ln in LAYERS.items()}
    flat = {n: kdb.Region(top.begin_shapes_rec(i)) for n, i in lidx.items()}

    blocks = {}
    for inst in top.each_inst():
        b = inst.dbbox()
        blocks[inst.cell.name] = (inst.cell, b)

    def owner_of(x: float, y: float) -> str:
        for name, (_, b) in blocks.items():
            if b.left <= x <= b.right and b.bottom <= y <= b.top:
                return name
        return "ldo_core (local routing)"

    fams: dict[str, dict] = {}
    for fam, items in sorted(markers.by_rule.items()):
        cells = Counter(i.cell for i in items)
        samples = []
        for i in items[: args.max_samples]:
            samples.append({"cell": i.cell, "kind": i.kind, "geometry": i.geometry[:200]})
        fams[fam] = {
            "count": len(items),
            "deck_cells": dict(cells.most_common(6)),
            "sample_markers": samples,
        }

    # --- via.1a_b: every via1 in the layout, by drawn size and owner -------
    for name in ("via1", "via2", "mcon", "licon"):
        top_own = _size_hist(top.shapes(lidx[name]).each(), dbu)
        in_blocks: Counter[str] = Counter()
        for cname, (cell, _) in blocks.items():
            for k, v in _size_hist((it.shape() for it in cell.begin_shapes_rec(lidx[name])), dbu).items():
                in_blocks[k] += v
        fams.setdefault("_census", {})[name] = {
            "top_cell_own_shapes": top_own,
            "inside_block_cells": dict(in_blocks.most_common()),
        }

    fams.setdefault("via.1a_b", {})["via1_census"] = fams["_census"]["via1"]

    # --- licon.1: per-block licon size census ------------------------------
    per_block = {}
    for cname, (cell, _) in blocks.items():
        h = _size_hist((it.shape() for it in cell.begin_shapes_rec(lidx["licon"])), dbu)
        off = {k: v for k, v in h.items() if k != "0.170x0.170"}
        if off:
            per_block[cname] = off
    fams.setdefault("licon.1", {})["off_size_licons_by_block"] = per_block
    fams["licon.1"]["offending_block_count"] = len(per_block)

    # --- m2.5 / via2.5: enclosure of each marked via by its metal ----------
    # Both rules read met2: the deck's via2.5 *code* tests `m2.enclosing(via2,
    # 0.085, ...)` (the DRM's via2.5 is a met2 rule too) although its message
    # string says "m3". The flagged condition is two ADJACENT edges with less
    # than 0.085um enclosure; two opposite deficient edges are not flagged.
    for fam, via_name, metal_name in (("m2.5", "via1", "met2"), ("via2.5", "via2", "met2")):
        if fam not in markers.by_rule:
            continue
        classes: Counter[str] = Counter()
        example: dict[str, dict] = {}
        for item in markers.by_rule[fam]:
            if item.cell != top.name or not item.bbox_um:
                continue
            x0, y0, x1, y1 = item.bbox_um
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            box = kdb.Box(round(x0 / dbu), round(y0 / dbu), round(x1 / dbu), round(y1 / dbu))
            enc = _enclosure(flat[metal_name], box, dbu)
            key = "l{left} r{right} b{bottom} t{top}".format(**enc)
            sz = f"{(x1 - x0):.3f}x{(y1 - y0):.3f}"
            key = f"marker {sz} um; enclosure(um) {key}"
            classes[key] += 1
            example.setdefault(key, {"x_um": round(cx, 3), "y_um": round(cy, 3)})
        fams[fam]["enclosure_classes"] = [
            {"class": k, "count": v, "example_at": example[k]} for k, v in classes.most_common()
        ]

    # --- nwell.9: nwell not covered by the hv marker -----------------------
    uncovered = flat["nwell"] - flat["hvi"]
    pieces = [p.bbox() for p in uncovered.each()]
    fams.setdefault("nwell.9", {})["nwell_minus_hvi"] = {
        "polygon_count": len(pieces),
        "area_um2": round(uncovered.area() * dbu * dbu, 3),
        "nwell_area_um2": round(flat["nwell"].area() * dbu * dbu, 3),
        "hvi_area_um2": round(flat["hvi"].area() * dbu * dbu, 3),
        "pieces_um": [
            [round(b.left * dbu, 3), round(b.bottom * dbu, 3), round(b.right * dbu, 3), round(b.top * dbu, 3)]
            for b in pieces[:8]
        ],
    }
    # Is the uncovered region the n-well's overhang beyond the hvi-covered
    # blocks (margins + inter-block gaps), or inside a block?
    in_block_cells = kdb.Region()
    for _, (cell, b) in blocks.items():
        in_block_cells.insert(kdb.Box(round(b.left / dbu), round(b.bottom / dbu), round(b.right / dbu), round(b.top / dbu)))
    inside = uncovered & in_block_cells
    fams["nwell.9"]["nwell_minus_hvi"]["area_inside_block_bboxes_um2"] = round(inside.area() * dbu * dbu, 3)

    # --- rpm / urpm: marker width per resistor block ------------------------
    for fam, layer in (("rpm.1a", "rpm"), ("urpm.1a", "urpm")):
        rows = {}
        for cname, (cell, _) in blocks.items():
            r = kdb.Region(cell.begin_shapes_rec(lidx[layer]))
            if not r.is_empty():
                bb = r.bbox()
                rows[cname] = {
                    "marker_bbox_um": f"{bb.width() * dbu:.3f}x{bb.height() * dbu:.3f}",
                    "polygons": r.count(),
                }
        fams.setdefault(fam, {})["marker_layer_by_block"] = rows

    args.out.write_text(json.dumps({"schema": "ldo-official-drc-diagnosis/1", "families": fams}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
