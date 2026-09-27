"""Unit coverage for sim/bin/yield-run.py's negative-control helpers.

PDK-free by design (no ngspice/xschem/volare/klt required) so this runs on
every `npm run check:ci` invocation, including in CI where the sky130 PDK is
not installed -- see sim/selftest.sh stage 1/3, and the sibling
test_corner_run.py this file mirrors.

yield-run.py is loaded by file path (not `import yield_run`) because the CLI
convention keeps the hyphenated `yield-run.py` filename, exactly as
test_corner_run.py does for `corner-run.py`.

Scope (issue #217): the four helpers PR #216 (issue #211's negative-control
work) grew without coverage -- `extract_sim_report_samples`,
`negative_control_description`, `build_sample_set` and `cross_check_nominal`.
The first three are pure data transforms; `cross_check_nominal` shells out to
`klt yield` via `run_klt_yield`, so its `subprocess.run` is mocked here
(mirroring test_corner_run.py's fake-ngspice pattern) and no real `klt` is
ever invoked.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR / "bin"))  # yield-run.py imports _record_common (issue #46)
_spec = importlib.util.spec_from_file_location("yield_run", SIM_DIR / "bin" / "yield-run.py")
yield_run = importlib.util.module_from_spec(_spec)
sys.modules["yield_run"] = yield_run
_spec.loader.exec_module(yield_run)

WHERE = "sim/mc-fixture/klt-responses/20260101-000000-abcdef0.json"


def _mc_corner(corner_id: str, values, name: str = "vout_mean"):
    """One `klt sim` Monte Carlo corner carrying `name` = each of `values`."""
    return {
        "corner_id": corner_id,
        "monte_carlo": {"sample": 0, "seed": 1},
        "measurements": [{"name": name, "value": v} for v in values],
    }


def _sim_report(corners, rollup=None) -> dict:
    report = {"corners": corners}
    if rollup is not None:
        report["measurements"] = rollup
    return report


class TestExtractSimReportSamples(unittest.TestCase):
    """The nominal leg of the derived sample-set document is *extracted* by
    this function rather than read by `klt yield` itself, so it has to apply
    the same rule the tool does: only corners carrying a non-null
    `monte_carlo` block contribute, a `null` value counts into `errored`, and
    `source_corners` strips klt sim's `/mc<i>` sample suffix."""

    def test_extracts_values_in_corner_order(self):
        report = _sim_report(
            [
                _mc_corner("tt_27c_3.30v/mc0", [1.80]),
                _mc_corner("tt_27c_3.30v/mc1", [1.81]),
                _mc_corner("tt_27c_3.30v/mc2", [1.79]),
            ]
        )
        out = yield_run.extract_sim_report_samples(report, "vout_mean", WHERE)
        self.assertEqual(out["samples"], [1.80, 1.81, 1.79])
        self.assertEqual(out["errored"], 0)

    def test_integer_values_are_coerced_to_float(self):
        report = _sim_report([_mc_corner("tt_27c_3.30v/mc0", [2])])
        out = yield_run.extract_sim_report_samples(report, "vout_mean", WHERE)
        self.assertEqual(out["samples"], [2.0])
        self.assertIsInstance(out["samples"][0], float)

    def test_null_value_counts_into_errored_and_is_not_sampled(self):
        report = _sim_report(
            [
                _mc_corner("tt_27c_3.30v/mc0", [1.80]),
                _mc_corner("tt_27c_3.30v/mc1", [None]),
                _mc_corner("tt_27c_3.30v/mc2", [1.79]),
            ]
        )
        out = yield_run.extract_sim_report_samples(report, "vout_mean", WHERE)
        self.assertEqual(out["samples"], [1.80, 1.79])
        self.assertEqual(out["errored"], 1)

    def test_source_corners_strip_the_mc_sample_suffix(self):
        report = _sim_report(
            [
                _mc_corner("tt_27c_3.30v/mc0", [1.80]),
                _mc_corner("tt_27c_3.30v/mc1", [1.81]),
            ]
        )
        out = yield_run.extract_sim_report_samples(report, "vout_mean", WHERE)
        self.assertEqual(out["source_corners"], ["tt_27c_3.30v"])

    def test_source_corners_dedupe_preserving_first_occurrence_order(self):
        report = _sim_report(
            [
                _mc_corner("ss_-40c_3.00v/mc0", [1.78]),
                _mc_corner("tt_27c_3.30v/mc0", [1.80]),
                _mc_corner("ss_-40c_3.00v/mc1", [1.77]),
                _mc_corner("tt_27c_3.30v/mc1", [1.81]),
            ]
        )
        out = yield_run.extract_sim_report_samples(report, "vout_mean", WHERE)
        self.assertEqual(out["source_corners"], ["ss_-40c_3.00v", "tt_27c_3.30v"])

    def test_corner_id_without_an_mc_suffix_is_kept_whole(self):
        report = _sim_report([_mc_corner("tt_27c_3.30v", [1.80])])
        out = yield_run.extract_sim_report_samples(report, "vout_mean", WHERE)
        self.assertEqual(out["source_corners"], ["tt_27c_3.30v"])

    def test_deterministic_pvt_corner_does_not_contribute_samples(self):
        # A corner with no `monte_carlo` block is not a draw from any
        # distribution, so its value must not land in the sample set.
        pvt = {
            "corner_id": "tt_27c_3.30v",
            "monte_carlo": None,
            "measurements": [{"name": "vout_mean", "value": 9.99}],
        }
        report = _sim_report([pvt, _mc_corner("tt_27c_3.30v/mc0", [1.80])])
        out = yield_run.extract_sim_report_samples(report, "vout_mean", WHERE)
        self.assertEqual(out["samples"], [1.80])

    def test_unit_is_carried_from_the_report_rollup(self):
        report = _sim_report(
            [_mc_corner("tt_27c_3.30v/mc0", [1.80])],
            rollup=[{"name": "vout_mean", "unit": "V"}],
        )
        out = yield_run.extract_sim_report_samples(report, "vout_mean", WHERE)
        self.assertEqual(out["unit"], "V")

    def test_unit_is_none_when_the_rollup_declares_none(self):
        report = _sim_report([_mc_corner("tt_27c_3.30v/mc0", [1.80])])
        out = yield_run.extract_sim_report_samples(report, "vout_mean", WHERE)
        self.assertIsNone(out["unit"])

    def test_other_measurements_in_the_same_corner_are_ignored(self):
        corner = _mc_corner("tt_27c_3.30v/mc0", [1.80])
        corner["measurements"].append({"name": "iq", "value": 1.2e-6})
        out = yield_run.extract_sim_report_samples(_sim_report([corner]), "vout_mean", WHERE)
        self.assertEqual(out["samples"], [1.80])

    def test_missing_corners_array_raises(self):
        with self.assertRaisesRegex(yield_run.HarnessError, "no 'corners' array"):
            yield_run.extract_sim_report_samples({}, "vout_mean", WHERE)

    def test_empty_corners_array_raises(self):
        with self.assertRaisesRegex(yield_run.HarnessError, "no 'corners' array"):
            yield_run.extract_sim_report_samples({"corners": []}, "vout_mean", WHERE)

    def test_non_list_corners_raises(self):
        with self.assertRaisesRegex(yield_run.HarnessError, "no 'corners' array"):
            yield_run.extract_sim_report_samples({"corners": {}}, "vout_mean", WHERE)

    def test_no_monte_carlo_corner_raises(self):
        report = {
            "corners": [
                {
                    "corner_id": "tt_27c_3.30v",
                    "monte_carlo": None,
                    "measurements": [{"name": "vout_mean", "value": 1.80}],
                }
            ]
        }
        with self.assertRaisesRegex(yield_run.HarnessError, "no corner carries a 'monte_carlo'"):
            yield_run.extract_sim_report_samples(report, "vout_mean", WHERE)

    def test_measurement_not_found_raises(self):
        report = _sim_report([_mc_corner("tt_27c_3.30v/mc0", [1.80])])
        with self.assertRaises(yield_run.HarnessError) as ctx:
            yield_run.extract_sim_report_samples(report, "iq", WHERE)
        message = str(ctx.exception)
        self.assertIn("no Monte Carlo corner reports a measurement named 'iq'", message)
        self.assertIn("must measure the same thing", message)

    def test_non_numeric_value_raises(self):
        report = _sim_report([_mc_corner("tt_27c_3.30v/mc0", ["1.80"])])
        with self.assertRaisesRegex(yield_run.HarnessError, "non-numeric value in corner"):
            yield_run.extract_sim_report_samples(report, "vout_mean", WHERE)

    def test_boolean_value_raises_rather_than_being_read_as_a_number(self):
        # bool is a subclass of int in Python; a `true` in a response is a
        # malformed measurement, not the sample 1.0.
        report = _sim_report([_mc_corner("tt_27c_3.30v/mc0", [True])])
        with self.assertRaisesRegex(yield_run.HarnessError, "non-numeric value in corner"):
            yield_run.extract_sim_report_samples(report, "vout_mean", WHERE)

    def test_error_message_names_the_input_document(self):
        with self.assertRaises(yield_run.HarnessError) as ctx:
            yield_run.extract_sim_report_samples({}, "vout_mean", WHERE)
        self.assertIn(WHERE, str(ctx.exception))


class TestNegativeControlDescription(unittest.TestCase):
    """Built from the degraded campaign's own committed manifest/record rather
    than from a flag, so the description cannot drift from the defect that
    actually ran."""

    EXP = {"slug": "mc-negative-control"}
    RECORD = {
        "netlist_patch": {
            "purpose": "negative control",
            "rationale": "halve the pass device width",
            "substitutions": [{"match": "W=10u", "replace": "W=5u", "count": 2}],
        },
        "klt_request": {"monte_carlo": {"n": 200, "vary": "mismatch", "seed": 20260817}},
    }

    def test_full_description_shape(self):
        out = yield_run.negative_control_description(
            self.EXP, self.RECORD, "20260101-000000-abcdef0"
        )
        self.assertEqual(
            out,
            "seeded known-bad variant `mc-negative-control` record "
            "20260101-000000-abcdef0 | N=200, vary=mismatch, seed=20260817 | "
            "declared netlist_patch: `W=10u` -> `W=5u` | "
            "rationale: halve the pass device width",
        )

    def test_multiple_substitutions_are_semicolon_joined(self):
        record = json.loads(json.dumps(self.RECORD))
        record["netlist_patch"]["substitutions"].append(
            {"match": "L=0.5u", "replace": "L=1u", "count": 1}
        )
        out = yield_run.negative_control_description(self.EXP, record, "rec")
        self.assertIn("declared netlist_patch: `W=10u` -> `W=5u`; `L=0.5u` -> `L=1u`", out)

    def test_no_netlist_patch_omits_both_patch_clauses(self):
        record = {"klt_request": {"monte_carlo": {"n": 50, "vary": "mismatch", "seed": 7}}}
        out = yield_run.negative_control_description(self.EXP, record, "rec")
        self.assertEqual(
            out,
            "seeded known-bad variant `mc-negative-control` record rec | "
            "N=50, vary=mismatch, seed=7",
        )
        self.assertNotIn("netlist_patch", out)
        self.assertNotIn("rationale", out)

    def test_patch_without_rationale_omits_only_the_rationale_clause(self):
        record = json.loads(json.dumps(self.RECORD))
        del record["netlist_patch"]["rationale"]
        out = yield_run.negative_control_description(self.EXP, record, "rec")
        self.assertIn("declared netlist_patch: `W=10u` -> `W=5u`", out)
        self.assertNotIn("rationale:", out)

    def test_patch_without_substitutions_omits_only_the_substitution_clause(self):
        record = json.loads(json.dumps(self.RECORD))
        del record["netlist_patch"]["substitutions"]
        out = yield_run.negative_control_description(self.EXP, record, "rec")
        self.assertNotIn("declared netlist_patch:", out)
        self.assertIn("rationale: halve the pass device width", out)

    def test_missing_monte_carlo_block_renders_none_rather_than_crashing(self):
        out = yield_run.negative_control_description(self.EXP, {}, "rec")
        self.assertIn("N=None, vary=None, seed=None", out)

    def test_missing_slug_renders_a_question_mark(self):
        out = yield_run.negative_control_description({}, self.RECORD, "rec")
        self.assertIn("seeded known-bad variant `?` record rec", out)


class TestBuildSampleSet(unittest.TestCase):
    NOMINAL = {
        "vout_mean": {
            "samples": [1.80, 1.81, 1.79],
            "errored": 0,
            "source_corners": ["tt_27c_3.30v"],
            "unit": "V",
        }
    }
    CONTROL = {
        "vout_mean": {
            "samples": [1.60, 1.59],
            "errored": 1,
            "source_corners": ["tt_27c_3.30v"],
            "unit": "V",
        }
    }
    LIMITS = {"measurements": {"vout_mean": {"min": 1.764, "max": 1.836}}}
    PROVENANCE = {"nominal_response": "nominal.json", "control_response": "control.json"}

    def _build(self, nominal=None, control=None, limits=None):
        return yield_run.build_sample_set(
            self.NOMINAL if nominal is None else nominal,
            self.CONTROL if control is None else control,
            self.LIMITS if limits is None else limits,
            "a description",
            self.PROVENANCE,
        )

    def test_one_entry_per_measurement_the_limits_document_names(self):
        doc = self._build()
        self.assertEqual([m["name"] for m in doc["measurements"]], ["vout_mean"])

    def test_nominal_samples_are_copied_verbatim(self):
        entry = self._build()["measurements"][0]
        self.assertEqual(entry["samples"], [1.80, 1.81, 1.79])
        self.assertEqual(entry["errored"], 0)
        self.assertEqual(entry["source_corners"], ["tt_27c_3.30v"])

    def test_control_samples_land_under_negative_control(self):
        entry = self._build()["measurements"][0]
        self.assertEqual(entry["negative_control"]["samples"], [1.60, 1.59])
        self.assertEqual(entry["negative_control"]["errored"], 1)
        self.assertEqual(entry["negative_control"]["description"], "a description")

    def test_limits_are_carried_from_the_limits_document(self):
        entry = self._build()["measurements"][0]
        self.assertEqual(entry["limits"], {"min": 1.764, "max": 1.836})

    def test_unit_is_carried_when_the_nominal_leg_has_one(self):
        self.assertEqual(self._build()["measurements"][0]["unit"], "V")

    def test_unit_is_omitted_when_the_nominal_leg_has_none(self):
        nominal = {
            "vout_mean": {"samples": [1.80], "errored": 0, "source_corners": ["tt"], "unit": None}
        }
        self.assertNotIn("unit", self._build(nominal=nominal)["measurements"][0])

    def test_provenance_is_carried_through(self):
        self.assertEqual(self._build()["provenance"], self.PROVENANCE)

    def test_document_carries_the_append_only_evidence_comment(self):
        comment = "\n".join(self._build()["comment"])
        self.assertIn("APPEND-ONLY EVIDENCE", comment)
        self.assertIn("NOTHING HERE IS A NEW MEASUREMENT", comment)
        self.assertIn("2AMLogic/klayout-tools#2563", comment)

    def test_measurement_missing_from_the_nominal_campaign_raises(self):
        limits = {"measurements": {"iq": {"max": 5e-6}}}
        with self.assertRaises(yield_run.HarnessError) as ctx:
            self._build(limits=limits)
        self.assertIn("the nominal campaign reports no measurement named 'iq'", str(ctx.exception))

    def test_measurement_missing_from_the_control_campaign_raises(self):
        nominal = dict(self.NOMINAL)
        nominal["iq"] = {"samples": [1e-6], "errored": 0, "source_corners": ["tt"], "unit": "A"}
        limits = {"measurements": {"iq": {"max": 5e-6}}}
        with self.assertRaises(yield_run.HarnessError) as ctx:
            self._build(nominal=nominal, limits=limits)
        message = str(ctx.exception)
        self.assertIn("the negative-control campaign reports no measurement named 'iq'", message)
        self.assertIn("cannot be compared against the nominal", message)

    def test_measurement_order_follows_the_limits_document(self):
        nominal = dict(self.NOMINAL)
        control = dict(self.CONTROL)
        for legs in (nominal, control):
            legs["iq"] = {"samples": [1e-6], "errored": 0, "source_corners": ["tt"], "unit": "A"}
        limits = {
            "measurements": {"iq": {"max": 5e-6}, "vout_mean": {"min": 1.764, "max": 1.836}}
        }
        doc = self._build(nominal=nominal, control=control, limits=limits)
        self.assertEqual([m["name"] for m in doc["measurements"]], ["iq", "vout_mean"])


def _measurement(name: str = "vout_mean", **overrides) -> dict:
    """One `klt yield` report measurement, with the four cross-checked blocks."""
    m = {
        "name": name,
        "n": 200,
        "errored": 0,
        "distribution": {"fit": "normal", "mean": 1.8, "stddev": 0.01},
        "capability": {"cpk": 1.2},
        "sample_size": {"verdict": "sufficient", "n": 200},
        "yield": {"empirical": {"passed": 198, "n": 200, "fraction": 0.99}},
    }
    m.update(overrides)
    return m


class TestCrossCheckNominal(unittest.TestCase):
    """The negative-control path hands `klt yield` a document this runner
    built, so the same `klt yield` is run a second time directly over the
    nominal response and the two nominal analyses are required to be
    identical. `run_klt_yield`'s `subprocess.run` is mocked here -- no real
    `klt` is invoked, and this test needs no PDK."""

    NOMINAL_RESPONSE = Path("sim/mc-fixture/klt-responses/20260101-000000-abcdef0.json")
    SOURCE_RECORD_ID = "20260101-000000-abcdef0"

    def _args(self):
        return argparse.Namespace(
            confidence=None, target_ci_halfwidth=None, min_samples=None, measurement=[]
        )

    def _run(self, derived: dict, direct: dict):
        fake_proc = subprocess.CompletedProcess(
            args=["klt", "yield"], returncode=0, stdout=json.dumps(direct), stderr=""
        )
        exp_dir = yield_run.REPO_ROOT / "sim" / "mc-fixture"
        with mock.patch.object(yield_run.subprocess, "run", return_value=fake_proc) as run:
            out = yield_run.cross_check_nominal(
                derived,
                self.NOMINAL_RESPONSE,
                exp_dir,
                self.SOURCE_RECORD_ID,
                "/nonexistent/klt",
                exp_dir / "klt-responses",
                f"../klt-requests/{self.SOURCE_RECORD_ID}.yield-limits.json",
                self._args(),
            )
        return out, run

    def test_identical_analyses_pass_and_are_recorded(self):
        report = {"measurements": [_measurement()]}
        direct = {"measurements": [_measurement()]}
        out, _run = self._run(report, direct)
        self.assertEqual(out["verdict"], "identical")
        self.assertEqual(out["nominal_response"], self.NOMINAL_RESPONSE.name)
        self.assertEqual(
            out["nominal_record"], f"sim/mc-fixture/records/{self.SOURCE_RECORD_ID}.md"
        )
        self.assertEqual(
            out["measurements"]["vout_mean"],
            {
                "n": 200,
                "errored": 0,
                "distribution_identical": True,
                "capability_identical": True,
                "sample_size_identical": True,
                "empirical_yield_identical": True,
            },
        )
        self.assertIn("byte-equal", out["method"])

    def test_the_second_klt_yield_run_targets_the_nominal_response_by_bare_name(self):
        report = {"measurements": [_measurement()]}
        _out, run = self._run(report, {"measurements": [_measurement()]})
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:3], ["/nonexistent/klt", "yield", self.NOMINAL_RESPONSE.name])
        self.assertIn("--format", cmd)

    def test_every_measurement_is_cross_checked(self):
        report = {"measurements": [_measurement("vout_mean"), _measurement("iq")]}
        direct = {"measurements": [_measurement("iq"), _measurement("vout_mean")]}
        out, _run = self._run(report, direct)
        self.assertEqual(sorted(out["measurements"]), ["iq", "vout_mean"])

    def test_distribution_mismatch_raises(self):
        report = {"measurements": [_measurement()]}
        direct = {
            "measurements": [
                _measurement(distribution={"fit": "normal", "mean": 1.7999, "stddev": 0.01})
            ]
        }
        with self.assertRaises(yield_run.HarnessError) as ctx:
            self._run(report, direct)
        message = str(ctx.exception)
        self.assertIn("nominal cross-check FAILED", message)
        self.assertIn("'distribution'", message)
        self.assertIn("fix the extraction, do not record this", message)

    def test_capability_mismatch_raises(self):
        report = {"measurements": [_measurement()]}
        direct = {"measurements": [_measurement(capability={"cpk": 1.3})]}
        with self.assertRaises(yield_run.HarnessError) as ctx:
            self._run(report, direct)
        self.assertIn("'capability'", str(ctx.exception))

    def test_sample_size_mismatch_raises(self):
        report = {"measurements": [_measurement()]}
        direct = {"measurements": [_measurement(sample_size={"verdict": "insufficient", "n": 20})]}
        with self.assertRaises(yield_run.HarnessError) as ctx:
            self._run(report, direct)
        self.assertIn("'sample_size'", str(ctx.exception))

    def test_empirical_yield_mismatch_raises(self):
        report = {"measurements": [_measurement()]}
        # `yield` is a Python keyword, so this override goes in by name.
        direct = {
            "measurements": [
                _measurement(
                    **{"yield": {"empirical": {"passed": 197, "n": 200, "fraction": 0.985}}}
                )
            ]
        }
        with self.assertRaises(yield_run.HarnessError) as ctx:
            self._run(report, direct)
        message = str(ctx.exception)
        self.assertIn("nominal cross-check FAILED", message)
        self.assertIn("empirical yield", message)

    def test_measurement_absent_from_the_direct_analysis_raises(self):
        report = {"measurements": [_measurement("vout_mean")]}
        direct = {"measurements": [_measurement("iq")]}
        with self.assertRaises(yield_run.HarnessError) as ctx:
            self._run(report, direct)
        self.assertIn("reports no measurement 'vout_mean'", str(ctx.exception))

    def test_klt_yield_producing_no_stdout_raises(self):
        fake_proc = subprocess.CompletedProcess(
            args=["klt", "yield"], returncode=2, stdout="", stderr="boom"
        )
        exp_dir = yield_run.REPO_ROOT / "sim" / "mc-fixture"
        with mock.patch.object(yield_run.subprocess, "run", return_value=fake_proc):
            with self.assertRaisesRegex(yield_run.HarnessError, "produced no stdout"):
                yield_run.cross_check_nominal(
                    {"measurements": [_measurement()]},
                    self.NOMINAL_RESPONSE,
                    exp_dir,
                    self.SOURCE_RECORD_ID,
                    "/nonexistent/klt",
                    exp_dir / "klt-responses",
                    "limits.json",
                    self._args(),
                )


if __name__ == "__main__":
    unittest.main()
