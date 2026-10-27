"""Item 5 envelopes (issue #449) must agree with the rollup they wrap.

Needs nothing but python3. Checks that signoff/make_item5_envelope.py's
committed output is current, that each envelope cites the record
measurements/characterization.md cites, and that each envelope's verdict equals
that record's verdict there -- a wrap must never grade a row differently from
the evidence it copies.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "signoff"))
import make_item5_envelope as m  # noqa: E402

# characterization.md verdict -> envelope status. A PVT-subset FAIL is still fail.
_ROW_BENCH = {
    "Dropout @ 50 mA": "dropout-vs-load", "Line regulation": "line-regulation",
    "Load regulation (0–50 mA)": "load-regulation", "Load transient": "load-transient",
    "PSRR": "psrr-dc", "Iq (excl. load current)": "iq", "Current limit": "current-limit",
    "Startup / soft-start": "startup", "Enable / shutdown": "enable-shutdown",
    "Thermal": "thermal", "Stability": "loop-gain",
}


def _rollup() -> dict[str, tuple[str, str]]:
    out = {}
    for line in (ROOT / "measurements" / "characterization.md").read_text().splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 4 and cells[0] in _ROW_BENCH:
            rec = re.search(r"/records/([\w-]+)\.md", cells[3])
            out[_ROW_BENCH[cells[0]]] = (rec.group(1), "fail" if "FAIL" in cells[2] else "pass")
    return out


class Item5Envelopes(unittest.TestCase):
    def test_committed_envelopes_are_current(self):
        for bench, rid in m.RECORDS:
            path = m.output_path(bench, rid)
            self.assertTrue(path.is_file(), path)
            self.assertEqual(path.read_text(), m.envelope_text(bench, rid), path.name)

    def test_records_and_verdicts_match_characterization(self):
        rollup = _rollup()
        self.assertEqual(set(rollup), set(_ROW_BENCH.values()))
        for bench, rid in m.RECORDS:
            char_rid, verdict = rollup[bench]
            self.assertEqual(rid, char_rid, bench)
            env = json.loads(m.output_path(bench, rid).read_text())
            self.assertEqual(env["status"], verdict, bench)

    def test_tagged_measurements_carry_ratified_bounds(self):
        for bench, rid in m.RECORDS:
            env = json.loads(m.output_path(bench, rid).read_text())
            for meas in env["measurements"]:
                if "spec_row" in meas:
                    row, bound = m.RATIFIED[bench][meas["name"]]
                    self.assertEqual(meas["spec_row"], row)
                    self.assertEqual(meas["limits"], bound)

    def test_every_citation_has_its_own_manifest_pin(self):
        man = json.loads((ROOT / "signoff" / "block-manifest.json").read_text())
        pins = json.loads((ROOT / "signoff" / "artifact-pins.json").read_text())["pins"]
        cited = {c["file"]: c["content_hash"] for c in man["evidence"]["5"]}
        self.assertEqual(set(cited), {m.output_path(b, r).relative_to(ROOT).as_posix() for b, r in m.RECORDS})
        for f, h in cited.items():
            self.assertTrue(
                any(p["item"] == "5" and p["cited_envelope"] == f and p["sha256"] == h and p["manifest_pinned"] for p in pins), f)

    def test_subset_record_is_never_a_full_pass(self):
        env = json.loads(m.output_path("dropout-vs-load", "20261011-092557-7a4e0cc").read_text())
        self.assertTrue(env["source_record"]["matrix_is_subset"])
        self.assertNotEqual(env["status"], "pass")

    def test_limit_disagreeing_with_ratified_bound_is_refused(self):
        orig = m.RATIFIED["iq"]["iq_no_load_ua"]
        m.RATIFIED["iq"]["iq_no_load_ua"] = ("iq", {"max": 29})
        try:
            with self.assertRaises(m.WrapError):
                m.build_envelope("iq", "20260910-034648-6c0436d")
        finally:
            m.RATIFIED["iq"]["iq_no_load_ua"] = orig


if __name__ == "__main__":
    unittest.main()
