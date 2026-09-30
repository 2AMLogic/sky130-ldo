#!/usr/bin/env python3
"""Pre-flight checks that keep layout/ldo-core/erc-supply-spec.json honest
against the GDS it is about to be run on (issue #112).

`klt erc` grades what the spec declares. Three of this spec's declarations are
claims *about the layout* that `klt erc` cannot re-derive for itself, so
nothing in its report would notice them going stale after a re-route:

  1. **The stackup omits the sky130 levels the block does not draw.** It
     declares li1..met3 and omits met4/met5, which is correct only while
     the block draws nothing on them (see the spec's own `stackup` comment
     for why declaring an undrawn level is not free). If a later routing
     pass puts a rail on an undeclared level, that level reads as extra
     electrical islands. `klt erc` does report that, loudly, as
     `erc.unconnected_net`, but naming the actual cause here is cheaper
     than root-causing that finding. This check fired for real once: #154
     put VIN on met3, and it refused the met1..met2 spec until met3 and
     via2 were declared.

  2. **`ties[].well_boxes` asserts where the substrate is.** sky130 NMOS sit
     in the native p-substrate with no drawn pwell shape, so the substrate
     region is a caller assertion rather than drawn geometry
     (klayout-tools#2255). The committed box is the bounding box of every
     substrate-bodied piece of device geometry the block draws --
     `(diff - nwell) U (tap - nwell)` -- rounded outward. A floorplan change
     that moves or grows that geometry must move the box with it; otherwise
     the assertion silently covers less of the block than it claims to.

  3. **The `_comment` block states figures about a DRAWN well.** The
     `nwell_tie` narrative says, in prose, how many n-well shapes the stream
     draws, what they merge to, and where that merged polygon sits. Unlike
     the two above, nothing machine-read depends on those figures --
     `well_layer: "64/20"` is a layer reference, not a coordinate -- which
     is exactly why they rotted unnoticed: the #89 redraw moved the well and
     the sentence kept quoting the pre-redraw span (issue #129). This check
     parses the figures back out of that sentence and re-derives them, so
     the narrative has the same mechanical backstop the substrate box has.
     **The sentence's shape is therefore load-bearing**: reword it freely,
     but keep the `... is DRAWN here: N shapes that merge into one A um2
     polygon spanning x X0..X1 um` form, or this check fails as
     un-re-derivable rather than passing silently.

All three are checked here, mechanically, from the same GDS the flow is about
to run `klt erc` on. Exits 0 when the spec still describes the layout, 1 when
it does not (with the re-derived value printed, so the fix is a copy-paste).

Run under layout/.venv-erc (it needs the `klayout` module `klt` pulls in):

    layout/.venv-erc/bin/python layout/bin/check-erc-supply-spec.py \\
        --gds <path/to/ldo_core.gds> --spec layout/ldo-core/erc-supply-spec.json
"""

from __future__ import annotations

import argparse
import json
import re
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

# The drawn-well narrative in the spec's `_comment` block quotes its area as a
# whole number of um2 and its x-span to 2 decimal places, so the comparison
# tolerances are the quoting precision, not a physical allowance: anything
# looser would let a real drift hide inside the rounding.
AREA_TOL_UM2 = 1.0
SPAN_TOL_UM = 0.01

# The one sentence in `_comment` that states figures about a drawn well.
# Deliberately anchored on `well_layer <l>/<d>` so it binds to a specific
# declared tie rather than matching anywhere in the prose. See this module's
# docstring, check 3, for why the sentence's shape is load-bearing.
DRAWN_WELL_NARRATIVE = (
    r"well_layer\s+{layer}\s*\([^)]*\)\s+is\s+DRAWN\s+here:\s+"
    r"(?P<shapes>\d+)\s+shapes?\s+that\s+merge\s+into\s+one\s+"
    r"(?P<area>[\d.]+)\s+um2\s+polygon\s+spanning\s+"
    r"x\s+(?P<x0>[-\d.]+)\s*\.\.\s*(?P<x1>[-\d.]+)\s+um"
)


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


def _narrative(spec: dict) -> str:
    """The `_comment` block as one whitespace-normalised string.

    The block is stored as a JSON array of hard-wrapped lines, so a sentence
    that reads as one sentence in the file is split across several entries.
    """
    lines = spec.get("_comment", [])
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def check_drawn_well_narrative(
    layout: db.Layout, top: db.Cell, spec: dict
) -> list[str]:
    """Re-derive what `_comment` claims about each DRAWN well (issue #129).

    For every tie declaring a real `well_layer`, this pulls the shape count,
    merged area and merged x-span back out of the spec's own prose and
    re-derives all three from the GDS. A drawn well is a fact about the
    stream, so a mismatch is always the prose being wrong, never the layout.
    """
    narrative = _narrative(spec)
    dbu = layout.dbu
    problems = []

    for tie in spec.get("ties", []):
        layer_text = tie.get("well_layer")
        if layer_text is None:
            continue
        name = tie.get("name", "<unnamed tie>")
        layer = _parse_layer(layer_text)

        shapes = db.Region(top.begin_shapes_rec(layout.layer(*layer)))
        derived_shapes = shapes.count()
        merged = shapes.dup()
        merged.merge()
        derived_polygons = merged.count()
        derived_area = merged.area() * dbu * dbu
        bbox = merged.bbox()
        derived_bbox = (
            bbox.left * dbu,
            bbox.bottom * dbu,
            bbox.right * dbu,
            bbox.top * dbu,
        )

        print(
            f"check-erc-supply-spec.py: {name} drawn well {layer_text} "
            f"derived: {derived_shapes} shapes -> {derived_polygons} merged "
            f"polygon(s), {derived_area:.2f} um2, bbox "
            f"{[round(v, 3) for v in derived_bbox]} um"
        )

        if derived_shapes == 0:
            problems.append(
                f"tie '{name}' declares well_layer {layer_text} but the "
                f"stream draws nothing on it -- the tie cannot be graded and "
                f"the _comment block's account of it cannot be re-derived"
            )
            continue

        match = re.search(
            DRAWN_WELL_NARRATIVE.format(layer=re.escape(layer_text)), narrative
        )
        if match is None:
            problems.append(
                f"the _comment block states no re-derivable figures for tie "
                f"'{name}''s drawn well_layer {layer_text}. Expected a "
                f"sentence of the form 'well_layer {layer_text} "
                f"(<name>) is DRAWN here: N shapes that merge into one A um2 "
                f"polygon spanning x X0..X1 um'.\n"
                f"    derived now: {derived_shapes} shapes -> "
                f"{derived_polygons} merged polygon(s), "
                f"{derived_area:.2f} um2, x {derived_bbox[0]:.2f}.."
                f"{derived_bbox[2]:.2f} um\n"
                "    (This check exists because that narrative went stale "
                "silently once already -- issue #129. Restore the sentence "
                "rather than dropping the check.)"
            )
            continue

        asserted_shapes = int(match.group("shapes"))
        asserted_area = float(match.group("area"))
        asserted_x0 = float(match.group("x0"))
        asserted_x1 = float(match.group("x1"))

        mismatches = []
        if derived_shapes != asserted_shapes:
            mismatches.append(
                f"shape count: asserted {asserted_shapes}, "
                f"derived {derived_shapes}"
            )
        if derived_polygons != 1:
            mismatches.append(
                f"merged polygon count: the sentence says the shapes merge "
                f"into ONE polygon, derived {derived_polygons}"
            )
        if abs(derived_area - asserted_area) > AREA_TOL_UM2:
            mismatches.append(
                f"merged area: asserted {asserted_area:.0f} um2, "
                f"derived {derived_area:.2f} um2"
            )
        if (
            abs(derived_bbox[0] - asserted_x0) > SPAN_TOL_UM
            or abs(derived_bbox[2] - asserted_x1) > SPAN_TOL_UM
        ):
            mismatches.append(
                f"merged x-span: asserted {asserted_x0:.2f}..{asserted_x1:.2f} "
                f"um, derived {derived_bbox[0]:.2f}..{derived_bbox[2]:.2f} um"
            )

        if mismatches:
            problems.append(
                f"the _comment block's account of tie '{name}''s drawn "
                f"well_layer {layer_text} no longer describes this layout "
                f"(a drawn well is a fact about the stream, so the prose is "
                f"what is wrong):\n"
                + "".join(f"    {m}\n" for m in mismatches)
                + f"    full derived bbox: "
                f"{[round(v, 3) for v in derived_bbox]} um\n"
                "    Correct the sentence, then mint a NEW record -- never "
                "edit an existing one."
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
    problems += check_drawn_well_narrative(layout, top, spec)
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
