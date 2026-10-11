"""Coverage for measurements/check_spec_status_counts.py (#325)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

M = Path(__file__).resolve().parent.parent
_s = importlib.util.spec_from_file_location("check_spec_status_counts", M / "check_spec_status_counts.py")
mod = importlib.util.module_from_spec(_s)
_s.loader.exec_module(mod)


class SpecStatusCounts(unittest.TestCase):
    def test_live_spec_is_clean(self):
        self.assertEqual(mod.find_violations(mod.SPEC.read_text()), [])

    def test_catches_reintroduced_counts(self):
        for tok in ("6/45", "12/15", "177/200", "0/45"):
            row = f"| Dropout | x | y | G | Current implementation: FAIL ({tok} PVT corners). |"
            self.assertEqual([t for _, t in mod.find_violations(row)], [tok])

    def test_ignores_prose_outside_table_rows(self):
        self.assertEqual(mod.find_violations("Corners pass 45/45 here.\n"), [])

    def test_ignores_non_count_tokens(self):
        self.assertEqual(mod.find_violations("| a | 1/450 | 5/15x | b | 1/f |"), [])


if __name__ == "__main__":
    unittest.main()
