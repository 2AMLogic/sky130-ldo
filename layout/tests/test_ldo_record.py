"""Tests for the dual-deck DRC gate of the ldo-core layout record (issue #260).

Fixture-based, standard library only. They cover the fail-closed behaviour a
live run cannot easily exercise: a clean curated deck must not mask a dirty or
non-running official deck, and a tool exit status of 0 -- or an empty /
truncated / structurally empty report -- must never read as "zero violations".
The live behaviour against the pinned PDK deck is the minted record's job.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN_DIR))

import _official_drc as od  # noqa: E402

CELL = "ldo_core"

HEADER = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
 <description>SKY130 DRC runset</description>
 <top-cell>{top}</top-cell>
 <categories>
  <category><name>via.1a_b</name><description>d</description><categories/></category>
  <category><name>m2.5</name><description>d</description><categories/></category>
 </categories>
"""

ITEM = """  <item>
   <category>'{rule}'</category>
   <cell>{cell}</cell>
   <values><value>{value}</value></values>
  </item>
"""


def lyrdb(items=(), top=CELL, with_items=True, categories=True, truncate=False) -> str:
    text = HEADER.format(top=top)
    if not categories:
        text = text.replace(text[text.index(" <categories>") : text.index(" </categories>") + 15], " <categories/>\n")
    if with_items:
        text += " <items>\n"
        for rule, value in items:
            text += ITEM.format(rule=rule, cell=top, value=value)
        text += " </items>\n"
    text += "</report-database>\n"
    return text[: len(text) // 2] if truncate else text


RUN_OK = {"deck_present": True, "klayout_found": True, "exit_code": 0, "deck_name": "sky130A_mr.drc"}
POLY = "polygon: (0,0;0,0.16;0.16,0.16;0.16,0)"


def write_out(d: Path, run=RUN_OK, report: str | None = None) -> Path:
    if run is not None:
        (d / "mr-drc.run.json").write_text(json.dumps(run))
    if report is not None:
        (d / "mr-drc.lyrdb").write_text(report)
    return d


class OfficialResultTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(prefix="out dir ")  # spaces on purpose
        self.d = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def res(self):
        return od.official_result(self.d, CELL)

    def test_zero_markers_with_valid_structure_is_clean(self):
        write_out(self.d, report=lyrdb())
        r = self.res()
        self.assertEqual(r.state, "clean")
        self.assertEqual(r.total, 0)
        self.assertEqual(r.rule_count, 2)

    def test_markers_counted_per_family(self):
        items = [("via.1a_b", POLY)] * 3 + [("m2.5", POLY)]
        write_out(self.d, report=lyrdb(items))
        r = self.res()
        self.assertEqual(r.state, "violations")
        self.assertEqual(r.total, 4)
        self.assertEqual(r.counts, {"m2.5": 1, "via.1a_b": 3})

    def test_missing_run_record_is_error(self):
        write_out(self.d, run=None, report=lyrdb())
        self.assertEqual(self.res().state, "error")

    def test_unparseable_run_record_is_error(self):
        (self.d / "mr-drc.run.json").write_text("{not json")
        (self.d / "mr-drc.lyrdb").write_text(lyrdb())
        self.assertEqual(self.res().state, "error")

    def test_missing_deck_is_error_even_with_a_clean_looking_report(self):
        write_out(self.d, run={**RUN_OK, "deck_present": False}, report=lyrdb())
        r = self.res()
        self.assertEqual(r.state, "error")
        self.assertIn("deck", r.detail)

    def test_missing_klayout_is_error(self):
        write_out(self.d, run={**RUN_OK, "klayout_found": False, "exit_code": None}, report=lyrdb())
        self.assertEqual(self.res().state, "error")

    def test_nonzero_klayout_exit_is_error_even_with_report_present(self):
        write_out(self.d, run={**RUN_OK, "exit_code": 1}, report=lyrdb())
        self.assertEqual(self.res().state, "error")

    def test_null_exit_code_is_error(self):
        write_out(self.d, run={**RUN_OK, "exit_code": None}, report=lyrdb())
        self.assertEqual(self.res().state, "error")

    def test_absent_report_is_error(self):
        write_out(self.d)
        self.assertEqual(self.res().state, "error")

    def test_empty_report_is_error(self):
        write_out(self.d, report="")
        self.assertEqual(self.res().state, "error")

    def test_truncated_report_is_error(self):
        write_out(self.d, report=lyrdb([("m2.5", POLY)] * 5, truncate=True))
        self.assertEqual(self.res().state, "error")

    def test_report_without_items_section_is_error(self):
        write_out(self.d, report=lyrdb(with_items=False))
        self.assertEqual(self.res().state, "error")

    def test_report_without_rule_categories_is_error(self):
        write_out(self.d, report=lyrdb(categories=False))
        self.assertEqual(self.res().state, "error")

    def test_wrong_top_cell_is_error(self):
        write_out(self.d, report=lyrdb(top="other_cell"))
        self.assertEqual(self.res().state, "error")

    def test_wrong_root_is_error(self):
        write_out(self.d, report="<html><body/></html>")
        self.assertEqual(self.res().state, "error")

    def test_marker_without_category_is_error(self):
        bad = lyrdb().replace(" </items>", "  <item><category></category><cell>c</cell></item>\n </items>")
        write_out(self.d, report=bad)
        self.assertEqual(self.res().state, "error")


class OverallPassTests(unittest.TestCase):
    clean = od.OfficialResult("clean", "")
    dirty = od.OfficialResult("violations", "", 1, {"m2.5": 1})
    err = od.OfficialResult("error", "")

    def test_pass_needs_every_gate(self):
        self.assertTrue(od.overall_pass("clean", self.clean, True, True))

    def test_one_official_marker_fails(self):
        self.assertFalse(od.overall_pass("clean", self.dirty, True, True))

    def test_official_error_fails(self):
        self.assertFalse(od.overall_pass("clean", self.err, True, True))

    def test_dirty_curated_fails_with_clean_official(self):
        self.assertFalse(od.overall_pass("violations", self.clean, True, True))
        self.assertFalse(od.overall_pass(None, self.clean, True, True))
        self.assertFalse(od.overall_pass("error", self.clean, True, True))

    def test_existing_device_and_routing_gates_still_apply(self):
        self.assertFalse(od.overall_pass("clean", self.clean, False, True))
        self.assertFalse(od.overall_pass("clean", self.clean, True, False))


class RenderEndToEndTests(unittest.TestCase):
    """Run render-ldo-record.py on a fixture directory with a stub `klt`."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory(prefix="render dir ")
        self.d = Path(self._t.name)
        self.out = self.d / "rec"
        self.out.mkdir()
        klt = self.d / "klt stub"
        klt.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            "  --version) echo 'klt stub 0';;\n"
            "  pdk) echo '{\"variant\": \"sky130A\", \"version\": \"stub\"}';;\n"
            "esac\n"
        )
        klt.chmod(klt.stat().st_mode | stat.S_IXUSR)
        self.klt = klt
        (self.out / "floorplan.json").write_text(
            json.dumps({"device_count": 1, "routing": {"net_count": 1, "terminal_count": 2}})
        )
        (self.out / "compose.json").write_text(json.dumps({"blocks": [{"id": "M"}], "unrouted_nets": []}))

    def tearDown(self):
        self._t.cleanup()

    def render(self, curated="clean", run=RUN_OK, report=None):
        (self.out / "drc.json").write_text(json.dumps({"status": curated, "violation_count": 0}))
        for name in ("mr-drc.run.json", "mr-drc.lyrdb"):
            p = self.out / name
            if p.exists():
                p.unlink()
        write_out(self.out, run=run, report=report)
        repo = Path(__file__).resolve().parents[2]
        proc = subprocess.run(
            [
                sys.executable, str(BIN_DIR / "render-ldo-record.py"),
                "--out-dir", str(self.out), "--record-id", "t", "--repo-root", str(repo),
                "--klt", str(self.klt), "--pdk-variant", "sky130A", "--cell-name", CELL,
                "--schematic-sha", "abc",
            ],
            capture_output=True, text=True, env={**os.environ},
        )
        return proc

    def test_both_clean_is_pass_exit_zero(self):
        p = self.render(report=lyrdb())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("## Overall verdict: PASS", p.stdout)

    def test_one_official_marker_is_fail_nonzero_with_counts(self):
        p = self.render(report=lyrdb([("m2.5", POLY)]))
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("## Overall verdict: FAIL", p.stdout)
        self.assertIn("| `m2.5` | 1 |", p.stdout)
        self.assertIn("| **total** | **1** |", p.stdout)

    def test_dirty_curated_clean_official_is_fail(self):
        p = self.render(curated="violations", report=lyrdb())
        self.assertEqual(p.returncode, 1)
        self.assertIn("## Overall verdict: FAIL", p.stdout)

    def test_missing_official_report_is_fail_not_pass(self):
        p = self.render(report=None)
        self.assertEqual(p.returncode, 1)
        self.assertIn("## Overall verdict: FAIL", p.stdout)
        self.assertIn("did not complete", p.stdout)

    def test_truncated_official_report_is_fail(self):
        p = self.render(report=lyrdb([("m2.5", POLY)], truncate=True))
        self.assertEqual(p.returncode, 1)
        self.assertIn("## Overall verdict: FAIL", p.stdout)

    def test_missing_curated_envelope_still_renders_a_fail_record(self):
        (self.out / "drc.json").write_text("")
        write_out(self.out, report=lyrdb())
        p = self.render_without_resetting_drc()
        self.assertEqual(p.returncode, 1)
        self.assertIn("## Overall verdict: FAIL", p.stdout)

    def render_without_resetting_drc(self):
        repo = Path(__file__).resolve().parents[2]
        return subprocess.run(
            [
                sys.executable, str(BIN_DIR / "render-ldo-record.py"),
                "--out-dir", str(self.out), "--record-id", "t", "--repo-root", str(repo),
                "--klt", str(self.klt), "--pdk-variant", "sky130A", "--cell-name", CELL,
                "--schematic-sha", "abc",
            ],
            capture_output=True, text=True,
        )


if __name__ == "__main__":
    unittest.main()
