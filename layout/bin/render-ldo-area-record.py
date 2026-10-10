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
from _record_common import git as _repo_git  # noqa: E402

REPO_ROOT = BIN_DIR.parent.parent
REPORTS = REPO_ROOT / "layout" / "ldo-core" / "reports"
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
    x0, y0, x1, y1 = m.bbox_dbu
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_id": rid,
        "issue": 236,
        "spec_row": "Area",
        "target": "< 0.1 mm^2 total core area, pass FET included, excluding pads and sealring",
        "layout_record": layout_record,
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

- Routed GDS: `{rel_gds}` (layout record `{layout_record}`, the `LATEST` DRC record when this was minted)
- SHA-256: `{sha}`
- Cell: `{m.cell}`; database unit {m.dbu_um} um (from the stream's UNITS record)
- Bounding box (um): ({_fmt(Decimal(x0) * m.dbu_um, 3)}, {_fmt(Decimal(y0) * m.dbu_um, 3)}) to ({_fmt(Decimal(x1) * m.dbu_um, 3)}, {_fmt(Decimal(y1) * m.dbu_um, 3)})

## Geometry convention

{ga.CONVENTION}

Details: the whole instantiated hierarchy counts (routing, rails, taps, well and marker layers, and the pass device); a bounding rectangle is conservative because it charges empty corners and the routing channel to the block; TEXT labels are excluded; PATH shapes grow by half their width; a non-Manhattan transform can only over-count. The core cell contains no pads or sealring, so nothing further is carved out for the row's exclusion clause. This is a measurement of the current routed layout, not a statement about what a compacted floorplan could reach -- compaction is a separate task.

## Independent cross-check

`{json.dumps(cross)}`

## Freshness

`measurements/build_characterization_report.py` compares this record's GDS SHA-256 with the current routed GDS named by `layout/ldo-core/reports/LATEST`. A re-routed layout makes this record STALE until a new area record is minted (this one is never edited).

## Reproduce

```bash
python3 layout/bin/render-ldo-area-record.py
```

Provenance: repo state `{record['provenance']['git_sha']}`.
"""
    (out_dir / "record.md").write_text(md)
    (REPORTS / "LATEST-AREA").write_text(rid + "\n")
    print(f"{rid}: {m.verdict} {m.area_mm2:.6f} mm^2 -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
