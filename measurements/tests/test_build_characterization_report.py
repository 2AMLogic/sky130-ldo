"""Unit coverage for measurements/build_characterization_report.py.

PDK-free by design (no ngspice/xschem/volare required) so this runs on every
`npm run check:ci` invocation, including in CI where the sky130 PDK is not
installed -- same convention as `sim/tests/test_corner_run.py`.

Three things are covered here:

1. the pure parsing/extraction/freshness helpers (the parts that decide what
   verdict text ends up in the report), exercised against fixture strings
   rather than the live tree, so a record landing under `sim/` never silently
   changes what these assertions mean;
2. the **no self-referential provenance** invariant (PR #49 review): the
   generated report must not embed the identity of the commit that generates
   it, because a commit cannot contain its own resulting sha -- a report that
   did would make `--check` fail by construction on the very commit that
   ships it; and
3. the **PDK-free structural check** `--check --ignore-sim-freshness` (#220),
   which is what gates the committed rollup on every push/PR. The risk there
   is not that it fails -- it is that it normalises too much and passes
   vacuously, so most of that coverage asserts what it must still *catch*.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

MEASUREMENTS_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "build_characterization_report",
    MEASUREMENTS_DIR / "build_characterization_report.py",
)
bcr = importlib.util.module_from_spec(_spec)
sys.modules["build_characterization_report"] = bcr
_spec.loader.exec_module(bcr)


SPEC_FIXTURE = """# Target spec (DRAFT)

Some prose that mentions a | pipe | but is not the table.

| Parameter | DRAFT target | DRAFT stretch | Source | Notes |
|---|---|---|---|---|
| Input | 3.0-3.6 V | — | port parity | stimulus condition |
| Output | 1.80 V ±2% | ±1% | port parity | measured by mc-output-accuracy |
| Load regulation (0–50 mA) | < 10 mV | < 5 mV | port parity | en-dash in the name |

Trailing prose after the table.
"""


class TestParseSpecRows(unittest.TestCase):
    def test_parses_every_data_row(self):
        rows = bcr.parse_spec_rows(SPEC_FIXTURE)
        self.assertEqual(
            [r["parameter"] for r in rows],
            ["Input", "Output", "Load regulation (0–50 mA)"],
        )

    def test_preserves_columns_verbatim(self):
        rows = bcr.parse_spec_rows(SPEC_FIXTURE)
        self.assertEqual(rows[1]["draft_target"], "1.80 V ±2%")
        self.assertEqual(rows[1]["draft_stretch"], "±1%")
        self.assertEqual(rows[1]["src"], "port parity")
        self.assertEqual(rows[1]["note"], "measured by mc-output-accuracy")

    def test_stops_at_end_of_table(self):
        rows = bcr.parse_spec_rows(SPEC_FIXTURE)
        self.assertEqual(len(rows), 3)

    def test_raises_when_no_table_header(self):
        with self.assertRaises(RuntimeError):
            bcr.parse_spec_rows("# no table here\n\njust prose\n")

    def test_raises_when_header_has_no_data_rows(self):
        with self.assertRaises(RuntimeError):
            bcr.parse_spec_rows("| Parameter | a | b | c | d |\n|---|---|---|---|---|\n")

    def test_live_spec_rows_are_all_covered_by_evidence_map(self):
        """Guards the report against silently emitting a generic N/A for a spec
        row someone added without updating EVIDENCE_MAP."""
        rows = bcr.parse_spec_rows(bcr.SPEC_FILE.read_text())
        missing = [r["parameter"] for r in rows if r["parameter"] not in bcr.EVIDENCE_MAP]
        self.assertEqual(missing, [], f"spec rows absent from EVIDENCE_MAP: {missing}")


class TestLatestSimRecord(unittest.TestCase):
    """Issue #215: `latest_sim_record` must select the latest *campaign*
    record under a slug's `records/` directory, never a derived record kind
    (e.g. a `klt yield` record, issue #203) sharing that same directory --
    even when the derived record's filename sorts after every campaign
    record's, which is exactly the original bug's trigger condition."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._orig_sim_dir = bcr.SIM_DIR
        bcr.SIM_DIR = Path(self._tmpdir.name)

    def tearDown(self):
        bcr.SIM_DIR = self._orig_sim_dir

    def _write_record(self, slug: str, record_id: str, data: dict) -> None:
        records_dir = bcr.SIM_DIR / slug / "records"
        records_dir.mkdir(parents=True, exist_ok=True)
        (records_dir / f"{record_id}.json").write_text(json.dumps(data))
        (records_dir / f"{record_id}.md").write_text(f"# {record_id}\n")

    def test_skips_a_later_yield_record_and_selects_the_campaign_record(self):
        self._write_record(
            "mixed-slug",
            "20260101-000000-campaign",
            {"record_id": "20260101-000000-campaign", "overall_pass": True},
        )
        # Filename sorts *after* the campaign record above -- the exact
        # condition that made the lexicographically-newest-file heuristic
        # pick a yield record instead (issue #215).
        self._write_record(
            "mixed-slug",
            "20260202-000000-yieldrec",
            {"record_id": "20260202-000000-yieldrec", "evidence_kind": "yield"},
        )
        found = bcr.latest_sim_record("mixed-slug")
        self.assertIsNotNone(found)
        data, _md_path = found
        self.assertEqual(data["record_id"], "20260101-000000-campaign")

    def test_returns_none_when_only_non_campaign_records_exist(self):
        self._write_record(
            "yield-only-slug",
            "20260101-000000-yieldrec",
            {"record_id": "20260101-000000-yieldrec", "evidence_kind": "yield"},
        )
        self.assertIsNone(bcr.latest_sim_record("yield-only-slug"))

    def test_still_picks_the_newest_among_multiple_campaign_records(self):
        self._write_record(
            "campaign-only-slug",
            "20260101-000000-first",
            {"record_id": "20260101-000000-first", "overall_pass": False},
        )
        self._write_record(
            "campaign-only-slug",
            "20260202-000000-second",
            {"record_id": "20260202-000000-second", "overall_pass": True},
        )
        data, _md_path = bcr.latest_sim_record("campaign-only-slug")
        self.assertEqual(data["record_id"], "20260202-000000-second")

    def test_missing_records_dir_returns_none(self):
        self.assertIsNone(bcr.latest_sim_record("no-such-slug"))


class TestCheckNetlistFreshnessTolerance(unittest.TestCase):
    """Issue #215 (option 3): a record shape this checker doesn't recognize
    (e.g. missing `links.netlist_snapshot`) must produce a diagnosed error
    string naming the offending record, not a raw KeyError traceback --
    this script's whole job is to report evidence state."""

    def test_missing_links_key_is_diagnosed_not_raised(self):
        record = {"record_id": "some-record", "experiment": {"provenance_source": "x"}}
        out = bcr.check_netlist_freshness(None, None, "some-slug", record)
        self.assertTrue(out.startswith("ERROR"), out)
        self.assertIn("some-record", out)
        self.assertIn("some-slug", out)


class TestSimTallies(unittest.TestCase):
    def test_corner_tally(self):
        rec = {"corners": [{"pass": True}, {"pass": False}, {"pass": True}]}
        self.assertEqual(bcr.sim_corner_tally(rec), "2/3 corner(s) PASS")

    def test_corner_tally_absent(self):
        self.assertIsNone(bcr.sim_corner_tally({}))
        self.assertIsNone(bcr.sim_corner_tally({"corners": []}))

    def test_mc_sample_tally(self):
        rec = {"klt_response": {"corners": [{"status": "pass"}, {"status": "fail"}]}}
        self.assertEqual(bcr.sim_mc_sample_tally(rec), "1/2 individual sample(s) PASS")

    def test_mc_sample_tally_absent(self):
        self.assertIsNone(bcr.sim_mc_sample_tally({}))
        self.assertIsNone(bcr.sim_mc_sample_tally({"klt_response": {"corners": []}}))


class TestFailingMeasurements(unittest.TestCase):
    """A row-level FAIL must say which bounded measurement failed (issue
    #120: a Thermal FAIL was misread as a theta-JA question when every failing
    corner had failed only the hysteresis-sign bound)."""

    def test_all_pass_reports_nothing(self):
        rec = {"corners": [{"pass": True, "measurements": [{"name": "a", "pass": True}]}]}
        self.assertIsNone(bcr.sim_failing_measurements(rec))

    def test_absent_corner_list_reports_nothing(self):
        self.assertIsNone(bcr.sim_failing_measurements({}))
        self.assertIsNone(bcr.sim_failing_measurements({"corners": []}))

    def test_counts_failing_measurements_per_name_in_record_order(self):
        rec = {
            "corners": [
                {"pass": True, "measurements": [{"name": "trip", "pass": True}]},
                {
                    "pass": False,
                    "measurements": [
                        {"name": "trip", "pass": True},
                        {"name": "hyst", "pass": False},
                    ],
                },
                {
                    "pass": False,
                    "measurements": [
                        {"name": "trip", "pass": False},
                        {"name": "hyst", "pass": False},
                    ],
                },
            ]
        }
        self.assertEqual(
            bcr.sim_failing_measurements(rec),
            "`hyst` at 2 corner(s); `trip` at 1 corner(s)",
        )

    def test_failing_corner_without_flagged_measurement_is_not_guessed(self):
        rec = {"corners": [{"pass": False, "measurements": [{"name": "a", "pass": True}]}]}
        self.assertEqual(
            bcr.sim_failing_measurements(rec),
            "1 corner(s) with no measurement flagged (run-level failure)",
        )


class TestSubsetReason(unittest.TestCase):
    """A verdict extracted from a PVT subset must be labelled as one: "3/3
    corner(s) PASS" from a 3-point subset otherwise reads exactly like
    full-matrix coverage next to a row citing 45 corners (issue #65)."""

    def test_full_matrix_record_has_no_subset_reason(self):
        self.assertIsNone(bcr.sim_subset_reason({"matrix": {"is_subset": False}}))

    def test_record_without_a_matrix_block_is_not_flagged(self):
        self.assertIsNone(bcr.sim_subset_reason({}))
        self.assertIsNone(bcr.sim_subset_reason({"matrix": None}))

    def test_subset_record_returns_its_own_stated_reason(self):
        rec = {"matrix": {"is_subset": True, "subset_reason": "3-point bring-up subset"}}
        self.assertEqual(bcr.sim_subset_reason(rec), "3-point bring-up subset")

    def test_subset_without_a_reason_is_still_flagged(self):
        """The runner will not write one, but the report must not silently
        drop the subset marker if a record somehow lacks the reason text."""
        rec = {"matrix": {"is_subset": True, "subset_reason": ""}}
        self.assertEqual(bcr.sim_subset_reason(rec), "(the record states no reason)")


class TestVerdictExtraction(unittest.TestCase):
    def test_overall_verdict_md(self):
        text = "# record\n\nprose\n\n## Overall verdict: PASS (0 violations)\n\nmore\n"
        self.assertEqual(bcr.extract_overall_verdict_md(text), "PASS (0 violations)")

    def test_overall_verdict_md_missing(self):
        self.assertIsNone(bcr.extract_overall_verdict_md("no verdict line here"))

    def test_pex_results_are_grouped_by_heading(self):
        text = (
            "## Schematic-side\n"
            "- Result: PASS\n"
            "\n"
            "## Extracted-side\n"
            "- Result: BLOCKED (upstream gap)\n"
        )
        self.assertEqual(
            bcr.extract_pex_results(text),
            [("Schematic-side", "PASS"), ("Extracted-side", "BLOCKED (upstream gap)")],
        )

    def test_pex_result_before_any_heading_is_ignored(self):
        self.assertEqual(bcr.extract_pex_results("- Result: PASS\n"), [])


class TestSchematicFreshness(unittest.TestCase):
    def setUp(self):
        self._orig = bcr.current_schematic_sha

    def tearDown(self):
        bcr.current_schematic_sha = self._orig

    def test_fresh_when_record_cites_current_commit(self):
        bcr.current_schematic_sha = lambda: "d0b244d"
        out = bcr.check_schematic_freshness_from_record(
            "Schematic freshness: netlisted from commit `d0b244d`\n"
        )
        self.assertTrue(out.startswith("fresh"), out)

    def test_stale_when_schematic_has_moved(self):
        bcr.current_schematic_sha = lambda: "81dc232"
        out = bcr.check_schematic_freshness_from_record(
            "Schematic freshness: netlisted from commit `d0b244d`\n"
        )
        self.assertTrue(out.startswith("STALE"), out)
        self.assertIn("81dc232", out)

    def test_differing_abbreviation_lengths_still_match(self):
        bcr.current_schematic_sha = lambda: "d0b244d"
        out = bcr.check_schematic_freshness_from_record(
            "Schematic freshness: netlisted from commit `d0b244dab12`\n"
        )
        self.assertTrue(out.startswith("fresh"), out)

    def test_unverified_when_record_has_no_freshness_line(self):
        bcr.current_schematic_sha = lambda: "d0b244d"
        self.assertTrue(
            bcr.check_schematic_freshness_from_record("no such line").startswith("unverified")
        )

    def test_unverified_when_git_unavailable(self):
        bcr.current_schematic_sha = lambda: ""
        out = bcr.check_schematic_freshness_from_record(
            "Schematic freshness: netlisted from commit `d0b244d`\n"
        )
        self.assertTrue(out.startswith("unverified"), out)


class TestPexLayoutFreshness(unittest.TestCase):
    def setUp(self):
        self._orig = bcr.read_pointer

    def tearDown(self):
        bcr.read_pointer = self._orig

    def test_fresh_when_cited_record_is_latest(self):
        bcr.read_pointer = lambda _p: "20260101-000000-lvs"
        out = bcr.check_pex_layout_freshness(
            "**Layout record**: `layout/ldo-core/reports/20260101-000000-lvs`\n"
        )
        self.assertTrue(out.startswith("fresh"), out)

    def test_stale_when_latest_pointer_has_moved(self):
        bcr.read_pointer = lambda _p: "20260202-000000-lvs"
        out = bcr.check_pex_layout_freshness(
            "**Layout record**: `layout/ldo-core/reports/20260101-000000-lvs`\n"
        )
        self.assertTrue(out.startswith("STALE"), out)

    def test_unverified_when_pointer_missing(self):
        bcr.read_pointer = lambda _p: None
        out = bcr.check_pex_layout_freshness(
            "**Layout record**: `layout/ldo-core/reports/20260101-000000-lvs`\n"
        )
        self.assertTrue(out.startswith("unverified"), out)

    def test_unverified_when_record_has_no_layout_record_line(self):
        self.assertTrue(bcr.check_pex_layout_freshness("nothing").startswith("unverified"))


class TestNoSelfReferentialProvenance(unittest.TestCase):
    """PR #49 review: the generated report must not embed the identity of the
    commit that generates it, or `--check` fails by construction on the commit
    that ships the regenerated file."""

    def setUp(self):
        self._orig_git = bcr.git
        self.calls: list[tuple[str, ...]] = []

        def recording_git(*args: str) -> str:
            self.calls.append(args)
            return self._orig_git(*args)

        bcr.git = recording_git

    def tearDown(self):
        bcr.git = self._orig_git

    def test_generator_never_asks_git_for_head_or_worktree_state(self):
        bcr.generate_report(skip_netlist_freshness=True)
        self.assertNotEqual(self.calls, [], "expected the generator to consult git at all")
        for args in self.calls:
            self.assertNotIn(
                "HEAD", args, f"generator resolved repo HEAD (self-referential): git {args}"
            )
            self.assertNotEqual(
                args[:1], ("status",), f"generator inspected worktree dirtiness: git {args}"
            )

    def test_report_does_not_name_the_generating_commit(self):
        report = bcr.generate_report(skip_netlist_freshness=True)
        self.assertNotIn("Generated against repo state", report)
        self.assertNotIn("working tree dirty at generation time", report)

    def test_report_is_reproducible_within_a_run(self):
        self.assertEqual(
            bcr.generate_report(skip_netlist_freshness=True),
            bcr.generate_report(skip_netlist_freshness=True),
        )


def _report_fixture(
    *,
    sim_freshness: str = "fresh",
    sim_freshness_prose: str = "fresh (a live xschem re-netlist of the current testbench "
    "schematic matches the committed netlist snapshot verbatim)",
    record_id: str = "20260101-000000-aaaaaaa",
    verdict: str = "**PASS**",
    tally: str = "45/45 corner(s) PASS",
    layout_freshness: str = "fresh",
) -> str:
    """A miniature report with the same shape the generator emits, so the
    normaliser is exercised against structure rather than against whatever
    happens to be committed today."""
    return f"""# LDO characterization report (against the ratified spec)

Prose that mentions `--check` and the Freshness column in passing.

## Per-spec-row characterization

| Parameter | Ratified target | Verdict (vs ratified target) | Evidence | Freshness |
|---|---|---|---|---|
| Input | 3.3 V ±10% | N/A | — | — |
| Dropout @ 50 mA | < 300 mV | {verdict} | [`{record_id}`](../sim/dropout-vs-load/records/{record_id}.md) | {sim_freshness} |
| Iq (excl. load current) | < 30 µA | **FAIL** (PVT subset) | [`20260102-000000-bbbbbbb`](../sim/iq/records/20260102-000000-bbbbbbb.md) | STALE |
| Thermal | Tj ≤ 125 °C | **PASS** | [`20260103-000000-ccccccc`](../sim/thermal/records/20260103-000000-ccccccc.md) | unverified |

### Evidence detail

- **Input**: N/A — exercised as a stimulus condition inside every PVT testbench below.
- **Dropout @ 50 mA**: {verdict} (vs the ratified spec row) — `sim/dropout-vs-load` record [`{record_id}`](../sim/dropout-vs-load/records/{record_id}.md), {tally}. Freshness: {sim_freshness_prose}.
- **Iq (excl. load current)**: **FAIL** (vs the ratified spec row) — `sim/iq` record [`20260102-000000-bbbbbbb`](../sim/iq/records/20260102-000000-bbbbbbb.md), 36/45 corner(s) PASS. Freshness: STALE (a live xschem re-netlist of the current testbench schematic no longer matches the committed netlist snapshot). Failing measurement(s), per the record: `iq_full_load_ua` at 9 corner(s). **PVT subset, not the full matrix this experiment declares** — the record's own stated reason: 3-point bring-up subset
- **Thermal**: **PASS** (vs the ratified spec row) — `sim/thermal` record [`20260103-000000-ccccccc`](../sim/thermal/records/20260103-000000-ccccccc.md), 15/15 corner(s) PASS. Freshness: unverified: PDK/toolchain unavailable (no PDK at /nope/sky130A. install it with: volare fetch).

{bcr.LAYOUT_SECTION_HEADING}

| Check | Verdict (record's own) | Record | Freshness |
|---|---|---|---|
| DRC (issue #16) | **PASS** (status=clean, violation_count=0) | [`20260104-000000-ddddddd`](../layout/ldo-core/reports/20260104-000000-ddddddd/record.md) | {layout_freshness} |

## Limitations

- Prose.
"""


class TestNormalizeSimFreshness(unittest.TestCase):
    """Issue #220. The per-`sim/` Freshness column is produced by a live xschem
    re-netlist, so it is the one part of this report a PDK-less runner cannot
    reproduce. `--check --ignore-sim-freshness` normalises exactly that much --
    and the assertions below are mostly about what it must still catch, since
    a normaliser that ate too much would pass vacuously and reinstate the #215
    blind spot this gate exists to close."""

    def test_normalizes_every_sim_freshness_token_in_the_table(self):
        out = bcr.normalize_sim_freshness(_report_fixture())
        header, _, body = out.partition(bcr.LAYOUT_SECTION_HEADING)
        for token in ("| fresh |", "| STALE |", "| unverified |"):
            self.assertNotIn(token, header, f"{token} survived normalisation")
        self.assertEqual(header.count(f"| {bcr.FRESHNESS_PLACEHOLDER} |"), 3)

    def test_leaves_na_rows_em_dash_alone(self):
        """A row losing its evidence is drift, not a freshness change."""
        out = bcr.normalize_sim_freshness(_report_fixture())
        self.assertIn("| Input | 3.3 V ±10% | N/A | — | — |", out)

    def test_normalizes_the_freshness_clause_of_every_detail_bullet(self):
        out = bcr.normalize_sim_freshness(_report_fixture())
        self.assertNotIn("Freshness: fresh", out)
        self.assertNotIn("Freshness: STALE", out)
        self.assertNotIn("Freshness: unverified", out)
        self.assertEqual(out.count(f"Freshness: {bcr.FRESHNESS_PLACEHOLDER}."), 3)

    def test_detail_bullet_text_after_the_freshness_clause_survives(self):
        """The clause ends at its own sentence -- the failing-measurement list
        and the `(PVT subset)` reason after it are real evidence and must stay
        compared."""
        out = bcr.normalize_sim_freshness(_report_fixture())
        self.assertIn(
            "Failing measurement(s), per the record: `iq_full_load_ua` at 9 corner(s).", out
        )
        self.assertIn("the record's own stated reason: 3-point bring-up subset", out)

    def test_a_period_inside_the_freshness_prose_does_not_truncate_the_match(self):
        """The `unverified: PDK/toolchain unavailable (...)` text can embed a
        period; stopping there would leave environment-specific residue in the
        'normalised' text and fail on a healthy tree."""
        out = bcr.normalize_sim_freshness(_report_fixture())
        self.assertNotIn("/nope/sky130A", out)
        self.assertNotIn("volare fetch", out)

    def test_error_freshness_is_normalized_too(self):
        """`ERROR` (#215/#218) is reachable only on the PDK path -- the same
        record reads `unverified` without the toolchain."""
        out = bcr.normalize_sim_freshness(
            _report_fixture(
                sim_freshness="ERROR",
                sim_freshness_prose="ERROR: record `x` under sim/y has no 'links'",
            )
        )
        self.assertNotIn("| ERROR |", out)
        self.assertNotIn("Freshness: ERROR", out)

    def test_layout_section_freshness_is_left_verbatim(self):
        """The layout Freshness column compares git history and `LATEST*`
        pointers -- no toolchain -- so it stays gated on every push/PR."""
        out = bcr.normalize_sim_freshness(_report_fixture(layout_freshness="STALE"))
        _, _, layout = out.partition(bcr.LAYOUT_SECTION_HEADING)
        self.assertIn("| STALE |", layout)
        self.assertNotIn(bcr.FRESHNESS_PLACEHOLDER, layout)

    def test_is_idempotent(self):
        once = bcr.normalize_sim_freshness(_report_fixture())
        self.assertEqual(bcr.normalize_sim_freshness(once), once)

    def test_reports_differing_only_in_sim_freshness_compare_equal(self):
        pdk_side = _report_fixture()
        headless_side = _report_fixture(
            sim_freshness="unverified",
            sim_freshness_prose="unverified: --no-netlist-freshness passed",
        )
        self.assertNotEqual(pdk_side, headless_side)
        self.assertEqual(
            bcr.normalize_sim_freshness(pdk_side),
            bcr.normalize_sim_freshness(headless_side),
        )

    def test_does_not_mask_a_drifted_record_id(self):
        self.assertNotEqual(
            bcr.normalize_sim_freshness(_report_fixture()),
            bcr.normalize_sim_freshness(_report_fixture(record_id="20260909-000000-deadbee")),
        )

    def test_does_not_mask_a_drifted_verdict(self):
        self.assertNotEqual(
            bcr.normalize_sim_freshness(_report_fixture()),
            bcr.normalize_sim_freshness(_report_fixture(verdict="**FAIL**")),
        )

    def test_does_not_mask_a_drifted_corner_tally(self):
        self.assertNotEqual(
            bcr.normalize_sim_freshness(_report_fixture()),
            bcr.normalize_sim_freshness(_report_fixture(tally="44/45 corner(s) PASS")),
        )

    def test_does_not_mask_drifted_layout_freshness(self):
        self.assertNotEqual(
            bcr.normalize_sim_freshness(_report_fixture()),
            bcr.normalize_sim_freshness(_report_fixture(layout_freshness="STALE")),
        )

    def test_raises_when_the_section_boundary_is_missing(self):
        """Without the boundary the function cannot tell PDK-dependent
        freshness from git-derived freshness, and normalising the whole
        document would silently stop checking the layout column."""
        with self.assertRaises(RuntimeError):
            bcr.normalize_sim_freshness("# report\n\nno layout heading here\n")

    def test_live_report_is_actually_normalized_somewhere(self):
        """Anti-vacuity: if the report's shape ever changes such that the
        substitutions stop matching, the gate must not quietly become a
        no-op comparison of two un-normalised documents."""
        report = bcr.generate_report(skip_netlist_freshness=True)
        normalized = bcr.normalize_sim_freshness(report)
        self.assertNotEqual(normalized, report)
        self.assertIn(bcr.FRESHNESS_PLACEHOLDER, normalized)


class TestCheckCli(unittest.TestCase):
    """Issue #220: the gate itself, exercised end to end PDK-free -- this is
    what `npm run check:ci` invokes on every push/PR."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.report_path = Path(self._tmpdir.name) / "characterization.md"
        self.report = bcr.generate_report(skip_netlist_freshness=True)

    def _run(self, *argv: str) -> int:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            return bcr.main(list(argv))

    def test_ignore_sim_freshness_requires_check(self):
        """Writing a report whose freshness column is a placeholder would
        commit a rollup that states nothing about freshness."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                bcr.parse_args(["--ignore-sim-freshness"])

    def test_passes_on_a_current_report(self):
        self.report_path.write_text(self.report)
        self.assertEqual(
            self._run("--check", "--ignore-sim-freshness", "--out", str(self.report_path)), 0
        )

    def test_passes_when_only_the_sim_freshness_column_differs(self):
        """The committed file is generated WITH the PDK, so its cells say
        fresh/STALE where a headless run says unverified. That difference is
        the whole reason this mode exists -- it must not fail."""
        pdk_flavoured = self.report.replace(
            "| unverified |", "| fresh |"
        ).replace(
            "Freshness: unverified: --no-netlist-freshness passed",
            "Freshness: fresh (a live xschem re-netlist of the current testbench "
            "schematic matches the committed netlist snapshot verbatim)",
        )
        self.assertNotEqual(pdk_flavoured, self.report)
        self.report_path.write_text(pdk_flavoured)
        self.assertEqual(
            self._run("--check", "--ignore-sim-freshness", "--out", str(self.report_path)), 0
        )

    def test_fails_on_a_drifted_record_id(self):
        """The drift class that went unnoticed for two days in #215."""
        drifted = re.sub(r"\[`(\d{8}-\d{6})-([0-9a-f]{7})`\]", r"[`\1-deadbee`]", self.report, count=1)
        self.assertNotEqual(drifted, self.report)
        self.report_path.write_text(drifted)
        self.assertEqual(
            self._run("--check", "--ignore-sim-freshness", "--out", str(self.report_path)), 1
        )

    def test_fails_on_a_missing_report(self):
        self.assertEqual(
            self._run("--check", "--ignore-sim-freshness", "--out", str(self.report_path)), 1
        )


if __name__ == "__main__":
    unittest.main()
