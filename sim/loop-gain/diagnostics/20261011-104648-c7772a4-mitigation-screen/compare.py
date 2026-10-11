#!/usr/bin/env python3
"""Issue #324: render comparison tables from runs/*/result.json (read-only).

    python3 -I compare.py <this-directory> > tables.md

Only reads; never edits runs/. INVALID points are printed as INVALID and are
never graded PASS. PASS/FAIL columns are against the ratified Stability row
(PM >= 45 deg, GM >= 10 dB) and the Iq row (< 30 uA), reported only at the
conditions actually run.
"""
import json
import sys
from pathlib import Path

LABEL = {1: "0.33uF/10m/50mA", 2: "0.33uF/10m/1mA", 3: "0.33uF/10m/0mA",
         4: "4.7uF/10m/50mA", 5: "4.7uF/10m/1mA", 6: "4.7uF/10m/0mA",
         7: "0.33uF/500m/50mA"}
PM_MIN, GM_MIN, IQ_MAX_UA = 45.0, 10.0, 30.0


def load(d):
    out = {}
    for f in sorted((Path(d) / "runs").glob("*/result.json")):
        r = json.load(open(f))
        out[r["run_id"]] = r
    return out


def cell(p):
    if not p["valid"]:
        return "INVALID"
    ok = p["pm_deg"] >= PM_MIN and p["gm_db"] >= GM_MIN
    return f"{p['pm_deg']:.1f} / {p['gm_db']:.1f} / {p['crossover_hz']:.4g} {'PASS' if ok else 'FAIL'}"


def table_pm(runs, ids, title):
    print(f"\n### {title}\n")
    print("Cell = PM deg / GM dB / crossover Hz, then PASS/FAIL against PM>=45 and GM>=10 at that single point.\n")
    print("| run | " + " | ".join(LABEL[i] for i in range(1, 8)) + " |")
    print("|---|" + "---|" * 7)
    for rid in ids:
        r = runs[rid]
        print(f"| `{rid}` | " + " | ".join(cell(p) for p in r["points"]) + " |")


def iq_ua(r, pt):
    p = r["points"][pt - 1]
    return p["iq_a"] * 1e6 if p["valid"] else None


def table_iq(runs, ids, base_id, title):
    print(f"\n### {title}\n")
    print("Iq = (VIN current from the seeded `op`) - VOUT/R_LOAD; internal bleed is NOT subtracted. "
          f"Budget < {IQ_MAX_UA:g} uA at no load and at 50 mA.\n")
    print("| run | Iq 0 mA (uA) | d vs base | Iq 50 mA (uA) | d vs base | bleed (uA) | 0 mA < 30 | 50 mA < 30 |")
    print("|---|---|---|---|---|---|---|---|")
    b = runs[base_id]
    for rid in ids:
        r = runs[rid]
        i0, i50 = iq_ua(r, 3), iq_ua(r, 1)
        b0, b50 = iq_ua(b, 3), iq_ua(b, 1)
        bleed = r["edits"]["bleed_ua"]

        def f(x):
            return "INVALID" if x is None else f"{x:.3f}"

        def d(x, y):
            return "n/a" if x is None or y is None else f"{x - y:+.3f}"

        def ok(x):
            return "INVALID" if x is None else ("yes" if x < IQ_MAX_UA else "NO")
        print(f"| `{rid}` | {f(i0)} | {d(i0, b0)} | {f(i50)} | {d(i50, b50)} | {bleed:g} | {ok(i0)} | {ok(i50)} |")


def table_pair(runs, pairs, title):
    print(f"\n### {title}\n")
    print("| condition | point | base PM | var PM | dPM | base GM | var GM | dGM | base fc | var fc |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for cond, bid, vid in pairs:
        for i in range(7):
            b, v = runs[bid]["points"][i], runs[vid]["points"][i]
            if b["valid"] and v["valid"]:
                print(f"| {cond} | {LABEL[i+1]} | {b['pm_deg']:.1f} | {v['pm_deg']:.1f} | {v['pm_deg']-b['pm_deg']:+.1f} | "
                      f"{b['gm_db']:.1f} | {v['gm_db']:.1f} | {v['gm_db']-b['gm_db']:+.1f} | "
                      f"{b['crossover_hz']:.4g} | {v['crossover_hz']:.4g} |")
            else:
                print(f"| {cond} | {LABEL[i+1]} | {'INVALID' if not b['valid'] else b['pm_deg']} | "
                      f"{'INVALID' if not v['valid'] else v['pm_deg']} | n/a | | | | | |")


def main():
    d = sys.argv[1]
    runs = load(d)
    print("## Operating-point validity and solver diagnostics (all loop-gain runs)\n")
    print("| run | ngspice exit | solver diagnostic | invalid points | min/max VOUT over 7 points (V) | VIN (V) |")
    print("|---|---|---|---|---|---|")
    for rid, r in runs.items():
        if r["bench"] != "loop-gain":
            continue
        vs = [p["vout_v"] for p in r["points"] if p["vout_v"] is not None]
        inv = [p["point"] for p in r["points"] if not p["valid"]]
        print(f"| `{rid}` | {r['ngspice_exit']} | {r['solver_diagnostic']} | {inv or 'none'} | "
              f"{min(vs):.4f} / {max(vs):.4f} | {r['condition']['supply_v']} |")
    table_pm(runs, ["base_tt_27C_3.30V", "base_ss_m40C_2.97V", "base_ff_125C_3.63V"],
             "Baseline (current schematic, no edits)")
    tt = "_tt_27C_3.30V"
    table_pm(runs, ["base" + tt] + [f"bleed{u}uA" + tt for u in (1, 3, 10)] + ["diagbleed100uA" + tt],
             "Bleed screen at tt/27C/3.30V (100 uA row is a mechanism probe outside the bound)")
    table_iq(runs, ["base" + tt] + [f"bleed{u}uA" + tt for u in (1, 3, 10)] + ["diagbleed100uA" + tt],
             "base" + tt, "Bleed screen Iq accounting at tt/27C/3.30V")
    table_pm(runs, ["base" + tt, "ccomp0p5" + tt, "ccomp2" + tt, "rcz0p5" + tt, "rcz2" + tt, "combo_rcz0p5_ccomp2" + tt],
             "Passive compensation screen at tt/27C/3.30V (one factor at a time; last row is the follow-up combination)")
    pairs = [("tt/27C/3.30V", "base" + tt, "rcz0p5" + tt),
             ("ss/-40C/2.97V", "base_ss_m40C_2.97V", "rcz0p5_ss_m40C_2.97V"),
             ("ff/125C/3.63V", "base_ff_125C_3.63V", "rcz0p5_ff_125C_3.63V")]
    table_pair(runs, pairs, "Variant V1 (R_CZ x0.5) vs paired baseline")
    pairs = [("tt/27C/3.30V", "base" + tt, "combo_rcz0p5_ccomp2" + tt),
             ("ss/-40C/2.97V", "base_ss_m40C_2.97V", "combo_rcz0p5_ccomp2_ss_m40C_2.97V"),
             ("ff/125C/3.63V", "base_ff_125C_3.63V", "combo_rcz0p5_ccomp2_ff_125C_3.63V")]
    table_pair(runs, pairs, "Variant V2 (R_CZ x0.5 and C_COMP x2) vs paired baseline")
    cond = [("tt/27C/3.30V", "base" + tt, "combo_rcz0p5_ccomp2" + tt, "rcz0p5" + tt),
            ("ss/-40C/2.97V", "base_ss_m40C_2.97V", "combo_rcz0p5_ccomp2_ss_m40C_2.97V", "rcz0p5_ss_m40C_2.97V"),
            ("ff/125C/3.63V", "base_ff_125C_3.63V", "combo_rcz0p5_ccomp2_ff_125C_3.63V", "rcz0p5_ff_125C_3.63V")]
    print("\n### Variant Iq accounting (absolute and delta vs paired baseline)\n")
    print("| condition | run | Iq 0 mA (uA) | d | Iq 50 mA (uA) | d | 0 mA < 30 | 50 mA < 30 |")
    print("|---|---|---|---|---|---|---|---|")
    for c, b, v2, v1 in cond:
        for rid in (b, v1, v2):
            r, bb = runs[rid], runs[b]
            i0, i50, b0, b50 = iq_ua(r, 3), iq_ua(r, 1), iq_ua(bb, 3), iq_ua(bb, 1)
            print(f"| {c} | `{rid}` | {i0:.3f} | {i0-b0:+.3f} | {i50:.3f} | {i50-b50:+.3f} | "
                  f"{'yes' if i0 < IQ_MAX_UA else 'NO'} | {'yes' if i50 < IQ_MAX_UA else 'NO'} |")
    print("\n### sim/iq transient cross-check (tt/27C/3.30V, baseline netlist)\n")
    for rid, r in runs.items():
        if r["bench"] == "iq":
            print(f"- `{rid}`: valid={r['valid']} meas={r['meas']}")


if __name__ == "__main__":
    main()
