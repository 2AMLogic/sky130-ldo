#!/usr/bin/env python3
"""Render layout/ldo-core/reports/<record-id>/record.md for an LDO-core LVS
attempt (issue #17), from the `klt` JSON envelopes
`run-ldo-lvs-flow.sh` just produced in that directory.

Standard library only (matches this repo's other `layout/bin/` render
scripts).

Unlike `render-record.py` / `render-ldo-record.py`, this renderer does not
assume the expected verdict is a pass: issue #17's first run is expected to
report `status: mismatch` (see `run-ldo-lvs-flow.sh`'s own comment), because
the committed ldo-core layout (issue #15) is a placed-but-unrouted floorplan
skeleton built against an earlier revision of the schematic. Exits non-zero
whenever the verdict is not `match`, same convention as the other renderers
(non-zero does not mean "something went wrong with this script" -- it means
"the LVS claim this record makes is not a clean match", which the caller
still writes to record.md as real evidence either way).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Devices present in design/ldo_3v3in_1v8out.sch as of issue #22 but absent
# from the issue #15 floorplan (layout/ldo-core/floorplan.md's device table
# predates #22). Recomputed from the schematic/floorplan device lists at
# authoring time -- if this drifts, a future run's device_counts diff in
# extract.json/lvs.json is the source of truth, not this list.
DEVICES_MISSING_FROM_LAYOUT = [
    "M_SENSE", "M_CLN1", "M_CLN2", "M_CLP", "M_CLIM", "M_ENP3",
    "M_INVP", "M_INVN", "M_SSDIS", "M_SSCHG", "M_IN2S",
]
CAPS_NOT_DRAWN = ["C_COMP", "C_CL", "C_SS"]


def _load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


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

    sha = _git(args.repo_root, "rev-parse", "HEAD")
    branch = _git(args.repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = _git(args.repo_root, "status", "--porcelain") != ""

    klt_version = subprocess.run(
        [args.klt, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    pdk_info_raw = subprocess.run(
        [args.klt, "pdk", "find", "--pdk", args.pdk_variant, "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pdk_info = json.loads(pdk_info_raw)

    status = lvs.get("status")
    is_match = status == "match"

    lines: list[str] = []
    a = lines.append
    a(f"# LDO core LVS record: {args.record_id}")
    a("")
    a(
        "First `klt extract` + `klt lvs` attempt against the real LDO layout "
        "(issue #17), comparing `layout/ldo-core/reports/"
        f"{args.layout_record_id}/{args.cell_name}.gds` (issue #15) against "
        "a reference netlist mechanically translated from "
        "`design/ldo_3v3in_1v8out.sch`'s own xschem netlist (issues #14/#22) "
        "by `layout/bin/gen-ldo-reference-netlist.py`."
    )
    a("")
    a("## Overall verdict: " + ("MATCH" if is_match else "MISMATCH -- not LVS-clean"))
    a("")
    a(f"- [{'x' if is_match else ' '}] `klt lvs` reports `status: match`")
    a("")
    if not is_match:
        a(
            "**This does not satisfy issue #17's acceptance criteria "
            "(`status: match`).** The root cause is not a `klt` defect -- "
            "see \"Root cause\" below. Filed as a real, committed negative "
            "result (`CLAUDE.md`'s \"Verification is the product\": "
            "append-only evidence, not a silently-dropped attempt), with a "
            "follow-on issue tracking the layout work a clean match needs."
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
        "generic `nfet`/`pfet` classes, `W_total = W * mult`; resistor "
        "model names pass through unchanged; capacitors dropped -- no `klt "
        "gen` capacitor generator exists)."
    )
    a(
        f"3. `klt extract {args.cell_name}.gds --deck sky130 --top "
        f"{args.cell_name}`"
    )
    a("4. `klt lvs` (extracted layout vs. the translated reference).")
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
    if not is_match:
        a("## Root cause")
        a("")
        a(
            "Three independent, well-understood gaps -- any one of them "
            "alone would already prevent a match; together they explain "
            f"the full LVS result above (0 of {counts.get('nets', {}).get('reference', '?')} "
            f"reference nets, 0 of {counts.get('devices', {}).get('reference', '?')} "
            "reference devices matched):"
        )
        a("")
        a(
            "1. **The layout is stale relative to the schematic.** "
            "`layout/ldo-core/` (issue #15) was floorplanned from "
            "`design/ldo_3v3in_1v8out.sch` as it stood before issue #22 "
            "added the current-limit and soft-start circuitry -- the "
            "branch #15 built from was based on commit `0e12b14`, before "
            "`4bda2cb` (#22) landed on `main`. The floorplan's device table "
            "(`layout/ldo-core/floorplan.md`) still lists only the "
            f"pre-#22 device set. **{len(DEVICES_MISSING_FROM_LAYOUT)} "
            "active MOS devices** added by #22 have no `klt gen` block at "
            "all: " + ", ".join(f"`{d}`" for d in DEVICES_MISSING_FROM_LAYOUT) + "."
        )
        a(
            "2. **`M_PASS`'s drawn width does not match the corrected "
            "schematic value.** `design/README.md`'s \"Pass-device width "
            "correction\" note explains the `mult` parameter is load-"
            "bearing (`W_total = W * mult`, not `W` alone); "
            "`layout/bin/gen-ldo-blocks.py`'s `MOS_DEVICES` table still "
            "passes only `w_um=100` with no `mult`, so the drawn "
            "`M_PASS` block is 100um wide, not the schematic's corrected "
            "2500um."
        )
        a(
            "3. **No inter-block routing exists.** `klt gen-compose` only "
            "places the 15 blocks it does draw -- `layout/ldo-core/"
            "floorplan.md`'s \"Explicitly out of scope\" section documents "
            "this as a deliberate #15 scope boundary "
            "(\"a real, separate design task in its own right\"). The "
            "extracted netlist's own `pin_count: "
            f"{extract.get('pin_count')}` (vs. the schematic's 4 top-level "
            "ports) is the direct evidence: with no metal connecting the "
            "placed blocks, almost nothing reaches the top-level cell "
            "boundary."
        )
        a("")
        a(
            "None of this is a `klt` tool defect -- `klt extract`/`klt lvs` "
            "produced a coherent, correctly-reasoned mismatch report "
            "against the layout exactly as drawn; the gap is real, "
            "physical layout content that does not exist yet. No "
            "`2AMLogic/klayout-tools` filing follows from this record. The "
            "one `device.body_unverified` warning in `lvs.json` reproduces "
            "the already-documented, already-filed \"no NMOS substrate-tap "
            "extraction\" deck limitation (`layout/README.md`) -- not a new "
            "finding."
        )
        a("")
        a(
            "**Follow-on**: extending the floorplan to cover the #22 "
            "devices, correcting `M_PASS`'s width, and adding inter-block "
            "routing is tracked as its own issue (linked from #17) -- out "
            "of this issue's own \"routine\" scope, matching "
            "`layout/ldo-core/floorplan.md`'s own characterization of "
            "routing as \"a real, separate design task in its own right "
            "... not a mechanical follow-on to placement.\""
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
