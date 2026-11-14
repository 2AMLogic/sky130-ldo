"""Shared batch-fleet campaign core for the `sim/bin/` `klt sim --backend batch`
drivers (issue #574).

`bias-retopo-pvt.py` (#467 / DR-013), `rcz-fleet-confirm.py` (#370 stage 1),
`rcz-adaptive-370.py` (#370 stage 2) and `bias-retopo-grid.py` (#467 / DR-013, folded
on by #586) all express a campaign the same way: netlist one testbench schematic once
(or, for the bias grid, write a small hand-built deck), text-edit a per-case variant
of that body, write one `klt sim` request per case, then submit every request to the
batch fleet with NO local fallback (host rule: a refused submit is reported, never
re-run as a local grid). That core was copy-pasted four times -- two of the drivers
even loaded `bias-retopo-pvt.py` through an importlib-by-path dance just to reach it,
and the copies had already drifted. This module is the single copy.

Pure extraction, no behaviour change: every request each driver writes is
byte-identical to the one it wrote before (verified with a request-only comparison
of the whole `requests/` tree -- netlisting is a single local `klt netlist`, and
nothing is submitted; #586 pinned that for the bias grid against its committed
`requests/` as a test). The drivers keep their own script paths, CLIs, grids,
grading and record rendering.

Row shaping deliberately stays with each caller: the records' `summary.json`
formats differ (three flatten measurements into the row, one nests them under
`"measurements"`; the bias grid drops `key`, which its committed rows never
carried), and those records are append-only evidence, so a re-run must keep
emitting the format its own record family already uses. `submit_all()` yields the
raw response and `corner_base()` supplies only the fields they all share.

Standard library only, matching every other `sim/bin/` script's convention. Mirrors
the `sim/bin/_record_common.py` shared-helper convention (issues #46 / #51 / #96 /
#224 / #522), one module over.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
REPO = SIM.parent
if str(HERE) not in sys.path:  # so the sibling-module imports below resolve
    sys.path.insert(0, str(HERE))

from _record_common import klt_binary, run_klt_sim  # noqa: E402
from xschem_exprs import eval_xschem_exprs  # noqa: E402

# ngspice process-corner sections in the order the records tabulate them.
PROCESS = ["tt", "ss", "ff", "sf", "fs"]

# Host rule (see CLAUDE.md): this is a shared dispatch worker, not a sim box.
MAX_WORKERS = 2

# The loop-gain instrumentation: ONE linear VCVS added inside the LDO subckt, so
# that v(VREF) being the AC-1 injection makes v(LG_DEN) = 1 - v(fb) and the loop
# gain LG = v(fb)/(1-v(fb)) is the transfer v(fb)/v(lg_den). The VCVS draws no
# current, so it perturbs nothing else.
LOOP_GAIN_PROBE = "ELG_DEN LG_DEN 0 VREF FB 1"

# The four klt `transfer` metrics of that loop gain. Read-only: callers embed it
# in a request and never mutate it.
LOOP_TRANSFER_MEAS = [
    {
        "name": n,
        "unit": u,
        "transfer": {"num": "v(xldo.fb)", "den": "v(xldo.lg_den)", "metric": m},
    }
    for n, m, u in (
        ("pm", "phase_margin_deg", "deg"),
        ("gm", "gain_margin_db", "dB"),
        ("fc", "unity_crossing_hz", "Hz"),
        ("dc", "low_frequency_magnitude", ""),
    )
]


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def preamble(
    workers: int, out: Path, allow_existing: bool = False
) -> tuple[dict, str, dict]:
    """The campaign preamble every driver opens with.

    Enforces the host worker cap, refuses to overwrite an existing record
    (`sim/` is append-only evidence; `allow_existing` is for a `--resume` that
    continues an interrupted run in place), then returns
    `(pdk.json contents, PDK_ROOT, child environment)`.
    """
    if workers > MAX_WORKERS:
        sys.exit(f"host rule: no more than {MAX_WORKERS} workers")
    if out.exists() and not allow_existing:
        sys.exit(f"refusing to overwrite existing record {out}")
    pdk = json.loads((SIM / "pdk.json").read_text())
    pdk_root = os.environ.get("PDK_ROOT") or str(Path.home() / ".volare")
    return pdk, pdk_root, {**os.environ, "PDK_ROOT": pdk_root}


def netlist(tb: str, outdir: Path, pdk_root: str, patch: Path | None = None) -> str:
    """Netlist testbench `tb` and return its body (repo-relative, no `.end`).

    `patch`, when given, is a candidate patch applied to the repo for netlisting
    only and reverted afterwards (the production schematic is never left edited).
    The raw `klt netlist` output lands in `outdir` and is removed again before
    returning -- every caller deleted it immediately; only the body is used.
    """
    raw = outdir / f"{tb}.raw.spice"
    if patch is not None:
        p = run(["git", "-C", str(REPO), "apply", str(patch)])
        if p.returncode:
            sys.exit(f"cannot apply candidate patch: {p.stderr}")
    try:
        p = run(
            [
                "klt",
                "netlist",
                "--allow-unevaluated-expr",
                "--rcfile",
                str(SIM / "xschemrc"),
                "--pdk",
                "sky130A",
                "--pdk-root",
                pdk_root,
                "-o",
                str(raw),
                str(
                    SIM
                    / tb.replace("tb_", "").replace("_", "-")
                    / "testbench"
                    / f"{tb}.sch"
                ),
            ]
        )
        if p.returncode:
            sys.exit(f"klt netlist failed: {p.stdout} {p.stderr}")
    finally:
        if patch is not None:
            run(["git", "-C", str(REPO), "apply", "-R", str(patch)])
    text = raw.read_text().replace(str(REPO) + os.sep, "")
    raw.unlink()
    text, _ = eval_xschem_exprs(text)
    if "expr(" in text:
        sys.exit("unevaluated expr() left in netlist")
    return (
        "\n".join(ln for ln in text.splitlines() if ln.strip().lower() != ".end") + "\n"
    )


def sub_line(body: str, prefix: str, new: str) -> str:
    """Rewrite the single card whose first token is `prefix` (the local `alter`
    cards, expressed as a netlist edit); exits if it is not found exactly once."""
    out, n = [], 0
    for ln in body.splitlines():
        if ln.split(" ")[0].upper() == prefix:
            ln, n = new, n + 1
        out.append(ln)
    if n != 1:
        sys.exit(f"expected exactly one {prefix} line, found {n}")
    return "\n".join(out) + "\n"


def insert_in_subckt(body: str, line: str) -> str:
    """Insert `line` just before the last `.ends` -- i.e. inside the LDO subckt."""
    lines = body.splitlines()
    i = max(k for k, ln in enumerate(lines) if ln.strip().lower().startswith(".ends"))
    lines.insert(i, line)
    return "\n".join(lines) + "\n"


def insert_loop_gain_probe(body: str) -> str:
    """Add the `LOOP_GAIN_PROBE` VCVS inside the LDO subckt (instrumentation only)."""
    return insert_in_subckt(body, LOOP_GAIN_PROBE)


def deck(body: str, vsup: float) -> str:
    """Wrap a netlist body as a runnable deck at supply `vsup`.

    The banner is deliberately left at its original wording: these decks are
    quoted verbatim inside committed append-only records, so re-wording it would
    make a re-run's `requests/` tree differ from the records' for no gain.
    """
    return f"* DR-013 candidate PVT bench (issue #467)\n.param vsup={vsup}\n.option wnflag=1\n{body}.end\n"


def base_request(
    net: Path,
    pdk: dict,
    corners: list[tuple[str, float]],
    analysis: dict | None = None,
    meas: list | None = None,
    shape: dict | None = None,
    order: list[str] | None = None,
) -> dict:
    """One `klt sim` batch request over `corners` (a list of `(process, temp_C)`).

    By default the request carries a single `analysis` + `measurements` pair.
    Pass `shape` instead for a different analysis shape (e.g. `analysis_steps`):
    it replaces that pair and is merged in after `options`/`batch`, which is
    exactly where the callers' former `req.pop(...)` + `req.update(shape)`
    workaround left it, so the emitted JSON is unchanged.

    `order` is the process-section ordering the request tabulates, defaulting to
    `PROCESS`. A campaign whose grid is a deliberate superset of `PROCESS` passes
    its own ordering -- `bias-retopo-grid.py` adds the resistor-only skew corners
    `ll`/`hh`, which `pdk.json`'s `process_corners` declares but the MOS-corner
    campaigns do not run. The ordering must cover every process in `corners`;
    a process missing from it is named rather than left to raise from `.index`.
    """
    order = PROCESS if order is None else order
    unknown = sorted({p for p, _ in corners} - set(order))
    if unknown:
        sys.exit(f"process corner(s) {unknown} are not in the ordering {order}")
    procs = sorted({p for p, _ in corners}, key=order.index)
    temps = sorted({t for _, t in corners})
    req: dict = {
        "netlist": str(net),
        "engine": "ngspice",
        "models": {"pdk": pdk["variant"], "lib": pdk["ngspice_lib"]},
        "corners": {"process": procs, "temperature_c": temps},
    }
    if shape is None:
        req["analysis"] = analysis
        req["measurements"] = meas
    req["options"] = {"timeout_s": 300, "keep_artifacts": True}
    req["batch"] = {"capacity_wait_s": 3 * 3600}
    if shape is not None:
        req.update(shape)
    return req


def submit(key: str, req_path: Path, out: Path, env: dict) -> dict:
    """Submit one request to the batch fleet; never falls back to a local run."""
    od = out / "responses" / key
    od.mkdir(parents=True)
    try:
        resp, _meta = run_klt_sim(
            req_path,
            od,
            "batch",
            env["PDK_ROOT"],
            klt_exe=klt_binary("submit batch grids"),
            require_corners=False,
        )
    except RuntimeError as exc:
        return {"key": key, "error": str(exc)[-1500:] or "no JSON from klt sim"}
    return {"key": key, "resp": resp}


def submit_all(
    jobs: list[tuple[str, dict, Path]],
    out: Path,
    env: dict,
    workers: int,
    errors: list,
) -> Iterator[tuple[str, dict, dict, str | None]]:
    """Submit every `(key, meta, request path)` job and yield one
    `(key, meta, response, job_id)` per request that came back.

    Submits run on a `ThreadPoolExecutor` of `workers` threads; results are
    consumed in job order so the caller's rows stay deterministic. A refused
    submit is NOT yielded: it is printed and appended to `errors` as
    `{"key": ..., "error": ...}`, and the campaign carries on -- there is no
    local fallback, so the caller reports the gap instead of filling it.
    """
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [(k, m, ex.submit(submit, k, rp, out, env)) for k, m, rp in jobs]
        for k, m, f in futs:
            r = f.result()
            if "error" in r:
                errors.append({"key": k, "error": r["error"]})
                print(
                    f"{k}: SUBMIT FAILED (no local fallback): {r['error'][:300]}",
                    flush=True,
                )
                continue
            resp = r["resp"]
            job = resp.get("environment", {}).get("remote", {}).get("job_id")
            print(
                f"{k}: {resp['status']} ({resp['corner_count']} corners) job {job}",
                flush=True,
            )
            yield k, m, resp, job


def corner_base(key: str, meta: dict, corner: dict, job: str | None) -> dict:
    """The row fields every driver records for one returned corner. Each caller
    merges its own measurement shaping on top (flattened or nested)."""
    return {
        **meta,
        "key": key,
        "process": corner["process"],
        "temp_c": corner["temperature_c"],
        "status": corner["status"],
        "job_id": job,
    }
