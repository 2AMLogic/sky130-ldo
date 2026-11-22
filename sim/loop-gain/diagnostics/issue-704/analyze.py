#!/usr/bin/env python3
"""Issue #704 paired analysis: tables, worst cases and verdict.json.

Reads ONLY what the campaign wrote under runs/ (responses, leg.json,
provenance); recomputes every grade from the raw paired values against the
ratified bounds (PM >= 45 deg and GM >= 10 dB; load step peak <= 150 mV and
recovery into +-1 % within 20 us; PSRR strictly > 50 dB @ 1 kHz and > 20 dB
@ 100 kHz). A missing or invalid measurement is reported as such, never
inferred and never counted as a pass. Writes tables/*.csv and
verdict.json next to this script.

Usage: python3 analyze.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from campaign import (  # noqa: E402
    LOADS, LOOP_CAP, LOOP_ESR, LOADSTEP_QUICK, PSRR_LOADS, PSRR_SUPPLIES, VSUP,
    corner_data, measurements, op_gate, response, solver_reason, transfer_row,
)
from _fleet_campaign import PM_MIN, GM_MIN  # noqa: E402

PSRR_1K_MIN, PSRR_100K_MIN = 50.0, 20.0
PEAK_MAX_V, REC_MAX_US = 0.150, 20.0
# A recovery reading at/above the leg window ceiling (998 us) minus one
# sample step (200 ns) means the trace never re-entered the band inside the
# window: "no recovery in window", not a recovery time.
REC_WINDOW_CEIL_US = 997.9
DESIGNS = ("base", "rev2")


def fnum(x, f="{:.4g}"):
    return "n/a" if x is None else f.format(x)


def load_legs():
    return [f"{cap}-{esr}-{load}" for cap in LOOP_CAP for esr in LOOP_ESR for load in LOADS]


# ---------------------------------------------------------------- loop gain
def loop_rows():
    rows = []
    for design in DESIGNS:
        out = HERE / "runs" / "loop" / design
        for leg in load_legs():
            cap, esr, load = leg.split("-", 2)
            resp = response(out, f"loop-{leg}")
            if "corners" not in resp:
                prov = json.loads((out / "provenance.json").read_text())
                resp["reason"] = prov["errors"].get(f"loop-{leg}", "no batch response")
            row = transfer_row(resp, "tt", 27.0)
            gate = op_gate(out, "op-gate", load, "tt", 27.0) if not row["reason"] else None
            # Per-metric validity: an unavailable GM (klt
            # transfer_metric_unavailable, typically no_downward_phase_crossing)
            # must not invalidate the leg's PM, and vice versa. A solver
            # diagnostic or op-gate failure invalidates both.
            mreason = row["reason"] or ""
            unavail = "transfer_metric_unavailable" in mreason or mreason.startswith(
                "missing or invalid")
            hard = None if unavail else (row["reason"] or gate)
            row.update(
                design=design, leg=leg, cap=cap, esr=esr, load=load,
                pm_valid=row["pm"] is not None and not hard,
                gm_valid=row["gm"] is not None and not hard,
                pm_unavailable_reason=(mreason if row["pm"] is None and not hard else None),
                gm_unavailable_reason=(mreason if row["gm"] is None and not hard else None),
                reason=hard or mreason,
            )
            rows.append(row)
    return rows


def decoupled_rows():
    d = HERE / "runs" / "loop" / "rev2-decoupled"
    if not (d / "provenance.json").is_file():
        return []
    prov = json.loads((d / "provenance.json").read_text())
    drawn = HERE / "runs" / "loop" / "rev2"
    rows = []
    for leg in prov["legs"]:
        a = transfer_row(response(drawn, f"loop-{leg}"), "tt", 27.0)
        b = transfer_row(response(d, f"decoupled-{leg}"), "tt", 27.0)
        if b.get("reason") and "corners" not in response(d, f"decoupled-{leg}"):
            b["reason"] = prov["errors"].get(f"decoupled-{leg}", b["reason"])
        rows.append({"leg": leg, "as_drawn": a, "decoupled": b})
    return rows


# --------------------------------------------------------------------- psrr
def psrr_rows():
    rows = []
    for design in DESIGNS:
        out = HERE / "runs" / "psrr" / design
        prov = json.loads((out / "provenance.json").read_text())
        for v in PSRR_SUPPLIES:
            for load in PSRR_LOADS:
                key = f"psrr-{load}-v{v:.2f}"
                resp = response(out, key)
                if "corners" not in resp:
                    resp["reason"] = prov["errors"].get(key, "no batch response")
                for process in ("tt", "ss", "ff", "sf", "fs"):
                    for temp in (-40.0, 27.0, 125.0):
                        c, job, reason = corner_data(resp, process, temp)
                        vals = measurements(c)
                        reason = reason or solver_reason(c)
                        if c.get("status") not in ("pass", "fail"):
                            reason = reason or f"corner {c.get('status')}"
                        p1k, p100k = vals.get("p1k"), vals.get("p100k")
                        a = None if p1k is None else -p1k
                        b = None if p100k is None else -p100k
                        if p1k is None or p100k is None:
                            reason = reason or "missing or invalid p1k/p100k"
                        if not reason:
                            reason = op_gate(out, f"op-gate-v{v:.2f}", load, process, temp)
                        rows.append({
                            "design": design, "load": load, "vsup": v, "process": process,
                            "temp_c": temp, "psrr_1k_db": a, "psrr_100k_db": b,
                            "job_id": job, "reason": reason,
                        })
    return rows


# ---------------------------------------------------------------- load step
LEG_IDS = ["c330n_esr0", "c330n_esr10m", "c330n_esr500m", "c4u7_esr0", "c4u7_esr10m", "c4u7_esr500m"]


def loadstep_rows():
    rows = []
    for design in DESIGNS:
        leg_json = HERE / "runs" / "loadstep" / design / "leg.json"
        if not leg_json.is_file():
            continue
        data = json.loads(leg_json.read_text())
        for r in data["results"]:
            for m in r["measurements"]:
                if m.get("leg") is None:
                    continue
                rows.append({
                    "design": design, "corner_id": r["corner_id"],
                    "process": r["process"], "temp_c": r["temperature_c"], "supply_v": r["supply_v"],
                    "leg": m["leg"], "name": m["name"].split("__")[0], "value": m.get("value"),
                    "pass": m.get("pass"), "reason": m.get("reason"),
                    "solver_diagnostic": r.get("solver_diagnostic"),
                    "batch_reasons": r.get("batch_reasons"),
                })
    return rows


def loadstep_pairs():
    """(design, corner, leg) -> dict of the six graded quantities."""
    grid = {}
    for r in loadstep_rows():
        g = grid.setdefault((r["design"], r["corner_id"], r["leg"]), {})
        g[r["name"]] = r
    out = []
    for (design, corner, leg), g in sorted(grid.items()):
        def val(name):
            e = g.get(name)
            return None if e is None or e["value"] is None else e["value"]

        pre = val("vout_pre_v")
        row = {
            "design": design, "corner_id": corner, "leg": leg,
            "vout_pre_v": pre,
            "peak_rise_v": None, "peak_fall_v": None,
            "rec_rise_us": val("recovery_rise_us"), "rec_fall_us": val("recovery_fall_us"),
            "reason": "",
        }
        ur, orr = val("undershoot_rise_v"), val("overshoot_rise_v")
        uf, of = val("undershoot_fall_v"), val("overshoot_fall_v")
        if None not in (ur, orr):
            row["peak_rise_v"] = max(abs(ur), abs(orr))
        if None not in (uf, of):
            row["peak_fall_v"] = max(abs(uf), abs(of))
        for name, entry in g.items():
            if entry["value"] is None:
                row["reason"] = row["reason"] or f"{name}: {entry.get('reason')}"
        out.append(row)
    return out


# ------------------------------------------------------------- classification
def classify(bound_ok, base_v, cand_v):
    """baseline-failure / regression / both-fail / both-pass / invalid."""
    if base_v is None or cand_v is None:
        return "invalid"
    b, c = bound_ok(base_v), bound_ok(cand_v)
    if b and c:
        return "both_pass"
    if b and not c:
        return "regression"
    if not b and c:
        return "improvement"
    return "both_fail"


def main() -> int:
    tables = HERE / "tables"
    tables.mkdir(exist_ok=True)

    # ---- loop gain
    lrows = loop_rows()
    with (tables / "loop_pair.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "design", "leg", "cap", "esr", "load", "pm", "gm", "fc", "dc",
            "pm_ge_45", "gm_ge_10db", "job_id", "reason"])
        w.writeheader()
        for r in lrows:
            w.writerow({
                **{k: r[k] for k in ("design", "leg", "cap", "esr", "load", "fc", "dc", "job_id", "reason")},
                "pm": fnum(r["pm"]), "gm": fnum(r["gm"]),
                "pm_ge_45": "" if r["pm"] is None else r["pm"] >= PM_MIN,
                "gm_ge_10db": "" if r["gm"] is None else r["gm"] >= GM_MIN,
            })

    loop_stats = {}
    for design in DESIGNS:
        rs = [r for r in lrows if r["design"] == design]
        wpm = min((r for r in rs if r["pm_valid"]), key=lambda r: r["pm"], default=None)
        wgm = min((r for r in rs if r["gm_valid"]), key=lambda r: r["gm"], default=None)
        loop_stats[design] = {
            "points": len(rs),
            "pm_valid": sum(1 for r in rs if r["pm_valid"]),
            "gm_valid": sum(1 for r in rs if r["gm_valid"]),
            "pm_unavailable": [f'{r["leg"]}: {r["pm_unavailable_reason"]}'
                               for r in rs if r["pm_unavailable_reason"]],
            "gm_unavailable": [f'{r["leg"]}: {r["gm_unavailable_reason"]}'
                               for r in rs if r["gm_unavailable_reason"]],
            "invalid": [f'{r["leg"]}: {r["reason"]}' for r in rs
                        if not r["pm_valid"] and not r["gm_valid"]],
            "pm_below_min": sum(1 for r in rs if r["pm_valid"] and r["pm"] < PM_MIN),
            "gm_below_min": sum(1 for r in rs if r["gm_valid"] and r["gm"] < GM_MIN),
            "worst_pm": {"leg": wpm and wpm["leg"], "pm": wpm and wpm["pm"]} if wpm else None,
            "worst_gm": {"leg": wgm and wgm["leg"], "gm": wgm and wgm["gm"]} if wgm else None,
        }
    pair = {}
    for leg in load_legs():
        b = next((r for r in lrows if r["design"] == "base" and r["leg"] == leg), None)
        c = next((r for r in lrows if r["design"] == "rev2" and r["leg"] == leg), None)
        def mv(r, k):
            return r[k] if r and r.get(k + "_valid") else None

        pair[leg] = {
            "pm": classify(lambda v: v >= PM_MIN, mv(b, "pm"), mv(c, "pm")),
            "gm": classify(lambda v: v >= GM_MIN, mv(b, "gm"), mv(c, "gm")),
            "d_pm": (c and c["pm"]) - (b and b["pm"]) if b and c and b["pm"] is not None and c["pm"] is not None else None,
            "d_gm": (c and c["gm"]) - (b and b["gm"]) if b and c and b["gm"] is not None and c["gm"] is not None else None,
        }

    # ---- decoupled extraction check
    drows = decoupled_rows()
    dec = []
    for d in drows:
        a, b = d["as_drawn"], d["decoupled"]
        dpm = None if None in (a["pm"], b["pm"]) else b["pm"] - a["pm"]
        dgm = None if None in (a["gm"], b["gm"]) else b["gm"] - a["gm"]
        if dpm is None:
            verdict = "unresolved: " + (b["reason"] or a["reason"] or "missing value")
        else:
            # PM agreement at the unity-gain crossing is the primary check; a
            # systematic as-drawn GM optimism (bias-path entry) is disclosed,
            # and flagged only when it could move the GM verdict.
            gm_note = ("" if dgm is None else
                       f', dGM={dgm:+.2f} dB (as-drawn reads {"higher" if dgm < 0 else "lower"})')
            ok_pm = abs(dpm) <= 1.0
            ok_gm = dgm is None or (b["gm"] >= GM_MIN) == (a["gm"] >= GM_MIN)
            verdict = ("validated" if ok_pm and ok_gm else
                       f"FLAGGED (|dPM|={abs(dpm):.2f} deg{gm_note})")
        dec.append({"leg": d["leg"], "d_pm_deg": dpm, "d_gm_db": dgm, "verdict": verdict,
                    "as_drawn": {k: a[k] for k in ("pm", "gm", "fc", "dc")},
                    "decoupled": {k: b[k] for k in ("pm", "gm", "fc", "dc")},
                    "reasons": [x["reason"] for x in (a, b) if x["reason"]]})

    # ---- psrr
    prows = psrr_rows()
    with (tables / "psrr_pair.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["design", "load", "vsup", "process", "temp_c",
                                          "psrr_1k_db", "psrr_100k_db", "ok_1k", "ok_100k",
                                          "job_id", "reason"])
        w.writeheader()
        for r in prows:
            w.writerow({
                **r,
                "psrr_1k_db": fnum(r["psrr_1k_db"], "{:.3f}"),
                "psrr_100k_db": fnum(r["psrr_100k_db"], "{:.3f}"),
                "ok_1k": "" if r["psrr_1k_db"] is None else r["psrr_1k_db"] > PSRR_1K_MIN,
                "ok_100k": "" if r["psrr_100k_db"] is None else r["psrr_100k_db"] > PSRR_100K_MIN,
            })
    psrr_stats = {}
    for design in DESIGNS:
        rs = [r for r in prows if r["design"] == design]
        ok = [r for r in rs if not r["reason"]]
        w1k = min((r for r in ok if r["psrr_1k_db"] is not None), key=lambda r: r["psrr_1k_db"], default=None)
        w100k = min((r for r in ok if r["psrr_100k_db"] is not None), key=lambda r: r["psrr_100k_db"], default=None)
        psrr_stats[design] = {
            "points": len(rs), "valid": len(ok),
            "invalid": [f'{r["load"]}/{r["process"]}/{r["temp_c"]:g}C/{r["vsup"]:.2f}V: {r["reason"]}'
                        for r in rs if r["reason"]][:20],
            "fail_1k": sum(1 for r in ok if r["psrr_1k_db"] is not None and r["psrr_1k_db"] <= PSRR_1K_MIN),
            "fail_100k": sum(1 for r in ok if r["psrr_100k_db"] is not None and r["psrr_100k_db"] <= PSRR_100K_MIN),
            "worst_1k": None if not w1k else {"at": f'{w1k["load"]}/{w1k["process"]}/{w1k["temp_c"]:g}C/{w1k["vsup"]:.2f}V',
                                              "db": w1k["psrr_1k_db"]},
            "worst_100k": None if not w100k else {"at": f'{w100k["load"]}/{w100k["process"]}/{w100k["temp_c"]:g}C/{w100k["vsup"]:.2f}V',
                                                  "db": w100k["psrr_100k_db"]},
        }

    # ---- load step
    lpairs = loadstep_pairs()
    with (tables / "loadstep_pair.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["design", "corner_id", "leg", "vout_pre_v",
                                          "peak_rise_v", "peak_fall_v", "rec_rise_us", "rec_fall_us",
                                          "peak_ok", "rec_ok", "reason"])
        w.writeheader()
        for r in lpairs:
            peak = max(x for x in (r["peak_rise_v"], r["peak_fall_v"]) if x is not None) \
                if any(x is not None for x in (r["peak_rise_v"], r["peak_fall_v"])) else None
            recs = [x for x in (r["rec_rise_us"], r["rec_fall_us"]) if x is not None]
            rec_ok = bool(recs) and all(x <= REC_MAX_US for x in recs)
            w.writerow({
                **{k: (fnum(v, "{:.4f}") if isinstance(v, float) else v)
                   for k, v in r.items() if k != "reason"},
                "peak_ok": "" if peak is None else peak <= PEAK_MAX_V,
                "rec_ok": rec_ok,
            })
    loadstep_stats = {}
    for design in DESIGNS:
        rs = [r for r in lpairs if r["design"] == design]
        okp = [r for r in rs if not r["reason"]]
        peaks = [p for r in okp for p in (r["peak_rise_v"], r["peak_fall_v"]) if p is not None]
        recs = [(r, d) for r in okp for d in (r["rec_rise_us"], r["rec_fall_us"]) if d is not None]
        wp = max(peaks, default=None)
        wr = max(recs, key=lambda t: t[1], default=None)
        no_rec = sum(1 for _, x in recs if x >= REC_WINDOW_CEIL_US)
        loadstep_stats[design] = {
            "legs_x_corners": len(rs), "valid": len(okp),
            "peak_above_bound": sum(1 for p in peaks if p > PEAK_MAX_V),
            "rec_above_bound": sum(1 for _, x in recs if x > REC_MAX_US),
            "no_recovery_in_window": no_rec,
            "worst_peak_v": wp, "worst_peak_at": None,
            "worst_rec_us": None if not wr else wr[1],
            "worst_rec_at": None if not wr else f'{wr[0]["corner_id"]}/{wr[0]["leg"]}',
            "invalid": [f'{r["corner_id"]}/{r["leg"]}: {r["reason"]}' for r in rs if r["reason"]][:20],
        }
        if wp is not None:
            e = next(r for r in okp if wp in (r["peak_rise_v"], r["peak_fall_v"]))
            loadstep_stats[design]["worst_peak_at"] = f'{e["corner_id"]}/{e["leg"]}'

    verdict = {
        "issue": 704,
        "generated_from": [str(p.relative_to(HERE)) for p in sorted(HERE.glob("runs/*/*/provenance.json"))],
        "loop_gain": {"stats": loop_stats, "pair_classification": pair,
                      "decoupled_check": dec},
        "psrr": {"stats": psrr_stats},
        "load_step": {"stats": loadstep_stats},
        "bounds": {
            "loop": f"PM >= {PM_MIN:g} deg, GM >= {GM_MIN:g} dB (spec/target-spec.md Stability row; "
                    "the issue table's 'GM >= 10 deg' is graded as 10 dB per the spec unit)",
            "load_step": f"peak <= {PEAK_MAX_V*1000:g} mV, recovery into +-1 % within {REC_MAX_US:g} us",
            "psrr": f"strictly > {PSRR_1K_MIN:g} dB @ 1 kHz and > {PSRR_100K_MIN:g} dB @ 100 kHz",
        },
        "coverage": {
            "loop_gain": f"tt/27C/{VSUP:.2f}V only, 42 conditions per DUT (the issue's pinned grid); "
                         "PVT corners of sim/loop-gain/experiment.json not attempted",
            "load_step": "the 6-leg window grid at the manifest's own quick_subset "
                         f"{LOADSTEP_QUICK}; the other 42 of the 45-corner matrix not attempted",
            "psrr": "full 45-corner matrix x both loads per DUT at the bench's own load network "
                    "(C_out 1 uF / ESR 10 mOhm)",
        },
    }
    (HERE / "verdict.json").write_text(json.dumps(verdict, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: verdict[k] for k in ("loop_gain", "psrr", "load_step")},
                     indent=1)[:4000])
    print("tables:", *(str(p.name) for p in sorted(tables.glob("*.csv"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
