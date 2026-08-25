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
    args = ap.parse_args()

    repo_root = Path(args.repo_root)
    sim_resp = load_json(Path(args.sim_schematic_response))
    pex_resp = load_json(Path(args.pex_response))

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
        },
        "request": f"klt-requests/{args.record_id}.request.json",
        "netlist_snapshots": {
            "schematic_dut": f"netlist-snapshots/{args.record_id}.schematic-dut.spice",
            "pex_extract": f"netlist-snapshots/{args.record_id}.pex.extract.spice",
        },
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
        "**Read this alongside `sim/pex-post-layout/README.md`** before drawing any conclusion from"
        " the numbers above -- two disclosed, real, upstream `klt`/PDK-model-interaction gaps"
        " (klayout-tools#1157, #1159) block the extracted-side leg from converging at all, plus a"
        " separate disclosed MOS-flavor-binding caveat where it would converge (klayout-tools#1369,"
        " sky130-specific; supersedes the now-closed #1089, whose own follow-on fix (#1111) landed"
        " gf180mcu-only) -- see that file's full caveat before comparing anything here to"
        " `spec/target-spec.md`.",
        "",
        f"- **Timestamp**: {out['timestamp']}",
        "- **Supersedes**: (none)",
        "",
    ]
    Path(args.out_md).write_text("\n".join(lines))

    print(f"render-pex-record.py: wrote {args.out_json}")
    print(f"render-pex-record.py: wrote {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
