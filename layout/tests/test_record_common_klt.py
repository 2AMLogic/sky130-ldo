"""Unit tests for the shared `run_klt_json` / `git` helpers (issue #273).

PDK-free: a stub executable stands in for `klt`.
"""

from __future__ import annotations

import importlib.util
import stat
import sys
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN_DIR))

from _record_common import git, run_klt_json  # noqa: E402


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RunKltJsonTest(unittest.TestCase):
    def _stub(self, body: str) -> str:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = Path(d.name) / "klt"
        p.write_text("#!/bin/sh\n" + body + "\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        return str(p)

    def test_success_parses_json_and_appends_format(self):
        klt = self._stub('echo "{\\"args\\": \\"$*\\"}"')
        self.assertEqual(run_klt_json(klt, "gen", "x"), {"args": "gen x --format json"})

    def test_nonzero_exit_raises_error_cls_with_stderr(self):
        klt = self._stub("echo boom >&2; exit 3")

        class MyErr(Exception):
            pass

        with self.assertRaises(MyErr) as cm:
            run_klt_json(klt, "gen", "res_array", error_cls=MyErr)
        self.assertEqual(str(cm.exception), "klt gen res_array failed: boom")

    def test_both_generators_fail_identically(self):
        klt = self._stub("echo boom >&2; exit 1")
        for fname in ("gen-folded-res-qual.py", "gen-ldo-blocks.py"):
            mod = _load("g_" + fname.replace("-", "_").replace(".", "_"), fname)
            with self.assertRaises(mod.GenError) as cm:
                mod.run_klt_json(klt, "gen", "r", error_cls=mod.GenError)
            self.assertEqual(str(cm.exception), "klt gen r failed: boom", fname)


class GitTest(unittest.TestCase):
    def test_git_strips_and_raises(self):
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(len(git(root, "rev-parse", "HEAD")), 40)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(Exception):
                git(Path(d), "rev-parse", "HEAD")


if __name__ == "__main__":
    unittest.main()
