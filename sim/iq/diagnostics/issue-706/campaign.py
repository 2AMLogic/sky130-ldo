#!/usr/bin/env python3
"""Issue #706 paired PVT campaign driver: committed production DUT vs #357 rev2.

Three benches, both DUTs at one base commit (the pairing contract shared with
#704): the candidate netlist is the production netlist after
`apply_candidate(raw, 2)` from this directory's `candidate.py` (imported
read-only from PR #703's head SHA `01dfd695`, recorded in provenance.json).

  iq-base / iq-cand   the full 45-point iq matrix through the validated #213
                      endpoint adapter (`corner-run.py`'s own batch backend:
                      `prepare_batch_requests` + `run_batch`), verbatim, with
                      NO extra cards -- the harness grades every corner with
                      the manifest's own bounds and solver-diagnostic gate, so
                      these legs are directly comparable with a records run.
  cl-pair-base / cl-pair-cand   the tt/27C/3.30V pair as two quick chained
                      batch requests validating the chained-step request shape
                      end-to-end on the fleet before the full grid.
  cl-base / cl-cand   the full 45-point current-limit matrix as ONE three-step
                      chained request per supply (`batch_current_limit.py`,
                      imported read-only from PR #648's head SHA `befb83fb`,
                      which is UNMERGED: main's batch backend has no
                      current-limit entry, so this driver builds and submits
                      the requests itself instead of going through
                      `prepare_batch_requests`). The manifest's ten graded
                      expressions travel verbatim as klt derived measurements
                      and are ALSO evaluated locally over the raw step cards,
                      with the manifest's own bounds, for the paired table.
                      Read-only EXTRA step measurements (the forced-VOUT dc
                      curve between the two manifest points, the clamp
                      comparator node, and the I_R / tail / clamp-reference
                      device currents that bind the bias chain to the clamp
                      and Iq results) are appended after the adapter's own
                      validation, exactly the #692 campaign's extra-card
                      pattern. I_R/tail currents are measured here (on the
                      clamp bench's 50 mA operating point) rather than on the
                      iq requests because the iq endpoint normalizer refuses
                      result identities it did not ask for; the bias chain is
                      load-independent, so the corner key is what matters.

  syntax-probe        ONE local `ngspice -b` per variant at tt / 27 C / 3.30 V
                      on the iq bench validating the candidate edit itself.
                      Not campaign evidence; the recorded evidence is the
                      batch runs.

All batch submissions go through `_record_common.run_klt_sim` with
`retry_capacity=True` and `batch.capacity_wait_s` >= 600 (host rules: never
hand-launch a grid locally, always wait for fleet capacity).
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
import batch_current_limit as bcl  # noqa: E402
import batch_line_regulation as blr  # noqa: E402
from _corner_model import grade_bounds  # noqa: E402
from _record_common import CAPACITY_RETRY_BUDGET_S, klt_binary, run_klt_sim  # noqa: E402

# PR #648's branch point predates main's batch_line_regulation refactor: its
# check_measurements calls blr._tokens, which main removed in favour of
# _EXPR.tokenize (same grammar, same EndpointTranslationError). Shim it rather
# than editing the pinned, verbatim-imported adapter; recorded in provenance.
if not hasattr(blr, "_tokens"):
    blr._tokens = blr._EXPR.tokenize

PF = "pfet_g5v0d10v5"
NF = "nfet_g5v0d10v5"
V = "@m.xldo.{n}.msky130_fd_pr__{t}[{p}]"

# PR #648 head `befb83fb`: the pinned stimulus/load elements each chained-step
# request's netlist must declare (its BATCH_ALLOWLIST entry, copied verbatim).
CL_STIMULUS = [
    "VVIN VIN 0 'vsup'",
    "VEN EN 0 dc 'vsup' pwl(0 0 100u 0 101u 'vsup' 10 'vsup')",
    "RLOAD VOUT 0 36 m=1",
    "RFORCE VOUT VF 1e12 m=1",
    "VFORCE VF 0 dc 1.8 pwl(0 1.8 1m 1.8 1.001m 0 10 0)",
]

# I_R binding (both DUTs): the bias reference that sets the clamp threshold
# (production: the VIN-scaled R_BIAS mirror XM_BIASP1; candidate: the
# VREF-referenced V-to-I XM_VRF), the amplifier tail, and the clamp reference
# XM_CLP itself (gate BIASP -> PBR is the candidate's one clamp change).
BIASREF = {"base": ("xm_biasp1", PF), "cand": ("xm_vrf", NF)}
TAIL = {"base": ("xm_tail", PF), "cand": ("xm_ntail", NF)}


def vec(n: str, t: str, p: str) -> str:
    return V.format(n=n, t=t, p=p)


def cl_extra_saves(variant: str) -> list[str]:
    bn, bt = BIASREF[variant]
    tn, tt_ = TAIL[variant]
    vs = [vec(bn, bt, "id"), vec(tn, tt_, "id"), vec("xm_clp", PF, "id")]
    return [f".save {v}" for v in vs]


def cl_extra_cards(variant: str) -> dict[str, list[dict]]:
    """Read-only extra meas cards per step name (appended AFTER the adapter's
    own parse/validation; the adapter's cards are never modified)."""
    bn, bt = BIASREF[variant]
    tn, tt_ = TAIL[variant]
    ir, tail, clp = vec(bn, bt, "id"), vec(tn, tt_, "id"), vec("xm_clp", PF, "id")
    tran = [
        ("ir_set_50ma", f"meas tran ir_set_50ma avg {ir} from=0.9m to=1.0m"),
        ("tail_i_set_50ma", f"meas tran tail_i_set_50ma avg {tail} from=0.9m to=1.0m"),
        ("clp_i_set_50ma", f"meas tran clp_i_set_50ma avg {clp} from=0.9m to=1.0m"),
        ("cl_cmp_50ma_x", "meas tran cl_cmp_50ma_x avg v(xldo.cl_cmp) from=0.9m to=1.0m"),
    ]
    dc = [
        (n, f"meas dc {n} find i(vforce) at={v:g}")
        for v, n in ((0.375, "i_at_375mv"), (0.75, "i_at_750mv"), (1.125, "i_at_1125mv"),
                     (1.5, "i_at_1500mv"), (1.625, "i_at_1625mv"))
    ] + [
        ("cl_cmp_at_short", "meas dc cl_cmp_at_short find v(xldo.cl_cmp) at=0"),
        ("cl_cmp_at_knee", "meas dc cl_cmp_at_knee find v(xldo.cl_cmp) at=1.75"),
        ("clp_i_at_short", f"meas dc clp_i_at_short find {clp} at=0"),
        ("ir_at_short", f"meas dc ir_at_short find {ir} at=0"),
    ]
    short = [
        ("clp_i_short", f"meas tran clp_i_short avg {clp} from=2.0m to=3.0m"),
    ]
    return {
        "tran1": [{"name": n, "spice": "." + c} for n, c in tran],
        "dc1": [{"name": n, "spice": "." + c} for n, c in dc],
        "tran2": [{"name": n, "spice": "." + c} for n, c in short],
    }


CL_EXTRA_NAMES = ["ir_set_50ma", "tail_i_set_50ma", "clp_i_set_50ma", "cl_cmp_50ma_x",
                  "i_at_375mv", "i_at_750mv", "i_at_1125mv", "i_at_1500mv", "i_at_1625mv",
                  "cl_cmp_at_short", "cl_cmp_at_knee", "clp_i_at_short", "ir_at_short",
                  "clp_i_short"]


def full_matrix(exp) -> list:
    c = exp.raw["corners"]
    return [cr.Corner(p, float(t), float(v)) for p in c["process"]
            for t in c["temperature_c"] for v in c["supply_v"]]


def variant_body(exp, pdk, variant: str, rev: int, extra_saves: list[str] | None = None
                 ) -> tuple[list[str], dict]:
    """Netlist body of the bench with the variant applied (+ .save cards)."""
    with tempfile.TemporaryDirectory(prefix="i706-nl-") as nl:
        net = cr.netlist_with_xschem(exp.schematic, Path(nl), pdk)
        raw = "\n".join(cr.netlist_body(net)) + "\n"
    notes, problems = [], []
    if variant == "cand":
        edited, notes = cand.apply_candidate(raw, rev)
        problems = cand.check_candidate(raw, edited)
        if problems:
            raise SystemExit("candidate invariant check failed: " + "; ".join(problems))
    else:
        edited = raw
    body = edited.splitlines() + (extra_saves or [])
    return body, {"raw": raw, "edited": edited, "notes": notes, "problems": problems}


def provenance_block(exp, pdk, variant: str, rev: int, prov: dict, body: list[str]) -> dict:
    return {
        "source_commit": pc.git_provenance(REPO),
        "driver_sha256": pc.sha(Path(__file__).read_bytes()),
        "candidate_py_sha256": pc.sha((HERE / "candidate.py").read_bytes()),
        "batch_current_limit_py_sha256": pc.sha((HERE / "batch_current_limit.py").read_bytes()),
        "netlist_sha256": pc.sha(("\n".join(body) + "\n").encode()),
        "dut_sch_sha256": pc.sha((REPO / "design" / "ldo_3v3in_1v8out.sch").read_bytes()),
        "testbench_sha256": pc.sha(exp.schematic.read_bytes()),
        "experiment_json_sha256": pc.sha((exp.dir / "experiment.json").read_bytes()),
        "edit_notes": prov["notes"],
        "candidate_invariant_problems": prov["problems"],
        "pdk": {"open_pdks_commit": pdk.installed_commit, "matches_pin": pdk.matches_pin,
                "lib_sha256": pc.sha(Path(pdk.lib_file).read_bytes())},
        "tools": cr.tool_versions(),
    }


# ------------------------------------------------------------------ iq legs
def _iq_groups(exp, matrix):
    from _batch_backend import batch_legs, group_batch_requests
    return group_batch_requests(matrix, False, batch_legs(exp))


def resume_iq_leg(leg: str, timeout: int = 300) -> dict:
    """Finish an interrupted iq leg: submit only the requests whose
    response.json is absent, then grade ALL responses through the harness's
    own endpoint normalizer (normalize_endpoint_response +
    finalize_endpoint_results, the exact path run_batch takes)."""
    from _batch_backend import (batch_remote_info, finalize_endpoint_results,
                                normalize_endpoint_response)
    from _record_common import assert_klt_read_the_pinned_pdk
    run_dir = HERE / "runs" / leg
    if not run_dir.is_dir():
        raise SystemExit(f"{run_dir} does not exist")
    if (run_dir / "leg.json").exists():
        raise SystemExit(f"{run_dir}/leg.json exists: leg already complete")
    pdk = cr.resolve_pdk(cr.load_pin())
    pin = cr.load_pin()
    exp = cr.load_experiment(SIM / "iq")
    rec = json.loads((run_dir / "provisional.json").read_text()) if (run_dir / "provisional.json").exists() else {}
    matrix = full_matrix(exp)
    variant = rec.get("variant") or ("cand" if "cand" in leg else "base")
    rev = rec.get("candidate_rev") or (2 if variant == "cand" else None)
    body, prov = variant_body(exp, pdk, variant, rev or 2)
    stored = (run_dir / "netlist.spice").read_text()
    if stored != "\n".join(body) + "\n":
        raise SystemExit("re-derived netlist differs from the interrupted leg's netlist.spice; "
                         "the base moved -- start a new leg instead of resuming")
    parts: dict[str, list[dict]] = {}
    logs: dict[str, str] = {}
    requests_meta = []
    for group in _iq_groups(exp, matrix):
        outdir = run_dir / "klt-out" / group.key
        request_path = run_dir / "klt-requests" / f"{group.key}.json"
        resp_path = outdir / "response.json"
        if not resp_path.is_file():
            response, meta = run_klt_sim(request_path, outdir, "batch", pdk.root,
                                         klt_exe=klt_binary("finish the iq leg"),
                                         retry_capacity=True, resolve_paths=True)
            resp_path.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n")
        else:
            response = json.loads(resp_path.read_text())
            meta = {"returncode": 0}
        info = batch_remote_info(response)
        assert_klt_read_the_pinned_pdk(response, pdk, pin, False)
        res, lg = normalize_endpoint_response(exp, group, response, outdir)
        for r in res:
            parts.setdefault(r["corner"].id, []).append(r)
        for cid, text in lg.items():
            logs[cid] = logs.get(cid, "") + (
                f"***** iq endpoint {group.leg} (klt sim request {group.key}) *****\n{text}\n")
        requests_meta.append({"key": group.key, "endpoint": group.leg,
                              "supply_v": group.supply_v, "n_points": len(group.corners),
                              "returncode": meta["returncode"],
                              "response_file": str(resp_path), "request_file": str(request_path),
                              **info})
    results = finalize_endpoint_results(exp, matrix, parts, timeout)
    prov_block = rec.get("provenance") or provenance_block(exp, pdk, variant, rev or 2, prov, body)
    out = {
        "leg": leg, "experiment": "iq", "variant": variant, "candidate_rev": rev,
        "resumed": True, "matrix": [[c.process, c.temp_c, c.supply_v] for c in matrix],
        "corner_ids": [c.id for c in matrix],
        "results": results, "execution": {"requests": requests_meta},
        "provenance": prov_block,
    }
    (run_dir / "leg.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    (run_dir / "logs").mkdir(exist_ok=True)
    for cid, text in logs.items():
        (run_dir / "logs" / f"{cid}.log").write_text(text)
    n_pass = sum(1 for r in results if r["pass"])
    print(f"[{leg}] {n_pass}/{len(results)} corners harness-pass; "
          f"jobs: {', '.join(str(r.get('job_id')) for r in requests_meta)}")
    return out


def run_iq_leg(leg: str, variant: str, rev: int, quick_matrix=None, timeout: int = 300) -> dict:
    """Full iq matrix through the validated endpoint adapter, NO extra cards."""
    run_dir = HERE / "runs" / leg
    if run_dir.exists():
        raise SystemExit(f"{run_dir} exists: evidence is append-only")
    run_dir.mkdir(parents=True)
    pdk = cr.resolve_pdk(cr.load_pin())
    pin = cr.load_pin()
    exp = cr.load_experiment(SIM / "iq")
    body, prov = variant_body(exp, pdk, variant, rev)
    (run_dir / "netlist.spice").write_text("\n".join(body) + "\n")
    (run_dir / "provisional.json").write_text(json.dumps(
        {"variant": variant, "candidate_rev": rev if variant == "cand" else None,
         "provenance": provenance_block(exp, pdk, variant, rev, prov, body)}, indent=1) + "\n")
    if variant == "cand":
        diff = "".join(difflib.unified_diff(
            prov["raw"].splitlines(True), prov["edited"].splitlines(True),
            "netlist.raw.spice", "netlist.edited.spice"))
        (run_dir / "netlist.diff").write_text(diff)
    matrix = quick_matrix if quick_matrix is not None else full_matrix(exp)
    prepared = cr.prepare_batch_requests(exp, pdk, matrix, quick_matrix is not None,
                                         body, run_dir, timeout)
    results, logs, execution = cr.run_batch(exp, pdk, pin, prepared, matrix, run_dir, timeout,
                                            False)
    rec = {
        "leg": leg, "experiment": "iq", "variant": variant,
        "candidate_rev": rev if variant == "cand" else None,
        "matrix": [[c.process, c.temp_c, c.supply_v] for c in matrix],
        "corner_ids": [c.id for c in matrix],
        "results": results, "execution": execution,
        "provenance": provenance_block(exp, pdk, variant, rev, prov, body),
    }
    (run_dir / "leg.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    (run_dir / "logs").mkdir(exist_ok=True)
    for cid, text in logs.items():
        (run_dir / "logs" / f"{cid}.log").write_text(text)
    n_pass = sum(1 for r in results if r["pass"])
    print(f"[{leg}] {n_pass}/{len(results)} corners harness-pass; "
          f"jobs: {', '.join(str(r.get('job_id')) for r in execution['requests'])}")
    return rec


# --------------------------------------------------------------- clamp legs
def build_cl_requests(exp, pdk, variant: str, rev: int, matrix, quick: bool, run_dir: Path,
                      body: list[str], timeout: int) -> list[tuple[str, Path, Path, float]]:
    """One three-step chained request per supply group (the #648 adapter's own
    grouping), written under run_dir/klt-requests/. Returns (key, request_path,
    netlist_path, supply_v)."""
    legs = bcl.parse_deck((exp.raw.get("deck") or {}).get("analyses") or [])
    bcl.check_measurements(legs, [(m.name, m.expr, m.unit) for m in exp.measurements])
    bcl.check_netlist(body, CL_STIMULUS)
    supplies = []
    for c in matrix:
        if c.supply_v not in supplies:
            supplies.append(c.supply_v)
    if quick:
        supplies = [matrix[0].supply_v]
        pts = {(matrix[0].process, matrix[0].temp_c)}
    req_dir = run_dir / "klt-requests"
    req_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for vsup in supplies:
        pts_at = {(c.process, c.temp_c) for c in matrix if c.supply_v == vsup}
        if quick:
            pts_at = pts
        procs, temps = [], []
        for c in matrix:
            if c.supply_v != vsup or (c.process, c.temp_c) not in pts_at:
                continue
            if c.process not in procs:
                procs.append(c.process)
            if c.temp_c not in temps:
                temps.append(c.temp_c)
        key = f"v{vsup:.2f}"
        netlist = [f".param vsup={vsup:g}"]
        for name, value in ((exp.raw.get("deck") or {}).get("params") or {}).items():
            netlist.append(f".param {name}={value}")
        for opt in (exp.raw.get("deck") or {}).get("options") or []:
            netlist.append(f".option {opt}")
        netlist.append(".save all")
        netlist += body
        netlist_path = (req_dir / f"{key}.spice").resolve()
        netlist_path.write_text("\n".join(netlist) + "\n")
        steps = bcl.chained_steps(legs)
        extras = cl_extra_cards(variant)
        for step in steps:
            have = {m.get("name") for m in step.get("measurements", [])}
            for e in extras.get(step["name"], []):
                if e["name"] not in have:
                    step["measurements"].append(e)
        request = {
            "netlist": str(netlist_path),
            "engine": "ngspice",
            "models": {"pdk": pdk.variant, "lib": str(pdk.lib_file.relative_to(pdk.dir))},
            "corners": {"process": procs, "temperature_c": temps},
            "analysis_steps": steps,
            "measurements": [
                {"name": f"meas_{m.name}", "expr": m.expr, "unit": m.unit} for m in exp.measurements
            ],
            "options": {"timeout_s": timeout, "keep_artifacts": True,
                        "ngspice_init": cr.spiceinit_lines()},
            "batch": {"capacity_wait_s": CAPACITY_RETRY_BUDGET_S},
        }
        request_path = req_dir / f"{key}.json"
        request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")
        out.append((key, request_path, netlist_path, vsup))
    return out


def grade_cl_corner(exp, rc: dict, log_text: str | None) -> dict:
    """One response corner -> raw step cards, locally evaluated manifest
    expressions with the manifest's own bounds, extras, solver diagnostic."""
    by_name: dict[str, list] = {}
    for rm in rc.get("measurements") or []:
        if isinstance(rm, dict) and isinstance(rm.get("name"), str):
            by_name.setdefault(rm["name"], []).append(rm)
    raw: dict[str, float | None] = {}
    reasons: list[str] = []
    for name, entries in sorted(by_name.items()):
        if len(entries) != 1 or not isinstance(entries[0].get("value"), (int, float)):
            raw[name] = None
            reasons.append(f"card {name} missing/duplicated/non-finite")
            continue
        raw[name] = float(entries[0]["value"])
    values = {}
    for m in exp.measurements:
        values[m.name] = blr.evaluate(m.expr, raw, bcl.card_refs(
            bcl.parse_deck((exp.raw.get("deck") or {}).get("analyses") or [])))
        if values[m.name] is None:
            reasons.append(f"derived {m.name} not evaluable")
    diag = cr.detect_solver_diagnostic(log_text) if log_text is not None else "log unavailable"
    if diag:
        reasons.append(f"solver diagnostic: {diag}")
    if rc.get("status") not in ("pass", "fail"):
        reasons.append(f"klt corner status {rc.get('status')!r}")
    checks = []
    for m in exp.measurements:
        v = values[m.name]
        ok, why = grade_bounds(m, v)
        if diag:
            ok = False  # the #171 gate: a solver diagnostic fails the corner outright
        checks.append({"name": m.name, "expr": m.expr, "unit": m.unit, "value": v,
                       "min": m.min, "max": m.max, "max_inclusive": m.max_inclusive,
                       "pass": bool(ok), "reason": "" if ok else (f"solver diagnostic: {diag}" if diag else why)})
    extras = {n: raw.get(f"{s}.{n}") for n, s in (
        *((x, "tran1") for x in ("ir_set_50ma", "tail_i_set_50ma", "clp_i_set_50ma", "cl_cmp_50ma_x")),
        *((x, "dc1") for x in ("i_at_375mv", "i_at_750mv", "i_at_1125mv", "i_at_1500mv",
                               "i_at_1625mv", "cl_cmp_at_short", "cl_cmp_at_knee",
                               "clp_i_at_short", "ir_at_short")),
        *((x, "tran2") for x in ("clp_i_short",)),
    )}
    passed = not reasons and all(c["pass"] for c in checks)
    return {"raw_cards": raw, "derived": checks, "extras": extras,
            "solver_diagnostic": diag, "klt_status": rc.get("status"),
            "reasons": reasons, "pass": passed}


def run_cl_leg(leg: str, variant: str, rev: int, quick_matrix=None, timeout: int = 1800,
               resume: bool = False) -> dict:
    run_dir = HERE / "runs" / leg
    if resume:
        if not run_dir.is_dir():
            raise SystemExit(f"{run_dir} does not exist")
        if (run_dir / "leg.json").exists():
            raise SystemExit(f"{run_dir}/leg.json exists: leg already complete")
        prov_rec = json.loads((run_dir / "provisional.json").read_text())
        variant, rev = prov_rec["variant"], prov_rec["candidate_rev"] or rev
    else:
        if run_dir.exists():
            raise SystemExit(f"{run_dir} exists: evidence is append-only")
        run_dir.mkdir(parents=True)
    pdk = cr.resolve_pdk(cr.load_pin())
    exp = cr.load_experiment(SIM / "current-limit")
    if resume:
        body = (run_dir / "netlist.spice").read_text().rstrip("\n").split("\n")
        prov = prov_rec["provenance"]
    else:
        body, prov = variant_body(exp, pdk, variant, rev, extra_saves=cl_extra_saves(variant))
        (run_dir / "netlist.spice").write_text("\n".join(body) + "\n")
        (run_dir / "provisional.json").write_text(json.dumps(
            {"variant": variant, "candidate_rev": rev if variant == "cand" else None,
             "provenance": provenance_block(exp, pdk, variant, rev, prov, body)}, indent=1) + "\n")
        if variant == "cand":
            diff = "".join(difflib.unified_diff(
                prov["raw"].splitlines(True), prov["edited"].splitlines(True),
                "netlist.raw.spice", "netlist.edited.spice"))
            (run_dir / "netlist.diff").write_text(diff)
    matrix = quick_matrix if quick_matrix is not None else full_matrix(exp)
    prepared = build_cl_requests(exp, pdk, variant, rev, matrix, quick_matrix is not None,
                                 run_dir, body, timeout)
    results = []
    requests_meta = []
    for key, request_path, netlist_path, vsup in prepared:
        outdir = run_dir / "klt-out" / key
        resp_path = outdir / "response.json"
        if resume and resp_path.is_file():
            response = json.loads(resp_path.read_text())
            meta = {"returncode": 0}
        else:
            response, meta = run_klt_sim(request_path, outdir, "batch", pdk.root,
                                         klt_exe=klt_binary("run the chained current-limit leg"),
                                         retry_capacity=True, resolve_paths=True)
            resp_path.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n")
        remote = (response.get("environment") or {}).get("remote") or {}
        requests_meta.append({
            "key": key, "supply_v": vsup, "returncode": meta["returncode"],
            "job_id": remote.get("job_id"), "provider": remote.get("provider"),
            "engine_version": (response.get("environment") or {}).get("engine_version"),
            "response_file": str(outdir / "response.json"),
            "request_file": str(request_path), "netlist_file": str(netlist_path),
        })
        want = {(c.process, c.temp_c): c for c in matrix if c.supply_v == vsup}
        if quick_matrix is not None:
            want = {(matrix[0].process, matrix[0].temp_c): matrix[0]}
        seen = {}
        for rc in response.get("corners", []):
            if isinstance(rc, dict) and isinstance(rc.get("process"), str):
                seen[(rc["process"], float(rc.get("temperature_c")))] = rc
        for (proc, temp), c in want.items():
            rc = seen.get((proc, temp))
            if rc is None:
                results.append({"corner_id": c.id, "process": proc, "temp_c": temp,
                                "supply_v": vsup, "pass": False,
                                "reasons": ["corner missing from response"]})
                continue
            art = rc.get("artifacts") or {}
            log_ref = art.get("log") if isinstance(art.get("log"), str) else None
            log_text = None
            if log_ref:
                lp = Path(log_ref) if Path(log_ref).is_absolute() else outdir / log_ref
                try:
                    log_text = lp.read_text(errors="replace")
                except OSError:
                    log_text = None
            g = grade_cl_corner(exp, rc, log_text)
            results.append({"corner_id": c.id, "process": proc, "temp_c": temp,
                            "supply_v": vsup, **g})
    rec = {
        "leg": leg, "experiment": "current-limit", "variant": variant,
        "candidate_rev": rev if variant == "cand" else None,
        "adapter": {"module": "batch_current_limit.py", "source": "PR #648 head befb83fb (unmerged)",
                    "shape": "one three-step chained request per supply"},
        "matrix": [[c.process, c.temp_c, c.supply_v] for c in matrix],
        "corner_ids": [c.id for c in matrix],
        "results": results, "execution": {"requests": requests_meta},
        "provenance": prov if resume else provenance_block(exp, pdk, variant, rev, prov, body),
    }
    (run_dir / "leg.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    n_pass = sum(1 for r in results if r["pass"])
    n_diag = sum(1 for r in results if r.get("solver_diagnostic"))
    print(f"[{leg}] {n_pass}/{len(results)} corners pass ({n_diag} solver-diagnostic); "
          f"jobs: {', '.join(str(r['job_id']) for r in requests_meta)}")
    return rec


# --------------------------------------------------------------- local probe
def syntax_probe() -> None:
    """One local ngspice -b per variant at tt/27C/3.30V on the iq bench:
    validates the candidate edit against the current netlist (not campaign
    evidence; the batch legs are)."""
    pdk = cr.resolve_pdk(cr.load_pin())
    exp = cr.load_experiment(SIM / "iq")
    corner = cr.Corner("tt", 27.0, 3.3)
    out = HERE / "runs" / "local-syntax"
    if out.exists():
        raise SystemExit(f"{out} exists: append-only")
    for variant in ("base", "cand"):
        body, prov = variant_body(exp, pdk, variant, 2)
        deck = cr.build_deck(exp, pdk, corner, body)
        rd = out / variant
        rd.mkdir(parents=True)
        (rd / "deck.spice").write_text(deck)
        (rd / ".spiceinit").write_text((SIM / "spiceinit").read_text())
        log, elapsed, rcode = pc.run_ngspice_deck(rd, timeout=900)
        m = lambda n: (float(v.group(1)) if (v := re.search(rf"^{n}\s*=\s*(-?[0-9.eE+-]+)", log, re.M)) else None)  # noqa: E731
        rec = {"variant": variant, "ngspice_exit": rcode, "elapsed_s": round(elapsed, 1),
               "solver_diagnostic": cr.detect_solver_diagnostic(log),
               "iq_no_load_raw": m("iq_no_load_raw"), "iq_full_load_raw": m("iq_full_load_raw"),
               "vout_no_load": m("vout_no_load"), "vout_full_load": m("vout_full_load"),
               "netlist_sha256": pc.sha(("\n".join(body) + "\n").encode()),
               "edit_notes": prov["notes"], "source_commit": pc.git_provenance(REPO)}
        (rd / "result.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
        print(json.dumps(rec))


def resume_cl_leg(leg: str, timeout: int = 1800) -> dict:
    return run_cl_leg(leg, "", 2, None, timeout, resume=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["syntax-probe", "iq-base", "iq-cand", "iq-resume",
                                     "cl-pair-base", "cl-pair-cand", "cl-base", "cl-cand",
                                     "cl-resume"])
    ap.add_argument("leg", nargs="?", default=None, help="leg dir name for *-resume modes")
    ap.add_argument("--rev", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=None)
    a = ap.parse_args(argv)
    if a.mode == "syntax-probe":
        syntax_probe()
        return
    if a.mode == "iq-resume":
        if not a.leg:
            raise SystemExit("iq-resume needs the leg dir name, e.g. iq-base")
        resume_iq_leg(a.leg, timeout=a.timeout or 300)
        return
    if a.mode == "cl-resume":
        if not a.leg:
            raise SystemExit("cl-resume needs the leg dir name, e.g. cl-base")
        resume_cl_leg(a.leg, timeout=a.timeout or 1800)
        return
    pair = [cr.Corner("tt", 27.0, 3.3)]
    if a.mode.startswith("iq-"):
        run_iq_leg(a.mode, "cand" if a.mode.endswith("cand") else "base", a.rev,
                   timeout=a.timeout or 300)
    elif a.mode.startswith("cl-pair-"):
        run_cl_leg(a.mode, "cand" if a.mode.endswith("cand") else "base", a.rev,
                   quick_matrix=pair, timeout=a.timeout or 1800)
    else:
        run_cl_leg(a.mode, "cand" if a.mode.endswith("cand") else "base", a.rev,
                   timeout=a.timeout or 1800)


if __name__ == "__main__":
    main()
