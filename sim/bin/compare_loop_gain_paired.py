#!/usr/bin/env python3
"""Issue #757: numerical comparison of a paired local/fleet loop-gain run.

PDK-free. Compares the 56 named results of one single-corner
`corner-run.py sim/loop-gain` pair (tt / 27 C / 3.30 V): 18 phase margins
(180 + acN.phc), 18 gain margins (-acN.gmdb), 18 operating-point seeds
(opN.vseed), leg 1's crossover frequency (ac1.fc) and DC gain (ac1.dcg).

These are *execution-path equivalence* tolerances, never spec limits, and are
constants here so a result can never be rescued by widening them from a caller:
vseed 1e-6 V, PM 1e-3 deg, GM 1e-3 dB, DC gain 1e-3 dB, crossover 1e-3 Hz
(sim/README.md batch-backend precedent: ~1 printed digit of the 6-significant-
digit console resolution; compare raw values, not the rounded console).

Confirmed unreached crossings: a value is the string "not_reached" when the
engine reported a no-crossing status (the batch adapter's `not_reached`/null,
the local ngspice measurement failure). Both sides "not_reached" is a
*confirmed non-crossing*, reported in `unreached_both` and counted as agreement.
One side only is a breach (`one_sided_crossing`, verdict rejected). Absent,
None, malformed or non-finite values are *missing* (verdict unresolved):
missing evidence never establishes agreement.

Verdict precedence matches _paired_compare: unresolved > rejected >
engine_mismatch > equivalent. Matching FAIL grades support execution
equivalence only; they never establish spec compliance.

Legs 7 and 13 are reported together (seed, PM, GM) in `continuation_legs`:
the local solver continues across ESR groups, the batch one restarts.

Usage: compare_loop_gain_paired.py REMOTE_VALUES.json LOCAL_VALUES.json
           --remote-engine V --local-engine V --remote-pass PASS|FAIL
           --local-pass PASS|FAIL [--out report.json]
Each values file is a JSON object keyed `opN.vseed`, `acN.phc`, `acN.gmdb`,
`ac1.fc`, `ac1.dcg` (N = 1..18); a no-crossing result is "not_reached".
Extract the remote map with `batch_loop_gain.extract_values` per group response.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _paired_compare
from _record_common import is_finite_number

NOT_REACHED = "not_reached"
N_LEGS = 18
CONTINUATION_LEGS = (7, 13)
VSEED_TOL_V = 1e-6
PM_TOL_DEG = 1e-3
GM_TOL_DB = 1e-3
DCG_TOL_DB = 1e-3
FC_TOL_HZ = 1e-3

TOLS = {
    **{f"pm{i}": (PM_TOL_DEG, "deg") for i in range(1, N_LEGS + 1)},
    **{f"gm{i}": (GM_TOL_DB, "dB") for i in range(1, N_LEGS + 1)},
    **{f"vseed{i}": (VSEED_TOL_V, "V") for i in range(1, N_LEGS + 1)},
    "fc1": (FC_TOL_HZ, "Hz"),
    "dcg1": (DCG_TOL_DB, "dB"),
}


def _val(raw: dict, key: str):
    v = raw.get(key)
    if v == NOT_REACHED:
        return NOT_REACHED
    return v if is_finite_number(v) else None


def derive(raw: dict) -> dict:
    """The 56 named results from the raw step values."""
    out: dict = {}
    for i in range(1, N_LEGS + 1):
        phc, gmdb = _val(raw, f"ac{i}.phc"), _val(raw, f"ac{i}.gmdb")
        out[f"pm{i}"] = 180 + phc if is_finite_number(phc) else phc
        out[f"gm{i}"] = -gmdb if is_finite_number(gmdb) else gmdb
        out[f"vseed{i}"] = _val(raw, f"op{i}.vseed")
    out["fc1"] = _val(raw, "ac1.fc")
    out["dcg1"] = _val(raw, "ac1.dcg")
    return out


def compare(
    remote_raw: dict,
    local_raw: dict,
    remote_engine,
    local_engine,
    remote_pass=None,
    local_pass=None,
) -> dict:
    remote, local = derive(remote_raw), derive(local_raw)
    unreached_both = [n for n in TOLS if remote[n] == NOT_REACHED and local[n] == NOT_REACHED]
    one_sided = [
        n for n in TOLS
        if (remote[n] == NOT_REACHED) != (local[n] == NOT_REACHED)
        and (remote[n] == NOT_REACHED or is_finite_number(remote[n]))
        and (local[n] == NOT_REACHED or is_finite_number(local[n]))
    ]
    skip = set(unreached_both) | set(one_sided)
    rep = _paired_compare.compare(
        {n: t for n, t in TOLS.items() if n not in skip},
        remote, local, remote_engine, local_engine, remote_pass, local_pass,
        extra={
            "continuation_legs": {
                str(i): {k: {"remote": remote[f"{k}{i}"], "local": local[f"{k}{i}"]}
                         for k in ("vseed", "pm", "gm")}
                for i in CONTINUATION_LEGS
            },
        },
    )
    rep["unreached_both"] = unreached_both
    rep["one_sided_crossing"] = one_sided
    for n in unreached_both:
        rep["rows"].append(dict(name=n, remote=NOT_REACHED, local=NOT_REACHED,
                                delta=None, tol=TOLS[n][0], unit=TOLS[n][1], ok=True))
    for n in one_sided:
        rep["breaches"].append(n)
        rep["rows"].append(dict(name=n, remote=remote[n], local=local[n],
                                delta=None, tol=TOLS[n][0], unit=TOLS[n][1], ok=False))
    if one_sided and rep["verdict"] in ("engine_mismatch", "equivalent"):
        rep["verdict"] = "rejected"
        rep["equivalence_claimable"] = False
    return rep


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("remote", type=Path)
    ap.add_argument("local", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--remote-engine", required=True)
    ap.add_argument("--local-engine", required=True)
    ap.add_argument("--remote-pass", choices=("PASS", "FAIL"), required=True)
    ap.add_argument("--local-pass", choices=("PASS", "FAIL"), required=True)
    a = ap.parse_args(argv)
    rep = compare(
        json.loads(a.remote.read_text()), json.loads(a.local.read_text()),
        a.remote_engine, a.local_engine,
        a.remote_pass == "PASS", a.local_pass == "PASS",
    )
    if a.out:
        a.out.write_text(json.dumps(rep, indent=2) + "\n")
    return _paired_compare.print_report(rep, 8)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
