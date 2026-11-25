#!/usr/bin/env python3
"""Issue #705 paired mismatch-accuracy legs (baseline vs #692 rev2 candidate).

Pairs sim/mc-output-accuracy with itself: both DUTs run the SAME sample
configuration -- manifest defaults N=200, vary=mismatch, k_sigma=3, the record
family's base seed 20260817, the tt_mm / 27 C / 3.30 V point, the `uic`
disabled-state start with EN rising at 100 us -- at one pinned production
commit, so #702 can attribute differences to the DUT rather than to the
sample sequence. The request is built by sim/bin/mc-run.py's own builders
(load_mc_experiment / build_klt_netlist / build_klt_request / run_klt_sim)
verbatim; the ONLY difference between the legs is the netlist body: the
candidate leg applies candidate.apply_candidate(raw, 2) + check_candidate
before the request is written.

This is a diagnostic pairing, not a record mint: no production record under
sim/mc-output-accuracy/records/ is created (mc-run.py's record path stays
untouched); each leg's klt request + response + per-sample analysis land in
this diagnostics directory as runs/mc-<variant>/.

Backend: `klt sim --backend batch` with --wait-for-capacity 600 (passed by
mc-run.py's run_klt_sim for the batch backend, plus the request-level
capacity_wait_s), per the host rule -- the 200-draw grid never runs locally.
"""
from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parents[2]
REPO = SIM.parent
sys.path.insert(0, str(SIM / "bin"))
sys.path.insert(0, str(HERE))
import _probe_common as pc  # noqa: E402

cr = pc.load_corner_run()
import candidate as cand  # noqa: E402

spec = importlib.util.spec_from_file_location("mc_run", SIM / "bin" / "mc-run.py")
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)

REV = 2
SEED = 20260817          # the mc-output-accuracy record family's base seed
WINDOW = (1.764, 1.836)  # ratified Output row, inclusive


def analyse_samples(response: dict) -> dict:
    """Per-sample accounting over the klt MC response: attempted (the request's
    N), returned corner entries, valid vout_ss values, in-window vs
    out-of-window (inclusive bounds), and errored/missing solves with sample
    ids -- the issue's mismatch-accuracy deliverable."""
    corners = response.get("corners") or []
    valid, violations, errored = [], [], []
    for i, rc in enumerate(corners):
        sid = rc.get("corner_id") if isinstance(rc, dict) else None
        if not isinstance(rc, dict) or rc.get("status") == "error":
            errored.append({"sample": sid or f"#{i}", "status": rc.get("status") if isinstance(rc, dict) else "non-dict",
                            "diagnostics": (rc.get("diagnostics") if isinstance(rc, dict) else None)})
            continue
        got = [m for m in (rc.get("measurements") or [])
               if isinstance(m, dict) and m.get("name") == "vout_ss"]
        if len(got) != 1 or not isinstance(got[0].get("value"), (int, float)):
            errored.append({"sample": sid, "status": rc.get("status"),
                            "diagnostics": "vout_ss missing or non-finite"})
            continue
        v = float(got[0]["value"])
        valid.append({"sample": sid, "vout_ss": v})
        if not (WINDOW[0] <= v <= WINDOW[1]):
            violations.append({"sample": sid, "vout_ss": v})
    vals = [s["vout_ss"] for s in valid]
    stats = None
    if vals:
        n = len(vals)
        mean = sum(vals) / n
        sd = (sum((v - mean) ** 2 for v in vals) / (n - 1)) ** 0.5 if n > 1 else 0.0
        stats = {"n": n, "mean": mean, "stddev": sd, "min": min(vals), "max": max(vals)}
    return {
        "window_v": {"min": WINDOW[0], "max": WINDOW[1], "inclusive": True},
        "returned_samples": len(corners),
        "valid_samples": len(valid),
        "in_window": len(valid) - len(violations),
        "out_of_window": len(violations),
        "violations": violations,
        "errored_or_missing": errored,
        "stats": stats,
    }


def run_leg(variant: str, n: int, timeout: int, allow_pdk_mismatch: bool) -> dict:
    run_dir = HERE / "runs" / f"mc-{variant}"
    if run_dir.exists():
        raise SystemExit(f"{run_dir} exists: evidence is append-only")
    run_dir.mkdir(parents=True)
    pin = cr.load_pin()
    pdk = cr.resolve_pdk(pin)
    exp = mc.load_mc_experiment(SIM / "mc-output-accuracy")
    defaults = exp.get("monte_carlo_defaults", {})
    vary = defaults.get("vary", "mismatch")
    k_sigma = defaults.get("k_sigma", 3)
    with __import__("tempfile").TemporaryDirectory(prefix="i705-mc-") as nl:
        net = cr.netlist_with_xschem(exp["_schematic"], Path(nl), pdk)
        raw = "\n".join(mc.build_klt_netlist(exp, net)) + "\n"
    notes, problems = [], []
    body_text = raw
    if variant == "cand":
        body_text, notes = cand.apply_candidate(raw, REV)
        problems = cand.check_candidate(raw, body_text)
        if problems:
            raise SystemExit("candidate invariant check failed: " + "; ".join(problems))
    netlist_path = run_dir / "netlist.spice"
    netlist_path.write_text(body_text)
    if variant == "cand":
        (run_dir / "netlist.diff").write_text("".join(difflib.unified_diff(
            raw.splitlines(True), body_text.splitlines(True),
            "netlist.raw.spice", "netlist.edited.spice")))
    request = mc.build_klt_request(exp, pdk, netlist_path.resolve(), n, SEED, vary,
                                   k_sigma, timeout, False)
    request_path = run_dir / "klt-request.json"
    request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")
    response = mc.run_klt_sim(request_path, run_dir / "klt-out", "batch",
                              max_workers=8, pdk_root=pdk.root)
    (run_dir / "klt-out" / "response.json").write_text(
        json.dumps(response, indent=2, sort_keys=True) + "\n")
    mc.assert_klt_read_the_pinned_pdk(response, pdk, pin, allow_pdk_mismatch)
    analysis = analyse_samples(response)
    env = response.get("environment") or {}
    prov = {
        "source_commit": pc.git_provenance(REPO),
        "variant": variant, "candidate_rev": REV if variant == "cand" else None,
        "candidate_py_sha256": pc.sha((HERE / "candidate.py").read_bytes()),
        "netlist_raw_sha256": pc.sha(raw.encode()),
        "netlist_edited_sha256": pc.sha(body_text.encode()),
        "edit_notes": notes, "candidate_invariant_problems": problems,
        "testbench_sha256": pc.sha(exp["_schematic"].read_bytes()),
        "experiment_json_sha256": pc.sha((SIM / "mc-output-accuracy" / "experiment.json").read_bytes()),
        "pdk": {"open_pdks_commit": pdk.installed_commit, "matches_pin": pdk.matches_pin},
        "tools": cr.tool_versions(),
        "seed": SEED, "n": n, "vary": vary, "k_sigma": k_sigma,
        "remote": env.get("remote"), "engine": env.get("engine"),
        "engine_version": env.get("engine_version"),
        "klt_version": (response.get("provenance") or {}).get("klt_version"),
        "klt_pdk_version": ((response.get("provenance") or {}).get("pdk") or {}).get("version"),
        "klt_status": response.get("status"),
    }
    rec = {"leg": f"mc-{variant}", "experiment": "mc-output-accuracy",
           "variant": variant, "provenance": prov, "analysis": analysis,
           "aggregate": {"status": response.get("status"),
                         "passed": response.get("passed"),
                         "failed": response.get("failed"),
                         "errored": response.get("errored"),
                         "corner_count": response.get("corner_count")}}
    (run_dir / "leg.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    print(f"[mc-{variant}] attempted={n} returned={analysis['returned_samples']} "
          f"valid={analysis['valid_samples']} out_of_window={analysis['out_of_window']} "
          f"errored={len(analysis['errored_or_missing'])} klt={response.get('status')}")
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("variant", choices=["base", "cand"])
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--allow-pdk-mismatch", action="store_true")
    a = ap.parse_args(argv)
    run_leg(a.variant, a.n, a.timeout, a.allow_pdk_mismatch)


if __name__ == "__main__":
    main()
