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
    CITE = "**Layout record**: `layout/ldo-core/reports/20260101-000000-lvs`\n"
    LVS = "Schematic freshness: netlisted from commit `aaa1111`\n"

    def setUp(self):
        self._orig = (bcr.read_pointer, bcr.read_layout_record_text, bcr.current_schematic_sha)
        self._geo = bcr.check_lvs_geometry_freshness
        self.addCleanup(lambda: setattr(bcr, "check_lvs_geometry_freshness", self._geo))
        bcr.check_lvs_geometry_freshness = lambda _d: "fresh (stub)"
        bcr.read_pointer = lambda _p: "20260101-000000-lvs"
        bcr.read_layout_record_text = lambda _i: self.LVS
        bcr.current_schematic_sha = lambda: "aaa1111"

    def tearDown(self):
        (bcr.read_pointer, bcr.read_layout_record_text, bcr.current_schematic_sha) = self._orig

    def test_fresh_when_pointer_matches_and_schematic_current(self):
        out = bcr.check_pex_layout_freshness(self.CITE)
        self.assertTrue(out.startswith("fresh"), out)

    def test_stale_when_pointer_matches_but_schematic_changed(self):
        bcr.current_schematic_sha = lambda: "bbb2222"
        out = bcr.check_pex_layout_freshness(self.CITE)
        self.assertTrue(out.startswith("STALE"), out)

    def test_stale_when_latest_pointer_has_moved(self):
        bcr.read_pointer = lambda _p: "20260202-000000-lvs"
        out = bcr.check_pex_layout_freshness(self.CITE)
        self.assertTrue(out.startswith("STALE"), out)

    def test_not_fresh_when_lvs_record_missing(self):
        bcr.read_layout_record_text = lambda _i: None
        out = bcr.check_pex_layout_freshness(self.CITE)
        self.assertTrue(out.startswith("unverified"), out)

    def test_not_fresh_when_lvs_record_has_no_provenance(self):
        bcr.read_layout_record_text = lambda _i: "no provenance here"
        out = bcr.check_pex_layout_freshness(self.CITE)
        self.assertTrue(out.startswith("unverified"), out)

    def test_not_fresh_when_git_history_unavailable(self):
        bcr.current_schematic_sha = lambda: ""
        out = bcr.check_pex_layout_freshness(self.CITE)
        self.assertTrue(out.startswith("unverified"), out)

    def test_unverified_when_pointer_missing(self):
        bcr.read_pointer = lambda _p: None
        out = bcr.check_pex_layout_freshness(self.CITE)
        self.assertTrue(out.startswith("unverified"), out)

    def test_unverified_when_record_has_no_layout_record_line(self):
        self.assertTrue(bcr.check_pex_layout_freshness("nothing").startswith("unverified"))

    def test_check_stays_active_under_ignore_sim_freshness(self):
        # The layout section is not normalised away by --ignore-sim-freshness.
        bcr.current_schematic_sha = lambda: "bbb2222"
        self.assertTrue(bcr.check_pex_layout_freshness(self.CITE).startswith("STALE"))
        text = "head\n" + bcr.LAYOUT_SECTION_HEADING + "\n| PEX | STALE |\n"
        self.assertIn("| PEX | STALE |", bcr.normalize_sim_freshness(text))


class TestLvsGeometryFreshness(unittest.TestCase):
    """Issue #287: LVS/PEX freshness is also content-based on the routed GDS."""

    SCH = "Schematic freshness: netlisted from commit `aaa1111`\n"
    GDS = b"gds-bytes-A"

    def setUp(self):
        import hashlib

        self.sha = hashlib.sha256(self.GDS).hexdigest()
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        self.reports = root / "layout" / "ldo-core" / "reports"
        self.reports.mkdir(parents=True)
        self._orig = (bcr.LAYOUT_DIR, bcr.current_schematic_sha)
        self.addCleanup(lambda: (setattr(bcr, "LAYOUT_DIR", self._orig[0]),
                                 setattr(bcr, "current_schematic_sha", self._orig[1])))
        bcr.LAYOUT_DIR = root / "layout"
        bcr.current_schematic_sha = lambda: "aaa1111"
        self.lvs = self._record("20260101-000000-lvs", self.GDS, self.sha, lvs=True)
        self._record("20260101-000001-drc", self.GDS)
        (self.reports / "LATEST-LVS").write_text("20260101-000000-lvs\n")
        (self.reports / "LATEST").write_text("20260101-000001-drc\n")
        self.cite = "**Layout record**: `layout/ldo-core/reports/20260101-000000-lvs`\n"

    def _record(self, rid, gds, sha=None, lvs=False):
        import json as _j

        d = self.reports / rid
        d.mkdir()
        (d / "ldo_core.gds").write_bytes(gds)
        if lvs:
            env = {"layout_sha256": sha} if sha is not None else {}
            (d / "lvs.json").write_text(_j.dumps({"environment": env}))
            (d / "record.md").write_text(self.SCH)
        return d

    def test_fresh_when_gds_identical(self):
        self.assertTrue(bcr.check_lvs_geometry_freshness(self.lvs).startswith("fresh"))
        self.assertTrue(bcr.check_pex_layout_freshness(self.cite).startswith("fresh"))

    def test_changed_current_gds_makes_lvs_and_pex_stale(self):
        (self.reports / "20260101-000001-drc" / "ldo_core.gds").write_bytes(b"rerouted")
        self.assertTrue(bcr.check_lvs_geometry_freshness(self.lvs).startswith("STALE"))
        self.assertTrue(bcr.check_pex_layout_freshness(self.cite).startswith("STALE"))

    def test_new_layout_record_with_identical_bytes_stays_fresh(self):
        self._record("20260202-000000-new", self.GDS)
        (self.reports / "LATEST").write_text("20260202-000000-new\n")
        self.assertTrue(bcr.check_lvs_geometry_freshness(self.lvs).startswith("fresh"))
        self.assertTrue(bcr.check_pex_layout_freshness(self.cite).startswith("fresh"))

    def test_tampered_cited_gds_detected(self):
        (self.lvs / "ldo_core.gds").write_bytes(b"tampered")
        self.assertTrue(bcr.check_lvs_geometry_freshness(self.lvs).startswith("STALE"))
        self.assertTrue(bcr.check_pex_layout_freshness(self.cite).startswith("STALE"))

    def test_missing_cited_gds_is_stale(self):
        (self.lvs / "ldo_core.gds").unlink()
        self.assertTrue(bcr.check_lvs_geometry_freshness(self.lvs).startswith("STALE"))

    def test_missing_hash_unverified(self):
        d = self._record("20260303-000000-nohash", self.GDS, None, lvs=True)
        out = bcr.check_lvs_geometry_freshness(d)
        self.assertTrue(out.startswith("unverified"), out)

    def test_missing_lvs_json_unverified(self):
        (self.lvs / "lvs.json").unlink()
        self.assertTrue(bcr.check_lvs_geometry_freshness(self.lvs).startswith("unverified"))
        self.assertFalse(bcr.check_pex_layout_freshness(self.cite).startswith("fresh"))

    def test_corrupt_lvs_json_unverified(self):
        (self.lvs / "lvs.json").write_text("{not json")
        self.assertTrue(bcr.check_lvs_geometry_freshness(self.lvs).startswith("unverified"))

    def test_missing_latest_pointer_unverified(self):
        (self.reports / "LATEST").unlink()
        out = bcr.check_lvs_geometry_freshness(self.lvs)
        self.assertTrue(out.startswith("unverified"), out)
        self.assertFalse(bcr.check_pex_layout_freshness(self.cite).startswith("fresh"))

    def test_missing_current_gds_unverified(self):
        (self.reports / "20260101-000001-drc" / "ldo_core.gds").unlink()
        self.assertTrue(bcr.check_lvs_geometry_freshness(self.lvs).startswith("unverified"))

    def test_stale_schematic_still_wins_over_fresh_geometry(self):
        bcr.current_schematic_sha = lambda: "bbb2222"
        self.assertTrue(bcr.check_pex_layout_freshness(self.cite).startswith("STALE"))

    def test_geometry_verdict_survives_ignore_sim_freshness(self):
        (self.reports / "20260101-000001-drc" / "ldo_core.gds").write_bytes(b"rerouted")
        out = bcr.check_lvs_geometry_freshness(self.lvs)
        text = "head\n" + bcr.LAYOUT_SECTION_HEADING + "\n| LVS | STALE |\n"
        self.assertTrue(out.startswith("STALE"))
        self.assertIn("| LVS | STALE |", bcr.normalize_sim_freshness(text))


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
        # Only the LAST cell is the schematic Freshness verdict; the Inputs
        # column before it is headless and must stay compared (#237). Only the
        # per-spec-row section is PDK-dependent: the layout section's
        # Freshness (which can itself read `unverified`, #304) is headless.
        idx = self.report.index(bcr.LAYOUT_SECTION_HEADING)
        head, tail = self.report[:idx], self.report[idx:]
        pdk_flavoured = re.sub(
            r"\| unverified \|$", "| fresh |", head, flags=re.MULTILINE
        ).replace(
            "Freshness: unverified: --no-netlist-freshness passed",
            "Freshness: fresh (a live xschem re-netlist of the current testbench "
            "schematic matches the committed netlist snapshot verbatim)",
        ) + tail
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

    def test_fails_when_only_the_inputs_column_drifts(self):
        """#237: the headless Inputs verdict is compared even under
        --ignore-sim-freshness (only the schematic Freshness cell is masked)."""
        drifted = self.report.replace("| unverified | unverified |", "| STALE | unverified |", 1)
        self.assertNotEqual(drifted, self.report)
        self.report_path.write_text(drifted)
        self.assertEqual(
            self._run("--check", "--ignore-sim-freshness", "--out", str(self.report_path)), 1
        )

    def test_fails_on_a_missing_report(self):
        self.assertEqual(
            self._run("--check", "--ignore-sim-freshness", "--out", str(self.report_path)), 1
        )


class TestInputFreshness(unittest.TestCase):
    """Issue #237: experiment/solver freshness, headless and independent of the
    schematic re-netlist. Each dimension must move on its own; prose-only
    manifest edits must not; legacy records must read `unverified`."""

    PVT = {
        "slug": "demo",
        "title": "Demo",
        "claim": "prose claim",
        "schematic": "testbench/tb.sch",
        "corners": {"process": ["tt", "ss"], "temperature_c": [27], "supply_v": [3.3]},
        "corners_note": "prose",
        "quick_subset": [["tt", 27, 3.3]],
        "deck": {
            "options": ["wnflag=1"],
            "params": {"a": 1},
            "analyses": ["* a comment", "", "dc temp 80 180 2"],
        },
        "measurements": [
            {"name": "m1", "expr": "v(vout)", "unit": "V", "min": 1.0, "max": 2.0, "note": "n"}
        ],
        "spread_checks": [{"measurement": "m1", "min_spread": 0.03, "note": "x"}],
    }
    MC = {
        "slug": "mcdemo",
        "claim": "prose",
        "schematic": "testbench/tb.sch",
        "mc_corner": {"process": "tt_mm", "temperature_c": 27, "vsup": 3.3, "note": "p"},
        "mc_analysis": {"kind": "tran", "args": "10u 3m uic", "note": "p"},
        "mc_measurements": [
            {"name": "v", "spice": ".meas tran v avg v(vout)", "unit": "V",
             "limits": {"min": 1.7, "max": 1.9}, "note": "p"}
        ],
        "monte_carlo_defaults": {"n": 200},
    }
    SPICEINIT = "option klu\n"

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        root = Path(self._tmpdir.name)
        (root / "sim" / "demo").mkdir(parents=True)
        self._orig = (bcr.REPO_ROOT, bcr.SIM_DIR)
        bcr.REPO_ROOT, bcr.SIM_DIR = root, root / "sim"
        self.addCleanup(lambda: setattr(bcr, "REPO_ROOT", self._orig[0]))
        self.addCleanup(lambda: setattr(bcr, "SIM_DIR", self._orig[1]))
        (root / "sim" / "spiceinit").write_text(self.SPICEINIT)
        self.manifest = root / "sim" / "demo" / "experiment.json"

    def _write(self, raw):
        self.manifest.write_text(json.dumps(raw))

    def _record(self, raw, kind="pvt", **extra):
        if kind == "pvt":
            sections = bcr.pvt_input_sections(raw, self.SPICEINIT)
        else:
            sections = bcr.mc_input_sections(raw)
        rec = {
            "links": {"manifest": "sim/demo/experiment.json"},
            "input_fingerprint": bcr.build_input_fingerprint(kind, sections),
        }
        if kind == "mc":
            rec["klt_request"] = {}
        rec.update(extra)
        return rec

    def _edit(self, raw, fn):
        import copy

        raw = copy.deepcopy(raw)
        fn(raw)
        return raw

    def test_unchanged_inputs_are_fresh(self):
        self._write(self.PVT)
        self.assertTrue(bcr.check_input_freshness("demo", self._record(self.PVT)).startswith("fresh"))

    def test_each_execution_input_changes_independently(self):
        cases = {
            "analyses": lambda r: r["deck"]["analyses"].append("dc temp 1 2 1"),
            "measurements": lambda r: r["measurements"][0].update(expr="v(vin)"),
            "matrix": lambda r: r["corners"].update(supply_v=[3.3, 3.6]),
        }
        for dim, fn in cases.items():
            with self.subTest(dim=dim):
                self._write(self._edit(self.PVT, fn))
                out = bcr.check_input_freshness("demo", self._record(self.PVT))
                self.assertTrue(out.startswith("STALE"), out)
                self.assertIn(dim, out)
                for other in {"analyses", "measurements", "matrix", "solver"} - {dim}:
                    self.assertNotIn(other, out)

    def test_measurement_bound_change_is_stale(self):
        self._write(self._edit(self.PVT, lambda r: r["measurements"][0].update(max=1.9)))
        out = bcr.check_input_freshness("demo", self._record(self.PVT))
        self.assertTrue(out.startswith("STALE") and "measurements" in out, out)

    def test_solver_settings_change_is_stale(self):
        self._write(self.PVT)
        rec = self._record(self.PVT)
        (bcr.SIM_DIR / "spiceinit").write_text(self.SPICEINIT + "option noopac\n")
        out = bcr.check_input_freshness("demo", rec)
        self.assertTrue(out.startswith("STALE") and "solver" in out, out)

    def test_prose_only_edits_stay_fresh(self):
        def prose(r):
            r["claim"] = "totally different prose"
            r["title"] = "New"
            r["corners_note"] = "edited"
            r["measurements"][0].update(note="edited", unit="mV")
            r["spread_checks"][0]["note"] = "edited"
            r["deck"]["analyses"] = ["* another comment", "dc temp 80 180 2", ""]
            r["corners"]["supply_v"] = [3.30]
        self._write(self._edit(self.PVT, prose))
        out = bcr.check_input_freshness("demo", self._record(self.PVT))
        self.assertTrue(out.startswith("fresh"), out)

    def test_legacy_record_is_unverified_and_unmodified(self):
        self._write(self.PVT)
        rec = {"links": {"manifest": "sim/demo/experiment.json"}}
        before = json.dumps(rec, sort_keys=True)
        out = bcr.check_input_freshness("demo", rec)
        self.assertTrue(out.startswith("unverified: analyses, measurements, matrix, solver"), out)
        self.assertIn("legacy", out)
        self.assertEqual(json.dumps(rec, sort_keys=True), before)

    def test_legacy_pvt_record_with_init_hash_still_compares_solver(self):
        self._write(self.PVT)
        good = {"links": {"manifest": "sim/demo/experiment.json"},
                "tools": {"spiceinit_sha256": bcr.pvt_input_sections(self.PVT, self.SPICEINIT)["solver"]}}
        out = bcr.check_input_freshness("demo", good)
        self.assertTrue(out.startswith("unverified: analyses, measurements, matrix "), out)
        self.assertIn("matching: solver", out)
        bad = {"links": good["links"], "tools": {"spiceinit_sha256": "0" * 64}}
        self.assertTrue(bcr.check_input_freshness("demo", bad).startswith("STALE"))

    def test_unknown_fingerprint_version_is_unverified(self):
        self._write(self.PVT)
        rec = self._record(self.PVT)
        rec["input_fingerprint"]["version"] = 999
        self.assertTrue(bcr.check_input_freshness("demo", rec).startswith("unverified"))

    def test_missing_manifest_is_unverified(self):
        self.assertTrue(bcr.check_input_freshness("demo", self._record(self.PVT)).startswith("unverified"))

    def test_mc_has_no_solver_dimension_and_ignores_spiceinit(self):
        self._write(self.MC)
        rec = self._record(self.MC, kind="mc")
        self.assertNotIn("solver", rec["input_fingerprint"]["sections"])
        (bcr.SIM_DIR / "spiceinit").write_text("option something-else\n")
        out = bcr.check_input_freshness("demo", rec)
        self.assertTrue(out.startswith("fresh"), out)
        self.assertIn("not applicable", out)

    def test_mc_dimensions_change_independently_and_prose_does_not(self):
        rec = self._record(self.MC, kind="mc")
        cases = {
            "analyses": lambda r: r["mc_analysis"].update(args="10u 4m uic"),
            "measurements": lambda r: r["mc_measurements"][0]["limits"].update(max=1.85),
            "matrix": lambda r: r["mc_corner"].update(vsup=3.0),
        }
        for dim, fn in cases.items():
            with self.subTest(dim=dim):
                self._write(self._edit(self.MC, fn))
                out = bcr.check_input_freshness("demo", rec)
                self.assertTrue(out.startswith("STALE") and dim in out, out)
        def prose(r):
            r["claim"] = "x"
            r["mc_analysis"]["note"] = "y"
            r["mc_measurements"][0]["note"] = "z"
            r["monte_carlo_defaults"]["n"] = 50
        self._write(self._edit(self.MC, prose))
        self.assertTrue(bcr.check_input_freshness("demo", rec).startswith("fresh"))

    def test_inputs_verdict_survives_ignore_sim_freshness_normalisation(self):
        """The Inputs verdict must not be masked by `--ignore-sim-freshness`."""
        report = (
            "| P | T | V | E | Inputs | Freshness |\n|---|---|---|---|---|---|\n"
            "| Output | x | **PASS** | [`r`](a.md) | STALE | fresh |\n"
            "- **Output**: **PASS** — rec. Experiment/solver inputs: STALE (changed: matrix). "
            "Freshness: fresh (x).\n\n"
            f"{bcr.LAYOUT_SECTION_HEADING}\n"
        )
        norm = bcr.normalize_sim_freshness(report)
        self.assertIn("| STALE | <freshness not compared> |", norm)
        self.assertIn("Experiment/solver inputs: STALE (changed: matrix).", norm)
        self.assertNotEqual(
            norm, bcr.normalize_sim_freshness(report.replace("| STALE |", "| fresh |", 1))
        )

    def test_fingerprint_is_deterministic_and_numeric_spelling_insensitive(self):
        a = bcr.pvt_input_sections(self.PVT, self.SPICEINIT)
        b = bcr.pvt_input_sections(
            self._edit(self.PVT, lambda r: r["corners"].update(temperature_c=[27.0])), self.SPICEINIT
        )
        self.assertEqual(a, b)
        fp = bcr.build_input_fingerprint("pvt", a)
        self.assertEqual(fp, bcr.build_input_fingerprint("pvt", dict(reversed(list(a.items())))))
        self.assertEqual(fp["version"], bcr.INPUT_FINGERPRINT_VERSION)



class TestAreaRow(unittest.TestCase):
    """Issue #236: the Area row reads a layout area record's verdict and
    detects a changed routed GDS as stale, without recomputing anything."""

    SPEC_ROWS = [{"parameter": "Area", "draft_target": "< 0.1 mm² total core area",
                  "draft_stretch": "—", "src": "G+S", "note": ""}]

    def setUp(self):
        import hashlib

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.reports = self.root / "layout" / "ldo-core" / "reports"
        (self.reports / "L1").mkdir(parents=True)
        (self.reports / "A1").mkdir()
        self.gds = self.reports / "L1" / "ldo_core.gds"
        self.gds.write_bytes(b"routed-v1")
        (self.reports / "LATEST").write_text("L1\n")
        (self.reports / "LATEST-AREA").write_text("A1\n")
        self.rec = {
            "record_id": "A1", "cell": "ldo_core", "verdict": "FAIL", "area_mm2": "0.4",
            "limit_mm2": "0.1", "width_um": "1", "height_um": "1", "convention": "conv.",
            "gds": {"path": "layout/ldo-core/reports/L1/ldo_core.gds",
                    "sha256": hashlib.sha256(b"routed-v1").hexdigest()},
        }
        self._write_rec()
        (self.reports / "A1" / "record.md").write_text("# rec\n")
        self._saved = (bcr.REPO_ROOT, bcr.LAYOUT_DIR)
        bcr.REPO_ROOT, bcr.LAYOUT_DIR = self.root, self.root / "layout"

    def tearDown(self):
        bcr.REPO_ROOT, bcr.LAYOUT_DIR = self._saved
        self._tmp.cleanup()

    def _write_rec(self):
        (self.reports / "A1" / "area.json").write_text(json.dumps(self.rec))

    def _row(self):
        table, detail = bcr.build_spec_row_table(self.SPEC_ROWS, True)
        return table[-1], detail[-1]

    def test_verdict_is_read_from_the_record_not_derived(self):
        self.rec["verdict"] = "PASS"  # contradicts area_mm2 on purpose
        self._write_rec()
        row, detail = self._row()
        self.assertIn("**PASS**", row)
        self.assertIn("**PASS**", detail)

    def test_fresh_when_current_routed_gds_matches(self):
        row, detail = self._row()
        self.assertIn("**FAIL**", row)
        self.assertTrue(row.endswith("| fresh (GDS sha256) |"), row)
        self.assertIn("GDS freshness: fresh", detail)

    def test_changed_routed_gds_is_stale(self):
        # A re-route: LATEST now names a new record whose GDS bytes differ.
        (self.reports / "L2").mkdir()
        (self.reports / "L2" / "ldo_core.gds").write_bytes(b"routed-v2")
        (self.reports / "LATEST").write_text("L2\n")
        row, detail = self._row()
        self.assertTrue(row.endswith("| STALE (GDS sha256) |"), row)
        self.assertIn("GDS freshness: STALE", detail)

    def test_edited_cited_gds_is_stale(self):
        self.gds.write_bytes(b"routed-v1-edited")
        row, _ = self._row()
        self.assertIn("STALE", row)

    def test_missing_pointer_is_an_error_row_not_na(self):
        (self.reports / "LATEST-AREA").unlink()
        row, _ = self._row()
        self.assertIn("**ERROR**", row)

    def test_area_freshness_survives_ignore_sim_freshness(self):
        """The headless GDS-hash freshness must still be compared under
        --ignore-sim-freshness: a stale Area row may not normalise away."""
        row, detail = self._row()
        text = bcr.LAYOUT_SECTION_HEADING + "\n"
        fresh = "\n".join([row, detail, text])
        (self.reports / "L2").mkdir()
        (self.reports / "L2" / "ldo_core.gds").write_bytes(b"routed-v2")
        (self.reports / "LATEST").write_text("L2\n")
        row2, detail2 = self._row()
        stale = "\n".join([row2, detail2, text])
        self.assertNotEqual(bcr.normalize_sim_freshness(fresh), bcr.normalize_sim_freshness(stale))

    def test_area_is_no_longer_na_in_the_committed_report(self):
        bcr.REPO_ROOT, bcr.LAYOUT_DIR = self._saved
        text = (MEASUREMENTS_DIR / "characterization.md").read_text()
        area = [ln for ln in text.splitlines() if ln.startswith("| Area |")]
        self.assertEqual(len(area), 1)
        self.assertNotIn("N/A", area[0])
        self.assertIn("layout/ldo-core/reports/", area[0])


class TestDrcRowDetail(unittest.TestCase):
    """Issue #260 / PR #268 review: the DRC row's verdict covers both the
    curated deck and the official `sky130A_mr.drc` deck, so its parenthetical
    must name each deck -- a FAIL beside only `status=clean, violation_count=0`
    contradicts itself."""

    LYRDB = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
 <top-cell>ldo_core</top-cell>
 <categories>
  <category><name>m2.5</name><description>d</description><categories/></category>
  <category><name>via.1a_b</name><description>d</description><categories/></category>
 </categories>
 <items>
{items} </items>
</report-database>
"""
    ITEM = (
        "  <item><category>'{rule}'</category><cell>ldo_core</cell>"
        "<values><value>polygon: (0,0;0,0.16;0.16,0.16;0.16,0)</value></values></item>\n"
    )
    RUN_OK = {"deck_present": True, "klayout_found": True, "exit_code": 0}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        (self.d / "drc.json").write_text(json.dumps({"status": "clean", "violation_count": 0}))

    def tearDown(self):
        self._tmp.cleanup()

    def _official(self, rules, run=None):
        (self.d / "mr-drc.run.json").write_text(json.dumps(run or self.RUN_OK))
        items = "".join(self.ITEM.format(rule=r) for r in rules)
        (self.d / "mr-drc.lyrdb").write_text(self.LYRDB.format(items=items))

    def test_official_violations_surface_beside_curated_clean(self):
        self._official(["m2.5", "m2.5", "via.1a_b"])
        detail = bcr.drc_row_detail(self.d)
        self.assertIn("curated deck: status=clean, violation_count=0", detail)
        self.assertIn(
            "official deck `sky130A_mr.drc`: violations, violation_count=3 in 2 rule families", detail
        )

    def test_official_clean_is_labelled_clean(self):
        self._official([])
        detail = bcr.drc_row_detail(self.d)
        self.assertIn("official deck `sky130A_mr.drc`: clean", detail)

    def test_official_error_is_not_clean(self):
        self._official([], run={"deck_present": True, "klayout_found": True, "exit_code": 1})
        detail = bcr.drc_row_detail(self.d)
        self.assertIn("official deck `sky130A_mr.drc`: ERROR", detail)
        self.assertNotIn("official deck `sky130A_mr.drc`: clean", detail)

    def test_truncated_official_report_is_an_error(self):
        self._official([])
        p = self.d / "mr-drc.lyrdb"
        p.write_text(p.read_text()[:40])
        self.assertIn("official deck `sky130A_mr.drc`: ERROR", bcr.drc_row_detail(self.d))

    def test_pre_dual_deck_record_says_official_not_run(self):
        detail = bcr.drc_row_detail(self.d)
        self.assertIn("curated deck: status=clean", detail)
        self.assertIn("official deck: not run in this record", detail)

    def test_committed_report_drc_row_names_both_decks(self):
        text = (MEASUREMENTS_DIR / "characterization.md").read_text()
        rows = [ln for ln in text.splitlines() if ln.startswith("| DRC (issue #16) |")]
        self.assertEqual(len(rows), 1)
        self.assertIn("curated deck:", rows[0])
        self.assertIn("official deck", rows[0])


class TestDrcInputFreshness(unittest.TestCase):
    """Issue #304: the DRC row's Freshness covers the GDS bytes the checkers
    read, not only the schematic commit. Every case renders the REAL DRC row
    through `build_layout_section` against a PDK-free fixture tree, so what is
    asserted is what the committed report would say."""

    RID = "20260101-000000-drc"
    SCH = "aaa1111"
    GDS = b"routed-gds-bytes"
    RECORD_MD = "## Overall verdict: FAIL\n\nSchematic freshness: netlisted from commit `aaa1111`\n"
    LYRDB = TestDrcRowDetail.LYRDB
    ITEM = TestDrcRowDetail.ITEM

    def setUp(self):
        import hashlib
        import shutil

        self.sha = hashlib.sha256(self.GDS).hexdigest()
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        saved = (bcr.LAYOUT_DIR, bcr.SIM_DIR, bcr.current_schematic_sha, bcr._sha256_of)
        self.addCleanup(lambda: (
            setattr(bcr, "LAYOUT_DIR", saved[0]), setattr(bcr, "SIM_DIR", saved[1]),
            setattr(bcr, "current_schematic_sha", saved[2]), setattr(bcr, "_sha256_of", saved[3]),
        ))
        bcr.LAYOUT_DIR = root / "layout"
        bcr.SIM_DIR = root / "sim"  # no PEX record: that row renders its own ERROR line
        bcr.current_schematic_sha = lambda: self.SCH
        reports = bcr.LAYOUT_DIR / "ldo-core" / "reports"
        self.d = reports / self.RID
        self.d.mkdir(parents=True)
        (reports / "LATEST").write_text(self.RID + "\n")
        (self.d / "record.md").write_text(self.RECORD_MD)
        (self.d / "ldo_core.gds").write_bytes(self.GDS)
        self.write_drc()
        self.write_run()

    # -- fixture writers ---------------------------------------------------

    def write_drc(self, content_hash="__default__", file="/elsewhere/out/ldo_core.gds", **extra):
        drc = {"status": "clean", "violation_count": 0}
        if file is not None:
            drc["file"] = file
        if content_hash is not None:
            if content_hash == "__default__":
                content_hash = "sha256:" + self.sha
            drc["provenance"] = {"input": {"content_hash": content_hash, "role": "layout"}}
        drc.update(extra)
        (self.d / "drc.json").write_text(json.dumps(drc))

    def write_run(self, input_sha256="__default__", rules=("m2.5", "m2.5", "via.1a_b")):
        run = dict(TestDrcRowDetail.RUN_OK)
        if input_sha256 is not None:
            run["input_sha256"] = self.sha if input_sha256 == "__default__" else input_sha256
        (self.d / "mr-drc.run.json").write_text(json.dumps(run))
        items = "".join(self.ITEM.format(rule=r) for r in rules)
        (self.d / "mr-drc.lyrdb").write_text(self.LYRDB.format(items=items))

    # -- readers -----------------------------------------------------------

    def row(self) -> str:
        rows = [ln for ln in bcr.build_layout_section() if ln.startswith("| DRC (issue #16) |")]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def freshness(self) -> str:
        return self.row().rstrip(" |").rsplit("|", 1)[-1].strip()

    def verdict_cells(self) -> str:
        return self.row().rsplit("|", 2)[0]

    def note(self) -> str:
        notes = [ln for ln in bcr.build_layout_section() if ln.startswith("DRC freshness detail")]
        self.assertEqual(len(notes), 1)
        return notes[0]

    # -- acceptance --------------------------------------------------------

    def test_matching_bytes_and_schematic_are_fresh(self):
        self.assertEqual(self.freshness(), "fresh")
        self.assertIn("official deck's recorded input_sha256", self.note())

    def test_appended_gds_bytes_are_stale_with_schematic_unchanged(self):
        before = self.verdict_cells()
        with (self.d / "ldo_core.gds").open("ab") as f:
            f.write(b"\x00\x04\x04\x00")
        self.assertEqual(self.freshness(), "STALE")
        self.assertIn("curated deck's recorded input content_hash", self.note())
        # The verdict and both decks' results are the record's own, unchanged.
        self.assertEqual(self.verdict_cells(), before)

    def test_both_verdicts_stay_visible_whatever_the_freshness(self):
        for mutate in (lambda: None, lambda: (self.d / "ldo_core.gds").write_bytes(b"x"),
                       lambda: self.write_drc(content_hash=None)):
            mutate()
            row = self.row()
            self.assertIn("**FAIL**", row)
            self.assertIn("curated deck: status=clean, violation_count=0", row)
            self.assertIn(
                "official deck `sky130A_mr.drc`: violations, violation_count=3 in 2 rule families", row
            )

    def test_moved_schematic_is_stale_even_with_matching_bytes(self):
        bcr.current_schematic_sha = lambda: "bbb2222"
        self.assertEqual(self.freshness(), "STALE")

    def test_missing_gds_is_stale(self):
        (self.d / "ldo_core.gds").unlink()
        self.assertEqual(self.freshness(), "STALE")

    def test_unreadable_gds_is_not_fresh(self):
        def boom(_p):
            raise OSError("permission denied")

        bcr._sha256_of = boom
        self.assertEqual(self.freshness(), "unverified")
        self.assertIn("unreadable", self.note())

    def test_cited_file_is_resolved_inside_the_record_not_at_its_absolute_path(self):
        # The recorded absolute path is the flow's run-time out dir; a file
        # that happens to exist there must not stand in for the record's GDS.
        self.write_drc(file=str(Path(self._outside_gds(b"other-bytes"))))
        self.assertEqual(self.freshness(), "fresh")
        (self.d / "ldo_core.gds").write_bytes(b"other-bytes")
        self.assertEqual(self.freshness(), "STALE")

    def _outside_gds(self, data: bytes) -> str:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "ldo_core.gds"
        p.write_bytes(data)
        return str(p)

    # -- missing / malformed provenance ------------------------------------

    def test_missing_curated_input_hash_is_unverified(self):
        self.write_drc(content_hash=None)
        self.assertEqual(self.freshness(), "unverified")
        self.assertIn("provenance.input.content_hash", self.note())

    def test_missing_input_file_is_unverified_not_inferred_from_the_directory(self):
        self.write_drc(file=None)
        self.assertEqual(self.freshness(), "unverified")
        self.assertIn("no input file", self.note())

    def test_malformed_curated_hashes_are_unverified(self):
        for bad in ("md5:" + self.sha[:32], "sha256:" + self.sha[:40], "sha256:", 1234, None, ""):
            with self.subTest(bad=bad):
                drc = {"status": "clean", "violation_count": 0, "file": "ldo_core.gds",
                       "provenance": {"input": {"content_hash": bad, "role": "layout"}}}
                (self.d / "drc.json").write_text(json.dumps(drc))
                self.assertEqual(self.freshness(), "unverified")

    def test_non_layout_input_role_is_unverified(self):
        drc = json.loads((self.d / "drc.json").read_text())
        drc["provenance"]["input"]["role"] = "netlist"
        (self.d / "drc.json").write_text(json.dumps(drc))
        self.assertEqual(self.freshness(), "unverified")

    def test_corrupt_or_missing_drc_json_is_unverified(self):
        (self.d / "drc.json").write_text("{not json")
        self.assertEqual(self.freshness(), "unverified")
        (self.d / "drc.json").write_text("[]")
        self.assertEqual(self.freshness(), "unverified")
        (self.d / "drc.json").unlink()
        self.assertEqual(self.freshness(), "unverified")

    def test_missing_record_md_is_unverified(self):
        (self.d / "record.md").unlink()
        self.assertEqual(self.freshness(), "unverified")

    def test_official_input_hash_mismatch_is_stale(self):
        self.write_run(input_sha256="0" * 64)
        self.assertEqual(self.freshness(), "STALE")
        self.assertIn("official deck's recorded input_sha256", self.note())

    def test_malformed_official_input_hash_is_unverified(self):
        for bad in ("deadbeef", None, 7):
            with self.subTest(bad=bad):
                run = dict(TestDrcRowDetail.RUN_OK, input_sha256=bad)
                (self.d / "mr-drc.run.json").write_text(json.dumps(run))
                self.assertEqual(self.freshness(), "unverified")

    def test_unreadable_official_run_record_is_unverified_and_its_verdict_an_error(self):
        (self.d / "mr-drc.run.json").write_text("{not json")
        self.assertEqual(self.freshness(), "unverified")
        self.assertIn("official deck `sky130A_mr.drc`: ERROR", self.row())

    # -- legacy records ----------------------------------------------------

    def test_legacy_dual_deck_record_without_official_input_hash_is_unverified(self):
        # The shape of every dual-deck record minted before #304.
        self.write_run(input_sha256=None)
        self.assertEqual(self.freshness(), "unverified")
        self.assertIn("records no input_sha256", self.note())
        self.assertIn("**FAIL**", self.row())

    def test_legacy_pre_dual_deck_record_is_judged_on_the_curated_deck(self):
        for name in ("mr-drc.run.json", "mr-drc.lyrdb"):
            (self.d / name).unlink()
        self.assertEqual(self.freshness(), "fresh")
        self.assertIn("official deck: not run in this record", self.row())
        (self.d / "ldo_core.gds").write_bytes(b"rerouted")
        self.assertEqual(self.freshness(), "STALE")

    def test_legacy_curated_envelope_without_provenance_is_unverified(self):
        for name in ("mr-drc.run.json", "mr-drc.lyrdb"):
            (self.d / name).unlink()
        (self.d / "drc.json").write_text(json.dumps(
            {"file": "ldo_core.gds", "status": "clean", "violation_count": 0, "provenance": None}
        ))
        self.assertEqual(self.freshness(), "unverified")

    def test_check_never_modifies_the_record(self):
        before = {p.name: p.read_bytes() for p in self.d.iterdir()}
        (self.d / "ldo_core.gds").write_bytes(b"changed")
        before["ldo_core.gds"] = b"changed"
        self.row()
        self.assertEqual({p.name: p.read_bytes() for p in self.d.iterdir()}, before)

    # -- hash spelling -----------------------------------------------------

    def test_hash_prefix_spellings_are_normalized(self):
        for curated, official in (
            ("sha256:" + self.sha, self.sha),
            (self.sha, "sha256:" + self.sha),
            ("SHA256:" + self.sha.upper(), self.sha.upper()),
            (" sha256:" + self.sha + "\n", self.sha),
        ):
            with self.subTest(curated=curated, official=official):
                self.write_drc(content_hash=curated)
                self.write_run(input_sha256=official)
                self.assertEqual(self.freshness(), "fresh")

    def test_normalize_sha256(self):
        self.assertEqual(bcr.normalize_sha256("sha256:" + self.sha), self.sha)
        self.assertEqual(bcr.normalize_sha256(self.sha.upper()), self.sha)
        for bad in (None, 1, "", "sha256:", "md5:" + self.sha, "sha1:" + self.sha, self.sha + "0"):
            self.assertIsNone(bcr.normalize_sha256(bad), bad)

    # -- headless check ----------------------------------------------------

    def test_drc_staleness_survives_ignore_sim_freshness(self):
        (self.d / "ldo_core.gds").write_bytes(b"rerouted")
        row = self.row()
        self.assertTrue(row.endswith("| STALE |"), row)
        text = "head\n| Out | x | PASS | r | fresh | fresh |\n" + bcr.LAYOUT_SECTION_HEADING + "\n" + row + "\n"
        self.assertIn(row, bcr.normalize_sim_freshness(text))
        fresh_text = text.replace("| STALE |", "| fresh |")
        self.assertNotEqual(bcr.normalize_sim_freshness(text), bcr.normalize_sim_freshness(fresh_text))


class TestCommittedDrcRow(unittest.TestCase):
    """The committed rollup's DRC row is the live renderer's output for the
    real tree (headless -- no PDK needed for the layout section)."""

    def test_committed_drc_row_matches_the_live_renderer(self):
        text = (MEASUREMENTS_DIR / "characterization.md").read_text()
        live = bcr.build_layout_section()
        for prefix in ("| DRC (issue #16) |", "DRC freshness detail"):
            committed = [ln for ln in text.splitlines() if ln.startswith(prefix)]
            rendered = [ln for ln in live if ln.startswith(prefix)]
            self.assertEqual(len(rendered), 1, prefix)
            self.assertEqual(committed, rendered, prefix)


class TestMalformedCampaignVerdict(unittest.TestCase):
    """Issue #255: a selected campaign's `overall_pass` must be a JSON boolean.
    Anything else is an evidence ERROR naming the record -- never coerced to
    PASS/FAIL by truthiness, and never replaced by an older campaign."""

    SLUG = "fake-slug"
    PARAM = "Fake param"
    ROWS = [{"parameter": PARAM, "draft_target": "< 1", "draft_stretch": "—",
             "src": "G+S", "note": ""}]
    MISSING = object()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self._saved = (bcr.REPO_ROOT, bcr.SIM_DIR, dict(bcr.EVIDENCE_MAP))
        bcr.REPO_ROOT, bcr.SIM_DIR = root, root / "sim"
        bcr.EVIDENCE_MAP[self.PARAM] = self.SLUG
        bcr.EVIDENCE_ERRORS.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        bcr.REPO_ROOT, bcr.SIM_DIR = self._saved[0], self._saved[1]
        bcr.EVIDENCE_MAP.clear()
        bcr.EVIDENCE_MAP.update(self._saved[2])
        bcr.EVIDENCE_ERRORS.clear()

    def _write(self, record_id, overall=True, **extra):
        d = bcr.SIM_DIR / self.SLUG / "records"
        d.mkdir(parents=True, exist_ok=True)
        data = {"record_id": record_id, **extra}
        if overall is not self.MISSING:
            data["overall_pass"] = overall
        (d / f"{record_id}.json").write_text(json.dumps(data))
        (d / f"{record_id}.md").write_text(f"# {record_id}\n")

    def _row(self):
        table, detail = bcr.build_spec_row_table(self.ROWS, True)
        return table[-1], detail[-1]

    def test_valid_booleans_render_unchanged(self):
        for value, word in ((True, "PASS"), (False, "FAIL")):
            with self.subTest(value=value):
                bcr.EVIDENCE_ERRORS.clear()
                self._write("20260101-000000-good", value)
                row, _ = self._row()
                self.assertIn(f"**{word}**", row)
                self.assertEqual(bcr.EVIDENCE_ERRORS, [])

    def test_non_boolean_verdicts_are_errors_not_pass_or_fail(self):
        bad = ["false", "true", "", "PASS", 0, 1, None, self.MISSING, [], [True], {}, {"a": 1}]
        for value in bad:
            with self.subTest(value=repr(value)):
                bcr.EVIDENCE_ERRORS.clear()
                self._write("20260101-000000-bad", value)
                row, detail = self._row()
                self.assertIn("**ERROR**", row)
                self.assertNotIn("**PASS**", row)
                self.assertNotIn("**FAIL**", row)
                self.assertIn("20260101-000000-bad", detail)
                self.assertEqual(len(bcr.EVIDENCE_ERRORS), 1)
                self.assertIn("20260101-000000-bad", bcr.EVIDENCE_ERRORS[0])

    def test_valid_older_then_invalid_newer_errors_naming_newer(self):
        self._write("20260101-000000-older", True)
        self._write("20260202-000000-newer", "false")
        row, detail = self._row()
        self.assertIn("**ERROR**", row)
        self.assertIn("20260202-000000-newer", row)
        self.assertNotIn("20260101-000000-older", row + detail)
        self.assertIn("20260202-000000-newer", bcr.EVIDENCE_ERRORS[0])

    def test_derived_record_with_no_verdict_is_still_excluded(self):
        self._write("20260101-000000-camp", False)
        self._write("20260202-000000-yield", self.MISSING, evidence_kind="yield")
        row, _ = self._row()
        self.assertIn("**FAIL**", row)
        self.assertIn("20260101-000000-camp", row)
        self.assertEqual(bcr.EVIDENCE_ERRORS, [])

    def test_subset_disclosure_and_freshness_still_rendered_for_valid_record(self):
        self._write("20260101-000000-sub", True,
                    matrix={"is_subset": True, "subset_reason": "3-point subset"})
        row, detail = self._row()
        self.assertIn("(PVT subset)", row)
        self.assertIn("3-point subset", detail)
        self.assertIn("unverified: --no-netlist-freshness passed", detail)

    def test_cli_exits_nonzero_on_malformed_verdict(self):
        self._write("20260101-000000-bad", "false")
        saved_spec = bcr.parse_spec_rows
        bcr.parse_spec_rows = lambda _text: self.ROWS
        self.addCleanup(lambda: setattr(bcr, "parse_spec_rows", saved_spec))
        out = Path(self._tmp.name) / "out.md"
        out.write_text("x")
        for argv in (["--check", "--ignore-sim-freshness"], ["--stdout"], []):
            with self.subTest(argv=argv):
                err = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                    rc = bcr.main([*argv, "--out", str(out)])
                self.assertEqual(rc, 1)
                self.assertIn("20260101-000000-bad", err.getvalue())
        self.assertEqual(out.read_text(), "x")


class TestWindowGridDisclosure(unittest.TestCase):
    """Issue #313: the report keeps PVT coverage and COUT/ESR coverage apart and
    never claims window qualification from a record that did not evidence it."""

    def test_record_without_grid_is_declared_not_evidenced(self):
        text = bcr.sim_window_grid_disclosure("load-transient", {"record_id": "old"})
        self.assertIn("declared but not", text)
        self.assertIn("no claim of COUT/ESR window qualification", text)
        self.assertIn("not a continuous-window proof", text)
        self.assertIn("separate from the PVT coverage", text)

    def test_incomplete_grid_is_disclosed_and_not_qualified(self):
        rec = {"window_grid": {"complete": False, "pass": False,
                               "conditions_passing": 10, "conditions_expected": 42}}
        text = bcr.sim_window_grid_disclosure("load-transient", rec)
        self.assertIn("INCOMPLETE", text)
        self.assertIn("10/42", text)
        self.assertIn("NOT qualified", text)

    def test_complete_failing_grid_is_not_qualified(self):
        rec = {"window_grid": {"complete": True, "pass": False,
                               "conditions_passing": 41, "conditions_expected": 42}}
        text = bcr.sim_window_grid_disclosure("load-transient", rec)
        self.assertIn("complete but failing", text)
        self.assertIn("NOT qualified", text)

    def test_passing_grid_still_states_finite_sample(self):
        rec = {"window_grid": {"complete": True, "pass": True,
                               "conditions_passing": 42, "conditions_expected": 42}}
        text = bcr.sim_window_grid_disclosure("load-transient", rec)
        self.assertIn("interior worst case", text)

    def test_experiment_without_grid_gets_no_clause(self):
        self.assertIsNone(bcr.sim_window_grid_disclosure("pdk-smoke", {}))
        self.assertIsNone(bcr.sim_window_grid_disclosure("no-such-experiment", {}))


if __name__ == "__main__":
    unittest.main()
