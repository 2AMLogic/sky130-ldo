#!/usr/bin/env python3
"""Render layout/ldo-core/reports/<record-id>/record.md from the `klt` JSON
envelopes `run-ldo-layout-flow.sh` just produced in that directory.

Standard library only (matches `layout/bin/render-record.py`'s convention).

Exits non-zero (after writing record.md, so the evidence trail still gets a
record of the failure) if the composed floorplan is not DRC-clean -- that is
this flow's actual gating claim; extraction/LVS are explicitly out of scope
here (issue #17).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


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
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    floorplan = _load(out_dir / "floorplan.json")
    compose = _load(out_dir / "compose.json")
    drc = _load(out_dir / "drc.json")

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

    checks = [
        ("DRC on the composed ldo-core floorplan is clean", drc.get("status") == "clean"),
        (
            "Every schematic active device has exactly one placed klt gen block",
            len(compose.get("blocks", [])) == 15,
        ),
    ]
    all_pass = all(ok for _, ok in checks)

    lines: list[str] = []
    a = lines.append
    a(f"# LDO core layout record: {args.record_id}")
    a("")
    a(
        "Placed floorplan skeleton for the sky130 LDO's core regulation loop "
        "(issue #15), one `klt gen` block per active device in "
        "`design/ldo_3v3in_1v8out.sch` (issue #14). **Not** an "
        "extraction/LVS-verified result -- inter-block routing and LVS are "
        "explicitly out of scope here, see `layout/ldo-core/floorplan.md`."
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
        "1. `layout/bin/gen-ldo-blocks.py` runs `klt gen mos_array`/"
        "`klt gen res_array` once per schematic device (13 MOS + 2 resistor "
        "blocks covering all 4 resistor instances = 15 blocks total), "
        "computes an explicit row-packed floorplan (see "
        "`layout/ldo-core/floorplan.md`), and runs `klt gen-compose` to "
        "place every block into one composed GDS."
    )
    a(f"2. `klt drc {args.cell_name}.gds --deck sky130`")
    a("")
    a("## Composed cell")
    a("")
    bbox = compose.get("bbox_um", {})
    a(f"- Cell name: `{compose.get('cell_name')}`")
    a(f"- Block count: {len(compose.get('blocks', []))}")
    a(f"- Composed bbox (um): {bbox}")
    if bbox:
        width = bbox.get("x1", 0) - bbox.get("x0", 0)
        height = bbox.get("y1", 0) - bbox.get("y0", 0)
        a(f"- Composed size: {width:.2f}um x {height:.2f}um")
    a("")
    a("### Floorplan rows (bottom to top)")
    a("")
    a("| Row | Blocks | y_base (um) | height (um) | width (um) |")
    a("| --- | --- | --- | --- | --- |")
    for row in floorplan.get("rows", []):
        a(
            f"| {row['row']} | {', '.join(row['blocks'])} | "
            f"{row['y_base_um']:.2f} | {row['height_um']:.2f} | "
            f"{row['width_um']:.2f} |"
        )
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
    a(
        "**Extraction/LVS not run here** -- issue #17's job. "
        "`layout/README.md`'s \"Known klt-deck limitations\" section "
        "documents two caveats a future LVS reference netlist needs to "
        "account for (no NMOS substrate-tap extraction, no voltage-flavor "
        "distinction on MOS devices)."
    )
    a("")
    a("## Known gap: `C_COMP` not drawn")
    a("")
    a(
        "The schematic's Miller compensation cap (`C_COMP`, MiM, `2p`, "
        "itself a placeholder value pending DR-002) has no corresponding "
        "`klt gen` device generator at this repo's pinned `klt` commit -- "
        "see `layout/ldo-core/floorplan.md`'s \"Known gap\" section and "
        "https://github.com/2AMLogic/klayout-tools/issues/1117 (filed per "
        "CLAUDE.md's friction protocol)."
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
        "note)."
    )
    a(f"- Repo state: `{sha}` on `{branch}`" + (" (dirty)" if dirty else ""))
    a("")
    a("## Links")
    a("")
    a("- [`floorplan.json`](floorplan.json) -- the resolved row-packing this run produced")
    a("- [`compose.request.json`](compose.request.json), [`compose.json`](compose.json)")
    a(f"- [`{args.cell_name}.gds`]({args.cell_name}.gds) -- the composed layout")
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
