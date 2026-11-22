"""Issue #177: the current-limit chained-steps adapter on the opt-in
`klt sim` batch backend.

PDK-free and headless: klt, xschem, git and the PDK are mocked by
test_corner_run.BatchHarness, so nothing is submitted and no ngspice runs.
The fake answers each three-step request the way klt's `analysis_steps[]`
runner does (verified once against a real local `klt sim` run while building
the adapter): step cards reported as `<step>.<card>`, the request's own
top-level `meas_<name>` rows evaluated over them as derived results, a
retained engine log and a finished batch job in environment.remote. OFFLINE
translation/grading checks only; they are not evidence of remote execution or
of local/fleet equivalence.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from test_corner_run import QUICK, SIM_DIR, BatchHarness, FakeKlt, HarnessErr, corner_run
from _endpoint_adapter_contract import (
    BackendContract,
    EndpointShapeGate,
    RecordProvenance,
    baseline_netlist,
    manifest,
)

sys.path.insert(0, str(SIM_DIR / "bin"))
import batch_current_limit as bcl  # noqa: E402
import batch_line_regulation as blr  # noqa: E402

SLUG = "current-limit"
STIMULUS = corner_run.BATCH_ALLOWLIST[SLUG]["stimulus"]

CL_NETLIST = baseline_netlist(SLUG, extra=(bcl.NODESET_CARD,))


def healthy_values(p: str, t: float, vsup: float) -> dict[str, float]:
    """Physically plausible raw card values for one corner: a regulating
    50 mA point, a brickwall-ish DC characteristic and a held short."""
    vout = 1.8 + {"tt": 0, "ss": -0.01, "ff": 0.01, "sf": 0.005, "fs": -0.005}[p] - 1e-4 * (t - 27)
    span = 1e-5 + 1e-6 * (t - 27) / 100
    ilim = 0.153 - 8e-4 * (t - 27)
    ish = -(ilim + 0.01)
    return {
        "tran1.vout_50ma": vout,
        "tran1.vout_50ma_lo": vout - span / 2,
        "tran1.vout_50ma_hi": vout + span / 2,
        "tran1.vin_50ma": vsup,
        "tran1.cl_cmp_50ma": vsup - 0.042,
        "dc1.ilim_short": ilim,
        "dc1.ilim_knee": ilim * 0.8,  # knee sits below the short, both above the 50 mA floor
        "tran2.ipre": -0.0133,
        "tran2.ish_avg": ish,
        "tran2.ish_max": ish + 4e-5,
        "tran2.ish_min": ish - 4e-5,
        "tran2.vsh_max": ilim * 1e-3,
    }


class FakeChainedKlt(FakeKlt):
    """Answers a three-step chained request the way klt does: `<step>.<card>`
    results, the request's own derived rows evaluated over them, a retained
    engine log and a finished batch job in environment.remote."""

    JOB_ID = "klt-sim-00ca17"
    RUNTIME_S = 41.0

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
        # issue #647: the seeded dc leg leads the deck
        self.test.assertEqual([s["name"] for s in req["analysis_steps"]],
                              ["dc1", "tran1", "tran2"])
        lines = Path(req["netlist"]).read_text().splitlines()
        vsup = float(lines[0].split("=")[1])
        outdir = Path(cmd[cmd.index("-o") + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        corners = []
        for p in req["corners"]["process"]:
            for t in req["corners"]["temperature_c"]:
                vals = self.values_of(p, t, vsup)
                ok = vals is not None
                logp = outdir / f"{p}_{t}.log"
                logp.write_text(self.log_text or f"triangle waveform {p} {t}\n")
                meas = []
                # every card the request's steps declare is a possible ref,
                # whether or not this corner produced a value for it (a
                # missing card makes the derived rows over it error, not the
                # expression grammar)
                refs = {f"{s['name']}.{m['name']}".lower() for s in req["analysis_steps"]
                        for m in s.get("measurements") or []}
                for name, value in (vals or {}).items():
                    meas.append({"name": name, "value": value, "status": "pass" if ok else "error"})
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


class CurrentLimitHarness(BatchHarness):
    SLUG = SLUG
    NETLIST = CL_NETLIST
    REFUSAL_TEXT = "no longer has the validated chained-steps shape"

    def make_fake(self, **kw):
        return FakeChainedKlt(self, self.pin, **kw)

    def requests(self):
        return [json.loads(Path(c[0][2]).read_text()) for c in self.klt_calls()]

    def write_manifest(self, raw):
        (self.exp_dir / "experiment.json").write_text(json.dumps(raw))

    def quick(self, **fake_kw):
        self.fake = self.make_fake(**fake_kw)
        return self.run_main("--backend", "batch", *QUICK, "--no-write")


class TestCurrentLimitAdapter(
    EndpointShapeGate, BackendContract, RecordProvenance, CurrentLimitHarness
):
    FIRST_CARD = "vout_50ma"
    DEFAULT_VALUES = staticmethod(lambda p, t, vsup=3.3: healthy_values(p, t, vsup))

    # -- the translation -----------------------------------------------------
    def test_parse_deck_translates_the_three_chained_legs(self):
        legs = bcl.parse_deck(manifest(SLUG)["deck"]["analyses"])
        # issue #647: the seeded dc leg LEADS the deck; step names follow
        # content (dc1, tran1, tran2), so the manifest's plot-qualified
        # graded expressions are position-independent
        self.assertEqual([(l.step_name, l.kind) for l in legs],
                         [("dc1", "dc"), ("tran1", "tran"), ("tran2", "tran")])
        self.assertEqual(legs[0].alters, [("rload", 1e12), ("rforce", 1e-3)])
        self.assertEqual(legs[0].analysis_args, "vforce 0 1.75 0.125")
        self.assertEqual(legs[1].alters, [("rload", 36.0), ("rforce", 1e12)])  # baseline restored
        self.assertEqual(legs[1].analysis_args, "5u 1.0m uic")
        self.assertEqual(legs[2].alters, [("rforce", 1e-3)])  # the short conducts through RFORCE
        self.assertEqual(legs[2].analysis_args, "500n 3.0m uic")
        self.assertEqual([n for n, _ in legs[0].cards], ["ilim_short", "ilim_knee"])
        self.assertEqual([n for n, _ in legs[1].cards],
                         ["vout_50ma", "vout_50ma_lo", "vout_50ma_hi", "vin_50ma", "cl_cmp_50ma"])
        self.assertEqual([n for n, _ in legs[2].cards],
                         ["ipre", "ish_avg", "ish_max", "ish_min", "vsh_max"])

    def test_request_carries_the_three_steps_and_verbatim_derived_rows(self):
        rc, _, _ = self.quick()
        self.assertEqual(rc, 0)
        req = self.requests()[0]
        steps = bcl.chained_steps(bcl.parse_deck(manifest(SLUG)["deck"]["analyses"]))
        self.assertEqual(req["analysis_steps"], steps)
        exp = corner_run.load_experiment(self.exp_dir)
        self.assertEqual(req["measurements"],
                         [{"name": f"meas_{m.name}", "expr": m.expr, "unit": m.unit}
                          for m in exp.measurements])

    def test_stimulus_pin_is_the_baseline_leg_1_state(self):
        # leg 1 runs at the netlist's own values; legs 2/3 alter from here --
        # so the pin IS leg 1's state: RLOAD = 36, RFORCE open, VFORCE's PWL
        # holding 1.8 V until the 1.001 ms short.
        self.assertEqual(STIMULUS, [
            "VVIN VIN 0 'vsup'",
            "VEN EN 0 dc 'vsup' pwl(0 0 100u 0 101u 'vsup' 10 'vsup')",
            "RLOAD VOUT 0 36 m=1",
            "RFORCE VOUT VF 1e12 m=1",
            "VFORCE VF 0 dc 1.8 pwl(0 1.8 1m 1.8 1.001m 0 10 0)",
        ])

    def test_full_matrix_is_three_supply_groups_of_15_points_45_total(self):
        self.fake = self.make_fake()
        rc, _, _ = self.run_main("--backend", "batch", "--no-write")
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 3)
        self.assertEqual(sum(len(r["corners"]["process"]) * len(r["corners"]["temperature_c"])
                             for r in reqs), 45)
        for req in reqs:
            self.assertEqual(len(req["analysis_steps"]), 3)
            self.assertEqual(len(req["measurements"]), 10)

    # -- grading ----------------------------------------------------------------
    def test_out_of_window_vout_fails_not_passes(self):
        def bad(p, t, vsup):
            v = healthy_values(p, t, vsup)
            v["tran1.vout_50ma"] = 1.9  # above the ratified Output window's 1.836
            v["tran1.vout_50ma_hi"] = 1.9005
            v["tran1.vout_50ma_lo"] = 1.8995
            return v
        rc, out, _ = self.quick(values_of=bad)
        self.assertEqual(rc, 2)
        self.assertIn("FAIL", out)

    def test_negative_short_current_reports_its_bound_reason(self):
        def sink(p, t, vsup):
            v = healthy_values(p, t, vsup)
            v["dc1.ilim_short"] = 0.01  # 10 mA: the clamp sits below the 50 mA floor
            return v
        rc, out, _ = self.quick(values_of=sink)
        self.assertEqual(rc, 2)
        self.assertIn("FAIL", out)

    def test_errored_step_card_value_cannot_pass(self):
        def broken(p, t, vsup):
            v = healthy_values(p, t, vsup)
            v.pop("dc1.ilim_short")  # the step produced no value for this card
            return v
        rc, out, _ = self.quick(values_of=broken)
        self.assertEqual(rc, 2)
        self.assertIn("FAIL", out)

    # -- refusals -----------------------------------------------------------------
    def test_deck_shape_refusals(self):
        for edit in (
            lambda a: [x.replace("tran 5u 1.0m uic", "tran 5u 1.0m") for x in a],  # no uic
            lambda a: [x for x in a if x != "tran 500n 3.0m uic"],  # leg 3 truncated
            lambda a: [x.replace("dc vforce 0 1.75 0.125", "op") for x in a],
            lambda a: a + ["alter rload = 36"],  # a fourth alter after leg 3
            lambda a: [x.replace("alter rforce = 1m", "alter rforce = 1meg") for x in a],
            # issue #647: the pre-#647 leg order (leg 1's tran first) no
            # longer parses -- the seeded dc leg must lead the deck
            lambda a: (
                [x for x in a if x == "tran 5u 1.0m uic"
                 or x.startswith(("meas tran vout_50ma", "meas tran vin_50ma", "meas tran cl_cmp_50ma"))]
                + [x for x in a if not (
                    x == "tran 5u 1.0m uic"
                    or x.startswith(("meas tran vout_50ma", "meas tran vin_50ma", "meas tran cl_cmp_50ma")))]
            ),
        ):
            r = json.loads(json.dumps(manifest(SLUG)))
            r["deck"]["analyses"] = edit(r["deck"]["analyses"])
            with self.assertRaises((bcl.CurrentLimitTranslationError, blr.EndpointTranslationError)):
                bcl.parse_deck(r["deck"]["analyses"])

    def test_seed_card_change_refused_before_submission(self):
        def tweak_seed(body):
            return [ln.replace("v(xldo.NB)=0.8641", "v(xldo.NB)=0.9") if ln.startswith(".nodeset") else ln
                    for ln in body]
        self.NETLIST = "\n".join(tweak_seed(CL_NETLIST.splitlines())) + "\n"
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        # a mutated card is not the pin, so the forbidden-card scan catches it
        self.assertIn("is not allowed in a current-limit chained-step request", str(err))
        self.assertEqual(self.klt_calls(), [])

    def test_seed_card_absent_refused_before_submission(self):
        self.NETLIST = "\n".join(
            ln for ln in CL_NETLIST.splitlines() if not ln.startswith(".nodeset")
        ) + "\n"
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("pinned card", str(err))
        self.assertEqual(self.klt_calls(), [])

    def test_stimulus_change_refused_before_submission(self):
        def swap_vforce_pwl(body):
            return [ln.replace("pwl(0 1.8 1m 1.8 1.001m 0 10 0)", "pwl(0 0 1m 0 1.001m 0 10 0)")
                    if ln.startswith("VFORCE ") else ln for ln in body]
        self.NETLIST = "\n".join(swap_vforce_pwl(CL_NETLIST.splitlines())) + "\n"
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("not the validated chained-steps baseline", str(err))
        self.assertEqual(self.klt_calls(), [])

    def test_editing_an_execution_manifest_section_refuses_even_with_matching_pins_stale(self):
        # issue #647: the seeded dc leg's own sweep line, restep-width edited
        self.refused(lambda raw: raw["deck"]["analyses"].__setitem__(
            self.find(raw, "dc vforce"), "dc vforce 0 1.75 0.05"))

    def test_sibling_local_only_benches_stay_refused(self):
        for slug in ("psrr-dc", "loop-gain", "enable-shutdown", "thermal"):
            self.assertNotIn(slug, corner_run.BATCH_ALLOWLIST)

    # -- provenance ------------------------------------------------------------
    def test_record_carries_batch_provenance_and_all_three_legs_evidence(self):
        rec_path, rec = self.run_and_load_record()
        ex = rec["execution"]
        self.assertEqual(len(ex["requests"]), 3)  # quick = 3 singleton requests
        for r, key in zip(ex["requests"], ("q1-tt_27c_3.30v", "q2-ss_-40c_2.97v", "q3-ff_125c_3.63v")):
            self.assertEqual(r["key"], key)
            self.assertEqual(r["reported_backend"], "aws-batch-fleet")
            self.assertTrue(r["job_id"])
            self.assertTrue(r["klt_pdk_names_pin"])
        # every corner's 12 step cards + 10 graded rows are in its checks
        for c in rec["corners"]:
            self.assertEqual(len(c["measurements"]), 10)
            self.assertTrue(all(m["value"] is not None for m in c["measurements"]))
            self.assertTrue(c["pass"])


if __name__ == "__main__":
    unittest.main()
