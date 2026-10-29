#!/usr/bin/env python3
"""Bias-generator-only PVT grid for the DR-013 bias re-topology study (issue #467).

Compares the bias generator of record (`R_BIAS` = res_high_po W=0.42 L=1500) with
the DR-013 candidate (`R_BIAS` = res_xhigh_po W=0.42 L=211) across the ratified
PVT matrix (5 process x 3 temperature x 3 supply) plus the resistor-only skew
corners ll/hh. Every other bias device is copied verbatim from
`design/ldo_3v3in_1v8out.sch`. The downstream consumer is represented by one
`M_TAIL` copy (the error-amplifier tail, the largest BIASP mirror) sinking into
a fixed 1.0 V source.

The grid is expressed as `klt sim` requests (one per design x supply) and goes
to the batch fleet; there is NO local fallback. Output is a NEW append-only
record directory `sim/bias-retopo/<record-id>/` (request files, raw responses,
`summary.json`, `record.md`).

This is a bias-generator screening grid. It is NOT a PSRR / stability / Iq
record of the full LDO (those are `sim/psrr-dc`, `sim/loop-gain`, `sim/iq`).

Usage:
    python3 sim/bin/bias-retopo-grid.py [--record-id ID]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PDK_JSON = REPO / "sim" / "pdk.json"
SUPPLIES = [2.97, 3.30, 3.63]
PROCESS = ["tt", "ss", "ff", "sf", "fs", "ll", "hh"]
TEMPS = [-40.0, 27.0, 125.0]
DESIGNS = {
    "record": ("sky130_fd_pr__res_high_po", 1500),
    "dr013": ("sky130_fd_pr__res_xhigh_po", 211),
}
NFET = "sky130_fd_pr__nfet_g5v0d10v5"
PFET = "sky130_fd_pr__pfet_g5v0d10v5"
MEAS = [
    ("v_nb", "v(nb)", "V"),
    ("v_biasp", "v(biasp)", "V"),
    ("i_tail_ua", "1e6*i(vtail)", "uA"),
    ("i_bias_pair_ua", "1e6*(-i(vvin)-i(vtail))", "uA"),
]


def netlist(res: str, length: int, vsup: float) -> str:
    return f""".param vsup={vsup}
.option wnflag=1
VVIN VIN 0 'vsup'
.save i(vvin)
XR_BIAS VIN NB 0 {res} W=0.42 L={length} mult=1 m=1
XM_BIASN1 NB NB BIAS_ENN 0 {NFET} L=1 W=4 nf=1 mult=1 m=1
XM_ENN BIAS_ENN VIN 0 0 {NFET} L=0.5 W=10 nf=1 mult=1 m=1
XM_BIASN2 BIASP NB BIAS_ENN 0 {NFET} L=1 W=4 nf=1 mult=1 m=1
XM_BIASP1 BIASP BIASP VIN VIN {PFET} L=1 W=10 nf=2 mult=1 m=1
XM_TAIL EA_TAIL BIASP VIN VIN {PFET} L=2 W=40 nf=8 mult=1 m=1
VTAIL EA_TAIL 0 1.0
.save i(vtail)
.end
"""


def request(path: Path, pdk: dict) -> dict:
    return {
        "netlist": str(path),
        "engine": "ngspice",
        "models": {"pdk": pdk["variant"], "lib": pdk["ngspice_lib"]},
        "corners": {"process": PROCESS, "temperature_c": TEMPS},
        "analysis": {"kind": "op", "args": ""},
        "measurements": [{"name": f"meas_{n}", "expr": e, "unit": u} for n, e, u in MEAS],
        "options": {"timeout_s": 300, "keep_artifacts": True},
        "batch": {"capacity_wait_s": 3 * 3600},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record-id", default=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    args = ap.parse_args()
    out = REPO / "sim" / "bias-retopo" / args.record_id
    if out.exists():
        sys.exit(f"refusing to overwrite existing record {out}")
    pdk = json.loads(PDK_JSON.read_text())
    pdk_root = os.environ.get("PDK_ROOT") or str(Path.home() / ".volare")
    (out / "requests").mkdir(parents=True)
    rows = []
    for name, (res, length) in DESIGNS.items():
        for vsup in SUPPLIES:
            key = f"{name}-v{vsup:.2f}"
            net = out / "requests" / f"{key}.spice"
            net.write_text(netlist(res, length, vsup))
            req = out / "requests" / f"{key}.json"
            req.write_text(json.dumps(request(net.resolve(), pdk), indent=2) + "\n")
            od = out / "responses" / key
            od.mkdir(parents=True)
            proc = subprocess.run(
                ["klt", "sim", str(req), "-o", str(od), "--backend", "batch", "--format", "json"],
                capture_output=True, text=True, env={**os.environ, "PDK_ROOT": pdk_root},
            )
            (od / "klt.stdout").write_text(proc.stdout)
            (od / "klt.stderr").write_text(proc.stderr)
            try:
                resp = json.loads(proc.stdout)
            except json.JSONDecodeError:
                sys.exit(f"{key}: klt sim batch submit failed (no JSON); NOT falling back to local.\n{proc.stderr[:2000]}")
            remote = resp.get("environment", {}).get("remote", {})
            for c in resp["corners"]:
                m = {x["name"].replace("meas_", ""): x["value"] for x in c["measurements"]}
                rows.append({"design": name, "vsup": vsup, "process": c["process"],
                             "temp_c": c["temperature_c"], "status": c["status"],
                             "job_id": remote.get("job_id"), **m})
            print(f"{key}: {resp['status']} ({resp['corner_count']} corners) job {remote.get('job_id')}", flush=True)
    (out / "summary.json").write_text(json.dumps(rows, indent=1) + "\n")
    # A/B table
    idx = {(r["design"], r["vsup"], r["process"], r["temp_c"]): r for r in rows}
    lines = [f"# Bias-generator PVT grid: {args.record_id}", "",
             "Issue #467 / DR-013. `record` = res_high_po L=1500; `dr013` = res_xhigh_po L=211.",
             "Executed through `klt sim --backend batch` (no local fallback). Bias generator + one M_TAIL copy only.", "",
             "| process | T(C) | VIN | I_pair record (uA) | I_pair dr013 (uA) | shift % | I_tail record | I_tail dr013 | tail shift % |",
             "|---|---|---|---|---|---|---|---|---|"]
    worst = 0.0
    worst_t = 0.0
    bad = 0
    for (d, v, p, t), r in sorted(idx.items(), key=lambda kv: (kv[0][2], kv[0][3], kv[0][1])):
        if d != "record":
            continue
        c = idx.get(("dr013", v, p, t))
        if c is None or r["status"] != "ok" and r["status"] != "passed" and r["i_bias_pair_ua"] is None:
            bad += 1
            continue
        try:
            s = 100 * (c["i_bias_pair_ua"] / r["i_bias_pair_ua"] - 1)
            st = 100 * (c["i_tail_ua"] / r["i_tail_ua"] - 1)
        except (TypeError, ZeroDivisionError):
            bad += 1
            continue
        worst = max(worst, abs(s))
        worst_t = max(worst_t, abs(st))
        lines.append(f"| {p} | {t:g} | {v:.2f} | {r['i_bias_pair_ua']:.4f} | {c['i_bias_pair_ua']:.4f} | {s:+.2f} | "
                     f"{r['i_tail_ua']:.4f} | {c['i_tail_ua']:.4f} | {st:+.2f} |")
    lines += ["", f"Worst |I_pair shift| = {worst:.2f} %; worst |I_tail shift| = {worst_t:.2f} %; unusable points = {bad}."]
    (out / "record.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[-3:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
