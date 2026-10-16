"""Issue #374: the dropout-vs-load cold-start crossing adapter on the opt-in
`klt sim` batch backend.

PDK-free and headless: klt, xschem, git and the PDK are mocked by
test_corner_run.BatchHarness, so nothing is submitted and no ngspice runs.
Two fixtures under fixtures/issue-374/ are REAL `klt sim --backend local`
responses (klt 0.7.0, ngspice-46) captured once while building the adapter:
`tt27-3v30` is the harness-generated request for tt / 27 C / 3.30 V (its
values equal the local harness's for that corner), `no-crossing` is a
PDK-free RC deck whose crossing card never fires. They pin the real response
contract the grader reads; they are local-backend captures, not evidence of
remote (fleet) execution.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from test_corner_run import QUICK, SIM_DIR, BatchHarness, FakeKlt, HarnessErr, corner_run

sys.path.insert(0, str(SIM_DIR / "bin"))
import batch_dropout as bd  # noqa: E402
from _record_common import pvt_input_sections  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "issue-374"
SLUG = "dropout-vs-load"
STIMULUS = corner_run.BATCH_ALLOWLIST[SLUG]["stimulus"]
DT_NETLIST = (
    "** sch_path: x\n"
    + "\n".join(
        [STIMULUS[0], ".save i(vvin)", STIMULUS[1], "VVREF VREF 0 1.2",
         "xldo VOUT VREF EN VIN ldo_3v3in_1v8out", "COUT VOUT VESR 1u m=1", "RESR VESR 0 10m m=1",
         STIMULUS[2], ".subckt ldo_3v3in_1v8out VOUT VREF EN VIN", "R1 VIN VOUT 1", ".ends"]
    )
    + "\n.end\n"
)


def manifest() -> dict:
    return json.loads((SIM_DIR / SLUG / "experiment.json").read_text())


class FakeDropoutKlt(FakeKlt):
    """Answers a single-step cold-start request the way klt 0.7 does (see the
    captured fixtures): `<step>.<name>` results, a retained engine log and a
    finished batch job in environment.remote."""

    def __init__(self, test, pin, value_of=None, log_text=None, **kw):
        super().__init__(test, pin, **kw)
        self.value_of = value_of or (lambda p, t, vsup: 0.25)
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
        vsup = float(Path(req["netlist"]).read_text().splitlines()[0].split("=")[1])
        outdir = Path(cmd[cmd.index("-o") + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        corners = []
        for p in req["corners"]["process"]:
            for t in req["corners"]["temperature_c"]:
                d = self.value_of(p, t, vsup)
                logp = outdir / f"{p}_{t}.log"
                logp.write_text(self.log_text or f"Operating point simulation skipped by 'uic'\n{p} {t}\n")
                vals = {"dropout_vin_x": None if d is None else d + 1.764,
                        "vout_at_max_vin_v": 1.8, "dropout_v": d}
                corners.append({
                    "corner_id": f"{p}/novdd/{t:g}C", "process": p, "temperature_c": t,
                    "status": "pass" if d is not None else "error", "runtime_s": 17.0,
                    "diagnostics": [] if d is not None else [
                        {"severity": "error", "code": "measurement",
                         "message": "measurement 'dropout.dropout_vin_x' produced no value"}],
                    "artifacts": {"log": str(logp)},
                    "measurements": [
                        {"name": f"{step['name']}.{m['name']}", "value": vals[m["name"]],
                         "status": "pass" if vals[m["name"]] is not None else "error"}
                        for m in step["measurements"]
                    ],
                })
        resp = {
            "status": "pass", "corners": corners,
            "environment": {"engine": "ngspice", "engine_version": "46",
                            "remote": {"provider": "aws-batch-fleet", "job_id": "klt-sim-00dd01",
                                       "state": "done", "exit_code": "0",
                                       "runner_compatibility": "match"}},
            "provenance": {"klt_version": "0.7.0", "pdk": {"version": self.pin["open_pdks_commit"]}},
        }
        if self.mutate:
            self.mutate(resp, req)
        out = self.stdout if self.stdout is not None else json.dumps(resp)
        return subprocess.CompletedProcess(cmd, self.rc, stdout=out, stderr="")


class DropoutHarness(BatchHarness):
    SLUG = SLUG
    NETLIST = DT_NETLIST

    def setUp(self):
        super().setUp()
        # the copied tree carries ~20 MB of committed #357 diagnostics the
        # adapter never reads; drop it from the scratch copy
        shutil.rmtree(self.exp_dir / "diagnostics", ignore_errors=True)

    def make_fake(self, **kw):
        return FakeDropoutKlt(self, self.pin, **kw)

    def requests(self):
        return [json.loads(Path(c[0][2]).read_text()) for c in self.klt_calls()]

    def write_manifest(self, raw):
        (self.exp_dir / "experiment.json").write_text(json.dumps(raw))

    def quick(self, **fake_kw):
        self.fake = FakeDropoutKlt(self, self.pin, **fake_kw)
        return self.run_main("--backend", "batch", *QUICK, "--no-write")


class TestDropoutRequests(DropoutHarness):
    def test_dry_run_emits_inspectable_requests_without_submission(self):
        rc, out, _ = self.run_main("--backend", "batch", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertEqual(self.fake.calls, [])
        self.assertIn("backend         : batch (3 klt sim request(s))", out)
        self.assertEqual(out.count('"analysis_steps"'), 3)
        self.assertEqual(out.count('"args": "10u 14m uic"'), 3)
        self.assertIn("batch adapter cold-start-crossing", out)
        for ln in STIMULUS:
            self.assertIn(ln, out)
        self.assertFalse((self.exp_dir / "records").exists())
        self.assertFalse((self.exp_dir / "klt-requests").exists())

    def test_request_preserves_cold_start_stimulus_and_crossing_semantics(self):
        rc, _, _ = self.run_main("--backend", "batch", *QUICK, "--no-write")
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 3)  # quick tuples are singletons
        self.assertEqual([r["corners"] for r in reqs], [
            {"process": ["tt"], "temperature_c": [27.0]},
            {"process": ["ss"], "temperature_c": [-40.0]},
            {"process": ["ff"], "temperature_c": [125.0]}])
        (step,) = reqs[0]["analysis_steps"]
        self.assertEqual(step["name"], "dropout")
        self.assertEqual(step["analysis"], {"kind": "tran", "args": "10u 14m uic"})
        self.assertNotIn("alter", step)
        self.assertEqual(step["measurements"], [
            {"name": "dropout_vin_x",
             "spice": ".meas tran dropout_vin_x find v(vin) when v(vout)=1.764 fall=1 td=6m"},
            {"name": "vout_at_max_vin_v",
             "spice": ".meas tran vout_at_max_vin_v avg v(vout) from=5.5m to=6m", "unit": "V"},
            {"name": "dropout_v", "expr": "dropout_vin_x - 1.764", "unit": "V"}])
        body = Path(reqs[0]["netlist"]).read_text().splitlines()
        self.assertEqual(body[:3], [".param vsup=3.3", ".option wnflag=1", ".save all"])
        for ln in STIMULUS:
            self.assertEqual(body.count(ln), 1)
        self.assertEqual([Path(r["netlist"]).read_text().splitlines()[0] for r in reqs],
                         [".param vsup=3.3", ".param vsup=2.97", ".param vsup=3.63"])
        init = [ln for ln in (SIM_DIR / "spiceinit").read_text().splitlines() if ln.strip()]
        self.assertEqual(reqs[0]["options"]["ngspice_init"], init)

    def test_full_matrix_is_one_request_per_supply(self):
        rc, _, _ = self.run_main("--backend", "batch", "--no-write")
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 3)
        self.assertTrue(all(r["corners"]["process"] == ["tt", "ss", "ff", "sf", "fs"]
                            and r["corners"]["temperature_c"] == [-40.0, 27.0, 125.0] for r in reqs))

    def test_step_is_the_local_deck_command_for_command(self):
        exp = corner_run.load_experiment(self.exp_dir)
        deck = corner_run.build_deck(exp, mock.Mock(lib_file="/x/l"),
                                     corner_run.Corner("tt", 27, 3.3), ["* b"]).splitlines()
        step = corner_run.cold_start_step(exp)
        self.assertIn(f"tran {step['analysis']['args']}", deck)
        for m in step["measurements"]:
            if "spice" in m:
                self.assertIn(m["spice"][1:], deck)
            else:
                self.assertIn(f"let meas_{m['name']} = {m['expr']}", deck)

    def test_captured_request_fixture_is_what_the_builder_emits(self):
        # The request whose real klt response is the tt27-3v30 fixture.
        captured = json.loads((FIXTURES / "tt27-3v30.request.json").read_text())
        exp = corner_run.load_experiment(SIM_DIR / SLUG)
        self.assertEqual(captured["analysis_steps"], [corner_run.cold_start_step(exp)])


class TestDropoutGrading(DropoutHarness):
    def test_exact_0_300_fails_the_strict_bound(self):
        rc, out, _ = self.quick(value_of=lambda p, t, v: 0.3 if p == "tt" else 0.25)
        self.assertEqual(rc, 2)
        self.assertIn("tt_27c_3.30v         FAIL  dropout_v=0.3", out)
        self.assertIn("overall  : FAIL", out)
        exp = corner_run.load_experiment(self.exp_dir)
        m = next(x for x in exp.measurements if x.name == "dropout_v")
        self.assertEqual(corner_run.grade_bounds(m, 0.3), (False, "not below strict max 0.3"))
        self.assertTrue(corner_run.grade_bounds(m, math.nextafter(0.3, 0))[0])
        self.assertFalse(corner_run.grade_bounds(m, math.nextafter(0.3, 1))[0])

    def test_below_bound_passes(self):
        rc, out, _ = self.quick(value_of=lambda p, t, v: 0.2999)
        self.assertEqual(rc, 0, out)
        self.assertIn("overall  : PASS", out)

    def test_no_crossing_is_a_recorded_fail(self):
        rc, out, err = self.quick(value_of=lambda p, t, v: None if p == "ss" else 0.25)
        self.assertEqual(rc, 2)
        self.assertIn("ss_-40c_2.97v        FAIL  dropout_v=n/a", out)
        self.assertIn("klt diagnostic measurement", err)
        self.assertIn("'error' (not a completed result)", err)

    def test_solver_diagnostic_fails_a_passing_value(self):
        for marker in corner_run.SOLVER_DIAGNOSTIC_MARKERS:
            rc, out, err = self.quick(log_text=f"tran\n{marker} here\n")
            self.assertEqual(rc, 2, marker)
            self.assertIn("solver diagnostic", err)

    def test_step_failed_diagnostic_cannot_pass(self):
        def m(resp, req):
            resp["corners"][0]["diagnostics"] = [{"severity": "warning", "code": "step_failed",
                                                  "message": "step 'dropout' produced no plot"}]
        rc, _, err = self.quick(mutate=m)
        self.assertEqual(rc, 2)
        self.assertIn("step_failed", err)

    def test_missing_log_cannot_pass(self):
        def m(resp, req):
            resp["corners"][0]["artifacts"] = {}
        rc, _, err = self.quick(mutate=m)
        self.assertEqual(rc, 2)
        self.assertIn("engine log", err)

    def test_missing_or_duplicate_result_value_cannot_pass(self):
        for edit in (lambda c: c["measurements"].pop(2),
                     lambda c: c["measurements"].append(dict(c["measurements"][2])),
                     lambda c: c["measurements"][2].update(value=float("nan"))):
            def m(resp, req, edit=edit):
                edit(resp["corners"][0])
            rc, out, _ = self.quick(mutate=m)
            self.assertEqual(rc, 2)


class TestDropoutStructuralFailures(DropoutHarness):
    def abort(self, **fake_kw):
        self.fake = FakeDropoutKlt(self, self.pin, **fake_kw)
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("no evidence record written", str(err))
        self.assertFalse((self.exp_dir / "records").exists())
        self.assertEqual(len(self.klt_calls()), 1)  # first request only: no retry, no fallback
        return str(err)

    def test_missing_and_duplicate_corner_abort(self):
        self.assertIn("missing corner", self.abort(mutate=lambda r, q: r["corners"].clear()))
        self.assertIn("duplicate corner",
                      self.abort(mutate=lambda r, q: r["corners"].append(dict(r["corners"][0]))))
        self.assertIn("unexpected corner",
                      self.abort(mutate=lambda r, q: r["corners"][0].update(process="ss")))

    def test_remote_error_envelope_aborts(self):
        env = {"schema_version": 1, "error": {"command": "sim", "message": "batch backend failed"}}
        self.assertIn("error envelope", self.abort(stdout=json.dumps(env), rc=1))
        self.assertIn("klt sim produced no stdout", self.abort(stdout="", rc=1))

    def test_incomplete_or_incompatible_remote_job_aborts(self):
        cases = {
            "running": lambda r: r["environment"]["remote"].update(state="running", exit_code=""),
            "interrupted": lambda r: r["environment"]["remote"].update(state="interrupted"),
            "failed rc1": lambda r: r["environment"]["remote"].update(state="failed", exit_code="1"),
            "mismatch": lambda r: r["environment"]["remote"].update(runner_compatibility="mismatch"),
            "unknown runner": lambda r: r["environment"]["remote"].update(runner_compatibility="unknown"),
            "unreported runner": lambda r: r["environment"]["remote"].pop("runner_compatibility"),
            "no job id": lambda r: r["environment"]["remote"].pop("job_id"),
            "no remote": lambda r: r["environment"].pop("remote"),
        }
        for name, edit in cases.items():
            msg = self.abort(mutate=lambda r, q, edit=edit: edit(r))
            self.assertRegex(msg, r"not a completed run|not 'match'|no job id|no environment.remote", name)

    def test_failed_job_that_still_ran_is_graded(self):
        # klt: a batch job marked failed whose klt exit is 3 (measurement fail) still reported
        rc, out, _ = self.quick(mutate=lambda r, q: r["environment"]["remote"].update(state="failed", exit_code="3"))
        self.assertEqual(rc, 0, out)


class TestDropoutShapeGate(DropoutHarness):
    def refused(self, edit, expect="validated cold-start crossing shape"):
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

    def test_structural_edits_are_refused_before_netlisting(self):
        def set_line(i, text):
            def e(raw):
                raw["deck"]["analyses"][self.code_lines(raw)[i]] = text
            return e
        edits = [
            set_line(0, "tran 10u 14m"),                       # no cold start
            set_line(0, "tran 10u 14m 0 1u uic"),               # tstart/tmax
            set_line(1, "meas tran dropout_vin_x find v(vin) when v(vout)=1.764 fall=1"),  # no td
            set_line(1, "meas tran dropout_vin_x find v(vin) at=7m"),
            lambda r: r["deck"]["analyses"].insert(self.code_lines(r)[0], "op"),
            lambda r: r["deck"]["analyses"].append("ic v(vout)=0"),
            lambda r: r["deck"]["analyses"].append("let x = 1"),
            lambda r: r["measurements"][0].update(expr="v(vout) - 1.764"),
            lambda r: r["measurements"][0].update(expr="dropout_vin_x - unknown"),
            lambda r: r["measurements"][1].update(expr="vout_at_max_vin_v * 2"),
            lambda r: r.update(spread_checks=[{"measurement": "dropout_v", "min_spread": 0.001}]),
        ]
        for edit in edits:
            self.refused(edit)

    def test_any_execution_manifest_change_needs_renewed_validation(self):
        edits = {
            "bound": lambda r: r["measurements"][0].update(max=0.31),
            "inclusivity": lambda r: r["measurements"][0].update(max_inclusive=True),
            "threshold": lambda r: r["deck"]["analyses"].__setitem__(
                self.code_lines(r)[1], "meas tran dropout_vin_x find v(vin) when v(vout)=1.700 fall=1 td=6m"),
            "time grid": lambda r: r["deck"]["analyses"].__setitem__(self.code_lines(r)[0], "tran 5u 14m uic"),
            "option": lambda r: r["deck"]["options"].append("reltol=1e-4"),
            "matrix": lambda r: r["corners"]["temperature_c"].append(150),
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
        # Renewal tripwire: editing the manifest's execution sections fails
        # this test until the adapter is re-validated and the pins updated.
        want = corner_run.BATCH_ALLOWLIST[SLUG]["manifest_sections"]
        self.assertEqual(pvt_input_sections(manifest(), None), want)


class TestDropoutNetlistGate(DropoutHarness):
    def refused_netlist(self, netlist):
        self.NETLIST = netlist
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("netlist is not the validated cold-start shape", str(err))
        self.assertEqual(self.fake.calls, [])
        return str(err)

    def test_changed_stimulus_is_refused_before_submission(self):
        self.refused_netlist(DT_NETLIST.replace("'vsup-2.13'", "'vsup-2.0'"))
        self.refused_netlist(DT_NETLIST.replace("100u 1u 1u 100 200", "200u 1u 1u 100 200"))
        self.refused_netlist(DT_NETLIST.replace(STIMULUS[2] + "\n", ""))
        self.refused_netlist(DT_NETLIST.replace(STIMULUS[2], STIMULUS[2] + "\nILOAD VOUT 0 10m"))

    def test_initial_condition_and_control_cards_are_refused(self):
        for card in (".ic v(vout)=1.8", ".nodeset v(vout)=1.8", ".control", ".tran 1u 1m",
                     ".meas tran x avg v(vout)", ".temp 50"):
            msg = self.refused_netlist(DT_NETLIST.replace(".end\n", card + "\n.end\n"))
            self.assertIn(card.split()[0], msg)


class TestDropoutRecord(DropoutHarness):
    def test_record_keeps_provenance_fingerprint_subset_and_append_only(self):
        rc, out, _ = self.run_main("--backend", "batch", *QUICK)
        self.assertEqual(rc, 0, out)
        (rec_path,) = self.records()
        rec = json.loads(rec_path.read_text())
        self.assertEqual(rec["backend"], "batch")
        self.assertEqual(rec["matrix"]["subset_reason"], "test")
        self.assertTrue(rec["matrix"]["is_subset"])
        self.assertEqual([r["corner_id"] for r in rec["corners"]], rec["matrix"]["point_ids"])
        self.assertEqual(rec["input_fingerprint"]["sections"]["analyses"],
                         corner_run.BATCH_ALLOWLIST[SLUG]["manifest_sections"]["analyses"])
        ad = rec["execution"]["adapter"]
        self.assertEqual((ad["name"], ad["analysis"]), ("cold-start-crossing", "tran 10u 14m uic"))
        self.assertEqual(ad["validated_stimulus"], STIMULUS)
        dv = rec["corners"][0]["measurements"][0]
        self.assertEqual((dv["name"], dv["max"], dv["max_inclusive"]), ("dropout_v", 0.3, False))
        self.assertTrue(all(r["job_id"] == "klt-sim-00dd01" for r in rec["execution"]["requests"]))
        md = rec_path.with_suffix(".md").read_text()
        self.assertIn("Batch adapter", md)
        self.assertIn("Subset of the full PVT matrix", md)
        for sub in ("klt-requests", "klt-responses", "klt-request-netlists"):
            self.assertEqual(len(list((self.exp_dir / sub).iterdir())), 3)
        self.assertEqual(len(list((self.exp_dir / "corners" / rec["record_id"]).iterdir())), 3)


class TestCapturedKltResponses(unittest.TestCase):
    """Grade REAL klt 0.7.0 responses (local backend) with the batch grader."""

    def setUp(self):
        self.exp = corner_run.load_experiment(SIM_DIR / SLUG)
        self.group = corner_run.group_batch_requests([corner_run.Corner("tt", 27.0, 3.3)], False)[0]

    def load(self, stem):
        r = json.loads((FIXTURES / f"{stem}.response.json").read_text())
        # local-backend capture: stand in the finished-batch-job block the
        # fleet adds (the grader requires one); nothing else is altered
        r["environment"]["remote"] = {"provider": "aws-batch-fleet", "job_id": "klt-sim-fixture",
                                      "state": "done", "exit_code": "0", "runner_compatibility": "match"}
        return r

    def test_real_baseline_response_reproduces_the_local_harness(self):
        res, logs = corner_run.normalize_batch_response(self.exp, self.group, self.load("tt27-3v30"),
                                                        FIXTURES, 300)
        vals = {m["name"]: m["value"] for m in res[0]["measurements"]}
        # local harness, same corner/netlist: dropout_v=0.397658, vout=1.79883 (record 20261011-092557-7a4e0cc)
        self.assertEqual(vals, {"dropout_v": 0.397658, "vout_at_max_vin_v": 1.798832})
        self.assertIsNone(res[0]["solver_diagnostic"])
        self.assertEqual(res[0]["batch_reasons"], [])
        self.assertFalse(res[0]["pass"])  # 0.397658 V is above the < 300 mV row
        self.assertIn("skipped by 'uic'", logs["tt_27c_3.30v"])

    def test_real_no_crossing_response_cannot_pass(self):
        r = self.load("no-crossing")
        # the PDK-free RC capture has no process axis (klt reports process
        # null); name the requested corner so the point matches the request
        r["corners"][0]["process"] = "tt"
        res, _ = corner_run.normalize_batch_response(self.exp, self.group, r, FIXTURES, 300)
        (corner,) = res
        self.assertFalse(corner["pass"])
        dv = corner["measurements"][0]
        self.assertIsNone(dv["value"])
        self.assertFalse(dv["pass"])
        self.assertTrue(any("produced no value" in x for x in corner["batch_reasons"]))

    def test_unfinished_job_in_real_response_aborts(self):
        r = self.load("tt27-3v30")
        r["environment"]["remote"]["state"] = "running"
        with self.assertRaises(corner_run.HarnessError):
            corner_run.normalize_batch_response(self.exp, self.group, r, FIXTURES, 300)


class TestTranslatorUnit(unittest.TestCase):
    def test_parse_and_refusals(self):
        ok = ["* c", "tran 1u 2m uic", "meas tran a find v(x) when v(y)=1 rise=2 td=1m",
              "meas tran b avg v(y) from=1m to=2m"]
        d = bd.parse_deck(ok)
        self.assertEqual((d.tran_args, d.crossing), ("1u 2m uic", ["a"]))
        bad = [
            [],
            ["meas tran a find v(x) when v(y)=1 fall=1 td=1m"],
            ["tran 1u 2m uic", "meas tran b avg v(y) from=1m to=2m"],  # no crossing
            ["tran 1u 2m uic", "meas tran a find v(x) when v(y)=1 fall=1 td=1m",
             "meas tran a avg v(y) from=1m to=2m"],  # duplicate name
            ["tran 1u 2m uic", "meas tran a find v(x) when v(y)=1 fall=1 td=1m", "print v(x)"],
            ["tran 1u 2m uic", "meas ac a find v(x) when v(y)=1 fall=1 td=1m"],
        ]
        for lines in bad:
            with self.assertRaises(bd.DropoutTranslationError, msg=lines):
                bd.parse_deck(lines)

    def test_expressions_reference_only_cards(self):
        d = bd.parse_deck(["tran 1u 2m uic", "meas tran a find v(x) when v(y)=1 fall=1 td=1m"])
        step = bd.dropout_step(d, [("m", "(a - 1.764e0)*2", "V"), ("a", "a", "V")])
        self.assertEqual(step["measurements"][-1]["expr"], "(a - 1.764e0)*2")
        self.assertEqual(step["measurements"][0]["unit"], "V")
        for expr in ("a - v(y)", "abs(a)", "a; quit", "", "1.0"):
            with self.assertRaises(bd.DropoutTranslationError, msg=expr):
                bd.dropout_step(d, [("m", expr, "V")])
        with self.assertRaises(bd.DropoutTranslationError):
            bd.dropout_step(d, [("a", "a*2", "V")])
        self.assertEqual(bd.klt_result_name("m"), "dropout.m")

    def test_remote_completion(self):
        def resp(**remote):
            return {"environment": {"remote": {"runner_compatibility": "match", **remote}}}
        self.assertIsNone(bd.remote_completion_problem(resp(job_id="j", state="done", exit_code="0")))
        self.assertIsNone(bd.remote_completion_problem(resp(job_id="j", state="failed", exit_code="4")))
        for r in (resp(job_id="j", state="failed", exit_code="2"), resp(job_id="j", state="running"),
                  resp(state="done"), {"environment": {}}, {},
                  resp(job_id="j", state="done", runner_compatibility="mismatch"),
                  resp(job_id="j", state="done", runner_compatibility="unknown"),
                  resp(job_id="j", state="done", runner_compatibility=None)):
            self.assertIsNotNone(bd.remote_completion_problem(r), r)


if __name__ == "__main__":
    unittest.main()
