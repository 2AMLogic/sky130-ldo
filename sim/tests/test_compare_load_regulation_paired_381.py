"""Issue #381: PDK-free controls for the paired load-regulation comparison.

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
import compare_load_regulation_paired as cmp


def values() -> dict:
    v = {"vout_0ma": 1.802385, "vout_50ma": 1.798832}
    v.update({k + s: v[k] for k in list(v) for s in ("_min", "_max")})
    v.update(cmp.derive(v))
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
        self.assertEqual(len(r["rows"]), 8)

    def test_engine_mismatch_never_claimable(self):
        r = self.run_cmp(le="42")
        self.assertEqual(r["verdict"], "engine_mismatch")
        self.assertFalse(r["equivalence_claimable"])

    def test_missing_and_non_finite_are_unresolved(self):
        local = values()
        del local["vout_50ma_min"]
        self.assertEqual(self.run_cmp(local)["verdict"], "unresolved")
        local = values()
        local["vout_0ma"] = float("nan")
        self.assertEqual(self.run_cmp(local)["verdict"], "unresolved")

    def test_tolerance_breach_is_rejected_not_widened(self):
        local = values()
        local["vout_50ma_max"] += 2e-6
        r = self.run_cmp(local)
        self.assertEqual((r["verdict"], r["breaches"]), ("rejected", ["vout_50ma_max"]))

    def test_derived_tolerance_breach(self):
        local = values()
        local["load_reg_v"] += 3e-6
        self.assertEqual(self.run_cmp(local)["breaches"], ["load_reg_v"])

    def test_verdict_mismatch_is_unresolved(self):
        self.assertEqual(self.run_cmp(lp=False)["verdict"], "unresolved")

    def test_derive(self):
        d = cmp.derive(values())
        self.assertAlmostEqual(d["load_reg_v"], 0.003553, places=9)
        self.assertAlmostEqual(d["load_reg_pct"], 0.197389, places=5)

    def test_load_local_reads_meas_and_print_lines_last_wins(self):
        import tempfile
        from pathlib import Path

        log = (
            "vout_0ma            =  1.80239e+00 from=  1.99000e-01 to=  2.00000e-01\n"
            "vout_0ma = 1.8023850000e+00\n"
            "vout_50ma = 1.7988320000e+00\n"
        )
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "local").mkdir()
            (Path(t) / "local" / "ngspice.log").write_text(log)
            v = cmp.load_local(Path(t))
        self.assertEqual(v["vout_0ma"], 1.802385)
        self.assertEqual(v["vout_50ma"], 1.798832)


GROUPS = ("0ma", "50ma")


def write_remote(d: Path, environments, vals=None) -> None:
    """Lay out remote/tran{1,2}/response.json: each request carries its own
    `environment` and, given `vals`, its three endpoint measurements."""
    for t, (environment, ld) in enumerate(zip(environments, GROUPS), 1):
        names = [f"vout_{ld}{sfx}" for sfx in ("", "_min", "_max")]
        ms = [{"name": f"tran.{n}", "value": vals[n]} for n in names] if vals else []
        (d / "remote" / f"tran{t}").mkdir(parents=True)
        (d / "remote" / f"tran{t}" / "response.json").write_text(
            json.dumps({"environment": environment, "corners": [{"measurements": ms}]})
        )


class RemoteEngineTests(unittest.TestCase):
    """Issue #768: the fleet version is the one both responses agree on."""

    KNOWN = {"engine_version": "46"}

    def load(self, environments):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            write_remote(d, environments)
            return cmp.load_remote(d)[1]

    def test_known_version_in_every_response(self):
        self.assertEqual(self.load([self.KNOWN] * 2), "46")

    def test_absent_version_is_none_not_the_string(self):
        self.assertIsNone(self.load([{}] * 2))

    def test_null_version_is_none(self):
        self.assertIsNone(self.load([{"engine_version": None}] * 2))

    def test_one_response_missing_its_version_is_none(self):
        self.assertIsNone(self.load([{}, self.KNOWN]))

    def test_conflicting_versions_are_none(self):
        self.assertIsNone(self.load([self.KNOWN, {"engine_version": "47"}]))


class CliEngineTests(unittest.TestCase):
    """Issue #768: both legs agree on every endpoint and both grade FAIL, so
    the verdict turns on the engine version alone."""

    def run_cli(self, environments, local_engine):
        v = values()
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            write_remote(d, environments, v)
            (d / "local").mkdir()
            (d / "local" / "ngspice.log").write_text(
                "".join(f"{k} = {x!r}\n" for k, x in v.items())
            )
            out = d / "report.json"
            argv = [str(d), "--local-engine", local_engine, "--remote-pass", "FAIL",
                    "--local-pass", "FAIL", "--out", str(out)]
            with contextlib.redirect_stdout(io.StringIO()):
                rc = cmp.main(argv)
            text = out.read_text()
        return rc, json.loads(text), text

    def test_missing_version_is_json_null_and_exit_2_for_any_local_engine(self):
        for environment in ({}, {"engine_version": None}):
            for local_engine in ("46", "None"):
                with self.subTest(environment=environment, local_engine=local_engine):
                    rc, rep, text = self.run_cli([environment] * 2, local_engine)
                    self.assertEqual(rc, 2)
                    self.assertEqual(rep["verdict"], "engine_mismatch")
                    self.assertIn('"remote_engine": null', text)

    def test_matching_known_version_and_grades_exit_0(self):
        rc, rep, _ = self.run_cli([{"engine_version": "46"}] * 2, "46")
        self.assertEqual(rc, 0)
        self.assertEqual(rep["verdict"], "equivalent")


if __name__ == "__main__":
    unittest.main()
