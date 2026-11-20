#!/usr/bin/env python3
"""Regenerate the #691 tables and verdict from this campaign's saved batch responses."""

import argparse
import importlib
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
screen = importlib.import_module("rcz-shelf-691")
adaptive = screen.adaptive


def fmt(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def condition(row):
    return f"{row['cap']}F / {row['esr']}Ω / {row['load']} / {row['process']} {row['temp']:g} °C"


def ac_summary(rows):
    valid = [r for r in rows if not r["reason"]]
    worst = {}
    for metric in ("pm", "gm"):
        limiting = min(valid, key=lambda r: r[metric], default=None)
        worst[metric] = (
            None
            if limiting is None
            else {"value": limiting[metric], "condition": condition(limiting)}
        )
    return {
        "valid": len(valid),
        "total": len(rows),
        "worst": worst,
        "failed": [
            condition(r)
            for r in valid
            if r["pm"] < screen.fc.PM_MIN or r["gm"] < screen.fc.GM_MIN
        ],
    }


def ac_table(lines, stage, rows):
    lines.extend(
        [
            f"## {stage} loop gain at 3.30 V",
            "",
            "| C_OUT / ESR / load / PVT | Baseline PM (°) / GM (dB) | Shelf PM (°) / GM (dB) |",
            "|---|---|---|",
        ]
    )
    for base, cand in zip(rows[: len(rows) // 2], rows[len(rows) // 2 :], strict=True):
        cells = []
        for r in (base, cand):
            note = f" ({' '.join(r['reason'].split())})" if r["reason"] else ""
            failed = not r["reason"] and (
                r["pm"] < screen.fc.PM_MIN or r["gm"] < screen.fc.GM_MIN
            )
            cells.append(
                f"{fmt(r['pm'])} / {fmt(r['gm'])}{note or (' FAIL' if failed else '')}"
            )
        lines.append(f"| {condition(base)} | " + " | ".join(cells) + " |")
    lines.append("")


def survivor_corner(out, key, process, temp, transient=False):
    c, job, error = screen.corner_data(screen.response(out, key), process, temp)
    values = screen.measurements(c)
    errors = [d for d in c.get("diagnostics", []) if d.get("severity") == "error"]
    # klt reports the corner as error when a valid tran has no band crossing.
    crossing_names = {
        f"{step}.{card}" for step in ("c0p33u", "c4p7u") for card in ("thi", "tlo")
    }

    def no_crossing(d):
        return d.get("code") == "measurement" and any(
            d.get("message", "").startswith(f"measurement '{name}' produced no value:")
            and values.get(name) is None
            for name in crossing_names
        )

    crossing_only = transient and errors and all(no_crossing(d) for d in errors)
    if (errors or c.get("status") not in ("pass", "fail")) and not crossing_only:
        error = error or f"corner {c.get('status')} with invalid measurements"
    return values, job, error


def tran_result(m):
    grade = adaptive.grade_tran(m)
    # For an excursion that settles, each visited boundary needs a post-step crossing.
    if grade["valid"] and abs(m["vfin"] - adaptive.VNOM) <= adaptive.BAND:
        for excursion, card in (
            (m["vmin"] < adaptive.VNOM - adaptive.BAND, "tlo"),
            (m["vmax"] > adaptive.VNOM + adaptive.BAND, "thi"),
        ):
            if excursion and (m.get(card) is None or m[card] < adaptive.T_STEP):
                return dict(grade, valid=False, recovered=False, rec_us=None)
    return grade


def survivor_tables(out, lines):
    iq_rows, tran_rows = [], []
    lines.extend(
        [
            "## Quiescent current at 3.30 V",
            "",
            "| PVT | Load | Baseline (µA) | Shelf (µA) | Delta (µA) | Shelf < 30 µA |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for process, temp in adaptive.OP_CORNERS:
        for load, iload in (("0mA", 0.0), ("50mA", 0.05)):
            pair = {}
            for design in screen.DESIGNS:
                m, job, reason = survivor_corner(out, f"iq__{design}", process, temp)
                vin_current = m.get(f"iq_{load}.ivin")
                iq = None
                if vin_current is not None and adaptive.regulating(
                    m.get(f"iq_{load}.vout")
                ):
                    # Compare the reported precision at the strict 30 µA boundary.
                    iq = float(
                        (Decimal(str(vin_current)) - Decimal(str(iload))) * 1_000_000
                    )
                reason = reason or (
                    "invalid supply current or VOUT" if iq is None or iq < 0 else None
                )
                pair[design] = {
                    "iq_uA": iq if not reason else None,
                    "reason": reason,
                    "job_id": job,
                }
            b, c = (pair[d]["iq_uA"] for d in screen.DESIGNS)
            delta = None if b is None or c is None else c - b
            passed = delta is not None and c < 30
            iq_rows.append(
                dict(
                    process=process,
                    temp=temp,
                    load=load,
                    **pair,
                    delta_uA=delta,
                    passed=passed,
                )
            )
            lines.append(
                f"| {process}/{temp:g} | {load} | {fmt(b, 3)} | {fmt(c, 3)} | {fmt(delta, 3)} | {passed} |"
            )
    lines.extend(
        [
            "",
            "## Load transients at 10 mΩ and 3.30 V",
            "",
            "Recovery uses the last crossing of the ±1% band. A trace staying inside the band has zero recovery time. A final voltage outside the band is unrecovered.",
            "",
            "| PVT | Step | C_OUT | Baseline peak (mV) / recovery (µs) | Shelf peak (mV) / recovery (µs) |",
            "|---|---|---|---|---|",
        ]
    )
    for process, temp in adaptive.OP_CORNERS:
        for case in ("r1to50mA", "f50to1mA"):
            pair = {
                d: survivor_corner(out, f"{case}__{d}", process, temp, transient=True)
                for d in screen.DESIGNS
            }
            for cap, _ in adaptive.CAPS:
                cells, results = [], {}
                for d, (values, job, error) in pair.items():
                    step = "c" + cap.replace(".", "p")
                    m = {n: values.get(f"{step}.{n}") for n, _ in adaptive.tran_cards()}
                    grade = tran_result({} if error else m)
                    results[d] = dict(grade, job_id=job, reason=error)
                    peak = grade["peak_v"]
                    cells.append(
                        f"{fmt(peak * 1000 if peak is not None else None)} / "
                        + (
                            fmt(grade["rec_us"])
                            if grade["recovered"]
                            else ("unrecovered" if grade["valid"] else "invalid")
                        )
                    )
                c = results["shelf"]
                passed = (
                    results["baseline"]["valid"]
                    and c["valid"]
                    and c["recovered"]
                    and c["peak_v"] <= 0.150
                    and c["rec_us"] <= 20
                )
                tran_rows.append(
                    dict(
                        process=process,
                        temp=temp,
                        case=case,
                        cap=cap,
                        **results,
                        passed=passed,
                    )
                )
                lines.append(
                    f"| {process}/{temp:g} | {case} | {cap}F | "
                    + " | ".join(cells)
                    + " |"
                )
    return iq_rows, tran_rows


def render(out, adoption_issue=None):
    meta = json.loads((out / "campaign.json").read_text())
    lines = [
        "# Frequency-dependent R_CZ screen",
        "",
        f"PM ≥ {screen.fc.PM_MIN:g}° and GM ≥ {screen.fc.GM_MIN:g} dB at every required point.",
        "",
    ]
    summary = {}
    skip = []
    verdict = {"mechanism": meta["mechanism"], "ac": summary, "not_run": skip}
    ac_ok = False
    for stage in ("tt", "pvt"):
        rows = screen.ac_rows(out, stage, meta)
        summary[stage] = {
            d: ac_summary([r for r in rows if r["design"] == d]) for d in screen.DESIGNS
        }
        ac_table(lines, stage, rows)
        for d, result in summary[stage].items():
            for metric, unit in (("pm", "°"), ("gm", " dB")):
                worst = result["worst"][metric]
                limit = (
                    f"{fmt(worst['value'])}{unit} at {worst['condition']}"
                    if worst
                    else "unmeasured"
                )
                lines.append(f"- {d} worst measured {metric.upper()} is {limit}.")
        lines.append("")
        ac_ok = screen.advance(rows, stage)
        if not ac_ok:
            if stage == "tt":
                skip.append(
                    "56 ss/ff points per design require 42 passing shelf tt points with valid matched baseline data."
                )
                if meta["preflight"]["exit"]:
                    skip.insert(
                        0,
                        "42 tt points per design require an accepted batch preflight.",
                    )
            skip.append(
                "Iq and load transients require both paired AC stages to clear."
            )
            break
    passed = False
    if ac_ok:
        iq, tran = survivor_tables(out, lines)
        verdict.update(iq=iq, transients=tran)
        passed = all(r["passed"] for r in iq + tran)
    if adoption_issue is not None and (adoption_issue < 1 or not passed):
        raise ValueError(
            "adoption requires complete passing paired AC, Iq and transient evidence"
        )
    if meta["preflight"]["exit"]:
        action = "Restore fleet submission access and rerun this same candidate. Circuit performance is unmeasured."
    elif not ac_ok:
        result = summary[stage]["shelf"]
        if (
            summary[stage]["baseline"]["valid"] < len(rows) // 2
            or result["valid"] < result["total"]
        ):
            action = "Resolve the missing or invalid paired measurements before changing the network."
        else:
            action = "Move the bypass transition or change the residual resistance to address the limiting conditions above, retaining the zero-load repair."
    elif not passed:
        action = (
            "Resolve the failed or invalid Iq and load-transient rows before advancing."
        )
    elif not adoption_issue:
        action = (
            "Name the schematic adoption and qualification follow-up before advancing."
        )
    else:
        action = f"Land the shelf network under #{adoption_issue}, coordinate the bias revision (#467), and run the remaining full qualification matrix (#554)."
    verdict["ac_evidence_complete"] = all(
        result["valid"] == result["total"]
        for stages in summary.values()
        for result in stages.values()
    )
    verdict.update(verdict="ADOPT" if adoption_issue else "REVISE", next_action=action)
    lines.extend(
        [
            "",
            "## NOT run",
            "",
            *[f"- {s}" for s in skip],
            "- The passive network has no control state or added CL_SNS load. Current-limit interaction and switch-state measurements do not apply.",
            "",
            f"**{verdict['verdict']}**. {action}",
            "",
        ]
    )
    (out / "verdict.json").write_text(json.dumps(verdict, indent=2) + "\n")
    (out / "tables.md").write_text("\n".join(lines))
    return verdict


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument(
        "--adoption-issue",
        type=int,
        help="schematic and qualification follow-up for a passing candidate",
    )
    args = parser.parse_args()
    print(render(args.record, args.adoption_issue)["verdict"])
