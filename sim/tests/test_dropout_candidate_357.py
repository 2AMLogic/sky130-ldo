"""Tests for the #357 physical dropout candidate: netlist transformation, structural
invariants, derived-measurement validity and the paired/bench classification.

Loaded by file path (like the other sim tests). Pure fixtures; no ngspice, no xschem.
Every invalid input must stay invalid: no dropout / derived number, named reason.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
DIAG = SIM_DIR / "dropout-vs-load" / "diagnostics" / "issue-357"
D339 = SIM_DIR / "dropout-vs-load" / "diagnostics" / "issue-339"
sys.path.insert(0, str(SIM_DIR / "bin"))
sys.path.insert(0, str(DIAG))


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, DIAG / fname)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cand = _load("candidate", "candidate.py")
an = _load("analyze", "analyze.py")
probe = _load("probe357", "probe.py")
summ = _load("summarize357", "summarize.py")

# The committed #339 baseline deck (xschem 3.4.4 wrapping): a real DUT netlist fixture.
BASE = (D339 / "baseline.deck.spice").read_text()


def rewrap(text):
    """Join every `+` continuation into one physical line (xschem-version-like rewrap)."""
    out = []
    for ln in text.splitlines():
        if ln.startswith("+") and out:
            out[-1] += " " + ln[1:].strip()
        else:
            out.append(ln)
    return "\n".join(out) + "\n"


class Geometry(unittest.TestCase):
    def test_geom_reproduces_committed_cards(self):
        cases = [("XM_BIASP1", 10, 2, 1), ("XM_MIRP1", 20, 4, 4), ("XM_BIASN1", 4, 1, 1),
                 ("XM_TAIL", 40, 8, 2), ("XM_ENP5", 2, 1, 0.5)]
        lines = BASE.splitlines()
        for name, w, nf, l in cases:
            _a, _b, txt = cand.card_text(lines, name)
            want = cand.card_tokens(txt)[6:]
            got = cand.card_tokens("X " * 6 + cand.geom(w, nf, l))[6:]
            self.assertEqual(got[:7], want[:7], name)  # L W nf ad as pd ps
            self.assertAlmostEqual(float(got[7].split("=")[1]), float(want[7].split("=")[1]), places=5)

    def test_enp5_copy_matches_committed_geometry(self):
        _a, _b, txt = cand.card_text(BASE.splitlines(), "XM_ENP5")
        self.assertEqual(cand.card_tokens(txt)[6:], cand.card_tokens("X " * 6 + cand.ENP5_GEOM)[6:])


class Transformation(unittest.TestCase):
    def test_both_revisions_apply_and_hold_invariants(self):
        for rev in (0, 1):
            ed, notes = cand.apply_candidate(BASE, rev)
            self.assertEqual(cand.check_candidate(BASE, ed), [], rev)
            self.assertIn(f"removed XM_TAIL", notes)

    def test_wrap_independent_exact_match(self):
        ed, _ = cand.apply_candidate(rewrap(BASE), 1)
        self.assertEqual(cand.check_candidate(rewrap(BASE), ed), [])

    def test_pass_device_and_ports_untouched(self):
        ed, _ = cand.apply_candidate(BASE, 1)
        for name in ("XM_PASS", "XM_SENSE", "XM_CLIM", "XM_TSHUT"):
            self.assertEqual(cand.card_text(BASE.splitlines(), name)[2], cand.card_text(ed.splitlines(), name)[2])
        self.assertEqual(ed.count(cand.SUBCKT_HEAD), 1)
        self.assertIn("xldo VOUT VREF EN VIN ldo_3v3in_1v8out", ed)

    def test_protection_connections_retained(self):
        ed, _ = cand.apply_candidate(BASE, 1)
        cl = cand.card_text(ed.splitlines(), "XM_CLP")[2]
        self.assertTrue(cl.startswith("XM_CLP CL_CMP PBR VIN VIN "))  # drain/source kept, gate re-referenced
        self.assertTrue(cand.card_text(ed.splitlines(), "XM_CLIM")[2].startswith("XM_CLIM EA_OUT CL_CMP VIN VIN "))
        self.assertTrue(cand.card_text(ed.splitlines(), "XM_TSHUT")[2].startswith("XM_TSHUT EA_OUT TS_CMP VIN VIN "))

    def test_drifted_card_fails(self):
        bad = BASE.replace("XM_TAIL EA_TAIL BIASP VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=2 W=40",
                           "XM_TAIL EA_TAIL BIASP VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=2 W=41")
        with self.assertRaisesRegex(ValueError, "XM_TAIL does not match"):
            cand.apply_candidate(bad, 0)

    def test_duplicate_card_fails(self):
        lines = BASE.splitlines()
        a, b, txt = cand.card_text(lines, "XM_CLP")
        dup = "\n".join(lines[:b] + txt.split("\n") + lines[b:]) + "\n"
        with self.assertRaisesRegex(ValueError, "exactly one card 'XM_CLP'"):
            cand.apply_candidate(dup, 0)

    def test_missing_card_fails(self):
        lines = BASE.splitlines()
        a, b, _ = cand.card_text(lines, "XM_MIR3")
        with self.assertRaisesRegex(ValueError, "exactly one card 'XM_MIR3'"):
            cand.apply_candidate("\n".join(lines[:a] + lines[b:]) + "\n", 0)

    def test_two_dut_subckts_fail(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            cand.apply_candidate(BASE + cand.SUBCKT_HEAD + "\n.ends\n", 0)

    def test_new_node_clash_fails(self):
        clash = BASE.replace("C_SS SS 0 10p m=1", "C_SS SS 0 10p m=1\nC_X PBR 0 1p m=1")
        with self.assertRaisesRegex(ValueError, "already exist"):
            cand.apply_candidate(clash, 0)

    def test_unknown_revision_fails(self):
        with self.assertRaises(ValueError):
            cand.apply_candidate(BASE, 7)


class Invariants(unittest.TestCase):
    def setUp(self):
        self.ed, _ = cand.apply_candidate(BASE, 1)

    def _inject(self, card):
        return self.ed.replace("* --- issue #357 candidate", card + "\n* --- issue #357 candidate", 1)

    def test_vref_on_drain_is_flagged(self):
        bad = self._inject("XM_BAD VREF EN VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=1 W=1 nf=1")
        self.assertTrue(any("VREF used on a non-gate" in p for p in cand.check_candidate(BASE, bad)))

    def test_aux_rail_is_flagged(self):
        bad = self.ed.replace("VVREF VREF 0 1.2", "VVREF VREF 0 1.2\nVVINA VINA 0 3.3")
        self.assertTrue(any("auxiliary rail" in p for p in cand.check_candidate(BASE, bad)))

    def test_foreign_node_is_flagged(self):
        bad = self._inject("XM_BAD NB NB VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=1 W=1 nf=1")
        self.assertTrue(any("not an allowed existing node" in p for p in cand.check_candidate(BASE, bad)))

    def test_pass_edit_is_flagged(self):
        bad = self.ed.replace("mult=50 m=50", "mult=40 m=40")
        self.assertTrue(any("XM_PASS not byte-identical" in p for p in cand.check_candidate(BASE, bad)))

    def test_non_hv_device_is_flagged(self):
        bad = self._inject("XM_BAD NM NM AMP_ENN 0 sky130_fd_pr__nfet_01v8 L=1 W=1 nf=1")
        self.assertTrue(any("not a sky130 g5v0d10v5" in p for p in cand.check_candidate(BASE, bad)))


# ------------------------------------------------------------- analysis fixtures
GOOD_LOG = "meas_dropout_v = {m:.6e}\nngspice-46 done\noption SCALE: Scale is set to 1e-06\n"


def synth(variant="cand", drop=0.16, regulate=True, t_end=14e-3):
    names = probe.column_names(variant)
    t = [i * 1e-5 for i in range(int(round(t_end / 1e-5)) + 1)]
    cols = {n: [] for n in names}
    for x in t:
        vin = min(3.3, 3.3 * x / 1e-4) if x < 6e-3 else 3.3 - (x - 6e-3) / 8e-3 * 2.13
        vout = 0.0 if x < 1e-4 else (min(1.8, vin - drop) if x > 3e-3 else 1.0)
        if not regulate:
            vout = 0.5
        for n in names:
            v = 1e-6
            if n == "v(vin)":
                v = vin
            elif n == "v(vout)":
                v = vout
            elif n == "v(en)":
                v = 0.0 if x < 1e-4 else 3.3
            elif n == "xm_pass.id":
                v = 0.05
            elif n == "i(vvin)":
                v = -0.05003
            elif n == "i(vvref)":
                v = 1e-15
            elif n.endswith(".vds"):
                v = 0.5
            elif n.endswith(".vdsat"):
                v = 0.1
            elif n == "v(xldo.ea_out)":
                v = 1.0
            cols[n].append(v)
    return t, names, cols


def write_run(d, variant="cand", log=None, exit_code=0, diag=None, mutate=None, **kw):
    t, names, cols = synth(variant, **kw)
    if mutate:
        mutate(t, cols)
    d.mkdir(parents=True, exist_ok=True)
    (d / "data.columns.json").write_text(json.dumps(names))
    rows = []
    for i, x in enumerate(t):
        rows.append(" ".join(f"{x:.9e} {cols[n][i]:.9e}" for n in names))
    (d / "data.dat").write_text("\n".join(rows) + "\n")
    drop = kw.get("drop", 0.16)
    (d / "ngspice.log").write_text(log if log is not None else GOOD_LOG.format(m=drop))
    (d / "result.json").write_text(json.dumps({"run_id": d.name, "variant": variant,
                                               "ngspice_exit": exit_code, "solver_diagnostic": diag}))
    return d


class DerivedValidity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t357-"))

    def run_(self, name, **kw):
        return an.analyze(write_run(self.tmp / name, **kw))

    def test_supported_crossing_valid_with_derived(self):
        r = self.run_("good")
        self.assertTrue(r["valid"], r["reasons"])
        self.assertAlmostEqual(r["dropout_v"], 0.16, places=3)
        self.assertIsNotNone(r["derived"])
        self.assertAlmostEqual(r["derived"]["crossing"]["tail_headroom_v"], 0.4, places=6)
        self.assertAlmostEqual(r["derived"]["pre_5p9ms"]["iq_vs_load_a"], 30e-6, places=9)
        self.assertTrue(r["spec_grade"]["pass"])

    def test_base_variant_roles(self):
        r = self.run_("goodb", variant="base", drop=0.4)
        self.assertTrue(r["valid"], r["reasons"])
        self.assertFalse(r["spec_grade"]["pass"])
        self.assertIn("pull_down_headroom_v", r["derived"]["crossing"])

    def _assert_invalid(self, r, needle):
        self.assertFalse(r["valid"])
        self.assertIsNone(r["dropout_v"])
        self.assertIsNone(r["derived"])
        self.assertIsNone(r["spec_grade"])
        self.assertTrue(any(needle in s for s in r["reasons"]), r["reasons"])

    def test_missing_crossing(self):
        def m(t, c):
            c["v(vout)"][:] = [1.8 if x > 3e-3 else v for x, v in zip(t, c["v(vout)"])]
        self._assert_invalid(self.run_("nox", mutate=m), "missing crossing")

    def test_nonfinite(self):
        def m(t, c):
            c["v(xldo.ea_out)"][700] = float("nan")
        self._assert_invalid(self.run_("nan", mutate=m), "nonfinite")

    def test_truncated_trace(self):
        self._assert_invalid(self.run_("trunc", t_end=9e-3), "before the 14 ms ramp end")

    def test_non_regulating_start(self):
        self._assert_invalid(self.run_("noreg", regulate=False), "not regulating")

    def test_solver_error_log(self):
        log = GOOD_LOG.format(m=0.16) + "Warning: singular matrix:  check node xldo.ea_cz\n"
        self._assert_invalid(self.run_("solver", log=log), "solver diagnostics")

    def test_nonzero_exit(self):
        self._assert_invalid(self.run_("exit", exit_code=1), "ngspice exit status 1")

    def test_corner_run_diagnostic_field(self):
        self._assert_invalid(self.run_("diag", diag="Warning: Dynamic gmin stepping failed"), "corner-run solver")

    def test_meas_missing(self):
        self._assert_invalid(self.run_("nomeas", log="ngspice-46 done\n"), "meas_dropout_v missing")

    def test_malformed_rows(self):
        d = write_run(self.tmp / "malformed")
        txt = (d / "data.dat").read_text().splitlines()
        txt[50] = txt[50].rsplit(" ", 2)[0]
        (d / "data.dat").write_text("\n".join(txt) + "\n")
        self._assert_invalid(an.analyze(d), "malformed data")

    def test_missing_data_file(self):
        d = write_run(self.tmp / "nodata")
        (d / "data.dat").unlink()
        self._assert_invalid(an.analyze(d), "data unavailable")

    def test_missing_derived_column_gives_no_derived(self):
        t, names, cols = synth("cand")
        res = an.a339.analyze_tran(t, cols, GOOD_LOG.format(m=0.16))
        self.assertTrue(res["valid"], res["reasons"])
        del cols["xm_ntail.vdsat"]
        d, why = an.derived(t, cols, "cand", res)
        self.assertIsNone(d)
        self.assertTrue(any("xm_ntail.vdsat" in w for w in why))

    def test_edge_vin_not_reached_gives_no_derived(self):
        t, names, cols = synth("cand")
        res = an.a339.analyze_tran(t, cols, GOOD_LOG.format(m=0.16))
        cols["v(vin)"] = [max(v, 2.2) for v in cols["v(vin)"]]
        d, why = an.derived(t, cols, "cand", res)
        self.assertIsNone(d)
        self.assertTrue(any("edge sample" in w for w in why))

    def test_derived_nonfinite_rejected(self):
        t, names, cols = synth("cand")
        res = an.a339.analyze_tran(t, cols, GOOD_LOG.format(m=0.16))
        cols["xm_clim.id"] = [float("inf")] * len(t)
        d, why = an.derived(t, cols, "cand", res)
        self.assertIsNone(d)
        self.assertTrue(any("nonfinite derived" in w for w in why))


class RepeatAndClassification(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t357r-"))

    def test_repeat_met_and_not_met(self):
        a = an.analyze(write_run(self.tmp / "a", drop=0.16))
        b = an.analyze(write_run(self.tmp / "b", drop=0.1603))
        c = an.analyze(write_run(self.tmp / "c", drop=0.1612))
        self.assertTrue(an.repeat_check(a, b)[0])
        self.assertFalse(an.repeat_check(a, c)[0])

    def test_repeat_with_invalid_run_is_not_met(self):
        a = an.analyze(write_run(self.tmp / "a2"))
        bad = an.analyze(write_run(self.tmp / "b2", exit_code=1))
        ok, msg = an.repeat_check(a, bad)
        self.assertFalse(ok)
        self.assertIn("INVALID", msg)

    def test_bench_classification(self):
        self.assertEqual(summ.classify(True, True, True, True), "pass")
        self.assertEqual(summ.classify(False, False, True, True), "pre-existing")
        self.assertEqual(summ.classify(True, False, True, True), "REGRESSION")
        self.assertEqual(summ.classify(False, True, True, True), "fixed")
        # an invalid run is never a pass, even when its numbers sit inside the bounds
        self.assertEqual(summ.classify(True, True, True, False), "INVALID")
        self.assertEqual(summ.classify(True, True, False, True), "INVALID")

    def test_bench_validity(self):
        ok = {"ngspice_exit": 0, "solver_diagnostic": None, "missing_measurements": []}
        self.assertEqual(summ.bench_valid(ok), (True, []))
        self.assertFalse(summ.bench_valid(dict(ok, solver_diagnostic="Warning: singular matrix"))[0])
        self.assertFalse(summ.bench_valid(dict(ok, ngspice_exit=1))[0])
        self.assertFalse(summ.bench_valid(dict(ok, missing_measurements=["iq_full_load_ua"]))[0])
        self.assertFalse(summ.bench_valid(None)[0])

    def test_thermal_state_invalid_and_pass_off(self):
        th = {"forced_tripped": True, "hold_tripped": True, "after_en_reenable_tripped": True,
              "nonfinite": False, "ipass_ua": {"90": 0.3, "165": 5.0}}
        r = {"ngspice_exit": 0, "solver_diagnostic": None, "thermal": th}
        s = summ.thermal_state(r)
        self.assertTrue(s["valid"])
        self.assertTrue(s["pass_off_90"])
        self.assertFalse(s["pass_off_165"])  # tripped but pass still conducting -> NOT pass-off
        self.assertFalse(summ.thermal_state(dict(r, solver_diagnostic="x"))["valid"])
        self.assertFalse(summ.thermal_state(dict(r, thermal=dict(th, nonfinite=True)))["valid"])


class CommittedEvidence(unittest.TestCase):
    def test_committed_edited_netlists_regenerate_byte_identically(self):
        runs = sorted((DIAG / "runs").glob("*/result.json"))
        n = 0
        for f in runs:
            r = json.loads(f.read_text())
            if r.get("variant") != "cand":
                continue
            raw = (f.parent / "netlist.raw.spice").read_text()
            ed, _ = cand.apply_candidate(raw, r["candidate_rev"])
            self.assertEqual(ed, (f.parent / "netlist.edited.spice").read_text(), f.parent.name)
            self.assertEqual(cand.check_candidate(raw, ed), [], f.parent.name)
            n += 1
        if runs:
            self.assertGreater(n, 0)


class Instrumentation(unittest.TestCase):
    def test_instrumentation_only_adds_save_and_wrdata(self):
        for variant in ("base", "cand"):
            deck, cols = probe.instrument_dropout(BASE, variant)
            self.assertEqual(deck.split(".control")[0], BASE.split(".control")[0])
            self.assertEqual(deck.count("wrdata data.dat"), 1)
            self.assertEqual(len(cols), len(set(cols)))
            self.assertNotIn("i(iload)", cols)  # not a valid ngspice vector (attempt d01_base)
            rest = [ln for ln in deck.split(".control")[1].splitlines()
                    if not ln.startswith(("save all", "wrdata"))]
            base_rest = [ln for ln in BASE.split(".control")[1].splitlines() if not ln.startswith("save all")]
            self.assertEqual(rest, base_rest)

    def test_bad_control_shape_rejected(self):
        with self.assertRaises(ValueError):
            probe.instrument_dropout(BASE.replace("save all\n", ""), "base")


if __name__ == "__main__":
    unittest.main(verbosity=1)
