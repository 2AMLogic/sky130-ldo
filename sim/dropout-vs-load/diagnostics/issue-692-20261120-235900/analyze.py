#!/usr/bin/env python3
"""Issue #692 campaign analysis: paired tables + machine-readable verdict.

Reads runs/<leg>/leg.json for the six batch legs (pair-*, dropout-base,
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
        import re
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


def load_leg(leg: str) -> dict:
    d = json.loads((RUNS / leg / "leg.json").read_text())
    rows = {}
    for r in d["results"]:
        meas = {m["name"]: m["value"] for m in r["measurements"]}
        valid = not r["batch_reasons"] and r.get("solver_diagnostic") is None
        rows[r["corner_id"]] = {"meas": meas, "valid": valid, "pass": r["pass"]}
    out = {"rows": rows, "extras": leg_extras(leg), "leg": d}
    return out


def corner_ids(leg: str) -> list[str]:
    d = json.loads((RUNS / leg / "leg.json").read_text())
    return d["corner_ids"]


def dropout_pass(v) -> bool:
    return v is not None and v < DROPOUT_BOUND


def iq_pass(v) -> bool:
    return v is not None and 0 <= v < IQ_BOUND


def main() -> None:
    TABLES.mkdir(exist_ok=True)
    db = load_leg("dropout-base")
    dc = load_leg("dropout-cand")
    d2 = load_leg("dropout-cand-r2")
    ib = load_leg("iq-base")
    ic = load_leg("iq-cand")
    i2 = load_leg("iq-cand-r2")
    cids = corner_ids("dropout-cand")

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
                v = src["extras"].get(cid, {}).get(name)
                return f"{v:.6g}" if isinstance(v, (int, float)) else ""
            def dv(src):
                r = src["rows"].get(cid)
                if r is None:
                    return "", ""
                v = r["meas"].get("dropout_v")
                ok = "VALID_PASS" if (r["valid"] and dropout_pass(v)) else (
                    "VALID_FAIL" if r["valid"] else "INVALID")
                return (f"{v:.6f}" if v is not None else "", ok)
            bv, bok = dv(db)
            cv, cok = dv(dc)
            rv, rok = dv(d2)
            def tail(src):
                return ex(src, "tail_i_at_x")
            w.writerow([cid, bv, bok, cv, cok, rv, rok,
                        ex(db, "ea_out_at_x"), ex(dc, "ea_out_at_x"), ex(d2, "ea_out_at_x"),
                        tail(db), tail(dc), tail(d2),
                        ex(db, "mclim_i_at_x"), ex(dc, "mclim_i_at_x"), ex(d2, "mclim_i_at_x"),
                        ex(dc, "vout_at_2v064"), ex(d2, "vout_at_2v064"),
                        ex(dc, "mclim_vgs_at_2v064"), ex(d2, "mclim_vgs_at_2v064"),
                        ex(dc, "mclim_i_at_2v064"), ex(d2, "mclim_i_at_2v064"),
                        ex(dc, "biasref_i_set"), ex(d2, "biasref_i_set"), ex(db, "biasref_i_set")])

    with open(TABLES / "iq_pair.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["corner", "base_nl", "base_fl", "base_ok", "rev1_nl", "rev1_fl", "rev1_ok",
                    "rev2_nl", "rev2_fl", "rev2_ok", "base_vout_fl", "rev1_vout_fl",
                    "rev2_vout_fl"])
        for cid in cids:
            def row(src):
                r = src["rows"].get(cid)
                if r is None:
                    return "", "", "", ""
                m = r["meas"]
                nl, fl = m.get("iq_no_load_ua"), m.get("iq_full_load_ua")
                ok = "VALID_PASS" if (r["valid"] and iq_pass(nl) and iq_pass(fl)) else (
                    "VALID_FAIL" if r["valid"] else "INVALID")
                return (f"{nl:.3f}" if nl is not None else "", f"{fl:.3f}" if fl is not None else "",
                        ok, m.get("vout_full_load_v"))
            bnl, bfl, bok, bvf = row(ib)
            cnl, cfl, cok, cvf = row(ic)
            rnl, rfl, rok, rvf = row(i2)
            w.writerow([cid, bnl, bfl, bok, cnl, cfl, cok, rnl, rfl, rok,
                        f"{bvf:.4f}" if bvf is not None else "",
                        f"{cvf:.4f}" if cvf is not None else "",
                        f"{rvf:.4f}" if rvf is not None else ""])

    def corners_summary(dsrc, isrc, revname):
        drops = {cid: dsrc["rows"][cid]["meas"].get("dropout_v") for cid in cids}
        valid_d = {cid: dsrc["rows"][cid]["valid"] for cid in cids}
        iq_nl = {cid: isrc["rows"][cid]["meas"].get("iq_no_load_ua") for cid in cids}
        iq_fl = {cid: isrc["rows"][cid]["meas"].get("iq_full_load_ua") for cid in cids}
        valid_i = {cid: isrc["rows"][cid]["valid"] for cid in cids}
        binding = max((cid for cid in cids if drops[cid] is not None), key=lambda c: drops[c])
        iq_worst = max((cid for cid in cids if iq_fl[cid] is not None), key=lambda c: iq_fl[c])
        dpass = [cid for cid in cids if valid_d[cid] and dropout_pass(drops[cid])]
        dinvalid = [cid for cid in cids if not valid_d[cid]]
        ipass = [cid for cid in cids if valid_i[cid] and iq_pass(iq_nl[cid]) and iq_pass(iq_fl[cid])]
        ifail = [cid for cid in cids if cid not in ipass]
        iinvalid = [cid for cid in cids if not valid_i[cid]]
        nonreg = [cid for cid in cids
                  if not (1.764 <= (isrc["rows"][cid]["meas"].get("vout_no_load_v") or 0) <= 1.836)
                  or not (1.764 <= (isrc["rows"][cid]["meas"].get("vout_full_load_v") or 0) <= 1.836)]
        return {
            "revision": revname,
            "dropout": {
                "n_pass": len(dpass), "n_fail": len(cids) - len(dpass) - len(dinvalid),
                "n_invalid": len(dinvalid), "invalid": dinvalid,
                "all_pass": len(dpass) == len(cids),
                "binding_corner": binding, "binding_dropout_v": drops[binding],
                "min_dropout_v": min(v for v in drops.values() if v is not None),
                "per_corner": {cid: {"dropout_v": drops[cid], "valid": valid_d[cid],
                                     "pass": valid_d[cid] and dropout_pass(drops[cid])}
                               for cid in cids},
            },
            "iq": {
                "n_pass": len(ipass), "n_fail": len(ifail), "failing": ifail,
                "n_invalid": len(iinvalid), "invalid": iinvalid,
                "non_regulating_vout": nonreg,
                "worst_full_load_corner": iq_worst,
                "max_full_load_ua": max(v for v in iq_fl.values() if v is not None),
                "max_no_load_ua": max(v for v in iq_nl.values() if v is not None),
                "per_corner": {cid: {"no_load_ua": iq_nl[cid], "full_load_ua": iq_fl[cid],
                                     "valid": valid_i[cid],
                                     "pass": valid_i[cid] and iq_pass(iq_nl[cid]) and iq_pass(iq_fl[cid])}
                               for cid in cids},
            },
        }

    verdict = {
        "issue": 692,
        "bound_dropout_v": DROPOUT_BOUND,
        "bound_iq_ua": IQ_BOUND,
        "baseline": corners_summary(db, ib, "baseline (committed design)"),
        "rev1": corners_summary(dc, ic, "rev1 (#357 re-based, byte-identical)"),
        "rev2": corners_summary(d2, i2, "rev2 (single Iq-driven revision: NTAIL 12/3 -> 7/2)"),
        "local_debug_probes": {
            p.name: json.loads((p / "result.json").read_text())
            for p in sorted(RUNS.glob("dbg-*")) if (p / "result.json").exists()
        },
    }
    r2max = verdict["rev2"]["iq"]["max_full_load_ua"]
    verdict["decision"] = {
        "decision": "ADOPT-REVIEW",
        "dropout_all_corners_below_bound": verdict["rev2"]["dropout"]["all_pass"]
        and verdict["rev1"]["dropout"]["all_pass"],
        "binding_corner": verdict["rev2"]["dropout"]["binding_corner"],
        "binding_dropout_v": verdict["rev2"]["dropout"]["binding_dropout_v"],
        "candidate_recommended": "rev2",
        "notes": [
            "rev1 holds < 300 mV at every corner (binding ff/-40C/2.97V 0.2192 V) but fails the",
            "ratified Iq row at 15 corners (13 excesses 30.2-33.2 uA plus two non-regulating",
            "states: ss/125C/3.30V full-load clamp latch, ff/27C/2.97V no-load non-physical",
            "settled state); failures retained unedited in tables/iq_pair.csv.",
            "rev2 (the one permitted revision, NTAIL 12/3 -> 7/2) passes both rows at all 45",
            f"corners; its worst Iq corner ff/125C/3.63V reads {r2max!r} uA against the strict",
            "< 30 uA bound -- a pass with ZERO effective margin (4.7e-6 uA), recorded as an",
            "at-bound finding the adoption review must re-measure, not as headroom.",
            "ADOPT-REVIEW per the issue's own criterion (dropout < 300 mV at every corner):",
            "the candidate goes to a separate production-adoption review issue (loop gain,",
            "PM/GM, load transient, PSRR, start-up, MC accuracy, plus this campaign's Iq",
            "at-bound corner, the rev1 robustness states and the current-limit/thermal",
            "re-checks), not to adoption here.",
        ],
    }
    (HERE / "verdict.json").write_text(json.dumps(verdict, indent=1, sort_keys=True) + "\n")
    for rev in ("baseline", "rev1", "rev2"):
        s = verdict[rev]
        print(f"{s['revision']}: dropout {s['dropout']['n_pass']}/45 pass "
              f"(binding {s['dropout']['binding_corner']} {s['dropout']['binding_dropout_v']:.4f} V), "
              f"iq {s['iq']['n_pass']}/45 pass (max full-load {s['iq']['max_full_load_ua']:.2f} uA at "
              f"{s['iq']['worst_full_load_corner']})")


if __name__ == "__main__":
    main()
