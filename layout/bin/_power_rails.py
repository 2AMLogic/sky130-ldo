"""The LDO core layout flow's power-rail sizing and planning layer (issue
#154), extracted from `gen-ldo-blocks.py` (issue #781).

Everything here is pure Python over the schematic's own device list, the
ratified `spec/target-spec.md` rows, and `klt`'s own parasitics/DRC decks --
no `klayout.db`, no GDS. It lives in its own hyphenless sibling module
(matching `_netlist_common.py` / `_spec_constants.py` /
`_record_common.py`) so the other consumer of these constants and helpers
(`layout/bin/gen-cap-rail-demo.py`) can do a plain ``import _power_rails``
instead of exec'ing the whole generator through an ``importlib`` shim.

The ``klayout_tools.decks`` readers import lazily, so this module (and
everything importing it) stays importable under a plain ``python3`` with
no `klt` installed -- which the layout unit tests depend on.
"""

from __future__ import annotations

import math
from typing import Any

from _spec_constants import SpecConstants

# --- routing geometry (all >= the sky130 deck's own minimums; see
#     `klt drc --deck sky130`'s rule list) ---------------------------------
STUB_W_UM = 0.19  # li1 stub (deck minimum li1 width 0.17)
TRUNK_W_UM = 0.30  # met1 trunk / met2 riser (deck minimum 0.14)
MCON_UM = 0.17  # li1 <-> met1 via
VIA1_UM = 0.15  # met1 <-> met2 via (sky130A_mr via.1a_b: exactly 0.15 max length)
VIA2_UM = 0.20  # met2 <-> met3 via (deck minimum size 0.20)
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
#: Deck "adjacent-edge" enclosure (m2.5 / via2.5): if a metal side encloses a
#: via by less than the 0.085 um long-form enclosure, the adjacent side must
#: enclose it by >= 0.085. Metal ends extended past a via centre by
#: ``via/2 + ADJ_ENCLOSURE_UM`` satisfy it with the (narrower) sides left alone.
ADJ_ENCLOSURE_UM = 0.085
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

#: GDS purpose-0 layer of each conductor level, index-aligned with the
#: parasitics deck's own `metals` tuple (0=li1, 1=met1, 2=met2, 3=met3).
METAL_LEVEL_LAYERS: list[tuple[int, int]] = [(67, 20), (68, 20), (69, 20), (70, 20)]


class GenError(RuntimeError):
    pass


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
            "_power_rails.py: needs `klt` importable (run it with "
            "layout/.venv/bin/python) to read the sky130 parasitics deck's "
            "sheet resistances"
        ) from exc
    deck = get_parasitics_deck(deck_name)
    return [None if rc is None else rc.sheet_res_ohm_sq for rc in deck.metals]


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
            "_power_rails.py: needs `klt` importable (run it with "
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
