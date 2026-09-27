#!/usr/bin/env python3
"""Yield/statistical-capability runner for sky130-ldo, via `klt yield`
(issue #203).

What this is, and what it is not
--------------------------------
`klt yield` is a *derived* analysis: it re-reads the per-sample data in an
already-committed `klt sim --format json` Monte Carlo response and turns it
into a yield estimate with a confidence interval, a distribution/normality
fit, Cpk/sigma-to-spec, and a sample-size verdict (2AMLogic/klayout-tools
docs/cli/yield.md, epic #710). It runs **no** simulation, touches **no** PDK,
and cannot change a measured number -- which is exactly why this runner takes
an existing `klt-responses/<source-record-id>.json` as its input instead of
re-running a campaign. The tool version and host recorded below are therefore
the ones that did the *arithmetic*; the ngspice/PDK/host that produced the
samples are recorded separately, quoted from the source campaign's own
record.

This mirrors `sim/pex-post-layout/`'s convention of minting a derived `klt`
report as its own `klt-responses/<record-id>.<tool>.json` artifact alongside
a `records/<record-id>.{json,md}` summary, rather than inventing a second
evidence directory (see `sim/README.md` and `sim/pex-post-layout/README.md`).

Usage
-----
    sim/bin/yield-run.py \\
        sim/mc-output-accuracy/klt-responses/20260925-131502-808cece.json

`klt yield` requires a spec-limits document whenever the samples document
carries none of its own, and the document it is given **wins** over any the
samples carry -- so it is the explicit statement of what the analysis holds
the design to. By default this runner *derives* that document from the
experiment's own `experiment.json` (`mc_measurements[].limits`, the same
ratified window the campaign was requested against and the only place this
repo states it) rather than asking the caller to retype a ratified number: a
second hand-maintained copy of a spec bound is a drift hazard, and inventing
a bound the spec does not ratify is forbidden outright (see the repo's
CLAUDE.md, "The spec is a gate"). `--limits <file>` overrides that with an
explicit document when a run genuinely needs one.

Note what is deliberately *absent* from the derived document: a
`target_yield`. `spec/target-spec.md` ratifies no yield/sigma target for this
block, so none is asserted here; `klt yield` then reports
`status: "reported"` ("no measurement declared a target_yield, so no yield
claim was checked"), which is the honest shape rather than a pass engineered
against a number nobody ratified.

Either way the document is written to
`<experiment>/klt-requests/<record-id>.yield-limits.json` and `klt yield` is
invoked against **that** copy, so the minted report's own `limits` field
names a committed, append-only artifact rather than a scratch path. The
report is invoked from inside `klt-responses/`, so its `samples` field records
the source response by bare filename -- the path `klt signoff` resolves
report-relative when it hashes a yield citation's input (docs/cli/signoff.md,
"`klt yield` evidence and content hashing").

Like `mc-run.py`, this runner never edits or deletes an existing record: it
refuses to start if the record id it would mint already exists on disk.

A `status: "fail"` payload (some measurement's declared `target_yield` was
not supported at the stated confidence) is recorded, not suppressed -- the
verdict is whatever the tool says.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _record_common import git, render_record_footer  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


class HarnessError(RuntimeError):
    """A recoverable, explained failure (printed without a traceback)."""


# --------------------------------------------------------------------------
# environment
# --------------------------------------------------------------------------


def klt_binary() -> str:
    exe = shutil.which("klt")
    if not exe:
        raise HarnessError(
            "klt not found on PATH; install klayout-tools "
            "(https://github.com/2AMLogic/klayout-tools) to run a yield analysis"
        )
    return exe


def klt_version(exe: str) -> str:
    try:
        out = subprocess.run(
            [exe, "--version"], capture_output=True, text=True, timeout=60, check=True
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""
    # `klt --version` prints "klt <version>"; keep just the version so callers
    # can label it themselves without doubling the program name.
    parts = out.split()
    return parts[-1] if parts else ""


def native_extension_version(exe: str) -> str:
    """Version of `klt_yield_native`, the Rust extension that does the
    statistics, as installed in the interpreter that runs `klt`.

    `klt yield` refuses to run without it and it is not published as a wheel
    (it needs a repo checkout plus a Rust toolchain -- see
    docs/cli/yield.md#building-the-native-extension), so which build is
    installed is real provenance for the numbers below, and it appears in no
    field of the report itself. Resolved generically: a console script's
    first line is a `#!<interpreter>` shebang, so ask that interpreter. Any
    failure returns "" rather than raising -- this is provenance decoration,
    not a precondition.
    """
    try:
        first = Path(exe).read_text(errors="replace").splitlines()[0]
    except (OSError, IndexError):
        return ""
    if not first.startswith("#!"):
        return ""
    interpreter = first[2:].strip().split()[0]
    try:
        return subprocess.run(
            [
                interpreter,
                "-c",
                "import importlib.metadata as m; print(m.version('klt-yield-native'))",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# input resolution
# --------------------------------------------------------------------------


def resolve_samples(path: Path) -> tuple[Path, Path, str]:
    """(experiment dir, resolved samples path, source record id).

    The samples document must be an experiment's own committed
    `klt-responses/<record-id>.json`: that is what makes this analysis
    citable evidence about *this* repo's campaign rather than about a file
    someone had lying around.
    """
    samples = path.resolve()
    if not samples.is_file():
        raise HarnessError(f"samples document not found: {samples}")
    if samples.parent.name != "klt-responses":
        raise HarnessError(
            f"{samples} is not under a `klt-responses/` directory -- this runner "
            "analyses an experiment's own committed klt sim response (see the "
            "module docstring)"
        )
    exp_dir = samples.parent.parent
    if not (exp_dir / "experiment.json").is_file():
        raise HarnessError(f"no experiment.json in {exp_dir}")
    return exp_dir, samples, samples.stem


def derive_limits(exp: dict, args: argparse.Namespace) -> dict:
    """Build the `klt yield` spec-limits document from `experiment.json`.

    Single-sourced from `mc_measurements[].limits` -- the same block
    `mc-run.py` puts into the `klt sim` request, so the yield analysis is held
    to exactly the window the campaign was requested against. `target_yield`
    is never synthesised: this repo's spec ratifies none, and a limits file is
    not a place to invent one.
    """
    measurements: dict[str, dict] = {}
    for m in exp.get("mc_measurements") or []:
        limits = {
            k: v
            for k, v in (m.get("limits") or {}).items()
            if k in ("min", "max", "exclusive_min", "exclusive_max") and v is not None
        }
        if not ({"min", "max"} & set(limits)):
            continue
        measurements[m["name"]] = limits
    if not measurements:
        raise HarnessError(
            "experiment.json declares no mc_measurements[].limits with a min or "
            "max, so no spec-limits document can be derived -- pass --limits "
            "explicitly"
        )
    doc: dict = {
        "comment": [
            "Spec-limits document for `klt yield`, derived by sim/bin/yield-run.py",
            "from this experiment's own experiment.json (mc_measurements[].limits) --",
            "the same ratified window the klt sim campaign was requested against.",
            "",
            "No `target_yield` is declared: spec/target-spec.md ratifies no yield or",
            "sigma target for this block, and a ratified row that carries no number",
            "is left open rather than invented (CLAUDE.md, 'The spec is a gate').",
            "`klt yield` therefore reports rather than grades the estimates -- see",
            "the record this file was minted alongside.",
        ],
        "measurements": measurements,
    }
    if args.confidence is not None:
        doc["confidence"] = args.confidence
    if args.target_ci_halfwidth is not None:
        doc["target_ci_halfwidth"] = args.target_ci_halfwidth
    if args.min_samples is not None:
        doc["min_samples"] = args.min_samples
    return doc


def load_source_record(exp_dir: Path, source_record_id: str) -> dict:
    record = exp_dir / "records" / f"{source_record_id}.json"
    if not record.is_file():
        raise HarnessError(
            f"no summary record for the source campaign at {record} -- a yield "
            "analysis cites the campaign's record, not just its raw response"
        )
    return json.loads(record.read_text())


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------


def run_klt_yield(
    exe: str,
    responses_dir: Path,
    samples_name: str,
    limits_rel: str,
    args: argparse.Namespace,
) -> tuple[list[str], str, dict, int]:
    """Invoke `klt yield` from inside `klt-responses/`.

    Returns (command, raw stdout, parsed payload, exit code). The cwd matters: the
    report records `samples` exactly as invoked, and `klt signoff` resolves
    that path relative to the report's own directory first.
    """
    cmd = [exe, "yield", samples_name, "--limits", limits_rel]
    if args.confidence is not None:
        cmd += ["--confidence", str(args.confidence)]
    if args.target_ci_halfwidth is not None:
        cmd += ["--target-ci-halfwidth", str(args.target_ci_halfwidth)]
    if args.min_samples is not None:
        cmd += ["--min-samples", str(args.min_samples)]
    for name in args.measurement:
        cmd += ["--measurement", name]
    cmd += ["--format", "json"]

    proc = subprocess.run(
        cmd, cwd=str(responses_dir), capture_output=True, text=True, timeout=None
    )
    if not proc.stdout.strip():
        raise HarnessError(
            "klt yield produced no stdout\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  cwd: {responses_dir}\n"
            f"  rc: {proc.returncode}\n"
            f"  stderr: {proc.stderr.strip()}"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise HarnessError(
            f"klt yield produced non-JSON stdout ({exc})\n  stdout: {proc.stdout[:2000]}"
        ) from exc
    if "error" in payload:
        raise HarnessError(
            "klt yield refused to run: "
            f"{payload['error'].get('message', json.dumps(payload['error']))}"
        )
    return cmd, proc.stdout, payload, proc.returncode


# --------------------------------------------------------------------------
# record rendering
# --------------------------------------------------------------------------


def fmt_yield(block: dict) -> str:
    ci = block["confidence_interval"]
    return (
        f"{block['estimate'] * 100:.4f}% "
        f"(CI {ci['low'] * 100:.4f}%-{ci['high'] * 100:.4f}% "
        f"@ {block['confidence'] * 100:g}% confidence, n={block['n']}, "
        f"method `{block['method']}`)"
    )


def render_measurement(m: dict) -> list[str]:
    lines: list[str] = []
    limits = m.get("limits") or {}
    bound = ", ".join(
        f"{k}={limits[k]}" for k in ("min", "max", "target_yield") if limits.get(k) is not None
    )
    unit = f" {m['unit']}" if m.get("unit") else ""
    lines.append(f"  - `{m['name']}`{unit} (limits: {bound or 'none'}): **{m['status'].upper()}**")
    lines.append(
        f"    - n={m['n']} (errored={m.get('errored', 0)}, "
        f"failed_unmeasurable={m.get('failed_unmeasurable', 0)}); "
        f"source corners: {', '.join(m.get('source_corners') or []) or '(none recorded)'}"
    )

    y = m.get("yield") or {}
    if y.get("empirical"):
        lines.append(f"    - empirical yield: {fmt_yield(y['empirical'])}")
    if y.get("normal"):
        lines.append(f"    - normal-fit yield: {fmt_yield(y['normal'])}")
    if y.get("variance_reduced"):
        lines.append(f"    - variance-reduced yield: {fmt_yield(y['variance_reduced'])}")

    d = m.get("distribution") or {}
    if d:
        lines.append(
            f"    - distribution (`{d.get('model')}`): mean={d.get('mean'):.6g}, "
            f"stddev={d.get('stddev'):.6g}, min={d.get('min'):.6g}, "
            f"max={d.get('max'):.6g}, median={d.get('median'):.6g}, "
            f"skewness={d.get('skewness'):.4g}, "
            f"excess_kurtosis={d.get('excess_kurtosis'):.4g}"
        )
        norm = d.get("normality") or {}
        if norm:
            lines.append(
                f"    - normality (`{norm.get('test')}`): **{norm.get('verdict')}** "
                f"(statistic={norm.get('statistic'):.6g} vs critical "
                f"{norm.get('critical_value')} at significance {norm.get('significance')})"
            )

    c = m.get("capability") or {}
    if c:
        cpk_ci = c.get("cpk_confidence_interval") or {}
        sts_ci = c.get("sigma_to_spec_confidence_interval") or {}
        lines.append(
            f"    - capability: Cp={c.get('cp'):.6g}, Cpk={c.get('cpk'):.6g} "
            f"(CI {cpk_ci.get('low'):.6g}-{cpk_ci.get('high'):.6g}), "
            f"sigma-to-spec={c.get('sigma_to_spec'):.6g}sigma "
            f"(CI {sts_ci.get('low'):.6g}-{sts_ci.get('high'):.6g}); "
            f"limiting side: {c.get('limiting_side')}"
        )

    s = m.get("sample_size") or {}
    if s:
        required_for_target = s.get("required_n_for_target")
        lines.append(
            f"    - sample size: **{s.get('verdict')}** "
            f"(n={s.get('n')}, observed CI half-width="
            f"{s.get('observed_ci_halfwidth'):.6g} vs target "
            f"{s.get('target_ci_halfwidth')}, required_n={s.get('required_n')}"
            + (
                f", required_n_for_target={required_for_target}"
                if required_for_target is not None
                else ""
            )
            + f", method `{s.get('method')}`)"
        )

    sampling = m.get("sampling") or {}
    if sampling:
        lines.append(f"    - sampling strategy: `{sampling.get('strategy')}`")
    for extra, label in (("negative_control", "negative control"), ("analytic_cross_check", "analytic cross-check")):
        lines.append(
            f"    - {label}: {'present' if m.get(extra) else '**none declared**'}"
        )
    for warning in m.get("warnings") or []:
        lines.append(f"    - warning: {warning}")
    return lines


def render_record(record: dict) -> str:
    r = record
    report = r["klt_yield_report"]
    src = r["source_campaign"]

    lines = [f"# Record {r['record_id']}", ""]
    lines.append(f"- **Record ID**: {r['record_id']}")
    lines.append(f"- **Experiment**: `{r['experiment']['slug']}` — {r['experiment']['title']}")
    lines.append(f"- **Evidence kind**: `klt yield` report ({r['evidence_kind_note']})")
    lines.append(f"- **Claim**: {r['experiment']['claim']}")
    lines.append(
        f"- **Netlist provenance**: {r['experiment']['provenance']} "
        f"(`{r['experiment']['provenance_source']}`) — inherited from the source "
        f"campaign; this record adds no simulation of its own"
    )
    lines.append("- **Source campaign** (the samples this analysis re-reads):")
    lines.append(f"  - Record: `{src['record_id']}` (`{src['record']}`)")
    lines.append(f"  - Samples document: `{src['response']}`")
    lines.append(f"  - Samples document sha256: `{src['response_sha256']}`")
    lines.append(f"  - Netlist snapshot: `{src['netlist_snapshot']}`")
    lines.append(
        f"  - As that record reports it: {src['statistical_convention']}; "
        f"aggregate status **{src['status'].upper()}**"
    )
    lines.append(f"  - PDK it ran on: {src['pdk']}")
    lines.append(f"  - Tools that produced the samples: {src['tools']}")
    lines.append("- **Spec limits**:")
    lines.append(f"  - File: `{r['limits']['file']}`")
    lines.append(f"  - Origin: {r['limits']['origin']}")
    lines.append(
        f"  - Measurements: `"
        f"{json.dumps(r['limits']['document'].get('measurements'), sort_keys=True)}`"
    )
    lines.append(f"  - {r['limits']['note']}")
    lines.append(f"- **Tools**: {r['tools_line']}")
    lines.append(
        f"- **Repo state**: `{r['git']['sha']}` on `{r['git']['branch']}`"
        + (" (working tree dirty at run time)" if r["git"]["dirty"] else " (clean working tree)")
    )
    lines.append(f"- **Command**: `{' '.join(r['command'])}` (run from `{r['command_cwd']}`)")
    lines.append(
        f"- **Statistical convention**: confidence={report.get('confidence')}, "
        f"target_ci_halfwidth={report.get('target_ci_halfwidth')}, "
        f"min_samples={report.get('min_samples')} — no new sampling; "
        f"the draw is the source campaign's"
    )
    lines.append("- **Result**:")
    lines.append(
        f"  - klt yield payload status: **{str(report.get('status')).upper()}** "
        f"({report.get('measurement_count')} measurement(s) analysed); exit code "
        f"{r['exit_code']}"
    )
    for m in report.get("measurements") or []:
        lines.extend(render_measurement(m))
    for warning in report.get("warnings") or []:
        lines.append(f"  - run-level warning: {warning}")
    lines.append(f"  - **Overall: {str(report.get('status')).upper()}**")
    lines.append("- **Links**:")
    for label, target in r["links"].items():
        lines.append(f"  - {label}: `{target}`")
    lines.extend(render_record_footer(r, "yield-run.py"))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="yield-run.py",
        description=(
            "Mint a `klt yield` evidence record over an existing, committed "
            "`klt sim` Monte Carlo response (no simulation is run)."
        ),
    )
    p.add_argument("samples", help="path to <experiment>/klt-responses/<record-id>.json")
    p.add_argument(
        "--limits",
        default="",
        help=(
            "path to an explicit `klt yield` spec-limits document. Default: derive "
            "it from experiment.json's mc_measurements[].limits. Either way the "
            "document used is written to "
            "<experiment>/klt-requests/<record-id>.yield-limits.json and klt yield "
            "is invoked against that copy"
        ),
    )
    p.add_argument("--confidence", type=float, default=None, help="klt yield --confidence")
    p.add_argument(
        "--target-ci-halfwidth", type=float, default=None, help="klt yield --target-ci-halfwidth"
    )
    p.add_argument("--min-samples", type=int, default=None, help="klt yield --min-samples")
    p.add_argument(
        "--measurement",
        action="append",
        default=[],
        help="restrict to this measurement (repeatable)",
    )
    p.add_argument("--record-id", default="", help="override the minted record id (testing)")
    p.add_argument("--supersedes", default="", help="record id this run supersedes")
    p.add_argument("--author", default="", help="record author (default: git user.email)")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        exp_dir, samples, source_record_id = resolve_samples(Path(args.samples))
        exp = json.loads((exp_dir / "experiment.json").read_text())
        source_record = load_source_record(exp_dir, source_record_id)

        if args.limits:
            limits_src: Path | None = Path(args.limits).resolve()
            if not limits_src.is_file():
                raise HarnessError(f"--limits document not found: {limits_src}")
            limits_doc = json.loads(limits_src.read_text())
        else:
            limits_src = None
            limits_doc = derive_limits(exp, args)

        now = datetime.now(timezone.utc)
        sha = git(REPO_ROOT, "rev-parse", "--short", "HEAD") or "unknown"
        record_id = args.record_id or f"{now.strftime('%Y%m%d-%H%M%S')}-{sha}"

        responses_dir = exp_dir / "klt-responses"
        requests_dir = exp_dir / "klt-requests"
        records_dir = exp_dir / "records"
        limits_path = requests_dir / f"{record_id}.yield-limits.json"
        report_path = responses_dir / f"{record_id}.yield.json"
        record_json = records_dir / f"{record_id}.json"
        record_md = records_dir / f"{record_id}.md"
        for path in (limits_path, report_path, record_json, record_md):
            if path.exists():
                raise HarnessError(
                    f"{path} already exists -- sim/ evidence is append-only; a "
                    "re-run mints a new record id (see sim/README.md)"
                )

        requests_dir.mkdir(parents=True, exist_ok=True)
        if limits_src is not None:
            shutil.copyfile(limits_src, limits_path)
        else:
            with limits_path.open("w") as fh:
                json.dump(limits_doc, fh, indent=2)
                fh.write("\n")

        exe = klt_binary()
        limits_rel = f"../klt-requests/{limits_path.name}"
        cmd, raw_stdout, report, exit_code = run_klt_yield(
            exe, responses_dir, samples.name, limits_rel, args
        )
        report_path.write_text(raw_stdout if raw_stdout.endswith("\n") else raw_stdout + "\n")

        rel = lambda p: str(Path(p).resolve().relative_to(REPO_ROOT))  # noqa: E731
        klt_ver = klt_version(exe)
        native_ver = native_extension_version(exe)
        src_pdk = source_record.get("pdk") or {}
        src_tools = source_record.get("tools") or {}
        src_mc = (source_record.get("klt_request") or {}).get("monte_carlo") or {}
        record = {
            "record_id": record_id,
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "author": args.author or git(REPO_ROOT, "config", "user.email") or "unknown",
            "supersedes": args.supersedes,
            "evidence_kind": "yield",
            "evidence_kind_note": (
                "a derived analysis of an already-committed klt sim Monte Carlo "
                "response; no simulation, no PDK access, no new samples"
            ),
            "experiment": {
                "slug": exp["slug"],
                "title": exp["title"],
                "claim": exp["claim"],
                "provenance": exp.get("provenance", ""),
                "provenance_source": exp.get("provenance_source", ""),
            },
            "source_campaign": {
                "record_id": source_record_id,
                "record": rel(exp_dir / "records" / f"{source_record_id}.md"),
                "response": rel(samples),
                "response_sha256": sha256_file(samples),
                "netlist_snapshot": rel(
                    exp_dir / "netlist-snapshots" / f"{source_record_id}.spice"
                ),
                "status": str((source_record.get("klt_response") or {}).get("status", "unknown")),
                "statistical_convention": (
                    f"N={src_mc.get('n')} Monte Carlo samples, vary=`{src_mc.get('vary')}`, "
                    f"seed=`{src_mc.get('seed')}`, k_sigma={src_mc.get('k_sigma')}"
                ),
                "pdk": (
                    f"{src_pdk.get('variant')} @ open_pdks `{src_pdk.get('installed_commit')}`"
                ),
                "tools": "; ".join(f"{k}={v}" for k, v in sorted(src_tools.items()) if v),
            },
            "limits": {
                "file": rel(limits_path),
                "origin": (
                    f"explicit --limits document ({limits_src})"
                    if limits_src is not None
                    else "derived from experiment.json's mc_measurements[].limits"
                ),
                "document": limits_doc,
                "note": (
                    "The spec-limits document wins over whatever limits the samples "
                    "document carried (docs/cli/yield.md), so it is the explicit "
                    "statement of what this analysis holds the design to. No "
                    "target_yield is declared -- spec/target-spec.md ratifies none "
                    "for this block -- so klt yield reports the estimates rather "
                    "than grading them."
                ),
            },
            "command": [Path(cmd[0]).name, *cmd[1:]],
            "command_cwd": rel(responses_dir),
            "exit_code": exit_code,
            "klt_version": klt_ver,
            "klt_yield_native_version": native_ver,
            "tools": {
                "klt": klt_ver,
                "klt_yield_native": native_ver,
                "python": platform.python_version(),
                "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
            },
            "git": {
                "sha": sha,
                "branch": git(REPO_ROOT, "rev-parse", "--abbrev-ref", "HEAD"),
                "dirty": bool(git(REPO_ROOT, "status", "--porcelain")),
            },
            "klt_yield_report": report,
            "overall_status": report.get("status"),
            "links": {},
        }
        record["tools_line"] = "; ".join(
            filter(
                None,
                [
                    f"klt {record['klt_version']}" if record["klt_version"] else "",
                    (
                        f"klt_yield_native {record['klt_yield_native_version']}"
                        if record["klt_yield_native_version"]
                        else "klt_yield_native (version not resolvable)"
                    ),
                    record["tools"]["platform"],
                    f"python {record['tools']['python']}",
                ],
            )
        )
        record["links"] = {
            "klt yield report (raw)": rel(report_path),
            "klt yield spec-limits": rel(limits_path),
            "source klt sim response (samples)": rel(samples),
            "source campaign record": rel(exp_dir / "records" / f"{source_record_id}.md"),
            "machine-readable record": rel(record_json),
            "experiment manifest": rel(exp_dir / "experiment.json"),
        }

        with record_json.open("w") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)
            fh.write("\n")
        record_md.write_text(render_record(record))

        print(f"wrote {rel(report_path)}")
        print(f"wrote {rel(limits_path)}")
        print(f"wrote {rel(record_json)}")
        print(f"wrote {rel(record_md)}")
        print(f"klt yield status: {report.get('status')}")
        return 0
    except HarnessError as exc:
        print(f"yield-run.py: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
