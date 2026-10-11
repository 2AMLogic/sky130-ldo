"""Headless regression coverage for sim/loop-gain's 18-leg boundary grid (#338).

PDK-free: parses experiment.json and the testbench text only. Checks leg
enumeration, measurement-to-leg mapping, exact-zero ESR handling and that a
deck missing a required leg is detected (negative control).
"""

from __future__ import annotations

import copy
import itertools
import json
import re
import unittest
from pathlib import Path

LG = Path(__file__).resolve().parent.parent / "loop-gain"
EXP = json.loads((LG / "experiment.json").read_text())
SCH = (LG / "testbench" / "tb_loop_gain.sch").read_text()

COUTS = (0.33e-6, 4.7e-6)
ESRS = (0.0, 0.01, 0.5)
LOADS = {"50ma": 36.0, "1ma": 1800.0, "0ma": 1e12}
PM_MIN, GM_MIN = 45, 10
SEED_BAND = (1.62, 1.98)

SCALE = {"u": 1e-6, "m": 1e-3, "k": 1e3}


def num(tok: str) -> float:
    tok = tok.strip()
    if tok and tok[-1] in SCALE:
        return float(tok[:-1]) * SCALE[tok[-1]]
    return float(tok)


def replay_deck(analyses: list[str], initial: dict) -> list[dict]:
    """Replay `alter` statements; return the circuit state at each `ac`."""
    state = dict(initial)
    out = []
    for ln in analyses:
        m = re.match(r"alter\s+cout\s*=\s*(\S+)", ln)
        if m:
            state["cout_f"] = num(m.group(1))
        m = re.match(r"alter\s+hesr\s+gain\s*=\s*(\S+)", ln)
        if m:
            state["esr_ohm"] = num(m.group(1))
        m = re.match(r"alter\s+rload\s*=\s*(\S+)", ln)
        if m:
            state["rload"] = num(m.group(1))
        if re.match(r"alter\s+resr\b", ln):
            raise AssertionError("ESR must not be walked on a resistor (0 ohm is floored)")
        if re.match(r"ac\s", ln):
            out.append(dict(state))
    return out


def initial_state() -> dict:
    m = re.search(r"name=COUT m=1 value=([0-9.]+)u", SCH)
    h = re.search(r"name=HESR vnam=VESRSENSE value=([^\s}]+)", SCH)
    r = re.search(r"name=RLOAD value=(\S+) ", SCH)
    return {"cout_f": float(m.group(1)) * 1e-6, "esr_ohm": num(h.group(1)), "rload": num(r.group(1))}


def audit(exp: dict) -> list[str]:
    """Return a list of grid-coverage problems (empty == complete)."""
    problems = []
    states = replay_deck(exp["deck"]["analyses"], initial_state())
    seen = set()
    for st in states:
        load = next((k for k, v in LOADS.items() if v == st["rload"]), None)
        seen.add((round(st["cout_f"], 12), st["esr_ohm"], load))
    want = {(round(c, 12), e, l) for c, e, l in itertools.product(COUTS, ESRS, LOADS)}
    for miss in sorted(want - seen, key=str):
        problems.append(f"missing leg {miss}")
    if len(states) != len(seen):
        problems.append("duplicate leg in deck")
    meas = {m["name"]: m for m in exp["measurements"]}
    for leg in exp["ac_leg_grid"]["legs"]:
        i = leg["ac_index"]
        for key, expr, floor in (
            ("pm_measurement", f"180 + ac{i}.phc", PM_MIN),
            ("gm_measurement", f"-ac{i}.gmdb", GM_MIN),
        ):
            m = meas.get(leg[key])
            if m is None or m["expr"] != expr or m["min"] != floor:
                problems.append(f"leg {i}: {key} missing or mis-mapped")
        v = meas.get(leg["validity_measurement"])
        if v is None or v["expr"] != f"op{i}.vseed" or (v["min"], v["max"]) != SEED_BAND:
            problems.append(f"leg {i}: operating-point validity gate missing or unbounded")
    return problems


class TestLoopGainGrid(unittest.TestCase):
    def test_enumerates_all_18_legs(self):
        self.assertEqual(audit(EXP), [])
        self.assertEqual(len(replay_deck(EXP["deck"]["analyses"], initial_state())), 18)
        self.assertEqual(len(EXP["ac_leg_grid"]["legs"]), 18)

    def test_declared_grid_matches_deck_replay(self):
        states = replay_deck(EXP["deck"]["analyses"], initial_state())
        for leg in EXP["ac_leg_grid"]["legs"]:
            st = states[leg["ac_index"] - 1]
            self.assertAlmostEqual(st["cout_f"], leg["cout_f"], delta=1e-12)
            self.assertEqual(st["esr_ohm"], leg["esr_ohm"])
            self.assertEqual(st["rload"], LOADS[leg["load"]])

    def test_original_seven_identities_preserved(self):
        names = {m["name"]: m["expr"] for m in EXP["measurements"]}
        for name, expr in {
            "pm_c033_50ma_deg": "180 + ac1.phc",
            "gm_c033_0ma_db": "-ac3.gmdb",
            "pm_c47_0ma_deg": "180 + ac6.phc",
            "pm_c033_esr500m_50ma_deg": "180 + ac7.phc",
            "vout_seed_p7_v": "op7.vseed",
        }.items():
            self.assertEqual(names[name], expr)

    def test_exact_zero_esr(self):
        self.assertIn("alter hesr gain = 0", EXP["deck"]["analyses"])
        zero = [leg for leg in EXP["ac_leg_grid"]["legs"] if leg["esr_ohm"] == 0]
        self.assertEqual(len(zero), 6)
        # ESR is a CCVS, never a resistor floor, and no positive floor leaks in.
        self.assertNotIn("name=RESR", SCH)
        self.assertRegex(SCH, r"name=HESR vnam=VESRSENSE")
        self.assertRegex(SCH, r"name=VESRSENSE value=0\}")
        for ln in EXP["deck"]["analyses"]:
            m = re.match(r"alter\s+hesr\s+gain\s*=\s*(\S+)", ln)
            if m:
                self.assertIn(num(m.group(1)), ESRS)

    def test_negative_control_missing_leg_detected(self):
        exp = copy.deepcopy(EXP)
        an = exp["deck"]["analyses"]
        start = max(i for i, ln in enumerate(an) if ln.startswith("* --- leg 18"))
        exp["deck"]["analyses"] = an[:start]
        problems = audit(exp)
        self.assertTrue(any("missing leg" in p for p in problems), problems)

    def test_negative_control_unbounded_validity_gate_detected(self):
        exp = copy.deepcopy(EXP)
        for m in exp["measurements"]:
            if m["name"] == "vout_seed_p13_v":
                m["min"] = m["max"] = None
        self.assertTrue(any("leg 13" in p for p in audit(exp)))

    def test_negative_control_unmapped_measurement_detected(self):
        exp = copy.deepcopy(EXP)
        exp["measurements"] = [m for m in exp["measurements"] if m["name"] != "gm_c47_esr0_1ma_db"]
        self.assertTrue(any("gm_measurement" in p for p in audit(exp)))

    def test_coverage_disclosure_present(self):
        text = EXP["ac_leg_grid"]["coverage_disclosure"]
        for word in ("PVT", "continuous", "7 legs"):
            self.assertIn(word, text)


if __name__ == "__main__":
    unittest.main()
