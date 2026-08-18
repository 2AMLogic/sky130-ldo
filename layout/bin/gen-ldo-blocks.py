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
  `rows=1`, `cols=<units>`, `dummy=0`. `cols` splits a device wider than
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
TRACK_PITCH_UM = 0.8  # between adjacent net trunks
CHANNEL_TOP_UM = -3.0  # first trunk's y (the row's blocks sit at y >= 0)
RISER_CLEAR_UM = 1.6  # gate riser's met1 landing pad above its block's top


class GenError(RuntimeError):
    pass


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
                nets.setdefault(net, []).append(
                    {
                        "block": block_id,
                        "port": port_name,
                        "terminal": terminal,
                        "x_um": port["x_um"] + offset["x"],
                        "y_um": port["y_um"] + offset["y"],
                        "riser": terminal == "G",
                        "block_top_um": plan["placed_bboxes_um"][block_id]["y1"],
                    }
                )
    return nets


def assign_tracks(
    nets: dict[str, list[dict[str, Any]]], body_nets: dict[str, str]
) -> dict[str, float]:
    """One horizontal met1 trunk per net, in the channel below the row.

    Tracks are ordered by each net's leftmost terminal so a net's trunk sits
    near the blocks it serves, which keeps the drawn trunk lengths (and the
    riser count crossing them) close to the minimum this single-channel
    topology allows.
    """
    routed = sorted(
        nets.keys(),
        key=lambda net: (min(t["x_um"] for t in nets[net]), net),
    )
    tracks: dict[str, float] = {}
    for index, net in enumerate(routed):
        tracks[net] = CHANNEL_TOP_UM - index * TRACK_PITCH_UM
    for net in body_nets.values():
        if net not in tracks:
            raise GenError(f"body net {net} has no routed terminals")
    return tracks


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
) -> dict[str, Any]:
    """Draw the block's inter-block wiring into the composed cell.

    The topology is a single routing channel below the device row, with one
    met1 trunk per schematic net:

    * every source/drain terminal drops straight down from its own li1 pad on
      li1 (the pads already run the full device height), and lands on its
      net's trunk through an mcon;
    * every gate terminal rises out of the top of its block on li1, transfers
      to met2 (mcon -> met1 landing pad -> via1) and runs back down *over* its
      own block on met2 -- the second routing level exists precisely so a gate
      can reach the channel without crossing the met1 trunks stacked in it --
      then lands on its trunk through a second via1;
    * the two body ties (n-well tie inside the PMOS well, substrate tie
      outside every well) drop onto the `VIN` and `0` trunks the same way a
      source/drain terminal does.

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
    mcon = layout.layer(67, 44)
    via1 = layout.layer(68, 44)
    licon = layout.layer(66, 44)
    tap = layout.layer(65, 44)
    nwell = layout.layer(64, 20)
    met1_label = layout.layer(68, 5)

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

    # --- one trunk per net, plus every terminal's drop/riser ---------------
    net_summaries: list[dict[str, Any]] = []
    for net, terminals in sorted(nets.items()):
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
        "trunk_width_um": TRUNK_W_UM,
        "net_count": len(net_summaries),
        "terminal_count": sum(n["terminal_count"] for n in net_summaries),
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
    tracks = assign_tracks(nets, body_nets)
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
    )

    floorplan = {
        "source_netlist": str(args.netlist),
        "device_count": len(devices),
        "mos_count": sum(1 for d in devices if d["kind"] == "mos"),
        "res_count": sum(1 for d in devices if d["kind"] == "res"),
        "block_count": len(plan["order"]),
        "undrawn_elements": skipped,
        "max_unit_w_um": MAX_UNIT_W_UM,
        "row_width_um": plan["row_width_um"],
        "row_height_um": plan["row_height_um"],
        "groups": plan["groups"],
        "body_nets": body_nets,
        "pin_nets": pin_nets,
        "devices": [
            {
                "id": d["id"],
                "name": d["name"],
                "kind": d["kind"],
                "group": d["group"],
                "flavor": d["flavor"],
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
                    k: v for k, v in routing.items() if k not in ("nets", "body_ties")
                },
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
