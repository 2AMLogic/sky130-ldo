#!/usr/bin/env python3
"""Issue #357 analysis: validity gates + derived dropout measurements + paired tables.

The transient validity gates are #339's, imported read-only from
../issue-339/analyze.py (cold start, finite data, strictly increasing time, run
reaches 14 ms, regulating at the starting supply with the 50 mA load established,
a real falling crossing after 6 ms, no solver diagnostics, ngspice meas agreeing
with the trajectory crossing within 0.5 mV). This module adds:

  * run-level gates: ngspice exit status 0 and the data file present/parseable;
  * derived measurements (headroom, branch currents, Iq, VREF current) that exist
    ONLY for a valid run -- an invalid run yields `derived = None` and its reasons,
    so no derived number can be read as a pass;
  * the paired baseline/candidate comparison and the repeat-pair tolerance check;
  * manifest grading of the dropout row (`dropout_v < 0.300 V`, strict).

Declared before execution (README section 3):
  DROPOUT_REPEAT_TOL_V  = 0.5 mV  (#339 precedent)
  EA_OUT_REPEAT_TOL_V   = 1.0 mV
  VREF_DC_CURRENT_MAX_A = 1 nA at the settled pre-ramp sample (VREF is a gate-only input)
  EDGE_VIN_V            = 2.064 V (= 1.764 + 0.300: the VIN at which a passing part must
                          still hold VOUT >= 1.764 V)

usage:
  analyze.py run <run_dir>                    # writes <run_dir>/analysis.json + .txt
  analyze.py pair <base_dir> <cand_dir>       # paired table (stdout)
  analyze.py repeat <dir_a> <dir_b>           # repeat tolerance check (stdout, exit 1 if not met)
"""
from __future__ import annotations

import gzip
import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("dropout339_analyze", HERE.parent / "issue-339" / "analyze.py")
a339 = importlib.util.module_from_spec(_spec)
sys.modules["dropout339_analyze"] = a339
_spec.loader.exec_module(a339)

DROPOUT_REPEAT_TOL_V = 0.5e-3
EA_OUT_REPEAT_TOL_V = 1.0e-3
VREF_DC_CURRENT_MAX_A = 1e-9
EDGE_VIN_V = 2.064
SPEC_DROPOUT_MAX_V = 0.300  # dropout-vs-load/experiment.json dropout_v: max 0.3, max_inclusive false
PRE_T = a339.PRE_T

# role -> device per variant (role names are what the tables report)
ROLES = {
    "base": {"tail": "xm_tail", "in_fb": "xm_in1", "in_ref": "xm_in2", "pull_up": "xm_mirp2",
             "pull_down": "xm_mir2"},
    "cand": {"tail": "xm_ntail", "in_fb": "xm_nin1", "in_ref": "xm_nin2", "pull_up": "xm_po1",
             "pull_down": "xm_nmo"},
}


def read_maybe_gz(path: Path) -> str:
    if path.is_file():
        return path.read_text()
    gz = Path(str(path) + ".gz")
    with gzip.open(gz, "rt") as f:
        return f.read()


def load(run_dir: Path):
    """(t, cols, log, meta, err). err is a string when the data cannot be used."""
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "result.json").read_text())
    log = (run_dir / "ngspice.log").read_text() if (run_dir / "ngspice.log").is_file() else ""
    try:
        names = json.loads((run_dir / "data.columns.json").read_text())
        text = read_maybe_gz(run_dir / "data.dat")
    except (OSError, ValueError) as ex:
        return None, None, log, meta, f"data unavailable: {ex}"
    scale, cols = a339.parse_wrdata(text, len(names))
    if scale is None:
        return None, None, log, meta, f"malformed data: {cols}"
    return scale, dict(zip(names, cols)), log, meta, None


def first_fall(t, y, level, t_after):
    """Interpolated time at which y first falls through `level` after t_after, or None."""
    for i in range(1, len(t)):
        if t[i] > t_after and y[i - 1] >= level > y[i]:
            f = (y[i - 1] - level) / (y[i - 1] - y[i])
            return t[i - 1] + f * (t[i] - t[i - 1])
    return None


def derived(t, cols, variant, res):
    """Derived measurements of a VALID run, or (None, reasons)."""
    if not res["valid"]:
        return None, ["run invalid: " + "; ".join(res["reasons"])]
    reasons = []
    roles = ROLES[variant]
    need = ["xldo.ea_out", "i(vvin)", "i(vvref)", "i(iload)"]
    need = [f"v({n})" if n.startswith("xldo") else n for n in need]
    for r in roles.values():
        need += [f"{r}.id"]
    for k in need + [f"{roles['tail']}.vds", f"{roles['tail']}.vdsat",
                     f"{roles['pull_down']}.vds", f"{roles['pull_down']}.vdsat"]:
        if k not in cols:
            reasons.append(f"missing column {k}")
    if reasons:
        return None, reasons
    t_edge = first_fall(t, cols["v(vin)"], EDGE_VIN_V, a339.RAMP_T0)
    if t_edge is None:
        return None, [f"VIN never falls through the {EDGE_VIN_V} V edge sample during the ramp"]
    pts = {"pre_5p9ms": PRE_T, "crossing": res["t_cross"], "vin_2p064": t_edge}
    out = {"t_s": pts}
    for lab, tt in pts.items():
        o = {k: a339.interp(tt, t, v) for k, v in cols.items()}
        d = {
            "vin_v": o["v(vin)"], "vout_v": o["v(vout)"], "ea_out_v": o["v(xldo.ea_out)"],
            "pass_vsg_v": o["v(vin)"] - o["v(xldo.ea_out)"],
            "pass_id_a": abs(o["xm_pass.id"]), "pass_vds_v": abs(o["xm_pass.vds"]),
            "pass_vdsat_v": abs(o["xm_pass.vdsat"]),
            "supply_current_a": -o["i(vvin)"],
            "iq_vs_load_a": -o["i(vvin)"] - o["i(iload)"],
            "iq_internal_a": -o["i(vvin)"] - abs(o["xm_pass.id"]),
            "vref_current_a": o["i(vvref)"],
            "clamp_clim_id_a": abs(o["xm_clim.id"]), "tshut_id_a": abs(o["xm_tshut.id"]),
            "clamp_ref_clp_id_a": abs(o["xm_clp.id"]), "clamp_sense_cln2_id_a": abs(o["xm_cln2.id"]),
            "sense_id_a": abs(o["xm_sense.id"]),
            "cl_cmp_v": o["v(xldo.cl_cmp)"], "clamp_vsg_v": o["v(vin)"] - o["v(xldo.cl_cmp)"],
        }
        for role, dev in roles.items():
            d[f"{role}_id_a"] = abs(o[f"{dev}.id"])
            if f"{dev}.vdsat" in o:
                d[f"{role}_headroom_v"] = abs(o[f"{dev}.vds"]) - abs(o[f"{dev}.vdsat"])
        out[lab] = d
    for lab in pts:
        for k, v in out[lab].items():
            if not math.isfinite(v):
                return None, [f"nonfinite derived value {k} at {lab}"]
    vref_pre = abs(out["pre_5p9ms"]["vref_current_a"])
    out["vref_dc_current_ok"] = vref_pre <= VREF_DC_CURRENT_MAX_A
    out["vref_current_max_abs_a"] = max(abs(x) for x in cols["i(vvref)"])
    return out, []


def analyze(run_dir: Path):
    run_dir = Path(run_dir)
    t, cols, log, meta, err = load(run_dir)
    variant = meta["variant"]
    if t is None:
        res = {"valid": False, "reasons": [err], "dropout_v": None}
    else:
        res = a339.analyze_tran(t, cols, log)
    if meta.get("ngspice_exit") != 0:
        res["valid"] = False
        res["dropout_v"] = None
        res["reasons"].append(f"ngspice exit status {meta.get('ngspice_exit')}")
    if meta.get("solver_diagnostic"):
        res["valid"] = False
        res["dropout_v"] = None
        res["reasons"].append("corner-run solver diagnostic: " + meta["solver_diagnostic"])
    der, dreasons = (None, ["no data"]) if t is None else derived(t, cols, variant, res)
    grade = None
    if res["valid"]:
        grade = {"dropout_v": res["dropout_v"], "max": SPEC_DROPOUT_MAX_V,
                 "pass": res["dropout_v"] < SPEC_DROPOUT_MAX_V}
    out = {"run_id": meta["run_id"], "variant": variant, "valid": res["valid"],
           "reasons": res["reasons"], "dropout_v": res["dropout_v"],
           "dropout_interp_v": res.get("dropout_interp"), "dropout_meas_v": res.get("dropout_meas"),
           "vin_cross_v": res.get("vin_cross"), "vout_pre_v": res.get("vout_pre"),
           "ipass_pre_a": res.get("ipass_pre"), "derived": der, "derived_reasons": dreasons,
           "spec_grade": grade}
    (run_dir / "analysis.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    (run_dir / "analysis.txt").write_text(report(out))
    return out


def _f(x, s=".6f"):
    return "n/a" if x is None else format(x, s)


def report(r):
    L = [f"== {r['run_id']} ({r['variant']}): {'VALID' if r['valid'] else 'INVALID'} =="]
    L += [f"  invalid reason: {x}" for x in r["reasons"]]
    L.append(f"dropout_v = {_f(r['dropout_v'])}  (interp {_f(r['dropout_interp_v'])}, meas {_f(r['dropout_meas_v'])})"
             f"  VIN@x = {_f(r['vin_cross_v'], '.5f')}")
    if r["spec_grade"]:
        L.append(f"manifest dropout_v < 0.300 V: {'PASS' if r['spec_grade']['pass'] else 'FAIL'} (tt/27C single condition only)")
    d = r["derived"]
    if d is None:
        L += [f"  derived: none ({x})" for x in r["derived_reasons"]]
        return "\n".join(L) + "\n"
    L.append(f"VREF current: pre-ramp {d['pre_5p9ms']['vref_current_a']:.3e} A (ok={d['vref_dc_current_ok']}), "
             f"max |i| over run {d['vref_current_max_abs_a']:.3e} A")
    keys = list(d["pre_5p9ms"].keys())
    L.append(f"{'quantity':28s} {'pre 5.9ms':>14s} {'crossing':>14s} {'VIN=2.064':>14s}")
    for k in keys:
        L.append(f"{k:28s} " + " ".join(f"{d[p][k]:>+14.6g}" for p in ("pre_5p9ms", "crossing", "vin_2p064")))
    return "\n".join(L) + "\n"


PAIR_KEYS = [("ea_out_v", 1, "V"), ("pass_vsg_v", 1, "V"), ("pass_vds_v", 1, "V"), ("pass_vdsat_v", 1, "V"),
             ("tail_id_a", 1e6, "uA"), ("tail_headroom_v", 1, "V"), ("in_fb_id_a", 1e6, "uA"),
             ("in_ref_id_a", 1e6, "uA"), ("pull_down_id_a", 1e6, "uA"), ("pull_down_headroom_v", 1, "V"),
             ("pull_up_id_a", 1e6, "uA"), ("clamp_clim_id_a", 1e9, "nA"), ("tshut_id_a", 1e9, "nA"),
             ("clamp_ref_clp_id_a", 1e6, "uA"), ("clamp_sense_cln2_id_a", 1e6, "uA"), ("clamp_vsg_v", 1, "V"),
             ("supply_current_a", 1e3, "mA"), ("iq_vs_load_a", 1e6, "uA"), ("iq_internal_a", 1e6, "uA")]


def pair_table(rb, rc):
    L = [f"paired tt/27C dropout screen: base={rb['run_id']} cand={rc['run_id']}",
         f"  valid: base={rb['valid']} cand={rc['valid']}",
         f"  dropout_v: base={_f(rb['dropout_v'])} cand={_f(rc['dropout_v'])} V  (manifest max 0.300, strict)",
         f"  VIN@crossing: base={_f(rb['vin_cross_v'], '.5f')} cand={_f(rc['vin_cross_v'], '.5f')} V"]
    if rb["derived"] is None or rc["derived"] is None:
        L.append("  derived comparison unavailable (an input run is invalid)")
        return "\n".join(L) + "\n"
    for p in ("pre_5p9ms", "crossing", "vin_2p064"):
        L.append(f"--- at {p}: base VIN={rb['derived'][p]['vin_v']:.4f} V / cand VIN={rc['derived'][p]['vin_v']:.4f} V")
        for k, sc, u in PAIR_KEYS:
            b, c = rb["derived"][p].get(k), rc["derived"][p].get(k)
            L.append(f"  {k:24s} [{u:>2s}] base={'n/a' if b is None else format(b * sc, '+.5g'):>12s}"
                     f"  cand={'n/a' if c is None else format(c * sc, '+.5g'):>12s}")
    return "\n".join(L) + "\n"


def repeat_check(ra, rb):
    """Repeat-pair agreement against the declared tolerances; invalid -> not met."""
    if not (ra["valid"] and rb["valid"]):
        return False, "repeat check INVALID: a run is invalid"
    dd = abs(ra["dropout_v"] - rb["dropout_v"])
    de = abs(ra["derived"]["crossing"]["ea_out_v"] - rb["derived"]["crossing"]["ea_out_v"])
    ok = dd <= DROPOUT_REPEAT_TOL_V and de <= EA_OUT_REPEAT_TOL_V
    return ok, (f"repeat {ra['run_id']} vs {rb['run_id']}: |d dropout|={dd*1e3:.4f} mV (tol {DROPOUT_REPEAT_TOL_V*1e3} mV), "
                f"|d EA_OUT@x|={de*1e3:.4f} mV (tol {EA_OUT_REPEAT_TOL_V*1e3} mV) -> {'MET' if ok else 'NOT MET'}")


def main(argv):
    c = argv[1]
    if c == "run":
        print(report(analyze(Path(argv[2]))))
    elif c == "pair":
        print(pair_table(analyze(Path(argv[2])), analyze(Path(argv[3]))))
    elif c == "repeat":
        ok, msg = repeat_check(analyze(Path(argv[2])), analyze(Path(argv[3])))
        print(msg)
        sys.exit(0 if ok else 1)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
