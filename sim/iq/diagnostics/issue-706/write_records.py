#!/usr/bin/env python3
"""Issue #706: mint the paired records under sim/iq/records/ and
sim/current-limit/records/ from the campaign legs' leg.json + tables/.

These are PAIRED CAMPAIGN records (candidate-vs-production diagnostics for the
#702 adoption decision), not single-DUT harness records: the iq legs were
graded by the harness's own endpoint normalizer (identical bounds and
solver-diagnostic gate), the clamp legs by the local evaluator over the same
manifest expressions and bounds (the #648 chained adapter is unmerged, so the
graded batch backend path does not exist on main for current-limit). The
window row stays TBD per spec: values are reported, never graded against an
invented window. Append-only: a fresh stamp per invocation, never overwriting.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parents[2]
REPO = SIM.parent
sys_stamp = None


def sha8():
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short=8", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def leg(name):
    return json.loads((HERE / "runs" / name / "leg.json").read_text())


def prov(leg_name):
    d = leg(leg_name)
    p = d["provenance"]
    return d, p


def exec_lines(d):
    out = []
    for r in d["execution"]["requests"]:
        out.append(
            f"  - request `{r['key']}`: job `{r.get('job_id')}` (provider=`{r.get('provider')}`, "
            f"engine `{r.get('engine_version')}`)")
    return "\n".join(out)


def iq_record() -> str:
    base, bp = prov("iq-base")
    cand, cp = prov("iq-cand")
    s = json.loads((HERE / "tables" / "summary.json").read_text())
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    rid = f"{stamp}-{sha8()}-i706-paired"
    rows = []
    for rb in base["results"]:
        rc = next(x for x in cand["results"] if x["corner_id"] == rb["corner_id"])
        def g(r, n):
            return next((m["value"] for m in r["measurements"] if m["name"] == n), None)
        def fmt(v, nd=4):
            return "n/a" if v is None else f"{v:.{nd}f}"
        rows.append(
            f"| {rb['corner_id']} | {fmt(g(rb,'iq_no_load_ua'))} | {fmt(g(rb,'iq_full_load_ua'))} "
            f"| {'PASS' if rb['pass'] else 'FAIL'} | {fmt(g(rc,'iq_no_load_ua'))} "
            f"| {fmt(g(rc,'iq_full_load_ua'))} | {'PASS' if rc['pass'] else 'FAIL'} |")
    fails_b = ", ".join(s["iq"]["base_fails"]) or "none"
    wm = s["iq"]["worst_margin"]
    return f"""# Paired record {rid} (issue #706)

- **Record ID**: {rid}
- **Experiment**: `iq` — paired campaign record: quiescent current of the committed production
  DUT vs the #357 rev2 candidate (issue #692 / PR #703), one base commit, for the #702 adoption
  decision. NOT a production records-run mint: the candidate netlist exists only as the
  `apply_candidate(raw, 2)` overlay of this campaign; no production file changes.
- **Row under test**: spec/target-spec.md "Iq (excl. load current)" (< 30 µA strict at no load
  and 50 mA full load; DR-009 'proposed'), graded by the harness's own iq endpoint adapter and
  bounds, identical to a records run (`normalize_endpoint_response` + `finalize_endpoint_results`,
  including the #171 solver-diagnostic gate and the #133 regulation gate).
- **Pairing provenance**: production base `db9f161a` (schematic sha256
  `{bp['dut_sch_sha256'][:16]}...`, testbench `{bp['testbench_sha256'][:16]}...`);
  candidate = same netlist after `apply_candidate(raw, 2)` from
  `sim/iq/diagnostics/issue-706/candidate.py` (sha256 `{cp['candidate_py_sha256'][:16]}...`,
  imported verbatim from PR #703 head `01dfd695`), edit verified by `check_candidate`
  (0 problems, every leg). The overlay's only rev2 lever is NTAIL W12/nf3 -> W7/nf2; the
  committed compensation parts it preserves are C_COMP = 150 p and XR_CZ = res_xhigh_po
  W=0.42 L=52 (the #691 shelf). Both legs' request netlists, diffs and per-corner engine logs
  are committed under `sim/iq/diagnostics/issue-706/runs/`.
- **PDK**: sky130A @ open_pdks `{bp['pdk']['open_pdks_commit']}` (pin match: {bp['pdk']['matches_pin']})
- **Tools**: remote executor engines per job below; local netlister {bp['tools']['xschem']};
  declared baseline ngspice 42 / xschem 3.4.4 (drifted, recorded not gated)
- **Repo state**: `{bp['source_commit']}`
- **Execution backend**: batch (`klt sim`, aws-batch-fleet), 6 requests per variant
  (one per supply x endpoint, 15 corners each):
{exec_lines(base)}
{exec_lines(cand)}
- **Corner matrix**: 5 process x -40/27/125 C x 2.97/3.30/3.63 V = 45 points per variant,
  full matrix, no subset.
- **Result** (Iq in µA; harness-graded, strict < 30 µA at BOTH loads; raw supply/load currents
  in A are preserved in `sim/iq/diagnostics/issue-706/tables/iq_pair.csv` and each leg's
  committed `klt-out/*/response.json`):

| corner | base no-load | base full-load | base | cand no-load | cand full-load | cand |
|---|---|---|---|---|---|---|
{chr(10).join(rows)}

- **Measured failures (valid results)**: production DUT fails the strict bound at 5 corners,
  all on the 3.63 V column at full load: {fails_b} (30.2–31.3 µA). The rev2 candidate passes
  all 45 corners.
- **Margin resolution at the 30 µA bound**: {s['iq']['resolution_note']}. Applied: production's
  worst corner is ff_-40c_3.63v at {wm['base']['margin_ua']:.3f} µA (a resolved EXCEEDANCE).
  The candidate's worst corner is ff_125c_3.63v at full load, where the raw card reads
  `-0.05003` A (6 significant digits) and the derived value is 29.999999999995 µA: the
  measurement coincides with the bound at its print resolution and the ~0.03 µA solver band
  straddles it, so **positive margin is NOT resolved** there — the strict-bound PASS is a
  floating-point inequality, not evidence of margin (no margin is inferred from the last
  printed digit).
- **Binding**: the candidate's Iq gain tracks its tail-current cut
  (NTAIL 2.8x of NBR; tail 1.36–2.37 µA over PVT vs the production tail's 2.40–4.06 µA,
  measured on the clamp legs' 50 mA operating point at the same corner keys — see
  `tables/ir_spread.csv`); production's worst Iq corners are exactly the corners where its
  VIN-scaled bias current peaks (3.63 V column).
- **Cross-links**: campaign summary and tables: `sim/iq/diagnostics/issue-706/`
  (README.md, tables/). Thermal and clamp legs of the same campaign: their own records.
"""


def clamp_record() -> str:
    base, bp = prov("cl-base")
    cand, cp = prov("cl-cand")
    s = json.loads((HERE / "tables" / "summary.json").read_text())
    rows = list(__import__("csv").DictReader((HERE / "tables" / "clamp_pair.csv").open()))
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    rid = f"{stamp}-{sha8()}-i706-paired"
    lines = []
    for r in rows:
        def f(k, nd=1):
            return "n/a" if not r.get(k) else f"{float(r[k]):.{nd}f}"
        db = "DIAG" if r.get("base_solver_diag") else ("PASS" if r.get("base_pass") == "True" else "FAIL")
        dc = "DIAG" if r.get("cand_solver_diag") else ("PASS" if r.get("cand_pass") == "True" else "FAIL")
        lines.append(f"| {r['corner']} | {f('base_vout_50ma_v',3)} | {f('base_ilim_short_ma')} | "
                     f"{f('base_ilim_knee_ma')} | {f('base_ishort_sustained_ma')} | {db} | "
                     f"{f('cand_vout_50ma_v',3)} | {f('cand_ilim_short_ma')} | "
                     f"{f('cand_ilim_knee_ma')} | {f('cand_ishort_sustained_ma')} | {dc} |")
    diag_b = "\n".join(f"  - {c}: {d}" for c, d in s["clamp"]["solver_diag_base"]) or "  - none"
    diag_c = "\n".join(f"  - {c}: {d}" for c, d in s["clamp"]["solver_diag_cand"]) or "  - none"
    return f"""# Paired record {rid} (issue #706)

- **Record ID**: {rid}
- **Experiment**: `current-limit` — paired campaign record: clamp engagement/knee/short of the
  committed production DUT vs the #357 rev2 candidate (issue #692 / PR #703), one base commit,
  for the #702 adoption decision. NOT a production records-run mint.
- **Row under test**: spec/target-spec.md "Current limit" row (constant-current clamp, window
  **TBD over PVT**; never engages for I_load <= 50 mA; survives continuous Vout = 0 short at
  Vin_max). Per the row and the issue: the window clauses are REPORTED, never graded against an
  invented window; the numeric clauses (ilim_short/ilim_knee > 50 mA, vout_50ma inside the
  ratified 1.764–1.836 V Output window, ishort ripple < 100 %) are evaluated with the manifest's
  own bounds by this campaign's local grader (same expressions, same `grade_bounds`), plus the
  #171 solver-diagnostic gate.
- **Batch adapter disclosure**: the three chained legs ran as ONE three-step `analysis_steps[]`
  request per supply through `batch_current_limit.py`, imported VERBATIM from PR #648 head
  `befb83fb` (**unmerged**; main's batch backend has no current-limit entry). One compatibility
  shim at the driver's call site (`blr._tokens = blr._EXPR.tokenize`; main removed `_tokens`
  after #648's branch point). The manifest's ten graded expressions travel verbatim as klt
  derived measurements; read-only extra cards (forced-VOUT dc curve at 0.375/0.75/1.125/1.5/
  1.625 V, CL_CMP node, I_R / tail / clamp-reference device currents) were appended after the
  adapter's own validation (#692's extra-card pattern).
- **Pairing provenance**: as the iq record; production base `db9f161a`, candidate
  `apply_candidate(raw, 2)` from PR #703 head `01dfd695` (verified, 0 invariant problems per
  leg; the candidate's one clamp change is XM_CLP's gate BIASP -> PBR). Evidence under
  `sim/iq/diagnostics/issue-706/runs/cl-*/` (request netlists + JSONs, per-corner logs).
- **PDK**: sky130A @ open_pdks `{bp['pdk']['open_pdks_commit']}` (pin match: {bp['pdk']['matches_pin']})
- **Tools / repo state**: engines per job below; netlister {bp['tools']['xschem']}; `{bp['source_commit']}`
- **Execution backend**: batch (`klt sim`, aws-batch-fleet), 3 chained requests per variant
  (one per supply, 15 corners each):
{exec_lines(base)}
{exec_lines(cand)}
- **Corner matrix**: 45 points per variant, full matrix. Vin_max (3.63 V) column included —
  the short is applied and HELD 2 ms per the bench's own leg 3 at every corner.
- **Result** (I_lim in mA; vout_50ma in V; DIAG = solver-diagnostic corner, reported separately
  per the #171 gate — its measured values are retained in the tables but do not count as
  harness-clean):

| corner | base v50 | base short | base knee | base ishort | base | cand v50 | cand short | cand knee | cand ishort | cand |
|---|---|---|---|---|---|---|---|---|---|---|
{chr(10).join(lines)}

- **Solver-invalid corners (reported separately, not folded into pass/fail)**:
  - production (4, all Vin_max — reproducing #647 exactly):
{diag_b}
  - rev2 candidate (2):
{diag_c}
  Every solver-invalid corner still returned healthy measured values (ilim_short 160–195 mA);
  the failures are the #171 gate working as designed, not out-of-family measurements.
- **Non-engagement at or below 50 mA**: both DUTs keep vout_50ma inside 1.764–1.836 V at all
  45 corners (production 1.7978–1.7991 V; rev2 1.8007–1.8043 V) and the minimum forced-output
  knee current is 71.8 mA (rev2; 74.6 mA production) — the clamp never engages for I_load <=
  50 mA at any PVT corner, with >= 21.8 mA of headroom to the knee.
- **Window (TBD per spec — reported, not graded)**: ilim_short 94.5–228.9 mA (rev2) vs
  97.7–231.7 mA (production) over PVT; short current sustained for the full 2 ms hold at every
  corner including Vin_max; ripple < 0.1 % everywhere. The rev2 clamp trip sits ~2–3 % below
  production's at each corner (the overlay deliberately preserves, not re-targets, the 3.3 V
  trip point).
- **Cross-links**: campaign summary and tables: `sim/iq/diagnostics/issue-706/`
  (README.md, tables/clamp_pair.csv, tables/ir_spread.csv).
"""


def main():
    stamp = dt.datetime.now(dt.timezone.utc)
    iq = SIM / "iq" / "records"
    cl = SIM / "current-limit" / "records"
    p1 = iq / f"{stamp:%Y%m%d-%H%M%S}-{sha8()}-i706-paired.md"
    p2 = cl / f"{stamp:%Y%m%d-%H%M%S}-{sha8()}-i706-paired.md"
    for p in (p1, p2):
        if p.exists():
            raise SystemExit(f"{p} exists: append-only")
    p1.write_text(iq_record())
    p2.write_text(clamp_record())
    print(p1)
    print(p2)


if __name__ == "__main__":
    main()
