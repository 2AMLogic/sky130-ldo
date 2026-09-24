#!/usr/bin/env python3
"""Generate, place, and route the sky130 LDO core layout (issues #15/#33)
from `design/ldo_3v3in_1v8out.sch`'s own xschem netlist -- one `klt gen`
block per active schematic device, composed by `klt gen-compose`, then wired
net-for-net by the channel router in this module.

Standard library plus `klayout.db` (already a `klt` dependency, resolved from
`layout/.venv`), matching `layout/bin/render-record.py`'s otherwise
no-extra-runtime-dependency convention.

Why netlist-driven (issue #33)
------------------------------
The first cut of this script (issue #15) carried a hand-transcribed device
table. That table went stale the moment the schematic grew -- issue #22's
current-limit/soft-start devices, then the rail-to-rail output stage and the
thermal-shutdown comparator, all landed without it, and #17's first LVS
attempt reported `status: mismatch` with 0 of 28 reference devices matched.
Deriving the device set mechanically from the schematic's own netlist (the
same input `layout/bin/gen-ldo-reference-netlist.py` translates into the LVS
reference) removes that drift class structurally: the layout cannot describe a
different device set than the schematic, because it reads the same file.

What is drawn
-------------
* **MOS devices** -- one `klt gen mos_array` block each, `fingers=1`,
  `rows=1`, `cols=<units>`, `dummy=0`, `voltage_flavor="hvi"` (issue #142 --
  see MOS_VOLTAGE_FLAVORS). `cols` splits a device wider than
  `MAX_UNIT_W_UM` into that many *parallel* unit devices of equal width whose
  S/D/G terminals this module's router straps together, so the drawn total
  width is the schematic's own `W * mult` (e.g. the pass device's 2500um as
  25 parallel 100um units). `klt lvs`'s `options.combine_devices` folds the
  strapped units back into one device of the summed width for the compare --
  the reason the reference netlist's single `W=2500U` element matches.
  `fingers>1` is deliberately *not* used: `klt gen`'s multi-finger unit leaves
  the interior diffusions unstrapped, so `klt extract` reads an n-finger
  device as n devices in *series* (each with its own floating gate), which is
  neither the schematic's topology nor foldable.
* **Resistors** -- one `klt gen res_array` block per schematic resistor
  instance (`num=1`, `dummy=0`), so the layout is 1:1 with the reference
  netlist's own per-instance resistor elements.
* **Body ties** -- one drawn `tap.drawing` tie per body net: an n-well tie
  inside the shared n-well that spans the PMOS group (PMOS bodies -> `VIN`)
  and a substrate tie outside every well (NMOS + poly-resistor bodies ->
  the schematic's `0`). The curated sky130 extraction deck resolves both
  (`docs/cli/extract.md`, "Coverage"), so neither body terminal is left on
  the deck-synthesized `vsubs` fallback.
* **Routing** -- see :func:`route_composed_cell`.
* **Power rails** -- the two nets that carry the block's full load current
  (the pass device's own drain and source nets, identified mechanically --
  see :func:`identify_power_nets`) are *not* routed as channel trunks at all.
  They get strapped two-level rails above the device row, sized from the
  ratified full-load current and dropout budget in `spec/target-spec.md` and
  from the sheet resistances `klt`'s own parasitics deck declares, never from
  a hand-picked width. See :func:`plan_power_rails` (issue #154).

Capacitors (`C_COMP`, `C_CL`, `C_SS`, `C_TS`) are still not drawn: `klt gen`
has no capacitor/MiM generator at this repo's pinned `klt` commit (filed as
https://github.com/2AMLogic/klayout-tools/issues/1117 per CLAUDE.md's friction
protocol). `gen-ldo-reference-netlist.py` drops them from the LVS reference
for the same reason, so the compare stays symmetric.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from _netlist_common import _merge_continuations
from _spec_constants import SpecConstants, read_spec_constants

# --------------------------------------------------------------------------
# Schematic -> device-set translation. The model-name maps mirror
# gen-ldo-reference-netlist.py's exactly (same schematic, same two flavors),
# so the layout and the LVS reference can never disagree about which
# schematic element is which device class.
# --------------------------------------------------------------------------

MOS_MODELS = {
    "sky130_fd_pr__nfet_g5v0d10v5": "nfet",
    "sky130_fd_pr__pfet_g5v0d10v5": "pfet",
}

#: Schematic MOS model -> the `klt gen mos_array` `voltage_flavor` whose
#: marker geometry makes an extracted device bind back to *that* model
#: (issue #142). Keyed on the same schematic model token MOS_MODELS is, so
#: the layout's voltage-domain marking is derived from the schematic rather
#: than hand-transcribed per device: adding a flavor to the schematic means
#: adding one row here, and forgetting to is a hard error (see
#: `mos_voltage_flavor`), not a silently-unmarked device.
#:
#: Why this matters: `klt gen mos_array`'s `voltage_flavor="hvi"` draws
#: sky130's `hvi.drawing` (75/20) voltage-domain marker over the unit array,
#: and the curated sky130 extraction deck's own
#: `EXTRACTION_DECK.mos_flavours` entry (`MOSFlavour(marker=(75, 20),
#: flavour="hvi", ...)`) is keyed on exactly that layer. Without it, `klt
#: extract --pdk sky130A` has nothing to key a flavor off and binds every
#: gate to the *1.8V core* subcircuit (`sky130_fd_pr__{n,p}fet_01v8`)
#: instead of the 5V-tolerant `g5v0d10v5` devices the schematic actually
#: instantiates -- so the extracted netlist describes different transistors
#: than the design, and a post-layout re-simulation against it is not
#: comparable to the schematic-side leg at all (see
#: `sim/pex-post-layout/README.md`).
#:
#: The marker is DRC-neutral on this deck by construction, not by hope:
#: `decks/sky130.py`'s own `hvi` layer-name comment records that no rule in
#: the curated sky130 DRC deck reads `hvi`, so every rule keeps applying its
#: general-case threshold to geometry drawn inside it. The DRC record this
#: flow lands is the authority on that either way.
MOS_VOLTAGE_FLAVORS = {
    "sky130_fd_pr__nfet_g5v0d10v5": "hvi",
    "sky130_fd_pr__pfet_g5v0d10v5": "hvi",
}
RES_MODELS = {
    "sky130_fd_pr__res_high_po": "high",
    "sky130_fd_pr__res_xhigh_po": "xhigh",
}

#: Widest single unit device drawn. A schematic device wider than this is
#: split into ceil(W_total / MAX_UNIT_W_UM) equal parallel units, strapped by
#: the router and folded back by `klt lvs`'s options.combine_devices. Keeps
#: the pass device (W_total = 2500um) a ~100um-tall block instead of a
#: 2500um-tall one, without changing the drawn total width.
MAX_UNIT_W_UM = 100.0

#: Function-group assignment by device-name prefix, longest prefix first.
#: Cosmetic (it orders the row and documents the floorplan); an unrecognised
#: name falls into "core" rather than failing, so a new schematic device is
#: never silently dropped from the layout.
GROUP_PREFIXES: list[tuple[str, str]] = [
    ("R_FB", "feedback_divider"),
    ("R_CZ", "compensation"),
    ("R_BIAS", "bias_resistor"),
    ("M_BIAS", "bias_enable"),
    ("M_ENN", "bias_enable"),
    ("M_ENP", "bias_enable"),
    ("M_TAIL", "error_amp"),
    ("M_IN", "error_amp"),
    ("M_MIR", "error_amp"),
    ("M_PASS", "output_pass"),
    ("M_SENSE", "current_limit"),
    ("M_CL", "current_limit"),
    ("M_INV", "soft_start"),
    ("M_SS", "soft_start"),
    ("M_TS", "thermal_shutdown"),
    ("M_TC", "thermal_shutdown"),
]

#: Row order for the placed floorplan. Every group listed here is emitted in
#: this order; a group not listed here is appended after them (in first-seen
#: order) rather than dropped.
GROUP_ORDER: list[str] = [
    "bias_resistor",
    "feedback_divider",
    "compensation",
    "bias_enable",
    "error_amp",
    "current_limit",
    "soft_start",
    "thermal_shutdown",
    "output_pass",
    "core",
]

# --- placement geometry ----------------------------------------------------
BLOCK_GAP_UM = 2.0  # between adjacent blocks in the row
GROUP_GAP_UM = 6.0  # between the NMOS/PMOS/resistor super-groups
TAP_SLOT_UM = 4.0  # reserved x slot for a drawn body tie

# --- routing geometry (all >= the sky130 deck's own minimums; see
#     `klt drc --deck sky130`'s rule list) ---------------------------------
STUB_W_UM = 0.19  # li1 stub (deck minimum li1 width 0.17)
TRUNK_W_UM = 0.30  # met1 trunk / met2 riser (deck minimum 0.14)
MCON_UM = 0.17  # li1 <-> met1 via
VIA1_UM = 0.16  # met1 <-> met2 via (deck minimum size 0.15)
VIA2_UM = 0.20  # met2 <-> met3 via (deck minimum size 0.20)
TRACK_PITCH_UM = 0.8  # between adjacent net trunks
CHANNEL_TOP_UM = -3.0  # first trunk's y (the row's blocks sit at y >= 0)
RISER_CLEAR_UM = 1.6  # gate riser's met1 landing pad above its block's top

# --- power-rail geometry (issue #154) --------------------------------------
# `TRUNK_W_UM` above is a *signal* conductor: it carries a gate's displacement
# current or a bias branch's microamps. The two nets that carry the block's
# full load current are a different object and are drawn as a different
# object -- a strapped two-level rail above the device row, whose width is
# computed (:func:`power_rail_width_um`) rather than chosen.
#
# Three inputs, none of them transcribed into this file:
#   * the load current, from `spec/target-spec.md`'s ratified `Load` row
#     (see `_spec_constants.py`);
#   * the voltage that current may drop across the block's own drawn power
#     interconnect, as `POWER_RAIL_IR_SHARE` of the ratified
#     `Dropout @ 50 mA` budget, split evenly across the rails;
#   * the metal sheet resistances, read from `klt`'s own parasitics deck
#     (:func:`rail_sheet_rho_ohm_sq`), the same deck `klt extract
#     --parasitics` measures the landed layout against.
#
#: Share of the ratified dropout budget the block's own drawn power
#: interconnect may consume, across every load-current rail together. 5% of
#: a 300mV budget is 15mV; a rail that needed more than this would be
#: telling us the floorplan, not the wire width, is the binding constraint.
POWER_RAIL_IR_SHARE = 0.05
#: Vertical clearance between the highest drawn thing over the device row
#: (a gate riser's met1 landing pad / met2 turn, RISER_CLEAR_UM above its
#: block) and the power terminals' own met1 -> met2 -> met3 transition.
POWER_TRANSITION_CLEAR_UM = 0.6
#: Vertical clearance between that transition and the first rail band.
RAIL_CLEAR_UM = 1.0
#: Vertical gap between adjacent rail bands.
RAIL_GAP_UM = 1.0
#: Stitch pitch of the via array that straps a rail's two metal levels.
RAIL_VIA_PITCH_UM = 1.0
#: met1 strap drawn over a power terminal's own li1 source/drain pad, with an
#: mcon every POWER_MCON_PITCH_UM along it. Without this a 100um-tall unit
#: device's li1 strap is contacted at exactly one point, so its own ~12.8
#: ohm/square local interconnect carries the unit's whole share of the load
#: current along up to half the device height. Its width is computed from the
#: drawn port pitch and the deck's own met1 spacing rule
#: (:func:`power_pad_strap_width_um`); these two bound that computation.
POWER_PAD_STRAP_MAX_W_UM = 1.0
POWER_PAD_STRAP_MARGIN_UM = 0.08
POWER_MCON_PITCH_UM = 2.0
#: Vertical riser between a power terminal's pad strap and its rail. Narrower
#: than the pad strap because above the block top it runs past the gate
#: risers' own met1 landing pads at the 0.46um gate-to-source port pitch.
POWER_RISER_W_UM = TRUNK_W_UM
#: met3 riser, >= via2 (0.20) + 2 x met3's 0.065um via2 enclosure.
POWER_MET3_RISER_W_UM = 0.40
#: Landing-pad side for the met1 <-> met2 <-> met3 transition stack.
POWER_VIA_PAD_UM = 0.30
#: How far a rail segment is extended past the outermost riser that lands on
#: it: one met3 riser half-width plus a margin, so no riser overhangs into a
#: sliver at the rail's end.
RAIL_END_MARGIN_UM = 0.40
#: The rails' floorplan cap: a power rail may be drawn as wide as the device
#: row is tall, and no wider. A required width beyond that is a statement
#: about the floorplan (a 2.4mm single row with the pass device at one end),
#: not about the wire, and is reported as such rather than silently drawn.
POWER_RAIL_MAX_W_FRACTION_OF_ROW = 1.0
#: Two-level strapping stack per rail band, outermost band last. Each entry
#: is (lower metal level index, upper metal level index) into the sky130
#: parasitics deck's own `metals` tuple (0=li1, 1=met1, 2=met2, 3=met3).
#: Band 0 sits closest to the row and is crossed by no other net's riser;
#: band 1 is reached by risers that must cross band 0, which is why its two
#: levels start one level higher -- the crossing happens on met3, a level
#: band 0 does not use.
RAIL_BAND_LEVELS: list[tuple[int, int]] = [(1, 2), (2, 3)]


class GenError(RuntimeError):
    pass


def mos_voltage_flavor(model: str) -> str:
    """The drawn voltage-domain marker for a schematic MOS `model`.

    Hard-fails on a model that MOS_MODELS recognises but MOS_VOLTAGE_FLAVORS
    does not: an unmarked device is not a cosmetic omission, it is a device
    that extracts as the wrong transistor (issue #142), so a future schematic
    that introduces a second MOS flavor must state its marker here rather
    than silently inheriting nothing.
    """
    try:
        return MOS_VOLTAGE_FLAVORS[model]
    except KeyError:
        raise GenError(
            f"{model}: no MOS_VOLTAGE_FLAVORS entry -- add the sky130 "
            "voltage-domain marker this model's devices must be drawn "
            "inside, or `klt extract --pdk` will bind them to the wrong "
            "device flavor (see this module's MOS_VOLTAGE_FLAVORS note)"
        ) from None


# --------------------------------------------------------------------------
# Netlist parsing
# --------------------------------------------------------------------------


def parse_netlist(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse an xschem-generated SPICE netlist into this module's device list.

    Returns ``(devices, skipped)``. ``skipped`` holds every element line with
    no recognised MOS/resistor model (the schematic's capacitors), reported
    rather than dropped silently.
    """
    lines = _merge_continuations(
        [ln.rstrip() for ln in path.read_text().splitlines()]
    )
    devices: list[dict[str, Any]] = []
    skipped: list[str] = []
    seen_names: dict[str, int] = {}

    for line in lines:
        if not line.startswith(("X", "C", "R", "M")):
            continue
        m = re.match(r"^X(\S+)\s+(.*)$", line)
        if not m:
            # A non-subcircuit element (the schematic's capacitors are plain
            # `C...` cards): no model token this module recognises.
            if line[:1] in ("C", "R", "M"):
                skipped.append(line)
            continue
        name, rest = m.group(1), m.group(2)
        toks = rest.split()
        model_idx = next(
            (i for i, t in enumerate(toks) if t in MOS_MODELS or t in RES_MODELS),
            None,
        )
        if model_idx is None:
            skipped.append(line)
            continue
        nets = toks[:model_idx]
        model = toks[model_idx]
        params: dict[str, str] = {}
        for tok in toks[model_idx + 1 :]:
            if "=" in tok:
                key, value = tok.split("=", 1)
                params[key] = value

        # The schematic reuses at least one instance name across two
        # sub-blocks (a genuine schematic defect, see this issue's PR). Keep
        # the layout single-valued by suffixing the duplicate rather than
        # silently overwriting the first block's GDS.
        count = seen_names.get(name, 0)
        seen_names[name] = count + 1
        block_id = name if count == 0 else f"{name}__{count + 1}"

        if model in MOS_MODELS:
            if len(nets) != 4:
                raise GenError(f"{name}: expected 4 MOS nets, got {nets}")
            w_um = float(params.get("W", "0"))
            mult = float(params.get("mult", "1"))
            devices.append(
                {
                    "kind": "mos",
                    "id": block_id,
                    "name": name,
                    "flavor": MOS_MODELS[model],
                    "model": model,
                    "voltage_flavor": mos_voltage_flavor(model),
                    "l_um": float(params.get("L", "0")),
                    "w_total_um": w_um * mult,
                    "nets": {
                        "D": nets[0],
                        "G": nets[1],
                        "S": nets[2],
                        "B": nets[3],
                    },
                }
            )
        else:
            if len(nets) != 3:
                raise GenError(f"{name}: expected 3 resistor nets, got {nets}")
            devices.append(
                {
                    "kind": "res",
                    "id": block_id,
                    "name": name,
                    "flavor": RES_MODELS[model],
                    "length_um": float(params.get("L", "0")),
                    "width_um": float(params.get("W", "0")),
                    "nets": {"A": nets[0], "B": nets[1], "W": nets[2]},
                }
            )

    if not devices:
        raise GenError(f"no MOS/resistor devices found in {path}")
    return devices, skipped


def assign_group(device: dict[str, Any]) -> str:
    name = device["name"]
    best = ""
    group = "core"
    for prefix, candidate in GROUP_PREFIXES:
        if name.startswith(prefix) and len(prefix) > len(best):
            best, group = prefix, candidate
    return group


def plan_units(w_total_um: float) -> tuple[int, float]:
    """Split a device width into equal parallel units <= MAX_UNIT_W_UM."""
    units = max(1, math.ceil(w_total_um / MAX_UNIT_W_UM - 1e-9))
    return units, w_total_um / units


# --------------------------------------------------------------------------
# Power-net identification and conductor sizing (issue #154)
# --------------------------------------------------------------------------


def identify_power_nets(devices: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The nets that carry the block's full load current, read off the
    schematic rather than named in this file.

    The load current flows through exactly one device: the pass device. It is
    identified the only way that cannot go stale against the schematic -- as
    the widest drawn MOS, by a decisive margin over the next widest. Its drain
    and source nets are then, by construction, the two nets every milliamp of
    load current has to pass through; every other net in the block carries
    bias or gate current.

    Returns ``{net: {"terminal": "D"|"S", "device": <block id>}}``.
    """
    mos = [d for d in devices if d["kind"] == "mos"]
    if not mos:
        raise GenError("no MOS device to identify the pass device from")
    ranked = sorted(mos, key=lambda d: d["w_total_um"], reverse=True)
    pass_device = ranked[0]
    if len(ranked) > 1 and pass_device["w_total_um"] < 4.0 * ranked[1]["w_total_um"]:
        raise GenError(
            f"{pass_device['name']} (W_total={pass_device['w_total_um']}um) is not "
            f"decisively wider than {ranked[1]['name']} "
            f"(W_total={ranked[1]['w_total_um']}um) -- this flow identifies the "
            "load-current nets as the widest MOS's drain/source, and that "
            "identification is no longer unambiguous"
        )
    power: dict[str, dict[str, Any]] = {}
    for terminal in ("D", "S"):
        net = pass_device["nets"][terminal]
        if net in power:
            raise GenError(
                f"{pass_device['name']}'s drain and source are the same net {net!r}"
            )
        power[net] = {"terminal": terminal, "device": pass_device["id"]}
    return power


def rail_sheet_rho_ohm_sq(deck_name: str) -> list[float | None]:
    """Per-metal-level sheet resistance, from `klt`'s own parasitics deck.

    Same discipline (and same reason) as
    `gen-ldo-reference-netlist.py`'s resistor constants: the deck that
    `klt extract --parasitics` will measure the landed layout against is the
    single source of truth for these, so the sizing arithmetic reads it
    rather than restating it.
    """
    try:
        from klayout_tools.decks import get_parasitics_deck
    except ImportError as exc:  # pragma: no cover - environment error path
        raise GenError(
            "gen-ldo-blocks.py: needs `klt` importable (run it with "
            "layout/.venv/bin/python) to read the sky130 parasitics deck's "
            "sheet resistances"
        ) from exc
    deck = get_parasitics_deck(deck_name)
    return [None if rc is None else rc.sheet_res_ohm_sq for rc in deck.metals]


#: GDS purpose-0 layer of each conductor level, index-aligned with the
#: parasitics deck's own `metals` tuple (0=li1, 1=met1, 2=met2, 3=met3).
METAL_LEVEL_LAYERS: list[tuple[int, int]] = [(67, 20), (68, 20), (69, 20), (70, 20)]


def metal_min_rule_um(deck_name: str, check: str) -> dict[int, float]:
    """Per-level minimum ``check`` ("width"/"space"), from `klt`'s own DRC deck.

    Same reason as :func:`rail_sheet_rho_ohm_sq`: the deck this layout is
    checked against is the authority on its own minimum widths, so the
    tail/riser widths are floored against it rather than against a number
    restated here (met3's 0.30um minimum is 2x met1's, and a tail drawn at
    met1's minimum on met3 would be a violation this flow could have known
    about before drawing it).
    """
    try:
        from klayout_tools.decks import get_deck, get_nominal_dbu
    except ImportError as exc:  # pragma: no cover - environment error path
        raise GenError(
            "gen-ldo-blocks.py: needs `klt` importable (run it with "
            "layout/.venv/bin/python) to read the sky130 deck's minimum widths"
        ) from exc
    dbu_um = get_nominal_dbu(deck_name)
    by_layer: dict[tuple[int, int], float] = {}
    for rule in get_deck(deck_name):
        if getattr(rule, "check", None) != check:
            continue
        layer = getattr(rule, "layer", None)
        threshold = getattr(rule, "threshold_dbu", None)
        if layer is None or threshold is None:
            continue
        key = (int(layer[0]), int(layer[1]))
        # The most restrictive rule of this kind on this layer wins.
        by_layer[key] = max(by_layer.get(key, 0.0), float(threshold) * dbu_um)
    found = {
        level: by_layer[layer]
        for level, layer in enumerate(METAL_LEVEL_LAYERS)
        if layer in by_layer
    }
    if not found:
        raise GenError(
            f"the {deck_name} deck declares no '{check}' rule on any of "
            f"{METAL_LEVEL_LAYERS} -- the rule shape changed and this flow "
            "would silently fall back to a guessed conductor geometry"
        )
    return found


def power_pad_strap_width_um(
    nets: dict[str, list[dict[str, Any]]],
    power_nets: dict[str, dict[str, Any]],
    deck_name: str,
) -> float:
    """Width of the met1 strap drawn over each load-current terminal's own
    li1 pad -- as wide as the drawn port pitch and the deck's own met1
    spacing rule allow, not a number chosen here.

    The strap is a *conductor* (it carries that unit device's whole share of
    the load current down the pad), so it wants every micron of width the
    geometry has room for; the only thing bounding it is the closest other
    load-current terminal in the same block, since nothing else in a block is
    drawn on met1 at the pad's own height.
    """
    min_width = metal_min_rule_um(deck_name, "width").get(1, TRUNK_W_UM)
    min_space = metal_min_rule_um(deck_name, "space").get(1, TRUNK_W_UM)
    by_block: dict[str, list[float]] = {}
    for net in power_nets:
        for terminal in nets.get(net, []):
            by_block.setdefault(terminal["block"], []).append(terminal["x_um"])
    pitch = math.inf
    for xs in by_block.values():
        ordered = sorted(xs)
        for left, right in zip(ordered, ordered[1:]):
            pitch = min(pitch, right - left)
    if not math.isfinite(pitch):
        return POWER_PAD_STRAP_MAX_W_UM
    width = pitch - min_space - POWER_PAD_STRAP_MARGIN_UM
    return max(min_width, min(POWER_PAD_STRAP_MAX_W_UM, width))


def parallel_sheet_rho(rho_ohm_sq: list[float | None], levels: tuple[int, int]) -> float:
    """Sheet resistance of two strapped metal levels carrying in parallel."""
    conductance = 0.0
    for level in levels:
        if level >= len(rho_ohm_sq) or rho_ohm_sq[level] is None:
            raise GenError(f"parasitics deck declares no sheet rho for metal level {level}")
        rho = rho_ohm_sq[level]
        assert rho is not None
        if rho <= 0.0:
            raise GenError(f"non-positive sheet rho for metal level {level}: {rho}")
        conductance += 1.0 / rho
    return 1.0 / conductance


def power_rail_width_um(
    span_um: float,
    current_a: float,
    budget_v: float,
    rho_ohm_sq: float,
    max_w_um: float,
    min_w_um: float,
) -> dict[str, float]:
    """Width of one load-current rail, from the current it carries.

    ``W = rho_sheet * L / R_budget`` with ``R_budget = budget_v / current_a``
    -- i.e. the rail is exactly as wide as it must be for the ratified load
    current to drop no more than its share of the ratified dropout budget
    across the span it actually carries that current over. Clamped to
    ``[min_w_um, max_w_um]``; the required and drawn widths and the resulting
    drop are both reported so a clamp is visible in the record rather than
    silent.
    """
    if span_um <= 0.0 or current_a <= 0.0 or budget_v <= 0.0:
        raise GenError("power rail sizing needs a positive span, current and budget")
    r_budget_ohm = budget_v / current_a
    required_w_um = rho_ohm_sq * span_um / r_budget_ohm
    drawn_w_um = max(min_w_um, min(required_w_um, max_w_um))
    r_drawn_ohm = rho_ohm_sq * span_um / drawn_w_um
    return {
        "span_um": span_um,
        "current_a": current_a,
        "ir_budget_v": budget_v,
        "sheet_rho_ohm_sq": rho_ohm_sq,
        "resistance_budget_ohm": r_budget_ohm,
        "required_width_um": required_w_um,
        "width_um": drawn_w_um,
        "resistance_ohm": r_drawn_ohm,
        "ir_drop_v": r_drawn_ohm * current_a,
        "width_clamped": drawn_w_um < required_w_um - 1e-9,
    }


# --------------------------------------------------------------------------
# klt block generation + placement
# --------------------------------------------------------------------------


def _run_klt(klt: str, *args: str) -> dict[str, Any]:
    proc = subprocess.run(
        [klt, *args, "--format", "json"], check=True, capture_output=True, text=True
    )
    return json.loads(proc.stdout)


def generate_blocks(
    klt: str, pdk_variant: str, out_dir: Path, devices: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for device in devices:
        block_id = device["id"]
        if device["kind"] == "mos":
            units, unit_w = plan_units(device["w_total_um"])
            device["units"] = units
            device["unit_w_um"] = unit_w
            params = {
                "w_um": unit_w,
                "l_um": device["l_um"],
                "fingers": 1,
                "rows": 1,
                "cols": units,
                "dummy": 0,
                "topology": "array",
                "flavor": device["flavor"],
                "voltage_flavor": device["voltage_flavor"],
                "gate_contact": True,
            }
            generator = "mos_array"
        else:
            params = {
                "length_um": device["length_um"],
                "width_um": device["width_um"],
                "num": 1,
                "dummy": 0,
                "flavor": device["flavor"],
            }
            generator = "res_array"
        report = _run_klt(
            klt,
            "gen",
            generator,
            "--pdk",
            pdk_variant,
            "--cell-name",
            block_id,
            "--params",
            json.dumps(params),
            "-o",
            str(out_dir / f"{block_id}.gds"),
        )
        if device["kind"] == "mos":
            # `klt gen` never *rejects* an unresolvable `voltage_flavor` -- it
            # reports the miss through `drc_hints` and draws no marker (see
            # `_voltage_flavor_mark_layer`'s "None means absent" contract). A
            # silent miss here is exactly the failure mode issue #142 exists
            # to close, so check the report rather than assume the request
            # took effect.
            hints = report.get("drc_hints", {})
            if not hints.get("voltage_flavor_mark_present"):
                raise GenError(
                    f"{block_id}: `klt gen mos_array` resolved no marker layer "
                    f"for voltage_flavor={device['voltage_flavor']!r} on "
                    f"--pdk {pdk_variant} (drc_hints: "
                    f"{json.dumps({k: hints.get(k) for k in ('voltage_flavor', 'voltage_flavor_mark_present')})})"
                    " -- this `klt` build predates sky130 voltage-flavor "
                    "support; bump layout/requirements.txt's pin"
                )
        (out_dir / f"gen.{block_id}.json").write_text(json.dumps(report, indent=2))
        reports[block_id] = report
    return reports


def order_devices(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Row order: resistors, then every NMOS block, then every PMOS block.

    The flavor split is load-bearing, not cosmetic: the PMOS bodies are tied
    through one shared n-well drawn across the whole PMOS span, and `klt
    extract` decides a device's flavor by n-well containment (`pfet_active =
    active & nwell`). A well drawn over an interleaved NMOS block would
    re-type it. Within each super-group, blocks keep their schematic order,
    grouped by function per GROUP_ORDER, so the row still reads like
    `design/README.md`'s own functional grouping.
    """

    def group_rank(device: dict[str, Any]) -> int:
        group = device["group"]
        return GROUP_ORDER.index(group) if group in GROUP_ORDER else len(GROUP_ORDER)

    def super_group(device: dict[str, Any]) -> int:
        if device["kind"] == "res":
            return 0
        return 1 if device["flavor"] == "nfet" else 2

    return sorted(
        devices,
        key=lambda d: (super_group(d), group_rank(d), d["index"]),
    )


def plan_placement(
    devices: list[dict[str, Any]], reports: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Pack every block into one bottom-aligned row and reserve the two
    body-tie slots. Returns the placement plan the compose request and the
    router both read."""
    order: list[str] = []
    origins: dict[str, dict[str, float]] = {}
    placed: dict[str, dict[str, float]] = {}
    rows: list[dict[str, Any]] = []

    x_cursor = 0.0
    prev_super: int | None = None
    subtap_x: float | None = None
    nwtap_x: float | None = None
    nwell_x0: float | None = None
    nwell_x1: float | None = None

    for device in devices:
        block_id = device["id"]
        bbox = reports[block_id]["bbox_um"]
        is_pmos = device["kind"] == "mos" and device["flavor"] == "pfet"
        is_nmos = device["kind"] == "mos" and device["flavor"] == "nfet"
        super_group = 0 if device["kind"] == "res" else (1 if is_nmos else 2)
        if prev_super is not None and super_group != prev_super:
            x_cursor += GROUP_GAP_UM
            if super_group == 1:
                # Substrate tie sits at the head of the NMOS span, outside
                # every n-well.
                subtap_x = x_cursor + TAP_SLOT_UM / 2
                x_cursor += TAP_SLOT_UM + GROUP_GAP_UM
            if super_group == 2:
                nwtap_x = x_cursor + TAP_SLOT_UM / 2
                nwell_x0 = x_cursor - 1.0
                x_cursor += TAP_SLOT_UM + BLOCK_GAP_UM
        prev_super = super_group

        origin_x = x_cursor - bbox["x0"]
        origin_y = -bbox["y0"]
        origins[block_id] = {"x": origin_x, "y": origin_y}
        placed[block_id] = {
            "x0": bbox["x0"] + origin_x,
            "y0": 0.0,
            "x1": bbox["x1"] + origin_x,
            "y1": bbox["y1"] + origin_y,
        }
        order.append(block_id)
        x_cursor = placed[block_id]["x1"] + BLOCK_GAP_UM
        if is_pmos:
            nwell_x1 = placed[block_id]["x1"] + 1.0
        device["placed_bbox_um"] = placed[block_id]

    for group in GROUP_ORDER:
        members = [d["id"] for d in devices if d["group"] == group]
        if not members:
            continue
        rows.append(
            {
                "group": group,
                "blocks": members,
                "x0_um": min(placed[b]["x0"] for b in members),
                "x1_um": max(placed[b]["x1"] for b in members),
                "height_um": max(placed[b]["y1"] for b in members),
            }
        )

    if subtap_x is None or nwtap_x is None or nwell_x0 is None or nwell_x1 is None:
        raise GenError("placement produced no NMOS or no PMOS span to tie")

    return {
        "order": order,
        "origins_um": origins,
        "placed_bboxes_um": placed,
        "groups": rows,
        "row_width_um": x_cursor,
        "row_height_um": max(b["y1"] for b in placed.values()),
        "subtap_x_um": subtap_x,
        "nwtap_x_um": nwtap_x,
        "nwell_x0_um": nwell_x0,
        "nwell_x1_um": nwell_x1,
        "block_gap_um": BLOCK_GAP_UM,
        "group_gap_um": GROUP_GAP_UM,
    }


def build_compose_request(
    out_dir: Path,
    pdk_variant: str,
    plan: dict[str, Any],
    cell_name: str,
) -> dict[str, Any]:
    return {
        "schema": "klt.gen_compose.request/1",
        "pdk": {"variant": pdk_variant},
        "blocks": [
            {"id": block_id, "generator_report": f"gen.{block_id}.json"}
            for block_id in plan["order"]
        ],
        "placement": {
            "strategy": "explicit",
            "order": plan["order"],
            "origins_um": plan["origins_um"],
        },
        "options": {
            "cell_name": cell_name,
            "output": str(out_dir / f"{cell_name}.placed.gds"),
        },
    }


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------


def collect_terminals(
    devices: list[dict[str, Any]],
    reports: dict[str, dict[str, Any]],
    plan: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Map every schematic net to the composed-frame port positions it owns.

    A MOS block's `units` parallel unit devices all belong to the same
    schematic device, so every unit's S/D/G port joins the same net -- that
    strapping is what makes the drawn units a single `W_total`-wide device
    after `klt lvs`'s options.combine_devices folds them.
    """
    nets: dict[str, list[dict[str, Any]]] = {}
    for device in devices:
        block_id = device["id"]
        offset = plan["origins_um"][block_id]
        ports = {p["name"]: p for p in reports[block_id]["ports"]}
        if device["kind"] == "mos":
            terminal_ports = {
                "S": [f"U{i}_S" for i in range(device["units"])],
                "D": [f"U{i}_D" for i in range(device["units"])],
                "G": [f"U{i}_G" for i in range(device["units"])],
            }
        else:
            terminal_ports = {"A": ["R0_A"], "B": ["R0_B"]}
        for terminal, port_names in terminal_ports.items():
            net = device["nets"][terminal]
            for port_name in port_names:
                port = ports.get(port_name)
                if port is None:
                    raise GenError(f"{block_id}: generator reported no {port_name}")
                # A source/drain/resistor port is a *pad*, not a point: the
                # generator reports the port's own extent as `width_um`, along
                # y for the 0/180-degree (side-facing) ports this row's
                # blocks present. The power-rail path contacts that whole
                # extent rather than its midpoint, so it is carried here.
                extent_um = float(port.get("width_um") or 0.0)
                vertical_pad = int(round(float(port.get("direction_deg", 0)))) % 180 == 0
                y_um = port["y_um"] + offset["y"]
                half = extent_um / 2.0 if vertical_pad else 0.0
                nets.setdefault(net, []).append(
                    {
                        "block": block_id,
                        "port": port_name,
                        "terminal": terminal,
                        "x_um": port["x_um"] + offset["x"],
                        "y_um": y_um,
                        "pad_y0_um": y_um - half,
                        "pad_y1_um": y_um + half,
                        "riser": terminal == "G",
                        "block_top_um": plan["placed_bboxes_um"][block_id]["y1"],
                    }
                )
    return nets


def assign_tracks(
    nets: dict[str, list[dict[str, Any]]],
    body_nets: dict[str, str],
    power_nets: dict[str, dict[str, Any]],
) -> dict[str, float]:
    """One horizontal met1 trunk per *signal* net, in the channel below the row.

    Tracks are ordered by each net's leftmost terminal so a net's trunk sits
    near the blocks it serves, which keeps the drawn trunk lengths (and the
    riser count crossing them) close to the minimum this single-channel
    topology allows.

    The load-current nets are deliberately absent: they are drawn as rails
    above the row instead (:func:`plan_power_rails`), so they neither occupy
    a signal track nor lengthen every other net's li1 drop past a wide rail.
    """
    routed = sorted(
        (net for net in nets if net not in power_nets),
        key=lambda net: (min(t["x_um"] for t in nets[net]), net),
    )
    tracks: dict[str, float] = {}
    for index, net in enumerate(routed):
        tracks[net] = CHANNEL_TOP_UM - index * TRACK_PITCH_UM
    for net in body_nets.values():
        if net not in tracks and net not in power_nets:
            raise GenError(f"body net {net} has no routed terminals")
    return tracks


def plan_power_rails(
    nets: dict[str, list[dict[str, Any]]],
    power_nets: dict[str, dict[str, Any]],
    plan: dict[str, Any],
    body_nets: dict[str, str],
    spec: SpecConstants,
    deck_name: str,
) -> dict[str, Any]:
    """Geometry and sizing for every load-current rail.

    Each rail is a two-level strapped conductor drawn *above* the device row,
    stacked in its own y band:

    * a **wide segment** over the x span across which the rail actually
      carries the full load current -- the span of the pass device's own
      terminals on that net. Its width comes from
      :func:`power_rail_width_um`, i.e. from the ratified load current and
      the rail's share of the ratified dropout budget, not from a constant;
    * a **tail** at signal width over the rest of the net's span. The tail
      reaches the feedback divider / bias resistor, which draw microamps: it
      is a sense connection, not a power conductor, and drawing it as wide as
      the rail would state a current it never carries.

    Band 0 sits closest to the row; band 1 sits above it. A band-1 terminal's
    riser crosses band 0, which is why the two bands' metal levels are offset
    by one (`RAIL_BAND_LEVELS`): the crossing happens on a level band 0 does
    not occupy.
    """
    rho_ohm_sq = rail_sheet_rho_ohm_sq(deck_name)
    min_w_um = metal_min_rule_um(deck_name, "width")
    row_top_um = plan["row_height_um"]
    # The highest drawn thing over the row is a gate riser's met1 landing pad
    # / met2 turn, RISER_CLEAR_UM above its own block's top.
    riser_top_um = row_top_um + RISER_CLEAR_UM + TRUNK_W_UM / 2.0
    transition_y_um = riser_top_um + POWER_TRANSITION_CLEAR_UM + POWER_VIA_PAD_UM / 2.0
    band_cursor = transition_y_um + POWER_VIA_PAD_UM / 2.0 + RAIL_CLEAR_UM

    max_w_um = POWER_RAIL_MAX_W_FRACTION_OF_ROW * row_top_um
    budget_per_rail_v = POWER_RAIL_IR_SHARE * spec.dropout_target_v / len(power_nets)

    # Deterministic band order: the drain net (the regulated output) takes the
    # band closest to the devices, so its conductor makes the fewest level
    # transitions between the pass device and the rail.
    ordered = sorted(power_nets, key=lambda net: (power_nets[net]["terminal"], net))
    if len(ordered) > len(RAIL_BAND_LEVELS):
        raise GenError(
            f"{len(ordered)} load-current nets but only "
            f"{len(RAIL_BAND_LEVELS)} rail bands are defined"
        )

    rails: dict[str, dict[str, Any]] = {}
    for index, net in enumerate(ordered):
        terminals = nets.get(net)
        if not terminals:
            raise GenError(f"load-current net {net} has no routed terminals")
        pass_device = power_nets[net]["device"]
        carrying = [t for t in terminals if t["block"] == pass_device]
        if not carrying:
            raise GenError(f"load-current net {net} has no pass-device terminal")
        xs = [t["x_um"] for t in terminals]
        if body_nets.get("pmos") == net:
            xs.append(plan["nwtap_x_um"])
        if body_nets.get("nmos") == net:
            xs.append(plan["subtap_x_um"])
        hot_x0 = min(t["x_um"] for t in carrying)
        hot_x1 = max(t["x_um"] for t in carrying)
        levels = RAIL_BAND_LEVELS[index]
        sizing = power_rail_width_um(
            span_um=hot_x1 - hot_x0,
            current_a=spec.full_load_a,
            budget_v=budget_per_rail_v,
            rho_ohm_sq=parallel_sheet_rho(rho_ohm_sq, levels),
            max_w_um=max_w_um,
            min_w_um=TRUNK_W_UM,
        )
        width = sizing["width_um"]
        # The tail must satisfy the widest minimum-width rule of either level
        # it is drawn on, plus a DBU-scale margin so a rule stated at exactly
        # the drawn width cannot fail on rounding.
        tail_w = max(
            TRUNK_W_UM,
            *(min_w_um.get(level, 0.0) + 0.02 for level in levels),
        )
        rails[net] = {
            "net": net,
            "band": index,
            "levels": list(levels),
            "pass_device": pass_device,
            "terminal_count": len(terminals),
            "carrying_terminal_count": len(carrying),
            "y0_um": band_cursor,
            "y1_um": band_cursor + width,
            # Both spans are extended by a riser half-width plus a margin, so
            # every riser that lands on them is fully covered rather than
            # overhanging into a sliver at the rail's end.
            "hot_x0_um": hot_x0 - RAIL_END_MARGIN_UM,
            "hot_x1_um": hot_x1 + RAIL_END_MARGIN_UM,
            "x0_um": min(xs) - RAIL_END_MARGIN_UM,
            "x1_um": max(xs) + RAIL_END_MARGIN_UM,
            "tail_width_um": tail_w,
            "transition_y_um": transition_y_um,
            "sizing": sizing,
        }
        band_cursor = band_cursor + width + RAIL_GAP_UM

    return {
        "rails": rails,
        "order": ordered,
        "pad_strap_width_um": power_pad_strap_width_um(nets, power_nets, deck_name),
        "mcon_pitch_um": POWER_MCON_PITCH_UM,
        "rail_via_pitch_um": RAIL_VIA_PITCH_UM,
        "transition_y_um": transition_y_um,
        "top_y_um": band_cursor - RAIL_GAP_UM,
        "ir_budget_share_of_dropout": POWER_RAIL_IR_SHARE,
        "ir_budget_per_rail_v": budget_per_rail_v,
        "max_width_um": max_w_um,
        "spec": {
            "source": spec.source,
            "full_load_a": spec.full_load_a,
            "dropout_target_v": spec.dropout_target_v,
        },
        "metal_sheet_rho_ohm_sq": rho_ohm_sq,
    }


def route_composed_cell(
    placed_gds: Path,
    output_gds: Path,
    cell_name: str,
    devices: list[dict[str, Any]],
    nets: dict[str, list[dict[str, Any]]],
    tracks: dict[str, float],
    plan: dict[str, Any],
    body_nets: dict[str, str],
    pin_nets: list[str],
    rail_plan: dict[str, Any],
) -> dict[str, Any]:
    """Draw the block's inter-block wiring into the composed cell.

    Two topologies, because the block has two kinds of net (issue #154).

    **Signal nets** -- a single routing channel below the device row, with
    one met1 trunk per net:

    * every source/drain terminal drops straight down from its own li1 pad on
      li1 (the pads already run the full device height), and lands on its
      net's trunk through an mcon;
    * every gate terminal rises out of the top of its block on li1, transfers
      to met2 (mcon -> met1 landing pad -> via1) and runs back down *over* its
      own block on met2 -- the second routing level exists precisely so a gate
      can reach the channel without crossing the met1 trunks stacked in it --
      then lands on its trunk through a second via1;
    * the substrate tie (outside every well) drops onto its trunk the same way
      a source/drain terminal does.

    **Load-current nets** -- rails above the row instead of trunks below it,
    because a 0.30um channel trunk is a signal wire and these two nets carry
    every milliamp the block delivers:

    * each unit device's li1 source/drain pad is strapped over its *whole*
      height by met1, contacted by an mcon every POWER_MCON_PITCH_UM, so the
      unit's share of the load current leaves the ~12.8 ohm/square local
      interconnect within a micron or so of where it enters it, instead of
      running up to half a device height along it to a single contact;
    * that strap rises past the gate risers' landing pads to the rail band,
      on met1 for the lower band and on met3 for the upper one -- the upper
      band's risers have to cross the lower band, and met3 is the level the
      lower band does not occupy;
    * each rail band is two metal levels strapped together by a via array on
      RAIL_VIA_PITCH_UM, wide where it carries the load current and at signal
      width over the tail that only reaches a microamp-scale sense tap;
    * the n-well tie rises to its own net's rail the same way a source
      terminal does.

    Every vertical run therefore owns a unique x (ports within a block are
    >= 0.46um apart and blocks are gapped), and every horizontal run owns a
    unique y, so no two nets share drawn metal. `klt drc` is the authority on
    the result; this router only guarantees the topology.
    """
    import klayout.db as kdb

    layout = kdb.Layout()
    layout.read(str(placed_gds))
    top = layout.top_cell()
    if top.name != cell_name:
        raise GenError(f"composed cell is '{top.name}', expected '{cell_name}'")

    li1 = layout.layer(67, 20)
    met1 = layout.layer(68, 20)
    met2 = layout.layer(69, 20)
    met3 = layout.layer(70, 20)
    mcon = layout.layer(67, 44)
    via1 = layout.layer(68, 44)
    via2 = layout.layer(69, 44)
    licon = layout.layer(66, 44)
    tap = layout.layer(65, 44)
    nwell = layout.layer(64, 20)
    met1_label = layout.layer(68, 5)

    #: Conductor level index (0=li1, 1=met1, 2=met2, 3=met3) -> its drawn
    #: layer and the via layer that connects it to the level above.
    level_layer = {0: li1, 1: met1, 2: met2, 3: met3}
    level_via_up = {0: mcon, 1: via1, 2: via2}
    level_via_size = {0: MCON_UM, 1: VIA1_UM, 2: VIA2_UM}

    def box(layer: int, x0: float, y0: float, x1: float, y1: float) -> None:
        top.shapes(layer).insert(kdb.DBox(x0, y0, x1, y1))

    def square(layer: int, x: float, y: float, side: float) -> None:
        box(layer, x - side / 2, y - side / 2, x + side / 2, y + side / 2)

    def drop_to_track(x: float, y_from: float, track_y: float) -> None:
        """li1 run from a pad down onto its net's trunk, plus the mcon."""
        box(li1, x - STUB_W_UM / 2, track_y - STUB_W_UM / 2, x + STUB_W_UM / 2, y_from)
        square(mcon, x, track_y, MCON_UM)

    def gate_riser(x: float, y_from: float, block_top: float, track_y: float) -> None:
        """li1 out of the block's top, then met2 back down onto the trunk."""
        y_pad = block_top + RISER_CLEAR_UM
        box(li1, x - STUB_W_UM / 2, y_from, x + STUB_W_UM / 2, y_pad + STUB_W_UM / 2)
        square(mcon, x, y_pad, MCON_UM)
        square(met1, x, y_pad, TRUNK_W_UM)
        square(via1, x, y_pad, VIA1_UM)
        box(
            met2,
            x - TRUNK_W_UM / 2,
            track_y - TRUNK_W_UM / 2,
            x + TRUNK_W_UM / 2,
            y_pad + TRUNK_W_UM / 2,
        )
        square(via1, x, track_y, VIA1_UM)
        square(met1, x, track_y, TRUNK_W_UM)

    rails: dict[str, dict[str, Any]] = rail_plan["rails"]
    transition_y = rail_plan["transition_y_um"]
    pad_strap_w = rail_plan["pad_strap_width_um"]

    def via_array(
        via_layer: int,
        size: float,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
    ) -> int:
        """Stitch two strapped levels over a rectangle, on RAIL_VIA_PITCH_UM.

        A strapped rail is only two conductors in parallel if the two levels
        are actually tied together along their length -- one via at each end
        would leave the upper level a stub. Inset by the larger of the deck's
        enclosure rules (0.065um for met3 over via2) plus a margin.
        """
        inset = size / 2.0 + 0.10
        x_lo, x_hi = x0 + inset, x1 - inset
        y_lo, y_hi = y0 + inset, y1 - inset
        if x_hi < x_lo or y_hi < y_lo:
            return 0
        count = 0
        nx = max(1, int((x_hi - x_lo) / RAIL_VIA_PITCH_UM) + 1)
        ny = max(1, int((y_hi - y_lo) / RAIL_VIA_PITCH_UM) + 1)
        for i in range(nx):
            x = x_lo + i * RAIL_VIA_PITCH_UM
            if x > x_hi:
                break
            for j in range(ny):
                y = y_lo + j * RAIL_VIA_PITCH_UM
                if y > y_hi:
                    break
                square(via_layer, x, y, size)
                count += 1
        return count

    def draw_rail(rail: dict[str, Any]) -> int:
        """The rail itself: two strapped levels, wide where the load current
        flows and at minimum width over the sense tail."""
        lower, upper = rail["levels"]
        y0, y1 = rail["y0_um"], rail["y1_um"]
        tail_w = rail["tail_width_um"]
        segments = [
            (rail["x0_um"], y0, rail["x1_um"], y0 + tail_w),
            (rail["hot_x0_um"], y0, rail["hot_x1_um"], y1),
        ]
        vias = 0
        for sx0, sy0, sx1, sy1 in segments:
            box(level_layer[lower], sx0, sy0, sx1, sy1)
            box(level_layer[upper], sx0, sy0, sx1, sy1)
            vias += via_array(
                level_via_up[lower], level_via_size[lower], sx0, sy0, sx1, sy1
            )
        return vias

    def power_terminal(terminal: dict[str, Any], rail: dict[str, Any]) -> int:
        """One load-current terminal: a full-height mcon'd met1 strap over its
        own li1 pad, then a riser to the rail."""
        x = terminal["x_um"]
        pad_y0 = terminal["pad_y0_um"]
        pad_y1 = terminal["pad_y1_um"]
        lower = rail["levels"][0]
        half = pad_strap_w / 2.0

        # met1 over the whole li1 pad, contacted along its whole height.
        strap_y0 = min(pad_y0, terminal["y_um"]) - MCON_UM
        strap_y1 = max(pad_y1, terminal["y_um"]) + MCON_UM
        box(met1, x - half, strap_y0, x + half, strap_y1)
        mcon_lo = pad_y0 + MCON_UM
        mcon_hi = pad_y1 - MCON_UM
        if mcon_hi < mcon_lo:
            mcon_lo = mcon_hi = (pad_y0 + pad_y1) / 2.0
        mcons = 0
        y = mcon_lo
        while y <= mcon_hi + 1e-9:
            square(mcon, x, y, MCON_UM)
            mcons += 1
            y += POWER_MCON_PITCH_UM

        # Land on the rail segment this terminal's x actually sits on: the
        # wide one if it carries load current there, the tail otherwise.
        on_hot = rail["hot_x0_um"] <= x <= rail["hot_x1_um"]
        riser_top = rail["y1_um"] if on_hot else rail["y0_um"] + rail["tail_width_um"]

        riser_half = POWER_RISER_W_UM / 2.0
        if lower == 1:
            # Band 0: met1 all the way into the rail, which is met1-based.
            box(met1, x - riser_half, strap_y1, x + riser_half, riser_top)
            return mcons
        # Band 1: met1 stops below band 0, and the crossing happens on met3.
        box(met1, x - riser_half, strap_y1, x + riser_half, transition_y)
        square(met1, x, transition_y, POWER_VIA_PAD_UM)
        square(via1, x, transition_y, VIA1_UM)
        square(met2, x, transition_y, POWER_VIA_PAD_UM)
        square(via2, x, transition_y, VIA2_UM)
        m3_half = POWER_MET3_RISER_W_UM / 2.0
        box(
            met3,
            x - m3_half,
            transition_y - POWER_MET3_RISER_W_UM / 2.0,
            x + m3_half,
            riser_top,
        )
        return mcons

    # --- n-well over the whole PMOS span + its own well tie ----------------
    row_top = plan["row_height_um"]
    box(nwell, plan["nwell_x0_um"], -1.0, plan["nwell_x1_um"], row_top + 1.0)

    def body_tie(x: float, net: str, inside_well: bool) -> dict[str, Any]:
        # Both ties sit in a reserved x slot in the row itself (y > 0), so the
        # only thing that distinguishes them is whether that slot is inside
        # the drawn n-well -- which is what `klt extract` splits `tap` by.
        y0 = 1.0
        box(tap, x - 0.75, y0, x + 0.75, y0 + 1.5)
        square(licon, x, y0 + 0.75, MCON_UM)
        square(li1, x, y0 + 0.75, 0.42)
        if net in rails:
            # The well tie belongs to a load-current net: it rises to that
            # net's rail exactly as a source terminal does, rather than
            # dropping onto a channel trunk that no longer exists.
            power_terminal(
                {
                    "x_um": x,
                    "y_um": y0 + 0.75,
                    "pad_y0_um": y0 + 0.75 - 0.21,
                    "pad_y1_um": y0 + 0.75 + 0.21,
                },
                rails[net],
            )
        else:
            drop_to_track(x, y0 + 0.75, tracks[net])
        return {
            "kind": "nwell_tie" if inside_well else "substrate_tie",
            "net": net,
            "x_um": x,
        }

    ties = [
        body_tie(plan["nwtap_x_um"], body_nets["pmos"], inside_well=True),
        body_tie(plan["subtap_x_um"], body_nets["nmos"], inside_well=False),
    ]

    # --- one trunk per signal net, plus every terminal's drop/riser --------
    net_summaries: list[dict[str, Any]] = []
    for net, terminals in sorted(nets.items()):
        if net in rails:
            rail = rails[net]
            mcons = sum(power_terminal(t, rail) for t in terminals)
            rail["via_count"] = draw_rail(rail)
            rail["mcon_count"] = mcons
            label_x = (rail["hot_x0_um"] + rail["hot_x1_um"]) / 2.0
            label_y = (rail["y0_um"] + rail["y1_um"]) / 2.0
            # Labelled on the rail's own lower level -- which for band 1 is
            # met2, so the label layer follows the level rather than being
            # pinned to met1.pin. The label sits on the wide segment, i.e. at
            # the pass device: that is physically where the block's power pin
            # is, not out at the microamp-scale sense tap.
            label_layer = layout.layer(67 + rail["levels"][0], 5)
            top.shapes(label_layer).insert(
                kdb.DText(net, kdb.DTrans(kdb.DVector(label_x, label_y)))
            )
            net_summaries.append(
                {
                    "net": net,
                    "kind": "power_rail",
                    "band": rail["band"],
                    "levels": rail["levels"],
                    "terminal_count": len(terminals),
                    "riser_count": 0,
                    "rail_y0_um": rail["y0_um"],
                    "rail_y1_um": rail["y1_um"],
                    "trunk_x0_um": rail["x0_um"],
                    "trunk_x1_um": rail["x1_um"],
                    "hot_x0_um": rail["hot_x0_um"],
                    "hot_x1_um": rail["hot_x1_um"],
                    "width_um": rail["sizing"]["width_um"],
                    "tail_width_um": rail["tail_width_um"],
                    "mcon_count": mcons,
                    "via_count": rail["via_count"],
                    "sizing": rail["sizing"],
                }
            )
            continue
        track_y = tracks[net]
        xs: list[float] = []
        for terminal in terminals:
            x = terminal["x_um"]
            xs.append(x)
            if terminal["riser"]:
                gate_riser(x, terminal["y_um"], terminal["block_top_um"], track_y)
            else:
                drop_to_track(x, terminal["y_um"], track_y)
        if net == body_nets["pmos"]:
            xs.append(plan["nwtap_x_um"])
        if net == body_nets["nmos"]:
            xs.append(plan["subtap_x_um"])
        x0, x1 = min(xs), max(xs)
        box(
            met1,
            x0 - TRUNK_W_UM / 2,
            track_y - TRUNK_W_UM / 2,
            x1 + TRUNK_W_UM / 2,
            track_y + TRUNK_W_UM / 2,
        )
        # Name every routed net on met1.pin, under its own schematic net name,
        # so the extracted netlist reads in schematic terms and `klt lvs` has
        # no name/identity conflict to report; `klt extract --pins` decides
        # which of them stay top-level pins. Labelling the ground trunk
        # matters most: it names the net the drawn substrate tie merges into,
        # so the body terminals resolve to the schematic's own `0` rather than
        # to the deck's synthesized `vsubs` global.
        top.shapes(met1_label).insert(
            kdb.DText(net, kdb.DTrans(kdb.DVector(x0, track_y)))
        )
        net_summaries.append(
            {
                "net": net,
                "kind": "signal_trunk",
                "track_y_um": track_y,
                "terminal_count": len(terminals),
                "riser_count": sum(1 for t in terminals if t["riser"]),
                "trunk_x0_um": x0,
                "trunk_x1_um": x1,
            }
        )

    layout.write(str(output_gds))
    return {
        "channel_top_um": CHANNEL_TOP_UM,
        "track_pitch_um": TRACK_PITCH_UM,
        "stub_width_um": STUB_W_UM,
        "signal_trunk_width_um": TRUNK_W_UM,
        # Kept under its pre-#154 name too: a per-net conductor width means
        # there is no longer one `trunk_width_um` for the whole block, and a
        # reader of an older record should see the signal-net value here
        # rather than a key that silently changed meaning.
        "trunk_width_um": TRUNK_W_UM,
        "net_count": len(net_summaries),
        "terminal_count": sum(n["terminal_count"] for n in net_summaries),
        "signal_net_count": sum(
            1 for n in net_summaries if n.get("kind") != "power_rail"
        ),
        "power_rail_count": sum(
            1 for n in net_summaries if n.get("kind") == "power_rail"
        ),
        "power_rails": {
            key: value for key, value in rail_plan.items() if key != "rails"
        }
        | {
            "rails": [
                {k: v for k, v in rails[net].items()} for net in rail_plan["order"]
            ]
        },
        "body_ties": ties,
        "nets": net_summaries,
    }


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--klt", required=True)
    ap.add_argument("--pdk-variant", required=True)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--cell-name", default="ldo_core")
    ap.add_argument(
        "--netlist",
        required=True,
        type=Path,
        help="xschem-generated SPICE netlist of design/ldo_3v3in_1v8out.sch",
    )
    ap.add_argument(
        "--pins",
        default="VOUT,VREF,EN,VIN",
        help="comma-separated top-level pin nets (labelled for `klt extract --pins`)",
    )
    ap.add_argument(
        "--spec",
        required=True,
        type=Path,
        help=(
            "spec/target-spec.md -- the ratified load current and dropout "
            "budget the power rails are sized from (issue #154)"
        ),
    )
    ap.add_argument(
        "--deck",
        default="sky130",
        help="klt deck to read sheet resistances and minimum widths from",
    )
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    devices, skipped = parse_netlist(args.netlist)
    for index, device in enumerate(devices):
        device["index"] = index
        device["group"] = assign_group(device)

    reports = generate_blocks(args.klt, args.pdk_variant, out_dir, devices)
    ordered = order_devices(devices)
    plan = plan_placement(ordered, reports)

    request = build_compose_request(out_dir, args.pdk_variant, plan, args.cell_name)
    request_path = out_dir / "compose.request.json"
    request_path.write_text(json.dumps(request, indent=2))
    compose_report = _run_klt(args.klt, "gen-compose", str(request_path))
    (out_dir / "compose.json").write_text(json.dumps(compose_report, indent=2))

    nets = collect_terminals(ordered, reports, plan)
    body_nets = {
        "pmos": next(
            d["nets"]["B"] for d in ordered if d["kind"] == "mos" and d["flavor"] == "pfet"
        ),
        "nmos": next(
            d["nets"]["B"] for d in ordered if d["kind"] == "mos" and d["flavor"] == "nfet"
        ),
    }
    for device in ordered:
        if device["kind"] != "mos":
            continue
        expected = body_nets["pmos" if device["flavor"] == "pfet" else "nmos"]
        if device["nets"]["B"] != expected:
            raise GenError(
                f"{device['id']}: body net {device['nets']['B']} differs from the "
                f"shared {device['flavor']} body net {expected} -- this layout ties "
                "each flavor's bodies with one drawn tie, so a per-device body net "
                "would need its own tie"
            )
    spec = read_spec_constants(args.spec)
    power_nets = identify_power_nets(ordered)
    rail_plan = plan_power_rails(nets, power_nets, plan, body_nets, spec, args.deck)
    tracks = assign_tracks(nets, body_nets, power_nets)
    pin_nets = [p for p in args.pins.split(",") if p]

    routing = route_composed_cell(
        out_dir / f"{args.cell_name}.placed.gds",
        out_dir / f"{args.cell_name}.gds",
        args.cell_name,
        ordered,
        nets,
        tracks,
        plan,
        body_nets,
        pin_nets,
        rail_plan,
    )

    floorplan = {
        "source_netlist": str(args.netlist),
        "device_count": len(devices),
        "mos_count": sum(1 for d in devices if d["kind"] == "mos"),
        "res_count": sum(1 for d in devices if d["kind"] == "res"),
        # Per-marker MOS counts (issue #142). Every MOS block is drawn inside
        # its schematic model's own voltage-domain marker, so this is also
        # the count `klt extract --pdk` should bind to that flavor's real
        # subcircuit -- the number the LVS/PEX records are checked against.
        "mos_voltage_flavor_counts": {
            flavor: sum(
                1
                for d in devices
                if d["kind"] == "mos" and d["voltage_flavor"] == flavor
            )
            for flavor in sorted(
                {d["voltage_flavor"] for d in devices if d["kind"] == "mos"}
            )
        },
        "block_count": len(plan["order"]),
        "undrawn_elements": skipped,
        "max_unit_w_um": MAX_UNIT_W_UM,
        "row_width_um": plan["row_width_um"],
        "row_height_um": plan["row_height_um"],
        "groups": plan["groups"],
        "body_nets": body_nets,
        "power_nets": power_nets,
        "pin_nets": pin_nets,
        "devices": [
            {
                "id": d["id"],
                "name": d["name"],
                "kind": d["kind"],
                "group": d["group"],
                "flavor": d["flavor"],
                "model": d.get("model"),
                "voltage_flavor": d.get("voltage_flavor"),
                "units": d.get("units", 1),
                "unit_w_um": d.get("unit_w_um"),
                "w_total_um": d.get("w_total_um"),
                "l_um": d.get("l_um"),
                "length_um": d.get("length_um"),
                "width_um": d.get("width_um"),
                "nets": d["nets"],
                "placed_bbox_um": d["placed_bbox_um"],
            }
            for d in ordered
        ],
        "routing": routing,
    }
    (out_dir / "floorplan.json").write_text(json.dumps(floorplan, indent=2))

    print(
        json.dumps(
            {
                "devices": floorplan["device_count"],
                "blocks": floorplan["block_count"],
                "undrawn_elements": skipped,
                "routing": {
                    k: v
                    for k, v in routing.items()
                    if k not in ("nets", "body_ties", "power_rails")
                },
                "power_rails": [
                    {
                        "net": r["net"],
                        "band": r["band"],
                        "levels": r["levels"],
                        "width_um": round(r["sizing"]["width_um"], 3),
                        "required_width_um": round(
                            r["sizing"]["required_width_um"], 3
                        ),
                        "width_clamped": r["sizing"]["width_clamped"],
                        "resistance_ohm": round(r["sizing"]["resistance_ohm"], 4),
                        "ir_drop_v": round(r["sizing"]["ir_drop_v"], 6),
                    }
                    for r in routing["power_rails"]["rails"]
                ],
                "compose": {
                    "bbox_um": compose_report.get("bbox_um"),
                    "unrouted_nets": compose_report.get("unrouted_nets"),
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
