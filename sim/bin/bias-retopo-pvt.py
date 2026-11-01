#!/usr/bin/env python3
"""Full-loop PSRR + stability PVT grid for the DR-013 `R_BIAS` candidate (issue #467).

`corner-run.py` refuses `--backend batch` for `psrr-dc` and `loop-gain` (their
decks are ngspice control scripts with `let`/`cph`/`meas ... when`, which have no
pinned translation). This script does NOT change that allowlist. It expresses the
same two benches as plain `klt sim` requests and lets `--backend batch` send them
to the fleet; there is NO local fallback (host rule: a refused submit is reported,
never re-run as a local grid).

Translation (every step is stated in the record it writes):
  * PSRR  : the `sim/psrr-dc` testbench netlist; `RLOAD` 1.8k (1 mA) / 36 (50 mA);
            `ac lin 3 1e3 1e5`; PSRR = -vdb(vout) read with `.meas ac ... find
            vdb(vout) at=` (exactly the local `-vdb(vout)[0]` / `[2]` points).
  * loop  : the `sim/loop-gain` testbench netlist; per leg `COUT`, `HESR` gain and
            `RLOAD` are rewritten (the local `alter` cards); `ac dec 30 1e-2 1e9`;
            loop gain LG = v(fb)/(1-v(fb)) is formed by ONE linear VCVS
            `ELG_DEN LG_DEN 0 VREF FB 1` added inside the LDO subckt (v(VREF) is
            the AC-1 injection, so v(LG_DEN) = 1 - v(fb)), and PM / GM / fc / DC gain
            are klt `transfer` metrics of v(fb)/v(lg_den). The VCVS draws no current.
  * The candidate is `sim/bias-retopo/20261029-fullloop-467/candidate-R_BIAS.patch`
    applied to the schematic for netlisting only (and reverted afterwards).

Grading is local, from raw responses, against the unchanged spec bounds
(PSRR > 50 dB @1 kHz, > 20 dB @100 kHz, strict; PM >= 45 deg, GM >= 10 dB).
It writes a NEW append-only record dir `sim/bias-retopo/<record-id>/`.

Usage:
    python3 sim/bin/bias-retopo-pvt.py psrr|loop [--record-id ID] [--design dr013|record]
                                       [--corners tt:27:3.30,...] [--workers 2]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SIM = REPO / "sim"
sys.path.insert(0, str(SIM / "bin"))
from xschem_exprs import eval_xschem_exprs

PATCH = SIM / "bias-retopo" / "20261029-fullloop-467" / "candidate-R_BIAS.patch"
SCH = "design/ldo_3v3in_1v8out.sch"
SUPPLIES = [2.97, 3.30, 3.63]
PROCESS = ["tt", "ss", "ff", "sf", "fs"]
TEMPS = [-40.0, 27.0, 125.0]
PSRR_LOADS = {"1ma": "1.8k", "50ma": "36"}
PSRR_MEAS = [("p1k", 1e3, 50.0), ("p100k", 1e5, 20.0)]
LOOP_COUT = {"c033": "0.33u", "c47": "4.7u"}
LOOP_ESR = {"esr10m": 0.01, "esr500m": 0.5, "esr0": 0.0}
LOOP_LOAD = {"50ma": "36", "1ma": "1.8k", "0ma": "1e12"}
PM_MIN, GM_MIN = 45.0, 10.0


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def netlist(tb: str, design: str, outdir: Path, pdk_root: str) -> str:
    """Netlist the testbench (candidate patch applied only while netlisting)."""
    patched = design == "dr013"
    if patched:
        p = run(["git", "-C", str(REPO), "apply", str(PATCH)])
        if p.returncode:
            sys.exit(f"cannot apply candidate patch: {p.stderr}")
    try:
        raw = outdir / f"{tb}.raw.spice"
        p = run(
            [
                "klt",
                "netlist",
                "--allow-unevaluated-expr",
                "--rcfile",
                str(SIM / "xschemrc"),
                "--pdk",
                "sky130A",
                "--pdk-root",
                pdk_root,
                "-o",
                str(raw),
                str(
                    SIM
                    / tb.replace("tb_", "").replace("_", "-")
                    / "testbench"
                    / f"{tb}.sch"
                ),
            ]
        )
        if p.returncode:
            sys.exit(f"klt netlist failed: {p.stdout} {p.stderr}")
    finally:
        if patched:
            run(["git", "-C", str(REPO), "apply", "-R", str(PATCH)])
    text = raw.read_text().replace(str(REPO) + os.sep, "")
    text, _ = eval_xschem_exprs(text)
    if "expr(" in text:
        sys.exit("unevaluated expr() left in netlist")
    return (
        "\n".join(ln for ln in text.splitlines() if ln.strip().lower() != ".end") + "\n"
    )


def sub_line(body: str, prefix: str, new: str) -> str:
    out, n = [], 0
    for ln in body.splitlines():
        if ln.split(" ")[0].upper() == prefix:
            ln, n = new, n + 1
        out.append(ln)
    if n != 1:
        sys.exit(f"expected exactly one {prefix} line, found {n}")
    return "\n".join(out) + "\n"


def deck(body: str, vsup: float) -> str:
    return f"* DR-013 candidate PVT bench (issue #467)\n.param vsup={vsup}\n.option wnflag=1\n{body}.end\n"


def base_request(
    net: Path, pdk: dict, corners: list[tuple[str, float]], analysis: dict, meas: list
) -> dict:
    procs = sorted({p for p, _ in corners}, key=PROCESS.index)
    temps = sorted({t for _, t in corners})
    return {
        "netlist": str(net),
        "engine": "ngspice",
        "models": {"pdk": pdk["variant"], "lib": pdk["ngspice_lib"]},
        "corners": {"process": procs, "temperature_c": temps},
        "analysis": analysis,
        "measurements": meas,
        "options": {"timeout_s": 300, "keep_artifacts": True},
        "batch": {"capacity_wait_s": 3 * 3600},
    }


def submit(key: str, req_path: Path, out: Path, env: dict) -> dict:
    od = out / "responses" / key
    od.mkdir(parents=True)
    p = run(
        [
            "klt",
            "sim",
            str(req_path),
            "-o",
            str(od),
            "--backend",
            "batch",
            "--format",
            "json",
        ],
        env=env,
    )
    (od / "klt.stdout").write_text(p.stdout)
    (od / "klt.stderr").write_text(p.stderr)
    try:
        resp = json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"key": key, "error": p.stderr[-1500:] or "no JSON from klt sim"}
    return {"key": key, "resp": resp}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["psrr", "loop"])
    ap.add_argument(
        "--record-id",
        default=datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-pvt",
    )
    ap.add_argument("--design", choices=["dr013", "record"], default="dr013")
    ap.add_argument(
        "--corners", help="process:temp:vsup list; default = full 45-point matrix"
    )
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    if args.workers > 2:
        sys.exit("host rule: no more than 2 workers")
    out = REPO / "sim" / "bias-retopo" / args.record_id
    if out.exists():
        sys.exit(f"refusing to overwrite existing record {out}")
    pdk = json.loads((SIM / "pdk.json").read_text())
    pdk_root = os.environ.get("PDK_ROOT") or str(Path.home() / ".volare")
    env = {**os.environ, "PDK_ROOT": pdk_root}
    (out / "requests").mkdir(parents=True)

    if args.corners:
        pts = [
            (c.split(":")[0], float(c.split(":")[1]), float(c.split(":")[2]))
            for c in args.corners.split(",")
        ]
    else:
        pts = [(p, t, v) for v in SUPPLIES for p in PROCESS for t in TEMPS]
    by_v: dict[float, list[tuple[str, float]]] = {}
    for p, t, v in pts:
        by_v.setdefault(v, []).append((p, t))

    body = netlist(
        "tb_psrr_dc" if args.kind == "psrr" else "tb_loop_gain",
        args.design,
        out / "requests",
        pdk_root,
    )
    (
        out
        / "requests"
        / f"{'tb_psrr_dc' if args.kind == 'psrr' else 'tb_loop_gain'}.raw.spice"
    ).unlink()
    jobs = []  # (key, meta, request path)
    if args.kind == "psrr":
        meas = [
            {"name": n, "spice": f".meas ac {n} find vdb(vout) at={f:g}"}
            for n, f, _ in PSRR_MEAS
        ]
        for v, cs in by_v.items():
            for load, r in PSRR_LOADS.items():
                key = f"psrr-{load}-v{v:.2f}"
                net = out / "requests" / f"{key}.spice"
                net.write_text(
                    deck(sub_line(body, "RLOAD", f"RLOAD VOUT 0 {r} m=1"), v)
                )
                rp = out / "requests" / f"{key}.json"
                rp.write_text(
                    json.dumps(
                        base_request(
                            net.resolve(),
                            pdk,
                            cs,
                            {"kind": "ac", "args": "lin 3 1e3 1e5"},
                            meas,
                        ),
                        indent=2,
                    )
                    + "\n"
                )
                jobs.append((key, {"vsup": v, "load": load}, rp))
    else:
        lines = body.splitlines()
        i = max(
            k for k, ln in enumerate(lines) if ln.strip().lower().startswith(".ends")
        )
        lines.insert(
            i, "ELG_DEN LG_DEN 0 VREF FB 1"
        )  # instrumentation only: v(lg_den) = v(vref) - v(fb)
        body = "\n".join(lines) + "\n"
        T = lambda n, m, u="": {
            "name": n,
            "unit": u,
            "transfer": {"num": "v(xldo.fb)", "den": "v(xldo.lg_den)", "metric": m},
        }
        meas = [
            T("pm", "phase_margin_deg", "deg"),
            T("gm", "gain_margin_db", "dB"),
            T("fc", "unity_crossing_hz", "Hz"),
            T("dc", "low_frequency_magnitude"),
        ]
        for v, cs in by_v.items():
            for cn, cv in LOOP_COUT.items():
                for en, ev in LOOP_ESR.items():
                    for ln_, lr in LOOP_LOAD.items():
                        key = f"loop-{cn}-{en}-{ln_}-v{v:.2f}"
                        b = sub_line(body, "COUT", f"COUT VOUT VESR {cv} m=1")
                        b = sub_line(b, "HESR", f"HESR VESRS 0 VESRSENSE {ev:g}")
                        b = sub_line(b, "RLOAD", f"RLOAD VOUT 0 {lr} m=1")
                        net = out / "requests" / f"{key}.spice"
                        net.write_text(deck(b, v))
                        rp = out / "requests" / f"{key}.json"
                        rp.write_text(
                            json.dumps(
                                base_request(
                                    net.resolve(),
                                    pdk,
                                    cs,
                                    {"kind": "ac", "args": "dec 30 1e-2 1e9"},
                                    meas,
                                ),
                                indent=2,
                            )
                            + "\n"
                        )
                        jobs.append(
                            (key, {"vsup": v, "cout": cn, "esr": en, "load": ln_}, rp)
                        )

    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [(k, m, ex.submit(submit, k, rp, out, env)) for k, m, rp in jobs]
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

    (out / "summary.json").write_text(
        json.dumps({"design": args.design, "rows": rows, "errors": errors}, indent=1)
        + "\n"
    )
    (out / "record.md").write_text(render(args, rows, errors, pts))
    print(f"record: {out}")
    return 1 if errors else 0


def fnum(x, f="{:.2f}"):
    return "n/a" if x is None else f.format(x)


def render(args, rows, errors, pts) -> str:
    head = [
        f"# {'PSRR' if args.kind == 'psrr' else 'Loop-gain stability'} PVT grid, {args.design}: {args.record_id}",
        "",
        "Issue #467 / DR-013. Executed through `klt sim --backend batch` (no local fallback); translation per the "
        "`sim/bin/bias-retopo-pvt.py` docstring. Bounds are the unchanged ratified spec rows. Graded locally from raw responses.",
        f"Design: `{args.design}` (`dr013` = `R_BIAS` res_xhigh_po W=0.42 L=211; `record` = schematic of record).",
        f"Points requested: {len(pts)}; rows returned: {len(rows)}; failed submits: {len(errors)}.",
        "",
    ]
    for e in errors:
        head.append(
            f"- NOT ESTABLISHED: `{e['key']}` submit failed: {e['error'][:200]!r}"
        )
    if args.kind == "psrr":
        lines = [
            "| load | VIN | process | T(C) | PSRR 1k (dB) | >50 | PSRR 100k (dB) | >20 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        worst = {}
        for r in sorted(
            rows,
            key=lambda r: (
                r["load"],
                r["vsup"],
                PROCESS.index(r["process"]),
                r["temp_c"],
            ),
        ):
            a = None if r.get("p1k") is None else -r["p1k"]
            b = None if r.get("p100k") is None else -r["p100k"]
            ga = "PASS" if a is not None and a > 50 else "FAIL"
            gb = "PASS" if b is not None and b > 20 else "FAIL"
            lines.append(
                f"| {r['load']} | {r['vsup']:.2f} | {r['process']} | {r['temp_c']:g} | {fnum(a)} | {ga} | {fnum(b)} | {gb} |"
            )
            for n, val in (("1k", a), ("100k", b)):
                if val is not None:
                    k = (r["load"], n)
                    if k not in worst or val < worst[k][0]:
                        worst[k] = (val, r)
        head += [
            "## Worst case per metric",
            "",
            "| load | freq | worst PSRR (dB) | at |",
            "|---|---|---|---|",
        ]
        for (load, n), (val, r) in sorted(worst.items()):
            head.append(
                f"| {load} | {n} | {val:.2f} | {r['process']}/{r['temp_c']:g}C/{r['vsup']:.2f}V |"
            )
        return "\n".join(head + ["", "## All points", ""] + lines) + "\n"
    legs = {}
    for r in rows:
        legs.setdefault((r["cout"], r["esr"], r["load"]), []).append(r)
    head += [
        "## Worst case per leg (min over the PVT points returned)",
        "",
        "| C_out | ESR | load | worst PM (deg) | at | PM<45 pts | worst GM (dB) | at | GM<10 pts | pts |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    pm_fail = gm_fail = 0
    for k in sorted(legs):
        rs = legs[k]
        okp = [r for r in rs if r.get("pm") is not None]
        okg = [r for r in rs if r.get("gm") is not None]
        at = lambda r: f"{r['process']}/{r['temp_c']:g}C/{r['vsup']:.2f}V"
        wp = min(okp, key=lambda r: r["pm"]) if okp else None
        wg = min(okg, key=lambda r: r["gm"]) if okg else None
        npm = sum(r["pm"] < PM_MIN for r in okp)
        ngm = sum(r["gm"] < GM_MIN for r in okg)
        pm_fail += npm
        gm_fail += ngm
        head.append(
            f"| {k[0]} | {k[1]} | {k[2]} | {fnum(wp and wp['pm'])} | {wp and at(wp) or ''} | {npm} | "
            f"{fnum(wg and wg['gm'])} | {wg and at(wg) or ''} | {ngm} | {len(okp)} PM / {len(okg)} GM of {len(rs)} |"
        )
    unav_pm = sum(r.get("pm") is None for r in rows)
    unav_gm = sum(r.get("gm") is None for r in rows)
    head += [
        "",
        f"Total PM<{PM_MIN:g} deg points: {pm_fail}; GM<{GM_MIN:g} dB points: {gm_fail}. "
        f"Unavailable (reported, not inferred, never counted as pass): PM at {unav_pm} points, GM at {unav_gm} points "
        "(klt `transfer_metric_unavailable`, typically `no_downward_phase_crossing`: the loop phase never reaches -180 deg in the band).",
        "Every per-point value is in `summary.json`.",
    ]
    return "\n".join(head) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
