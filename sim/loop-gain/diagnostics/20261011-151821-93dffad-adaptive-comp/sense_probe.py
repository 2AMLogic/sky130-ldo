#!/usr/bin/env python3
"""Issue #349 sense-path characterization probe (one ngspice -b per invocation).

Phase A of the load-adaptive compensation screen: measure the EXISTING
load-sense path (M_SENSE -> CL_SNS -> M_CLN1/M_CLN2 -> CL_CMP) as a candidate
control signal, before any prototype is attached. Answers, from measured
operating points at one PVT condition:

  - polarity and range of v(CL_SNS) / v(CL_CMP) vs external load
  - the sense-replica current vs load (via a 0 V monitor source VSNSMON in
    series with M_SENSE's drain -- netlist-level, diagnostic-only edit)
  - what the candidate gate-tap (M_CLN3 mirror + ADAPT_G pull-up) does to
    CL_SNS and where the adaptive switch's gate node (ADAPT_G) sits vs load

No spec value, no production netlist change; append-only run directories.

Modes (all netlist-level edits, raw + edited netlists both saved + hashed):
  --sense-mon (default on)    VSNSMON monitor in series with M_SENSE drain
  --tap-w W                   add the candidate tap: M_CLN3 (nfet, L=1, W=W,
                              gate=CL_SNS, source=AMP_ENN, drain=ADAPT_G)
                              + XM_ADPU pull-up (pfet, L=1, W=1.25 nf=1,
                              gate=BIASP, source=VIN, drain=ADAPT_G)
  --no-tap                    characterize the unmodified path only

Loads scanned: 0, 0.5, 1, 2, 3, 5, 7, 10, 20, 50 mA (RLOAD alters, same
36-ohm-at-50mA convention as sim/loop-gain/experiment.json).

Usage:
  sense_probe.py --outdir DIR --run-id ID --process tt --temp 27 --supply 3.3 [--tap-w 20]
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

# (load_mA, RLOAD ohm) -- vout/1.8 * 36 convention of the loop-gain deck
LOADS = [
    (0.0, 1e12),
    (0.5, 3600.0),
    (1.0, 1800.0),
    (2.0, 900.0),
    (3.0, 600.0),
    (5.0, 360.0),
    (7.0, 257.14),
    (10.0, 180.0),
    (20.0, 90.0),
    (50.0, 36.0),
]
NODES = ["ea_out", "ea_cz", "cl_sns", "cl_cmp", "biasp", "amp_enn", "adapt_g"]
NUM = r"-?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|-?inf|nan"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def logical_lines(text: str) -> list[tuple[int, int]]:
    """[(start,end)] line-index spans of each logical line (physical + `+` continuations)."""
    spans, start = [], None
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if not ln.startswith("+"):
            if start is not None:
                spans.append((start, i))
            start = i
    if start is not None:
        spans.append((start, len(lines)))
    return spans


def edit_netlist(text: str, tap_w: float) -> tuple[str, list[str]]:
    """Insert the sense monitor and, optionally, the candidate gate tap.

    Edits operate on logical lines (an instance plus its `+` continuations),
    so inserted cards never inherit or orphan continuation parameters.
    """
    notes = []
    lines = text.splitlines()
    # VSNSMON: 0 V source between M_SENSE's drain and CL_SNS (i(v.xldo.vsnsmon)
    # = sense-replica current). Pure series monitor, zero volts. M_SENSE's
    # drain pin is renamed SNS_MON; the full multi-line instance is preserved.
    hit = None
    for s, e in logical_lines(text):
        if lines[s].startswith("XM_SENSE CL_SNS EA_OUT VIN VIN "):
            hit = (s, e)
            break
    assert hit is not None, "XM_SENSE logical line not found"
    s, e = hit
    lines[s] = lines[s].replace("XM_SENSE CL_SNS EA_OUT VIN VIN ", "XM_SENSE SNS_MON EA_OUT VIN VIN ", 1)
    lines.insert(e, "VSNSMON CL_SNS SNS_MON 0")
    notes.append("VSNSMON 0V monitor in series with M_SENSE drain (CL_SNS <- SNS_MON)")
    if tap_w > 0:
        # The candidate tap of the hypothesis: M_CLN3 mirrors M_CLN1's Vgs
        # (gate CL_SNS, source AMP_ENN, same L=1) into the high-impedance node
        # ADAPT_G; XM_ADPU (a 1/8-width BIASP PMOS unit, the M_TSPS geometry)
        # pulls ADAPT_G up toward VIN. DC-wise the tap adds no current to
        # CL_SNS (a gate draws none), so the current-limit DC threshold is
        # untouched by construction -- measured here anyway.
        ins = (f"XM_CLN3 ADAPT_G CL_SNS AMP_ENN 0 sky130_fd_pr__nfet_g5v0d10v5 L=1 W={tap_w:g} nf=1 ad=0.29\n"
               "XM_ADPU ADAPT_G BIASP VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=1 W=1.25 nf=1 ad=0.3625")
        hit = None
        for s, e in logical_lines("\n".join(lines)):
            if lines[s].startswith("XM_CLN1 CL_SNS CL_SNS AMP_ENN 0 "):
                hit = (s, e)
                break
        assert hit is not None, "XM_CLN1 logical line not found"
        lines.insert(hit[1], ins)
        notes.append(f"gate tap: M_CLN3 L=1 W={tap_w:g} + ADAPT_G pull-up XM_ADPU W=1.25 (BIASP)")
    return "\n".join(lines) + "\n", notes


def sense_analyses(tap_w: float) -> list[str]:
    out = ["set numdgt=10"]
    names = ["vout"] + NODES if tap_w > 0 else ["vout"] + NODES[:-1]
    for i, (_ma, rload) in enumerate(LOADS, start=1):
        out += [f"* load leg {i}: RLOAD {rload:g}", "alter rload = %g" % rload, "op",
                f"echo LEG{i}_OP"]
        # one vector per print: an unknown vector aborts the whole print line
        out += [f"print v({n if n == 'vout' else 'xldo.' + n})" for n in names]
        out += ["print i(vvin) i(v.xldo.vsnsmon)"]
    return out


def parse_legs(log: str) -> dict[int, dict]:
    res: dict[int, dict] = {}
    segs = re.split(r"^LEG(\d+)_OP\s*$", log, flags=re.M)
    for i in range(1, len(segs), 2):
        leg, body = int(segs[i]), segs[i + 1]
        d = res.setdefault(leg, {})
        for name in ["vout"] + NODES:
            prefix = "" if name == "vout" else "xldo."
            m = re.search(rf"^v\({re.escape(prefix)}{name}\)\s*=\s*({NUM})\s*$", body, flags=re.M)
            if m and name not in d:
                d[name] = float(m.group(1))
        m = re.search(r"^i\(vvin\)\s*=\s*(" + NUM + r")\s*$", body, flags=re.M)
        if m:
            d["ivin"] = float(m.group(1))
        m = re.search(r"^i\(v\.xldo\.vsnsmon\)\s*=\s*(" + NUM + r")\s*$", body, flags=re.M)
        if m:
            d["isense"] = float(m.group(1))
    return res


def classify(leg, vals, supply, rload, tap_w, diag):
    reasons = []
    vout = vals.get("vout")
    r = {"leg": leg, "load_nominal_a": 1.8 / rload if rload < 1e11 else 0.0,
         "rload_ohm": rload}
    for name in ["vout"] + NODES:
        r["v_" + name] = vals.get(name)
    r["ivin_a"] = vals.get("ivin")
    r["isense_a"] = vals.get("isense")
    if vout is None or vals.get("ivin") is None:
        reasons.append("operating point not printed")
    else:
        if not (1.7 <= vout <= 1.9):
            reasons.append(f"non-regulating operating point (VOUT={vout:.4f} V, VIN={supply} V)")
        iload = vout / rload
        r["external_load_a"] = iload
        r["iq_a"] = -vals["ivin"] - iload
    if tap_w > 0 and vals.get("adapt_g") is None:
        reasons.append("tap mode but ADAPT_G not printed")
    if diag:
        reasons.append("ngspice solver diagnostic present in run: " + diag)
    r["valid"] = not reasons
    r["invalid_reasons"] = reasons
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--process", required=True)
    ap.add_argument("--temp", type=float, required=True)
    ap.add_argument("--supply", type=float, required=True)
    ap.add_argument("--tap-w", type=float, default=0.0)
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()

    run = Path(a.outdir) / "runs" / a.run_id
    if run.exists():
        sys.exit(f"{run} exists: evidence is append-only, pick a new --run-id")
    run.mkdir(parents=True)

    pin = cr.load_pin()
    pdk = cr.resolve_pdk(pin)
    exp = cr.load_experiment(SIM / "loop-gain")
    tbdir = run / "xschem"
    net = cr.netlist_with_xschem(exp.schematic, tbdir, pdk)
    raw_text = "\n".join(cr.netlist_body(net)) + "\n"
    (run / "netlist.raw.spice").write_text(raw_text)
    edited, notes = edit_netlist(raw_text, a.tap_w)
    (run / "netlist.edited.spice").write_text(edited)
    shutil.rmtree(tbdir)
    corner = cr.Corner(a.process, a.temp, a.supply)
    exp.raw["deck"]["analyses"] = sense_analyses(a.tap_w)
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
        "run_id": a.run_id, "bench": "sense-path", "issue": 349,
        "condition": {"process": a.process, "temp_c": a.temp, "supply_v": a.supply},
        "edits": {"tap_w": a.tap_w, "notes": notes},
        "provenance": {
            "source_commit": git_sha,
            "driver_sha256": sha(Path(__file__).read_bytes()),
            "experiment_json_sha256": sha((SIM / "loop-gain" / "experiment.json").read_bytes()),
            "testbench_sha256": sha(exp.schematic.read_bytes()),
            "dut_sha256": sha((REPO / "design" / "ldo_3v3in_1v8out.sch").read_bytes()),
            "netlist_raw_sha256": sha(raw_text.encode()),
            "netlist_edited_sha256": sha(edited.encode()),
            "deck_sha256": sha((run / "deck.spice").read_bytes()),
            "spiceinit_sha256": sha((SIM / "spiceinit").read_bytes()),
            "pdk": {"open_pdks_commit": pdk.installed_commit, "matches_pin": pdk.matches_pin},
            "tools": cr.tool_versions(),
        },
        "ngspice_exit": p.returncode, "elapsed_s": round(elapsed, 2),
        "solver_diagnostic": diag,
    }
    vals = parse_legs(log)
    rec["legs"] = [classify(i, vals.get(i, {}), a.supply, LOADS[i - 1][1], a.tap_w, diag)
                   for i in range(1, len(LOADS) + 1)]
    rec["valid_all"] = all(x["valid"] for x in rec["legs"])
    (run / "result.json").write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps({k: rec[k] for k in ("run_id", "ngspice_exit", "elapsed_s", "solver_diagnostic", "valid_all")}))
    print(f"{'load_mA':>8} {'VOUT':>8} {'EA_OUT':>8} {'EA_CZ':>8} {'CL_SNS':>8} {'CL_CMP':>8} "
          f"{'BIASP':>8} {'ADAPT_G':>8} {'Isense_uA':>10} {'Iq_uA':>9}")
    for x in rec["legs"]:
        isu = (x.get("isense_a") or float("nan")) * 1e6
        iqu = (x.get("iq_a") or float("nan")) * 1e6
        g = lambda k: "--" if x.get("v_" + k) is None else f"{x['v_' + k]:.4f}"
        print(f"{x['load_nominal_a']*1e3:8.2f} {g('vout'):>8} {g('ea_out'):>8} {g('ea_cz'):>8} "
              f"{g('cl_sns'):>8} {g('cl_cmp'):>8} {g('biasp'):>8} {g('adapt_g'):>8} {isu:10.4f} {iqu:9.3f} "
              f"{'' if x['valid'] else 'INVALID: ' + '; '.join(x['invalid_reasons'])}")


if __name__ == "__main__":
    main()
