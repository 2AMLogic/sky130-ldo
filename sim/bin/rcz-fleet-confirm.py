#!/usr/bin/env python3
"""Fleet confirmation of the #365 baseline vs R_CZ x16 loop-gain pairs (issue #370).

#365's lever-B numbers were a PROVISIONAL local multi-leg run (tt / 27 C / 3.30 V). This
re-expresses the same 10 legs, for the baseline and the R_CZ L 52 -> 832 um (x16) netlist
edit, as plain `klt sim` AC requests and sends each to the batch fleet; there is NO local
fallback (a refused submit is reported and exits non-zero). Reuses the #467 translation
(sim/bin/bias-retopo-pvt.py): LG = v(fb)/(1-v(fb)) via ONE linear VCVS, PM/GM/fc/DC gain
as klt `transfer` metrics, per-leg COUT / HESR / RLOAD line rewrites.

Writes a NEW append-only dir (requests/, responses/, summary.json, comparison.md); the
design schematic and every earlier record are untouched. Grading never turns a missing
crossing or a failed/errored corner into a PASS.

    python3 sim/bin/rcz-fleet-confirm.py --outdir sim/loop-gain/diagnostics/<id> [--workers 2]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location(
    "bias_retopo_pvt", HERE / "bias-retopo-pvt.py"
)
brp = importlib.util.module_from_spec(_spec)
sys.modules["bias_retopo_pvt"] = brp
_spec.loader.exec_module(brp)

CORNER = ("tt", 27.0)
VSUP = 3.30
# (cout label, cout, esr label, esr ohm, load label, rload, #365 leg label)
LEGS = [
    ("0.33u", "0.33u", 0.010, "0mA", "1e12", "0.33u/10m/0mA"),
    ("4.7u", "4.7u", 0.010, "0mA", "1e12", "4.7u/10m/0mA"),
    ("0.33u", "0.33u", 0.0, "0mA", "1e12", "0.33u/0/0mA"),
    ("4.7u", "4.7u", 0.0, "0mA", "1e12", "4.7u/0/0mA"),
    ("0.33u", "0.33u", 0.5, "0mA", "1e12", "0.33u/500m/0mA"),
    ("4.7u", "4.7u", 0.5, "0mA", "1e12", "4.7u/500m/0mA"),
    ("0.33u", "0.33u", 0.010, "1mA", "1800", "0.33u/10m/1mA"),
    ("4.7u", "4.7u", 0.010, "1mA", "1800", "4.7u/10m/1mA"),
    ("0.33u", "0.33u", 0.010, "50mA", "36", "0.33u/10m/50mA"),
    ("4.7u", "4.7u", 0.010, "50mA", "36", "4.7u/10m/50mA"),
]
DESIGNS = {"baseline": 1, "rcz16": 16}
PRIOR = {"baseline": "base_tt", "rcz16": "rcz16_tt"}
PRIOR_DIR = "20261011-190000-860f93f-lightload-phase-dip"
PM_MIN, GM_MIN = 45.0, 10.0
PM_TOL_DEG, GM_TOL_DB = (
    2.0,
    2.0,
)  # agreement bands vs #365's local numbers (reported, not a spec bound)


def edit_rcz(body: str, scale: int) -> str:
    out, n = [], 0
    for ln in body.splitlines():
        if ln.split(" ")[0].upper() == "XR_CZ":
            assert " L=52 " in ln, ln
            ln, n = ln.replace(" L=52 ", f" L={52 * scale} ", 1), n + 1
        out.append(ln)
    if n != 1:
        sys.exit(f"expected exactly one XR_CZ card, found {n}")
    return "\n".join(out) + "\n"


def grade(row: dict) -> dict:
    """PM/GM verdict; anything missing, non-passing or non-regulating is not a pass."""
    ok = (
        row["status"] in ("pass", "fail")
        and row.get("pm") is not None
        and row.get("gm") is not None
    )
    pm, gm = row.get("pm"), row.get("gm")
    return {"valid": ok, "pm_pass": ok and pm >= PM_MIN, "gm_pass": ok and gm >= GM_MIN}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    if args.workers > 2:
        sys.exit("host rule: no more than 2 workers")
    out = Path(args.outdir).resolve()
    if out.exists():
        sys.exit(f"refusing to overwrite existing record {out}")
    pdk = json.loads((brp.SIM / "pdk.json").read_text())
    pdk_root = os.environ.get("PDK_ROOT") or str(Path.home() / ".volare")
    env = {**os.environ, "PDK_ROOT": pdk_root}
    (out / "requests").mkdir(parents=True)

    body = brp.netlist("tb_loop_gain", "record", out / "requests", pdk_root)
    (out / "requests" / "tb_loop_gain.raw.spice").unlink()
    lines = body.splitlines()
    i = max(k for k, ln in enumerate(lines) if ln.strip().lower().startswith(".ends"))
    lines.insert(
        i, "ELG_DEN LG_DEN 0 VREF FB 1"
    )  # instrumentation only: v(lg_den) = 1 - v(fb)
    body = "\n".join(lines) + "\n"
    meas = [
        {
            "name": n,
            "unit": u,
            "transfer": {"num": "v(xldo.fb)", "den": "v(xldo.lg_den)", "metric": m},
        }
        for n, m, u in (
            ("pm", "phase_margin_deg", "deg"),
            ("gm", "gain_margin_db", "dB"),
            ("fc", "unity_crossing_hz", "Hz"),
            ("dc", "low_frequency_magnitude", ""),
        )
    ]
    jobs = []
    for dn, scale in DESIGNS.items():
        for cl, cv, esr, ll, rl, label in LEGS:
            key = f"{dn}__{label.replace('/', '_')}"
            b = edit_rcz(body, scale) if scale != 1 else body
            b = brp.sub_line(b, "COUT", f"COUT VOUT VESR {cv} m=1")
            b = brp.sub_line(b, "HESR", f"HESR VESRS 0 VESRSENSE {esr:g}")
            b = brp.sub_line(b, "RLOAD", f"RLOAD VOUT 0 {rl} m=1")
            net = out / "requests" / f"{key}.spice"
            net.write_text(brp.deck(b, VSUP))
            rp = out / "requests" / f"{key}.json"
            rp.write_text(
                json.dumps(
                    brp.base_request(
                        net.resolve(),
                        pdk,
                        [CORNER],
                        {"kind": "ac", "args": "dec 30 1e-2 1e9"},
                        meas,
                    ),
                    indent=2,
                )
                + "\n"
            )
            jobs.append((key, {"design": dn, "leg": label}, rp))

    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [(k, m, ex.submit(brp.submit, k, rp, out, env)) for k, m, rp in jobs]
        for k, m, f in futs:
            r = f.result()
            if "error" in r:
                errors.append({"key": k, "error": r["error"]})
                print(
                    f"{k}: SUBMIT FAILED (no local fallback): {r['error'][:300]}",
                    flush=True,
                )
                continue
            resp = r["resp"]
            job = resp.get("environment", {}).get("remote", {}).get("job_id")
            for c in resp["corners"]:
                vals = {x["name"]: x["value"] for x in c["measurements"]}
                rows.append(
                    {
                        **m,
                        "key": k,
                        "process": c["process"],
                        "temp_c": c["temperature_c"],
                        "status": c["status"],
                        "job_id": job,
                        **vals,
                    }
                )
            print(
                f"{k}: {resp['status']} ({resp['corner_count']} corners) job {job}",
                flush=True,
            )
    for row in rows:
        row["grade"] = grade(row)
    (out / "summary.json").write_text(
        json.dumps({"rows": rows, "errors": errors}, indent=1) + "\n"
    )
    (out / "comparison.md").write_text(render(rows, errors))
    print(f"record: {out}")
    return 1 if errors else 0


def prior_points() -> dict:
    base = brp.SIM / "loop-gain" / "diagnostics" / PRIOR_DIR / "runs"
    res = {}
    for dn, run in PRIOR.items():
        d = json.loads((base / run / "result.json").read_text())
        for p in d["points"]:
            r = p.get("response") or {}
            res[(dn, p["label"])] = (
                r.get("pm_deg"),
                r.get("worst_gm_db"),
                r.get("crossover_hz"),
                p["classification"]["valid"],
            )
    return res


def fmt(x, f="{:.1f}"):
    return "n/a" if x is None else f.format(x)


def render(rows, errors) -> str:
    prior = prior_points()
    idx = {(r["design"], r["leg"]): r for r in rows}
    L = [
        "# Fleet confirmation of the #365 baseline / R_CZ x16 loop-gain pairs (issue #370)",
        "",
        (
            "tt / 27 C / 3.30 V only (the corner #365 ran); one `klt sim --backend batch` request per design x leg, "
            "no local fallback. Fleet = klt batch runner; PM/GM/fc via klt `transfer` metrics of v(fb)/v(lg_den) "
            "(LG = v(fb)/(1-v(fb))). #365 = its provisional local run (committed `result.json`). Agreement bands "
            f"are +-{PM_TOL_DEG:g} deg PM and +-{GM_TOL_DB:g} dB GM (a reporting convenience, not a spec bound)."
        ),
        "",
        "| design | leg | fleet PM | #365 PM | fleet GM | #365 GM | fleet fc (Hz) | #365 fc | status | PM>=45 | GM>=10 | PM/GM agree |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    agree_all = True
    for dn in DESIGNS:
        for *_, label in LEGS:
            r = idx.get((dn, label))
            pp = prior.get((dn, label), (None, None, None, False))
            if r is None:
                L.append(
                    f"| {dn} | {label} | UNRUN | {fmt(pp[0])} | UNRUN | {fmt(pp[1])} | UNRUN | {fmt(pp[2], '{:.0f}')} | unrun | - | - | no |"
                )
                agree_all = False
                continue
            g = r["grade"]
            ag = (
                g["valid"]
                and pp[0] is not None
                and pp[1] is not None
                and abs(r["pm"] - pp[0]) <= PM_TOL_DEG
                and abs(r["gm"] - pp[1]) <= GM_TOL_DB
            )
            agree_all &= bool(ag)
            L.append(
                f"| {dn} | {label} | {fmt(r.get('pm'))} | {fmt(pp[0])} | {fmt(r.get('gm'))} | {fmt(pp[1])} | "
                f"{fmt(r.get('fc'), '{:.0f}')} | {fmt(pp[2], '{:.0f}')} | {r['status']}{'' if g['valid'] else ' (invalid)'} | "
                f"{'PASS' if g['pm_pass'] else 'FAIL'} | {'PASS' if g['gm_pass'] else 'FAIL'} | {'yes' if ag else 'NO'} |"
            )
    L += [
        "",
        f"Submit errors: {len(errors)}"
        + ("".join(f"\n- {e['key']}: {e['error'][:200]}" for e in errors)),
        "",
        f"All 20 pairs present and agreeing with #365 within the bands: **{'yes' if agree_all and not errors else 'no'}**.",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
