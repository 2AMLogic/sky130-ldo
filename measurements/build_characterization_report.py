#!/usr/bin/env python3
"""Aggregated, per-spec-row characterization report generator (issue #21).

Rolls up the append-only evidence this repo already has -- the PVT-corner and
Monte Carlo records under `sim/*/records/`, the DRC/LVS records under
`layout/ldo-core/reports/`, and the post-layout PEX record under
`sim/pex-post-layout/records/` -- into one committed Markdown report,
`measurements/characterization.md`, keyed to each row of
`spec/target-spec.md`.

Design rules (see the issue and `sim/README.md`'s own conventions):

- **Extraction, not derivation.** Every PASS/FAIL/MATCH/clean verdict printed
  here is read verbatim from a record's own stated result (a JSON
  `overall_pass` field, a `## Overall verdict: ...` line, or a `status`
  field) -- this script never recomputes a verdict from raw measurements.
- **Freshness, not staleness-blindness.** For each `sim/` PVT/MC experiment
  cited, the script re-netlists the current testbench schematic via xschem
  and checks it against the committed netlist snapshot verbatim. For the
  DRC/LVS/PEX layout records, it checks the schematic/layout commit each
  record itself cites against the current git history / `LATEST*` pointers.
  A record that no longer matches is flagged `STALE`, not silently reported
  as current.
- **Conformance guardrail.** `spec/target-spec.md` is ratified (issue #1,
  DR-006) -- every verdict below is a conformance check against that ratified
  target, never a claim that ratification itself implies the implementation
  meets it (see #19's own record for the same convention, and DR-006 for why
  several rows are ratified while still failing this report's own checks).
- **N/A, not a fabricated PASS/FAIL.** A spec row with no independent
  testbench (e.g. Input, Load -- exercised as stimulus conditions inside
  other rows' testbenches, not measured by one of their own) is reported
  N/A with a stated reason, never forced into a PASS/FAIL slot it has no
  evidence for.
- **A subset verdict is labelled as one.** A record that ran fewer corners
  than its `experiment.json` declares is marked `(PVT subset)` and its own
  stated `--subset-reason` is quoted, so a 3-of-45-corner `PASS` cannot be
  read at a glance as full-matrix coverage.
- **Deterministic, and never self-referential.** No wall-clock timestamps and
  no *generating-commit* identity (repo `HEAD` sha, dirty flag, run id) are
  embedded. That second half is what makes `--check` usable: the commit that
  regenerates `measurements/characterization.md` necessarily has a different
  sha than whatever `HEAD` was before it, so any line naming the generating
  commit would make `--check` fail on the very commit that ships the file,
  and on every regenerate+commit cycle thereafter, forever. Content is
  therefore a pure function of the *cited evidence* (records, spec table,
  netlists, `LATEST*` pointers) -- so re-running this script against an
  unchanged tree reproduces byte-identical output both before and after the
  commit that lands it. This file itself is *not* append-only evidence in the
  `sim/README.md` sense -- it is a generated rollup of evidence that already
  lives under version control, so git history (not a per-run record id) is
  its audit trail; regenerate and commit it whenever the evidence it cites
  changes.

Usage
-----
    python3 measurements/build_characterization_report.py            # print to stdout
    python3 measurements/build_characterization_report.py --out PATH # write PATH
    python3 measurements/build_characterization_report.py --check    # verify
        measurements/characterization.md matches a fresh run; exit 1 if stale
    python3 measurements/build_characterization_report.py \\
        --no-netlist-freshness   # skip the xschem-based sim/ freshness re-check
                                  # (reports "unverified" instead) -- for
                                  # machines without the PDK toolchain
    python3 measurements/build_characterization_report.py \\
        --check --ignore-sim-freshness   # PDK-free structural check: compare
                                  # everything EXCEPT the per-`sim/` Freshness
                                  # column, which only a machine with the PDK
                                  # toolchain can evaluate (issue #220)

Why `--check` has two modes (issue #220)
----------------------------------------
Plain `--check` is byte-exact, and the per-`sim/` **Freshness** column it
compares is produced by a *live* xschem re-netlist -- so it can only be run
where the pinned sky130 PDK toolchain is installed. On a PDK-less machine the
generator honestly degrades every such cell to `unverified`, which means a bare
`--check` there FAILs on a perfectly healthy tree. That is why nothing gated
this generator for its first months: neither mode of the tool fit the headless
CI job, so no job ran it, and a `KeyError` that crashed *every* invocation went
unnoticed for two days (#215, fixed by #218) while CI stayed green.

`--ignore-sim-freshness` closes that gap without weakening the committed file:
it normalises **only** the per-`sim/`-row freshness verdict (the table cell and
the `Freshness: ...` clause of the matching Evidence-detail bullet) on *both*
sides before diffing. Everything else is still compared verbatim -- verdicts,
record ids, corner tallies, failing-measurement lists, `(PVT subset)` markers,
spec-row text, the prose, and the whole layout (DRC/LVS/PEX) section including
*its* Freshness column, which is derived from git history and `LATEST*`
pointers and therefore needs no toolchain at all.

The **Inputs** column (issue #237) is NOT normalised: it compares a record's
versioned input fingerprint (analyses, measurements, matrix, solver settings)
with the current `experiment.json` / `sim/spiceinit`, needs no toolchain, and
so stays verbatim-compared under `--ignore-sim-freshness` -- settings drift is
caught headlessly even where the schematic re-netlist is unavailable.

The gate is documented in `.github/workflows/ci.yml` and `package.json` rather
than inside the report it checks, deliberately: `measurements/characterization.md`
is sha256-pinned for T1 item 8 in `signoff/artifact-pins.json` (and, transitively,
in `signoff/block-manifest.json`, `signoff/evidence/characterization.generic.json`
and `signoff/records/t1-tier-report.json`), so **any** change to the text this
function emits -- prose included -- makes `signoff/check.sh` fail until all four
are re-pinned with a note saying why the artifact moved. Editing the emitted
prose is therefore a signoff-evidence change, not a docs change; keep
tooling/CI notes out of the report unless the pin move is the point.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

MEASUREMENTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = MEASUREMENTS_DIR.parent
SIM_DIR = REPO_ROOT / "sim"
LAYOUT_DIR = REPO_ROOT / "layout"
SPEC_FILE = REPO_ROOT / "spec" / "target-spec.md"

_SIM_BIN_DIR = str(SIM_DIR / "bin")
if _SIM_BIN_DIR not in sys.path:
    sys.path.insert(0, _SIM_BIN_DIR)
from _record_common import (  # shared helpers (issues #51, #96, #237)
    INPUT_FINGERPRINT_VERSION,
    build_input_fingerprint,  # noqa: F401 -- re-exported; tests use the module attribute
    git,
    load_corner_run_module,
    mc_input_sections,
    pvt_input_sections,
)

_LAYOUT_BIN_DIR = str(LAYOUT_DIR / "bin")
if _LAYOUT_BIN_DIR not in sys.path:
    sys.path.insert(0, _LAYOUT_BIN_DIR)
from _official_drc import official_result  # fail-closed official-deck reader (issue #260)

SCHEMATIC_FILE = "design/ldo_3v3in_1v8out.sch"
DEFAULT_OUT = MEASUREMENTS_DIR / "characterization.md"

# Heading that ends the per-spec-row (PDK-dependent freshness) section and
# starts the layout section, whose freshness is git-derived and needs no
# toolchain. `--ignore-sim-freshness` normalises text ABOVE this line only, so
# the two places that spell it must never drift apart -- hence the constant.
LAYOUT_SECTION_HEADING = "## Layout verification (not itself a spec row)"

# --------------------------------------------------------------------------
# spec row -> evidence mapping
# --------------------------------------------------------------------------

# Parameter name (must match spec/target-spec.md's own "Parameter" column
# text verbatim) -> sim/<slug> experiment that substantiates it, or None if
# no independent testbench exists for that row yet.
EVIDENCE_MAP: dict[str, str | None] = {
    "Input": None,
    "Output": "mc-output-accuracy",
    "Load": None,
    "Dropout @ 50 mA": "dropout-vs-load",
    "Line regulation": "line-regulation",
    "Load regulation (0–50 mA)": "load-regulation",
    "Load transient": "load-transient",
    "PSRR": "psrr-dc",
    "Iq (excl. load current)": "iq",
    "Current limit": "current-limit",
    "Startup / soft-start": "startup",
    "Enable / shutdown": "enable-shutdown",
    "Thermal": "thermal",
    "Output noise": None,
    # "Area" is deliberately absent from the sim/ map: its evidence is a layout
    # record (issue #236), read by the AREA_ROW branch of build_spec_row_table.
    "Area": None,
    "Stability": "loop-gain",
}

# Reason shown for a row this script reports N/A. Rows not listed here (a
# future spec row EVIDENCE_MAP doesn't know about) get a generic reason
# instead of crashing -- see GENERIC_NA_REASON.
NA_REASONS: dict[str, str] = {
    "Input": (
        "exercised as a stimulus condition (VIN step/sweep) inside every PVT "
        "testbench below, not measured by a testbench of its own."
    ),
    "Load": (
        "exercised as a stimulus condition (I_LOAD step/sweep) inside every "
        "PVT testbench below, not measured by a testbench of its own."
    ),
    "Output noise": (
        'waived by the spec row itself ("not specified — waived unless a '
        'consumer states a requirement").'
    ),
}
GENERIC_NA_REASON = "no independent testbench under `sim/` substantiates this row yet."


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def read_pointer(path: Path) -> str | None:
    if not path.is_file():
        return None
    val = path.read_text().strip()
    return val or None


# --------------------------------------------------------------------------
# spec/target-spec.md table parsing
# --------------------------------------------------------------------------


def parse_spec_rows(text: str) -> list[dict]:
    lines = text.splitlines()
    header_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith("| Parameter |"):
            header_idx = i
            break
    if header_idx is None:
        raise RuntimeError(f"{SPEC_FILE}: could not find the '| Parameter |' table header")
    rows = []
    i = header_idx + 2  # skip header row + '|---|---|' separator row
    while i < len(lines) and lines[i].strip().startswith("|"):
        cols = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if len(cols) >= 5 and cols[0]:
            rows.append(
                {
                    "parameter": cols[0],
                    "draft_target": cols[1],
                    "draft_stretch": cols[2],
                    "src": cols[3],
                    "note": cols[4],
                }
            )
        i += 1
    if not rows:
        raise RuntimeError(f"{SPEC_FILE}: table header found but no data rows parsed")
    return rows


# --------------------------------------------------------------------------
# sim/<slug> evidence (PVT + Monte Carlo records share one JSON schema)
# --------------------------------------------------------------------------


# Malformed-evidence diagnostics collected while a report is generated; the
# CLI exits nonzero when any are present (issue #255).
EVIDENCE_ERRORS: list[str] = []


def _describe_value(value: object) -> str:
    if value is None:
        return "null or missing"
    return f"{type(value).__name__} {json.dumps(value)[:40]}"


def latest_sim_record(slug: str) -> tuple[dict, Path] | None:
    """The latest *campaign* record under `sim/<slug>/records/`.

    A campaign record (minted by `mc-run.py` / `corner-run.py`) stamps no
    `evidence_kind` key at all. A *derived* record kind -- e.g. `sim/bin/
    yield-run.py`'s `klt yield` records (issue #203) -- always stamps an
    explicit non-`None` `evidence_kind` and measures nothing of its own (no
    netlist, no ngspice run), so it must never be selected here even if its
    filename sorts after every campaign record's (issue #215: the newest
    file under a slug's `records/` is not necessarily a campaign record
    once a second record kind shares that directory).

    Selecting on "no `evidence_kind` key" rather than an allow-list of one
    derived-kind string keeps the *next* new derived record kind from
    silently resurrecting this same bug.
    """
    records_dir = SIM_DIR / slug / "records"
    if not records_dir.is_dir():
        return None
    json_files = sorted(records_dir.glob("*.json"))
    campaign: list[tuple[dict, Path]] = []
    for f in json_files:
        try:
            data = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("evidence_kind") is None:
            campaign.append((data, f))
    if not campaign:
        return None
    data, latest = campaign[-1]
    return data, latest.with_suffix(".md")


def sim_corner_tally(record: dict) -> str | None:
    corners = record.get("corners")
    if isinstance(corners, list) and corners:
        passed = sum(1 for c in corners if c.get("pass"))
        return f"{passed}/{len(corners)} corner(s) PASS"
    return None


def sim_subset_reason(record: dict) -> str | None:
    """The record's own stated reason for running a PVT subset, or None if it
    ran the full matrix its manifest declares.

    A verdict extracted from a 3-corner subset is not the same claim as one
    extracted from the full 45-point matrix — "3/3 corner(s) PASS" would
    otherwise read, at a glance, exactly like full-matrix coverage. The runner
    already refuses to write a subset record without a `--subset-reason`
    (`sim/README.md`), so this is an extraction of what the record itself
    states, not a re-derivation."""
    matrix = record.get("matrix")
    if not isinstance(matrix, dict) or not matrix.get("is_subset"):
        return None
    reason = str(matrix.get("subset_reason") or "").strip()
    return reason or "(the record states no reason)"


def sim_failing_measurements(record: dict) -> str | None:
    """Which bounded measurement(s) a corner-matrix record's FAIL corners
    actually failed on, as the record's own per-measurement `pass` flags state
    them — or None if every corner passed (or the record has no corner list).

    A row-level "FAIL, 12/15" does not say *which clause* failed, and a spec
    row can carry several (issue #120: the Thermal row's FAIL was read as a
    theta-JA/Tj question when every failing corner had in fact failed only
    the thermal-shutdown hysteresis-sign bound). Extraction only, no
    re-derivation: a corner that failed without any measurement flagged (e.g.
    an ngspice error or timeout) is counted as such rather than guessed at."""
    corners = record.get("corners")
    if not isinstance(corners, list) or not corners:
        return None
    counts: dict[str, int] = {}
    unflagged = 0
    for corner in corners:
        if corner.get("pass"):
            continue
        failed = [
            str(m.get("name", "?"))
            for m in corner.get("measurements") or []
            if isinstance(m, dict) and m.get("pass") is False
        ]
        if not failed:
            unflagged += 1
        for name in failed:
            counts[name] = counts.get(name, 0) + 1
    if not counts and not unflagged:
        return None
    parts = [f"`{name}` at {n} corner(s)" for name, n in counts.items()]
    if unflagged:
        parts.append(f"{unflagged} corner(s) with no measurement flagged (run-level failure)")
    return "; ".join(parts)


def sim_mc_sample_tally(record: dict) -> str | None:
    resp = record.get("klt_response")
    if not isinstance(resp, dict):
        return None
    corners = resp.get("corners")
    if not isinstance(corners, list) or not corners:
        return None
    passed = sum(1 for c in corners if c.get("status") == "pass")
    return f"{passed}/{len(corners)} individual sample(s) PASS"


def _record_kind(record: dict) -> str:
    fp = record.get("input_fingerprint")
    if isinstance(fp, dict) and fp.get("kind") in ("pvt", "mc"):
        return fp["kind"]
    return "mc" if "klt_request" in record else "pvt"


def check_input_freshness(slug: str, record: dict) -> str:
    """Experiment/solver freshness (issue #237): does the cited record's
    effective-input fingerprint still match the current manifest and solver
    settings? Headless -- reads `experiment.json` and `sim/spiceinit` only, no
    xschem/PDK -- so it runs under `--ignore-sim-freshness` and
    `--no-netlist-freshness` too. Independent of the schematic re-netlist
    (`check_netlist_freshness`); the two are reported as separate reasons.

    Dimensions: analyses, measurements, matrix, solver (PVT) or
    analyses, measurements, matrix, netlist_patch (MC; the klt backend is not
    shown to read `sim/spiceinit`, so no solver dimension is claimed for it).
    A dimension the record carries no provenance for is "unverified", never
    assumed fresh; the original record is never modified.
    """
    manifest_rel = (record.get("links") or {}).get("manifest") or f"sim/{slug}/experiment.json"
    manifest = REPO_ROOT / manifest_rel
    if not manifest.is_file():
        return f"unverified: experiment manifest not found ({manifest_rel})"
    try:
        raw = json.loads(manifest.read_text())
    except (OSError, ValueError) as exc:
        return f"unverified: experiment manifest unreadable ({manifest_rel}: {exc})"

    kind = _record_kind(record)
    spiceinit = SIM_DIR / "spiceinit"
    if kind == "pvt":
        current = pvt_input_sections(
            raw, spiceinit.read_text() if spiceinit.is_file() else None
        )
    else:
        current = mc_input_sections(raw)

    fp = record.get("input_fingerprint")
    recorded: dict = {}
    legacy_note = ""
    if isinstance(fp, dict) and fp.get("version") == INPUT_FINGERPRINT_VERSION and isinstance(
        fp.get("sections"), dict
    ):
        recorded = dict(fp["sections"])
    else:
        legacy_note = (
            "no input fingerprint in this legacy record"
            if not isinstance(fp, dict)
            else f"unsupported input-fingerprint version {fp.get('version')!r}"
        )
        # A PVT record from #190 on already carries the init-settings hash.
        legacy_solver = (record.get("tools") or {}).get("spiceinit_sha256")
        if kind == "pvt" and legacy_solver:
            recorded["solver"] = legacy_solver

    dims = list(current) if kind == "mc" else ["analyses", "measurements", "matrix", "solver"]
    stale, unverified, matched = [], [], []
    for dim in dims:
        if dim not in recorded:
            unverified.append(dim)
        elif dim not in current:
            unverified.append(dim)
        elif recorded[dim] == current[dim]:
            matched.append(dim)
        else:
            stale.append(dim)

    na = (
        "; solver settings: not applicable (klt backend; `sim/spiceinit` is not consumed)"
        if kind == "mc"
        else ""
    )
    if stale:
        msg = f"STALE (changed since the record: {', '.join(stale)}"
        if unverified:
            msg += f"; unverified: {', '.join(unverified)}"
        return msg + ")"
    if unverified:
        why = f" -- {legacy_note}" if legacy_note else ""
        ok = f"; matching: {', '.join(matched)}" if matched else ""
        return f"unverified: {', '.join(unverified)}{why}{ok}"
    return (
        f"fresh (the record's input fingerprint v{INPUT_FINGERPRINT_VERSION} matches the "
        f"current manifest/solver inputs: {', '.join(matched)}{na})"
    )


def check_netlist_freshness(module, pdk, slug: str, record: dict) -> str:
    # Defense in depth alongside `latest_sim_record`'s own campaign-only
    # selection (issue #215): this function's whole job is to report
    # evidence state, so an unexpected record shape (e.g. a future derived
    # record kind that also lacks `links.netlist_snapshot`) must produce a
    # diagnosed error naming the offending record -- never a raw KeyError
    # traceback that takes the whole report generator down with it.
    record_id = record.get("record_id", "?")
    try:
        provenance_source = record["experiment"]["provenance_source"]
        snapshot_rel = record["links"]["netlist_snapshot"]
    except (KeyError, TypeError) as exc:
        return (
            f"ERROR: record `{record_id}` under sim/{slug} has no {exc} -- "
            "not a campaign record this checker recognizes"
        )
    schematic = REPO_ROOT / provenance_source
    snapshot_path = REPO_ROOT / snapshot_rel
    if not schematic.is_file():
        return f"unverified: testbench schematic not found ({provenance_source})"
    if not snapshot_path.is_file():
        return f"unverified: netlist snapshot not found ({snapshot_rel})"
    if not shutil.which("xschem"):
        return "unverified: xschem not on PATH (skipping live re-netlist)"
    try:
        tmp_dir = module.BUILD_DIR / "characterization-report" / slug
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        fresh_netlist = module.netlist_with_xschem(schematic, tmp_dir, pdk)
        fresh_body = module.netlist_body(fresh_netlist)
    except module.HarnessError as exc:
        return f"unverified: {exc}"

    # `corner-run.py` (PVT records) appends a trailing `.end` line the runner
    # itself owns (never part of `netlist_body()`'s own output, which strips
    # every `.end` line already); `mc-run.py` (Monte Carlo records) appends no
    # such line. Drop only that literal trailing `.end` -- NOT trailing blank
    # lines, which `netlist_body()`'s own output can legitimately end with
    # (the schematic's last `.ends` is often followed by a blank line before
    # xschem's own `.end`), so stripping blanks here would silently misalign
    # the tail-match below by one line.
    snapshot_lines = snapshot_path.read_text().splitlines()
    if snapshot_lines and snapshot_lines[-1].strip().lower() == ".end":
        snapshot_lines.pop()

    if fresh_body and len(fresh_body) <= len(snapshot_lines) and (
        snapshot_lines[len(snapshot_lines) - len(fresh_body) :] == fresh_body
    ):
        return (
            "fresh (a live xschem re-netlist of the current testbench schematic "
            "matches the committed netlist snapshot verbatim)"
        )
    return (
        "STALE (a live xschem re-netlist of the current testbench schematic no "
        "longer matches the committed netlist snapshot)"
    )


# --------------------------------------------------------------------------
# layout (DRC/LVS) evidence
# --------------------------------------------------------------------------

OVERALL_MD_RE = re.compile(r"^## Overall verdict:\s*(.+)$", re.MULTILINE)
SCHEMATIC_FRESHNESS_RE = re.compile(r"Schematic freshness:.*?commit `([0-9a-f]+)`")
LAYOUT_RECORD_RE = re.compile(r"\*\*Layout record\*\*:\s*`([^`]+)`")


def current_schematic_sha() -> str:
    return git(REPO_ROOT, "log", "-1", "--format=%h", "--", SCHEMATIC_FILE)


def extract_overall_verdict_md(text: str) -> str | None:
    m = OVERALL_MD_RE.search(text)
    return m.group(1).strip() if m else None


def check_schematic_freshness_from_record(record_text: str) -> str:
    m = SCHEMATIC_FRESHNESS_RE.search(record_text)
    if not m:
        return "unverified: no 'Schematic freshness' line found in the record"
    recorded_sha = m.group(1)
    current_sha = current_schematic_sha()
    if not current_sha:
        return "unverified: could not resolve the schematic's current git history"
    if current_sha.startswith(recorded_sha) or recorded_sha.startswith(current_sha):
        return (
            f"fresh (record cites commit `{recorded_sha}`, matching the schematic's "
            "current last-touching commit)"
        )
    return (
        f"STALE (record cites commit `{recorded_sha}`; the schematic has since moved "
        f"to `{current_sha}`)"
    )


def layout_record(pointer_name: str) -> tuple[str, Path] | None:
    pointer = LAYOUT_DIR / "ldo-core" / "reports" / pointer_name
    record_id = read_pointer(pointer)
    if record_id is None:
        return None
    d = LAYOUT_DIR / "ldo-core" / "reports" / record_id
    if not d.is_dir():
        return None
    return record_id, d


AREA_ROW = "Area"


def latest_area_record() -> tuple[dict, Path] | None:
    """The record `layout/ldo-core/reports/LATEST-AREA` names (issue #236),
    as `(area.json contents, record.md path)`."""
    found = layout_record("LATEST-AREA")
    if found is None:
        return None
    _record_id, d = found
    path = d / "area.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text()), d / "record.md"
    except ValueError:
        return None


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_area_freshness(record: dict) -> str:
    """Is the area record about the routed GDS that exists now?

    Two content checks, no toolchain: (1) the artifact the record cites still
    hashes to the sha256 it recorded, and (2) the CURRENT routed GDS -- the
    `ldo_core.gds` in the `layout/ldo-core/reports/LATEST` record -- hashes to
    the same value. A re-routed layout fails (2) and is reported STALE until a
    new area record is minted; the verdict itself is never recomputed here.
    """
    gds = record.get("gds") or {}
    recorded = gds.get("sha256")
    cited = gds.get("path")
    if not recorded or not cited:
        return "unverified: area record carries no GDS path/sha256"
    cited_path = REPO_ROOT / cited
    if not cited_path.is_file():
        return f"STALE (cited GDS `{cited}` no longer exists)"
    if _sha256_of(cited_path) != recorded:
        return f"STALE (cited GDS `{cited}` no longer hashes to the recorded sha256)"
    latest = layout_record("LATEST")
    if latest is None:
        return "unverified: layout/ldo-core/reports/LATEST pointer is missing"
    latest_id, latest_dir = latest
    current = latest_dir / f"{record.get('cell', 'ldo_core')}.gds"
    if not current.is_file():
        return f"unverified: no routed GDS in the current `LATEST` record `{latest_id}`"
    if _sha256_of(current) == recorded:
        return f"fresh (the routed GDS in the current `LATEST` record `{latest_id}` has the recorded sha256)"
    return (
        f"STALE (the routed GDS in the current `LATEST` record `{latest_id}` differs from "
        f"the measured one; mint a new area record)"
    )


def check_lvs_geometry_freshness(lvs_dir: Path) -> str:
    """Is the LVS record about the routed GDS that exists now? (issue #287)

    Content-based and toolchain-free, modelled on `check_area_freshness`: (1)
    the GDS stored in the LVS record dir hashes to the `environment.layout_sha256`
    its `lvs.json` recorded, and (2) the CURRENT routed GDS in the
    `layout/ldo-core/reports/LATEST` record hashes to the same value. Identity
    is bytes, never timestamps, directory names or pointer identity. Every
    missing input gives a diagnosed `unverified`/`STALE` result.
    """
    path = lvs_dir / "lvs.json"
    try:
        env = json.loads(path.read_text()).get("environment") or {}
        recorded = env.get("layout_sha256")
    except (OSError, ValueError, AttributeError):
        return "unverified: LVS record has no readable lvs.json"
    if not isinstance(recorded, str) or not recorded:
        return "unverified: LVS record carries no environment.layout_sha256"
    cited_path = lvs_dir / "ldo_core.gds"
    if not cited_path.is_file():
        return "STALE (the GDS cited by the LVS record no longer exists)"
    try:
        if _sha256_of(cited_path) != recorded:
            return "STALE (the GDS stored with the LVS record no longer hashes to its recorded layout_sha256)"
    except OSError:
        return "unverified: the GDS stored with the LVS record is unreadable"
    latest = layout_record("LATEST")
    if latest is None:
        return "unverified: layout/ldo-core/reports/LATEST pointer is missing"
    latest_id, latest_dir = latest
    current = latest_dir / "ldo_core.gds"
    if not current.is_file():
        return f"unverified: no routed GDS in the current `LATEST` record `{latest_id}`"
    try:
        same = _sha256_of(current) == recorded
    except OSError:
        return f"unverified: routed GDS in the current `LATEST` record `{latest_id}` is unreadable"
    if same:
        return f"fresh (the routed GDS in the current `LATEST` record `{latest_id}` has the LVS-recorded sha256)"
    return (
        f"STALE (the routed GDS in the current `LATEST` record `{latest_id}` differs from "
        "the one LVS checked; re-run LVS)"
    )


def combine_freshness(*parts: str) -> str:
    """STALE if any part is STALE; fresh only if all are; otherwise unverified."""
    for p in parts:
        if p.startswith("STALE"):
            return p
    for p in parts:
        if not p.startswith("fresh"):
            return p if p.startswith("unverified") else f"unverified: {p}"
    return "fresh (" + "; ".join(parts) + ")"


def read_layout_record_text(record_id: str) -> str | None:
    path = LAYOUT_DIR / "ldo-core" / "reports" / record_id / "record.md"
    try:
        return path.read_text()
    except OSError:
        return None


def check_pex_layout_freshness(record_text: str) -> str:
    m = LAYOUT_RECORD_RE.search(record_text)
    if not m:
        return "unverified: no 'Layout record' line found in the record"
    cited = m.group(1).rsplit("/", 1)[-1]
    current = read_pointer(LAYOUT_DIR / "ldo-core" / "reports" / "LATEST-LVS")
    if current is None:
        return "unverified: layout/ldo-core/reports/LATEST-LVS pointer is missing"
    if cited != current:
        return f"STALE (cites LVS record `{cited}`; `LATEST-LVS` now points to `{current}`)"
    # The pointer matching is necessary but not sufficient: the cited LVS
    # record must itself be current against the schematic (#245).
    lvs_text = read_layout_record_text(cited)
    if lvs_text is None:
        return f"unverified: cited LVS record `{cited}` record.md is missing or unreadable"
    sch = combine_freshness(
        check_schematic_freshness_from_record(lvs_text),
        check_lvs_geometry_freshness(LAYOUT_DIR / "ldo-core" / "reports" / cited),
    )
    if sch.startswith("fresh"):
        return f"fresh (cites the current `LATEST-LVS` record `{cited}`; its {sch})"
    if sch.startswith("STALE"):
        return f"STALE (cites the current `LATEST-LVS` record `{cited}`, but that LVS record is stale: {sch})"
    return f"unverified: cites the current `LATEST-LVS` record `{cited}`, but its schematic provenance is unverified ({sch})"


def extract_pex_results(text: str) -> list[tuple[str, str]]:
    results = []
    heading = None
    for line in text.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
        m = re.match(r"^- Result: (.+)$", line.strip())
        if m and heading:
            results.append((heading, m.group(1).strip()))
    return results


def latest_pex_record() -> tuple[dict, Path] | None:
    return latest_sim_record("pex-post-layout")


# --------------------------------------------------------------------------
# report assembly
# --------------------------------------------------------------------------


def rel(path: Path) -> str:
    """Path relative to `measurements/` (where the generated report lives),
    for use as a Markdown link target -- NOT relative to REPO_ROOT, which
    would silently produce a broken link from a reader viewing the committed
    `measurements/characterization.md` file."""
    return os.path.relpath(path, MEASUREMENTS_DIR)


def _short_verdict(text: str) -> str:
    for token in ("fresh", "STALE", "ERROR"):
        if text.startswith(token):
            return token
    return "unverified"


def build_spec_row_table(
    spec_rows: list[dict], skip_netlist_freshness: bool
) -> tuple[list[str], list[str]]:
    """Returns (table_lines, detail_lines)."""
    module = None
    pdk = None
    if not skip_netlist_freshness:
        try:
            # Reused purely for its xschem-netlisting + PDK-resolution helpers
            # (`netlist_with_xschem`, `netlist_body`, `resolve_pdk`,
            # `load_pin`). Read-only reuse: this script never calls anything
            # that writes evidence.
            module = load_corner_run_module(SIM_DIR / "bin")
            pdk = module.resolve_pdk(module.load_pin())
        except Exception as exc:  # noqa: BLE001 -- degrade to "unverified", never crash the report
            module = None
            pdk = None
            _pdk_error = str(exc)
        else:
            _pdk_error = None
    else:
        _pdk_error = None

    table = [
        "| Parameter | Ratified target | Verdict (vs ratified target) | Evidence | Inputs | Freshness |",
        "|---|---|---|---|---|---|",
    ]
    detail: list[str] = []

    for row in spec_rows:
        param = row["parameter"]
        if param == AREA_ROW:
            area = latest_area_record()
            if area is None:
                table.append(
                    f"| {param} | {row['draft_target']} | **ERROR** | no record under "
                    f"`layout/ldo-core/reports/LATEST-AREA` | — | — |"
                )
                detail.append(
                    f"- **{param}**: ERROR — no area record is pointed to by "
                    f"`layout/ldo-core/reports/LATEST-AREA`. Mint one with "
                    f"`layout/bin/render-ldo-area-record.py`."
                )
                continue
            arec, amd = area
            verdict = arec.get("verdict", "?")
            rid = arec.get("record_id", "?")
            freshness = check_area_freshness(arec)
            fshort = _short_verdict(freshness)
            # The Freshness cell is "<token> (GDS sha256)", not a bare token:
            # this verdict is headless (a content hash, no PDK), so it must
            # stay verbatim-compared under `--ignore-sim-freshness`, whose
            # normaliser only rewrites bare-token cells.
            table.append(
                f"| {param} | {row['draft_target']} | **{verdict}** | "
                f"[`{rid}`]({rel(amd)}) | — | {fshort} (GDS sha256) |"
            )
            detail.append(
                f"- **{param}**: **{verdict}** (vs the ratified row; verdict read from the "
                f"record) — layout record [`{rid}`]({rel(amd)}): `{arec.get('cell')}` measures "
                f"{arec.get('width_um')} um x {arec.get('height_um')} um = "
                f"{arec.get('area_mm2')} mm² against the unchanged < {arec.get('limit_mm2')} mm² "
                f"limit (strict). Convention: {arec.get('convention')} "
                f"GDS `{(arec.get('gds') or {}).get('path')}` "
                f"(sha256 `{(arec.get('gds') or {}).get('sha256')}`). "
                f"GDS freshness: {freshness}."
            )
            continue

        slug = EVIDENCE_MAP.get(param)
        if slug is None:
            reason = NA_REASONS.get(param, GENERIC_NA_REASON)
            table.append(f"| {param} | {row['draft_target']} | N/A | — | — | — |")
            detail.append(f"- **{param}**: N/A — {reason}")
            continue

        found = latest_sim_record(slug)
        if found is None:
            table.append(
                f"| {param} | {row['draft_target']} | **ERROR** | no record found under "
                f"`sim/{slug}/records/` | — | — |"
            )
            detail.append(
                f"- **{param}**: ERROR — `EVIDENCE_MAP` cites `sim/{slug}`, but no record "
                f"exists there. This is a report/mapping bug, not an N/A row."
            )
            continue

        record, md_path = found
        record_id = record.get("record_id", "?")
        record_rel = rel(md_path)
        overall = record.get("overall_pass")
        if not isinstance(overall, bool):
            msg = (
                f"record `{record_id}` ({record_rel}) under sim/{slug} has a malformed "
                f"`overall_pass` verdict ({_describe_value(overall)}); a campaign record "
                "must state a JSON boolean. Not coerced, and no older campaign record is "
                "substituted."
            )
            EVIDENCE_ERRORS.append(f"{param}: {msg}")
            table.append(
                f"| {param} | {row['draft_target']} | **ERROR** | "
                f"[`{record_id}`]({record_rel}) | — | — |"
            )
            detail.append(f"- **{param}**: ERROR — {msg}")
            continue
        verdict = "PASS" if overall else "FAIL"
        tally = sim_corner_tally(record) or sim_mc_sample_tally(record) or "n/a"

        if module is not None and pdk is not None:
            freshness = check_netlist_freshness(module, pdk, slug, record)
        elif skip_netlist_freshness:
            freshness = "unverified: --no-netlist-freshness passed"
        else:
            freshness = f"unverified: PDK/toolchain unavailable ({_pdk_error})"

        freshness_short = "fresh" if freshness.startswith("fresh") else (
            "STALE" if freshness.startswith("STALE") else (
                "ERROR" if freshness.startswith("ERROR") else "unverified"
            )
        )

        inputs = check_input_freshness(slug, record)
        inputs_short = _short_verdict(inputs)

        subset_reason = sim_subset_reason(record)
        subset_flag = " (PVT subset)" if subset_reason else ""

        table.append(
            f"| {param} | {row['draft_target']} | **{verdict}**{subset_flag} | "
            f"[`{record_id}`]({record_rel}) | {inputs_short} | {freshness_short} |"
        )
        detail_line = (
            f"- **{param}**: **{verdict}** (vs the ratified spec row) — "
            f"`sim/{slug}` record [`{record_id}`]({record_rel}), {tally}. "
            f"Experiment/solver inputs: {inputs}. "
            f"Freshness: {freshness}."
        )
        failing = sim_failing_measurements(record)
        if failing:
            detail_line += f" Failing measurement(s), per the record: {failing}."
        if subset_reason:
            detail_line += (
                " **PVT subset, not the full matrix this experiment declares** — "
                f"the record's own stated reason: {subset_reason}"
            )
        detail.append(detail_line)

    return table, detail


LDO_CORE_CELL = "ldo_core"  # top cell of the ldo-core flow (run-ldo-layout-flow.sh CELL)


def drc_row_detail(d: Path) -> str:
    """The DRC row's parenthetical, naming each deck explicitly (issue #260).

    The record's overall verdict covers BOTH the curated klt deck (`drc.json`)
    and, from #260 on, the PDK's official deck (`mr-drc.run.json` +
    `mr-drc.lyrdb`). Showing only the curated fields beside a FAIL driven by
    the official deck would make the row contradict itself, so each deck is
    labelled. The official deck's state comes from the same fail-closed reader
    the flow uses (`layout/bin/_official_drc.py`); a record that predates the
    dual-deck gate (no `mr-drc.run.json`) says so rather than implying clean.
    """
    parts: list[str] = []
    drc_json_path = d / "drc.json"
    if drc_json_path.is_file():
        try:
            drc_json = json.loads(drc_json_path.read_text())
            parts.append(
                f"curated deck: status={drc_json.get('status')}, "
                f"violation_count={drc_json.get('violation_count')}"
            )
        except ValueError:
            parts.append("curated deck: ERROR (unreadable drc.json)")
    else:
        parts.append("curated deck: ERROR (no drc.json)")

    if not (d / "mr-drc.run.json").is_file():
        parts.append("official deck: not run in this record")
    else:
        off = official_result(d, LDO_CORE_CELL)
        if off.state == "clean":
            parts.append(f"official deck `sky130A_mr.drc`: clean, {off.detail}")
        elif off.state == "violations":
            parts.append(
                f"official deck `sky130A_mr.drc`: violations, violation_count={off.total} "
                f"in {len(off.counts)} rule families"
            )
        else:
            parts.append(f"official deck `sky130A_mr.drc`: ERROR ({off.detail})")
    return "; ".join(parts)


def build_layout_section() -> list[str]:
    lines: list[str] = []
    lines.append("| Check | Verdict (record's own) | Record | Freshness |")
    lines.append("|---|---|---|---|")

    drc = layout_record("LATEST")
    if drc is not None:
        record_id, d = drc
        record_text = (d / "record.md").read_text() if (d / "record.md").is_file() else ""
        verdict = extract_overall_verdict_md(record_text) or "?"
        detail = drc_row_detail(d)
        freshness = (
            check_schematic_freshness_from_record(record_text) if record_text else "unverified"
        )
        freshness_short = "fresh" if freshness.startswith("fresh") else (
            "STALE" if freshness.startswith("STALE") else "unverified"
        )
        lines.append(
            f"| DRC (issue #16) | **{verdict}** ({detail}) | "
            f"[`{record_id}`]({rel(d / 'record.md')}) | {freshness_short} |"
        )
    else:
        lines.append("| DRC (issue #16) | **ERROR** | no `layout/ldo-core/reports/LATEST` record | — |")

    lvs = layout_record("LATEST-LVS")
    if lvs is not None:
        record_id, d = lvs
        record_text = (d / "record.md").read_text() if (d / "record.md").is_file() else ""
        verdict = extract_overall_verdict_md(record_text) or "?"
        lvs_json_path = d / "lvs.json"
        detail = ""
        if lvs_json_path.is_file():
            lvs_json = json.loads(lvs_json_path.read_text())
            detail = (
                f"status={lvs_json.get('status')}, mismatch_count={lvs_json.get('mismatch_count')}"
            )
        freshness = (
            combine_freshness(
                check_schematic_freshness_from_record(record_text),
                check_lvs_geometry_freshness(d),
            )
            if record_text
            else "unverified"
        )
        freshness_short = "fresh" if freshness.startswith("fresh") else (
            "STALE" if freshness.startswith("STALE") else "unverified"
        )
        lines.append(
            f"| LVS (issue #17) | **{verdict}** ({detail}) | "
            f"[`{record_id}`]({rel(d / 'record.md')}) | {freshness_short} |"
        )
    else:
        lines.append(
            "| LVS (issue #17) | **ERROR** | no `layout/ldo-core/reports/LATEST-LVS` record | — |"
        )

    pex = latest_pex_record()
    if pex is not None:
        pex_json, pex_md = pex
        record_id = pex_json.get("record_id", "?")
        record_text = pex_md.read_text() if pex_md.is_file() else ""
        results = extract_pex_results(record_text)
        detail = "; ".join(f"{h}: {r}" for h, r in results) if results else "?"
        freshness = check_pex_layout_freshness(record_text) if record_text else "unverified"
        freshness_short = "fresh" if freshness.startswith("fresh") else (
            "STALE" if freshness.startswith("STALE") else "unverified"
        )
        lines.append(
            f"| Post-layout PEX (issue #20) | see detail — no single PASS/FAIL "
            f"([caveat](../sim/pex-post-layout/README.md)) | "
            f"[`{record_id}`]({rel(pex_md)}) | {freshness_short} |"
        )
        lines.append("")
        lines.append(
            f"Post-layout PEX detail (record `{record_id}`): {detail}. "
            "This paragraph is generated from the record's own `- Result:` "
            "lines and carries no hand-written triage beyond them — the "
            "per-record narrative (`klt` pin, per-corner root-cause "
            "attribution, upstream/repo-local issue cross-references) is "
            "hand-maintained in "
            "[`sim/pex-post-layout/README.md`](../sim/pex-post-layout/README.md) "
            "instead, so do not hand-edit it in here."
        )
    else:
        lines.append(
            "| Post-layout PEX (issue #20) | **ERROR** | no `sim/pex-post-layout/records/` record | — |"
        )

    return lines


def generate_report(skip_netlist_freshness: bool = False) -> str:
    EVIDENCE_ERRORS.clear()
    spec_text = SPEC_FILE.read_text()
    spec_rows = parse_spec_rows(spec_text)
    table, detail = build_spec_row_table(spec_rows, skip_netlist_freshness)
    layout_lines = build_layout_section()

    lines: list[str] = []
    lines.append("# LDO characterization report (against the ratified spec)")
    lines.append("")
    lines.append(
        "Generated by [`measurements/build_characterization_report.py`]"
        "(build_characterization_report.py) — the capstone rollup of the "
        "block's own append-only evidence (DRC #16, LVS #17, full PVT-corner + "
        "Monte Carlo/yield #19, post-layout extracted-netlist #20), keyed to "
        "each row of [`spec/target-spec.md`](../spec/target-spec.md)."
    )
    lines.append("")
    lines.append(
        "**This is not a compliance claim — it is the opposite: a live "
        "conformance check against `spec/target-spec.md`, which is ratified "
        "(issue #1, DR-006).** Every verdict below is stated explicitly as "
        "*against the ratified row*, per the same guardrail issue #19's own "
        "records already use. A `PASS`/`FAIL`/`MATCH`/`clean` value here is "
        "read verbatim from the cited record's own stated result — this "
        "script never recomputes a verdict from raw measurements (see the "
        "module docstring in "
        "`build_characterization_report.py` for the full extraction/"
        "freshness/no-re-derivation rules)."
    )
    lines.append("")
    lines.append(
        "This file is a **generated rollup**, not itself append-only "
        "evidence in the `sim/README.md` sense: it is overwritten in place "
        "each time the generator runs, and git history — not a per-run "
        "record id — is its audit trail. Regenerate it (and commit the "
        "result) whenever the evidence it cites changes:"
    )
    lines.append("")
    lines.append("```bash")
    lines.append(
        "python3 measurements/build_characterization_report.py "
        "--out measurements/characterization.md"
    )
    lines.append("# or verify the committed file is not stale:")
    lines.append("python3 measurements/build_characterization_report.py --check")
    lines.append("```")
    lines.append("")
    lines.append(
        "Re-running this generator against an unchanged tree with the same "
        "pinned toolchain (`sim/pdk.json`) reproduces this file byte-for-"
        "byte — no wall-clock timestamps and no generating-commit identity "
        "are embedded, so `--check` passes both before and after the commit "
        "that lands a regenerated report. The per-`sim/` "
        "**Freshness** column below is a live check (a fresh `xschem` "
        "re-netlist of the current testbench schematic, compared verbatim "
        "against the committed netlist snapshot); on a machine without the "
        "PDK toolchain it degrades to `unverified` rather than a false "
        "claim of freshness (`--no-netlist-freshness` forces this "
        "explicitly). The separate **Inputs** column / `Experiment/solver "
        "inputs` clause is a headless check (no `xschem`/PDK): it compares "
        "the cited record's versioned input fingerprint (analyses, "
        "measurement expressions/bounds, declared matrix, solver settings — "
        "an allow-list of execution-relevant manifest keys, so prose edits do "
        "not invalidate a simulation; `sim/README.md`) with the current "
        "`experiment.json` and `sim/spiceinit`, and reports a legacy record "
        "without that provenance as `unverified` rather than guessing. It is "
        "compared even under `--ignore-sim-freshness`. The layout (DRC/LVS/PEX) **Freshness** column instead "
        "compares the schematic/layout commit each record itself cites "
        "against the current git history / `LATEST*` pointers — no "
        "toolchain required."
    )
    lines.append("")
    lines.append(
        "No generating-commit SHA is stamped into this file, deliberately: a "
        "commit that regenerates this report cannot contain its own resulting "
        "hash, so such a line would make `--check` fail by construction on the "
        "very commit that ships the regenerated file. Provenance instead comes "
        "from the record ids cited per row (each of which is itself an "
        "append-only, commit-pinned record) plus this file's own git history."
    )
    lines.append("")

    lines.append("## Per-spec-row characterization")
    lines.append("")
    lines.extend(table)
    lines.append("")
    lines.append("### Evidence detail")
    lines.append("")
    lines.extend(detail)
    lines.append("")

    lines.append(LAYOUT_SECTION_HEADING)
    lines.append("")
    lines.append(
        "DRC/LVS/post-layout PEX substantiate that the routed layout matches "
        "the schematic these spec-row testbenches above simulate — they are "
        "not measurements of a numeric spec parameter themselves, so they "
        "are rolled up separately rather than forced into the table above."
    )
    lines.append("")
    lines.extend(layout_lines)
    lines.append("")

    lines.append("## Limitations")
    lines.append("")
    lines.append(
        "- **Ratified spec, unratified implementation.** Every verdict above "
        "is against `spec/target-spec.md`'s ratified row (issue #1, DR-006) — "
        "a FAIL here means the current implementation, not the target, falls "
        "short. Re-verification is required whenever the underlying `sim/` or "
        "layout evidence changes, or a future decision record supersedes a "
        "ratified row's target (see DR-006's Consequences)."
    )
    lines.append(
        "- **N/A rows are a coverage gap, not a pass.** A row marked N/A above "
        "has no independent testbench yet — it is neither substantiated nor "
        "refuted by this report."
    )
    lines.append(
        "- **A `(PVT subset)` verdict is narrower than a full-matrix one.** "
        "That marker means the cited record ran fewer corners than its own "
        "`experiment.json` declares (the runner refuses to write such a record "
        "without a stated reason, quoted in the Evidence detail above). A "
        "subset `PASS` says the corners that ran passed — it does not say the "
        "full matrix would."
    )
    lines.append(
        "- **Freshness checks trust the tree, not the working copy.** The "
        "schematic-freshness check (layout section) compares against git "
        "history, so uncommitted local edits to "
        f"`{SCHEMATIC_FILE}` will not be detected as stale until committed."
    )
    lines.append(
        "- **Post-layout PEX (issue #20) has no single PASS/FAIL** — see "
        "`sim/pex-post-layout/README.md` for the disclosed `klt`/PDK/layout "
        "caveats that bound the extracted-side leg for the cited record, and "
        "for that record's own narrative summary. This bullet is generated "
        "and deliberately makes no record-specific claim of its own: which "
        "caveats bind, and whether they are upstream or repo-local, changes "
        "from record to record and is tracked in that file, not here."
    )
    lines.append("")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# PDK-free structural comparison (issue #220)
# --------------------------------------------------------------------------

# What a normalised per-`sim/`-row freshness verdict is replaced with. Chosen
# to be obviously not a verdict, so it cannot be mistaken for one if it ever
# leaks into a diff a human reads.
FRESHNESS_PLACEHOLDER = "<freshness not compared>"

# The freshness verdicts the generator can emit for a `sim/` row. Anchoring the
# substitutions on this closed set matters: a freshness cell holding anything
# else is NOT normalised, so a malformed/hand-edited committed report surfaces
# as drift instead of being silently accepted.
#
# `ERROR` (an unrecognized record shape, #215/#218) belongs here too: it is
# only ever reachable on the PDK path -- the same record reads `unverified` on
# a machine without the toolchain -- so leaving it out would make the headless
# check fail on a tree whose committed report is perfectly current.
_FRESHNESS_TOKENS = r"(?:fresh|STALE|unverified|ERROR)"

# `| ... | <verdict> |` -- the last cell of a per-spec-row table line. N/A rows
# carry an em dash there and are deliberately left alone (a row losing its
# evidence is drift, not a freshness change).
_TABLE_FRESHNESS_RE = re.compile(rf"^(\|[^\n]*\| ){_FRESHNESS_TOKENS}( \|)$", re.MULTILINE)

# `Freshness: <prose>.` inside an Evidence-detail bullet. The bullet may
# continue after that sentence ("Failing measurement(s)...", "**PVT subset..."),
# so the match ends at the first period that is followed by end-of-line or one
# of those continuations -- never at a period *inside* the freshness prose
# (a PDK error string can contain one).
_DETAIL_FRESHNESS_RE = re.compile(
    rf"(Freshness: ){_FRESHNESS_TOKENS}.*?\.(?=$| Failing measurement\(s\)| \*\*PVT subset)",
    re.MULTILINE,
)


def normalize_sim_freshness(text: str) -> str:
    """Replace every per-`sim/`-row freshness verdict with a fixed placeholder.

    Only the region *above* `LAYOUT_SECTION_HEADING` is touched: that is where
    the PDK-dependent verdicts live. The layout (DRC/LVS/PEX) section's own
    Freshness column is derived from git history and the `LATEST*` pointers --
    no toolchain required, identical on every machine -- so it stays compared
    verbatim and keeps protecting against layout-evidence drift.

    Raises if the boundary heading is absent: without it this function cannot
    tell the two kinds of freshness apart, and normalising the whole document
    would silently stop checking the layout column too.
    """
    idx = text.find(LAYOUT_SECTION_HEADING)
    if idx == -1:
        raise RuntimeError(
            f"cannot scope the freshness normalisation: heading "
            f"{LAYOUT_SECTION_HEADING!r} not found in the report text"
        )
    head, tail = text[:idx], text[idx:]
    head = _TABLE_FRESHNESS_RE.sub(rf"\g<1>{FRESHNESS_PLACEHOLDER}\g<2>", head)
    head = _DETAIL_FRESHNESS_RE.sub(rf"\g<1>{FRESHNESS_PLACEHOLDER}.", head)
    return head + tail


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"path to write (or, with --check, compare against); default {DEFAULT_OUT}",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify --out matches a fresh run instead of writing it; exit 1 if stale/missing",
    )
    parser.add_argument(
        "--no-netlist-freshness",
        action="store_true",
        help="skip the xschem-based sim/ netlist freshness re-check (reports 'unverified' "
        "instead) -- for machines without the PDK toolchain",
    )
    parser.add_argument(
        "--ignore-sim-freshness",
        action="store_true",
        help="with --check: compare everything EXCEPT the per-sim/ Freshness column "
        "(which only a PDK-equipped machine can evaluate). Implies "
        "--no-netlist-freshness. This is the mode CI runs on every push/PR.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="print the generated report to stdout instead of writing --out",
    )
    args = parser.parse_args(argv)
    if args.ignore_sim_freshness and not args.check:
        # Writing a report whose freshness column is a placeholder would commit
        # a rollup that states nothing about freshness -- exactly the false
        # artifact this mode exists to avoid. It is a comparison mode only.
        parser.error("--ignore-sim-freshness is only meaningful together with --check")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    skip_netlist_freshness = args.no_netlist_freshness or args.ignore_sim_freshness
    report = generate_report(skip_netlist_freshness=skip_netlist_freshness)

    if EVIDENCE_ERRORS:
        for err in EVIDENCE_ERRORS:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    if args.check:
        if not args.out.is_file():
            print(f"FAIL: {args.out} does not exist -- run without --check to generate it.", file=sys.stderr)
            return 1
        committed = args.out.read_text()
        expected, actual = committed, report
        if args.ignore_sim_freshness:
            expected, actual = normalize_sim_freshness(expected), normalize_sim_freshness(actual)
        if expected != actual:
            scope = (
                " (per-`sim/` Freshness column not compared: --ignore-sim-freshness)"
                if args.ignore_sim_freshness
                else ""
            )
            print(
                f"FAIL: {args.out} is stale relative to a fresh run of this generator{scope}.",
                file=sys.stderr,
            )
            print("Regenerate with:", file=sys.stderr)
            print(
                f"  python3 {Path(__file__).relative_to(REPO_ROOT)} --out {args.out}",
                file=sys.stderr,
            )
            if args.ignore_sim_freshness:
                print(
                    "  (run that on a machine with the pinned sky130 PDK toolchain, so the "
                    "Freshness column is evaluated rather than degraded to 'unverified')",
                    file=sys.stderr,
                )
            diff = difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile=str(args.out),
                tofile="freshly generated",
            )
            sys.stderr.writelines(list(diff)[:200])
            return 1
        if args.ignore_sim_freshness:
            print(
                f"OK: {args.out} matches a fresh run, except the per-`sim/` Freshness "
                "column, which was not compared (--ignore-sim-freshness)."
            )
        else:
            print(f"OK: {args.out} matches a fresh run.")
        return 0

    if args.stdout:
        sys.stdout.write(report)
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
