"""The opt-in `klt sim` batch backend for `sim/bin/corner-run.py` (issue #298).

Extracted verbatim from `corner-run.py` (issue #580): it was already one
banner-delimited section there, and four non-test modules
(`sim/bin/batch-preflight.py`, `sim/bin/psrr-cap-sweep-run.py`,
`sim/thermal/run_hysteresis.py`, `layout/cap-study/run-cap-study.py`) plus the
`sim/tests/test_batch_*.py` suites already consumed it as a library through
`_record_common.load_corner_run_module()`'s importlib-by-path shim. This module
has an importable filename, so they can reach it with a plain `import`.

`corner-run.py` re-exports every public name below, so `corner_run.<name>`
keeps resolving for the `load_corner_run_module()` consumers unchanged. The
shared types and graders both modules need live in `_corner_model.py`; neither
this module nor the runner imports the other.

Standard library only, matching every `sim/bin/*.py` script's own convention.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import batch_dropout
import batch_iq as biq
import batch_line_regulation as blr
import batch_load_regulation as bld
from batch_window_grid import TranslationError, leg_step, parse_leg_template
from _corner_model import (
    Corner,
    Experiment,
    HarnessError,
    Measurement,
    Pdk,
    SPICEINIT_FILE,
    compare_tool_versions,
    detect_solver_diagnostic,
    grade_bounds,
    leg_values,
    unique_in_order,
    window_legs,
)
from _record_common import (
    assert_klt_read_the_pinned_pdk as _shared_assert_pdk,
    CAPACITY_RETRY_BUDGET_S,
    is_finite_number as _finite_number,
    klt_binary as _shared_klt_binary,
    pvt_input_sections,
    run_klt_sim,
)

#
# BOUNDED on purpose: only the unchanged `pdk-smoke` shape (one `op` analysis,
# two scalar measurements), the `load-transient` COUT/ESR window grid
# (issue #326: one single-step `tran` request per supply x leg, see
# sim/bin/batch_window_grid.py) and the `dropout-vs-load` cold-start crossing
# (issue #374: one single-step `tran ... uic` request per supply, see
# sim/bin/batch_dropout.py) may use it. Every other manifest is refused
# before any netlisting, submission or local ngspice -- see sim/README.md
# "Batch backend". The local path above is untouched; this section only adds a
# second way to obtain the same per-corner result dicts.

BATCH_ALLOWLIST = {
    "pdk-smoke": {
        "analyses": ["op"],
        "measurements": [("vgs", "v(vg)"), ("isup", "-i(v1)")],
    },
    # Shape: a `window_grid` whose leg_analyses translate to a klt step, every
    # measurement per-leg, and no deck-level analysis (comments only).
    "load-transient": {"window_grid": True},
    # Shape (issue #374): one cold-start `tran ... uic`, td-delayed crossing /
    # window-avg `meas tran` cards, graded expressions over those cards, and
    # the stimulus below sent verbatim in the netlist. RENEWAL: the manifest
    # is pinned by the record input-fingerprint digests of its execution
    # sections (analyses, measurements incl. bounds/inclusivity, matrix), so
    # ANY intentional change to them refuses the batch backend until the
    # translation is re-validated (sim/tests/test_batch_dropout_374.py) and
    # these digests are updated deliberately.
    "dropout-vs-load": {
        "cold_start_crossing": True,
        "manifest_sections": {
            "analyses": "bce00b423fb13bf2c527284fcf14780e6bcbfbc0417eaf652f54f538407a71c8",
            "measurements": "9c84c875c74b59ddf3bd20af49497817d30c0c250ade790ca1778949f22d7b19",
            "matrix": "639e50d5a920cef70120de11fefa3ffc5bf53f0446c56a853f87c39e95976b21",
        },
        "stimulus": [
            "VVIN VIN 0 PWL(0 0 100u 'vsup' 6m 'vsup' 14m 'vsup-2.13')",
            "VEN EN 0 PULSE(0 'vsup' 100u 1u 1u 100 200)",
            "ILOAD VOUT 0 PWL(0 0 2.5m 0 2.6m 50m)",
        ],
    },
    # Shape (issue #379): four independent cold-start endpoint points, each its
    # own single-step `tran ... uic` request (the per-point VIN / EN PWL / load
    # state travels in the request netlist; see sim/bin/batch_line_regulation.py).
    # RENEWAL: pinned exactly like dropout-vs-load, by the record
    # input-fingerprint digests (sim/tests/test_batch_line_regulation_379.py).
    "line-regulation": {
        "endpoint_adapter": True,
        "manifest_sections": {
            "analyses": "0cfeeac0f4e21500b2c5cca10b68e5d15ebc0e8a1c70a24fb917bd99d9938c48",
            "measurements": "6eae44b4f597147dc34d973ba0c061c5418708fef80a14a43d525dac2ed300fb",
            "matrix": "639e50d5a920cef70120de11fefa3ffc5bf53f0446c56a853f87c39e95976b21",
        },
        # the baseline (pre-`alter`) source lines each request rewrites
        "stimulus": [
            "VVIN VIN 0 3.3",
            "VEN EN 0 dc 0 pwl(0 0 100u 0 101u 3.3 10 3.3)",
            "ILOAD VOUT 0 1m",
        ],
        "baseline_iload": "1m",
    },
    # Shape (issue #381): TWO independent cold-start endpoints (no load, then
    # 50 mA), each its own single-step `tran ... uic` request. VIN and full-rail
    # EN stay the corner supply (`'vsup'`); only the load differs per request
    # (see sim/bin/batch_load_regulation.py). RENEWAL: pinned like
    # line-regulation, by the record input-fingerprint digests
    # (sim/tests/test_batch_load_regulation_381.py).
    "load-regulation": {
        "endpoint_adapter": True,
        "adapter_kind": "load-regulation",
        "manifest_sections": {
            "analyses": "e9064e2b26967ccb49de8a1b37e684c2a3cc4c44b0f83d12f01559ad04f7cfdb",
            "measurements": "1637b3f8f570b4f7cc458b2d82d3cdb8268cf1fea8f7db7a3dbbccf64ef25f76",
            "matrix": "639e50d5a920cef70120de11fefa3ffc5bf53f0446c56a853f87c39e95976b21",
        },
        # the baseline (pre-`alter`) source lines each request rewrites
        "stimulus": [
            "VVIN VIN 0 'vsup'",
            "VEN EN 0 dc 0 pwl(0 0 100u 0 101u 'vsup' 10 'vsup')",
            "ILOAD VOUT 0 0",
        ],
        "baseline_iload": "0",
    },
    # Shape (issue #213): the same TWO cold-start endpoints as load-regulation
    # (no load, then 50 mA; VIN and full-rail EN on the corner supply), each
    # with an `avg v(vout)` and an `avg i(vvin)` card (sim/bin/batch_iq.py).
    # RENEWAL: pinned like load-regulation (sim/tests/test_batch_iq_213.py).
    "iq": {
        "endpoint_adapter": True,
        "adapter_kind": "iq",
        "manifest_sections": {
            "analyses": "f3dba2c7ad5486123fbfddb60fcc5d731eb31a72dc4545cbbd699c239c3a263a",
            "measurements": "b9fb2b2a0068ef936c8b669deb20ec0ce4878f51fffcd8aefb766aa0d1fe2dc1",
            "matrix": "639e50d5a920cef70120de11fefa3ffc5bf53f0446c56a853f87c39e95976b21",
        },
        "stimulus": [
            "VVIN VIN 0 'vsup'",
            "VEN EN 0 dc 0 pwl(0 0 100u 0 101u 'vsup' 10 'vsup')",
            "ILOAD VOUT 0 0",
        ],
        "baseline_iload": "0",
    },
}

BATCH_REFUSAL_HINT = (
    "the batch backend is bounded to the unchanged sim/pdk-smoke shape (one `op` "
    "analysis, scalar measurements), the sim/load-transient COUT/ESR window "
    "grid (one `tran` step per leg) and the validated sim/dropout-vs-load "
    "cold-start crossing (one `tran ... uic` step per supply) and the validated "
    "sim/line-regulation endpoints (four single-step `tran ... uic` requests per "
    "supply) and the validated sim/load-regulation endpoints (two single-step "
    "`tran ... uic` requests per supply); every other "
    "experiment, including the other transient/AC/DC-sweep and mc-* manifests, "
    "stays on the local backend (see sim/README.md, \"Batch backend\")"
)


def is_cold_start_crossing(exp: Experiment) -> bool:
    """Whether the experiment runs through the issue #374 dropout adapter."""
    return bool(BATCH_ALLOWLIST.get(exp.slug, {}).get("cold_start_crossing"))


def cold_start_step(exp: Experiment) -> dict:
    """The klt `analysis_steps[]` entry for the cold-start crossing deck."""
    deck = batch_dropout.parse_deck((exp.raw.get("deck") or {}).get("analyses") or [])
    return batch_dropout.dropout_step(deck, [(m.name, m.expr, m.unit) for m in exp.measurements])


def check_cold_start_batch_shape(exp: Experiment) -> None:
    """Refuse a dropout manifest whose shape is not the validated one: the
    structural translation must succeed AND the execution sections must still
    digest to the pinned values (issue #374: an intentional manifest change
    requires renewed validation, never a silent pass-through)."""
    allowed = BATCH_ALLOWLIST[exp.slug]
    why = None
    if exp.raw.get("window_grid") or any(m.leg is not None for m in exp.measurements):
        why = "a window_grid / per_leg measurement is not part of the cold-start shape"
    elif exp.raw.get("spread_checks"):
        why = "spread_checks are not part of the validated cold-start shape"
    else:
        try:
            cold_start_step(exp)
        except batch_dropout.DropoutTranslationError as exc:
            why = f"deck does not translate to a cold-start klt step ({exc})"
    if why is None:
        got = pvt_input_sections(exp.raw, None)
        changed = [k for k, v in allowed["manifest_sections"].items() if got.get(k) != v]
        extra = sorted(set(got) - set(allowed["manifest_sections"]))
        if changed or extra:
            why = (
                f"manifest section(s) {changed + extra} changed since the adapter was validated "
                "(pinned digests in BATCH_ALLOWLIST); re-validate the translation and update "
                "the pins deliberately"
            )
    if why:
        raise HarnessError(
            f"--backend batch: {exp.slug!r} no longer has the validated cold-start crossing "
            f"shape ({why}): {BATCH_REFUSAL_HINT}"
        )


def is_endpoint_adapter(exp: Experiment) -> bool:
    """Whether the experiment runs through the issue #379 line-regulation
    endpoint adapter."""
    return bool(BATCH_ALLOWLIST.get(exp.slug, {}).get("endpoint_adapter"))


def endpoint_module(exp: Experiment):
    """The endpoint-adapter module for the experiment: load-regulation (issue
    #381) or, by default, line-regulation (issue #379). Both raise
    blr.EndpointTranslationError."""
    kind = BATCH_ALLOWLIST.get(exp.slug, {}).get("adapter_kind")
    if kind == "iq":
        return biq
    return bld if kind == "load-regulation" else blr


def endpoint_deck(exp: Experiment) -> list[blr.Endpoint]:
    """The endpoints of the deck (four line-regulation, two load-regulation),
    parsed and with every graded expression checked against them (raises
    EndpointTranslationError)."""
    endpoints = endpoint_module(exp).parse_deck(
        (exp.raw.get("deck") or {}).get("analyses") or [], BATCH_ALLOWLIST[exp.slug]["baseline_iload"]
    )
    blr.check_measurements(endpoints, [(m.name, m.expr, m.unit) for m in exp.measurements])
    return endpoints


def endpoint_step(exp: Experiment, endpoint_id: str) -> dict:
    """The klt `analysis_steps[]` entry for one endpoint request."""
    endpoints = endpoint_deck(exp)
    units = blr.check_measurements(endpoints, [(m.name, m.expr, m.unit) for m in exp.measurements])
    ep = next(e for e in endpoints if e.step_name == endpoint_id)
    return blr.endpoint_step(ep, units)


def check_endpoint_batch_shape(exp: Experiment) -> None:
    """Refuse a line-regulation manifest whose shape is not the validated one:
    the structural translation must succeed AND the execution sections must
    still digest to the pinned values (issue #379)."""
    allowed = BATCH_ALLOWLIST[exp.slug]
    why = None
    if exp.raw.get("window_grid") or any(m.leg is not None for m in exp.measurements):
        why = "a window_grid / per_leg measurement is not part of the endpoint shape"
    elif exp.raw.get("spread_checks"):
        why = "spread_checks are not part of the validated endpoint shape"
    else:
        try:
            endpoint_deck(exp)
        except blr.EndpointTranslationError as exc:
            why = f"deck does not translate to cold-start endpoint steps ({exc})"
    if why is None:
        got = pvt_input_sections(exp.raw, None)
        changed = [k for k, v in allowed["manifest_sections"].items() if got.get(k) != v]
        extra = sorted(set(got) - set(allowed["manifest_sections"]))
        if changed or extra:
            why = (
                f"manifest section(s) {changed + extra} changed since the adapter was validated "
                "(pinned digests in BATCH_ALLOWLIST); re-validate the translation and update "
                "the pins deliberately"
            )
    if why:
        raise HarnessError(
            f"--backend batch: {exp.slug!r} no longer has the validated {exp.slug} "
            f"endpoint shape ({why}): {BATCH_REFUSAL_HINT}"
        )


def batch_legs(exp: Experiment) -> list[str] | None:
    """Per-request leg ids a batch run splits into: window-grid legs, or the
    line-regulation endpoint ids; None for any other allowlisted experiment."""
    if is_endpoint_adapter(exp):
        return [e.step_name for e in endpoint_deck(exp)]
    if not BATCH_ALLOWLIST.get(exp.slug, {}).get("window_grid"):
        return None
    return [leg["id"] for leg in window_legs(exp.raw)]


def leg_template_name(m: Measurement) -> str:
    """The manifest template name of an expanded per-leg measurement."""
    suffix = "__" + str(m.leg)
    return m.name[: -len(suffix)] if m.name.endswith(suffix) else m.name


def window_grid_step(exp: Experiment, leg_id: str) -> dict:
    """The klt `analysis_steps[]` entry for one window-grid leg (issue #326)."""
    grid = exp.raw["window_grid"]
    leg = next(x for x in grid["legs"] if x["id"] == leg_id)
    template = parse_leg_template(grid["leg_analyses"])
    meas = [(leg_template_name(m), m.expr, m.unit) for m in exp.measurements if m.leg == leg_id]
    return leg_step(template, leg_id, leg_values(grid, leg), meas)


def check_window_grid_batch_shape(exp: Experiment) -> None:
    grid = exp.raw.get("window_grid")
    why = None
    if not grid or not window_legs(exp.raw):
        why = "no window_grid legs declared"
    elif any(
        ln.strip() and not ln.strip().startswith("*")
        for ln in (exp.raw.get("deck") or {}).get("analyses") or []
    ):
        why = "deck.analyses carries commands outside the leg block"
    elif any(m.leg is None for m in exp.measurements):
        why = "a measurement is not per-leg (it would need a deck-level analysis)"
    elif exp.raw.get("spread_checks"):
        why = "spread_checks are not defined for per-leg batch requests"
    else:
        try:
            for leg in window_legs(exp.raw):
                window_grid_step(exp, leg["id"])
        except (TranslationError, KeyError, StopIteration) as exc:
            why = f"window_grid leg block does not translate to a klt step ({exc})"
    if why:
        raise HarnessError(
            f"--backend batch: {exp.slug!r} no longer has the supported window-grid "
            f"shape ({why}): {BATCH_REFUSAL_HINT}"
        )


def klt_binary() -> str:
    return _shared_klt_binary("run batch PVT grids", error_cls=HarnessError)


def check_batch_supported(exp: Experiment) -> None:
    """Refuse an experiment outside the batch allowlist, before any work."""
    allowed = BATCH_ALLOWLIST.get(exp.slug)
    if allowed is None:
        raise HarnessError(
            f"--backend batch does not support experiment {exp.slug!r}: {BATCH_REFUSAL_HINT}"
        )
    deck = exp.raw.get("deck") or {}
    if exp.raw.get("ramp_monotonicity"):
        raise HarnessError(
            f"--backend batch does not support {exp.slug!r}: waveform post-processing "
            f"(ramp_monotonicity) is local-only: {BATCH_REFUSAL_HINT}"
        )
    if allowed.get("window_grid"):
        check_window_grid_batch_shape(exp)
        return
    if allowed.get("cold_start_crossing"):
        check_cold_start_batch_shape(exp)
        return
    if allowed.get("endpoint_adapter"):
        check_endpoint_batch_shape(exp)
        return
    analyses = list(deck.get("analyses") or ["op"])
    meas = [(m.name, m.expr) for m in exp.measurements]
    if analyses != allowed["analyses"] or meas != allowed["measurements"]:
        raise HarnessError(
            f"--backend batch: {exp.slug!r} no longer has the supported smoke shape "
            f"(analyses {analyses}, measurements {meas}): {BATCH_REFUSAL_HINT}"
        )


def spiceinit_lines() -> list[str]:
    """`sim/spiceinit` as request `ngspice_init` lines: empty lines dropped,
    comments, order and command text retained."""
    return [ln for ln in SPICEINIT_FILE.read_text().splitlines() if ln.strip()]


@dataclass
class BatchGroup:
    key: str
    supply_v: float
    corners: list[Corner]  # the selected points this request covers
    process: list[str]
    temperature_c: list[float]
    leg: str | None = None  # window-grid leg this request runs (issue #326)


def group_batch_requests(
    matrix: list[Corner], quick: bool, legs: list[str] | None = None
) -> list[BatchGroup]:
    """Partition the selected points into `klt sim` requests.

    A supply is a netlist `.param`, not a klt corner axis, so each request has
    ONE fixed supply. The full/overridden Cartesian matrix becomes one request
    per supply (process x temperature grid); `--quick` tuples are explicit
    points and each is its own singleton request, never a Cartesian expansion.
    With window-grid `legs`, every such request is further split into one
    request per leg (supply-major, then declared leg order).
    """
    base = _group_by_supply(matrix, quick)
    if legs is None:
        return base
    return [
        BatchGroup(f"{g.key}-{leg}", g.supply_v, g.corners, g.process, g.temperature_c, leg)
        for g in base
        for leg in legs
    ]


def _group_by_supply(matrix: list[Corner], quick: bool) -> list[BatchGroup]:
    groups: list[BatchGroup] = []
    if quick:
        for i, c in enumerate(matrix, start=1):
            groups.append(BatchGroup(f"q{i}-{c.id}", c.supply_v, [c], [c.process], [c.temp_c]))
        return groups
    for supply in unique_in_order(c.supply_v for c in matrix):
        pts = [c for c in matrix if c.supply_v == supply]
        procs = unique_in_order(c.process for c in pts)
        temps = unique_in_order(c.temp_c for c in pts)
        if len(pts) != len(procs) * len(temps) or len({(c.process, c.temp_c) for c in pts}) != len(pts):
            raise HarnessError(
                f"batch grouping: points at {supply:g} V are not a process x temperature "
                "grid; refusing to widen the request"
            )
        groups.append(BatchGroup(f"v{supply:.2f}", supply, pts, procs, temps))
    return groups


def build_batch_netlist(exp: Experiment, group: BatchGroup, body: list[str]) -> list[str]:
    """Request netlist body: fixed `.param vsup`, deck params/options, saved
    vectors, then the circuit body (the same pieces `build_deck` emits)."""
    deck = exp.raw.get("deck", {})
    head = [f".param vsup={group.supply_v}"]
    for name, value in (deck.get("params") or {}).items():
        head.append(f".param {name}={value}")
    for opt in deck.get("options") or []:
        head.append(f".option {opt}")
    head.append(".save all")
    if is_endpoint_adapter(exp):
        # Each endpoint request carries that point's complete source state
        # (VIN, EN's PWL high level, load) in the netlist (issue #379).
        ep = next(e for e in endpoint_deck(exp) if e.step_name == group.leg)
        body = endpoint_module(exp).endpoint_body(body, ep)
    return head + body


def build_batch_request(
    exp: Experiment, pdk: Pdk, group: BatchGroup, netlist_path: Path, timeout: int
) -> dict:
    if is_endpoint_adapter(exp):
        # One single-step request per supply group x endpoint (issue #379).
        shape = {"analysis_steps": [endpoint_step(exp, group.leg)]}
    elif group.leg is not None:
        # One single-step request per window-grid leg (issue #326).
        shape = {"analysis_steps": [window_grid_step(exp, group.leg)]}
    elif is_cold_start_crossing(exp):
        # One single-step cold-start request per supply group (issue #374).
        shape = {"analysis_steps": [cold_start_step(exp)]}
    else:
        shape = {
            "analysis": {"kind": "op", "args": ""},
            "measurements": [
                {"name": f"meas_{m.name}", "expr": m.expr, "unit": m.unit} for m in exp.measurements
            ],
        }
    return {
        "netlist": str(netlist_path),
        "engine": "ngspice",
        "models": {"pdk": pdk.variant, "lib": str(pdk.lib_file.relative_to(pdk.dir))},
        "corners": {"process": list(group.process), "temperature_c": list(group.temperature_c)},
        **shape,
        "options": {
            "timeout_s": timeout,
            "keep_artifacts": True,
            "ngspice_init": spiceinit_lines(),
        },
        # A klt that classifies the fleet-cap refusal waits on its own (issue #345);
        # run_klt_batch's caller-side retry covers a klt that does not.
        "batch": {"capacity_wait_s": CAPACITY_RETRY_BUDGET_S},
    }


def prepare_batch_requests(
    exp: Experiment, pdk: Pdk, matrix: list[Corner], is_quick: bool, body: list[str],
    run_dir: Path, timeout: int,
) -> list[tuple[BatchGroup, Path, dict]]:
    """Write each request's netlist + request JSON under the scratch run dir."""
    if is_cold_start_crossing(exp):
        # The stimulus travels in the netlist: refuse before any request is
        # written (and so before any submission) if it is not the validated one.
        try:
            batch_dropout.check_netlist(body, BATCH_ALLOWLIST[exp.slug]["stimulus"])
        except batch_dropout.DropoutTranslationError as exc:
            raise HarnessError(
                f"--backend batch: {exp.slug!r} netlist is not the validated cold-start "
                f"shape ({exc}): {BATCH_REFUSAL_HINT}"
            ) from exc
    if is_endpoint_adapter(exp):
        try:
            blr.check_netlist(body, BATCH_ALLOWLIST[exp.slug]["stimulus"])
        except blr.EndpointTranslationError as exc:
            raise HarnessError(
                f"--backend batch: {exp.slug!r} netlist is not the validated {exp.slug} "
                f"endpoint baseline ({exc}): {BATCH_REFUSAL_HINT}"
            ) from exc
    req_dir = run_dir / "klt-requests"
    req_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for group in group_batch_requests(matrix, is_quick, batch_legs(exp)):
        netlist_path = (req_dir / f"{group.key}.spice").resolve()
        netlist_path.write_text("\n".join(build_batch_netlist(exp, group, body)) + "\n")
        request = build_batch_request(exp, pdk, group, netlist_path, timeout)
        request_path = req_dir / f"{group.key}.json"
        request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")
        out.append((group, request_path, request))
    return out


def run_klt_batch(request_path: Path, outdir: Path, pdk_root: Path) -> tuple[dict, dict]:
    """`klt sim --backend batch` via the shared helper, with fleet-cap retry
    (see `_record_common.run_klt_sim`); never replaced by a local run."""
    return run_klt_sim(
        request_path, outdir, "batch", pdk_root,
        klt_exe=klt_binary(), error_cls=HarnessError, retry_capacity=True,
    )


def batch_remote_info(response: dict) -> dict:
    env = response.get("environment") if isinstance(response.get("environment"), dict) else {}
    remote = env.get("remote") if isinstance(env.get("remote"), dict) else {}
    return {
        "reported_backend": remote.get("provider"),
        "job_id": remote.get("job_id"),
        "remote": remote,
        "engine": env.get("engine"),
        "engine_version": env.get("engine_version"),
        "klt_version": (response.get("provenance") or {}).get("klt_version"),
        "pdk_version": ((response.get("provenance") or {}).get("pdk") or {}).get("version"),
        "klt_status": response.get("status"),
    }


def _index_response_corners(
    group: BatchGroup, response: dict
) -> tuple[dict[tuple[str, float], Corner], dict[tuple[str, float], dict]]:
    """Match a response's corners to the request's points: malformed,
    unexpected, duplicate or missing points raise HarnessError."""
    want = {(c.process, c.temp_c): c for c in group.corners}
    seen: dict[tuple[str, float], dict] = {}
    for i, rc in enumerate(response["corners"]):
        if (
            not isinstance(rc, dict)
            or not isinstance(rc.get("process"), str)
            or not _finite_number(rc.get("temperature_c"))
            or not isinstance(rc.get("status"), str)
            or not isinstance(rc.get("measurements"), list)
        ):
            raise HarnessError(f"request {group.key}: malformed corner entry #{i} in response: {rc!r:.300}")
        key = (rc["process"], float(rc["temperature_c"]))
        if key not in want:
            raise HarnessError(f"request {group.key}: unexpected corner {key} in response")
        if key in seen:
            raise HarnessError(f"request {group.key}: duplicate corner {key} in response")
        seen[key] = rc
    missing = [k for k in want if k not in seen]
    if missing:
        raise HarnessError(f"request {group.key}: response is missing corner(s) {missing}")
    return want, seen


def normalize_batch_response(
    exp: Experiment, group: BatchGroup, response: dict, outdir: Path, timeout: int
) -> tuple[list[dict], dict[str, str]]:
    """Validate one response against its request and grade each point locally.

    Structure problems (missing/duplicate/unexpected/malformed points) raise
    HarnessError -- there is no trustworthy result to record. Per-point
    problems (errored/inconclusive corner, absent or non-finite value, absent
    log) become recorded FAIL results. klt's own verdict is never consulted;
    limits, spread and the solver-diagnostic gate are the harness's own.
    Returns (results in request point order, {corner id: engine log text}).
    """
    cold_start = group.leg is None and is_cold_start_crossing(exp)
    if cold_start:
        # An unfinished / incompatible / unidentified remote job is never a
        # result (issue #374): abort, no record, no fallback.
        problem = batch_dropout.remote_completion_problem(response)
        if problem:
            raise HarnessError(f"request {group.key}: {problem}")
    want, seen = _index_response_corners(group, response)
    if cold_start:
        wanted = [(m, batch_dropout.klt_result_name(m.name)) for m in exp.measurements]
    elif group.leg is None:
        wanted = [(m, f"meas_{m.name}") for m in exp.measurements]
    else:
        # klt names a step-scoped result `<step>.<name>`; the step is the leg.
        wanted = [(m, f"{group.leg}.{leg_template_name(m)}") for m in exp.measurements
                  if m.leg == group.leg]
    tag = "" if group.leg is None else f"[leg {group.leg}] "

    results, logs = [], {}
    for key, corner in want.items():
        rc = seen[key]
        reasons: list[str] = []
        status = rc["status"]
        if status not in ("pass", "fail"):
            reasons.append(f"{tag}klt sim corner status {status!r} (not a completed result)")
        if cold_start:
            reasons.extend(batch_dropout.corner_diagnostic_problems(rc))
        by_name: dict[str, list] = {}
        for rm in rc["measurements"]:
            if isinstance(rm, dict) and isinstance(rm.get("name"), str):
                by_name.setdefault(rm["name"], []).append(rm)
        checks = []
        for m, klt_name in wanted:
            entries = by_name.get(klt_name, [])
            value, reason = None, ""
            if len(entries) != 1:
                reason = ("measurement not found in klt sim response" if not entries
                          else "measurement reported more than once in klt sim response")
            elif not _finite_number(entries[0].get("value")):
                reason = f"measurement value is missing or non-finite ({entries[0].get('value')!r})"
            else:
                value = float(entries[0]["value"])
            graded, bound_reason = grade_bounds(m, value)
            passed = graded
            if value is not None:
                reason = bound_reason
            checks.append({
                "name": m.name, "expr": m.expr, "unit": m.unit, "value": value,
                "min": m.min, "max": m.max,
                "min_inclusive": m.min_inclusive, "max_inclusive": m.max_inclusive,
                "pass": passed, "reason": reason,
                **({"leg": m.leg, "cout_f": m.cout_f, "esr_ohm": m.esr_ohm, "direction": m.direction}
                   if m.leg is not None else {}),
            })

        solver_diagnostic, log_text, log_note = None, None, None
        art = rc.get("artifacts")
        log_ref = art.get("log") if isinstance(art, dict) else None
        if isinstance(log_ref, str) and log_ref:
            lp = Path(log_ref)
            if not lp.is_absolute():
                lp = outdir / lp
            try:
                log_text = lp.read_text(errors="replace")
            except OSError as exc:
                log_note = f"{tag}engine log unreadable ({lp}: {exc})"
        else:
            log_note = f"{tag}engine log not retained in klt sim response (artifacts.log absent)"
        if log_text is not None:
            solver_diagnostic = detect_solver_diagnostic(log_text)
            logs[corner.id] = log_text
        else:
            reasons.append(log_note)
        if solver_diagnostic is not None:
            reasons.append(f"{tag}solver diagnostic: {solver_diagnostic}")

        runtime = rc.get("runtime_s")
        ok = (not reasons) and all(c["pass"] for c in checks)
        results.append({
            "corner_id": corner.id,
            "process": corner.process,
            "temperature_c": corner.temp_c,
            "supply_v": corner.supply_v,
            "execution": "batch",
            "ngspice_exit": None,  # not observable for a remote run; never fabricated
            "timed_out": False,
            "killed_by_signal": None,
            "killed_by_signal_name": None,
            "elapsed_s": runtime if _finite_number(runtime) else None,
            "timeout_s": timeout,
            "measurements": checks,
            "solver_diagnostic": solver_diagnostic,
            "pass": ok,
            "log": None,
            "klt_request": group.key,
            "klt_corner_id": rc.get("corner_id"),
            "klt_status": status,
            "batch_reasons": reasons,
        })
    return results, logs


def normalize_endpoint_response(
    exp: Experiment, group: BatchGroup, response: dict, outdir: Path
) -> tuple[list[dict], dict[str, str]]:
    """Validate one line-regulation endpoint response (issue #379) and return,
    per corner, that endpoint's RAW card values plus the reasons it cannot
    PASS. Grading happens in `finalize_endpoint_results` once all four
    endpoints of a corner are in hand (the slopes span two of them).

    Structure problems (and an unfinished/incompatible remote job) raise
    HarnessError; per-corner problems (errored status, klt error diagnostics,
    missing/duplicate/non-finite/unexpected results, absent log, solver
    diagnostic) become reasons.
    """
    problem = batch_dropout.remote_completion_problem(response)
    if problem:
        raise HarnessError(f"request {group.key}: {problem}")
    want, seen = _index_response_corners(group, response)
    ep = next(e for e in endpoint_deck(exp) if e.step_name == group.leg)
    parts, logs = [], {}
    for key, corner in want.items():
        rc = seen[key]
        reasons: list[str] = []
        if rc["status"] not in ("pass", "fail"):
            reasons.append(f"[{ep.step_name}] klt sim corner status {rc['status']!r} (not a completed result)")
        reasons.extend(f"[{ep.step_name}] {r}" for r in batch_dropout.corner_diagnostic_problems(rc))
        values, vreasons = blr.extract_endpoint_values(ep, rc["measurements"])
        reasons.extend(vreasons)
        log_text, solver_diagnostic = None, None
        art = rc.get("artifacts")
        log_ref = art.get("log") if isinstance(art, dict) else None
        if isinstance(log_ref, str) and log_ref:
            lp = Path(log_ref)
            if not lp.is_absolute():
                lp = outdir / lp
            try:
                log_text = lp.read_text(errors="replace")
            except OSError as exc:
                reasons.append(f"[{ep.step_name}] engine log unreadable ({lp}: {exc})")
        else:
            reasons.append(f"[{ep.step_name}] engine log not retained in klt sim response (artifacts.log absent)")
        if log_text is not None:
            solver_diagnostic = detect_solver_diagnostic(log_text)
            logs[corner.id] = log_text
        if solver_diagnostic is not None:
            reasons.append(f"[{ep.step_name}] solver diagnostic: {solver_diagnostic}")
        runtime = rc.get("runtime_s")
        parts.append({
            "corner": corner, "endpoint": ep.step_name, "values": values, "reasons": reasons,
            "solver_diagnostic": solver_diagnostic,
            "elapsed_s": runtime if _finite_number(runtime) else None,
            "klt_request": group.key, "klt_corner_id": rc.get("corner_id"), "klt_status": rc["status"],
        })
    return parts, logs


def finalize_endpoint_results(
    exp: Experiment, matrix: list[Corner], parts: dict[str, list[dict]], timeout: int
) -> list[dict]:
    """Grade each corner locally from its four endpoints' raw card values, with
    the manifest's own expressions and `grade_bounds` (identical to the local
    backend's grading). A corner missing an endpoint part cannot PASS."""
    endpoints = endpoint_deck(exp)
    refs = blr.card_refs(endpoints)
    results = []
    for corner in matrix:
        mine = parts.get(corner.id, [])
        reasons = [r for p in mine for r in p["reasons"]]
        for ep in endpoints:
            if not any(p["endpoint"] == ep.step_name for p in mine):
                reasons.append(f"[{ep.step_name}] no result for this endpoint")
        values: dict[str, float | None] = {}
        for p in mine:
            values.update(p["values"])
        checks = []
        for m in exp.measurements:
            value = blr.evaluate(m.expr, values, refs)
            passed, why = grade_bounds(m, value)
            reason = why if value is not None else "measurement not found in endpoint results"
            checks.append({
                "name": m.name, "expr": m.expr, "unit": m.unit, "value": value,
                "min": m.min, "max": m.max,
                "min_inclusive": m.min_inclusive, "max_inclusive": m.max_inclusive,
                "pass": passed, "reason": reason,
            })
        diags = [p["solver_diagnostic"] for p in mine if p["solver_diagnostic"]]
        elapsed = [p["elapsed_s"] for p in mine]
        results.append({
            "corner_id": corner.id, "process": corner.process, "temperature_c": corner.temp_c,
            "supply_v": corner.supply_v, "execution": "batch",
            "ngspice_exit": None, "timed_out": False, "killed_by_signal": None,
            "killed_by_signal_name": None,
            "elapsed_s": sum(elapsed) if elapsed and all(_finite_number(e) for e in elapsed) else None,
            "timeout_s": timeout, "measurements": checks,
            "solver_diagnostic": "; ".join(diags) if diags else None,
            "pass": (not reasons) and all(c["pass"] for c in checks),
            "log": None,
            "klt_request": [p["klt_request"] for p in mine],
            "klt_corner_id": [p["klt_corner_id"] for p in mine],
            "klt_status": [p["klt_status"] for p in mine],
            "batch_reasons": reasons,
        })
    return results


def merge_leg_parts(exp: Experiment, acc: dict | None, part: dict) -> dict:
    """Fold one window-grid leg's batch result for a corner into that corner's
    single result dict (issue #326). Checks are kept in manifest order; the
    corner passes only if every leg part passed; reasons, requests and klt
    statuses accumulate, and runtime sums only while every part reported one."""
    if acc is None:
        merged = dict(part)
        merged["klt_request"] = [part["klt_request"]]
        merged["klt_corner_id"] = [part["klt_corner_id"]]
        merged["klt_status"] = [part["klt_status"]]
        merged["batch_reasons"] = list(part["batch_reasons"])
        return merged
    order = {m.name: i for i, m in enumerate(exp.measurements)}
    merged = dict(acc)
    merged["measurements"] = sorted(
        acc["measurements"] + part["measurements"], key=lambda c: order.get(c["name"], len(order))
    )
    merged["pass"] = acc["pass"] and part["pass"]
    merged["batch_reasons"] = acc["batch_reasons"] + part["batch_reasons"]
    merged["klt_request"] = acc["klt_request"] + [part["klt_request"]]
    merged["klt_corner_id"] = acc["klt_corner_id"] + [part["klt_corner_id"]]
    merged["klt_status"] = acc["klt_status"] + [part["klt_status"]]
    diags = [d for d in (acc["solver_diagnostic"], part["solver_diagnostic"]) if d]
    merged["solver_diagnostic"] = "; ".join(diags) if diags else None
    a, b = acc["elapsed_s"], part["elapsed_s"]
    merged["elapsed_s"] = a + b if _finite_number(a) and _finite_number(b) else None
    return merged


def run_batch(
    exp: Experiment, pdk: Pdk, pin: dict, prepared: list[tuple[BatchGroup, Path, dict]],
    matrix: list[Corner], run_dir: Path, timeout: int, allow_mismatch: bool,
) -> tuple[list[dict], dict[str, str], dict]:
    """Submit each request in turn and reassemble results in matrix order."""
    by_id: dict[str, dict] = {}
    endpoint_parts: dict[str, list[dict]] = {}
    endpoint_mode = is_endpoint_adapter(exp)
    logs: dict[str, str] = {}
    requests_meta = []
    jobs: list[str] = []
    for group, request_path, request in prepared:
        outdir = run_dir / "klt-out" / group.key
        try:
            response, meta = run_klt_batch(request_path, outdir, pdk.root)
            (outdir / "response.json").write_text(json.dumps(response, indent=2, sort_keys=True) + "\n")
            info = batch_remote_info(response)
            if info["job_id"]:
                jobs.append(str(info["job_id"]))
            _shared_assert_pdk(response, pdk, pin, allow_mismatch, error_cls=HarnessError)
            if endpoint_mode:
                res, lg = normalize_endpoint_response(exp, group, response, outdir)
            else:
                res, lg = normalize_batch_response(exp, group, response, outdir, timeout)
        except HarnessError as exc:
            raise HarnessError(
                f"{exc}\n  request {group.key} failed; no evidence record written, no local "
                f"fallback, no resubmission\n  remote job id(s) from earlier requests: "
                f"{', '.join(jobs) if jobs else 'none'}"
            ) from exc
        for r in res:
            if endpoint_mode:
                endpoint_parts.setdefault(r["corner"].id, []).append(r)
                continue
            cid = r["corner_id"]
            by_id[cid] = r if group.leg is None else merge_leg_parts(exp, by_id.get(cid), r)
        for cid, text in lg.items():
            if endpoint_mode:
                logs[cid] = logs.get(cid, "") + (
                    f"***** {exp.slug} endpoint {group.leg} (klt sim request {group.key}) *****\n{text}\n"
                )
            elif group.leg is None:
                logs[cid] = text
            else:
                logs[cid] = logs.get(cid, "") + (
                    f"***** window leg {group.leg} (klt sim request {group.key}) *****\n{text}\n"
                )
        requests_meta.append({
            "key": group.key,
            **({"endpoint" if endpoint_mode else "leg": group.leg} if group.leg is not None else {}),
            "supply_v": group.supply_v,
            "n_points": len(group.corners),
            "returncode": meta["returncode"],
            "response_file": str((outdir / "response.json")),
            "request_file": str(request_path),
            **info,
            "klt_pdk_names_pin": pin["open_pdks_commit"] in (info["pdk_version"] or ""),
        })
    if endpoint_mode:
        results = finalize_endpoint_results(exp, matrix, endpoint_parts, timeout)
    else:
        results = [by_id[c.id] for c in matrix]
    return results, logs, {"requests": requests_meta}


def batch_tools(base: dict, execution: dict) -> dict:
    """The record's `tools` block for a batch run: ngspice is the executor's,
    as klt reported it, not this machine's."""
    tools = dict(base)
    engines = unique_in_order(
        f"{r['engine'] or 'ngspice'}-{r['engine_version']}" if r["engine_version"] else "unreported"
        for r in execution["requests"]
    )
    tools["ngspice"] = (
        f"{engines[0]} (remote executor, reported by klt sim)"
        if len(engines) == 1 else f"mixed: {', '.join(engines)} (remote executor, reported by klt sim)"
    )
    if tools.get("declared"):
        versions = {"ngspice": engines[0] if len(engines) == 1 else "mixed", "xschem": tools["xschem"]}
        tools["on_baseline"] = not compare_tool_versions(tools["declared"], versions)
    return tools
