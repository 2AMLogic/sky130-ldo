#!/usr/bin/env python3
"""Issue #349: render tables from runs/*/result.json (read-only).

    python3 -I compare.py <this-directory> > tables.md

Never edits runs/. INVALID points print as INVALID and are never graded PASS.
PASS/FAIL is against the ratified Stability row (PM >= 45 deg, GM >= 10 dB) and the
Iq row (< 30 uA), only at the conditions actually run.
"""
import json
import sys
from pathlib import Path

PM_MIN, GM_MIN, IQ_MAX = 45.0, 10.0, 30.0
CONDS = [("tt", "tt/27C/3.30V"), ("ss", "ss/-40C/2.97V"), ("ff", "ff/125C/3.63V")]
VARIANTS = [("base", "baseline"), ("r1", "R1 (Ra/Rb 0.5/0.5, tap W=6)"), ("r2", "R2 (Ra/Rb 0.4/0.6, tap W=4)")]


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
    return f"{p['pm_deg']:.1f}/{p['gm_db']:.1f}/{p['crossover_hz']:.3g} {'P' if ok else 'F'}"


def main(d):
    runs = load(d)
    print("# Generated tables (compare.py; read-only over runs/)\n")
    print("Cell = PM deg / GM dB / crossover Hz, then P/F against PM>=45 and GM>=10 at that single point; "
          "`INVALID` = missing crossing / non-regulating / solver diagnostic (never a pass).\n")
    for cid, clabel in CONDS:
        ids = [f"lg_{v}_{cid}" for v, _ in VARIANTS]
        if not all(i in runs for i in ids):
            print(f"## {clabel}: NOT RUN (missing {[i for i in ids if i not in runs]})\n")
            continue
        base = runs[ids[0]]
        print(f"## Loop gain, {clabel}\n")
        print("| leg | " + " | ".join(l for _, l in VARIANTS) + " |")
        print("|---|---|---|---|")
        for k, bp in enumerate(base["points"]):
            row = [cell(runs[i]["points"][k]) for i in ids]
            print(f"| {bp['leg']} {bp['label']} | " + " | ".join(row) + " |")
        print()
        print(f"### Control node and effective R_CZ, {clabel}\n")
        print("Reff/Ra = 1 + (R_b||switch)/R_a from the AC voltage-drop ratio at 0.01 Hz; Reff = Reff/Ra x R_a "
              "(R_a nominal at tt/27C = 150.2k x frac/0.5 -- exact only at tt; the ratio is the primary datum). "
              "Baseline R_CZ = 300.6k (tt/27C calibration).\n")
        print("| leg | R1 V(ADAPT_G) | R1 Reff/Ra | R1 Reff(k, tt-cal) | R2 V(ADAPT_G) | R2 Reff/Ra | R2 Reff(k, tt-cal) |")
        print("|---|---|---|---|---|---|---|")
        r1, r2 = runs[ids[1]], runs[ids[2]]
        seen = set()
        for k, bp in enumerate(base["points"]):
            if bp["rload_ohm"] in seen and bp["cout_f"] != 0.33e-6:
                pass
            p1, p2 = r1["points"][k], r2["points"][k]
            if bp["esr_ohm"] != 0.01:
                continue
            def f(p, frac):
                if p.get("v_adapt_g") is None or p.get("reff_over_ra") is None:
                    return "n/a | n/a | n/a"
                return f"{p['v_adapt_g']:.3f} | {p['reff_over_ra']:.3f} | {300.6 * frac * p['reff_over_ra'] / 2:.1f}"
            print(f"| {bp['label']} | {f(p1, 0.5)} | {f(p2, 0.4)} |")
        print()
        print(f"### Absolute Iq from the explicit loop-gain `op` (VIN current - VOUT/RLOAD), {clabel}\n")
        print("| load | baseline (uA) | R1 (uA) | R1 delta (uA) | R2 (uA) | R2 delta (uA) | baseline <30 | R1 <30 | R2 <30 |")
        print("|---|---|---|---|---|---|---|---|---|")
        for k, bp in enumerate(base["points"]):
            if not (bp["cout_f"] == 0.33e-6 and bp["esr_ohm"] == 0.01):
                continue
            vals = [runs[i]["points"][k].get("iq_a") for i in ids]
            if any(v is None for v in vals):
                print(f"| {bp['label']} | INVALID |")
                continue
            u = [v * 1e6 for v in vals]
            yn = lambda x: "yes" if x < IQ_MAX else "NO"
            print(f"| {bp['label'].split('/')[-1]} | {u[0]:.3f} | {u[1]:.3f} | {u[1]-u[0]:+.3f} | {u[2]:.3f} | {u[2]-u[0]:+.3f} | "
                  f"{yn(u[0])} | {yn(u[1])} | {yn(u[2])} |")
        print()
    print("## sim/iq cold-start settled transient (manifest analyses verbatim)\n")
    print("| condition | variant | Iq 0 mA (uA) | delta | Iq 50 mA (uA) | delta | VOUT 0/50 mA (V) | valid |")
    print("|---|---|---|---|---|---|---|---|")
    for cid, clabel in CONDS:
        b = runs.get(f"iq_base_{cid}")
        for v, vl in VARIANTS:
            r = runs.get(f"iq_{v}_{cid}")
            if not r:
                print(f"| {clabel} | {vl} | NOT RUN | | | | | |")
                continue
            m = r["meas"]
            if not r["valid"]:
                print(f"| {clabel} | {vl} | INVALID | | | | | no ({r.get('missing_measurements')}; diag={r['solver_diagnostic']}) |")
                continue
            d0 = m["iq_no_load_ua"] - b["meas"]["iq_no_load_ua"]
            d1 = m["iq_full_load_ua"] - b["meas"]["iq_full_load_ua"]
            print(f"| {clabel} | {vl} | {m['iq_no_load_ua']:.3f} | {d0:+.3f} | {m['iq_full_load_ua']:.3f} | {d1:+.3f} | "
                  f"{m['vout_no_load_v']:.4f}/{m['vout_full_load_v']:.4f} | yes |")
    print()
    print("## sim/current-limit (manifest analyses verbatim)\n")
    names = ["vout_50ma_v", "cl_margin_50ma_v", "ilim_short_ma", "ilim_knee_ma", "ilim_droop_pct",
             "ishort_sustained_ma", "ishort_ripple_pct", "vout_short_mv", "isup_pre_short_ma"]
    print("| condition | variant | " + " | ".join(names) + " | valid |")
    print("|---|---|" + "---|" * (len(names) + 1))
    for cid, clabel in CONDS:
        for v, vl in VARIANTS:
            r = runs.get(f"cl_{v}_{cid}")
            if not r:
                print(f"| {clabel} | {vl} | NOT RUN |" + " |" * len(names))
                continue
            m = r["meas"]
            print(f"| {clabel} | {vl} | " + " | ".join(f"{m[n]:.5g}" if n in m else "MISSING" for n in names) +
                  f" | {'yes' if r['valid'] else 'NO ' + str(r.get('missing_measurements')) + str(r['solver_diagnostic'])} |")
    print()
    print("## sim/load-transient 1<->50 mA window grid (manifest analyses verbatim), rise = 1->50 mA, fall = 50->1 mA\n")
    legs = ["c330n_esr0", "c330n_esr10m", "c330n_esr500m", "c4u7_esr0", "c4u7_esr10m", "c4u7_esr500m"]
    items = ["undershoot_rise_v", "overshoot_fall_v", "recovery_rise_us", "recovery_fall_us", "settle_err_50ma_pct"]
    for it in items:
        print(f"### {it}\n")
        print("| condition | variant | " + " | ".join(legs) + " | valid |")
        print("|---|---|" + "---|" * (len(legs) + 1))
        for cid, clabel in CONDS:
            for v, vl in VARIANTS:
                r = runs.get(f"lt_{v}_{cid}")
                if not r:
                    print(f"| {clabel} | {vl} | NOT RUN |" + " |" * len(legs))
                    continue
                m = r["meas"]
                print(f"| {clabel} | {vl} | " + " | ".join(f"{m[f'{it}__{l}']:.5g}" if f"{it}__{l}" in m else "MISSING" for l in legs) +
                      f" | {'yes' if r['valid'] else 'NO'} |")
        print()
    print("## Existing sense path as control signal (sense_probe.py, one `op` per load; tap rows add the candidate control circuit)\n")
    print("Isense = current through the 0 V monitor in M_SENSE's drain. dCL_SNS / dCL_CMP = tap run minus baseline run "
          "(loading of the existing current-limit sense/compare nodes). Iq = -I(VVIN) - VOUT/RLOAD.\n")
    for cid, clabel in CONDS:
        b = runs.get(f"sense_base_{cid}" if cid != "tt" else "sense_base_tt_v3")
        if not b:
            print(f"### {clabel}: NOT RUN\n")
            continue
        print(f"### {clabel}\n")
        print("| load (mA) | Isense (uA) | CL_SNS base (V) | CL_CMP base (V) | tap6 ADAPT_G (V) | tap6 dCL_SNS (mV) | tap6 dCL_CMP (mV) | tap6 dIq (uA) | tap4 ADAPT_G (V) | tap4 dCL_SNS (mV) | tap4 dIq (uA) |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        t6, t4 = runs.get(f"sense_tap6_{cid}"), runs.get(f"sense_tap4_{cid}")
        for k, bl in enumerate(b["legs"]):
            def g(t, key):
                x = t["legs"][k] if t else None
                return x
            if not bl["valid"]:
                print(f"| {bl['load_nominal_a']*1e3:g} | INVALID |")
                continue
            x6, x4 = g(t6, 0), g(t4, 0)
            row = f"| {bl['load_nominal_a']*1e3:.3g} | {-bl['isense_a']*1e6:.4f} | {bl['v_cl_sns']:.4f} | {bl['v_cl_cmp']:.4f} | "
            for x, full in ((x6, True), (x4, False)):
                if not x or not x["valid"]:
                    row += "INVALID | " + ("| | | " if full else "| ")
                    continue
                if full:
                    row += (f"{x['v_adapt_g']:.3f} | {(x['v_cl_sns']-bl['v_cl_sns'])*1e3:+.2f} | "
                            f"{(x['v_cl_cmp']-bl['v_cl_cmp'])*1e3:+.2f} | {(x['iq_a']-bl['iq_a'])*1e6:+.3f} | ")
                else:
                    row += f"{x['v_adapt_g']:.3f} | {(x['v_cl_sns']-bl['v_cl_sns'])*1e3:+.2f} | {(x['iq_a']-bl['iq_a'])*1e6:+.3f} |"
            print(row)
        print()
    print("## Provenance index\n")
    print("| run | bench | condition | source commit | driver sha256 | netlist.edited sha256 | deck sha256 | ngspice exit | solver diag |")
    print("|---|---|---|---|---|---|---|---|---|")
    for rid, r in runs.items():
        pv = r.get("provenance", {})
        c = r["condition"]
        print(f"| `{rid}` | {r['bench']} | {c['process']}/{c['temp_c']:g}C/{c['supply_v']} | `{pv.get('source_commit','')[:9]}` | "
              f"`{pv.get('driver_sha256','')[:12]}` | `{pv.get('netlist_edited_sha256','')[:12]}` | `{pv.get('deck_sha256','')[:12]}` | "
              f"{r['ngspice_exit']} | {r['solver_diagnostic']} |")


if __name__ == "__main__":
    main(sys.argv[1])
