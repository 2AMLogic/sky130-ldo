"""PDK-free coverage for layout/bin/check-erc-supply-spec.py (issue #249).

Builds tiny in-memory klayout.db layouts so each of the checker's three
claims-about-the-layout is pinned by one passing case and one negative
control: stackup covers drawn routing, drawn-well narrative, and the
substrate well_boxes assertion. A final pair drives main() end to end to pin
the exit-code contract.

Needs the `klayout` module (present in the layout ERC venv, layout/.venv-erc).
CI's headless `checks` job installs no klayout wheel, so these tests skip with
an explicit reason there rather than failing.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import klayout.db as db
except ImportError:  # pragma: no cover - depends on the environment
    db = None

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "check-erc-supply-spec.py"
SKIP_REASON = (
    "klayout.db not importable; run under the layout ERC venv "
    "(layout/.venv-erc) to exercise check-erc-supply-spec.py"
)

NWELL = (64, 20)
DIFF = (65, 20)
TAP = (65, 44)
MET1 = (68, 20)
MET4 = (71, 20)

NARRATIVE = [
    "well_layer 64/20 (nwell) is DRAWN here: 2 shapes that merge into one",
    "100 um2 polygon spanning x 0.00..10.00 um.",
]


def _load():
    spec = importlib.util.spec_from_file_location("check_erc_supply_spec", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build(shapes):
    """shapes: {(layer, datatype): [(l, b, r, t) in um]} -> (layout, top)."""
    layout = db.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("ldo_core")
    for (layer, datatype), boxes in shapes.items():
        index = layout.layer(layer, datatype)
        for left, bottom, right, top_um in boxes:
            top.shapes(index).insert(
                db.DBox(left, bottom, right, top_um).to_itype(layout.dbu)
            )
    return layout, top


def _well_shapes():
    # Two overlapping boxes: 2 shapes -> 1 polygon, 100 um2, x 0..10, kept
    # clear of the substrate geometry below so the two checks coexist.
    return {NWELL: [(0, 20, 6, 30), (5, 20, 10, 30)]}


def _substrate_shapes():
    # Substrate-bodied geometry bbox is (0, 0, 14, 10) um.
    return {DIFF: [(0, 0, 10, 10)], TAP: [(12, 0, 14, 10)]}


def _well_spec(comment=NARRATIVE):
    return {"_comment": list(comment), "ties": [
        {"name": "nwell_tie", "well_layer": "64/20"}]}


def _substrate_spec(box):
    return {"ties": [{"name": "ptap", "well_boxes": [box]}]}


@unittest.skipUnless(db is not None, SKIP_REASON)
class CheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def quiet(self, fn, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args)

    # 1. stackup covers drawn routing
    def test_stackup_pass(self):
        layout, _ = _build({MET1: [(0, 0, 5, 1)]})
        spec = {"stackup": [{"layer": "68/20"}], "vias": []}
        self.assertEqual(
            self.mod.check_stackup_covers_drawn_routing(layout, spec), [])

    def test_stackup_negative_undeclared_met4(self):
        layout, _ = _build({MET1: [(0, 0, 5, 1)], MET4: [(0, 0, 5, 1)]})
        spec = {"stackup": [{"layer": "68/20"}], "vias": []}
        problems = self.mod.check_stackup_covers_drawn_routing(layout, spec)
        self.assertEqual(len(problems), 1)
        self.assertIn("71/20", problems[0])
        self.assertIn("met4", problems[0])

    # 2. drawn-well narrative
    def test_narrative_pass(self):
        layout, top = _build(_well_shapes())
        self.assertEqual(
            self.quiet(self.mod.check_drawn_well_narrative,
                       layout, top, _well_spec()), [])

    def test_narrative_negative_stale_figures(self):
        layout, top = _build(_well_shapes())
        stale = [NARRATIVE[0], "100 um2 polygon spanning x 0.00..12.00 um."]
        problems = self.quiet(self.mod.check_drawn_well_narrative,
                              layout, top, _well_spec(stale))
        self.assertEqual(len(problems), 1)
        self.assertIn("merged x-span", problems[0])

    def test_narrative_negative_missing_sentence(self):
        layout, top = _build(_well_shapes())
        problems = self.quiet(self.mod.check_drawn_well_narrative,
                              layout, top, _well_spec(["nothing here"]))
        self.assertEqual(len(problems), 1)
        self.assertIn("re-derivable", problems[0])

    # 3. substrate assertion
    def test_substrate_pass(self):
        layout, top = _build(_substrate_shapes())
        spec = _substrate_spec([-0.5, -0.5, 14.5, 10.5])
        self.assertEqual(
            self.quiet(self.mod.check_substrate_assertion, layout, top, spec),
            [])

    def test_substrate_negative_box_too_small(self):
        layout, top = _build(_substrate_shapes())
        spec = _substrate_spec([0.0, 0.0, 10.0, 10.0])  # misses the tap
        problems = self.quiet(self.mod.check_substrate_assertion,
                              layout, top, spec)
        self.assertEqual(len(problems), 1)
        self.assertIn("no longer covers", problems[0])

    def test_substrate_negative_box_too_loose(self):
        layout, top = _build(_substrate_shapes())
        spec = _substrate_spec([-10.0, -10.0, 30.0, 30.0])
        problems = self.quiet(self.mod.check_substrate_assertion,
                              layout, top, spec)
        self.assertEqual(len(problems), 1)
        self.assertIn("much larger", problems[0])

    # CLI verdict
    def _run_main(self, shapes, spec):
        layout, _ = _build(shapes)
        with tempfile.TemporaryDirectory() as tmp:
            gds = Path(tmp) / "t.gds"
            spec_path = Path(tmp) / "spec.json"
            layout.write(str(gds))
            spec_path.write_text(json.dumps(spec))
            argv = sys.argv
            sys.argv = ["check-erc-supply-spec.py", "--gds", str(gds),
                        "--spec", str(spec_path)]
            out, err = io.StringIO(), io.StringIO()
            try:
                with contextlib.redirect_stdout(out), \
                        contextlib.redirect_stderr(err):
                    code = self.mod.main()
            finally:
                sys.argv = argv
        return code, err.getvalue()

    def test_main_exit_zero_when_spec_matches(self):
        shapes = {**_well_shapes(), **_substrate_shapes(), MET1: [(0, 0, 5, 1)]}
        spec = {**_well_spec(), "stackup": [{"layer": "68/20"}], "vias": [],
                "ties": _well_spec()["ties"]
                + _substrate_spec([-0.5, -0.5, 14.5, 10.5])["ties"]}
        code, err = self._run_main(shapes, spec)
        self.assertEqual(code, 0, err)

    def test_main_exit_nonzero_on_problem(self):
        shapes = {**_well_shapes(), **_substrate_shapes(), MET4: [(0, 0, 5, 1)]}
        spec = {**_well_spec(), "stackup": [], "vias": [],
                "ties": _well_spec()["ties"]
                + _substrate_spec([-0.5, -0.5, 14.5, 10.5])["ties"]}
        code, err = self._run_main(shapes, spec)
        self.assertEqual(code, 1)
        self.assertIn("met4", err)


if __name__ == "__main__":
    unittest.main()
