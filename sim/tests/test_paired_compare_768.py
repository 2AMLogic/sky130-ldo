"""Issue #768: PDK-free controls for the shared engine-version rule.

These exercise _paired_compare.engine_version alone; they are not simulator
evidence. Each comparator's own test file covers its loader and CLI.
"""

from __future__ import annotations

import sys
import unittest

from test_corner_run import SIM_DIR

sys.path.insert(0, str(SIM_DIR / "bin"))
import _paired_compare as pc


class EngineVersionTests(unittest.TestCase):
    def test_one_known_version(self):
        self.assertEqual(pc.engine_version(["46"]), "46")

    def test_numeric_version_is_normalized_to_its_string(self):
        self.assertEqual(pc.engine_version([46]), "46")

    def test_every_response_agreeing_is_that_version(self):
        self.assertEqual(pc.engine_version(["46", "46", "46"]), "46")

    def test_absent_or_null_in_any_response_is_none(self):
        for versions in ([None], [None, None], ["46", None], [None, "46", "46"]):
            with self.subTest(versions=versions):
                self.assertIsNone(pc.engine_version(versions))

    def test_conflicting_versions_are_none(self):
        self.assertIsNone(pc.engine_version(["46", "47"]))
        self.assertIsNone(pc.engine_version(["46", "46", "47"]))

    def test_no_responses_is_none(self):
        self.assertIsNone(pc.engine_version([]))


class VerdictTests(unittest.TestCase):
    """A missing remote version must not equal any local engine string."""

    def test_missing_remote_engine_is_never_equivalent(self):
        tols = {"v": (1e-6, "V")}
        for local_engine in ("None", "46", None):
            with self.subTest(local_engine=local_engine):
                rep = pc.compare(
                    tols, {"v": 1.0}, {"v": 1.0}, None, local_engine, False, False
                )
                self.assertEqual(rep["verdict"], "engine_mismatch")
                self.assertIsNone(rep["remote_engine"])
                self.assertFalse(rep["equivalence_claimable"])


if __name__ == "__main__":
    unittest.main()
