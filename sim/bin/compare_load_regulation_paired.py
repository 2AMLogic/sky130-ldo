#!/usr/bin/env python3
"""Issue #381: numerical comparison of a paired local/fleet load-regulation run.

PDK-free. Compares the six raw endpoint values and both derived differences of
one single-corner `corner-run.py sim/load-regulation` pair. These are
*execution-path equivalence* tolerances, never spec limits: raw endpoint
|d| <= 1 uV, `load_reg_v` |d| <= 2 uV, `load_reg_pct` |d| <= 1.2e-4 percentage
points (sim/README.md, "Load regulation endpoints on the batch backend").
Tolerances are constants here so a result can never be rescued by widening
them.

Verdicts and precedence match compare_line_regulation_paired.py:
unresolved > rejected > engine_mismatch > equivalent. Matching FAIL verdicts
support execution equivalence only; they never establish spec compliance.

Local values are read from the full-precision `meas` lines of the local
ngspice log (7 significant digits), not from corner-run's `%.6g` summary. The
printed resolution (1e-6 V at 1.8 V) equals the raw tolerance, so a delta of
exactly one printed digit is reported but cannot by itself prove sub-uV
agreement; that limit is recorded in the report as `print_resolution_v`.

Usage: compare_load_regulation_paired.py <diagnostics-dir> --local-engine N
           --remote-pass PASS|FAIL [--out report.json]
(reads remote/tran{1,2}/response.json and local/ngspice.log).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _record_common import is_finite_number

ENDPOINT_TOL_V = 1e-6
LOAD_REG_V_TOL = 2e-6
LOAD_REG_PCT_TOL = 1.2e-4
PRINT_RESOLUTION_V = 1e-6  # ngspice prints 7 significant digits at ~1.8 V
VNOM = 1.8
ENDPOINTS = [
    f"vout_{ld}{sfx}" for ld in ("0ma", "50ma") for sfx in ("", "_min", "_max")
]
DERIVED = ["load_reg_v", "load_reg_pct"]
TOLS = {
    **{n: (ENDPOINT_TOL_V, "V") for n in ENDPOINTS},
    "load_reg_v": (LOAD_REG_V_TOL, "V"),
    "load_reg_pct": (LOAD_REG_PCT_TOL, "%"),
}


def derive(v: dict) -> dict:
    """Both differences from the graded average endpoints, as the manifest does."""
    a, b = v.get("vout_0ma"), v.get("vout_50ma")
    if not (is_finite_number(a) and is_finite_number(b)):
        return {"load_reg_v": None, "load_reg_pct": None}
    return {
        "load_reg_v": abs(b - a),
        "load_reg_pct": 100 * abs(b - a) / VNOM,
    }


def compare(
    remote: dict,
    local: dict,
    remote_engine,
    local_engine,
    remote_pass=None,
    local_pass=None,
) -> dict:
    rows, missing, breaches = [], [], []
    for name in ENDPOINTS + DERIVED:
        tol, unit = TOLS[name]
        r, l = remote.get(name), local.get(name)
        if not (is_finite_number(r) and is_finite_number(l)):
            missing.append(name)
            rows.append(
                dict(name=name, remote=r, local=l, delta=None, tol=tol, unit=unit, ok=False)
            )
            continue
        d = l - r
        ok = abs(d) <= tol
        if not ok:
            breaches.append(name)
        rows.append(dict(name=name, remote=r, local=l, delta=d, tol=tol, unit=unit, ok=ok))
    engines_equal = remote_engine is not None and str(remote_engine) == str(local_engine)
    verdict_match = remote_pass is not None and remote_pass == local_pass
    if missing or not verdict_match:
        verdict = "unresolved"
    elif breaches:
        verdict = "rejected"
    elif not engines_equal:
        verdict = "engine_mismatch"
    else:
        verdict = "equivalent"
    return {
        "verdict": verdict,
        "equivalence_claimable": verdict == "equivalent",
        "engines_equal": engines_equal,
        "remote_engine": remote_engine,
        "local_engine": local_engine,
        "print_resolution_v": PRINT_RESOLUTION_V,
        "spec_verdicts": {
            "remote_pass": remote_pass,
            "local_pass": local_pass,
            "match": verdict_match,
        },
        "missing": missing,
        "breaches": breaches,
        "rows": rows,
    }


def load_remote(d: Path) -> tuple[dict, str | None, list[str]]:
    vals, engines = {}, set()
    for t in (1, 2):
        resp = json.loads((d / "remote" / f"tran{t}" / "response.json").read_text())
        engines.add(str(resp["environment"].get("engine_version")))
        for m in resp["corners"][0]["measurements"]:
            if is_finite_number(m.get("value")):
                vals[m["name"].split(".", 1)[1]] = m["value"]
    vals.update({k: v for k, v in derive(vals).items() if v is not None})
    return vals, (engines.pop() if len(engines) == 1 else None), sorted(engines)


_MEAS = re.compile(
    r"^(vout_(?:0ma|50ma)(?:_min|_max)?)\s*=\s*([-+0-9.eE]+)(?:\s+(?:from|at)=.*)?$", re.M
)


def load_local(d: Path) -> dict:
    """Endpoint values from the local ngspice log. Accepts the 6-digit `meas` lines and
    the `print` lines (`name = value`, `set numdgt`); a later line for the same name wins."""
    text = (d / "local" / "ngspice.log").read_text()
    vals = {m.group(1): float(m.group(2)) for m in _MEAS.finditer(text)}
    vals.update({k: v for k, v in derive(vals).items() if v is not None})
    return vals


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--local-engine", required=True, help="e.g. 42")
    ap.add_argument("--remote-pass", choices=("PASS", "FAIL"), required=True)
    ap.add_argument("--local-pass", choices=("PASS", "FAIL"), required=True)
    a = ap.parse_args(argv)
    rv, reng, _ = load_remote(a.dir)
    lv = load_local(a.dir)
    rep = compare(
        rv, lv, reng, a.local_engine, a.remote_pass == "PASS", a.local_pass == "PASS"
    )
    if a.out:
        a.out.write_text(json.dumps(rep, indent=2) + "\n")
    for r in rep["rows"]:
        d = "n/a" if r["delta"] is None else f"{r['delta']:+.6g}"
        print(
            f"{r['name']:16s} remote={r['remote']} local={r['local']} "
            f"d={d} {r['unit']} {'ok' if r['ok'] else 'OUT'}"
        )
    print(
        f"engines remote={rep['remote_engine']} local={rep['local_engine']} "
        f"-> verdict {rep['verdict']}"
    )
    return 0 if rep["verdict"] == "equivalent" else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
