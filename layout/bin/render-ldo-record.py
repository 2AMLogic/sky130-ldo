#!/usr/bin/env python3
"""Render layout/ldo-core/reports/<record-id>/record.md from the `klt` JSON
envelopes `run-ldo-layout-flow.sh` just produced in that directory.

Standard library only (matches `layout/bin/render-record.py`'s convention).

Exits non-zero (after writing record.md, so the evidence trail still gets a
record of the failure) if the layout is not DRC-clean, or if the drawn block
set does not cover the schematic's own device set -- those are this flow's
gating claims. LVS is its own driver and its own record
(`run-ldo-lvs-flow.sh`, issue #17).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _record_common import _load, provenance


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--record-id", required=True)
    ap.add_argument("--repo-root", required=True, type=Path)
    ap.add_argument("--klt", required=True)
    ap.add_argument("--pdk-variant", required=True)
    ap.add_argument("--cell-name", required=True)
    ap.add_argument("--schematic-sha", required=True)
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    floorplan = _load(out_dir / "floorplan.json")
    compose = _load(out_dir / "compose.json")
    drc = _load(out_dir / "drc.json")
    routing = floorplan.get("routing", {})

    prov = provenance(args.repo_root, args.klt, args.pdk_variant)
    sha, branch, dirty = prov.sha, prov.branch, prov.dirty
    klt_version, pdk_info = prov.klt_version, prov.pdk_info

    checks = [
        ("DRC on the routed ldo-core layout is clean", drc.get("status") == "clean"),
        (
            "Every schematic MOS/resistor device has exactly one placed "
            f"`klt gen` block ({floorplan.get('device_count')} devices)",
            len(compose.get("blocks", [])) == floorplan.get("device_count"),
        ),
        (
            "Every schematic net the drawn devices touch is routed "
            f"({routing.get('net_count')} nets, "
            f"{routing.get('terminal_count')} terminals)",
            bool(routing.get("net_count")) and not compose.get("unrouted_nets"),
        ),
    ]
    all_pass = all(ok for _, ok in checks)

    lines: list[str] = []
    a = lines.append
    a(f"# LDO core layout record: {args.record_id}")
    a("")
    a(
        "Placed and routed layout for the sky130 LDO's core regulation loop "
        "(issues #15/#33), generated from `design/ldo_3v3in_1v8out.sch`'s own "
        "headless xschem netlist: one `klt gen` block per active schematic "
        "device, placed by `klt gen-compose` and wired net-for-net by "
        "`layout/bin/gen-ldo-blocks.py`'s channel router. LVS against the "
        "schematic is its own driver and its own record -- see "
        "`layout/bin/run-ldo-lvs-flow.sh` and `reports/LATEST-LVS`."
    )
    a("")
    a("## Overall verdict: " + ("PASS" if all_pass else "FAIL"))
    a("")
    for desc, ok in checks:
        a(f"- [{'x' if ok else ' '}] {desc}")
    a("")
    a("## Flow")
    a("")
    a(
        "1. `xschem -n -q -x -s ...` -- headless netlist of "
        "`design/ldo_3v3in_1v8out.sch`, the single source this layout's "
        "device set and connectivity are both derived from."
    )
    a(
        "2. `layout/bin/gen-ldo-blocks.py` runs `klt gen mos_array` / "
        f"`klt gen res_array` once per schematic device "
        f"({floorplan.get('mos_count')} MOS + {floorplan.get('res_count')} "
        "resistor blocks), computes an explicit single-row placement (see "
        "`layout/ldo-core/floorplan.md`), runs `klt gen-compose` to place "
        "them, then draws the inter-block routing and the two body ties."
    )
    a(f"3. `klt drc {args.cell_name}.gds --deck sky130`")
    a("")
    a("## Composed cell")
    a("")
    bbox = compose.get("bbox_um", {})
    a(f"- Cell name: `{compose.get('cell_name')}`")
    a(f"- Block count: {len(compose.get('blocks', []))}")
    a(f"- Placed bbox (um), before routing: {bbox}")
    a(
        f"- Device row: {floorplan.get('row_width_um', 0):.2f}um x "
        f"{floorplan.get('row_height_um', 0):.2f}um"
    )
    a(
        f"- Routing channel: {routing.get('net_count')} met1 trunks on a "
        f"{routing.get('track_pitch_um')}um pitch below the row, "
        f"{routing.get('terminal_count')} terminals landed"
    )
    a("")
    a("### Function groups (x extent within the row)")
    a("")
    a(
        "Blocks are ordered resistors -> every NMOS -> every PMOS, and inside "
        "each of those spans by function group, so a group that has both "
        "flavors (e.g. the error amplifier) occupies two x ranges rather than "
        "one contiguous block. The flavor split is load-bearing: the PMOS "
        "bodies are tied through one n-well drawn across the whole PMOS span, "
        "and `klt extract` decides a device's flavor by n-well containment."
    )
    a("")
    a("| Group | Blocks | x0 (um) | x1 (um) | height (um) |")
    a("| --- | --- | --- | --- | --- |")
    for group in floorplan.get("groups", []):
        a(
            f"| {group['group']} | {', '.join(group['blocks'])} | "
            f"{group['x0_um']:.2f} | {group['x1_um']:.2f} | "
            f"{group['height_um']:.2f} |"
        )
    a("")
    a("### Devices drawn as parallel unit arrays")
    a("")
    split = [d for d in floorplan.get("devices", []) if (d.get("units") or 1) > 1]
    if split:
        a("| Device | W_total (um) | Units | Unit W (um) |")
        a("| --- | --- | --- | --- |")
        for device in split:
            a(
                f"| `{device['name']}` | {device['w_total_um']:g} | "
                f"{device['units']} | {device['unit_w_um']:g} |"
            )
        a("")
        a(
            "A device wider than "
            f"{floorplan.get('max_unit_w_um')}um is drawn as that many equal "
            "parallel unit devices with their terminals strapped, rather than "
            "as one enormous single-finger device. `klt lvs`'s "
            "`options.combine_devices` folds them back into one device of the "
            "summed width for the compare."
        )
    else:
        a("(none)")
    a("")
    a("## Results")
    a("")
    a("| Stage | Status | Detail |")
    a("| --- | --- | --- |")
    a(
        "| DRC | "
        f"{drc.get('status')} | violation_count={drc.get('violation_count')} |"
    )
    a("")
    coverage = drc.get("coverage", {})
    if coverage:
        a(
            f"DRC coverage: layers_checked={coverage.get('layers_checked')}, "
            f"rules_skipped={len(coverage.get('rules_skipped', []) or [])}."
        )
        a("")
    a("## Known gap: the schematic's capacitors are not drawn")
    a("")
    undrawn = floorplan.get("undrawn_elements", [])
    a(
        f"{len(undrawn)} schematic element(s) have no corresponding `klt gen` "
        "generator at this repo's pinned `klt` commit -- there is no "
        "capacitor/MiM family member alongside `mos_array`/`res_array`, "
        "filed generically per `CLAUDE.md`'s friction protocol as "
        "https://github.com/2AMLogic/klayout-tools/issues/1117:"
    )
    a("")
    for element in undrawn:
        a(f"- `{element.split()[0]}`")
    a("")
    a(
        "`layout/bin/gen-ldo-reference-netlist.py` drops the same elements "
        "from the LVS reference, so the compare stays symmetric -- their "
        "absence is a disclosed coverage gap in both directions, not a "
        "silent one."
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
        f"- KLayout engine version: "
        f"`{drc.get('provenance', {}).get('klayout_version')}`"
    )
    a(f"- PDK: `{pdk_info.get('variant')}`, `{pdk_info.get('version')}`")
    a(
        "- PDK pin cross-check: compare `version` above against "
        "`sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself "
        "enforce the pin (unlike `sim/bin/corner-run.py`), consistent with "
        "`layout/README.md`'s trivial-cell flow."
    )
    a(
        f"- Schematic freshness: `design/ldo_3v3in_1v8out.sch` as of commit "
        f"`{args.schematic_sha}` (see `design/README.md`'s own Freshness "
        "note). This record's device set was read from that schematic at run "
        "time, not from a table."
    )
    a(f"- Repo state: `{sha}` on `{branch}`" + (" (dirty)" if dirty else ""))
    a("")
    a("## Links")
    a("")
    a("- [`floorplan.json`](floorplan.json) -- resolved placement, per-device sizing, and the routed net table")
    a("- [`compose.request.json`](compose.request.json), [`compose.json`](compose.json)")
    a(f"- [`{args.cell_name}.gds`]({args.cell_name}.gds) -- the routed layout")
    a(
        f"- [`{args.cell_name}.placed.gds`]({args.cell_name}.placed.gds) -- "
        "`klt gen-compose`'s own output, before this flow's routing was drawn"
    )
    a("- [`drc.json`](drc.json)")
    a(
        "- `gen.<device>.json` / `<device>.gds` -- per-device `klt gen` "
        "report and standalone cell, one pair per schematic device"
    )
    a("- [`report.md`](report.md) -- `klt report --format github-summary` rendering of `drc.json`")
    a("")

    print("\n".join(lines))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
