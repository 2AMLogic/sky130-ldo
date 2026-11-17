"""Issue #336: the startup ramp-trace grid on the batch backend.

Headless: `klt sim` is faked (nothing submitted). Covers the shape gate, the
scalar per-leg request + leg netlist, the returned-waveform trace grading
(including a missing artifact, a wrong-shaped artifact, a strict-0 V
monotonicity failure and an unreached tset), the runner-compatibility abort,
cross-leg merging and the staged trace files in the record.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_corner_run import SIM_DIR, BatchHarness, FakeKlt, HarnessErr

from _sim_script_loader import load_script

import _batch_backend  # noqa: E402  (imported before corner-run.py, so both share one module)
import batch_startup_ramp  # noqa: E402

corner_run = load_script("corner_run_batch_startup", SIM_DIR / "bin" / "corner-run.py", register=True)

SUBSET = ["--process", "tt", "--temp", "27", "--supply", "3.3", "--subset-reason", "test"]

STARTUP_NETLIST = (
    "** sch_path: x\nVVIN VIN 0 'vsup'\nVEN EN 0 PULSE(0 'vsup' 100u 1u 1u 100 200)\n"
    "VVREF VREF 0 1.2\nxldo VOUT VREF EN VIN ldo_3v3in_1v8out\n"
    "COUT VOUT VESR 4.7u m=1\nRESR VESR 0 10m m=1\nCDIR VOUT 0 0 m=1\n"
    "RLOAD VOUT 0 36 m=1\n.end\n"
)


def ramp_waveform(t_enable=1e-4, t_end=4e-3, v_target=1.80, dip_v=0.0, dip_at=1.2e-4):
    """A strictly monotonic cold-start trace reaching the window at ~430 us.
    `dip_v` forces one sample strictly BELOW its predecessor (a real drawdown
    of ~dip_v against the running maximum), the way the pilot's sub-mV dips
    appear."""
    n = 440
    variables = [{"name": "time", "type": "time", "dimension": 0},
                 {"name": "v(vout)", "type": "voltage", "dimension": 0}]
    points = []
    for i in range(n):
        t = t_end * i / (n - 1)
        frac = min(1.0, max(0.0, (t - t_enable) / 3.3e-4))
        points.append([t, v_target * (frac ** 2)])
    if dip_v:
        idx = next(i for i, p in enumerate(points) if p[0] >= dip_at)
        points[idx][1] = points[idx - 1][1] - dip_v
    return {"plotname": "Transient Analysis", "variables": variables, "points": points}


class FakeScalarKlt(FakeKlt):
    """Answers a scalar-`tran` startup leg request: measurements by plain card
    name, plus a waveform JSON artifact per corner."""

    def __init__(self, test, pin, vpk=1.812, vfloor=1.807, tset=4.274e-4,
                 waveform=None, drop_waveform=False, **kw):
        super().__init__(test, pin, **kw)
        self.vpk, self.vfloor, self.tset = vpk, vfloor, tset
        self.waveform = waveform if waveform is not None else ramp_waveform()
        self.drop_waveform = drop_waveform

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if cmd[0] != "/fake/klt":
            self.test.fail(f"unexpected launch: {cmd}")
        req = json.loads(Path(cmd[2]).read_text())
        self.test.assertIn("analysis", req)
        self.test.assertNotIn("analysis_steps", req)
        self.test.assertEqual(req["analysis"]["kind"], "tran")
        outdir = Path(cmd[cmd.index("-o") + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        values = {"vpk": self.vpk, "vfloor": self.vfloor, "tset": self.tset}
        corners = []
        for p in req["corners"]["process"]:
            for t in req["corners"]["temperature_c"]:
                logp = outdir / f"{p}_{t}.log"
                logp.write_text(f"ngspice log {p} {t}\n")
                art = {"log": str(logp)}
                if not self.drop_waveform:
                    wpath = outdir / f"{p}_{t}.waveform.json"
                    wpath.write_text(json.dumps(self.waveform))
                    art["waveform"] = str(wpath)
                corners.append({
                    "corner_id": f"{p}/{t:g}C", "process": p, "temperature_c": t,
                    "status": "pass", "runtime_s": 2.0, "diagnostics": [],
                    "artifacts": art,
                    "measurements": [
                        {"name": n, "status": "pass", "value": v} for n, v in values.items()
                    ],
                })
        resp = {
            "status": "pass", "corners": corners,
            "environment": {"engine": "ngspice", "engine_version": "42",
                            "remote": {"provider": "aws-batch-fleet", "job_id": "klt-sim-0 startup"
                                       .replace(" ", ""),
                                       "state": "done", "exit_code": "0",
                                       "runner_compatibility": "match"}},
            "provenance": {"klt_version": "0.9.0", "pdk": {"version": self.pin["open_pdks_commit"]}},
        }
        if self.mutate:
            self.mutate(resp, req)
        return subprocess.CompletedProcess(cmd, self.rc, stdout=json.dumps(resp), stderr="")


class StartupBatchHarness(BatchHarness):
    SLUG = "startup"
    NETLIST = STARTUP_NETLIST

    def make_fake(self, **kw):
        return FakeScalarKlt(self, self.pin, **kw)

    def requests(self):
        return [json.loads(Path(c[0][2]).read_text()) for c in self.klt_calls()]

    def run_batch_subset(self, *extra, expect_exit=None):
        return self.run_main("--backend", "batch", *SUBSET, *extra, expect_exit=expect_exit)


class TestStartupShapeGate(unittest.TestCase):
    """The manifest shape a trace-returning batch run relies on (no fleet)."""

    @classmethod
    def setUpClass(cls):
        cls.exp = corner_run.load_experiment(SIM_DIR / "startup")
        sys.path.insert(0, str(SIM_DIR / "bin"))

    def gate(self, raw):
        exp = corner_run.Experiment(SIM_DIR / "startup", raw)
        exp.measurements = corner_run.expand_measurements(raw)
        try:
            corner_run.check_batch_supported(exp)
            return None
        except corner_run.HarnessError as exc:
            return str(exc)

    def test_committed_manifest_is_admitted(self):
        self.assertIsNone(self.gate(self.exp.raw))

    def test_no_ramp_block_refuses(self):
        raw = json.loads(json.dumps(self.exp.raw))
        del raw["ramp_monotonicity"]
        self.assertIn("declares no ramp_monotonicity", self.gate(raw) or "")

    def test_missing_wrdata_refuses(self):
        raw = json.loads(json.dumps(self.exp.raw))
        raw["window_grid"]["leg_analyses"] = [
            ln for ln in raw["window_grid"]["leg_analyses"] if not ln.startswith("wrdata")
        ]
        err = self.gate(raw)
        self.assertIn("declares no wrdata trace", err or "")

    def test_wrdata_signal_mismatch_refuses(self):
        raw = json.loads(json.dumps(self.exp.raw))
        raw["window_grid"]["leg_analyses"] = [
            ln.replace("v(vout)", "v(out2)") if ln.startswith("wrdata") else ln
            for ln in raw["window_grid"]["leg_analyses"]
        ]
        self.assertIn("is not the leg's wrdata signal", self.gate(raw) or "")

    def test_ramp_leg_mismatch_refuses(self):
        raw = json.loads(json.dumps(self.exp.raw))
        raw["ramp_monotonicity"]["legs"] = raw["ramp_monotonicity"]["legs"][:6]
        self.assertIn("not exactly the declared window_grid legs", self.gate(raw) or "")

    def test_missing_setting_refuses(self):
        raw = json.loads(json.dumps(self.exp.raw))
        del raw["ramp_monotonicity"]["tolerance_v"]
        self.assertIn("missing 'tolerance_v'", self.gate(raw) or "")

    def test_let_helper_refuses(self):
        raw = json.loads(json.dumps(self.exp.raw))
        raw["window_grid"]["leg_analyses"].append("let x = vpk")
        self.assertIn("declares let helpers", self.gate(raw) or "")

    def test_other_window_grid_slugs_stay_refused(self):
        # load-transient stays a step-grid experiment; a startup slug without
        # the ramp block must not be admitted either.
        raw = json.loads((SIM_DIR / "load-transient" / "experiment.json").read_text())
        raw["slug"] = "startup"
        exp = corner_run.Experiment(SIM_DIR / "startup", raw)
        exp.measurements = corner_run.expand_measurements(raw)
        with self.assertRaises(corner_run.HarnessError) as cm:
            corner_run.check_batch_supported(exp)
        self.assertIn("ramp_monotonicity", str(cm.exception))

    def test_ramp_block_under_a_foreign_slug_stays_refused(self):
        raw = json.loads(json.dumps(self.exp.raw))
        raw["slug"] = "load-transient"
        exp = corner_run.Experiment(SIM_DIR / "startup", raw)
        exp.measurements = corner_run.expand_measurements(raw)
        with self.assertRaises(corner_run.HarnessError) as cm:
            corner_run.check_batch_supported(exp)
        self.assertIn("ramp-trace", str(cm.exception))


class TestStartupLegRequests(StartupBatchHarness):
    def test_full_matrix_is_one_scalar_request_per_supply_and_leg(self):
        rc, out, _ = self.run_main("--backend", "batch", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(out.count("klt sim request v"), 3 * 12)
        self.assertIn("backend         : batch (36 klt sim request(s))", out)
        self.assertIn("batch adapter startup-ramp-traces (issue #336)", out)
        self.assertFalse((self.exp_dir / "records").exists())

    def test_request_shape_and_leg_netlist(self):
        rc, _, _ = self.run_batch_subset()
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 12)
        exp = corner_run.load_experiment(SIM_DIR / "startup")
        legs = {leg["id"]: leg for leg in corner_run.window_legs(exp.raw)}
        seen = set()
        for r in reqs:
            self.assertNotIn("analysis_steps", r)
            self.assertEqual(r["analysis"], {"kind": "tran", "args": "10u 4m"})
            cards = {m["name"]: m for m in r["measurements"]}
            self.assertEqual(
                sorted(cards),
                ["tset", "vfloor", "vpk"],
            )
            self.assertTrue(cards["vpk"]["spice"].startswith(".meas tran vpk"))
            self.assertEqual(cards["tset"].get("on_unreached"), "null")
            self.assertNotIn("on_unreached", cards["vpk"])
            self.assertTrue(r["options"]["waveforms"])
            self.assertTrue(r["options"]["keep_artifacts"])
            body = Path(r["netlist"]).read_text().splitlines()
            vsup = next(float(l.split("=")[1]) for l in body if l.startswith(".param vsup"))
            leg_id = next(k for k in legs if f"-{k}.spice" in r["netlist"])
            seen.add(leg_id)
            vals = corner_run.leg_values(exp.raw["window_grid"], legs[leg_id])
            by_elem = {}
            for ln in body:
                tok = ln.split()
                if tok and tok[0].lower() in ("cout", "resr", "cdir", "rload"):
                    by_elem[tok[0].lower()] = float(tok[3])
            self.assertEqual(by_elem["cout"], vals["cout_esr_f"], leg_id)
            self.assertEqual(by_elem["resr"], vals["resr_f"], leg_id)
            self.assertEqual(by_elem["cdir"], vals["cout_dir_f"], leg_id)
            self.assertEqual(by_elem["rload"], vals["rload_f"], leg_id)
        self.assertEqual(seen, set(legs))

    def test_esr0_leg_bakes_the_direct_branch_topology(self):
        self.run_batch_subset()
        target = next(
            Path(r["netlist"]) for r in self.requests()
            if r["netlist"].endswith("v3.30-c330n_0ma_esr0.spice")
        )
        body = target.read_text().splitlines()
        self.assertIn("COUT VOUT VESR 0.0 m=1", body)
        self.assertIn("RESR VESR 0 0.01 m=1", body)
        self.assertIn("CDIR VOUT 0 3.3e-07 m=1", body)
        self.assertIn("RLOAD VOUT 0 1000000000000.0 m=1", body)


class TestStartupTraceGrading(StartupBatchHarness):
    def record_json(self):
        recs = sorted((self.exp_dir / "records").glob("*.json"))
        self.assertEqual(len(recs), 1)
        return json.loads(recs[0].read_text()), recs[0]

    def test_all_pass_record_carries_ramp_results_and_traces(self):
        rc, out, _ = self.run_batch_subset()
        self.assertEqual(rc, 0)
        rec, rec_path = self.record_json()
        self.assertTrue(rec["overall_pass"])
        self.assertEqual(rec["backend"], "batch")
        self.assertEqual(rec["execution"]["adapter"]["name"], "startup-ramp-traces")
        corner = rec["corners"][0]
        ramp = corner["ramp_monotonicity"]
        self.assertEqual([l["leg"] for l in ramp], [l["id"] for l in rec["window_grid"]["legs"]])
        self.assertTrue(all(l["status"] == "PASS" and l["pass"] for l in ramp))
        # every leg's trace is staged in the record's corners dir, sha256 matches
        corners_dir = rec_path.parent.parent / f"corners/{rec['record_id']}"
        for leg in ramp:
            f = corners_dir / leg["trace_file"]
            self.assertTrue(f.is_file(), leg["trace_file"])
            import hashlib
            self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(), leg["trace_sha256"])
        grid = rec["window_grid"]
        self.assertTrue(grid["complete"] and grid["pass"], grid)
        self.assertEqual(grid["conditions_passing"], grid["conditions_expected"])
        self.assertEqual(grid["conditions_expected"], 12 * (3 + 1))

    def test_merged_corner_has_36_measurement_checks_plus_12_ramp(self):
        self.run_batch_subset()
        rec, _ = self.record_json()
        corner = rec["corners"][0]
        names = [c["name"] for c in corner["measurements"]]
        self.assertEqual(len(names), 36 + 12)
        self.assertEqual(len([n for n in names if n.startswith("ramp_drawdown_")]), 12)
        self.assertEqual(len(corner["ramp_monotonicity"]), 12)
        self.assertIn("vpk_v__c330n_0ma_esr0", names)
        self.assertIn("tramp_ms__c4u7_50ma_esr500m", names)
        # graded rows first (manifest order), ramp conditions trailing (leg order)
        # template-major order, matching the local path's manifest-order rows
        self.assertEqual([n for n in names if not n.startswith("ramp_drawdown_")][:3],
                         ["vpk_v__c330n_0ma_esr0", "vpk_v__c330n_0ma_esr10m",
                          "vpk_v__c330n_0ma_esr500m"])

    def test_missing_waveform_artifact_invalidates_the_leg(self):
        # through the normalizer directly, so the recorded shape is visible
        exp = corner_run.load_experiment(SIM_DIR / "startup")
        resp = {
            "status": "pass",
            "corners": [{
                "corner_id": "tt/27C", "process": "tt", "temperature_c": 27.0,
                "status": "pass", "runtime_s": 1.0, "diagnostics": [],
                "artifacts": {}, "measurements": [
                    {"name": "vpk", "value": 1.812, "status": "pass"},
                    {"name": "vfloor", "value": 1.807, "status": "pass"},
                    {"name": "tset", "value": 4.274e-4, "status": "pass"},
                ],
            }],
            "environment": {"remote": {"job_id": "j", "state": "done", "exit_code": "0",
                                       "runner_compatibility": "match"}},
        }
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(tmp, True))
        group = _batch_backend.BatchGroup("v3.30-c330n_0ma_esr0", 3.3, [
            corner_run.Corner("tt", 27.0, 3.3)], ["tt"], [27.0], "c330n_0ma_esr0")
        res, logs = _batch_backend.normalize_startup_response(exp, group, resp, tmp, 300)
        self.assertEqual(len(res), 1)
        self.assertFalse(res[0]["pass"])
        self.assertTrue(any("waveform artifact" in r for r in res[0]["batch_reasons"]))
        ramp = res[0]["ramp_monotonicity"][0]
        self.assertEqual(ramp["status"], "INVALID")
        self.assertFalse(ramp["pass"])
        check = next(c for c in res[0]["measurements"] if c["name"].startswith("ramp_drawdown_"))
        self.assertFalse(check["pass"])
        self.assertIn("INVALID", check["reason"])

    def test_waveform_without_signal_invalidates_the_leg(self):
        def strip_signal(resp, req):
            for c in resp["corners"]:
                doc = json.loads(Path(c["artifacts"]["waveform"]).read_text())
                doc["variables"] = [v for v in doc["variables"] if v["name"] != "v(vout)"]
                doc["points"] = [row[:1] for row in doc["points"]]
                Path(c["artifacts"]["waveform"]).write_text(json.dumps(doc))
        self.fake.mutate = strip_signal
        rc, out, _ = self.run_batch_subset()
        self.assertEqual(rc, 2)
        rec, _ = self.record_json()
        corner = rec["corners"][0]
        self.assertFalse(corner["pass"])
        self.assertFalse(rec["window_grid"]["pass"])
        ramp = {l["leg"]: l for l in corner["ramp_monotonicity"]}
        self.assertTrue(all(l["status"] == "INVALID" for l in ramp.values()))
        self.assertIn("does not contain v(vout)", next(iter(ramp.values()))["reasons"][0])

    def test_strict_monotonicity_failure_lowers_grid_and_corner(self):
        self.fake = FakeScalarKlt(self, self.pin, waveform=ramp_waveform(dip_v=32e-6))
        rc, out, _ = self.run_batch_subset()
        self.assertEqual(rc, 2)
        self.assertIn("overall : FAIL", out)
        rec, _ = self.record_json()
        corner = rec["corners"][0]
        ramp = {l["leg"]: l for l in corner["ramp_monotonicity"]}
        failing = [l for l in ramp.values() if l["status"] == "FAIL"]
        self.assertTrue(failing)
        self.assertGreater(max(l["max_drawdown_v"] for l in failing), 0)
        grid = rec["window_grid"]
        self.assertFalse(grid["pass"])
        self.assertGreater(grid["n_failing_or_missing"], 0)
        self.assertTrue(rec["corners"][0]["measurements"][0]["pass"])  # electrical rows still pass

    def test_monotone_waveform_passes_strict_check(self):
        self.run_batch_subset()
        rec, _ = self.record_json()
        ramp = rec["corners"][0]["ramp_monotonicity"]
        self.assertTrue(all(l["max_drawdown_v"] == 0.0 for l in ramp))

    def test_tset_unreached_is_missing_not_an_abort(self):
        self.fake = FakeScalarKlt(self, self.pin, tset=None)
        rc, out, _ = self.run_batch_subset()
        self.assertEqual(rc, 2)
        rec, _ = self.record_json()
        corner = rec["corners"][0]
        tr = next(c for c in corner["measurements"] if c["name"].startswith("tramp_ms"))
        self.assertIsNone(tr["value"])
        self.assertFalse(tr["pass"])
        self.assertIn("missing", tr["reason"])

    def test_mismatched_runner_aborts_with_no_record(self):
        def mismatch(resp, req):
            resp["environment"]["remote"]["runner_compatibility"] = "mismatch"
        self.fake = FakeScalarKlt(self, self.pin, mutate=mismatch)
        err, _, _ = self.run_batch_subset(expect_exit=HarnessErr)
        self.assertIn("no local fallback", str(err))
        self.assertFalse((self.exp_dir / "records").exists())


class TestStartupLocalPathUnchanged(unittest.TestCase):
    """The local backend still walks the legs with wrdata + reset (no drift)."""

    @classmethod
    def setUpClass(cls):
        cls.exp = corner_run.load_experiment(SIM_DIR / "startup")

    def test_deck_keeps_wrdata_and_one_reset_per_leg(self):
        deck = corner_run.build_deck(
            self.exp, mock.Mock(lib_file="/x/l"), corner_run.Corner("tt", 27, 3.3), ["* b"]
        )
        self.assertEqual(len([ln for ln in deck.splitlines() if ln.startswith("wrdata ")]), 12)
        self.assertEqual(deck.count("\nreset\n"), 12)
        self.assertIn("wrdata tt_27c_3.30v.c330n_0ma_esr0.trace.dat v(vout)", deck)


if __name__ == "__main__":
    unittest.main()
