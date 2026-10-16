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

Negative control (`--negative-control`, issue #211)
---------------------------------------------------
A yield statistic that has never been shown to reject a bad design is an
assumption, not evidence, so `klt yield` takes a **seeded, known-bad
variant's own samples** as a `negative_control` block on a measurement and
checks that the deliberate defect shows up as a statistically distinguishable
drop in yield -- not merely a lower point estimate (docs/cli/yield.md, "Negative
control"). `--negative-control <experiment>/klt-responses/<record-id>.json`
points this runner at that variant's own committed campaign response; the
degraded campaign is minted by `mc-run.py` exactly like any other, and
declares its defect in its own `experiment.json` (`netlist_patch`), so what
was degraded is committed alongside the samples rather than described only in
prose.

Why this changes the *input shape*, and the tool gap behind it: a
`negative_control` is metadata on a measurement, and `klt yield` reads it from
either input shape it accepts -- but `klt sim` has no request-side field for
it and never emits one on its response's `measurements[]` rollup, so a
`klt sim` Monte Carlo response can only ever carry a negative control if
someone hand-edits a committed response, which this repo's append-only
`sim/` discipline forbids outright. (`--limits` is not a way round it either:
a spec-limits document carries only `min`/`max`/`target_yield`/`exclusive_*`,
and `klt yield` drops everything else it finds there.) Filed upstream as
2AMLogic/klayout-tools#2563. So with `--negative-control` this runner mints a
**sample-set document** instead --
`<experiment>/klt-responses/<record-id>.samples.json`, committed and
append-only like every other artifact here -- carrying the nominal campaign's
own per-sample values plus the control's, and runs `klt yield` against that.
Two consequences worth stating plainly:

* The nominal samples in that document are *extracted* from the nominal
  campaign response by this runner, using the same rule `klt yield` applies to
  a sim report itself (one value per Monte-Carlo-sampled corner, in corner
  order; a `null` value counts into `errored`; `source_corners` are the corner
  ids with `klt sim`'s `/mc<i>` sample suffix stripped). Nothing is
  recomputed, reordered or filtered -- and the record asserts the derived
  document's own nominal statistics against the sim-report path's, so a
  faithless extraction shows up as a mismatch rather than as a quiet
  difference.
* `klt signoff` hashes the artifact a yield citation's `samples` field names,
  so with a negative control the hashed artifact is the derived sample-set
  document, not the nominal campaign response. The record says which is which,
  and both are pinned.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _record_common import (  # noqa: E402
    copy_new,
    git,
    klt_binary as _shared_klt_binary,
    render_record_footer,
    reserve_record_id,
    write_new_text,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class HarnessError(RuntimeError):
    """A recoverable, explained failure (printed without a traceback)."""


# --------------------------------------------------------------------------
# environment
# --------------------------------------------------------------------------


def klt_binary() -> str:
    return _shared_klt_binary("run a yield analysis", error_cls=HarnessError)


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


# --------------------------------------------------------------------------
# negative control: sample extraction + derived sample-set document (#211)
# --------------------------------------------------------------------------


def extract_sim_report_samples(report: dict, name: str, where: str) -> dict:
    """Per-sample values for one measurement of a `klt sim` MC response.

    Deliberately the same rule `klt yield` applies when it reads a sim report
    itself (see `_measurements_from_sim_report` in klayout_tools/
    yield_analysis.py, and docs/cli/yield.md's "klt sim Monte Carlo report"
    section): only corners carrying a non-null `monte_carlo` block contribute
    -- a deterministic PVT corner is not a draw from any distribution -- a
    `null` value counts into `errored` rather than being analysed, and
    `source_corners` names the originating corners with `klt sim`'s
    `/mc<sample-index>` suffix stripped.

    This runner only needs it because `klt sim` cannot express a
    `negative_control` on its own response (see the module docstring): the two
    campaigns' samples have to be brought into one sample-set document, which
    means reading the values out of each response. Nothing is recomputed or
    reordered -- and `main()` asserts the derived document reproduces the
    sim-report path's own statistics, so a divergence between this function and
    the tool's reader surfaces as a failed assertion instead of a quiet
    difference in a committed number.
    """
    corners = report.get("corners")
    if not isinstance(corners, list) or not corners:
        raise HarnessError(f"{where}: no 'corners' array -- is this a klt sim response?")
    mc_corners = [c for c in corners if isinstance(c, dict) and c.get("monte_carlo") is not None]
    if not mc_corners:
        raise HarnessError(
            f"{where}: no corner carries a 'monte_carlo' block, so it declares no "
            "Monte Carlo samples"
        )
    samples: list[float] = []
    errored = 0
    source_corners: list[str] = []
    unit = None
    for entry in report.get("measurements") or []:
        if isinstance(entry, dict) and entry.get("name") == name:
            unit = entry.get("unit")
            break
    found_measurement = False
    for corner in mc_corners:
        corner_id = corner.get("corner_id")
        if isinstance(corner_id, str):
            origin = corner_id.rsplit("/mc", 1)[0]
            if origin not in source_corners:
                source_corners.append(origin)
        for m in corner.get("measurements") or []:
            if not isinstance(m, dict) or m.get("name") != name:
                continue
            found_measurement = True
            value = m.get("value")
            if value is None:
                errored += 1
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HarnessError(
                    f"{where}: measurement {name!r} has a non-numeric value in corner "
                    f"{corner_id!r}"
                )
            else:
                samples.append(float(value))
    if not found_measurement:
        raise HarnessError(
            f"{where}: no Monte Carlo corner reports a measurement named {name!r} -- "
            "the nominal and the negative-control campaign must measure the same thing"
        )
    return {
        "samples": samples,
        "errored": errored,
        "source_corners": source_corners,
        "unit": unit,
    }


def negative_control_description(exp: dict, record: dict, record_id: str) -> str:
    """The `negative_control.description` klt yield echoes back.

    Built from the degraded campaign's own committed manifest/record rather
    than from a flag, so the description cannot drift from the defect that
    actually ran. `--negative-control-description` overrides it.
    """
    patch = record.get("netlist_patch") or {}
    subs = "; ".join(
        f"`{s['match']}` -> `{s['replace']}`" for s in patch.get("substitutions") or []
    )
    mc = (record.get("klt_request") or {}).get("monte_carlo") or {}
    parts = [
        f"seeded known-bad variant `{exp.get('slug', '?')}` record {record_id}",
        f"N={mc.get('n')}, vary={mc.get('vary')}, seed={mc.get('seed')}",
    ]
    if subs:
        parts.append(f"declared netlist_patch: {subs}")
    if patch.get("rationale"):
        parts.append(f"rationale: {patch['rationale']}")
    return " | ".join(str(p) for p in parts)


def build_sample_set(
    nominal: dict,
    control: dict,
    limits_doc: dict,
    description: str,
    provenance: dict,
) -> dict:
    """The derived sample-set document `klt yield` is run against.

    One entry per measurement the limits document names, carrying the nominal
    campaign's own extracted samples plus the negative control's. Limits are
    carried too even though the `--limits` document wins over them -- a
    sample-set document that states no limits at all is harder to read in
    isolation than one that agrees with the file beside it.
    """
    measurements = []
    for name in limits_doc["measurements"]:
        if name not in nominal:
            raise HarnessError(
                f"the nominal campaign reports no measurement named {name!r}, but the "
                "spec-limits document names it"
            )
        if name not in control:
            raise HarnessError(
                f"the negative-control campaign reports no measurement named {name!r} "
                "-- a control that does not measure the same thing cannot be compared "
                "against the nominal"
            )
        entry = {
            "name": name,
            "samples": nominal[name]["samples"],
            "errored": nominal[name]["errored"],
            "source_corners": nominal[name]["source_corners"],
            "limits": limits_doc["measurements"][name],
            "negative_control": {
                "samples": control[name]["samples"],
                "errored": control[name]["errored"],
                "description": description,
            },
        }
        if nominal[name].get("unit"):
            entry["unit"] = nominal[name]["unit"]
        measurements.append(entry)
    return {
        "comment": [
            "Sample-set document for `klt yield`, derived by sim/bin/yield-run.py.",
            "",
            "APPEND-ONLY EVIDENCE, not a scratch file: `klt signoff` hashes the",
            "artifact a yield citation's `samples` field names, so this document is",
            "what a citation of the report beside it is pinned to.",
            "",
            "WHY THIS SHAPE. `klt yield` reads a `negative_control` from either input",
            "shape it accepts, but `klt sim` has no request-side field for one and",
            "never emits one on its response rollup, so a klt sim response can carry a",
            "negative control only if a committed response is hand-edited -- which",
            "sim/README.md's append-only discipline forbids. Filed upstream as",
            "2AMLogic/klayout-tools#2563. So the two campaigns' own per-sample values",
            "are brought together here instead.",
            "",
            "NOTHING HERE IS A NEW MEASUREMENT. Every number below is copied out of a",
            "committed klt sim response, by the same rule klt yield applies to a sim",
            "report itself; the record minted alongside this file asserts that the",
            "nominal leg reproduces the sim-report path's own statistics.",
        ],
        "provenance": provenance,
        "measurements": measurements,
    }


def cross_check_nominal(
    report: dict,
    nominal_response: Path,
    exp_dir: Path,
    source_record_id: str,
    exe: str,
    responses_dir: Path,
    limits_rel: str,
    args: argparse.Namespace,
) -> dict:
    """Assert the derived sample-set document's nominal leg is faithful.

    The negative-control path hands `klt yield` a document this runner built,
    rather than the campaign response the tool would have read itself, so the
    obvious failure mode is a silently wrong extraction -- a committed
    statistic that no longer describes the committed samples. So the same
    `klt yield` is run a second time directly over the nominal response (the
    pre-#211 input shape, no negative control) and the two runs' nominal
    `distribution` and `yield.empirical` blocks are required to be identical.
    Not "close": identical, because both are the same arithmetic over the same
    values, and any difference at all means the extraction moved a number.

    That second run mints no artifact -- it is a check, not evidence -- but
    what it found is recorded, so the assertion is auditable after the fact
    rather than only having been made once at run time.
    """
    _, raw_stdout, direct, _ = run_klt_yield(
        exe, responses_dir, nominal_response.name, limits_rel, args
    )
    del raw_stdout
    by_name = {m["name"]: m for m in direct.get("measurements") or []}
    checked = {}
    for m in report.get("measurements") or []:
        name = m["name"]
        if name not in by_name:
            raise HarnessError(
                f"nominal cross-check: the direct analysis of {nominal_response.name} "
                f"reports no measurement {name!r}"
            )
        other = by_name[name]
        for field in ("distribution", "capability", "sample_size"):
            if m.get(field) != other.get(field):
                raise HarnessError(
                    "nominal cross-check FAILED: the derived sample-set document's "
                    f"{field!r} for {name!r} differs from a direct `klt yield` over "
                    f"{nominal_response.name}\n"
                    f"  derived: {json.dumps(m.get(field), sort_keys=True)}\n"
                    f"  direct : {json.dumps(other.get(field), sort_keys=True)}\n"
                    "  the nominal samples were not carried across faithfully -- fix "
                    "the extraction, do not record this"
                )
        mine = (m.get("yield") or {}).get("empirical")
        theirs = (other.get("yield") or {}).get("empirical")
        if mine != theirs:
            raise HarnessError(
                "nominal cross-check FAILED: the derived sample-set document's "
                f"empirical yield for {name!r} differs from a direct `klt yield` over "
                f"{nominal_response.name}\n"
                f"  derived: {json.dumps(mine, sort_keys=True)}\n"
                f"  direct : {json.dumps(theirs, sort_keys=True)}"
            )
        checked[name] = {
            "n": m.get("n"),
            "errored": m.get("errored"),
            "distribution_identical": True,
            "capability_identical": True,
            "sample_size_identical": True,
            "empirical_yield_identical": True,
        }
    return {
        "method": (
            "`klt yield` was run a second time directly over the nominal campaign "
            f"response ({nominal_response.name}, the pre-#211 sim-report input shape, "
            "no negative control) and its nominal distribution/capability/sample-size/"
            "empirical-yield blocks were required to be byte-equal to the derived "
            "sample-set document's. This check mints no artifact; a mismatch aborts "
            "the run instead of being recorded"
        ),
        "nominal_response": str(nominal_response.name),
        "nominal_record": str(
            (exp_dir / "records" / f"{source_record_id}.md").relative_to(REPO_ROOT)
        ),
        "verdict": "identical",
        "measurements": checked,
    }


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

    nc = m.get("negative_control")
    if not nc:
        lines.append("    - negative control: **none declared**")
    else:
        lines.append(f"    - negative control: **{str(nc.get('verdict')).upper()}**")
        lines.append(
            f"      - what was degraded: {nc.get('description') or '(no description given)'}"
        )
        nc_y = (nc.get("yield") or {}).get("empirical") or {}
        if nc_y:
            lines.append(
                f"      - the control's own empirical yield: {fmt_yield(nc_y)} "
                f"— against the nominal's {nc.get('nominal_empirical_estimate', float('nan')) * 100:.4f}%"
            )
        nc_norm = (nc.get("yield") or {}).get("normal") or {}
        if nc_norm:
            lines.append(f"      - the control's own normal-fit yield: {fmt_yield(nc_norm)}")
        nc_dist = nc.get("distribution") or {}
        if nc_dist:
            lines.append(
                f"      - the control's own distribution: mean={nc_dist.get('mean'):.6g}, "
                f"stddev={nc_dist.get('stddev'):.6g}, min={nc_dist.get('min'):.6g}, "
                f"max={nc_dist.get('max'):.6g}"
            )
        lines.append(
            f"      - n={nc.get('n')} (errored={nc.get('errored', 0)}, "
            f"failed_unmeasurable={nc.get('failed_unmeasurable', 0)})"
        )
        lines.append(
            "      - How to read the verdict (docs/cli/yield.md#negative-control): "
            "`detected` means the control's exact (Clopper-Pearson) yield interval "
            "does not overlap the nominal's — a gap too large to be sampling noise, "
            "not merely a lower point estimate. `not_detected` means the intervals "
            "overlap (or the control is not even lower), i.e. this statistic, at "
            "this sample count, cannot tell this deliberate defect from the nominal "
            "design."
        )
    lines.append(
        f"    - analytic cross-check: "
        f"{'present' if m.get('analytic_cross_check') else '**none declared**'}"
    )
    for warning in m.get("warnings") or []:
        lines.append(f"    - warning: {warning}")
    return lines


def render_negative_control_provenance(r: dict) -> list[str]:
    """The `- **Negative control**:` / `- **Analysed document**:` bullets.

    Separated from the per-measurement `negative_control` *verdict* that
    `render_measurement` prints: this block is where the control's samples came
    from and what was deliberately broken to produce them, which is provenance,
    not a result.
    """
    nc = r.get("negative_control")
    doc = r.get("analysed_document") or {}
    lines: list[str] = []
    if nc:
        lines.append(
            "- **Negative control** (the seeded, known-bad variant this analysis is "
            "checked against — issue #211):"
        )
        lines.append(f"  - Experiment: `{nc['experiment_slug']}` (`{nc['experiment_manifest']}`)")
        lines.append(f"  - Record: `{nc['record_id']}` (`{nc['record']}`)")
        lines.append(f"  - Samples document: `{nc['response']}`")
        lines.append(f"  - Samples document sha256: `{nc['response_sha256']}`")
        lines.append(f"  - Netlist snapshot (the DEGRADED deck): `{nc['netlist_snapshot']}`")
        patch = nc.get("netlist_patch") or {}
        if patch:
            lines.append(f"  - What was deliberately broken: {patch.get('rationale')}")
            for sub in patch.get("substitutions") or []:
                lines.append(
                    f"    - declared substitution ({sub['count']} occurrence(s), "
                    f"asserted): `{sub['match']}` → `{sub['replace']}`"
                )
            lines.append(
                f"    - deck sha256 before the patch `{patch.get('netlist_sha256_before')}` → "
                f"after `{patch.get('netlist_sha256_after')}`"
            )
        lines.append(
            f"  - As that record reports it: {nc['statistical_convention']}; aggregate "
            f"status **{str(nc['status']).upper()}** (a FAIL there is the intended "
            f"result — the control exists to be rejected)"
        )
        lines.append(f"  - PDK it ran on: {nc['pdk']}")
        lines.append(f"  - Execution backend: `{nc.get('backend')}`")
        lines.append(f"  - Tools that produced the control's samples: {nc['tools']}")
        if nc.get("engine_version") is not None:
            lines.append(
                f"  - Simulation engine version `klt sim` recorded for the control's "
                f"samples: `{nc['engine_version']}`"
            )
        check = nc.get("nominal_statistics_cross_check") or {}
        if check:
            lines.append(
                f"  - Nominal-leg faithfulness check: **{str(check.get('verdict')).upper()}** "
                f"— {check.get('method')}"
            )
    if doc:
        lines.append(
            f"- **Analysed document** ({doc.get('kind')}) — `{doc.get('file')}`, sha256 "
            f"`{doc.get('sha256')}`"
        )
        lines.append(f"  - {doc.get('note')}")
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
    if src.get("engine_version") is not None:
        lines.append(
            f"  - Simulation engine version `klt sim` recorded for those samples: "
            f"`{src['engine_version']}`"
        )
    lines.extend(render_negative_control_provenance(r))
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
    p.add_argument(
        "--negative-control",
        default="",
        help=(
            "path to the seeded, known-bad variant campaign's own committed "
            "<experiment>/klt-responses/<record-id>.json. Its per-sample values are "
            "carried into each measurement's `negative_control` block so `klt yield` "
            "can check that the deliberate defect shows up as a statistically "
            "distinguishable drop in yield (docs/cli/yield.md#negative-control). "
            "Because `klt sim` cannot express a negative control on its own response, "
            "this switches the analysed input to a derived, committed sample-set "
            "document -- see the module docstring"
        ),
    )
    p.add_argument(
        "--negative-control-description",
        default="",
        help=(
            "override the `negative_control.description` echoed into the report. "
            "Default: built from the degraded campaign's own experiment.json "
            "`netlist_patch` and record, so it cannot drift from the defect that ran"
        ),
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
        sample_set_path = responses_dir / f"{record_id}.samples.json"
        # Atomic claim before any evidence is written (issue #310).
        reserve_record_id(REPO_ROOT / "sim" / "build", exp_dir.name, record_id, HarnessError)
        guarded = [limits_path, report_path, record_json, record_md]
        if args.negative_control:
            guarded.append(sample_set_path)
        for path in guarded:
            if path.exists():
                raise HarnessError(
                    f"{path} already exists -- sim/ evidence is append-only; a "
                    "re-run mints a new record id (see sim/README.md)"
                )

        requests_dir.mkdir(parents=True, exist_ok=True)
        if limits_src is not None:
            copy_new(limits_src, limits_path)
        else:
            with limits_path.open("x") as fh:
                json.dump(limits_doc, fh, indent=2)
                fh.write("\n")

        rel = lambda p: str(Path(p).resolve().relative_to(REPO_ROOT))  # noqa: E731

        # ---------------------------------------------------------------
        # negative control (#211): bring the known-bad variant's own samples
        # alongside the nominal's in a derived, committed sample-set document,
        # because `klt sim` cannot express one on its own response.
        # ---------------------------------------------------------------
        negative_control = None
        analysed_name = samples.name
        if args.negative_control:
            nc_exp_dir, nc_samples, nc_record_id = resolve_samples(Path(args.negative_control))
            if nc_samples == samples:
                raise HarnessError(
                    "--negative-control names the same response as the nominal samples "
                    "document -- a campaign cannot be its own negative control"
                )
            nc_exp = json.loads((nc_exp_dir / "experiment.json").read_text())
            nc_record = load_source_record(nc_exp_dir, nc_record_id)
            if not nc_exp.get("netlist_patch") and not nc_record.get("netlist_patch"):
                raise HarnessError(
                    f"{nc_exp_dir / 'experiment.json'} declares no `netlist_patch`, and "
                    f"neither does its record -- refusing to present an undeclared "
                    "campaign as a seeded, known-bad variant. A negative control has to "
                    "say what was deliberately broken (see mc-run.py's netlist_patch)"
                )
            nominal_report = json.loads(samples.read_text())
            control_report = json.loads(nc_samples.read_text())
            nominal_by_name = {
                name: extract_sim_report_samples(nominal_report, name, f"nominal {samples.name}")
                for name in limits_doc["measurements"]
            }
            control_by_name = {
                name: extract_sim_report_samples(
                    control_report, name, f"negative control {nc_samples.name}"
                )
                for name in limits_doc["measurements"]
            }
            description = args.negative_control_description or negative_control_description(
                nc_exp, nc_record, nc_record_id
            )
            nc_mc = (nc_record.get("klt_request") or {}).get("monte_carlo") or {}
            nc_pdk = nc_record.get("pdk") or {}
            nc_tools = nc_record.get("tools") or {}
            negative_control = {
                "experiment_slug": nc_exp.get("slug"),
                "experiment_manifest": rel(nc_exp_dir / "experiment.json"),
                "record_id": nc_record_id,
                "record": rel(nc_exp_dir / "records" / f"{nc_record_id}.md"),
                "response": rel(nc_samples),
                "response_sha256": sha256_file(nc_samples),
                "netlist_snapshot": rel(
                    nc_exp_dir / "netlist-snapshots" / f"{nc_record_id}.spice"
                ),
                "netlist_patch": nc_record.get("netlist_patch"),
                "description": description,
                "status": str((nc_record.get("klt_response") or {}).get("status", "unknown")),
                "statistical_convention": (
                    f"N={nc_mc.get('n')} Monte Carlo samples, vary=`{nc_mc.get('vary')}`, "
                    f"seed=`{nc_mc.get('seed')}`, k_sigma={nc_mc.get('k_sigma')}"
                ),
                "backend": nc_record.get("backend"),
                "pdk": f"{nc_pdk.get('variant')} @ open_pdks `{nc_pdk.get('installed_commit')}`",
                "tools": "; ".join(f"{k}={v}" for k, v in sorted(nc_tools.items()) if v),
                "engine_version": (
                    (control_report.get("environment") or {}).get("engine_version")
                ),
                "sample_counts": {
                    name: {
                        "n": len(control_by_name[name]["samples"]),
                        "errored": control_by_name[name]["errored"],
                    }
                    for name in control_by_name
                },
            }
            sample_set = build_sample_set(
                nominal_by_name,
                control_by_name,
                limits_doc,
                description,
                {
                    "nominal": {
                        "response": rel(samples),
                        "sha256": sha256_file(samples),
                        "record": rel(exp_dir / "records" / f"{source_record_id}.md"),
                        "engine_version": (
                            (nominal_report.get("environment") or {}).get("engine_version")
                        ),
                    },
                    "negative_control": {
                        "response": negative_control["response"],
                        "sha256": negative_control["response_sha256"],
                        "record": negative_control["record"],
                        "engine_version": negative_control["engine_version"],
                        "netlist_patch": negative_control["netlist_patch"],
                    },
                },
            )
            with sample_set_path.open("w") as fh:
                json.dump(sample_set, fh, indent=2)
                fh.write("\n")
            analysed_name = sample_set_path.name

        exe = klt_binary()
        limits_rel = f"../klt-requests/{limits_path.name}"
        cmd, raw_stdout, report, exit_code = run_klt_yield(
            exe, responses_dir, analysed_name, limits_rel, args
        )
        write_new_text(report_path, raw_stdout if raw_stdout.endswith("\n") else raw_stdout + "\n")

        if negative_control is not None:
            negative_control["nominal_statistics_cross_check"] = cross_check_nominal(
                report, samples, exp_dir, source_record_id, exe, responses_dir, limits_rel, args
            )

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
                "engine_version": (
                    (source_record.get("klt_response") or {}).get("environment") or {}
                ).get("engine_version"),
            },
            "negative_control": negative_control,
            "analysed_document": {
                "file": rel(sample_set_path if negative_control else samples),
                "sha256": sha256_file(sample_set_path if negative_control else samples),
                "kind": "derived sample-set document" if negative_control else "klt sim response",
                "note": (
                    (
                        "This is the artifact `klt yield`'s own `samples` field names, "
                        "and therefore the artifact `klt signoff` hashes for a citation "
                        "of the report beside it (docs/cli/signoff.md, '`klt yield` "
                        "evidence and content hashing'). It is a document this runner "
                        "derived -- the nominal campaign's own per-sample values plus "
                        "the negative control's -- because `klt sim` cannot express a "
                        "negative_control on its own response "
                        "(2AMLogic/klayout-tools#2563). The nominal campaign response "
                        "it was built from is pinned under `source_campaign` and its "
                        "statistics are cross-checked against a direct analysis of it; "
                        "both are committed and append-only."
                    )
                    if negative_control
                    else (
                        "The nominal campaign response, analysed directly -- the "
                        "artifact `klt signoff` hashes for a citation of the report "
                        "beside it."
                    )
                ),
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
        if negative_control is not None:
            record["links"]["analysed sample-set document (what klt signoff hashes)"] = rel(
                sample_set_path
            )
            record["links"]["negative-control campaign record"] = negative_control["record"]
            record["links"]["negative-control klt sim response"] = negative_control["response"]
            record["links"]["negative-control experiment manifest"] = negative_control[
                "experiment_manifest"
            ]

        with record_json.open("x") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)
            fh.write("\n")
        write_new_text(record_md, render_record(record))

        print(f"wrote {rel(report_path)}")
        print(f"wrote {rel(limits_path)}")
        if negative_control is not None:
            print(f"wrote {rel(sample_set_path)}")
        print(f"wrote {rel(record_json)}")
        print(f"wrote {rel(record_md)}")
        print(f"klt yield status: {report.get('status')}")
        for m in report.get("measurements") or []:
            nc = m.get("negative_control")
            if nc:
                print(f"negative control ({m['name']}): {nc.get('verdict')}")
        return 0
    except HarnessError as exc:
        print(f"yield-run.py: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
