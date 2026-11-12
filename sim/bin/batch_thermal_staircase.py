"""Translate the thermal-hysteresis staircase into `klt sim` requests (issue #511).

PDK-free, standard library only. `sim/thermal/run_hysteresis.py` walks a
temperature staircase of SEPARATE fixed-stimulus transients (ngspice has no
time-varying TEMP). Each point is one `tran 400n 170u uic` whose observations
are the comparator output sampled at fixed instants, so it fits a single-step
`klt sim` request:

* the stimulus (supply, disturbance current IX, EN dip) travels in the request
  netlist as `.param` cards -- the testbench already reads `vsup`, `ix_amp` and
  `en_dip`, exactly as `deck_text()` writes them for the local path;
* the process corner and temperature are klt corner axes (one process per
  request, a list of temperatures);
* the observations are `.meas tran ... find v(xldo.ts_cmp) at=<t>u` cards.
  Sampling is by interpolation (`find ... at`), where the local path uses the
  nearest saved sample; the 400 ns step keeps the two within a sample.

Issue #541 adds the dependent rounds (cold start, EN re-enable, disturbance
amplitude) after each corner's bracket is known; see `dependent_points()`.

Grading is local, from the raw card values. Adaptive bisection becomes ROUNDS:
`plan()` is a pure function of the recorded results, so a resumed run
reproduces the same next-round points.
"""

from __future__ import annotations

SCENARIOS = {  # name -> (disturbance amplitude A, want_lowest of the held predicate)
    "hot": (+0.5e-6, True),        # tripped state held?  -> T_reset
    "cold_exc": (-0.5e-6, False),  # untripped state held? -> T_trip
}
T_STOP_US, TSTEP = 170, "400n"
T_COLD, T_FORCED, T_HOLD, T_EN_LOW, T_REEN = 19, 39, 90, 108, 165
CARDS = {  # card name -> observation instant (us); the probe is the comparator output
    f"ts_cmp_{t}": t for t in (T_COLD, T_FORCED, T_HOLD)  # staircase / amplitude points (unchanged from #511)
}
CARDS_EXT = {f"ts_cmp_{t}": t for t in (T_COLD, T_FORCED, T_HOLD, T_EN_LOW, T_REEN)}  # cold / en points
IX_HOT = SCENARIOS["hot"][0]
AMPS_HOT, AMPS_COLD = (0.25e-6, 1.0e-6), (-0.25e-6, -1.0e-6)  # amplitude robustness (run_hysteresis.py [3])
PROBE = "v(xldo.ts_cmp)"
STEP_NAME = "tran1"
GRID = [130, 140, 150, 160, 170, 180, 190]
# Issue #231 operator ruling (option a): the ff deck does not converge at 190 C
# (timestep_too_small), so ff's bisection upper bound is lowered to the highest
# grid point at which it does (180 C).  A PDK-model extrapolation limit, not a
# spec change; other processes keep the full grid.
GRID_TOP_C = {"ff": 180}


def grid_for(proc: str, top_c: dict[str, float] | None = None) -> list[float]:
    """Coarse grid for `proc`, truncated at its lowered upper bound if any."""
    top = (GRID_TOP_C if top_c is None else top_c).get(proc)
    return [T for T in GRID if top is None or T <= top]


def request_netlist(body: list[str], supply_v: float, ix_amp: float, en_dip: str = "vsup") -> list[str]:
    """Request netlist: the same `.param`/`.option` header `deck_text()` emits,
    then the circuit body (the `.nodeset` card already dropped by the caller)."""
    return [
        f".param vsup={supply_v}",
        f".param ix_amp={ix_amp}",
        f".param en_dip={en_dip}",
        ".option wnflag=1",
        ".save all",
        *body,
    ]


def scenario_params(label: str) -> dict:
    """Stimulus of a point label: staircase `hot`/`cold_exc`, dependent `cold` / `en`,
    or an amplitude point `<hot|cold_exc>_ix<+-A>uA` (A in microamps, as the local run_id)."""
    if label in SCENARIOS:
        return {"base": label, "ix_amp": SCENARIOS[label][0], "en_dip": "vsup", "cards": CARDS}
    if label == "cold":  # EN rises from 0, no disturbance
        return {"base": "cold", "ix_amp": 0.0, "en_dip": "vsup", "cards": CARDS_EXT}
    if label == "en":  # `hot`, then EN dropped 101..115 us (DR-005 non-latching auto-restart)
        return {"base": "en", "ix_amp": IX_HOT, "en_dip": "0", "cards": CARDS_EXT}
    base, sep, amp = label.partition("_ix")
    if sep and base in SCENARIOS and amp.endswith("uA"):
        return {"base": base, "ix_amp": float(amp[:-2]) * 1e-6, "en_dip": "vsup", "cards": CARDS}
    raise ValueError(f"unknown point label {label!r}")


def amp_label(base: str, amp: float) -> str:
    return f"{base}_ix{amp * 1e6:+g}uA"


def dependent_points(reset: list[float], trip: list[float]) -> list[tuple[str, float]]:
    """(label, temperature) of the cold / en / amplitude points, a pure function of the
    recorded T_reset and T_trip brackets (run_hysteresis.py `[3]` and `[4]`), so a resumed
    run reproduces the same set."""
    reset_mid, trip_mid = sum(reset) / 2, sum(trip) / 2
    pts = sorted({round(x) for x in (reset_mid - 8, reset_mid - 1, reset_mid + 2, (reset_mid + trip_mid) / 2,
                                     trip_mid - 2, trip_mid + 1, trip_mid + 8)})
    out = [(lab, T) for lab in ("cold", "en") for T in pts]
    out += [(amp_label("hot", a), T) for a in AMPS_HOT for T in (reset[1], reset[0])]
    out += [(amp_label("cold_exc", a), T) for a in AMPS_COLD for T in (trip[0], trip[1])]
    return out


def step(cards: dict = CARDS) -> dict:
    return {
        "name": STEP_NAME,
        "analysis": {"kind": "tran", "args": f"{TSTEP} {T_STOP_US}u uic"},
        "measurements": [
            {"name": n, "spice": f".meas tran {n} find {PROBE} at={t}u", "unit": "V"} for n, t in cards.items()
        ],
    }


def build_request(netlist_path, process: str, temps: list[float], model: dict, spiceinit: list[str],
                  timeout_s: int, capacity_wait_s: int, cards: dict = CARDS) -> dict:
    return {
        "netlist": str(netlist_path),
        "engine": "ngspice",
        "models": model,
        "corners": {"process": [process], "temperature_c": list(temps)},
        "analysis_steps": [step(cards)],
        "options": {"timeout_s": timeout_s, "keep_artifacts": True, "ngspice_init": spiceinit},
        "batch": {"capacity_wait_s": capacity_wait_s},
    }


def tripped(v_cmp: float, supply_v: float) -> bool:
    return v_cmp < supply_v / 2  # same rule as _record_common.tripped


def held(scenario: str, forced_v: float, hold_v: float, supply_v: float) -> bool:
    """The monotone hold predicate of run_hysteresis.Runner (tripped_held /
    untripped_held), from the two raw observations."""
    f, h = tripped(forced_v, supply_v), tripped(hold_v, supply_v)
    return (f and h) if scenario == "hot" else ((not f) and (not h))


def extract_values(measurements: list[dict], cards: dict = CARDS) -> tuple[dict[str, float], list[str]]:
    """Raw card values (V) from a klt corner's `measurements`, plus the reasons
    the point cannot count (missing, duplicate, non-finite, unexpected)."""
    got: dict[str, float] = {}
    reasons: list[str] = []
    for m in measurements:
        name = str(m.get("name", "")).rsplit(".", 1)[-1]
        if name not in cards:
            reasons.append(f"unexpected measurement {m.get('name')!r}")
            continue
        v = m.get("value")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or abs(v) == float("inf"):
            reasons.append(f"card {name} has no finite value ({v!r})")
        elif name in got:
            reasons.append(f"duplicate card {name}")
        else:
            got[name] = float(v)
    reasons += [f"card {n} missing" for n in cards if n not in got and not any(n in r for r in reasons)]
    return got, reasons


def plan(results: dict[float, bool], scenario: str, tol: float, grid: list[float] = GRID) -> dict:
    """Next step of one (corner, scenario) search, a pure function of the
    recorded `results` (temperature -> held). Mirrors the local flow: a coarse
    grid, then bisection of the bracket the grid implies until `tol`.

    Returns {"pending": [T...]} (points still to run this round), or
    {"done": True, "bracket": [lo, hi]}, or {"error": why}.
    """
    want_lowest = SCENARIOS[scenario][1]
    missing = [T for T in grid if T not in results]
    if missing:
        return {"pending": missing}
    flags = [results[T] for T in grid]
    if want_lowest:  # F..F T..T : lowest True
        ok = [i for i in range(len(grid)) if not any(flags[: i + 1])]
        if not ok:
            return {"error": f"{scenario}: held already at the coldest grid point {grid[0]} C (bracket start)"}
        lo_i = ok[-1]
        hi = next((grid[i] for i in range(lo_i + 1, len(grid)) if flags[i]), None)
    else:  # T..T F..F : highest True
        ok = [i for i in range(len(grid)) if all(flags[: i + 1])]
        if not ok:
            return {"error": f"{scenario}: not held at the coldest grid point {grid[0]} C (bracket start)"}
        lo_i = ok[-1]
        hi = next((grid[i] for i in range(lo_i + 1, len(grid)) if not flags[i]), None)
    if hi is None:
        return {"error": f"{scenario}: predicate never flips above {grid[lo_i]} C within the grid"}
    lo = grid[lo_i]
    while hi - lo > tol:
        mid = round((lo + hi) / 2, 4)
        if mid not in results:
            return {"pending": [mid]}
        ok_mid = results[mid]
        if want_lowest:
            lo, hi = (lo, mid) if ok_mid else (mid, hi)
        else:
            lo, hi = (mid, hi) if ok_mid else (lo, mid)
    return {"done": True, "bracket": [lo, hi]}
