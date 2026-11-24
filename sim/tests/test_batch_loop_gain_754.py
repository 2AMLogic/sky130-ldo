"""Issue #754: the loop-gain `ac_leg_grid` adapter on the opt-in `klt sim`
batch backend.

PDK-free and headless: klt, xschem, git and the PDK are mocked by
test_corner_run.BatchHarness, so nothing is submitted and no ngspice runs.
The fake answers each ESR-group `analysis_steps[]` request the way klt does
(step cards reported as `<step>.<name>`, intermediates unreported, an
unreached `.meas` crossing reported `not_reached` with a null value, a
retained engine log and a finished batch job in environment.remote). OFFLINE
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
    manifest,
)

sys.path.insert(0, str(SIM_DIR / "bin"))
import batch_loop_gain as blg  # noqa: E402

SLUG = "loop-gain"
STIMULUS = corner_run.BATCH_ALLOWLIST[SLUG]["stimulus"]

LG_NETLIST = (
    "** sch_path: x\n"
    + "\n".join([
        STIMULUS[0], ".save i(vvin)", *STIMULUS[1:], "xldo VOUT VREF EN VIN ldo_3v3in_1v8out",
        blg.NODESET_CARD,
        ".subckt ldo_3v3in_1v8out VOUT VREF EN VIN", "R1 VIN VOUT 1", ".ends",
    ])
    + "\n.end\n"
)


def healthy_values(p: str, t: float, vsup: float) -> dict[str, float | None]:
    """Plausible raw step-card values for one corner, ALL eighteen legs."""
    v: dict[str, float | None] = {}
    for i in range(1, blg.N_LEGS + 1):
        v[f"op{i}.vseed"] = 1.8
        v[f"ac{i}.fc"] = 2.0e5
        v[f"ac{i}.phc"] = -115.0 - i * 0.1  # PM ~ 65 deg
        v[f"ac{i}.gmdb"] = -18.0  # GM 18 dB
    v["ac1.dcg"] = 72.0
    return v


class FakeLoopGainKlt(FakeKlt):
    JOB_ID = "klt-sim-00109a"
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
        self.test.assertNotIn("measurements", req)  # graded locally, never by klt
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
                logp.write_text(self.log_text or f"ac sweep {p} {t}\n")
                meas = []
                for step in req["analysis_steps"]:
                    for m in step["measurements"]:
                        if m.get("intermediate"):
                            continue
                        name = f"{step['name']}.{m['name']}"
                        if not ok:
                            continue
                        value = vals.get(name)
                        if value is None:
                            meas.append({"name": name, "value": None, "status": "not_reached",
                                         "severity": "info"})
                        else:
                            meas.append({"name": name, "value": value, "status": "pass"})
                corners.append({
                    "corner_id": f"{p}/novdd/{t:g}C", "process": p, "temperature_c": t,
                    "status": "pass" if ok else "error", "runtime_s": self.RUNTIME_S,
                    "diagnostics": [] if ok else [
                        {"severity": "error", "code": "step_failed", "message": "no value"}],
                    "artifacts": {"log": str(logp)}, "measurements": meas,
                })
        resp = {
            "status": "pass", "corners": corners,
            "environment": {"engine": "ngspice", "engine_version": "47",
                            "remote": {"provider": "aws-batch-fleet", "job_id": self.JOB_ID,
                                       "state": "done", "exit_code": "0",
                                       "runner_compatibility": "match"}},
            "provenance": {"klt_version": "0.9.3.dev4220+g01d19126ca02",
                           "pdk": {"version": self.pin["open_pdks_commit"]}},
        }
        if self.mutate:
            self.mutate(resp, req)
        out = self.stdout if self.stdout is not None else json.dumps(resp)
        return subprocess.CompletedProcess(cmd, self.rc, stdout=out, stderr="")


class LoopGainHarness(BatchHarness):
    SLUG = SLUG
    NETLIST = LG_NETLIST
    REFUSAL_TEXT = "no longer has the validated ac-leg-grid shape"

    def make_fake(self, **kw):
        return FakeLoopGainKlt(self, self.pin, **kw)

    def requests(self):
        return [json.loads(Path(c[0][2]).read_text()) for c in self.klt_calls()]

    def write_manifest(self, raw):
        (self.exp_dir / "experiment.json").write_text(json.dumps(raw))

    def quick(self, **fake_kw):
        self.fake = self.make_fake(**fake_kw)
        return self.run_main("--backend", "batch", *QUICK, "--no-write")


def deck_of(edit):
    raw = json.loads(json.dumps(manifest(SLUG)))
    edit(raw)
    return raw


class TestLoopGainAdapter(EndpointShapeGate, BackendContract, RecordProvenance, LoopGainHarness):
    FIRST_CARD = "vseed"
    DEFAULT_VALUES = staticmethod(healthy_values)

    # -- the translation -----------------------------------------------------
    def test_parse_deck_replays_the_eighteen_legs_into_three_esr_groups(self):
        raw = manifest(SLUG)
        legs = blg.parse_deck(raw["deck"]["analyses"], raw["ac_leg_grid"])
        self.assertEqual(len(legs), 18)
        self.assertEqual([l.group for l in legs], ["esr10m"] * 6 + ["esr500m"] * 6 + ["esr0"] * 6)
        self.assertEqual([l.id for l in legs], [g["id"] for g in raw["ac_leg_grid"]["legs"]])
        leg13 = legs[12]
        self.assertEqual((leg13.cout_f, leg13.esr_ohm, leg13.rload_ohm), (4.7e-6, 0.0, 36.0))
        self.assertEqual(legs[2].rload_ohm, 1e12)  # the 0 mA leg
        self.assertEqual(legs[1].rload_ohm, 1800.0)

    def test_request_is_twelve_steps_per_esr_group_with_explicit_alters(self):
        rc, _, _ = self.quick()
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 9)  # 3 quick points x 3 ESR groups
        first = reqs[:3]
        for req, (key, _e, lit) in zip(first, blg.ESR_GROUPS):
            self.assertEqual(len(req["analysis_steps"]), 12)
            self.assertEqual(req["options"]["ngspice_init"][-1], "set units=degrees")
            self.assertEqual(req["options"]["ngspice_init"][:-1], corner_run.spiceinit_lines())
            net = Path(req["netlist"]).read_text().splitlines()
            self.assertEqual([l for l in net if l.startswith("HESR")], [f"HESR VESRS 0 VESRSENSE {lit}"])
            self.assertTrue(key in Path(req["netlist"]).name)
            for s in req["analysis_steps"][::2]:
                self.assertEqual(s["analysis"], {"kind": "op", "args": ""})
                self.assertEqual(set(s["alter"]), {"COUT", "RLOAD"})
        esr0 = first[2]["analysis_steps"]
        self.assertEqual(esr0[0]["name"], "op13")
        self.assertEqual(esr0[0]["alter"], {"COUT": 4.7e-6, "RLOAD": 36.0})  # self-contained group
        self.assertEqual(esr0[1]["analysis"], {"kind": "ac", "args": "dec 30 1e-2 1e9"})
        cards = {m["name"]: m for m in esr0[1]["measurements"]}
        for c in ("fc", "phc", "gmdb"):
            self.assertEqual(cards[c]["on_unreached"], "null")
        self.assertNotIn("dcg", cards)  # leg 1 only
        ac1 = {m["name"]: m for m in first[0]["analysis_steps"][1]["measurements"]}
        self.assertEqual(ac1["dcg"]["expr"], "lgdb[0]")
        # the zero-ESR group carries the exact CCVS short, never a resistor
        self.assertNotIn("RESR", Path(first[2]["netlist"]).read_text())

    def test_full_matrix_is_nine_requests_covering_45_points(self):
        self.fake = self.make_fake()
        rc, _, _ = self.run_main("--backend", "batch", "--no-write")
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 9)
        self.assertEqual(sum(len(r["corners"]["process"]) * len(r["corners"]["temperature_c"])
                             for r in reqs), 3 * 3 * 15)

    # -- grading ----------------------------------------------------------------
    def checks(self, out_rec):
        return {m["name"]: m for m in out_rec["corners"][0]["measurements"]}

    def test_record_grades_all_56_measurements_and_passes(self):
        _, rec = self.run_and_load_record()
        ex = rec["execution"]
        self.assertEqual(len(ex["requests"]), 9)
        self.assertEqual(ex["adapter"]["name"], "loop-gain-ac-leg-grid")
        self.assertEqual(ex["adapter"]["issue"], 754)
        for r in ex["requests"]:
            self.assertEqual(r["reported_backend"], "aws-batch-fleet")
            self.assertTrue(r["klt_pdk_names_pin"])
        for c in rec["corners"]:
            self.assertEqual(len(c["measurements"]), 56)
            self.assertTrue(all(m["value"] is not None for m in c["measurements"]))
            self.assertTrue(c["pass"])
            self.assertEqual(len(c["klt_request"]), 3)

    def boundary(self, name_value):
        def values(p, t, vsup):
            v = healthy_values(p, t, vsup)
            v.update(name_value)
            return v
        return values

    def run_values(self, values_of):
        self.fake = self.make_fake(values_of=values_of)
        rc, out, err = self.run_main("--backend", "batch", *QUICK)
        (path,) = self.records()
        return rc, json.loads(path.read_text())

    def test_bounds_are_strict_at_equality(self):
        # PM = 45.0, GM = 10.0 and the vout_seed window ends all PASS ...
        rc, rec = self.run_values(self.boundary({
            "ac4.phc": -135.0, "ac4.gmdb": -10.0, "op1.vseed": 1.62, "op2.vseed": 1.98}))
        self.assertEqual(rc, 0)
        # ... and a hair outside FAILS
        for edit in ({"ac4.phc": -135.0001}, {"ac4.gmdb": -9.9999},
                     {"op1.vseed": 1.6199}, {"op2.vseed": 1.9801}):
            self.setUp_fresh()
            rc, rec = self.run_values(self.boundary(edit))
            self.assertEqual(rc, 2, edit)
            self.assertFalse(rec["corners"][0]["pass"], edit)

    def setUp_fresh(self):
        for f in self.records():
            f.unlink()

    def test_unreached_crossing_grades_fail_never_pass_and_keeps_other_legs(self):
        def values(p, t, vsup):
            v = healthy_values(p, t, vsup)
            v["ac8.gmdb"] = None  # leg 8 never crosses -180 deg
            return v
        rc, rec = self.run_values(values)
        self.assertEqual(rc, 2)
        c = rec["corners"][0]
        by = {m["name"]: m for m in c["measurements"]}
        self.assertFalse(by["gm_c033_esr500m_1ma_db"]["pass"])
        self.assertIsNone(by["gm_c033_esr500m_1ma_db"]["value"])
        self.assertTrue(by["pm_c033_esr500m_1ma_deg"]["pass"])  # the rest still graded
        self.assertEqual(c["batch_reasons"], [])  # a missing crossing is not a corner error
        self.assertEqual(sum(1 for m in c["measurements"] if not m["pass"]), 1)

    def test_missing_result_and_unrequested_result_cannot_pass(self):
        def drop_leg(resp, req):
            if req["analysis_steps"][0]["name"] == "op7":
                resp["corners"][0]["measurements"] = [
                    m for m in resp["corners"][0]["measurements"] if not m["name"].startswith("ac9.")]
        rc, out, err = self.quick(mutate=drop_leg)
        self.assertEqual(rc, 2)
        self.assertIn("reported 0 time(s)", err)

        def extra(resp, req):
            resp["corners"][0]["measurements"].append(
                {"name": "ac1.lgdb", "value": 1.0, "status": "pass"})
        rc, out, err = self.quick(mutate=extra)
        self.assertEqual(rc, 2)
        self.assertIn("is not one the request asked for", err)

    def test_corner_with_a_missing_esr_group_cannot_pass(self):
        exp = corner_run.load_experiment(self.exp_dir)
        from _batch_backend import finalize_ac_grid_results
        corner = corner_run.Corner("tt", 27.0, 3.3)
        values = healthy_values("tt", 27.0, 3.3)
        part = lambda g: {"corner": corner, "group": g, "values": values, "reasons": [],
                          "solver_diagnostic": None, "elapsed_s": 1.0, "klt_request": g,
                          "klt_corner_id": "c", "klt_status": "pass"}
        ok = finalize_ac_grid_results(exp, [corner], {corner.id: [part(g) for g in blg.GROUP_KEYS]}, 60)
        self.assertTrue(ok[0]["pass"])
        short = finalize_ac_grid_results(exp, [corner], {corner.id: [part("esr10m"), part("esr0")]}, 60)
        self.assertFalse(short[0]["pass"])
        self.assertTrue(any("esr500m" in r for r in short[0]["batch_reasons"]))
        dup = finalize_ac_grid_results(
            exp, [corner], {corner.id: [part(g) for g in blg.GROUP_KEYS] + [part("esr0")]}, 60)
        self.assertFalse(dup[0]["pass"])

    # -- refusals -----------------------------------------------------------------
    def test_deck_shape_refusals(self):
        edits = (
            lambda a: [x.replace("ac dec 30 1e-2 1e9", "ac dec 10 1e-2 1e9") for x in a],
            lambda a: [x for x in a if x != "set units=degrees"],
            lambda a: [x for x in a if x != "let dcg = lgdb[0]"],
            lambda a: [x.replace("alter hesr gain = 500m", "alter hesr gain = 400m") for x in a],
            lambda a: [x.replace("alter rload = 1.8k", "alter rload = 2k") for x in a],
            # unsupported suffix still raises this adapter's own error (#769)
            lambda a: [x.replace("alter rload = 1.8k", "alter rload = 1.8q") for x in a],
            lambda a: a + ["alter rload = 36"],
            lambda a: [x.replace("meas ac phc find lgph when lgdb=0 cross=1",
                                 "meas ac phc find lgph when lgdb=0 cross=2") for x in a],
        )
        for edit in edits:
            raw = deck_of(lambda r, edit=edit: r["deck"].update(analyses=edit(r["deck"]["analyses"])))
            with self.assertRaises(blg.LoopGainTranslationError):
                blg.parse_deck(raw["deck"]["analyses"], raw["ac_leg_grid"])

    def test_ac_leg_grid_drift_refused_even_though_digests_do_not_cover_it(self):
        def edit(raw):
            raw["ac_leg_grid"]["legs"][3]["cout_f"] = 2.2e-6
        self.refused(edit)

    def test_measurement_expression_edit_refused(self):
        self.refused(lambda raw: raw["measurements"][0].update(expr="170 + ac1.phc"))

    def test_deck_edit_refused_before_submission(self):
        self.refused(lambda raw: raw["deck"]["analyses"].__setitem__(
            self.find(raw, "ac dec", 4), "ac dec 31 1e-2 1e9"))

    def test_netlist_refusals_before_submission(self):
        cases = {
            "seed absent": ([ln for ln in LG_NETLIST.splitlines() if not ln.startswith(".nodeset")],
                            "pinned card"),
            "seed edited": ([ln.replace("=0.6", "=0.7") if ln.startswith(".nodeset") else ln
                             for ln in LG_NETLIST.splitlines()], "is not allowed in an AC leg-grid request"),
            "hesr changed": ([ln.replace("VESRSENSE 10m", "VESRSENSE 20m") for ln in LG_NETLIST.splitlines()],
                             "stimulus element HESR"),
            "hesr duplicated": (LG_NETLIST.splitlines() + ["HESR VESRS 0 VESRSENSE 10m"],
                                "stimulus element HESR"),
            "cout changed": ([ln.replace("0.33u", "1u") for ln in LG_NETLIST.splitlines()],
                             "stimulus element COUT"),
        }
        for name, (lines, why) in cases.items():
            self.NETLIST = "\n".join(lines) + "\n"
            self.fake = self.make_fake()
            err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
            self.assertIn("not the validated ac-leg-grid baseline", str(err), name)
            self.assertIn(why, str(err), name)
            self.assertEqual(self.klt_calls(), [], name)

    def test_admitted_and_sibling_benches_still_refused(self):
        self.assertIn(SLUG, corner_run.BATCH_ALLOWLIST)
        for slug in ("psrr-dc", "thermal"):
            self.assertNotIn(slug, corner_run.BATCH_ALLOWLIST)

    def test_dry_run_prints_the_nine_requests(self):
        self.fake = self.make_fake()
        rc, out, _ = self.run_main("--backend", "batch", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("batch (9 klt sim request(s))", out)
        self.assertIn("HESR VESRS 0 VESRSENSE 0", out)
        self.assertEqual(self.klt_calls(), [])


if __name__ == "__main__":
    unittest.main()
