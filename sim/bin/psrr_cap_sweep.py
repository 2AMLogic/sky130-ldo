"""PSRR C_eff x ESR reduced-sweep helpers (issue #314, Phase 1).

Pure functions, no ngspice/PDK needed:
  * sweep_points / expected_cells  -- expand the manifest
  * apply_cap_point                -- rewrite the testbench netlist for one
                                      (C_eff, ESR) point, incl. zero-ESR topology
  * select_worst                   -- worst-sampled-point selection per sub-metric

This is an evidence finding about the SAMPLED grid only; it does not define the
spec condition (that is a decision record, Phase 2).
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

TIE_TOL_DB = 1e-6

_COUT_RE = re.compile(r"^(COUT)\s+(\S+)\s+(\S+)\s+(\S+)(.*)$", re.IGNORECASE)
_RESR_RE = re.compile(r"^RESR\s+", re.IGNORECASE)


def load_manifest(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def sweep_points(manifest: dict) -> list[tuple[float, float]]:
    """(c_eff_uf, esr_ohm) points, ordered by C_eff then ESR."""
    return [(c, r) for c in manifest["c_eff_uf"] for r in manifest["esr_ohm"]]


def corner_key(corner) -> str:
    process, temp, supply = corner
    return f"{process}_{temp:g}c_{supply:.2f}v"  # == corner-run.py Corner.id


def expected_cells(manifest: dict) -> list[tuple[str, tuple[float, float]]]:
    return [(corner_key(k), p) for k in manifest["corners"] for p in sweep_points(manifest)]


def apply_cap_point(body: list[str], c_uf: float, esr_ohm: float) -> list[str]:
    """Set COUT / ESR in an xschem netlist body for one sweep point.

    ESR == 0 is an electrically equivalent topology: RESR is dropped and COUT's
    second terminal is tied to ground (RESR's other terminal), not replaced by a
    tiny resistor.  Raises ValueError if the expected cards are absent.
    """
    if c_uf <= 0 or esr_ohm < 0:
        raise ValueError("c_uf must be > 0 and esr_ohm >= 0")
    out: list[str] = []
    esr_node = None
    resr_gnd = None
    for ln in body:
        if _RESR_RE.match(ln):
            parts = ln.split()
            esr_node, resr_gnd = parts[1], parts[2]
    if esr_node is None:
        raise ValueError("no RESR card in netlist")
    seen_c = False
    for ln in body:
        m = _COUT_RE.match(ln)
        if m:
            seen_c = True
            bottom = m.group(3)
            if esr_ohm == 0:
                bottom = resr_gnd
            out.append(f"COUT {m.group(2)} {bottom} {c_uf:g}u{m.group(5)}")
        elif _RESR_RE.match(ln):
            if esr_ohm == 0:
                out.append("* RESR removed: zero-ESR topology (#314)")
            else:
                parts = ln.split()
                out.append(f"RESR {parts[1]} {parts[2]} {esr_ohm:g}" + (" " + " ".join(parts[4:]) if len(parts) > 4 else ""))
        else:
            out.append(ln)
    if not seen_c:
        raise ValueError("no COUT card in netlist")
    return out


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def select_worst(manifest: dict, results: list[dict]) -> dict:
    """Worst sampled point per sub-metric.

    results: dicts {corner_id, c_uf, esr_ohm, metrics: {name: float|None}, ok: bool}.
    Returns {metric: {"finding": {...}|None, "missing": [...]}}.  A cell is missing
    if absent, not ok, or its value is non-finite; any missing cell for a metric
    means finding is None (never silently dropped).
    """
    by_cell = {(r["corner_id"], (float(r["c_uf"]), float(r["esr_ohm"]))): r for r in results}
    cells = expected_cells(manifest)
    report: dict = {}
    for metric in manifest["metrics"]:
        missing = []
        per_point: dict[tuple[float, float], tuple[float, str]] = {}
        for corner, point in cells:
            r = by_cell.get((corner, point))
            v = None if r is None or not r.get("ok", True) else (r.get("metrics") or {}).get(metric)
            if not _finite(v):
                missing.append({"corner_id": corner, "c_uf": point[0], "esr_ohm": point[1]})
                continue
            if point not in per_point or v < per_point[point][0]:
                per_point[point] = (v, corner)
        finding = None
        if not missing and per_point:
            floor = min(v for v, _ in per_point.values())
            tied = [p for p, (v, _) in per_point.items() if v - floor <= TIE_TOL_DB]
            c, esr = min(tied)  # lower C_eff, then lower ESR
            v, corner = per_point[(c, esr)]
            finding = {"c_uf": c, "esr_ohm": esr, "psrr_db": v, "corner_id": corner, "tied_points": sorted(tied)}
        report[metric] = {"finding": finding, "missing": missing}
    return report


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] not in ("select",):
        print("usage: psrr_cap_sweep.py select MANIFEST.json RESULTS.json", file=sys.stderr)
        return 2
    rep = select_worst(load_manifest(Path(argv[1])), json.loads(Path(argv[2]).read_text()))
    print(json.dumps(rep, indent=2))
    return 1 if any(v["finding"] is None for v in rep.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
