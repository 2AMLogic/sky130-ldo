#!/usr/bin/env python3
"""Render layout/ldo-core/reports/<record-id>/record.md for an LDO-core LVS
attempt (issue #17), from the `klt` JSON envelopes
`run-ldo-lvs-flow.sh` just produced in that directory.

Standard library only (matches this repo's other `layout/bin/` render
scripts).

Unlike `render-record.py` / `render-ldo-record.py`, this renderer does not
assume the expected verdict is a pass, and it never narrates a root cause it
has not read: a mismatch is summarised from `lvs.json`'s own `mismatches[]`
(the run's evidence), not from a story hard-coded here that can go stale the
way the layout itself once did. Exits non-zero whenever the verdict is not
`match`, same convention as the other renderers (non-zero does not mean
"something went wrong with this script" -- it means "the LVS claim this
record makes is not a clean match", which the caller still writes to
record.md as real evidence either way).
"""

from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

from _record_common import _load, provenance

#: Schematic elements with no drawn counterpart, and why. Capacitors have no
#: `klt gen` generator at this repo's pinned `klt` commit (filed upstream as
#: klayout-tools#1117); `gen-ldo-reference-netlist.py` drops them from the
#: reference for the same reason, so the compare stays symmetric.
CAPS_NOT_DRAWN_REASON = (
    "the schematic's MiM capacitors are not drawn and are dropped from the "
    "reference on both sides -- `klt gen` has no capacitor/MiM generator at "
    "this repo's pinned commit "
    "(https://github.com/2AMLogic/klayout-tools/issues/1117)"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--record-id", required=True)
    ap.add_argument("--repo-root", required=True, type=Path)
    ap.add_argument("--klt", required=True)
    ap.add_argument("--pdk-variant", required=True)
    ap.add_argument("--cell-name", required=True)
    ap.add_argument("--schematic-sha", required=True)
    ap.add_argument("--layout-sha", required=True)
    ap.add_argument("--layout-record-id", required=True)
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    extract = _load(out_dir / "extract.json")
    lvs = _load(out_dir / "lvs.json")

    prov = provenance(args.repo_root, args.klt, args.pdk_variant)
    sha, branch, dirty = prov.sha, prov.branch, prov.dirty
    klt_version, pdk_info = prov.klt_version, prov.pdk_info

    status = lvs.get("status")
    is_match = status == "match"

    lines: list[str] = []
    a = lines.append
    a(f"# LDO core LVS record: {args.record_id}")
    a("")
    a(
        "`klt extract` + `klt lvs` against the LDO core layout (issue #17's "
        "driver), comparing `layout/ldo-core/reports/"
        f"{args.layout_record_id}/{args.cell_name}.gds` against a reference "
        "netlist mechanically translated from "
        "`design/ldo_3v3in_1v8out.sch`'s own xschem netlist by "
        "`layout/bin/gen-ldo-reference-netlist.py`. Both sides are derived "
        "from that one netlist -- the layout's device set comes from it too "
        "(`layout/bin/gen-ldo-blocks.py`, issue #33) -- so neither side can "
        "silently describe a different circuit than the schematic."
    )
    a("")
    a("## Overall verdict: " + ("MATCH" if is_match else "MISMATCH -- not LVS-clean"))
    a("")
    a(f"- [{'x' if is_match else ' '}] `klt lvs` reports `status: match`")
    a("")
    if not is_match:
        a(
            "**This does not satisfy issue #17's acceptance criteria "
            "(`status: match`).** Filed as a real, committed negative "
            "result (`CLAUDE.md`'s \"Verification is the product\": "
            "append-only evidence, not a silently-dropped attempt). The "
            "findings `klt lvs` actually reported are summarised below -- "
            "read `lvs.json` for the full list."
        )
        a("")
    a("## Flow")
    a("")
    a(
        "1. `xschem -n -q -x -s -o ... design/ldo_3v3in_1v8out.sch` -- "
        "headless netlist, same invocation `design/README.md`'s "
        "\"Validating this schematic\" section documents."
    )
    a(
        "2. `layout/bin/gen-ldo-reference-netlist.py` translates that "
        "netlist into an LVS reference (MOS model names -> `klt extract`'s "
        "generic `nfet`/`pfet` classes, `W_total = W * mult`; each "
        "resistor's expected `R`/`A`/`P` computed from its drawn geometry "
        "using `klt`'s own deck constants; capacitors dropped -- "
        f"{CAPS_NOT_DRAWN_REASON})."
    )
    a(
        f"3. `klt extract {args.cell_name}.gds --deck sky130 --top "
        f"{args.cell_name} --pins ...` (the schematic's own four ports; "
        "every other labelled net stays an internal node)."
    )
    a(
        "4. `klt lvs` (extracted layout vs. the translated reference), with "
        "`options.combine_devices`, `layout.declared_pins` and "
        "`reference.device_bulk` -- see `run-ldo-lvs-flow.sh`'s header for "
        "what each one reconciles and why. Every one of them is disclosed "
        "as its own `warning` entry in `lvs.json`."
    )
    a("")
    a("## Results")
    a("")
    a("| Stage | Status | Detail |")
    a("| --- | --- | --- |")
    a(
        "| Extract | "
        f"{extract.get('status')} | device_count={extract.get('device_count')}, "
        f"net_count={extract.get('net_count')}, pin_count={extract.get('pin_count')}, "
        f"device_counts={extract.get('device_counts')} |"
    )
    counts = lvs.get("counts", {})
    a(
        "| LVS | "
        f"{lvs.get('status')} | mismatch_count={lvs.get('mismatch_count')}, "
        f"category_counts={lvs.get('category_counts')}, "
        f"nets(layout/reference/matched)={counts.get('nets', {})}, "
        f"devices(layout/reference/matched)={counts.get('devices', {})}, "
        f"pins(layout/reference/matched)={counts.get('pins', {})} |"
    )
    a("")
    mismatches = lvs.get("mismatches", [])
    errors = [m for m in mismatches if m.get("severity") == "error"]
    warnings = [m for m in mismatches if m.get("severity") != "error"]

    if errors:
        a("## Findings (`severity: error`)")
        a("")
        a("| Category | Side | Description | Device / net |")
        a("| --- | --- | --- | --- |")
        for entry in errors[:40]:
            subject = entry.get("device") or entry.get("net") or ""
            a(
                f"| `{entry.get('category')}` | {entry.get('side')} | "
                f"{entry.get('description')} | `{subject}` |"
            )
        if len(errors) > 40:
            a(f"| ... | | {len(errors) - 40} further error entries, see `lvs.json` | |")
        a("")
        by_category = collections.Counter(e.get("category") for e in errors)
        a(f"Error findings by category: `{dict(by_category)}`.")
        a("")

    a("## Disclosed warnings (non-blocking)")
    a("")
    if warnings:
        for entry in warnings:
            a(f"- `{entry.get('category')}` -- {entry.get('description')}")
    else:
        a("- (none)")
    a("")
    a(
        "A `warning` entry never changes `status`; each one records a "
        "dimension this compare could not verify structurally, or a "
        "request-level reconciliation it was given. Read them alongside the "
        "verdict, not instead of it."
    )
    a("")
    a("## Provenance")
    a("")
    a(f"- Record ID: `{args.record_id}`")
    a(
        f"- `klt` version: `{klt_version}` (pinned commit, see "
        "`layout/requirements.txt`)"
    )
    a(
        "- KLayout engine version: "
        f"`{lvs.get('provenance', {}).get('klayout_version')}`"
    )
    a(f"- PDK: `{pdk_info.get('variant')}`, `{pdk_info.get('version')}`")
    a(
        "- PDK pin cross-check: compare `version` above against "
        "`sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself "
        "enforce the pin, consistent with `layout/README.md`'s "
        "trivial-cell flow."
    )
    a(
        f"- Schematic freshness: `design/ldo_3v3in_1v8out.sch` as of commit "
        f"`{args.schematic_sha}`."
    )
    a(
        f"- Layout freshness: `layout/ldo-core/` as of commit "
        f"`{args.layout_sha}`; GDS taken from layout record "
        f"`{args.layout_record_id}`."
    )
    a(f"- Repo state: `{sha}` on `{branch}`" + (" (dirty)" if dirty else ""))
    a("")
    a("## Links")
    a("")
    a(f"- [`{args.cell_name}.gds`]({args.cell_name}.gds) -- copy of the layout record's composed GDS")
    a("- [`xschem_out/ldo_3v3in_1v8out.spice`](xschem_out/ldo_3v3in_1v8out.spice) -- headless schematic netlist")
    a("- [`reference.spice`](reference.spice) -- translated LVS reference")
    a(f"- [`extract.json`](extract.json), [`{args.cell_name}.extract.spice`]({args.cell_name}.extract.spice)")
    a("- [`lvs.request.json`](lvs.request.json), [`lvs.json`](lvs.json)")
    a("- [`report.md`](report.md) -- `klt report --format github-summary` rendering of `lvs.json`")
    a("")

    print("\n".join(lines))
    return 0 if is_match else 1


if __name__ == "__main__":
    sys.exit(main())
