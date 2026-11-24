"""Issue #757: PDK-free controls for the paired loop-gain comparison.

These exercise the comparison logic only; they are not simulator evidence.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from test_corner_run import SIM_DIR

sys.path.insert(0, str(SIM_DIR / "bin"))
import compare_loop_gain_paired as cmp


def raw() -> dict:
    v = {}
    for i in range(1, 19):
        v[f"op{i}.vseed"] = 1.8 + i * 1e-3
        v[f"ac{i}.phc"] = -120.0 - i
        v[f"ac{i}.gmdb"] = -15.0 - i * 0.1
    v["ac1.fc"] = 12345.678
    v["ac1.dcg"] = 80.5
    return v


class CompareTests(unittest.TestCase):
    def run_cmp(self, local=None, remote=None, re="46", le="46", rp=True, lp=True):
        remote = remote if remote is not None else raw()
        return cmp.compare(remote, local if local is not None else dict(remote), re, le, rp, lp)

    def test_identical_same_engine_is_equivalent(self):
        r = self.run_cmp()
        self.assertEqual(r["verdict"], "equivalent")
        self.assertEqual(len(r["rows"]), 56)

    def test_engine_mismatch_never_claimable(self):
        r = self.run_cmp(le="42")
        self.assertEqual(r["verdict"], "engine_mismatch")
        self.assertFalse(r["equivalence_claimable"])

    def test_two_confirmed_non_crossings_agree(self):
        a, b = raw(), raw()
        for d in (a, b):
            d["ac14.gmdb"] = cmp.NOT_REACHED
            d["ac15.gmdb"] = cmp.NOT_REACHED
        r = self.run_cmp(local=b, remote=a)
        self.assertEqual(r["verdict"], "equivalent")
        self.assertEqual(r["unreached_both"], ["gm14", "gm15"])
        self.assertEqual(len(r["rows"]), 56)

    def test_one_sided_crossing_is_rejected(self):
        loc = raw()
        loc["ac14.gmdb"] = cmp.NOT_REACHED
        r = self.run_cmp(local=loc)
        self.assertEqual((r["verdict"], r["breaches"]), ("rejected", ["gm14"]))
        self.assertFalse(r["equivalence_claimable"])

    def test_missing_and_malformed_are_unresolved(self):
        for bad in (None, float("nan"), "oops", True):
            loc = raw()
            loc["op7.vseed"] = bad
            self.assertEqual(self.run_cmp(local=loc)["verdict"], "unresolved", bad)
        loc = raw()
        del loc["ac3.phc"]
        r = self.run_cmp(local=loc)
        self.assertEqual((r["verdict"], r["missing"]), ("unresolved", ["pm3"]))

    def test_missing_with_unreached_other_side_is_unresolved(self):
        rem = raw()
        rem["ac5.gmdb"] = cmp.NOT_REACHED
        loc = raw()
        del loc["ac5.gmdb"]
        self.assertEqual(self.run_cmp(local=loc, remote=rem)["verdict"], "unresolved")

    def test_tolerance_breach_is_rejected_not_widened(self):
        loc = raw()
        loc["ac13.phc"] += 2e-3
        r = self.run_cmp(local=loc)
        self.assertEqual((r["verdict"], r["breaches"]), ("rejected", ["pm13"]))

    def test_verdict_mismatch_is_unresolved(self):
        self.assertEqual(self.run_cmp(lp=False)["verdict"], "unresolved")
        self.assertEqual(self.run_cmp(rp=None, lp=None)["verdict"], "unresolved")

    def test_continuation_legs_reported(self):
        loc = raw()
        loc["op7.vseed"] += 5e-6
        r = self.run_cmp(local=loc)
        self.assertEqual(sorted(r["continuation_legs"]), ["13", "7"])
        self.assertEqual(r["breaches"], ["vseed7"])
        self.assertAlmostEqual(r["continuation_legs"]["7"]["vseed"]["local"], 1.807005)

    def test_pm_gm_derivation(self):
        d = cmp.derive(raw())
        self.assertAlmostEqual(d["pm1"], 59.0)
        self.assertAlmostEqual(d["gm1"], 15.1)


ERR = "runner-error"  # sentinel: layout writes this result as status "error"


def confirming_log(step: str, card: str) -> str:
    """The three ngspice log lines that pin a no-crossing on one step+card."""
    return (
        f"Error: measure  {card}  find(AT) : out of interval\n"
        f" meas ac {card} find lgdb when lgph=-1.800000e+02 cross=1 failed!\n"
        f"Warning from checkvalid: vector {step}__{card} is not available "
        "or has zero length.\n"
    )


def write_pair(d: Path, engines=("46", "46", "46"), remote_mut=None, local_mut=None, logs=None):
    """Lay out <d>/remote/<group>/response.json and <d>/local/values.json from raw()."""
    r = raw()
    if remote_mut:
        remote_mut(r)
    groups = ("esr10m", "esr500m", "esr0")
    for gi, (g, eng) in enumerate(zip(groups, engines)):
        ms = []
        for k, v in r.items():
            leg = int("".join(c for c in k.split(".")[0] if c.isdigit()))
            if (leg - 1) // 6 != gi:
                continue
            if v is ERR:
                ms.append({"name": k, "step": k.split(".")[0], "status": "error", "value": None})
            elif v is None:
                ms.append({"name": k, "step": k.split(".")[0], "status": "not_reached", "value": None})
            else:
                ms.append({"name": k, "step": k.split(".")[0], "status": "ok", "value": v})
        (d / "remote" / g).mkdir(parents=True)
        (d / "remote" / g / "response.json").write_text(json.dumps(
            {"environment": {"engine_version": eng}, "corners": [{"measurements": ms}]}))
        if logs and g in logs:
            (d / "remote" / g / "ngspice.log").write_text(logs[g])
    (d / "local").mkdir()
    loc = raw()
    if local_mut:
        local_mut(loc)
    (d / "local" / "values.json").write_text(json.dumps(loc))


class ArtifactTests(unittest.TestCase):
    def cmp_dir(self, **kw):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            write_pair(d, **kw)
            rv, eng, _ = cmp.load_remote(d)
            return cmp.compare(rv, cmp.load_local(d), eng, "46", True, True)

    def test_clean_pair_equivalent(self):
        self.assertEqual(self.cmp_dir()["verdict"], "equivalent")

    def test_group_engine_disagreement_is_mismatch(self):
        r = self.cmp_dir(engines=("46", "46", "45"))
        self.assertEqual(r["verdict"], "engine_mismatch")
        self.assertFalse(r["equivalence_claimable"])

    def test_missing_engine_is_mismatch(self):
        self.assertEqual(self.cmp_dir(engines=("46", None, "46"))["verdict"], "engine_mismatch")

    def test_confirmed_non_crossing_reachable_from_artifacts(self):
        def both(d):
            d["ac14.gmdb"] = None
        r = self.cmp_dir(remote_mut=both, local_mut=both)
        self.assertEqual(r["verdict"], "equivalent")
        self.assertEqual(r["unreached_both"], ["gm14"])

    def test_local_absent_key_is_missing_not_non_crossing(self):
        def rm(d):
            d["ac14.gmdb"] = None
        def drop(d):
            del d["ac14.gmdb"]
        r = self.cmp_dir(remote_mut=rm, local_mut=drop)
        self.assertEqual(r["verdict"], "unresolved")


class RunnerErrorBridgeTests(unittest.TestCase):
    """klayout-tools#7770: a runner `error` result is a confirmed non-crossing
    only when the retained engine log pins it on that exact step and card."""

    def cmp_dir(self, logs=None, remote_mut=None, local_mut=None):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            write_pair(d, remote_mut=remote_mut, local_mut=local_mut, logs=logs)
            rv, eng, _ = cmp.load_remote(d)
            return cmp.compare(rv, cmp.load_local(d), eng, "46", True, True)

    def test_error_with_confirming_log_is_non_crossing(self):
        # leg 14 lives in the esr0 group ((14-1)//6 == 2)
        def rem(d):
            d["ac14.gmdb"] = ERR

        def loc(d):
            d["ac14.gmdb"] = None
        r = self.cmp_dir(logs={"esr0": confirming_log("ac14", "gmdb")},
                         remote_mut=rem, local_mut=loc)
        self.assertEqual(r["verdict"], "equivalent")
        self.assertEqual(r["unreached_both"], ["gm14"])

    def test_error_without_log_stays_missing(self):
        def rem(d):
            d["ac14.gmdb"] = ERR

        def loc(d):
            d["ac14.gmdb"] = None
        r = self.cmp_dir(remote_mut=rem, local_mut=loc)
        self.assertEqual(r["verdict"], "unresolved")
        self.assertIn("gm14", r["missing"])

    def test_error_with_log_naming_other_card_stays_missing(self):
        def rem(d):
            d["ac14.gmdb"] = ERR

        def loc(d):
            d["ac14.gmdb"] = None
        r = self.cmp_dir(logs={"esr0": confirming_log("ac14", "fc")},
                         remote_mut=rem, local_mut=loc)
        self.assertEqual(r["verdict"], "unresolved")

    def test_error_with_log_naming_other_step_stays_missing(self):
        def rem(d):
            d["ac14.gmdb"] = ERR

        def loc(d):
            d["ac14.gmdb"] = None
        r = self.cmp_dir(logs={"esr0": confirming_log("ac15", "gmdb")},
                         remote_mut=rem, local_mut=loc)
        self.assertEqual(r["verdict"], "unresolved")

    def test_error_without_out_of_interval_stays_missing(self):
        # vector warning + failed! echo present, but the meas error carries a
        # DIFFERENT reason (a solver/RHS failure, not a no-crossing)
        log = (
            "Error: measure  gmdb  find(AT) : no convergence\n"
            " meas ac gmdb find lgdb when lgph=-180 cross=1 failed!\n"
            "Warning from checkvalid: vector ac14__gmdb is not available "
            "or has zero length.\n"
        )

        def rem(d):
            d["ac14.gmdb"] = ERR

        def loc(d):
            d["ac14.gmdb"] = None
        r = self.cmp_dir(logs={"esr0": log}, remote_mut=rem, local_mut=loc)
        self.assertEqual(r["verdict"], "unresolved")

    def test_error_vseed_never_upgraded(self):
        log = (
            "Error: measure  vseed  find(AT) : out of interval\n"
            " meas op vseed find v(vout) failed!\n"
            "Warning from checkvalid: vector op7__vseed is not available "
            "or has zero length.\n"
        )

        def rem(d):
            d["op7.vseed"] = ERR
        r = self.cmp_dir(logs={"esr10m": log}, remote_mut=rem)
        self.assertEqual(r["verdict"], "unresolved")
        self.assertIn("vseed7", r["missing"])

    def test_two_legs_failing_same_card_stay_missing(self):
        # ac13 is a real no-crossing; ac14 fails the same card for another
        # reason. Un-namespaced evidence must not be attributed to ac14 (or
        # ac13): both stay missing and the verdict stays unresolved.
        log = (
            confirming_log("ac13", "gmdb")
            + "Error: RHS \"gmdb\" invalid\n"
            "Warning from checkvalid: vector ac14__gmdb is not available "
            "or has zero length.\n"
        )

        def rem(d):
            d["ac13.gmdb"] = ERR
            d["ac14.gmdb"] = ERR

        def loc(d):
            d["ac13.gmdb"] = None
            d["ac14.gmdb"] = None
        r = self.cmp_dir(logs={"esr0": log}, remote_mut=rem, local_mut=loc)
        self.assertEqual(r["verdict"], "unresolved")
        self.assertIn("gm14", r["missing"])
        self.assertNotIn("gm14", r["unreached_both"])

    def test_bridge_real_shape(self):
        # the exact lines from the issue-#757 fleet log (legs renamed)
        log = (
            "gmdb                =  -5.06785e+01\n"
            "ac10__gmdb = -5.06785e+01\n"
            "Error: measure  gmdb  find(AT) : out of interval\n"
            " meas ac gmdb find lgdb when lgph=-1.800000e+02 cross=1 failed!\n"
            "Warning from checkvalid: vector gmdb is not available "
            "or has zero length.\n"
            "Error: RHS \"gmdb\" invalid\n"
            "Warning from checkvalid: vector ac11__gmdb is not available "
            "or has zero length.\n"
            "gmdb                =  -7.35666e+01\n"
            "ac12__gmdb = -7.35666e+01\n"
        )

        def rem(d):
            d["ac11.gmdb"] = ERR

        def loc(d):
            d["ac11.gmdb"] = None
        # leg 11 lives in the esr500m group
        r = self.cmp_dir(logs={"esr500m": log}, remote_mut=rem, local_mut=loc)
        self.assertEqual(r["verdict"], "equivalent")
        self.assertEqual(r["unreached_both"], ["gm11"])


if __name__ == "__main__":
    unittest.main()
