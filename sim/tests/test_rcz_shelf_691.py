"""Bounded stability-screen coverage. No simulator or fleet needed."""

import itertools
import json
import tempfile
import unittest
from pathlib import Path

from _sim_script_loader import load_script

BIN = Path(__file__).resolve().parents[1] / "bin"
screen = load_script("rcz_shelf_691", BIN / "rcz-shelf-691.py", register=True)
BODY = """COUT VOUT VESR 1u m=1
HESR VESRS 0 VESRSENSE 0.01
RLOAD VOUT 0 1800 m=1
.subckt ldo VOUT VREF EN VIN
XR_CZ EA_CZ EA_OUT 0 sky130_fd_pr__res_xhigh_po W=0.42 L=52 mult=1 m=1
.ends
"""


class Grid(unittest.TestCase):
    def test_requests_match_electrical_grid_and_design(self):
        loads = ["0mA", "10uA", "30uA", "100uA", "300uA", "1mA", "50mA"]
        caps = ["0.33u", "4.7u"]
        esr_values = {"0": "0", "10m": "0.01", "500m": "0.5"}
        resistances = dict(
            zip(loads, ["1e12", "180k", "60k", "18k", "6k", "1800", "36"], strict=True)
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "requests").mkdir()
            for stage, esrs, procs, temps in (
                ("tt", ["0", "10m", "500m"], ["tt"], [27]),
                ("pvt", ["10m"], ["ss", "ff"], [-40, 125]),
            ):
                for design in screen.DESIGNS:
                    jobs = screen.ac_requests(
                        out,
                        {"variant": "sky130A", "ngspice_lib": "model"},
                        BODY,
                        stage,
                        design,
                    )
                    expected = set(itertools.product(caps, esrs, loads))
                    self.assertEqual(len(jobs), len(expected))
                    self.assertEqual(
                        {key.split("__")[2] for key, _ in jobs},
                        {"_".join(v) for v in expected},
                    )
                    for key, path in jobs:
                        req = json.loads(path.read_text())
                        self.assertEqual(
                            req["corners"], {"process": procs, "temperature_c": temps}
                        )
                        deck = Path(req["netlist"]).read_text()
                        cap, esr, load = key.split("__")[2].split("_")
                        self.assertIn(f"COUT VOUT VESR {cap} m=1", deck)
                        self.assertIn(
                            f"HESR VESRS 0 VESRSENSE {esr_values[esr]}\n",
                            deck,
                        )
                        self.assertIn(
                            f"RLOAD VOUT 0 {resistances[load]} ",
                            deck,
                        )
                        self.assertEqual(deck.count("ELG_DEN "), 1)
                        self.assertEqual("C_BYP" in deck, design == "shelf")

    def test_gates_require_every_paired_result_but_baseline_may_fail(self):
        rows = [
            {"design": d, "pm": 20 if d == "baseline" else 45, "gm": 10, "reason": None}
            for _ in range(42)
            for d in screen.DESIGNS
        ]
        self.assertTrue(screen.advance(rows, "tt"))
        self.assertFalse(screen.advance(rows[:-1], "tt"))
        for field, value in [("pm", 44.99), ("gm", 9.99), ("reason", "missing gm")]:
            with self.subTest(field=field):
                bad = [*rows[:-1], dict(rows[-1], **{field: value})]
                self.assertFalse(screen.advance(bad, "tt"))
        rows[0]["reason"] = "missing baseline"
        self.assertFalse(screen.advance(rows, "tt"))

    def test_missing_duplicate_and_bad_metrics_are_explained(self):
        case = {
            "process": "tt",
            "temperature_c": 27,
            "status": "pass",
            "measurements": [
                {"name": "pm", "value": 45, "status": "pass"},
                {"name": "gm", "value": 10, "status": "pass"},
            ],
        }
        for corners, fragment in [
            ([], "missing"),
            ([case, case], "duplicate"),
            ([dict(case, measurements=case["measurements"][:1])], "gm"),
            ([dict(case, status="error")], "error"),
        ]:
            r = {"environment": {"remote": {"job_id": "job"}}, "corners": corners}
            self.assertIn(fragment, screen.margins(r, "tt", 27)["reason"])


report = load_script("rcz_shelf_report_691", BIN / "rcz-shelf-691-report.py")


class Reporting(unittest.TestCase):
    def test_replay_the_refused_preflight(self):
        # The source is the actual refused probe. No prior campaign is a data source.
        rec = BIN.parent / "loop-gain/diagnostics/20261120-223530-542c11e-rcz-shelf"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "campaign.json").write_bytes((rec / "campaign.json").read_bytes())
            verdict = report.render(out)
            self.assertEqual(verdict["verdict"], "REVISE")
            self.assertFalse(verdict["ac_evidence_complete"])
            self.assertNotIn("pvt", verdict["ac"])
            for result in verdict["ac"]["tt"].values():
                self.assertEqual((result["valid"], result["total"]), (0, 42))
                self.assertIsNone(result["worst"]["pm"])
            for name in ("tables.md", "verdict.json"):
                self.assertEqual((out / name).read_bytes(), (rec / name).read_bytes())
            with self.assertRaises(ValueError):
                report.render(out, adoption_issue=1)

    def test_transient_crossings_must_match_observed_excursions(self):
        m = {
            "vmin": 1.79,
            "vmax": 1.81,
            "pre": 1.8,
            "vfin": 1.8,
            "tlo": None,
            "thi": None,
        }
        self.assertEqual(report.tran_result(m)["rec_us"], 0)
        self.assertFalse(report.tran_result(dict(m, vmax=1.9, vfin=1.85))["recovered"])
        self.assertFalse(
            report.tran_result(dict(m, vmin=1.74, vmax=1.89, thi=0.00015))["valid"]
        )
        self.assertAlmostEqual(
            report.tran_result(dict(m, vmin=1.70, tlo=0.00014))["rec_us"], 40
        )

    def test_survivor_iq_delta_and_strict_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for design, draw in (("baseline", 0.050029), ("shelf", 0.050030)):
                path = out / "responses" / f"iq__{design}"
                path.mkdir(parents=True)
                values = {
                    "iq_0mA.ivin": 0.000014,
                    "iq_0mA.vout": 1.8,
                    "iq_50mA.ivin": draw,
                    "iq_50mA.vout": 1.8,
                }
                data = {
                    "environment": {"remote": {"job_id": "test"}},
                    "corners": [
                        {
                            "process": "ss",
                            "temperature_c": -40,
                            "status": "pass",
                            "measurements": [
                                {"name": k, "value": v, "status": "pass"}
                                for k, v in values.items()
                            ],
                        }
                    ],
                }
                (path / "klt.stdout").write_text(json.dumps(data))
            iq, tran = report.survivor_tables(out, [])
            self.assertEqual(len(iq), 18)
            self.assertEqual(len(tran), 36)
            row = next(
                r
                for r in iq
                if (r["process"], r["temp"], r["load"]) == ("ss", -40, "50mA")
            )
            self.assertEqual(
                (row["delta_uA"], row["shelf"]["iq_uA"], row["passed"]), (1, 30, False)
            )
            self.assertFalse(any(r["passed"] for r in tran))
