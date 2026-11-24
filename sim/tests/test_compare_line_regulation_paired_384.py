"""Issue #384: PDK-free controls for the paired line-regulation comparison.

These exercise the comparison logic only; they are not simulator evidence.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from test_corner_run import SIM_DIR

sys.path.insert(0, str(SIM_DIR / "bin"))
import compare_line_regulation_paired as cmp


def values() -> dict:
    v = {
        "vout_1ma_lo": 1.8005,
        "vout_1ma_hi": 1.80071,
        "vout_50ma_lo": 1.79872,
        "vout_50ma_hi": 1.79892,
    }
    for k in list(v):
        v[k + "_min"] = v[k + "_max"] = v[k]
    v.update(cmp.derive_slopes(v))
    return v


class CompareTests(unittest.TestCase):
    def run_cmp(self, local=None, re="46", le="46", rp=True, lp=True):
        remote = values()
        return cmp.compare(
            remote, local if local is not None else dict(remote), re, le, rp, lp
        )

    def test_identical_same_engine_is_equivalent(self):
        r = self.run_cmp()
        self.assertEqual(r["verdict"], "equivalent")
        self.assertTrue(r["equivalence_claimable"])
        self.assertEqual(len(r["rows"]), 14)

    def test_missing_value_is_unresolved(self):
        local = values()
        del local["vout_50ma_hi_min"]
        r = self.run_cmp(local)
        self.assertEqual(
            (r["verdict"], r["missing"]), ("unresolved", ["vout_50ma_hi_min"])
        )

    def test_non_finite_value_is_unresolved(self):
        local = values()
        local["vout_1ma_lo"] = float("nan")
        self.assertEqual(self.run_cmp(local)["verdict"], "unresolved")

    def test_tolerance_breach_is_rejected_not_widened(self):
        local = values()
        local["vout_50ma_hi_max"] += 2e-6
        r = self.run_cmp(local)
        self.assertEqual(
            (r["verdict"], r["breaches"]), ("rejected", ["vout_50ma_hi_max"])
        )

    def test_slope_breach_is_rejected(self):
        local = values()
        local["line_reg_1ma_mv_per_v"] += 0.02
        self.assertEqual(self.run_cmp(local)["breaches"], ["line_reg_1ma_mv_per_v"])

    def test_engine_mismatch_blocks_equivalence_claim(self):
        r = self.run_cmp(le="42")
        self.assertEqual(r["verdict"], "engine_mismatch")
        self.assertFalse(r["equivalence_claimable"])

    def test_unknown_remote_engine_blocks_equivalence_claim(self):
        self.assertFalse(self.run_cmp(re=None)["equivalence_claimable"])

    def test_matching_spec_failure_is_equivalent_but_not_compliance(self):
        r = self.run_cmp(rp=False, lp=False)
        self.assertEqual(r["verdict"], "equivalent")
        self.assertEqual(
            r["spec_verdicts"],
            {"remote_pass": False, "local_pass": False, "match": True},
        )

    def test_mismatched_spec_verdicts_are_unresolved(self):
        self.assertEqual(self.run_cmp(rp=True, lp=False)["verdict"], "unresolved")


GROUPS = (("1ma", "lo"), ("1ma", "hi"), ("50ma", "lo"), ("50ma", "hi"))


def write_remote(d: Path, environments, vals=None) -> None:
    """Lay out remote/tran{1..4}/response.json: each request carries its own
    `environment` and, given `vals`, its three endpoint measurements."""
    for t, (environment, (ld, vin)) in enumerate(zip(environments, GROUPS), 1):
        names = [f"vout_{ld}_{vin}{sfx}" for sfx in ("", "_min", "_max")]
        ms = (
            [{"name": f"tran.{n}", "status": "pass", "value": vals[n]} for n in names]
            if vals
            else []
        )
        (d / "remote" / f"tran{t}").mkdir(parents=True)
        (d / "remote" / f"tran{t}" / "response.json").write_text(
            json.dumps({"environment": environment, "corners": [{"measurements": ms}]})
        )


class RemoteEngineTests(unittest.TestCase):
    """Issue #768: the fleet version is the one all four responses agree on."""

    KNOWN = {"engine_version": "46"}

    def load(self, environments):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            write_remote(d, environments)
            return cmp.load_remote(d)[1]

    def test_known_version_in_every_response(self):
        self.assertEqual(self.load([self.KNOWN] * 4), "46")

    def test_absent_version_is_none_not_the_string(self):
        self.assertIsNone(self.load([{}] * 4))

    def test_null_version_is_none(self):
        self.assertIsNone(self.load([{"engine_version": None}] * 4))

    def test_one_response_missing_its_version_is_none(self):
        self.assertIsNone(self.load([self.KNOWN, {}, self.KNOWN, self.KNOWN]))

    def test_conflicting_versions_are_none(self):
        self.assertIsNone(
            self.load([self.KNOWN, self.KNOWN, {"engine_version": "47"}, self.KNOWN])
        )


class CliEngineTests(unittest.TestCase):
    """Issue #768: both legs agree on every endpoint and both grade FAIL, so
    the verdict turns on the engine version alone."""

    def run_cli(self, environments, local_engine):
        v = values()
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            write_remote(d, environments, v)
            (d / "local").mkdir()
            (d / "local" / "corner-run.log").write_text(
                "[    1/1] tt_27c_3v30 FAIL "
                + ", ".join(f"{k}={x!r}" for k, x in v.items())
                + "\n"
            )
            out = d / "report.json"
            argv = [str(d), "--local-engine", local_engine, "--remote-pass", "FAIL",
                    "--out", str(out)]
            with contextlib.redirect_stdout(io.StringIO()):
                rc = cmp.main(argv)
            text = out.read_text()
        return rc, json.loads(text), text

    def test_missing_version_is_json_null_and_exit_2_for_any_local_engine(self):
        for environment in ({}, {"engine_version": None}):
            for local_engine in ("46", "None"):
                with self.subTest(environment=environment, local_engine=local_engine):
                    rc, rep, text = self.run_cli([environment] * 4, local_engine)
                    self.assertEqual(rc, 2)
                    self.assertEqual(rep["verdict"], "engine_mismatch")
                    self.assertIn('"remote_engine": null', text)

    def test_matching_known_version_and_grades_exit_0(self):
        rc, rep, _ = self.run_cli([{"engine_version": "46"}] * 4, "46")
        self.assertEqual(rc, 0)
        self.assertEqual(rep["verdict"], "equivalent")


if __name__ == "__main__":
    unittest.main()
