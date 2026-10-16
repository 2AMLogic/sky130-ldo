#!/usr/bin/env python3
"""Issue #360 bounded missing-crossing diagnostic (one ngspice -b per invocation).

Re-uses the #349 driver's netlisting/edit/deck/classify helpers READ-ONLY (that
directory is not modified) and adds: (a) an extended AC sweep with the complex loop
gain saved per leg via wrdata, (b) the original scalar `meas` extraction in the same
deck for like-for-like comparison, (c) response-level extraction (crossing_extract.py).

Legs are chosen by label from the #338 18-leg grid; there is no grid mode.  Candidate
realization (optional) is the #349 R1 (--ra-frac 0.5 --tap-w 6).  Evidence dirs are
append-only: an existing run id is refused.

  crossing_probe.py --outdir DIR --run-id ID --process tt --temp 27 --supply 3.3 \
      [--ra-frac 0.5 --tap-w 6] [--fmax 1e12] [--legs L1,L2,...]
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


ap = _load("adaptive_probe", next((SIM / "loop-gain" / "diagnostics").glob("*-adaptive-comp")) / "adaptive_probe.py")
ce = _load("crossing_extract", HERE / "crossing_extract.py")
cr = ap.cr

DEFAULT_LEGS = ["4.7u/500m/1mA", "4.7u/500m/50mA", "4.7u/10m/50mA"]  # missing, missing-under-R1, control (finite GM)


def select_legs(labels):
    by = {l[3]: l for l in ap.GRID18}
    missing = [x for x in labels if x not in by]
    if missing:
        raise SystemExit(f"unknown leg labels {missing}; known: {sorted(by)}")
    return [by[x] for x in labels]


def deck_analyses(adaptive, legs, fmax, ppd=30):
    out = ["set numdgt=10", "set units=degrees", "set wr_vecnames", "set wr_singlescale"]
    for n, (cout, esr, rload, label) in enumerate(legs, start=1):
        out += [f"* --- leg {n}: {label} ---",
                f"alter cout = {cout:g}", f"alter hesr gain = {esr:g}", f"alter rload = {rload:g}",
                "op", "let vseed = v(vout)", "let ivin = -i(vvin)", f"echo PT{n}_OP", "print vseed ivin"]
        if adaptive:
            out += ["print v(xldo.adapt_g)", "print v(xldo.ea_out)", "print v(xldo.cl_sns)"]
        out += [f"ac dec {ppd} 1e-2 {fmax:g}",
                "let lg = v(xldo.fb)/(1-v(xldo.fb))", "let lgdb = db(lg)", "let lgph = cph(lg)",
                f"wrdata resp_leg{n}.txt lg",
                # original scalar extraction, unchanged semantics (cross=1), on the EXTENDED sweep
                "meas ac fc when lgdb=0 cross=1",
                "meas ac phc find lgph when lgdb=0 cross=1",
                "meas ac gmdb find lgdb when lgph=-180 cross=1",
                "let dcg = lgdb[0]"]
        if adaptive:
            out += ["let zr = real((v(xldo.ea_out)-v(xldo.rcz_mid))/(v(xldo.rcz_mid)-v(xldo.ea_cz)))",
                    "let rbsw_over_ra = zr[0]"]
        out += [f"echo PT{n}_AC", "print fc", "print phc", "print gmdb", "print dcg", "print lgph[0]"]
        if adaptive:
            out += ["print rbsw_over_ra"]
    return out


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--outdir", required=True)
    a.add_argument("--run-id", required=True)
    a.add_argument("--process", required=True)
    a.add_argument("--temp", type=float, required=True)
    a.add_argument("--supply", type=float, required=True)
    a.add_argument("--ra-frac", type=float, default=0.0)
    a.add_argument("--sw-w", type=float, default=2.0)
    a.add_argument("--tap-w", type=float, default=0.0)
    a.add_argument("--fmax", type=float, default=1e12)
    a.add_argument("--legs", default=",".join(DEFAULT_LEGS))
    a.add_argument("--timeout", type=int, default=480)
    o = a.parse_args()

    run = Path(o.outdir) / "runs" / o.run_id
    if run.exists():
        sys.exit(f"{run} exists: evidence is append-only, pick a new --run-id")
    run.mkdir(parents=True)
    adaptive = o.ra_frac > 0
    legs = select_legs([s for s in o.legs.split(",") if s])

    pin = cr.load_pin()
    pdk = cr.resolve_pdk(pin)
    exp = cr.load_experiment(SIM / "loop-gain")
    net = cr.netlist_with_xschem(exp.schematic, run / "xschem", pdk)
    raw_text = "\n".join(cr.netlist_body(net)) + "\n"
    (run / "netlist.raw.spice").write_text(raw_text)
    edited, notes = ap.edit_netlist(raw_text, o.ra_frac, o.sw_w, o.tap_w, 1.0)
    (run / "netlist.edited.spice").write_text(edited)
    shutil.rmtree(run / "xschem")
    corner = cr.Corner(o.process, o.temp, o.supply)
    analyses = deck_analyses(adaptive, legs, o.fmax)
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

    vals = ap.parse_legs(log, adaptive)
    points = []
    for n, leg in enumerate(legs, start=1):
        pt = ap.classify_ac(n, leg, vals.get(n, {}), o.supply, adaptive, diag)  # #349 gates unchanged
        f = run / f"resp_leg{n}.txt"
        if f.exists():
            fr, re, im = ce.read_wrdata(f.read_text())
            pt["response"] = ce.analyze(fr, re, im)
            pt["response_file"] = f.name
        else:
            pt["response"] = None
            pt["response_note"] = "response file not written (ac failed?)"
        points.append(pt)
    rec = {
        "run_id": o.run_id, "issue": 360, "kind": "missing-crossing-diagnosis",
        "condition": {"process": o.process, "temp_c": o.temp, "supply_v": o.supply},
        "edits": {"ra_frac": o.ra_frac, "tap_w_um": o.tap_w, "notes": notes},
        "sweep": {"f_start_hz": 1e-2, "f_stop_hz": o.fmax, "points_per_decade": 30,
                  "original_sweep_stop_hz": 1e9},
        "stimulus": analyses,
        "provenance": {
            "source_commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
            "driver_sha256": ap.sha(Path(__file__).read_bytes()),
            "extract_sha256": ap.sha((HERE / "crossing_extract.py").read_bytes()),
            "experiment_json_sha256": ap.sha((SIM / "loop-gain" / "experiment.json").read_bytes()),
            "testbench_sha256": ap.sha(exp.schematic.read_bytes()),
            "dut_sha256": ap.sha((REPO / "design" / "ldo_3v3in_1v8out.sch").read_bytes()),
            "netlist_raw_sha256": ap.sha(raw_text.encode()),
            "netlist_edited_sha256": ap.sha(edited.encode()),
            "deck_sha256": ap.sha((run / "deck.spice").read_bytes()),
            "pdk": {"open_pdks_commit": pdk.installed_commit, "matches_pin": pdk.matches_pin},
            "tools": cr.tool_versions(),
        },
        "ngspice_exit": p.returncode, "elapsed_s": round(elapsed, 2), "solver_diagnostic": diag,
        "points": points,
    }
    (run / "result.json").write_text(json.dumps(rec, indent=2) + "\n")
    for x in points:
        r = x["response"] or {}
        print(f"{x['label']:>16} valid349={x['valid']!s:5} vout={x.get('vout_v')} status={r.get('status')} "
              f"pm={r.get('pm_deg')} gm={r.get('gm_db')} endG={r.get('end_gain_db')} minPh={r.get('min_phase_deg')} "
              f"meas_gm={x.get('gm_db')} {x['invalid_reasons']}")
    print(json.dumps({k: rec[k] for k in ("run_id", "ngspice_exit", "elapsed_s", "solver_diagnostic")}))


if __name__ == "__main__":
    main()
