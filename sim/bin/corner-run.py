#!/usr/bin/env python3
"""PVT corner runner for sky130-ldo.

Netlists an xschem testbench, sweeps a process/voltage/temperature matrix
through ngspice against the pinned sky130 PDK, and writes an append-only
evidence record under sim/<experiment-slug>/. See sim/README.md for the
record format and the rules the runner enforces.

Ported from the sibling sky130-bandgap repo's sim/bin/corner-run.py (same
PDK, same pin, same harness convention -- issue #2), with two additions:
`--check-env` (a fast toolchain/PDK liveness check for sim/selftest.sh) and
`--no-write` (run every corner for real but skip persisting the evidence
record, so a CI selftest run does not mint new evidence on every push).

Usage
-----
    sim/bin/corner-run.py sim/pdk-smoke                     # full PVT matrix
    sim/bin/corner-run.py sim/pdk-smoke --quick \\
        --subset-reason "harness liveness check"            # 3-point subset
    sim/bin/corner-run.py --print-env                       # PDK env exports
    sim/bin/corner-run.py --check-env                       # toolchain/PDK check
    sim/bin/corner-run.py --check-env --require-pdk         # ... tool drift is a FAIL

The runner never edits or deletes an existing record: it refuses to start if
the record id it would mint already exists on disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import batch_line_regulation as blr  # noqa: F401  (re-exported; tests call corner_run.blr)
import batch_load_regulation as bld
import batch_iq as biq
from ramp_monotonicity import evaluate_legs
from xschem_exprs import eval_xschem_exprs  # noqa: F401  (re-exported; tests call corner_run.eval_xschem_exprs)
from _record_common import (
    build_input_fingerprint,
    CAPACITY_RETRY_BACKOFF_S,  # noqa: F401  (re-exported for tests)
    CAPACITY_RETRY_BUDGET_S,  # noqa: F401  (re-exported for tests)
    git,
    is_finite_number as _finite_number,
    pvt_input_sections,
    reserve_record_id,
    render_record_footer,
    render_record_header,
    write_new_text,
)
import _evidence_store
from _corner_model import (  # noqa: F401  (re-exported: corner_run.<name> is a public surface)
    BUILD_DIR,
    Corner,
    Experiment,
    HarnessError,
    Measurement,
    PDK_PIN_FILE,
    Pdk,
    REPO_ROOT,
    SIM_DIR,
    SOLVER_DIAGNOSTIC_MARKERS,
    SPICEINIT_FILE,
    XSCHEMRC_FILE,
    compare_tool_versions,
    detect_solver_diagnostic,
    grade_bounds,
    leg_values,
    parse_tool_version,
    unique_in_order,
    window_legs,
)
from _batch_backend import (  # noqa: F401  (re-exported: corner_run.<name> is a public surface)
    BATCH_ALLOWLIST,
    BATCH_REFUSAL_HINT,
    BatchGroup,
    batch_legs,
    batch_remote_info,
    batch_tools,
    build_batch_netlist,
    build_batch_request,
    check_batch_supported,
    check_cold_start_batch_shape,
    check_endpoint_batch_shape,
    check_window_grid_batch_shape,
    cold_start_step,
    endpoint_deck,
    endpoint_module,
    endpoint_step,
    finalize_endpoint_results,
    group_batch_requests,
    is_cold_start_crossing,
    is_endpoint_adapter,
    klt_binary,
    leg_template_name,
    merge_leg_parts,
    normalize_batch_response,
    normalize_endpoint_response,
    prepare_batch_requests,
    run_batch,
    run_klt_batch,
    spiceinit_lines,
    window_grid_step,
)


# --------------------------------------------------------------------------
# PDK resolution
# --------------------------------------------------------------------------


def load_pin() -> dict:
    if not PDK_PIN_FILE.exists():
        raise HarnessError(f"missing PDK pin file: {PDK_PIN_FILE}")
    return json.loads(PDK_PIN_FILE.read_text())


def volare_path() -> Path | None:
    exe = shutil.which("volare")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "path"], capture_output=True, text=True, timeout=60, check=True
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None
    return Path(out) if out else None


def resolve_pdk(pin: dict) -> Pdk:
    root_env = os.environ.get("PDK_ROOT", "").strip()
    if root_env:
        root = Path(root_env).expanduser()
    else:
        root = volare_path() or Path(pin["default_pdk_root"]).expanduser()
    variant = os.environ.get("PDK", "").strip() or pin["variant"]
    pdk_dir = root / variant
    if not pdk_dir.is_dir():
        raise HarnessError(
            f"no PDK at {pdk_dir}\n"
            f"  install the pinned version with: {pin['install_command']}\n"
            f"  (or set PDK_ROOT / PDK to an existing install)"
        )
    lib_file = pdk_dir / pin["ngspice_lib"]
    if not lib_file.is_file():
        raise HarnessError(f"no ngspice model library at {lib_file}")
    return Pdk(
        pin=pin,
        root=root,
        variant=variant,
        dir=pdk_dir,
        installed_commit=installed_commit(pdk_dir),
        lib_file=lib_file,
    )


def installed_commit(pdk_dir: Path) -> str:
    """Recover the volare version hash by resolving the PDK symlink."""
    parts = pdk_dir.resolve().parts
    if "versions" in parts:
        idx = parts.index("versions")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return "unknown"


def print_env(pdk: Pdk) -> None:
    print(f"export PDK_ROOT={pdk.root}")
    print(f"export PDK={pdk.variant}")
    print(f"export SKY130_MODEL_LIB={pdk.lib_file}")
    print(f"export XSCHEM_RCFILE={XSCHEMRC_FILE}")


# --------------------------------------------------------------------------
# tool versions / --check-env
# --------------------------------------------------------------------------


def first_line(cmd: list[str]) -> str:
    exe = shutil.which(cmd[0])
    if not exe:
        return "not found"
    try:
        proc = subprocess.run(
            [exe, *cmd[1:]], capture_output=True, text=True, timeout=60
        )
    except (subprocess.SubprocessError, OSError) as exc:  # pragma: no cover
        return f"error: {exc}"
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        line = line.strip().lstrip("*").strip()
        if line:
            return line
    return "unknown"


def declared_tool_versions(pin: dict) -> dict:
    """The `tools` block of sim/pdk.json (empty if the pin does not declare one)."""
    return dict(pin.get("tools") or {})


def tool_versions() -> dict:
    versions = {
        "ngspice": first_line(["ngspice", "-v"]),
        "xschem": first_line(["xschem", "--version"]),
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": platform.python_version(),
    }
    # issue #291: say whether this run is on the declared baseline, so a reader
    # can tell "recorded on baseline" from "recorded on drifted tools".
    try:
        declared = declared_tool_versions(load_pin())
    except (HarnessError, ValueError):
        declared = {}
    if declared:
        versions["declared"] = declared
        versions["on_baseline"] = not compare_tool_versions(declared, versions)
    return versions


# --------------------------------------------------------------------------
# ngspice init settings (the deck is only half the input -- issue #190)
# --------------------------------------------------------------------------


def spiceinit_digest(text: str) -> str:
    """sha256 of a set of ngspice init settings."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def spiceinit_provenance() -> dict:
    """Identify the `.spiceinit` this run puts in front of ngspice.

    ngspice reads `.spiceinit` from its working directory at startup, so the
    deck is not the whole input: `sim/spiceinit` sets `option klu` (the KLU
    direct linear solver) among other settings, and a corner's solver
    diagnostics do not necessarily reproduce without it (issue #190). The
    hash lets a reader tell whether the settings a record was produced under
    are still the ones in the tree.
    """
    return {
        "spiceinit_file": str(SPICEINIT_FILE.relative_to(REPO_ROOT)),
        "spiceinit_sha256": spiceinit_digest(SPICEINIT_FILE.read_text()),
    }


def spiceinit_log_section(run_dir: Path) -> list[str]:
    """The corner log's `.spiceinit` block: the second input, verbatim.

    Embeds the file that was actually in the run directory (not the one in
    the tree), so the log stays self-contained and honest even if
    `sim/spiceinit` changes later or never got copied.
    """
    header = "# ==== .spiceinit (2nd input: ngspice reads it from the run directory) ===="
    path = run_dir / ".spiceinit"
    if not path.is_file():
        return [
            header,
            "# NOT PRESENT in the run directory for this run — ngspice fell back to",
            "# whatever it found elsewhere (e.g. ~/.spiceinit) or to its built-in",
            "# defaults, so this corner's solver settings are NOT pinned by this log.",
        ]
    text = path.read_text()
    return [
        header,
        f"# sha256: {spiceinit_digest(text)}",
        *[f"| {ln}" for ln in text.splitlines()],
    ]


TOOL_VERSION_FLAGS = {
    "ngspice": "-v",
    "xschem": "--version",
    "volare": "--version",
}


def check_env(require_pdk: bool = False) -> int:
    """Print a short toolchain/PDK liveness report. 0 if everything is usable.

    A tool version that differs from sim/pdk.json's `tools` block is a named
    WARN (exit unchanged) -- or a FAIL when `require_pdk` is set (issue #291).
    """
    status = 0
    versions: dict = {}
    for tool, flag in TOOL_VERSION_FLAGS.items():
        exe = shutil.which(tool)
        if exe:
            versions[tool] = first_line([tool, flag])
            print(f"{tool:<8}: OK   {versions[tool]}")
        else:
            print(f"{tool:<8}: MISSING (not on PATH)")
            status = 1
    try:
        pin = load_pin()
    except HarnessError as exc:
        print(f"PDK     : MISSING\n{exc}")
        return 1
    declared = declared_tool_versions(pin)
    for tool, want, got in compare_tool_versions(
        {t: v for t, v in declared.items() if t in versions}, versions
    ):
        level = "FAIL" if require_pdk else "WARN"
        print(f"{tool:<8}: {level} {tool} drifted from declared {want} to {got} "
              "(sim/pdk.json tools)")
        if require_pdk:
            status = 1
    try:
        pdk = resolve_pdk(pin)
    except HarnessError as exc:
        print(f"PDK     : MISSING\n{exc}")
        return 1
    match_note = "matches sim/pdk.json pin" if pdk.matches_pin else "MISMATCH vs sim/pdk.json pin"
    print(f"PDK     : OK   {pdk.dir} (open_pdks {pdk.installed_commit}, {match_note})")
    print(f"  models: {pdk.lib_file}")
    if not pdk.matches_pin:
        status = 1
    return status


# --------------------------------------------------------------------------
# git provenance
# --------------------------------------------------------------------------


def git_state() -> dict:
    sha = git(REPO_ROOT, "rev-parse", "--short", "HEAD") or "nogit"
    dirty = bool(git(REPO_ROOT, "status", "--porcelain"))
    return {
        "sha": sha,
        "branch": git(REPO_ROOT, "rev-parse", "--abbrev-ref", "HEAD") or "unknown",
        "dirty": dirty,
    }


def default_author() -> str:
    for var in ("SIM_AUTHOR", "LOOM_AGENT"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return git(REPO_ROOT, "config", "user.email") or "unknown"


# --------------------------------------------------------------------------
# experiment manifest
# --------------------------------------------------------------------------


def leg_measurement_name(template: str, leg_id: str) -> str:
    """Name of a per-leg measurement. The leg id (which carries the COUT/ESR
    coordinates) is part of the name so every result row is self-describing."""
    return f"{template}__{leg_id}"


def expand_measurements(raw: dict) -> list[Measurement]:
    """Manifest measurements -> concrete Measurements. A `per_leg` template
    becomes one measurement per declared window_grid leg (template order, then
    leg order); everything else passes through unchanged."""
    legs = window_legs(raw)
    out: list[Measurement] = []
    for m in raw["measurements"]:
        if not m.get("per_leg"):
            out.append(Measurement(**m))
            continue
        if not legs:
            raise HarnessError(
                f"measurement {m['name']!r} is per_leg but the manifest declares no window_grid legs"
            )
        for leg in legs:
            fields = {k: v for k, v in m.items() if k != "per_leg"}
            fields.update(
                name=leg_measurement_name(m["name"], leg["id"]),
                leg=leg["id"],
                cout_f=leg["cout_f"],
                esr_ohm=leg["esr_ohm"],
            )
            out.append(Measurement(**fields))
    return out


def load_experiment(path: Path) -> Experiment:
    exp_dir = path.resolve()
    manifest = exp_dir / "experiment.json"
    if not manifest.is_file():
        raise HarnessError(f"no experiment.json in {exp_dir}")
    raw = json.loads(manifest.read_text())
    for key in ("slug", "claim", "schematic", "corners", "measurements"):
        if key not in raw:
            raise HarnessError(f"{manifest}: missing required key {key!r}")
    exp = Experiment(dir=exp_dir, raw=raw)
    exp.measurements = expand_measurements(raw)
    if not exp.schematic.is_file():
        raise HarnessError(f"{manifest}: schematic not found: {exp.schematic}")
    return exp


# --------------------------------------------------------------------------
# corner matrix
# --------------------------------------------------------------------------


def fmt_temp(value: float) -> str:
    return f"{value:g}"


def build_matrix(exp: Experiment, args: argparse.Namespace, pin: dict) -> tuple[list[Corner], bool]:
    corners = exp.raw["corners"]
    if args.quick:
        subset = exp.raw.get("quick_subset")
        if not subset:
            raise HarnessError(f"{exp.slug}: --quick needs a quick_subset in experiment.json")
        return [Corner(p, float(t), float(v)) for p, t, v in subset], True

    process = args.process or corners["process"]
    temps = args.temp if args.temp is not None else corners["temperature_c"]
    supplies = args.supply if args.supply is not None else corners["supply_v"]

    known = set(pin["process_corners"])
    unknown = [p for p in process if p not in known]
    if unknown:
        raise HarnessError(
            f"process corner(s) {unknown} are not in sim/pdk.json process_corners "
            f"{sorted(known)}; add them there once verified against the PDK "
            f"library sections"
        )

    matrix = [
        Corner(p, float(t), float(v))
        for p in process
        for t in temps
        for v in supplies
    ]
    is_subset = (
        list(process) != list(corners["process"])
        or [float(t) for t in temps] != [float(t) for t in corners["temperature_c"]]
        or [float(v) for v in supplies] != [float(v) for v in corners["supply_v"]]
    )
    return matrix, is_subset


# --------------------------------------------------------------------------
# netlisting
# --------------------------------------------------------------------------


def netlist_with_xschem(schematic: Path, out_dir: Path, pdk: Pdk) -> Path:
    if not shutil.which("xschem"):
        raise HarnessError("xschem not found on PATH; cannot netlist the testbench")
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PDK_ROOT"] = str(pdk.root)
    env["PDK"] = pdk.variant
    cmd = [
        "xschem",
        "-n",  # netlist
        "-q",  # quit when done
        "-x",  # no X11 / no GUI
        "-s",  # spice netlist format
        "-o",
        str(out_dir),
        "--rcfile",
        str(XSCHEMRC_FILE),
        str(schematic),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, env=env, timeout=300, stdin=subprocess.DEVNULL
    )
    produced = out_dir / (schematic.stem + ".spice")
    if proc.returncode != 0 or not produced.is_file():
        raise HarnessError(
            "xschem netlisting failed\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  rc: {proc.returncode}\n"
            f"  stdout: {proc.stdout.strip()}\n"
            f"  stderr: {proc.stderr.strip()}"
        )
    return produced


def netlist_body(netlist: Path, eval_exprs: bool = True) -> list[str]:
    """Strip the trailing .end so the deck can wrap the netlist.

    Also rewrites the absolute path xschem stamps into its `** sch_path:`
    comment to a repo-relative one, so netlist snapshots are byte-comparable
    across machines and checkouts, and (unless eval_exprs=False) evaluates
    un-evaluated `expr('...')` parameters from older xschem releases.
    """
    text = netlist.read_text().replace(str(REPO_ROOT) + os.sep, "")
    if eval_exprs:
        text, _ = eval_xschem_exprs(text)
    return [ln for ln in text.splitlines() if ln.strip().lower() != ".end"]


# --------------------------------------------------------------------------
# deck generation and simulation
# --------------------------------------------------------------------------


def fmt_spice_value(value: float) -> str:
    return repr(float(value))


def window_leg_lines(
    exp: Experiment, leg_ids: list[str] | None = None, corner_id: str = "{corner_id}"
) -> list[str]:
    """The in-deck COUT/ESR window walk (issue #313): one independent block per
    declared leg -- `reset`, that leg's own `alter` cards, its own `tran` and
    measurements. `leg_ids` selects/reorders legs (used by the leg-order
    independence smoke check); the default is the declared order.

    ESR = 0 is realised electrically, not with a stand-in resistor: COUT moves
    to the direct VOUT-to-ground branch (`cdir`) and the series COUT+RESR branch
    is set to 0 F (open); every ESR > 0 leg does the reverse.
    """
    grid = exp.raw.get("window_grid")
    if not grid:
        return []
    by_id = {leg["id"]: leg for leg in grid["legs"]}
    order = leg_ids or exp.leg_order or [leg["id"] for leg in grid["legs"]]
    template = grid["leg_analyses"]
    lines: list[str] = []
    for leg_id in order:
        leg = by_id[leg_id]
        cout, esr = float(leg["cout_f"]), float(leg["esr_ohm"])
        subs = {k: fmt_spice_value(v) for k, v in leg_values(grid, leg).items()}
        lines.append(
            f"* --- window leg {leg_id}: COUT={cout:g} F, ESR={esr:g} ohm "
            "(independent reset/seed/tran) ---"
        )
        for ln in template:
            for key, val in subs.items():
                ln = ln.replace("{" + key + "}", val)
            # `{leg_id}`/`{corner_id}` name a per-leg trace file (issue #336).
            lines.append(ln.replace("{leg_id}", leg_id).replace("{corner_id}", corner_id))
        for m in exp.measurements:
            if m.leg == leg_id:
                lines.append(f"let meas_{m.name} = {m.expr}")
                lines.append(f"print meas_{m.name}")
    return lines


def build_deck(exp: Experiment, pdk: Pdk, corner: Corner, body: list[str]) -> str:
    deck = exp.raw.get("deck", {})
    head = [
        f"* {exp.slug} corner deck -- generated by sim/bin/corner-run.py, do not edit",
        f"* corner: {corner.id}",
        f".param vsup={corner.supply_v}",
    ]
    for name, value in (deck.get("params") or {}).items():
        head.append(f".param {name}={value}")
    for opt in deck.get("options") or []:
        head.append(f".option {opt}")
    head.append(f".temp {fmt_temp(corner.temp_c)}")
    head.append(f'.lib "{pdk.lib_file}" {corner.process}')

    control = [".control", "save all"]
    # `{corner_id}` lets a manifest write a per-corner trace file (issue #309).
    control += [ln.replace("{corner_id}", corner.id) for ln in (deck.get("analyses") or ["op"])]
    control += window_leg_lines(exp, corner_id=corner.id)
    # Per-leg measurements are evaluated inside their own leg block (each leg's
    # tran is its own plot, so a trailing `let` could not see them).
    for m in exp.measurements:
        if m.leg is None:
            control.append(f"let meas_{m.name} = {m.expr}")
    for m in exp.measurements:
        if m.leg is None:
            control.append(f"print meas_{m.name}")
    control += ["quit", ".endc", ".end", ""]

    return "\n".join(head + body + control)


MEAS_RE = re.compile(r"^meas_([A-Za-z0-9_]+)\s*=\s*(-?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)")


def parse_measurements(log: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for line in log.splitlines():
        m = MEAS_RE.match(line.strip())
        if m:
            values[m.group(1)] = float(m.group(2))
    return values


def signal_name(signum: int) -> str:
    """POSIX name for a signal number, e.g. 9 -> 'SIGKILL'."""
    try:
        return signal.Signals(signum).name
    except ValueError:
        return f"signal {signum}"


def exit_note(rc: int, timed_out: bool, killed_by_signal: int | None) -> str:
    """One-line explanation of *why* a corner produced no measurement.

    The three failure modes are otherwise indistinguishable in the record: the
    harness's own timeout, a child killed by a signal from outside the harness
    (OOM killer, an operator, a session reaper), and a clean nonzero exit from
    ngspice itself.
    """
    if timed_out:
        return " (TIMEOUT — the harness killed ngspice after --timeout expired)"
    if killed_by_signal is not None:
        return (
            f" ({signal_name(killed_by_signal)} — ngspice was killed by a signal from"
            " OUTSIDE the harness; the harness did not time it out)"
        )
    return ""


def run_corner(
    exp: Experiment,
    pdk: Pdk,
    corner: Corner,
    body: list[str],
    run_dir: Path,
    log_path: Path | None,
    timeout: int,
) -> dict:
    deck_text = build_deck(exp, pdk, corner, body)
    deck_path = run_dir / f"{corner.id}.deck.spice"
    deck_path.write_text(deck_text)

    started = time.monotonic()
    try:
        proc = subprocess.run(
            ["ngspice", "-b", deck_path.name],
            cwd=run_dir,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        rc = -1
        timed_out = True
    elapsed_s = time.monotonic() - started

    # subprocess reports a signal-killed child as a NEGATIVE return code. The
    # harness's own timeout path above is the only place that sets rc = -1, so
    # any other negative rc means something outside the harness killed ngspice.
    killed_by_signal = None if timed_out else (-rc if rc < 0 else None)

    values = parse_measurements(stdout + "\n" + stderr)
    solver_diagnostic = detect_solver_diagnostic(stdout + "\n" + stderr)
    checks = []
    ok = rc == 0 and not timed_out and solver_diagnostic is None
    for m in exp.measurements:
        value = values.get(m.name)
        passed, reason = grade_bounds(m, value)
        checks.append(
            {
                "name": m.name,
                "expr": m.expr,
                "unit": m.unit,
                "value": value,
                "min": m.min,
                "max": m.max,
                "min_inclusive": m.min_inclusive,
                "max_inclusive": m.max_inclusive,
                "pass": passed,
                "reason": reason,
                **(
                    {
                        "leg": m.leg,
                        "cout_f": m.cout_f,
                        "esr_ohm": m.esr_ohm,
                        "direction": m.direction,
                    }
                    if m.leg is not None
                    else {}
                ),
            }
        )
        ok = ok and passed

    ramp_legs = []
    ramp_cfg = exp.raw.get("ramp_monotonicity")
    if ramp_cfg:
        ramp_legs = evaluate_legs(ramp_cfg, run_dir, corner.id)
        for leg in ramp_legs:
            passed = leg["pass"]
            checks.append(
                {
                    "name": f"ramp_drawdown_{leg['leg']}_v",
                    "expr": "ramp_monotonicity.max_drawdown(v(vout))",
                    "unit": "V",
                    "value": leg["max_drawdown_v"],
                    "min": None,
                    "max": leg["settings"]["tolerance_v"],
                    "pass": passed,
                    "reason": "" if passed else f"{leg['status']}: " + "; ".join(leg["reasons"]),
                }
            )
            ok = ok and passed
        if log_path is not None:
            for leg in ramp_legs:
                src = run_dir / leg["trace_file"]
                if src.is_file():
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, log_path.parent / leg["trace_file"])

    log_text = "\n".join(
        [
            f"# corner: {corner.id}",
            f"# process={corner.process} temp={fmt_temp(corner.temp_c)}C "
            f"supply={corner.supply_v:.2f}V",
            f"# ngspice exit: {rc}{exit_note(rc, timed_out, killed_by_signal)}",
            f"# wall clock: {elapsed_s:.1f}s (--timeout was {timeout}s)",
            f"# result: {'PASS' if ok else 'FAIL'}",
            *(
                [f"# solver diagnostic: {solver_diagnostic}"]
                if solver_diagnostic is not None
                else []
            ),
            "",
            "# ngspice was given TWO inputs: the deck below and the .spiceinit below",
            "# it. To reproduce this corner by hand, write the `|`-prefixed deck to",
            f"# {corner.id}.spice, write the `|`-prefixed .spiceinit block to",
            "# `.spiceinit` in the SAME directory, then run",
            f"#     ngspice -b {corner.id}.spice",
            "# Both are required: .spiceinit selects the linear solver, so a run",
            "# without it can differ in its solver diagnostics (issue #190).",
            "",
            "# ==== deck (1st input: the .spice file given to ngspice) ====",
            *[f"| {ln}" for ln in deck_text.splitlines()],
            "",
            *spiceinit_log_section(run_dir),
            "",
            "# ==== ngspice stdout ====",
            stdout.rstrip(),
            "",
            "# ==== ngspice stderr ====",
            stderr.rstrip(),
            "",
        ]
    )
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(log_text)
    if not ok:
        # Failure diagnostics survive --no-write (issue #288): the full
        # simulator log lands next to the deck in the scratch run dir, which CI
        # uploads as an artifact on failure.
        (run_dir / f"{corner.id}.fail.log").write_text(log_text)
        print(f"  ngspice diagnostics ({corner.id}, exit {rc}):", file=sys.stderr)
        for ln in (stdout + "\n" + stderr).splitlines():
            if re.search(r"error|undefined|fatal|cannot|timestep too small", ln, re.I):
                print(f"    {ln.strip()[:200]}", file=sys.stderr)
        print(f"  full log: {run_dir / (corner.id + '.fail.log')}", file=sys.stderr)

    return {
        "corner_id": corner.id,
        "process": corner.process,
        "temperature_c": corner.temp_c,
        "supply_v": corner.supply_v,
        "ngspice_exit": rc,
        "timed_out": timed_out,
        "killed_by_signal": killed_by_signal,
        "killed_by_signal_name": (
            signal_name(killed_by_signal) if killed_by_signal is not None else None
        ),
        "elapsed_s": round(elapsed_s, 3),
        "timeout_s": timeout,
        "measurements": checks,
        **({"ramp_monotonicity": ramp_legs} if ramp_legs else {}),
        "solver_diagnostic": solver_diagnostic,
        "pass": ok,
        "log": str(log_path.relative_to(REPO_ROOT)) if log_path is not None else None,
    }


# --------------------------------------------------------------------------
# window-grid aggregation (issue #313)
# --------------------------------------------------------------------------

GRID_FAILURE_CAP = 200  # failing conditions itemised in the record (count is exact)


def grid_coverage(exp: Experiment, results: list[dict], corners: list[Corner]) -> dict | None:
    """Conservative campaign-level verdict for a manifest's COUT/ESR window grid.

    The grid PASSes only if EVERY declared (corner x COUT x ESR x direction)
    measurement is present, finite, within its manifest bounds AND flagged
    passing by the per-corner run. The expected set is derived from the manifest
    and the corner matrix, never from what the results happen to contain, so a
    missing leg, a missing corner, a NaN/unparsable value, or one failed
    condition can only lower the verdict. Returns None for an experiment with no
    `window_grid`.
    """
    grid = exp.raw.get("window_grid")
    if not grid:
        return None
    by_corner = {r.get("corner_id"): r for r in results}
    leg_ms = [m for m in exp.measurements if m.leg is not None]
    expected = evaluated = passing = 0
    failures: list[dict] = []
    n_failures = 0
    for corner in corners:
        res = by_corner.get(corner.id)
        present = {c.get("name"): c for c in (res or {}).get("measurements") or []}
        for m in leg_ms:
            expected += 1
            check = present.get(m.name)
            value = None if check is None else check.get("value")
            if check is None or value is None:
                status, reason = "missing", "no result for this condition"
            elif not _finite_number(value):
                status, reason = "non-finite", "value is NaN/inf"
            else:
                evaluated += 1
                if m.min is not None and value < m.min:
                    status, reason = "fail", f"below min {m.min:g}"
                elif m.max is not None and value > m.max:
                    status, reason = "fail", f"above max {m.max:g}"
                elif check.get("pass") is not True:
                    status, reason = "fail", check.get("reason") or "flagged failing"
                else:
                    status, reason = "pass", ""
            if status == "pass":
                passing += 1
                continue
            n_failures += 1
            if len(failures) < GRID_FAILURE_CAP:
                failures.append(
                    {
                        "corner_id": corner.id,
                        "process": corner.process,
                        "temperature_c": corner.temp_c,
                        "supply_v": corner.supply_v,
                        "leg": m.leg,
                        "cout_f": m.cout_f,
                        "esr_ohm": m.esr_ohm,
                        "direction": m.direction,
                        "measurement": m.name,
                        "status": status,
                        "value": value if _finite_number(value) else None,
                        "reason": reason,
                    }
                )
        # Issue #336: a grid leg whose startup ramp-monotonicity trace is
        # missing/INVALID/failing must lower the grid verdict, not only the
        # corner's, so the ramp verdict of every declared leg is a condition.
        ramp_cfg = exp.raw.get("ramp_monotonicity") or {}
        by_leg = {leg["id"]: leg for leg in grid["legs"]}
        for rleg in ramp_cfg.get("legs") or []:
            expected += 1
            name = f"ramp_drawdown_{rleg['id']}_v"
            check = present.get(name)
            value = None if check is None else check.get("value")
            if check is None or value is None:
                status, reason = "missing", "no valid ramp-monotonicity trace for this condition"
            elif not _finite_number(value):
                status, reason = "non-finite", "value is NaN/inf"
            else:
                evaluated += 1
                if check.get("pass") is True:
                    passing += 1
                    continue
                status, reason = "fail", check.get("reason") or "flagged failing"
            n_failures += 1
            if len(failures) < GRID_FAILURE_CAP:
                gl = by_leg.get(rleg["id"], {})
                failures.append(
                    {
                        "corner_id": corner.id,
                        "process": corner.process,
                        "temperature_c": corner.temp_c,
                        "supply_v": corner.supply_v,
                        "leg": rleg["id"],
                        "cout_f": gl.get("cout_f"),
                        "esr_ohm": gl.get("esr_ohm"),
                        "direction": "ramp",
                        "measurement": name,
                        "status": status,
                        "value": value if _finite_number(value) else None,
                        "reason": reason,
                    }
                )
    complete = expected > 0 and evaluated == expected
    return {
        "title": grid.get("title", ""),
        "legs": [
            {"id": leg["id"], "cout_f": leg["cout_f"], "esr_ohm": leg["esr_ohm"]}
            for leg in grid["legs"]
        ],
        "directions": list(grid.get("directions") or []),
        "leg_order": list(exp.leg_order or [leg["id"] for leg in grid["legs"]]),
        "pvt_points": len(corners),
        "conditions_expected": expected,
        "conditions_evaluated": evaluated,
        "conditions_passing": passing,
        "complete": complete,
        "pass": complete and passing == expected,
        "n_failing_or_missing": n_failures,
        "failures": failures,
        "failures_truncated": max(0, n_failures - len(failures)),
        "sampling_statement": grid.get("sampling_statement", ""),
        "coverage_note": (
            "PVT coverage and COUT/ESR coverage are separate axes: this record ran "
            f"{len(corners)} PVT point(s) x {len(grid['legs'])} declared COUT/ESR leg(s); "
            "the legs are a finite sample of the DR-002 window, not a continuous proof."
        ),
    }


# --------------------------------------------------------------------------
# spread checks (is the harness actually corner-aware?)
# --------------------------------------------------------------------------


def spread_checks(exp: Experiment, results: list[dict]) -> list[dict]:
    out = []
    for check in exp.raw.get("spread_checks") or []:
        name = check["measurement"]
        values = [
            c["value"]
            for r in results
            for c in r["measurements"]
            if c["name"] == name and c["value"] is not None
        ]
        spread = (max(values) - min(values)) if len(values) > 1 else 0.0
        passed = len(values) > 1 and spread >= float(check["min_spread"])
        out.append(
            {
                "measurement": name,
                "min_spread": float(check["min_spread"]),
                "observed_spread": spread,
                "n": len(values),
                "pass": passed,
                "note": check.get("note", ""),
                "reason": (
                    ""
                    if passed
                    else (
                        "fewer than two corner points"
                        if len(values) < 2
                        else "spread below min_spread -- corners may not be taking effect"
                    )
                ),
            }
        )
    return out


# --------------------------------------------------------------------------
# opt-in `klt sim` batch backend (issue #298) -- sim/bin/_batch_backend.py
# --------------------------------------------------------------------------
#
# The backend moved to an importable sibling module (issue #580); its names are
# re-exported in the import block above, so `corner_run.<name>` still resolves
# for every `load_corner_run_module()` consumer. Nothing else about it changed:
# it is still BOUNDED to the allowlisted experiment shapes, still refuses every
# other manifest before any netlisting or submission, and still leaves the
# local path untouched -- see `_batch_backend.py`'s own header and sim/README.md
# "Batch backend".
# --------------------------------------------------------------------------
# record rendering
# --------------------------------------------------------------------------


def cold_start_adapter_info(exp: Experiment) -> dict:
    """Provenance of the issue #374 adapter for a batch record / dry run."""
    allowed = BATCH_ALLOWLIST[exp.slug]
    step = cold_start_step(exp)
    return {
        "name": "cold-start-crossing",
        "issue": 374,
        "step": step["name"],
        "analysis": f"{step['analysis']['kind']} {step['analysis']['args']}",
        "cards": [m["spice"] for m in step["measurements"] if "spice" in m],
        "graded": [m.name for m in exp.measurements],
        "validated_manifest_sections": dict(allowed["manifest_sections"]),
        "validated_stimulus": list(allowed["stimulus"]),
    }


def endpoint_adapter_info(exp: Experiment) -> dict:
    """Provenance of the issue #379 adapter for a batch record / dry run."""
    allowed = BATCH_ALLOWLIST[exp.slug]
    endpoints = endpoint_deck(exp)
    mod = endpoint_module(exp)
    name, issue = {
        biq: ("iq-endpoints", 213), bld: ("load-regulation-endpoints", 381),
    }.get(mod, ("line-regulation-endpoints", 379))
    return {
        "name": name,
        "issue": issue,
        "endpoints": [
            {
                "step": e.step_name, "vin": e.vin, "iload": e.iload,
                "analysis": f"tran {e.tran_args}",
                "sources": endpoint_module(exp).endpoint_source_lines(e),
                "cards": [text for _, _, text in e.cards],
            }
            for e in endpoints
        ],
        "graded": [{"name": m.name, "expr": m.expr} for m in exp.measurements],
        "validated_manifest_sections": dict(allowed["manifest_sections"]),
        "validated_baseline_stimulus": list(allowed["stimulus"]),
    }


def _vin_label(vin) -> str:
    """A fixed VIN literal gets a unit; the load-regulation corner-supply
    parameter (`'vsup'`) is shown as is."""
    return str(vin) if str(vin).startswith("'") else f"{vin} V"


def render_batch_execution(record: dict) -> list[str]:
    """Requested vs klt-reported execution environment of a batch record."""
    ex = record["execution"]
    lines = [
        f"- **Execution backend**: requested `{ex['requested_backend']}` via `klt sim` "
        f"({len(ex['requests'])} request(s), one per fixed supply value unless `--quick`, "
        "and one per COUT/ESR window-grid leg where the manifest declares a grid); "
        "ngspice ran **on the remote executor, not this machine** and no local ngspice "
        "exit code exists for these corners"
    ]
    for rq in ex["requests"]:
        remote = rq.get("remote") or {}
        detail = ", ".join(
            f"{k}=`{remote[k]}`"
            for k in ("provider", "job_id", "instance_type", "lifecycle", "region", "elapsed_seconds")
            if remote.get(k) is not None
        )
        lines.append(
            f"  - request `{rq['key']}` ({rq['supply_v']:g} V, {rq['n_points']} point(s)): "
            f"reported backend `{rq.get('reported_backend') or 'not reported'}`, "
            f"engine {rq.get('engine') or '?'} {rq.get('engine_version') or '?'}, "
            f"klt {rq.get('klt_version') or '?'}, job `{rq.get('job_id') or 'not reported'}`"
            + (f" ({detail})" if detail else "")
        )
        lines.append(
            f"    - klt provenance.pdk.version `{rq.get('pdk_version') or 'not reported'}` — "
            + ("names" if rq.get("klt_pdk_names_pin") else "**does NOT name**")
            + " the pinned open_pdks commit"
        )
    if ex.get("adapter") and ex["adapter"].get("name") in (
        "line-regulation-endpoints", "load-regulation-endpoints", "iq-endpoints",
    ):
        ad = ex["adapter"]
        lines.append(
            f"- **Batch adapter**: `{ad['name']}` (issue #{ad['issue']}): one single-step "
            "`analysis_steps` request per supply group x endpoint ("
            + "; ".join(
                f"`{e['step']}` = `tran {e['analysis'].split(' ', 1)[1]}` at VIN {_vin_label(e['vin'])}, "
                f"I_LOAD {e['iload']}"
                for e in ad["endpoints"]
            )
            + "); each request's netlist carries that endpoint's complete VIN / EN-PWL / load "
            "state, EN's high level equal to VIN; raw endpoint values come back as "
            "`tran<N>.<card>` and the slopes/deltas, windows and bounds are graded locally "
            "(offline translation checks do not establish local/fleet numerical equivalence)"
        )
    elif ex.get("adapter"):
        ad = ex["adapter"]
        lines.append(
            f"- **Batch adapter**: `{ad['name']}` (issue #{ad['issue']}): one `analysis_steps` "
            f"step `{ad['step']}` running `{ad['analysis']}` (no operating-point solve), cards "
            + ", ".join(f"`{c}`" for c in ad["cards"])
            + "; stimulus sent verbatim in the request netlist and checked against the "
            "validated lines; graded locally with the manifest's own bounds"
        )
    lines.append(
        f"- **ngspice init settings**: `{record['tools'].get('spiceinit_file', 'sim/spiceinit')}` "
        f"(sha256 `{record['tools'].get('spiceinit_sha256', '?')}`) sent as the request's "
        "`options.ngspice_init` lines (empty lines dropped, order kept)"
    )
    return lines


def render_window_grid(g: dict) -> list[str]:
    """Markdown block for a record's COUT/ESR window-grid verdict (issue #313)."""

    def eng(v: float) -> str:
        return f"{v:g}"

    out = [
        "- **COUT/ESR window grid** (separate from the PVT matrix above): "
        + ("COMPLETE" if g["complete"] else "INCOMPLETE")
        + f" -- {g['conditions_passing']}/{g['conditions_expected']} declared "
        "(corner x COUT x ESR x direction) conditions present, finite and passing; "
        f"grid verdict **{'PASS' if g['pass'] else 'FAIL'}**.",
        "  - Declared legs (COUT F / ESR ohm): "
        + ", ".join(f"`{x['id']}` ({eng(x['cout_f'])} / {eng(x['esr_ohm'])})" for x in g["legs"])
        + "; directions: "
        + ", ".join(g["directions"])
        + ".",
        f"  - {g['coverage_note']}",
        f"  - {g['sampling_statement']}",
    ]
    if not g["pass"]:
        out.append(
            f"  - A missing leg, an unparsable/NaN value or any failed condition makes the "
            f"grid FAIL: {g['n_failing_or_missing']} condition(s) failed or are missing"
            + (
                f" (first {len(g['failures'])} itemised; the rest are in the JSON record's "
                "per-corner measurements)"
                if g["failures_truncated"]
                else ""
            )
            + "."
        )
        for f in g["failures"][:20]:
            val = "n/a" if f["value"] is None else f"{f['value']:.6g}"
            out.append(
                f"    - {f['corner_id']} (process {f['process']}, {fmt_temp(f['temperature_c'])} C, "
                f"{f['supply_v']:.2f} V) COUT={eng(f['cout_f'])} F ESR={eng(f['esr_ohm'])} ohm "
                f"{f['direction']}: `{f['measurement']}` {f['status']} ({val}"
                + (f"; {f['reason']}" if f["reason"] else "")
                + ")"
            )
    return out


def render_record(record: dict) -> str:
    r = record
    tools = r["tools"]
    tools_line = f"{tools['ngspice']}; {tools['xschem']}; {tools['platform']}"
    lines = render_record_header(r, tools_line)

    # issue #190: the deck is not the whole ngspice input. Name the
    # `.spiceinit` that was in force, so the record says which solver
    # configuration produced these numbers. `.get()` because records minted
    # before #190 have no such field.
    if tools.get("declared"):
        decl = ", ".join(f"{t} {v}" for t, v in tools["declared"].items())
        lines.append(
            f"- **toolchain baseline** (`sim/pdk.json` tools): {decl} — "
            + ("recorded ON baseline" if tools.get("on_baseline") else "recorded on DRIFTED tools")
        )
    if r.get("backend") == "batch":
        lines.extend(render_batch_execution(r))
    elif tools.get("spiceinit_sha256"):
        lines.append(
            f"- **ngspice init settings**: `{tools.get('spiceinit_file', 'sim/spiceinit')}` "
            f"(sha256 `{tools['spiceinit_sha256']}`), copied into the run directory as "
            "`.spiceinit` and read by ngspice alongside each deck; it selects the linear "
            "solver, so reproducing a corner by hand requires it (each corner log embeds "
            "its own copy)"
        )

    matrix = r["matrix"]
    lines.append("- **Corner matrix run**:")
    lines.append(f"  - Process: {', '.join(matrix['process'])}")
    lines.append(
        "  - Temperature: " + ", ".join(f"{fmt_temp(t)} °C" for t in matrix["temperature_c"])
    )
    lines.append("  - Supply: " + ", ".join(f"{v:.2f} V" for v in matrix["supply_v"]))
    lines.append(f"  - {matrix['n_points']} corner point(s) executed")
    axes_product = (
        len(matrix["process"]) * len(matrix["temperature_c"]) * len(matrix["supply_v"])
    )
    if matrix["n_points"] != axes_product:
        lines.append(
            "  - Explicit point list (not the full cross product of the axes above): "
            + ", ".join(f"`{p}`" for p in matrix["point_ids"])
        )
    if matrix["is_subset"]:
        lines.append(f"  - **Subset of the full PVT matrix.** Reason: {matrix['subset_reason']}")
    else:
        lines.append(
            "  - Full PVT matrix declared in `experiment.json` "
            "(−40/27/125 °C × supply corners × process corners)"
        )
    lines.append(f"- **Statistical convention**: {r['experiment']['statistical_convention']}")
    if r.get("window_grid"):
        lines.extend(render_window_grid(r["window_grid"]))

    lines.append("- **Result**:")
    for res in r["corners"]:
        parts = []
        for c in res["measurements"]:
            value = "n/a" if c["value"] is None else f"{c['value']:.6g}{c['unit']}"
            parts.append(f"{c['name']}={value}")
        verdict = "PASS" if res["pass"] else "FAIL"
        detail = "; ".join(parts)
        why = ""
        fails = [c["reason"] for c in res["measurements"] if not c["pass"] and c["reason"]]
        if res.get("solver_diagnostic"):
            fails.append(f"solver diagnostic: {res['solver_diagnostic']}")
        if res.get("execution") == "batch":
            # remote result: no local ngspice exit code exists to report
            fails.extend(res.get("batch_reasons") or [])
        elif res["timed_out"]:
            fails.append(
                "ngspice TIMED OUT — the harness killed it after "
                f"--timeout {res.get('timeout_s', '?')}s"
            )
        elif res.get("killed_by_signal") is not None:
            fails.append(
                f"ngspice was KILLED BY {res['killed_by_signal_name']} "
                f"(exit {res['ngspice_exit']}) after {res.get('elapsed_s', '?')}s — a signal "
                "from OUTSIDE the harness, not a harness timeout; investigate the machine "
                "(OOM killer, session reaper, operator), not --timeout"
            )
        elif res["ngspice_exit"] != 0:
            fails.append(f"ngspice exit {res['ngspice_exit']} (clean nonzero exit, no signal)")
        if fails:
            why = f" — {'; '.join(fails)}"
        lines.append(f"  - {res['corner_id']}: {verdict} ({detail}){why}")
    if r.get("ramp_monotonicity_settings"):
        cfg = r["ramp_monotonicity_settings"]
        lines.append(
            "- **Ramp-monotonicity checker settings** (issue #309; `sim/README.md`, "
            f"\"Startup ramp monotonicity\"): `{json.dumps(cfg, sort_keys=True)}`. Raw "
            "`<corner>.<leg>.trace.dat` files (time, V(VOUT)) are retained beside the "
            "per-corner logs; per-leg sha256, drawdown, worst interval and sampling "
            "resolution are in the machine-readable record."
        )
        for res in r["corners"]:
            for leg in res.get("ramp_monotonicity") or []:
                iv = leg.get("worst_interval_s")
                lines.append(
                    f"  - {res['corner_id']} leg `{leg['leg']}`: {leg['status']}, drawdown "
                    f"{'n/a' if leg['max_drawdown_v'] is None else format(leg['max_drawdown_v'], '.6g') + ' V'}"
                    + (f", worst interval {iv[0]:.6g}-{iv[1]:.6g} s" if iv else "")
                    + ", worst sample gap "
                    + ("n/a" if leg["resolution_s"] is None else f"{leg['resolution_s']:.3g} s")
                )
    for sc in r["spread_checks"]:
        verdict = "PASS" if sc["pass"] else "FAIL"
        lines.append(
            f"  - corner-sensitivity check on `{sc['measurement']}`: {verdict} "
            f"(observed spread {sc['observed_spread']:.6g} over {sc['n']} points, "
            f"required ≥ {sc['min_spread']:g})"
            + (f" — {sc['reason']}" if sc["reason"] else "")
        )
    lines.append(f"  - **Overall: {'PASS' if r['overall_pass'] else 'FAIL'}**")

    lines.append("- **Links**:")
    lines.append(f"  - Testbench: `{r['links']['testbench']}`")
    lines.append(f"  - Netlist snapshot: `{r['links']['netlist_snapshot']}`")
    lines.append(f"  - Raw per-corner logs: `{r['links']['corners_dir']}`")
    for key, path in (r["links"].get("klt_requests") or {}).items():
        lines.append(f"  - klt sim request `{key}`: `{path}`")
    for key, path in (r["links"].get("klt_responses") or {}).items():
        lines.append(f"  - klt sim response `{key}` (raw): `{path}`")
    for key, path in (r["links"].get("request_netlists") or {}).items():
        lines.append(f"  - Request netlist `{key}`: `{path}`")
    lines.append(f"  - Machine-readable record: `{r['links']['json']}`")
    lines.append(f"  - Experiment manifest: `{r['links']['manifest']}`")
    lines.extend(render_record_footer(r, "corner-run.py"))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def csv_list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def csv_floats(value: str) -> list[float]:
    return [float(v) for v in csv_list(value)]


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="PVT corner runner for sky130-ldo (see sim/README.md)"
    )
    p.add_argument("experiment", nargs="?", help="path to sim/<experiment-slug>/")
    p.add_argument("--print-env", action="store_true", help="print PDK env exports and exit")
    p.add_argument(
        "--check-env",
        action="store_true",
        help="check ngspice/xschem/volare/PDK are usable and exit (0 if all OK)",
    )
    p.add_argument(
        "--require-pdk",
        action="store_true",
        help="with --check-env: a tool version differing from sim/pdk.json 'tools' "
        "is a FAIL instead of a WARN",
    )
    p.add_argument("--process", type=csv_list, help="process corners (default: manifest)")
    p.add_argument("--temp", type=csv_floats, help="temperatures in °C (default: manifest)")
    p.add_argument("--supply", type=csv_floats, help="supply voltages (default: manifest)")
    p.add_argument("--quick", action="store_true", help="run the manifest's quick_subset only")
    p.add_argument(
        "--subset-reason",
        default="",
        help="why a subset of the full PVT matrix is acceptable (required for subsets)",
    )
    p.add_argument(
        "--leg-order",
        type=csv_list,
        help="window_grid leg execution order (a permutation of the declared legs); "
        "leg-order independence smoke check, issue #313",
    )
    p.add_argument("--supersedes", default="", help="record id this run supersedes")
    p.add_argument("--author", default="", help="record author (default: git user.email)")
    p.add_argument("--timeout", type=int, default=300, help="per-corner ngspice timeout (s)")
    p.add_argument(
        "--backend",
        choices=["local", "batch"],
        default="local",
        help="execution backend. `local` (default) runs ngspice here, one process per "
        "corner. `batch` hands the grid to `klt sim --backend batch` (one request per "
        "supply value, and per window-grid leg); opt-in and bounded to the unchanged "
        "sim/pdk-smoke shape, the sim/load-transient window grid and the validated "
        "sim/dropout-vs-load cold-start crossing -- every other experiment is "
        "refused (see sim/README.md, \"Batch backend\")",
    )
    p.add_argument(
        "--allow-pdk-mismatch",
        action="store_true",
        help="run even if the installed PDK differs from the sim/pdk.json pin",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="netlist and print the corner list and one deck, run nothing, write nothing",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help="run every corner for real (ngspice included) but do not write an "
        "evidence record under sim/<experiment>/ -- for CI/selftest liveness runs "
        "that should not mint new evidence on every push",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    pin = load_pin()

    if args.check_env:
        return check_env(require_pdk=args.require_pdk)

    pdk = resolve_pdk(pin)

    if args.print_env:
        print_env(pdk)
        return 0

    if not args.experiment:
        raise HarnessError(
            "give an experiment directory, e.g. sim/pdk-smoke "
            "(or --print-env / --check-env)"
        )

    if not pdk.matches_pin and not args.allow_pdk_mismatch:
        raise HarnessError(
            f"installed PDK {pdk.variant} is open_pdks {pdk.installed_commit}, "
            f"but sim/pdk.json pins {pin['open_pdks_commit']}\n"
            f"  install the pin: {pin['install_command']}\n"
            f"  or re-run with --allow-pdk-mismatch (the record will say so)"
        )

    exp = load_experiment(Path(args.experiment))
    if args.leg_order:
        declared = [leg["id"] for leg in window_legs(exp.raw)]
        if sorted(args.leg_order) != sorted(declared):
            raise HarnessError(
                f"--leg-order must be a permutation of the declared window_grid legs: {declared}"
            )
        exp.leg_order = list(args.leg_order)
    batch = args.backend == "batch"
    if batch:
        # Refuse before netlisting, submission or any local ngspice.
        check_batch_supported(exp)
        if args.leg_order:
            raise HarnessError(
                "--leg-order is local-only: under --backend batch every window-grid leg is "
                "its own klt sim request (its own ngspice process), so there is no in-deck "
                "leg order to permute"
            )
        if not args.dry_run:
            klt_binary()  # fail fast if klt is missing
    matrix, is_subset = build_matrix(exp, args, pin)
    if not matrix:
        raise HarnessError("empty corner matrix")
    if is_subset and not args.subset_reason:
        raise HarnessError(
            "this run is a subset of the full PVT matrix; pass --subset-reason "
            '"..." so the record states why (CLAUDE.md: PVT corners on every '
            "recorded result)"
        )

    git_info = git_state()
    now = datetime.now(timezone.utc)
    record_id = f"{now:%Y%m%d}-{now:%H%M%S}-{git_info['sha']}"

    records_dir = exp.dir / "records"
    snapshots_dir = exp.dir / "netlist-snapshots"
    corners_dir = exp.dir / "corners" / record_id
    record_md = records_dir / f"{record_id}.md"
    record_json = records_dir / f"{record_id}.json"
    snapshot = snapshots_dir / f"{record_id}.spice"

    requests_dir = exp.dir / "klt-requests"
    responses_dir = exp.dir / "klt-responses"
    request_netlists_dir = exp.dir / "klt-request-netlists"

    if not args.dry_run and not args.no_write:
        # Atomic claim BEFORE any scratch dir/evidence is written (issue #310).
        reserve_record_id(BUILD_DIR, exp.dir.name, record_id, HarnessError)

    if not args.dry_run and not args.no_write:
        extra = []
        if batch:
            extra = [
                p
                for d in (requests_dir, responses_dir, request_netlists_dir)
                for p in (d.glob(f"{record_id}.*") if d.is_dir() else [])
            ]
        for path in (record_md, record_json, snapshot, corners_dir, *extra):
            if path.exists():
                raise HarnessError(
                    f"{path} already exists — sim/ is append-only, refusing to overwrite"
                )

    store = None
    if not args.dry_run and not args.no_write:
        # Fail closed BEFORE simulating: new evidence bytes go to the artifact
        # store, never into git (issue #436).
        try:
            store = _evidence_store.EvidenceRun(
                REPO_ROOT, exp.dir.name, record_id, _evidence_store.preflight()
            )
        except _evidence_store.EvidenceStoreError as err:
            raise HarnessError(str(err)) from err

    run_dir = BUILD_DIR / exp.slug / record_id
    if args.dry_run or args.no_write:
        # no evidence => no reservation, so keep scratch off any real run's dir
        run_dir = BUILD_DIR / exp.slug / f"{record_id}.ephemeral-{os.getpid()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SPICEINIT_FILE, run_dir / ".spiceinit")

    netlist = netlist_with_xschem(exp.schematic, run_dir, pdk)
    body = netlist_body(netlist)

    print(f"experiment      : {exp.slug}")
    print(f"record id       : {record_id}" + (" (not written: --no-write)" if args.no_write else ""))
    print(f"PDK             : {pdk.dir} (open_pdks {pdk.installed_commit})")
    print(f"testbench       : {exp.schematic.relative_to(REPO_ROOT)}")
    print(f"corner points   : {len(matrix)}" + (" (SUBSET)" if is_subset else " (full matrix)"))
    print(f"scratch run dir : {run_dir}")

    if batch:
        prepared = prepare_batch_requests(
            exp, pdk, matrix, args.quick, body, run_dir, args.timeout
        )
        print(f"backend         : batch ({len(prepared)} klt sim request(s))")

    if args.dry_run and batch:
        if is_endpoint_adapter(exp):
            ad = endpoint_adapter_info(exp)
            print(f"\n-- batch adapter {ad['name']} (issue #{ad['issue']}) --")
            for e in ad["endpoints"]:
                print(f"  {e['step']}: {e['analysis']}; VIN={e['vin']} I_LOAD={e['iload']}")
                for line in e["sources"].values():
                    print(f"    source (request netlist): {line}")
                for c in e["cards"]:
                    print(f"    card : {c}")
        if is_cold_start_crossing(exp):
            ad = cold_start_adapter_info(exp)
            print(f"\n-- batch adapter {ad['name']} (issue #374) --")
            print(f"  step {ad['step']}: {ad['analysis']}")
            for c in ad["cards"]:
                print(f"  card : {c}")
            for ln in ad["validated_stimulus"]:
                print(f"  stimulus (verified in each request netlist): {ln}")
        print("\n-- corner list --")
        for corner in matrix:
            print(f"  {corner.id}")
        for group, request_path, request in prepared:
            print(f"\n-- klt sim request {group.key} (dry run; netlist: {request['netlist']}) --")
            print(json.dumps(request, indent=2))
        print("\n(dry run: klt sim not invoked, nothing submitted, nothing written under "
              "sim/<experiment>/)")
        return 0

    if args.dry_run:
        print("\n-- corner list --")
        for corner in matrix:
            print(f"  {corner.id}")
        print(f"\n-- deck for {matrix[0].id} --")
        print(build_deck(exp, pdk, matrix[0], body))
        print("\n(dry run: ngspice not invoked, nothing written under sim/<experiment>/)")
        return 0

    results = []
    batch_logs: dict[str, str] = {}
    execution = None
    if batch:
        results, batch_logs, execution = run_batch(
            exp, pdk, pin, prepared, matrix, run_dir, args.timeout, args.allow_pdk_mismatch
        )
    for i, corner in enumerate([] if batch else matrix, start=1):
        log_path = None if args.no_write else store.stage / "corners" / record_id / f"{corner.id}.log"
        res = run_corner(exp, pdk, corner, body, run_dir, log_path, args.timeout)
        results.append(res)
        summary = ", ".join(
            f"{c['name']}={'n/a' if c['value'] is None else format(c['value'], '.6g')}"
            for c in res["measurements"]
        )
        print(
            f"[{i:>3}/{len(matrix)}] {corner.id:<20} "
            f"{'PASS' if res['pass'] else 'FAIL'}  {summary}"
        )

    if batch:
        for i, (corner, res) in enumerate(zip(matrix, results), start=1):
            summary = ", ".join(
                f"{c['name']}={'n/a' if c['value'] is None else format(c['value'], '.6g')}"
                for c in res["measurements"]
            )
            print(
                f"[{i:>3}/{len(matrix)}] {corner.id:<20} "
                f"{'PASS' if res['pass'] else 'FAIL'}  {summary}"
            )
            for why in res["batch_reasons"]:
                print(f"      {why}", file=sys.stderr)

    spreads = spread_checks(exp, results)
    grid = grid_coverage(exp, results, matrix)
    overall = (
        all(r["pass"] for r in results)
        and all(s["pass"] for s in spreads)
        and (grid is None or grid["pass"])
    )
    if grid is not None:
        print(
            f"window grid     : {grid['conditions_passing']}/{grid['conditions_expected']} "
            f"conditions passing ({'complete' if grid['complete'] else 'INCOMPLETE'}) -> "
            f"{'PASS' if grid['pass'] else 'FAIL'}"
        )

    if args.no_write:
        print()
        print("evidence : not recorded (--no-write)")
        print(f"overall  : {'PASS' if overall else 'FAIL'}")
        return 0 if overall else 2

    snapshot_rel = f"netlist-snapshots/{record_id}.spice"
    store.stage_text(snapshot_rel, "\n".join(body) + "\n.end\n")
    for res in results:
        if not batch:
            res["log"] = store.uri_label(f"corners/{record_id}/{res['corner_id']}.log")

    record = {
        "record_id": record_id,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "author": args.author or default_author(),
        "supersedes": args.supersedes,
        "experiment": {
            "slug": exp.slug,
            "title": exp.raw.get("title", exp.slug),
            "claim": exp.raw["claim"],
            "provenance": exp.raw.get("provenance", "schematic"),
            "provenance_source": exp.raw.get(
                "provenance_source", str(exp.schematic.relative_to(REPO_ROOT))
            ),
            "statistical_convention": exp.raw.get("statistical_convention", "N/A"),
        },
        "pdk": {
            "root": str(pdk.root),
            "variant": pdk.variant,
            "installed_commit": pdk.installed_commit,
            "pinned_commit": pin["open_pdks_commit"],
            "matches_pin": pdk.matches_pin,
            "lib_file": str(pdk.lib_file),
        },
        # The ngspice init settings are part of the input, not just the
        # toolchain — record their hash so the record says which solver
        # configuration produced it (issue #190).
        "tools": {**tool_versions(), **spiceinit_provenance()},
        # Versioned fingerprint of the effective experiment + solver inputs
        # (issue #237): the report's headless freshness check compares it.
        "input_fingerprint": build_input_fingerprint(
            "pvt", pvt_input_sections(exp.raw, SPICEINIT_FILE.read_text())
        ),
        "git": git_info,
        "matrix": {
            "process": unique_in_order(c.process for c in matrix),
            "temperature_c": sorted({c.temp_c for c in matrix}),
            "supply_v": sorted({c.supply_v for c in matrix}),
            "n_points": len(matrix),
            "is_subset": is_subset,
            "subset_reason": args.subset_reason,
            "points": [[c.process, c.temp_c, c.supply_v] for c in matrix],
            "point_ids": [c.id for c in matrix],
        },
        "corners": results,
        **(
            {"ramp_monotonicity_settings": exp.raw["ramp_monotonicity"]}
            if exp.raw.get("ramp_monotonicity")
            else {}
        ),
        "spread_checks": spreads,
        **({"window_grid": grid} if grid is not None else {}),
        "overall_pass": overall,
        "links": {
            "testbench": str(exp.schematic.relative_to(REPO_ROOT)),
            "manifest": str((exp.dir / "experiment.json").relative_to(REPO_ROOT)),
            "netlist_snapshot": store.uri_label(snapshot_rel),
            "corners_dir": store.uri_label(f"corners/{record_id}") + "/",
            "json": store.uri_label(f"records/{record_id}.json"),
            "artifact_manifest": store.manifest_rel(),
            "record": str(record_md.relative_to(REPO_ROOT)),
        },
    }

    if batch:
        record["backend"] = "batch"
        record["tools"] = batch_tools(record["tools"], execution)
        link_reqs, link_resps, link_nets = {}, {}, {}
        for rq in execution["requests"]:
            key = rq["key"]
            for d, src, ext, links in (
                (requests_dir, rq["request_file"], "json", link_reqs),
                (responses_dir, rq["response_file"], "json", link_resps),
                (request_netlists_dir, str(Path(rq["request_file"]).with_suffix(".spice")), "spice", link_nets),
            ):
                rel = f"{d.name}/{record_id}.{key}.{ext}"
                store.stage_file(rel, Path(src))
                links[key] = store.uri_label(rel)
        for cid, text in batch_logs.items():
            store.stage_text(f"corners/{record_id}/{cid}.log", text)
        for res in results:
            if res["corner_id"] in batch_logs:
                res["log"] = store.uri_label(f"corners/{record_id}/{res['corner_id']}.log")
        for rq in execution["requests"]:
            rq["request_file"] = link_reqs[rq["key"]]
            rq["response_file"] = link_resps[rq["key"]]
        record["execution"] = {"requested_backend": "batch", **execution}
        if is_cold_start_crossing(exp):
            record["execution"]["adapter"] = cold_start_adapter_info(exp)
        if is_endpoint_adapter(exp):
            record["execution"]["adapter"] = endpoint_adapter_info(exp)
        record["links"].update(
            {"klt_requests": link_reqs, "klt_responses": link_resps, "request_netlists": link_nets}
        )

    store.stage_text(f"records/{record_id}.json", json.dumps(record, indent=2, sort_keys=True) + "\n")
    try:
        entries = store.commit()
    except _evidence_store.EvidenceStoreError as err:
        raise HarnessError(f"evidence not stored, nothing committed: {err}") from err
    records_dir.mkdir(parents=True, exist_ok=True)
    summary = _evidence_store.render_summary(entries, store.manifest_rel())
    write_new_text(record_md, render_record(record) + "\n\n" + "\n".join(summary) + "\n")

    print()
    print(f"record  : {record_md.relative_to(REPO_ROOT)}")
    print(f"manifest: {store.manifest_rel()}")
    print(f"overall : {'PASS' if overall else 'FAIL'}")
    return 0 if overall else 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except HarnessError as err:
        print(f"corner-run: error: {err}", file=sys.stderr)
        sys.exit(1)
