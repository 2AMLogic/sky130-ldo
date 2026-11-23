#!/usr/bin/env python3
"""Issue #706 paired thermal trip/reset re-bisection: base vs #357 rev2.

Drives the bench's own DR-005 hysteresis procedure (`sim/thermal/run_hysteresis.py`
+ `sim/bin/batch_thermal_staircase.py`, issues #511/#541) over its full 15-point
process x supply grid, for the committed production DUT and for the rev2
candidate (`apply_candidate(raw, 2)`, this directory's candidate.py). The
staircase loop, point records, bisection planner, dependent-point round and
refusal handling are run_hysteresis.py's own, imported and reused verbatim;
this driver only swaps in the variant netlist body and writes honest provenance
(issue, command line, pairing) into the result -- which is why the loop is
replicated here instead of calling `run_hysteresis.main()` (its result.json
hardcodes issue 541 and its own command line).

Evidence is append-only under `sim/thermal/hysteresis/<stamp>-<sha>-i706-paired-<variant>/`
(the bench's own convention), never overwriting an earlier record; `--resume`
continues an interrupted record. There is NO local fallback: a capacity refusal
is recorded in refusals.jsonl and the run exits non-zero (re-run with --resume).
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parents[2]
REPO = SIM.parent
THERMAL = SIM / "thermal"
sys.path.insert(0, str(SIM / "bin"))
sys.path.insert(0, str(THERMAL))
sys.path.insert(0, str(HERE))
import _probe_common as pc  # noqa: E402

cr = pc.load_corner_run()
import run_hysteresis as rh  # noqa: E402
import batch_thermal_staircase as bts  # noqa: E402
import candidate as cand  # noqa: E402


def variant_body(pdk, variant: str, rev: int) -> tuple[list[str], dict]:
    """The staircase body (testbench netlisted with `klt netlist`, IC_SEED
    `.nodeset` dropped as run_hysteresis does), with the variant applied."""
    with tempfile.TemporaryDirectory(prefix="i706-th-nl-") as nl:
        body, n_expr = rh.netlist_body_for_staircase(pdk, Path(nl))
    raw = "\n".join(body) + "\n"
    notes, problems = [], []
    if variant == "cand":
        edited, notes = cand.apply_candidate(raw, rev)
        problems = cand.check_candidate(raw, edited)
        if problems:
            raise SystemExit("candidate invariant check failed: " + "; ".join(problems))
        body = edited.splitlines()
    return body, {"raw": raw, "edited": "\n".join(body) + "\n", "notes": notes,
                  "problems": problems, "n_expr": n_expr}


def append_jsonl(path: Path, obj: dict) -> None:
    with path.open("a") as fh:
        fh.write(json.dumps(obj, sort_keys=True) + "\n")


def run_variant(args, pdk, pin, git, variant: str, rev: int) -> int:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    rec_id = f"{stamp}-{git['sha'][:8]}-i706-paired-{variant}"
    out = args.resume or (THERMAL / "hysteresis" / rec_id)
    if args.resume:
        rec_id = out.name
        if (out / "result.json").exists():
            raise SystemExit(f"{out} is already complete; evidence is append-only")
    else:
        out.mkdir(parents=True, exist_ok=False)
    (out / "points").mkdir(exist_ok=True)

    body, prov = variant_body(pdk, variant, rev)
    if args.resume:
        if (out / "netlist.spice").read_text() != "\n".join(body) + "\n":
            raise SystemExit("netlist differs from the record being resumed; start a new record")
    else:
        (out / "netlist.spice").write_text("\n".join(body) + "\n")
        if variant == "cand":
            (out / "netlist.diff").write_text("".join(difflib.unified_diff(
                prov["raw"].splitlines(True), prov["edited"].splitlines(True),
                "netlist.raw.spice", "netlist.edited.spice")))

    corners = rh.parse_corners(args.corners)
    work = Path(tempfile.mkdtemp(prefix="thermal-batch-"))
    model = {"pdk": pdk.variant, "lib": str(pdk.lib_file.relative_to(pdk.dir))}
    init = cr.spiceinit_lines()
    klt = rh.klt_binary("run the paired thermal staircase")
    failed_pts: set = set()
    corner_err: dict[tuple, str] = {}
    refused = False
    rnd = 0
    while True:
        points = rh.load_points(out)
        todo = []
        for proc, vsup in corners:
            for scen in bts.SCENARIOS:
                if (proc, vsup, scen) in corner_err:
                    continue
                res = {k[3]: v["held"] for k, v in points.items() if k[:3] == (proc, vsup, scen)}
                p = bts.plan(res, scen, args.tol, bts.grid_for(proc, args.grid_top_c))
                if "error" in p:
                    corner_err[(proc, vsup, scen)] = p["error"]
                elif "pending" in p:
                    if any((proc, vsup, scen, T) in failed_pts for T in p["pending"]):
                        corner_err[(proc, vsup, scen)] = "a point failed (see failures.jsonl)"
                    else:
                        todo.append((proc, vsup, scen, p["pending"]))
        if not todo:
            for proc, vsup in corners:
                br = rh.corner_brackets(points, proc, vsup, args.tol, args.grid_top_c)
                need: dict[str, list] = {}
                for lab, T in (bts.dependent_points(*br) if br else []):
                    if rh.above_bound(proc, T, args.grid_top_c) and (proc, vsup, lab, T) not in points:
                        continue
                    if (proc, vsup, lab, T) not in points and (proc, vsup, lab, T) not in failed_pts:
                        need.setdefault(lab, []).append(T)
                todo += [(proc, vsup, lab, Ts) for lab, Ts in need.items()]
        if not todo:
            break
        rnd += 1
        rdir = work / f"round{rnd:02d}"
        rdir.mkdir()
        reqs = []
        for proc, vsup, scen, temps in todo:
            name = f"{proc}_{vsup:.2f}V_{scen}"
            nl = rdir / f"{name}.spice"
            prm = bts.scenario_params(scen)
            nl.write_text("\n".join(bts.request_netlist(body, vsup, prm["ix_amp"], prm["en_dip"])) + "\n")
            req = bts.build_request(nl, proc, temps, model, init, 900, args.capacity_wait_s, prm["cards"])
            rp = rdir / f"{name}.json"
            rp.write_text(json.dumps(req, indent=2) + "\n")
            reqs.append((name, rp, proc, vsup, scen, temps))
        print(f"[{variant} round {rnd}] {len(reqs)} request(s), "
              f"{sum(len(r[5]) for r in reqs)} point(s)", flush=True)
        cmd = [klt, "sim", "--batch-set", *[str(r[1]) for r in reqs], "--max-in-flight",
               str(args.max_in_flight), "--capacity-retries", str(args.capacity_retries),
               "-o", str(rdir / "out"), "--format", "json"]
        env = dict(os.environ, PDK_ROOT=str(pdk.root))
        proc_ = subprocess.run(cmd, capture_output=True, text=True, env=env,
                               stdin=subprocess.DEVNULL)
        try:
            env_json = json.loads(proc_.stdout)
        except json.JSONDecodeError:
            append_jsonl(out / "failures.jsonl",
                         {"round": rnd, "error": "klt sim --batch-set produced no JSON",
                          "rc": proc_.returncode, "stderr": proc_.stderr[-1500:]})
            print("klt sim --batch-set produced no JSON; NOT falling back to local", file=sys.stderr)
            return 2
        by_req = {Path(e["request"]).stem: e for e in env_json.get("requests", [])}
        for name, rp, proc, vsup, scen, temps in reqs:
            e = by_req.get(name)
            err = (e or {}).get("error")
            code = (err or {}).get("code") if isinstance(err, dict) else None
            if e is None or err or not e.get("report"):
                refused = refused or (code in ("batch_no_capacity", "batch_concurrency_cap"))
                append_jsonl(out / "refusals.jsonl", {"round": rnd, "request": name, "code": code,
                                                      "error": err, "job_ids": (e or {}).get("job_ids")})
                for T in temps:
                    failed_pts.add((proc, vsup, scen, T))
                continue
            rpt = Path(e["report"])
            n, fails = rh.ingest_report(out, rpt.parent, json.loads(rpt.read_text()), proc, vsup,
                                        scen, temps, pdk, pin, name)
            for T in temps:
                if not rh.point_path(out, proc, vsup, scen, T).exists():
                    failed_pts.add((proc, vsup, scen, T))
            for f in fails:
                append_jsonl(out / "failures.jsonl", {"round": rnd, "failure": f})
                print(f"  FAIL {f}", file=sys.stderr)
        if refused:
            print("capacity refusal(s) recorded in refusals.jsonl; stopping (no local fallback); "
                  f"re-run with --resume {out}", file=sys.stderr)
            return 3
    shutil.rmtree(work, ignore_errors=True)

    points = rh.load_points(out)
    per_corner = {}
    for proc, vsup in corners:
        c = {}
        for scen, key in (("hot", "t_reset_falling_c"), ("cold_exc", "t_trip_rising_c")):
            res = {k[3]: v["held"] for k, v in points.items() if k[:3] == (proc, vsup, scen)}
            p = bts.plan(res, scen, args.tol, bts.grid_for(proc, args.grid_top_c))
            if p.get("done"):
                lo, hi = p["bracket"]
                c[key] = {"bracket": [lo, hi], "midpoint": (lo + hi) / 2}
            else:
                c[key] = {"error": corner_err.get((proc, vsup, scen)) or str(p)}
        if "midpoint" in c["t_reset_falling_c"] and "midpoint" in c["t_trip_rising_c"]:
            c["hysteresis_c"] = {
                "midpoint": c["t_trip_rising_c"]["midpoint"] - c["t_reset_falling_c"]["midpoint"],
                "min": c["t_trip_rising_c"]["bracket"][0] - c["t_reset_falling_c"]["bracket"][1],
                "max": c["t_trip_rising_c"]["bracket"][1] - c["t_reset_falling_c"]["bracket"][0]}
        br = rh.corner_brackets(points, proc, vsup, args.tol, args.grid_top_c)
        if br is None:
            c["dependent_points"] = {"skipped": "bracket missing or errored"}
        else:
            want = bts.dependent_points(*br)
            mine = {(k[2], k[3]): v for k, v in points.items() if k[:2] == (proc, vsup)}
            missing = [f"{lab}@{T:g}C" for lab, T in want
                       if (lab, T) not in mine and not rh.above_bound(proc, T, args.grid_top_c)]
            beyond = [f"{lab}@{T:g}C" for lab, T in want
                      if (lab, T) not in mine and rh.above_bound(proc, T, args.grid_top_c)]
            c["dependent_points"] = {"planned": len(want), "missing": missing}
            if beyond:
                c["dependent_points"]["beyond_grid_top_not_run"] = beyond
            c["cold_start_by_temp"] = {f"{T:g}": mine[("cold", T)]["cold_start_tripped"]
                                       for lab, T in want if lab == "cold" and ("cold", T) in mine}
            c["en_reenable_by_temp"] = {
                f"{T:g}": {"tripped_before_dip": mine[("en", T)]["hold_tripped"],
                           "ts_cmp_while_en_low_v": mine[("en", T)]["ts_cmp_while_en_low_v"],
                           "tripped_after_reenable": mine[("en", T)]["after_en_reenable_tripped"]}
                for lab, T in want if lab == "en" and ("en", T) in mine}
            c["amplitude_robustness"] = {
                f"{lab}@{T:g}C": mine[(lab, T)]["held"]
                for lab, T in want if lab not in ("cold", "en") and (lab, T) in mine}
        per_corner[f"{proc}_{vsup:.2f}V"] = c
    ok = all("error" not in v for c in per_corner.values()
             for v in (c["t_reset_falling_c"], c["t_trip_rising_c"])) and \
        all(not c["dependent_points"].get("skipped") and not c["dependent_points"].get("missing")
            for c in per_corner.values())
    result = {
        "record_id": rec_id, "issue": 706, "backend": "batch", "variant": variant,
        "candidate_rev": rev if variant == "cand" else None,
        "corners": per_corner, "bisection_tol_c": args.tol, "grid_top_c": args.grid_top_c,
        "n_points": len(points),
        "jobs": sorted({v["remote"]["job_id"] for v in points.values() if v["remote"].get("job_id")}),
        "complete": ok,
        "note": "issue #706 paired thermal trip/reset re-bisection on the bench's own DR-005 "
                "procedure (run_hysteresis.py / batch_thermal_staircase.py, issues #511/#541), "
                "reused verbatim; only the DUT body differs (variant above). Development "
                "evidence for the #702 rev2 adoption decision; states are recorded, no "
                "threshold is applied or relaxed.",
        "pairing": {
            "source_commit": pc.git_provenance(REPO),
            "driver_sha256": pc.sha(Path(__file__).read_bytes()),
            "candidate_py_sha256": pc.sha((HERE / "candidate.py").read_bytes()),
            "dut_sch_sha256": pc.sha((REPO / "design" / "ldo_3v3in_1v8out.sch").read_bytes()),
            "testbench_sha256": pc.sha((THERMAL / "testbench" / "tb_thermal_trip.sch").read_bytes()),
            "edit_notes": prov["notes"], "candidate_invariant_problems": prov["problems"],
            "xschem_expr_substitutions": prov["n_expr"],
        },
        "tools": cr.tool_versions(),
        "pdk": {"variant": pdk.variant, "installed_commit": pdk.installed_commit,
                "pinned_commit": pin["open_pdks_commit"], "lib": str(pdk.lib_file)},
        "repo": git,
        "command": "python3 sim/iq/diagnostics/issue-706/thermal_pair.py "
                   + " ".join(sys.argv[1:]),
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    text = json.dumps(result, indent=2) + "\n"
    (out / ("result.json" if ok else
            f"result-incomplete-{dt.datetime.now(dt.timezone.utc):%H%M%S}.json")).write_text(text)
    for k, c in per_corner.items():
        print(k, {a: b.get("midpoint", b.get("error")) for a, b in c.items()
                  if a in ("t_reset_falling_c", "t_trip_rising_c")})
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=("base", "cand"), required=True)
    ap.add_argument("--rev", type=int, default=2)
    ap.add_argument("--tol", type=float, default=0.3125)
    ap.add_argument("--corners", default="")
    ap.add_argument("--resume", type=Path, default=None)
    ap.add_argument("--max-in-flight", type=int, default=4)
    ap.add_argument("--capacity-retries", type=int, default=2)
    ap.add_argument("--capacity-wait-s", type=int, default=1800)
    ap.add_argument("--grid-top", default="")
    args = ap.parse_args()
    args.grid_top_c = (dict((a, float(b)) for a, b in (x.split(":") for x in args.grid_top.split(",")))
                       if args.grid_top else dict(bts.GRID_TOP_C))
    pin = cr.load_pin()
    pdk = cr.resolve_pdk(pin)
    git = cr.git_state()
    return run_variant(args, pdk, pin, git, args.variant, args.rev)


if __name__ == "__main__":
    sys.exit(main())
