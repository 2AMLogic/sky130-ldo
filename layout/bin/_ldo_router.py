"""The LDO core layout's inter-block channel router (issues #33/#154),
extracted from `gen-ldo-blocks.py` (issue #781).

This is the only module in the layout flow that touches ``klayout.db``:
`gen-ldo-blocks.py` orchestrates the `klt gen` / `gen-compose` pipeline and
hands the composed cell to :func:`route_composed_cell` here, which draws the
signal trunks, the load-current rails, and the body ties into it.

``import klayout.db`` stays *inside* :func:`route_composed_cell` so importing
this module (and `gen-ldo-blocks.py`, which imports it) never requires
``klayout`` -- the plain-``python3`` layout unit tests depend on that.

The channel geometry constants live here with the router that defines the
channel topology; `gen-ldo-blocks.py`'s ``assign_tracks`` imports them.
Conductor sizing constants and the rail planner live in ``_power_rails.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from _power_rails import (
    ADJ_ENCLOSURE_UM,
    MCON_UM,
    POWER_MET3_RISER_W_UM,
    POWER_MCON_PITCH_UM,
    POWER_RISER_W_UM,
    POWER_VIA_PAD_UM,
    RAIL_VIA_PITCH_UM,
    RISER_CLEAR_UM,
    STUB_W_UM,
    TRUNK_W_UM,
    VIA1_UM,
    VIA2_UM,
    GenError,
)

TRACK_PITCH_UM = 0.8  # between adjacent net trunks
CHANNEL_TOP_UM = -3.0  # first trunk's y (the row's blocks sit at y >= 0)


class _Canvas:
    """The composed cell's drawing surface.

    Holds the layer handles, the conductor-level tables the rail primitives
    index, and the rail-plan values the power primitives share, so every
    drawing primitive the router uses is an independently readable method
    rather than a closure over ``route_composed_cell``'s locals (issue #781).
    """

    def __init__(
        self,
        kdb: Any,
        layout: Any,
        top: Any,
        rail_plan: dict[str, Any],
        tracks: dict[str, float],
    ) -> None:
        self.kdb = kdb
        self.layout = layout
        self.top = top
        self.tracks = tracks
        self.rails: dict[str, dict[str, Any]] = rail_plan["rails"]
        self.transition_y: float = rail_plan["transition_y_um"]
        self.pad_strap_w: float = rail_plan["pad_strap_width_um"]

        self.li1 = layout.layer(67, 20)
        self.met1 = layout.layer(68, 20)
        self.met2 = layout.layer(69, 20)
        self.met3 = layout.layer(70, 20)
        self.mcon = layout.layer(67, 44)
        self.via1 = layout.layer(68, 44)
        self.via2 = layout.layer(69, 44)
        self.licon = layout.layer(66, 44)
        self.tap = layout.layer(65, 44)
        self.nwell = layout.layer(64, 20)
        self.hvi = layout.layer(75, 20)
        self.met1_label = layout.layer(68, 5)

        #: Conductor level index (0=li1, 1=met1, 2=met2, 3=met3) -> its drawn
        #: layer and the via layer that connects it to the level above.
        self.level_layer = {0: self.li1, 1: self.met1, 2: self.met2, 3: self.met3}
        self.level_via_up = {0: self.mcon, 1: self.via1, 2: self.via2}
        self.level_via_size = {0: MCON_UM, 1: VIA1_UM, 2: VIA2_UM}

    # --- drawing primitives -------------------------------------------------

    def box(self, layer: int, x0: float, y0: float, x1: float, y1: float) -> None:
        self.top.shapes(layer).insert(self.kdb.DBox(x0, y0, x1, y1))

    def square(self, layer: int, x: float, y: float, side: float) -> None:
        self.box(layer, x - side / 2, y - side / 2, x + side / 2, y + side / 2)

    def text(self, layer: int, label: str, x: float, y: float) -> None:
        self.top.shapes(layer).insert(
            self.kdb.DText(label, self.kdb.DTrans(self.kdb.DVector(x, y)))
        )

    # --- signal-net primitives ----------------------------------------------

    def drop_to_track(self, x: float, y_from: float, track_y: float) -> None:
        """li1 run from a pad down onto its net's trunk, plus the mcon."""
        self.box(self.li1, x - STUB_W_UM / 2, track_y - STUB_W_UM / 2, x + STUB_W_UM / 2, y_from)
        self.square(self.mcon, x, track_y, MCON_UM)

    def gate_riser(self, x: float, y_from: float, block_top: float, track_y: float) -> None:
        """li1 out of the block's top, then met2 back down onto the trunk."""
        y_pad = block_top + RISER_CLEAR_UM
        self.box(self.li1, x - STUB_W_UM / 2, y_from, x + STUB_W_UM / 2, y_pad + STUB_W_UM / 2)
        self.square(self.mcon, x, y_pad, MCON_UM)
        # via.5a: met1 encloses the 0.15 via by only 0.075 left/right, so both
        # ends must reach >= ADJ_ENCLOSURE_UM past it.
        half_y = VIA1_UM / 2 + ADJ_ENCLOSURE_UM
        self.box(self.met1, x - TRUNK_W_UM / 2, y_pad - half_y, x + TRUNK_W_UM / 2, y_pad + half_y)
        self.square(self.via1, x, y_pad, VIA1_UM)
        self.box(
            self.met2,
            x - TRUNK_W_UM / 2,
            track_y - VIA1_UM / 2 - ADJ_ENCLOSURE_UM,
            x + TRUNK_W_UM / 2,
            y_pad + VIA1_UM / 2 + ADJ_ENCLOSURE_UM,
        )
        self.square(self.via1, x, track_y, VIA1_UM)
        # Trunk-end landing: extend along the trunk so both ends of the via
        # have >= ADJ_ENCLOSURE_UM of met1 even where the trunk stops here.
        half_x = VIA1_UM / 2 + ADJ_ENCLOSURE_UM
        self.box(
            self.met1,
            x - half_x,
            track_y - TRUNK_W_UM / 2,
            x + half_x,
            track_y + TRUNK_W_UM / 2,
        )

    # --- power-rail primitives ----------------------------------------------

    def via_array(
        self,
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
                self.square(via_layer, x, y, size)
                count += 1
        return count

    def draw_rail(self, rail: dict[str, Any]) -> int:
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
            self.box(self.level_layer[lower], sx0, sy0, sx1, sy1)
            self.box(self.level_layer[upper], sx0, sy0, sx1, sy1)
            vias += self.via_array(
                self.level_via_up[lower], self.level_via_size[lower], sx0, sy0, sx1, sy1
            )
        return vias

    def power_terminal(self, terminal: dict[str, Any], rail: dict[str, Any]) -> int:
        """One load-current terminal: a full-height mcon'd met1 strap over its
        own li1 pad, then a riser to the rail."""
        x = terminal["x_um"]
        pad_y0 = terminal["pad_y0_um"]
        pad_y1 = terminal["pad_y1_um"]
        lower = rail["levels"][0]
        half = self.pad_strap_w / 2.0

        # met1 over the whole li1 pad, contacted along its whole height.
        strap_y0 = min(pad_y0, terminal["y_um"]) - MCON_UM
        strap_y1 = max(pad_y1, terminal["y_um"]) + MCON_UM
        self.box(self.met1, x - half, strap_y0, x + half, strap_y1)
        mcon_lo = pad_y0 + MCON_UM
        mcon_hi = pad_y1 - MCON_UM
        if mcon_hi < mcon_lo:
            mcon_lo = mcon_hi = (pad_y0 + pad_y1) / 2.0
        mcons = 0
        y = mcon_lo
        while y <= mcon_hi + 1e-9:
            self.square(self.mcon, x, y, MCON_UM)
            mcons += 1
            y += POWER_MCON_PITCH_UM

        # Land on the rail segment this terminal's x actually sits on: the
        # wide one if it carries load current there, the tail otherwise.
        on_hot = rail["hot_x0_um"] <= x <= rail["hot_x1_um"]
        riser_top = rail["y1_um"] if on_hot else rail["y0_um"] + rail["tail_width_um"]

        riser_half = POWER_RISER_W_UM / 2.0
        if lower == 1:
            # Band 0: met1 all the way into the rail, which is met1-based.
            self.box(self.met1, x - riser_half, strap_y1, x + riser_half, riser_top)
            return mcons
        # Band 1: met1 stops below band 0, and the crossing happens on met3.
        self.box(self.met1, x - riser_half, strap_y1, x + riser_half, self.transition_y)
        m1_half_y = VIA1_UM / 2.0 + ADJ_ENCLOSURE_UM
        self.box(
            self.met1,
            x - POWER_VIA_PAD_UM / 2.0,
            self.transition_y - m1_half_y,
            x + POWER_VIA_PAD_UM / 2.0,
            self.transition_y + m1_half_y,
        )
        self.square(self.via1, x, self.transition_y, VIA1_UM)
        # met2 landing pad: 0.30 wide, tall enough that the end enclosure of
        # both via1 (0.15) and via2 (0.20) is >= ADJ_ENCLOSURE_UM.
        pad_half_y = VIA2_UM / 2.0 + ADJ_ENCLOSURE_UM
        self.box(
            self.met2,
            x - POWER_VIA_PAD_UM / 2.0,
            self.transition_y - pad_half_y,
            x + POWER_VIA_PAD_UM / 2.0,
            self.transition_y + pad_half_y,
        )
        self.square(self.via2, x, self.transition_y, VIA2_UM)
        m3_half = POWER_MET3_RISER_W_UM / 2.0
        self.box(
            self.met3,
            x - m3_half,
            self.transition_y - POWER_MET3_RISER_W_UM / 2.0,
            x + m3_half,
            riser_top,
        )
        return mcons

    # --- body ties -----------------------------------------------------------

    def body_tie(self, x: float, net: str, inside_well: bool) -> dict[str, Any]:
        # Both ties sit in a reserved x slot in the row itself (y > 0), so the
        # only thing that distinguishes them is whether that slot is inside
        # the drawn n-well -- which is what `klt extract` splits `tap` by.
        y0 = 1.0
        self.box(self.tap, x - 0.75, y0, x + 0.75, y0 + 1.5)
        self.square(self.licon, x, y0 + 0.75, MCON_UM)
        self.square(self.li1, x, y0 + 0.75, 0.42)
        if net in self.rails:
            # The well tie belongs to a load-current net: it rises to that
            # net's rail exactly as a source terminal does, rather than
            # dropping onto a channel trunk that no longer exists.
            self.power_terminal(
                {
                    "x_um": x,
                    "y_um": y0 + 0.75,
                    "pad_y0_um": y0 + 0.75 - 0.21,
                    "pad_y1_um": y0 + 0.75 + 0.21,
                },
                self.rails[net],
            )
        else:
            self.drop_to_track(x, y0 + 0.75, self.tracks[net])
        return {
            "kind": "nwell_tie" if inside_well else "substrate_tie",
            "net": net,
            "x_um": x,
        }


def route_composed_cell(
    placed_gds: Path,
    output_gds: Path,
    cell_name: str,
    nets: dict[str, list[dict[str, Any]]],
    tracks: dict[str, float],
    plan: dict[str, Any],
    body_nets: dict[str, str],
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

    canvas = _Canvas(kdb, layout, top, rail_plan, tracks)
    rails = canvas.rails

    # --- n-well over the whole PMOS span + its own well tie ----------------
    row_top = plan["row_height_um"]
    canvas.box(canvas.nwell, plan["nwell_x0_um"], -1.0, plan["nwell_x1_um"], row_top + 1.0)
    # nwell.9: an n-well carrying hvi devices must be covered by hvi. Blocks
    # draw hvi only over their own bbox, so cover the whole well box here.
    canvas.box(canvas.hvi, plan["nwell_x0_um"], -1.0, plan["nwell_x1_um"], row_top + 1.0)

    ties = [
        canvas.body_tie(plan["nwtap_x_um"], body_nets["pmos"], inside_well=True),
        canvas.body_tie(plan["subtap_x_um"], body_nets["nmos"], inside_well=False),
    ]

    # --- one trunk per signal net, plus every terminal's drop/riser --------
    net_summaries: list[dict[str, Any]] = []
    for net, terminals in sorted(nets.items()):
        if net in rails:
            rail = rails[net]
            mcons = sum(canvas.power_terminal(t, rail) for t in terminals)
            rail["via_count"] = canvas.draw_rail(rail)
            rail["mcon_count"] = mcons
            label_x = (rail["hot_x0_um"] + rail["hot_x1_um"]) / 2.0
            label_y = (rail["y0_um"] + rail["y1_um"]) / 2.0
            # Labelled on the rail's own lower level -- which for band 1 is
            # met2, so the label layer follows the level rather than being
            # pinned to met1.pin. The label sits on the wide segment, i.e. at
            # the pass device: that is physically where the block's power pin
            # is, not out at the microamp-scale sense tap.
            label_layer = layout.layer(67 + rail["levels"][0], 5)
            canvas.text(label_layer, net, label_x, label_y)
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
                canvas.gate_riser(x, terminal["y_um"], terminal["block_top_um"], track_y)
            else:
                canvas.drop_to_track(x, terminal["y_um"], track_y)
        if net == body_nets["pmos"]:
            xs.append(plan["nwtap_x_um"])
        if net == body_nets["nmos"]:
            xs.append(plan["subtap_x_um"])
        x0, x1 = min(xs), max(xs)
        canvas.box(
            canvas.met1,
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
        canvas.text(canvas.met1_label, net, x0, track_y)
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
