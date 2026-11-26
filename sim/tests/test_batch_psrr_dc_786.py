"""Issue #786: the psrr-dc chained-steps adapter on the opt-in `klt sim` batch backend.

PDK-free and headless: klt, xschem, git and the PDK are mocked by
test_corner_run.BatchHarness, so nothing is submitted and no ngspice runs.
The fake answers each four-step request the way klt's `analysis_steps[]`
runner is assumed to (step `expr` measurements reported as `<step>.<name>`,
the request's top-level `meas_<name>` rows evaluated over them). The step
`expr` form (`-vdb(vout)[0]` over an `ac` step) is inferred from the
loop-gain (#754) precedent: OFFLINE translation/grading checks only, not
evidence of remote execution or of local/fleet equivalence.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from test_corner_run import QUICK, SIM_DIR, BatchHarness, FakeKlt, HarnessErr, corner_run
from _endpoint_adapter_contract import BackendContract, EndpointShapeGate, RecordProvenance, manifest

sys.path.insert(0, str(SIM_DIR / "bin"))
import batch_line_regulation as blr  # noqa: E402
import batch_psrr_dc as bpd  # noqa: E402

SLUG = "psrr-dc"
STIMULUS = corner_run.BATCH_ALLOWLIST[SLUG]["stimulus"]

PSRR_NETLIST = (
    "** sch_path: x\n"
    + "\n".join(
        [STIMULUS[0], ".save i(vvin)", STIMULUS[1], STIMULUS[2],
         "xldo VOUT VREF EN VIN ldo_3v3in_1v8out", *STIMULUS[3:], "CDIR VOUT 0 0",
         bpd.NODESET_CARD,
         ".subckt ldo_3v3in_1v8out VOUT VREF EN VIN", "R1 VIN VOUT 1", ".ends"]
    )
    + "\n.end\n"
)

# the six distinct readings, keyed by the step result the fake reports
SEED1, P1K_1MA, P100K_1MA = "op1.vout_seed_1ma_v", "ac1.psrr_1khz_1ma_db", "ac1.psrr_100khz_1ma_db"
SEED2, P1K_50MA, P100K_50MA = "op2.vout_seed_50ma_v", "ac2.psrr_1khz_50ma_db", "ac2.psrr_100khz_50ma_db"


def healthy_values(p: str, t: float, vsup: float) -> dict[str, float]:
    return {SEED1: 1.8001, P1K_1MA: 71.0, P100K_1MA: 41.0,
            SEED2: 1.7982, P1K_50MA: 62.0, P100K_50MA: 23.0}


# the two-corner subset the issue #808 regression runs: both temperatures of
# one supply group, so both points travel in ONE klt response
TWO_POINT = ("--process", "tt", "--temp", "27,125", "--supply", "3.30",
             "--subset-reason", "fixture", "--no-write")


def _corner_verdicts(out: str) -> dict[str, str]:
    """The per-corner verdict lines the CLI prints ({corner id: PASS/FAIL})."""
    verdicts: dict[str, str] = {}
    for ln in out.splitlines():
        m = re.match(r"\[\s*\d+/\s*\d+\]\s+(\S+)\s+(PASS|FAIL)", ln)
        if m:
            verdicts[m.group(1)] = m.group(2)
    return verdicts


class FakePsrrKlt(FakeKlt):
    JOB_ID = "klt-sim-786001"
    RUNTIME_S = 55.0

    def __init__(self, test, pin, values_of=None, log_text=None, **kw):
        super().__init__(test, pin, **kw)
        self.values_of = values_of or healthy_values
        self.log_text = log_text

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if cmd[0] != "/fake/klt":
            self.test.fail(f"unexpected launch: {cmd}")
        if self.raise_exc:
            raise self.raise_exc
        req = json.loads(Path(cmd[2]).read_text())
        self.test.assertNotIn("analysis", req)
        self.test.assertEqual([s["name"] for s in req["analysis_steps"]],
                              ["op1", "ac1", "op2", "ac2"])
        vsup = float(Path(req["netlist"]).read_text().splitlines()[0].split("=")[1])
        outdir = Path(cmd[cmd.index("-o") + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        corners = []
        for p in req["corners"]["process"]:
            for t in req["corners"]["temperature_c"]:
                vals = self.values_of(p, t, vsup)
                ok = vals is not None
                logp = outdir / f"{p}_{t}.log"
                logp.write_text(self.log_text or f"triangle waveform {p} {t}\n")
                refs = {f"{s['name']}.{m['name']}".lower() for s in req["analysis_steps"]
                        for m in s.get("measurements") or []}
                meas = [{"name": n, "value": v, "status": "pass" if ok else "error"}
                        for n, v in (vals or {}).items()]
                for m in req.get("measurements") or []:
                    v = blr.evaluate(m["expr"], vals or {}, refs) if ok else None
                    meas.append({"name": m["name"], "value": v,
                                 "status": "pass" if v is not None else "error"})
                corners.append({
                    "corner_id": f"{p}/novdd/{t:g}C", "process": p, "temperature_c": t,
                    "status": "pass" if ok else "error", "runtime_s": self.RUNTIME_S,
                    "diagnostics": [] if ok else [
                        {"severity": "error", "code": "measurement", "message": "no value"}],
                    "artifacts": {"log": str(logp)}, "measurements": meas,
                })
        resp = {
            "status": "pass", "corners": corners,
            "environment": {"engine": "ngspice", "engine_version": "46",
                            "remote": {"provider": "aws-batch-fleet", "job_id": self.JOB_ID,
                                       "state": "done", "exit_code": "0",
                                       "runner_compatibility": "match"}},
            "provenance": {"klt_version": "0.9.3.dev614+g32005e5ebde1",
                           "pdk": {"version": self.pin["open_pdks_commit"]}},
        }
        if self.mutate:
            self.mutate(resp, req)
        out = self.stdout if self.stdout is not None else json.dumps(resp)
        return subprocess.CompletedProcess(cmd, self.rc, stdout=out, stderr="")


class PsrrHarness(BatchHarness):
    SLUG = SLUG
    NETLIST = PSRR_NETLIST
    REFUSAL_TEXT = "no longer has the validated chained-steps shape"

    def make_fake(self, **kw):
        return FakePsrrKlt(self, self.pin, **kw)

    def requests(self):
        return [json.loads(Path(c[0][2]).read_text()) for c in self.klt_calls()]

    def write_manifest(self, raw):
        (self.exp_dir / "experiment.json").write_text(json.dumps(raw))

    def quick(self, **fake_kw):
        self.fake = self.make_fake(**fake_kw)
        return self.run_main("--backend", "batch", *QUICK, "--no-write")

    def graded(self, **overrides):
        def values(p, t, vsup):
            v = healthy_values(p, t, vsup)
            v.update(overrides)
            return v
        return self.quick(values_of=values)


class TestPsrrDcAdapter(EndpointShapeGate, BackendContract, RecordProvenance, PsrrHarness):
    FIRST_CARD = "psrr_1khz_1ma_db"
    DEFAULT_VALUES = staticmethod(lambda p, t, vsup=3.3: healthy_values(p, t, vsup))

    # -- the translation -----------------------------------------------------
    def test_parse_deck_translates_the_four_steps(self):
        legs = bpd.parse_deck(manifest(SLUG)["deck"]["analyses"])
        self.assertEqual([(l.step_name, l.kind, l.analysis_args) for l in legs],
                         [("op1", "op", ""), ("ac1", "ac", "lin 3 1e3 1e5"),
                          ("op2", "op", ""), ("ac2", "ac", "lin 3 1e3 1e5")])
        self.assertEqual([l.alters for l in legs], [[], [], [("rload", 36.0)], []])

    def test_request_matches_the_reference_deck(self):
        rc, _, _ = self.quick()
        self.assertEqual(rc, 0)
        req = self.requests()[0]
        steps = {s["name"]: s for s in req["analysis_steps"]}
        self.assertNotIn("analysis", req)
        self.assertNotIn("alter", steps["op1"])
        self.assertNotIn("alter", steps["ac1"])
        self.assertEqual(steps["op2"]["alter"], {"rload": 36.0})
        self.assertEqual(steps["ac1"]["analysis"], {"kind": "ac", "args": "lin 3 1e3 1e5"})
        self.assertEqual(steps["ac2"]["analysis"], {"kind": "ac", "args": "lin 3 1e3 1e5"})
        self.assertEqual(steps["op1"]["measurements"],
                         [{"name": "vout_seed_1ma_v", "expr": "v(vout)", "unit": "V"}])
        self.assertEqual(steps["op2"]["measurements"],
                         [{"name": "vout_seed_50ma_v", "expr": "v(vout)", "unit": "V"}])
        for ac, load in (("ac1", "1ma"), ("ac2", "50ma")):
            self.assertEqual(steps[ac]["measurements"], [
                {"name": f"psrr_1khz_{load}_db", "expr": "-vdb(vout)[0]", "unit": "dB"},
                {"name": f"psrr_100khz_{load}_db", "expr": "-vdb(vout)[2]", "unit": "dB"}])
        derived = {m["name"]: m["expr"] for m in req["measurements"]}
        self.assertEqual(len(derived), 6)
        self.assertEqual(derived["meas_psrr_100khz_50ma_db"], "ac2.psrr_100khz_50ma_db")
        self.assertEqual(derived["meas_vout_seed_1ma_v"], "op1.vout_seed_1ma_v")
        # the seed and the stimulus travel in the netlist, verbatim
        net = Path(req["netlist"]).read_text()
        self.assertIn(bpd.NODESET_CARD, net)
        self.assertIn("VVIN VIN 0 DC 'vsup' AC 1", net)

    def test_full_matrix_is_three_supply_groups_covering_45_corners(self):
        self.fake = self.make_fake()
        rc, _, _ = self.run_main("--backend", "batch", "--no-write")
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 3)
        self.assertEqual(sum(len(r["corners"]["process"]) * len(r["corners"]["temperature_c"])
                             for r in reqs), 45)
        for req in reqs:
            self.assertEqual(len(req["analysis_steps"]), 4)
            self.assertEqual(len(req["measurements"]), 6)

    # -- grading ----------------------------------------------------------------
    def test_healthy_values_pass_and_report_distinct_readings(self):
        rec_path, rec = self.run_and_load_record()
        for c in rec["corners"]:
            vals = {m["name"]: m["value"] for m in c["measurements"]}
            self.assertEqual(vals["psrr_1khz_1ma_db"], 71.0)
            self.assertEqual(vals["psrr_100khz_1ma_db"], 41.0)
            self.assertEqual(vals["psrr_1khz_50ma_db"], 62.0)
            self.assertEqual(vals["psrr_100khz_50ma_db"], 23.0)
            self.assertEqual(vals["vout_seed_1ma_v"], 1.8001)
            self.assertEqual(vals["vout_seed_50ma_v"], 1.7982)
            self.assertTrue(c["pass"])

    def test_strict_bounds_per_load_and_frequency(self):
        for key, bound in ((P1K_1MA, 50.0), (P1K_50MA, 50.0), (P100K_1MA, 20.0), (P100K_50MA, 20.0)):
            rc, out, _ = self.graded(**{key: bound})
            self.assertEqual(rc, 2, key)  # exactly at the bound fails (strict)
            self.assertIn("FAIL", out)
            rc, _, _ = self.graded(**{key: bound + 0.001})
            self.assertEqual(rc, 0, key)

    def test_a_swapped_reading_is_detected(self):
        # 100 kHz reading below its 20 dB bound while 1 kHz is huge: only the
        # right (load, frequency) pairing fails
        rc, _, _ = self.graded(**{P100K_50MA: 19.0, P1K_50MA: 90.0})
        self.assertEqual(rc, 2)

    def test_seed_voltages_are_reported_without_a_bound(self):
        rc, _, _ = self.graded(**{SEED1: 0.0, SEED2: 3.6})
        self.assertEqual(rc, 0)

    def test_missing_or_nonfinite_reading_at_either_load_cannot_pass(self):
        for key in (P1K_1MA, P100K_1MA, SEED1, P1K_50MA, P100K_50MA, SEED2):
            def missing(p, t, vsup, key=key):
                v = healthy_values(p, t, vsup)
                v.pop(key)
                return v
            rc, out, _ = self.quick(values_of=missing)
            self.assertEqual(rc, 2, key)
            self.assertIn("FAIL", out)
            for bad in (float("nan"), float("inf")):
                rc, _, _ = self.graded(**{key: bad})
                self.assertEqual(rc, 2, (key, bad))

    # -- issue #808: a corner's diagnostics follow its validated pairing ------
    def test_a_corner_error_fails_only_that_corner_without_worker_ids(self):
        # The chained grader indexed the response by the worker's optional
        # `corner_id`: with two corners sharing an id (or both omitting it)
        # every corner graded against whichever raw entry came last, so a real
        # corner error was lost. The validated process/temperature pairing
        # (sim/bin/_batch_backend.py, `_index_response_corners`) keeps each
        # corner's diagnostics with its own measurements, whatever the worker
        # ids say and in either response order.
        def err_27c(resp, req):
            for c in resp["corners"]:
                if c["temperature_c"] == 27:
                    c["diagnostics"] = [
                        {"severity": "error", "code": "measurement", "message": "injected error"}]

        def strip_ids(resp, req):
            for c in resp["corners"]:
                c.pop("corner_id", None)

        def repeat_id(resp, req):
            for c in resp["corners"]:
                c["corner_id"] = "tt/novdd/shared"

        def two_point(mutate=None):
            self.fake = self.make_fake(mutate=mutate)
            return self.run_main("--backend", "batch", *TWO_POINT)

        rc, out, _ = two_point()  # healthy control: distinct ids, no error
        self.assertEqual(rc, 0, out)
        self.assertEqual(_corner_verdicts(out),
                         {"tt_27c_3.30v": "PASS", "tt_125c_3.30v": "PASS"})
        for mangle in (lambda r, q: None, strip_ids, repeat_id):
            for order in ("as-built", "reversed"):
                def mutate(resp, req, mangle=mangle, order=order):
                    mangle(resp, req)
                    err_27c(resp, req)
                    if order == "reversed":
                        resp["corners"].reverse()
                rc, out, err = two_point(mutate)
                self.assertEqual(rc, 2, (mangle, order, out))
                self.assertEqual(_corner_verdicts(out),
                                 {"tt_27c_3.30v": "FAIL", "tt_125c_3.30v": "PASS"},
                                 (mangle, order))
                self.assertIn("klt diagnostic", err)

    # -- refusals -----------------------------------------------------------------
    def test_deck_shape_refusals(self):
        for edit in (
            lambda a: [x.replace("ac lin 3 1e3 1e5", "ac lin 2 1e3 1e5") for x in a],
            lambda a: [x.replace("alter rload = 36", "alter rload = 40") for x in a],
            lambda a: [x.replace("-vdb(vout)[2]", "-vdb(vout)[1]") for x in a],
            lambda a: [x for x in a if x != "alter rload = 36"],
            lambda a: a + ["op"],
            lambda a: [x for x in a if not x.startswith("let vseed")],
        ):
            raw = json.loads(json.dumps(manifest(SLUG)))
            raw["deck"]["analyses"] = edit(raw["deck"]["analyses"])
            with self.assertRaises(bpd.PsrrDcTranslationError):
                bpd.parse_deck(raw["deck"]["analyses"])

    def test_untranslatable_measurement_expression_is_refused(self):
        legs = bpd.parse_deck(manifest(SLUG)["deck"]["analyses"])
        for expr in ("ac1.p1k+ac2.p1k", "ac3.p1k", "ac1.nope", "op1.p1k"):
            with self.assertRaises(bpd.PsrrDcTranslationError):
                bpd.check_measurements(legs, [("m", expr, "dB")])

    def test_changed_manifest_sections_refused_before_submission(self):
        self.refused(lambda raw: raw["deck"]["analyses"].__setitem__(
            self.find(raw, "ac lin"), "ac lin 3 1e3 2e5"))
        self.refused(lambda raw: raw["deck"]["analyses"].__setitem__(
            self.find(raw, "alter rload"), "alter rload = 40"))
        self.refused(lambda raw: raw["measurements"][0].update(min=40))
        self.refused(lambda raw: raw["measurements"][0].update(expr="ac2.p1k"))

    def test_stimulus_and_seed_changes_refused_before_submission(self):
        for old, new in (("VVIN VIN 0 DC 'vsup' AC 1", "VVIN VIN 0 DC 'vsup' AC 2"),
                         ("VEN EN 0 'vsup'", "VEN EN 0 'vsup' AC 1"),
                         ("VVREF VREF 0 1.2", "VVREF VREF 0 1.1"),
                         ("COUT VOUT VESR 1u m=1", "COUT VOUT VESR 2u m=1"),
                         ("RESR VESR 0 10m m=1", "RESR VESR 0 20m m=1"),
                         ("RLOAD VOUT 0 1.8k m=1", "RLOAD VOUT 0 1k m=1"),
                         (bpd.NODESET_CARD, ".nodeset v(VOUT)=1.8 v(xldo.FB)=1.2"),
                         (bpd.NODESET_CARD, "")):
            self.NETLIST = PSRR_NETLIST.replace(old, new)
            err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
            self.assertIn("not the validated chained-steps baseline", str(err), old)
            self.assertEqual(self.klt_calls(), [])

    def test_still_excluded_benches_stay_refused(self):
        self.assertNotIn("thermal", corner_run.BATCH_ALLOWLIST)

    # -- provenance ------------------------------------------------------------
    def test_record_carries_batch_provenance_and_every_result(self):
        rec_path, rec = self.run_and_load_record()
        ex = rec["execution"]
        self.assertEqual(len(ex["requests"]), 3)
        for r in ex["requests"]:
            self.assertEqual(r["reported_backend"], "aws-batch-fleet")
            self.assertTrue(r["job_id"])
            self.assertTrue(r["klt_pdk_names_pin"])
        for c in rec["corners"]:
            self.assertEqual(len(c["measurements"]), 6)
            self.assertTrue(all(m["value"] is not None for m in c["measurements"]))


if __name__ == "__main__":
    unittest.main()
