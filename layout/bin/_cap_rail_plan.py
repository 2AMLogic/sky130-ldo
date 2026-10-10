"""Pure planning arithmetic for the MiM-capacitor + supply-rail overlay
demonstrator (issue #254). Standard library only, so `layout/tests/` can
exercise it under the repo's plain `python3` (no `klt`, no KLayout).

What lives here, and why it is separate from the drawing code in
`gen-cap-rail-demo.py`:

* reading the schematic's capacitors (name, both nets, value) out of the
  xschem netlist -- the demonstrator draws what the schematic says, not a
  transcribed list;
* sizing each capacitor as an array of stacked MiM units whose *extraction*
  value (area + perimeter law, coefficients read from `klt`'s own deck by the
  caller) reproduces the schematic value;
* the plate assignment (which schematic net goes on the outer plates);
* the block-overhead geometry shared by the generator and the area budget;
* the footprint/limit arithmetic behind the feasibility verdict.

Nothing here changes a spec value: the ratified Area row is read as a fixed
strict limit (`LIMIT_UM2`) and only ever compared against.
"""

from __future__ import annotations

import math
import re
from typing import Any

#: Ratified Area row: < 0.1 mm^2 core area (strict). Read-only here.
LIMIT_UM2 = 0.1e6

#: sky130 manufacturing grid. Every drawn coordinate is snapped to it.
GRID_UM = 0.005

#: Unit-plate side bounds. sky130A's own device generator
#: (`libs.tech/magic/sky130A.tcl`, `sky130_fd_pr__cap_mim_m3_{1,2}_defaults`)
#: offers each MiM unit at 2..30 um per side; larger capacitors are arrays of
#: units. Kept inside that range so every unit is a size the PDK itself
#: offers, rather than one 200 um plate nothing in the PDK characterises.
MIN_UNIT_SIDE_UM = 2.0
MAX_UNIT_SIDE_UM = 30.0

#: Spacing between adjacent unit top plates inside one capacitor. Over a
#: shared (continuous) bottom plate the binding official rules are
#: capm.2a / cap2m.2a (0.84 um); 1.2 um is the bottom-plate isolation
#: distance of capm.2b, used here as a margin rather than a requirement.
UNIT_GAP_UM = 1.2

#: Enclosure of the unit array by the met3 (outer) and met4 (inner) plates.
#: Official minimum is 0.14 um (capm.3 / cap2m.3).
PLATE_ENCLOSURE_UM = 0.5

#: Outer-plate strap on the block's left edge, joining the met3 outer plate
#: to the met5 outer plate:
#:   met3 plate -> via2 -> met2 bridge -> via2 -> *separate* met3 island
#:   -> via3 -> met4 island -> via4 -> met5 plate.
#: The met3 island is a separate polygon on purpose: the pinned `klt
#: extract` cuts every via3 that overlaps a met3 polygon touching `capm`
#: (its MiM top-plate-via exclusion), so a via3 dropped straight onto the
#: plate outside the top-plate footprint would silently not connect. The
#: island's inner edge sits STRAP_ISLAND_INNER_UM outside the unit array:
#: >= 0.14 + 1.2 um from the capm edge (capm.2b_a), and its met4 island
#: >= 1.2 um from the inner met4 plate (cap2m.2b_a margin).
STRAP_ISLAND_INNER_UM = 1.5
STRAP_ISLAND_W_UM = 2.4
#: Gap between the inner met4 plate and the strap's met4 island.
STRAP_M4_GAP_UM = 1.2
#: Pitch of the met2 bridges along the strap.
STRAP_POST_PITCH_UM = 10.0

#: Inner-plate tap (met4 tab -> via3 -> met3 island -> via2 -> met2 pad) on
#: the block's right edge, the island again >= 1.34 um from the capm edge.
TAP_ISLAND_INNER_UM = 1.5
TAP_ISLAND_W_UM = 2.0
TAP_ISLAND_H_UM = 1.0


def snap(value_um: float) -> float:
    """Snap to the manufacturing grid (and clean the float)."""
    return round(round(value_um / GRID_UM) * GRID_UM, 6)


_SI = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "": 1.0}


def parse_value(text: str) -> float:
    """SPICE-style number with an optional SI suffix (`150p` -> 1.5e-10)."""
    match = re.fullmatch(r"([0-9.eE+-]+)([fpnumk]?)", text.strip())
    if match is None:
        raise ValueError(f"cannot parse a capacitance value from {text!r}")
    return float(match.group(1)) * _SI[match.group(2)]


def parse_capacitors(netlist_text: str) -> list[dict[str, Any]]:
    """Every top-level `C<name> n1 n2 value ...` card in an xschem netlist.

    Instance names are kept verbatim (`C_COMP`), so the layout, the LVS
    reference and the record all speak the schematic's own names. A `m=`
    multiplier other than 1 is refused rather than silently ignored.
    """
    caps: list[dict[str, Any]] = []
    for raw in netlist_text.splitlines():
        line = raw.strip()
        if not line or line[0] not in "Cc" or line.startswith("*"):
            continue
        fields = line.split()
        if len(fields) < 4:
            continue
        name, n1, n2, value = fields[:4]
        mult = 1.0
        for extra in fields[4:]:
            if extra.lower().startswith("m="):
                mult = float(extra.split("=", 1)[1])
        if mult != 1.0:
            raise ValueError(f"{name}: m={mult} is not supported by this planner")
        caps.append({"name": name, "nets": [n1, n2], "value_f": parse_value(value)})
    return caps


def unit_cap_f(side_um: float, area_f_um2: float, perim_f_um: float) -> float:
    """One square MiM unit's capacitance under the deck's area + perimeter law."""
    return area_f_um2 * side_um * side_um + perim_f_um * 4.0 * side_um


def solve_unit_side_um(c_unit_f: float, area_f_um2: float, perim_f_um: float) -> float:
    """Side of a square unit whose `unit_cap_f` equals `c_unit_f` (unsnapped)."""
    if c_unit_f <= 0 or area_f_um2 <= 0 or perim_f_um < 0:
        raise ValueError("unit sizing needs positive capacitance and area coefficient")
    a, b = area_f_um2, 4.0 * perim_f_um
    return (-b + math.sqrt(b * b + 4.0 * a * c_unit_f)) / (2.0 * a)


def size_capacitor(
    name: str,
    value_f: float,
    rows: int,
    cols: int,
    layers: int,
    area_f_um2: float,
    perim_f_um: float,
) -> dict[str, Any]:
    """Size `rows x cols` stacked units (`layers` MiM levels each) to `value_f`.

    Raises if the required unit side leaves the PDK's 2..30 um unit range --
    the caller must pick a different array shape, not draw an out-of-range
    unit.
    """
    if rows < 1 or cols < 1 or layers < 1:
        raise ValueError(f"{name}: rows/cols/layers must be >= 1")
    units = rows * cols
    c_unit = value_f / (units * layers)
    side = snap(solve_unit_side_um(c_unit, area_f_um2, perim_f_um))
    if not MIN_UNIT_SIDE_UM <= side <= MAX_UNIT_SIDE_UM:
        raise ValueError(
            f"{name}: a {rows}x{cols} array needs {side:.3f} um units, outside the "
            f"PDK's {MIN_UNIT_SIDE_UM}..{MAX_UNIT_SIDE_UM} um unit range"
        )
    c_layer_unit = unit_cap_f(side, area_f_um2, perim_f_um)
    total = c_layer_unit * units * layers
    return {
        "name": name,
        "target_f": value_f,
        "rows": rows,
        "cols": cols,
        "units": units,
        "layers": layers,
        "unit_side_um": side,
        "unit_cap_per_layer_f": c_layer_unit,
        "per_layer_total_f": c_layer_unit * units,
        "planned_total_f": total,
        "planned_rel_error": (total - value_f) / value_f,
    }


def array_span_um(n: int, side_um: float) -> float:
    return snap(n * side_um + (n - 1) * UNIT_GAP_UM)


def block_extent_um(rows: int, cols: int, side_um: float) -> dict[str, float]:
    """Drawn extent of one capacitor block, relative to its unit array's
    lower-left corner: left strap, array, right tap. Shared by the generator
    (which draws exactly this) and the budget (which counts it)."""
    lx = array_span_um(cols, side_um)
    ly = array_span_um(rows, side_um)
    e = PLATE_ENCLOSURE_UM
    left = STRAP_ISLAND_INNER_UM + STRAP_ISLAND_W_UM
    right = TAP_ISLAND_INNER_UM + TAP_ISLAND_W_UM
    return {
        "array_w_um": lx,
        "array_h_um": ly,
        "left_um": snap(left),
        "right_um": snap(right),
        "bottom_um": e,
        "top_um": e,
        "w_um": snap(left + lx + right),
        "h_um": snap(ly + 2 * e),
    }


def assign_plates(cap_nets: list[str], outer_net: str) -> dict[str, str]:
    """Outer plates (met3 bottom of the m3 MiM + met5 top of the m4 MiM) take
    the low-impedance terminal; the inner plate (met4 + both top-plate marks)
    takes the other, so the high-impedance node is sandwiched between plates
    of its own capacitor's other terminal rather than facing the circuitry
    below or anything above."""
    if outer_net not in cap_nets:
        raise ValueError(f"outer net {outer_net!r} is not one of the capacitor's nets {cap_nets}")
    inner = [n for n in cap_nets if n != outer_net]
    if len(inner) != 1:
        raise ValueError(f"capacitor nets {cap_nets} do not name two distinct terminals")
    return {"outer": outer_net, "inner": inner[0]}


def core_rectangle(
    mos_domain_w_um: float,
    bank_w_um: float,
    bank_gap_um: float,
    channel_h_um: float,
    row_h_um: float,
    rail_band_h_um: float,
) -> dict[str, float]:
    """The planned core outline: measured MOS-domain width plus a folded
    resistor-bank column, by channel + device row + rail bands tall."""
    w = mos_domain_w_um + bank_gap_um + bank_w_um
    h = channel_h_um + row_h_um + rail_band_h_um
    area = w * h
    return {
        "w_um": w,
        "h_um": h,
        "area_um2": area,
        "area_mm2": area / 1e6,
        "limit_um2": LIMIT_UM2,
        "margin_um2": LIMIT_UM2 - area,
        "margin_fraction": (LIMIT_UM2 - area) / LIMIT_UM2,
        "below_limit": area < LIMIT_UM2,
    }


def side_by_side_area_um2(cap_block_areas_um2: list[float], core_area_um2: float) -> float:
    """Counterfactual: the same drawn capacitor blocks placed beside the core
    instead of over it (no overlay), with no extra spacing/routing counted."""
    return core_area_um2 + sum(cap_block_areas_um2)
