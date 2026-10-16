"""Issue #360 -- response-level loop-gain margin extraction (pure python, no ngspice).

Input: frequency [Hz] and the complex loop gain T(f) (re, im) from a saved sweep.
Phase convention: arg(T) in degrees, unwrapped to be continuous in f, then shifted by a
multiple of 360 so the lowest-frequency sample lies in (-180, 180] (this is what ngspice
cph() does; the principal-value phase is also kept for comparison).  PM = 180 + phase at
unity gain; a "-180 crossing" is a sign change of (unwrapped phase + 180).

Nothing here converts a missing crossing into a number: a response with no -180 crossing
returns gm_db=None and a status that says whether the inspected range could have hidden
one (truncated) or not.  Statuses:

  finite              exactly one negative-real-axis crossing (Im(T) changes sign, Re<0; every
                      odd multiple of 180 deg, independent of unwrapping); gm from the FIRST
                      crossing (the repo's `cross=1` rule); worst_gm_db is the minimum over all
                      crossings.  The legacy `lgph=-180` view is kept as legacy_gm_db for comparison
  multiple_crossings  as finite, but >1 crossing (selection ambiguity disclosed)
  truncated_range     no crossing, and at the top of the sweep the loop gain is still >= 0 dB
                      or the phase would reach the axis within TRUNC_DECADES at its end slope:
                      a crossing just beyond the sweep cannot be excluded
  absent_in_range     no crossing, loop gain < 0 dB at the top of the sweep and the phase is
                      not heading to the axis soon: no crossing in the inspected range; the
                      scalar GM is undefined (NOT infinite, NOT a pass)
  starts_past_180     the lowest sample is already at/below -180 (no crossing to find)
  no_unity_crossing   |T| never crosses 0 dB (PM undefined as well)
"""
from __future__ import annotations

import math

TARGET_PM_DEG = 45.0
TARGET_GM_DB = 10.0
NOTCH_STEP_DEG = 60.0     # phase step between adjacent samples above which a crossing is 'notch-like'
TRUNC_DECADES = 2.0       # no crossing but the phase would reach the axis within this many decades at the end slope


def db(re: float, im: float) -> float:
    m = math.hypot(re, im)
    return -math.inf if m == 0 else 20.0 * math.log10(m)


def principal_phase(re, im):
    return [math.degrees(math.atan2(i, r)) for r, i in zip(re, im)]


def unwrap_deg(ph):
    """Continuous phase: remove 360 deg jumps; first sample is kept in (-180, 180]."""
    out = []
    for k, p in enumerate(ph):
        if k == 0:
            out.append(p)
            continue
        d = p - ph[k - 1]
        d -= 360.0 * round(d / 360.0)
        out.append(out[-1] + d)
    return out


def _interp_cross(f0, f1, y0, y1, level):
    """log-f linear interpolation of y at which y==level between two samples."""
    t = (level - y0) / (y1 - y0)
    return 10 ** (math.log10(f0) + t * (math.log10(f1) - math.log10(f0))), t


def crossings(freq, y, level, direction=None):
    """Indices/freqs where y crosses `level`. direction: -1 falling, +1 rising, None any."""
    out = []
    for k in range(len(y) - 1):
        a, b = y[k] - level, y[k + 1] - level
        if a == 0 and k > 0:
            continue  # exact touch already recorded as b == 0 of the previous interval
        if not ((a < 0 < b) or (a > 0 > b) or b == 0 or a == 0) or a == b:
            continue
        d = 1 if b > a else -1
        if direction is not None and d != direction:
            continue
        fx, t = _interp_cross(freq[k], freq[k + 1], y[k], y[k + 1], level)
        out.append((k, fx, t, d))
    return out


def analyze(freq, re, im):
    n = len(freq)
    assert n == len(re) == len(im) and n >= 3, "need >=3 samples"
    assert all(freq[k] < freq[k + 1] for k in range(n - 1)), "frequency must increase"
    gdb = [db(r, i) for r, i in zip(re, im)]
    pr = principal_phase(re, im)
    ph = unwrap_deg(pr)
    wraps = sum(1 for k in range(n - 1) if abs(pr[k + 1] - pr[k]) > 180.0)
    res = {
        "n_points": n, "f_min_hz": freq[0], "f_max_hz": freq[-1],
        "phase_convention": "arg(T) deg, continuous (unwrapped) in f, first sample in (-180,180]; "
                            "PM = 180 + phase at unity gain; GM = -|T|dB at the -180 crossing",
        "dc_gain_db": gdb[0], "dc_phase_deg": ph[0], "end_gain_db": gdb[-1], "end_phase_deg": ph[-1],
        "min_phase_deg": min(ph), "f_at_min_phase_hz": freq[ph.index(min(ph))],
        "max_gain_db": max(gdb), "principal_phase_wraps": wraps,
    }
    # unity-gain crossings (falling = the crossover; any further ones are disclosed)
    ug = crossings(freq, gdb, 0.0)
    res["unity_crossings"] = []
    for k, fx, t, d in ug:
        pk = ph[k] + t * (ph[k + 1] - ph[k]) if k + 1 < n else ph[k]
        res["unity_crossings"].append({"f_hz": fx, "direction": d, "phase_deg": pk, "pm_deg": 180.0 + pk})
    fall = [u for u in res["unity_crossings"] if u["direction"] < 0]
    res["pm_deg"] = fall[0]["pm_deg"] if fall else None
    res["crossover_hz"] = fall[0]["f_hz"] if fall else None
    # (1) LEGACY-equivalent: -180 crossings of the unwrapped phase only (what `when lgph=-180`
    #     sees; blind to +180, -540, ... and dependent on the unwrap branch).
    pc = crossings(freq, ph, -180.0)
    res["legacy_phase_crossings"] = []
    for k, fx, t, d in pc:
        gk = gdb[k] + t * (gdb[k + 1] - gdb[k]) if k + 1 < n else gdb[k]
        res["legacy_phase_crossings"].append({"f_hz": fx, "direction": d, "gain_db": gk, "gm_db": -gk})
    res["legacy_gm_db"] = res["legacy_phase_crossings"][0]["gm_db"] if res["legacy_phase_crossings"] else None
    # (2) wrap-independent: T on the NEGATIVE REAL AXIS = Im(T) changes sign while Re(T) < 0.
    #     Covers every odd multiple of 180 deg.  |T| there is -Re(T), so GM = -20log10(-Re).
    ac = []
    for k in range(n - 1):
        a_, b_ = im[k], im[k + 1]
        if a_ == 0 and k > 0:
            continue
        if not ((a_ < 0 < b_) or (a_ > 0 > b_) or b_ == 0 or a_ == 0) or a_ == b_:
            continue
        t = (0.0 - a_) / (b_ - a_)
        rx = re[k] + t * (re[k + 1] - re[k])  # linear in (Re, Im) between samples
        if rx >= 0:
            continue  # positive real axis (phase 0 mod 360): not a gain-margin point
        fx = 10 ** (math.log10(freq[k]) + t * (math.log10(freq[k + 1]) - math.log10(freq[k])))
        step = max(abs(pr[j + 1] - pr[j] - 360.0 * round((pr[j + 1] - pr[j]) / 360.0))
                   for j in range(max(0, k - 1), min(n - 1, k + 2)))
        ac.append({"f_hz": fx, "direction": 1 if b_ > a_ else -1, "gain_db": db(rx, 0.0), "gm_db": -db(rx, 0.0),
                   "max_adjacent_phase_step_deg": step,
                   "notch_like": step > NOTCH_STEP_DEG,
                   "min_gain_db_within_2_samples": min(gdb[max(0, k - 2):k + 4])})
    res["negative_axis_crossings"] = ac
    res["gm_db"] = ac[0]["gm_db"] if ac else None  # first crossing = the repo's cross=1 rule
    res["gm_crossing_hz"] = ac[0]["f_hz"] if ac else None
    res["worst_gm_db"] = min(c["gm_db"] for c in ac) if ac else None
    res["legacy_agrees"] = (res["legacy_gm_db"] is None) == (res["gm_db"] is None) and (
        res["legacy_gm_db"] is None or abs(res["legacy_gm_db"] - res["gm_db"]) < 0.5)
    res["any_notch_like_crossing"] = any(c["notch_like"] for c in ac)
    # sufficient bound independent of phase: any negative-axis crossing ABOVE crossover has
    # |T| <= max post-crossover gain, so GM >= -max_post_fc_gain_db (valid lower bound only).
    if fall:
        post = [g for f_, g in zip(freq, gdb) if f_ > fall[-1]["f_hz"]]
        res["max_gain_above_crossover_db"] = max(post) if post else None
        res["gm_lower_bound_above_crossover_db"] = -max(post) if post else None
    # status
    if not fall:
        status = "no_unity_crossing"
    elif ph[0] <= -180.0:
        status = "starts_past_180"
    elif ac:
        status = "multiple_crossings" if len(ac) > 1 else "finite"
    else:
        j = max(0, min(range(n), key=lambda q: abs(math.log10(freq[q]) - (math.log10(freq[-1]) - 1.0))))
        slope = (ph[-1] - ph[j]) / max(1e-12, math.log10(freq[-1]) - math.log10(freq[j]))
        res["end_phase_slope_deg_per_dec"] = slope
        # heuristic distance (decades) to the nearest odd multiple of 180 deg ahead at that slope
        if slope != 0:
            tgt = 180.0 * (math.floor((ph[-1] - 180.0) / 360.0) * 2 + 1) if slope < 0 else \
                  180.0 * (math.ceil((ph[-1] - 180.0) / 360.0) * 2 + 1)
            if abs(ph[-1] - tgt) < 1e-9:
                tgt += -360.0 if slope < 0 else 360.0
            res["extrapolated_decades_to_axis"] = abs(ph[-1] - tgt) / abs(slope)
        else:
            res["extrapolated_decades_to_axis"] = math.inf
        if gdb[-1] >= 0.0 or res["extrapolated_decades_to_axis"] < TRUNC_DECADES:
            status = "truncated_range"
        else:
            status = "absent_in_range"
    res["status"] = status
    res["gm_supported"] = status in ("finite", "multiple_crossings")
    if res["gm_supported"] and res["pm_deg"] is not None:
        res["pm_ge_45"] = res["pm_deg"] >= TARGET_PM_DEG
        res["gm_ge_10"] = res["worst_gm_db"] >= TARGET_GM_DB
    return res


def read_wrdata(text: str):
    """Parse ngspice `wrdata` of one complex vector over ac: rows 'f 0 re im' or 'f re im'
    (ngspice writes freq, then re, im per vector; some builds repeat a zero imaginary
    column for the scale)."""
    freq, re, im = [], [], []
    for ln in text.splitlines():
        p = ln.split()
        if not p or p[0].startswith(("*", "#")):
            continue
        try:
            v = [float(x) for x in p]
        except ValueError:
            if freq:
                raise
            continue  # wr_vecnames header line before the first data row
        if len(v) == 4:
            f, _z, r, i = v
        elif len(v) == 3:
            f, r, i = v
        else:
            raise ValueError(f"unexpected wrdata row: {ln!r}")
        freq.append(f); re.append(r); im.append(i)
    return freq, re, im
