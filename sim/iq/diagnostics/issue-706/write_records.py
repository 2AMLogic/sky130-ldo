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


def worker_pdk(legs):
    """Executed-worker PDK evidence from the committed klt reports of `legs`:
    (stamp texts, pdk_stamp_comparison statuses, models_lib_comparison statuses,
    n_reports). Read from the rows, never assumed from the submitter's pin."""
    stamps, cmp_, lib, n = set(), set(), set(), 0
    for lg in legs:
        for rp in sorted((HERE / "runs" / lg / "klt-out").glob("*/report.json")):
            rem = json.loads(rp.read_text())["environment"]["remote"]
            w = rem["worker_environment"]
            stamps.add(w["pdk"]["stamp_text"])
            cmp_.add(w["pdk_stamp_comparison"]["status"])
            lib.add(rem["models_lib_comparison"]["status"])
            n += 1
    return sorted(stamps), sorted(cmp_), sorted(lib), n


def pdk_line(bp, legs):
    stamps, cmp_, lib, n = worker_pdk(legs)
    return (f"submitter-resolved pin: sky130A @ open_pdks `{bp['pdk']['open_pdks_commit']}` "
            f"(matches `sim/pdk.json`: {bp['pdk']['matches_pin']}). **Executed worker PDK "
            f"(from the {n} committed klt reports of these legs)**: stamp "
            f"{', '.join('`' + x + '`' for x in stamps)}; "
            f"`pdk_stamp_comparison.status` = {', '.join(cmp_)} (the worker's PDK revision stamp "
            f"differs from the submitter's pin, so results may differ from a local run at the "
            f"pin); `models_lib_comparison.status` = {', '.join(lib)} (the model library the "
            f"deck loads compared equal). Both results are reported so the reader can judge "
            f"applicability to the production pin; this record does not claim the run executed "
            f"on the submitter's `{bp['pdk']['open_pdks_commit'][:8]}` revision.")


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
    res = s["iq"]["resolution"]
    pp = s["iq"]["paired"]
    fail_cuts = ", ".join(f"{c} {v:+.1f}" for c, v in
                          pp["base_failing_corner_deltas_full_load_ua"].items())
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
- **PDK**: {pdk_line(bp, ("iq-base", "iq-cand"))}
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

- **Measured failures (valid results)**: production DUT fails the strict bound at {len(s['iq']['base_fails'])} corners,
  all on the 3.63 V column at full load: {fails_b}. The rev2 candidate passes
  all {s['iq']['paired']['n_valid']['cand']} corners (production passes {s['iq']['paired']['n_valid']['base']}).
- **Resolution of the full-load figure (printed and solver reported separately)**: the full-load
  meas card prints the ~0.05 A supply current with 6 significant digits (e.g. `-5.00300e-02` A
  at ff_125c_3.63v), so the last printed digit is 1e-7 A = **{res['full_load_print_quantum_ua']} µA**; the manifest
  then subtracts the ideal 0.05 A load, which does not refine that resolution. Solver settings
  (ngspice defaults: reltol {res['solver_settings']['reltol']:g}, abstol {res['solver_settings']['abstol_a']:g} A,
  vntol {res['solver_settings']['vntol_v']:g} V; no override in the deck or `sim/spiceinit`) are a separate
  matter: {res['solver_note']}. The harness grade is kept as reported (PASS/FAIL columns above).
  Applied: production's worst corner is {wm['base']['corner']} at {wm['base']['margin_ua']:.3f} µA
  ({'an exceedance larger than' if wm['base']['exceeds_print_quantum'] else 'a margin within'} the print quantum). The candidate's worst corner is
  {wm['cand']['corner']} at full load, where the derived value is 29.999999999995 µA: the margin
  (~5e-12 µA) is far inside the {res['full_load_print_quantum_ua']} µA print quantum, so **strict-bound compliance is unresolved at this corner**; the
  PASS is a floating-point inequality on the harness grade, not evidence of margin, and no
  solver-resolved margin is claimed (no precision/tolerance comparison was run).
- **Where the cut is largest (joined by corner, `tables/iq_pair.csv`)**: per-corner full-load
  ΔIq spans {pp['delta_full_load_ua']['largest_cut'][0]:+.1f} µA ({pp['delta_full_load_ua']['largest_cut'][1]}, a corner production already passes)
  to {pp['delta_full_load_ua']['largest_increase'][0]:+.1f} µA ({pp['delta_full_load_ua']['largest_increase'][1]}). At production's
  five failing corners the cuts are {fail_cuts} µA, i.e. smaller than the largest cut
  and not the largest cuts overall.
- **Binding (bias/tail currents joined by corner, `tables/ir_spread.csv`)**: production I_R
  {pp['base_ir_set_50ma']['min'][0]*1e6:.2f}–{pp['base_ir_set_50ma']['max'][0]*1e6:.2f} µA and tail {pp['base_tail_i_set_50ma']['min'][0]*1e6:.2f}–{pp['base_tail_i_set_50ma']['max'][0]*1e6:.2f} µA
  both peak at {pp['base_ir_set_50ma']['max'][1]} (I_R) / {pp['base_tail_i_set_50ma']['max'][1]} (tail);
  rev2 I_R {pp['cand_ir_set_50ma']['min'][0]*1e6:.2f}–{pp['cand_ir_set_50ma']['max'][0]*1e6:.2f} µA peaks at {pp['cand_ir_set_50ma']['max'][1]}, tail
  {pp['cand_tail_i_set_50ma']['min'][0]*1e6:.2f}–{pp['cand_tail_i_set_50ma']['max'][0]*1e6:.2f} µA at {pp['cand_tail_i_set_50ma']['max'][1]}. The currents were measured on
  the clamp legs' 50 mA operating point. Production's failing corners are not where its
  bias peaks (sf 3.63 V); the Iq gain is the tail-current reduction at the 3.63 V column, not a
  match to the I_R peak.
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
    cp_ = dict(s["clamp"]["paired"])
    kmin, kmax = cp_["knee_change_min"], cp_["knee_change_max"]
    vr = lambda t: [float(r[f"{t}_vout_50ma_v"]) for r in rows if r[f"{t}_pass"] == "True"]
    cp_["base_v50"], cp_["cand_v50"] = (min(vr("base")), max(vr("base"))), (min(vr("cand")), max(vr("cand")))
    inv_c = "; ".join(f"{d['corner']} short {d['ilim_short_ma']:.1f} mA / knee {d['ilim_knee_ma']:.1f} mA"
                      for d in cp_["cand"]["solver_invalid"])
    ip = s["iq"]["paired"]
    ir_b = f"{ip['base_ir_set_50ma']['min'][0]*1e6:.2f}–{ip['base_ir_set_50ma']['max'][0]*1e6:.2f}"
    ir_c = f"{ip['cand_ir_set_50ma']['min'][0]*1e6:.2f}–{ip['cand_ir_set_50ma']['max'][0]*1e6:.2f}"
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
  `befb83fb` (**unmerged at campaign time**; main's batch backend had no current-limit entry then; #648 has since merged, 2026-11-22T21:20:53Z, so the graded backend path now exists on main and this record's local-evaluator grading is a campaign-time condition). One compatibility
  shim at the driver's call site (`blr._tokens = blr._EXPR.tokenize`; main removed `_tokens`
  after #648's branch point). The manifest's ten graded expressions travel verbatim as klt
  derived measurements; read-only extra cards (forced-VOUT dc curve at 0.375/0.75/1.125/1.5/
  1.625 V, CL_CMP node, I_R / tail / clamp-reference device currents) were appended after the
  adapter's own validation (#692's extra-card pattern).
- **Pairing provenance**: as the iq record; production base `db9f161a`, candidate
  `apply_candidate(raw, 2)` from PR #703 head `01dfd695` (verified, 0 invariant problems per
  leg; the candidate's one clamp change is XM_CLP's gate BIASP -> PBR). Evidence under
  `sim/iq/diagnostics/issue-706/runs/cl-*/` (request netlists + JSONs, per-corner logs).
- **PDK**: {pdk_line(bp, ("cl-base", "cl-cand"))}
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
  Validity from the `base_pass` / `cand_pass` columns: **{cp_['base']['n_valid']}/45 valid corners
  production, {cp_['cand']['n_valid']}/45 rev2**; paired statistics below use the {cp_['n_pairs_both_valid']} corners
  where both runs passed the gate. Both rev2 diagnostic keys are new relative to production
  (production's four are Vin_max-class; rev2's `fs_-40c_3.63v` and `ff_27c_3.30v` are not in
  production's list). Their retained values are NOT all in the 160–195 mA family:
  {inv_c}. They are listed, not counted valid.
- **Non-engagement at or below 50 mA**: both DUTs keep vout_50ma inside 1.764–1.836 V at all
  valid corners (production {cp_['base_v50'][0]:.4f}–{cp_['base_v50'][1]:.4f} V; rev2 {cp_['cand_v50'][0]:.4f}–{cp_['cand_v50'][1]:.4f} V) and the minimum
  forced-output knee (current sampled at Vout = 1.75 V; a proxy for engagement current, not a
  measured engagement point) is {cp_['cand']['ilim_knee_ma']['min'][0]:.1f} mA (rev2, {cp_['cand']['ilim_knee_ma']['min'][1]}) vs
  {cp_['base']['ilim_knee_ma']['min'][0]:.1f} mA (production, {cp_['base']['ilim_knee_ma']['min'][1]}) over valid corners.
- **Window (TBD per spec — reported, not graded)**: valid-corner ilim_short
  {cp_['cand']['ilim_short_ma']['min'][0]:.1f}–{cp_['cand']['ilim_short_ma']['max'][0]:.1f} mA (rev2) vs {cp_['base']['ilim_short_ma']['min'][0]:.1f}–{cp_['base']['ilim_short_ma']['max'][0]:.1f} mA (production);
  short current sustained for the full 2 ms hold at every corner including Vin_max; peak ripple
  on a valid corner {cp_['base']['ishort_ripple_pct']['max'][0]:.6f} % (production, {cp_['base']['ishort_ripple_pct']['max'][1]}) and
  {cp_['cand']['ishort_ripple_pct']['max'][0]:.6f} % (rev2, {cp_['cand']['ishort_ripple_pct']['max'][1]}).
- **The clamp moves substantially across PVT (paired, per corner)**: rev2/production − 1 on the
  knee current spans **{kmin['knee_pct']:+.1f} %** ({kmin['corner']}: {kmin['knee_base_ma']:.3f} → {kmin['knee_cand_ma']:.3f} mA;
  short {kmin['short_pct']:+.1f} %) to **{kmax['knee_pct']:+.1f} %** ({kmax['corner']}: {kmax['knee_base_ma']:.3f} → {kmax['knee_cand_ma']:.3f} mA;
  short {kmax['short_pct']:+.1f} %); the knee falls at {cp_['n_knee_decrease']} and rises at {cp_['n_knee_increase']} of the
  {cp_['n_pairs_both_valid']} paired corners. This is **not** a uniform 2–3 % shift: the overlay's clamp-visible change
  (XM_CLP gate BIASP → PBR) moves the trip with the measured bias currents
  (`tables/ir_spread.csv`: I_R {ir_b} µA production vs {ir_c} µA rev2), and the adoption
  trade-off should be read from those paired per-corner changes. The window stays TBD.
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
