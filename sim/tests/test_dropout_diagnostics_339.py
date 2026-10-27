"""Tests for the #339 dropout screening analysis + deck generator.

Loaded by file path (like the other sim tests). Pure fixtures; no ngspice.
Every invalid input must stay invalid: no dropout number, named reason.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from _sim_script_loader import load_script  # noqa: E402

SIM_DIR = Path(__file__).resolve().parents[1]
DIAG = SIM_DIR / "dropout-vs-load" / "diagnostics" / "issue-339"


def _load(name, fname):
    return load_script(name, DIAG / fname, register=True)


an = _load("dropout339_analyze", "analyze.py")
gen = _load("dropout339_gen", "make_probe_deck.py")

GOOD_LOG = "meas_dropout_v = {m:.6e}\nngspice-42 done\noption SCALE: Scale is set to 1e-06\n"


def good_run(drop=0.3, regulate=True):
    """Synthetic run: VIN 0 -> 3.3 by 0.1 ms, flat to 6 ms, ramp down to 1.17 V by 14 ms.
    VOUT follows min(1.8, VIN-drop) after the ramp starts."""
    t = [i * 1e-5 for i in range(1401)]
    vin, vout, en, ipass = [], [], [], []
    for x in t:
        v = min(3.3, 3.3 * x / 1e-4) if x < 6e-3 else 3.3 - (x - 6e-3) / 8e-3 * 2.13
        vin.append(v)
        vout.append(0.0 if x < 1e-4 else (min(1.8, v - drop) if x > 3e-3 else 1.0))
        en.append(0.0 if x < 1e-4 else 3.3)
        ipass.append(0.05)
    if not regulate:
        vout = [0.5 for _ in t]
    cols = {"v(vin)": vin, "v(vout)": vout, "v(en)": en, "xm_pass.id": ipass}
    return t, cols


class TranGates(unittest.TestCase):
    def test_good_run_is_valid(self):
        t, c = good_run()
        r = an.analyze_tran(t, c, GOOD_LOG.format(m=0.3 + 1e-9))
        self.assertTrue(r["valid"], r["reasons"])
        self.assertAlmostEqual(r["dropout_v"], 0.3, places=3)

    def test_missing_crossing(self):
        t, c = good_run(drop=0.0)  # VOUT = min(1.8, VIN) never falls below 1.764 before ramp end? it does at VIN<1.764
        c["v(vout)"] = [1.8 if x > 3e-3 else v for x, v in zip(t, c["v(vout)"])]
        r = an.analyze_tran(t, c, GOOD_LOG.format(m=0.1))
        self.assertFalse(r["valid"])
        self.assertIsNone(r["dropout_v"])
        self.assertTrue(any("missing crossing" in s for s in r["reasons"]))

    def test_non_regulating_start(self):
        t, c = good_run(regulate=False)
        r = an.analyze_tran(t, c, GOOD_LOG.format(m=0.1))
        self.assertFalse(r["valid"])
        self.assertIsNone(r["dropout_v"])
        self.assertTrue(any("not regulating" in s for s in r["reasons"]))

    def test_nonfinite_data(self):
        t, c = good_run()
        c["v(vout)"][4000 // 10] = float("nan")
        r = an.analyze_tran(t, c, GOOD_LOG.format(m=0.3))
        self.assertFalse(r["valid"])
        self.assertIsNone(r["dropout_v"])
        self.assertTrue(any("nonfinite" in s for s in r["reasons"]))

    def test_solver_warning_invalidates(self):
        t, c = good_run()
        for bad in ("Warning: singular matrix", "doAnalyses: TRAN:  Timestep too small",
                    "Error: no convergence in transient"):
            r = an.analyze_tran(t, c, GOOD_LOG.format(m=0.3 + 1e-9) + bad + "\n")
            self.assertFalse(r["valid"], bad)
            self.assertIsNone(r["dropout_v"])
            self.assertTrue(any("solver diagnostics" in s for s in r["reasons"]))

    def test_benign_scale_notice_is_not_a_solver_finding(self):
        self.assertEqual(an.solver_findings("option SCALE: Scale is set to 1e-06 for instance"), [])

    def test_missing_meas_or_disagreement(self):
        t, c = good_run()
        r = an.analyze_tran(t, c, "ngspice-42 done\n")
        self.assertFalse(r["valid"])
        r = an.analyze_tran(t, c, GOOD_LOG.format(m=0.35))
        self.assertFalse(r["valid"])
        self.assertTrue(any("disagrees" in s for s in r["reasons"]))

    def test_truncated_run_and_warm_start(self):
        t, c = good_run()
        r = an.analyze_tran(t[:1000], {k: v[:1000] for k, v in c.items()}, GOOD_LOG.format(m=0.3))
        self.assertFalse(r["valid"])
        t, c = good_run()
        c["v(vout)"][0] = 1.8
        r = an.analyze_tran(t, c, GOOD_LOG.format(m=0.3 + 1e-9))
        self.assertFalse(r["valid"])
        self.assertTrue(any("cold start" in s for s in r["reasons"]))

    def test_load_not_established(self):
        t, c = good_run()
        c["xm_pass.id"] = [1e-6] * len(t)
        r = an.analyze_tran(t, c, GOOD_LOG.format(m=0.3 + 1e-9))
        self.assertFalse(r["valid"])

    def test_missing_column(self):
        t, c = good_run()
        del c["v(en)"]
        self.assertFalse(an.analyze_tran(t, c, GOOD_LOG.format(m=0.3))["valid"])


class Parsing(unittest.TestCase):
    def test_malformed_rows(self):
        s, r = an.parse_wrdata("1 2 3 4\n1 2 3\n", 2)
        self.assertIsNone(s)
        s, r = an.parse_wrdata("1 2 x 4\n", 2)
        self.assertIsNone(s)
        s, r = an.parse_wrdata("", 2)
        self.assertIsNone(s)

    def test_nonfinite_tokens_parse_then_fail_gate(self):
        s, cols = an.parse_wrdata("0 nan 0 1\n", 2)
        self.assertIsNotNone(s)


def pass_rows(points):
    """points: list of (vg, vsd, id) at source 2.16."""
    n = len(points)
    return {"g": [p[0] for p in points], "d": [2.16 - p[1] for p in points], "s": [2.16] * n,
            "i_vd": [p[2] for p in points], "i_vs": [-p[2] for p in points],
            "id": [-p[2] for p in points], "vgs": [0] * n,
            "vds": [-(p[1] - 0.009) for p in points], "vdsat": [0.4] * n, "gm": [0.2] * n}


class Contour(unittest.TestCase):
    def ramp(self, imax):
        return [(0.5, v / 100, imax * (v / 100) / 0.5) for v in range(0, 51)]

    def test_interpolates_crossing(self):
        c = an.contour_50mA(pass_rows(self.ramp(0.1)))[0]
        self.assertEqual(c["status"], "ok")
        self.assertAlmostEqual(c["vsd"], 0.25, places=6)
        self.assertAlmostEqual(c["vsd"] - c["vds_model"], 0.009, places=6)

    def test_no_crossing_is_not_a_result(self):
        c = an.contour_50mA(pass_rows(self.ramp(0.04)))[0]
        self.assertEqual(c["status"], "no_crossing")
        self.assertNotIn("vsd", c)

    def test_nonfinite_and_nonmonotone(self):
        rows = pass_rows(self.ramp(0.1))
        rows["id"][3] = float("nan")
        self.assertTrue(an.contour_50mA(rows)[0]["status"].startswith("invalid"))
        pts = self.ramp(0.1)
        pts[10] = (pts[10][0], pts[10][1], 0.0)
        self.assertTrue(an.contour_50mA(pass_rows(pts))[0]["status"].startswith("invalid"))

    def test_polarity_check(self):
        rows = pass_rows(self.ramp(0.1))
        self.assertEqual(an.polarity_problems(rows), [])
        rows["i_vd"] = [-x for x in rows["i_vd"]]
        self.assertTrue(an.polarity_problems(rows))

    def test_rounded_tolerance_formula(self):
        self.assertAlmostEqual(an.rounded_tolerance(0.2, 0.1), 0.2 * 0.5e-3 + 0.1 * 0.5e-3 + 0.05e-3)


class DeckGenerator(unittest.TestCase):
    def setUp(self):
        self.base = gen.BASELINE.read_text()

    def changed(self, edits, bias=None):
        deck, _cols = gen.build_probe(edits, "x.dat", self.base, bias)
        a, b = self.base.splitlines(), deck.splitlines()
        return [ln for ln in b if ln not in a]

    def test_no_edit_only_instrumentation(self):
        new = self.changed([])
        self.assertTrue(all(ln.startswith(("save all", "wrdata")) for ln in new), new)

    def test_combined_edit_is_the_union(self):
        new = self.changed(["ideal_tail", "no_clamps"])
        joined = "\n".join(new)
        for need in ("ITAIL_IDEAL VINA EA_TAIL DC 3.2744u", "XM_CLIM XCLIM_D", "XM_TSHUT XTSHUT_D",
                     "RXCLIM XCLIM_D 0 1G", "RXTSHUT XTSHUT_D 0 1G", "VVINA VINA 0 3.3"):
            self.assertIn(need, joined)
        self.assertNotIn("XM_TAIL EA_TAIL", build := gen.build_probe(["ideal_tail"], "x", self.base)[0])
        self.assertIn("XM_PASS VOUT EA_OUT VIN VIN", build)  # pass device untouched

    def test_frozen_bias_requires_value_and_is_en_gated(self):
        with self.assertRaises(ValueError):
            gen.build_probe(["frozen_bias"], "x", self.base)
        deck, _ = gen.build_probe(["frozen_bias"], "x", self.base, "2.005")
        self.assertIn("IBIAS_FROZEN VINA NB PULSE(0 2.005u 100u 1u 1u 100 200)", deck)
        self.assertNotIn("XR_BIAS", deck)

    def test_unknown_edit_rejected(self):
        with self.assertRaises(AssertionError):
            gen.apply_edits(self.base, ["bogus"])

    def test_columns_match_wrdata_width(self):
        deck, cols = gen.build_probe(["ideal_tail"], "x.dat", self.base)
        self.assertNotIn("xm_tail.id", cols)
        self.assertIn("i(vvina)", cols)
        wr = next(ln for ln in deck.splitlines() if ln.startswith("wrdata"))
        self.assertEqual(len(wr.split()) - 2, len(cols))

    def test_pass_bench_uses_committed_mpass_verbatim(self):
        inst = gen.pass_instance(self.base)
        self.assertTrue(inst.startswith("XM_PASS D G S S sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=100 nf=25"))
        self.assertIn("mult=50 m=50", inst)
        deck = gen.build_pass_contour(2.16, 0.005, baseline_text=self.base)
        self.assertIn("VS S 0 2.16", deck)
        self.assertIn("dc VD 2.16 1.660000 -0.005 VG 0.714 0.0 -0.017", deck)


if __name__ == "__main__":
    unittest.main()
