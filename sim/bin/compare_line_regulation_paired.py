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
`rejected` (a difference exceeds tolerance), `unresolved` (invalid endpoint
measurements, missing/non-finite values or mismatched pass/fail verdicts).
Precedence: unresolved > rejected > engine_mismatch > equivalent.
Matching FAIL verdicts support execution equivalence only.

Usage: compare_line_regulation_paired.py <diagnostics-dir> [--out report.json]
(reads remote/tran{1..4}/response.json and local/corner-run.log).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# `python3 -I` (the README reproduce form) implies -P on Python 3.11+, so
# this script's directory is not on sys.path; the sibling modules below
# live there.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _paired_compare
from _record_common import is_finite_number

ENDPOINT_TOL_V = 1e-6
SLOPE_TOL_MV_PER_V = 0.01
ENDPOINT_CARDS = [
    [base, base + "_min", base + "_max"]
    for base in ("vout_1ma_lo", "vout_1ma_hi", "vout_50ma_lo", "vout_50ma_hi")
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


TOLS = {
    **{n: (ENDPOINT_TOL_V, "V") for cards in ENDPOINT_CARDS for n in cards},
    **{n: (SLOPE_TOL_MV_PER_V, "mV/V") for n in SLOPES},
}


def compare(
    remote: dict,
    local: dict,
    remote_engine,
    local_engine,
    remote_pass=None,
    local_pass=None,
    remote_errors: list[str] | None = None,
) -> dict:
    return _paired_compare.compare(
        TOLS, remote, local, remote_engine, local_engine, remote_pass, local_pass,
        remote_errors=remote_errors,
    )


def load_remote(d: Path) -> tuple[dict, str | None, list[str]]:
    vals, engine, errors = _paired_compare.load_endpoint_responses(d, ENDPOINT_CARDS)
    vals.update({k: v for k, v in derive_slopes(vals).items() if v is not None})
    return vals, engine, errors


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
    rv, reng, errors = load_remote(a.dir)
    lv, lpass = load_local(a.dir)
    rep = compare(
        rv, lv, reng, a.local_engine, a.remote_pass == "PASS", lpass, remote_errors=errors
    )
    text = json.dumps(rep, indent=2) + "\n"
    if a.out:
        a.out.write_text(text)
    return _paired_compare.print_report(rep, 28)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
