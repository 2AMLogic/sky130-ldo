#!/usr/bin/env python3
"""Wrap the committed corner-matrix records into `klt sim`-shaped envelopes
for T1 item 5 (issue #449).

T1 item 5 ("Full corner verification vs a ratified spec") accepts exactly one
evidence kind for an analog block: a ``klt sim`` envelope (a ``measurements``
list plus ``corner_count``). The experiment records under
``sim/<bench>/records/*.json`` are this repo's own harness format, which the
grader does not read, so item 5 rendered ``no_evidence`` even though a full
45-point PVT campaign exists. This script **wraps those committed records,
without re-simulating anything**, into the ``klt sim`` response shape. It is
the "wrap" route of the issue, the same route as
``2AMLogic/gf180-comparator``'s ``signoff/make_item5_envelope.py``.

Honesty contract (read before trusting an envelope)
---------------------------------------------------
* An envelope is NOT output of a ``klt sim`` run. Its ``wrapper`` field says
  so. Every value, limit and pass/fail verdict is copied verbatim from the
  cited record (pinned by sha256 in ``source_record``); nothing is re-measured
  and no verdict is recomputed. The only thing this script adds is the
  ``spec_row`` tag on a measurement and the ``margin`` arithmetic.
* The limit carried on each tagged measurement is the **ratified** bound.
  ``RATIFIED`` below states each bound next to the spec row it comes from, and
  the script refuses to write if a record's own limit disagrees with it. So a
  bench that quietly gated on a looser bound cannot be wrapped as if it graded
  the ratified one, and no ratified bound is relaxed here.
* Each envelope is pinned (``provenance.input.content_hash``) to the netlist
  snapshot the record simulated. That is "the netlist this record ran on", not
  a claim that it is the current schematic: ``measurements/characterization.md``
  reports the freshness of each record separately and most read ``STALE``.
* A record that ran fewer corners than its experiment declares (the dropout
  record is a one-corner attribution run) is never reported as ``pass``: its
  envelope is ``pass_partial`` at best, with the missing matrix recorded as
  skipped work in ``coverage``.
* ``Area`` and ``Output noise`` are NOT wrapped. Area is a layout measurement
  (the bounding box of a GDS), not a netlist simulation, so no ``klt sim``
  envelope can express it; Output noise is waived by the spec row itself. Both
  are declared gaps in ``signoff/block-manifest.json``.

Usage (from the repo root):

    python3 signoff/make_item5_envelope.py           # write (append-only)
    python3 signoff/make_item5_envelope.py --check   # exit 1 on drift

Output files are named ``signoff/evidence/item5-<bench>-<record id>.sim.json``.
An existing file with different content is never overwritten: a newer record
mints a new file, and the manifest and ``signoff/artifact-pins.json`` are then
re-pointed at it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "signoff" / "evidence"

#: (bench, record id) -- the record `measurements/characterization.md` cites
#: for each row. tests/test_item5_envelopes.py checks this list against that
#: file, so an envelope cannot drift from the rollup it must agree with.
RECORDS = [
    ("dropout-vs-load", "20261011-092557-7a4e0cc"),
    ("line-regulation", "20260926-200304-35b7392"),
    ("load-regulation", "20260926-010432-228fbc7"),
    ("load-transient", "20260926-013955-6449a98"),
    ("psrr-dc", "20260926-033606-4a9ec09"),
    ("iq", "20260910-034648-6c0436d"),
    ("current-limit", "20260825-105322-933dfdd"),
    ("startup", "20260825-110456-933dfdd"),
    ("enable-shutdown", "20260825-111526-933dfdd"),
    ("thermal", "20260926-095154-f6ab418"),
    ("loop-gain", "20260926-040338-4a9ec09"),
]

#: bench -> {measurement: (spec row id, ratified {"min"/"max"} bound)}.
#: Row ids are the ones declared under ``spec_rows."5"`` in the manifest.
#: Bounds are read from the ratified row of spec/target-spec.md (cited per
#: line); a measurement not listed is carried as an untagged observation with
#: the record's own limits.
_BAND = {"min": 1.764, "max": 1.836}  # Output / startup: 1.8 V +-2 %
RATIFIED: dict[str, dict[str, tuple[str, dict[str, float]]]] = {
    # Dropout @ 50 mA: < 300 mV
    "dropout-vs-load": {"dropout_v": ("dropout", {"max": 0.3})},
    # Line regulation: < 5 mV/V at 1 mA and 50 mA
    "line-regulation": {
        "line_reg_1ma_mv_per_v": ("line-regulation", {"max": 5}),
        "line_reg_50ma_mv_per_v": ("line-regulation", {"max": 5}),
    },
    # Load regulation: < 1 % (18 mV)
    "load-regulation": {
        "load_reg_v": ("load-regulation", {"max": 0.018}),
        "load_reg_pct": ("load-regulation", {"max": 1}),
    },
    # Load transient: peak excursion <= 150 mV, recover to +-1 % in <= 20 us
    "load-transient": {
        "undershoot_v": ("load-transient", {"max": 0.15}),
        "overshoot_v": ("load-transient", {"max": 0.15}),
        "recovery_rise_us": ("load-transient", {"max": 20}),
        "recovery_fall_us": ("load-transient", {"max": 20}),
    },
    # PSRR: > 50 dB @ 1 kHz and > 20 dB @ 100 kHz, at 1 mA and 50 mA
    "psrr-dc": {
        "psrr_1khz_1ma_db": ("psrr", {"min": 50}),
        "psrr_1khz_50ma_db": ("psrr", {"min": 50}),
        "psrr_100khz_1ma_db": ("psrr", {"min": 20}),
        "psrr_100khz_50ma_db": ("psrr", {"min": 20}),
    },
    # Iq: < 30 uA at no load and at full load (DR-009, proposed)
    "iq": {
        "iq_no_load_ua": ("iq", {"max": 30}),
        "iq_full_load_ua": ("iq", {"max": 30}),
    },
    # Output: 1.8 V +-2 % (graded at 50 mA over the 45-point matrix here);
    # Current limit: never engages for I_load <= 50 mA, survives a Vout = 0 short
    "current-limit": {
        "vout_50ma_v": ("output", _BAND),
        "ilim_short_ma": ("current-limit", {"min": 50}),
        "ilim_knee_ma": ("current-limit", {"min": 50}),
        "ishort_ripple_pct": ("current-limit", {"max": 100}),
    },
    # Startup: inside +-2 % window, overshoot <= +2 %
    "startup": {
        f"{kind}_{cout}_{load}_v": ("startup", {"max": 1.836} if kind == "vpk" else {"min": 1.764})
        for kind in ("vpk", "vfloor")
        for cout in ("c033", "c47")
        for load in ("0ma", "50ma")
    },
    # Enable / shutdown: shutdown Iq < 3 uA, Vin->Vout leakage <= 1 uA
    "enable-shutdown": {
        "iq_shutdown_static_ua": ("enable-shutdown", {"max": 3.0}),
        "iq_shutdown_after_edge_ua": ("enable-shutdown", {"max": 3.0}),
        "leak_vin_vout_ua": ("enable-shutdown", {"max": 1.0}),
    },
    # Thermal: specified to Tj <= 125 C; DR-005 backstop trips above it and
    # auto-restarts with positive hysteresis
    "thermal": {
        "trip_temp_c": ("thermal", {"min": 125}),
        "hysteresis_c": ("thermal", {"min": 0}),
    },
    # Stability: PM >= 45 deg, GM >= 10 dB, worst corner
    "loop-gain": {
        "pm_c033_50ma_deg": ("stability", {"min": 45}),
        "pm_c033_1ma_deg": ("stability", {"min": 45}),
        "pm_c033_0ma_deg": ("stability", {"min": 45}),
        "pm_c47_50ma_deg": ("stability", {"min": 45}),
        "pm_c47_1ma_deg": ("stability", {"min": 45}),
        "pm_c47_0ma_deg": ("stability", {"min": 45}),
        "pm_c033_esr500m_50ma_deg": ("stability", {"min": 45}),
        "gm_c033_50ma_db": ("stability", {"min": 10}),
        "gm_c033_0ma_db": ("stability", {"min": 10}),
    },
}

WRAPPER = (
    "NOT a `klt sim` run. Hand-wrapped by signoff/make_item5_envelope.py from "
    "the committed harness-format record named in `source_record`; every "
    "value, limit and verdict is copied verbatim and nothing was re-simulated. "
    "Measurements tagged with a `spec_row` carry that row's RATIFIED bound "
    "(spec/target-spec.md, DR-006), which the script checked against the "
    "record's own limit before writing. The input pin is the netlist snapshot "
    "the record simulated, not necessarily the current schematic: see "
    "measurements/characterization.md for per-record freshness."
)


class WrapError(Exception):
    """A record does not say what the ratified row requires; nothing is written."""


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _limits(m: dict) -> dict | None:
    lim = {k: m[k] for k in ("min", "max") if m.get(k) is not None}
    return lim or None


def _margin(value: float, lim: dict | None) -> float | None:
    if not lim:
        return None
    margins = []
    if "max" in lim:
        margins.append(lim["max"] - value)
    if "min" in lim:
        margins.append(value - lim["min"])
    return min(margins)


def _load(bench: str, rid: str) -> tuple[dict, Path]:
    path = REPO_ROOT / "sim" / bench / "records" / f"{rid}.json"
    return json.loads(path.read_text()), path


def build_envelope(bench: str, rid: str) -> dict:
    rec, rec_path = _load(bench, rid)
    tags = RATIFIED[bench]
    snap = REPO_ROOT / rec["links"]["netlist_snapshot"]
    matrix = rec.get("matrix") or {}
    subset = bool(matrix.get("is_subset"))

    corners, checked, seen = [], [], set()
    for c in rec["corners"]:
        ms = []
        for m in c["measurements"]:
            name = m["name"]
            seen.add(name)
            lim = _limits(m)
            if name in tags:
                row, bound = tags[name]
                if lim != bound:
                    raise WrapError(
                        f"{bench} {rid}: {name} carries limits {lim} but the "
                        f"ratified '{row}' row requires {bound}"
                    )
            entry = {
                "name": name,
                "value": m["value"],
                "unit": m.get("unit"),
                "limits": lim,
                "status": "pass" if m["pass"] else "fail",
                "margin": _margin(m["value"], lim),
            }
            ms.append(entry)
            if lim:
                checked.append(f"{bench}:{c['corner_id']}:{name}")
        diag = []
        if c.get("solver_diagnostic"):
            diag.append({"severity": "error", "code": "solver_diagnostic",
                         "message": str(c["solver_diagnostic"])})
        corners.append({
            "corner_id": c["corner_id"],
            "process": c["process"],
            "supply_v": {"vvin": c["supply_v"]},
            "temperature_c": c["temperature_c"],
            "status": "pass" if c["pass"] else "fail",
            "measurements": ms,
            "diagnostics": diag,
        })
    missing = sorted(set(tags) - seen)
    if missing:
        raise WrapError(f"{bench} {rid}: ratified measurement(s) absent from the record: {missing}")

    rollup = []
    for name in dict.fromkeys(m["name"] for c in corners for m in c["measurements"]):
        pts = [(c["corner_id"], m) for c in corners for m in c["measurements"] if m["name"] == name]
        limited = [p for p in pts if p[1]["margin"] is not None]
        wc_id, wc = min(limited, key=lambda p: p[1]["margin"]) if limited else pts[0]
        entry = {
            "name": name,
            "unit": wc["unit"],
            "limits": wc["limits"],
            "status": "fail" if any(m["status"] == "fail" for _, m in pts) else "pass",
            "worst_case": {"corner_id": wc_id, "value": wc["value"], "margin": wc["margin"]},
        }
        if name in tags:
            entry["spec_row"] = tags[name][0]
        rollup.append(entry)

    n_fail = sum(1 for c in corners if c["status"] == "fail")
    n_pass = len(corners) - n_fail
    skipped = []
    if subset:
        skipped.append({
            "id": f"{bench}:corner-matrix",
            "reason": "pvt_subset: " + str(matrix.get("subset_reason") or "record ran fewer corners than its experiment declares"),
        })
    if n_fail:
        status = "fail"
    elif skipped:
        status = "pass_partial"
    else:
        status = "pass"

    declared = len(rollup)
    with_limits = sum(1 for m in rollup if m["limits"])
    return {
        "schema_version": 1,
        "netlist": snap.relative_to(REPO_ROOT).as_posix(),
        "status": status,
        "corner_count": len(corners),
        "passed": n_pass,
        "failed": n_fail,
        "errored": 0,
        "wrapper": WRAPPER,
        "source_record": {
            "bench": bench,
            "record_id": rid,
            "path": rec_path.relative_to(REPO_ROOT).as_posix(),
            "sha256": _sha(rec_path),
            "overall_pass": rec["overall_pass"],
            "matrix_is_subset": subset,
        },
        "environment": {
            "engine": "ngspice",
            "engine_version": rec["tools"].get("ngspice"),
            "pdk": rec["pdk"].get("pinned_commit"),
            "platform": rec["tools"].get("platform"),
        },
        "provenance": {
            "input": {
                "path": snap.relative_to(REPO_ROOT).as_posix(),
                "role": "netlist",
                "content_hash": _sha(snap),
            },
        },
        "metrics": {
            "sim__corner__count": len(corners),
            "sim__corner__passed_count": n_pass,
            "sim__corner__failed_count": n_fail,
            "sim__corner__errored_count": 0,
        },
        "coverage": {
            "schema_version": 1,
            "known": True,
            "checked": sorted(checked),
            "skipped": skipped,
            "inapplicable": [],
            "unknown": [],
            "nothing_checked": False,
            "nothing_checked_reasons": [],
            "measurements_declared": declared,
            "measurements_with_limits": with_limits,
        },
        "measurements": rollup,
        "corners": corners,
    }


def output_path(bench: str, rid: str) -> Path:
    return OUT_DIR / f"item5-{bench}-{rid}.sim.json"


def envelope_text(bench: str, rid: str) -> str:
    return json.dumps(build_envelope(bench, rid), indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    check = "--check" in argv
    rc = 0
    for bench, rid in RECORDS:
        out = output_path(bench, rid)
        rel = out.relative_to(REPO_ROOT)
        try:
            text = envelope_text(bench, rid)
        except WrapError as e:
            print(f"FATAL: {e}", file=sys.stderr)
            return 1
        if check:
            if not out.is_file():
                print(f"FATAL: {rel} not found -- run python3 signoff/make_item5_envelope.py", file=sys.stderr)
                rc = 1
            elif out.read_text() != text:
                print(f"FAIL: committed {rel} is not what make_item5_envelope.py would write", file=sys.stderr)
                rc = 1
            else:
                print(f"OK: {rel}")
            continue
        if out.exists():
            if out.read_text() == text:
                print(f"unchanged: {rel}")
                continue
            print(f"FATAL: {rel} exists with different content; evidence is append-only", file=sys.stderr)
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        print(f"wrote {rel} {_sha(out)}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
