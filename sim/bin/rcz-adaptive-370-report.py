#!/usr/bin/env python3
"""Render tables.md + verdict.json for an rcz-adaptive-370.py record (issue #370, stage 2).

    python3 sim/bin/rcz-adaptive-370-report.py <record-dir>

Pure post-processing of <record-dir>/summary.json (and the stage-1 fleet-confirm summary for the
baseline / x16 legs stage 2 did not re-run). Anything missing, errored or non-regulating is counted
as UNRUN/INVALID and can never contribute to a PASS or to an `advance` verdict.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "rcz_adaptive_370", HERE / "rcz-adaptive-370.py"
)
ra = importlib.util.module_from_spec(_spec)
sys.modules["rcz_adaptive_370"] = ra
_spec.loader.exec_module(ra)

STAGE1 = (
    HERE.parent
    / "loop-gain/diagnostics/20261105-080222-a45f37b-fleet-confirm-365/summary.json"
)
DESIGNS = ra.DESIGNS
IQ_DELTA_MAX_UA = (
    0.5  # reporting convenience for the screen: candidate may add at most this to Iq
)


def f(x, fmt="{:.1f}"):
    return "n/a" if x is None else fmt.format(x)


def ac_valid(m: dict) -> bool:
    return m.get("pm") is not None and m.get("gm") is not None


def ac_pass(m: dict) -> bool:
    return ac_valid(m) and m["pm"] >= ra.PM_MIN and m["gm"] >= ra.GM_MIN


def collect(rows):
    ac, pvt, op, tran = {}, {}, {}, {}
    for r in rows:
        m = r["measurements"]
        ok = r["status"] in ("pass", "fail")
        if r["fam"] == "ac":
            ac[(r["design"], r["leg"])] = m if ok else {}
        elif r["fam"] == "acpvt":
            pvt[(r["design"], r["leg"], r["process"], r["temp_c"])] = m if ok else {}
        elif r["fam"] == "op":
            for k, v in m.items():
                step, name = k.split(".", 1)
                op.setdefault((r["design"], r["process"], r["temp_c"], step[3:]), {})[
                    name
                ] = v if ok or v is not None else None
        elif r["fam"] == "tran":
            for k, v in m.items():
                step, name = k.split(".", 1)
                tran.setdefault(
                    (r["design"], r["case"], r["process"], r["temp_c"], step), {}
                )[name] = v
    if STAGE1.exists():
        for r in json.loads(STAGE1.read_text())["rows"]:
            ac.setdefault(
                (r["design"], r["leg"]),
                {"pm": r.get("pm"), "gm": r.get("gm"), "fc": r.get("fc")}
                if r["status"] in ("pass", "fail")
                else {},
            )
    return ac, pvt, op, tran


def main() -> int:
    rec = Path(sys.argv[1])
    data = json.loads((rec / "summary.json").read_text())
    ac, pvt, op, tran = collect(data["rows"])
    L = ["# Adaptive R_CZ screen — tables (issue #370 stage 2)", ""]
    verdict = {}

    # ---- AC tt/27
    legs = [l[5] for l in ra.AC_LEGS]
    L += [
        "## Loop gain, tt / 27 C / 3.30 V (PM deg / GM dB; `*` = fails PM>=45 or GM>=10; `-` = unrun/invalid)",
        "",
        "| leg | baseline | x16 | candA | candB |",
        "|---|---|---|---|---|",
    ]
    for lg in legs:
        cells = []
        for d in DESIGNS:
            m = ac.get((d, lg), {})
            cells.append(
                "-"
                if not ac_valid(m)
                else f"{m['pm']:.1f} / {m['gm']:.1f}{'' if ac_pass(m) else ' *'}"
            )
        L.append(f"| {lg} | " + " | ".join(cells) + " |")
    L.append("")
    for d in ra.ADAPTIVE:
        valid = [lg for lg in legs if ac_valid(ac.get((d, lg), {}))]
        fails = [lg for lg in legs if not ac_pass(ac.get((d, lg), {}))]
        regress = [
            lg
            for lg in legs
            if ac_pass(ac.get(("baseline", lg), {}))
            and not ac_pass(ac.get((d, lg), {}))
        ]
        verdict[d] = {
            "ac_tt_valid": len(valid),
            "ac_tt_total": len(legs),
            "ac_tt_fail_or_unrun": fails,
            "ac_tt_regressions_vs_baseline": regress,
        }

    # ---- AC PVT
    L += [
        "## Loop gain, ss/ff x -40/125 C (PM / GM)",
        "",
        "| leg | corner | baseline | candA | candB |",
        "|---|---|---|---|---|",
    ]
    for lg in sorted({k[1] for k in pvt}):
        for p, t in ra.PVT_CORNERS:
            cells = []
            for d in ("baseline", "candA", "candB"):
                m = pvt.get((d, lg, p, t), {})
                cells.append(
                    "-"
                    if not ac_valid(m)
                    else f"{m['pm']:.1f} / {m['gm']:.1f}{'' if ac_pass(m) else ' *'}"
                )
            L.append(f"| {lg} | {p}/{t:g} | " + " | ".join(cells) + " |")
    L.append("")
    for d in ra.ADAPTIVE:
        keys = [
            (lg, p, t) for lg in sorted({k[1] for k in pvt}) for p, t in ra.PVT_CORNERS
        ]
        verdict[d]["ac_pvt_total"] = len(keys)
        verdict[d]["ac_pvt_regressions_vs_baseline"] = [
            f"{lg}@{p}/{t:g}"
            for lg, p, t in keys
            if ac_pass(pvt.get(("baseline", lg, p, t), {}))
            and not ac_pass(pvt.get((d, lg, p, t), {}))
        ]

    # ---- OP
    L += [
        "## Operating point: Iq (uA, = I(VIN) - I_load), effective R_CZ (kohm), switch gate (V); worst over 9 PVT corners",
        "",
        "| load | design | worst Iq | worst dIq vs baseline | R_CZ eff at tt/27 | R_CZ eff min..max over PVT | non-regulating corners |",
        "|---|---|---|---|---|---|---|",
    ]
    for ld, il in ra.OP_LOADS.items():
        for d in DESIGNS:
            iqs, effs, bad, dq = [], [], 0, []
            for p, t in ra.OP_CORNERS:
                m = op.get((d, p, t, ld), {})
                if not ra.regulating(m.get("vout")) or m.get("ivin") is None:
                    bad += 1
                    continue
                iq = ra.iq_ua(-m["ivin"] if m["ivin"] < 0 else m["ivin"], il)
                iqs.append(iq)
                b = op.get(("baseline", p, t, ld), {})
                if ra.regulating(b.get("vout")) and b.get("ivin") is not None:
                    dq.append(
                        iq - ra.iq_ua(-b["ivin"] if b["ivin"] < 0 else b["ivin"], il)
                    )
                e = ra.r_eff(d, m)
                if e:
                    effs.append((p, t, e))
            tt = [e for p, t, e in effs if (p, t) == ("tt", 27.0)]
            L.append(
                f"| {ld} | {d} | {f(max(iqs), '{:.3f}') if iqs else 'n/a'} | {f(max(dq), '{:+.3f}') if dq else 'n/a'} | "
                f"{f(tt[0] / 1e3, '{:.0f}') if tt else 'n/a'} | "
                f"{(f(min(e for *_, e in effs) / 1e3, '{:.0f}') + '..' + f(max(e for *_, e in effs) / 1e3, '{:.0f}')) if effs else 'n/a'} | {bad} |"
            )
            if d in ra.ADAPTIVE and dq:
                verdict[d].setdefault("worst_dIq_uA", {})[ld] = max(dq)
            if d in ra.ADAPTIVE:
                verdict[d].setdefault("op_nonregulating", {})[ld] = bad
    L.append("")
    L += [
        "Switch state (R_CZ eff at tt/27, kohm) vs load — adaptation threshold:",
        "",
        "| design | corner | " + " | ".join(ra.OP_LOADS) + " |",
        "|---|---|" + "---|" * len(ra.OP_LOADS),
    ]
    for d in ra.ADAPTIVE:
        for p, t in ra.OP_CORNERS:
            cells = []
            for ld in ra.OP_LOADS:
                e = ra.r_eff(d, op.get((d, p, t, ld), {}))
                cells.append(f(e / 1e3, "{:.0f}") if e else "-")
            L.append(f"| {d} | {p}/{t:g} | " + " | ".join(cells) + " |")
    L.append("")

    # ---- TRAN
    L += [
        "## Load-step transients (ESR 10 mOhm; peak = max |dev| from pre-step; rec = time to stay inside +-1% of 1.8 V)",
        "",
        "| case | COUT | corner | baseline peak mV / rec us | x16 | candA | candB |",
        "|---|---|---|---|---|---|---|",
    ]
    tran_reg = {d: [] for d in ra.ADAPTIVE}
    for case in ra.TRAN_CASES:
        for cstep in ("c0p33u", "c4p7u"):
            for p, t in ra.OP_CORNERS:
                cells, gr = [], {}
                for d in DESIGNS:
                    m = tran.get((d, case, p, t, cstep))
                    if m is None:
                        cells.append("unrun")
                        continue
                    g = ra.grade_tran(m)
                    gr[d] = g
                    cells.append(
                        "INVALID"
                        if not g["valid"]
                        else f"{g['peak_v'] * 1e3:.0f} / {('NOT RECOVERED' if not g['recovered'] else f(g['rec_us'], '{:.0f}'))}"
                    )
                L.append(
                    f"| {case} | {cstep} | {p}/{t:g} | " + " | ".join(cells) + " |"
                )
                b = gr.get("baseline")
                for d in ra.ADAPTIVE:
                    g = gr.get(d)
                    if (
                        g is None
                        or not g["valid"]
                        or not g["recovered"]
                        and (b and b["valid"] and b["recovered"])
                    ):
                        tran_reg[d].append(f"{case}/{cstep}/{p}/{t:g}")
                    elif b and b["valid"] and g["peak_v"] > b["peak_v"] + 0.020:
                        tran_reg[d].append(f"{case}/{cstep}/{p}/{t:g}(peak)")
                    elif (
                        b
                        and b["valid"]
                        and b["rec_us"] is not None
                        and g["rec_us"] is not None
                        and g["rec_us"] > 1.2 * b["rec_us"] + 10.0
                    ):
                        tran_reg[d].append(
                            f"{case}/{cstep}/{p}/{t:g}(recovery {b['rec_us']:.0f}->{g['rec_us']:.0f}us)"
                        )
    L.append("")
    for d in ra.ADAPTIVE:
        verdict[d]["tran_regressions_or_invalid"] = tran_reg[d]

    # ---- verdict
    for d in ra.ADAPTIVE:
        v = verdict[d]
        diq = max(v.get("worst_dIq_uA", {}).values(), default=None)
        v["max_dIq_uA"] = diq
        full_ac = v["ac_tt_valid"] == v["ac_tt_total"]
        clean = (
            full_ac
            and not v["ac_tt_fail_or_unrun"]
            and not v["ac_pvt_regressions_vs_baseline"]
            and not v["tran_regressions_or_invalid"]
            and diq is not None
            and diq <= IQ_DELTA_MAX_UA
        )
        if v["ac_tt_regressions_vs_baseline"] or (
            diq is not None and diq > IQ_DELTA_MAX_UA
        ):
            v["verdict"] = "reject"
        elif clean:
            v["verdict"] = "advance"
        else:
            v["verdict"] = "revise"
    (rec / "verdict.json").write_text(json.dumps(verdict, indent=1) + "\n")
    L += [
        "## Machine verdict (screen only; never a qualification claim)",
        "",
        "```json",
        json.dumps(verdict, indent=1),
        "```",
        "",
    ]
    (rec / "tables.md").write_text("\n".join(L))
    print("\n".join(f"{d}: {verdict[d]['verdict']}" for d in ra.ADAPTIVE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
