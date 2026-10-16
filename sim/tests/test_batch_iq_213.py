"""Issue #213: the iq endpoint adapter on the opt-in `klt sim` batch backend.

PDK-free and headless (klt, xschem, git and the PDK are mocked by
test_corner_run.BatchHarness). OFFLINE translation/grading checks only; they
are not evidence of remote execution or of local/fleet equivalence.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from test_corner_run import QUICK, SIM_DIR, corner_run
from test_batch_load_regulation_381 import (
    LD_NETLIST, FakeLoadRegKlt, LoadRegHarness,
)

sys.path.insert(0, str(SIM_DIR / "bin"))
import batch_iq as biq  # noqa: E402
from _record_common import pvt_input_sections  # noqa: E402

SLUG = "iq"
STIMULUS = corner_run.BATCH_ALLOWLIST[SLUG]["stimulus"]


def manifest() -> dict:
    return json.loads((SIM_DIR / SLUG / "experiment.json").read_text())


# healthy raw cards: vout, and i(vvin) = -(iq + load)
RAW = {
    "tran1": {"vout_no_load": 1.8, "iq_no_load_raw": -14e-6},
    "tran2": {"vout_full_load": 1.798, "iq_full_load_raw": -(0.05 + 20e-6)},
}


def mutate_values(raw):
    def mutate(resp, req):
        for c in resp["corners"]:
            for m in c["measurements"]:
                step, card = m["name"].split(".", 1)
                m["value"] = raw[step][card]
    return mutate


class IqHarness(LoadRegHarness):
    SLUG = SLUG
    NETLIST = LD_NETLIST

    def quick(self, raw=None, **fake_kw):
        self.fake = FakeLoadRegKlt(self, self.pin, mutate=mutate_values(raw or RAW), **fake_kw)
        return self.run_main("--backend", "batch", *QUICK, "--no-write")


class TestIqAdapter(IqHarness):
    def test_pins_equal_the_committed_manifest(self):
        self.assertEqual(pvt_input_sections(manifest(), None),
                         corner_run.BATCH_ALLOWLIST[SLUG]["manifest_sections"])

    def test_stimulus_pin_is_what_the_endpoint_requests_write(self):
        exp = corner_run.load_experiment(self.exp_dir)
        eps = corner_run.endpoint_deck(exp)
        self.assertEqual([(e.step_name, e.iload) for e in eps], [("tran1", "0"), ("tran2", "50m")])
        self.assertEqual(list(biq.endpoint_source_lines(eps[0]).values()), STIMULUS)

    def test_requests_one_step_per_endpoint_with_current_card(self):
        rc, _, _ = self.quick()
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 6)
        for i, req in enumerate(reqs):
            (step,) = req["analysis_steps"]
            self.assertEqual(step["name"], ("tran1", "tran2")[i % 2])
            self.assertEqual(step["analysis"], {"kind": "tran", "args": "10u 200m uic"})
            spices = [m["spice"] for m in step["measurements"]]
            self.assertEqual([s.split()[3:5] for s in spices], [["avg", "v(vout)"], ["avg", "i(vvin)"]])
            self.assertTrue(all(s.endswith("from=199m to=200m") for s in spices))
            body = Path(req["netlist"]).read_text().splitlines()
            load = "0" if i % 2 == 0 else "50m"
            self.assertEqual([ln for ln in body if ln.startswith("ILOAD ")], [f"ILOAD VOUT 0 {load}"])

    def test_full_matrix_is_three_supply_groups_of_two_endpoints_45_points(self):
        self.fake = FakeLoadRegKlt(self, self.pin, mutate=mutate_values(RAW))
        rc, _, _ = self.run_main("--backend", "batch", "--no-write")
        self.assertEqual(rc, 0)
        reqs = self.requests()
        self.assertEqual(len(reqs), 6)
        self.assertEqual(sum(len(r["corners"]["process"]) * len(r["corners"]["temperature_c"])
                             for r in reqs[::2]), 45)

    def test_affine_iq_is_graded_locally_from_raw_cards(self):
        exp = corner_run.load_experiment(self.exp_dir)
        eps = corner_run.endpoint_deck(exp)
        refs = corner_run.blr.card_refs(eps)
        vals = {"tran1.iq_no_load_raw": -14e-6, "tran2.iq_full_load_raw": -(0.05 + 20e-6)}
        got = {m.name: corner_run.blr.evaluate(m.expr, vals, refs) for m in exp.measurements
               if m.name.startswith("iq_")}
        self.assertAlmostEqual(got["iq_no_load_ua"], 14.0, places=6)
        self.assertAlmostEqual(got["iq_full_load_ua"], 20.0, places=6)

    def test_negative_current_and_out_of_window_vout_fail_not_pass(self):
        bad = {"tran1": {"vout_no_load": 1.8, "iq_no_load_raw": 3e-3},   # -3000 uA
               "tran2": {"vout_full_load": 0.1, "iq_full_load_raw": -(0.05 + 20e-6)}}
        rc, _, _ = self.quick(raw=bad)
        self.assertEqual(rc, 2)

    def test_deck_shape_refusals(self):
        raw = manifest()
        for edit in (
            lambda a: [x for x in a if "iq_full_load_raw" not in x],       # drop a card
            lambda a: [x.replace("avg i(vvin)", "avg v(vin)") for x in a],  # wrong probe
            lambda a: [x.replace("avg v(vout)", "max v(vout)", 1) for x in a],  # wrong kind
        ):
            r = json.loads(json.dumps(raw))
            r["deck"]["analyses"] = edit(r["deck"]["analyses"])
            with self.assertRaises(corner_run.blr.EndpointTranslationError):
                biq.parse_deck(r["deck"]["analyses"], "0")


if __name__ == "__main__":
    unittest.main()
