#!/usr/bin/env python3
"""Issue #324 single-condition diagnostic probe (one ngspice -b per invocation).

Netlists the CURRENT schematic's loop-gain testbench (sim/loop-gain/testbench/
tb_loop_gain.sch) with the repo's own xschem flow, applies explicit netlist-level
testbench edits (never touching design/), runs the canonical seven-point
loop-gain deck from sim/loop-gain/experiment.json (verbatim analyses, with
extra operating-point prints for VIN-current / load accounting) at ONE
process/temperature/supply condition, and writes an append-only run directory.

Edits (all optional, testbench-only):
  --bleed-ua X     fixed internal bleed, resistor VOUT->0 of 1.8/X Mohm
                   (X uA equivalent at VOUT = 1.8 V). Not external load.
  --ccomp-scale S  C_COMP value x S    (design value 150p)
  --rcz-scale S    R_CZ length  x S    (design L = 52 um, W = 0.42 um)

Usage:
  mitigation_probe.py --outdir DIR --run-id ID --process tt --temp 27 --supply 3.3
                      [--bleed-ua 3] [--ccomp-scale 2] [--rcz-scale 0.5]
  mitigation_probe.py ... --bench iq    # sim/iq transient cross-check instead

Invalid-by-construction rules (never PASS): see classify() below.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SIM = REPO / "sim"
sys.path.insert(0, str(SIM / "bin"))
_spec = importlib.util.spec_from_file_location("corner_run", SIM / "bin" / "corner-run.py")
cr = importlib.util.module_from_spec(_spec)
sys.modules["corner_run"] = cr
_spec.loader.exec_module(cr)

# (point id, C_out, ESR, nominal R_LOAD ohm) -- order and values from experiment.json
POINTS = [
    (1, 0.33e-6, 0.010, 36.0),
    (2, 0.33e-6, 0.010, 1800.0),
    (3, 0.33e-6, 0.010, 1e12),
    (4, 4.7e-6, 0.010, 36.0),
    (5, 4.7e-6, 0.010, 1800.0),
    (6, 4.7e-6, 0.010, 1e12),
    (7, 0.33e-6, 0.500, 36.0),
]
NUM = r"-?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|-?inf|nan"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def edit_netlist(text: str, bleed_ua: float, ccomp: float, rcz: float):
    notes = []
    if ccomp != 1.0:
        text, n = re.subn(r"^(C_COMP VOUT EA_CZ )150p", lambda m: m.group(1) + f"{150 * ccomp:g}p", text, flags=re.M)
        assert n == 1, "C_COMP line not found"
        notes.append(f"C_COMP 150p -> {150 * ccomp:g}p")
    if rcz != 1.0:
        text, n = re.subn(r"^(XR_CZ EA_CZ EA_OUT 0 sky130_fd_pr__res_xhigh_po W=0.42 L=)52\b",
                          lambda m: m.group(1) + f"{52 * rcz:g}", text, flags=re.M)
        assert n == 1, "XR_CZ line not found"
        notes.append(f"R_CZ L 52 -> {52 * rcz:g} (W=0.42)")
    if bleed_ua > 0:
        rb = 1.8 / (bleed_ua * 1e-6)
        text, n = re.subn(r"^(RLOAD VOUT 0 36 m=1)$", lambda m: m.group(1) + f"\nRBLEED VOUT 0 {rb:g}", text, flags=re.M)
        assert n == 1, "RLOAD line not found"
        notes.append(f"RBLEED VOUT-0 {rb:g} ohm ({bleed_ua} uA @ 1.8 V)")
    return text, notes


def loop_gain_analyses(exp_raw: dict) -> list[str]:
    out = ["set numdgt=10"]
    pt = 0
    for ln in exp_raw["deck"]["analyses"]:
        out.append(ln)
        if ln.strip() == "op":
            pt += 1
            out += ["let vseed = v(vout)", "let ivin = -i(vvin)",
                    f"echo PT{pt}_OP", "print vseed ivin"]
        if ln.startswith("meas ac gmdb"):
            out += ["let dcg = lgdb[0]", f"echo PT{pt}_AC", "print fc phc gmdb dcg"]
    return out


def parse_points(log: str) -> dict:
    res = {}
    segs = re.split(r"^PT(\d+)_(OP|AC)\s*$", log, flags=re.M)
    # segs: [pre, n, kind, body, n, kind, body ...]
    for i in range(1, len(segs), 3):
        n, kind, body = int(segs[i]), segs[i + 1], segs[i + 2]
        d = res.setdefault(n, {})
        for name in ("vseed", "ivin", "fc", "phc", "gmdb", "dcg"):
            m = re.search(rf"^{name}\s*=\s*({NUM})\s*$", body, flags=re.M)
            if m and name not in d:
                d[name] = float(m.group(1))
    return res


def classify(pt, vals, vin, rload, bleed_ua, diag):
    """Return the per-point record. Any missing/unphysical piece => INVALID."""
    reasons = []
    vout = vals.get("vseed")
    r = {"point": pt[0], "cout_f": pt[1], "esr_ohm": pt[2], "rload_ohm": rload,
         "vout_v": vout, "vin_current_a": vals.get("ivin"),
         "crossover_hz": vals.get("fc"), "dc_loop_gain_db": vals.get("dcg")}
    if vout is None or vals.get("ivin") is None:
        reasons.append("operating point not printed")
    else:
        if not (1.7 <= vout <= 1.9):
            reasons.append(f"non-regulating operating point (VOUT={vout:.4f} V, VIN={vin} V)")
        iload = vout / rload
        r["external_load_a"] = iload
        r["iq_a"] = vals["ivin"] - iload
        r["bleed_a_nominal"] = (vout / (1.8 / (bleed_ua * 1e-6))) if bleed_ua else 0.0
    if "fc" not in vals:
        reasons.append("no unity-gain crossing (fc missing)")
    if "phc" not in vals:
        reasons.append("phase at crossing missing")
    else:
        r["pm_deg"] = 180.0 + vals["phc"]
    if "gmdb" not in vals:
        reasons.append("no -180 deg phase crossing (GM missing)")
    else:
        r["gm_db"] = -vals["gmdb"]
    if diag:
        reasons.append("ngspice solver diagnostic present in run: " + diag)
    r["valid"] = not reasons
    r["invalid_reasons"] = reasons
    if r["valid"]:
        r["pm_ge_45"] = r["pm_deg"] >= 45.0
        r["gm_ge_10"] = r["gm_db"] >= 10.0
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--process", required=True)
    ap.add_argument("--temp", type=float, required=True)
    ap.add_argument("--supply", type=float, required=True)
    ap.add_argument("--bleed-ua", type=float, default=0.0)
    ap.add_argument("--ccomp-scale", type=float, default=1.0)
    ap.add_argument("--rcz-scale", type=float, default=1.0)
    ap.add_argument("--bench", choices=["loop-gain", "iq"], default="loop-gain")
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()

    run = Path(a.outdir) / "runs" / a.run_id
    if run.exists():
        sys.exit(f"{run} exists: evidence is append-only, pick a new --run-id")
    run.mkdir(parents=True)

    pin = cr.load_pin()
    pdk = cr.resolve_pdk(pin)
    slug = "loop-gain" if a.bench == "loop-gain" else "iq"
    exp = cr.load_experiment(SIM / slug)
    tbdir = run / "xschem"
    net = cr.netlist_with_xschem(exp.schematic, tbdir, pdk)
    raw_text = "\n".join(cr.netlist_body(net)) + "\n"
    raw_text_full = raw_text
    (run / "netlist.raw.spice").write_text(raw_text_full)
    edited, notes = edit_netlist(raw_text, a.bleed_ua, a.ccomp_scale, a.rcz_scale)
    (run / "netlist.edited.spice").write_text(edited)
    shutil.rmtree(tbdir)
    corner = cr.Corner(a.process, a.temp, a.supply)
    body = edited.splitlines()

    if a.bench == "loop-gain":
        exp.raw["deck"]["analyses"] = loop_gain_analyses(exp.raw)
        exp.measurements = []
    deck = cr.build_deck(exp, pdk, corner, body)
    (run / "deck.spice").write_text(deck)
    shutil.copy(SIM / "spiceinit", run / ".spiceinit")

    t0 = time.monotonic()
    p = subprocess.run(["ngspice", "-b", "deck.spice"], cwd=run, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=a.timeout)
    elapsed = time.monotonic() - t0
    log = p.stdout + "\n" + p.stderr
    (run / "ngspice.log").write_text(log)
    diag = cr.detect_solver_diagnostic(log)

    git_sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    rec = {
        "run_id": a.run_id, "bench": a.bench, "issue": 324,
        "condition": {"process": a.process, "temp_c": a.temp, "supply_v": a.supply},
        "edits": {"bleed_ua": a.bleed_ua, "ccomp_scale": a.ccomp_scale, "rcz_scale": a.rcz_scale, "notes": notes},
        "provenance": {
            "source_commit": git_sha,
            "driver_sha256": sha(Path(__file__).read_bytes()),
            "experiment_json_sha256": sha((SIM / slug / "experiment.json").read_bytes()),
            "testbench_sha256": sha(exp.schematic.read_bytes()),
            "dut_sha256": sha((REPO / "design" / "ldo_3v3in_1v8out.sch").read_bytes()),
            "netlist_raw_sha256": sha(raw_text_full.encode()),
            "netlist_edited_sha256": sha(edited.encode()),
            "deck_sha256": sha((run / "deck.spice").read_bytes()),
            "spiceinit_sha256": sha((SIM / "spiceinit").read_bytes()),
            "pdk": {"open_pdks_commit": pdk.installed_commit, "matches_pin": pdk.matches_pin},
            "tools": cr.tool_versions(),
        },
        "ngspice_exit": p.returncode, "elapsed_s": round(elapsed, 2),
        "solver_diagnostic": diag,
    }
    if a.bench == "loop-gain":
        vals = parse_points(log)
        rec["points"] = [classify(pt, vals.get(pt[0], {}), a.supply, pt[3], a.bleed_ua, diag) for pt in POINTS]
        # Iq accounting only meaningful at 0 and 50 mA points
        rec["valid_all"] = all(x["valid"] for x in rec["points"])
    else:
        meas = cr.parse_measurements(log)
        rec["meas"] = meas
        rec["valid"] = (p.returncode == 0 and not diag and all(k in meas for k in
                        ("vout_no_load_v", "iq_no_load_ua", "vout_full_load_v", "iq_full_load_ua")))
    (run / "result.json").write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps({k: rec[k] for k in ("run_id", "ngspice_exit", "elapsed_s", "solver_diagnostic")}))
    if a.bench == "loop-gain":
        for x in rec["points"]:
            print(f"P{x['point']} valid={x['valid']} vout={x.get('vout_v')} pm={x.get('pm_deg')} "
                  f"gm={x.get('gm_db')} fc={x.get('crossover_hz')} iq_uA={(x.get('iq_a') or float('nan'))*1e6:.3f} "
                  f"{x['invalid_reasons']}")
    else:
        print(rec["meas"], rec["valid"])


if __name__ == "__main__":
    main()
