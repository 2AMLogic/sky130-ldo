"""Issue #381: the load-regulation endpoint adapter on the opt-in `klt sim`
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
import batch_load_regulation as bld  # noqa: E402
from _record_common import pvt_input_sections  # noqa: E402

SLUG = "load-regulation"
STIMULUS = corner_run.BATCH_ALLOWLIST[SLUG]["stimulus"]
SUPPLY = "'vsup'"
LD_NETLIST = (
    "** sch_path: x\n"
    + "\n".join(
        [STIMULUS[0], ".save i(vvin)", STIMULUS[1], "VVREF VREF 0 1.2",
         "xldo VOUT VREF EN VIN ldo_3v3in_1v8out", "COUT VOUT VESR 1u m=1", "RESR VESR 0 10m m=1",
         STIMULUS[2], ".subckt ldo_3v3in_1v8out VOUT VREF EN VIN", "R1 VIN VOUT 1", ".ends"]
    )
    + "\n.end\n"
)
ENDPOINTS = [("tran1", SUPPLY, "0"), ("tran2", SUPPLY, "50m")]
CARDS = ["vout_0ma", "vout_0ma_min", "vout_0ma_max", "vout_50ma", "vout_50ma_min", "vout_50ma_max"]


def manifest() -> dict:
    return json.loads((SIM_DIR / SLUG / "experiment.json").read_text())


def default_values(p, t, iload):
    """(avg, min, max) of a healthy endpoint: 2 mV load droop."""
    avg = 1.8 - (0.002 if iload == "50m" else 0.0)
    return avg, avg - 0.001, avg + 0.001


class FakeLoadRegKlt(FakeKlt):
    def __init__(self, test, pin, values_of=None, log_text=None, **kw):
        super().__init__(test, pin, **kw)
        self.values_of = values_of or default_values
        self.log_text = log_text
        self.seen = []  # (request json, netlist lines)

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
        self.seen.append((req, lines))
        iload = next(ln for ln in lines if ln.startswith("ILOAD ")).split()[3]
        outdir = Path(cmd[cmd.index("-o") + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        corners = []
        for p in req["corners"]["process"]:
            for t in req["corners"]["temperature_c"]:
                vals = self.values_of(p, t, iload)
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
                            "remote": {"provider": "aws-batch-fleet", "job_id": "klt-sim-00ee02",
                                       "state": "done", "exit_code": "0",
                                       "runner_compatibility": "match"}},
            "provenance": {"klt_version": "0.7.0", "pdk": {"version": self.pin["open_pdks_commit"]}},
        }
        if self.mutate:
            self.mutate(resp, req)
        out = self.stdout if self.stdout is not None else json.dumps(resp)
        return subprocess.CompletedProcess(cmd, self.rc, stdout=out, stderr="")


class LoadRegHarness(BatchHarness):
    SLUG = SLUG
    NETLIST = LD_NETLIST

    def make_fake(self, **kw):
        return FakeLoadRegKlt(self, self.pin, **kw)

    def requests(self):
        return [json.loads(Path(c[0][2]).read_text()) for c in self.klt_calls()]

    def write_manifest(self, raw):
        (self.exp_dir / "experiment.json").write_text(json.dumps(raw))

    def quick(self, **fake_kw):
        self.fake = FakeLoadRegKlt(self, self.pin, **fake_kw)
        return self.run_main("--backend", "batch", *QUICK, "--no-write")


class TestEndpointTranslation(LoadRegHarness):
    def test_two_endpoint_states_supply_linked_vin_en_and_independent_load(self):
        exp = corner_run.load_experiment(self.exp_dir)
        eps = corner_run.endpoint_deck(exp)
        self.assertEqual([(e.step_name, e.vin, e.iload) for e in eps], ENDPOINTS)
        for e in eps:
            src = bld.endpoint_source_lines(e)
            # VIN and EN's high level stay the corner supply parameter, never a number
            self.assertEqual(src["vvin"], "VVIN VIN 0 'vsup'")
            self.assertEqual(src["ven"], "VEN EN 0 dc 0 pwl(0 0 100u 0 101u 'vsup' 10 'vsup')")
            self.assertEqual(src["iload"], f"ILOAD VOUT 0 {e.iload}")
            self.assertEqual(e.tran_args, "10u 200m uic")
        # the baseline stimulus pin is exactly what the endpoint requests write
        self.assertEqual(list(bld.endpoint_source_lines(eps[0]).values()), STIMULUS)

    def test_request_netlists_carry_each_endpoints_complete_state(self):
        rc, _, _ = self.quick()
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 6)  # 3 singleton tuples x 2 endpoints, no Cartesian expansion
        for i, req in enumerate(reqs):
            name, _, iload = ENDPOINTS[i % 2]
            body = Path(req["netlist"]).read_text().splitlines()
            self.assertEqual([ln for ln in body if ln.startswith("VVIN ")], [STIMULUS[0]])
            self.assertEqual([ln for ln in body if ln.startswith("VEN ")], [STIMULUS[1]])
            self.assertEqual([ln for ln in body if ln.startswith("ILOAD ")], [f"ILOAD VOUT 0 {iload}"])
            (step,) = req["analysis_steps"]
            self.assertEqual(step["name"], name)
            self.assertEqual(step["analysis"], {"kind": "tran", "args": "10u 200m uic"})
            self.assertNotIn("alter", step)
            # corner supply param is the request's first line and 'vsup' is its only source link
            self.assertRegex(body[0], r"^\.param vsup=")
            self.assertEqual(body[1:3], [".option wnflag=1", ".save all"])

    def test_all_six_raw_cards_keep_windows_and_kinds(self):
        self.quick()
        reqs = self.requests()
        got = []
        for req in reqs[:2]:
            for m in req["analysis_steps"][0]["measurements"]:
                got.append((req["analysis_steps"][0]["name"], m["name"], m["spice"], m["unit"]))
        self.assertEqual(len(got), 6)
        self.assertEqual([g[1] for g in got], CARDS)
        for (step, name, spice, unit), kind in zip(got, ["avg", "min", "max"] * 2):
            self.assertEqual(spice, f".meas tran {name} {kind} v(vout) from=199m to=200m")
            self.assertEqual(unit, "V")
        self.assertEqual({g[0] for g in got[:3]}, {"tran1"})
        self.assertEqual({g[0] for g in got[3:]}, {"tran2"})
        # derived differences are NOT sent to klt: they span two requests
        for req in reqs:
            self.assertFalse(any("load_reg" in m["name"] for m in req["analysis_steps"][0]["measurements"]))

    def test_step_cards_are_the_local_deck_cards(self):
        exp = corner_run.load_experiment(self.exp_dir)
        deck = corner_run.build_deck(exp, type("P", (), {"lib_file": "/x/l"})(),
                                     corner_run.Corner("tt", 27, 3.3), ["* b"]).splitlines()
        self.assertEqual(deck.count("tran 10u 200m uic"), 2)
        self.assertEqual(deck.count("alter iload = 50m"), 1)
        for e in corner_run.endpoint_deck(exp):
            step = corner_run.endpoint_step(exp, e.step_name)
            self.assertIn(f"tran {step['analysis']['args']}", deck)
            for m in step["measurements"]:
                self.assertIn(m["spice"][1:], deck)
        # no operating-point solve anywhere in the deck or the requests
        self.assertFalse(any(ln.split()[0:1] == ["op"] for ln in deck))

    def test_full_matrix_preserves_all_45_identities(self):
        rc, _, _ = self.run_main("--backend", "batch", "--no-write")
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 6)  # 3 supply values x 2 endpoints
        self.assertTrue(all(r["corners"]["process"] == ["tt", "ss", "ff", "sf", "fs"]
                            and r["corners"]["temperature_c"] == [-40.0, 27.0, 125.0] for r in reqs))
        self.assertEqual([Path(r["netlist"]).read_text().splitlines()[0] for r in reqs[::2]],
                         [".param vsup=2.97", ".param vsup=3.3", ".param vsup=3.63"])
        self.assertEqual(sum(len(r["corners"]["process"]) * len(r["corners"]["temperature_c"])
                             for r in reqs[::2]), 45)

    def test_explicit_quick_subset_is_singletons_per_endpoint(self):
        self.quick()
        reqs = self.requests()
        self.assertEqual([r["corners"] for r in reqs[::2]], [
            {"process": ["tt"], "temperature_c": [27.0]},
            {"process": ["ss"], "temperature_c": [-40.0]},
            {"process": ["ff"], "temperature_c": [125.0]}])
        self.assertEqual([Path(r["netlist"]).read_text().splitlines()[0] for r in reqs[::2]],
                         [".param vsup=3.3", ".param vsup=2.97", ".param vsup=3.63"])

    def test_dry_run_submits_nothing_and_names_adapter(self):
        rc, out, _ = self.run_main("--backend", "batch", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertEqual(self.fake.calls, [])
        self.assertIn("batch adapter load-regulation-endpoints (issue #381)", out)
        self.assertEqual(out.count('"analysis_steps"'), 6)
        self.assertFalse((self.exp_dir / "records").exists())

    def test_local_backend_is_unchanged(self):
        exp = corner_run.load_experiment(self.exp_dir)
        before = corner_run.build_deck(exp, type("P", (), {"lib_file": "/x/l"})(),
                                       corner_run.Corner("tt", 27, 3.3), ["VVIN VIN 0 'vsup'"])
        self.assertIn("alter iload = 50m", before)
        self.assertEqual(before.count("tran 10u 200m uic"), 2)


class TestEndpointGrading(LoadRegHarness):
    def test_healthy_run_passes_and_delta_maps_to_the_right_endpoints(self):
        rc, out, _ = self.quick()
        self.assertEqual(rc, 0, out)
        self.assertIn("load_reg_v=0.002", out)
        self.assertIn("vout_0ma_v=1.8", out)

    def test_delta_uses_tran2_minus_tran1_and_pct_of_1v8(self):
        exp = corner_run.load_experiment(self.exp_dir)
        refs = bld.card_refs(corner_run.endpoint_deck(exp))
        by = {m.name: m for m in exp.measurements}
        vals = {"tran1.vout_0ma": 1.80, "tran2.vout_50ma": 1.79}
        self.assertAlmostEqual(bld.evaluate(by["load_reg_v"].expr, vals, refs), 0.01, places=12)
        self.assertAlmostEqual(bld.evaluate(by["load_reg_pct"].expr, vals, refs), 100 * 0.01 / 1.8, places=9)
        vals = {"tran1.vout_0ma": 1.79, "tran2.vout_50ma": 1.80}  # abs(): sign-independent
        self.assertAlmostEqual(bld.evaluate(by["load_reg_v"].expr, vals, refs), 0.01, places=12)

    def test_delta_bounds_are_strict_at_exactly_the_limit(self):
        exp = corner_run.load_experiment(self.exp_dir)
        by = {m.name: m for m in exp.measurements}
        self.assertEqual(corner_run.grade_bounds(by["load_reg_v"], 0.018), (False, "not below strict max 0.018"))
        self.assertEqual(corner_run.grade_bounds(by["load_reg_pct"], 1.0), (False, "not below strict max 1"))
        self.assertTrue(corner_run.grade_bounds(by["load_reg_v"], math.nextafter(0.018, 0))[0])
        self.assertTrue(corner_run.grade_bounds(by["load_reg_pct"], math.nextafter(1.0, 0))[0])
        # end to end: a 20 mV droop (above the bound) fails through the batch grader
        rc, out, _ = self.quick(values_of=lambda p, t, i: (1.82 - (0.02 if i == "50m" else 0), 1.78, 1.83))
        self.assertEqual(rc, 2)

    def test_output_window_is_inclusive_on_endpoints_and_extrema(self):
        exp = corner_run.load_experiment(self.exp_dir)
        by = {m.name: m for m in exp.measurements}
        for name, edges in (("vout_0ma_v", (1.764, 1.836)), ("vout_50ma_v", (1.764, 1.836)),
                            ("vout_0ma_min_v", (1.764,)), ("vout_50ma_min_v", (1.764,)),
                            ("vout_0ma_max_v", (1.836,)), ("vout_50ma_max_v", (1.836,))):
            for edge in edges:
                self.assertTrue(corner_run.grade_bounds(by[name], edge)[0], (name, edge))
        self.assertFalse(corner_run.grade_bounds(by["vout_0ma_v"], math.nextafter(1.764, 0))[0])
        self.assertFalse(corner_run.grade_bounds(by["vout_50ma_max_v"], math.nextafter(1.836, 2))[0])
        self.assertFalse(corner_run.grade_bounds(by["vout_0ma_min_v"], math.nextafter(1.764, 0))[0])

    def test_equal_out_of_window_endpoints_fail_despite_zero_delta(self):
        rc, out, _ = self.quick(values_of=lambda p, t, i: (1.2, 1.2, 1.2))
        self.assertEqual(rc, 2)
        self.assertIn("load_reg_v=0", out)

    def test_averages_in_window_with_extrema_outside_fail(self):
        for which, vals in (
            ("min 0mA", lambda p, t, i: (1.8, 1.7 if i == "0" else 1.799, 1.801)),
            ("min 50mA", lambda p, t, i: (1.8, 1.7 if i == "50m" else 1.799, 1.801)),
            ("max 0mA", lambda p, t, i: (1.8, 1.799, 1.9 if i == "0" else 1.801)),
            ("max 50mA", lambda p, t, i: (1.8, 1.799, 1.9 if i == "50m" else 1.801)),
        ):
            rc, out, _ = self.quick(values_of=vals)
            self.assertEqual(rc, 2, which)

    def test_evaluator_refuses_and_never_guesses(self):
        refs = bld.card_refs(corner_run.endpoint_deck(corner_run.load_experiment(self.exp_dir)))
        self.assertIsNone(bld.evaluate("tran1.vout_0ma - tran2.vout_50ma", {"tran1.vout_0ma": 1.0}, refs))
        for bad in ("tran9.vout_0ma", "__import__('os')", "tran1.vout_0ma ** 2", "sqrt(1)", "(1", ""):
            with self.assertRaises(bld.EndpointTranslationError, msg=bad):
                bld.evaluate(bad, {}, refs)


class TestEndpointNegativeControls(LoadRegHarness):
    def test_missing_duplicate_nonfinite_or_unexpected_values_cannot_pass(self):
        edits = {
            "missing": lambda c: c["measurements"].pop(1),
            "duplicate": lambda c: c["measurements"].append(dict(c["measurements"][0])),
            "nan": lambda c: c["measurements"][2].update(value=float("nan")),
            "null": lambda c: c["measurements"][0].update(value=None),
            "string": lambda c: c["measurements"][0].update(value="1.8"),
            "unexpected identity": lambda c: c["measurements"].append(
                {"name": "tran1.not_requested", "value": 1.8, "status": "pass"}),
            "wrong step": lambda c: c["measurements"][0].update(name="dropout.vout_0ma"),
            "unqualified name": lambda c: c["measurements"][0].update(name="vout_0ma"),
            "errored value": lambda c: c["measurements"][0].update(status="error"),
        }
        for name, edit in edits.items():
            def m(resp, req, edit=edit):
                edit(resp["corners"][0])
            rc, out, err = self.quick(mutate=m)
            self.assertEqual(rc, 2, name)
            self.assertIn("FAIL", out, name)

    def test_errored_or_incomplete_corner_cannot_pass(self):
        rc, out, err = self.quick(values_of=lambda p, t, i: None if p == "ss" else default_values(p, t, i))
        self.assertEqual(rc, 2)
        self.assertIn("ss_-40c_2.97v        FAIL", out)
        self.assertIn("not a completed result", err)
        for edit in (lambda c: c.update(status="error"),
                     lambda c: c.update(diagnostics=[{"severity": "warning", "code": "step_failed", "message": "x"}]),
                     lambda c: c.update(artifacts={})):  # missing log
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
            self.fake = FakeLoadRegKlt(self, self.pin, mutate=mutate)
            err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
            self.assertIn("no evidence record written", str(err), name)
            self.assertFalse((self.exp_dir / "records").exists())
            self.assertEqual(len(self.klt_calls()), 1, name)  # no retry, no local fallback

    def test_error_envelope_aborts(self):
        env = {"schema_version": 1, "error": {"command": "sim", "message": "batch backend failed"}}
        self.fake = FakeLoadRegKlt(self, self.pin, stdout=json.dumps(env), rc=1)
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("error envelope", str(err))


class TestEndpointShapeGate(LoadRegHarness):
    def refused(self, edit, expect="validated load-regulation endpoint shape"):
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
            setl("meas tran vout_0ma avg", "meas tran vout_0ma rms v(vout) from=199m to=200m"),
            setl("meas tran vout_0ma avg", "meas tran vout_0ma avg v(vout)"),  # no window
            setl("meas tran vout_0ma avg", "meas tran vout_0ma find v(vout) when v(vin)=1 fall=1"),
            setl("alter iload", "alter iload = 0"),                           # identical loads
            setl("alter iload", "alter vven = 0"),                            # unsupported alter
            lambda r: r["deck"]["analyses"].insert(self.find(r, "tran"), "op"),
            lambda r: r["deck"]["analyses"].insert(self.find(r, "tran"), "alter iload = 10m"),  # point 1 load
            lambda r: r["deck"]["analyses"].insert(self.find(r, "tran"), "set vinpt = 3.3"),
            lambda r: r["deck"]["analyses"].insert(self.find(r, "tran"), "alter @ven[pwl] = [ 0 0 ]"),
            lambda r: r["deck"]["analyses"].append("ic v(vout)=0"),
            lambda r: r["deck"]["analyses"].append("let x = 1"),
            lambda r: r["deck"]["analyses"].append("reset"),
            lambda r: r["deck"]["analyses"].__delitem__(self.find(r, "meas tran vout_0ma_min")),
            lambda r: r["deck"]["analyses"].__delitem__(self.find(r, "alter iload")),
            lambda r: r["deck"]["analyses"].__delitem__(self.find(r, "tran", 1)),
            lambda r: r["measurements"][0].update(expr="abs(tran2.vout_50ma - tran9.x)"),
            lambda r: r["measurements"][0].update(expr="abs(vout_50ma - vout_0ma)"),
            lambda r: r["measurements"][0].update(expr="v(vout)"),
            lambda r: r.update(spread_checks=[{"measurement": "vout_0ma_v", "min_spread": 0.001}]),
        ]
        for edit in edits:
            self.refused(edit)

    def test_any_execution_manifest_change_needs_renewed_validation(self):
        edits = {
            "delta bound": lambda r: r["measurements"][0].update(max=0.02),
            "strictness": lambda r: r["measurements"][0].update(max_inclusive=True),
            "pct strictness": lambda r: r["measurements"][1].update(max_inclusive=True),
            "window": lambda r: r["measurements"][2].update(min=1.7),
            "extremum bound": lambda r: r["measurements"][3].update(min=1.7),
            "window edge": lambda r: r["deck"]["analyses"].__setitem__(
                self.find(r, "meas tran vout_0ma avg"), "meas tran vout_0ma avg v(vout) from=190m to=200m"),
            "duration": lambda r: r["deck"]["analyses"].__setitem__(self.find(r, "tran", 0), "tran 10u 100m uic"),
            "iload": lambda r: r["deck"]["analyses"].__setitem__(self.find(r, "alter iload"), "alter iload = 40m"),
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
        for slug in ("psrr-dc", "startup"):
            self.assertNotIn(slug, corner_run.BATCH_ALLOWLIST)


class TestEndpointNetlistGate(LoadRegHarness):
    def refused_netlist(self, netlist):
        self.NETLIST = netlist
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("netlist is not the validated load-regulation endpoint baseline", str(err))
        self.assertEqual(self.fake.calls, [])
        return str(err)

    def test_changed_baseline_stimulus_is_refused_before_submission(self):
        self.refused_netlist(LD_NETLIST.replace(STIMULUS[0], "VVIN VIN 0 3.3"))       # fixed VIN literal
        self.refused_netlist(LD_NETLIST.replace("101u 'vsup' 10 'vsup'", "101u 2.0 10 'vsup'"))
        self.refused_netlist(LD_NETLIST.replace(STIMULUS[1] + "\n", ""))              # no EN
        self.refused_netlist(LD_NETLIST.replace(STIMULUS[1], STIMULUS[1] + "\n" + STIMULUS[1]))
        self.refused_netlist(LD_NETLIST.replace(STIMULUS[2] + "\n", ""))
        self.refused_netlist(LD_NETLIST.replace(STIMULUS[2], STIMULUS[2] + "\nILOAD VOUT 0 10m"))
        self.refused_netlist(LD_NETLIST.replace(STIMULUS[2], "ILOAD VOUT 0 50m"))

    def test_initial_condition_and_control_cards_are_refused(self):
        for card in (".ic v(vout)=1.8", ".nodeset v(vout)=1.8", ".control", ".tran 1u 1m",
                     ".meas tran x avg v(vout)", ".temp 50"):
            msg = self.refused_netlist(LD_NETLIST.replace(".end\n", card + "\n.end\n"))
            self.assertIn(card.split()[0], msg)

    def test_line_regulation_baseline_is_not_accepted_here(self):
        lr = "VVIN VIN 0 3.3"
        self.refused_netlist(LD_NETLIST.replace(STIMULUS[0], lr).replace(STIMULUS[2], "ILOAD VOUT 0 1m"))


class TestEndpointRecord(LoadRegHarness):
    def test_record_keeps_provenance_fingerprint_subset_and_adapter(self):
        rc, out, _ = self.run_main("--backend", "batch", *QUICK)
        self.assertEqual(rc, 0, out)
        (rec_path,) = self.records()
        rec = json.loads(rec_path.read_text())
        self.assertEqual(rec["backend"], "batch")
        self.assertTrue(rec["matrix"]["is_subset"])
        self.assertEqual([r["corner_id"] for r in rec["corners"]], rec["matrix"]["point_ids"])
        sections = corner_run.BATCH_ALLOWLIST[SLUG]["manifest_sections"]
        for k, v in sections.items():
            self.assertEqual(rec["input_fingerprint"]["sections"][k], v)
        ad = rec["execution"]["adapter"]
        self.assertEqual((ad["name"], ad["issue"]), ("load-regulation-endpoints", 381))
        self.assertEqual([(e["step"], e["vin"], e["iload"]) for e in ad["endpoints"]], ENDPOINTS)
        self.assertEqual(ad["validated_baseline_stimulus"], STIMULUS)
        self.assertEqual(ad["validated_manifest_sections"], sections)
        self.assertEqual(len(rec["execution"]["requests"]), 6)
        self.assertEqual({r["endpoint"] for r in rec["execution"]["requests"]}, {"tran1", "tran2"})
        for r in rec["execution"]["requests"]:
            self.assertEqual(r["job_id"], "klt-sim-00ee02")
            self.assertEqual(r["engine"], "ngspice")
        c0 = rec["corners"][0]
        self.assertEqual(len(c0["klt_request"]), 2)
        self.assertEqual(len(c0["measurements"]), len(manifest()["measurements"]))
        md = rec_path.with_suffix(".md").read_text()
        self.assertIn("do not establish local/fleet numerical equivalence", md)
        log = (self.exp_dir / "corners" / rec["record_id"]).iterdir()
        text = next(iter(log)).read_text()
        self.assertEqual(text.count("load-regulation endpoint tran"), 2)


if __name__ == "__main__":
    unittest.main()
