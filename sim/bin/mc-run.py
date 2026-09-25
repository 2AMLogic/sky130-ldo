#!/usr/bin/env python3
"""Monte Carlo (mismatch) runner for sky130-ldo, via `klt sim`'s native
`request.monte_carlo` support.

Netlists an xschem testbench (same convention as `corner-run.py`), wraps it
into a `klt sim` request that selects sky130A's per-instance mismatch
section (`tt_mm` -- see docs/cli/sim.md "Corner axes" in
2AMLogic/klayout-tools), re-runs it `--n` times with a fresh seeded
per-instance AGAUSS draw each time, and writes an append-only evidence
record under sim/<experiment-slug>/, in the same record-format family as
corner-run.py's PVT records (see sim/README.md).

Why `klt sim` instead of a bespoke MC loop (issue #19's Addendum, "two real
implementation options"): `klt sim`'s `monte_carlo` field already implements
a documented, reproducible seed contract (SHA-256-derived per-sample seeds,
never Python's salted `hash()`), per-measurement statistics (mean/stddev/
quantiles/sigma-window), and a per-family mismatch-activity report that
verifies which device families actually got per-instance variation instead
of assuming it -- reimplementing that in `corner-run.py` would duplicate
already-tested upstream machinery for no benefit. `corner-run.py` itself is
untouched; this is a separate script layered on top of the same PDK/git/
netlisting plumbing, imported directly.

Usage
-----
    sim/bin/mc-run.py sim/mc-output-accuracy --n 200 --seed 20260817

The runner never edits or deletes an existing record: it refuses to start if
the record id it would mint already exists on disk. Unlike corner-run.py's
per-corner .log evidence, an MC run's raw klt sim request/response JSON
*is* the append-only evidence (it fully pins reproducibility via the seed
contract) -- per-sample ngspice logs are not kept by default (`--keep-logs`
opts in), to avoid committing hundreds of near-duplicate log files for one
run.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _record_common import load_corner_run_module, render_record_footer, render_record_header

corner_run = load_corner_run_module(Path(__file__).resolve().parent)

HarnessError = corner_run.HarnessError
REPO_ROOT = corner_run.REPO_ROOT
BUILD_DIR = corner_run.BUILD_DIR


# --------------------------------------------------------------------------
# experiment manifest (MC-flavored: no PVT corners/quick_subset, instead a
# single mismatch-enabled corner point plus a monte_carlo/analysis/
# measurements block that maps ~1:1 onto a klt sim request)
# --------------------------------------------------------------------------


def load_mc_experiment(path: Path) -> dict:
    exp_dir = path.resolve()
    manifest = exp_dir / "experiment.json"
    if not manifest.is_file():
        raise HarnessError(f"no experiment.json in {exp_dir}")
    raw = json.loads(manifest.read_text())
    for key in ("slug", "claim", "schematic", "mc_corner", "mc_analysis", "mc_measurements"):
        if key not in raw:
            raise HarnessError(f"{manifest}: missing required key {key!r}")
    schematic = (exp_dir / raw["schematic"]).resolve()
    if not schematic.is_file():
        raise HarnessError(f"{manifest}: schematic not found: {schematic}")
    raw["_dir"] = exp_dir
    raw["_schematic"] = schematic
    return raw


def klt_binary() -> str:
    exe = shutil.which("klt")
    if not exe:
        raise HarnessError(
            "klt not found on PATH; install klayout-tools "
            "(https://github.com/2AMLogic/klayout-tools) to run Monte Carlo experiments"
        )
    return exe


def build_klt_netlist(exp: dict, netlist: Path) -> list[str]:
    """The klt-sim-ready circuit body: corner-run.py's netlist_body() plus a
    default `.param vsup=...` (klt's `alter` only *modifies* a `.param` the
    body already defines; a bare `'vsup'` source reference alone is not
    enough) and an explicit `.save all` (the schematic's own per-source
    `.save i(...)` lines otherwise restrict ngspice's saved-vector set,
    silently dropping v(vout) -- the same reason corner-run.py's own deck
    always opens with `save all`).
    """
    body = corner_run.netlist_body(netlist)
    vsup_default = exp["mc_corner"].get("vsup")
    prefix = [".save all"]
    if vsup_default is not None:
        prefix = [f".param vsup={vsup_default}"] + prefix
    return prefix + body


def build_klt_request(
    exp: dict,
    pdk,
    netlist_path: Path,
    n: int,
    seed: int,
    vary: str,
    k_sigma: float,
    timeout_s: int,
    keep_artifacts: bool,
) -> dict:
    corner = exp["mc_corner"]
    return {
        "netlist": str(netlist_path),
        "engine": "ngspice",
        "models": {
            "pdk": pdk.variant,
            "lib": str(pdk.lib_file.relative_to(pdk.dir)),
        },
        "corners": {
            "process": [corner["process"]],
            "temperature_c": [corner.get("temperature_c", 27)],
        },
        "monte_carlo": {"n": n, "seed": seed, "vary": vary, "k_sigma": k_sigma},
        "analysis": dict(exp["mc_analysis"]),
        "measurements": [dict(m) for m in exp["mc_measurements"]],
        "options": {"timeout_s": timeout_s, "keep_artifacts": keep_artifacts},
    }


def run_klt_sim(
    request_path: Path,
    outdir: Path,
    backend: str,
    max_workers: int,
) -> dict:
    cmd = [
        klt_binary(),
        "sim",
        str(request_path),
        "-o",
        str(outdir),
        "--backend",
        backend,
        "--format",
        "json",
    ]
    if backend == "local-parallel":
        cmd += ["--max-workers", str(max_workers)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=None)
    if not proc.stdout.strip():
        raise HarnessError(
            "klt sim produced no stdout\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  rc: {proc.returncode}\n"
            f"  stderr: {proc.stderr.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise HarnessError(
            f"klt sim produced non-JSON stdout ({exc})\n  stdout: {proc.stdout[:2000]}"
        ) from exc


# --------------------------------------------------------------------------
# record rendering
# --------------------------------------------------------------------------


def nominal_vs_spread(values: list, limits: dict) -> dict | None:
    """Split one measurement's per-sample values into the in-window
    subpopulation and everything else, so a record can say *why* it failed.

    A statistical (Monte Carlo) row can miss its window two very different
    ways, and the aggregate `k pass / m fail` count cannot tell them apart:

    * **Spread** — the population is one distribution, centred where it
      should be (or not), whose tails simply reach past the window. Then the
      out-of-window samples sit *contiguous* with the in-window tail, a
      fraction of a sigma beyond the edge, and sizing devices for matching
      (or re-centring the nominal point) is the lever that moves them.
    * **A second mode** — most samples regulate and a minority land somewhere
      else entirely, many sigma away with an empty gap in between. Matching
      is then the wrong lever: no plausible sizing change closes a gap that
      is orders of magnitude wider than the distribution's own width.

    Returns `None` when the split is not computable (no two-sided window, or
    fewer than two in-window samples to take a stddev from).
    """
    lo, hi = limits.get("min"), limits.get("max")
    if lo is None or hi is None:
        return None
    vals = [v for v in values if v is not None]
    inside = [v for v in vals if lo <= v <= hi]
    outside = [v for v in vals if not (lo <= v <= hi)]
    if len(inside) < 2:
        return None
    mean = statistics.fmean(inside)
    sd = statistics.stdev(inside)
    centre = (lo + hi) / 2.0
    out = {
        "n_valued": len(vals),
        "n_inside": len(inside),
        "n_outside": len(outside),
        "inside_mean": mean,
        "inside_stddev": sd,
        "window_centre": centre,
        "centre_offset": mean - centre,
        "centre_offset_frac": (mean - centre) / centre if centre else None,
        # How far the *window* edge is from the in-window subpopulation, in
        # that subpopulation's own sigma: the yield this distribution alone
        # would give if nothing else were going on.
        "edge_sigma": (min(mean - lo, hi - mean) / sd) if sd > 0 else None,
        # How far the nearest out-of-window sample is *past* the window edge,
        # in the same sigma. Small (order 1) => contiguous tail => spread.
        # Large => a separate mode => a different mechanism.
        "gap_sigma": None,
        "outside_min": min(outside) if outside else None,
        "outside_max": max(outside) if outside else None,
    }
    if outside and sd > 0:
        out["gap_sigma"] = min((lo - v) if v < lo else (v - hi) for v in outside) / sd
    return out


def render_nominal_vs_spread(nvs: dict) -> list[str]:
    """The `- Nominal-vs-spread decomposition` bullets for one measurement."""
    pct = (
        f"{nvs['centre_offset_frac'] * 100:+.3f} %"
        if nvs["centre_offset_frac"] is not None
        else "n/a"
    )
    lines = [
        "    - Nominal-vs-spread decomposition (computed by `mc-run.py` from the "
        "per-sample values in the klt response — see that function's docstring for "
        "how to read it):"
    ]
    lines.append(
        f"      - in-window subpopulation: n={nvs['n_inside']} of {nvs['n_valued']} "
        f"valued samples, mean={nvs['inside_mean']:.6g}, stddev={nvs['inside_stddev']:.6g}"
    )
    lines.append(
        f"      - nominal (centring) error: mean is {nvs['centre_offset']:+.6g} from the "
        f"window centre {nvs['window_centre']:.6g} ({pct} of centre)"
    )
    if nvs["edge_sigma"] is not None:
        lines.append(
            f"      - spread vs the window: the nearer window edge is "
            f"{nvs['edge_sigma']:.3g}σ from that subpopulation's mean"
        )
    if nvs["n_outside"]:
        gap = (
            f"{nvs['gap_sigma']:.4g}σ past the window edge"
            if nvs["gap_sigma"] is not None
            else "n/a"
        )
        verdict = (
            "contiguous with the in-window tail — reads as **spread** (matching/centring)"
            if nvs["gap_sigma"] is not None and nvs["gap_sigma"] <= 3
            else "**not** contiguous with the in-window tail — reads as a **separate mode**, "
            "i.e. a different mechanism than matching spread"
        )
        lines.append(
            f"      - out-of-window samples: n={nvs['n_outside']}, "
            f"min={nvs['outside_min']:.6g}, max={nvs['outside_max']:.6g}; "
            f"nearest is {gap} — {verdict}"
        )
    else:
        lines.append("      - out-of-window samples: none")
    return lines


def render_execution_backend(record: dict) -> list[str]:
    """`- **Execution backend**: ...` — where the samples actually ran.

    The `- **Tools**:` line above reports *this* machine's toolchain, which is
    the toolchain that ran the samples only for the `local`/`local-parallel`
    backends. On `remote`/`batch` the samples run on someone else's host with
    its own ngspice build, so the record must say so verbatim (and name the
    engine version klt reports from there) rather than letting the local
    version stand as the provenance of a number it did not produce.
    """
    r = record
    backend = r.get("backend", "local-parallel")
    env = (r.get("klt_response") or {}).get("environment") or {}
    engine = env.get("engine", "?")
    engine_version = env.get("engine_version", "?")
    lines = [
        f"- **Execution backend**: `{backend}` — samples executed by "
        f"{engine} {engine_version} as reported by `klt sim`"
        + (
            " (this machine)"
            if backend in ("local", "local-parallel")
            else " **on the remote executor, not this machine**"
        )
    ]
    remote = env.get("remote") or {}
    if remote:
        detail = ", ".join(
            f"{k}=`{remote[k]}`"
            for k in ("provider", "job_id", "instance_type", "lifecycle", "region", "elapsed_seconds")
            if remote.get(k) is not None
        )
        lines.append(f"  - Remote job: {detail}")
        lines.append(
            "  - The remote executor resolves its own PDK copy; `klt sim`'s own "
            f"provenance block records it as `{(r.get('klt_response') or {}).get('provenance', {}).get('pdk', {}).get('version', 'unknown')}` "
            "— compare that against the **PDK** line above, which is this machine's install."
        )
    return lines


def fmt_or_na(value, label: str) -> str:
    """`label=<6sig>` for a real number, `label=n/a` for a missing one."""
    return f"{label}=n/a" if value is None else f"{label}={value:.6g}"


def render_record(record: dict) -> str:
    r = record
    resp = r["klt_response"]
    tools = r["tools"]
    tools_line = (
        f"{tools['ngspice']}; {tools['xschem']}; klt {r['klt_version']}; {tools['platform']}"
        f"; klt sim backend `{r.get('backend', 'local-parallel')}`"
    )
    lines = render_record_header(r, tools_line)
    lines.extend(render_execution_backend(r))

    corner = r["mc_corner"]
    lines.append("- **Corner matrix run**:")
    lines.append(
        f"  - Single mismatch-enabled point (not a PVT sweep — see Statistical "
        f"convention below): process `{corner['process']}`, {corner.get('temperature_c', 27)} °C"
        + (f", vsup default {corner['vsup']} V" if corner.get("vsup") is not None else "")
    )
    lines.append(
        "  - **Not the full PVT matrix** — a Monte Carlo mismatch run samples device "
        "variation at one representative process/temperature/supply point per run, "
        "orthogonal to the PVT axis corner-run.py sweeps; see `sim/README.md`."
    )
    mc = r["monte_carlo_request"]
    lines.append(
        f"- **Statistical convention**: N={mc['n']} Monte Carlo samples, "
        f"vary=`{mc['vary']}`, seed=`{mc['seed']}` (klt sim's SHA-256-derived, "
        f"reproducible seed contract — same seed reproduces the same sample "
        f"sequence), k_sigma={mc['k_sigma']} (mean ± k·stddev limit-window check)"
    )

    lines.append("- **Result**:")
    lines.append(f"  - klt sim aggregate status: **{resp['status'].upper()}** "
                  f"({resp['passed']} pass / {resp['failed']} fail / {resp['errored']} error "
                  f"of {resp['corner_count']} samples)")
    for meas in resp.get("measurements", []):
        mcstat = meas.get("monte_carlo") or {}
        limits = meas.get("limits") or {}
        lim_str = ", ".join(
            f"{k}={v:g}" for k, v in (("min", limits.get("min")), ("max", limits.get("max"))) if v is not None
        )
        lines.append(
            f"  - `{meas['name']}` ({meas['unit']}, limits: {lim_str or 'none'}): "
            f"**{meas['status'].upper()}**"
        )
        if mcstat:
            lines.append(
                f"    - n={mcstat['n']} (errored={mcstat['errored']}), "
                f"mean={mcstat['mean']:.6g}, stddev={mcstat['stddev']:.6g}, "
                f"min={mcstat['min']:.6g}, max={mcstat['max']:.6g}"
            )
            q = mcstat.get("quantiles") or {}
            if q:
                lines.append(
                    "    - quantiles: " + ", ".join(f"{k}={v:.6g}" for k, v in q.items())
                )
            sw = mcstat.get("sigma_window")
            if sw:
                lines.append(
                    f"    - sigma_window (k={sw['k']:g}): [{sw['low']:.6g}, {sw['high']:.6g}] "
                    f"— **{sw['status'].upper()}** (margin {sw['margin']:.6g})"
                )
        per_sample = [
            m["value"]
            for c in resp.get("corners", [])
            for m in c.get("measurements", [])
            if m.get("name") == meas["name"]
        ]
        nvs = nominal_vs_spread(per_sample, limits)
        if nvs:
            lines.extend(render_nominal_vs_spread(nvs))
        wc = meas.get("worst_case") or {}
        if wc:
            # An errored sample has no value/margin at all -- klt reports it as the
            # worst case with `null` fields. Render that honestly instead of
            # crashing the record writer (a crash loses the whole record even
            # though the raw klt response has already been written to disk).
            lines.append(
                f"    - worst single sample: `{wc['corner_id']}` "
                + fmt_or_na(wc.get("value"), "value")
                + " "
                + fmt_or_na(wc.get("margin"), "margin")
                + (
                    " — this sample **errored** (no measurement produced); see the raw "
                    "klt response for its diagnostics"
                    if wc.get("value") is None
                    else ""
                )
            )

    fam = (resp.get("environment", {}).get("monte_carlo") or {}).get("family_mismatch") or []
    if fam:
        lines.append("  - Per-family mismatch-activity report (klt sim, from the netlist's own "
                      "device instances):")
        for f in fam:
            active = "unconfirmed" if f["active"] is None else ("ACTIVE" if f["active"] else "inactive")
            lines.append(f"    - `{f['family']}`: {active} — {f['note']}")

    lines.append(f"  - **Overall: {resp['status'].upper()}**")

    lines.append("- **Links**:")
    lines.append(f"  - Testbench: `{r['links']['testbench']}`")
    lines.append(f"  - Netlist snapshot (klt-sim-ready): `{r['links']['netlist_snapshot']}`")
    lines.append(f"  - klt sim request: `{r['links']['klt_request']}`")
    lines.append(f"  - klt sim response (raw, full per-sample data): `{r['links']['klt_response']}`")
    lines.append(f"  - Machine-readable record: `{r['links']['json']}`")
    lines.append(f"  - Experiment manifest: `{r['links']['manifest']}`")
    lines.extend(render_record_footer(r, "mc-run.py"))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Monte Carlo (mismatch) runner for sky130-ldo via `klt sim` (see sim/README.md)"
    )
    p.add_argument("experiment", help="path to sim/<experiment-slug>/")
    p.add_argument("--n", type=int, help="samples (default: manifest monte_carlo_defaults.n)")
    p.add_argument("--seed", type=int, required=True, help="base seed (recorded verbatim; required)")
    p.add_argument("--vary", default="", help="default: manifest monte_carlo_defaults.vary")
    p.add_argument("--k-sigma", type=float, default=None, help="default: manifest monte_carlo_defaults.k_sigma")
    p.add_argument(
        "--backend",
        default="local-parallel",
        choices=["local", "local-parallel", "remote", "batch"],
        help=(
            "klt sim execution backend. `local`/`local-parallel` run ngspice on this "
            "machine; `remote`/`batch` hand the expanded sample grid to klt's own "
            "remote/EC2-batch backends (see docs/cli/sim.md in 2AMLogic/klayout-tools). "
            "A shared dispatch host that forbids hand-launched local ngspice grids "
            "needs `--backend batch` here — the local-parallel default is a local grid."
        ),
    )
    p.add_argument("--max-workers", type=int, default=8)
    p.add_argument("--timeout", type=int, default=180, help="per-sample ngspice timeout (s)")
    p.add_argument("--keep-logs", action="store_true", help="keep klt's per-sample logs (options.keep_artifacts)")
    p.add_argument("--supersedes", default="", help="record id this run supersedes")
    p.add_argument("--author", default="", help="record author (default: git user.email)")
    p.add_argument(
        "--allow-pdk-mismatch",
        action="store_true",
        help="run even if the installed PDK differs from the sim/pdk.json pin",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="netlist and print the klt sim request, run nothing, write nothing",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    pin = corner_run.load_pin()
    pdk = corner_run.resolve_pdk(pin)

    if not pdk.matches_pin and not args.allow_pdk_mismatch:
        raise HarnessError(
            f"installed PDK {pdk.variant} is open_pdks {pdk.installed_commit}, "
            f"but sim/pdk.json pins {pin['open_pdks_commit']}\n"
            f"  install the pin: {pin['install_command']}\n"
            f"  or re-run with --allow-pdk-mismatch (the record will say so)"
        )

    exp = load_mc_experiment(Path(args.experiment))
    defaults = exp.get("monte_carlo_defaults", {})
    n = args.n or defaults.get("n")
    vary = args.vary or defaults.get("vary", "mismatch")
    k_sigma = args.k_sigma if args.k_sigma is not None else defaults.get("k_sigma", 3)
    if not n:
        raise HarnessError("--n not given and no monte_carlo_defaults.n in experiment.json")

    klt_binary()  # fail fast if klt is missing

    git_info = corner_run.git_state()
    now = datetime.now(timezone.utc)
    record_id = f"{now:%Y%m%d}-{now:%H%M%S}-{git_info['sha']}"

    records_dir = exp["_dir"] / "records"
    snapshots_dir = exp["_dir"] / "netlist-snapshots"
    requests_dir = exp["_dir"] / "klt-requests"
    responses_dir = exp["_dir"] / "klt-responses"
    record_md = records_dir / f"{record_id}.md"
    record_json = records_dir / f"{record_id}.json"
    snapshot = snapshots_dir / f"{record_id}.spice"
    request_file = requests_dir / f"{record_id}.json"
    response_file = responses_dir / f"{record_id}.json"

    if not args.dry_run:
        for path in (record_md, record_json, snapshot, request_file, response_file):
            if path.exists():
                raise HarnessError(
                    f"{path} already exists — sim/ is append-only, refusing to overwrite"
                )

    run_dir = BUILD_DIR / exp["slug"] / record_id
    run_dir.mkdir(parents=True, exist_ok=True)

    netlist = corner_run.netlist_with_xschem(exp["_schematic"], run_dir, pdk)
    body = build_klt_netlist(exp, netlist)
    prepped_netlist_text = "\n".join(body) + "\n"

    print(f"experiment      : {exp['slug']}")
    print(f"record id       : {record_id}")
    print(f"PDK             : {pdk.dir} (open_pdks {pdk.installed_commit})")
    print(f"testbench       : {exp['_schematic'].relative_to(REPO_ROOT)}")
    print(f"MC samples      : {n} (vary={vary}, seed={args.seed}, k_sigma={k_sigma})")
    print(f"backend         : {args.backend}")

    if args.dry_run:
        scratch_netlist = run_dir / "mc_body.spice"
        scratch_netlist.write_text(prepped_netlist_text)
        req = build_klt_request(
            exp, pdk, scratch_netlist, n, args.seed, vary, k_sigma, args.timeout, args.keep_logs
        )
        print("\n-- klt sim request (dry run) --")
        print(json.dumps(req, indent=2))
        print("\n(dry run: klt sim not invoked, nothing written under sim/<experiment>/)")
        return 0

    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(prepped_netlist_text)

    request = build_klt_request(
        exp, pdk, snapshot.resolve(), n, args.seed, vary, k_sigma, args.timeout, args.keep_logs
    )
    requests_dir.mkdir(parents=True, exist_ok=True)
    request_file.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")

    klt_outdir = run_dir / "klt-out"
    response = run_klt_sim(request_file, klt_outdir, args.backend, args.max_workers)

    responses_dir.mkdir(parents=True, exist_ok=True)
    response_file.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n")

    overall_pass = response.get("status") == "pass"

    record = {
        "record_id": record_id,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "author": args.author or corner_run.default_author(),
        "supersedes": args.supersedes,
        "experiment": {
            "slug": exp["slug"],
            "title": exp.get("title", exp["slug"]),
            "claim": exp["claim"],
            "provenance": exp.get("provenance", "schematic"),
            "provenance_source": exp.get(
                "provenance_source", str(exp["_schematic"].relative_to(REPO_ROOT))
            ),
        },
        "pdk": {
            "root": str(pdk.root),
            "variant": pdk.variant,
            "installed_commit": pdk.installed_commit,
            "pinned_commit": pin["open_pdks_commit"],
            "matches_pin": pdk.matches_pin,
            "lib_file": str(pdk.lib_file),
        },
        "tools": corner_run.tool_versions(),
        "klt_version": response.get("provenance", {}).get("klt_version", "unknown"),
        "backend": args.backend,
        "git": git_info,
        "mc_corner": exp["mc_corner"],
        "monte_carlo_request": request["monte_carlo"],
        "klt_request": request,
        "klt_response": response,
        "overall_pass": overall_pass,
        "links": {
            "testbench": str(exp["_schematic"].relative_to(REPO_ROOT)),
            "manifest": str((exp["_dir"] / "experiment.json").relative_to(REPO_ROOT)),
            "netlist_snapshot": str(snapshot.relative_to(REPO_ROOT)),
            "klt_request": str(request_file.relative_to(REPO_ROOT)),
            "klt_response": str(response_file.relative_to(REPO_ROOT)),
            "json": str(record_json.relative_to(REPO_ROOT)),
            "record": str(record_md.relative_to(REPO_ROOT)),
        },
    }

    records_dir.mkdir(parents=True, exist_ok=True)
    record_json.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    record_md.write_text(render_record(record))

    print()
    print(f"record   : {record_md.relative_to(REPO_ROOT)}")
    print(f"json     : {record_json.relative_to(REPO_ROOT)}")
    print(f"response : {response_file.relative_to(REPO_ROOT)}")
    print(f"overall  : {'PASS' if overall_pass else 'FAIL'}")
    return 0 if overall_pass else 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except HarnessError as err:
        print(f"mc-run: error: {err}", file=sys.stderr)
        sys.exit(1)
