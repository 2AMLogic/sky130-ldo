#!/usr/bin/env python3
"""Render a `records/<record-id>.{json,md}` pair for a `klt pex` run
(issue #20), same append-only evidence convention as sim/dropout-vs-load
etc.'s own records -- machine-readable JSON summary + a short human-readable
markdown summary, both pointing at the full klt-requests/klt-responses/
netlist-snapshots artifacts rather than duplicating them.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SIM_BIN_DIR = str(Path(__file__).resolve().parents[2] / "bin")
if _SIM_BIN_DIR not in sys.path:
    sys.path.insert(0, _SIM_BIN_DIR)
from _record_common import git  # shared git() helper (issue #51/#84)


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def summarize_delta(pex_resp: dict | None, request: dict | None) -> dict | None:
    """Per-measurement |delta%| spread across `klt pex`'s `delta[]` rows.

    Why this is in the record at all (issue #142): `klt pex`'s row `status`
    is graded against the *declared* limits in the request's `measurements[]`
    -- and this experiment's request declares none. So an all-`pass`,
    exit-code-0 `klt pex` report means "both legs produced a number for every
    row", **not** "the extracted values agree with the schematic values". The
    spread below is the number that actually says how far apart the two legs
    are, and `limits_declared` is the flag that says how much the verdict is
    worth. Recording only the verdict, without these, would be the kind of
    dressed-up pass `README.md`'s own "not a fabricated pass" note refuses.
    """
    if not pex_resp:
        return None
    rows = pex_resp.get("delta") or []
    if not rows:
        return None
    declared = set()
    for measurement in (request or {}).get("measurements", []) or []:
        if any(k in measurement for k in ("limits", "limit", "tolerance_pct")):
            declared.add(measurement.get("name"))
    per_row: dict[str, dict] = {}
    for row in rows:
        name = row.get("spec_row")
        value = row.get("delta_pct")
        if name is None or value is None:
            continue
        per_row.setdefault(name, {"deltas": [], "worst_corner": None})
        per_row[name]["deltas"].append((abs(value), row.get("corner_id")))
    summary = {}
    for name, acc in per_row.items():
        magnitudes = sorted(m for m, _ in acc["deltas"])
        worst = max(acc["deltas"])
        summary[name] = {
            "row_count": len(magnitudes),
            "abs_delta_pct_min": round(magnitudes[0], 3),
            "abs_delta_pct_median": round(magnitudes[len(magnitudes) // 2], 3),
            "abs_delta_pct_max": round(magnitudes[-1], 3),
            "worst_corner": worst[1],
            "limits_declared": name in declared,
        }
    return summary or None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-id", required=True)
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--layout-record-id", required=True)
    ap.add_argument("--sim-schematic-response", required=True)
    ap.add_argument("--sim-schematic-exit", required=True, type=int)
    ap.add_argument("--pex-response", required=True)
    ap.add_argument("--pex-exit", required=True, type=int)
    ap.add_argument("--request", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-md", required=True)
    ap.add_argument(
        "--supersedes",
        default="",
        help="record id this run supersedes (append-only evidence pointer; "
        "e.g. a prior run whose cited layout/LVS record has since gone stale)",
    )
    args = ap.parse_args()

    repo_root = Path(args.repo_root)
    sim_resp = load_json(Path(args.sim_schematic_response))
    pex_resp = load_json(Path(args.pex_response))
    request = load_json(Path(args.request))
    delta_summary = summarize_delta(pex_resp, request)

    sha = git(repo_root, "rev-parse", "HEAD")
    dirty = bool(git(repo_root, "status", "--porcelain"))
    branch = git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")

    sim_summary = None
    if sim_resp is not None:
        sim_summary = {
            "status": sim_resp.get("status"),
            "corner_count": sim_resp.get("corner_count"),
            "passed": sim_resp.get("passed"),
            "failed": sim_resp.get("failed"),
            "errored": sim_resp.get("errored"),
        }

    pex_summary = None
    if pex_resp is not None:
        pex_summary = {
            "status": pex_resp.get("status"),
            "passed": pex_resp.get("passed"),
            "failed": pex_resp.get("failed"),
            "errored": pex_resp.get("errored"),
            "pin_count_mismatch": pex_resp.get("pin_count_mismatch"),
            "extraction": pex_resp.get("extraction"),
            "error": pex_resp.get("error"),
        }

    out = {
        "record_id": args.record_id,
        "experiment": "pex-post-layout",
        "issue": 20,
        "layout_record_id": args.layout_record_id,
        "repo_state": {"sha": sha, "branch": branch, "dirty": dirty},
        "sim_schematic": {
            "exit_code": args.sim_schematic_exit,
            "response": f"klt-responses/{args.record_id}.sim-schematic.json",
            "summary": sim_summary,
        },
        "pex": {
            "exit_code": args.pex_exit,
            "response": f"klt-responses/{args.record_id}.pex.json",
            "summary": pex_summary,
            "delta_spread": delta_summary,
        },
        "request": f"klt-requests/{args.record_id}.request.json",
        "netlist_snapshots": {
            "schematic_dut": f"netlist-snapshots/{args.record_id}.schematic-dut.spice",
            "pex_extract": f"netlist-snapshots/{args.record_id}.pex.extract.spice",
        },
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "supersedes": args.supersedes or None,
    }
    Path(args.out_json).write_text(json.dumps(out, indent=2) + "\n")

    exit_meaning = {
        0: "all delta[] rows passed",
        1: "hard failure (see error below)",
        3: "ran; at least one delta[] row failed its own declared limits",
        4: "ran; at least one delta[] row errored (no trustworthy extracted-side value)",
    }.get(args.pex_exit, "unrecognized exit code")

    lines = [
        f"# Record {args.record_id}",
        "",
        "- **Record ID**: " + args.record_id,
        "- **Experiment**: `pex-post-layout` -- post-layout (parasitic-extracted) verification (issue #20)",
        f"- **Layout record**: `layout/ldo-core/reports/{args.layout_record_id}` (via `layout/ldo-core/reports/LATEST-LVS`)",
        f"- **Repo state**: `{sha[:9]}` on `{branch}`" + (" (working tree dirty at run time)" if dirty else ""),
        "",
        "## `klt sim` (schematic-side leg, standalone)",
        "",
        f"- Exit code: {args.sim_schematic_exit}",
    ]
    if sim_summary:
        lines.append(
            f"- Result: status={sim_summary['status']}, corners={sim_summary['corner_count']}, "
            f"passed={sim_summary['passed']}, failed={sim_summary['failed']}, errored={sim_summary['errored']}"
        )
    else:
        lines.append("- Result: response JSON not parseable -- see the raw response file")
    lines += [
        f"- Response: `klt-responses/{args.record_id}.sim-schematic.json`",
        "",
        "## `klt pex` (schematic + extracted legs + delta)",
        "",
        f"- Exit code: {args.pex_exit} ({exit_meaning})",
    ]
    if pex_summary and pex_summary.get("status") is not None:
        lines.append(
            f"- Result: status={pex_summary['status']}, passed={pex_summary['passed']}, "
            f"failed={pex_summary['failed']}, errored={pex_summary['errored']}, "
            f"pin_count_mismatch={pex_summary['pin_count_mismatch']}"
        )
        if pex_summary.get("extraction"):
            ext = pex_summary["extraction"]
            lines.append(
                f"- Extraction: deck={ext.get('deck')}, device_count={ext.get('device_count')}, "
                f"net_count={ext.get('net_count')}"
            )
    elif pex_summary and pex_summary.get("error"):
        lines.append(f"- Hard failure: {pex_summary['error'].get('message')}")
    else:
        lines.append("- Result: response JSON not parseable -- see the raw response file")
    lines += [
        f"- Response: `klt-responses/{args.record_id}.pex.json`",
        f"- Extracted netlist: `netlist-snapshots/{args.record_id}.pex.extract.spice`",
        f"- Schematic DUT used: `netlist-snapshots/{args.record_id}.schematic-dut.spice`",
        f"- Request: `klt-requests/{args.record_id}.request.json`",
        "",
    ]
    if delta_summary:
        ungraded = [n for n, s in delta_summary.items() if not s["limits_declared"]]
        lines += [
            "### `delta[]` spread (extracted vs. schematic)",
            "",
            "| Measurement | Rows | min \\|delta\\| % | median \\|delta\\| % |"
            " max \\|delta\\| % | Worst corner | Limits declared |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for name, stats in sorted(delta_summary.items()):
            lines.append(
                f"| `{name}` | {stats['row_count']} | "
                f"{stats['abs_delta_pct_min']:g} | "
                f"{stats['abs_delta_pct_median']:g} | "
                f"{stats['abs_delta_pct_max']:g} | "
                f"`{stats['worst_corner']}` | "
                f"{'yes' if stats['limits_declared'] else '**no**'} |"
            )
        lines.append("")
        if ungraded:
            lines.append(
                "**A row's `status` is graded against the limits its own"
                " `measurements[]` entry declares, and "
                + ", ".join(f"`{n}`" for n in sorted(ungraded))
                + (" declare" if len(ungraded) > 1 else " declares")
                + " none.** For those rows `pass` means only that"
                " both legs produced a number -- it is *not* a statement that"
                " the extracted value agrees with the schematic value. Read"
                " the spread above, not the verdict, for how far apart the two"
                " legs actually are."
            )
            lines.append("")
    lines += [
        "**Read this alongside `sim/pex-post-layout/README.md`** before drawing any conclusion from"
        " the numbers above. The three gaps that previously bounded the extracted-side leg are"
        " closed as of this record: klayout-tools#1157 and #1159 (which blocked it from converging"
        " at all) upstream, and the MOS-flavour-binding gap klayout-tools#1369 upstream plus its"
        " repo-local half -- the layout now draws sky130's `hvi` (75/20) voltage-domain marker"
        " (issue #142), so `klt extract --pdk` binds the schematic's own"
        " `sky130_fd_pr__{n,p}fet_g5v0d10v5` models instead of substituting the 1.8V core flavour."
        " Read that file's caveat section for what this experiment still does not cover before"
        " comparing anything here to `spec/target-spec.md`.",
        "",
        f"- **Timestamp**: {out['timestamp']}",
        f"- **Supersedes**: {args.supersedes or '(none)'}",
        "",
    ]
    Path(args.out_md).write_text("\n".join(lines))

    print(f"render-pex-record.py: wrote {args.out_json}")
    print(f"render-pex-record.py: wrote {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
