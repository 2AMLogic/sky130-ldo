"""Shared contract scaffolding for the `klt sim` batch endpoint-adapter tests
(issue #587).

One definition per contract property. The three adapter test files
(`test_batch_dropout_374.py`, `test_batch_line_regulation_379.py`,
`test_batch_load_regulation_381.py`) each carried their own byte-identical copy
of the LDO baseline netlist, the manifest-shape-gate helpers, the two renewal
tripwires and the batch-backend response contract; a change to any of them had
to be made two or three times and could silently be made once. The tripwires in
particular exist to fail when an adapter drifts, so a stale copy is exactly the
failure they are meant to catch.

This applies the split `sim/README.md`'s "Writing a new batch-fleet campaign
driver (issue #574)" section already settles for the campaign drivers — shared
core in one module, per-case shaping left in the caller — one layer up, to the
adapter tests. What stays in each adapter's own file: its admission rules, its
mutation tables, its card lists, its grading maths and its record assertions.

The mixins below carry test methods, so each adapter subclass contributes its
own copy of every shared test (one test method per subclass, as before). The
leading underscore keeps this module out of collection: `sim/selftest.sh` runs
`python3 -m unittest discover -s sim/tests -t sim/tests`, which collects
`test*.py` only — the same reason `_sim_script_loader.py` is named that way.
"""

from __future__ import annotations

import json
import sys

from test_corner_run import QUICK, SIM_DIR, HarnessErr, corner_run

sys.path.insert(0, str(SIM_DIR / "bin"))
from _record_common import pvt_input_sections  # noqa: E402


def baseline_netlist(slug: str) -> str:
    """The LDO baseline xschem netlist every endpoint adapter validates against,
    carrying `slug`'s own validated stimulus pin.

    The body is one deck for all adapters; the only thing that varies is the
    three-line stimulus, which already comes keyed by slug from
    `corner_run.BATCH_ALLOWLIST[slug]["stimulus"]`.
    """
    stimulus = corner_run.BATCH_ALLOWLIST[slug]["stimulus"]
    return (
        "** sch_path: x\n"
        + "\n".join(
            [stimulus[0], ".save i(vvin)", stimulus[1], "VVREF VREF 0 1.2",
             "xldo VOUT VREF EN VIN ldo_3v3in_1v8out", "COUT VOUT VESR 1u m=1", "RESR VESR 0 10m m=1",
             stimulus[2], ".subckt ldo_3v3in_1v8out VOUT VREF EN VIN", "R1 VIN VOUT 1", ".ends"]
        )
        + "\n.end\n"
    )


def manifest(slug: str) -> dict:
    """The committed experiment manifest for `slug`, re-read from the repo."""
    return json.loads((SIM_DIR / slug / "experiment.json").read_text())


class EndpointShapeGate:
    """The manifest-shape-gate helpers and the two renewal tripwires.

    Mix into a `BatchHarness` subclass that sets `SLUG` and provides
    `write_manifest()`. `REFUSAL_TEXT` is the adapter's own shape-gate refusal
    phrase, the one `refused()` asserts by default.
    """

    REFUSAL_TEXT: str = ""

    def refused(self, edit, expect=None):
        """Apply `edit` to the committed manifest and assert the adapter refuses
        it before anything is netlisted or submitted."""
        raw = manifest(self.SLUG)
        edit(raw)
        self.write_manifest(raw)
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn(self.REFUSAL_TEXT if expect is None else expect, str(err))
        self.assertEqual(self.fake.calls, [])
        corner_run.netlist_with_xschem.assert_not_called()
        return str(err)

    def code_lines(self, raw):
        """Indices of the manifest's non-comment analysis lines."""
        return [i for i, ln in enumerate(raw["deck"]["analyses"]) if not ln.lstrip().startswith("*")]

    def find(self, raw, prefix, nth=0):
        """Index of the `nth` non-comment analysis line starting with `prefix`."""
        hits = [i for i in self.code_lines(raw) if raw["deck"]["analyses"][i].startswith(prefix)]
        return hits[nth]

    # -- renewal tripwires: they fail when the committed manifest's execution
    #    sections drift from the pins the adapter was validated against.
    def test_prose_only_edits_keep_the_validated_shape(self):
        raw = manifest(self.SLUG)
        raw["claim"] += " (edited)"
        raw["measurements"][0]["note"] = "short"
        raw["deck"]["analyses"].insert(0, "* an added comment")
        self.write_manifest(raw)
        rc, _, _ = self.run_main("--backend", "batch", *QUICK, "--no-write")
        self.assertEqual(rc, 0)

    def test_pins_equal_the_committed_manifest(self):
        # Renewal tripwire: editing the manifest's execution sections fails
        # this test until the adapter is re-validated and the pins updated.
        want = corner_run.BATCH_ALLOWLIST[self.SLUG]["manifest_sections"]
        self.assertEqual(pvt_input_sections(manifest(self.SLUG), None), want)


class SiblingBenchGate:
    """The sibling-regulation benches stay off the batch allowlist.

    Its own mixin rather than part of `EndpointShapeGate` so it keeps exactly
    the two copies it has today — the dropout adapter never claimed it.
    """

    def test_sibling_regulation_benches_stay_refused(self):
        for slug in ("psrr-dc", "startup"):
            self.assertNotIn(slug, corner_run.BATCH_ALLOWLIST)


class BackendContract:
    """The batch-backend response contract, which is adapter-independent by
    construction: response-envelope integrity, solver-diagnostic refusal, and
    the structural-abort guarantee — no evidence record written, no retry, no
    local fallback, exactly one `klt` call.

    Mix into a `BatchHarness` subclass providing `make_fake()`, `quick()` and
    `klt_calls()`, and set:
      FIRST_CARD      the name of the manifest's first raw `.meas` card
      DEFAULT_VALUES  staticmethod: the adapter's healthy per-endpoint values
    """

    FIRST_CARD: str = ""
    DEFAULT_VALUES = None

    def test_missing_duplicate_nonfinite_or_unexpected_values_cannot_pass(self):
        card = self.FIRST_CARD
        edits = {
            "missing": lambda c: c["measurements"].pop(1),
            "duplicate": lambda c: c["measurements"].append(dict(c["measurements"][0])),
            "nan": lambda c: c["measurements"][2].update(value=float("nan")),
            "null": lambda c: c["measurements"][0].update(value=None),
            "string": lambda c: c["measurements"][0].update(value="1.8"),
            "unexpected identity": lambda c: c["measurements"].append(
                {"name": "tran1.not_requested", "value": 1.8, "status": "pass"}),
            "wrong step": lambda c: c["measurements"][0].update(name=f"dropout.{card}"),
            "unqualified name": lambda c: c["measurements"][0].update(name=card),
            "errored value": lambda c: c["measurements"][0].update(status="error"),
        }
        for name, edit in edits.items():
            def m(resp, req, edit=edit):
                edit(resp["corners"][0])
            rc, out, err = self.quick(mutate=m)
            self.assertEqual(rc, 2, name)
            self.assertIn("FAIL", out, name)

    def test_errored_or_incomplete_corner_cannot_pass(self):
        healthy = self.DEFAULT_VALUES
        rc, out, err = self.quick(values_of=lambda p, t, *pt: None if p == "ss" else healthy(p, t, *pt))
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
            self.fake = self.make_fake(mutate=mutate)
            err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
            self.assertIn("no evidence record written", str(err), name)
            self.assertFalse((self.exp_dir / "records").exists())
            self.assertEqual(len(self.klt_calls()), 1, name)  # no retry, no local fallback

    def test_error_envelope_aborts(self):
        env = {"schema_version": 1, "error": {"command": "sim", "message": "batch backend failed"}}
        self.fake = self.make_fake(stdout=json.dumps(env), rc=1)
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("error envelope", str(err))


class RecordProvenance:
    """The provenance head every adapter's evidence record carries.

    A helper, not a test: each adapter's own record test calls it and then
    asserts its own adapter block, request count and log contents.
    """

    def run_and_load_record(self):
        """Run the quick subset writing a record, then load the one it minted."""
        rc, out, _ = self.run_main("--backend", "batch", *QUICK)
        self.assertEqual(rc, 0, out)
        (rec_path,) = self.records()
        rec = json.loads(rec_path.read_text())
        self.assertEqual(rec["backend"], "batch")
        self.assertTrue(rec["matrix"]["is_subset"])
        self.assertEqual([r["corner_id"] for r in rec["corners"]], rec["matrix"]["point_ids"])
        return rec_path, rec
