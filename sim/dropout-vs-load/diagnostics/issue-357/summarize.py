#!/usr/bin/env python3
"""Issue #357 summary tables from the append-only runs/ directory (no simulation).

Grades every bench run against its UNCHANGED manifest bounds (as recorded by
probe.py from corner-run.py's own grade_bounds) and classifies each candidate
measurement against the paired baseline at the same supply:

  pass          both pass
  pre-existing  baseline fails AND candidate fails (not attributable to the candidate)
  REGRESSION    baseline passes, candidate fails
  fixed         baseline fails, candidate passes
  INVALID       either run is invalid (nonzero exit, solver diagnostic, missing
                measurement) -- never a pass, whatever the numbers say

usage: summarize.py            (prints to stdout; commands.sh redirects to summary.txt)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze as an  # noqa: E402

RUNS = HERE / "runs"
T_HOLD, T_REEN = "90", "165"
PASS_OFF_A = 1.0  # uA, declared (README section 3)


def load(rid):
    f = RUNS / rid / "result.json"
    return json.loads(f.read_text()) if f.is_file() else None


def bench_valid(r):
    """(valid, reasons) for a manifest-bench run."""
    if r is None:
        return False, ["run missing"]
    why = []
    if r.get("ngspice_exit") != 0:
        why.append(f"ngspice exit {r.get('ngspice_exit')}")
    if r.get("solver_diagnostic"):
        why.append("solver diagnostic: " + r["solver_diagnostic"])
    if r.get("missing_measurements"):
        why.append("missing: " + ", ".join(r["missing_measurements"]))
    return not why, why


def classify(base_pass, cand_pass, base_valid, cand_valid):
    if not (base_valid and cand_valid):
        return "INVALID"
    if base_pass and cand_pass:
        return "pass"
    if not base_pass and not cand_pass:
        return "pre-existing"
    return "REGRESSION" if base_pass else "fixed"


def bench_table(bench, supply, base_id, cand_ids):
    b = load(base_id)
    bv, bwhy = bench_valid(b)
    L = [f"### {bench} @ tt / 27 C / {supply} V   base={base_id}" + "".join(f"  {c}" for c in cand_ids)]
    L.append(f"  base valid={bv} {'; '.join(bwhy)}")
    cands = []
    for cid in cand_ids:
        c = load(cid)
        cv, cwhy = bench_valid(c)
        cands.append((cid, c, cv))
        L.append(f"  {cid} valid={cv} {'; '.join(cwhy)}")
    names = list((b or {}).get("grading_vs_manifest_bounds", {}).keys())
    hdr = f"  {'measurement':28s} {'bounds':>16s} {'base':>12s}" + "".join(f" {cid[-12:]:>12s} {'class':>12s}" for cid, _c, _v in cands)
    L.append(hdr)
    for n in names:
        g = b["grading_vs_manifest_bounds"][n]
        bounds = f"[{g['min']}, {g['max']}]"
        row = f"  {n:28s} {bounds:>16s} {fmtv(g['value'], g['pass'] and bv):>12s}"
        for cid, c, cv in cands:
            cg = c["grading_vs_manifest_bounds"][n]
            cls = classify(g["pass"], cg["pass"], bv, cv)
            row += f" {fmtv(cg['value'], cg['pass'] and cv):>12s} {cls:>12s}"
        L.append(row)
    return L


def fmtv(v, ok):
    if v is None:
        return "missing"
    return f"{v:.6g}{'' if ok else '*'}"


def thermal_state(r):
    if r is None or "thermal" not in r:
        return None
    th = r["thermal"]
    if th.get("invalid_reason"):
        return {"valid": False, "invalid_reason": th["invalid_reason"]}
    ok = r["ngspice_exit"] == 0 and not r["solver_diagnostic"] and not th["nonfinite"]
    tripped_end = th["after_en_reenable_tripped"]
    return {"valid": ok, "forced": th["forced_tripped"], "hold": th["hold_tripped"],
            "end": tripped_end,
            "pass_off_90": (th["ipass_ua"][T_HOLD] < PASS_OFF_A) if th["hold_tripped"] else None,
            "pass_off_165": (th["ipass_ua"][T_REEN] < PASS_OFF_A) if tripped_end else None,
            "ipass_165_ua": th["ipass_ua"][T_REEN]}


def thermal_table():
    L = ["### thermal two-state (run_hysteresis.py stimulus); electrical tt, imposed device temperature",
         "  state = forced/hold/end-of-run tripped (T=tripped, u=untripped); pass-off = |Id(M_PASS)| < 1 uA "
         "while tripped (declared at 90 us; supplementary at 165 us, see README)",
         f"  {'supply':>6s} {'T[C]':>5s} {'scenario':>9s} {'base':>9s} {'cand_r0':>9s} {'cand_r1':>9s}  "
         f"{'same?':>6s}  pass-off@165 base/r0/r1   Id_pass@165 [uA] base/r0/r1"]
    allsame = True
    for sup in ("3p3", "2p1"):
        for temp, scen in (("027", "cold"), ("150", "coldexc"), ("150", "hot"), ("166", "coldexc"),
                           ("166", "hot"), ("185", "coldexc"), ("185", "hot"), ("185", "en")):
            ids = [f"th_base_{sup}_{temp}_{scen}", f"th_cand_r0_{sup}_{temp}_{scen}", f"th_cand_r1_{sup}_{temp}_{scen}"]
            st = [thermal_state(load(i)) for i in ids]

            def s(x):
                if x is None:
                    return "missing"
                if not x["valid"]:
                    return "INVALID"
                return "".join("T" if x[k] else "u" for k in ("forced", "hold", "end"))
            tags = [s(x) for x in st]
            same = len(set(tags)) == 1 and "INVALID" not in tags and "missing" not in tags
            allsame &= same
            po = "/".join("-" if x is None or x["pass_off_165"] is None else ("ok" if x["pass_off_165"] else "NO") for x in st)
            ip = "/".join("n/a" if x is None else f"{x['ipass_165_ua']:.3g}" for x in st)
            L.append(f"  {sup.replace('p', '.'):>6s} {int(temp):5d} {scen:>9s} {tags[0]:>9s} {tags[1]:>9s} {tags[2]:>9s}  "
                     f"{'yes' if same else 'NO':>6s}  {po:>24s}   {ip}")
    L.append(f"  all candidate states identical to the paired baseline: {allsame}")
    return L


def dropout_table():
    L = ["### dropout (dropout-vs-load manifest deck, tt / 27 C, VIN 3.3 V -> 1.17 V ramp, 50 mA)"]
    r = load("d00_replay339_probe0")
    if r:
        L.append(f"  d00_replay339_probe0 (#339 deck verbatim, this host's ngspice): valid={r['valid']} "
                 f"dropout={r['dropout_v']!r} V vs #339 recorded {r['dropout_v_339_recorded']!r} "
                 f"(delta {r['delta_vs_339_v']!r}); data sha256 identical to #339: "
                 f"{r['data_sha256'] == r['data_sha256_339_recorded']}")
    L.append(f"  {'run':18s} {'variant':8s} {'valid':6s} {'dropout_v[V]':>13s} {'VINx[V]':>9s} {'<0.300?':>8s}  reasons")
    for rid in ("d01_base", "d01b_base", "d03_base_rep", "d02_cand_r0", "d04_cand_r0_rep", "d05_cand_r1", "d06_cand_r1_rep"):
        if not (RUNS / rid).is_dir():
            continue
        a = an.analyze(RUNS / rid)
        g = a["spec_grade"]
        L.append(f"  {rid:18s} {a['variant']:8s} {str(a['valid']):6s} {an._f(a['dropout_v']):>13s} "
                 f"{an._f(a['vin_cross_v'], '.5f'):>9s} {('PASS' if g['pass'] else 'FAIL') if g else 'INVALID':>8s}  "
                 f"{'; '.join(a['reasons'])}")
    for x, y in (("d01b_base", "d03_base_rep"), ("d02_cand_r0", "d04_cand_r0_rep"), ("d05_cand_r1", "d06_cand_r1_rep")):
        ok, msg = an.repeat_check(an.analyze(RUNS / x), an.analyze(RUNS / y))
        L.append("  " + msg)
    return L


def main():
    out = ["# Issue #357 summary (generated by summarize.py from runs/; tt / 27 C electrical only)", ""]
    out += dropout_table() + [""]
    for bench, pre in (("current-limit", "cl"), ("iq", "iq"), ("enable-shutdown", "en")):
        for sup in ("3p3", "2p1"):
            base = f"{pre}_base_{sup}"
            if load(base) is None:
                continue
            cands = [c for c in (f"{pre}_cand_r0_{sup}", f"{pre}_cand_r1_{sup}") if load(c) is not None]
            out += bench_table(bench, sup.replace("p", "."), base, cands) + [""]
    out += thermal_table()
    out += ["", "('*' marks a value that fails its manifest bound or comes from an invalid run;"
            " 2.10 V is outside the ratified 2.97-3.63 V input range -- graded against the same"
            " manifest bounds for the paired comparison only, not as a spec claim.)"]
    print("\n".join(out))


if __name__ == "__main__":
    main()
