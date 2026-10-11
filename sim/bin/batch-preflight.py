#!/usr/bin/env python3
"""Batch-runner compatibility preflight (issue #356).

One shared, cheap re-check for every issue parked on the fleet runner
accepting this host's klt client (`batch_runner_version_mismatch`,
2AMLogic/klayout-tools#2948). It submits ONE single-unit `sim/pdk-smoke`
request (the smallest allowlisted batch shape, tt / 27 C / 1.8 V) through
`corner-run.py`'s own request builder and `klt sim --backend batch` runner,
then reads `environment.remote` from the response.

Exit codes:
  0  accepted: the runner took the job (compatibility not "mismatch", no
     batch failure)
  3  version mismatch: runner_compatibility == "mismatch" or a corner carries
     runner_code batch_runner_version_mismatch. Reported, never worked around
  1  any other failure (klt missing, no/garbled response, job failed for
     another reason, xschem/PDK problem)

This is a probe, not evidence: it writes nothing under any `sim/<experiment>/`
directory (scratch lives in a temp dir, removed on exit unless --keep). No
local fallback exists. `klt sim` has no compatibility-only check (checked
against klt 0.7.0), so a real single-unit submit is the cheapest available
probe -- run it once per re-check, not in a loop.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import _probe_common as pc

EXIT_ACCEPTED, EXIT_OTHER, EXIT_MISMATCH = 0, 1, 3
MISMATCH_CODE = "batch_runner_version_mismatch"
EXPERIMENT = "pdk-smoke"
POINT = ("tt", 27.0, 1.8)


def remote_of(response: dict) -> dict:
    env = response.get("environment") if isinstance(response, dict) else None
    remote = env.get("remote") if isinstance(env, dict) else None
    return remote if isinstance(remote, dict) else {}


def classify(response) -> tuple[int, dict]:
    """Pure: (exit code, info) for a klt batch response (or None)."""
    remote = remote_of(response) if isinstance(response, dict) else {}
    info = {
        "job_id": remote.get("job_id"),
        "runner_klt_version": remote.get("runner_klt_version"),
        "client_klt_version": remote.get("client_klt_version"),
        "runner_compatibility": remote.get("runner_compatibility"),
        "job_state": remote.get("state"),
        "reason": "",
    }
    if not isinstance(response, dict) or not isinstance(response.get("corners"), list):
        info["reason"] = "no usable klt sim response"
        return EXIT_OTHER, info
    codes, msgs = set(), []
    for corner in response["corners"]:
        for d in (corner.get("diagnostics") or []) if isinstance(corner, dict) else []:
            if isinstance(d, dict):
                if d.get("runner_code"):
                    codes.add(d["runner_code"])
                for k in ("runner_klt_version", "client_klt_version"):
                    if d.get(k) and not info[k]:
                        info[k] = d[k]
                if d.get("severity") == "error" and d.get("message"):
                    msgs.append(str(d["message"]))
    if info["runner_compatibility"] == "mismatch" or MISMATCH_CODE in codes:
        info["reason"] = remote.get("runner_compatibility_warning") or MISMATCH_CODE
        return EXIT_MISMATCH, info
    failed = (
        info["job_state"] == "failed"
        or response.get("status") == "error"
        or bool(response.get("errored"))
        or bool(codes)
    )
    if failed:
        info["reason"] = (msgs[0] if msgs else f"batch job state {info['job_state']!r}")[:500]
        return EXIT_OTHER, info
    if not info["job_id"]:
        info["reason"] = "response names no remote job id; not a batch run"
        return EXIT_OTHER, info
    return EXIT_ACCEPTED, info


def report(code: int, info: dict) -> None:
    verdict = {EXIT_ACCEPTED: "ACCEPTED", EXIT_MISMATCH: "VERSION MISMATCH"}.get(code, "FAILED")
    print(f"batch preflight : {verdict} (exit {code})")
    print(f"job id          : {info.get('job_id') or 'none'}")
    print(f"runner klt      : {info.get('runner_klt_version') or 'unknown'}")
    print(f"client klt      : {info.get('client_klt_version') or 'unknown'}")
    print(f"compatibility   : {info.get('runner_compatibility') or 'unreported'}")
    if info.get("reason"):
        print(f"reason          : {info['reason']}")


def submit_probe(cr, scratch: Path) -> dict:
    """Build the one-unit pdk-smoke request in `scratch` and submit it."""
    pin = cr.load_pin()
    pdk = cr.resolve_pdk(pin)
    exp = cr.load_experiment(cr.SIM_DIR / EXPERIMENT)
    cr.check_batch_supported(exp)
    cr.klt_binary()
    shutil.copyfile(cr.SPICEINIT_FILE, scratch / ".spiceinit")
    body = cr.netlist_body(cr.netlist_with_xschem(exp.schematic, scratch, pdk))
    corner = cr.Corner(*POINT)
    prepared = cr.prepare_batch_requests(exp, pdk, [corner], True, body, scratch, 300)
    (group, request_path, _request), = prepared
    response, _meta = cr.run_klt_batch(request_path, scratch / "klt-out" / group.key, pdk.root)
    return response


def main(argv: list[str], cr=None, submit=submit_probe) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--keep", action="store_true", help="keep the scratch dir (printed)")
    ap.add_argument("--json", action="store_true", help="also print the result as JSON")
    args = ap.parse_args(argv)
    cr = cr or pc.load_corner_run()
    scratch = Path(tempfile.mkdtemp(prefix="batch-preflight-"))
    try:
        try:
            response = submit(cr, scratch)
        except (cr.HarnessError, OSError) as exc:
            code, info = EXIT_OTHER, classify(None)[1]
            info["reason"] = str(exc)[:1500]
        else:
            code, info = classify(response)
        report(code, info)
        if args.json:
            print(json.dumps({"exit": code, **info}, sort_keys=True))
        return code
    finally:
        if args.keep:
            print(f"scratch dir     : {scratch}")
        else:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
