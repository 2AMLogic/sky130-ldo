"""PDK-free verdict tests for the layout evidence renderers (issues #278, #306).

Pins the verdict logic that `record.md` headlines ("Item 11 verdict: MET",
"Overall verdict: MATCH") to one passing case and one negative control per
clause, so a dropped conjunct (e.g. the `bool(ties)` guard) fails CI.

Issue #306 extends the boundary to the cap-rail demonstrator, the folded-resistor
PVT study and qualification renderer, the trivial-cell record and the
official-DRC marker-family summary. Where a committed record can be replayed
without a PDK, the regression classes re-render it and require byte-identical
output; where it cannot (the PVT study's simulations, the KLayout geometry
census), they compare the helper against a frozen copy of the pre-extraction
inline logic on inputs derived from committed files.

Standard library only; runs in the headless `checks` job (no klayout wheel).
The scripts' filenames contain hyphens, so they are loaded by path.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import itertools
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from decimal import Decimal
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parents[1] / "bin"
LAYOUT = BIN.parent
sys.path.insert(0, str(BIN))


def _load(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, BIN / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


erc = _load("render-ldo-erc-record.py", "render_ldo_erc_record")
lvs = _load("render-ldo-lvs-record.py", "render_ldo_lvs_record")
area = _load("render-ldo-area-record.py", "render_ldo_area_record")
cap_rail = _load("render-cap-rail-record.py", "render_cap_rail_record")
fr_pvt = _load("run-folded-res-pvt.py", "run_folded_res_pvt")
fr_qual = _load("render-folded-res-qual-record.py", "render_folded_res_qual_record")
trivial = _load("render-record.py", "render_record")

import _official_drc as od  # noqa: E402
import _record_common as record_common  # noqa: E402

CAP_RAIL_RECORD = LAYOUT / "cap-rail-demo" / "reports" / "20261010-033947-80bc87e"
QUAL_RECORDS = [
    LAYOUT / "folded-res-qual" / "reports" / rid
    for rid in ("20261010-032804-ea209d2", "20261010-033502-704005c")
]
TRIVIAL_RECORD = LAYOUT / "trivial-cell" / "reports" / "20260814-002846-42bbf2e"
OFFICIAL_DRC_RECORD = LAYOUT / "ldo-core" / "reports" / "20261010-045715-e17e713"
PVT_MATRIX = json.loads((LAYOUT / "folded-res-qual" / "pvt" / "matrix.json").read_text())


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

    def test_unavailable_crosscheck_asserts_no_agreement(self):
        note = area._crosscheck_note({"status": "unavailable", "detail": "x"})
        self.assertIn("no independent agreement is asserted", note)
        self.assertEqual(area._crosscheck_note({"status": "agrees"}), "")
        self.assertIn("DISAGREES", area._crosscheck_note({"status": "DISAGREES"}))


class AreaCoverageTests(unittest.TestCase):
    """Issue #318: every area record discloses what its footprint does not
    cover -- undrawn capacitors, the official-DRC result for that exact
    layout record, LVS freshness against the measured bytes, and the
    standalone capacitor demonstrator cited separately."""

    SHA = "a" * 64

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.reports = self.tmp / "reports"
        self.layout_dir = self.reports / "L1"
        self.layout_dir.mkdir(parents=True)
        self.demo = self.tmp / "demo"
        (self.demo / "D1").mkdir(parents=True)
        (self.demo / "LATEST").write_text("D1\n")
        (self.layout_dir / "floorplan.json").write_text(json.dumps({
            "mos_count": 2, "res_count": 1, "block_count": 3,
            "undrawn_elements": ["C_A X Y 1p m=1", "C_B X 0 2p m=1"],
            "devices": [
                {"name": "M_SMALL", "kind": "mos", "w_total_um": 10.0, "units": 1, "unit_w_um": 10.0, "l_um": 1},
                {"name": "M_BIG", "kind": "mos", "w_total_um": 400.0, "units": 4, "unit_w_um": 100.0, "l_um": 0.5},
                {"name": "R_X", "kind": "res", "w_total_um": None},
            ],
        }))
        lvs_dir = self.reports / "V1"
        lvs_dir.mkdir()
        (lvs_dir / "lvs.json").write_text(json.dumps({"status": "match", "environment": {"layout_sha256": "b" * 64}}))
        (self.reports / "LATEST-LVS").write_text("V1\n")

    def cov(self):
        return area.coverage_disclosure(
            self.layout_dir, self.SHA, "ldo_core", reports=self.reports,
            cap_demo_reports=self.demo, root=self.tmp,
        )

    def test_undrawn_capacitors_and_inventory_are_read_from_floorplan(self):
        c = self.cov()
        self.assertEqual(c["undrawn_elements"], ["C_A", "C_B"])
        self.assertIn("not evidence that a complete, capacitor-inclusive core", c["statement"])
        self.assertEqual((c["inventory"]["mos_count"], c["inventory"]["res_count"]), (2, 1))
        self.assertEqual(c["inventory"]["widest_mos"]["name"], "M_BIG")
        self.assertEqual(c["inventory"]["widest_mos"]["units"], 4)

    def test_lvs_of_other_bytes_is_stale_even_when_it_matched(self):
        c = self.cov()
        self.assertEqual(c["lvs"]["freshness"], "STALE")
        self.assertIn("**STALE**", area.coverage_markdown(c))

    def test_lvs_of_the_same_bytes_is_fresh(self):
        (self.reports / "V1" / "lvs.json").write_text(
            json.dumps({"status": "match", "environment": {"layout_sha256": "sha256:" + self.SHA}}))
        self.assertEqual(self.cov()["lvs"]["freshness"], "fresh")

    def test_missing_official_run_is_not_clean(self):
        c = self.cov()
        self.assertEqual(c["official_drc"]["state"], "not run")
        (self.layout_dir / "mr-drc.run.json").write_text(json.dumps(
            {"deck_present": True, "klayout_found": True, "exit_code": 0}))
        self.assertEqual(self.cov()["official_drc"]["state"], "error")  # no lyrdb: fail closed

    def test_demonstrator_cited_separately_and_not_as_core_evidence(self):
        c = self.cov()
        self.assertFalse(c["capacitor_demonstrator"]["certifies_core"])
        self.assertIn("do not certify this core", area.coverage_markdown(c))

    def test_missing_floorplan_is_never_read_as_complete(self):
        (self.layout_dir / "floorplan.json").unlink()
        c = self.cov()
        self.assertEqual(c["inventory"]["status"], "unavailable")
        self.assertIn("could not be read", c["statement"])


# --- issue #306: cap-rail demonstrator ---------------------------------------


class CapRailVerdictTests(unittest.TestCase):
    CORE = {"area_um2": 76813.0, "area_mm2": 0.076813, "below_limit": True, "margin_fraction": 0.23}
    TOTALS = {"cap_block_um2": 50000.0, "overlay_usable_um2": 60000.0, "side_by_side_area_um2": 120000.0}
    SINGLE = 89000.0

    def verdict(self, core=None, totals=None, single=None, gates_ok=True):
        return cap_rail.feasibility_verdict(
            core or self.CORE, totals or self.TOTALS, self.SINGLE if single is None else single, gates_ok
        )

    def test_all_conjuncts_hold_is_feasible(self):
        v = self.verdict()
        self.assertTrue(v["below_limit"])
        self.assertTrue(v["caps_fit_in_overlay"])
        self.assertTrue(v["feasible_geometrically"])

    def test_core_not_below_limit_is_not_feasible(self):
        v = self.verdict(core={**self.CORE, "below_limit": False})
        self.assertTrue(v["caps_fit_in_overlay"])  # other input preserved
        self.assertFalse(v["feasible_geometrically"])

    def test_caps_not_fitting_overlay_is_not_feasible(self):
        v = self.verdict(totals={**self.TOTALS, "cap_block_um2": 60000.1})
        self.assertTrue(v["below_limit"])
        self.assertFalse(v["caps_fit_in_overlay"])
        self.assertFalse(v["feasible_geometrically"])

    def test_overlay_fit_is_inclusive(self):
        v = self.verdict(totals={**self.TOTALS, "cap_block_um2": 60000.0})
        self.assertTrue(v["caps_fit_in_overlay"])
        self.assertTrue(v["feasible_geometrically"])

    def test_failed_gate_is_not_feasible(self):
        v = self.verdict(gates_ok=False)
        self.assertTrue(v["below_limit"])
        self.assertTrue(v["caps_fit_in_overlay"])
        self.assertFalse(v["feasible_geometrically"])

    def test_counterfactual_fields(self):
        v = self.verdict()
        self.assertEqual(v["limit_um2"], cap_rail.plan.LIMIT_UM2)
        self.assertFalse(v["side_by_side_below_limit"])  # 120000 >= 100000
        self.assertFalse(v["single_mim_level_fits_overlay"])  # 89000 > 60000
        self.assertTrue(self.verdict(single=60000.0)["single_mim_level_fits_overlay"])


class CapRailGateTests(unittest.TestCase):
    def kwargs(self, **over):
        base = dict(
            drc={"status": "clean", "violation_count": 0},
            mr={},
            mr_rules=237,
            lvs={"status": "match"},
            neg_value={"status": "mismatch"},
            neg_net={"status": "mismatch"},
        )
        base.update(over)
        return base

    def test_all_gates_hold(self):
        g = cap_rail.gate_flags(**self.kwargs())
        self.assertEqual(
            g, {"drc_clean": True, "mr_clean": True, "lvs_match": True, "negs_ok": True, "gates_ok": True}
        )

    def test_each_gate_negative_control(self):
        cases = {
            "klt_drc_status": dict(drc={"status": "violations", "violation_count": 0}),
            "klt_drc_count": dict(drc={"status": "clean", "violation_count": 1}),
            "official_markers": dict(mr={"m2.5": 1}),
            "official_no_rules": dict(mr_rules=0),
            "lvs_mismatch": dict(lvs={"status": "mismatch"}),
            "neg_value_matched": dict(neg_value={"status": "match"}),
            "neg_net_matched": dict(neg_net={"status": "error"}),
        }
        for name, over in cases.items():
            with self.subTest(name):
                self.assertFalse(cap_rail.gate_flags(**self.kwargs(**over))["gates_ok"])


# --- issue #306: folded-resistor PVT study control check ----------------------


def _legacy_control_check(quals, controls):
    """Frozen pre-extraction copy of run-folded-res-pvt.py's inline logic."""
    ctl_fail = [q for q in quals if q["control"] and q["det_ok"]]
    control_ok = not ctl_fail
    control_check = ("The known nonequivalent control(s) "
                     + ", ".join(f"{d} N={n}" for d, ns in controls.items() for n in ns)
                     + (" FAILED the deterministic criterion as required (study valid)." if control_ok
                        else " PASSED the deterministic criterion: the study is INVALID."))
    return control_ok, control_check, 0 if control_ok else 1


def _q(device, segments, det_ok, control):
    return {"device": device, "segments": segments, "det_ok": det_ok, "control": control}


class FoldedResControlTests(unittest.TestCase):
    CONTROLS = {"R_BIAS": [16], "R_FB_A": []}

    def test_failing_controls_make_a_valid_study(self):
        quals = [_q("R_BIAS", 4, True, False), _q("R_BIAS", 16, False, True)]
        d = fr_pvt.control_decision(quals, self.CONTROLS)
        self.assertTrue(d.ok)
        self.assertEqual(d.exit_code, 0)
        self.assertEqual(
            d.message,
            "The known nonequivalent control(s) R_BIAS N=16 FAILED the deterministic criterion "
            "as required (study valid).",
        )

    def test_one_passing_control_invalidates_the_study(self):
        quals = [_q("R_BIAS", 4, True, False), _q("R_BIAS", 16, True, True)]
        d = fr_pvt.control_decision(quals, self.CONTROLS)
        self.assertFalse(d.ok)
        self.assertEqual(d.exit_code, 1)
        self.assertTrue(d.message.endswith(" PASSED the deterministic criterion: the study is INVALID."))

    def test_passing_non_control_rows_do_not_invalidate(self):
        quals = [_q("R_BIAS", n, True, False) for n in (2, 4, 8)] + [_q("R_FB_A", 6, True, False)]
        d = fr_pvt.control_decision(quals, self.CONTROLS)
        self.assertTrue(d.ok)
        self.assertEqual(d.exit_code, 0)

    def test_no_rows_is_valid(self):
        self.assertEqual(fr_pvt.control_decision([], self.CONTROLS).exit_code, 0)

    def test_multiple_declared_controls_all_named(self):
        controls = {"R_BIAS": [12, 16], "R_FB_A": [6]}
        quals = [_q("R_BIAS", 12, False, True), _q("R_BIAS", 16, False, True), _q("R_FB_A", 6, False, True)]
        d = fr_pvt.control_decision(quals, controls)
        self.assertTrue(d.ok)
        self.assertIn("control(s) R_BIAS N=12, R_BIAS N=16, R_FB_A N=6 FAILED", d.message)
        # Any single one of them passing invalidates the study.
        for i in range(len(quals)):
            with self.subTest(passing=i):
                flipped = [dict(q, det_ok=(j == i)) for j, q in enumerate(quals)]
                d = fr_pvt.control_decision(flipped, controls)
                self.assertFalse(d.ok)
                self.assertEqual(d.exit_code, 1)
                self.assertIn("the study is INVALID", d.message)


class FoldedResControlRegressionTests(unittest.TestCase):
    """The committed PVT record is BLOCKED (no qualification rows), so the
    helper inputs are derived from the committed matrix.json through the real
    `_folded_res_pvt.qualification()` and compared to the frozen inline copy."""

    def quals(self, det_ok):
        import _folded_res_pvt as pvt

        det, agg = [], {}
        for dev in PVT_MATRIX["devices"]:
            name = dev["schematic_device"]
            for n in dev["candidate_segments"]:
                verdict = "EQUIVALENT" if det_ok(name, n) else "NOT EQUIVALENT"
                for mode in ("j1", "j4"):
                    det.append({"device": name, "segments": n, "mode": mode, "verdict": verdict,
                                "worst_abs_shift": 0.0})
                agg[(name, n, "j1")] = {"m1": True, "m2": True}
        return pvt.qualification(det, agg, PVT_MATRIX)

    def test_matches_pre_extraction_logic_on_matrix_derived_rows(self):
        controls = {d["schematic_device"]: d["control_segments"] for d in PVT_MATRIX["devices"]}
        self.assertTrue(any(controls.values()), "matrix.json declares no control")
        scenarios = {
            "controls_fail_as_required": lambda name, n: n not in controls[name],
            "everything_equivalent": lambda name, n: True,
            "nothing_equivalent": lambda name, n: False,
            "small_n_only": lambda name, n: n <= 4,
        }
        for label, det_ok in scenarios.items():
            with self.subTest(label):
                quals = self.quals(det_ok)
                d = fr_pvt.control_decision(quals, controls)
                self.assertEqual((d.ok, d.message, d.exit_code), _legacy_control_check(quals, controls))
        self.assertEqual(fr_pvt.control_decision(self.quals(scenarios["controls_fail_as_required"]),
                                                 controls).exit_code, 0)
        self.assertEqual(fr_pvt.control_decision(self.quals(scenarios["everything_equivalent"]),
                                                 controls).exit_code, 1)

    def test_exhaustive_small_grid_matches_pre_extraction_logic(self):
        controls = {"R_BIAS": [8, 16], "R_FB_A": [6]}
        keys = [("R_BIAS", 4, False), ("R_BIAS", 8, True), ("R_BIAS", 16, True), ("R_FB_A", 6, True)]
        for bits in itertools.product((False, True), repeat=len(keys)):
            quals = [_q(dev, n, ok, ctl) for (dev, n, ctl), ok in zip(keys, bits)]
            d = fr_pvt.control_decision(quals, controls)
            self.assertEqual((d.ok, d.message, d.exit_code), _legacy_control_check(quals, controls))

    def test_main_uses_the_helper(self):
        src = (BIN / "run-folded-res-pvt.py").read_text()
        self.assertIn("decision = control_decision(quals, controls)", src)
        self.assertIn("return decision.exit_code", src)
        self.assertEqual(src.count('q["control"] and q["det_ok"]'), 1)


# --- issue #306: folded-resistor qualification renderer -----------------------


class FoldedResQualVerdictTests(unittest.TestCase):
    ROW = {"schematic_device": "R_BIAS", "segments": 4, "joints_included": True,
           "delta_frac": 0.00123, "delta_ohm": 1.5, "tolerance_frac": 0.00246, "verdict": "EQUIVALENT"}

    def test_equivalent_row(self):
        self.assertEqual(fr_qual.displayed_verdict(self.ROW), "EQUIVALENT")
        self.assertEqual(fr_qual.electrical_cells(self.ROW), ("+0.123% (+1.5 ohm)", "0.246%", "EQUIVALENT"))

    def test_non_equivalent_row(self):
        row = dict(self.ROW, delta_frac=-0.01, delta_ohm=-12.0, verdict="NOT EQUIVALENT")
        self.assertEqual(fr_qual.displayed_verdict(row), "NOT EQUIVALENT")
        self.assertEqual(fr_qual.electrical_cells(row), ("-1.000% (-12.0 ohm)", "0.246%", "NOT EQUIVALENT"))

    def test_missing_row_is_na(self):
        self.assertEqual(fr_qual.displayed_verdict(None), "n/a")
        self.assertEqual(fr_qual.electrical_cells(None), ("n/a", "n/a", "n/a"))

    def test_drawn_row_matches_device_segments_and_joints(self):
        summary = {"electrical": {"rows": [dict(self.ROW, joints_included=False), self.ROW]}}
        case = {"schematic_device": "R_BIAS", "segments": 4}
        self.assertIs(fr_qual.drawn_row(summary, case), summary["electrical"]["rows"][1])
        self.assertIsNone(fr_qual.drawn_row(summary, {"schematic_device": "R_BIAS", "segments": 8}))

    def test_render_case_without_electrical_row_shows_na(self):
        summary = json.loads((QUAL_RECORDS[-1] / "summary.json").read_text())
        case = summary["cases"][0]
        summary["electrical"]["rows"] = [
            r for r in summary["electrical"]["rows"]
            if not (r["schematic_device"] == case["schematic_device"] and r["segments"] == case["segments"])
        ]
        line = next(ln for ln in fr_qual.render(summary).splitlines() if ln.startswith(f"| `{case['case']}` |"))
        self.assertTrue(line.endswith("| n/a | n/a | **n/a** |"), line)


class FoldedResQualRegressionTests(unittest.TestCase):
    def test_committed_records_render_byte_identically(self):
        for rec in QUAL_RECORDS:
            with self.subTest(rec.name):
                summary = json.loads((rec / "summary.json").read_text())
                self.assertEqual(fr_qual.render(summary), (rec / "record.md").read_text())

    def test_committed_verdict_column_comes_from_the_helper(self):
        for rec in QUAL_RECORDS:
            summary = json.loads((rec / "summary.json").read_text())
            for cs in summary["cases"]:
                with self.subTest(rec=rec.name, case=cs["case"]):
                    verdict = fr_qual.displayed_verdict(fr_qual.drawn_row(summary, cs))
                    self.assertIn(verdict, ("EQUIVALENT", "NOT EQUIVALENT"))
                    self.assertIn(f"| **{verdict}** |", (rec / "record.md").read_text())


# --- issue #306: trivial-cell record -------------------------------------------


class TrivialCellVerdictTests(unittest.TestCase):
    GOOD = dict(
        drc={"status": "clean"},
        lvs_good={"status": "match"},
        lvs_bad_dev={"status": "mismatch"},
        lvs_bad_topo={"status": "mismatch"},
    )

    def checks(self, **over):
        return trivial.trivial_cell_checks(**{**self.GOOD, **over})

    def test_all_pass(self):
        checks = self.checks()
        self.assertEqual(len(checks), 4)
        self.assertTrue(all(ok for _, ok in checks))
        self.assertTrue(trivial.overall_pass(checks))

    def test_each_conjunct_negative_control(self):
        cases = {
            "DRC on trivial_mos_array is clean": dict(drc={"status": "violations"}),
            "LVS matches the known-good reference": dict(lvs_good={"status": "mismatch"}),
            "LVS negative control (device-parameter corruption) reports mismatch":
                dict(lvs_bad_dev={"status": "match"}),
            "LVS negative control (topology corruption) reports mismatch":
                dict(lvs_bad_topo={"status": "match"}),
        }
        for desc, over in cases.items():
            with self.subTest(desc):
                checks = self.checks(**over)
                self.assertEqual([d for d, ok in checks if not ok], [desc])
                self.assertFalse(trivial.overall_pass(checks))

    def test_missing_status_fails(self):
        self.assertFalse(trivial.overall_pass(self.checks(drc={})))
        self.assertFalse(trivial.overall_pass(self.checks(lvs_bad_topo={})))


class TrivialCellRegressionTests(unittest.TestCase):
    PROV = record_common.Provenance(
        "42bbf2e37d1fa12579f62a2fd3072104a52958a8", "feature/issue-2", True, "klt 0.2.0",
        {"variant": "sky130A", "version": "open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b"},
    )

    def run_main(self, out_dir: Path):
        argv = ["render-record.py", "--out-dir", str(out_dir), "--record-id", TRIVIAL_RECORD.name,
                "--repo-root", ".", "--klt", "klt", "--pdk-variant", "sky130A"]
        buf = io.StringIO()
        with mock.patch.object(trivial, "provenance", return_value=self.PROV), \
                mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf):
            rc = trivial.main()
        return rc, buf.getvalue()

    def test_committed_record_renders_byte_identically(self):
        rc, out = self.run_main(TRIVIAL_RECORD)
        self.assertEqual(rc, 0)
        self.assertEqual(out, (TRIVIAL_RECORD / "record.md").read_text())

    def test_flipped_negative_control_fails_the_record(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            for f in TRIVIAL_RECORD.glob("*.json"):
                shutil.copy(f, d)
            bad = json.loads((d / "lvs.broken-topology.json").read_text())
            bad["status"] = "match"
            (d / "lvs.broken-topology.json").write_text(json.dumps(bad))
            rc, out = self.run_main(d)
        self.assertEqual(rc, 1)
        self.assertIn("## Overall verdict: FAIL", out)
        self.assertIn("- [ ] LVS negative control (topology corruption) reports mismatch", out)


# --- issue #306: cap-rail regression (committed record replay) -----------------


class CapRailRegressionTests(unittest.TestCase):
    INPUTS = ("plan.json", "drc.json", "mr-drc.lyrdb", "extract.json", "pex.json", "lvs.json",
              "lvs-gds-shape.json", "lvs-neg-value.json", "lvs-neg-net.json", "klt-version.json",
              "klayout-version.txt")

    def replay(self, mutate=None):
        committed = json.loads((CAP_RAIL_RECORD / "summary.json").read_text())
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            for name in self.INPUTS:
                shutil.copy(CAP_RAIL_RECORD / name, d)
            if mutate:
                mutate(d)
            argv = ["render-cap-rail-record.py", "--out-dir", str(d), "--record-id", committed["record_id"],
                    "--schematic-sha", committed["schematic_sha"], "--pin", committed["klt_pin"]]
            buf = io.StringIO()
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf):
                rc = cap_rail.main()
            return rc, buf.getvalue(), (d / "summary.json").read_text()

    def test_committed_record_replays_byte_identically(self):
        rc, md, summary = self.replay()
        self.assertEqual(rc, 0)
        self.assertEqual(md, (CAP_RAIL_RECORD / "record.md").read_text())
        self.assertEqual(summary, (CAP_RAIL_RECORD / "summary.json").read_text())

    def test_committed_verdict_from_helper(self):
        pl = json.loads((CAP_RAIL_RECORD / "plan.json").read_text())
        committed = json.loads((CAP_RAIL_RECORD / "summary.json").read_text())
        v = cap_rail.feasibility_verdict(pl["core"], pl["totals"],
                                         committed["single_mim_level_counterfactual"]["block_area_um2"],
                                         committed["gates"]["all_ok"])
        self.assertEqual(json.dumps(v, sort_keys=True), json.dumps(committed["verdict"], sort_keys=True))

    def test_failed_negative_control_flips_verdict_and_exit(self):
        def mutate(d):
            neg = json.loads((d / "lvs-neg-net.json").read_text())
            neg["status"] = "match"
            (d / "lvs-neg-net.json").write_text(json.dumps(neg))

        rc, md, summary = self.replay(mutate)
        self.assertEqual(rc, 1)
        s = json.loads(summary)
        self.assertFalse(s["gates"]["all_ok"])
        self.assertFalse(s["verdict"]["feasible_geometrically"])
        self.assertIn("**Verdict: NOT demonstrated**", md)


# --- issue #306: official-DRC marker-family summary ----------------------------


def _marker(rule, cell, kind="polygon", geometry=None):
    geometry = geometry or f"{kind}: (0,0;1,0;1,1;0,1)"
    return od.Marker(rule, cell, kind, geometry, od._bbox(geometry))


def _legacy_families(report, max_samples):
    """Frozen pre-extraction copy of diagnose-official-drc.py's inline loop."""
    fams = {}
    for fam, items in sorted(report.by_rule.items()):
        cells = Counter(i.cell for i in items)
        samples = []
        for i in items[: max_samples]:
            samples.append({"cell": i.cell, "kind": i.kind, "geometry": i.geometry[:200]})
        fams[fam] = {"count": len(items), "deck_cells": dict(cells.most_common(6)), "sample_markers": samples}
    return fams


class MarkerFamilySummaryTests(unittest.TestCase):
    def report(self):
        long_geom = "edge-pair: " + ";".join(f"({i},{i})" for i in range(100))
        by_rule = {
            "via.1a_b": [_marker("via.1a_b", "ldo_core") for _ in range(4)]
                        + [_marker("via.1a_b", "mos_array$3", "edge-pair", long_geom)],
            "licon.1": [_marker("licon.1", f"cell{c}") for c in "aabbbcdefgh"],
            "m2.5": [_marker("m2.5", "ldo_core", "box", "box: (0,0;2,2)")],
        }
        total = sum(len(v) for v in by_rule.values())
        return od.Report("ldo_core", 3, total, by_rule), long_geom

    def test_family_order_counts_and_cells(self):
        rep, _ = self.report()
        fams = od.summarize_marker_families(rep, 3)
        self.assertEqual(list(fams), ["licon.1", "m2.5", "via.1a_b"])  # sorted, not insertion order
        self.assertEqual({k: v["count"] for k, v in fams.items()}, {"licon.1": 11, "m2.5": 1, "via.1a_b": 5})
        self.assertEqual(fams["via.1a_b"]["deck_cells"], {"ldo_core": 4, "mos_array$3": 1})
        cells = fams["licon.1"]["deck_cells"]
        self.assertEqual(len(cells), 6)  # bounded to the six most frequent
        self.assertEqual(list(cells.items())[:2], [("cellb", 3), ("cella", 2)])
        self.assertEqual(sum(cells.values()), 3 + 2 + 4)

    def test_samples_are_bounded_and_carry_kind_and_geometry(self):
        rep, long_geom = self.report()
        fams = od.summarize_marker_families(rep, 3)
        self.assertEqual(len(fams["licon.1"]["sample_markers"]), 3)
        self.assertEqual(fams["m2.5"]["sample_markers"],
                         [{"cell": "ldo_core", "kind": "box", "geometry": "box: (0,0;2,2)"}])
        full = od.summarize_marker_families(rep, 10)["via.1a_b"]["sample_markers"]
        self.assertEqual(len(full), 5)
        self.assertEqual(full[-1]["kind"], "edge-pair")
        self.assertEqual(full[-1]["geometry"], long_geom[:200])
        self.assertEqual(len(full[-1]["geometry"]), 200)
        self.assertEqual([len(f["sample_markers"]) for f in od.summarize_marker_families(rep, 0).values()],
                         [0, 0, 0])

    def test_empty_report(self):
        self.assertEqual(od.summarize_marker_families(od.Report("ldo_core", 3, 0, {}), 3), {})

    def test_matches_pre_extraction_logic(self):
        rep, _ = self.report()
        for n in (0, 1, 3, 20):
            self.assertEqual(json.dumps(od.summarize_marker_families(rep, n)),
                             json.dumps(_legacy_families(rep, n)))

    def test_seam_imports_without_klayout(self):
        code = (
            "import sys\n"
            "class Block:\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            "        if name == 'klayout' or name.startswith('klayout.'):\n"
            "            raise ImportError('klayout blocked')\n"
            "sys.meta_path.insert(0, Block())\n"
            f"sys.path.insert(0, {str(BIN)!r})\n"
            "import _official_drc as od\n"
            "assert callable(od.summarize_marker_families)\n"
            "assert not any(m == 'klayout' or m.startswith('klayout.') for m in sys.modules)\n"
        )
        proc = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_diagnose_script_uses_the_seam(self):
        src = (BIN / "diagnose-official-drc.py").read_text()
        self.assertIn("fams = summarize_marker_families(markers, args.max_samples)", src)
        self.assertNotIn("Counter(i.cell for i in items)", src)


class MarkerFamilyRegressionTests(unittest.TestCase):
    """The KLayout census can't run headless, but the marker-family part of the
    committed `official-drc-diagnosis.json` is reproducible from its lyrdb."""

    def test_committed_diagnosis_families_reproduce(self):
        report = od.parse_lyrdb(OFFICIAL_DRC_RECORD / "mr-drc.lyrdb")
        fams = od.summarize_marker_families(report, 3)  # the script's --max-samples default
        committed = json.loads((OFFICIAL_DRC_RECORD / "official-drc-diagnosis.json").read_text())["families"]
        expected = {
            fam: {k: body[k] for k in ("count", "deck_cells", "sample_markers")}
            for fam, body in committed.items() if "count" in body
        }
        self.assertEqual(json.dumps(fams, indent=1), json.dumps(expected, indent=1))
        self.assertEqual(json.dumps(fams), json.dumps(_legacy_families(report, 3)))


if __name__ == "__main__":
    unittest.main()
