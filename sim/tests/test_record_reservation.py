"""Record-ID reservation + exclusive publication (issue #310).

PDK-free: fake simulator/netlister calls, no PVT matrices, no ngspice/klt.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
BIN = SIM_DIR / "bin"
sys.path.insert(0, str(BIN))
import _record_common as rc  # noqa: E402


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, BIN / fname)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


corner_run = _load("corner_run", "corner-run.py")
mc_run = _load("mc_run", "mc-run.py")

# A worker: reserve, and only the winner "netlists" (writes a scratch marker).
WORKER = """
import sys, time
from pathlib import Path
sys.path.insert(0, {bin!r})
import _record_common as rc
build, exp, rid, tag = sys.argv[1:5]
try:
    rc.reserve_record_id(Path(build), exp, rid)
except RuntimeError:
    print("LOSE"); sys.exit(0)
(Path(build) / "scratch-" f"{{tag}}").write_text("work")
print("WIN")
"""


class ReservationTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.build = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _spawn(self, exp, rid, tag):
        return subprocess.Popen(
            [sys.executable, "-c", WORKER.format(bin=str(BIN)), str(self.build), exp, rid, tag],
            stdout=subprocess.PIPE, text=True,
        )

    def test_two_processes_same_id_exactly_one_winner(self):
        procs = [self._spawn("exp-a", "20260101-000000-abc", t) for t in ("p1", "p2")]
        outs = sorted(p.communicate()[0].strip() for p in procs)
        self.assertEqual(outs, ["LOSE", "WIN"])
        # loser did no work: exactly one scratch marker exists
        self.assertEqual(len(list(self.build.glob("scratch-*"))), 1)

    def test_distinct_ids_and_experiments_proceed(self):
        rc.reserve_record_id(self.build, "exp-a", "id1")
        rc.reserve_record_id(self.build, "exp-a", "id2")
        rc.reserve_record_id(self.build, "exp-b", "id1")

    def test_collision_leaves_owner_state_untouched(self):
        resv = rc.reserve_record_id(self.build, "e", "i")
        before = (resv / "owner.json").read_bytes()
        with self.assertRaises(RuntimeError):
            rc.reserve_record_id(self.build, "e", "i")
        self.assertEqual((resv / "owner.json").read_bytes(), before)

    def test_write_new_refuses_replacement(self):
        p = self.build / "rec.json"
        rc.write_new_text(p, "one")
        with self.assertRaises(FileExistsError):
            rc.write_new_text(p, "two")
        with self.assertRaises(FileExistsError):
            rc.copy_new(p, p)
        self.assertEqual(p.read_text(), "one")

    def test_interrupted_run_keeps_reservation_and_fresh_id_proceeds(self):
        rc.reserve_record_id(self.build, "e", "i")
        # simulated interruption: process died, nothing cleaned up
        with self.assertRaises(RuntimeError):
            rc.reserve_record_id(self.build, "e", "i")
        self.assertTrue((self.build / ".reservations" / "e" / "i").is_dir())
        # documented recovery: re-run mints a new id
        rc.reserve_record_id(self.build, "e", "i2")


class RunnerCollisionTests(unittest.TestCase):
    """main() fails on a held ID before netlisting; dry-run reserves nothing."""

    FIXED = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.build = self.root / "build"
        self.expdir = self.root / "myexp"
        self.expdir.mkdir()
        self.rid = "20260101-000000-abc1234"

    def tearDown(self):
        self._td.cleanup()

    def _fake_dt(self, mod):
        fake = mock.Mock(wraps=datetime)
        fake.now.return_value = self.FIXED
        return mock.patch.object(mod, "datetime", fake)

    def _corner_patches(self, netlist):
        exp = SimpleNamespace(dir=self.expdir, slug="myexp", schematic=self.expdir / "t.sch", raw={})
        pdk = SimpleNamespace(matches_pin=True, dir=self.root, installed_commit="x",
                              variant="v", root=self.root, lib_file=self.root)
        return [
            mock.patch.object(corner_run, "BUILD_DIR", self.build),
            mock.patch.object(corner_run, "load_pin", return_value={"open_pdks_commit": "x"}),
            mock.patch.object(corner_run, "resolve_pdk", return_value=pdk),
            mock.patch.object(corner_run, "load_experiment", return_value=exp),
            mock.patch.object(corner_run, "build_matrix", return_value=([object()], False)),
            mock.patch.object(corner_run, "git_state", return_value={"sha": "abc1234"}),
            mock.patch.object(corner_run, "netlist_with_xschem", netlist),
            self._fake_dt(corner_run),
        ]

    def test_corner_main_collision_fails_before_netlisting(self):
        rc.reserve_record_id(self.build, "myexp", self.rid)
        netlist = mock.Mock(side_effect=AssertionError("netlisted"))
        with contextlib_stack(self._corner_patches(netlist)):
            with self.assertRaises(corner_run.HarnessError) as cm:
                corner_run.main([str(self.expdir)])
        self.assertIn("already reserved", str(cm.exception))
        netlist.assert_not_called()
        self.assertFalse((self.build / "myexp").exists())
        self.assertEqual([p.name for p in self.expdir.iterdir()], [])

    def test_corner_dry_run_takes_no_reservation_and_writes_no_evidence(self):
        netlist = mock.Mock(side_effect=RuntimeError("stop after reservation point"))
        with contextlib_stack(self._corner_patches(netlist)):
            with self.assertRaises(RuntimeError):
                corner_run.main([str(self.expdir), "--dry-run"])
        self.assertFalse((self.build / ".reservations").exists())
        self.assertEqual([p.name for p in self.expdir.iterdir()], [])

    def test_mc_main_collision_fails_before_netlisting(self):
        exp = {"slug": "myexp", "_dir": self.expdir, "_schematic": self.expdir / "t.sch",
               "claim": "c", "monte_carlo_defaults": {"n": 2}}
        pdk = SimpleNamespace(matches_pin=True)
        rc.reserve_record_id(self.build, "myexp", self.rid)
        netlist = mock.Mock(side_effect=AssertionError("netlisted"))
        patches = [
            mock.patch.object(mc_run, "BUILD_DIR", self.build),
            mock.patch.object(mc_run.corner_run, "load_pin", return_value={}),
            mock.patch.object(mc_run.corner_run, "resolve_pdk", return_value=pdk),
            mock.patch.object(mc_run, "load_mc_experiment", return_value=exp),
            mock.patch.object(mc_run, "klt_binary", return_value="klt"),
            mock.patch.object(mc_run.corner_run, "git_state", return_value={"sha": "abc1234"}),
            mock.patch.object(mc_run.corner_run, "netlist_with_xschem", netlist),
            self._fake_dt(mc_run),
        ]
        with contextlib_stack(patches):
            with self.assertRaises(mc_run.HarnessError):
                mc_run.main([str(self.expdir), "--seed", "1"])
        netlist.assert_not_called()
        self.assertEqual([p.name for p in self.expdir.iterdir()], [])


class contextlib_stack:
    def __init__(self, cms):
        self.cms = cms

    def __enter__(self):
        for c in self.cms:
            c.__enter__()

    def __exit__(self, *a):
        for c in reversed(self.cms):
            c.__exit__(*a)
        return False


if __name__ == "__main__":
    unittest.main()
