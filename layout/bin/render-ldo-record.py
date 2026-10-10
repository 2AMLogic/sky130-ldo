#!/usr/bin/env python3
"""Render layout/ldo-core/reports/<record-id>/record.md from the `klt` JSON
envelopes `run-ldo-layout-flow.sh` just produced in that directory.

Standard library only (matches `layout/bin/render-record.py`'s convention).

Exits non-zero (after writing record.md, so the evidence trail still gets a
record of the failure) if the layout is not clean under BOTH DRC decks -- the
curated `klt drc --deck sky130` deck and the PDK's own official
`sky130A_mr.drc` (issue #260), reported separately, the latter fail-closed
(see `_official_drc.py`) -- or if the drawn block
set does not cover the schematic's own device set -- those are this flow's
gating claims. LVS is its own driver and its own record
(`run-ldo-lvs-flow.sh`, issue #17).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _official_drc import official_result, overall_pass
from _record_common import _load, provenance

#: `klt gen`'s `voltage_flavor` name -> the sky130 marker layer it draws, for
#: rendering only (issue #142). Transcribed from the curated sky130 deck's own
#: `MOSFlavour(marker=(75, 20), flavour="hvi", ...)`; the flow never reads this
#: to decide anything -- `gen-ldo-blocks.py` asserts against `klt gen`'s
#: `drc_hints.voltage_flavor_mark_present` instead, and the DRC verdict below
#: is measured, so a stale entry here can only mislabel a table cell.
VOLTAGE_FLAVOR_MARK_LAYERS = {
    "hvi": "75/20",
}


DIAGNOSIS_HEADER = (
    "### Rule-family attribution (issue #260)\n\n"
    "Each line separates what was measured from this record's own GDS "
    "(`official-drc-diagnosis.json`) from hypotheses about the fix. A "
    "hypothesis is not a claim until a later record demonstrates it."
)


def describe_family(rule: str, n: int, d: dict | None) -> str:
    """One attribution line per family, built only from measured fields."""
    if not d:
        return f"{n} markers; not diagnosed by this tool version."
    if rule == "via.1a_b":
        v = d.get("via1_census") or {}
        return (
            f"{n} markers. Measured: every via1 in the layout is drawn by the "
            f"flow's own router in the top cell, sizes (um) "
            f"{v.get('top_cell_own_shapes', {})}; inside generated blocks: "
            f"{v.get('inside_block_cells') or 'none'}. The "
            "deck's cap is a 0.15um via. Owner: local routing "
            "(`VIA1_UM` in `gen-ldo-blocks.py`). Hypothesis: shrinking to "
            "0.15um removes this family but changes metal enclosure (see "
            "`m2.5`); needs LVS/PEX re-run."
        )
    if rule == "licon.1":
        return (
            f"{n} markers. Measured: {d.get('offending_block_count')} "
            "generated block cells (resistor and MOS `klt gen` blocks) contain "
            "licons whose size is not 0.17um (sizes: "
            f"{sorted({k for v in d.get('off_size_licons_by_block', {}).values() for k in v})}); "
            "the flow's own body-tie licons are 0.17um and are not flagged. "
            "Owner: upstream `klt gen` (generic tool gap, see PR notes). "
            "Deck marker cell names (`mos_array$N`) are the deck's own "
            "renumbering and are not block names."
        )
    if rule in ("m2.5", "via2.5"):
        cls = d.get("enclosure_classes") or []
        txt = "; ".join(f"{c['count']} x {c['class']}" for c in cls)
        return (
            f"{n} markers. Measured, all in the top cell (local routing): {txt}. "
            "The rule flags a via with <0.085um met2 enclosure on two ADJACENT "
            "edges. "
            + (
                "Owner: local routing (met2 riser ends / landing pad). "
                "Hypothesis: extend riser ends >=0.085um past the via and/or "
                "widen the pad; needs LVS/PEX re-run."
            )
        )
    if rule == "nwell.9":
        w = d.get("nwell_minus_hvi") or {}
        return (
            f"{n} markers. Measured: n-well area {w.get('nwell_area_um2')}um2 "
            f"vs hvi marker {w.get('hvi_area_um2')}um2; n-well not covered by "
            f"hvi = {w.get('area_um2')}um2, of which "
            f"{w.get('area_inside_block_bboxes_um2')}um2 lies inside a "
            "generated block's own bbox (so the uncovered well is the local "
            "overhang: the 1um margins and the inter-block gaps). Owner: local "
            "routing (the single n-well rectangle). Hypothesis: extend the "
            "voltage-domain marker over the well; changes the marked area and "
            "needs LVS re-run."
        )
    if rule in ("rpm.1a", "urpm.1a"):
        rows = d.get("marker_layer_by_block") or {}
        return (
            f"{n} markers. Measured resistor-marker extents by block: {rows}. "
            "The marker is drawn exactly the resistor body width (0.42um), "
            "below the deck's 1.27um minimum marker width. Owner: upstream "
            "`klt gen res_array` (generic tool gap, see PR notes)."
        )
    return f"{n} markers (additional family; not yet diagnosed)."


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
    try:
        drc = _load(out_dir / "drc.json")
    except (OSError, ValueError) as exc:
        drc = {"status": "error", "error": f"drc.json: {exc}"}
    off = official_result(out_dir, args.cell_name)
    try:
        diag = _load(out_dir / "official-drc-diagnosis.json").get("families", {})
    except (OSError, ValueError):
        diag = {}
    routing = floorplan.get("routing", {})

    prov = provenance(args.repo_root, args.klt, args.pdk_variant)
    sha, branch, dirty = prov.sha, prov.branch, prov.dirty
    klt_version, pdk_info = prov.klt_version, prov.pdk_info

    checks = [
        (
            "Curated-deck DRC (`klt drc --deck sky130`) on the routed ldo-core "
            "layout is clean",
            drc.get("status") == "clean",
        ),
        (
            "Official-deck DRC (PDK `sky130A_mr.drc`) ran to completion and "
            f"reports zero markers ({off.detail})",
            off.state == "clean",
        ),
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
    assert all_pass == overall_pass(
        drc.get("status"), off, checks[2][1], checks[3][1]
    )

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
    a(f"3. `klt drc {args.cell_name}.gds --deck sky130` (curated deck)")
    a(
        f"4. `klayout -b -r sky130A_mr.drc` on the same `{args.cell_name}.gds` "
        "(the PDK's official deck; FEOL/BEOL/offgrid on, floating-metal and "
        "seal off, mirroring `layout/bin/run-cap-rail-demo-flow.sh`), then "
        "`layout/bin/diagnose-official-drc.py` to attribute any markers"
    )
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
    a("### Voltage-domain marking")
    a("")
    flavor_counts = floorplan.get("mos_voltage_flavor_counts") or {}
    if flavor_counts:
        a(
            "Every MOS block is drawn inside the sky130 voltage-domain marker "
            "its own schematic model implies (issue #142), so `klt extract "
            "--pdk` binds the model the schematic actually instantiates "
            "instead of defaulting to the 1.8V core flavour:"
        )
        a("")
        a("| `voltage_flavor` | Marker layer | MOS blocks |")
        a("| --- | --- | --- |")
        for flavor, count in sorted(flavor_counts.items()):
            layer = VOLTAGE_FLAVOR_MARK_LAYERS.get(flavor, "(unknown)")
            a(f"| `{flavor}` | {layer} | {count} |")
        a("")
        marker_layers = {
            VOLTAGE_FLAVOR_MARK_LAYERS[f]
            for f in flavor_counts
            if f in VOLTAGE_FLAVOR_MARK_LAYERS
        }
        in_stream = set(
            drc.get("coverage", {}).get("layers_in_stream_without_rules", []) or []
        )
        checked = set(drc.get("coverage", {}).get("layers_checked", []) or [])
        present = marker_layers & (in_stream | checked)
        a(
            "DRC neutrality is measured here, not assumed: the marker "
            f"layer(s) {sorted(present) or '(none found)'} appear in this "
            "record's own `drc.json` coverage under "
            "`layers_in_stream_without_rules` -- i.e. the geometry is really "
            "in the stream, and no rule in the curated sky130 deck reads it, "
            "so every rule kept applying its general-case threshold. The "
            f"verdict above (`{drc.get('status')}`, "
            f"violation_count={drc.get('violation_count')}) is the authority."
        )
    else:
        a("(none -- no MOS block carries a voltage-domain marker)")
    a("")
    a("## Results")
    a("")
    a("| Stage | Status | Detail |")
    a("| --- | --- | --- |")
    a(
        "| DRC, curated deck (`klt drc --deck sky130`) | "
        f"{drc.get('status')} | violation_count={drc.get('violation_count')} |"
    )
    off_status = {"clean": "clean", "violations": "violations", "error": "ERROR"}[off.state]
    a(f"| DRC, official deck (`sky130A_mr.drc`) | {off_status} | {off.detail} |")
    a("")
    a(
        "The two decks are separate gates and neither substitutes for the "
        "other: the curated deck is a hand-transcribed subset that is clean "
        "on this layout, while the PDK's own deck is the authority a tapeout "
        "would be checked against."
    )
    a("")
    if off.state == "violations":
        a("### Official-deck markers per rule family")
        a("")
        a("| Rule | Markers |")
        a("| --- | --- |")
        for rule, n in sorted(off.counts.items(), key=lambda kv: -kv[1]):
            a(f"| `{rule}` | {n} |")
        a(f"| **total** | **{off.total}** |")
        a("")
        a(
            "Marker totals are raw deck markers (edges / edge-pairs / "
            "polygons), not distinct defects: for example every undersized "
            "via contributes one marker per edge."
        )
        a("")
        a(DIAGNOSIS_HEADER)
        a("")
        if diag:
            for rule in sorted(off.counts):
                a(f"- `{rule}`: " + describe_family(rule, off.counts[rule], diag.get(rule)))
        else:
            a("(`official-drc-diagnosis.json` is absent: attribution was not produced for this record.)")
        a("")
    elif off.state == "error":
        a(f"**Official deck did not complete: {off.detail}.** No verdict is claimed from it.")
        a("")
        err = out_dir / "mr-drc.error.txt"
        if err.is_file():
            a("Diagnostic tail (`mr-drc.error.txt`):")
            a("")
            a("```")
            a(err.read_text(errors="replace").rstrip()[-3000:])
            a("```")
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
    run = off.run
    a(
        f"- Official deck: `{run.get('deck_name')}` sha256 "
        f"`{run.get('deck_sha256')}` from the resolved PDK; switches "
        f"`{run.get('switches')}`; `klayout -v`: `{run.get('klayout_version')}`"
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
    a("- [`drc.json`](drc.json) -- curated-deck envelope")
    a(
        "- [`mr-drc.lyrdb`](mr-drc.lyrdb), [`mr-drc.run.json`](mr-drc.run.json) -- "
        "the official deck's report database and the run record "
        "(deck sha256, switches, exit status)"
    )
    a(
        "- [`official-drc-diagnosis.json`](official-drc-diagnosis.json) -- "
        "per-family attribution measured from this record's `ldo_core.gds`"
    )
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
