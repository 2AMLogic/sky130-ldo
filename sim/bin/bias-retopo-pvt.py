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

The netlist / request / submit core it shares with the other batch-fleet campaign
drivers lives in `sim/bin/_fleet_campaign.py` (issue #574); only this campaign's
grid, grading and record rendering are here.

Usage:
    python3 sim/bin/bias-retopo-pvt.py psrr|loop [--record-id ID] [--design dr013|record]
                                       [--corners tt:27:3.30,...] [--workers 2]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SIM = REPO / "sim"
sys.path.insert(0, str(SIM / "bin"))
import _fleet_campaign as fc  # noqa: E402

PATCH = (
    SIM / "bias-retopo" / "20261029-fullloop-467" / "candidate-R_BIAS.patch"
)  # default; --patch overrides
SCH = "design/ldo_3v3in_1v8out.sch"
SUPPLIES = [2.97, 3.30, 3.63]
PROCESS = fc.PROCESS
TEMPS = [-40.0, 27.0, 125.0]
PSRR_LOADS = {"1ma": "1.8k", "50ma": "36"}
PSRR_MEAS = [("p1k", 1e3, 50.0), ("p100k", 1e5, 20.0)]
LOOP_COUT = {"c033": "0.33u", "c47": "4.7u"}
LOOP_ESR = {"esr10m": 0.01, "esr500m": 0.5, "esr0": 0.0}
LOOP_LOAD = {"50ma": "36", "1ma": "1.8k", "0ma": "1e12"}
PM_MIN, GM_MIN = 45.0, 10.0


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
    ap.add_argument(
        "--patch",
        help="candidate patch to apply for netlisting (default: DR-013 R_BIAS patch)",
    )
    args = ap.parse_args()
    if args.patch:
        global PATCH
        PATCH = Path(args.patch).resolve()
    out = REPO / "sim" / "bias-retopo" / args.record_id
    pdk, pdk_root, env = fc.preamble(args.workers, out)
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

    body = fc.netlist(
        "tb_psrr_dc" if args.kind == "psrr" else "tb_loop_gain",
        out / "requests",
        pdk_root,
        patch=PATCH if args.design == "dr013" else None,
    )
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
                    fc.deck(fc.sub_line(body, "RLOAD", f"RLOAD VOUT 0 {r} m=1"), v)
                )
                rp = out / "requests" / f"{key}.json"
                rp.write_text(
                    json.dumps(
                        fc.base_request(
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
        body = fc.insert_loop_gain_probe(body)
        meas = fc.LOOP_TRANSFER_MEAS
        for v, cs in by_v.items():
            for cn, cv in LOOP_COUT.items():
                for en, ev in LOOP_ESR.items():
                    for ln_, lr in LOOP_LOAD.items():
                        key = f"loop-{cn}-{en}-{ln_}-v{v:.2f}"
                        b = fc.sub_line(body, "COUT", f"COUT VOUT VESR {cv} m=1")
                        b = fc.sub_line(b, "HESR", f"HESR VESRS 0 VESRSENSE {ev:g}")
                        b = fc.sub_line(b, "RLOAD", f"RLOAD VOUT 0 {lr} m=1")
                        net = out / "requests" / f"{key}.spice"
                        net.write_text(fc.deck(b, v))
                        rp = out / "requests" / f"{key}.json"
                        rp.write_text(
                            json.dumps(
                                fc.base_request(
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
    for k, m, resp, job in fc.submit_all(jobs, out, env, args.workers, errors):
        for c in resp["corners"]:
            vals = {x["name"]: x["value"] for x in c["measurements"]}
            rows.append({**fc.corner_base(k, m, c, job), **vals})

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
