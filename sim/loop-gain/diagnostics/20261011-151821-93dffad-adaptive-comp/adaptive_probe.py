#!/usr/bin/env python3
"""Issue #349 load-adaptive compensation prototype probe (one ngspice -b per invocation).

Netlists the repo's own testbench for the chosen bench with the repo's xschem flow,
applies explicit NETLIST-LEVEL edits (design/ is never touched), runs ngspice once at
ONE process/temperature/supply condition and writes an append-only run directory
(raw + edited netlist, deck, ngspice log, result.json with hashes/tool versions).

Prototype edit (all optional; with no edit flags the run is the unmodified baseline):

  --ra-frac F     split R_CZ: R_a (frac F of today's L=52 um) from EA_CZ to RCZ_MID,
                  R_b (frac 1-F) from RCZ_MID to EA_OUT, and a PDK-modelled PMOS
                  XM_CZSW (pfet_g5v0d10v5 L=0.5 W=--sw-w) across R_b, bulk VIN,
                  gate ADAPT_G.  Switch OFF (gate high) -> R_CZ ~= today's total;
                  switch ON (gate low) -> R_CZ ~= R_a only.
  --tap-w W       control circuit: XM_CLN3 (nfet_g5v0d10v5 L=1 W=W, gate CL_SNS,
                  source AMP_ENN, drain ADAPT_G) mirrors the existing sense diode
                  XM_CLN1's Vgs; XM_ADPU (pfet L=1 W=1.25, gate BIASP) pulls ADAPT_G
                  to VIN.  The tap's only loading of the sense node is the gate
                  capacitance of XM_CLN3 (no DC current); its Iq cost is the pull-up
                  current that flows to ground through XM_CLN3 once the mirror
                  current exceeds it, i.e. at load.
  --ccomp-scale S C_COMP x S (design 150p)

Benches: loop-gain (custom 18-leg #338 grid + 8 transition-region legs, op+ac per leg),
iq / current-limit / load-transient (the repo manifests' own analyses, verbatim).

Usage:
  adaptive_probe.py --bench loop-gain --outdir DIR --run-id ID --process tt --temp 27 \
      --supply 3.3 [--ra-frac 0.5 --tap-w 6 --sw-w 2 --ccomp-scale 1]

Invalid-by-construction rules (never PASS) live in classify_ac(); rejected/invalid
points are kept in result.json.
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

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SIM = REPO / "sim"
sys.path.insert(0, str(SIM / "bin"))
_spec = importlib.util.spec_from_file_location("corner_run", SIM / "bin" / "corner-run.py")
cr = importlib.util.module_from_spec(_spec)
sys.modules["corner_run"] = cr
_spec.loader.exec_module(cr)

NUM = r"-?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|-?inf|nan"
R_TOTAL_L_UM = 52.0
R_OHM_PER_UM_TT27 = 300.6e3 / 52.0  # rcz_resistance/ (issue #324): L=52 -> 300.6k at tt/27C

# (cout, esr, rload ohm, label) -- the #338 18-leg grid in manifest order
GRID18 = [
    (0.33e-6, 0.010, 36.0, "0.33u/10m/50mA"), (0.33e-6, 0.010, 1800.0, "0.33u/10m/1mA"),
    (0.33e-6, 0.010, 1e12, "0.33u/10m/0mA"), (4.7e-6, 0.010, 36.0, "4.7u/10m/50mA"),
    (4.7e-6, 0.010, 1800.0, "4.7u/10m/1mA"), (4.7e-6, 0.010, 1e12, "4.7u/10m/0mA"),
    (0.33e-6, 0.5, 36.0, "0.33u/500m/50mA"), (0.33e-6, 0.5, 1800.0, "0.33u/500m/1mA"),
    (0.33e-6, 0.5, 1e12, "0.33u/500m/0mA"), (4.7e-6, 0.5, 36.0, "4.7u/500m/50mA"),
    (4.7e-6, 0.5, 1800.0, "4.7u/500m/1mA"), (4.7e-6, 0.5, 1e12, "4.7u/500m/0mA"),
    (4.7e-6, 0.0, 36.0, "4.7u/0/50mA"), (4.7e-6, 0.0, 1800.0, "4.7u/0/1mA"),
    (4.7e-6, 0.0, 1e12, "4.7u/0/0mA"), (0.33e-6, 0.0, 1e12, "0.33u/0/0mA"),
    (0.33e-6, 0.0, 1800.0, "0.33u/0/1mA"), (0.33e-6, 0.0, 36.0, "0.33u/0/50mA"),
]
TRANS_LOADS = [(2, 900.0), (3, 600.0), (5, 360.0), (10, 180.0)]  # mA, RLOAD (1.8 V / I)
TRANS = [(c, 0.010, r, f"{cl}/10m/{ma}mA") for ma, r in TRANS_LOADS
         for c, cl in ((0.33e-6, "0.33u"), (4.7e-6, "4.7u"))]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def logical_lines(lines: list[str]) -> list[tuple[int, int]]:
    spans, start = [], None
    for i, ln in enumerate(lines):
        if not ln.startswith("+"):
            if start is not None:
                spans.append((start, i))
            start = i
    if start is not None:
        spans.append((start, len(lines)))
    return spans


def find_card(lines: list[str], prefix: str) -> tuple[int, int]:
    hits = [(s, e) for s, e in logical_lines(lines) if lines[s].startswith(prefix)]
    assert len(hits) == 1, f"expected exactly one card starting {prefix!r}, found {len(hits)}"
    return hits[0]


def edit_netlist(text: str, ra_frac: float, sw_w: float, tap_w: float, ccomp: float):
    notes = []
    lines = text.splitlines()
    if ccomp != 1.0:
        s, e = find_card(lines, "C_COMP VOUT EA_CZ 150p")
        lines[s] = lines[s].replace("150p", f"{150 * ccomp:g}p", 1)
        notes.append(f"C_COMP 150p -> {150 * ccomp:g}p")
    if ra_frac > 0:
        assert 0 < ra_frac < 1
        s, e = find_card(lines, "XR_CZ EA_CZ EA_OUT 0 sky130_fd_pr__res_xhigh_po W=0.42 L=52 ")
        assert e - s == 1, "XR_CZ is expected to be a single physical line"
        la, lb = R_TOTAL_L_UM * ra_frac, R_TOTAL_L_UM * (1 - ra_frac)
        new = [
            f"XR_CZA EA_CZ RCZ_MID 0 sky130_fd_pr__res_xhigh_po W=0.42 L={la:g} mult=1 m=1",
            f"XR_CZB RCZ_MID EA_OUT 0 sky130_fd_pr__res_xhigh_po W=0.42 L={lb:g} mult=1 m=1",
            f"XM_CZSW RCZ_MID ADAPT_G EA_OUT VIN sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W={sw_w:g} nf=1 ad={0.29 * sw_w / 2:g}",
        ]
        lines[s:e] = new
        notes.append(f"R_CZ split: R_a L={la:g} um, R_b L={lb:g} um (W=0.42), XM_CZSW W={sw_w:g} across R_b")
    if tap_w > 0:
        s, e = find_card(lines, "XM_CLN1 CL_SNS CL_SNS AMP_ENN 0 ")
        ins = [f"XM_CLN3 ADAPT_G CL_SNS AMP_ENN 0 sky130_fd_pr__nfet_g5v0d10v5 L=1 W={tap_w:g} nf=1 ad={0.29 * tap_w / 1:g}",
               "XM_ADPU ADAPT_G BIASP VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=1 W=1.25 nf=1 ad=0.3625"]
        lines[e:e] = ins
        notes.append(f"control tap: XM_CLN3 W={tap_w:g} (gate CL_SNS) + XM_ADPU W=1.25 (gate BIASP) -> ADAPT_G")
    assert (ra_frac > 0) == (tap_w > 0) or (ra_frac == 0 and tap_w == 0), "need both --ra-frac and --tap-w, or neither"
    return "\n".join(lines) + "\n", notes


def loop_gain_analyses(adaptive: bool, legs) -> list[str]:
    out = ["set numdgt=10", "set units=degrees"]
    for n, (cout, esr, rload, label) in enumerate(legs, start=1):
        out += [f"* --- leg {n}: {label} (explicit alter of cout/hesr/rload; no inherited state) ---",
                f"alter cout = {cout:g}", f"alter hesr gain = {esr:g}", f"alter rload = {rload:g}",
                "op", "let vseed = v(vout)", "let ivin = -i(vvin)",
                f"echo PT{n}_OP", "print vseed ivin"]
        if adaptive:
            out += ["print v(xldo.adapt_g)", "print v(xldo.ea_out)", "print v(xldo.cl_sns)"]
        out += ["ac dec 30 1e-2 1e9",
                "let lg = v(xldo.fb)/(1-v(xldo.fb))", "let lgdb = db(lg)", "let lgph = cph(lg)",
                "meas ac fc when lgdb=0 cross=1",
                "meas ac phc find lgph when lgdb=0 cross=1",
                "meas ac gmdb find lgdb when lgph=-180 cross=1",
                "let dcg = lgdb[0]"]
        if adaptive:
            # ratio of voltage drops across (R_b || switch) and R_a at the lowest swept
            # frequency: same series current, so (R_b||sw)/R_a.  real() part only.
            out += ["let zr = real((v(xldo.ea_out)-v(xldo.rcz_mid))/(v(xldo.rcz_mid)-v(xldo.ea_cz)))",
                    "let rbsw_over_ra = zr[0]"]
        out += [f"echo PT{n}_AC", "print fc", "print phc", "print gmdb", "print dcg"]
        if adaptive:
            out += ["print rbsw_over_ra"]
    return out


def parse_legs(log: str, adaptive: bool) -> dict[int, dict]:
    res: dict[int, dict] = {}
    segs = re.split(r"^PT(\d+)_(OP|AC)\s*$", log, flags=re.M)
    for i in range(1, len(segs), 3):
        n, body = int(segs[i]), segs[i + 2]
        d = res.setdefault(n, {})
        names = ["vseed", "ivin", "fc", "phc", "gmdb", "dcg", "rbsw_over_ra"]
        for name in names:
            m = re.search(rf"^{name}\s*=\s*({NUM})\s*$", body, flags=re.M)
            if m and name not in d:
                d[name] = float(m.group(1))
        for tag, key in (("v(xldo.adapt_g)", "adapt_g"), ("v(xldo.ea_out)", "ea_out"), ("v(xldo.cl_sns)", "cl_sns")):
            m = re.search(rf"^{re.escape(tag)}\s*=\s*({NUM})\s*$", body, flags=re.M)
            if m and key not in d:
                d[key] = float(m.group(1))
    return res


def classify_ac(n, leg, vals, vin, adaptive, diag):
    cout, esr, rload, label = leg
    reasons = []
    r = {"leg": n, "label": label, "cout_f": cout, "esr_ohm": esr, "rload_ohm": rload,
         "vout_v": vals.get("vseed"), "vin_current_a": vals.get("ivin"),
         "crossover_hz": vals.get("fc"), "dc_loop_gain_db": vals.get("dcg"),
         "v_adapt_g": vals.get("adapt_g"), "v_ea_out": vals.get("ea_out"), "v_cl_sns": vals.get("cl_sns")}
    vout = vals.get("vseed")
    if vout is None or vals.get("ivin") is None:
        reasons.append("operating point not printed")
    else:
        if not (1.7 <= vout <= 1.9):
            reasons.append(f"non-regulating operating point (VOUT={vout:.4f} V, VIN={vin} V)")
        iload = vout / rload
        r["external_load_a"] = iload
        r["iq_a"] = vals["ivin"] - iload
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
    if adaptive:
        if vals.get("adapt_g") is None:
            reasons.append("ADAPT_G not printed")
        if "rbsw_over_ra" in vals:
            q = vals["rbsw_over_ra"]
            r["rbsw_over_ra"] = q
            r["reff_over_ra"] = 1.0 + q
        else:
            reasons.append("effective-resistance ratio not printed")
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
    ap.add_argument("--bench", choices=["loop-gain", "iq", "current-limit", "load-transient"], default="loop-gain")
    ap.add_argument("--legs", choices=["grid18", "transition", "both"], default="both")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--process", required=True)
    ap.add_argument("--temp", type=float, required=True)
    ap.add_argument("--supply", type=float, required=True)
    ap.add_argument("--ra-frac", type=float, default=0.0)
    ap.add_argument("--sw-w", type=float, default=2.0)
    ap.add_argument("--tap-w", type=float, default=0.0)
    ap.add_argument("--ccomp-scale", type=float, default=1.0)
    ap.add_argument("--timeout", type=int, default=480)
    a = ap.parse_args()

    run = Path(a.outdir) / "runs" / a.run_id
    if run.exists():
        sys.exit(f"{run} exists: evidence is append-only, pick a new --run-id")
    run.mkdir(parents=True)
    adaptive = a.ra_frac > 0

    pin = cr.load_pin()
    pdk = cr.resolve_pdk(pin)
    exp = cr.load_experiment(SIM / a.bench)
    tbdir = run / "xschem"
    net = cr.netlist_with_xschem(exp.schematic, tbdir, pdk)
    raw_text = "\n".join(cr.netlist_body(net)) + "\n"
    (run / "netlist.raw.spice").write_text(raw_text)
    edited, notes = edit_netlist(raw_text, a.ra_frac, a.sw_w, a.tap_w, a.ccomp_scale)
    (run / "netlist.edited.spice").write_text(edited)
    shutil.rmtree(tbdir)
    corner = cr.Corner(a.process, a.temp, a.supply)

    legs = []
    if a.bench == "loop-gain":
        legs = (GRID18 if a.legs in ("grid18", "both") else []) + (TRANS if a.legs in ("transition", "both") else [])
        exp.raw["deck"]["analyses"] = loop_gain_analyses(adaptive, legs)
        exp.measurements = []
    deck = cr.build_deck(exp, pdk, corner, edited.splitlines())
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
        "run_id": a.run_id, "bench": a.bench, "issue": 349,
        "condition": {"process": a.process, "temp_c": a.temp, "supply_v": a.supply},
        "edits": {"ra_frac": a.ra_frac, "sw_w_um": a.sw_w if adaptive else None, "tap_w_um": a.tap_w,
                  "ccomp_scale": a.ccomp_scale, "notes": notes},
        "stimulus": {"analyses": exp.raw["deck"]["analyses"] if a.bench == "loop-gain" else "verbatim from sim/%s/experiment.json (see deck.spice)" % a.bench},
        "provenance": {
            "source_commit": git_sha,
            "driver_sha256": sha(Path(__file__).read_bytes()),
            "experiment_json_sha256": sha((SIM / a.bench / "experiment.json").read_bytes()),
            "testbench_sha256": sha(exp.schematic.read_bytes()),
            "dut_sha256": sha((REPO / "design" / "ldo_3v3in_1v8out.sch").read_bytes()),
            "netlist_raw_sha256": sha(raw_text.encode()),
            "netlist_edited_sha256": sha(edited.encode()),
            "deck_sha256": sha((run / "deck.spice").read_bytes()),
            "spiceinit_sha256": sha((SIM / "spiceinit").read_bytes()),
            "pdk": {"open_pdks_commit": pdk.installed_commit, "matches_pin": pdk.matches_pin},
            "tools": cr.tool_versions(),
        },
        "ngspice_exit": p.returncode, "elapsed_s": round(elapsed, 2), "solver_diagnostic": diag,
    }
    if a.bench == "loop-gain":
        vals = parse_legs(log, adaptive)
        rec["points"] = [classify_ac(i, leg, vals.get(i, {}), a.supply, adaptive, diag) for i, leg in enumerate(legs, start=1)]
        rec["valid_all"] = all(x["valid"] for x in rec["points"])
        for x in rec["points"]:
            print(f"L{x['leg']:02d} {x['label']:>18} valid={x['valid']!s:5} vout={x.get('vout_v')} "
                  f"pm={x.get('pm_deg')} gm={x.get('gm_db')} fc={x.get('crossover_hz')} "
                  f"iq_uA={(x.get('iq_a') or float('nan'))*1e6:.3f} gate={x.get('v_adapt_g')} "
                  f"reff/ra={x.get('reff_over_ra')} {x['invalid_reasons']}")
    else:
        meas = cr.parse_measurements(log)
        rec["meas"] = meas
        expected = [m.name for m in exp.measurements]
        missing = [n for n in expected if n not in meas]
        rec["missing_measurements"] = missing
        rec["valid"] = (p.returncode == 0 and not diag and not missing)
        rec["grading_vs_manifest_bounds"] = {m.name: cr.grade_bounds(m, meas.get(m.name))[0] for m in exp.measurements}
        for k, v in meas.items():
            print(f"{k} = {v}")
        print("valid", rec["valid"], "missing", missing)
    (run / "result.json").write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps({k: rec[k] for k in ("run_id", "ngspice_exit", "elapsed_s", "solver_diagnostic")}))


if __name__ == "__main__":
    main()
