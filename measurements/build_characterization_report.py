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
- **DRAFT guardrail.** `spec/target-spec.md` is not yet ratified (issue #1
  open) -- every verdict below is stated explicitly as "vs the current DRAFT
  spec", never as a final ratified-compliance claim (see #19's own record for
  the same convention).
- **N/A, not a fabricated PASS/FAIL.** A spec row with no independent
  testbench (e.g. Input, Load -- exercised as stimulus conditions inside
  other rows' testbenches, not measured by one of their own) is reported
  N/A with a stated reason, never forced into a PASS/FAIL slot it has no
  evidence for.
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
"""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

MEASUREMENTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = MEASUREMENTS_DIR.parent
SIM_DIR = REPO_ROOT / "sim"
LAYOUT_DIR = REPO_ROOT / "layout"
SPEC_FILE = REPO_ROOT / "spec" / "target-spec.md"
SCHEMATIC_FILE = "design/ldo_3v3in_1v8out.sch"
DEFAULT_OUT = MEASUREMENTS_DIR / "characterization.md"

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
    "Line regulation": None,
    "Load regulation (0–50 mA)": None,
    "Load transient": "load-transient",
    "PSRR": "psrr-dc",
    "Iq (excl. load current)": None,
    "Current limit": None,
    "Startup / soft-start": None,
    "Enable / shutdown": None,
    "Thermal": None,
    "Output noise": None,
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
    "Line regulation": (
        "no dedicated testbench exists yet under `sim/` (see `sim/README.md`'s "
        "testbench map)."
    ),
    "Load regulation (0–50 mA)": (
        "no dedicated testbench exists yet under `sim/` (see `sim/README.md`'s "
        "testbench map)."
    ),
    "Iq (excl. load current)": "no dedicated testbench exists yet under `sim/`.",
    "Current limit": (
        "the current-limit clamp circuitry (issue #22) is present in the "
        "schematic, but no dedicated clamp-threshold testbench exists yet "
        "under `sim/`."
    ),
    "Startup / soft-start": (
        "the soft-start circuitry (issue #22) is present in the schematic, "
        "but no dedicated startup-transient testbench exists yet under `sim/`."
    ),
    "Enable / shutdown": "no dedicated testbench exists yet under `sim/`.",
    "Thermal": (
        "the thermal-shutdown circuitry (issue #35) is present in the "
        "schematic, but no dedicated thermal testbench exists yet under "
        "`sim/`."
    ),
    "Output noise": (
        'waived by the spec row itself ("not specified — waived unless a '
        'consumer states a requirement").'
    ),
    "Area": (
        "no dedicated area-extraction check exists yet; the routed layout's "
        "own geometry is not re-derived into a verdict here, per this "
        "report's own no-re-derivation rule."
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


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def load_corner_run_module():
    """Import sim/bin/corner-run.py by path (its filename has a hyphen, so it
    can't be `import`ed directly) -- same trick `sim/bin/mc-run.py` already
    uses, reused here purely for its xschem-netlisting + PDK-resolution
    helpers (`netlist_with_xschem`, `netlist_body`, `resolve_pdk`,
    `load_pin`). Read-only reuse: this script never calls anything that
    writes evidence."""
    bin_dir = str(SIM_DIR / "bin")
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)  # corner-run.py does `from _record_common import ...`
    spec = importlib.util.spec_from_file_location(
        "corner_run", SIM_DIR / "bin" / "corner-run.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["corner_run"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


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


def latest_sim_record(slug: str) -> tuple[dict, Path] | None:
    records_dir = SIM_DIR / slug / "records"
    if not records_dir.is_dir():
        return None
    json_files = sorted(records_dir.glob("*.json"))
    if not json_files:
        return None
    latest = json_files[-1]
    data = json.loads(latest.read_text())
    return data, latest.with_suffix(".md")


def sim_corner_tally(record: dict) -> str | None:
    corners = record.get("corners")
    if isinstance(corners, list) and corners:
        passed = sum(1 for c in corners if c.get("pass"))
        return f"{passed}/{len(corners)} corner(s) PASS"
    return None


def sim_mc_sample_tally(record: dict) -> str | None:
    resp = record.get("klt_response")
    if not isinstance(resp, dict):
        return None
    corners = resp.get("corners")
    if not isinstance(corners, list) or not corners:
        return None
    passed = sum(1 for c in corners if c.get("status") == "pass")
    return f"{passed}/{len(corners)} individual sample(s) PASS"


def check_netlist_freshness(module, pdk, slug: str, record: dict) -> str:
    provenance_source = record["experiment"]["provenance_source"]
    snapshot_rel = record["links"]["netlist_snapshot"]
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
    return git("log", "-1", "--format=%h", "--", SCHEMATIC_FILE)


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


def check_pex_layout_freshness(record_text: str) -> str:
    m = LAYOUT_RECORD_RE.search(record_text)
    if not m:
        return "unverified: no 'Layout record' line found in the record"
    cited = m.group(1).rsplit("/", 1)[-1]
    current = read_pointer(LAYOUT_DIR / "ldo-core" / "reports" / "LATEST-LVS")
    if current is None:
        return "unverified: layout/ldo-core/reports/LATEST-LVS pointer is missing"
    if cited == current:
        return f"fresh (cites the current `LATEST-LVS` record `{cited}`)"
    return f"STALE (cites LVS record `{cited}`; `LATEST-LVS` now points to `{current}`)"


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


def build_spec_row_table(
    spec_rows: list[dict], skip_netlist_freshness: bool
) -> tuple[list[str], list[str]]:
    """Returns (table_lines, detail_lines)."""
    module = None
    pdk = None
    if not skip_netlist_freshness:
        try:
            module = load_corner_run_module()
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
        "| Parameter | DRAFT target (starting point) | Verdict (vs DRAFT) | Evidence | Freshness |",
        "|---|---|---|---|---|",
    ]
    detail: list[str] = []

    for row in spec_rows:
        param = row["parameter"]
        slug = EVIDENCE_MAP.get(param)
        if slug is None:
            reason = NA_REASONS.get(param, GENERIC_NA_REASON)
            table.append(f"| {param} | {row['draft_target']} | N/A | — | — |")
            detail.append(f"- **{param}**: N/A — {reason}")
            continue

        found = latest_sim_record(slug)
        if found is None:
            table.append(
                f"| {param} | {row['draft_target']} | **ERROR** | no record found under "
                f"`sim/{slug}/records/` | — |"
            )
            detail.append(
                f"- **{param}**: ERROR — `EVIDENCE_MAP` cites `sim/{slug}`, but no record "
                f"exists there. This is a report/mapping bug, not an N/A row."
            )
            continue

        record, md_path = found
        verdict = "PASS" if record.get("overall_pass") else "FAIL"
        record_id = record.get("record_id", "?")
        record_rel = rel(md_path)
        tally = sim_corner_tally(record) or sim_mc_sample_tally(record) or "n/a"

        if module is not None and pdk is not None:
            freshness = check_netlist_freshness(module, pdk, slug, record)
        elif skip_netlist_freshness:
            freshness = "unverified: --no-netlist-freshness passed"
        else:
            freshness = f"unverified: PDK/toolchain unavailable ({_pdk_error})"

        freshness_short = "fresh" if freshness.startswith("fresh") else (
            "STALE" if freshness.startswith("STALE") else "unverified"
        )

        table.append(
            f"| {param} | {row['draft_target']} | **{verdict}** | "
            f"[`{record_id}`]({record_rel}) | {freshness_short} |"
        )
        detail.append(
            f"- **{param}**: **{verdict}** (vs the current DRAFT spec row) — "
            f"`sim/{slug}` record [`{record_id}`]({record_rel}), {tally}. "
            f"Freshness: {freshness}."
        )

    return table, detail


def build_layout_section() -> list[str]:
    lines: list[str] = []
    lines.append("| Check | Verdict (record's own) | Record | Freshness |")
    lines.append("|---|---|---|---|")

    drc = layout_record("LATEST")
    if drc is not None:
        record_id, d = drc
        record_text = (d / "record.md").read_text() if (d / "record.md").is_file() else ""
        verdict = extract_overall_verdict_md(record_text) or "?"
        drc_json_path = d / "drc.json"
        detail = ""
        if drc_json_path.is_file():
            drc_json = json.loads(drc_json_path.read_text())
            detail = f"status={drc_json.get('status')}, violation_count={drc_json.get('violation_count')}"
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
            check_schematic_freshness_from_record(record_text) if record_text else "unverified"
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
        lines.append(f"Post-layout PEX detail: {detail}")
    else:
        lines.append(
            "| Post-layout PEX (issue #20) | **ERROR** | no `sim/pex-post-layout/records/` record | — |"
        )

    return lines


def generate_report(skip_netlist_freshness: bool = False) -> str:
    spec_text = SPEC_FILE.read_text()
    spec_rows = parse_spec_rows(spec_text)
    table, detail = build_spec_row_table(spec_rows, skip_netlist_freshness)
    layout_lines = build_layout_section()

    lines: list[str] = []
    lines.append("# LDO characterization report (DRAFT spec)")
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
        "**This is not a final compliance claim.** `spec/target-spec.md` is "
        "still DRAFT — nothing in it is ratified (issue #1 open). Every "
        "verdict below is stated explicitly as *against the current DRAFT "
        "row*, per the same guardrail issue #19's own records already use. "
        "A `PASS`/`FAIL`/`MATCH`/`clean` value here is read verbatim from the "
        "cited record's own stated result — this script never recomputes a "
        "verdict from raw measurements (see the module docstring in "
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
        "explicitly). The layout (DRC/LVS/PEX) **Freshness** column instead "
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

    lines.append("## Layout verification (not itself a spec row)")
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
        "- **DRAFT spec.** Every verdict above is against `spec/target-spec.md`'s "
        "current DRAFT row, not a ratified target. Re-verification is required "
        "once issue #1 (spec ratification) and the open decision records "
        "(`spec/decision-records/`) resolve."
    )
    lines.append(
        "- **N/A rows are a coverage gap, not a pass.** A row marked N/A above "
        "has no independent testbench yet — it is neither substantiated nor "
        "refuted by this report."
    )
    lines.append(
        "- **Freshness checks trust the tree, not the working copy.** The "
        "schematic-freshness check (layout section) compares against git "
        "history, so uncommitted local edits to "
        f"`{SCHEMATIC_FILE}` will not be detected as stale until committed."
    )
    lines.append(
        "- **Post-layout PEX (issue #20) has no single PASS/FAIL** — see "
        "`sim/pex-post-layout/README.md` for the three disclosed, real "
        "upstream `klt`/PDK-model-interaction gaps that currently bound the "
        "extracted-side leg."
    )
    lines.append("")

    return "\n".join(lines) + "\n"


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
        "--stdout",
        action="store_true",
        help="print the generated report to stdout instead of writing --out",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    report = generate_report(skip_netlist_freshness=args.no_netlist_freshness)

    if args.check:
        if not args.out.is_file():
            print(f"FAIL: {args.out} does not exist -- run without --check to generate it.", file=sys.stderr)
            return 1
        committed = args.out.read_text()
        if committed != report:
            print(
                f"FAIL: {args.out} is stale relative to a fresh run of this generator.",
                file=sys.stderr,
            )
            print("Regenerate with:", file=sys.stderr)
            print(
                f"  python3 {Path(__file__).relative_to(REPO_ROOT)} --out {args.out}",
                file=sys.stderr,
            )
            diff = difflib.unified_diff(
                committed.splitlines(keepends=True),
                report.splitlines(keepends=True),
                fromfile=str(args.out),
                tofile="freshly generated",
            )
            sys.stderr.writelines(list(diff)[:200])
            return 1
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
