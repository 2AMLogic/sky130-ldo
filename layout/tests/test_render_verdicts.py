"""PDK-free verdict tests for the layout evidence renderers (issue #278).

Pins the verdict logic that `record.md` headlines ("Item 11 verdict: MET",
"Overall verdict: MATCH") to one passing case and one negative control per
clause, so a dropped conjunct (e.g. the `bool(ties)` guard) fails CI.

Standard library only; runs in the headless `checks` job (no klayout wheel).
The scripts' filenames contain hyphens, so they are loaded by path.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from decimal import Decimal
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))


def _load(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, BIN / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


erc = _load("render-ldo-erc-record.py", "render_ldo_erc_record")
lvs = _load("render-ldo-lvs-record.py", "render_ldo_lvs_record")
area = _load("render-ldo-area-record.py", "render_ldo_area_record")


class Item11VerdictTests(unittest.TestCase):
    SUPPLIES = ["VIN", "0"]
    TIES = ["substrate_tie", "nwell_tie"]

    def kwargs(self, **over):
        base = dict(
            item_11_findings=[],
            net_work_checked=[f'erc.net_connectivity:["{s}"]' for s in self.SUPPLIES],
            supplies=self.SUPPLIES,
            tie_work_checked=[f'erc.missing_tie:["{t}"]' for t in self.TIES],
            ties=self.TIES,
            tie_work_skipped=[],
        )
        base.update(over)
        return base

    def test_clean_run_is_met(self):
        self.assertTrue(erc.item_11_met(**self.kwargs()))

    def test_any_finding_is_not_met(self):
        self.assertFalse(erc.item_11_met(**self.kwargs(item_11_findings=["erc.supply_short"])))

    def test_unchecked_supply_is_not_met(self):
        self.assertFalse(
            erc.item_11_met(**self.kwargs(net_work_checked=['erc.net_connectivity:["VIN"]']))
        )

    def test_unchecked_tie_is_not_met(self):
        self.assertFalse(
            erc.item_11_met(**self.kwargs(tie_work_checked=['erc.missing_tie:["nwell_tie"]']))
        )

    def test_skipped_tie_work_is_not_met(self):
        self.assertFalse(
            erc.item_11_met(**self.kwargs(tie_work_skipped=[{"id": 'erc.missing_tie:["x"]'}]))
        )

    def test_no_declared_ties_is_not_met(self):
        # Counts match (0 == 0) and nothing fired; only bool(ties) blocks MET.
        self.assertFalse(erc.item_11_met(**self.kwargs(tie_work_checked=[], ties=[])))

    def test_rules_helper_tolerates_missing_findings(self):
        self.assertEqual(erc._rules({}), [])
        self.assertEqual(erc._rules({"erc_findings": [{"rule": "a"}]}), ["a"])


class LvsVerdictTests(unittest.TestCase):
    def test_match_is_match(self):
        self.assertTrue(lvs.lvs_is_match("match"))
        self.assertEqual(lvs.verdict_heading(True), "## Overall verdict: MATCH")

    def test_non_match_statuses_render_mismatch(self):
        for status in ("mismatch", "error", "MATCH", "", None):
            with self.subTest(status=status):
                self.assertFalse(lvs.lvs_is_match(status))
                self.assertEqual(
                    lvs.verdict_heading(lvs.lvs_is_match(status)),
                    "## Overall verdict: MISMATCH -- not LVS-clean",
                )


class AreaVerdictTests(unittest.TestCase):
    """The area renderer copies `verdict` verbatim; its own logic is the klt
    bbox cross-check. `_gds_area.verdict_for` is covered by test_gds_area."""

    def measurement(self):
        import _gds_area as ga

        dbu = Decimal("0.001")
        return ga.AreaMeasurement(
            "ldo_core", (0, 0, 1000, 2000), dbu, Decimal("1"), Decimal("2"),
            Decimal("2"), Decimal("0.000002"), Decimal("0.1"), "PASS",
        )

    def test_bbox_within_two_dbu_agrees(self):
        m = self.measurement()
        self.assertTrue(area.bbox_agrees(Decimal("1.002"), Decimal("1.998"), m))

    def test_bbox_width_off_alone_disagrees(self):
        m = self.measurement()
        self.assertFalse(area.bbox_agrees(Decimal("1.003"), Decimal("2"), m))

    def test_bbox_height_off_alone_disagrees(self):
        m = self.measurement()
        self.assertFalse(area.bbox_agrees(Decimal("1"), Decimal("2.003"), m))


if __name__ == "__main__":
    unittest.main()
