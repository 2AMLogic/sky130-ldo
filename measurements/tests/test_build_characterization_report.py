"""Unit coverage for measurements/build_characterization_report.py.

PDK-free by design (no ngspice/xschem/volare required) so this runs on every
`npm run check:ci` invocation, including in CI where the sky130 PDK is not
installed -- same convention as `sim/tests/test_corner_run.py`.

Two things are covered here:

1. the pure parsing/extraction/freshness helpers (the parts that decide what
   verdict text ends up in the report), exercised against fixture strings
   rather than the live tree, so a record landing under `sim/` never silently
   changes what these assertions mean; and
2. the **no self-referential provenance** invariant (PR #49 review): the
   generated report must not embed the identity of the commit that generates
   it, because a commit cannot contain its own resulting sha -- a report that
   did would make `--check` fail by construction on the very commit that
   ships it.
"""

from __future__ import annotations

import importlib.util
import sys
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


if __name__ == "__main__":
    unittest.main()
