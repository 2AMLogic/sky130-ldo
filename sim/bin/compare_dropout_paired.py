#!/usr/bin/env python3
"""Issue #375: numerical comparison of the paired local/fleet dropout run.

PDK-free. Compares the two raw card values and the derived dropout voltage of
one single-corner `corner-run.py sim/dropout-vs-load` pair (the cold-start
crossing adapter, one tt / 27 °C / 3.30 V request). These are *execution-path
equivalence* tolerances, never spec limits: |d| <= 1 uV on `dropout_vin_x`,
`vout_at_max_vin_v` and the derived `dropout_v = dropout_vin_x - 1.764`
(sim/README.md, "Dropout cold-start crossing on the batch backend"). Tolerances
are constants here so a result can never be rescued by widening them.

Verdicts and precedence match compare_load_regulation_paired.py (#381) and
compare_line_regulation_paired.py (#384): unresolved > rejected >
engine_mismatch > equivalent. Matching FAIL verdicts (the expected grade here:
0.398 V is above the ratified < 0.3 V bound) support execution equivalence
only; they never establish spec compliance.

Local values are read from the full-precision lines of the local ngspice log
(7 significant digits), not from corner-run's `%.6g` summary. The printed
resolution at the ~1.8 V endpoint is 1e-6 V -- exactly the tolerance -- so a
delta of one printed digit on `vout_at_max_vin_v` is reported but sub-uV
agreement there cannot be demonstrated; that limit is recorded in the report
as `print_resolution_v` (the ~0.4 V dropout metrics resolve to 1e-7 V).

Usage: compare_dropout_paired.py <diagnostics-dir> --local-engine N
           --remote-pass PASS|FAIL --local-pass PASS|FAIL [--out report.json]
(reads remote/*/response.json -- exactly the one request this bench writes;
zero or several responses is an error, never a merge -- and local/ngspice.log).
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
DROPOUT_V_TOL = 1e-6
PRINT_RESOLUTION_V = 1e-6  # ngspice prints 7 significant digits: 1e-6 V at the ~1.8 V endpoint
CROSSING_V = 1.764  # the v(vout) threshold the crossing card fires at
RAW = ["dropout_vin_x", "vout_at_max_vin_v"]
DERIVED = ["dropout_v"]
TOLS = {
    "dropout_vin_x": (ENDPOINT_TOL_V, "V"),
    "vout_at_max_vin_v": (ENDPOINT_TOL_V, "V"),
    "dropout_v": (DROPOUT_V_TOL, "V"),
}


def derive(v: dict) -> dict:
    """The dropout voltage from the raw crossing card, as the manifest does."""
    x = v.get("dropout_vin_x")
    return {"dropout_v": None if not is_finite_number(x) else x - CROSSING_V}


def compare(
    remote: dict,
    local: dict,
    remote_engine,
    local_engine,
    remote_pass=None,
    local_pass=None,
) -> dict:
    return _paired_compare.compare(
        TOLS,
        remote,
        local,
        remote_engine,
        local_engine,
        remote_pass,
        local_pass,
        extra={"print_resolution_v": PRINT_RESOLUTION_V},
    )


def load_remote(d: Path) -> tuple[dict, str | None]:
    """Load the one remote response this bench writes; pooling measurements
    across requests would let two incomplete requests fake a complete pair."""
    paths = sorted((d / "remote").glob("*/response.json"))
    if len(paths) != 1:
        raise SystemExit(
            f"expected exactly one remote/*/response.json under {d}, found {len(paths)}"
        )
    resp = json.loads(paths[0].read_text())
    vals = {}
    for m in resp["corners"][0]["measurements"]:
        if is_finite_number(m.get("value")):
            vals[m["name"].split(".", 1)[-1]] = m["value"]
    if not vals:
        raise SystemExit(f"no remote/*/response.json measurements under {d}")
    vals.update({k: v for k, v in derive(vals).items() if v is not None})
    return vals, _paired_compare.engine_version(
        [resp.get("environment", {}).get("engine_version")]
    )


# Accepts the `.meas` echo lines (`name = value at=/from=...`) and the
# `print meas_<name>` lines (`meas_name = value`); a later line for the same
# name wins (the print lines come after the meas echoes in ngspice stdout).
_LOCAL = re.compile(
    r"^(?:meas_)?(dropout_vin_x|vout_at_max_vin_v|dropout_v)\s*=\s*"
    r"([-+0-9.eE]+)(?:\s+[a-z_-]+=.*)?$",
    re.M,
)


def load_local(d: Path) -> dict:
    """Raw card and derived values from the local ngspice log. `dropout_v` is
    recomputed from the raw card, exactly as the remote half is."""
    text = (d / "local" / "ngspice.log").read_text()
    vals = {m.group(1): float(m.group(2)) for m in _LOCAL.finditer(text)}
    vals.update({k: v for k, v in derive(vals).items() if v is not None})
    return vals


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--local-engine", required=True, help="e.g. 47")
    ap.add_argument("--remote-pass", choices=("PASS", "FAIL"), required=True)
    ap.add_argument("--local-pass", choices=("PASS", "FAIL"), required=True)
    a = ap.parse_args(argv)
    rv, reng = load_remote(a.dir)
    lv = load_local(a.dir)
    rep = compare(
        rv, lv, reng, a.local_engine, a.remote_pass == "PASS", a.local_pass == "PASS"
    )
    if a.out:
        a.out.write_text(json.dumps(rep, indent=2) + "\n")
    return _paired_compare.print_report(rep, 20)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
