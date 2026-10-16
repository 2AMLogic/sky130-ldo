#!/usr/bin/env python3
"""Mint a content-pinned core-area evidence record (issue #236).

Measures the routed `ldo_core.gds` the `layout/ldo-core/reports/LATEST`
pointer names (or `--gds`) with `_gds_area.py`'s stated convention, compares
it against the ratified, unchanged `< 0.1 mm^2` Area target, and writes a NEW
record directory `layout/ldo-core/reports/<UTC>-<sha>/` holding `area.json`
(the machine-read verdict) and `record.md`, then moves the
`LATEST-AREA` pointer. Earlier records are never touched (append-only).

The record cites the GDS by repo-relative path + SHA-256 instead of copying
the ~0.8 MB stream. `measurements/build_characterization_report.py` reads the
`verdict` field verbatim and re-hashes the current routed GDS to decide
freshness; it never recomputes the verdict.

Optionally cross-checks the bounding box against `klt stats` (an independent
implementation); a disagreement is recorded, not hidden.

Every record also carries a `coverage` disclosure (issue #318), read from the
measured layout record's own files rather than restated: the drawn MOS /
resistor inventory and pass-device width (`floorplan.json`), the schematic
elements that are NOT drawn (the capacitors), the official-deck DRC result for
that exact layout record (fail-closed reader `_official_drc.py`), whether the
`LATEST-LVS` record checked these exact GDS bytes, and the standalone
capacitor/rail demonstrator cited separately. A footprint measured without the
capacitors is not evidence that a complete, capacitor-inclusive core meets the
Area row, and the record says so.

Standard library only. Usage:
    python3 layout/bin/render-ldo-area-record.py [--gds PATH] [--klt klt]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN_DIR))
import _gds_area as ga  # noqa: E402
from _official_drc import official_result  # noqa: E402
from _record_common import git as _repo_git  # noqa: E402

REPO_ROOT = BIN_DIR.parent.parent
REPORTS = REPO_ROOT / "layout" / "ldo-core" / "reports"
CAP_DEMO_REPORTS = REPO_ROOT / "layout" / "cap-rail-demo" / "reports"
SCHEMA_VERSION = 1


def _fmt(d: Decimal, places: int = 6) -> str:
    return f"{d:.{places}f}"


def bbox_agrees(w: Decimal, h: Decimal, m: ga.AreaMeasurement) -> bool:
    """klt's bbox agrees with ours within two database units on each axis."""
    tol = m.dbu_um * 2
    return abs(w - m.width_um) <= tol and abs(h - m.height_um) <= tol


def klt_crosscheck(klt: str, gds: Path, m: ga.AreaMeasurement) -> dict:
    try:
        ver = subprocess.run([klt, "--version"], check=True, capture_output=True, text=True).stdout.strip()
        out = subprocess.run(
            [klt, "stats", str(gds), "--format", "json"], check=True, capture_output=True, text=True
        ).stdout
        b = json.loads(out)["bbox_um"]
    except Exception as exc:  # noqa: BLE001 -- recorded, never fatal
        return {"tool": klt, "status": "unavailable", "detail": str(exc)}
    w, h = Decimal(str(b["width"])), Decimal(str(b["height"]))
    tol = m.dbu_um * 2
    agree = bbox_agrees(w, h, m)
    return {
        "tool": ver,
        "command": "klt stats <gds> --format json",
        "bbox_width_um": str(w),
        "bbox_height_um": str(h),
        "status": "agrees" if agree else "DISAGREES",
        "tolerance_um": str(tol),
    }


def _crosscheck_note(cross: dict) -> str:
    status = cross.get("status")
    if status == "agrees":
        return ""
    if status == "DISAGREES":
        return "\n**The independent bbox cross-check DISAGREES with this measurement**; the verdict above is this script's own measurement and the disagreement is recorded, not resolved.\n"
    return (
        f"\nThe independent `klt stats` cross-check was {status}; no independent agreement is "
        f"asserted for this record.\n"
    )


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def coverage_disclosure(
    layout_dir: Path, gds_sha: str, cell: str, reports: Path = REPORTS,
    cap_demo_reports: Path = CAP_DEMO_REPORTS, root: Path = REPO_ROOT,
) -> dict:
    """What the measured footprint does and does not cover (issue #318).

    Everything is read from files next to the measured GDS (or from the
    `LATEST-LVS` / cap-demo `LATEST` pointers), never restated: a missing or
    unreadable source is reported as unavailable, never as a clean result.
    """
    cov: dict = {}

    fp = _read_json(layout_dir / "floorplan.json")
    if fp is None:
        cov["inventory"] = {"status": "unavailable", "detail": "no readable floorplan.json beside the measured GDS"}
        cov["undrawn_elements"] = None
    else:
        mos = [d for d in fp.get("devices", []) if d.get("kind") == "mos"]
        widest = max(mos, key=lambda d: d.get("w_total_um") or 0, default=None)
        cov["inventory"] = {
            "source": _rel(layout_dir / "floorplan.json", root),
            "mos_count": fp.get("mos_count"),
            "res_count": fp.get("res_count"),
            "block_count": fp.get("block_count"),
            "widest_mos": None if widest is None else {
                "name": widest.get("name"),
                "w_total_um": widest.get("w_total_um"),
                "units": widest.get("units"),
                "unit_w_um": widest.get("unit_w_um"),
                "l_um": widest.get("l_um"),
            },
        }
        cov["undrawn_elements"] = [str(e).split()[0] for e in fp.get("undrawn_elements") or []]

    if not (layout_dir / "mr-drc.run.json").is_file():
        cov["official_drc"] = {"state": "not run", "detail": "no official-deck run in the measured layout record"}
    else:
        off = official_result(layout_dir, cell)
        cov["official_drc"] = {
            "record": _rel(layout_dir / "record.md", root),
            "state": off.state,
            "detail": off.detail,
            "total": off.total,
            "rule_counts": dict(off.counts),
        }

    lvs_id = None
    try:
        lvs_id = (reports / "LATEST-LVS").read_text().strip() or None
    except OSError:
        pass
    if lvs_id is None:
        cov["lvs"] = {"freshness": "unavailable", "detail": "no LATEST-LVS pointer"}
    else:
        lvs_json = _read_json(reports / lvs_id / "lvs.json")
        if lvs_json is None:
            cov["lvs"] = {"record": lvs_id, "freshness": "unavailable", "detail": "LATEST-LVS record has no readable lvs.json"}
        else:
            checked = str((lvs_json.get("environment") or {}).get("layout_sha256") or "")
            checked = checked.removeprefix("sha256:")
            fresh = checked == gds_sha
            cov["lvs"] = {
                "record": lvs_id,
                "status": lvs_json.get("status"),
                "checked_layout_sha256": checked or None,
                "freshness": "fresh" if fresh else "STALE",
                "detail": (
                    "LATEST-LVS checked these exact GDS bytes" if fresh else
                    "LATEST-LVS checked a different GDS; its verdict does not cover the measured layout"
                ),
            }

    demo_id = None
    try:
        demo_id = (cap_demo_reports / "LATEST").read_text().strip() or None
    except OSError:
        pass
    if demo_id is None:
        cov["capacitor_demonstrator"] = None
    else:
        cov["capacitor_demonstrator"] = {
            "record": _rel(cap_demo_reports / demo_id / "record.md", root),
            "scope": "standalone MiM-capacitor + supply-rail overlay; no MOS device, resistor or signal route drawn",
            "certifies_core": False,
        }

    undrawn = cov.get("undrawn_elements")
    if undrawn:
        cov["statement"] = (
            f"The measured footprint omits {len(undrawn)} schematic element(s) that are not drawn in this "
            f"layout ({', '.join(undrawn)}). It is not evidence that a complete, capacitor-inclusive core "
            f"meets the Area row."
        )
    elif undrawn == []:
        cov["statement"] = "floorplan.json lists no undrawn schematic elements."
    else:
        cov["statement"] = "Undrawn-element coverage could not be read; do not treat this footprint as complete-core."
    return cov


def coverage_markdown(cov: dict) -> str:
    lines = ["## Coverage limitations (issue #318)", "", cov["statement"], ""]
    inv = cov.get("inventory") or {}
    if inv.get("status") == "unavailable":
        lines.append(f"- Drawn inventory: unavailable ({inv.get('detail')})")
    else:
        w = inv.get("widest_mos") or {}
        lines.append(
            f"- Drawn inventory (from `{inv.get('source')}`): {inv.get('mos_count')} MOS + "
            f"{inv.get('res_count')} resistor blocks ({inv.get('block_count')} blocks)"
        )
        if w:
            lines.append(
                f"- Widest MOS (the pass device): `{w.get('name')}` W_total {w.get('w_total_um')} um drawn as "
                f"{w.get('units')} x {w.get('unit_w_um')} um parallel units, L {w.get('l_um')} um"
            )
    undrawn = cov.get("undrawn_elements")
    if undrawn:
        lines.append(f"- Not drawn: {', '.join(f'`{e}`' for e in undrawn)} -- absent from both the layout and the LVS reference")
    off = cov.get("official_drc") or {}
    if off.get("state") == "violations":
        lines.append(
            f"- Official-deck DRC (`sky130A_mr.drc`) for this exact layout record (`{off.get('record')}`): "
            f"**FAIL** -- {off.get('detail')}; attribution is in that record. This area record does not change it."
        )
    elif off.get("state") == "clean":
        lines.append(f"- Official-deck DRC for this exact layout record (`{off.get('record')}`): clean -- {off.get('detail')}")
    else:
        lines.append(f"- Official-deck DRC for this layout record: {off.get('state', 'unavailable')} -- {off.get('detail')}")
    lvs = cov.get("lvs") or {}
    if lvs.get("freshness") == "fresh":
        lines.append(f"- LVS: `LATEST-LVS` record `{lvs.get('record')}` (status `{lvs.get('status')}`) checked these exact GDS bytes")
    elif lvs.get("freshness") == "STALE":
        lines.append(
            f"- LVS: **STALE** -- `LATEST-LVS` record `{lvs.get('record')}` (status `{lvs.get('status')}`) checked "
            f"layout sha256 `{lvs.get('checked_layout_sha256')}`, not the measured GDS. No LVS result covers this layout; "
            f"its earlier verdict must not be read as current coverage."
        )
    else:
        lines.append(f"- LVS: unavailable -- {lvs.get('detail')}")
    demo = cov.get("capacitor_demonstrator")
    if demo:
        lines.append(
            f"- Standalone capacitor/rail demonstrator, cited separately: [`{demo.get('record')}`]"
            f"(../../../../{demo.get('record')}) -- {demo.get('scope')}. Its results are about that "
            f"demonstrator only and do not certify this core."
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gds", type=Path, help="routed GDS; default: LATEST record's ldo_core.gds")
    ap.add_argument("--cell", default="ldo_core")
    ap.add_argument("--klt", default="klt", help="klt binary for the independent bbox cross-check ('' to skip)")
    ap.add_argument("--record-id", help="override <UTC>-<sha> (tests)")
    args = ap.parse_args()

    latest = (REPORTS / "LATEST").read_text().strip()
    gds = args.gds or (REPORTS / latest / "ldo_core.gds")
    gds = gds.resolve()
    layout_record = gds.parent.name
    m = ga.measure_file(gds, args.cell)
    sha = ga.sha256_file(gds)
    rel_gds = gds.relative_to(REPO_ROOT).as_posix()

    short = _repo_git(REPO_ROOT, "rev-parse", "--short", "HEAD")
    rid = args.record_id or f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{short}"
    out_dir = REPORTS / rid
    out_dir.mkdir(parents=True, exist_ok=False)  # never overwrite a record

    cross = klt_crosscheck(args.klt, gds, m) if args.klt else {"status": "skipped"}
    coverage = coverage_disclosure(gds.parent, sha, m.cell)
    is_latest = layout_record == latest
    x0, y0, x1, y1 = m.bbox_dbu
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_id": rid,
        "issue": 236,
        "spec_row": "Area",
        "target": "< 0.1 mm^2 total core area, pass FET included, excluding pads and sealring",
        "layout_record": layout_record,
        "layout_record_was_latest": is_latest,
        "gds": {"path": rel_gds, "sha256": sha, "bytes": gds.stat().st_size},
        "cell": m.cell,
        "convention": ga.CONVENTION,
        "dbu_um": str(m.dbu_um),
        "bbox_dbu": [x0, y0, x1, y1],
        "bbox_um": [str(Decimal(v) * m.dbu_um) for v in (x0, y0, x1, y1)],
        "width_um": str(m.width_um),
        "height_um": str(m.height_um),
        "area_um2": str(m.area_um2),
        "area_mm2": str(m.area_mm2),
        "limit_mm2": str(m.limit_mm2),
        "comparison": "area_mm2 < limit_mm2 (strict; exactly the limit FAILS)",
        "verdict": m.verdict,
        "crosscheck": cross,
        "coverage": coverage,
        "provenance": {"git_sha": _repo_git(REPO_ROOT, "rev-parse", "HEAD"), "tool": "layout/bin/render-ldo-area-record.py"},
    }
    (out_dir / "area.json").write_text(json.dumps(record, indent=2) + "\n")

    md = f"""# LDO core area record: {rid}

Measures the routed `{m.cell}` layout against the ratified Area row (`spec/target-spec.md`: < 0.1 mm^2 total core area, pass FET included, excluding pads and sealring), issue #236. The target is unchanged; this record reports where the current layout stands against it.

## Overall verdict: {m.verdict}

- Core footprint: {_fmt(m.width_um, 3)} um x {_fmt(m.height_um, 3)} um = {_fmt(m.area_um2, 1)} um^2 = **{_fmt(m.area_mm2, 6)} mm^2**
- Limit: {m.limit_mm2} mm^2, strict (`area < limit` passes; exactly the limit fails)
- Ratio to limit: {_fmt(m.area_mm2 / m.limit_mm2, 2)}x

## Measured artifact (content-pinned)

- Routed GDS: `{rel_gds}` (layout record `{layout_record}`, {"the" if is_latest else "NOT the"} `LATEST` layout record when this was minted)
- SHA-256: `{sha}`
- Cell: `{m.cell}`; database unit {m.dbu_um} um (from the stream's UNITS record)
- Bounding box (um): ({_fmt(Decimal(x0) * m.dbu_um, 3)}, {_fmt(Decimal(y0) * m.dbu_um, 3)}) to ({_fmt(Decimal(x1) * m.dbu_um, 3)}, {_fmt(Decimal(y1) * m.dbu_um, 3)})

## Geometry convention

{ga.CONVENTION}

Details: the whole instantiated hierarchy counts (routing, rails, taps, well and marker layers, and the pass device); a bounding rectangle is conservative because it charges empty corners and the routing channel to the block; TEXT labels are excluded; PATH shapes grow by half their width; a non-Manhattan transform can only over-count. The core cell contains no pads or sealring, so nothing further is carved out for the row's exclusion clause. This is a measurement of the current routed layout, not a statement about what a compacted floorplan could reach -- compaction is a separate task.

## Independent cross-check

`{json.dumps(cross)}`
{_crosscheck_note(cross)}
{coverage_markdown(coverage)}
## Freshness

`measurements/build_characterization_report.py` compares this record's GDS SHA-256 with the current routed GDS named by `layout/ldo-core/reports/LATEST`. A re-routed layout makes this record STALE until a new area record is minted (this one is never edited).

## Reproduce

```bash
python3 layout/bin/render-ldo-area-record.py --gds {rel_gds}
```

Provenance: repo state `{record['provenance']['git_sha']}`.
"""
    (out_dir / "record.md").write_text(md)
    (REPORTS / "LATEST-AREA").write_text(rid + "\n")
    print(f"{rid}: {m.verdict} {m.area_mm2:.6f} mm^2 -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
