#!/usr/bin/env python3
"""Bounded fleet screen of ONE physical light-load adaptive R_CZ realization (issue #370, stage 2).

Candidate (diagnostic only; the production schematic is NOT edited): R_CZ is split into the stock
52 um segment plus an extra 780 um segment (total 832 um = the #365 "x16" value) and a pfet switch
(XM_RZSW) that shorts the extra segment when the load is above a threshold. The control is the
EXISTING current-limit sense FET's mirror node (CL_SNS): a second nfet mirror (XM_LLN, same L=1 /
W=20 as M_CLN1, ratio 1:1) pulls the switch gate (GSW) down against a small pfet reference current
(XM_LLP, gate BIASP) that pulls it up. No extra sense FET is added, so no extra sense current flows
at heavy load; the cost is the reference pfet current (a few nA) and an enable pullup (XM_LLEN).

The "at most two parameter choices" are the reference pfet length: A = L 11 um (threshold ~20 uA at
tt/27 C), B = L 2.2 um (threshold ~150 uA at tt/27 C). Everything else is fixed.

Everything multi-condition goes to the batch fleet through `klt sim` (NO local fallback; a refused
submit is reported and the run exits non-zero). Four request families, all schematic-netlisted then
text-edited (the same variant-netlist approach as sim/bin/rcz-fleet-confirm.py):

  ac    10..18 loop-gain legs per design (PM/GM/fc via klt `transfer` metrics, as stage 1), tt/27 C
        plus a ss/ff x -40/125 C subset
  op    per design, ILOAD steps 0..50 mA x 9 PVT corners: VOUT, VIN current (Iq = I(VIN) - I_load),
        switch gate, switch gds, and instrumentation-resistor conductances (effective R_CZ)
  tran  0<->1 mA (crosses the adaptation region) and 1<->50 mA load steps, COUT 0.33/4.7 uF, ESR 10 mOhm

    python3 sim/bin/rcz-adaptive-370.py --outdir sim/loop-gain/diagnostics/<id> [--only ac,op,tran] [--dry-run]

Grading never converts a missing crossing, a non-regulating point, a solver failure or an unrun case
into a PASS.

The netlist / request / submit core shared with the other batch-fleet campaign drivers lives in
sim/bin/_fleet_campaign.py (issue #574); only this campaign's families and grading are here.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _fleet_campaign as fc  # noqa: E402


def _load(name: str, fname: str):
    """Load a hyphen-named sibling script as a module (it cannot be `import`ed)."""
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Stage 1's own campaign data (`LEGS`, `edit_rcz`), not generic helpers.
rc = _load("rcz_fleet_confirm", "rcz-fleet-confirm.py")

VSUP = 3.30
PM_MIN, GM_MIN = 45.0, 10.0
VNOM, BAND = 1.8, 0.018  # +-1% recovery band around the 1.8 V nominal
CAND_REF_L = {
    "candA": 11,
    "candB": 2.2,
}  # the two parameter choices (reference pfet length, um)
DESIGNS = ["baseline", "rcz16", "candA", "candB"]
ADAPTIVE = ("candA", "candB")
R_CZ0_L, R_CX_L = 52, 780

# (cap label, cap, esr label, esr, load label, rload ohm string)
CAPS = [("0.33u", "0.33u"), ("4.7u", "4.7u")]
AC_LEGS = rc.LEGS + [
    (cl, cv, 0.010, ll, rl, f"{cl}/10m/{ll}")
    for ll, rl in (("10uA", "180k"), ("30uA", "60k"), ("100uA", "18k"), ("300uA", "6k"))
    for cl, cv in CAPS
]
# stage 1 already ran baseline/rcz16 at the first 10 legs (same driver family); only the new loads re-run
STAGE1_LEGS = {leg[5] for leg in rc.LEGS}
PVT_AC_LEGS = [
    leg
    for leg in AC_LEGS
    if leg[2] == 0.010 and leg[3] in ("0mA", "100uA", "1mA", "50mA")
]
PVT_CORNERS = [("ss", -40.0), ("ss", 125.0), ("ff", -40.0), ("ff", 125.0)]
OP_LOADS = {
    "0": 0.0,
    "3uA": 3e-6,
    "10uA": 1e-5,
    "30uA": 3e-5,
    "100uA": 1e-4,
    "300uA": 3e-4,
    "1mA": 1e-3,
    "50mA": 5e-2,
}
OP_CORNERS = [(p, t) for p in ("tt", "ss", "ff") for t in (-40.0, 27.0, 125.0)]
TRAN_CASES = {  # name -> (ILOAD pulse lo, hi, rising?)
    "r0to1mA": (0.0, 1e-3, True),
    "f1mAto0": (0.0, 1e-3, False),
    "r1to50mA": (1e-3, 5e-2, True),
    "f50to1mA": (1e-3, 5e-2, False),
}
T_STEP = 100e-6


# ---------------------------------------------------------------- netlist edits
def edit_candidate(body: str, ref_l: float) -> str:
    """Split R_CZ (52 um) + extra 780 um segment shorted by a load-sensing pfet switch."""
    out, n = [], 0
    for ln in body.splitlines():
        if ln.split(" ")[0].upper() == "XR_CZ":
            assert " L=52 " in ln and "EA_CZ EA_OUT" in ln, ln
            out.append(ln.replace("EA_CZ EA_OUT", "EA_CZ EA_MID", 1))
            out += [
                f"XR_CX EA_MID EA_OUT 0 sky130_fd_pr__res_xhigh_po W=0.42 L={R_CX_L} mult=1 m=1",
                "XM_RZSW EA_MID GSW EA_OUT VIN sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=2 nf=1 mult=1 m=1",
                "XM_LLN GSW CL_SNS AMP_ENN 0 sky130_fd_pr__nfet_g5v0d10v5 L=1 W=20 nf=1 mult=1 m=1",
                f"XM_LLP GSW BIASP VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L={ref_l:g} W=0.5 nf=1 mult=1 m=1",
                "XM_LLEN GSW EN VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=2 nf=1 mult=1 m=1",
            ]
            n += 1
        else:
            out.append(ln)
    if n != 1:
        sys.exit(f"expected exactly one XR_CZ card, found {n}")
    return "\n".join(out) + "\n"


def variant(body: str, design: str) -> str:
    if design == "baseline":
        return body
    if design == "rcz16":
        return rc.edit_rcz(body, 16)
    return edit_candidate(body, CAND_REF_L[design])


def probe_lines(design: str) -> list[str]:
    """Instrumentation-only: 1 V across a copy of each R_CZ segment gives its conductance."""
    segs = {"rcz0": R_CZ0_L if design != "rcz16" else 832}
    if design in ADAPTIVE:
        segs["rcx"] = R_CX_L
    out = []
    for k, ln_um in segs.items():
        out.append(f"VPR_{k} PR_{k} 0 DC 1")
        out.append(
            f"XPR_{k} PR_{k} 0 0 sky130_fd_pr__res_xhigh_po W=0.42 L={ln_um} mult=1 m=1"
        )
    return out


def load_body(root: Path, pdk_root: str) -> str:
    return fc.netlist("tb_loop_gain", root, pdk_root)


def with_load(body: str, new: str) -> str:
    return fc.sub_line(body, "RLOAD", new)


# ---------------------------------------------------------------- request builders
def req_ac(body, design, leg, corners, out: Path, pdk, prefix="ac"):
    _cl, cv, esr, _ll, rl, label = leg
    b = fc.insert_loop_gain_probe(variant(body, design))
    b = fc.sub_line(b, "COUT", f"COUT VOUT VESR {cv} m=1")
    b = fc.sub_line(b, "HESR", f"HESR VESRS 0 VESRSENSE {esr:g}")
    b = with_load(b, f"RLOAD VOUT 0 {rl} m=1")
    return _write(
        out,
        f"{prefix}__{design}__{label.replace('/', '_')}",
        b,
        pdk,
        corners,
        {
            "analysis": {"kind": "ac", "args": "dec 30 1e-2 1e9"},
            "measurements": fc.LOOP_TRANSFER_MEAS,
        },
    )


def op_exprs(design: str) -> list[tuple[str, str, str]]:
    m = [
        ("vout", "v(vout)", "V"),
        ("ivin", "-i(vvin)", "A"),
        ("vgsw", "v(xldo.gsw)" if design in ADAPTIVE else "v(xldo.ea_out)", "V"),
        ("vea_out", "v(xldo.ea_out)", "V"),
        ("g_rcz0", "-i(vpr_rcz0)", "S"),
    ]
    if design in ADAPTIVE:
        m += [
            ("g_rcx", "-i(vpr_rcx)", "S"),
            ("gds_sw", "@m.xldo.xm_rzsw.msky130_fd_pr__pfet_g5v0d10v5[gds]", "S"),
        ]
    return m


def req_op(body, design, out: Path, pdk):
    b = variant(body, design) + "\n".join(probe_lines(design)) + "\n"
    b = fc.sub_line(b, "COUT", "COUT VOUT VESR 4.7u m=1")
    b = fc.sub_line(b, "HESR", "HESR VESRS 0 VESRSENSE 0.010")
    b = with_load(b, "ILOAD VOUT 0 DC 0")
    steps = [
        {
            "name": f"op_{k}",
            "analysis": {"kind": "op", "args": ""},
            "alter": {"ILOAD": v},
            "measurements": [
                {"name": n, "expr": e, "unit": u} for n, e, u in op_exprs(design)
            ],
        }
        for k, v in OP_LOADS.items()
    ]
    return _write(out, f"op__{design}", b, pdk, OP_CORNERS, {"analysis_steps": steps})


def tran_cards() -> list[tuple[str, str]]:
    t0, t1 = T_STEP, 1e-3
    return [
        ("pre", f".meas tran pre AVG v(vout) from={t0 - 40e-6:g} to={t0 - 1e-6:g}"),
        ("vmin", f".meas tran vmin MIN v(vout) from={t0:g} to={t1:g}"),
        ("vmax", f".meas tran vmax MAX v(vout) from={t0:g} to={t1:g}"),
        ("vfin", f".meas tran vfin AVG v(vout) from={t1 - 50e-6:g} to={t1:g}"),
        ("tlo", f".meas tran tlo WHEN v(vout)={VNOM - BAND:g} CROSS=LAST"),
        ("thi", f".meas tran thi WHEN v(vout)={VNOM + BAND:g} CROSS=LAST"),
    ]


def req_tran(body, design, case, out: Path, pdk):
    lo, hi, rising = TRAN_CASES[case]
    a, b2 = (lo, hi) if rising else (hi, lo)
    b = variant(body, design)
    b = fc.sub_line(b, "HESR", "HESR VESRS 0 VESRSENSE 0.010")
    b = with_load(b, f"ILOAD VOUT 0 PULSE({a:g} {b2:g} {T_STEP:g} 1u 1u 1 2)")
    steps = [
        {
            "name": "c" + cl.replace(".", "p"),
            "analysis": {"kind": "tran", "args": "0.5u 1m"},
            "alter": {"COUT": float(cv.replace("u", "e-6"))},
            "measurements": [{"name": n, "spice": c} for n, c in tran_cards()],
        }
        for cl, cv in CAPS
    ]
    return _write(
        out,
        f"tran__{design}__{case}",
        b,
        pdk,
        [("tt", 27.0), ("ss", -40.0), ("ff", 125.0)] and OP_CORNERS,
        {"analysis_steps": steps},
        cout_literal=True,
    )


def _write(
    out: Path, key: str, body: str, pdk, corners, shape: dict, cout_literal=False
):
    net = out / "requests" / f"{key}.spice"
    net.write_text(fc.deck(body, VSUP))
    req = fc.base_request(net.resolve(), pdk, corners, shape=shape)
    rp = out / "requests" / f"{key}.json"
    rp.write_text(json.dumps(req, indent=2) + "\n")
    return key, rp


# ---------------------------------------------------------------- grading
def r_eff(design: str, v: dict) -> float | None:
    """Effective R_CZ (ohm) at a DC operating point from the instrumentation conductances."""
    try:
        r0 = 1.0 / v["g_rcz0"]
        if design in ADAPTIVE:
            return r0 + 1.0 / (1.0 / (1.0 / v["g_rcx"]) + v["gds_sw"])
        return r0
    except (KeyError, TypeError, ZeroDivisionError):
        return None


def iq_ua(ivin: float | None, iload: float) -> float | None:
    return None if ivin is None else (ivin - iload) * 1e6


def regulating(vout: float | None) -> bool:
    return vout is not None and abs(vout - VNOM) <= 0.05


def grade_tran(v: dict, t_step: float = T_STEP) -> dict:
    """Peak deviation (from pre-step), recovery time to +-1%, and a pass flag; missing data never passes."""
    need = ("pre", "vmin", "vmax", "vfin")
    if any(v.get(k) is None for k in need):
        return {"valid": False, "recovered": False, "peak_v": None, "rec_us": None}
    pre, lo, hi, fin = v["pre"], v["vmin"], v["vmax"], v["vfin"]
    peak = max(pre - lo, hi - pre)
    in_band = lo >= VNOM - BAND and hi <= VNOM + BAND
    settled = abs(fin - VNOM) <= BAND
    if in_band:
        return {"valid": True, "recovered": True, "peak_v": peak, "rec_us": 0.0}
    if not settled:
        return {"valid": True, "recovered": False, "peak_v": peak, "rec_us": None}
    ts = [v[k] for k in ("tlo", "thi") if v.get(k) is not None]
    rec = (max(ts) - t_step) * 1e6 if ts else None
    return {"valid": True, "recovered": rec is not None, "peak_v": peak, "rec_us": rec}


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--only", default="ac,op,tran")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument(
        "--resume",
        action="store_true",
        help="continue an interrupted run in --outdir: keep completed requests' rows, resubmit the rest",
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="write requests only; submit nothing"
    )
    args = ap.parse_args()
    fam = set(args.only.split(","))
    out = Path(args.outdir).resolve()
    pdk, pdk_root, env = fc.preamble(args.workers, out, allow_existing=args.resume)
    prior = (
        json.loads((out / "summary.json").read_text())
        if args.resume and out.exists()
        else {"rows": [], "errors": []}
    )
    (out / "requests").mkdir(parents=True, exist_ok=args.resume)
    body = load_body(out / "requests", pdk_root)

    jobs = []  # (key, meta, request path)
    if "ac" in fam:
        for d in DESIGNS:
            for leg in AC_LEGS:
                if d in ("baseline", "rcz16") and leg[5] in STAGE1_LEGS:
                    continue  # stage 1 record already holds these
                k, rp = req_ac(body, d, leg, [("tt", 27.0)], out, pdk)
                jobs.append(
                    (k, {"fam": "ac", "design": d, "leg": leg[5], "cond": "tt/27"}, rp)
                )
        for d in ("baseline", "candA", "candB"):
            for leg in PVT_AC_LEGS:
                k2, rp = req_ac(body, d, leg, PVT_CORNERS, out, pdk, prefix="acpvt")
                jobs.append((k2, {"fam": "acpvt", "design": d, "leg": leg[5]}, rp))
    if "op" in fam:
        for d in DESIGNS:
            k, rp = req_op(body, d, out, pdk)
            jobs.append((k, {"fam": "op", "design": d}, rp))
    if "tran" in fam:
        for d in DESIGNS:
            for case in TRAN_CASES:
                if d == "rcz16" and case.startswith(("r0", "f1mA")):
                    continue
                k, rp = req_tran(body, d, case, out, pdk)
                jobs.append((k, {"fam": "tran", "design": d, "case": case}, rp))
    done_keys = {r["key"] for r in prior["rows"]}
    jobs = [j for j in jobs if j[0] not in done_keys]
    for (
        k,
        _m,
        _rp,
    ) in jobs:  # an interrupted submit leaves a partial response dir; resubmit cleanly
        part = out / "responses" / k
        if part.exists():
            shutil.rmtree(part)
    print(f"{len(jobs)} requests written under {out / 'requests'}", flush=True)
    if args.dry_run:
        return 0

    rows, errors = list(prior["rows"]), []
    for k, m, resp, job in fc.submit_all(jobs, out, env, args.workers, errors):
        for c in resp["corners"]:
            rows.append(
                {
                    **fc.corner_base(k, m, c, job),
                    "measurements": {
                        x["name"]: x.get("value") for x in c.get("measurements", [])
                    },
                }
            )
        (out / "summary.json").write_text(  # partial progress survives an interrupt
            json.dumps({"rows": rows, "errors": errors}, indent=1) + "\n"
        )
    (out / "summary.json").write_text(
        json.dumps({"rows": rows, "errors": errors}, indent=1) + "\n"
    )
    print(f"record: {out}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
