"""Startup ramp-monotonicity checker (issue #309). PDK-free, standard library only.

Metric: the maximum DRAWDOWN of a startup trace. Walk the samples from the
enable instant up to and including the first sample that is inside the
regulation window (v >= v_low); the drawdown at a sample is
`running_max - v`, and the metric is the largest such value. A ramp that is
monotonically non-decreasing at the sample points has drawdown exactly 0.
The worst drawdown's interval is reported as (t at the running maximum,
t at the trough) so a FAIL says where in time to look.

Verdicts are PASS / FAIL / INVALID. INVALID (a missing, truncated, nonfinite,
unordered, mis-sized or insufficiently sampled trace, or one that never enters
the window) is never a PASS: a monotonicity claim needs a trace that can
substantiate it.

Limits of the claim (see sim/README.md, "Startup ramp monotonicity"):
 * It is a statement about the SAMPLED trace only. A dip that falls entirely
   between two adjacent samples is invisible; `max_dt_s` bounds that gap and
   the observed worst gap is reported as `resolution_s`.
 * `tolerance_v` is a numerical allowance, default 0.0 (strict). It is
   recorded in every result. It must never be raised to absorb a physical dip:
   a nonzero value needs a decision record (spec/), not a code edit.
 * It is distinct from post-settling ripple: the window ends at first entry.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

REQUIRED_SETTINGS = ("t_enable_s", "v_low", "max_dt_s", "min_samples")


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _result(status, reasons, settings, **extra) -> dict:
    out = {
        "status": status,
        "pass": status == "PASS",
        "reasons": list(reasons),
        "max_drawdown_v": None,
        "worst_interval_s": None,
        "t_entry_s": None,
        "n_samples": None,
        "n_window_samples": None,
        "resolution_s": None,
        "settings": dict(settings),
    }
    out.update(extra)
    return out


def check_ramp_monotonicity(times, volts, settings: dict) -> dict:
    """Evaluate one startup trace. Never raises on bad data; returns INVALID."""
    s = {"tolerance_v": 0.0, **settings}
    missing = [k for k in REQUIRED_SETTINGS if k not in s]
    if missing:
        return _result("INVALID", [f"missing checker settings: {', '.join(missing)}"], s)
    if not all(_finite(s[k]) for k in (*REQUIRED_SETTINGS, "tolerance_v")) or s["tolerance_v"] < 0:
        return _result("INVALID", ["checker settings must be finite (tolerance_v >= 0)"], s)

    if times is None or volts is None or len(times) == 0 or len(volts) == 0:
        return _result("INVALID", ["trace missing or empty"], s)
    if len(times) != len(volts):
        return _result("INVALID", ["time and voltage columns differ in length"], s)
    n = len(times)
    if not all(_finite(t) for t in times) or not all(_finite(v) for v in volts):
        return _result("INVALID", ["trace contains nonfinite samples"], s, n_samples=n)
    if any(b <= a for a, b in zip(times, times[1:])):
        return _result("INVALID", ["time column is not strictly increasing"], s, n_samples=n)
    if times[0] > s["t_enable_s"]:
        return _result(
            "INVALID", ["trace starts after the enable instant (no pre-enable baseline)"], s,
            n_samples=n,
        )

    start = next((i for i, t in enumerate(times) if t >= s["t_enable_s"]), None)
    if start is None:
        return _result("INVALID", ["trace ends before the enable instant"], s, n_samples=n)
    entry = next((i for i in range(start, n) if volts[i] >= s["v_low"]), None)
    if entry is None:
        return _result(
            "INVALID",
            ["output never enters the regulation window (v >= v_low); ramp not evaluable"],
            s, n_samples=n,
        )

    window = range(start, entry + 1)
    n_win = len(window)
    gaps = [times[i + 1] - times[i] for i in range(start, entry)]
    # include the gap from the enable instant to the first window sample
    gaps.append(times[start] - s["t_enable_s"])
    resolution = max(gaps) if gaps else 0.0
    reasons = []
    if n_win < s["min_samples"]:
        reasons.append(f"only {n_win} samples between enable and window entry (< {s['min_samples']:g})")
    if resolution > s["max_dt_s"]:
        reasons.append(f"worst sample gap {resolution:.3g} s exceeds max_dt_s {s['max_dt_s']:.3g} s")

    peak_i, worst, worst_pk, worst_tr = start, 0.0, start, start
    for i in window:
        if volts[i] > volts[peak_i]:
            peak_i = i
        dd = volts[peak_i] - volts[i]
        if dd > worst:
            worst, worst_pk, worst_tr = dd, peak_i, i
    base = dict(
        max_drawdown_v=worst,
        worst_interval_s=[times[worst_pk], times[worst_tr]] if worst > 0 else None,
        t_entry_s=times[entry],
        n_samples=n,
        n_window_samples=n_win,
        resolution_s=resolution,
    )
    if reasons:
        return _result("INVALID", reasons, s, **base)
    if worst > s["tolerance_v"]:
        return _result(
            "FAIL",
            [
                f"ramp not monotonic: drawdown {worst:.6g} V between t={times[worst_pk]:.6g} s "
                f"and t={times[worst_tr]:.6g} s (tolerance {s['tolerance_v']:g} V)"
            ],
            s, **base,
        )
    return _result("PASS", [], s, **base)


def parse_trace(text: str) -> tuple[list[float], list[float]]:
    """Parse an ngspice `wrdata` file (`time value` per line). A malformed line
    raises ValueError so the caller can mark the leg INVALID."""
    times, volts = [], []
    for ln in text.splitlines():
        if not ln.strip():
            continue
        parts = ln.split()
        if len(parts) != 2:
            raise ValueError(f"unexpected trace line: {ln.strip()[:80]!r}")
        times.append(float(parts[0]))
        volts.append(float(parts[1]))
    return times, volts


def evaluate_legs(settings: dict, run_dir: Path, corner_id: str) -> list[dict]:
    """Check every leg of one corner. Each leg's trace is
    `<run_dir>/<corner_id>.<leg id>.trace.dat`; a missing/unparsable file is
    INVALID. Each result carries the leg id, trace file name and sha256."""
    common = {k: v for k, v in settings.items() if k not in ("legs", "signal")}
    out = []
    for leg in settings["legs"]:
        name = f"{corner_id}.{leg['id']}.trace.dat"
        path = Path(run_dir) / name
        sha = None
        try:
            raw = path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            t, v = parse_trace(raw.decode())
            res = check_ramp_monotonicity(t, v, common)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            res = _result("INVALID", [f"trace unreadable: {exc}"], common)
        res.update({"leg": leg["id"], "trace_file": name, "trace_sha256": sha})
        out.append(res)
    return out
