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

Evidence comes from artifacts, never operator assertions (as the sibling
comparators): the remote map and engine version are read from
`<dir>/remote/<group>/response.json` for the three ESR groups (esr10m, esr500m,
esr0); the engine is the one `environment.engine_version` all three agree on, and
disagreement (or absence) is `None`, i.e. `engine_mismatch`. A remote result with
`status: "not_reached"` and `value: null` is a confirmed non-crossing (derived
in `load_remote`); any other null/errored/duplicated result is missing.
The local map is `<dir>/local/values.json`, an object keyed `opN.vseed`,
`acN.phc`, `acN.gmdb`, `ac1.fc`, `ac1.dcg`: a crossing card (fc/phc/gmdb) PRESENT
with value null is the local ngspice's failed crossing measurement (`n/a` in
corner-run's console) and is read as a confirmed non-crossing; an absent key is
missing (`load_local`).

Usage: compare_loop_gain_paired.py DIR --local-engine V --remote-pass PASS|FAIL
           --local-pass PASS|FAIL [--out report.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _paired_compare
import batch_loop_gain as blr
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


def load_remote(d: Path) -> tuple[dict, str | None, list[str]]:
    """Raw remote map + the single agreed engine version (None on any
    disagreement or absence) + the engine versions seen."""
    vals: dict = {}
    dup: set[str] = set()
    engines: set = set()
    for key in blr.GROUP_KEYS:
        resp = json.loads((d / "remote" / key / "response.json").read_text())
        eng = resp.get("environment", {}).get("engine_version")
        engines.add(None if eng is None else str(eng))
        for m in resp["corners"][0]["measurements"]:
            name = m.get("name")
            if not isinstance(name, str):
                continue
            name = name.lower()
            if name in vals:
                dup.add(name)
            card = name.split(".", 1)[-1]
            if m.get("status") == "not_reached" and card in blr.UNREACHABLE and m.get("value") is None:
                vals[name] = NOT_REACHED
            elif m.get("status") == "error":
                vals[name] = None
            else:
                vals[name] = m.get("value")
    for name in dup:
        vals[name] = None  # reported twice: never evidence
    seen = sorted(e for e in engines if e is not None)
    engine = seen[0] if len(engines) == 1 and None not in engines else None
    return vals, engine, seen


def load_local(d: Path) -> dict:
    raw = json.loads((d / "local" / "values.json").read_text())
    out = {}
    for k, v in raw.items():
        card = k.lower().split(".", 1)[-1]
        out[k.lower()] = NOT_REACHED if v is None and card in blr.UNREACHABLE else v
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--local-engine", required=True)
    ap.add_argument("--remote-pass", choices=("PASS", "FAIL"), required=True)
    ap.add_argument("--local-pass", choices=("PASS", "FAIL"), required=True)
    a = ap.parse_args(argv)
    rv, reng, _ = load_remote(a.dir)
    rep = compare(rv, load_local(a.dir), reng, a.local_engine,
                  a.remote_pass == "PASS", a.local_pass == "PASS")
    if a.out:
        a.out.write_text(json.dumps(rep, indent=2) + "\n")
    return _paired_compare.print_report(rep, 8)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
