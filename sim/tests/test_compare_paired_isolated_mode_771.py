"""Issue #771: the documented `python3 -I` reproduce commands for the four
paired comparators must work as written.

Since Python 3.11 `-I` implies `-P`, so the script's own directory is no
longer on sys.path and the comparators' sibling imports (_paired_compare,
_record_common, batch_loop_gain) fail with ModuleNotFoundError before any
comparison runs. Each test here invokes one comparator exactly the way its
diagnostic README documents it -- a subprocess with `-I` over a matching
pair laid out in a temporary directory -- and asserts exit 0.

These exercise the documented invocation only; they are not simulator
evidence.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_compare_loop_gain_paired_757 import write_pair as write_loop_gain_pair
from test_corner_run import SIM_DIR

BIN = SIM_DIR / "bin"


def _response(engine: str, measurements: list) -> str:
    return json.dumps(
        {
            "environment": {"engine_version": engine},
            "corners": [{"measurements": measurements}],
        }
    )


def write_dropout_pair(d: Path) -> None:
    vals = {"dropout_vin_x": 2.161658, "vout_at_max_vin_v": 1.798832}
    measurements = [{"name": f"dropout.{k}", "value": v} for k, v in vals.items()]
    measurements.append(
        {"name": "dropout.dropout_v", "value": vals["dropout_vin_x"] - 1.764}
    )
    (d / "remote" / "v3.30").mkdir(parents=True)
    (d / "remote" / "v3.30" / "response.json").write_text(
        _response("46", measurements)
    )
    (d / "local").mkdir()
    (d / "local" / "ngspice.log").write_text(
        "".join(f"{k} = {v:.10e}\n" for k, v in vals.items())
    )


def write_load_regulation_pair(d: Path) -> None:
    vals = {"vout_0ma": 1.802385, "vout_50ma": 1.798832}
    for t, (prefix, value) in enumerate(vals.items(), start=1):
        names = [prefix + s for s in ("", "_min", "_max")]
        (d / "remote" / f"tran{t}").mkdir(parents=True)
        (d / "remote" / f"tran{t}" / "response.json").write_text(
            _response("46", [{"name": f"tran{t}.{n}", "value": value} for n in names])
        )
    (d / "local").mkdir()
    (d / "local" / "ngspice.log").write_text(
        "".join(
            f"{prefix}{s} = {value:.10e}\n"
            for prefix, value in vals.items()
            for s in ("", "_min", "_max")
        )
    )


def write_line_regulation_pair(d: Path) -> None:
    vals = {
        f"vout_{ld}_{vin}{sfx}": v
        for ld, lo, hi in (("1ma", 1.8005, 1.80071), ("50ma", 1.79872, 1.79892))
        for vin, v in (("lo", lo), ("hi", hi))
        for sfx in ("", "_min", "_max")
    }
    names = list(vals)
    for t in range(1, 5):
        part = names[3 * (t - 1) : 3 * t]
        (d / "remote" / f"tran{t}").mkdir(parents=True)
        (d / "remote" / f"tran{t}" / "response.json").write_text(
            _response("46", [{"name": f"tran{t}.{n}", "value": vals[n]} for n in part])
        )
    slopes = {
        f"line_reg_{ld}_mv_per_v": abs(1000 * (hi - lo) / (3.63 - 2.97))
        for ld, lo, hi in (("1ma", 1.8005, 1.80071), ("50ma", 1.79872, 1.79892))
    }
    cards = ", ".join(f"{k}={v!r}" for k, v in {**vals, **slopes}.items())
    (d / "local").mkdir()
    (d / "local" / "corner-run.log").write_text(f"[ 1/1] tt_27c_3v30 FAIL {cards}\n")


def run_isolated(script: str, d: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", str(BIN / script), str(d), *args],
        capture_output=True,
        text=True,
    )


class IsolatedModeTests(unittest.TestCase):
    def check(self, script, writer, *args):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            writer(d)
            r = run_isolated(script, d, *args)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_dropout_paired(self):
        self.check(
            "compare_dropout_paired.py",
            write_dropout_pair,
            "--local-engine",
            "46",
            "--remote-pass",
            "FAIL",
            "--local-pass",
            "FAIL",
        )

    def test_load_regulation_paired(self):
        self.check(
            "compare_load_regulation_paired.py",
            write_load_regulation_pair,
            "--local-engine",
            "46",
            "--remote-pass",
            "FAIL",
            "--local-pass",
            "FAIL",
        )

    def test_line_regulation_paired(self):
        self.check(
            "compare_line_regulation_paired.py",
            write_line_regulation_pair,
            "--local-engine",
            "46",
            "--remote-pass",
            "FAIL",
        )

    def test_loop_gain_paired(self):
        self.check(
            "compare_loop_gain_paired.py",
            write_loop_gain_pair,
            "--local-engine",
            "46",
            "--remote-pass",
            "PASS",
            "--local-pass",
            "PASS",
        )


if __name__ == "__main__":
    unittest.main()
