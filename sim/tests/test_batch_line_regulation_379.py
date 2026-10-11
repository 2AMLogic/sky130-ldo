"""Issue #379: the line-regulation endpoint adapter on the opt-in `klt sim`
batch backend.

PDK-free and headless: klt, xschem, git and the PDK are mocked by
test_corner_run.BatchHarness, so nothing is submitted and no ngspice runs.
These tests are OFFLINE translation/grading checks. They are not evidence of
remote (fleet) execution or of local/fleet numerical equivalence; that is the
separate paired-validation stage described in sim/README.md.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import unittest
from pathlib import Path

from test_corner_run import QUICK, SIM_DIR, BatchHarness, FakeKlt, HarnessErr, corner_run

sys.path.insert(0, str(SIM_DIR / "bin"))
import batch_line_regulation as blr  # noqa: E402
from _record_common import pvt_input_sections  # noqa: E402

SLUG = "line-regulation"
STIMULUS = corner_run.BATCH_ALLOWLIST[SLUG]["stimulus"]
LR_NETLIST = (
    "** sch_path: x\n"
    + "\n".join(
        [STIMULUS[0], ".save i(vvin)", STIMULUS[1], "VVREF VREF 0 1.2",
         "xldo VOUT VREF EN VIN ldo_3v3in_1v8out", "COUT VOUT VESR 1u m=1", "RESR VESR 0 10m m=1",
         STIMULUS[2], ".subckt ldo_3v3in_1v8out VOUT VREF EN VIN", "R1 VIN VOUT 1", ".ends"]
    )
    + "\n.end\n"
)
ENDPOINTS = [("tran1", "2.97", "1m"), ("tran2", "3.63", "1m"), ("tran3", "2.97", "50m"), ("tran4", "3.63", "50m")]


def manifest() -> dict:
    return json.loads((SIM_DIR / SLUG / "experiment.json").read_text())


def default_values(p, t, vin, iload):
    """(avg, min, max) of a healthy endpoint: ~2 mV/V line, small load droop."""
    avg = 1.8 + 0.002 * (vin - 3.3) - (0.001 if iload == "50m" else 0.0)
    return avg, avg - 0.001, avg + 0.001


class FakeLineRegKlt(FakeKlt):
    def __init__(self, test, pin, values_of=None, log_text=None, **kw):
        super().__init__(test, pin, **kw)
        self.values_of = values_of or default_values
        self.log_text = log_text

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if cmd[0] != "/fake/klt":
            self.test.fail(f"unexpected launch: {cmd}")
        if self.raise_exc:
            raise self.raise_exc
        req = json.loads(Path(cmd[2]).read_text())
        self.test.assertNotIn("analysis", req)
        (step,) = req["analysis_steps"]
        lines = Path(req["netlist"]).read_text().splitlines()
        vin = float(next(ln for ln in lines if ln.startswith("VVIN ")).split()[3])
        iload = next(ln for ln in lines if ln.startswith("ILOAD ")).split()[3]
        outdir = Path(cmd[cmd.index("-o") + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        corners = []
        for p in req["corners"]["process"]:
            for t in req["corners"]["temperature_c"]:
                vals = self.values_of(p, t, vin, iload)
                logp = outdir / f"{p}_{t}.log"
                logp.write_text(self.log_text or f"Operating point simulation skipped by 'uic'\n{p} {t}\n")
                meas = []
                for m in step["measurements"]:
                    kind = m["spice"].split()[3]
                    v = None if vals is None else vals[{"avg": 0, "min": 1, "max": 2}[kind]]
                    meas.append({"name": f"{step['name']}.{m['name']}", "value": v,
                                 "status": "pass" if v is not None else "error"})
                corners.append({
                    "corner_id": f"{p}/novdd/{t:g}C", "process": p, "temperature_c": t,
                    "status": "pass" if vals is not None else "error", "runtime_s": 9.0,
                    "diagnostics": [] if vals is not None else [
                        {"severity": "error", "code": "measurement", "message": "no value"}],
                    "artifacts": {"log": str(logp)}, "measurements": meas,
                })
        resp = {
            "status": "pass", "corners": corners,
            "environment": {"engine": "ngspice", "engine_version": "46",
                            "remote": {"provider": "aws-batch-fleet", "job_id": "klt-sim-00ee01",
                                       "state": "done", "exit_code": "0",
                                       "runner_compatibility": "match"}},
            "provenance": {"klt_version": "0.7.0", "pdk": {"version": self.pin["open_pdks_commit"]}},
        }
        if self.mutate:
            self.mutate(resp, req)
        out = self.stdout if self.stdout is not None else json.dumps(resp)
        return subprocess.CompletedProcess(cmd, self.rc, stdout=out, stderr="")


class LineRegHarness(BatchHarness):
    SLUG = SLUG
    NETLIST = LR_NETLIST

    def make_fake(self, **kw):
        return FakeLineRegKlt(self, self.pin, **kw)

    def requests(self):
        return [json.loads(Path(c[0][2]).read_text()) for c in self.klt_calls()]

    def write_manifest(self, raw):
        (self.exp_dir / "experiment.json").write_text(json.dumps(raw))

    def quick(self, **fake_kw):
        self.fake = FakeLineRegKlt(self, self.pin, **fake_kw)
        return self.run_main("--backend", "batch", *QUICK, "--no-write")


class TestEndpointTranslation(LineRegHarness):
    def test_four_endpoint_states_vin_en_coherence_and_load(self):
        exp = corner_run.load_experiment(self.exp_dir)
        eps = corner_run.endpoint_deck(exp)
        self.assertEqual([(e.step_name, e.vin, e.iload) for e in eps], ENDPOINTS)
        for e in eps:
            src = blr.endpoint_source_lines(e)
            self.assertEqual(src["vvin"], f"VVIN VIN 0 {e.vin}")
            # EN's high level is the SAME literal as VIN: full-rail EN
            self.assertEqual(src["ven"], f"VEN EN 0 dc 0 pwl(0 0 100u 0 101u {e.vin} 10 {e.vin})")
            self.assertEqual(src["iload"], f"ILOAD VOUT 0 {e.iload}")
            self.assertEqual(e.tran_args, "10u 200m uic")

    def test_request_netlists_carry_each_endpoints_complete_source_state(self):
        rc, _, _ = self.quick()
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 12)  # 3 singleton tuples x 4 endpoints, no Cartesian expansion
        for i, req in enumerate(reqs):
            name, vin, iload = ENDPOINTS[i % 4]
            body = Path(req["netlist"]).read_text().splitlines()
            self.assertEqual([ln for ln in body if ln.startswith("VVIN ")], [f"VVIN VIN 0 {vin}"])
            self.assertEqual([ln for ln in body if ln.startswith("VEN ")],
                             [f"VEN EN 0 dc 0 pwl(0 0 100u 0 101u {vin} 10 {vin})"])
            # 50 mA is applied at points 3/4 and the 1 mA default restored/kept at 1/2
            self.assertEqual([ln for ln in body if ln.startswith("ILOAD ")], [f"ILOAD VOUT 0 {iload}"])
            (step,) = req["analysis_steps"]
            self.assertEqual(step["name"], name)
            self.assertEqual(step["analysis"], {"kind": "tran", "args": "10u 200m uic"})
            self.assertNotIn("alter", step)
            self.assertEqual(body[:3], [body[0], ".option wnflag=1", ".save all"])

    def test_cards_keep_windows_and_kinds(self):
        rc, _, _ = self.quick()
        step = self.requests()[0]["analysis_steps"][0]
        self.assertEqual(step["measurements"], [
            {"name": "vout_1ma_lo", "spice": ".meas tran vout_1ma_lo avg v(vout) from=199m to=200m", "unit": "V"},
            {"name": "vout_1ma_lo_min", "spice": ".meas tran vout_1ma_lo_min min v(vout) from=199m to=200m", "unit": "V"},
            {"name": "vout_1ma_lo_max", "spice": ".meas tran vout_1ma_lo_max max v(vout) from=199m to=200m", "unit": "V"}])
        # slopes are NOT sent to klt: they span two requests and are graded locally
        for req in self.requests():
            self.assertFalse(any("line_reg" in m["name"] for m in req["analysis_steps"][0]["measurements"]))

    def test_step_cards_are_the_local_deck_cards(self):
        exp = corner_run.load_experiment(self.exp_dir)
        deck = corner_run.build_deck(exp, type("P", (), {"lib_file": "/x/l"})(),
                                     corner_run.Corner("tt", 27, 3.3), ["* b"]).splitlines()
        for e in corner_run.endpoint_deck(exp):
            step = corner_run.endpoint_step(exp, e.step_name)
            self.assertIn(f"tran {step['analysis']['args']}", deck)
            for m in step["measurements"]:
                self.assertIn(m["spice"][1:], deck)

    def test_full_matrix_keeps_supply_label_multiplicity(self):
        rc, _, _ = self.run_main("--backend", "batch", "--no-write")
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 12)  # 3 supply labels x 4 endpoints
        self.assertTrue(all(r["corners"]["process"] == ["tt", "ss", "ff", "sf", "fs"]
                            and r["corners"]["temperature_c"] == [-40.0, 27.0, 125.0] for r in reqs))
        self.assertEqual([Path(r["netlist"]).read_text().splitlines()[0] for r in reqs[::4]],
                         [".param vsup=2.97", ".param vsup=3.3", ".param vsup=3.63"])

    def test_explicit_quick_subset_is_singletons_per_endpoint(self):
        self.quick()
        reqs = self.requests()
        self.assertEqual([r["corners"] for r in reqs[::4]], [
            {"process": ["tt"], "temperature_c": [27.0]},
            {"process": ["ss"], "temperature_c": [-40.0]},
            {"process": ["ff"], "temperature_c": [125.0]}])

    def test_dry_run_submits_nothing_and_names_adapter(self):
        rc, out, _ = self.run_main("--backend", "batch", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertEqual(self.fake.calls, [])
        self.assertIn("batch adapter line-regulation-endpoints", out)
        self.assertEqual(out.count('"analysis_steps"'), 12)
        self.assertFalse((self.exp_dir / "records").exists())

    def test_local_backend_is_unchanged(self):
        exp = corner_run.load_experiment(self.exp_dir)
        before = corner_run.build_deck(exp, type("P", (), {"lib_file": "/x/l"})(),
                                       corner_run.Corner("tt", 27, 3.3), ["VVIN VIN 0 3.3"])
        self.assertIn("alter @ven[pwl] = [ 0 0 100u 0 101u $vinpt 10 $vinpt ]", before)
        self.assertEqual(before.count("tran 10u 200m uic"), 4)
        self.assertIn("VVIN VIN 0 3.3", before)


class TestEndpointGrading(LineRegHarness):
    def test_healthy_run_passes_and_slope_maps_to_the_right_endpoints(self):
        rc, out, _ = self.quick()
        self.assertEqual(rc, 0, out)
        # 0.002 V/V = 2 mV/V line regulation, from tran2 - tran1 (1 mA) and tran4 - tran3 (50 mA)
        self.assertIn("line_reg_1ma_mv_per_v=2", out)
        self.assertIn("line_reg_50ma_mv_per_v=2", out)

    def test_slope_uses_endpoint_values_of_the_matching_load(self):
        # make only the 50 mA pair slope differently; the 1 mA slope must not move
        def vals(p, t, vin, iload):
            slope = 0.004 if iload == "50m" else 0.001
            avg = 1.8 + slope * (vin - 3.3)
            return avg, avg - 0.0005, avg + 0.0005
        rc, out, _ = self.quick(values_of=vals)
        self.assertEqual(rc, 0, out)
        self.assertIn("line_reg_1ma_mv_per_v=1", out)
        self.assertIn("line_reg_50ma_mv_per_v=4", out)

    def test_slope_bound_is_strict(self):
        exp = corner_run.load_experiment(self.exp_dir)
        m = next(x for x in exp.measurements if x.name == "line_reg_1ma_mv_per_v")
        self.assertEqual(corner_run.grade_bounds(m, 5.0), (False, "not below strict max 5"))
        self.assertTrue(corner_run.grade_bounds(m, math.nextafter(5.0, 0))[0])
        # end to end: exactly 5 mV/V over 0.66 V fails, via the local evaluator
        refs = blr.card_refs(corner_run.endpoint_deck(exp))
        vals = {"tran1.vout_1ma_lo": 1.8, "tran2.vout_1ma_hi": 1.8 + 5 * 0.66e-3}
        got = blr.evaluate(m.expr, vals, refs)
        self.assertAlmostEqual(got, 5.0, places=9)

        def vals_of(p, t, vin, iload):
            avg = 1.8 + 0.0051 * (vin - 3.3)
            return avg, avg - 0.0001, avg + 0.0001
        rc, out, _ = self.quick(values_of=vals_of)
        self.assertEqual(rc, 2)

    def test_output_window_is_inclusive_on_endpoints_and_extrema(self):
        exp = corner_run.load_experiment(self.exp_dir)
        by = {m.name: m for m in exp.measurements}
        for name, lo_hi in (("vout_1ma_lo", (1.764, 1.836)), ("vout_50ma_hi_min", (1.764, None)),
                            ("vout_1ma_hi_max", (None, 1.836))):
            m = by[name]
            for edge in lo_hi:
                if edge is not None:
                    self.assertTrue(corner_run.grade_bounds(m, edge)[0], (name, edge))
        self.assertFalse(corner_run.grade_bounds(by["vout_1ma_lo"], math.nextafter(1.764, 0))[0])
        self.assertFalse(corner_run.grade_bounds(by["vout_1ma_hi_max"], math.nextafter(1.836, 2))[0])

    def test_tail_extremum_outside_window_fails_even_with_in_window_average(self):
        def vals(p, t, vin, iload):
            avg = 1.8 + 0.002 * (vin - 3.3)
            return avg, (1.7 if (vin, iload) == (3.63, "50m") else avg - 0.001), avg + 0.001
        rc, out, _ = self.quick(values_of=vals)
        self.assertEqual(rc, 2)
        self.assertIn("vout_50ma_hi_min=1.7", out)

    def test_two_equal_collapsed_endpoints_cannot_pass_on_zero_slope(self):
        rc, out, _ = self.quick(values_of=lambda p, t, v, i: (1.2, 1.2, 1.2))
        self.assertEqual(rc, 2)
        self.assertIn("line_reg_1ma_mv_per_v=0", out)

    def test_evaluator_refuses_and_never_guesses(self):
        refs = blr.card_refs(corner_run.endpoint_deck(corner_run.load_experiment(self.exp_dir)))
        self.assertIsNone(blr.evaluate("tran1.vout_1ma_lo - tran2.vout_1ma_hi", {"tran1.vout_1ma_lo": 1.0}, refs))
        self.assertIsNone(blr.evaluate("1/(tran1.vout_1ma_lo-tran1.vout_1ma_lo)", {"tran1.vout_1ma_lo": 1.0}, refs))
        for bad in ("tran9.vout_1ma_lo", "__import__('os')", "tran1.vout_1ma_lo ** 2", "sqrt(1)",
                    "tran1.vout_1ma_lo; 1", "abs 1", "(1", ""):
            with self.assertRaises(blr.EndpointTranslationError, msg=bad):
                blr.evaluate(bad, {}, refs)


class TestEndpointNegativeControls(LineRegHarness):
    def test_missing_duplicate_nonfinite_or_unexpected_values_cannot_pass(self):
        edits = {
            "missing": lambda c: c["measurements"].pop(1),
            "duplicate": lambda c: c["measurements"].append(dict(c["measurements"][0])),
            "nan": lambda c: c["measurements"][2].update(value=float("nan")),
            "null": lambda c: c["measurements"][0].update(value=None),
            "string": lambda c: c["measurements"][0].update(value="1.8"),
            "unexpected identity": lambda c: c["measurements"].append(
                {"name": "tran1.not_requested", "value": 1.8, "status": "pass"}),
            "wrong step": lambda c: c["measurements"][0].update(name="dropout.vout_1ma_lo"),
            "unqualified name": lambda c: c["measurements"][0].update(name="vout_1ma_lo"),
            "errored value": lambda c: c["measurements"][0].update(status="error"),
        }
        for name, edit in edits.items():
            def m(resp, req, edit=edit):
                edit(resp["corners"][0])
            rc, out, err = self.quick(mutate=m)
            self.assertEqual(rc, 2, name)
            self.assertIn("FAIL", out, name)

    def test_errored_or_incomplete_corner_cannot_pass(self):
        rc, out, err = self.quick(values_of=lambda p, t, v, i: None if p == "ss" else default_values(p, t, v, i))
        self.assertEqual(rc, 2)
        self.assertIn("ss_-40c_2.97v        FAIL", out)
        self.assertIn("not a completed result", err)
        for edit in (lambda c: c.update(status="error"),
                     lambda c: c.update(diagnostics=[{"severity": "warning", "code": "step_failed", "message": "x"}]),
                     lambda c: c.update(artifacts={})):
            rc, _, _ = self.quick(mutate=lambda r, q, edit=edit: edit(r["corners"][0]))
            self.assertEqual(rc, 2)

    def test_solver_diagnostic_in_any_endpoint_log_fails(self):
        for marker in corner_run.SOLVER_DIAGNOSTIC_MARKERS:
            rc, _, err = self.quick(log_text=f"tran\n{marker} here\n")
            self.assertEqual(rc, 2, marker)
            self.assertIn("solver diagnostic", err)

    def test_structural_failures_abort_without_record_or_fallback(self):
        cases = {
            "missing corner": lambda r, q: r["corners"].clear(),
            "duplicate corner": lambda r, q: r["corners"].append(dict(r["corners"][0])),
            "unexpected corner": lambda r, q: r["corners"][0].update(process="ss"),
            "running": lambda r, q: r["environment"]["remote"].update(state="running", exit_code=""),
            "mismatch": lambda r, q: r["environment"]["remote"].update(runner_compatibility="mismatch"),
            "no remote": lambda r, q: r["environment"].pop("remote"),
        }
        for name, mutate in cases.items():
            self.fake = FakeLineRegKlt(self, self.pin, mutate=mutate)
            err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
            self.assertIn("no evidence record written", str(err), name)
            self.assertFalse((self.exp_dir / "records").exists())
            self.assertEqual(len(self.klt_calls()), 1, name)  # no retry, no local fallback

    def test_error_envelope_aborts(self):
        env = {"schema_version": 1, "error": {"command": "sim", "message": "batch backend failed"}}
        self.fake = FakeLineRegKlt(self, self.pin, stdout=json.dumps(env), rc=1)
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("error envelope", str(err))


class TestEndpointShapeGate(LineRegHarness):
    def refused(self, edit, expect="validated line-regulation endpoint shape"):
        raw = manifest()
        edit(raw)
        self.write_manifest(raw)
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn(expect, str(err))
        self.assertEqual(self.fake.calls, [])
        corner_run.netlist_with_xschem.assert_not_called()
        return str(err)

    def code_lines(self, raw):
        return [i for i, ln in enumerate(raw["deck"]["analyses"]) if not ln.lstrip().startswith("*")]

    def find(self, raw, prefix, nth=0):
        hits = [i for i in self.code_lines(raw) if raw["deck"]["analyses"][i].startswith(prefix)]
        return hits[nth]

    def test_unsupported_cards_and_altered_stimulus_are_refused_before_netlisting(self):
        def setl(prefix, text, nth=0):
            def e(raw):
                raw["deck"]["analyses"][self.find(raw, prefix, nth)] = text
            return e
        edits = [
            setl("tran", "tran 10u 200m"),                                    # no cold start
            setl("tran", "tran 10u 200m 0 1u uic"),                           # tstart/tmax
            setl("alter @ven[pwl]", "alter @ven[pwl] = [ 0 0 100u 0 101u 3.3 10 $vinpt ]"),  # EN != VIN
            setl("alter @ven[pwl]", "alter @ven[pwl] = [ 0 0 100u 0 101u $vinpt 10 3.63 ]", 1),
            setl("alter vvin", "alter vvin = 3.3"),                           # VIN not from the literal
            setl("meas tran vout_1ma_lo avg", "meas tran vout_1ma_lo rms v(vout) from=199m to=200m"),
            setl("meas tran vout_1ma_lo avg", "meas tran vout_1ma_lo avg v(vout)"),  # no window
            setl("meas tran vout_1ma_lo avg", "meas tran vout_1ma_lo find v(vout) when v(vin)=1 fall=1"),
            lambda r: r["deck"]["analyses"].insert(self.find(r, "tran"), "op"),
            lambda r: r["deck"]["analyses"].append("ic v(vout)=0"),
            lambda r: r["deck"]["analyses"].append("let x = 1"),
            lambda r: r["deck"]["analyses"].append("reset"),
            lambda r: r["deck"]["analyses"].__delitem__(self.find(r, "tran", 3)),      # three endpoints
            lambda r: r["measurements"][0].update(expr="abs(1000*(tran2.vout_1ma_hi - tran9.x))"),
            lambda r: r["measurements"][0].update(expr="abs(1000*(vout_1ma_hi - vout_1ma_lo))"),
            lambda r: r["measurements"][0].update(expr="v(vout)"),
            lambda r: r.update(spread_checks=[{"measurement": "vout_1ma_lo", "min_spread": 0.001}]),
        ]
        for edit in edits:
            self.refused(edit)

    def test_any_execution_manifest_change_needs_renewed_validation(self):
        edits = {
            "slope bound": lambda r: r["measurements"][0].update(max=5.5),
            "strictness": lambda r: r["measurements"][0].update(max_inclusive=True),
            "window": lambda r: r["measurements"][2].update(min=1.7),
            "window edge": lambda r: r["deck"]["analyses"].__setitem__(
                self.find(r, "meas tran vout_1ma_lo avg"), "meas tran vout_1ma_lo avg v(vout) from=190m to=200m"),
            "duration": lambda r: r["deck"]["analyses"].__setitem__(self.find(r, "tran", 0), "tran 10u 100m uic"),
            "iload": lambda r: r["deck"]["analyses"].__setitem__(self.find(r, "alter iload"), "alter iload = 40m"),
            "vin": lambda r: r["deck"]["analyses"].__setitem__(self.find(r, "set vinpt"), "set vinpt = 3.0"),
            "option": lambda r: r["deck"]["options"].append("reltol=1e-4"),
            "matrix": lambda r: r["corners"]["supply_v"].pop(),
            "quick subset": lambda r: r["quick_subset"].pop(),
        }
        for name, edit in edits.items():
            self.assertIn("re-validate", self.refused(edit), name)

    def test_prose_only_edits_keep_the_validated_shape(self):
        raw = manifest()
        raw["claim"] += " (edited)"
        raw["measurements"][0]["note"] = "short"
        raw["deck"]["analyses"].insert(0, "* an added comment")
        self.write_manifest(raw)
        rc, _, _ = self.run_main("--backend", "batch", *QUICK, "--no-write")
        self.assertEqual(rc, 0)

    def test_pins_equal_the_committed_manifest(self):
        want = corner_run.BATCH_ALLOWLIST[SLUG]["manifest_sections"]
        self.assertEqual(pvt_input_sections(manifest(), None), want)

    def test_sibling_regulation_benches_stay_refused(self):
        for slug in ("load-regulation", "iq", "psrr-dc", "startup"):
            self.assertNotIn(slug, corner_run.BATCH_ALLOWLIST)


class TestEndpointNetlistGate(LineRegHarness):
    def refused_netlist(self, netlist):
        self.NETLIST = netlist
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("netlist is not the validated line-regulation endpoint baseline", str(err))
        self.assertEqual(self.fake.calls, [])
        return str(err)

    def test_changed_baseline_stimulus_is_refused_before_submission(self):
        self.refused_netlist(LR_NETLIST.replace("VVIN VIN 0 3.3", "VVIN VIN 0 3.0"))
        self.refused_netlist(LR_NETLIST.replace("101u 3.3 10 3.3", "101u 2.0 10 3.3"))
        self.refused_netlist(LR_NETLIST.replace(STIMULUS[2] + "\n", ""))
        self.refused_netlist(LR_NETLIST.replace(STIMULUS[2], STIMULUS[2] + "\nILOAD VOUT 0 10m"))
        self.refused_netlist(LR_NETLIST.replace(STIMULUS[2], "ILOAD VOUT 0 50m"))

    def test_initial_condition_and_control_cards_are_refused(self):
        for card in (".ic v(vout)=1.8", ".nodeset v(vout)=1.8", ".control", ".tran 1u 1m",
                     ".meas tran x avg v(vout)", ".temp 50"):
            msg = self.refused_netlist(LR_NETLIST.replace(".end\n", card + "\n.end\n"))
            self.assertIn(card.split()[0], msg)


class TestEndpointRecord(LineRegHarness):
    def test_record_keeps_provenance_fingerprint_subset_and_adapter(self):
        rc, out, _ = self.run_main("--backend", "batch", *QUICK)
        self.assertEqual(rc, 0, out)
        (rec_path,) = self.records()
        rec = json.loads(rec_path.read_text())
        self.assertEqual(rec["backend"], "batch")
        self.assertTrue(rec["matrix"]["is_subset"])
        self.assertEqual([r["corner_id"] for r in rec["corners"]], rec["matrix"]["point_ids"])
        self.assertEqual(rec["input_fingerprint"]["sections"]["analyses"],
                         corner_run.BATCH_ALLOWLIST[SLUG]["manifest_sections"]["analyses"])
        ad = rec["execution"]["adapter"]
        self.assertEqual((ad["name"], ad["issue"]), ("line-regulation-endpoints", 379))
        self.assertEqual([(e["step"], e["vin"], e["iload"]) for e in ad["endpoints"]], ENDPOINTS)
        self.assertEqual(ad["validated_baseline_stimulus"], STIMULUS)
        self.assertEqual(len(rec["execution"]["requests"]), 12)
        self.assertEqual({r["endpoint"] for r in rec["execution"]["requests"]}, {e[0] for e in ENDPOINTS})
        c0 = rec["corners"][0]
        self.assertEqual(len(c0["klt_request"]), 4)
        self.assertEqual(len(c0["measurements"]), len(manifest()["measurements"]))
        log = (self.exp_dir / "corners" / rec["record_id"]).iterdir()
        text = next(iter(log)).read_text()
        self.assertEqual(text.count("line-regulation endpoint tran"), 4)


if __name__ == "__main__":
    unittest.main()
