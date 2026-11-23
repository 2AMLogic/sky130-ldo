#!/usr/bin/env python3
"""Issue #705 paired qualification campaign: baseline vs #692 rev2 candidate
over the startup, line-regulation and load-regulation benches.

Both DUTs run at ONE pinned production commit (recorded per leg in each
leg.json as source_commit, together with the sha256 of the raw baseline
netlist, the sha256 of the edited rev2 netlist, the overlay revision and the
PDK/tools provenance). The candidate is the re-based #357 overlay with its
REV[2] sizing, copied byte-identical from the #692 campaign directory
(candidate.py); the overlay invariants (check_candidate) are re-verified
against every bench netlist at leg-build time and recorded in runs/
verify-overlay/verification.json.

Bench routing follows the issue's implementation guidance verbatim: the three
corner benches go through their own validated batch adapters via
corner-run.py's batch backend (the #336 startup ramp-trace adapter -- one
scalar tran request per supply x leg with options.waveforms, the ramp traces
returned as waveform artifacts, rebuilt and graded locally by
ramp_monotonicity.py -- and the #379/#381 endpoint adapters), driven by
prepare_batch_requests/run_batch exactly like the #692 campaign driver. No
manifest, stimulus, measurement or limit is modified: the graded request shape
is the validated one, verbatim.

Evidence retention (startup legs): the ramp trace and the klt waveform
artifact of every (corner, leg) that is CLEAN -- vpk/vfloor in window, tset
reached, trace graded, no solver diagnostic, klt status completed -- are
dropped after grading and recorded by sha256 in retention.json; the flagged
conditions the issue names (a latch or VOUT above VIN, an invalid solve) keep
their rebuilt trace.dat, the raw waveform artifact and the engine log. All
per-corner .meas values, ramp drawdowns and verdicts stay in leg.json either
way, so expected-vs-observed counts remain auditable. Line/load endpoint legs
keep everything klt returned (no waveform artifacts, small logs).

Modes (one batch submit set each; see commands.sh for the as-executed order):

  verify-overlay   netlist all four benches, apply rev2, check the invariants,
                   write runs/verify-overlay/verification.json; submits nothing
  startup-base / startup-cand    full 45-corner x 12-leg startup grid
  line-base   / line-cand        full 45-corner line-regulation endpoints
  load-base   / load-cand        full 45-corner load-regulation endpoints
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parents[2]
REPO = SIM.parent
sys.path.insert(0, str(SIM / "bin"))
sys.path.insert(0, str(HERE))
import _probe_common as pc  # noqa: E402

cr = pc.load_corner_run()
import candidate as cand  # noqa: E402

REV = 2
BENCHES = ("startup", "line-regulation", "load-regulation")
DROPOUT_DIR = SIM / "dropout-vs-load" / "diagnostics" / "issue-692-20261120-235900"


def full_matrix(exp) -> list:
    c = exp.raw["corners"]
    return [cr.Corner(p, float(t), float(v)) for p in c["process"]
            for t in c["temperature_c"] for v in c["supply_v"]]


def bench_body(exp_slug: str, pdk) -> tuple[list[str], dict]:
    """Netlist body of the bench (+ provenance dict with raw/edited text)."""
    exp = cr.load_experiment(SIM / exp_slug)
    with tempfile.TemporaryDirectory(prefix="i705-nl-") as nl:
        net = cr.netlist_with_xschem(exp.schematic, Path(nl), pdk)
        raw = "\n".join(cr.netlist_body(net)) + "\n"
    return raw, {"exp": exp, "raw": raw}


def variant_body(exp_slug: str, pdk, variant: str) -> tuple[list[str], dict]:
    raw, ctx = bench_body(exp_slug, pdk)
    if variant == "cand":
        edited, notes = cand.apply_candidate(raw, REV)
        problems = cand.check_candidate(raw, edited)
        if problems:
            raise SystemExit("candidate invariant check failed: " + "; ".join(problems))
    else:
        edited, notes, problems = raw, [], []
    body = edited.splitlines()
    return body, {"exp": ctx["exp"], "raw": raw, "edited": edited,
                  "notes": notes, "problems": problems}


def provenance_block(exp, pdk, prov: dict, variant: str) -> dict:
    pin = cr.load_pin()
    return {
        "source_commit": pc.git_provenance(REPO),
        "git_state": cr.git_state(),
        "variant": variant,
        "candidate_rev": REV if variant == "cand" else None,
        "overlay_source": str(DROPOUT_DIR.relative_to(REPO) / "candidate.py"),
        "candidate_py_sha256": pc.sha((HERE / "candidate.py").read_bytes()),
        "netlist_raw_sha256": pc.sha(prov["raw"].encode()),
        "netlist_edited_sha256": pc.sha(prov["edited"].encode()),
        "edit_notes": prov["notes"],
        "candidate_invariant_problems": prov["problems"],
        "dut_sch_sha256": pc.sha((REPO / "design" / "ldo_3v3in_1v8out.sch").read_bytes()),
        "testbench_sha256": pc.sha(exp.schematic.read_bytes()),
        "experiment_json_sha256": pc.sha((SIM / exp.slug / "experiment.json").read_bytes()),
        "pdk": {"open_pdks_commit": pdk.installed_commit, "matches_pin": pdk.matches_pin,
                "lib_sha256": pc.sha(Path(pdk.lib_file).read_bytes())},
        "tools": cr.tool_versions(),
        "pin": {"open_pdks_commit": pin["open_pdks_commit"]},
    }


# ------------------------------------------------------------- retention
def _meas(result: dict, name: str) -> dict | None:
    for c in result.get("measurements", []):
        if c["name"] == name:
            return c
    return None


def flagged_reasons(result: dict) -> list[str]:
    """Why this (merged) startup corner keeps its trace/artifacts: the issue's
    named retention classes -- a bound failure on peak/floor (the latch /
    VOUT-above-VIN family), a ramp that never entered the window, a
    structurally invalid leg (missing trace/log/measurement), or an errored
    klt corner. A strict-monotonicity drawdown failure alone is NOT in these
    classes (its verdict and drawdown are recorded in leg.json; the historic
    0 V-tolerance failure mode is every leg of every corner, both DUTs -- see
    sim/startup/records/20261117-221657-efb6bd6b), and neither is a cold-start
    `singular matrix` warning on a corner whose measurements all came back and
    graded (the diagnostic text stays in leg.json and the engine log stays in
    klt-out; the historic record carries the same warnings as text)."""
    why: list[str] = []
    vpk, vfloor, tramp = _meas(result, "vpk_v"), _meas(result, "vfloor_v"), _meas(result, "tramp_ms")
    if vpk is not None and not vpk["pass"]:
        why.append(f"vpk_v bound failure ({vpk['value']!r} V)")
    if vfloor is not None and not vfloor["pass"]:
        why.append(f"vfloor_v bound failure ({vfloor['value']!r} V)")
    if tramp is not None and tramp["value"] is None:
        why.append("tramp_ms missing (never entered the window)")
    for tr in result.get("ramp_monotonicity") or []:
        st = str(tr.get("status", "")).upper()
        if st not in ("FAIL", "PASS"):
            why.append(f"leg {tr.get('leg')}: ramp condition not evaluated ("
                       + "; ".join(tr.get("reasons") or ["no reasons"]) + ")")
    if result.get("batch_reasons"):
        structural = [str(r) for r in result["batch_reasons"]
                      if "solver diagnostic" not in str(r)]
        why.extend(structural)
    if result.get("klt_status") not in ("pass", "fail") and not isinstance(result.get("klt_status"), list):
        why.append(f"klt corner status {result.get('klt_status')!r}")
    return why


def apply_startup_retention(run_dir: Path, results: list[dict], execution: dict) -> dict:
    """Drop the clean corners' waveform artifacts + rebuilt traces; keep the
    flagged ones. Every dropped file is recorded by sha256 so the
    expected-vs-observed accounting stays complete."""
    flagged = {}
    for r in results:
        why = flagged_reasons(r)
        if why:
            flagged[r["corner_id"]] = why
    kept, dropped = [], []
    trace_entries = execution.get("traces") or {}
    for corner_id, entries in trace_entries.items():
        keep = corner_id in flagged
        for e in entries:
            tpath = Path(e["path"])
            if not tpath.exists():
                continue
            if keep:
                kept.append({"corner": corner_id, "file": e["file"],
                             "sha256": pc.sha(tpath.read_bytes()),
                             "reasons": flagged[corner_id]})
                continue
            dropped.append({"corner": corner_id, "file": e["file"],
                            "sha256": pc.sha(tpath.read_bytes())})
            tpath.unlink()
    # the raw klt waveform JSON artifacts mirror the rebuilt traces; map each
    # response entry back to its harness corner by (process, temp, supply):
    # after merge_leg_parts a result's klt_request is a LIST of group keys,
    # so string comparison against one group name never matches
    corner_index = {}
    for r in results:
        corner_index[(str(r["process"]), float(r["temperature_c"]), float(r["supply_v"]))] = r["corner_id"]
    art_dropped = 0
    raw_removed = 0
    for resp_path in sorted(run_dir.glob("klt-out/*/response.json")):
        resp = json.loads(resp_path.read_text())
        outdir = resp_path.parent
        m = re.match(r"v([0-9.]+)", resp_path.parent.name)
        supply = float(m.group(1)) if m else None
        for rc in resp.get("corners", []):
            if not isinstance(rc, dict) or not isinstance(rc.get("process"), str):
                continue
            key = corner_index.get((rc["process"], float(rc.get("temperature_c")), supply))
            art = rc.get("artifacts") or {}
            wf_ref = art.get("waveform") if isinstance(art, dict) else None
            if isinstance(wf_ref, str) and wf_ref:
                wp = Path(wf_ref)
                if not wp.is_absolute():
                    wp = outdir / wp
                if wp.exists() and key not in flagged:
                    # clean corner: the trace it carried was graded and dropped
                    dropped.append({"corner": key, "file": wp.name, "sha256": pc.sha(wp.read_bytes())})
                    wp.unlink()
                    art_dropped += 1
            # the ngspice rawfile behind the waveform (gitignored, transient):
            # kept only for the trace-retained corners, deleted elsewhere.
            # klt's per-corner dir is named `<proc>_novdd_<T>C` with negative
            # temperatures spelled `n40`, so parse rather than reconstruct.
            for raw in outdir.glob("*/waveform.raw"):
                dname = raw.parent.name
                m2 = re.fullmatch(r"(\w+)_novdd_(n?\d+)C", dname)
                if not m2:
                    continue
                rk = corner_index.get(
                    (m2.group(1), float(m2.group(2).replace("n", "-")), supply))
                if rk in flagged:
                    continue
                raw.unlink()
                raw_removed += 1
    rec = {
        "policy": "clean (corner,leg) waveform artifacts and rebuilt traces are dropped after "
                  "grading; flagged conditions (vpk/vfloor bound failure, tset missing, invalid "
                  "leg, errored corner) keep trace + artifact + log; every "
                  "dropped file is listed by sha256",
        "flagged_corners": flagged,
        "kept_traces": kept,
        "dropped_files": dropped,
        "counts": {"flagged_corners": len(flagged), "kept_traces": len(kept),
                   "dropped_files": len(dropped), "dropped_waveform_artifacts": art_dropped,
                   "removed_transient_rawfiles": raw_removed},
    }
    (run_dir / "retention.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    return rec


# ------------------------------------------------------------- legs
SLUGS = {"startup": "startup", "line": "line-regulation", "load": "load-regulation"}


def run_leg(mode: str, timeout: int, allow_pdk_mismatch: bool) -> dict:
    bench, variant = mode.rsplit("-", 1)
    exp_slug = SLUGS[bench]
    run_dir = HERE / "runs" / mode
    if run_dir.exists():
        raise SystemExit(f"{run_dir} exists: evidence is append-only")
    run_dir.mkdir(parents=True)
    pdk = cr.resolve_pdk(cr.load_pin())
    pin = cr.load_pin()
    exp = cr.load_experiment(SIM / exp_slug)
    body, prov = variant_body(exp_slug, pdk, variant)
    (run_dir / "netlist.spice").write_text("\n".join(body) + "\n")
    if variant == "cand":
        diff = "".join(difflib.unified_diff(
            prov["raw"].splitlines(True), prov["edited"].splitlines(True),
            "netlist.raw.spice", "netlist.edited.spice"))
        (run_dir / "netlist.diff").write_text(diff)
    matrix = full_matrix(exp)
    prepared = cr.prepare_batch_requests(exp, pdk, matrix, False, body, run_dir, timeout)
    results, logs, execution = cr.run_batch(exp, pdk, pin, prepared, matrix, run_dir,
                                            timeout, allow_pdk_mismatch)
    retention = None
    if exp_slug == "startup":
        retention = apply_startup_retention(run_dir, results, execution)
    rec = {
        "leg": mode, "experiment": exp_slug, "variant": variant,
        "candidate_rev": REV if variant == "cand" else None,
        "matrix": [[c.process, c.temp_c, c.supply_v] for c in matrix],
        "corner_ids": [c.id for c in matrix],
        "results": results, "execution": execution,
        "provenance": provenance_block(exp, pdk, prov, variant),
        **({"retention": {"counts": retention["counts"],
                          "flagged_corners": list(retention["flagged_corners"])}}
           if retention else {}),
    }
    (run_dir / "leg.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    (run_dir / "logs").mkdir(exist_ok=True)
    for cid, text in logs.items():
        safe = cid.replace("/", "_")
        (run_dir / "logs" / f"{safe}.log").write_text(text)
    n_pass = sum(1 for r in results if r["pass"])
    print(f"[{mode}] {n_pass}/{len(results)} corners harness-pass; "
          f"jobs: {', '.join(str(r.get('job_id')) for r in execution['requests'])}")
    return rec


def verify_overlay() -> None:
    """Re-based overlay verification over every bench this issue touches
    (startup, line-regulation, load-regulation AND mc-output-accuracy),
    recorded as evidence; submits nothing."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("mc_run", SIM / "bin" / "mc-run.py")
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    pdk = cr.resolve_pdk(cr.load_pin())
    out = HERE / "runs" / "verify-overlay"
    out.mkdir(parents=True, exist_ok=True)
    report = {"source_commit": pc.git_provenance(REPO), "rev": REV,
              "candidate_py_sha256": pc.sha((HERE / "candidate.py").read_bytes()),
              "benches": {}}
    for slug in (*BENCHES, "mc-output-accuracy"):
        if slug == "mc-output-accuracy":
            exp = mc.load_mc_experiment(SIM / slug)
            with tempfile.TemporaryDirectory(prefix="i705-nl-") as nl:
                net = cr.netlist_with_xschem(exp["_schematic"], Path(nl), pdk)
                raw = "\n".join(mc.build_klt_netlist(exp, net)) + "\n"
        else:
            exp = cr.load_experiment(SIM / slug)
            with tempfile.TemporaryDirectory(prefix="i705-nl-") as nl:
                net = cr.netlist_with_xschem(exp.schematic, Path(nl), pdk)
                raw = "\n".join(cr.netlist_body(net)) + "\n"
        edited, notes = cand.apply_candidate(raw, REV)
        problems = cand.check_candidate(raw, edited)
        report["benches"][slug] = {
            "netlist_raw_sha256": pc.sha(raw.encode()),
            "netlist_edited_sha256": pc.sha(edited.encode()),
            "cards_added": len(notes), "edit_notes": notes,
            "invariant_problems": problems,
        }
        print(f"{slug}: problems={problems}")
    ok = all(not b["invariant_problems"] for b in report["benches"].values())
    report["all_benches_clean"] = ok
    (out / "verification.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    if not ok:
        raise SystemExit("overlay invariants failed on at least one bench")
    print(f"verify-overlay: all benches clean at {report['source_commit']}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["verify-overlay", "startup-base", "startup-cand",
                                     "line-base", "line-cand", "load-base", "load-cand",
                                     "re-retain"])
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--allow-pdk-mismatch", action="store_true")
    ap.add_argument("--leg", help="re-retain: the leg directory name under runs/")
    a = ap.parse_args(argv)
    if a.mode == "verify-overlay":
        verify_overlay()
        return
    if a.mode == "re-retain":
        if not a.leg:
            raise SystemExit("re-retain needs --leg <name>")
        run_dir = HERE / "runs" / a.leg
        rec = json.loads((run_dir / "leg.json").read_text())
        ret = apply_startup_retention(run_dir, rec["results"], rec["execution"])
        rec["retention"] = {"counts": ret["counts"],
                            "flagged_corners": list(ret["flagged_corners"])}
        (run_dir / "leg.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
        print(f"[re-retain {a.leg}] {ret['counts']}")
        return
    run_leg(a.mode, a.timeout, a.allow_pdk_mismatch)


if __name__ == "__main__":
    main()
