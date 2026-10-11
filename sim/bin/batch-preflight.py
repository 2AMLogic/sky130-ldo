#!/usr/bin/env python3
"""Batch-runner compatibility preflight (issue #356).

One shared, cheap re-check for every issue parked on the fleet runner
accepting this host's klt client (`batch_runner_version_mismatch`,
2AMLogic/klayout-tools#2948). It submits ONE single-unit `sim/pdk-smoke`
request (the smallest allowlisted batch shape, tt / 27 C / 1.8 V) through
`corner-run.py`'s own request builder and `klt sim --backend batch` runner,
then reads `environment.remote` from the response.

Exit codes:
  0  accepted: the runner ran the job to a usable completed result -- a
     remote job id, a terminal successful remote state, exactly one corner
     and it is the requested smoke corner (tt / 27 C), that corner completed
     (status pass or fail), and no error-severity diagnostic or runner code
     anywhere (issue #359). A completed measurement FAIL is still accepted:
     this is a compatibility probe, not an electrical grade
  3  version mismatch: runner_compatibility == "mismatch" or a corner carries
     runner_code batch_runner_version_mismatch. Reported, never worked
     around; takes precedence over every other finding
  1  any other failure (klt missing, no/garbled/malformed response, job not
     finished or failed for another reason, missing/duplicate/unexpected or
     incomplete smoke corner, error diagnostics, xschem/PDK problem)

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


# klt's batch backend (klt 0.7.0 sim_batch): status.json state "done" is a
# clean finish; the fleet harness marks any non-zero `klt sim` exit "failed",
# but exit 0/3/4 still means the sweep ran and wrote a report (3 = measurement
# failure, 4 = corner error -- the latter is rejected below by corner status).
REMOTE_DONE = "done"
REMOTE_RAN_EXIT_CODES = (0, 3, 4)
# Corner statuses that are a completed result (mirrors corner-run.py's
# normalize_batch_response); "error"/"inconclusive"/anything else is not.
COMPLETED_STATUSES = ("pass", "fail")
REASON_MAX = 500


def remote_of(response: dict) -> dict:
    env = response.get("environment") if isinstance(response, dict) else None
    remote = env.get("remote") if isinstance(env, dict) else None
    return remote if isinstance(remote, dict) else {}


def _finite_number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value
        and value not in (float("inf"), float("-inf"))
    )


def _exit_code(value):
    """status.json writes exit_code as a string ("" when the job never ran)."""
    if isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _scan_diagnostics(corners: list, info: dict) -> tuple[set, list, list]:
    """Defensively walk every corner's diagnostics.

    Returns (runner codes, error messages, malformed-shape problems). Never
    raises on odd shapes: a non-list container, a non-dict entry or a
    non-string runner_code is reported as a problem instead.
    """
    codes, errors, malformed = set(), [], []
    for i, corner in enumerate(corners):
        if not isinstance(corner, dict):
            continue  # reported by the corner-shape check
        diags = corner.get("diagnostics")
        if diags is None:
            continue
        if not isinstance(diags, list):
            malformed.append(f"corner #{i} diagnostics is not a list ({type(diags).__name__})")
            continue
        for j, d in enumerate(diags):
            if not isinstance(d, dict):
                malformed.append(f"corner #{i} diagnostic #{j} is not an object ({type(d).__name__})")
                continue
            rc = d.get("runner_code")
            if rc is not None and rc != "":
                if isinstance(rc, str):
                    codes.add(rc)
                else:
                    malformed.append(f"corner #{i} diagnostic #{j} runner_code is not a string ({rc!r:.80})")
            for k in ("runner_klt_version", "client_klt_version"):
                if isinstance(d.get(k), str) and d[k] and not info[k]:
                    info[k] = d[k]
            if d.get("severity") == "error":
                msg = d.get("message")
                label = msg if isinstance(msg, str) and msg else (
                    d.get("code") if isinstance(d.get("code"), str) and d.get("code") else None)
                errors.append(str(label) if label else f"corner #{i} error diagnostic with no message")
    return codes, errors, malformed


def _smoke_corner_problems(corners: list) -> list[str]:
    """Exactly one corner, well-formed, identified as the smoke point, completed."""
    want = (POINT[0], float(POINT[1]))
    if not corners:
        return [f"response has no corners (expected exactly the smoke corner {want})"]
    problems, matches = [], []
    for i, c in enumerate(corners):
        if (
            not isinstance(c, dict)
            or not isinstance(c.get("process"), str)
            or not _finite_number(c.get("temperature_c"))
            or not isinstance(c.get("status"), str)
        ):
            problems.append(f"malformed corner entry #{i}: {c!r:.200}")
            continue
        key = (c["process"], float(c["temperature_c"]))
        if key != want:
            problems.append(f"unexpected corner {key} in response (expected {want})")
            continue
        matches.append(c)
    if len(matches) > 1:
        problems.append(f"smoke corner {want} reported {len(matches)} times")
    elif not matches:
        problems.append(f"response is missing the smoke corner {want}")
    elif matches[0]["status"] not in COMPLETED_STATUSES:
        problems.append(
            f"smoke corner status {matches[0]['status']!r} is not a completed result"
        )
    return problems


def classify(response) -> tuple[int, dict]:
    """Pure: (exit code, info) for a klt batch response (or None).

    ACCEPTED only for a completed, usable one-unit smoke response; see the
    module docstring. Version mismatch (exit 3) wins over any other finding.
    """
    remote = remote_of(response) if isinstance(response, dict) else {}
    info = {
        "job_id": remote.get("job_id"),
        "runner_klt_version": remote.get("runner_klt_version"),
        "client_klt_version": remote.get("client_klt_version"),
        "runner_compatibility": remote.get("runner_compatibility"),
        "job_state": remote.get("state"),
        "reason": "",
    }
    if not isinstance(response, dict):
        info["reason"] = "no usable klt sim response"
        return EXIT_OTHER, info
    corners = response.get("corners")
    codes, errors, malformed = _scan_diagnostics(corners if isinstance(corners, list) else [], info)
    if info["runner_compatibility"] == "mismatch" or MISMATCH_CODE in codes:
        warning = remote.get("runner_compatibility_warning")
        info["reason"] = (warning if isinstance(warning, str) and warning else MISMATCH_CODE)[:REASON_MAX]
        return EXIT_MISMATCH, info
    if not isinstance(corners, list):
        info["reason"] = "no usable klt sim response"
        return EXIT_OTHER, info

    # Most actionable first: the runner's own error messages.
    problems = list(errors)
    problems += [f"runner_code {c}" for c in sorted(codes)]
    problems += malformed
    if response.get("status") == "error" or bool(response.get("errored")):
        problems.append(
            f"klt sim status {response.get('status')!r}, errored {response.get('errored')!r}"
        )
    state, rc = info["job_state"], _exit_code(remote.get("exit_code"))
    if not (state == REMOTE_DONE or (state == "failed" and rc in REMOTE_RAN_EXIT_CODES)):
        problems.append(
            f"batch job state {state!r} (exit_code {remote.get('exit_code')!r}) "
            "is not a terminal successful execution"
        )
    if not info["job_id"]:
        problems.append("response names no remote job id; not a batch run")
    problems += _smoke_corner_problems(corners)
    if problems:
        info["reason"] = "; ".join(problems)[:REASON_MAX]
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
