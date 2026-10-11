#!/usr/bin/env python3
"""Run the PSRR C_eff x ESR reduced sweep (issue #314, Phase 1) through `klt sim`.

One `klt sim` request per corner of `sim/psrr-dc/cap-esr-sweep.json`; each
request's deck walks the 9 (C_eff, ESR) points x 2 loads as ordered
`analysis_steps` (see psrr_cap_sweep.build_steps), plus a repeat of the
nominal point at the end as an order-independence check.

Backends
--------
* `--backend batch` (default): every corner request goes to the Spot batch
  fleet (`klt sim --backend batch`).  A failed/ambiguous submit aborts with
  NO record and NO local fallback.
* `--backend local`: only with exactly one `--corner` (a single-corner spot
  check -- this host is not a simulation box); never writes a record.

A record is minted only when every manifest corner came back from the fleet:
`sim/psrr-dc/records/<id>.{json,md}` with `evidence_kind:
"psrr-cap-esr-sweep"` (so the characterization report's campaign-record
selector skips it), plus the raw klt requests/responses/netlists and the
retrieved engine logs.  Append-only: nothing existing is ever overwritten.

Usage
-----
    python3 sim/bin/psrr-cap-sweep-run.py --dry-run
    python3 sim/bin/psrr-cap-sweep-run.py                     # batch, all corners, mint record
    python3 sim/bin/psrr-cap-sweep-run.py --backend local --corner tt_27c_3.30v
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN_DIR))

import psrr_cap_sweep as pcs  # noqa: E402
from _record_common import (  # noqa: E402
    assert_klt_read_the_pinned_pdk,
    load_corner_run_module,
    reserve_record_id,
    write_new_text,
)

cr = load_corner_run_module(BIN_DIR)
SIM_DIR = cr.SIM_DIR
REPO_ROOT = cr.REPO_ROOT
EXP_DIR = SIM_DIR / "psrr-dc"
MANIFEST = EXP_DIR / "cap-esr-sweep.json"
REFERENCE_RECORD = "20260926-033606-4a9ec09"
HarnessError = cr.HarnessError


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def corner_netlist(body: list[str], supply_v: float, options: list[str]) -> str:
    head = [f".param vsup={supply_v}"] + [f".option {o}" for o in options] + [".save all"]
    return "\n".join(head + body) + "\n"


def run_klt(request_path: Path, outdir: Path, backend: str, pdk_root: Path) -> tuple[dict, dict]:
    """One `klt sim` call; never retried, never replaced by a local run."""
    outdir = outdir.resolve()  # a relative -o breaks klt's per-corner cwd (klayout-tools#2892)
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [cr.klt_binary(), "sim", str(request_path.resolve()), "-o", str(outdir),
           "--backend", backend, "--format", "json"]
    env = dict(os.environ, PDK_ROOT=str(pdk_root))
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    (outdir / "klt.stdout").write_text(proc.stdout or "")
    (outdir / "klt.stderr").write_text(proc.stderr or "")
    ids = sorted(set(cr._JOB_ID_RE.findall((proc.stdout or "") + (proc.stderr or ""))))
    where = (f"  cmd: {' '.join(cmd)}\n  rc: {proc.returncode}\n  job id(s): {', '.join(ids) or 'none'}\n"
             f"  stderr: {(proc.stderr or '').strip()[:2000]}\n  kept in {outdir}")
    try:
        response = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise HarnessError(f"klt sim gave no JSON response\n{where}") from None
    if not isinstance(response, dict) or not isinstance(response.get("corners"), list):
        raise HarnessError(f"klt sim returned an error envelope\n{where}\n"
                           f"  stdout: {(proc.stdout or '').strip()[:2000]}")
    return response, {"returncode": proc.returncode, "cmd": cmd, "job_ids_seen": ids}


def engine_log(rc: dict, outdir: Path) -> str | None:
    art = rc.get("artifacts") if isinstance(rc.get("artifacts"), dict) else {}
    ref = art.get("log")
    if not isinstance(ref, str) or not ref:
        return None
    p = Path(ref)
    for cand in (p, outdir / p, outdir.parent / p):
        if cand.is_file():
            return cand.read_text(errors="replace")
    return None


def reference_values() -> dict:
    """The nominal-point values of the 45-corner record this sweep spot-checks."""
    rec = json.loads((EXP_DIR / "records" / f"{REFERENCE_RECORD}.json").read_text())
    for c in rec.get("corners", []):
        if c.get("corner_id") == "tt_27c_3.30v":
            return {m["name"]: m.get("value") for m in c.get("measurements", [])}
    return {}


def spot_check(results: list[dict]) -> dict | None:
    row = next((r for r in results if r["corner_id"] == "tt_27c_3.30v"
                and r["c_uf"] == 1.0 and r["esr_ohm"] == 0.01), None)
    if row is None:
        return None
    ref = reference_values()
    cmp = []
    for name, v in sorted(row["metrics"].items()):
        b = ref.get(name)
        cmp.append({"metric": name, "this_db": v, "reference_db": b,
                    "delta_db": (v - b) if pcs._finite(v) and pcs._finite(b) else None})
    return {"reference_record": REFERENCE_RECORD, "corner_id": "tt_27c_3.30v",
            "point": {"c_uf": 1.0, "esr_ohm": 0.01}, "comparison": cmp}


def fmt(v, nd=3) -> str:
    return "—" if v is None else f"{v:.{nd}f}"


def render_md(rec: dict) -> str:
    m = rec["manifest"]
    L = [f"# PSRR C_eff x ESR reduced sweep — `{rec['record_id']}`", ""]
    L += [
        f"- **Evidence kind**: `{rec['evidence_kind']}` (issue #314, Phase 1; a sampled-grid "
        "characterization, not a 45-corner campaign record and not a spec verdict)",
        f"- **Timestamp**: {rec['timestamp']}",
        f"- **Git**: `{rec['git']['sha']}` on `{rec['git']['branch']}`"
        + (" (dirty tree)" if rec["git"]["dirty"] else ""),
        f"- **Manifest**: `{m['path']}` (sha256 `{m['sha256'][:16]}…`)",
        f"- **Testbench**: `sim/psrr-dc/testbench/tb_psrr_dc.sch`, netlist snapshot "
        f"`sim/psrr-dc/netlist-snapshots/{rec['record_id']}.spice` (with the added `CDIR` branch)",
        f"- **PDK**: {rec['pdk']['variant']} @ `{rec['pdk']['installed_commit']}` "
        f"(pin `{rec['pdk']['pin']}`, matches: {rec['pdk']['matches_pin']})",
        f"- **Execution**: `klt sim --backend {rec['backend']}`, one request per corner",
        "",
        "## Execution backend", "",
        "| corner | job id | reported backend | engine | klt | klt PDK names pin | corner status |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in rec["execution"]:
        L.append(f"| `{e['corner_id']}` | `{e.get('job_id')}` | {e.get('reported_backend')} | "
                 f"{e.get('engine')} {e.get('engine_version')} | {e.get('klt_version')} | "
                 f"{e.get('klt_pdk_names_pin')} | {e.get('klt_corner_status')} |")
    L += ["", "## Results (dB; VOUT of the seeded operating point in V)", "",
          "| corner | C_eff (uF) | ESR (ohm) | 1k/1mA | 100k/1mA | 1k/50mA | 100k/50mA | "
          "VOUT 1mA | VOUT 50mA | ok |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rec["results"]:
        mm = r["metrics"]
        L.append(
            f"| `{r['corner_id']}` | {r['c_uf']:g} | {r['esr_ohm']:g} | "
            + " | ".join(fmt(mm.get(k)) for k in m["metrics"])
            + f" | {fmt(r['vseed_v'].get('1ma'), 4)} | {fmt(r['vseed_v'].get('50ma'), 4)} | "
            + ("yes" if r["ok"] else "NO: " + "; ".join(r["reasons"])) + " |")
    L += ["", "## Worst sampled point per sub-metric (fixed selection rule)", "",
          f"Rule: {m['selection_rule']}", "",
          "| sub-metric | worst point (C_eff, ESR) | PSRR (dB) | at corner | tied points | missing cells |",
          "|---|---|---|---|---|---|"]
    for name in m["metrics"]:
        s = rec["selection"][name]
        f = s["finding"]
        if f is None:
            L.append(f"| `{name}` | **no finding** | — | — | — | {len(s['missing'])} |")
        else:
            L.append(f"| `{name}` | {f['c_uf']:g} uF, {f['esr_ohm']:g} ohm | {f['psrr_db']:.3f} | "
                     f"`{f['corner_id']}` | {len(f['tied_points'])} | 0 |")
    L += ["", "## Order-independence check", "",
          f"The point {tuple(m['independence_check'])} was re-run as the last point of every "
          f"corner's deck; values must be identical (|delta| <= {m['independence_tol_db']:g} dB).", "",
          f"All identical: **{rec['independence']['all_identical']}** "
          f"({len(rec['independence']['rows'])} comparisons).", ""]
    for row in rec["independence"]["rows"]:
        if not row["identical"]:
            L.append(f"- MISMATCH `{row['corner_id']}` `{row['metric']}`: first {row['first_db']} "
                     f"vs repeat {row['repeat_db']}")
    sc = rec.get("spot_check")
    L += ["## Spot check against the 45-corner record", ""]
    if sc:
        L.append(f"Nominal point (1 uF / 10 mOhm) at `{sc['corner_id']}` vs record "
                 f"`{sc['reference_record']}`:")
        L.append("")
        for c in sc["comparison"]:
            L.append(f"- `{c['metric']}`: {fmt(c['this_db'], 4)} vs {fmt(c['reference_db'], 4)} "
                     f"(delta {fmt(c['delta_db'], 4)} dB)")
    L += ["", "## Solver diagnostics (deck-level, per corner)", ""]
    for cid, d in rec["solver_diagnostics"].items():
        L.append(f"- `{cid}`: {d or 'none detected'}")
    L += ["", "## What this record does and does not show", ""]
    L += [f"- {line}" for line in rec["limits_of_claim"]]
    L += ["", "Generated by `sim/bin/psrr-cap-sweep-run.py`. Append-only evidence: never edited "
          "after creation; a correction mints a new record.", ""]
    return "\n".join(L)


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--backend", choices=["batch", "local"], default="batch")
    ap.add_argument("--corner", action="append", default=[],
                    help="restrict to this corner id (e.g. tt_27c_3.30v); repeatable")
    ap.add_argument("--dry-run", action="store_true", help="write requests, run nothing")
    ap.add_argument("--no-write", action="store_true", help="run but mint no record")
    ap.add_argument("--timeout", type=int, default=3600, help="per-corner timeout_s in the request")
    ap.add_argument("--allow-pdk-mismatch", action="store_true")
    return ap.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest = pcs.load_manifest(MANIFEST)
    exp = json.loads((EXP_DIR / "experiment.json").read_text())
    corners = [tuple(c) for c in manifest["corners"]]
    if args.corner:
        unknown = set(args.corner) - {pcs.corner_key(c) for c in corners}
        if unknown:
            raise HarnessError(f"unknown corner(s): {sorted(unknown)}")
        corners = [c for c in corners if pcs.corner_key(c) in args.corner]
    if args.backend == "local" and len(corners) != 1 and not args.dry_run:
        raise HarnessError("--backend local runs exactly ONE corner (single-corner spot check); "
                           "the multi-corner grid goes to the batch fleet")
    full = len(corners) == len(manifest["corners"])
    write = full and args.backend == "batch" and not args.no_write and not args.dry_run

    pin = cr.load_pin()
    pdk = cr.resolve_pdk(pin)
    git = cr.git_state()
    now = datetime.now(timezone.utc)
    record_id = f"{now:%Y%m%d}-{now:%H%M%S}-{git['sha']}"
    run_dir = (cr.BUILD_DIR / "psrr-cap-sweep" / record_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    if write:
        reserve_record_id(cr.BUILD_DIR, EXP_DIR.name, record_id, HarnessError)

    netlist = cr.netlist_with_xschem(EXP_DIR / "testbench" / "tb_psrr_dc.sch", run_dir / "xschem", pdk)
    body = pcs.add_direct_cap(cr.netlist_body(netlist))
    options = list((exp.get("deck") or {}).get("options") or [])
    init = cr.spiceinit_lines()
    lib_rel = str(pdk.lib_file.relative_to(pdk.dir))

    prepared = []
    for c in corners:
        cid = pcs.corner_key(c)
        npath = run_dir / f"{cid}.spice"
        npath.write_text(corner_netlist(body, c[2], options))
        req = pcs.build_request(manifest, str(npath), pdk.variant, lib_rel, c[0], c[1], args.timeout, init)
        rpath = run_dir / f"{cid}.request.json"
        rpath.write_text(json.dumps(req, indent=2, sort_keys=True) + "\n")
        prepared.append((c, cid, npath, rpath, req))
    print(f"run dir: {run_dir}")
    print(f"{len(prepared)} request(s), {len(prepared[0][4]['analysis_steps'])} steps each, backend {args.backend}")
    if args.dry_run:
        print("dry run: nothing submitted, nothing written under sim/psrr-dc/")
        return 0

    results, repeats, execution, diags, responses = [], [], [], {}, {}
    for c, cid, npath, rpath, req in prepared:
        outdir = run_dir / "klt-out" / cid
        print(f"submitting {cid} ({args.backend}) ...", flush=True)
        try:
            response, meta = run_klt(rpath, outdir, args.backend, pdk.root)
            assert_klt_read_the_pinned_pdk(response, pdk, pin, args.allow_pdk_mismatch, error_cls=HarnessError)
        except HarnessError as exc:
            done = [e["job_id"] for e in execution]
            raise HarnessError(f"{exc}\n  corner {cid} failed: NO record written, NO local fallback, "
                               f"no resubmission; earlier job ids: {done or 'none'}") from exc
        (outdir / "response.json").write_text(json.dumps(response, indent=2, sort_keys=True) + "\n")
        responses[cid] = response
        rcs = [x for x in response["corners"] if isinstance(x, dict)]
        if len(rcs) != 1 or rcs[0].get("process") != c[0] or float(rcs[0].get("temperature_c", "nan")) != float(c[1]):
            raise HarnessError(f"{cid}: response does not hold exactly the requested corner; no record")
        rc = rcs[0]
        res, rep = pcs.parse_corner(manifest, cid, rc)
        results += res
        repeats += rep
        log = engine_log(rc, outdir)
        diags[cid] = None if log is None else cr.detect_solver_diagnostic(log)
        if log is None:
            diags[cid] = "engine log not retrieved"
        info = cr.batch_remote_info(response)
        execution.append({"corner_id": cid, **info, "returncode": meta["returncode"],
                          "job_ids_seen": meta["job_ids_seen"], "klt_corner_status": rc.get("status"),
                          "klt_pdk_names_pin": pin["open_pdks_commit"] in (info["pdk_version"] or ""),
                          "has_log": log is not None})
        print(f"  {cid}: klt status {rc.get('status')}, job {info.get('job_id')}, "
              f"ok cells {sum(r['ok'] for r in res)}/{len(res)}", flush=True)

    sel = pcs.select_worst(manifest, results) if full else None
    tol = manifest["independence_check"]["tol_db"]
    indep = pcs.independence_report(results, repeats, tol)
    summary = {
        "results": results, "repeats": repeats,
        "independence": {"all_identical": bool(indep) and all(r["identical"] for r in indep), "rows": indep},
        "selection": sel, "solver_diagnostics": diags, "spot_check": spot_check(results),
        "execution": execution,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"selection": sel, "independence_all_identical": summary["independence"]["all_identical"],
                      "spot_check": summary["spot_check"]}, indent=2))
    if not write:
        print(f"no record written (full={full}, backend={args.backend}, no_write={args.no_write}); "
              f"summary in {run_dir / 'summary.json'}")
        return 0

    # ---- mint the append-only record --------------------------------------
    mtext = MANIFEST.read_text()
    snap = EXP_DIR / "netlist-snapshots" / f"{record_id}.spice"
    write_new_text(snap, "\n".join(body) + "\n")
    for sub in ("klt-requests", "klt-responses", "klt-request-netlists"):
        (EXP_DIR / sub).mkdir(parents=True, exist_ok=True)
    corner_logs = EXP_DIR / "corners" / record_id
    corner_logs.mkdir(parents=True, exist_ok=False)
    for c, cid, npath, rpath, req in prepared:
        write_new_text(EXP_DIR / "klt-request-netlists" / f"{record_id}.{cid}.spice", npath.read_text())
        write_new_text(EXP_DIR / "klt-requests" / f"{record_id}.{cid}.json", rpath.read_text())
        write_new_text(EXP_DIR / "klt-responses" / f"{record_id}.{cid}.json",
                       json.dumps(responses[cid], indent=2, sort_keys=True) + "\n")
        log = engine_log(responses[cid]["corners"][0], run_dir / "klt-out" / cid)
        if log is not None:
            write_new_text(corner_logs / f"{cid}.log", log)
    limits = [
        "The grid SAMPLES the DR-002 window: 3 C_eff x 3 ESR points at 3 corners (the psrr-dc "
        "quick_subset). It cannot prove the continuous-window worst case or the all-45-corner worst "
        "case; an interior C_eff/ESR value or another PVT corner may be worse.",
        "The worst sampled point is an evidence finding about this grid only. Which capacitor "
        "condition the PSRR row binds at is a specification decision (Phase 2 of #314, a decision "
        "record), not decided here.",
        "No threshold and no spec/target-spec.md row is touched; the bounds quoted by experiment.json "
        "are not graded here (this record carries no PASS/FAIL verdict).",
        "Solver diagnostics are deck-level (one ngspice log per corner covers all points); they are "
        "listed, not attributed to individual points.",
    ]
    record = {
        "record_id": record_id,
        "evidence_kind": "psrr-cap-esr-sweep",
        "evidence_kind_note": "reduced C_eff x ESR characterization for #314 Phase 1; not a campaign record",
        "issue": 314, "phase": 1,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git": git,
        "backend": args.backend,
        "manifest": {"path": str(MANIFEST.relative_to(REPO_ROOT)), "sha256": sha256_text(mtext),
                     "metrics": manifest["metrics"], "selection_rule": manifest["selection_rule"],
                     "independence_check": manifest["independence_check"]["point"],
                     "independence_tol_db": tol, "corners": manifest["corners"],
                     "c_eff_uf": manifest["c_eff_uf"], "esr_ohm": manifest["esr_ohm"]},
        "pdk": {"variant": pdk.variant, "installed_commit": pdk.installed_commit,
                "pin": pin["open_pdks_commit"], "matches_pin": pdk.matches_pin},
        "tools": cr.tool_versions(),
        "netlist_snapshot": str(snap.relative_to(REPO_ROOT)),
        "netlist_snapshot_sha256": sha256_text(snap.read_text()),
        "limits_of_claim": limits,
        **summary,
    }
    rj = EXP_DIR / "records" / f"{record_id}.json"
    write_new_text(rj, json.dumps(record, indent=2, sort_keys=True) + "\n")
    write_new_text(rj.with_suffix(".md"), render_md(record))
    print(f"record written: {rj.relative_to(REPO_ROOT)} (+ .md)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except HarnessError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
