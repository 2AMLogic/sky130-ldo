#!/usr/bin/env python3
"""Translate design/ldo_3v3in_1v8out.sch's own xschem-generated netlist into
an LVS reference netlist `klt lvs` can compare against `klt extract`'s
output (issue #17).

Standard library only (matches this repo's other `layout/bin/` scripts).

Why a translator instead of a hand-written reference (unlike
`trivial-cell/reference.spice`): the LDO schematic has 24+ active devices
across several revisions (#14, #22), so hand-transcribing invites drift the
moment the schematic changes again. Mechanically deriving the reference from
the schematic's own netlist means a future re-run after a schematic edit
regenerates a reference that is *by construction* in sync, at the cost of
requiring `xschem` on PATH to produce the input netlist (see
`run-ldo-lvs-flow.sh`).

Two translations account for `layout/README.md`'s documented klt-deck
limitations:

- MOS model names (`sky130_fd_pr__{n,p}fet_g5v0d10v5`) collapse to `klt
  extract`'s generic, flavor-agnostic `nfet`/`pfet` classes -- the deck does
  not disambiguate voltage flavor structurally (see "No voltage-flavor
  distinction on MOS devices").
- `mult` is folded into the emitted width (`W_total = W * mult`), matching
  `design/README.md`'s "Pass-device width correction" note: the xschem
  symbol's `W` is a per-`mult`-group total, not the device's overall total:
  `mult` parallel groups, not `nf` (which only splits a group into fingers
  and does not scale current/width).

Resistor model names (`sky130_fd_pr__res_{high,xhigh}_po`) already match
`klt extract`'s flavor-specific resistor classes 1:1 -- no translation
needed, but their *values* do: the schematic states a resistor's geometry
(`W`/`L`) while `klt extract` reports the resistance, area and perimeter it
measured off the drawn body, and `klt lvs` compares all three. This script
therefore emits each resistor's expected `R`/`A`/`P` computed from the same
geometry, using the sheet resistivity and fixed end-contact offset read out
of `klt`'s own curated sky130 extraction deck (`klayout_tools.decks`) rather
than a transcribed copy of those constants -- there is exactly one source of
truth for them, and it is the deck the layout side is extracted with.

The schematic's ground net (`0`) is emitted unchanged. It needs no
translation because the layout draws a real substrate tie and *labels* the
net it lands on `0` (see `gen-ldo-blocks.py`'s router): the deck's
synthesized `vsubs` substrate global therefore never surfaces as a net name
on the layout side, and the two sides name the same physical node the same
way. The resistor bulk terminal -- which `klt extract` reports but a
schematic netlist does not carry as a separate node -- is supplied through
`request.reference.device_bulk` instead (see `run-ldo-lvs-flow.sh`).

Capacitors (`C_COMP`, `C_CL`, `C_SS`) are dropped: no `klt gen`
capacitor/MiM generator exists at this repo's pinned `klt` commit (see
`layout/ldo-core/floorplan.md`'s "Known gap"), so none are drawn in the
layout and including them in the reference would only add a redundant,
already-documented mismatch dimension.

MOS body terminals are passed through unchanged: this schematic ties every
NMOS body to one net (`0`) and every PMOS body to one net (`VIN`), and the
layout draws exactly one substrate tie and one n-well tie to match, so both
body nets are real, drawn, extracted nets on the layout side rather than the
deck's synthesized fallback.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MOS_MODEL_MAP = {
    "sky130_fd_pr__nfet_g5v0d10v5": "nfet",
    "sky130_fd_pr__pfet_g5v0d10v5": "pfet",
}
RES_MODEL_MAP = {
    "sky130_fd_pr__res_high_po": "res_high_po",
    "sky130_fd_pr__res_xhigh_po": "res_xhigh_po",
}


def resistor_models(deck_name: str) -> dict[str, tuple[float, float]]:
    """``{class name: (sheet_rho_ohm_sq, fixed_offset_ohm)}`` from `klt`'s own
    curated extraction deck -- the single source of truth the layout side is
    extracted with. Requires running under `layout/.venv` (see
    `run-ldo-lvs-flow.sh`), which is where `klt` lives."""
    try:
        from klayout_tools.decks import get_extraction_deck
    except ImportError as exc:  # pragma: no cover - environment error path
        raise SystemExit(
            "gen-ldo-reference-netlist.py: needs `klt` importable (run it with "
            "layout/.venv/bin/python -- see layout/bin/run-ldo-lvs-flow.sh): "
            f"{exc}"
        ) from exc
    deck = get_extraction_deck(deck_name)
    return {
        resistor.name: (resistor.sheet_rho_ohm_sq, resistor.fixed_offset_ohm)
        for resistor in deck.resistors
    }


def _merge_continuations(lines: list[str]) -> list[str]:
    """xschem wraps long device lines with a leading `+` continuation --
    merge those back onto the device line they belong to."""
    merged: list[str] = []
    for line in lines:
        if line.startswith("+") and merged:
            merged[-1] = merged[-1] + " " + line[1:].strip()
        else:
            merged.append(line)
    return merged


def translate(
    netlist_path: Path,
    subckt_name: str,
    ports: list[str],
    deck_name: str = "sky130",
) -> str:
    raw_lines = netlist_path.read_text().splitlines()
    lines = _merge_continuations([ln.rstrip() for ln in raw_lines])
    res_models = resistor_models(deck_name)

    out: list[str] = [
        "* Mechanically translated LVS reference netlist for "
        f"`{subckt_name}`, generated by",
        "* layout/bin/gen-ldo-reference-netlist.py from "
        "design/ldo_3v3in_1v8out.sch's",
        "* own xschem netlist (issue #17). MOS model names translated to "
        "`klt extract`'s",
        "* generic nfet/pfet classes; resistor model names already match "
        "flavor-specific",
        "* classes. Capacitors are dropped (no klt gen capacitor generator "
        "exists --",
        "* see layout/ldo-core/floorplan.md's Known gap). Regenerate rather "
        "than hand-edit.",
        f".SUBCKT {subckt_name} {' '.join(ports)}",
    ]

    skipped: list[str] = []
    for line in lines:
        if not line.startswith("X"):
            continue
        m = re.match(r"^X(\S+)\s+(.*)$", line)
        if not m:
            continue
        inst_suffix, rest = m.group(1), m.group(2)
        toks = rest.split()

        model_idx = None
        for i, t in enumerate(toks):
            if t in MOS_MODEL_MAP or t in RES_MODEL_MAP:
                model_idx = i
                break
        if model_idx is None:
            skipped.append(line)
            continue

        nets = toks[:model_idx]
        model_token = toks[model_idx]
        params = toks[model_idx + 1 :]
        pdict: dict[str, str] = {}
        for p in params:
            if "=" in p:
                k, v = p.split("=", 1)
                pdict[k] = v

        if model_token in MOS_MODEL_MAP:
            d, g, s, b = nets
            klass = MOS_MODEL_MAP[model_token]
            l_um = pdict.get("L", "?")
            w_um = float(pdict.get("W", "0"))
            mult = float(pdict.get("mult", "1"))
            w_total_um = w_um * mult
            # inst_suffix already carries the schematic's own "M_..." prefix
            # (e.g. "M_BIASN1") -- reuse it verbatim as the SPICE element
            # name rather than prepending another "M".
            elem_name = inst_suffix if inst_suffix[:1] in ("M", "m") else f"M{inst_suffix}"
            out.append(
                f"{elem_name} {d} {g} {s} {b} {klass} "
                f"L={l_um}U W={w_total_um:g}U"
            )
        else:
            a, b_, _bulk = nets
            klass = RES_MODEL_MAP[model_token]
            l_um = float(pdict.get("L", "0"))
            w_um = float(pdict.get("W", "0"))
            sheet_rho, fixed_offset = res_models[klass]
            # The value/area/perimeter `klt extract` measures off the drawn
            # body (`klt lvs` compares all three). The bulk terminal is *not*
            # emitted as a third net -- KLayout's SPICE reader would read it
            # as the element's value; it is supplied instead through
            # `request.reference.device_bulk`, see run-ldo-lvs-flow.sh.
            r_ohm = sheet_rho * l_um / w_um + fixed_offset
            area_um2 = l_um * w_um
            perimeter_um = 2.0 * (l_um + w_um)
            elem_name = inst_suffix if inst_suffix[:1] in ("R", "r") else f"R{inst_suffix}"
            out.append(
                f"{elem_name} {a} {b_} {r_ohm:.6f} {klass} "
                f"L={l_um:g}U W={w_um:g}U A={area_um2:g}P P={perimeter_um:g}U"
            )

    out.append(f".ENDS {subckt_name}")

    if skipped:
        print(
            f"gen-ldo-reference-netlist.py: {len(skipped)} device line(s) "
            "had no recognized MOS/resistor model and were dropped "
            "(expected for capacitors -- see module docstring):",
            file=sys.stderr,
        )
        for s in skipped:
            print(f"  {s}", file=sys.stderr)

    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--netlist", required=True, type=Path, help="xschem-generated .spice")
    ap.add_argument("--subckt-name", required=True)
    ap.add_argument("--ports", required=True, help="space-separated port list, e.g. 'VOUT VREF EN VIN'")
    ap.add_argument("--deck", default="sky130", help="klt extraction deck to read resistor constants from")
    ap.add_argument("-o", "--output", required=True, type=Path)
    args = ap.parse_args()

    reference = translate(
        args.netlist,
        args.subckt_name,
        args.ports.split(),
        deck_name=args.deck,
    )
    args.output.write_text(reference)
    print(f"gen-ldo-reference-netlist.py: wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
