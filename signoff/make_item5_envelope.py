#!/usr/bin/env python3
"""Wrap the committed corner-matrix records into `klt sim`-shaped envelopes
for T1 item 5 (issue #449).

T1 item 5 ("Full corner verification vs a ratified spec") accepts exactly one
evidence kind for an analog block: a ``klt sim`` envelope (a ``measurements``
list plus ``corner_count``). The experiment records under
``sim/<bench>/records/*.json`` are this repo's own harness format, which the
grader does not read, so item 5 rendered ``no_evidence`` even though a full
45-point PVT campaign exists. This script **wraps those committed records,
without re-simulating anything**, into the ``klt sim`` response shape. It is
the "wrap" route of the issue, the same route as
``2AMLogic/gf180-comparator``'s ``signoff/make_item5_envelope.py``.

Honesty contract (read before trusting an envelope)
---------------------------------------------------
* An envelope is NOT output of a ``klt sim`` run. Its ``wrapper`` field says
  so. Every value, limit and pass/fail verdict is copied verbatim from the
  cited record (pinned by sha256 in ``source_record``); nothing is re-measured
  and no verdict is recomputed. The only thing this script adds is the
  ``spec_row`` tag on a measurement and the ``margin`` arithmetic.
* The limit carried on each tagged measurement is the **ratified** bound.
  ``RATIFIED`` below states each bound next to the spec row it comes from, and
  the script refuses to write if a record's own limit disagrees with it. So a
  bench that quietly gated on a looser bound cannot be wrapped as if it graded
  the ratified one, and no ratified bound is relaxed here.
* Each envelope is pinned (``provenance.input.content_hash``) to the netlist
  snapshot the record simulated. That is "the netlist this record ran on", not
  a claim that it is the current schematic: ``measurements/characterization.md``
  reports the freshness of each record separately and most read ``STALE``.
* A record that ran fewer corners than its experiment declares (the dropout
  record is a one-corner attribution run) is never reported as ``pass``: its
  envelope is ``pass_partial`` at best, with the missing matrix recorded as
  skipped work in ``coverage``.
* ``Area`` and ``Output noise`` are NOT wrapped. Area is a layout measurement
  (the bounding box of a GDS), not a netlist simulation, so no ``klt sim``
  envelope can express it; Output noise is waived by the spec row itself. Both
  are declared gaps in ``signoff/block-manifest.json``.

Usage (from the repo root):

    python3 signoff/make_item5_envelope.py           # write (append-only)
    python3 signoff/make_item5_envelope.py --check   # exit 1 on drift
    python3 signoff/make_item5_envelope.py --check --offline
    #   headless structural check (the build_characterization_report.py
    #   --offline mode, issue #503): verifies every committed envelope's
    #   citation chain with no store fetch. Records whose JSON twin is
    #   committed still get the full byte-exact rebuild; records held in the
    #   artifact store get their manifest digest chain checked instead --
    #   coverage, not a skip. Only a host with `klt` + store access can
    #   confirm a store-held envelope byte-for-byte.

Output files are named ``signoff/evidence/item5-<bench>-<record id>.sim.json``.
An existing file with different content is never overwritten: a newer record
mints a new file, and the manifest and ``signoff/artifact-pins.json`` are then
re-pointed at it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# The Thermal row is graded by measurements/build_characterization_report.py; the
# hysteresis branch below imports that rule rather than restating it.
sys.path.insert(0, str(REPO_ROOT / "measurements"))
import build_characterization_report as _report  # noqa: E402

# The repo's one content-digest contract (issue #589). Appended, so neither
# tree's `_record_common` can shadow the other's.
sys.path.append(str(REPO_ROOT / "layout" / "bin"))
from _digest import sha256_file_prefixed  # noqa: E402
from _store_manifest import (  # noqa: E402 -- the one store-manifest contract (issue #671)
    StoreFetchError,
    fetch_entry_bytes,
    manifest_entries,
)

OUT_DIR = REPO_ROOT / "signoff" / "evidence"

#: (bench, record id) -- the record `measurements/characterization.md` cites
#: for each row. tests/test_item5_envelopes.py checks this list against that
#: file, so an envelope cannot drift from the rollup it must agree with.
RECORDS = [
    ("dropout-vs-load", "20261011-092557-7a4e0cc"),
    ("line-regulation", "20260926-200304-35b7392"),
    ("load-regulation", "20260926-010432-228fbc7"),
    ("load-transient", "20260926-013955-6449a98"),
    ("psrr-dc", "20261029-092008-5ba605f"),
    ("iq", "20261110-223334-f66373a0"),
    ("current-limit", "20260825-105322-933dfdd"),
    ("startup", "20261117-221657-efb6bd6b"),
    ("enable-shutdown", "20260825-111526-933dfdd"),
    ("thermal", "20261105-202028-97cd9a9e-qual-15corner"),
    ("loop-gain", "20261029-092024-5ba605f"),
]

#: bench -> {measurement: (spec row id, ratified {"min"/"max"} bound)}.
#: Row ids are the ones declared under ``spec_rows."5"`` in the manifest.
#: Bounds are read from the ratified row of spec/target-spec.md (cited per
#: line); a measurement not listed is carried as an untagged observation with
#: the record's own limits.
_BAND = {"min": 1.764, "max": 1.836}  # Output / startup: 1.8 V +-2 %
RATIFIED: dict[str, dict[str, tuple[str, dict[str, float]]]] = {
    # Dropout @ 50 mA: < 300 mV
    "dropout-vs-load": {"dropout_v": ("dropout", {"max": 0.3})},
    # Line regulation: < 5 mV/V at 1 mA and 50 mA
    "line-regulation": {
        "line_reg_1ma_mv_per_v": ("line-regulation", {"max": 5}),
        "line_reg_50ma_mv_per_v": ("line-regulation", {"max": 5}),
    },
    # Load regulation: < 1 % (18 mV)
    "load-regulation": {
        "load_reg_v": ("load-regulation", {"max": 0.018}),
        "load_reg_pct": ("load-regulation", {"max": 1}),
    },
    # Load transient: peak excursion <= 150 mV, recover to +-1 % in <= 20 us
    "load-transient": {
        "undershoot_v": ("load-transient", {"max": 0.15}),
        "overshoot_v": ("load-transient", {"max": 0.15}),
        "recovery_rise_us": ("load-transient", {"max": 20}),
        "recovery_fall_us": ("load-transient", {"max": 20}),
    },
    # PSRR: > 50 dB @ 1 kHz and > 20 dB @ 100 kHz, at 1 mA and 50 mA
    "psrr-dc": {
        "psrr_1khz_1ma_db": ("psrr", {"min": 50}),
        "psrr_1khz_50ma_db": ("psrr", {"min": 50}),
        "psrr_100khz_1ma_db": ("psrr", {"min": 20}),
        "psrr_100khz_50ma_db": ("psrr", {"min": 20}),
    },
    # Iq: < 30 uA at no load and at full load (DR-009, proposed)
    "iq": {
        "iq_no_load_ua": ("iq", {"max": 30}),
        "iq_full_load_ua": ("iq", {"max": 30}),
    },
    # Output: 1.8 V +-2 % (graded at 50 mA over the 45-point matrix here);
    # Current limit: never engages for I_load <= 50 mA, survives a Vout = 0 short
    "current-limit": {
        "vout_50ma_v": ("output", _BAND),
        "ilim_short_ma": ("current-limit", {"min": 50}),
        "ilim_knee_ma": ("current-limit", {"min": 50}),
        "ishort_ripple_pct": ("current-limit", {"max": 100}),
    },
    # Startup: inside +-2 % window, overshoot <= +2 % — measured on the
    # per-leg names the #336 twelve-leg grid expanded (the strict-0 V
    # ramp_drawdown_* conditions carry no ratified bound yet: the tolerance
    # question is the open decision record in sim/README.md, so they stay
    # untagged observations with the record's own limits).
    "startup": {
        f"{kind}_v__{leg}": ("startup", {"max": 1.836} if kind == "vpk" else {"min": 1.764})
        for kind in ("vpk", "vfloor")
        for leg in (
            "c330n_0ma_esr0", "c330n_0ma_esr10m", "c330n_0ma_esr500m",
            "c330n_50ma_esr0", "c330n_50ma_esr10m", "c330n_50ma_esr500m",
            "c4u7_0ma_esr0", "c4u7_0ma_esr10m", "c4u7_0ma_esr500m",
            "c4u7_50ma_esr0", "c4u7_50ma_esr10m", "c4u7_50ma_esr500m",
        )
    },
    # Enable / shutdown: shutdown Iq < 3 uA, Vin->Vout leakage <= 1 uA
    "enable-shutdown": {
        "iq_shutdown_static_ua": ("enable-shutdown", {"max": 3.0}),
        "iq_shutdown_after_edge_ua": ("enable-shutdown", {"max": 3.0}),
        "leak_vin_vout_ua": ("enable-shutdown", {"max": 1.0}),
    },
    # Thermal: specified to Tj <= 125 C; DR-005 backstop trips above it and
    # auto-restarts with positive hysteresis
    "thermal": {
        "trip_temp_c": ("thermal", {"min": 125}),
        "hysteresis_c": ("thermal", {"min": 0}),
    },
    # Stability: PM >= 45 deg, GM >= 10 dB, worst corner
    "loop-gain": {
        "pm_c033_50ma_deg": ("stability", {"min": 45}),
        "pm_c033_1ma_deg": ("stability", {"min": 45}),
        "pm_c033_0ma_deg": ("stability", {"min": 45}),
        "pm_c47_50ma_deg": ("stability", {"min": 45}),
        "pm_c47_1ma_deg": ("stability", {"min": 45}),
        "pm_c47_0ma_deg": ("stability", {"min": 45}),
        "pm_c033_esr500m_50ma_deg": ("stability", {"min": 45}),
        "gm_c033_50ma_db": ("stability", {"min": 10}),
        "gm_c033_0ma_db": ("stability", {"min": 10}),
    },
}

WRAPPER = (
    "NOT a `klt sim` run. Hand-wrapped by signoff/make_item5_envelope.py from "
    "the committed harness-format record named in `source_record`; every "
    "value, limit and verdict is copied verbatim and nothing was re-simulated. "
    "Measurements tagged with a `spec_row` carry that row's RATIFIED bound "
    "(spec/target-spec.md, DR-006), which the script checked against the "
    "record's own limit before writing. The input pin is the netlist snapshot "
    "the record simulated, not necessarily the current schematic: see "
    "measurements/characterization.md for per-record freshness."
)

HYSTERESIS_WRAPPER = (
    " For a hysteresis record (sim/thermal/hysteresis/<id>/result.json) the "
    "record holds bisection brackets, not per-corner verdicts: the envelope "
    "carries each corner's conservative edges (trip bracket lower edge, "
    "hysteresis min) and grades them with the same rule as "
    "measurements/build_characterization_report.py. `temperature_c` is null "
    "because temperature is the swept variable, not a corner axis; the input "
    "pin is the record's own netlist.spice."
)


class WrapError(Exception):
    """A record does not say what the ratified row requires; nothing is written."""


def _limits(m: dict) -> dict | None:
    lim = {k: m[k] for k in ("min", "max") if m.get(k) is not None}
    return lim or None


def _margin(value: float, lim: dict | None) -> float | None:
    if not lim or value is None:
        # No bound, or the record carried a null value (a missing or
        # inconclusive measurement, e.g. an expr the runner could not
        # evaluate): no margin is computable, faithfully.
        return None
    margins = []
    # A null bound (batch records emit `"min": null` for max-only limits)
    # is no bound.
    if lim.get("max") is not None:
        margins.append(lim["max"] - value)
    if lim.get("min") is not None:
        margins.append(value - lim["min"])
    return min(margins) if margins else None


def _load(bench: str, rid: str) -> tuple[dict, Path]:
    """The record's JSON twin: on disk when the run wrote it there; fetched
    via `klt artifact get` (sha256-verified against the committed store
    manifest) when the evidence went to the artifact broker instead -- the
    batch backend's shape, whose committed `records/<rid>.md` links both the
    JSON and the netlist snapshot into the store (fetch delegated to the
    shared _store_manifest helper)."""
    path = REPO_ROOT / "sim" / bench / "records" / f"{rid}.json"
    if path.is_file():
        return json.loads(path.read_text()), path
    ref = _report._store_manifest_entry(bench, rid)
    if ref is None:
        raise WrapError(
            f"{bench} {rid}: no records/{rid}.json on disk and no store manifest entry"
        )
    try:
        return json.loads(fetch_entry_bytes(*ref)), path
    except StoreFetchError as exc:
        raise WrapError(f"{bench} {rid}: {exc}") from exc


_HEX64_RE = re.compile(r"[0-9a-f]{64}")


def _offline_store_record_problems(bench: str, rid: str) -> list[str]:
    """Structural verification of a store-held record's committed envelope
    with no store fetch (headless CI mode; the offline_check() pattern of
    build_characterization_report.py, issue #503).

    Rebuilding the envelope needs the record's JSON twin, which lives in the
    artifact broker behind the committed store manifest -- only hosts with
    `klt` + store access can read it. Offline, verify the citation chain
    instead: the manifest entry for the record JSON is present with a
    well-formed sha256 and the committed envelope pins exactly that digest;
    the netlist-snapshot pin agrees with the materialised file when it is
    committed, else with the manifest's own digest for it. Returns one
    message per problem (empty = consistent).
    """
    ref = _report._store_manifest_entry(bench, rid)
    where = f"sim/{bench}/records/{rid}.json"
    if ref is None:
        return [f"{where}: not committed and no store manifest entry -- cannot verify offline"]
    manifest, name = ref
    rec_entry = next((e for e in manifest_entries(manifest) if e.get("name") == name), None)
    if rec_entry is None:
        return [f"{manifest.name}: unreadable or has no entry {name} -- cannot verify {where} offline"]
    digest = rec_entry.get("sha256")
    if not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest):
        return [f"{manifest.name}: entry {name} has no well-formed sha256 digest"]

    out = output_path(bench, rid)
    rel = out.relative_to(REPO_ROOT).as_posix()
    env = json.loads(out.read_text())
    errors: list[str] = []
    claimed = env.get("source_record", {}).get("sha256")
    if claimed != f"sha256:{digest}":
        errors.append(
            f"{rel}: source_record.sha256 pins {claimed} but {manifest.name} "
            f"digests {name} as sha256:{digest}"
        )
    pin = env.get("provenance", {}).get("input", {})
    snap_rel, claimed_snap = pin.get("path"), pin.get("content_hash")
    snap_file = REPO_ROOT / snap_rel
    snap_entry = next((e for e in entries if isinstance(e, dict) and e.get("name") == snap_rel), None)
    if snap_file.is_file():
        actual = sha256_file_prefixed(snap_file)
        if claimed_snap != actual:
            errors.append(f"{snap_rel}: hashes to {actual} but {rel} pins {claimed_snap}")
        snap_digest = (snap_entry or {}).get("sha256")
        if isinstance(snap_digest, str) and _HEX64_RE.fullmatch(snap_digest) \
                and f"sha256:{snap_digest}" != claimed_snap:
            errors.append(
                f"{manifest.name}: entry {snap_rel} digests sha256:{snap_digest} "
                f"but {rel} pins {claimed_snap}"
            )
    elif snap_entry is None:
        errors.append(
            f"{snap_rel}: neither committed nor listed in {manifest.name} -- "
            f"{rel}'s input pin is unverifiable offline"
        )
    else:
        snap_digest = snap_entry.get("sha256")
        if not isinstance(snap_digest, str) or not _HEX64_RE.fullmatch(snap_digest):
            errors.append(f"{manifest.name}: entry {snap_rel} has no well-formed sha256 digest")
        elif f"sha256:{snap_digest}" != claimed_snap:
            errors.append(
                f"{manifest.name}: entry {snap_rel} digests sha256:{snap_digest} "
                f"but {rel} pins {claimed_snap}"
            )
    return errors


def offline_check() -> list[str]:
    """Offline structural check of the committed item-5 envelopes (headless
    CI mode; mirrors build_characterization_report.offline_check, issue #503).

    Never fetches from the artifact store. For every record it verifies what
    is verifiable without one: a record whose JSON twin is committed on disk
    gets the FULL currency check (envelope_text vs the committed file -- no
    store-backed step is involved for those); a store-held record gets its
    citation chain verified instead. It cannot re-derive a store-held
    envelope's measurements from bytes it cannot read, so it cannot say
    whether that envelope still equals a fresh wrap -- that stays the
    store-backed `--check`'s job. Returns one message per problem (empty =
    consistent).
    """
    errors: list[str] = []
    for bench, rid in RECORDS:
        out = output_path(bench, rid)
        rel = out.relative_to(REPO_ROOT).as_posix()
        if not out.is_file():
            errors.append(f"{rel}: missing -- run python3 signoff/make_item5_envelope.py")
            continue
        if _is_hysteresis(bench, rid) or (REPO_ROOT / "sim" / bench / "records" / f"{rid}.json").is_file():
            try:
                text = envelope_text(bench, rid)
            except WrapError as e:
                errors.append(f"{rel}: {e}")
                continue
            if out.read_text() != text:
                errors.append(
                    f"{rel}: committed text is not what make_item5_envelope.py would write"
                )
            continue
        errors.extend(_offline_store_record_problems(bench, rid))
    return errors


def _hysteresis_dir(bench: str, rid: str) -> Path:
    return REPO_ROOT / "sim" / bench / "hysteresis" / rid


def _is_hysteresis(bench: str, rid: str) -> bool:
    return (_hysteresis_dir(bench, rid) / "result.json").is_file()


def _envelope(
    *,
    bench: str,
    rid: str,
    rec: dict,
    rec_path: Path,
    snap: Path,
    status: str,
    corners: list[dict],
    rollup: list[dict],
    checked: list[str],
    skipped: list[dict],
    n_pass: int,
    n_fail: int,
    wrapper: str,
    overall_pass: bool,
    matrix_is_subset: bool,
    remote: dict | None,
    measurements_declared: int,
    measurements_with_limits: int,
    rec_sha256: str | None = None,
    snap_sha256: str | None = None,
) -> dict:
    """The one item-5 envelope literal, shared by both wrap paths.

    Key insertion order is the on-disk byte order (`envelope_text()` dumps
    with ``json.dumps(..., indent=2)``), so keys must stay in this order and
    `remote` is appended as the last `environment` key only when the caller
    passes one — exactly the split between the two wrap paths.
    """
    env: dict = {
        "schema_version": 1,
        "netlist": snap.relative_to(REPO_ROOT).as_posix(),
        "status": status,
        "corner_count": len(corners),
        "passed": n_pass,
        "failed": n_fail,
        "errored": 0,
        "wrapper": wrapper,
        "source_record": {
            "bench": bench,
            "record_id": rid,
            "path": rec_path.relative_to(REPO_ROOT).as_posix(),
            "sha256": rec_sha256 or sha256_file_prefixed(rec_path),
            "overall_pass": overall_pass,
            "matrix_is_subset": matrix_is_subset,
        },
        "environment": {
            "engine": "ngspice",
            "engine_version": rec["tools"].get("ngspice"),
            "pdk": rec["pdk"].get("pinned_commit"),
            "platform": rec["tools"].get("platform"),
        },
        "provenance": {
            "input": {
                "path": snap.relative_to(REPO_ROOT).as_posix(),
                "role": "netlist",
                "content_hash": snap_sha256 or sha256_file_prefixed(snap),
            },
        },
        "metrics": {
            "sim__corner__count": len(corners),
            "sim__corner__passed_count": n_pass,
            "sim__corner__failed_count": n_fail,
            "sim__corner__errored_count": 0,
        },
        "coverage": {
            "schema_version": 1,
            "known": True,
            "checked": sorted(checked),
            "skipped": skipped,
            "inapplicable": [],
            "unknown": [],
            "nothing_checked": False,
            "nothing_checked_reasons": [],
            "measurements_declared": measurements_declared,
            "measurements_with_limits": measurements_with_limits,
        },
        "measurements": rollup,
        "corners": corners,
    }
    if remote is not None:
        env["environment"]["remote"] = remote
    return env


def build_hysteresis_envelope(bench: str, rid: str) -> dict:
    """Wrap a directory-style hysteresis record (`result.json` with per-corner
    bracket edges) into the envelope shape.

    Each corner contributes two measurements on the conservative edges the
    characterization rollup grades (`thermal_corner_edges`): the trip bracket's
    lower edge as ``trip_temp_c`` and ``hysteresis_c.min`` as ``hysteresis_c``.
    Pass/fail uses ``thermal_corner_fails`` from the same module, so the two
    cannot disagree. Bounds come from ``sim/<bench>/experiment.json`` and must
    equal the ratified ``RATIFIED[bench]`` bounds.
    """
    rec_dir = _hysteresis_dir(bench, rid)
    rec_path = rec_dir / "result.json"
    rec = json.loads(rec_path.read_text())
    tags = RATIFIED[bench]
    exp = {m["name"]: m for m in json.loads((REPO_ROOT / "sim" / bench / "experiment.json").read_text())["measurements"]}
    for name, (row, bound) in tags.items():
        if _limits(exp[name]) != bound:
            raise WrapError(
                f"{bench} {rid}: experiment.json carries limits {_limits(exp[name])} for {name} "
                f"but the ratified '{row}' row requires {bound}"
            )
    trip_min = tags["trip_temp_c"][1]["min"]
    hyst_min = tags["hysteresis_c"][1]["min"]
    snap = rec_dir / "netlist.spice"

    corners, checked = [], []
    for cid, c in rec["corners"].items():
        process, supply = cid.split("_")
        supply_v = float(supply.rstrip("V"))
        trip_lo, h_min = _report.thermal_corner_edges(c)
        ms = []
        for name, value in (("trip_temp_c", trip_lo), ("hysteresis_c", h_min)):
            lim = tags[name][1]
            ms.append({
                "name": name, "value": value, "unit": "C", "limits": lim,
                "status": "pass" if _margin(value, lim) >= 0 else "fail",
                "margin": _margin(value, lim),
            })
            checked.append(f"{bench}:{cid}:{name}")
        corners.append({
            "corner_id": cid, "process": process, "supply_v": {"vvin": supply_v},
            "temperature_c": None,
            "status": "fail" if _report.thermal_corner_fails(c, trip_min, hyst_min) else "pass",
            "measurements": ms, "diagnostics": [],
        })
    rollup = []
    for name in tags:
        pts = [(c["corner_id"], m) for c in corners for m in c["measurements"] if m["name"] == name]
        wc_id, wc = min(pts, key=lambda p: p[1]["margin"])
        rollup.append({
            "name": name, "unit": "C", "limits": wc["limits"],
            "status": "fail" if any(m["status"] == "fail" for _, m in pts) else "pass",
            "worst_case": {"corner_id": wc_id, "value": wc["value"], "margin": wc["margin"]},
            "spec_row": tags[name][0],
        })
    n_fail = sum(1 for c in corners if c["status"] == "fail")
    n_pass = len(corners) - n_fail
    complete = rec.get("complete") is True
    skipped = [] if complete else [{"id": f"{bench}:hysteresis", "reason": "record is not complete"}]
    status = "fail" if n_fail else ("pass" if complete else "pass_partial")
    return _envelope(
        bench=bench, rid=rid, rec=rec, rec_path=rec_path, snap=snap,
        status=status, corners=corners, rollup=rollup, checked=checked,
        skipped=skipped, n_pass=n_pass, n_fail=n_fail,
        wrapper=WRAPPER + HYSTERESIS_WRAPPER,
        overall_pass=status == "pass",
        matrix_is_subset=False,
        remote={"backend": rec.get("backend"), "jobs": len(rec.get("jobs") or [])},
        measurements_declared=len(rollup),
        measurements_with_limits=len(rollup),
    )


def build_envelope(bench: str, rid: str) -> dict:
    if _is_hysteresis(bench, rid):
        return build_hysteresis_envelope(bench, rid)
    rec, rec_path = _load(bench, rid)
    tags = RATIFIED[bench]
    snap = REPO_ROOT / rec["links"]["netlist_snapshot"]
    rec_sha = snap_sha = None
    if not rec_path.is_file():
        # Store-held record (batch backend): the JSON twin and possibly the
        # netlist snapshot live in the artifact broker behind the committed
        # store manifest. Fetch the bytes (klt verifies sha256 against the
        # manifest) so the envelope pins what the record actually is and ran
        # on; a snapshot already materialised at its netlist-snapshots path
        # is hashed from disk. Path labels stay the record's own links.
        import hashlib

        ref = _report._store_manifest_entry(bench, rid)
        if ref is None:
            raise WrapError(
                f"{bench} {rid}: records/{rid}.json is not on disk and no "
                "store manifest entry carries it"
            )
        manifest, _ = ref
        try:
            rec_sha = "sha256:" + hashlib.sha256(
                fetch_entry_bytes(manifest, f"sim/{bench}/records/{rid}.json")
            ).hexdigest()
            if snap.is_file():
                snap_sha = "sha256:" + hashlib.sha256(snap.read_bytes()).hexdigest()
            else:
                snap_sha = "sha256:" + hashlib.sha256(
                    fetch_entry_bytes(manifest, rec["links"]["netlist_snapshot"])
                ).hexdigest()
        except StoreFetchError as e:
            raise WrapError(f"{bench} {rid}: {e}") from e
    matrix = rec.get("matrix") or {}
    subset = bool(matrix.get("is_subset"))

    corners, checked, seen = [], [], set()
    for c in rec["corners"]:
        ms = []
        for m in c["measurements"]:
            name = m["name"]
            seen.add(name)
            lim = _limits(m)
            if name in tags:
                row, bound = tags[name]
                # Every field the ratified row declares must match exactly;
                # extra record-side guards (e.g. iq's `min: 0` nonnegativity
                # guard, issue #336 rollup regeneration) are kept verbatim.
                mismatched = {k: (lim.get(k), bound[k]) for k in bound if lim.get(k) != bound[k]}
                if mismatched:
                    raise WrapError(
                        f"{bench} {rid}: {name} carries limits {lim} but the "
                        f"ratified '{row}' row requires {bound} "
                        f"(differing fields: {mismatched})"
                    )
            entry = {
                "name": name,
                "value": m["value"],
                "unit": m.get("unit"),
                "limits": lim,
                "status": "pass" if m["pass"] else "fail",
                "margin": _margin(m["value"], lim),
            }
            ms.append(entry)
            if lim:
                checked.append(f"{bench}:{c['corner_id']}:{name}")
        diag = []
        if c.get("solver_diagnostic"):
            diag.append({"severity": "error", "code": "solver_diagnostic",
                         "message": str(c["solver_diagnostic"])})
        corners.append({
            "corner_id": c["corner_id"],
            "process": c["process"],
            "supply_v": {"vvin": c["supply_v"]},
            "temperature_c": c["temperature_c"],
            "status": "pass" if c["pass"] else "fail",
            "measurements": ms,
            "diagnostics": diag,
        })
    missing = sorted(set(tags) - seen)
    if missing:
        raise WrapError(f"{bench} {rid}: ratified measurement(s) absent from the record: {missing}")

    rollup = []
    for name in dict.fromkeys(m["name"] for c in corners for m in c["measurements"]):
        pts = [(c["corner_id"], m) for c in corners for m in c["measurements"] if m["name"] == name]
        limited = [p for p in pts if p[1]["margin"] is not None]
        wc_id, wc = min(limited, key=lambda p: p[1]["margin"]) if limited else pts[0]
        entry = {
            "name": name,
            "unit": wc["unit"],
            "limits": wc["limits"],
            "status": "fail" if any(m["status"] == "fail" for _, m in pts) else "pass",
            "worst_case": {"corner_id": wc_id, "value": wc["value"], "margin": wc["margin"]},
        }
        if name in tags:
            entry["spec_row"] = tags[name][0]
        rollup.append(entry)

    n_fail = sum(1 for c in corners if c["status"] == "fail")
    n_pass = len(corners) - n_fail
    skipped = []
    if subset:
        skipped.append({
            "id": f"{bench}:corner-matrix",
            "reason": "pvt_subset: " + str(matrix.get("subset_reason") or "record ran fewer corners than its experiment declares"),
        })
    if n_fail:
        status = "fail"
    elif skipped:
        status = "pass_partial"
    else:
        status = "pass"

    declared = len(rollup)
    with_limits = sum(1 for m in rollup if m["limits"])
    return _envelope(
        bench=bench, rid=rid, rec=rec, rec_path=rec_path, snap=snap,
        status=status, corners=corners, rollup=rollup, checked=checked,
        skipped=skipped, n_pass=n_pass, n_fail=n_fail,
        wrapper=WRAPPER,
        overall_pass=rec["overall_pass"],
        matrix_is_subset=subset,
        remote=None,
        measurements_declared=declared,
        measurements_with_limits=with_limits,
        rec_sha256=rec_sha,
        snap_sha256=snap_sha,
    )


def output_path(bench: str, rid: str) -> Path:
    return OUT_DIR / f"item5-{bench}-{rid}.sim.json"


def envelope_text(bench: str, rid: str) -> str:
    return json.dumps(build_envelope(bench, rid), indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    check = "--check" in argv
    offline = "--offline" in argv
    if offline and not check:
        print("FATAL: --offline is only meaningful together with --check", file=sys.stderr)
        return 2
    if offline:
        problems = offline_check()
        if problems:
            for p in problems:
                print(f"FAIL: {p}", file=sys.stderr)
            return 1
        print("OK: committed item-5 envelopes consistent with their citation chains (offline; no store fetch).")
        return 0
    rc = 0
    for bench, rid in RECORDS:
        out = output_path(bench, rid)
        rel = out.relative_to(REPO_ROOT)
        try:
            text = envelope_text(bench, rid)
        except WrapError as e:
            print(f"FATAL: {e}", file=sys.stderr)
            return 1
        if check:
            if not out.is_file():
                print(f"FATAL: {rel} not found -- run python3 signoff/make_item5_envelope.py", file=sys.stderr)
                rc = 1
            elif out.read_text() != text:
                print(f"FAIL: committed {rel} is not what make_item5_envelope.py would write", file=sys.stderr)
                rc = 1
            else:
                print(f"OK: {rel}")
            continue
        if out.exists():
            if out.read_text() == text:
                print(f"unchanged: {rel}")
                continue
            print(f"FATAL: {rel} exists with different content; evidence is append-only", file=sys.stderr)
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        print(f"wrote {rel} {sha256_file_prefixed(out)}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
