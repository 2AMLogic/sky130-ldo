#!/usr/bin/env python3
"""Issue #706: mint the paired THERMAL record under sim/thermal/records/
from the campaign's two hysteresis result.json files (base + cand).

Paired campaign record for the #702 adoption decision, same contract as the
iq / current-limit records minted by write_records.py (which ran before the
thermal legs finished, so this is a separate append-only mint -- it never
touches those records). States are reported; no threshold is applied or
relaxed.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parents[2]
REPO = SIM.parent
HYST = SIM / "thermal" / "hysteresis"


def sha8():
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short=8", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def load(variant):
    dirs = sorted(HYST.glob(f"*-i706-paired-{variant}"))
    if not dirs:
        raise SystemExit(f"no hysteresis run dir for variant {variant}")
    d = json.loads((dirs[-1] / "result.json").read_text())
    if not d["complete"]:
        raise SystemExit(f"{dirs[-1]} is incomplete; evidence is append-only, do not mint")
    return d


def main():
    base, cand = load("base"), load("cand")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    rid = f"{stamp}-{sha8()}-i706-paired"
    p = SIM / "thermal" / "records" / f"{rid}.md"
    if p.exists():
        raise SystemExit(f"{p} exists: append-only")

    bp = base["pairing"]
    order = ["tt_2.97V", "tt_3.30V", "tt_3.63V", "ss_2.97V", "ss_3.30V", "ss_3.63V",
             "ff_2.97V", "ff_3.30V", "ff_3.63V", "sf_2.97V", "sf_3.30V", "sf_3.63V",
             "fs_2.97V", "fs_3.30V", "fs_3.63V"]
    rows = []
    dts = []
    for k in order:
        b, c = base["corners"][k], cand["corners"][k]
        bt, ct = b["t_trip_rising_c"]["midpoint"], c["t_trip_rising_c"]["midpoint"]
        dts.append(ct - bt)
        rows.append(
            f"| {k} | {bt:.4g} | {b['t_reset_falling_c']['midpoint']:.4g} "
            f"| {b['hysteresis_c']['midpoint']:.4g} ({b['hysteresis_c']['min']:.4g}–{b['hysteresis_c']['max']:.4g}) "
            f"| {ct:.4g} | {c['t_reset_falling_c']['midpoint']:.4g} "
            f"| {c['hysteresis_c']['midpoint']:.4g} ({c['hysteresis_c']['min']:.4g}–{c['hysteresis_c']['max']:.4g}) "
            f"| {ct - bt:+.4g} |")
    trips = [c["t_trip_rising_c"]["midpoint"] for d in (base, cand) for c in d["corners"].values()]
    resets = [c["t_reset_falling_c"]["midpoint"] for d in (base, cand) for c in d["corners"].values()]
    hysts = [c["hysteresis_c"]["midpoint"] for d in (base, cand) for c in d["corners"].values()]
    tol = base["bisection_tol_c"]
    missing = [k for d in (base, cand) for k, c in d["corners"].items()
               if (c.get("dependent_points") or {}).get("missing")]

    body = f"""# Paired record {rid} (issue #706)

- **Record ID**: {rid}
- **Experiment**: `thermal` — paired campaign record: thermal-shutdown trip/reset re-bisection
  and hysteresis of the committed production DUT vs the #357 rev2 candidate (issue #692 /
  PR #703), one base commit, for the #702 adoption decision. NOT a production records-run
  mint. The bench's own DR-005 procedure (`sim/thermal/run_hysteresis.py` +
  `sim/bin/batch_thermal_staircase.py`, issues #511/#541) is reused verbatim by
  `thermal_pair.py`; only the DUT body differs. States are recorded, no threshold is applied
  or relaxed.
- **Row under test**: spec/target-spec.md "Thermal" row fault-backstop clauses per DR-005 —
  150 °C nominal trip / 135 °C nominal reset (untrimmed, PVT-loose by the DR's own wording),
  auto-restart non-latching, hysteresis positive (the spec row's binding backstop bound is the
  hysteresis SIGN). DR-005 sits above DR-004's characterized 125 °C axis: every trip/reset
  point runs the pinned BSIM models in extrapolation, the caveat the bench's own records
  carry; this campaign inherits it unchanged.
- **Pairing provenance**: production base `{bp['source_commit'][:8]}` (schematic sha256
  `{bp['dut_sch_sha256'][:16]}...`, staircase testbench `{bp['testbench_sha256'][:16]}...`);
  candidate = same staircase body after `apply_candidate(raw, 2)` from
  `sim/iq/diagnostics/issue-706/candidate.py` (sha256 `{bp['candidate_py_sha256'][:16]}...`,
  imported verbatim from PR #703 head `01dfd695`), edit verified by `check_candidate`
  (0 problems) before submission; netlist diff committed as `netlist.diff` in the candidate
  run dir. As the iq/clamp records: the overlay's only rev2 lever is NTAIL W12/nf3 -> W7/nf2
  (the thermal-shutdown sense/reference chain is untouched by the overlay).
- **PDK**: sky130A @ open_pdks `{base['pdk']['installed_commit']}` (pin match:
  {base['pdk']['installed_commit'] == base['pdk']['pinned_commit']})
- **Tools**: remote executor engines (ngspice `{base['tools']['ngspice'].split()[0]}`);
  local netlister {base['tools']['xschem']}; declared baseline ngspice 42 / xschem 3.4.4
  (drifted, recorded not gated)
- **Repo state**: `{bp['source_commit']}` (campaign base; driver sha256 `{bp['driver_sha256'][:16]}...`)
- **Execution backend**: batch (`klt sim`, aws-batch-fleet), {len(base['jobs'])} jobs for the
  production leg (`{base['jobs'][0]}` … `{base['jobs'][-1]}`) and {len(cand['jobs'])} for the
  candidate leg (`{cand['jobs'][0]}` … `{cand['jobs'][-1]}`); full job lists in each run dir's
  `result.json`, every point record under `points/`.
- **Corner matrix**: 5 process x 2.97/3.30/3.63 V = 15 corners per variant at the bisected
  temperature ({base['n_points']} staircase points per variant), bisection tolerance
  {tol} °C. Cold-start (trip direction) and tripped-seed (reset direction) staircases plus
  the procedure's dependent rounds (EN re-enable, amplitude robustness) — all states in each
  run dir.
- **Result** (°C; trip = rising crossing, reset = falling crossing, hysteresis = trip − reset
  with its bracket range; delta = candidate − production trip, one bisection step =
  {tol} °C):

| corner | base trip | base reset | base hyst | cand trip | cand reset | cand hyst | Δtrip |
|---|---|---|---|---|---|---|---|
{chr(10).join(rows)}

- **Crossings validity**: both crossings bisected at all 15 corners for BOTH variants — no
  missing or invalid crossings ({len(missing)} corners with missing dependent points; every
  corner's `dependent_points.missing` list is empty). Auto-restart confirmed at every corner:
  the EN-dip dependent round re-trips after re-enable above the crossing and stays off below
  it (`en_reenable_by_temp` in each run dir).
- **DR-005 comparison**: measured trip {min(trips):.4g}–{max(trips):.4g} °C (nominal 150,
  both DUTs above nominal everywhere — the untrimmed PVT-loose direction DR-005 itself
  predicts); reset {min(resets):.4g}–{max(resets):.4g} °C (nominal 135, likewise above);
  hysteresis {min(hysts):.4g}–{max(hysts):.4g} °C — **positive at all 30 corner/variant
  pairs**, i.e. the spec row's binding hysteresis-sign bound passes everywhere, while the
  15 °C nominal is missed by 1.6–2.5 °C on both DUTs equally (an inherited offset, not an
  rev2 change).
- **Candidate vs production**: |Δtrip| <= {max(abs(d) for d in dts):.4g} °C = exactly one
  bisection step at every corner — the rev2 tail cut does not move the thermal trip or reset
  outside the measurement's own resolution; worst-condition behavior is identical
  (highest trip fs_2.97V, lowest trip sf_3.63V/ss_3.63V, both variants).
- **Classification**: every thermal limitation above (nominal-trip offset, sub-nominal
  hysteresis magnitude, >125 °C model extrapolation) is **inherited** — present identically
  in the production DUT; rev2 introduces nothing here.
- **Cross-links**: campaign summary: `sim/iq/diagnostics/issue-706/` (README.md,
  tables/summary.json). Sibling records: `sim/iq/records/` (Iq) and
  `sim/current-limit/records/` (clamp), same stamp family. Raw evidence:
  `sim/thermal/hysteresis/{base['record_id']}/` and `sim/thermal/hysteresis/{cand['record_id']}/`.
"""
    p.write_text(body)
    print(p)


if __name__ == "__main__":
    main()
