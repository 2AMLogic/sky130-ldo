"""README.md's T1 headline must mirror signoff/records/t1-tier-report.json.

Covers signoff/check-t1-headline.py (issue #579): the numeric-`id` denominator
(the record's trailing `id: null` rows are the T2/T3/T4 tier rows, not T1
items, so counting all 14 entries would be wrong), each way the headline can
disagree with the record, and the cases where the check must fail loudly
rather than pass silently.

Needs nothing but python3 -- no klt, no PDK, no network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "check_t1_headline", ROOT / "signoff" / "check-t1-headline.py"
)
assert _spec is not None and _spec.loader is not None
m = importlib.util.module_from_spec(_spec)
sys.modules["check_t1_headline"] = m
_spec.loader.exec_module(m)

HEADLINE = "### Where this block sits on the evidence ladder: **T1 {met}/{total}, `tier: {tier}`**"


def _item(n, status="met", tier="T1"):
    return {"id": n, "tier": tier, "status": status}


def _record(met=9, total=11, tier=None, with_summary=True, tier_rows=True):
    """A tier report shaped like the committed one: T1 items plus tier rows."""
    items = [_item(n, "met" if n <= met else "unmet") for n in range(1, total + 1)]
    if tier_rows:
        items += [{"id": None, "tier": t, "status": "unmet"} for t in ("T2", "T3", "T4")]
    doc = {"kind": "t1-tier-report", "tier": tier, "items": items}
    if with_summary:
        doc["t1_item_count"] = total
        doc["t1_met_count"] = met
    return doc


def _readme(met=9, total=11, tier="null", preamble=True):
    body = "# Block\n\nSome prose.\n\n" if preamble else ""
    return body + HEADLINE.format(met=met, total=total, tier=tier) + "\n\nMore prose.\n"


class RunMixin:
    """Run the check over temporary README/record files and return its exit code."""

    def run_check(self, readme_text, record_doc):
        with tempfile.TemporaryDirectory() as d:
            readme = Path(d) / "README.md"
            record = Path(d) / "t1-tier-report.json"
            readme.write_text(readme_text, encoding="utf-8")
            record.write_text(json.dumps(record_doc), encoding="utf-8")
            return m.main(["check-t1-headline.py", str(readme), str(record)])


class TestCountsFromRecord(unittest.TestCase):
    def test_excludes_null_id_tier_rows(self):
        """The 3 trailing `id: null` rows must not inflate the denominator."""
        doc = _record(met=9, total=11)
        self.assertEqual(len(doc["items"]), 14)
        self.assertEqual(m.counts_from_record(doc), (9, 11, "null"))

    def test_counts_only_met(self):
        self.assertEqual(m.counts_from_record(_record(met=5, total=11))[0], 5)

    def test_tier_text(self):
        self.assertEqual(m.counts_from_record(_record(tier="T1"))[2], "T1")
        self.assertEqual(m.counts_from_record(_record(tier=None))[2], "null")

    def test_no_items_list(self):
        with self.assertRaises(m.HeadlineError):
            m.counts_from_record({"kind": "t1-tier-report"})

    def test_no_numeric_ids(self):
        doc = {"tier": None, "items": [{"id": None, "tier": "T2", "status": "unmet"}]}
        with self.assertRaises(m.HeadlineError):
            m.counts_from_record(doc)

    def test_internally_inconsistent_summary_rejected(self):
        """A record whose own summary disagrees with its items is not a source of truth."""
        doc = _record(met=9, total=11)
        doc["t1_met_count"] = 5
        with self.assertRaises(m.HeadlineError):
            m.counts_from_record(doc)

    def test_summary_absent_is_fine(self):
        self.assertEqual(m.counts_from_record(_record(with_summary=False)), (9, 11, "null"))


class TestHeadlineFromReadme(unittest.TestCase):
    def test_parses(self):
        line, met, total, tier = m.headline_from_readme(_readme(9, 11, "null"))
        self.assertEqual((met, total, tier), (9, 11, "null"))
        self.assertGreater(line, 1)

    def test_missing_headline(self):
        with self.assertRaises(m.HeadlineError):
            m.headline_from_readme("# Block\n\nNo ladder headline here at all.\n")

    def test_malformed_headline(self):
        with self.assertRaises(m.HeadlineError):
            m.headline_from_readme(
                "### Where this block sits on the evidence ladder: nearly ratified\n"
            )

    def test_duplicate_headlines(self):
        with self.assertRaises(m.HeadlineError):
            m.headline_from_readme(_readme() + _readme(preamble=False))


class TestMain(RunMixin, unittest.TestCase):
    def test_matching_headline_passes(self):
        self.assertEqual(self.run_check(_readme(9, 11, "null"), _record(9, 11)), 0)

    def test_wrong_met_fails(self):
        self.assertEqual(self.run_check(_readme(5, 11, "null"), _record(9, 11)), 1)

    def test_wrong_total_fails(self):
        """The 9/14 a naive all-entries count would produce must be rejected."""
        self.assertEqual(self.run_check(_readme(9, 14, "null"), _record(9, 11)), 1)

    def test_wrong_tier_fails(self):
        self.assertEqual(self.run_check(_readme(9, 11, "T1"), _record(9, 11, tier=None)), 1)

    def test_missing_headline_fails_loudly(self):
        self.assertEqual(self.run_check("# Block\n\nnothing here\n", _record()), 2)

    def test_unreadable_record_fails_loudly(self):
        with tempfile.TemporaryDirectory() as d:
            readme = Path(d) / "README.md"
            readme.write_text(_readme(), encoding="utf-8")
            record = Path(d) / "t1-tier-report.json"
            record.write_text("{not json", encoding="utf-8")
            self.assertEqual(m.main(["x", str(readme), str(record)]), 2)

    def test_missing_files_fail_loudly(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                m.main(["x", str(Path(d) / "nope.md"), str(Path(d) / "nope.json")]), 2
            )


class TestCommittedTree(unittest.TestCase):
    """The committed README and record must agree -- this is the check on `main`."""

    def test_committed_record_is_9_of_11(self):
        doc = json.loads((ROOT / "signoff" / "records" / "t1-tier-report.json").read_text())
        self.assertEqual(m.counts_from_record(doc), (9, 11, "null"))

    def test_committed_readme_matches_the_record(self):
        self.assertEqual(m.main(["check-t1-headline.py"]), 0)


if __name__ == "__main__":
    unittest.main()
