#!/usr/bin/env python3
"""Batch-only, paired stability screen for issue #691. Each invocation mints a new record."""

import argparse
import importlib
import itertools
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _fleet_campaign as fc  # noqa: E402
from _record_common import JOB_ID_RE, is_finite_number  # noqa: E402

adaptive = importlib.import_module("rcz-adaptive-370")
DESIGNS = ("baseline", "shelf")
LOADS = {
    "0mA": "1e12",
    "10uA": "180k",
    "30uA": "60k",
    "100uA": "18k",
    "300uA": "6k",
    "1mA": "1800",
    "50mA": "36",
}
ESRS = {"0": 0, "10m": 0.010, "500m": 0.500}
CORNERS = {"tt": [("tt", 27.0)], "pvt": adaptive.PVT_CORNERS}
MECHANISM = (
    "Split R_CZ into 26 and 806 µm xhigh_po sections and shunt the longer section with 18 pF. "
    "Below the nominal 1.9 kHz bypass pole the series length approaches the 832 µm "
    "light-load repair. Above the pole the bypass impedance falls toward a 26 µm residual. "
    "The lower crossover at 4.7 µF should retain more resistance in the 10–300 µA band. "
    "The faster 0.33 µF loop should see less, including at 50 mA. "
    "The passive branch uses no switch, bias current source or CL_SNS connection."
)


def variant(body, design):
    if design == "baseline":
        return body
    if design != "shelf":
        raise ValueError(design)
    original = "XR_CZ EA_CZ EA_OUT 0 sky130_fd_pr__res_xhigh_po W=0.42 L=52 mult=1 m=1"
    if body.splitlines().count(original) != 1:
        raise ValueError("production R_CZ has changed; recheck the candidate")
    return fc.sub_line(
        body,
        "XR_CZ",
        "\n".join(
            (
                original.replace("EA_OUT", "RZ_MID").replace("L=52", "L=26"),
                original.replace("XR_CZ EA_CZ", "XR_EXT RZ_MID").replace(
                    "L=52", "L=806"
                ),
                "C_BYP RZ_MID EA_OUT 18p",
            )
        ),
    )


def grid(stage):
    return itertools.product(
        ("0.33u", "4.7u"), ESRS if stage == "tt" else ("10m",), LOADS
    )


def key_for(stage, design, cap, esr, load):
    return f"{stage}__{design}__{cap}_{esr}_{load}"


def write_request(out, pdk, key, body, corners, shape):
    net = out / "requests" / f"{key}.spice"
    net.write_text(fc.deck(body, adaptive.VSUP))
    req = fc.base_request(net.resolve(), pdk, corners, shape=shape)
    path = net.with_suffix(".json")
    path.write_text(json.dumps(req, indent=2) + "\n")
    return key, path


def ac_requests(out, pdk, body, stage, design):
    probed = fc.insert_loop_gain_probe(variant(body, design))
    shape = {
        "analysis": {"kind": "ac", "args": "dec 30 1e-2 1e9"},
        "measurements": fc.LOOP_TRANSFER_MEAS,
    }
    jobs = []
    for cap, esr, load in grid(stage):
        b = fc.sub_line(probed, "COUT", f"COUT VOUT VESR {cap} m=1")
        b = fc.sub_line(b, "HESR", f"HESR VESRS 0 VESRSENSE {ESRS[esr]:g}")
        b = fc.sub_line(b, "RLOAD", f"RLOAD VOUT 0 {LOADS[load]} m=1")
        jobs.append(
            write_request(
                out,
                pdk,
                key_for(stage, design, cap, esr, load),
                b,
                CORNERS[stage],
                shape,
            )
        )
    return jobs


def survivor_requests(out, pdk, body, design):
    """Run paired Iq and both directions of the load step only after both AC gates."""
    b = fc.sub_line(variant(body, design), "HESR", "HESR VESRS 0 VESRSENSE 0.01")
    b = fc.sub_line(b, "COUT", "COUT VOUT VESR 4.7u m=1")
    steps = [
        {
            "name": "iq_" + load,
            "analysis": {"kind": "op", "args": ""},
            "alter": {"ILOAD": value},
            "measurements": [
                {"name": "ivin", "expr": "-i(vvin)", "unit": "A"},
                {"name": "vout", "expr": "v(vout)", "unit": "V"},
            ],
        }
        for load, value in (("0mA", 0), ("50mA", 0.05))
    ]
    jobs = [
        write_request(
            out,
            pdk,
            f"iq__{design}",
            fc.sub_line(b, "RLOAD", "ILOAD VOUT 0 DC 0"),
            adaptive.OP_CORNERS,
            {"analysis_steps": steps},
        )
    ]
    for case in ("r1to50mA", "f50to1mA"):
        lo, hi, rising = adaptive.TRAN_CASES[case]
        start, end = (lo, hi) if rising else (hi, lo)
        tran = fc.sub_line(
            b,
            "RLOAD",
            f"ILOAD VOUT 0 PULSE({start:g} {end:g} {adaptive.T_STEP:g} 1u 1u 1 2)",
        )
        steps = [
            {
                "name": "c" + cap.replace(".", "p"),
                "analysis": {"kind": "tran", "args": "0.5u 1m"},
                "alter": {"COUT": float(cap.replace("u", "e-6"))},
                "measurements": [
                    {"name": name, "spice": card}
                    for name, card in adaptive.tran_cards()
                ],
            }
            for cap, _ in adaptive.CAPS
        ]
        jobs.append(
            write_request(
                out,
                pdk,
                f"{case}__{design}",
                tran,
                adaptive.OP_CORNERS,
                {"analysis_steps": steps},
            )
        )
    return jobs


def response(out, key):
    path = out / "responses" / key / "klt.stdout"
    if path.exists() and path.stat().st_size:
        try:
            data = json.loads(path.read_text())
        except ValueError:
            return {"reason": "invalid klt response JSON"}
        if isinstance(data, dict):
            return data
    return {}


def corner_data(resp, process, temp):
    job = resp.get("environment", {}).get("remote", {}).get("job_id")
    matches = [
        c
        for c in resp.get("corners", [])
        if (c.get("process"), c.get("temperature_c")) == (process, temp)
    ]
    if len(matches) != 1:
        return (
            {},
            job,
            resp.get("reason") or ("duplicate corner" if matches else "missing corner"),
        )
    return matches[0], job, None if job else "missing fleet job ID"


def measurements(corner):
    values = {}
    for m in corner.get("measurements", []):
        name, v = m["name"], m.get("value")
        values[name] = (
            v
            if name not in values and m.get("status") == "pass" and is_finite_number(v)
            else None
        )
    return values


def margins(resp, process, temp):
    c, job, reason = corner_data(resp, process, temp)
    values = measurements(c)
    for diag in c.get("diagnostics", []):
        if diag.get("severity") == "error":
            reason = (
                reason or diag.get("message") or diag.get("code") or "error diagnostic"
            )
    if c.get("status") not in ("pass", "fail"):
        reason = reason or f"corner {c.get('status')}"
    pm, gm = values.get("pm"), values.get("gm")
    missing = [name for name, v in (("pm", pm), ("gm", gm)) if v is None]
    if missing:
        reason = reason or f"missing or invalid {', '.join(missing)}"
    return {"pm": pm, "gm": gm, "job_id": job, "reason": reason}


def ac_rows(out, stage, meta):
    rows = []
    for design, (cap, esr, load) in itertools.product(DESIGNS, grid(stage)):
        key = key_for(stage, design, cap, esr, load)
        resp = response(out, key)
        if "corners" not in resp:
            resp["reason"] = (
                resp.get("reason")
                or meta["errors"].get(key)
                or (
                    "preflight refused"
                    if meta["preflight"]["exit"]
                    else "no batch response"
                )
            )
        for process, temp in CORNERS[stage]:
            rows.append(
                {
                    "design": design,
                    "cap": cap,
                    "esr": esr,
                    "load": load,
                    "process": process,
                    "temp": temp,
                    **margins(resp, process, temp),
                }
            )
    return rows


def advance(rows, stage):
    """ac_rows enumerates every required baseline/candidate point, even when absent."""
    expected_per_design = sum(1 for _ in grid(stage)) * len(CORNERS[stage])
    return len(rows) == 2 * expected_per_design and all(
        not r["reason"]
        and (
            r["design"] == "baseline" or (r["pm"] >= fc.PM_MIN and r["gm"] >= fc.GM_MIN)
        )
        for r in rows
    )


def submit(jobs, out, env, workers):
    # Keep the batch helper's raw stdout/stderr. A refusal can be a JSON error
    # envelope without corners, which submit_all's progress formatter cannot consume.
    errors = {}

    def run(job):
        key, path = job
        result = fc.submit(key, path, out, env)
        resp = result.get("resp", {})
        if "corners" not in resp:
            return key, result.get("error") or str(resp.get("error", "missing corners"))
        return key, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for key, error in pool.map(run, jobs):
            if error:
                errors[key] = error
            print(f"{key} {'refused' if error else 'returned'}", flush=True)
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument(
        "--workers", type=int, choices=range(1, fc.MAX_WORKERS + 1), default=2
    )
    args = ap.parse_args()
    out = args.outdir.resolve()
    pdk, root, env = fc.preamble(args.workers, out)
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=fc.REPO, text=True
    ).strip()
    subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            sha,
            "--",
            "design",
            "sim/loop-gain/testbench",
            "sim/pdk.json",
            "sim/xschemrc",
        ],
        cwd=fc.REPO,
        check=True,
    )
    out.mkdir(parents=True, exist_ok=False)
    scratch = out / "preflight"
    scratch.mkdir()
    tool = subprocess.check_output(["klt", "--version"], text=True).strip()
    probe = subprocess.run(
        [sys.executable, str(HERE / "batch-preflight.py"), "--keep", "--json"],
        env={**env, "TMPDIR": str(scratch)},
        capture_output=True,
        text=True,
    )
    probe_text = probe.stdout + probe.stderr
    (scratch / "probe.txt").write_text(
        "\n".join(line.rstrip() for line in probe_text.splitlines()) + "\n"
    )
    info = next(
        (
            json.loads(s)
            for s in probe.stdout.splitlines()
            if s.startswith("{") and s.endswith("}")
        ),
        {
            "exit": probe.returncode or 1,
            "reason": "missing preflight report",
            "job_id": None,
        },
    )
    submission_ids = list(dict.fromkeys(JOB_ID_RE.findall(probe.stdout)))
    meta = {
        "preflight_submission_ids": submission_ids,
        "dut_sha": sha,
        "klt": tool,
        "mechanism": MECHANISM,
        "preflight": info,
        "errors": {},
    }

    def checkpoint():
        (out / "campaign.json").write_text(json.dumps(meta, indent=2) + "\n")

    checkpoint()
    if probe.returncode or info["exit"] or not info.get("job_id"):
        print(info.get("reason"), file=sys.stderr)
        return 1
    (out / "requests").mkdir()
    body = fc.netlist("tb_loop_gain", out / "requests", root)
    for stage in CORNERS:
        for design in DESIGNS:
            jobs = ac_requests(out, pdk, body, stage, design)
            meta["errors"].update(submit(jobs, out, env, args.workers))
            checkpoint()
        rows = ac_rows(out, stage, meta)
        if not advance(rows, stage):
            return int(any(r["reason"] for r in rows))
    for design in DESIGNS:
        meta["errors"].update(
            submit(survivor_requests(out, pdk, body, design), out, env, args.workers)
        )
        checkpoint()
    return int(bool(meta["errors"]))


if __name__ == "__main__":
    sys.exit(main())
