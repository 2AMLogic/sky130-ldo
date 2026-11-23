#!/usr/bin/env python3
"""Issue #706 paired analysis: iq + clamp legs -> tables + verdict data.

Reads runs/{iq-base,iq-cand,cl-base,cl-cand}/leg.json (graded results) and the
committed klt-out response.json files (raw card values), and writes:

  tables/iq_pair.csv     45 rows: raw + graded Iq, both DUTs, per corner
  tables/clamp_pair.csv  45 rows: clamp metrics, both DUTs, per corner
  tables/ir_spread.csv   45 rows: I_R / tail / clamp-reference currents
  tables/summary.json    worst conditions, inherited/introduced classification,
                         resolution statements, solver-invalid lists

PDK-free, standard library only. Thermal pairs are summarized from the two
hysteresis result.json files by the same script (--thermal).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
TABLES = HERE / "tables"
PROCS = ["tt", "ss", "ff", "sf", "fs"]
TEMPS = [-40.0, 27.0, 125.0]
VSUPS = [2.97, 3.30, 3.63]
# Resolution of the graded Iq numbers. The full-load figure is the supply
# current at a ~0.05 A load: the meas card prints it with 6 significant digits
# (e.g. -5.00300e-02 A), so the last printed digit is 1e-7 A = 0.1 uA, and the
# manifest then subtracts the ideal 0.05 A load. Subtracting an exact constant
# does not improve the resolution: the derived uA value is only known to the
# print quantum of the raw card, i.e. 0.1 uA (not 1e-10 A). The no-load card is
# ~1.5e-5 A at 6 digits (~1e-11 A). The solver settings (ngspice defaults,
# reltol 1e-3, abstol 1e-12 A, vntol 1e-6 V; no override in the deck or
# sim/spiceinit) are reported separately: a convergence setting is NOT an error
# bound on the difference of two near-equal currents, and this campaign ran no
# precision/tolerance comparison, so no margin is called solver-resolved.
FULL_LOAD_PRINT_QUANTUM_UA = 0.1
IQ_RESOLUTION_UA = FULL_LOAD_PRINT_QUANTUM_UA


def corner_key(proc, temp, vsup):
    return f"{proc}_{int(temp)}c_{vsup:.2f}v"


def load_leg(leg):
    d = json.loads((RUNS / leg / "leg.json").read_text())
    by = {r["corner_id"]: r for r in d["results"]}
    jobs = [r.get("job_id") for r in d["execution"]["requests"]]
    return d, by, jobs


def raw_cards(leg):
    """{corner_id: {card: value}} from the leg's committed responses (cards of
    every request at that corner -- both iq endpoints -- are merged)."""
    out = {}
    for resp in sorted((RUNS / leg / "klt-out").glob("*/response.json")):
        d = json.loads(resp.read_text())
        for rc in d.get("corners", []):
            if not isinstance(rc, dict) or not isinstance(rc.get("process"), str):
                continue
            cid = corner_key(rc["process"], float(rc["temperature_c"]),
                             float(rc.get("supply_v") or 0) or _supply_from_dir(resp.parent.name))
            vals = out.setdefault(cid, {})
            for m in rc.get("measurements") or []:
                if isinstance(m, dict) and isinstance(m.get("value"), (int, float)):
                    vals[str(m["name"])] = float(m["value"])
    return out


def _supply_from_dir(name):
    return float(name.split("-")[0][1:])


def graded(r, name):
    if not r:
        return None, None
    for m in r.get("measurements", r.get("derived", [])):
        if m.get("name") == name:
            return m.get("value"), m.get("pass")
    return None, None


def fmt(v, nd=4):
    return "" if v is None else f"{v:.{nd}g}"


def iq_table():
    base, b_by, b_jobs = load_leg("iq-base")
    cand, c_by, c_jobs = load_leg("iq-cand")
    b_raw, c_raw = raw_cards("iq-base"), raw_cards("iq-cand")
    rows = []
    fails_b, fails_c = [], []
    worst = {"base": None, "cand": None}  # per variant: (margin_ua, corner)
    for proc in PROCS:
        for temp in TEMPS:
            for vsup in VSUPS:
                cid = corner_key(proc, temp, vsup)
                rb, rc = b_by.get(cid), c_by.get(cid)
                bn, bp = graded(rb, "iq_no_load_ua")
                bf, bpf = graded(rb, "iq_full_load_ua")
                cn, cp = graded(rc, "iq_no_load_ua")
                cf, cpf = graded(rc, "iq_full_load_ua")
                if rb and not rb["pass"]:
                    fails_b.append(cid)
                if rc and not rc["pass"]:
                    fails_c.append(cid)
                for v, no, fl in (("base", bn, bf), ("cand", cn, cf)):
                    if no is None or fl is None:
                        continue
                    m = 30 - max(no, fl)
                    if worst[v] is None or m < worst[v][0]:
                        worst[v] = (m, cid)
                rows.append({
                    "corner": cid,
                    "base_iq_no_load_raw_a": b_raw.get(cid, {}).get("tran1.iq_no_load_raw"),
                    "base_iq_full_load_raw_a": b_raw.get(cid, {}).get("tran2.iq_full_load_raw"),
                    "base_iq_no_load_ua": bn, "base_iq_full_load_ua": bf,
                    "base_pass": rb["pass"] if rb else None,
                    "cand_iq_no_load_raw_a": c_raw.get(cid, {}).get("tran1.iq_no_load_raw"),
                    "cand_iq_full_load_raw_a": c_raw.get(cid, {}).get("tran2.iq_full_load_raw"),
                    "cand_iq_no_load_ua": cn, "cand_iq_full_load_ua": cf,
                    "cand_pass": rc["pass"] if rc else None,
                    "delta_no_load_ua": None if None in (bn, cn) else cn - bn,
                    "delta_full_load_ua": None if None in (bf, cf) else cf - bf,
                })
    return rows, dict(fail_base=fails_b, fail_cand=fails_c, jobs_base=b_jobs, jobs_cand=c_jobs,
                      worst=worst)

def clamp_table():
    base, b_by, b_jobs = load_leg("cl-base")
    cand, c_by, c_jobs = load_leg("cl-cand")
    names = ["vout_50ma_v", "cl_margin_50ma_v", "ilim_short_ma", "ilim_knee_ma",
             "ilim_droop_pct", "ishort_sustained_ma", "ishort_ripple_pct", "vout_short_mv"]
    rows = []
    diag_b, diag_c = [], []
    for proc in PROCS:
        for temp in TEMPS:
            for vsup in VSUPS:
                cid = corner_key(proc, temp, vsup)
                rb, rc = b_by.get(cid), c_by.get(cid)
                if rb and rb.get("solver_diagnostic"):
                    diag_b.append((cid, rb["solver_diagnostic"]))
                if rc and rc.get("solver_diagnostic"):
                    diag_c.append((cid, rc["solver_diagnostic"]))
                row = {"corner": cid}
                for tag, r in (("base", rb), ("cand", rc)):
                    for n in names:
                        v, p = graded(r, n)
                        row[f"{tag}_{n}"] = v
                    row[f"{tag}_pass"] = r["pass"] if r else None
                    row[f"{tag}_solver_diag"] = r.get("solver_diagnostic") if r else None
                    ex = (r or {}).get("extras") or {}
                    for k in ("ir_set_50ma", "tail_i_set_50ma", "clp_i_set_50ma",
                              "cl_cmp_50ma_x", "i_at_375mv", "i_at_750mv", "i_at_1125mv",
                              "i_at_1500mv", "i_at_1625mv", "cl_cmp_at_short", "cl_cmp_at_knee",
                              "clp_i_at_short", "ir_at_short", "clp_i_short"):
                        row[f"{tag}_{k}"] = ex.get(k)
                rows.append(row)
    return rows, names, dict(diag_base=diag_b, diag_cand=diag_c, jobs_base=b_jobs,
                             jobs_cand=c_jobs)


def _f(x):
    return None if x in (None, "") else float(x)


def clamp_paired(rows):
    """Paired knee/short changes on corners where BOTH runs passed the solver
    gate, per-leg valid-corner ranges and counts, from the clamp_pair rows."""
    valid = [r for r in rows if r["base_pass"] in (True, "True") and r["cand_pass"] in (True, "True")]
    chg = []
    for r in valid:
        kb, kc = _f(r["base_ilim_knee_ma"]), _f(r["cand_ilim_knee_ma"])
        sb, sc = _f(r["base_ilim_short_ma"]), _f(r["cand_ilim_short_ma"])
        chg.append({"corner": r["corner"], "knee_pct": 100 * (kc / kb - 1),
                    "short_pct": 100 * (sc / sb - 1), "knee_base_ma": kb, "knee_cand_ma": kc,
                    "short_base_ma": sb, "short_cand_ma": sc})
    lo = min(chg, key=lambda c: c["knee_pct"])
    hi = max(chg, key=lambda c: c["knee_pct"])
    out = {"n_pairs_both_valid": len(valid),
           "knee_change_min": lo, "knee_change_max": hi,
           "n_knee_decrease": sum(c["knee_pct"] < 0 for c in chg),
           "n_knee_increase": sum(c["knee_pct"] > 0 for c in chg),
           "knee_note": ("knee = forced-output current sampled at Vout = 1.75 V; it is a "
                         "proxy for engagement current, not a measured engagement point")}
    for tag in ("base", "cand"):
        v = [r for r in rows if r[f"{tag}_pass"] in (True, "True")]
        out[tag] = {"n_valid": len(v)}
        for m in ("ilim_short_ma", "ilim_knee_ma", "ishort_ripple_pct"):
            vals = [(_f(r[f"{tag}_{m}"]), r["corner"]) for r in v]
            out[tag][m] = {"min": min(vals), "max": max(vals)}
        out[tag]["solver_invalid"] = [
            {"corner": r["corner"], "ilim_short_ma": _f(r[f"{tag}_ilim_short_ma"]),
             "ilim_knee_ma": _f(r[f"{tag}_ilim_knee_ma"])}
            for r in rows if r[f"{tag}_pass"] not in (True, "True")]
    return out


def iq_paired(iq_rows, ir_rows):
    """Worst conditions from the joined per-corner rows."""
    def ext(rows, key, fn):
        vals = [(r[key], r["corner"]) for r in rows if r.get(key) is not None]
        return fn(vals)
    out = {
        "n_valid": {"base": sum(r["base_pass"] is True for r in iq_rows),
                    "cand": sum(r["cand_pass"] is True for r in iq_rows)},
        "delta_full_load_ua": {"largest_cut": ext(iq_rows, "delta_full_load_ua", min),
                               "largest_increase": ext(iq_rows, "delta_full_load_ua", max)},
        "delta_no_load_ua": {"largest_cut": ext(iq_rows, "delta_no_load_ua", min),
                             "largest_increase": ext(iq_rows, "delta_no_load_ua", max)},
        "base_failing_corner_deltas_full_load_ua": {
            r["corner"]: r["delta_full_load_ua"] for r in iq_rows if r["base_pass"] is False},
    }
    for tag in ("base", "cand"):
        for q in ("ir_set_50ma", "tail_i_set_50ma"):
            vals = [(_f(r[f"{tag}_{q}"]), r["corner"]) for r in ir_rows]
            out[f"{tag}_{q}"] = {"min": min(vals), "max": max(vals)}
    return out


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: (fmt(v, 6) if isinstance(v, float) else v) for k, v in r.items()})


def thermal_summary():
    out = {}
    hyst = HERE.parents[2] / "thermal" / "hysteresis"
    for variant, pat in (("base", "*i706-paired-base"), ("cand", "*i706-paired-cand")):
        dirs = sorted(hyst.glob(pat + "/result.json"))
        if not dirs:
            dirs = sorted(hyst.glob(pat + "/result-incomplete-*.json"))
        if not dirs:
            out[variant] = None
            continue
        d = json.loads(dirs[-1].read_text())
        out[variant] = {
            "record": d["record_id"], "complete": d["complete"], "n_points": d["n_points"],
            "jobs": d["jobs"],
            "corners": {k: {
                "t_reset_c": v["t_reset_falling_c"].get("midpoint",
                                                        v["t_reset_falling_c"].get("error")),
                "t_trip_c": v["t_trip_rising_c"].get("midpoint",
                                                     v["t_trip_rising_c"].get("error")),
                "hysteresis_c": (v.get("hysteresis_c") or {}).get("midpoint"),
                "dependent_missing": (v.get("dependent_points") or {}).get("missing"),
            } for k, v in d["corners"].items()},
        }
    return out


def main():
    TABLES.mkdir(exist_ok=True)
    iq_rows, iq_sum = iq_table()
    write_csv(TABLES / "iq_pair.csv", iq_rows)
    cl_rows, cl_names, cl_sum = clamp_table()
    write_csv(TABLES / "clamp_pair.csv", cl_rows)
    ir_rows = [{k: v for k, v in r.items()
                if k == "corner" or "ir_set" in k or "tail_i_set" in k or "clp_i" in k
                or "cl_cmp" in k or "i_at_" in k} for r in cl_rows]
    write_csv(TABLES / "ir_spread.csv", ir_rows)

    iq_pairs = iq_paired(iq_rows, ir_rows)
    summary = {
        "iq": {
            "n_corners": len(iq_rows),
            "base_fails": iq_sum["fail_base"],
            "cand_fails": iq_sum["fail_cand"],
            "worst_margin": {
                v: {"corner": iq_sum["worst"][v][1], "margin_ua": iq_sum["worst"][v][0],
                    "exceeds_print_quantum": abs(iq_sum["worst"][v][0]) > IQ_RESOLUTION_UA,
                    "solver_resolved": None}
                for v in ("base", "cand") if iq_sum["worst"][v] is not None
            },
            "resolution": {
                "full_load_print_quantum_ua": FULL_LOAD_PRINT_QUANTUM_UA,
                "print_note": (
                    "the full-load meas card prints the ~0.05 A supply current with 6 "
                    "significant digits (last digit 1e-7 A = 0.1 uA); the manifest subtracts "
                    "the ideal 0.05 A load, which does not refine that resolution"),
                "solver_settings": {"reltol": 1e-3, "abstol_a": 1e-12, "vntol_v": 1e-6,
                                    "source": "ngspice defaults; no override in deck or "
                                              "sim/spiceinit"},
                "solver_note": (
                    "a convergence setting is not an error bound on the difference of two "
                    "near-equal currents; no precision/tolerance comparison was run, so "
                    "strict-bound compliance at a corner whose margin is within the print "
                    "quantum is unresolved and no margin is called solver-resolved"),
            },
            "paired": iq_pairs,
            "jobs": {"base": iq_sum["jobs_base"], "cand": iq_sum["jobs_cand"]},
        },
        "clamp": {
            "n_corners": len(cl_rows),
            "solver_diag_base": cl_sum["diag_base"],
            "solver_diag_cand": cl_sum["diag_cand"],
            "paired": clamp_paired(cl_rows),
            "window_tbd_note": ("the current-limit window stays TBD per spec/target-spec.md; "
                                "values are reported, not graded against an invented window"),
            "jobs": {"base": cl_sum["jobs_base"], "cand": cl_sum["jobs_cand"]},
        },
        "thermal": thermal_summary(),
    }

    # ff/125C/3.63V strict-bound rows, both loads, both DUTs (the AC's named row)
    key = corner_key("ff", 125.0, 3.63)
    row = next((r for r in iq_rows if r["corner"] == key), None)
    if row:
        summary["iq"]["ff_125c_363v"] = {
            k: row[k] for k in row if "iq_" in k or "pass" in k}
    (TABLES / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"iq_fails_base": len(iq_sum["fail_base"]),
                      "iq_fails_cand": len(iq_sum["fail_cand"]),
                      "clamp_diag_base": len(cl_sum["diag_base"]),
                      "clamp_diag_cand": len(cl_sum["diag_cand"]),
                      "thermal": {k: (v or {}).get("complete") for k, v in summary["thermal"].items()}},
                     indent=1))


if __name__ == "__main__":
    main()
