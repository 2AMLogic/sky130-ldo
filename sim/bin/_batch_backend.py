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

import batch_current_limit as bcl
import batch_dropout
import batch_iq as biq
import batch_line_regulation as blr
import batch_load_regulation as bld
import batch_startup_ramp as bsr
from batch_window_grid import TranslationError, leg_step, parse_leg_template
from ramp_monotonicity import ramp_check
from _corner_model import (
    Corner,
    Experiment,
    HarnessError,
    Measurement,
    Pdk,
    SPICEINIT_FILE,
    compare_tool_versions,
    detect_solver_diagnostic,
    grade_check,
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
# sim/bin/batch_window_grid.py), the `dropout-vs-load` cold-start crossing
# (issue #374: one single-step `tran ... uic` request per supply, see
# sim/bin/batch_dropout.py) and the `startup` ramp-trace grid (issue #336:
# one scalar-`tran` request per supply x leg with `options.waveforms`, the
# ramp traces returned as waveform artifacts and graded locally, see
# sim/bin/batch_startup_ramp.py) may use it. Every other manifest is refused
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
    # Shape (issue #336): a `window_grid` + `ramp_monotonicity` whose leg
    # block translates to a scalar per-leg `tran` request (one request per
    # supply x leg; leg element values baked into the request netlist, the
    # leg's wrdata trace returned as the corner's waveform artifact via
    # `options.waveforms` and rebuilt/graded locally by
    # sim/bin/ramp_monotonicity.py). The manifest shape the translation
    # relies on is pinned by `check_ramp_trace_shape`, not by digests: the
    # wrdata signal, the leg ids and the checker settings must match the
    # ramp block exactly, or the backend refuses before any submission.
    "startup": {"window_grid": True, "ramp_traces": True},
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
    # Shape (issue #177, reordered by #647): the THREE chained legs of the
    # current-limit bench as ONE three-step `analysis_steps[]` request per
    # supply group (sim/bin/batch_current_limit.py) -- leg 2 FIRST (the
    # seeded dc leg leads the deck, issue #647): `alter rload = 1e12` +
    # `alter rforce = 1m` + the `dc vforce 0 1.75 0.125` sweep + find cards;
    # then leg 1, `alter rload = 36` + `alter rforce = 1e12` (baseline
    # restored) + cold-start `tran 5u 1.0m uic` + window cards; then leg 3,
    # `alter rforce = 1m` (the short is applied through the forcing branch)
    # + cold-start `tran 500n 3.0m uic` whose VFORCE PWL applies and holds
    # the short -- the alters are cumulative, which is why the legs are one
    # request, not three. The manifest's graded expressions are already
    # plot-qualified (`tran1.vout_50ma`, `1000*dc1.ilim_short`, ...) and
    # travel verbatim as klt derived measurements; step names follow content
    # (dc1, tran1, tran2), not position. RENEWAL: pinned like the endpoint
    # adapters, by the record input-fingerprint digests
    # (sim/tests/test_batch_current_limit_177.py).
    "current-limit": {
        "chained_steps": True,
        "manifest_sections": {
            "analyses": "cf6ad58bd847ff0db131daf23d6a2ed644a1ec54723054fd82472c57e2589789",
            "measurements": "356180bb130fc6adbb882cfce66ffa7d021e5fc3854eb9cf4894001275c92eb5",
            "matrix": "639e50d5a920cef70120de11fefa3ffc5bf53f0446c56a853f87c39e95976b21",
        },
        # the stimulus / load elements each request's netlist must declare
        # (leg 1 runs at exactly these baseline values; legs 2/3 alter from
        # here -- leg 2 first, then leg 1 restores, then leg 3 re-alters
        # rforce, issue #647). The IC_SEED `.nodeset` card the seeded dc leg
        # depends on is pinned separately by the adapter
        # (batch_current_limit.NODESET_CARD), verbatim like these lines.
        "stimulus": [
            "VVIN VIN 0 'vsup'",
            "VEN EN 0 dc 'vsup' pwl(0 0 100u 0 101u 'vsup' 10 'vsup')",
            "RLOAD VOUT 0 36 m=1",
            "RFORCE VOUT VF 1e12 m=1",
            "VFORCE VF 0 dc 1.8 pwl(0 1.8 1m 1.8 1.001m 0 10 0)",
        ],
    },
}

BATCH_REFUSAL_HINT = (
    "the batch backend is bounded to the unchanged sim/pdk-smoke shape (one `op` "
    "analysis, scalar measurements), the sim/load-transient COUT/ESR window "
    "grid (one `tran` step per leg) and the validated sim/dropout-vs-load "
    "cold-start crossing (one `tran ... uic` step per supply) and the validated "
    "sim/line-regulation endpoints (four single-step `tran ... uic` requests per "
    "supply) and the validated sim/load-regulation endpoints (two single-step "
    "`tran ... uic` requests per supply) and sim/iq's two cold-start endpoints "
    "(two single-step `tran ... uic` requests per supply) and sim/current-limit's "
    "three chained legs (one three-step `analysis_steps[]` request per supply) "
    "and the sim/startup ramp-trace grid "
    "(one scalar `tran` request per leg with `options.waveforms`, issue #336); "
    "every other "
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


def _check_pinned_batch_shape(
    exp: Experiment, *, inner_shape: str, outer_shape: str, translate, err_types, step_noun: str,
) -> None:
    """The shared pinned-adapter manifest shape gate (issues #374 / #177 /
    #379): the structural translation must succeed AND the execution
    sections must still digest to the pinned values -- an intentional
    manifest change requires renewed validation, never a silent pass-through.
    `inner_shape` / `outer_shape` name the shape in the why-strings / the
    refusal, `translate` + `err_types` run and catch the adapter's deck
    translation, `step_noun` names what the deck fails to translate to."""
    allowed = BATCH_ALLOWLIST[exp.slug]
    why = None
    if exp.raw.get("window_grid") or any(m.leg is not None for m in exp.measurements):
        why = f"a window_grid / per_leg measurement is not part of the {inner_shape} shape"
    elif exp.raw.get("spread_checks"):
        why = f"spread_checks are not part of the validated {inner_shape} shape"
    else:
        try:
            translate(exp)
        except err_types as exc:
            why = f"deck does not translate to {step_noun} ({exc})"
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
            f"--backend batch: {exp.slug!r} no longer has the validated {outer_shape} "
            f"shape ({why}): {BATCH_REFUSAL_HINT}"
        )


def check_cold_start_batch_shape(exp: Experiment) -> None:
    """Refuse a dropout manifest whose shape is not the validated one: the
    structural translation must succeed AND the execution sections must still
    digest to the pinned values (issue #374: an intentional manifest change
    requires renewed validation, never a silent pass-through)."""
    _check_pinned_batch_shape(
        exp,
        inner_shape="cold-start", outer_shape="cold-start crossing",
        translate=cold_start_step, err_types=batch_dropout.DropoutTranslationError,
        step_noun="a cold-start klt step",
    )


def is_endpoint_adapter(exp: Experiment) -> bool:
    """Whether the experiment runs through the issue #379 line-regulation
    endpoint adapter."""
    return bool(BATCH_ALLOWLIST.get(exp.slug, {}).get("endpoint_adapter"))


def is_chained_steps(exp: Experiment) -> bool:
    """Whether the experiment runs through the issue #177 current-limit
    chained-steps adapter."""
    return bool(BATCH_ALLOWLIST.get(exp.slug, {}).get("chained_steps"))


def chained_deck(exp: Experiment) -> list[bcl.Leg]:
    """The three chained legs of the deck, parsed and with every graded
    expression checked against them (raises CurrentLimitTranslationError)."""
    legs = bcl.parse_deck((exp.raw.get("deck") or {}).get("analyses") or [])
    bcl.check_measurements(legs, [(m.name, m.expr, m.unit) for m in exp.measurements])
    return legs


def check_chained_batch_shape(exp: Experiment) -> None:
    """Refuse a current-limit manifest whose shape is not the validated one:
    the structural translation must succeed AND the execution sections must
    still digest to the pinned values (issue #177, same discipline as the
    endpoint adapters)."""
    _check_pinned_batch_shape(
        exp,
        inner_shape="chained-steps", outer_shape="chained-steps",
        translate=chained_deck,
        err_types=(bcl.CurrentLimitTranslationError, blr.EndpointTranslationError),
        step_noun="the three chained klt steps",
    )


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
    _check_pinned_batch_shape(
        exp,
        inner_shape="endpoint", outer_shape=f"{exp.slug} endpoint",
        translate=endpoint_deck, err_types=blr.EndpointTranslationError,
        step_noun="cold-start endpoint steps",
    )


def batch_legs(exp: Experiment) -> list[str] | None:
    """Per-request leg ids a batch run splits into: window-grid legs, or the
    line-regulation endpoint ids; None for any other allowlisted experiment."""
    if is_endpoint_adapter(exp):
        return [e.step_name for e in endpoint_deck(exp)]
    if not BATCH_ALLOWLIST.get(exp.slug, {}).get("window_grid"):
        return None
    return [leg["id"] for leg in window_legs(exp.raw)]


def is_ramp_trace_grid(exp: Experiment) -> bool:
    """A window-grid experiment whose per-leg ramp traces must come back from
    the batch run (issue #336 startup): each leg is a scalar-`tran` request
    with `options.waveforms`, and the ramp condition is graded locally from
    the returned waveform artifact."""
    return bool(
        BATCH_ALLOWLIST.get(exp.slug, {}).get("ramp_traces") and exp.raw.get("ramp_monotonicity")
    )


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
    if exp.raw.get("ramp_monotonicity") and not allowed.get("ramp_traces"):
        raise HarnessError(
            f"--backend batch does not support {exp.slug!r}: waveform post-processing "
            f"(ramp_monotonicity) is local-only: {BATCH_REFUSAL_HINT}"
        )
    if allowed.get("ramp_traces") and not exp.raw.get("ramp_monotonicity"):
        # The ratified startup method grades a ramp condition on every leg;
        # a startup manifest without the block would qualify nothing.
        raise HarnessError(
            f"--backend batch: {exp.slug!r} declares no ramp_monotonicity block; "
            f"the trace-returning shape requires it: {BATCH_REFUSAL_HINT}"
        )
    if allowed.get("window_grid"):
        check_window_grid_batch_shape(exp)
        if allowed.get("ramp_traces"):
            try:
                bsr.check_ramp_trace_shape(exp)
            except bsr.StartupRampError as exc:
                raise HarnessError(
                    f"--backend batch: {exp.slug!r} does not have the supported "
                    f"ramp-trace shape ({exc}): {BATCH_REFUSAL_HINT}"
                ) from exc
        return
    if allowed.get("cold_start_crossing"):
        check_cold_start_batch_shape(exp)
        return
    if allowed.get("endpoint_adapter"):
        check_endpoint_batch_shape(exp)
        return
    if allowed.get("chained_steps"):
        check_chained_batch_shape(exp)
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
    if is_ramp_trace_grid(exp):
        # Each leg request carries its element values in the netlist: an
        # `analysis_steps` request cannot return waveforms, so the leg runs
        # as a scalar tran with the alters baked in (issue #336).
        body = bsr.leg_netlist_body(exp, group.leg, body)
    elif is_endpoint_adapter(exp):
        # Each endpoint request carries that point's complete source state
        # (VIN, EN's PWL high level, load) in the netlist (issue #379).
        ep = next(e for e in endpoint_deck(exp) if e.step_name == group.leg)
        body = endpoint_module(exp).endpoint_body(body, ep)
    return head + body


def build_batch_request(
    exp: Experiment, pdk: Pdk, group: BatchGroup, netlist_path: Path, timeout: int
) -> dict:
    if is_ramp_trace_grid(exp):
        # One scalar-tran request per leg (issue #336): the leg's values live
        # in the request netlist, and the ramp trace comes back as the
        # corner's waveform artifact (`options.waveforms`).
        shape = bsr.scalar_leg_request(exp, group.leg)
    elif is_endpoint_adapter(exp):
        # One single-step request per supply group x endpoint (issue #379).
        shape = {"analysis_steps": [endpoint_step(exp, group.leg)]}
    elif group.leg is not None:
        # One single-step request per window-grid leg (issue #326).
        shape = {"analysis_steps": [window_grid_step(exp, group.leg)]}
    elif is_chained_steps(exp):
        # One three-step chained request per supply group (issue #177): the
        # manifest's graded rows travel as klt derived measurements, named
        # `meas_<name>` so the response lookup and local grading match the
        # other backends' contract.
        shape = {
            "analysis_steps": bcl.chained_steps(chained_deck(exp)),
            "measurements": [
                {"name": f"meas_{m.name}", "expr": m.expr, "unit": m.unit} for m in exp.measurements
            ],
        }
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
    options = {
        "timeout_s": timeout,
        "keep_artifacts": True,
        "ngspice_init": spiceinit_lines(),
    }
    if is_ramp_trace_grid(exp):
        options["waveforms"] = True
    return {
        "netlist": str(netlist_path),
        "engine": "ngspice",
        "models": {"pdk": pdk.variant, "lib": str(pdk.lib_file.relative_to(pdk.dir))},
        "corners": {"process": list(group.process), "temperature_c": list(group.temperature_c)},
        **shape,
        "options": options,
        # A klt that classifies the fleet-cap refusal waits on its own (issue #345);
        # run_klt_batch's caller-side retry covers a klt that does not.
        "batch": {"capacity_wait_s": CAPACITY_RETRY_BUDGET_S},
    }


def _check_pinned_netlist(exp: Experiment, body: list[str]) -> None:
    """The shared stimulus-pin netlist gate for every pinned batch adapter:
    `blr.check_netlist` (issue #379), whose `error_cls` / `context` only
    select the exception type and the message's noun, plus -- for the
    current-limit chained steps -- the IC_SEED `.nodeset` card pinned verbatim
    (issue #647, `pinned_extra`)."""
    allowed = BATCH_ALLOWLIST[exp.slug]
    if is_cold_start_crossing(exp):
        try:
            blr.check_netlist(body, allowed["stimulus"],
                              batch_dropout.DropoutTranslationError, "a cold-start crossing request")
        except batch_dropout.DropoutTranslationError as exc:
            raise HarnessError(
                f"--backend batch: {exp.slug!r} netlist is not the validated cold-start "
                f"shape ({exc}): {BATCH_REFUSAL_HINT}"
            ) from exc
    if is_endpoint_adapter(exp):
        try:
            blr.check_netlist(body, allowed["stimulus"])
        except blr.EndpointTranslationError as exc:
            raise HarnessError(
                f"--backend batch: {exp.slug!r} netlist is not the validated {exp.slug} "
                f"endpoint baseline ({exc}): {BATCH_REFUSAL_HINT}"
            ) from exc
    if is_chained_steps(exp):
        try:
            blr.check_netlist(body, allowed["stimulus"], bcl.CurrentLimitTranslationError,
                              "a current-limit chained-step request",
                              pinned_extra=(bcl.NODESET_CARD,))
        except bcl.CurrentLimitTranslationError as exc:
            raise HarnessError(
                f"--backend batch: {exp.slug!r} netlist is not the validated chained-steps "
                f"baseline ({exc}): {BATCH_REFUSAL_HINT}"
            ) from exc


def prepare_batch_requests(
    exp: Experiment, pdk: Pdk, matrix: list[Corner], is_quick: bool, body: list[str],
    run_dir: Path, timeout: int,
) -> list[tuple[BatchGroup, Path, dict]]:
    """Write each request's netlist + request JSON under the scratch run dir."""
    # The stimulus travels in the netlist: refuse before any request is
    # written (and so before any submission) if it is not the validated one.
    _check_pinned_netlist(exp, body)
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


def _engine_log_check(rc: dict, outdir: Path, prefix: str) -> tuple[str | None, str | None, list[str]]:
    """Read one remote corner's engine log artifact and check its text for a
    solver diagnostic (a relative artifact path resolves against `outdir`).
    Returns (log text or None, solver diagnostic or None, failure reasons): a
    log missing from the response or unreadable on disk yields no text and one
    `prefix`-bearing reason, while a readable log — an empty one included —
    yields its text and a diagnostic reason only if a marker matched."""
    reasons: list[str] = []
    log_text: str | None = None
    art = rc.get("artifacts")
    log_ref = art.get("log") if isinstance(art, dict) else None
    if isinstance(log_ref, str) and log_ref:
        lp = Path(log_ref)
        if not lp.is_absolute():
            lp = outdir / lp
        try:
            log_text = lp.read_text(errors="replace")
        except OSError as exc:
            reasons.append(f"{prefix}engine log unreadable ({lp}: {exc})")
    else:
        reasons.append(f"{prefix}engine log not retained in klt sim response (artifacts.log absent)")
    solver_diagnostic = None
    if log_text is not None:
        solver_diagnostic = detect_solver_diagnostic(log_text)
        if solver_diagnostic is not None:
            reasons.append(f"{prefix}solver diagnostic: {solver_diagnostic}")
    return log_text, solver_diagnostic, reasons


def _batch_corner_result(
    corner: Corner,
    *,
    elapsed_s: float | None,
    timeout_s: int,
    measurements: list[dict],
    solver_diagnostic: str | None,
    klt_request,
    klt_corner_id,
    klt_status,
    batch_reasons: list[str],
    ramp_monotonicity: list[dict] | None = None,
) -> dict:
    """The 19-key corner result every batch normalizer emits (issue #736):
    one schema for the standard, startup ramp-trace and endpoint adapters, so
    a new key or adapter cannot drift from the others. `elapsed_s` is the
    already-normalized runtime (None when unobservable); the three `klt_*`
    fields are the per-corner values (or, for the endpoint adapter, the
    per-endpoint lists). `ramp_monotonicity` is included only when non-empty.
    A remote run's ngspice exit is not observable and never fabricated."""
    return {
        "corner_id": corner.id,
        "process": corner.process,
        "temperature_c": corner.temp_c,
        "supply_v": corner.supply_v,
        "execution": "batch",
        "ngspice_exit": None,
        "timed_out": False,
        "killed_by_signal": None,
        "killed_by_signal_name": None,
        "elapsed_s": elapsed_s,
        "timeout_s": timeout_s,
        "measurements": measurements,
        **({"ramp_monotonicity": ramp_monotonicity} if ramp_monotonicity else {}),
        "solver_diagnostic": solver_diagnostic,
        "pass": (not batch_reasons) and all(c["pass"] for c in measurements),
        "log": None,
        "klt_request": klt_request,
        "klt_corner_id": klt_corner_id,
        "klt_status": klt_status,
        "batch_reasons": batch_reasons,
    }


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
            checks.append(grade_check(m, value, missing_reason=reason))

        log_text, solver_diagnostic, log_reasons = _engine_log_check(rc, outdir, tag)
        if log_text is not None:
            logs[corner.id] = log_text
        reasons.extend(log_reasons)

        runtime = rc.get("runtime_s")
        results.append(_batch_corner_result(
            corner,
            elapsed_s=runtime if _finite_number(runtime) else None,
            timeout_s=timeout,
            measurements=checks,
            solver_diagnostic=solver_diagnostic,
            klt_request=group.key,
            klt_corner_id=rc.get("corner_id"),
            klt_status=status,
            batch_reasons=reasons,
        ))
    return results, logs


def normalize_startup_response(
    exp: Experiment, group: BatchGroup, response: dict, outdir: Path, timeout: int
) -> tuple[list[dict], dict[str, str]]:
    """Validate one startup ramp-trace leg response and grade each point
    locally (issue #336).

    Structure problems raise HarnessError (an unfinished/incompatible remote
    job is never a result; there is no trustworthy record to write). Per-point
    problems (errored corner, absent log, solver diagnostic, missing/non-finite
    `.meas` card) become recorded FAIL reasons. The manifest's per-leg
    measurements are evaluated over the leg's raw card values with the
    manifest's own expressions, and the ramp-monotonicity condition is graded
    from the returned waveform artifact (a missing/unusable trace is an
    INVALID condition with its reasons — it can only lower the verdict).
    Returns (results in request point order, {corner id: engine log text}).
    """
    problem = batch_dropout.remote_completion_problem(response)
    if problem:
        raise HarnessError(f"request {group.key}: {problem}")
    want, seen = _index_response_corners(group, response)
    template_cards = [name for name, _ in bsr._leg_template(exp).meas_cards]
    tag = f"[leg {group.leg}] "
    results, logs = [], {}
    for key, corner in want.items():
        rc = seen[key]
        reasons: list[str] = []
        status = rc["status"]
        if status not in ("pass", "fail"):
            reasons.append(f"{tag}klt sim corner status {status!r} (not a completed result)")
        reasons.extend(f"{tag}{r}" for r in batch_dropout.corner_diagnostic_problems(rc))
        by_name: dict[str, dict] = {}
        for rm_ in rc["measurements"]:
            if isinstance(rm_, dict) and isinstance(rm_.get("name"), str):
                name = rm_["name"]
                if name in by_name:
                    reasons.append(f"{tag}measurement {name!r} reported more than once")
                by_name[name] = rm_
        card_values: dict[str, float | None] = {}
        for name in template_cards:
            entry = by_name.get(name)
            if entry is None:
                reasons.append(f"{tag}measurement {name!r} not found in klt sim response")
                card_values[name] = None
            elif not _finite_number(entry.get("value")):
                reasons.append(
                    f"{tag}measurement {name!r} value is missing or non-finite "
                    f"({entry.get('value')!r}, klt status {entry.get('status')!r})"
                )
                card_values[name] = None
            else:
                card_values[name] = float(entry["value"])

        checks = []
        for m in exp.measurements:
            if m.leg != group.leg:
                continue
            value = bsr.evaluate_measurement(m.expr, card_values)
            checks.append(grade_check(
                m, value,
                missing_reason=f"measurement not computable: {m.expr} over missing card value(s)",
            ))

        log_text, solver_diagnostic, log_reasons = _engine_log_check(rc, outdir, tag)
        if log_text is not None:
            logs[corner.id] = log_text
        reasons.extend(log_reasons)

        leg_result, trace_path, structural = bsr.leg_ramp_condition(
            exp, group.leg, corner.id, rc.get("artifacts"), outdir
        )
        reasons.extend(structural)
        checks.append(ramp_check(leg_result))
        if trace_path is not None:
            leg_result["_trace_path"] = str(trace_path)

        runtime = rc.get("runtime_s")
        results.append(_batch_corner_result(
            corner,
            elapsed_s=runtime if _finite_number(runtime) else None,
            timeout_s=timeout,
            measurements=checks,
            solver_diagnostic=solver_diagnostic,
            klt_request=group.key,
            klt_corner_id=rc.get("corner_id"),
            klt_status=status,
            batch_reasons=reasons,
            ramp_monotonicity=[leg_result],
        ))
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
        log_text, solver_diagnostic, log_reasons = _engine_log_check(
            rc, outdir, f"[{ep.step_name}] ")
        if log_text is not None:
            logs[corner.id] = log_text
        reasons.extend(log_reasons)
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
            checks.append(grade_check(m, value, missing_reason="measurement not found in endpoint results"))
        diags = [p["solver_diagnostic"] for p in mine if p["solver_diagnostic"]]
        elapsed = [p["elapsed_s"] for p in mine]
        results.append(_batch_corner_result(
            corner,
            elapsed_s=sum(elapsed) if elapsed and all(_finite_number(e) for e in elapsed) else None,
            timeout_s=timeout,
            measurements=checks,
            solver_diagnostic="; ".join(diags) if diags else None,
            klt_request=[p["klt_request"] for p in mine],
            klt_corner_id=[p["klt_corner_id"] for p in mine],
            klt_status=[p["klt_status"] for p in mine],
            batch_reasons=reasons,
        ))
    return results


def normalize_chained_response(
    exp: Experiment, group: BatchGroup, response: dict, outdir: Path, timeout: int
) -> tuple[list[dict], dict[str, str]]:
    """One chained-steps (issue #177) response: `normalize_batch_response`'s
    per-corner grading -- the request's own `meas_<name>` derived results --
    with the endpoint adapters' strictness: an unfinished / incompatible /
    unidentified remote job is never a result (the same completion gate at
    entry the other batch normalizers apply, issue #374), a klt-side error
    diagnostic or a failed step is a reason the corner cannot PASS, and the
    response's result
    set is checked by NAME and COUNT against the request -- every step card
    and every derived row must be present exactly once (the local deck grades
    all twelve cards; a batch response that lost one would otherwise pass
    silently whenever no derived row happened to read it), and a result the
    request never asked for is refused rather than ignored."""
    problem = batch_dropout.remote_completion_problem(response)
    if problem:
        raise HarnessError(f"request {group.key}: {problem}")
    results, logs = normalize_batch_response(exp, group, response, outdir, timeout)
    legs = chained_deck(exp)
    expected = [f"{leg.step_name}.{name}" for leg in legs for name, _ in leg.cards]
    expected += [f"meas_{m.name}" for m in exp.measurements]
    by_corner = {c.get("corner_id"): c for c in response["corners"] if isinstance(c, dict)}
    for r in results:
        rc = by_corner.get(r["klt_corner_id"], {})
        reasons = batch_dropout.corner_diagnostic_problems(rc)
        names: dict[str, int] = {}
        for rm in rc.get("measurements") or []:
            if not isinstance(rm, dict) or not isinstance(rm.get("name"), str):
                continue
            key = rm["name"].lower()
            names[key] = names.get(key, 0) + 1
            if key not in {e.lower() for e in expected}:
                reasons.append(f"result {rm['name']!r} is not one the request asked for")
            elif rm.get("status") == "error":
                reasons.append(f"result {rm['name']!r} is errored in klt sim response")
            elif not _finite_number(rm.get("value")):
                reasons.append(f"result {rm['name']!r} value is missing or non-finite ({rm.get('value')!r})")
        for want in expected:
            got = names.get(want.lower(), 0)
            if got != 1:
                reasons.append(
                    f"result {want!r} reported {got} time(s) in klt sim response (expected once)")
        r["batch_reasons"].extend(reasons)
        r["pass"] = r["pass"] and not r["batch_reasons"]
    return results, logs


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
    ramp = acc.get("ramp_monotonicity", []) + part.get("ramp_monotonicity", [])
    if ramp:
        merged["ramp_monotonicity"] = ramp
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
    startup_mode = is_ramp_trace_grid(exp)
    logs: dict[str, str] = {}
    traces: dict[str, list[tuple[str, Path]]] = {}
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
            if is_chained_steps(exp):
                # The chained legs are ONE klt request, so one response
                # covers all three steps of a corner and
                # normalize_chained_response -- completion gate at entry like
                # the other batch normalizers, then normalize_batch_response's
                # per-corner grading -- is the right reader for it.
                res, lg = normalize_chained_response(exp, group, response, outdir, timeout)
            elif endpoint_mode:
                res, lg = normalize_endpoint_response(exp, group, response, outdir)
            elif startup_mode:
                res, lg = normalize_startup_response(exp, group, response, outdir, timeout)
            else:
                res, lg = normalize_batch_response(exp, group, response, outdir, timeout)
            for r in res:
                for tr in r.get("ramp_monotonicity") or []:
                    p = tr.pop("_trace_path", None)  # harness-internal; never recorded
                    if p:
                        traces.setdefault(r["corner_id"], []).append((tr["trace_file"], Path(p)))
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
    traces_meta = {
        cid: [{"file": name, "path": str(path)} for name, path in entries]
        for cid, entries in traces.items()
    }
    return results, logs, {"requests": requests_meta, **({"traces": traces_meta} if traces_meta else {})}


def startup_ramp_adapter_info(exp: Experiment) -> dict:
    """Provenance of the issue #336 trace-return adapter for a batch record."""
    return bsr.adapter_info(exp)


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
