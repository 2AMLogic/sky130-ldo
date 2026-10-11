"""Issue #377: line/load regulation endpoints grade the settled tail's sampled
extrema, not only its average.

Before #377 each endpoint was graded on `meas tran ... avg v(vout)
from=199m to=200m` alone, so a tail alternating equally between 1.7 V and
1.9 V averages 1.8 V, passes the Output-window gate and gives a zero
delta/slope. These tests exercise the ACTUAL manifests through the
production path (build_deck -> ngspice stdout -> parse_measurements ->
grade_bounds inside run_corner):

- the analysis cards: every endpoint's avg card has `min`/`max` siblings over
  the identical window, after the same `tran` (so in the same `tranN` plot),
  and each graded expression names that plot;
- grading through run_corner with a stubbed ngspice: equal valid means with an
  out-of-window minimum or maximum FAIL, flat valid tails PASS, exact window
  edges PASS, missing/non-finite extrema FAIL;
- a PDK-free toy deck (skipped when ngspice is not on PATH) that runs the
  production deck's own analysis cards through real ngspice, proving the plot
  association and the min/max card syntax end to end;
- the batch backend admits both manifests only at their pinned endpoint-adapter
  shape (#379 line, #381 load), and still refuses the sibling regulation benches.

The extrema are SAMPLED over the simulator's own timepoints in the window: they
bound the measured tail, not continuous-time behaviour between samples.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from test_corner_run import SIM_DIR, corner_run

WINDOW = "from=199m to=200m"
OUT_MIN, OUT_MAX = 1.764, 1.836

# slug -> endpoint card name -> (tran plot index, graded avg / min / max measurement names)
ENDPOINTS = {
    "load-regulation": {
        "vout_0ma": (1, "vout_0ma_v", "vout_0ma_min_v", "vout_0ma_max_v"),
        "vout_50ma": (2, "vout_50ma_v", "vout_50ma_min_v", "vout_50ma_max_v"),
    },
    "line-regulation": {
        "vout_1ma_lo": (1, "vout_1ma_lo", "vout_1ma_lo_min", "vout_1ma_lo_max"),
        "vout_1ma_hi": (2, "vout_1ma_hi", "vout_1ma_hi_min", "vout_1ma_hi_max"),
        "vout_50ma_lo": (3, "vout_50ma_lo", "vout_50ma_lo_min", "vout_50ma_lo_max"),
        "vout_50ma_hi": (4, "vout_50ma_hi", "vout_50ma_hi_min", "vout_50ma_hi_max"),
    },
}
# The pre-#377 average/delta/slope measurements, pinned so the change stays additive.
UNCHANGED = {
    "load-regulation": {
        "load_reg_v": ("abs(tran2.vout_50ma - tran1.vout_0ma)", None, 0.018, False),
        "load_reg_pct": ("100*abs(tran2.vout_50ma - tran1.vout_0ma)/1.8", None, 1, False),
        "vout_0ma_v": ("tran1.vout_0ma", OUT_MIN, OUT_MAX, True),
        "vout_50ma_v": ("tran2.vout_50ma", OUT_MIN, OUT_MAX, True),
    },
    "line-regulation": {
        "line_reg_1ma_mv_per_v": ("abs(1000*(tran2.vout_1ma_hi - tran1.vout_1ma_lo)/(3.63-2.97))", None, 5, False),
        "line_reg_50ma_mv_per_v": ("abs(1000*(tran4.vout_50ma_hi - tran3.vout_50ma_lo)/(3.63-2.97))", None, 5, False),
        "vout_1ma_lo": ("tran1.vout_1ma_lo", OUT_MIN, OUT_MAX, True),
        "vout_1ma_hi": ("tran2.vout_1ma_hi", OUT_MIN, OUT_MAX, True),
        "vout_50ma_lo": ("tran3.vout_50ma_lo", OUT_MIN, OUT_MAX, True),
        "vout_50ma_hi": ("tran4.vout_50ma_hi", OUT_MIN, OUT_MAX, True),
    },
}

MEAS_CARD = re.compile(r"^meas tran (\w+) (avg|min|max) v\(vout\) (from=\S+ to=\S+)$")


def analyses(slug: str) -> list[str]:
    raw = json.loads((SIM_DIR / slug / "experiment.json").read_text())
    return raw["deck"]["analyses"]


def meas_cards(slug: str) -> dict[str, tuple[int, str, str]]:
    """card name -> (tran plot index it lands in, statistic, window)."""
    out, plot = {}, 0
    for ln in analyses(slug):
        s = ln.strip()
        if s.startswith("tran "):
            plot += 1
            continue
        m = MEAS_CARD.match(s)
        if m:
            out[m.group(1)] = (plot, m.group(2), m.group(3))
    return out


def card_values(slug: str, avg: float, lo: float, hi: float) -> dict[str, float]:
    """Every endpoint card of `slug` reads (avg, min=lo, max=hi)."""
    vals = {}
    for card in ENDPOINTS[slug]:
        vals[card] = avg
        vals[card + "_min"] = lo
        vals[card + "_max"] = hi
    return vals


def ngspice_stdout(exp, cards: dict, drop=(), override=None) -> str:
    """What the production deck's trailing `print meas_<name>` lines would show
    for the given card values: each graded expr is evaluated over `tranN`
    plots exactly as ngspice's `let` does. `drop` omits a measurement (ngspice
    printed nothing usable); `override` replaces a printed token verbatim."""
    plots: dict[int, dict] = {}
    for name, (plot, _stat, _win) in meas_cards(exp.slug).items():
        plots.setdefault(plot, {})[name] = cards[name]
    env = {"abs": abs, **{f"tran{k}": SimpleNamespace(**v) for k, v in plots.items()}}
    lines = []
    for m in exp.measurements:
        if m.name in drop:
            continue
        token = (override or {}).get(m.name)
        if token is None:
            token = f"{eval(m.expr, {'__builtins__': {}}, env):.9e}"
        lines.append(f"meas_{m.name} = {token}")
    return "\n".join(lines) + "\n"


def run_production(slug: str, stdout: str) -> dict:
    """run_corner() on the ACTUAL manifest with ngspice stubbed to `stdout`."""
    exp = corner_run.load_experiment(SIM_DIR / slug)
    pdk = mock.Mock(lib_file="/nonexistent/sky130.lib.spice")
    corner = corner_run.Corner("tt", 27.0, 3.3)
    proc = subprocess.CompletedProcess(args=["ngspice", "-b"], returncode=0, stdout=stdout, stderr="")
    with tempfile.TemporaryDirectory() as td, \
            mock.patch.object(corner_run.subprocess, "run", return_value=proc), \
            mock.patch("sys.stderr"):
        return corner_run.run_corner(exp, pdk, corner, ["* body"], Path(td), None, 60)


def by_name(result: dict) -> dict[str, dict]:
    return {c["name"]: c for c in result["measurements"]}


class TestManifestCards(unittest.TestCase):
    def test_every_endpoint_measures_min_and_max_over_its_average_window(self):
        for slug, eps in ENDPOINTS.items():
            cards = meas_cards(slug)
            self.assertEqual(len(cards), 3 * len(eps), slug)
            for card, (plot, *_names) in eps.items():
                self.assertEqual(cards[card], (plot, "avg", WINDOW), (slug, card))
                self.assertEqual(cards[card + "_min"], (plot, "min", WINDOW), (slug, card))
                self.assertEqual(cards[card + "_max"], (plot, "max", WINDOW), (slug, card))

    def test_extrema_are_graded_against_the_output_window_from_their_own_plot(self):
        for slug, eps in ENDPOINTS.items():
            ms = {m.name: m for m in corner_run.load_experiment(SIM_DIR / slug).measurements}
            for card, (plot, _avg, mn, mx) in eps.items():
                self.assertEqual(ms[mn].expr, f"tran{plot}.{card}_min")
                self.assertEqual((ms[mn].min, ms[mn].max, ms[mn].min_inclusive), (OUT_MIN, None, True))
                self.assertEqual(ms[mx].expr, f"tran{plot}.{card}_max")
                self.assertEqual((ms[mx].min, ms[mx].max, ms[mx].max_inclusive), (None, OUT_MAX, True))
                self.assertEqual(ms[mn].unit, "V")
                self.assertEqual(ms[mx].unit, "V")

    def test_averages_deltas_and_slopes_unchanged(self):
        for slug, pinned in UNCHANGED.items():
            ms = {m.name: m for m in corner_run.load_experiment(SIM_DIR / slug).measurements}
            for name, (expr, lo, hi, hi_incl) in pinned.items():
                m = ms[name]
                self.assertEqual((m.expr, m.min, m.max, m.max_inclusive), (expr, lo, hi, hi_incl), name)
            self.assertEqual(len(ms), len(pinned) + 2 * len(ENDPOINTS[slug]), slug)
            trans = [ln for ln in analyses(slug) if ln.startswith("tran ")]
            self.assertEqual(trans, ["tran 10u 200m uic"] * len(ENDPOINTS[slug]), slug)

    def test_production_deck_carries_cards_before_the_lets(self):
        for slug in ENDPOINTS:
            exp = corner_run.load_experiment(SIM_DIR / slug)
            deck = corner_run.build_deck(exp, mock.Mock(lib_file="/x/l"), corner_run.Corner("tt", 27, 3.3), ["* b"])
            lines = deck.splitlines()
            for card in ENDPOINTS[slug]:
                for stat, suffix in (("min", "_min"), ("max", "_max")):
                    self.assertIn(f"meas tran {card}{suffix} {stat} v(vout) {WINDOW}", lines)
            first_let = next(i for i, ln in enumerate(lines) if ln.startswith("let meas_"))
            last_meas = max(i for i, ln in enumerate(lines) if ln.startswith("meas tran "))
            self.assertLess(last_meas, first_let, slug)

    def test_batch_backend_admits_line_and_load_regulation_strictly(self):
        # issue #379 admits sim/line-regulation and issue #381 admits
        # sim/load-regulation, each only at its pinned endpoint-adapter shape
        # (see test_batch_line_regulation_379.py / test_batch_load_regulation_381.py);
        # the sibling regulation benches stay local-only.
        for slug in ENDPOINTS:
            self.assertTrue(corner_run.BATCH_ALLOWLIST[slug].get("endpoint_adapter"), slug)
            corner_run.check_batch_supported(corner_run.load_experiment(SIM_DIR / slug))
        for slug in ("iq", "psrr-dc", "startup"):
            exp = corner_run.load_experiment(SIM_DIR / slug)
            with self.assertRaises(corner_run.HarnessError) as cm:
                corner_run.check_batch_supported(exp)
            self.assertIn("does not support experiment", str(cm.exception))


class TestProductionGrading(unittest.TestCase):
    """run_corner + parse_measurements + grade_bounds on the real manifests."""

    def grade(self, slug, avg, lo, hi, **kw):
        exp = corner_run.load_experiment(SIM_DIR / slug)
        return run_production(slug, ngspice_stdout(exp, card_values(slug, avg, lo, hi), **kw))

    def test_issue_counterexample_equal_valid_means_fail_on_extrema(self):
        for slug, eps in ENDPOINTS.items():
            res = self.grade(slug, 1.8, 1.7, 1.9)
            checks = by_name(res)
            self.assertFalse(res["pass"], slug)
            for name, (_e, *_rest) in UNCHANGED[slug].items():
                self.assertTrue(checks[name]["pass"], (slug, name))  # the old hole, still open on its own
            for _card, (_p, _avg, mn, mx) in eps.items():
                self.assertFalse(checks[mn]["pass"], (slug, mn))
                self.assertFalse(checks[mx]["pass"], (slug, mx))
                self.assertEqual(checks[mn]["reason"], f"below min {OUT_MIN:g}")
                self.assertEqual(checks[mx]["reason"], f"above max {OUT_MAX:g}")

    def test_only_minimum_or_only_maximum_out_of_window_fails(self):
        for slug, eps in ENDPOINTS.items():
            for lo, hi, bad in ((1.7639, 1.80, "min"), (1.80, 1.8361, "max")):
                res = self.grade(slug, 1.8, lo, hi)
                checks = by_name(res)
                self.assertFalse(res["pass"], (slug, bad))
                for _card, (_p, _avg, mn, mx) in eps.items():
                    self.assertEqual(checks[mn]["pass"], bad != "min", (slug, mn))
                    self.assertEqual(checks[mx]["pass"], bad != "max", (slug, mx))

    def test_single_endpoint_excursion_fails_the_corner(self):
        for slug, eps in ENDPOINTS.items():
            last = list(eps)[-1]
            exp = corner_run.load_experiment(SIM_DIR / slug)
            cards = card_values(slug, 1.8, 1.8, 1.8)
            cards[last + "_max"] = 1.9
            res = run_production(slug, ngspice_stdout(exp, cards))
            failing = [c["name"] for c in res["measurements"] if not c["pass"]]
            self.assertEqual(failing, [eps[last][3]], slug)
            self.assertFalse(res["pass"])

    def test_flat_valid_tail_passes(self):
        for slug in ENDPOINTS:
            res = self.grade(slug, 1.8, 1.8, 1.8)
            self.assertTrue(res["pass"], [c for c in res["measurements"] if not c["pass"]])

    def test_exact_output_window_edges_pass(self):
        for slug, eps in ENDPOINTS.items():
            res = self.grade(slug, 1.8, OUT_MIN, OUT_MAX)
            checks = by_name(res)
            for _card, (_p, _avg, mn, mx) in eps.items():
                self.assertEqual(checks[mn]["value"], OUT_MIN)
                self.assertEqual(checks[mx]["value"], OUT_MAX)
                self.assertTrue(checks[mn]["pass"] and checks[mx]["pass"], (slug, mn, mx))
            self.assertTrue(res["pass"], slug)

    def test_missing_extremum_fails(self):
        for slug, eps in ENDPOINTS.items():
            for _card, (_p, _avg, mn, mx) in eps.items():
                for gone in (mn, mx):
                    res = self.grade(slug, 1.8, 1.8, 1.8, drop=(gone,))
                    c = by_name(res)[gone]
                    self.assertIsNone(c["value"])
                    self.assertFalse(c["pass"])
                    self.assertEqual(c["reason"], "measurement not found in ngspice output")
                    self.assertFalse(res["pass"], (slug, gone))

    def test_nonfinite_extremum_fails(self):
        for slug, eps in ENDPOINTS.items():
            _p, _avg, mn, mx = next(iter(eps.values()))
            for name in (mn, mx):
                for token in ("nan", "inf", "-inf", "NaN"):
                    res = self.grade(slug, 1.8, 1.8, 1.8, override={name: token})
                    self.assertFalse(by_name(res)[name]["pass"], (slug, name, token))
                    self.assertFalse(res["pass"])
                for bad in (float("nan"), float("inf"), float("-inf"), None):
                    m = next(m for m in corner_run.load_experiment(SIM_DIR / slug).measurements if m.name == name)
                    self.assertFalse(corner_run.grade_bounds(m, bad)[0], (name, bad))


TOY_LIB = ".lib tt\n.endl tt\n"


def toy_body(base: float, amp: float) -> list[str]:
    """A PDK-free stand-in for the testbench netlist: the same source names the
    manifests `alter` (VVIN, VEN's pwl, ILOAD), and a VOUT that is `base` plus a
    1 kHz sine of amplitude `amp` -- so every 199-200 ms window holds exactly
    one period, its average is `base` and its sampled extrema are base +- amp."""
    return [
        "VVIN vin 0 3.3",
        "VEN en 0 pwl(0 0 100u 0 101u 3.3 10 3.3)",
        "ILOAD 0 nl 1m",
        "RNL nl 0 1",
        "REN en 0 1meg",
        "RVIN vin 0 1meg",
        f"BOUT vout 0 V = {base} + {amp}*sin(6.283185307179586e3*time)",
        "RL vout 0 1k",
    ]


@unittest.skipUnless(shutil.which("ngspice"), "ngspice not on PATH")
class TestRealNgspiceToyDeck(unittest.TestCase):
    """The production deck's own analysis cards, run by real ngspice against a
    PDK-free toy netlist (seconds, no PDK, not evidence of anything about the
    LDO): proves the min/max card syntax and the `tranN.` plot association."""

    def run_toy(self, slug: str, base: float, amp: float) -> dict:
        exp = corner_run.load_experiment(SIM_DIR / slug)
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            lib = run_dir / "toy.lib"
            lib.write_text(TOY_LIB)
            shutil.copyfile(corner_run.SPICEINIT_FILE, run_dir / ".spiceinit")
            with mock.patch("sys.stderr"):
                return corner_run.run_corner(
                    exp, mock.Mock(lib_file=lib), corner_run.Corner("tt", 27.0, 3.3),
                    toy_body(base, amp), run_dir, None, 120,
                )

    def test_rippled_tail_with_valid_mean_fails_only_on_extrema(self):
        for slug, eps in ENDPOINTS.items():
            res = self.run_toy(slug, 1.8, 0.1)
            self.assertEqual(res["ngspice_exit"], 0, slug)
            checks = by_name(res)
            self.assertFalse(res["pass"], slug)
            for name in UNCHANGED[slug]:
                self.assertTrue(checks[name]["pass"], (slug, name, checks[name]))
            for _card, (_p, avg, mn, mx) in eps.items():
                self.assertAlmostEqual(checks[avg]["value"], 1.8, places=4)
                self.assertAlmostEqual(checks[mn]["value"], 1.7, places=2)
                self.assertAlmostEqual(checks[mx]["value"], 1.9, places=2)
                self.assertFalse(checks[mn]["pass"] or checks[mx]["pass"], (slug, mn, mx))

    def test_flat_tail_passes_and_extrema_come_from_each_plot(self):
        for slug, eps in ENDPOINTS.items():
            res = self.run_toy(slug, 1.8, 0.0)
            self.assertTrue(res["pass"], (slug, [c for c in res["measurements"] if not c["pass"]]))
            checks = by_name(res)
            for _card, (_p, avg, mn, mx) in eps.items():
                for n in (avg, mn, mx):
                    self.assertTrue(math.isclose(checks[n]["value"], 1.8, abs_tol=1e-9), (slug, n))


if __name__ == "__main__":
    unittest.main()
