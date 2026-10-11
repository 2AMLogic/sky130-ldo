#!/usr/bin/env python3
"""Capacitor-implementation comparison study (issue #319). Standard library only.

Compares on-chip implementations of the schematic's four capacitors (MiM,
stacked MiM, sky130 ``cap_vpp`` cells, ``cap_var`` MOS varactors) against the
ratified Area row, from the pinned PDK's own model/layout files plus two kinds
of simulation evidence:

* ``op``  -- the capacitor terminal voltages over the bounded matrix
  (process_corners x -40/27/125 C x 2.97/3.30/3.63 V x 0/50 mA). Each point is
  the repo's cold-start settled operating point (contract #171: ``tran 10u
  200m uic`` with EN stepping high, terminal voltages averaged over 199-200 ms),
  NOT a bare ``.op`` (#164: unconstrained ``.op`` is not a physically
  realisable state of this block). The grid is submitted to ``klt sim
  --backend batch`` -- six requests (supply x load), each process x
  temperature. A failed submit is recorded, never replaced by a local grid.
* ``op-local`` -- exactly ONE point through ``klt sim --backend local`` (a
  single-unit debug probe, allowed on this host).
* ``cv``  -- the varactor C(V) sweep through ``klt sim``: ``--backend local``
  for the single tt/27 C unit, ``--backend batch`` for the corner x
  temperature grid.
* ``matrix`` -- assembles ``matrix.json`` deterministically from the PDK
  files and whatever evidence the record directory holds; anything missing
  becomes ``unmeasured``. Re-running it on the same inputs reproduces the file
  byte for byte (no timestamps inside).

Usage (from the repo root)::

    python3 layout/cap-study/run-cap-study.py prepare  --record layout/cap-study/<id>
    python3 layout/cap-study/run-cap-study.py op       --record layout/cap-study/<id>
    python3 layout/cap-study/run-cap-study.py op-local --record layout/cap-study/<id> --point tt,27,3.3,0
    python3 layout/cap-study/run-cap-study.py cv       --record layout/cap-study/<id> --backend local
    python3 layout/cap-study/run-cap-study.py cv       --record layout/cap-study/<id> --backend batch
    python3 layout/cap-study/run-cap-study.py matrix   --record layout/cap-study/<id>
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT / "sim" / "bin"))

import _cap_study as cs  # noqa: E402

TESTBENCH = REPO_ROOT / "sim" / "load-regulation" / "testbench" / "tb_load_regulation.sch"
SCHEMATIC = "design/ldo_3v3in_1v8out.sch"
AREA_STUDY = REPO_ROOT / "layout" / "area-study" / "20261009-study-246" / "budget.json"
CAP_RAIL_LATEST = REPO_ROOT / "layout" / "cap-rail-demo" / "reports" / "LATEST"
LOOP_GAIN_RECORD = REPO_ROOT / "sim" / "loop-gain" / "records" / "20260926-040338-4a9ec09.json"

TEMPS_C = [-40.0, 27.0, 125.0]
SUPPLIES_V = [2.97, 3.30, 3.63]
LOADS = [("0ma", "0"), ("50ma", "50m")]
OP_TRAN = "10u 200m uic"
OP_WINDOW = ("199m", "200m")
OP_TIMEOUT_S = 1800

# Varactor C(V) sweep: plate (c0 - c1) bias from the model's own SOA bound.
CV_FLAVORS = ["lvt", "hvt"]
CV_GEOMS = [(5.0, 0.5), (10.0, 10.0)]  # (w, l) um: the model's default and a large unit
CV_STEP_V = 0.1
CV_FREQS_HZ = [1e3]  # + the loop's unity-gain frequency, read from a sim/ record
CV_TIMEOUT_S = 600

VPP_PIN_RE = re.compile(r'\.include\s+"([^"]*sky130_fd_pr__cap_vpp_[^"]+)"', re.I)


# --------------------------------------------------------------------------
# PDK / repo access
# --------------------------------------------------------------------------


def corner_run():
    from _record_common import load_corner_run_module  # noqa: E402
    return load_corner_run_module(REPO_ROOT / "sim" / "bin")


def pdk_ctx():
    cr = corner_run()
    pin = cr.load_pin()
    pdk = cr.resolve_pdk(pin)
    return cr, pin, pdk


def pdk_ref(pdk_dir: Path, p: Path) -> str:
    """A PDK file named relative to the variant dir, e.g. ``sky130A/libs.tech/...``."""
    try:
        return f"{pdk_dir.name}/{p.resolve().relative_to(pdk_dir.resolve())}"
    except ValueError:
        try:
            return f"{pdk_dir.name}/{p.resolve().relative_to(pdk_dir.resolve().parent / pdk_dir.name)}"
        except ValueError:
            return str(p)


def resolve_inc(base: Path, inc: str) -> Path:
    return (base.parent / inc).resolve()


# --------------------------------------------------------------------------
# prepare: netlist the testbench and write the op-point requests
# --------------------------------------------------------------------------


def op_meas_nodes(caps: list[dict]) -> list[str]:
    nets = []
    for c in caps:
        for n in c["nets"]:
            if n != "0" and n not in nets:
                nets.append(n)
    return nets


def op_request(netlist_path: Path, pdk, process: list[str], temps: list[float], nodes: list[str]) -> dict:
    meas = []
    for n in nodes:
        meas.append({
            "name": cs.meas_name("v", n),
            "spice": f".meas tran {cs.meas_name('v', n)} avg v({cs.node_ident(n)}) "
                     f"from={OP_WINDOW[0]} to={OP_WINDOW[1]}",
            "unit": "V",
        })
    return {
        "netlist": str(netlist_path),
        "engine": "ngspice",
        "models": {"pdk": pdk.variant, "lib": str(pdk.lib_file.relative_to(pdk.dir))},
        "corners": {"process": list(process), "temperature_c": list(temps)},
        "analysis": {"kind": "tran", "args": OP_TRAN},
        "measurements": meas,
        "options": {"timeout_s": OP_TIMEOUT_S, "keep_artifacts": True,
                    "ngspice_init": corner_run().spiceinit_lines()},
    }


def cv_freqs() -> list[float]:
    f = list(CV_FREQS_HZ)
    ugf = loop_ugf()
    if ugf is not None:
        f.append(round(ugf["tt_27c_3.30v_hz"], 1))
    return f


def cv_netlist(flavors=CV_FLAVORS, geoms=CV_GEOMS, step=CV_STEP_V, soa=2.301) -> tuple[list[str], list[dict]]:
    """One netlist holding every (flavor, geometry, bias) point as its own
    varactor, AC-driven by a 1 A current source; its DC bias comes from a
    voltage source through 1 Tohm. Then C = -1/(2 pi f Im(V))."""
    n = int(math.floor(soa / step + 1e-9))
    biases = [round(k * step, 6) for k in range(-n, n + 1)]
    lines = ["* varactor C(V) sweep (issue #319): c0 = plate under test, c1 = 0, b = 0"]
    points = []
    for fl in flavors:
        for (w, l) in geoms:
            for b in biases:
                tag = f"{fl}_w{w:g}_l{l:g}_{'m' if b < 0 else 'p'}{abs(b):.2f}".replace(".", "p")
                lines += [
                    f"VB_{tag} b_{tag} 0 dc {b}",
                    f"RB_{tag} b_{tag} n_{tag} 1e12",
                    f"IA_{tag} 0 n_{tag} dc 0 ac 1",
                    f"X_{tag} n_{tag} 0 0 sky130_fd_pr__cap_var_{fl} w={w:g} l={l:g}",
                ]
                points.append({"tag": tag, "flavor": fl, "w_um": w, "l_um": l, "bias_v": b})
    return lines, points


def cv_request(netlist_path: Path, pdk, process: list[str], temps: list[float], points: list[dict],
               freqs: list[float]) -> dict:
    meas = []
    for p in points:
        for i, f in enumerate(freqs):
            meas.append({"name": f"vi_{p['tag']}_f{i}",
                         "spice": f".meas ac vi_{p['tag']}_f{i} find vi(n_{p['tag']}) at={f:g}",
                         "unit": "V"})
    # ngspice's `ac lin 2 a b` yields ONE row (measured with ngspice 42), so the
    # sweep uses 3 points; the midpoint is not reported.
    if len(freqs) == 2:
        fargs = f"lin 3 {freqs[0]:g} {freqs[1]:g}"
    elif len(freqs) == 1:
        fargs = f"lin 3 {freqs[0]:g} {2 * freqs[0]:g}"
    else:
        raise ValueError("cv_request supports one or two report frequencies")
    return {
        "netlist": str(netlist_path),
        "engine": "ngspice",
        "models": {"pdk": pdk.variant, "lib": str(pdk.lib_file.relative_to(pdk.dir))},
        "corners": {"process": list(process), "temperature_c": list(temps)},
        "analysis": {"kind": "ac", "args": fargs},
        "measurements": meas,
        "options": {"timeout_s": CV_TIMEOUT_S, "keep_artifacts": True,
                    "ngspice_init": corner_run().spiceinit_lines()},
    }


def cmd_prepare(args) -> int:
    cr, pin, pdk = pdk_ctx()
    rec = Path(args.record).resolve()
    if (rec / "op" / "netlist.spice").exists():
        raise SystemExit(f"{rec} already prepared (append-only; mint a new record directory)")
    (rec / "op" / "requests").mkdir(parents=True, exist_ok=True)
    scratch = REPO_ROOT / "sim" / "build" / "cap-study" / rec.name
    nl = cr.netlist_with_xschem(TESTBENCH, scratch / "xschem", pdk)
    body = cr.netlist_body(nl)
    text = "\n".join(body) + "\n"
    (rec / "op" / "netlist.spice").write_text(text)
    caps = cs.netlist_caps(text)
    (rec / "op" / "terminals.json").write_text(json.dumps(
        {"source": "xschem netlist of sim/load-regulation/testbench/tb_load_regulation.sch "
                   f"(DUT {SCHEMATIC}); terminals only, not voltages",
         "capacitors": caps}, indent=2, sort_keys=True) + "\n")
    nodes = op_meas_nodes(caps)
    procs = list(pin["process_corners"])
    for vs in SUPPLIES_V:
        for lname, lval in LOADS:
            key = f"v{vs:.2f}_{lname}"
            npath = rec / "op" / "requests" / f"{key}.spice"
            head = [f".param vsup={vs}", ".option wnflag=1", ".save all"]
            npath.write_text("\n".join(head) + "\n" + cs.set_load(text, lval))
            req = op_request(Path(npath.name), pdk, procs, TEMPS_C, nodes)  # relative to the request file
            (rec / "op" / "requests" / f"{key}.json").write_text(json.dumps(req, indent=2, sort_keys=True) + "\n")
    # C(V) netlist + requests
    (rec / "cv").mkdir(parents=True, exist_ok=True)
    lines, points = cv_netlist()
    (rec / "cv" / "netlist.spice").write_text("\n".join(lines) + "\n")
    (rec / "cv" / "points.json").write_text(json.dumps({"points": points, "freqs_hz": cv_freqs()},
                                                       indent=2, sort_keys=True) + "\n")
    print(f"prepared {rec}: {len(caps)} capacitors, nodes {nodes}, {len(SUPPLIES_V) * len(LOADS)} op requests, "
          f"{len(points)} C(V) points")
    return 0


# --------------------------------------------------------------------------
# running klt sim
# --------------------------------------------------------------------------


_BUCKET_RE = re.compile(r"\b2am-batch-jobs-[0-9]+\b")


def scrub(text: str, pdk_root: Path | None = None) -> str:
    """Saved artifacts name repo files relative to the repo root, the PDK as
    ``$PDK_ROOT/...``, and do not carry the fleet's job-bucket name (it
    encodes deployment account detail)."""
    text = _BUCKET_RE.sub("<batch-job-bucket>", text).replace(str(REPO_ROOT) + os.sep, "")
    if pdk_root is not None:
        text = text.replace(str(pdk_root.resolve()) + os.sep, "$PDK_ROOT/")
        text = text.replace(str(pdk_root) + os.sep, "$PDK_ROOT/")
    return text


def scrub_tree(outdir: Path, pdk_root: Path) -> None:
    for f in sorted(outdir.rglob("*")):
        if f.is_file() and f.suffix in (".json", ".cir", ".log", ".stdout", ".stderr", ".spice"):
            t = f.read_text(errors="replace")
            u = scrub(t, pdk_root)
            if u != t:
                f.write_text(u)


def job_failed(summary: dict, outdir: Path) -> bool:
    """True when klt returned no response or the fleet job itself failed (no
    corner was simulated) -- the signal to stop submitting further requests."""
    if summary.get("status") == "no-response":
        return True
    remote = ((summary.get("remote") or {}).get("remote") or {})
    return remote.get("state") == "failed"


def run_klt(request: dict, req_path: Path, outdir: Path, backend: str, pdk_root: Path) -> dict:
    """One ``klt sim`` call, never retried and never replaced by another backend.
    Returns a summary dict that is written next to the raw stdout/stderr."""
    cr = corner_run()
    outdir = outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    req_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")
    cmd = [cr.klt_binary(), "sim", str(req_path.resolve()), "-o", str(outdir), "--backend", backend,
           "--format", "json"]
    env = dict(os.environ, PDK_ROOT=str(pdk_root))
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    stdout, stderr = scrub(proc.stdout or "", pdk_root), scrub(proc.stderr or "", pdk_root)
    (outdir / "klt.stderr").write_text(stderr)
    ids = sorted(set(cr._JOB_ID_RE.findall(stdout + stderr)))
    summary = {"cmd": [Path(cmd[0]).name] + [scrub(c, pdk_root) for c in cmd[1:]], "returncode": proc.returncode,
               "backend": backend, "job_ids_seen": ids}
    try:
        resp = json.loads(stdout)
    except json.JSONDecodeError:
        resp = None
    if isinstance(resp, dict) and isinstance(resp.get("corners"), list):
        (outdir / "response.json").write_text(stdout)  # klt's own JSON, verbatim (scrubbed)
        summary["response"] = "response.json"
        summary["remote"] = cr.batch_remote_info(resp)
        summary["status"] = resp.get("status")
    else:
        (outdir / "klt.stdout").write_text(stdout)
        summary["response"] = None
        summary["status"] = "no-response"
        summary["error"] = (stderr + stdout).strip()[-3000:]
    (outdir / "submission.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    scrub_tree(outdir, pdk_root)
    return summary


def cmd_op(args) -> int:
    cr, pin, pdk = pdk_ctx()
    rec = Path(args.record).resolve()
    reqs = sorted((rec / "op" / "requests").glob("*.json"))
    if not reqs:
        raise SystemExit("run `prepare` first")
    failures = 0
    for rp in reqs:
        key = rp.stem
        out = rec / "op" / "batch" / key
        if (out / "submission.json").exists():
            print(f"{key}: already submitted (append-only), skipping")
            continue
        req = json.loads(rp.read_text())
        req["netlist"] = str((rec / "op" / "requests" / f"{key}.spice").resolve())
        print(f"submitting {key} to klt sim --backend batch ...", flush=True)
        s = run_klt(req, out / "request.json", out, "batch", pdk.root)
        print(f"  {key}: rc {s['returncode']} status {s['status']} jobs {s['job_ids_seen']}", flush=True)
        if job_failed(s, out):
            failures += 1
            print("  the job did not run; not retried, NO local fallback. Remaining requests NOT submitted "
                  "(the same runner would refuse them).")
            break
    return 1 if failures else 0


def cmd_op_local(args) -> int:
    cr, pin, pdk = pdk_ctx()
    rec = Path(args.record).resolve()
    proc, temp, vs, load = args.point.split(",")
    lval = dict(LOADS)
    lname = {"0": "0ma", "50": "50ma"}[load]
    key = f"v{float(vs):.2f}_{lname}"
    rp = rec / "op" / "requests" / f"{key}.json"
    req = json.loads(rp.read_text())
    req["netlist"] = str((rec / "op" / "requests" / f"{key}.spice").resolve())
    req["corners"] = {"process": [proc], "temperature_c": [float(temp)]}
    out = rec / "op" / "local" / f"{proc}_{float(temp):g}c_{key}"
    if (out / "submission.json").exists():
        raise SystemExit(f"{out} exists (append-only)")
    assert lval[lname] is not None
    s = run_klt(req, out / "request.json", out, "local", pdk.root)
    print(json.dumps({k: s[k] for k in ("returncode", "status")}))
    return 0 if s["status"] != "no-response" else 1


def cmd_cv(args) -> int:
    cr, pin, pdk = pdk_ctx()
    rec = Path(args.record).resolve()
    meta = json.loads((rec / "cv" / "points.json").read_text())
    npath = (rec / "cv" / "netlist.spice").resolve()
    if args.backend == "local":
        procs, temps, sub = ["tt"], [27.0], "local_tt_27c"
    else:
        procs = [p for p in pin["process_corners"]]
        temps, sub = TEMPS_C, "batch"
    out = rec / "cv" / sub
    if (out / "submission.json").exists():
        raise SystemExit(f"{out} exists (append-only)")
    req = cv_request(npath, pdk, procs, temps, meta["points"], meta["freqs_hz"])
    s = run_klt(req, out / "request.json", out, args.backend, pdk.root)
    print(json.dumps({k: s[k] for k in ("returncode", "status", "job_ids_seen")}))
    return 0 if s["status"] != "no-response" else 1


# --------------------------------------------------------------------------
# evidence readers
# --------------------------------------------------------------------------


def loop_ugf() -> dict | None:
    """Unity-gain (crossover) frequency of the loop from an existing sim/ record."""
    if not LOOP_GAIN_RECORD.is_file():
        return None
    d = json.loads(LOOP_GAIN_RECORD.read_text())
    vals, tt = [], None
    for c in d.get("corners", []):
        for m in c.get("measurements", []):
            if m.get("name") == "fc_c033_50ma_hz" and isinstance(m.get("value"), (int, float)):
                vals.append(float(m["value"]))
                if c.get("corner_id") == "tt_27c_3.30v":
                    tt = float(m["value"])
    if not vals or tt is None:
        return None
    return {"tt_27c_3.30v_hz": tt, "min_hz": min(vals), "max_hz": max(vals), "n_corners": len(vals),
            "measurement": "fc_c033_50ma_hz",
            "source": str(LOOP_GAIN_RECORD.relative_to(REPO_ROOT))}


def _resp_points(resp: dict) -> list[dict]:
    out = []
    for c in resp.get("corners", []):
        if not isinstance(c, dict):
            continue
        ms = {}
        for m in c.get("measurements", []) or []:
            if isinstance(m, dict) and isinstance(m.get("value"), (int, float)) and math.isfinite(m["value"]):
                ms[m["name"]] = float(m["value"])
        out.append({"process": c.get("process"), "temperature_c": c.get("temperature_c"),
                    "status": c.get("status"), "measurements": ms,
                    "diagnostics": [d.get("code") for d in c.get("diagnostics", []) or [] if isinstance(d, dict)]})
    return out


def read_op(rec: Path, caps: list[dict], process_corners: list[str]) -> dict:
    """Every point of the bounded matrix: plate voltages or ``unmeasured``."""
    found: dict[tuple, dict] = {}
    subs = []
    for kind in ("batch", "local"):
        base = rec / "op" / kind
        if not base.is_dir():
            continue
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            sub = json.loads((d / "submission.json").read_text()) if (d / "submission.json").is_file() else None
            if sub is None:
                continue
            req = json.loads((d / "request.json").read_text())
            m = re.search(r"v(\d+\.\d+)_(\d+ma)", d.name)
            subs.append({"dir": str(d.relative_to(rec)), "backend": sub.get("backend"),
                         "status": sub.get("status"), "returncode": sub.get("returncode"),
                         "job_ids": sub.get("job_ids_seen"),
                         "remote": {k: (sub.get("remote") or {}).get("remote", {}).get(k)
                                    for k in ("job_id", "state", "exit_code", "runner_klt_version",
                                              "client_klt_version", "runner_compatibility")}
                         if sub.get("remote") else None,
                         "error": (sub.get("error") or "")[-600:] or None,
                         "corners": req.get("corners")})
            if not m or sub.get("response") is None:
                continue
            vs, load = float(m.group(1)), m.group(2)
            resp = json.loads((d / "response.json").read_text())
            for p in _resp_points(resp):
                found[(p["process"], float(p["temperature_c"]), vs, load)] = {**p, "backend": kind,
                                                                             "dir": str(d.relative_to(rec))}
    points = []
    for proc in process_corners:
        for t in TEMPS_C:
            for vs in SUPPLIES_V:
                for lname, _ in LOADS:
                    key = (proc, t, round(vs, 2), lname)
                    p = found.get(key)
                    row = {"process": proc, "temperature_c": t, "supply_v": vs, "load": lname}
                    if p is None:
                        row["status"] = cs.UNMEASURED
                        row["caps"] = {c["name"]: cs.unmeasured("point not run (see submissions)") for c in caps}
                    else:
                        row["status"] = p["status"]
                        row["source"] = p["dir"]
                        row["diagnostics"] = p["diagnostics"]
                        row["caps"] = {}
                        for c in caps:
                            v = []
                            for n in c["nets"]:
                                v.append(0.0 if n == "0" else p["measurements"].get(cs.meas_name("v", n)))
                            if "batch_job_failed" in p["diagnostics"]:
                                row["caps"][c["name"]] = cs.unmeasured(
                                    "not simulated: the batch job failed before running (see submissions)")
                            elif p["status"] not in ("pass", "ok") or None in v:
                                row["caps"][c["name"]] = cs.unmeasured(
                                    f"corner status {p['status']!r} or value missing (non-convergent/not measured)")
                            else:
                                row["caps"][c["name"]] = {"v_plus_v": round(v[0], 6), "v_minus_v": round(v[1], 6),
                                                          "v_plate_v": round(v[0] - v[1], 6),
                                                          "nets": c["nets"], "source": p["dir"]}
                    points.append(row)
    return {"points": points, "submissions": subs}


def read_cv(rec: Path) -> dict:
    meta_p = rec / "cv" / "points.json"
    if not meta_p.is_file():
        return {"runs": [], "submissions": []}
    meta = json.loads(meta_p.read_text())
    freqs = meta["freqs_hz"]
    runs, subs = [], []
    for d in sorted(p for p in (rec / "cv").iterdir() if p.is_dir()):
        sub = json.loads((d / "submission.json").read_text()) if (d / "submission.json").is_file() else None
        if sub is None:
            continue
        subs.append({"dir": str(d.relative_to(rec)), "backend": sub.get("backend"), "status": sub.get("status"),
                     "returncode": sub.get("returncode"), "job_ids": sub.get("job_ids_seen"),
                     "error": (sub.get("error") or "")[-600:] or None})
        if sub.get("response") is None:
            continue
        resp = json.loads((d / "response.json").read_text())
        for p in _resp_points(resp):
            curves = {}
            for pt in meta["points"]:
                key = f"{pt['flavor']}_w{pt['w_um']:g}_l{pt['l_um']:g}"
                cur = curves.setdefault(key, {"flavor": pt["flavor"], "w_um": pt["w_um"], "l_um": pt["l_um"],
                                              "bias_v": [], "c_f": {f"{f:g}": [] for f in freqs}})
                cur["bias_v"].append(pt["bias_v"])
                for i, f in enumerate(freqs):
                    vi = p["measurements"].get(f"vi_{pt['tag']}_f{i}")
                    c = cs.c_from_vi(vi, f) if vi is not None else None
                    cur["c_f"][f"{f:g}"].append(None if c is None else float(f"{c:.6e}"))
            runs.append({"process": p["process"], "temperature_c": p["temperature_c"], "status": p["status"],
                         "source": str(d.relative_to(rec)), "curves": curves})
    return {"freqs_hz": freqs, "runs": runs, "submissions": subs}


# --------------------------------------------------------------------------
# matrix
# --------------------------------------------------------------------------


def mim_rows(pdk) -> dict:
    cont = pdk.dir / "libs.tech" / "combined" / "continuous"
    mc = (cont / "models_capacitors.spice").read_text()
    out = {"formula_ok": {n: cs.mim_subckt_formula_ok(mc, n) for n in
                          ("sky130_fd_pr__cap_mim_m3_1", "sky130_fd_pr__cap_mim_m3_2")},
           "formula_source": pdk_ref(pdk.dir, cont / "models_capacitors.spice"), "corners": {}}
    for corner, fname in (("tt", "parameters_cap_nom.spice"), ("ll", "parameters_cap_low.spice"),
                          ("hh", "parameters_cap_high.spice")):
        p = cs.parse_params((cont / fname).read_text())
        ca = cs.eval_corner_param(p["sw_cap_mim_ca"])  # F/um^2
        dw = cs.eval_corner_param(p["sw_cap_mim_dw"])  # m
        out["corners"][corner] = {"ca_f_per_um2": ca, "dw_um": dw * 1e6,
                                  "source": f"{pdk_ref(pdk.dir, cont / fname)}: sw_cap_mim_ca, sw_cap_mim_dw"}
    return out


def vpp_rows(pdk) -> list[dict]:
    comb = pdk.dir / "libs.tech" / "combined"
    rescap = comb / "rescap"
    envs = {}
    for corner, fname in (("tt", "res_typical__cap_typical__lin.spice"), ("ll", "res_low__cap_low__lin.spice"),
                          ("hh", "res_high__cap_high__lin.spice")):
        raw = cs.parse_params((rescap / fname).read_text())
        env = {}
        for k, v in raw.items():
            try:
                env[k] = cs.eval_expr(v, {})
            except (KeyError, ValueError):
                pass
        envs[corner] = (env, f"{pdk_ref(pdk.dir, rescap / fname)}")
    # Only the vpp cells the pinned combined library actually includes are simulatable.
    included: list[Path] = []
    for f in sorted(rescap.glob("sky130_fd_pr__model__cap_vpp*.model.spice")):
        for inc in VPP_PIN_RE.findall(f.read_text()):
            included.append(resolve_inc(f, inc))
    mag_dir = pdk.dir / "libs.ref" / "sky130_fd_pr" / "mag"
    rows = []
    for mp in sorted(set(included)):
        text = mp.read_text() if mp.is_file() else ""
        hdr_names = re.findall(r"^\s*\.subckt\s+(\S+)", text, re.M | re.I)
        if not hdr_names:
            continue
        name = hdr_names[0]
        row = {"cell": name, "model_source": pdk_ref(pdk.dir, mp), "rat_sum": cs.vpp_rat_sum(text)}
        mag = mag_dir / f"{name}.mag"
        bb = cs.mag_bbox(mag.read_text()) if mag.is_file() else None
        row["layout_source"] = pdk_ref(pdk.dir, mag) if mag.is_file() else None
        if bb is None:
            row["bbox"] = cs.unmeasured("no flat .mag cell in the pinned PDK for this model")
        else:
            row["bbox"] = {**bb, "source": row["layout_source"]}
        row["ctot_f"] = {}
        row["density_f_per_um2"] = {}
        for corner, (env, src) in envs.items():
            c = cs.vpp_ctot(text, env)
            if c is None:
                row["ctot_f"][corner] = cs.unmeasured("model has no evaluable ctot_a")
                row["density_f_per_um2"][corner] = cs.unmeasured("no ctot_a")
                continue
            row["ctot_f"][corner] = {"value": float(f"{c:.6e}"), "unit": "F",
                                     "source": f"{row['model_source']}: ctot_a with corner factors of {src}"}
            if bb is None:
                row["density_f_per_um2"][corner] = cs.unmeasured("no layout bbox")
            else:
                row["density_f_per_um2"][corner] = {"value": float(f"{c / bb['area_um2']:.6e}"),
                                                    "unit": "F/um^2",
                                                    "source": "ctot_a / .mag bounding-box area"}
        rows.append(row)
    return rows


def var_soa_rows(pdk) -> dict:
    spice = pdk.dir / "libs.ref" / "sky130_fd_pr" / "spice"
    out = {}
    for fl in CV_FLAVORS:
        f = spice / f"sky130_fd_pr__cap_var_{fl}.model.spice"
        soa = cs.var_soa(f.read_text(), fl)
        out[fl] = {**soa, "source": f"{pdk_ref(pdk.dir, f)}: sky130_fd_pr__cap_var_{fl}__vgs_min/max"} \
            if soa else cs.unmeasured("SOA parameters not found")
    return out


def budget(rec: Path) -> list[dict]:
    t = json.loads((rec / "op" / "terminals.json").read_text())
    return t["capacitors"]


def build_matrix(rec: Path) -> dict:
    cr, pin, pdk = pdk_ctx()
    caps = budget(rec)
    total = sum(c["value_f"] for c in caps)
    a246 = json.loads(AREA_STUDY.read_text())
    core_d = a246["scenarios_um2"]["D_C_plus_net_mos_change_to_current_schematic"]
    cap_rail_id = CAP_RAIL_LATEST.read_text().strip()
    cap_rail = json.loads((CAP_RAIL_LATEST.parent / cap_rail_id / "summary.json").read_text())
    ugf = loop_ugf()
    op = read_op(rec, caps, list(pin["process_corners"]))
    cv = read_cv(rec)
    mim = mim_rows(pdk)
    vpps = vpp_rows(pdk)
    soa = var_soa_rows(pdk)

    def split_area(density: float) -> dict:
        return {c["name"]: round(cs.area_for(c["value_f"], density), 1) for c in caps}

    ref = {
        "limit_um2": cs.LIMIT_UM2, "limit_source": "spec/target-spec.md Area row (< 0.1 mm^2, strict)",
        "core_without_caps_um2": core_d,
        "core_without_caps_source": f"{AREA_STUDY.relative_to(REPO_ROOT)}: scenarios_um2."
                                    "D_C_plus_net_mos_change_to_current_schematic",
        "E1_um2": a246["scenarios_um2"]["E_D_plus_caps_beside_single_mim_cap_mim_m3_1"],
        "E2_um2": a246["scenarios_um2"]["E_D_plus_caps_beside_stacked_two_mim_assumed"],
        "convention": "drawn-capacitor area = C / areal density (no spacing, routing, perimeter term or "
                      "keep-out), the #246 cap_area_um2 convention; 'beside' total = core_without_caps + "
                      "drawn-capacitor area (#246 scenario E). Keep-out-inclusive figures are reported "
                      "separately and only where a drawn record measured them.",
    }
    options = []

    # --- 1. single-level MiM ------------------------------------------------
    def mim_option(oid, label, devices, levels_factor, levels, overlay, extra):
        dens, area, beside = {}, {}, {}
        for corner, row in mim["corners"].items():
            d = row["ca_f_per_um2"] * levels_factor
            dens[corner] = cs.cell(float(f"{d:.6e}"), "F/um^2",
                                   row["source"] + (f" (x{levels_factor} levels in one footprint)"
                                                    if levels_factor > 1 else ""))
            a = cs.area_for(total, d)
            area[corner] = cs.cell(round(a, 1), "um^2", f"{total:.4g} F / density")
            beside[corner] = cs.cell(round(core_d + a, 1), "um^2", "core_without_caps + drawn area")
        return {"id": oid, "label": label, "devices": devices,
                "model_formula_area_only": all(mim["formula_ok"].values()),
                "model_formula_source": mim["formula_source"],
                "voltage_dependence": cs.cell(0.0, "1/V", f"{mim['formula_source']}: C = sw_cap_mim_ca*(w+dw)*(l+dw)"
                                              " has no voltage or temperature term"),
                "density_f_per_um2": dens, "area_162pf_um2": area,
                "split_area_tt_um2": split_area(dens["tt"]["value"]),
                "beside_total_um2": beside, "metal_levels": levels, "overlay": overlay, **extra}

    single_overlay = {
        "over_core": "conflicts",
        "detail": "met3 is the bottom plate; the #254 assignment keeps met3 for the VIN rail column over "
                  "the pass device. #254 computed (arithmetic, not drawn) that one MiM level needs "
                  f"{cap_rail['single_mim_level_counterfactual']['block_area_um2']:.0f} um^2 of blocks, more "
                  f"than the {cap_rail['totals']['overlay_usable_um2']:.0f} um^2 overlay area outside the rail "
                  "column, so only part of the budget could overlay.",
        "source": f"layout/cap-rail-demo/reports/{cap_rail_id}/record.md",
    }
    o1 = mim_option("mim_m3_1", "MiM cap_mim_m3_1 (met3-capm), one level", ["sky130_fd_pr__cap_mim_m3_1"], 1,
                    ["met3", "capm", "via3", "met4"], single_overlay,
                    {"requalification": "required only for parasitics of the final placement (same device as the "
                                        "schematic's ideal capacitor law)"})
    beside_lb = o1["beside_total_um2"]["tt"]["value"]
    # Partial overlay (part of the budget over the core, the rest beside) is
    # geometrically possible and no record has drawn or priced it, so this is
    # not a no-fit: missing evidence never becomes 'does-not-fit'.
    o1["verdict"] = cs.fit_verdict(beside_lb, keepout_known=False, overlay_possible=True,
                                   overlay_evidenced_below_limit=False)
    o1["verdict_reason"] = ("beside the core the drawn-area lower bound "
                            f"{beside_lb:.0f} um^2 already breaks the limit and full overlay does not fit "
                            "(#254 arithmetic), but a mixed overlay + beside placement has not been drawn or "
                            "priced by any record")
    options.append(o1)

    # --- 2. stacked MiM -------------------------------------------------------
    stacked_overlay = {
        "over_core": "drawn",
        "detail": "#254 drew all four capacitors as stacked cap_mim_m3_1 + cap_mim_m3_2 over the planned core, "
                  "met3 kept out of the pass-device rail column; DRC clean (klt + official sky130A_mr.drc), "
                  "LVS match. This study does not redo it.",
        "source": f"layout/cap-rail-demo/reports/{cap_rail_id}/record.md",
    }
    o2 = mim_option("mim_stacked", "Stacked MiM cap_mim_m3_1 + cap_mim_m3_2 (met3-capm / met4-capm2)",
                    ["sky130_fd_pr__cap_mim_m3_1", "sky130_fd_pr__cap_mim_m3_2"], 2,
                    ["met3", "capm", "via3", "met4", "capm2", "via4", "met5"], stacked_overlay,
                    {"requalification": "required: plate-to-circuit coupling and the full-core parasitics "
                                        "(owned by #231, as #254 states)"})
    o2["drawn_evidence"] = cs_drawn_evidence(cap_rail, cap_rail_id)
    o2["model_check_of_246_E2"] = (
        "both MiM classes use the same sw_cap_mim_ca, so two levels in one footprint give "
        f"{2 * mim['corners']['tt']['ca_f_per_um2'] * 1e15:.2f} fF/um^2 by the model (tt); the drawn #254 "
        "arrays reach the density in drawn_evidence once straps and taps are counted")
    rect = o2["drawn_evidence"].get("core_rectangle_um2")
    o2["verdict"] = cs.fit_verdict(o2["beside_total_um2"]["tt"]["value"], keepout_known=True, overlay_possible=True,
                                   overlay_evidenced_below_limit=isinstance(rect, (int, float)) and rect < cs.LIMIT_UM2)
    o2["verdict_reason"] = ("a drawn, DRC/LVS-clean overlay record places all four capacitors inside a planned "
                            "core rectangle below the limit, conditional on that record's stated assumptions")
    options.append(o2)

    # --- 3. vpp ------------------------------------------------------------------
    usable = [r for r in vpps if not cs.is_unmeasured(r["bbox"]) and not cs.is_unmeasured(r["density_f_per_um2"]["tt"])]
    usable.sort(key=lambda r: (-r["density_f_per_um2"]["tt"]["value"], r["cell"]))
    best = usable[0] if usable else None
    o3 = {"id": "vpp", "label": "Vertical-parallel-plate cap_vpp (fixed PDK cells)",
          "cells_evaluated": vpps,
          "selection_rule": "densest cell by ctot_a(tt) / .mag bounding-box area among the vpp models the "
                            "pinned combined library includes and that have a flat .mag cell"}
    if best is None:
        o3.update({"density_f_per_um2": {c: cs.unmeasured("no evaluable vpp cell") for c in ("tt", "ll", "hh")}})
    else:
        o3["selected_cell"] = best["cell"]
        o3["density_f_per_um2"] = best["density_f_per_um2"]
        o3["area_162pf_um2"] = {}
        o3["beside_total_um2"] = {}
        for corner, d in best["density_f_per_um2"].items():
            if cs.is_unmeasured(d):
                o3["area_162pf_um2"][corner] = d
                o3["beside_total_um2"][corner] = d
                continue
            a = cs.area_for(total, d["value"])
            o3["area_162pf_um2"][corner] = cs.cell(round(a, 1), "um^2", f"{total:.4g} F / density")
            o3["beside_total_um2"][corner] = cs.cell(round(core_d + a, 1), "um^2", "core_without_caps + drawn area")
        o3["split_area_tt_um2"] = split_area(best["density_f_per_um2"]["tt"]["value"])
        o3["metal_levels"] = best["bbox"]["levels"]
        o3["unit_cells_for_162pf_tt"] = math.ceil(total / best["ctot_f"]["tt"]["value"])
    o3["voltage_dependence"] = cs.unmeasured("the vpp models are linear capacitors (no voltage term in ctot_a); "
                                             "no C(V) measured")
    lower_levels = sorted({lv for r in usable for lv in r["bbox"]["levels"]} & {"poly", "li1", "met1", "met2"})
    o3["overlay"] = {
        "over_core": "conflicts",
        "detail": "every evaluated vpp cell uses at least one of li1/met1/met2 "
                  f"(levels seen: {', '.join(lower_levels)}), the levels the #254 assignment keeps for device "
                  "pads, signal trunks, risers and the VOUT/VIN rails over the pass device; so a vpp cannot be "
                  "laid over the MOS rows and is placed beside the core. Stacking a MiM above a li1-met2 vpp "
                  "beside the core is a possible combination that no record has drawn (unmeasured).",
        "source": "layout/cap-rail-demo/README.md (metal assignment); .mag levels of the evaluated cells",
    }
    o3["requalification"] = ("required: different device, plate-to-substrate parasitics (model c0_sub/c1_sub), "
                             "series resistance")
    if best is not None:
        lb = o3["beside_total_um2"]["tt"]["value"]
        o3["verdict"] = cs.fit_verdict(lb, keepout_known=False, overlay_possible=False,
                                       overlay_evidenced_below_limit=False)
        o3["verdict_reason"] = (f"beside the core the drawn-area lower bound is {lb:.0f} um^2 "
                                f"({'>=' if lb >= cs.LIMIT_UM2 else '<'} the limit); overlay conflicts with the "
                                "rail/device levels")
    else:
        o3["verdict"] = "not-established"
        o3["verdict_reason"] = "no evaluable vpp cell"
    options.append(o3)

    # --- 4. MOS varactor -------------------------------------------------------
    o4 = mos_option(caps, total, core_d, op, cv, soa, ugf)
    options.append(o4)

    verdicts = {o["id"]: o["verdict"] for o in options}
    incomplete = evidence_gaps(op, cv, options)
    outc = cs.outcome(verdicts, evidence_complete=not incomplete)
    return {
        "schema": "sky130-ldo/cap-study-matrix/1",
        "issue": 319,
        "pdk": {"variant": pdk.variant, "open_pdks_commit_pin": pin["open_pdks_commit"],
                "installed_commit": pdk.installed_commit, "matches_pin": pdk.matches_pin},
        "capacitors": caps,
        "total_f": total,
        "reference": ref,
        "loop_unity_gain": ugf if ugf else cs.unmeasured("no sim/ record gives the crossover frequency"),
        "options": options,
        "operating_points": op,
        "varactor_cv": cv,
        "varactor_soa": soa,
        "verdicts": verdicts,
        "evidence_gaps": incomplete,
        "outcome": outc,
    }


def cs_drawn_evidence(summary: dict, rid: str) -> dict:
    """The #254 record's own measured figures (whatever keys it carries)."""
    out = {"record": f"layout/cap-rail-demo/reports/{rid}/", "source": f"layout/cap-rail-demo/reports/{rid}/summary.json"}
    flat = {}

    def walk(prefix, v):
        if isinstance(v, dict):
            for k, x in v.items():
                walk(f"{prefix}.{k}" if prefix else k, x)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            flat[prefix] = v
    walk("", summary)
    picks = {
        "core_rectangle_um2": ("verdict.core_rectangle_um2",),
        "density_f_per_um2_drawn": ("totals.effective_density_f_um2",),
        "cap_blocks_um2": ("totals.cap_block_um2",),
        "mim_top_plate_um2": ("totals.mim_footprint_um2",),
        "overlay_usable_um2": ("totals.overlay_usable_um2",),
        "side_by_side_um2": ("verdict.side_by_side_um2",),
        "single_level_blocks_um2": ("single_mim_level_counterfactual.block_area_um2",),
    }
    out["gates_all_ok"] = bool((summary.get("gates") or {}).get("all_ok"))
    for k, cands in picks.items():
        for c in cands:
            if c in flat:
                out[k] = flat[c]
                break
        else:
            out[k] = cs.unmeasured(f"key not found in summary.json (looked for {', '.join(cands)})")
    return out


def mos_option(caps, total, core_d, op, cv, soa, ugf) -> dict:
    o = {"id": "mos_varactor", "label": "MOS varactor cap_var_lvt / cap_var_hvt (accumulation, nwell)",
         "devices": ["sky130_fd_pr__cap_var_lvt", "sky130_fd_pr__cap_var_hvt"], "soa": soa}
    # per-capacitor plate-voltage range over the measured op points
    vr = {}
    n_total = len(op["points"])
    for c in caps:
        vals = [p["caps"][c["name"]]["v_plate_v"] for p in op["points"]
                if not cs.is_unmeasured(p["caps"][c["name"]])]
        vr[c["name"]] = {"n_measured": len(vals), "n_points": n_total,
                         "min_v": min(vals) if vals else cs.UNMEASURED,
                         "max_v": max(vals) if vals else cs.UNMEASURED,
                         "complete": len(vals) == n_total}
    o["plate_voltage_range"] = vr
    plate_v = {c["name"]: [p["caps"][c["name"]]["v_plate_v"] for p in op["points"]
                           if not cs.is_unmeasured(p["caps"][c["name"]])] for c in caps}
    tt = next((r for r in cv["runs"] if r["process"] == "tt" and float(r["temperature_c"]) == 27.0), None)
    dens = {}
    at_bias = {}
    if tt is None:
        for fl in CV_FLAVORS:
            dens[fl] = cs.unmeasured("no C(V) run")
    else:
        f0 = f"{cv['freqs_hz'][0]:g}"
        for key, cur in sorted(tt["curves"].items()):
            area = cur["w_um"] * cur["l_um"]
            cvals = [x for x in cur["c_f"][f0] if x is not None]
            if not cvals:
                continue
            row = {"cmax_f": max(cvals), "cmin_f": min(cvals),
                   "cmax_density_f_per_um2": float(f"{max(cvals) / area:.6e}"),
                   "cmin_density_f_per_um2": float(f"{min(cvals) / area:.6e}"),
                   "gate_area_um2": area, "source": tt["source"]}
            if len(cv["freqs_hz"]) > 1:
                f1 = f"{cv['freqs_hz'][1]:g}"
                rel = [abs(b - a) / a for a, b in zip(cur["c_f"][f0], cur["c_f"][f1])
                       if a is not None and b is not None and a > 0]
                row["c_at_ugf_vs_1khz_max_rel_diff"] = float(f"{max(rel):.3e}") if rel else cs.UNMEASURED
                row["ugf_hz"] = cv["freqs_hz"][1]
            # C at each measured op-point plate voltage (tt/27 C curve only).
            # Either plate may be the gate (c0), so both orientations are
            # reported; v is c0 - c1, i.e. +v_plate when the first net is
            # on the gate and -v_plate otherwise.
            lim = soa.get(cur["flavor"]) if isinstance(soa.get(cur["flavor"]), dict) else {}
            per_cap = {}
            for c in caps:
                vs = plate_v[c["name"]]
                if not vs:
                    per_cap[c["name"]] = cs.unmeasured("no operating point measured")
                    continue
                orient = {}
                for oname, sign in ((f"gate_on_{c['nets'][0]}", 1.0), (f"gate_on_{c['nets'][1]}", -1.0)):
                    vv = [sign * v for v in vs]
                    in_soa = all(lim.get("vgs_min_v", -1e9) <= v <= lim.get("vgs_max_v", 1e9) for v in vv)
                    cc = [cs.interp(cur["bias_v"], cur["c_f"][f0], v) for v in vv]
                    if not in_soa or any(x is None for x in cc):
                        orient[oname] = {"within_soa": in_soa, "c_density_f_per_um2": cs.unmeasured(
                            "plate voltage outside the model SOA / the swept range at a measured point")}
                        continue
                    orient[oname] = {"within_soa": True,
                                     "c_density_min_f_per_um2": float(f"{min(cc) / area:.6e}"),
                                     "c_density_max_f_per_um2": float(f"{max(cc) / area:.6e}")}
                per_cap[c["name"]] = {"orientations": orient,
                                      "over_measured_points": f"{len(vs)}/{n_total}"}
            row["at_bias"] = per_cap
            dens[key] = row
        at_bias = {k: v.get("at_bias") for k, v in dens.items() if isinstance(v, dict) and "at_bias" in v}
    o["cv_tt_27c"] = dens
    big = [v for k, v in dens.items() if isinstance(v, dict) and "cmax_density_f_per_um2" in v
           and v["gate_area_um2"] >= 100]
    if big:
        b = max(big, key=lambda v: v["cmax_density_f_per_um2"])
        a_best = cs.area_for(total, b["cmax_density_f_per_um2"])
        a_worst = cs.area_for(total, b["cmin_density_f_per_um2"])
        o["area_162pf_um2"] = {
            "tt_at_cmax": cs.cell(round(a_best, 1), "um^2", "C / Cmax density over gate area (tt, 27 C, 1 kHz)",
                                  "gate area only: diffusion, nwell, contact and tap overhead unmeasured"),
            "tt_at_cmin": cs.cell(round(a_worst, 1), "um^2", "C / Cmin density over gate area (tt, 27 C, 1 kHz)"),
            "ll": cs.unmeasured("C(V) not run at the ll corner"),
            "hh": cs.unmeasured("C(V) not run at the hh corner"),
        }
        o["beside_total_um2"] = {"tt_at_cmax": cs.cell(round(core_d + a_best, 1), "um^2",
                                                       "core_without_caps + gate-area lower bound")}
        lb = core_d + a_best
    else:
        o["area_162pf_um2"] = {c: cs.unmeasured("no C(V) run") for c in ("tt", "ll", "hh")}
        lb = None
    o["cell_footprint_um2"] = cs.unmeasured("no fixed layout cell in the PDK and no klt generator for a varactor; "
                                            "only gate area is known")
    o["metal_levels"] = ["nwell", "diff (nsdm)", "poly", "licon", "li1", "mcon", "met1"]
    o["overlay"] = {"over_core": "conflicts",
                    "detail": "a varactor is a front-end device (nwell, diffusion, poly): it occupies device "
                              "area and cannot sit over the MOS rows; it frees met3-met5 but not the substrate.",
                    "source": "device structure (model pins c0 poly / c1 nwell / b substrate)"}
    o["requalification"] = ("required: voltage-dependent C at each node's bias, plate-to-substrate (nwell-psub) "
                            "junction, series resistance (model rg), SOA |V| <= the model's vgs_max on every "
                            "plate pair across PVT and transients")
    o["at_bias_summary"] = at_bias
    soa_excluded = sorted({cap for v in at_bias.values() if isinstance(v, dict) for cap, r in v.items()
                           if isinstance(r, dict) and "orientations" in r
                           and not any(x["within_soa"] for x in r["orientations"].values())})
    o["soa_excluded_at_measured_points"] = soa_excluded
    complete = all(v["complete"] for v in vr.values())
    if lb is None or not complete:
        o["verdict"] = "not-established"
        o["verdict_reason"] = ("C(V) at the measured bias of every capacitor needs the full operating-point "
                               "matrix" + ("" if complete else " (incomplete: see plate_voltage_range)")
                               + "; the cell footprint is unmeasured"
                               + (f"; {', '.join(soa_excluded)} exceed(s) the varactor SOA at a measured point "
                                  "in both orientations, so those capacitors would need another device"
                                  if soa_excluded else ""))
    else:
        o["verdict"] = cs.fit_verdict(lb, keepout_known=False, overlay_possible=False,
                                      overlay_evidenced_below_limit=False)
        o["verdict_reason"] = "gate-area lower bound only; footprint and keep-out unmeasured"
    return o


def evidence_gaps(op, cv, options) -> list[str]:
    gaps = []
    n_un = sum(1 for p in op["points"] if p["status"] == cs.UNMEASURED or
               any(cs.is_unmeasured(v) for v in p["caps"].values()))
    if n_un:
        gaps.append(f"operating-point matrix: {n_un}/{len(op['points'])} points unmeasured")
    have = {(r["process"], float(r["temperature_c"])) for r in cv["runs"]}
    want = {(p, t) for p in ("tt", "ss", "ff", "sf", "fs", "ll", "hh") for t in TEMPS_C}
    if not want <= have:
        gaps.append(f"varactor C(V): {len(want - have)}/{len(want)} corner x temperature runs missing")
    for o in options:
        if o["verdict"] == "not-established":
            gaps.append(f"option {o['id']}: fit not established ({o.get('verdict_reason', '')})")
    return gaps


def cmd_matrix(args) -> int:
    rec = Path(args.record).resolve()
    m = build_matrix(rec)
    text = json.dumps(m, indent=2, sort_keys=True) + "\n"
    (rec / "matrix.json").write_text(text)
    print(f"wrote {rec / 'matrix.json'}: outcome ({m['outcome']}); verdicts {m['verdicts']}")
    for g in m["evidence_gaps"]:
        print(f"  gap: {g}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prepare", "op", "matrix"):
        p = sub.add_parser(name)
        p.add_argument("--record", required=True)
    p = sub.add_parser("op-local")
    p.add_argument("--record", required=True)
    p.add_argument("--point", required=True, help="process,temp_c,supply_v,load_ma e.g. tt,27,3.3,0")
    p = sub.add_parser("cv")
    p.add_argument("--record", required=True)
    p.add_argument("--backend", choices=["local", "batch"], required=True)
    args = ap.parse_args(argv)
    return {"prepare": cmd_prepare, "op": cmd_op, "op-local": cmd_op_local, "cv": cmd_cv,
            "matrix": cmd_matrix}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
