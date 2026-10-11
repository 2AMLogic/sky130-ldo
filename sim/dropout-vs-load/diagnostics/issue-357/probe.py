#!/usr/bin/env python3
"""Issue #357 single-condition probe driver: ONE ngspice -b per invocation.

Netlists the repo's own testbench with the repo's xschem flow (corner-run.py),
optionally applies the #357 candidate (candidate.py) to the DUT subcircuit,
builds the bench's own deck (manifest analyses verbatim, or the thermal two-state
transient of sim/thermal/run_hysteresis.py), runs ngspice once at one
process / temperature / supply, and writes an append-only run directory:

  runs/<run-id>/netlist.raw.spice  netlist.edited.spice  netlist.diff
                deck.spice  ngspice.log  [data.dat.gz  data.columns.json]  result.json

Benches
  dropout          sim/dropout-vs-load manifest deck (#339's cold-start `tran 10u 14m uic`,
                   50 mA ramp, VIN 3.3 -> 1.17 V, crossing VOUT falling through 1.764 V)
                   + save/wrdata instrumentation (no other change)
  current-limit    sim/current-limit manifest deck, verbatim (forced-output DC + held short)
  iq               sim/iq manifest deck, verbatim (0 mA and 50 mA settled transients)
  enable-shutdown  sim/enable-shutdown manifest deck, verbatim
  thermal          sim/thermal testbench, run_hysteresis.py's two-state transient
                   (`cold` / `hot` / `cold_exc` / `en`) at one EXTERNALLY IMPOSED device
                   temperature (--temp); the electrical condition is still tt + --supply

Strictly one run per call; commands.sh calls it sequentially. No grid, no pool.
"""
from __future__ import annotations

import argparse
import difflib
import gzip
import json
import math
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parents[2]
REPO = SIM.parent
sys.path.insert(0, str(SIM / "bin"))
sys.path.insert(0, str(HERE))
import _probe_common as pc  # noqa: E402
import _record_common as rc  # noqa: E402
import candidate as cand  # noqa: E402

cr = pc.load_corner_run()

BENCH_DIR = {"dropout": "dropout-vs-load", "current-limit": "current-limit", "iq": "iq",
             "enable-shutdown": "enable-shutdown", "thermal": "thermal"}

# ---------------------------------------------------------------- dropout columns
P = "@m.xldo.{n}.msky130_fd_pr__{t}[{p}]"
PF, NF = "pfet_g5v0d10v5", "nfet_g5v0d10v5"
DEV_COMMON = {
    "xm_pass": (PF, ["id", "vgs", "vds", "vdsat", "vth", "gm"]),
    "xm_sense": (PF, ["id", "vgs", "vds"]),
    "xm_clim": (PF, ["id", "vgs", "vds"]),
    "xm_tshut": (PF, ["id", "vgs", "vds"]),
    "xm_clp": (PF, ["id", "vgs", "vds", "vdsat"]),
    "xm_cln2": (NF, ["id"]),
    "xm_biasn1": (NF, ["id"]),
    "xm_biasp1": (PF, ["id"]),
    "xm_enn2": (NF, ["id", "vds"]),
}
DEV_BASE = {
    "xm_tail": (PF, ["id", "vds", "vdsat"]),
    "xm_in1": (PF, ["id", "vds", "vdsat"]),
    "xm_in2": (PF, ["id", "vds", "vdsat"]),
    "xm_in2s": (PF, ["id"]),
    "xm_mirp1": (PF, ["id"]),
    "xm_mirp2": (PF, ["id", "vgs", "vds", "vdsat"]),   # EA_OUT pull-up
    "xm_mir2": (NF, ["id", "vgs", "vds", "vdsat"]),    # EA_OUT pull-down
}
DEV_CAND = {
    "xm_ntail": (NF, ["id", "vds", "vdsat"]),
    "xm_nin1": (NF, ["id", "vds", "vdsat"]),
    "xm_nin2": (NF, ["id", "vds", "vdsat"]),
    "xm_nin1c": (NF, ["id", "vds"]),
    "xm_nin2s": (NF, ["id", "vds"]),
    "xm_pd1": (PF, ["id", "vgs"]),
    "xm_pd2": (PF, ["id", "vgs"]),
    "xm_po2": (PF, ["id", "vds", "vdsat"]),
    "xm_nmd": (NF, ["id"]),
    "xm_po1": (PF, ["id", "vgs", "vds", "vdsat"]),     # EA_OUT pull-up
    "xm_nmo": (NF, ["id", "vgs", "vds", "vdsat"]),     # EA_OUT pull-down
    "xm_vrf": (NF, ["id", "vds", "vdsat"]),
    "xm_pbr": (PF, ["id"]),
    "xm_pbn": (PF, ["id"]),
    "xm_nbr": (NF, ["id"]),
}
NODES_COMMON = ["vin", "vout", "en", "xldo.ea_out", "xldo.biasp", "xldo.cl_cmp", "xldo.cl_sns",
                "xldo.ts_cmp", "xldo.amp_enn", "xldo.fb", "xldo.nb", "xldo.ss"]
NODES_BASE = ["xldo.ea_tail", "xldo.ea_d1", "xldo.ea_d2", "xldo.pb"]
NODES_CAND = ["xldo.ntail", "xldo.nx1", "xldo.nx2", "xldo.nd1", "xldo.nd2", "xldo.nm",
              "xldo.pbr", "xldo.nbr", "xldo.nvr"]
CURRENTS = ["i(vvin)", "i(vvref)"]  # i(iload) is not a valid ngspice vector (attempt d01_base)


def devices(variant):
    d = dict(DEV_COMMON)
    d.update(DEV_BASE if variant == "base" else DEV_CAND)
    return d


def column_names(variant):
    nodes = NODES_COMMON + (NODES_BASE if variant == "base" else NODES_CAND)
    names = [f"v({n})" for n in nodes] + CURRENTS
    for n, (_t, ps) in devices(variant).items():
        names += [f"{n}.{p}" for p in ps]
    return names


def spice_vec(label, variant):
    m = re.fullmatch(r"(xm_\w+)\.(\w+)", label)
    if not m:
        return label
    n, p = m.groups()
    return P.format(n=n, t=devices(variant)[n][0], p=p)


def instrument_dropout(deck, variant, dat="data.dat"):
    """#339's instrumentation shape: extend `save all` and add one wrdata before the
    first `let meas_dropout_v`; nothing else in the deck changes."""
    cols = column_names(variant)
    saves = [spice_vec(c, variant) for c in cols if c.startswith("xm_")]
    i = deck.index(".control")
    ctl = deck[i:]
    if ctl.count("save all\n") != 1 or ctl.count("let meas_dropout_v") != 1:
        raise ValueError("dropout deck control block is not the expected manifest shape")
    ctl = ctl.replace("save all\n", "save all " + " ".join(saves) + "\n", 1)
    wr = "wrdata %s %s\n" % (dat, " ".join(spice_vec(c, variant) for c in cols))
    ctl = ctl.replace("let meas_dropout_v", wr + "let meas_dropout_v", 1)
    return deck[:i] + ctl, cols


# ---------------------------------------------------------------- thermal deck
TH_VECTORS = ["xldo.ts_cmp", "xldo.rc_a", "xldo.rc_b", "xldo.ea_out", "vout", "en",
              "xldo.ts_sns", "xldo.ts_ref"]
TH_KEYS = ["ts_cmp", "rc_a", "rc_b", "ea_out", "vout", "en", "ts_sns", "ts_ref", "ipass", "ivin"]
T_COLD, T_FORCED, T_HOLD, T_EN_LOW, T_REEN = 19, 39, 90, 108, 165  # us, run_hysteresis.py
IX = {"cold": 0.0, "hot": +0.5e-6, "cold_exc": -0.5e-6, "en": +0.5e-6}
EN_DIP = {"cold": "vsup", "hot": "vsup", "cold_exc": "vsup", "en": "0"}


def thermal_deck(body, pdk, supply, temp_c, scenario, dat="data.dat"):
    """run_hysteresis.py's deck_text() with the supply as a parameter and two more
    saved vectors (pass Id, VIN current) for the pass-off check."""
    head = [
        "* issue #357 thermal two-state deck (run_hysteresis.py stimulus) -- generated by probe.py",
        f"* corner: tt / {supply} V electrical; device temperature imposed = {temp_c} C; scenario {scenario}",
        f".param vsup={supply}", f".param ix_amp={IX[scenario]}", f".param en_dip={EN_DIP[scenario]}",
        ".option wnflag=1", f".temp {temp_c}", f'.lib "{pdk.lib_file}" tt',
    ]
    ipass = P.format(n="xm_pass", t=PF, p="id")
    ctl = [".control", "save all " + ipass, "tran 400n 170u uic",
           f"wrdata {dat} " + " ".join(f"v({v})" for v in TH_VECTORS) + f" {ipass} i(vvin)",
           "quit", ".endc", ".end", ""]
    return "\n".join(head + body + ctl)


T_STOP_US, T_STOP_TOL_US = 170, 0.5  # declared .tran stop (thermal_deck) and one-step slack


def thermal_trace_invalid_reason(path):
    """Fail-closed trace check, run before any sampling (rc.at() clamps out-of-range
    targets to an endpoint, so a truncated trace would otherwise yield usable labels).
    Returns (t, v, None) for a usable trace, else (None, None, named reason)."""
    try:
        rows = [ln.split() for ln in Path(path).read_text().splitlines() if ln.strip()]
    except (OSError, UnicodeDecodeError) as e:
        return None, None, f"unreadable data: {e}"
    if not rows:
        return None, None, "empty data"
    width = 2 * len(TH_KEYS)
    bad = [i for i, r in enumerate(rows) if len(r) != width]
    if bad:
        return None, None, f"malformed columns: row {bad[0]} has {len(rows[bad[0]])} of {width} columns"
    try:
        t, v = rc.read_dat(Path(path), TH_KEYS)
    except ValueError as e:
        return None, None, f"malformed columns: {e}"
    if any(not math.isfinite(x) for x in t):
        return None, None, "nonfinite time"
    if any(b <= a for a, b in zip(t, t[1:])):
        return None, None, "time not strictly increasing"
    if any(not math.isfinite(x) for k in TH_KEYS for x in v[k]):
        return None, None, "nonfinite vector value"
    if len(t) < 2:
        return None, None, f"too few rows: {len(t)} (need >= 2 to interpolate)"
    if t[0] > T_COLD * 1e-6:
        return None, None, (f"late-start trace: begins at {t[0] * 1e6:.3f} us, after the first "
                            f"sample time {T_COLD} us")
    if t[-1] < (T_STOP_US - T_STOP_TOL_US) * 1e-6:
        return None, None, f"truncated trace: ends at {t[-1] * 1e6:.3f} us, declared stop {T_STOP_US} us"
    return t, v, None


def thermal_result(run, supply):
    t, v, why = thermal_trace_invalid_reason(run / "data.dat")
    if why:
        return {"invalid_reason": why, "nonfinite": "nonfinite" in why}
    at = lambda k, x: rc.at(t, v[k], x)  # noqa: E731
    trip = lambda x: rc.tripped(at("ts_cmp", x), supply)  # noqa: E731
    r = {"cold_start_tripped": trip(T_COLD), "forced_tripped": trip(T_FORCED),
         "hold_tripped": trip(T_HOLD), "after_en_reenable_tripped": trip(T_REEN),
         "ts_cmp_v": {k: round(at("ts_cmp", k), 4) for k in (T_COLD, T_FORCED, T_HOLD, T_EN_LOW, T_REEN)},
         "ea_out_v": {k: round(at("ea_out", k), 4) for k in (T_COLD, T_FORCED, T_HOLD, T_REEN)},
         "vout_v": {k: round(at("vout", k), 4) for k in (T_COLD, T_FORCED, T_HOLD, T_REEN)},
         "ipass_ua": {k: round(abs(at("ipass", k)) * 1e6, 4) for k in (T_COLD, T_FORCED, T_HOLD, T_REEN)},
         "ivin_ua": {k: round(-at("ivin", k) * 1e6, 4) for k in (T_COLD, T_HOLD)},
         "sns_minus_ref_mv_at_hold": round(1e3 * (at("ts_sns", T_HOLD) - at("ts_ref", T_HOLD)), 2),
         "nonfinite": any(x != x or abs(x) == float("inf") for k in TH_KEYS for x in v[k]),
         "t_end_us": t[-1] * 1e6 if t else None}
    # pass-off witness while tripped (declared before execution, README section 3)
    r["pass_off_at_hold"] = r["ipass_ua"][T_HOLD] < 1.0
    return r


# ---------------------------------------------------------------- main
def make_netlist(bench, pdk):
    exp = cr.load_experiment(SIM / BENCH_DIR[bench])
    with tempfile.TemporaryDirectory(prefix="i357-nl-") as nl:
        net = cr.netlist_with_xschem(exp.schematic, Path(nl), pdk)
        if bench == "thermal":
            text, _n = cr.eval_xschem_exprs("\n".join(cr.netlist_body(net, eval_exprs=False)) + "\n")
            # as run_hysteresis.py: drop the dc-temp IC_SEED .nodeset so `uic` is a true cold start
            stmts = [x for x in re.split(r"\n(?!\+)", text.rstrip("\n"))
                     if not x.lower().startswith(".nodeset")]
            text = "\n".join(stmts) + "\n"
        else:
            text = "\n".join(cr.netlist_body(net)) + "\n"
    return exp, text


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", choices=list(BENCH_DIR), required=True)
    ap.add_argument("--variant", choices=["base", "cand"], required=True)
    ap.add_argument("--rev", type=int, default=0)
    ap.add_argument("--supply", type=float, required=True)
    ap.add_argument("--temp", type=float, default=27.0)
    ap.add_argument("--scenario", choices=list(IX), default=None)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args(argv)
    if (a.bench == "thermal") != (a.scenario is not None):
        sys.exit("--scenario is required for, and only for, --bench thermal")

    run = HERE / "runs" / a.run_id
    if run.exists():
        sys.exit(f"{run} exists: evidence is append-only, pick a new --run-id")
    run.mkdir(parents=True)

    pdk = cr.resolve_pdk(cr.load_pin())
    exp, raw = make_netlist(a.bench, pdk)
    (run / "netlist.raw.spice").write_text(raw)
    notes, problems = [], []
    if a.variant == "cand":
        edited, notes = cand.apply_candidate(raw, a.rev)
        problems = cand.check_candidate(raw, edited)
        if problems:
            (run / "netlist.edited.spice").write_text(edited)
            sys.exit("candidate invariant check failed: " + "; ".join(problems))
    else:
        edited = raw
    (run / "netlist.edited.spice").write_text(edited)
    diff = "".join(difflib.unified_diff(raw.splitlines(True), edited.splitlines(True),
                                        "netlist.raw.spice", "netlist.edited.spice"))
    (run / "netlist.diff").write_text(diff)

    cols = None
    if a.bench == "thermal":
        deck = thermal_deck(edited.splitlines(), pdk, a.supply, a.temp, a.scenario)
    else:
        corner = cr.Corner("tt", a.temp, a.supply)
        deck = cr.build_deck(exp, pdk, corner, edited.splitlines())
        if a.bench == "dropout":
            deck, cols = instrument_dropout(deck, a.variant)
            (run / "data.columns.json").write_text(json.dumps(cols) + "\n")
    (run / "deck.spice").write_text(deck)
    (run / ".spiceinit").write_text((SIM / "spiceinit").read_text())

    log, elapsed, rcode = pc.run_ngspice_deck(run, timeout=a.timeout)
    diag = cr.detect_solver_diagnostic(log)
    rec = {
        "run_id": a.run_id, "issue": 357, "bench": a.bench, "variant": a.variant,
        "candidate_rev": a.rev if a.variant == "cand" else None,
        "condition": {"process": "tt", "electrical_temp_c": a.temp if a.bench != "thermal" else 27.0,
                      "device_temp_imposed_c": a.temp if a.bench == "thermal" else None,
                      "supply_v": a.supply, "scenario": a.scenario},
        "edit_notes": notes, "candidate_invariant_problems": problems,
        "ngspice_exit": rcode, "elapsed_s": round(elapsed, 2), "solver_diagnostic": diag,
        "command": "python3 -B probe.py " + " ".join(sys.argv[1:] if argv is None else argv),
        "provenance": {
            "source_commit": pc.git_provenance(REPO),
            "driver_sha256": pc.sha(Path(__file__).read_bytes()),
            "candidate_py_sha256": pc.sha((HERE / "candidate.py").read_bytes()),
            "probe_common_sha256": pc.sha((SIM / "bin" / "_probe_common.py").read_bytes()),
            "experiment_json_sha256": pc.sha((SIM / BENCH_DIR[a.bench] / "experiment.json").read_bytes()),
            "testbench_sha256": pc.sha(exp.schematic.read_bytes()),
            "dut_sch_sha256": pc.sha((REPO / "design" / "ldo_3v3in_1v8out.sch").read_bytes()),
            "netlist_raw_sha256": pc.sha(raw.encode()),
            "netlist_edited_sha256": pc.sha(edited.encode()),
            "deck_sha256": pc.sha(deck.encode()),
            "spiceinit_sha256": pc.sha((SIM / "spiceinit").read_bytes()),
            "pdk": {"open_pdks_commit": pdk.installed_commit, "matches_pin": pdk.matches_pin,
                    "lib_sha256": pc.sha(Path(pdk.lib_file).read_bytes())},
            "tools": cr.tool_versions(),
        },
    }
    dat = run / "data.dat"
    if a.bench == "thermal":
        if dat.is_file():
            rec["thermal"] = thermal_result(run, a.supply)
    elif a.bench != "dropout":
        meas = cr.parse_measurements(log)
        rec["meas"] = meas
        rec["missing_measurements"] = [m.name for m in exp.measurements if m.name not in meas]
        rec["grading_vs_manifest_bounds"] = {
            m.name: {"value": meas.get(m.name), "min": m.min, "max": m.max,
                     "pass": cr.grade_bounds(m, meas.get(m.name))[0],
                     "detail": cr.grade_bounds(m, meas.get(m.name))[1]} for m in exp.measurements}
    rec["data_sha256"] = pc.sha(dat.read_bytes()) if dat.is_file() else None
    if dat.is_file():
        with open(dat, "rb") as f, gzip.open(str(dat) + ".gz", "wb", compresslevel=9) as g:
            shutil.copyfileobj(f, g)
        dat.unlink()
    (run / "result.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: rec[k] for k in ("run_id", "ngspice_exit", "elapsed_s", "solver_diagnostic")}))
    if "meas" in rec:
        for k, g in rec["grading_vs_manifest_bounds"].items():
            print(f"  {k} = {g['value']}  [{g['min']}, {g['max']}]  {'pass' if g['pass'] else 'FAIL'}")
    if "thermal" in rec:
        th = rec["thermal"]
        if th.get("invalid_reason"):
            print(f"  thermal INVALID: {th['invalid_reason']}")
            return
        print(f"  forced={th['forced_tripped']} hold={th['hold_tripped']} cold={th['cold_start_tripped']} "
              f"reen={th['after_en_reenable_tripped']} ipass@hold={th['ipass_ua'][T_HOLD]}uA ea_out@hold={th['ea_out_v'][T_HOLD]}")


if __name__ == "__main__":
    main()
