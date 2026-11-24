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


def write_pair(d: Path, engines=("46", "46", "46"), remote_mut=None, local_mut=None):
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
            if v is None:
                ms.append({"name": k, "status": "not_reached", "value": None})
            else:
                ms.append({"name": k, "status": "ok", "value": v})
        (d / "remote" / g).mkdir(parents=True)
        (d / "remote" / g / "response.json").write_text(json.dumps(
            {"environment": {"engine_version": eng}, "corners": [{"measurements": ms}]}))
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


if __name__ == "__main__":
    unittest.main()
