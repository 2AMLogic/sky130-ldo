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


# --------------------------------------------------------------------------
# klt sim request shape (one request per corner; the 9 points x 2 loads are
# ordered `analysis_steps` inside that corner's single deck).  Pure functions.
# --------------------------------------------------------------------------

CDIR = "CDIR"


def add_direct_cap(body: list[str]) -> list[str]:
    """Add a direct VOUT-to-ground capacitor `CDIR` (initially 0 F) next to RESR.

    Same zero-ESR realisation as sim/load-transient (#313): an ESR = 0 point
    puts the full C_eff on CDIR and opens the series COUT+RESR branch (COUT =
    0 F); an ESR > 0 point does the reverse.  This keeps ONE netlist per
    request, which `alter` can walk.  Raises ValueError if COUT/RESR are absent
    or CDIR already exists."""
    cout = next((ln for ln in body if _COUT_RE.match(ln)), None)
    resr = next((ln for ln in body if _RESR_RE.match(ln)), None)
    if cout is None or resr is None:
        raise ValueError("netlist needs both COUT and RESR cards")
    if any(ln.split()[:1] and ln.split()[0].upper() == CDIR for ln in body):
        raise ValueError("netlist already has a CDIR card")
    top = _COUT_RE.match(cout).group(2)
    gnd = resr.split()[2]
    out: list[str] = []
    for ln in body:
        out.append(ln)
        if ln is resr:
            out.append(f"{CDIR} {top} {gnd} 0")
    return out


def point_alters(c_uf: float, esr_ohm: float, park_ohm: float) -> dict[str, float]:
    """`alter` values for one (C_eff, ESR) point (every element set explicitly)."""
    if c_uf <= 0 or esr_ohm < 0:
        raise ValueError("c_uf must be > 0 and esr_ohm >= 0")
    c = c_uf * 1e-6
    if esr_ohm == 0:
        # RESR parked: in series with a 0 F capacitor it carries no current.
        return {"COUT": 0.0, "RESR": float(park_ohm), CDIR: c}
    return {"COUT": c, "RESR": float(esr_ohm), CDIR: 0.0}


def _tok(v: float) -> str:
    return f"{v:g}".replace(".", "p").replace("-", "m")


def point_tag(c_uf: float, esr_ohm: float) -> str:
    return f"c{_tok(c_uf)}u_esr{_tok(esr_ohm * 1000)}m"


def build_steps(manifest: dict) -> tuple[list[dict], list[dict]]:
    """Ordered klt `analysis_steps` and the step map used to read them back.

    For each point (manifest order) and each load: an `op` step (all alters --
    COUT, RESR, CDIR, RLOAD -- set explicitly, so no point inherits another's
    values; the netlist's .nodeset seed applies to this solve) measuring the
    seeded VOUT, then the `ac` step measuring both frequencies.  The manifest's
    `independence_check` point is re-run at the very end under a distinct tag;
    its values must equal the first run's (order independence)."""
    ac_args = manifest["ac_args"]
    park = manifest["resr_park_ohm"]
    rload = manifest["load_rload_ohm"]
    points = sweep_points(manifest)
    rep = tuple(float(x) for x in manifest["independence_check"]["point"])
    if rep not in points:
        raise ValueError("independence_check point is not a sweep point")
    runs = [(p, point_tag(*p)) for p in points] + [(rep, "rep_" + point_tag(*rep))]
    steps: list[dict] = []
    smap: list[dict] = []
    for (c, esr), tag in runs:
        for load in manifest["loads"]:
            alters = dict(point_alters(c, esr, park))
            alters["RLOAD"] = float(rload[load])
            op_name, ac_name = f"{tag}_{load}_op", f"{tag}_{load}_ac"
            steps.append({
                "name": op_name, "analysis": {"kind": "op", "args": ""}, "alter": alters,
                "measurements": [{"name": "vseed", "expr": "v(vout)", "unit": "V"}],
            })
            steps.append({
                "name": ac_name, "analysis": {"kind": "ac", "args": ac_args},
                "measurements": [
                    {"name": "p1k", "expr": "-vdb(vout)[0]", "unit": "dB"},
                    {"name": "p100k", "expr": "-vdb(vout)[2]", "unit": "dB"},
                ],
            })
            smap.append({"tag": tag, "c_uf": c, "esr_ohm": esr, "load": load,
                         "op": op_name, "ac": ac_name})
    return steps, smap


def build_request(manifest: dict, netlist_path: str, pdk_variant: str, lib_rel: str,
                  process: str, temp_c: float, timeout_s: int, ngspice_init: list[str]) -> dict:
    steps, _ = build_steps(manifest)
    return {
        "netlist": netlist_path,
        "engine": "ngspice",
        "models": {"pdk": pdk_variant, "lib": lib_rel},
        "corners": {"process": [process], "temperature_c": [temp_c]},
        "analysis_steps": steps,
        "options": {"timeout_s": timeout_s, "keep_artifacts": True, "ngspice_init": ngspice_init},
    }


def _metric_name(freq: str, load: str) -> str:
    return f"psrr_{'1khz' if freq == 'p1k' else '100khz'}_{load}_db"


def parse_corner(manifest: dict, corner_id: str, rc: dict | None) -> tuple[list[dict], list[dict]]:
    """One klt response corner -> (results for select_worst, repeat-run rows).

    A cell is `ok` only if both of its steps report `ok` and the value is
    finite; anything else stays in the result set with ok=False (reported,
    never dropped).  `rc` None (corner absent from the response) makes every
    cell not-ok."""
    _, smap = build_steps(manifest)
    status = {}
    values: dict[str, object] = {}
    if isinstance(rc, dict):
        status = {s.get("name"): s.get("status") for s in rc.get("steps") or [] if isinstance(s, dict)}
        for m in rc.get("measurements") or []:
            if isinstance(m, dict) and isinstance(m.get("name"), str):
                values[m["name"]] = m.get("value")
    cells: dict[tuple[str, tuple[float, float]], dict] = {}
    for e in smap:
        key = (e["tag"], (e["c_uf"], e["esr_ohm"]))
        row = cells.setdefault(key, {
            "corner_id": corner_id, "c_uf": e["c_uf"], "esr_ohm": e["esr_ohm"],
            "ok": True, "metrics": {}, "vseed_v": {}, "reasons": [],
        })
        for step in (e["op"], e["ac"]):
            if status.get(step) != "ok":
                row["ok"] = False
                row["reasons"].append(f"step {step}: status {status.get(step)!r}")
        vs = values.get(f"{e['op']}.vseed")
        row["vseed_v"][e["load"]] = float(vs) if _finite(vs) else None
        for freq in ("p1k", "p100k"):
            v = values.get(f"{e['ac']}.{freq}")
            name = _metric_name(freq, e["load"])
            row["metrics"][name] = float(v) if _finite(v) else None
            if not _finite(v):
                row["reasons"].append(f"{name}: value {v!r} not finite/absent")
    results, repeats = [], []
    for (tag, _), row in cells.items():
        row["ok"] = row["ok"] and not row["reasons"]
        (repeats if tag.startswith("rep_") else results).append(row)
    return results, repeats


def job_not_run_reason(rc: dict, has_engine_log: bool) -> str | None:
    """Why a response corner reflects a simulation that never ran, or None.

    A corner with no engine log was never simulated (e.g. a batch job refused
    by the fleet runner, or a launch failure).  That is an infrastructure
    failure: no measurement exists, so it must abort the run without a record
    rather than be minted as an all-missing grid.  A corner that ran but whose
    steps failed has a log and goes through as not-ok cells instead."""
    if has_engine_log:
        return None
    diags = rc.get("diagnostics") if isinstance(rc, dict) else None
    msgs = [f"{d.get('code')}: {d.get('message')}" for d in diags or [] if isinstance(d, dict)]
    return "; ".join(msgs)[:1000] or f"no engine log (klt corner status {rc.get('status')!r})"


def independence_report(results: list[dict], repeats: list[dict], tol_db: float) -> list[dict]:
    """Compare each repeat-run cell against the first run of the same point."""
    first = {(r["corner_id"], r["c_uf"], r["esr_ohm"]): r for r in results}
    out = []
    for rep in repeats:
        base = first.get((rep["corner_id"], rep["c_uf"], rep["esr_ohm"]))
        for name, v in sorted(rep["metrics"].items()):
            b = None if base is None else base["metrics"].get(name)
            same = _finite(v) and _finite(b) and abs(v - b) <= tol_db
            out.append({"corner_id": rep["corner_id"], "c_uf": rep["c_uf"], "esr_ohm": rep["esr_ohm"],
                        "metric": name, "first_db": b, "repeat_db": v, "identical": bool(same)})
    return out


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
