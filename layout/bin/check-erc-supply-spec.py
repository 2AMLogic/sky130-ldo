#!/usr/bin/env python3
"""Pre-flight checks that keep layout/ldo-core/erc-supply-spec.json honest
against the GDS it is about to be run on (issue #112).

`klt erc` grades what the spec declares. Two of this spec's declarations are
claims *about the layout* that `klt erc` cannot re-derive for itself, so
nothing in its report would notice them going stale after a re-route:

  1. **The stackup omits met3/met4/met5.** That is correct only while the
     block draws nothing on them (see the spec's own `stackup` comment for
     why declaring them anyway is not free). If a later routing pass puts a
     rail on met3+, an undeclared level reads as extra electrical islands --
     which `klt erc` does report, loudly, as `erc.unconnected_net`, but
     naming the actual cause here is cheaper than root-causing that finding.

  2. **`ties[].well_boxes` asserts where the substrate is.** sky130 NMOS sit
     in the native p-substrate with no drawn pwell shape, so the substrate
     region is a caller assertion rather than drawn geometry
     (klayout-tools#2255). The committed box is the bounding box of every
     substrate-bodied piece of device geometry the block draws --
     `(diff - nwell) U (tap - nwell)` -- rounded outward. A floorplan change
     that moves or grows that geometry must move the box with it; otherwise
     the assertion silently covers less of the block than it claims to.

Both are checked here, mechanically, from the same GDS the flow is about to
run `klt erc` on. Exits 0 when the spec still describes the layout, 1 when
it does not (with the re-derived value printed, so the fix is a copy-paste).

Run under layout/.venv-erc (it needs the `klayout` module `klt` pulls in):

    layout/.venv-erc/bin/python layout/bin/check-erc-supply-spec.py \\
        --gds <path/to/ldo_core.gds> --spec layout/ldo-core/erc-supply-spec.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import klayout.db as db

# sky130 routing/via layers a supply could plausibly be routed on, from the
# same two sources the spec itself cites (the PDK's own sky130A.lyp and
# klayout-tools' curated sky130 deck layer table). Any of these drawn in the
# stream but missing from the spec's stackup/vias is what check 1 catches.
SKY130_ROUTING_LAYERS: dict[tuple[int, int], str] = {
    (67, 20): "li1.drawing",
    (68, 20): "met1.drawing",
    (69, 20): "met2.drawing",
    (70, 20): "met3.drawing",
    (71, 20): "met4.drawing",
    (72, 20): "met5.drawing",
    (66, 44): "licon1.drawing",
    (67, 44): "mcon.drawing",
    (68, 44): "via.drawing",
    (69, 44): "via2.drawing",
    (70, 44): "via3.drawing",
    (71, 44): "via4.drawing",
}

NWELL = (64, 20)
DIFF = (65, 20)
TAP = (65, 44)

# How far outside the derived substrate-device bounding box the committed
# assertion is allowed to sit before it stops being "the same region",
# in micrometres. The box is written rounded outward to 0.5 um.
BOX_SLACK_UM = 2.0


def _parse_layer(text: str) -> tuple[int, int]:
    layer, _, datatype = text.partition("/")
    return int(layer), int(datatype)


def _declared_layers(spec: dict) -> set[tuple[int, int]]:
    declared = set()
    for entry in spec.get("stackup", []):
        declared.add(_parse_layer(entry["layer"]))
    for entry in spec.get("vias", []):
        declared.add(_parse_layer(entry["layer"]))
    return declared


def _merged(layout: db.Layout, top: db.Cell, layer: tuple[int, int]) -> db.Region:
    region = db.Region(top.begin_shapes_rec(layout.layer(*layer)))
    region.merge()
    return region


def _drawn_layers(layout: db.Layout) -> set[tuple[int, int]]:
    drawn = set()
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        for cell in layout.each_cell():
            if not cell.shapes(index).is_empty():
                drawn.add((info.layer, info.datatype))
                break
    return drawn


def check_stackup_covers_drawn_routing(
    layout: db.Layout, spec: dict
) -> list[str]:
    declared = _declared_layers(spec)
    drawn = _drawn_layers(layout)
    problems = []
    for layer, name in sorted(SKY130_ROUTING_LAYERS.items()):
        if layer in drawn and layer not in declared:
            problems.append(
                f"layer {layer[0]}/{layer[1]} ({name}) is drawn in this stream "
                f"but is declared by neither stackup[] nor vias[] -- a supply "
                f"routed on it would read as extra electrical islands"
            )
    return problems


def check_substrate_assertion(
    layout: db.Layout, top: db.Cell, spec: dict
) -> list[str]:
    asserted = []
    for tie in spec.get("ties", []):
        if tie.get("well_layer") is None:
            asserted.extend(tie.get("well_boxes", []))
    if not asserted:
        return []

    dbu = layout.dbu
    nwell = _merged(layout, top, NWELL)
    substrate_devices = (
        _merged(layout, top, DIFF) - nwell
    ) + (_merged(layout, top, TAP) - nwell)
    substrate_devices.merge()
    if substrate_devices.is_empty():
        return [
            "no substrate-bodied device geometry ((diff - nwell) U "
            "(tap - nwell)) found at all -- the well_boxes assertion cannot "
            "be re-derived, so it cannot be trusted"
        ]

    derived = substrate_devices.bbox()
    derived_um = (
        derived.left * dbu,
        derived.bottom * dbu,
        derived.right * dbu,
        derived.top * dbu,
    )

    union = db.Box()
    for left, bottom, right, top_um in asserted:
        union += db.Box(
            db.DPoint(left, bottom).to_itype(dbu),
            db.DPoint(right, top_um).to_itype(dbu),
        )
    union_um = (
        union.left * dbu,
        union.bottom * dbu,
        union.right * dbu,
        union.top * dbu,
    )

    problems = []
    if not union.contains(derived.p1) or not union.contains(derived.p2):
        problems.append(
            "the committed ties[].well_boxes assertion no longer covers every "
            "substrate-bodied device in this layout.\n"
            f"    asserted (union): {[round(v, 3) for v in union_um]}\n"
            f"    derived  (bbox of (diff - nwell) U (tap - nwell)): "
            f"{[round(v, 3) for v in derived_um]}\n"
            "    Re-derive the box (round outward to 0.5 um) and update the "
            "spec, then mint a NEW record -- never edit an existing one."
        )
    else:
        slack = max(
            derived_um[0] - union_um[0],
            derived_um[1] - union_um[1],
            union_um[2] - derived_um[2],
            union_um[3] - derived_um[3],
        )
        if slack > BOX_SLACK_UM:
            problems.append(
                "the committed ties[].well_boxes assertion is much larger "
                "than the substrate geometry it claims to be about "
                f"(slack {slack:.3f} um > {BOX_SLACK_UM} um). A looser "
                "assertion is weaker evidence: tighten it to the derived "
                f"bbox {[round(v, 3) for v in derived_um]}."
            )

    # The tool's own degeneracy gate rejects an assertion within 1% of the
    # top cell's bbox area; report the margin so the record can state it.
    top_area = top.bbox().area() * dbu * dbu
    union_area = union.area() * dbu * dbu
    print(
        f"check-erc-supply-spec.py: substrate assertion "
        f"{[round(v, 3) for v in union_um]} um, {union_area:.1f} um2 "
        f"({100.0 * union_area / top_area:.2f}% of the {top_area:.1f} um2 "
        f"top-cell bbox); derived substrate-device bbox "
        f"{[round(v, 3) for v in derived_um]} um"
    )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gds", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--top", default="ldo_core")
    args = parser.parse_args()

    with args.spec.open() as handle:
        spec = json.load(handle)

    layout = db.Layout()
    layout.read(str(args.gds))
    top = layout.cell(args.top)
    if top is None:
        print(
            f"check-erc-supply-spec.py: no cell '{args.top}' in {args.gds}",
            file=sys.stderr,
        )
        return 1

    problems = check_stackup_covers_drawn_routing(layout, spec)
    problems += check_substrate_assertion(layout, top, spec)

    if problems:
        print(
            f"check-erc-supply-spec.py: {len(problems)} problem(s) -- the spec "
            f"no longer describes {args.gds}:",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("check-erc-supply-spec.py: spec still describes this layout")
    return 0


if __name__ == "__main__":
    sys.exit(main())
