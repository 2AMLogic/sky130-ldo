"""Issue #755: the enable-shutdown chained-steps adapter on the opt-in
`klt sim` batch backend.

PDK-free and headless: klt, xschem, git and the PDK are mocked by
test_corner_run.BatchHarness, so nothing is submitted and no ngspice runs.
The fake answers each four-step request the way klt's `analysis_steps[]`
runner is assumed to (step cards and step `expr` measurements reported as
`<step>.<name>`, the request's top-level `meas_<name>` rows evaluated over
them). The step names and the op-step `expr` form are inferred from the #177
and window-grid precedents, not run on a fleet: OFFLINE translation/grading
checks only, not evidence of remote execution or of local/fleet equivalence.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from test_corner_run import QUICK, SIM_DIR, BatchHarness, FakeKlt, HarnessErr, corner_run
from _endpoint_adapter_contract import BackendContract, EndpointShapeGate, RecordProvenance, manifest

sys.path.insert(0, str(SIM_DIR / "bin"))
import batch_enable_shutdown as bes  # noqa: E402
import batch_line_regulation as blr  # noqa: E402

SLUG = "enable-shutdown"
STIMULUS = corner_run.BATCH_ALLOWLIST[SLUG]["stimulus"]

ES_NETLIST = (
    "** sch_path: x\n"
    + "\n".join(
        [STIMULUS[0], ".save i(vvin)", STIMULUS[1], STIMULUS[2],
         "xldo VOUT VREF EN VIN ldo_3v3in_1v8out", *STIMULUS[3:],
         ".subckt ldo_3v3in_1v8out VOUT VREF EN VIN", "R1 VIN VOUT 1", ".ends"]
    )
    + "\n.end\n"
)


def healthy_values(p: str, t: float, vsup: float) -> dict[str, float]:
    """Raw step results for one corner: a block that regulated before the
    disable edge and then draws ~10 nA (raw i(vvin) is negative = delivering)."""
    return {
        "tran1.vpre": 1.8, "tran1.vhold": 1.79,
        "tran1.iq_avg": -8e-9, "tran1.iq_worst": -1e-8,
        "op1.iq_shutdown_static_ua": 0.01, "op1.vout_disabled_static_v": 1.79,
        "op2.leak_vin_vout_ua": 0.005, "op3.ivout_held_1v8_ua": 0.6,
    }


class FakeShutdownKlt(FakeKlt):
    JOB_ID = "klt-sim-0e5d07"
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
                              ["tran1", "op1", "op2", "op3"])
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


class ShutdownHarness(BatchHarness):
    SLUG = SLUG
    NETLIST = ES_NETLIST
    REFUSAL_TEXT = "no longer has the validated chained-steps shape"

    def make_fake(self, **kw):
        return FakeShutdownKlt(self, self.pin, **kw)

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


class TestEnableShutdownAdapter(
    EndpointShapeGate, BackendContract, RecordProvenance, ShutdownHarness
):
    FIRST_CARD = "vpre"
    DEFAULT_VALUES = staticmethod(lambda p, t, vsup=3.3: healthy_values(p, t, vsup))

    # -- the translation -----------------------------------------------------
    def test_parse_deck_translates_the_four_steps(self):
        legs = bes.parse_deck(manifest(SLUG)["deck"]["analyses"])
        self.assertEqual([(l.step_name, l.kind) for l in legs],
                         [("tran1", "tran"), ("op1", "op"), ("op2", "op"), ("op3", "op")])
        self.assertEqual(legs[0].analysis_args, "5u 4.5m")
        self.assertEqual([n for n, _ in legs[0].cards], ["vpre", "iq_avg", "iq_worst", "vhold"])
        self.assertEqual(legs[1].alters, [])
        self.assertEqual(legs[2].alters, [("rforce", 1e-3)])
        # op3 keeps the 1 mOhm forcing path explicitly, so it is correct whether
        # or not klt carries alters across chained steps
        self.assertEqual(legs[3].alters, [("rforce", 1e-3), ("vforce", 1.8)])

    def test_request_carries_step_exprs_and_all_eight_derived_rows(self):
        rc, _, _ = self.quick()
        self.assertEqual(rc, 0)
        req = self.requests()[0]
        steps = {s["name"]: s for s in req["analysis_steps"]}
        self.assertNotIn("alter", steps["op1"])
        self.assertEqual(steps["op2"]["alter"], {"rforce": 1e-3})
        self.assertEqual(steps["op3"]["alter"], {"rforce": 1e-3, "vforce": 1.8})
        exprs = {s: [m for m in steps[s]["measurements"] if "expr" in m] for s in steps}
        self.assertEqual(exprs["tran1"], [])
        self.assertEqual(exprs["op1"], [
            {"name": "iq_shutdown_static_ua", "expr": "-1e6*i(vvin)", "unit": "uA"},
            {"name": "vout_disabled_static_v", "expr": "v(vout)", "unit": "V"}])
        self.assertEqual(exprs["op2"], [
            {"name": "leak_vin_vout_ua", "expr": "1e6*i(vforce)", "unit": "uA"}])
        self.assertEqual(exprs["op3"], [
            {"name": "ivout_held_1v8_ua", "expr": "-1e6*i(vforce)", "unit": "uA"}])
        self.assertEqual([m["name"] for m in steps["tran1"]["measurements"]],
                         ["vpre", "iq_avg", "iq_worst", "vhold"])
        derived = {m["name"]: m["expr"] for m in req["measurements"]}
        self.assertEqual(len(derived), 8)
        self.assertEqual(derived["meas_iq_shutdown_static_ua"], "op1.iq_shutdown_static_ua")
        self.assertEqual(derived["meas_iq_shutdown_after_edge_ua"], "-1e6*tran1.iq_worst")
        self.assertEqual(derived["meas_vout_pre_disable_v"], "tran1.vpre")
        self.assertEqual(derived["meas_ivout_held_1v8_ua"], "op3.ivout_held_1v8_ua")

    def test_full_matrix_is_three_supply_groups_covering_45_corners(self):
        self.fake = self.make_fake()
        rc, _, _ = self.run_main("--backend", "batch", "--no-write")
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 3)
        self.assertEqual(sum(len(r["corners"]["process"]) * len(r["corners"]["temperature_c"])
                             for r in reqs), 45)
        self.assertEqual(len(reqs[0]["corners"]["process"]), 5)
        self.assertEqual(len(reqs[0]["corners"]["temperature_c"]), 3)
        for req in reqs:
            self.assertEqual(len(req["analysis_steps"]), 4)
            self.assertEqual(len(req["measurements"]), 8)

    # -- grading ----------------------------------------------------------------
    def test_healthy_values_pass(self):
        rc, _, _ = self.graded()
        self.assertEqual(rc, 0)

    def test_shutdown_iq_fails_at_3_ua_static_and_after_edge(self):
        rc, out, _ = self.graded(**{"op1.iq_shutdown_static_ua": 3.0})
        self.assertEqual(rc, 2)
        self.assertIn("FAIL", out)
        raw = -3.0 / 1e6
        self.assertEqual(-1e6 * raw, 3.0)  # the sign flip reaches exactly 3 uA
        rc, out, _ = self.graded(**{"tran1.iq_worst": raw})
        self.assertEqual(rc, 2)
        self.assertIn("FAIL", out)

    def test_just_below_3_ua_passes(self):
        rc, _, _ = self.graded(**{"op1.iq_shutdown_static_ua": 2.999, "tran1.iq_worst": -2.999e-6})
        self.assertEqual(rc, 0)

    def test_leakage_passes_at_1_ua_and_fails_above(self):
        rc, _, _ = self.graded(**{"op2.leak_vin_vout_ua": 1.0})
        self.assertEqual(rc, 0)
        rc, out, _ = self.graded(**{"op2.leak_vin_vout_ua": 1.001})
        self.assertEqual(rc, 2)
        self.assertIn("FAIL", out)

    def test_pre_disable_voltage_outside_window_fails_despite_good_currents(self):
        for v in (1.763, 1.837, 0.0):
            rc, out, _ = self.graded(**{"tran1.vpre": v})
            self.assertEqual(rc, 2, v)
            self.assertIn("FAIL", out)

    def test_collapsed_hold_voltage_fails(self):
        rc, _, _ = self.graded(**{"tran1.vhold": 1.5})
        self.assertEqual(rc, 2)

    def test_errored_op_step_value_cannot_pass(self):
        def broken(p, t, vsup):
            v = healthy_values(p, t, vsup)
            v.pop("op2.leak_vin_vout_ua")
            return v
        rc, out, _ = self.quick(values_of=broken)
        self.assertEqual(rc, 2)
        self.assertIn("FAIL", out)

    # -- refusals -----------------------------------------------------------------
    def test_deck_shape_refusals(self):
        for edit in (
            lambda a: [x.replace("tran 5u 4.5m", "tran 5u 4.5m uic") for x in a],
            lambda a: [x for x in a if x != "alter vforce = 1.8"],
            lambda a: [x.replace("alter rforce = 1m", "alter rforce = 1meg") for x in a],
            # unsupported suffix still raises this adapter's own error (#769:
            # `meg` itself now parses under _meas_expr's superset table and is
            # caught by the pinned-value check above instead)
            lambda a: [x.replace("alter rforce = 1m", "alter rforce = 1q") for x in a],
            lambda a: [x.replace("alter vforce = 1.8", "alter vforce = 1.7") for x in a],
            lambda a: a + ["op"],
            lambda a: [x for x in a if not x.startswith("meas tran")],
        ):
            raw = json.loads(json.dumps(manifest(SLUG)))
            raw["deck"]["analyses"] = edit(raw["deck"]["analyses"])
            with self.assertRaises(bes.EnableShutdownTranslationError):
                bes.parse_deck(raw["deck"]["analyses"])

    def test_unsupported_suffix_refused_by_the_number_parser_itself(self):
        # #778: the deck-shape `1q` edit above can be caught by the pinned-value
        # check instead of the suffix grammar if `q` ever joins _SCALE; this
        # case fails under that widening on its own, whichever check wins there.
        with self.assertRaisesRegex(bes.EnableShutdownTranslationError,
                                    r"unsupported alter value '1q'"):
            bes._num("1q")

    def test_untranslatable_measurement_expression_is_refused(self):
        legs = bes.parse_deck(manifest(SLUG)["deck"]["analyses"])
        for expr in ("op1.i(vvin)+op2.i(vforce)", "op9.v(vout)", "tran1.nope"):
            with self.assertRaises((bes.EnableShutdownTranslationError, blr.EndpointTranslationError)):
                bes.check_measurements(legs, [("m", expr, "V")])

    def test_changed_manifest_sections_refused_before_submission(self):
        self.refused(lambda raw: raw["deck"]["analyses"].__setitem__(
            self.find(raw, "tran "), "tran 5u 4.6m"))
        self.refused(lambda raw: raw["measurements"][0].update(max=3.5))
        self.refused(lambda raw: raw["measurements"][3].update(expr="-1e6*op2.i(vforce)"))

    def test_en_stimulus_change_refused_before_submission(self):
        self.NETLIST = ES_NETLIST.replace("2m 'vsup' 2.001m 0", "3m 'vsup' 3.001m 0")
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("not the validated chained-steps baseline", str(err))
        self.assertEqual(self.klt_calls(), [])

    def test_forcing_element_change_refused_before_submission(self):
        for old, new in (("RFORCE VOUT VF 1e12 m=1", "RFORCE VOUT VF 1k m=1"),
                         ("VFORCE VF 0 0", "VFORCE VF 0 0.5"),
                         ("RLOAD VOUT 0 1e12 m=1", "RLOAD VOUT 0 100 m=1")):
            self.NETLIST = ES_NETLIST.replace(old, new)
            err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
            self.assertIn("not the validated chained-steps baseline", str(err))
            self.assertEqual(self.klt_calls(), [])

    def test_missing_pinned_element_refused_before_submission(self):
        self.NETLIST = ES_NETLIST.replace("VVREF VREF 0 1.2\n", "")
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("VVREF", str(err))
        self.assertEqual(self.klt_calls(), [])

    def test_sibling_local_only_benches_stay_refused(self):
        for slug in ("thermal",):
            self.assertNotIn(slug, corner_run.BATCH_ALLOWLIST)

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
            self.assertEqual(len(c["measurements"]), 8)
            self.assertTrue(all(m["value"] is not None for m in c["measurements"]))
            self.assertTrue(c["pass"])


if __name__ == "__main__":
    unittest.main()
