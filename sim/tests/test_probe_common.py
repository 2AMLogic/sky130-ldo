"""PDK-free tests for sim/bin/_probe_common.py (issue #353). No ngspice."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR / "bin"))
import _probe_common as pc  # noqa: E402

NET = "R1 a b 1k\nXM1 d g s b nfet\n+ W=1 L=1\n+ nf=1\nC1 a 0 1p\n"


class TestProbeCommon(unittest.TestCase):
    def test_load_corner_run(self):
        cr = pc.load_corner_run()
        self.assertTrue(hasattr(cr, "build_deck"))
        self.assertTrue(hasattr(cr, "detect_solver_diagnostic"))

    def test_sha(self):
        self.assertEqual(pc.sha(b"x"), hashlib.sha256(b"x").hexdigest())

    def test_logical_lines_str_and_list_agree(self):
        want = [(0, 1), (1, 4), (4, 5)]
        self.assertEqual(pc.logical_lines(NET), want)
        self.assertEqual(pc.logical_lines(NET.splitlines()), want)
        self.assertEqual(pc.logical_lines(""), [])

    def test_find_card(self):
        self.assertEqual(pc.find_card(NET, "XM1 "), (1, 4))
        with self.assertRaises(AssertionError):
            pc.find_card(NET, "ZZ")
        with self.assertRaises(AssertionError):
            pc.find_card(NET + "R1 x y 1\n", "R1 ")

    def test_run_ngspice_deck_mocked(self):
        fake = mock.Mock(stdout="out", stderr="err", returncode=3)
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(pc.subprocess, "run", return_value=fake) as run:
            log, elapsed, rc = pc.run_ngspice_deck(d, timeout=5)
            self.assertEqual((log, rc), ("out\nerr", 3))
            self.assertGreaterEqual(elapsed, 0)
            self.assertEqual((Path(d) / "ngspice.log").read_text(), "out\nerr")
            self.assertEqual(run.call_args.args[0], ["ngspice", "-b", "deck.spice"])
            self.assertEqual(run.call_args.kwargs["cwd"], Path(d))

    def test_git_provenance(self):
        with mock.patch.object(pc._record_common, "git", return_value="abc") as g:
            self.assertEqual(pc.git_provenance("/r"), "abc")
            g.assert_called_once_with(Path("/r"), "rev-parse", "HEAD")

    def test_load_results(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("b", "a"):
                p = Path(d) / "runs" / n
                p.mkdir(parents=True)
                (p / "result.json").write_text(json.dumps({"run_id": n}))
            self.assertEqual(list(pc.load_results(d)), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
