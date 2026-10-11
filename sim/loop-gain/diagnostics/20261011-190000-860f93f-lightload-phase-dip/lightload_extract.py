"""Issue #365 -- response-level light-load phase-dip characterisation (pure python, no ngspice).

Input: frequency [Hz] and complex T(f) (loop gain) from a saved sweep.  Output is
descriptive, NOT a pole/zero identification: it reports where the continuous phase has its
local minimum/maximum (the dip), the smoothed magnitude slope in dB/dec, and the frequencies
where that slope steps down (pole-like corner) or up (zero-like corner).  A "doublet
candidate" is a pole-like corner and a zero-like corner within DOUBLET_DECADES of each
other.  That is an inference from a magnitude/phase shape only (a rational fit was NOT done
in the committed code) and is labelled as such by the caller.
"""
from __future__ import annotations

import math

DOUBLET_DECADES = 1.0
SLOPE_STEP_DB_DEC = 8.0   # min change of smoothed slope (dB/dec) to call a corner
SMOOTH_DECADES = 0.5      # half-width of the slope estimation window (decades)


def read_wrdata_nodes(text: str, n_vec: int):
    """Parse `wrdata` of n_vec complex vectors with wr_singlescale: rows f re1 im1 re2 im2 ..."""
    freq, cols = [], [[] for _ in range(2 * n_vec)]
    for ln in text.splitlines():
        p = ln.split()
        if not p:
            continue
        try:
            v = [float(x) for x in p]
        except ValueError:
            if freq:
                raise
            continue
        if len(v) != 1 + 2 * n_vec:
            raise ValueError(f"expected {1 + 2 * n_vec} columns, got {len(v)}: {ln!r}")
        freq.append(v[0])
        for k in range(2 * n_vec):
            cols[k].append(v[1 + k])
    return freq, [(cols[2 * k], cols[2 * k + 1]) for k in range(n_vec)]


def _unwrap(ph):
    out = [ph[0]]
    for k in range(1, len(ph)):
        d = ph[k] - ph[k - 1]
        d -= 360.0 * round(d / 360.0)
        out.append(out[-1] + d)
    return out


def mag_db(re, im):
    return [20.0 * math.log10(max(math.hypot(r, i), 1e-300)) for r, i in zip(re, im)]


def phase_deg(re, im):
    return _unwrap([math.degrees(math.atan2(i, r)) for r, i in zip(re, im)])


def smoothed_slope(freq, y, half_dec=SMOOTH_DECADES):
    """Local least-squares slope of y vs log10 f over +-half_dec decades (units of y per decade)."""
    lf = [math.log10(f) for f in freq]
    out = []
    for k in range(len(freq)):
        idx = [j for j in range(len(freq)) if abs(lf[j] - lf[k]) <= half_dec]
        if len(idx) < 3:
            out.append(float("nan"))
            continue
        mx = sum(lf[j] for j in idx) / len(idx)
        my = sum(y[j] for j in idx) / len(idx)
        sxx = sum((lf[j] - mx) ** 2 for j in idx)
        out.append(sum((lf[j] - mx) * (y[j] - my) for j in idx) / sxx if sxx > 0 else float("nan"))
    return out


def slope_corners(freq, gdb):
    """Frequencies where the smoothed |T| slope steps by >= SLOPE_STEP_DB_DEC.

    kind 'pole-like' = slope decreases (more negative), 'zero-like' = slope increases.
    Steps are located at local extrema of the slope derivative, merged within 0.3 decades.
    """
    s = smoothed_slope(freq, gdb)
    lf = [math.log10(f) for f in freq]
    corners = []
    w = 0.35
    k = 1
    while k < len(freq) - 1:
        if math.isnan(s[k]):
            k += 1
            continue
        # change in slope across +-w decades
        lo = [j for j in range(len(freq)) if lf[k] - w <= lf[j] <= lf[k] and not math.isnan(s[j])]
        hi = [j for j in range(len(freq)) if lf[k] <= lf[j] <= lf[k] + w and not math.isnan(s[j])]
        if lo and hi:
            step = s[hi[-1]] - s[lo[0]]
            if abs(step) >= SLOPE_STEP_DB_DEC:
                corners.append((lf[k], step))
        k += 1
    # merge adjacent detections of the same sign: keep the largest |step| per 0.5-decade cluster
    merged = []
    for lfk, step in corners:
        if merged and abs(lfk - merged[-1][0]) <= 0.5 and (step > 0) == (merged[-1][1] > 0):
            if abs(step) > abs(merged[-1][1]):
                merged[-1] = (lfk, step)
        else:
            merged.append((lfk, step))
    return [{"f_hz": 10 ** a, "slope_step_db_dec": b, "kind": "zero-like" if b > 0 else "pole-like"}
            for a, b in merged]


def doublet_candidates(corners):
    out = []
    for i, a in enumerate(corners):
        for b in corners[i + 1:]:
            if a["kind"] != b["kind"] and abs(math.log10(a["f_hz"] / b["f_hz"])) <= DOUBLET_DECADES:
                out.append({"pole_like_hz": (a if a["kind"] == "pole-like" else b)["f_hz"],
                            "zero_like_hz": (a if a["kind"] == "zero-like" else b)["f_hz"]})
    return out


def phase_dip(freq, re, im):
    """Describe the continuous-phase excursion around crossover.

    Returns the global minimum phase and its frequency, the phase at the first falling
    0 dB crossing, and the phase 'recovery' (max phase above the minimum, at f above it
    up to 100 x the minimum's frequency): a large recovery = a dip (pole then zero) as
    opposed to a monotone roll-off.
    """
    g, ph = mag_db(re, im), phase_deg(re, im)
    kmin = min(range(len(ph)), key=lambda k: ph[k])
    recov = 0.0
    for k in range(kmin, len(ph)):
        if freq[k] > freq[kmin] * 100.0:
            break
        recov = max(recov, ph[k] - ph[kmin])
    fc = None
    for k in range(len(g) - 1):
        if g[k] > 0 >= g[k + 1]:
            t = g[k] / (g[k] - g[k + 1])
            fc = 10 ** (math.log10(freq[k]) + t * (math.log10(freq[k + 1]) - math.log10(freq[k])))
            pc = ph[k] + t * (ph[k + 1] - ph[k])
            break
    return {"min_phase_deg": ph[kmin], "f_at_min_phase_hz": freq[kmin],
            "recovery_after_min_deg": recov, "fc_hz": fc,
            "phase_at_fc_deg": pc if fc is not None else None,
            "dip_present": recov > 20.0}


def node_contributions(freq, node_resp, fc):
    """Magnitude (dB) and phase (deg, relative to the first sample) of each named node
    transfer at the first frequency >= fc, plus its own phase change from f<<fc to fc."""
    out = {}
    if fc is None:
        return out
    k = min(range(len(freq)), key=lambda q: abs(math.log10(freq[q]) - math.log10(fc)))
    for name, (re, im) in node_resp.items():
        g, ph = mag_db(re, im), phase_deg(re, im)
        out[name] = {"mag_db_at_fc": g[k], "phase_deg_at_fc": ph[k], "phase_deg_at_fmin": ph[0],
                     "phase_change_to_fc_deg": ph[k] - ph[0]}
    return out


# ---- candidate comparison helpers (issue #365) ----------------------------------------
TRANSIENT_BOUNDS = {"undershoot": 0.15, "overshoot": 0.15, "recovery": 20.0}  # V, V, us (ratified row)
IQ_LIMIT_UA = 30.0


def _bound(metric):
    for k, v in TRANSIENT_BOUNDS.items():
        if metric.startswith(k):
            return v
    return None


def transient_regressions(base, cand):
    """Compare two load-transient `meas` dicts.  Returns a list of
    {metric, base, cand, kind} where kind is 'new_violation' (cand exceeds the ratified
    bound, base did not), 'worse_violation' (both exceed, cand larger), or 'improved_violation'
    (both exceed, cand smaller; informational).  Metrics without a bound (settle error) are skipped.
    A metric missing from cand is reported as 'missing' -- never as an improvement."""
    out = []
    for m, b in base.items():
        lim = _bound(m)
        if lim is None:
            continue
        c = cand.get(m)
        if c is None:
            out.append({"metric": m, "base": b, "cand": None, "kind": "missing"})
        elif c > lim and not b > lim:
            out.append({"metric": m, "base": b, "cand": c, "kind": "new_violation"})
        elif c > lim and b > lim:
            out.append({"metric": m, "base": b, "cand": c, "kind": "worse_violation" if c > b else "improved_violation"})
    return out


def verdict(margin_rows, transient, iq_by_leg_ua):
    """advance / revise / reject for one candidate.

    margin_rows: list of dicts with valid (bool), pm_deg, worst_gm_db (None allowed).
    transient: output of transient_regressions (or None if not run).
    iq_by_leg_ua: iterable of Iq in uA including every added current.
    reject  : Iq over the limit, or any needed margin leg invalid/missing-crossing.
    revise  : margins and Iq fine on every leg but transient regressions are present or untested,
              or some leg misses PM/GM (the lever helps somewhere but is not sufficient alone).
    advance : every leg valid with PM>=45 and GM>=10, Iq within limit, no transient new/worse
              violations, transient tested.
    """
    if any(i > IQ_LIMIT_UA for i in iq_by_leg_ua):
        return "reject"
    if any(not r["valid"] for r in margin_rows):
        return "reject"
    margins_ok = all(r["pm_deg"] >= 45.0 and r["worst_gm_db"] >= 10.0 for r in margin_rows)
    bad_tr = transient is None or any(t["kind"] in ("new_violation", "worse_violation", "missing") for t in transient)
    return "advance" if margins_ok and not bad_tr else "revise"
