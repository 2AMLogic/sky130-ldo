#!/usr/bin/env python3
"""Issue #692 campaign analysis: paired tables + machine-readable verdict.

Reads runs/<leg>/leg.json for the six matrix legs (dropout-base,
dropout-cand, dropout-cand-r2, iq-base, iq-cand, iq-cand-r2) and the local
debug probes, and writes:

  tables/dropout_pair.csv   45-row paired dropout table (base vs rev1 vs rev2)
  tables/iq_pair.csv        45-row paired Iq table (base vs rev1 vs rev2)
  verdict.json              per-corner machine-readable verdicts + decision inputs

Failures are recorded as failures: a corner is a PASS only when the harness
result is valid (no batch_reasons, no solver diagnostic) AND the measurement
is inside the ratified bound. Non-regulating starts are INVALID, never passes.
"""
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
TABLES = HERE / "tables"
DROPOUT_BOUND = 0.300
IQ_BOUND = 30.0


EXTRA_NAMES = ["ea_out_at_x", "tail_i_at_x", "mclim_i_at_x", "vout_at_2v064",
               "mclim_vgs_at_2v064", "mclim_i_at_2v064", "tail_i_set", "biasref_i_set"]


def leg_extras(leg: str) -> dict[str, dict[str, float | None]]:
    """{corner_id: {extra name: value}} from a leg's klt responses, keyed by the
    harness corner id (the supply comes from each request's directory name)."""
    out: dict[str, dict[str, float | None]] = {}
    for resp_path in sorted((RUNS / leg / "klt-out").glob("*/response.json")):
        m = re.fullmatch(r"v([0-9.]+)", resp_path.parent.name)
        if m is None:
            continue
        supply = float(m.group(1))
        for rc in json.loads(resp_path.read_text()).get("corners", []):
            if not isinstance(rc, dict) or not isinstance(rc.get("process"), str):
                continue
            cid = f"{rc['process']}_{float(rc['temperature_c']):g}c_{supply:.2f}v"
            by_name = {rm["name"]: rm.get("value") for rm in rc.get("measurements", [])
                       if isinstance(rm, dict) and isinstance(rm.get("name"), str)}
            out[cid] = {n: (float(by_name[f"dropout.{n}"])
                            if isinstance(by_name.get(f"dropout.{n}"), (int, float)) else None)
                        for n in EXTRA_NAMES}
    return out


def regulating(vout):
    return vout is not None and 1.764 <= vout <= 1.836


def dropout_corner(meas):
    value = meas.get("dropout_v")
    start = meas.get("vout_at_max_vin_v")
    row = {"dropout_v": value, "vout_at_max_vin_v": start}
    if value is None or start is None:
        return row, "INVALID", "missing_crossing_or_start"
    if not regulating(start):
        return row, "INVALID", "non_regulating_start"
    return row, "VALID_PASS" if value < DROPOUT_BOUND else "VALID_FAIL", None


def iq_corner(meas):
    nl = meas.get("iq_no_load_ua")
    fl = meas.get("iq_full_load_ua")
    # The printed full-load VIN current has a 0.1 uA least digit at 50 mA.
    # Remove binary subtraction residue before applying the strict bound.
    if fl is not None:
        fl = round(fl, 1)
    vnl, vfl = meas.get("vout_no_load_v"), meas.get("vout_full_load_v")
    row = {"no_load_ua": nl, "full_load_ua": fl,
           "vout_no_load_v": vnl, "vout_full_load_v": vfl}
    if None in (nl, fl, vnl, vfl):
        return row, "INVALID", "missing_endpoint"
    if not (regulating(vnl) and regulating(vfl)):
        return row, "INVALID", "non_regulating_vout"
    if not (0 <= nl < IQ_BOUND and 0 <= fl <= IQ_BOUND):
        return row, "VALID_FAIL", None
    if fl == IQ_BOUND:
        return row, "AT_BOUND", "full_load_at_resolution_limit"
    return row, "VALID_PASS", None


def grade_leg(leg, cids, grade_corner):
    results = {r["corner_id"]: r for r in leg["results"]}
    rows = {}
    for cid in cids:
        r = results.get(cid)
        measurements = r["measurements"] if r is not None else []
        meas = {m["name"]: m["value"] for m in measurements
                if m["value"] is not None and math.isfinite(m["value"])}
        row, status, reason = grade_corner(meas)
        if r is None:
            status, reason = "INVALID", "missing_corner"
        elif r["batch_reasons"] or r.get("solver_diagnostic") is not None or r["timed_out"]:
            status, reason = "INVALID", "batch_or_solver_failure"
        row.update(status=status, valid=status != "INVALID")
        row["pass"] = status == "VALID_PASS"
        if reason:
            row["reason"] = reason
        rows[cid] = row
    return rows


def summary(rows):
    failed = [cid for cid, r in rows.items() if r["status"] == "VALID_FAIL"]
    invalid = [cid for cid, r in rows.items() if not r["valid"]]
    passes = sum(r["pass"] for r in rows.values())
    return {"n_pass": passes, "n_fail": len(failed), "failing": failed,
            "n_invalid": len(invalid), "invalid": invalid,
            "all_pass": bool(rows) and passes == len(rows), "per_corner": rows}


def corners_summary(drops, currents, revname):
    dropout = summary(drops)
    valid_d = {cid: r["dropout_v"] for cid, r in drops.items() if r["valid"]}
    binding = max(valid_d, key=valid_d.get, default=None)
    dropout.update(binding_corner=binding, binding_dropout_v=valid_d.get(binding),
                   min_dropout_v=min(valid_d.values(), default=None))

    iq = summary(currents)
    valid_i = {cid: r for cid, r in currents.items() if r["valid"]}
    worst = max(valid_i, key=lambda cid: valid_i[cid]["full_load_ua"], default=None)
    at_bound = [cid for cid, r in currents.items() if r["status"] == "AT_BOUND"]
    iq.update(n_at_bound=len(at_bound), at_bound=at_bound,
              non_regulating_vout=[cid for cid, r in currents.items()
                                   if r.get("reason") == "non_regulating_vout"],
              worst_full_load_corner=worst,
              max_full_load_ua=valid_i[worst]["full_load_ua"] if worst else None,
              max_no_load_ua=max((r["no_load_ua"] for r in valid_i.values()), default=None))
    return {"revision": revname, "dropout": dropout, "iq": iq}


def main() -> None:
    TABLES.mkdir(exist_ok=True)

    def load(leg):
        return json.loads((RUNS / leg / "leg.json").read_text())

    dc_leg = load("dropout-cand")
    cids = dc_leg["corner_ids"]
    db = grade_leg(load("dropout-base"), cids, dropout_corner)
    dc = grade_leg(dc_leg, cids, dropout_corner)
    d2 = grade_leg(load("dropout-cand-r2"), cids, dropout_corner)
    ib = grade_leg(load("iq-base"), cids, iq_corner)
    ic = grade_leg(load("iq-cand"), cids, iq_corner)
    i2 = grade_leg(load("iq-cand-r2"), cids, iq_corner)
    xb, xc, x2 = (leg_extras(leg) for leg in ("dropout-base", "dropout-cand", "dropout-cand-r2"))

    with open(TABLES / "dropout_pair.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["corner", "base_v", "base_ok", "rev1_v", "rev1_ok", "rev2_v", "rev2_ok",
                    "base_ea_x", "rev1_ea_x", "rev2_ea_x", "base_tail_x", "rev1_tail_x",
                    "rev2_tail_x", "base_mclim_x", "rev1_mclim_x", "rev2_mclim_x",
                    "rev1_vout_2v064", "rev2_vout_2v064", "rev1_mclim_vgs_2v064",
                    "rev2_mclim_vgs_2v064", "rev1_mclim_i_2v064", "rev2_mclim_i_2v064",
                    "rev1_ir_set", "rev2_ir_set", "base_ibias_set"])
        for cid in cids:
            def ex(src, name):
                v = src.get(cid, {}).get(name)
                return f"{v:.6g}" if isinstance(v, (int, float)) else ""

            def dv(src):
                r = src[cid]
                v = r["dropout_v"]
                return (f"{v:.6f}" if v is not None else "", r["status"])

            bv, bok = dv(db)
            cv, cok = dv(dc)
            rv, rok = dv(d2)
            def tail(src):
                return ex(src, "tail_i_at_x")
            w.writerow([cid, bv, bok, cv, cok, rv, rok,
                        ex(xb, "ea_out_at_x"), ex(xc, "ea_out_at_x"), ex(x2, "ea_out_at_x"),
                        tail(xb), tail(xc), tail(x2),
                        ex(xb, "mclim_i_at_x"), ex(xc, "mclim_i_at_x"), ex(x2, "mclim_i_at_x"),
                        ex(xc, "vout_at_2v064"), ex(x2, "vout_at_2v064"),
                        ex(xc, "mclim_vgs_at_2v064"), ex(x2, "mclim_vgs_at_2v064"),
                        ex(xc, "mclim_i_at_2v064"), ex(x2, "mclim_i_at_2v064"),
                        ex(xc, "biasref_i_set"), ex(x2, "biasref_i_set"), ex(xb, "biasref_i_set")])

    with open(TABLES / "iq_pair.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["corner", "base_nl", "base_fl", "base_ok", "rev1_nl", "rev1_fl", "rev1_ok",
                    "rev2_nl", "rev2_fl", "rev2_ok", "base_vout_fl", "rev1_vout_fl",
                    "rev2_vout_fl"])
        for cid in cids:
            def row(src):
                r = src[cid]
                nl, fl = r["no_load_ua"], r["full_load_ua"]
                return (f"{nl:.3f}" if nl is not None else "", f"{fl:.1f}" if fl is not None else "",
                        r["status"], r["vout_full_load_v"])
            bnl, bfl, bok, bvf = row(ib)
            cnl, cfl, cok, cvf = row(ic)
            rnl, rfl, rok, rvf = row(i2)
            w.writerow([cid, bnl, bfl, bok, cnl, cfl, cok, rnl, rfl, rok,
                        f"{bvf:.4f}" if bvf is not None else "",
                        f"{cvf:.4f}" if cvf is not None else "",
                        f"{rvf:.4f}" if rvf is not None else ""])

    verdict = {
        "issue": 692,
        "bound_dropout_v": DROPOUT_BOUND,
        "bound_iq_ua": IQ_BOUND,
        "full_load_iq_resolution_ua": 0.1,
        "baseline": corners_summary(db, ib, "baseline (committed design)"),
        "rev1": corners_summary(dc, ic, "rev1 (#357 re-based, byte-identical)"),
        "rev2": corners_summary(d2, i2, "rev2 (single Iq-driven revision: NTAIL 12/3 -> 7/2)"),
        "local_debug_probes": {
            p.name: json.loads((p / "result.json").read_text())
            for p in sorted(RUNS.glob("dbg-*")) if (p / "result.json").exists()
        },
    }
    rev2_dropout = verdict["rev2"]["dropout"]
    verdict["decision"] = {
        "decision": "ADOPT-REVIEW" if rev2_dropout["all_pass"] else "REVISE",
        "dropout_all_corners_below_bound": rev2_dropout["all_pass"],
        "binding_corner": rev2_dropout["binding_corner"],
        "binding_dropout_v": rev2_dropout["binding_dropout_v"],
        "candidate_recommended": "rev2" if rev2_dropout["all_pass"] else None,
        "notes": [
            "The decision grades rev2 against the all-corner dropout criterion in issue #692.",
            "Rev1's ss/-40C/3.30V crossing is clamp-mediated after a non-regulating start.",
            "Rev1's two invalid Iq endpoints are diagnosed in README section 6.",
            "At full load the VIN current resolves to 0.1 uA. A reading at the strict bound "
            "requires higher-resolution measurement in the adoption review.",
        ],
    }
    (HERE / "verdict.json").write_text(json.dumps(verdict, indent=1, sort_keys=True) + "\n")
    for rev in ("baseline", "rev1", "rev2"):
        s = verdict[rev]
        print(f"{s['revision']}: dropout {s['dropout']['n_pass']}/{len(cids)} pass "
              f"(binding {s['dropout']['binding_corner']} {s['dropout']['binding_dropout_v']} V), "
              f"Iq {s['iq']['n_pass']}/{len(cids)} pass, {s['iq']['n_at_bound']} at bound, "
              f"{s['iq']['n_invalid']} invalid")


if __name__ == "__main__":
    main()
