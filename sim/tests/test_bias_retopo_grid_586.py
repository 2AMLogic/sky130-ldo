"""Golden-reference tests for the bias-generator PVT grid driver, folded onto the
shared batch-fleet campaign core (issue #586; core is #574).

The driver had no test at all before this file: it was the one campaign driver
#574's dedup pass missed, so the copy of the request builder and the
no-local-fallback submit path it carried was never exercised. The verification
that the fold changed nothing is the committed `requests/` tree of the record the
pre-fold driver minted, `sim/bias-retopo/20261029-bias-grid-467/requests/`: the
rebuilt request JSON and deck for every one of its six cases must come back
byte-identical.

Pure python: nothing is netlisted, nothing is submitted, no PDK is needed.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _sim_script_loader import load_script

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR / "bin"))
import _fleet_campaign as fc  # noqa: E402

bg = load_script(
    "bias_retopo_grid", SIM_DIR / "bin" / "bias-retopo-grid.py", register=True
)
GOLD = SIM_DIR / "bias-retopo" / "20261029-bias-grid-467" / "requests"
PDK = json.loads((SIM_DIR / "pdk.json").read_text())


class GoldenRequests(unittest.TestCase):
    """`20261029-bias-grid-467/requests/` is append-only evidence, so it is the
    golden reference: whatever the folded driver emits must equal it exactly."""

    def cases(self):
        gold = sorted(GOLD.glob("*.json"))
        self.assertEqual(len(gold), len(bg.DESIGNS) * len(bg.SUPPLIES))
        for g in gold:
            design, vtxt = g.stem.split("-v")
            yield g, design, float(vtxt)

    def test_request_json_is_rebuilt_byte_for_byte(self):
        for g, design, vsup in self.cases():
            with self.subTest(case=g.stem):
                want = g.read_text()
                # The committed request names the absolute deck path of the
                # worktree that minted it; feeding that same path back is what
                # makes the comparison byte-exact rather than path-normalised.
                net = Path(json.loads(want)["netlist"])
                self.assertEqual(net.name, f"{g.stem}.spice")
                got = json.dumps(bg.request(net, PDK), indent=2) + "\n"
                self.assertEqual(got, want)
                self.assertEqual(design in bg.DESIGNS, True)
                self.assertIn(vsup, bg.SUPPLIES)

    def test_deck_is_rebuilt_byte_for_byte(self):
        for g, design, vsup in self.cases():
            with self.subTest(case=g.stem):
                res, length = bg.DESIGNS[design]
                self.assertEqual(
                    bg.netlist(res, length, vsup),
                    g.with_suffix(".spice").read_text(),
                )

    def test_request_carries_the_skew_corners_in_this_benchs_order(self):
        g = GOLD / "dr013-v2.97.json"
        req = bg.request(Path(json.loads(g.read_text())["netlist"]), PDK)
        self.assertEqual(
            req["corners"]["process"], ["tt", "ss", "ff", "sf", "fs", "ll", "hh"]
        )
        self.assertEqual(req["corners"]["temperature_c"], [-40.0, 27.0, 125.0])

    def test_the_grid_is_fc_process_plus_the_resistor_skew_corners(self):
        """The ll/hh superset is deliberate (DR-013 moves R_BIAS), and it is the
        reason the shared core needed an `order=`: `fc.PROCESS.index('ll')` raises."""
        self.assertEqual(bg.PROCESS, [*fc.PROCESS, "ll", "hh"])
        self.assertEqual(set(bg.PROCESS), set(PDK["process_corners"]))


class Rows(unittest.TestCase):
    # All four of MEAS, in the order klt returns them, so the key order below is
    # the committed one and not an artefact of a short fixture.
    CORNER = {
        "process": "hh",
        "temperature_c": 125.0,
        "status": "pass",
        "measurements": [
            {"name": f"meas_{n}", "value": v}
            for (n, _e, _u), v in zip(bg.MEAS, [0.74, 2.08, 2.64, 3.13], strict=True)
        ],
    }

    def test_row_shape_matches_the_committed_summary_json(self):
        got = bg.row("dr013-v3.30", {"design": "dr013", "vsup": 3.30}, self.CORNER, "J7")
        self.assertEqual(
            got,
            {
                "design": "dr013",
                "vsup": 3.30,
                "process": "hh",
                "temp_c": 125.0,
                "status": "pass",
                "job_id": "J7",
                "v_nb": 0.74,
                "v_biasp": 2.08,
                "i_tail_ua": 2.64,
                "i_bias_pair_ua": 3.13,
            },
        )
        # Field ORDER is part of the committed format, and `key` is not in it.
        committed = json.loads((GOLD.parent / "summary.json").read_text())[0]
        self.assertEqual(list(got), list(committed))
        self.assertNotIn("key", got)

    def test_key_is_dropped_but_recoverable_from_the_row(self):
        meta = {"design": "dr013", "vsup": 3.30}
        key = "dr013-v3.30"
        got = bg.row(key, meta, self.CORNER, "J7")
        self.assertEqual(f"{got['design']}-v{got['vsup']:.2f}", key)
        self.assertIn("key", fc.corner_base(key, meta, self.CORNER, "J7"))


class RecordRendering(unittest.TestCase):
    """A failed submit is now reported and the campaign carries on (the shared
    core's host-rule branch) where the pre-fold driver `sys.exit`ed on the first
    refusal, abandoning requests already written to the record dir."""

    ROWS = [
        {
            "design": d,
            "vsup": 3.30,
            "process": "ll",
            "temp_c": 27.0,
            "status": "pass",
            "job_id": "J1",
            "i_bias_pair_ua": v,
            "i_tail_ua": v,
        }
        for d, v in (("record", 4.0), ("dr013", 4.2))
    ]

    def test_a_clean_run_renders_the_pre_fold_record_text(self):
        out = bg.render("20261029-bias-grid-467", self.ROWS, [])
        self.assertEqual(
            out.splitlines()[:4],
            [
                "# Bias-generator PVT grid: 20261029-bias-grid-467",
                "",
                "Issue #467 / DR-013. `record` = res_high_po L=1500; `dr013` = res_xhigh_po L=211.",
                "Executed through `klt sim --backend batch` (no local fallback). Bias generator + one M_TAIL copy only.",
            ],
        )
        self.assertIn("| ll | 27 | 3.30 | 4.0000 | 4.2000 | +5.00 |", out)
        self.assertIn("Worst |I_pair shift| = 5.00 %", out)
        self.assertNotIn("NOT ESTABLISHED", out)
        self.assertNotIn("Failed submits", out)

    def test_a_refused_submit_is_named_in_the_record(self):
        out = bg.render(
            "r", self.ROWS, [{"key": "dr013-v3.63", "error": "batch_no_capacity"}]
        )
        self.assertIn(
            "- NOT ESTABLISHED: `dr013-v3.63` submit failed: 'batch_no_capacity'", out
        )
        self.assertIn("Failed submits: 1", out)
        self.assertNotIn("local fallback) fell back", out)

    def test_a_missing_counterpart_is_counted_unusable_not_graded(self):
        out = bg.render("r", [self.ROWS[0]], [])
        self.assertIn("unusable points = 1", out)
        self.assertNotIn("| ll | 27 | 3.30 |", out)


class ReplayAgainstTheCommittedRecord(unittest.TestCase):
    """The whole driver, replayed offline against the record it minted.

    `run_klt_sim` is stubbed with responses synthesized from the committed
    `summary.json`, so nothing is submitted and no PDK is needed. This is the
    end-to-end counterpart of the per-request checks above: it also pins the row
    shaping (Blocker 2 of #586 -- `key` dropped) and the record rendering, both
    of which a request-only comparison cannot see.
    """

    def replay(self):
        committed = json.loads((GOLD.parent / "summary.json").read_text())
        names = [n for n, _e, _u in bg.MEAS]

        def stub(req_path, od, backend, pdk_root, klt_exe=None, require_corners=True):
            self.assertEqual(backend, "batch")  # host rule: never a local grid
            design, vtxt = Path(req_path).stem.split("-v")
            rows = [
                r
                for r in committed
                if r["design"] == design and r["vsup"] == float(vtxt)
            ]
            self.assertTrue(rows)
            return {
                "status": "pass",
                "corner_count": len(rows),
                "environment": {"remote": {"job_id": rows[0]["job_id"]}},
                "corners": [
                    {
                        "process": r["process"],
                        "temperature_c": r["temp_c"],
                        "status": r["status"],
                        "measurements": [
                            {"name": f"meas_{n}", "value": r[n]} for n in names
                        ],
                    }
                    for r in rows
                ],
            }, {}

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        argv = ["bias-retopo-grid.py", "--record-id", GOLD.parent.name]
        with (
            mock.patch.object(fc, "run_klt_sim", stub),
            mock.patch.object(bg, "REPO", Path(tmp.name)),
            mock.patch.object(sys, "argv", argv),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            rc = bg.main()
        self.assertEqual(rc, 0)
        return Path(tmp.name) / "sim" / "bias-retopo" / GOLD.parent.name

    def test_requests_summary_and_record_all_match(self):
        out = self.replay()

        gold = sorted(GOLD.glob("*"))
        self.assertEqual(len(gold), 12)  # 6 cases x (deck + request)
        for g in gold:
            with self.subTest(file=g.name):
                want, got = g.read_text(), (out / "requests" / g.name).read_text()
                if g.suffix == ".json":
                    # Only the deck path differs: it is absolute, so it names the
                    # record dir of whichever tree ran the driver.
                    want = want.replace(
                        json.loads(want)["netlist"], json.loads(got)["netlist"]
                    )
                self.assertEqual(got, want)

        self.assertEqual(
            (out / "summary.json").read_text(),
            (GOLD.parent / "summary.json").read_text(),
        )
        # The committed record.md has since gained an additive "Harness /
        # Reproduce" citation (#586); everything the driver renders precedes it.
        rendered = (GOLD.parent / "record.md").read_text()
        self.assertIn("\n## Harness / Reproduce\n", rendered)
        self.assertEqual(
            (out / "record.md").read_text(),
            rendered.split("\n\n## Harness / Reproduce")[0] + "\n",
        )

    def test_nothing_is_written_outside_the_new_record_dir(self):
        out = self.replay()
        self.assertEqual(
            sorted(p.name for p in out.iterdir()),
            ["record.md", "requests", "responses", "summary.json"],
        )
        self.assertEqual([p.name for p in out.parent.iterdir()], [GOLD.parent.name])


if __name__ == "__main__":
    unittest.main()
