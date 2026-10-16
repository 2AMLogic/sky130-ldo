#!/usr/bin/env python3
"""Issue #365 bounded light-load probe (ONE ngspice -b per invocation, ONE PVT condition).

Re-uses the #349 driver's netlisting/classification helpers READ-ONLY and the #360
crossing extractor; adds node-resolved responses for the mechanism, and three
netlist-level testbench levers (the design/ schematic is never edited):

  --ccomp-scale S   C_COMP x S         (design 150p)
  --rcz-scale S     R_CZ length x S   (design L=52 um)
  --tail-scale S    M_TAIL width x S  (design W=40 um nf=8): amplifier tail current lever

Benches: loop-gain (a fixed 10-leg set, see LEGS), iq and load-transient (the repo
manifests' own analyses, verbatim).  Evidence dirs are append-only.

  lightload_probe.py --outdir DIR --run-id ID --process tt --temp 27 --supply 3.3 \
      [--bench loop-gain|iq|load-transient] [--tail-scale S] [--ccomp-scale S] [--rcz-scale S]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SIM = REPO / "sim"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


DIAG = SIM / "loop-gain" / "diagnostics"
ap = _load("adaptive_probe", next(DIAG.glob("*-adaptive-comp")) / "adaptive_probe.py")
ce = _load("crossing_extract", next(DIAG.glob("*-missing-crossing")) / "crossing_extract.py")
ll = _load("lightload_extract", HERE / "lightload_extract.py")
cr = ap.cr

# (cout, esr, rload, label): 0 mA at both endpoints and the three ratified ESR values,
# plus 1 mA and 50 mA regression controls at ESR 10 mOhm.
LEGS = [
    (0.33e-6, 0.010, 1e12, "0.33u/10m/0mA"), (4.7e-6, 0.010, 1e12, "4.7u/10m/0mA"),
    (0.33e-6, 0.0, 1e12, "0.33u/0/0mA"), (4.7e-6, 0.0, 1e12, "4.7u/0/0mA"),
    (0.33e-6, 0.5, 1e12, "0.33u/500m/0mA"), (4.7e-6, 0.5, 1e12, "4.7u/500m/0mA"),
    (0.33e-6, 0.010, 1800.0, "0.33u/10m/1mA"), (4.7e-6, 0.010, 1800.0, "4.7u/10m/1mA"),
    (0.33e-6, 0.010, 36.0, "0.33u/10m/50mA"), (4.7e-6, 0.010, 36.0, "4.7u/10m/50mA"),
]
NODES = ["xldo.ea_out", "xldo.ea_cz", "vout", "xldo.fb", "xldo.ea_d1", "xldo.ea_tail"]
FMAX = 1e9
VOUT_LO, VOUT_HI = 1.7, 1.9   # same operating-point gate as #349 classify_ac


def edit_netlist(text, ccomp, rcz, tail):
    notes = []
    lines = text.splitlines()
    if ccomp != 1.0:
        s, _ = ap.find_card(lines, "C_COMP VOUT EA_CZ 150p")
        lines[s] = lines[s].replace("150p", f"{150 * ccomp:g}p", 1)
        notes.append(f"C_COMP 150p -> {150 * ccomp:g}p")
    if rcz != 1.0:
        s, e = ap.find_card(lines, "XR_CZ EA_CZ EA_OUT 0 sky130_fd_pr__res_xhigh_po W=0.42 L=52 ")
        lines[s] = lines[s].replace("L=52 ", f"L={52 * rcz:g} ", 1)
        notes.append(f"R_CZ L 52 -> {52 * rcz:g} (W=0.42)")
    if tail != 1.0:
        s, e = ap.find_card(lines, "XM_TAIL EA_TAIL BIASP VIN VIN ")
        blk = " ".join(lines[s:e])
        assert " W=40 " in blk, "XM_TAIL W=40 not found"
        new = blk.replace(" W=40 ", f" W={40 * tail:g} ", 1)
        lines[s:e] = [new]
        notes.append(f"M_TAIL W 40 -> {40 * tail:g} um (nf=8 unchanged; ad/as/pd/ps left at design values)")
    return "\n".join(lines) + "\n", notes


def deck_analyses(legs):
    out = ["set numdgt=10", "set units=degrees", "set wr_vecnames", "set wr_singlescale"]
    vecs = " ".join(["lg"] + [f"v({n})" for n in NODES])
    for n, (cout, esr, rload, label) in enumerate(legs, start=1):
        out += [f"* --- leg {n}: {label} ---",
                f"alter cout = {cout:g}", f"alter hesr gain = {esr:g}", f"alter rload = {rload:g}",
                "op", "let vseed = v(vout)", "let ivin = -i(vvin)", f"echo PT{n}_OP", "print vseed ivin",
                f"ac dec 30 1e-2 {FMAX:g}",
                "let lg = v(xldo.fb)/(1-v(xldo.fb))", "let lgdb = db(lg)", "let lgph = cph(lg)",
                f"wrdata resp_leg{n}.txt {vecs}",
                "meas ac fc when lgdb=0 cross=1",
                "meas ac phc find lgph when lgdb=0 cross=1",
                "meas ac gmdb find lgdb when lgph=-180 cross=1",
                "let dcg = lgdb[0]", f"echo PT{n}_AC", "print fc", "print phc", "print gmdb", "print dcg"]
    return out


def classify_response(resp, vout_v):
    """Margin classification from the saved response.  Missing crossings stay invalid."""
    reasons = []
    if vout_v is None or not (VOUT_LO <= vout_v <= VOUT_HI):
        reasons.append(f"VOUT outside the validity window ({vout_v})")
    if resp is None:
        reasons.append("no response")
        return {"valid": False, "reasons": reasons, "pm_pass": None, "gm_pass": None}
    if resp.get("pm_deg") is None:
        reasons.append("no unity-gain crossing (PM undefined)")
    if not resp.get("gm_supported"):
        reasons.append(f"no usable gain-margin crossing ({resp.get('status')}); GM undefined, not a pass")
    valid = not reasons
    return {"valid": valid, "reasons": reasons,
            "pm_pass": (resp["pm_deg"] >= 45.0) if resp.get("pm_deg") is not None and not
            [r for r in reasons if r.startswith("VOUT")] else None,
            "gm_pass": (resp["worst_gm_db"] >= 10.0) if valid else None}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--bench", choices=["loop-gain", "iq", "load-transient"], default="loop-gain")
    a.add_argument("--outdir", required=True)
    a.add_argument("--run-id", required=True)
    a.add_argument("--process", required=True)
    a.add_argument("--temp", type=float, required=True)
    a.add_argument("--supply", type=float, required=True)
    a.add_argument("--ccomp-scale", type=float, default=1.0)
    a.add_argument("--rcz-scale", type=float, default=1.0)
    a.add_argument("--tail-scale", type=float, default=1.0)
    a.add_argument("--timeout", type=int, default=900)
    o = a.parse_args()

    run = Path(o.outdir) / "runs" / o.run_id
    if run.exists():
        sys.exit(f"{run} exists: evidence is append-only, pick a new --run-id")
    run.mkdir(parents=True)
    pin = cr.load_pin()
    pdk = cr.resolve_pdk(pin)
    exp = cr.load_experiment(SIM / o.bench)
    net = cr.netlist_with_xschem(exp.schematic, run / "xschem", pdk)
    raw_text = "\n".join(cr.netlist_body(net)) + "\n"
    (run / "netlist.raw.spice").write_text(raw_text)
    edited, notes = edit_netlist(raw_text, o.ccomp_scale, o.rcz_scale, o.tail_scale)
    (run / "netlist.edited.spice").write_text(edited)
    shutil.rmtree(run / "xschem")
    corner = cr.Corner(o.process, o.temp, o.supply)
    analyses = None
    if o.bench == "loop-gain":
        analyses = deck_analyses(LEGS)
        exp.raw["deck"]["analyses"] = analyses
        exp.measurements = []
    (run / "deck.spice").write_text(cr.build_deck(exp, pdk, corner, edited.splitlines()))
    shutil.copy(SIM / "spiceinit", run / ".spiceinit")

    t0 = time.monotonic()
    p = subprocess.run(["ngspice", "-b", "deck.spice"], cwd=run, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=o.timeout)
    elapsed = time.monotonic() - t0
    log = p.stdout + "\n" + p.stderr
    (run / "ngspice.log").write_text(log)
    diag = cr.detect_solver_diagnostic(log)

    rec = {
        "run_id": o.run_id, "issue": 365, "bench": o.bench,
        "condition": {"process": o.process, "temp_c": o.temp, "supply_v": o.supply},
        "edits": {"ccomp_scale": o.ccomp_scale, "rcz_scale": o.rcz_scale, "tail_scale": o.tail_scale, "notes": notes},
        "stimulus": analyses if analyses else f"verbatim from sim/{o.bench}/experiment.json (see deck.spice)",
        "provenance": {
            "source_commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
            "driver_sha256": ap.sha(Path(__file__).read_bytes()),
            "extract_sha256": ap.sha((HERE / "lightload_extract.py").read_bytes()),
            "experiment_json_sha256": ap.sha((SIM / o.bench / "experiment.json").read_bytes()),
            "testbench_sha256": ap.sha(exp.schematic.read_bytes()),
            "dut_sha256": ap.sha((REPO / "design" / "ldo_3v3in_1v8out.sch").read_bytes()),
            "netlist_raw_sha256": ap.sha(raw_text.encode()),
            "netlist_edited_sha256": ap.sha(edited.encode()),
            "deck_sha256": ap.sha((run / "deck.spice").read_bytes()),
            "pdk": {"open_pdks_commit": pdk.installed_commit, "matches_pin": pdk.matches_pin},
            "tools": cr.tool_versions(),
        },
        "ngspice_exit": p.returncode, "elapsed_s": round(elapsed, 2), "solver_diagnostic": diag,
    }
    if o.bench == "loop-gain":
        vals = ap.parse_legs(log, False)
        pts = []
        for n, leg in enumerate(LEGS, start=1):
            cout, esr, rload, label = leg
            v = vals.get(n, {})
            pt = {"leg": n, "label": label, "cout_f": cout, "esr_ohm": esr, "rload_ohm": rload,
                  "vout_v": v.get("vseed"), "vin_current_a": v.get("ivin")}
            if v.get("vseed") is not None and v.get("ivin") is not None:
                pt["iq_a"] = v["ivin"] - v["vseed"] / rload
            f = run / f"resp_leg{n}.txt"
            if f.exists() and not diag:
                fr, cols = ll.read_wrdata_nodes(f.read_text(), 1 + len(NODES))
                lre, lim = cols[0]
                resp = ce.analyze(fr, lre, lim)
                pt["response"] = resp
                pt["phase_dip"] = ll.phase_dip(fr, lre, lim)
                g = ll.mag_db(lre, lim)
                pt["corners"] = ll.slope_corners(fr, g)
                pt["doublet_candidates"] = ll.doublet_candidates(pt["corners"])
                pt["nodes"] = ll.node_contributions(fr, dict(zip(NODES, cols[1:])), resp.get("crossover_hz"))
            else:
                pt["response"] = None
            pt["scalar_meas"] = {k: v.get(k) for k in ("fc", "phc", "gmdb", "dcg")}
            pt["classification"] = classify_response(pt["response"], pt["vout_v"])
            if diag:
                pt["classification"]["valid"] = False
                pt["classification"]["reasons"].append("solver diagnostic: " + diag)
            pts.append(pt)
        rec["points"] = pts
        for x in pts:
            r = x["response"] or {}
            c = x["classification"]
            print(f"{x['label']:>16} valid={c['valid']!s:5} vout={x['vout_v']} iq_uA={(x.get('iq_a') or float('nan'))*1e6:.3f} "
                  f"status={r.get('status')} pm={r.get('pm_deg')} gm={r.get('gm_db')} fc={r.get('crossover_hz')} "
                  f"dip={x.get('phase_dip', {}).get('min_phase_deg')} {c['reasons']}")
    else:
        rec["meas"] = cr.parse_measurements(log)
        print(rec["meas"])
    (run / "result.json").write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps({k: rec[k] for k in ("run_id", "ngspice_exit", "elapsed_s", "solver_diagnostic")}))


if __name__ == "__main__":
    main()
