#!/usr/bin/env python3
"""Issue #384: numerical comparison of a paired local/fleet line-regulation run.

PDK-free. Compares the 12 raw endpoint values and both derived slopes of one
single-corner `corner-run.py sim/line-regulation` pair. These are
*execution-path equivalence* tolerances, never spec limits: raw endpoint
|d| <= 1 uV, slope |d| <= 0.01 mV/V (sim/README.md, "Line regulation
endpoints on the batch backend"). Tolerances are constants here so a result
can never be rescued by widening them.

Verdicts: `equivalent` (all values present, within tolerance, engines equal),
`engine_mismatch` (values may be reported, equivalence NOT claimable),
`rejected` (a difference exceeds tolerance), `unresolved` (missing/non-finite
value or a mismatched pass/fail verdict). Precedence: unresolved > rejected >
engine_mismatch > equivalent. Matching FAIL verdicts support execution
equivalence only; they never establish spec compliance.

Usage: compare_line_regulation_paired.py <diagnostics-dir> [--out report.json]
(reads remote/tran{1..4}/response.json and local/corner-run.log).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _record_common import is_finite_number

ENDPOINT_TOL_V = 1e-6
SLOPE_TOL_MV_PER_V = 0.01
ENDPOINTS = [
    f"vout_{ld}_{vin}{sfx}"
    for ld in ("1ma", "50ma")
    for vin in ("lo", "hi")
    for sfx in ("", "_min", "_max")
]
SLOPES = ["line_reg_1ma_mv_per_v", "line_reg_50ma_mv_per_v"]


def derive_slopes(v: dict) -> dict:
    """Slope from the graded average endpoints, as the deck/manifest defines it."""
    out = {}
    for ld, name in (("1ma", SLOPES[0]), ("50ma", SLOPES[1])):
        lo, hi = v.get(f"vout_{ld}_lo"), v.get(f"vout_{ld}_hi")
        out[name] = (
            abs(1000 * (hi - lo) / (3.63 - 2.97))
            if is_finite_number(lo) and is_finite_number(hi)
            else None
        )
    return out


def compare(
    remote: dict,
    local: dict,
    remote_engine,
    local_engine,
    remote_pass=None,
    local_pass=None,
) -> dict:
    rows, missing, breaches = [], [], []
    for name in ENDPOINTS + SLOPES:
        tol, unit = (
            (SLOPE_TOL_MV_PER_V, "mV/V") if name in SLOPES else (ENDPOINT_TOL_V, "V")
        )
        r, l = remote.get(name), local.get(name)
        if not (is_finite_number(r) and is_finite_number(l)):
            missing.append(name)
            rows.append(
                {
                    "name": name,
                    "remote": r,
                    "local": l,
                    "delta": None,
                    "tol": tol,
                    "unit": unit,
                    "ok": False,
                }
            )
            continue
        d = l - r
        ok = abs(d) <= tol
        if not ok:
            breaches.append(name)
        rows.append(
            {
                "name": name,
                "remote": r,
                "local": l,
                "delta": d,
                "tol": tol,
                "unit": unit,
                "ok": ok,
            }
        )
    engines_equal = remote_engine is not None and str(remote_engine) == str(
        local_engine
    )
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
    for t in range(1, 5):
        resp = json.loads((d / "remote" / f"tran{t}" / "response.json").read_text())
        engines.add(str(resp["environment"].get("engine_version")))
        for m in resp["corners"][0]["measurements"]:
            if m.get("status") == "pass" or is_finite_number(m.get("value")):
                vals[m["name"].split(".", 1)[1]] = m["value"]
    vals.update({k: v for k, v in derive_slopes(vals).items() if v is not None})
    return vals, (engines.pop() if len(engines) == 1 else None), sorted(engines)


def load_local(d: Path) -> tuple[dict, bool | None]:
    text = (d / "local" / "corner-run.log").read_text()
    m = re.search(r"^\[\s*1/1\]\s+\S+\s+(PASS|FAIL)\s+(.*)$", text, re.MULTILINE)
    if not m:
        return {}, None
    vals = {}
    for kv in m.group(2).split(", "):
        k, _, v = kv.partition("=")
        try:
            vals[k.strip()] = float(v)
        except ValueError:
            pass
    return vals, m.group(1) == "PASS"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument(
        "--local-engine",
        required=True,
        help="e.g. 42 (ngspice major version of the local run)",
    )
    ap.add_argument("--remote-pass", choices=("PASS", "FAIL"), required=True)
    a = ap.parse_args(argv)
    rv, reng, _ = load_remote(a.dir)
    lv, lpass = load_local(a.dir)
    rep = compare(rv, lv, reng, a.local_engine, a.remote_pass == "PASS", lpass)
    text = json.dumps(rep, indent=2) + "\n"
    if a.out:
        a.out.write_text(text)
    for r in rep["rows"]:
        d = "n/a" if r["delta"] is None else f"{r['delta']:+.6g}"
        print(
            f"{r['name']:28s} remote={r['remote']} local={r['local']} d={d} {r['unit']} {'ok' if r['ok'] else 'OUT'}"
        )
    print(
        f"engines remote={rep['remote_engine']} local={rep['local_engine']} -> verdict {rep['verdict']}"
    )
    return 0 if rep["verdict"] == "equivalent" else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
