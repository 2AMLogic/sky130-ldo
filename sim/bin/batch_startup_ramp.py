"""Startup ramp-trace grid on the batch backend (issue #336).

PDK-free, standard library only. `sim/startup`'s manifest carries a
`window_grid` (the #313 mechanism) AND a `ramp_monotonicity` block: every leg
must retain its raw `V(VOUT)` trace so `ramp_monotonicity.py` can grade it.
`analysis_steps` requests never produce a rawfile (klt refuses
`options.waveforms` for a step sequence — one waveform artifact per corner
cannot represent several analyses), so each leg instead runs as its own
**scalar-analysis request**:

* `reset` / `save all` / the leg's `alter` cards -> the leg's element values
  are baked into that request's netlist (the COUT/RESR/CDIR/RLOAD cards
  rewritten to exactly what the local `alter` would set; ESR = 0 keeps the
  `leg_values()` topology — series branch 0 F, direct branch carries COUT,
  RESR parked). Each (corner, leg) is still its own ngspice process: nothing
  carries over, so isolation is at least the local deck's in-process `reset`.
* `tran <args>` -> the request's scalar `analysis` (kind `tran`).
* the leg's `.meas` cards -> request `measurements[]` with `spice` verbatim
  (`on_unreached: "null"` on `when`-threshold cards so a ramp that never
  reaches the window is a missing value, not an error-grade diagnostic).
* `wrdata ... v(vout)` -> replaced by `options.waveforms: true` +
  `keep_artifacts`: klt returns each corner's waveform JSON artifact and the
  harness rebuilds the same `<corner>.<leg>.trace.dat` locally, then grades
  it with `ramp_monotonicity.evaluate_legs` — the same checker, the same
  trace file name and sha256, the strict 0 V tolerance unchanged.

A missing, unparsable or wrong-shaped waveform artifact makes the leg's ramp
condition INVALID with an explicit reason: a missing trace can only lower the
verdict, never qualify it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import batch_window_grid as bwg
import ramp_monotonicity as rm
from _corner_model import Experiment, leg_values

# A scalar request measurement's card that thresholds a crossing: a ramp that
# never reaches it must come back as a null value (recorded missing), not as
# an error-grade diagnostic that would abort the corner.
_ON_UNREACHED = "null"

_TIME_RE = re.compile(r"^time$", re.IGNORECASE)


class StartupRampError(ValueError):
    """The startup manifest (or a response artifact) has no faithful
    scalar-request / trace form."""


def _leg_template(exp: Experiment) -> bwg.LegTemplate:
    grid = exp.raw["window_grid"]
    return bwg.parse_leg_template(grid["leg_analyses"])


def check_ramp_trace_shape(exp: Experiment) -> None:
    """Pin the startup shape a trace-returning batch run relies on, before any
    request is written (and so before any submission)."""
    cfg = exp.raw.get("ramp_monotonicity") or {}
    for key in ("signal", "t_enable_s", "v_low", "max_dt_s", "min_samples", "tolerance_v", "legs"):
        if key not in cfg:
            raise StartupRampError(f"ramp_monotonicity is missing {key!r}")
    template = _leg_template(exp)
    if template.wrdata_signal is None:
        raise StartupRampError(
            "leg_analyses declares no wrdata trace: there is nothing for "
            "options.waveforms to return"
        )
    if template.lets:
        raise StartupRampError(
            "leg_analyses declares let helpers; their vector results have no "
            "scalar-request form"
        )
    if template.wrdata_signal.lower() != str(cfg["signal"]).lower():
        raise StartupRampError(
            f"ramp_monotonicity.signal {cfg['signal']!r} is not the leg's wrdata "
            f"signal {template.wrdata_signal!r}"
        )
    legs = [leg["id"] for leg in exp.raw["window_grid"]["legs"]]
    if [leg["id"] for leg in cfg["legs"]] != legs:
        raise StartupRampError(
            "ramp_monotonicity.legs is not exactly the declared window_grid legs "
            "(in order): a trace condition without a leg, or a leg without a "
            "trace condition, could qualify nothing"
        )


def scalar_leg_request(exp: Experiment, leg_id: str) -> dict:
    """The scalar `analysis` + `measurements[]` body for one leg's request."""
    template = _leg_template(exp)
    cards = [{"name": name, "spice": card} for name, card in template.meas_cards]
    for card in cards:
        if re.search(r"\bwhen\b", card["spice"], re.IGNORECASE):
            card["on_unreached"] = _ON_UNREACHED
    return {
        "analysis": {"kind": "tran", "args": template.tran_args},
        "measurements": cards,
    }


def leg_netlist_body(exp: Experiment, leg_id: str, body: list[str]) -> list[str]:
    """The request netlist body with this leg's element values baked in."""
    grid = exp.raw["window_grid"]
    leg = next(x for x in grid["legs"] if x["id"] == leg_id)
    values = leg_values(grid, leg)
    template = _leg_template(exp)
    out = list(body)
    for elem, placeholder in template.alters:
        if placeholder not in values:
            raise StartupRampError(f"leg {leg_id}: no value for alter placeholder {{{placeholder}}}")
        out = _rewrite_element(out, elem, float(values[placeholder]), leg_id)
    return out


def _rewrite_element(body: list[str], elem: str, value: float, leg_id: str) -> list[str]:
    """Replace the value field of the ONE card whose first token is `elem` —
    the netlist edit the local deck's `alter <elem> = value` performs."""
    out, hits = [], 0
    want = elem.lower()
    for ln in body:
        tok = ln.split()
        if tok and tok[0].lower() == want:
            if len(tok) < 4:
                raise StartupRampError(
                    f"leg {leg_id}: element card `{ln.strip()}` has no value field"
                )
            tok[3] = repr(value)
            ln = " ".join(tok)
            hits += 1
        out.append(ln)
    if hits != 1:
        raise StartupRampError(
            f"leg {leg_id}: expected exactly one `{elem}` card in the request "
            f"netlist, found {hits}"
        )
    return out


def waveform_trace(
    ramp_signal: str, artifacts: dict | None, outdir: Path
) -> tuple[list[float], list[float]]:
    """(times, volts) of the ramp signal out of a corner's waveform artifact.

    `artifacts.waveform` is klt's documented waveform JSON (`plotname`,
    `variables`, `points`); the paths in a collected batch response are
    relative to the request's own `-o` directory. Raises StartupRampError —
    never a silent skip — when the artifact is absent, unreadable or does not
    contain the time axis and the declared signal.
    """
    ref = (artifacts or {}).get("waveform")
    if not isinstance(ref, str) or not ref:
        raise StartupRampError(
            "klt sim response retains no waveform artifact (options.waveforms "
            "did not come back): the leg's ramp condition has no trace"
        )
    path = Path(ref)
    if not path.is_absolute():
        path = outdir / path
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise StartupRampError(f"waveform artifact unreadable ({path}: {exc})") from exc
    variables = doc.get("variables")
    points = doc.get("points")
    if not isinstance(variables, list) or not isinstance(points, list) or not points:
        raise StartupRampError(f"waveform artifact {path} is not a populated waveform JSON")
    names = [str(v.get("name", "")).lower() if isinstance(v, dict) else "" for v in variables]
    want = ramp_signal.lower()
    if want not in names:
        shown = ", ".join(n for n in names[:8] if n) or "(none)"
        raise StartupRampError(
            f"waveform artifact {path} does not contain {ramp_signal} (variables: {shown})"
        )
    t_idx = next((i for i, n in enumerate(names) if _TIME_RE.match(n)), None)
    if t_idx is None:
        raise StartupRampError(f"waveform artifact {path} has no time axis")
    sig_idx = names.index(want)
    width = len(names)
    times: list[float] = []
    volts: list[float] = []
    for i, row in enumerate(points):
        if not isinstance(row, list) or len(row) != width:
            got = len(row) if isinstance(row, list) else "non-list"
            raise StartupRampError(
                f"waveform artifact {path}: point #{i} has {got} value(s), expected {width}"
            )
        times.append(float(row[t_idx]))
        volts.append(float(row[sig_idx]))
    return times, volts


def leg_ramp_condition(
    exp: Experiment,
    leg_id: str,
    corner_id: str,
    artifacts: dict | None,
    outdir: Path,
) -> tuple[dict, Path | None, list[str]]:
    """Grade one leg's ramp-monotonicity condition from the corner's returned
    waveform artifact.

    Returns (leg result as `ramp_monotonicity.evaluate_legs` shapes it, the
    rebuilt trace file's path, structural reasons). A structurally missing or
    unusable artifact yields an INVALID leg result plus the reasons — the
    condition is recorded, never silently skipped. An evaluated trace is
    graded with the manifest's own settings and the strict 0 V tolerance.
    """
    cfg = dict(exp.raw["ramp_monotonicity"])
    try:
        times, volts = waveform_trace(cfg["signal"], artifacts, outdir)
    except StartupRampError as exc:
        result = rm.invalid_result(cfg, [str(exc)])
        result.update({"leg": leg_id, "trace_file": f"{corner_id}.{leg_id}.trace.dat"})
        return result, None, [f"[leg {leg_id}] {exc}"]
    trace_dir = outdir / "traces"
    path = trace_dir / f"{corner_id}.{leg_id}.trace.dat"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{t!r} {v!r}" for t, v in zip(times, volts)]
    path.write_text("\n".join(lines) + "\n")
    one_leg = {**cfg, "legs": [{"id": leg_id}]}
    (result,) = rm.evaluate_legs(one_leg, trace_dir, corner_id)
    return result, path, []


def ramp_check(leg_result: dict) -> dict:
    """The per-leg condition as a corner check row (the local run_corner
    shape): max = tolerance_v, pass = the leg's own verdict."""
    passed = leg_result["pass"]
    return {
        "name": f"ramp_drawdown_{leg_result['leg']}_v",
        "expr": "ramp_monotonicity.max_drawdown(v(vout))",
        "unit": "V",
        "value": leg_result["max_drawdown_v"],
        "min": None,
        "max": leg_result["settings"]["tolerance_v"],
        "pass": passed,
        "reason": ""
        if passed
        else f"{leg_result['status']}: " + "; ".join(leg_result["reasons"]),
    }


def adapter_info(exp: Experiment) -> dict:
    """Provenance of the issue #336 trace-return adapter for a batch record."""
    template = _leg_template(exp)
    cfg = exp.raw["ramp_monotonicity"]
    return {
        "name": "startup-ramp-traces",
        "issue": 336,
        "analysis": f"tran {template.tran_args}",
        "waveform_signal": template.wrdata_signal,
        "cards": [card for _, card in template.meas_cards],
        "graded": [{"name": m.name, "expr": m.expr} for m in exp.measurements],
        "ramp_tolerance_v": cfg["tolerance_v"],
        "trace_source": "options.waveforms waveform JSON artifact, rebuilt locally "
        "as <corner>.<leg>.trace.dat and graded by sim/bin/ramp_monotonicity.py",
    }


_NUM_RE = re.compile(r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)([a-zA-Z]*)")
_SCALE = {"": 1.0, "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3, "u": 1e-6,
          "n": 1e-9, "p": 1e-12, "f": 1e-15}
_TOKEN_RE = re.compile(r"\s*(?:(abs)\b|([A-Za-z_][A-Za-z0-9_]*)|"
                       r"((?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?[a-zA-Z]*)|([-+*/()]))")


def _num(text: str) -> float:
    m = _NUM_RE.fullmatch(text)
    if m is None or m.group(2).lower() not in _SCALE:
        raise StartupRampError(f"unsupported number {text!r} in startup measurement expression")
    return float(m.group(1)) * _SCALE[m.group(2).lower()]


def evaluate_measurement(expr: str, card_values: dict[str, float | None]) -> float | None:
    """Evaluate a manifest measurement expression over one leg's raw `.meas`
    card values: card-name references, spice-suffixed numbers, `abs(...)`,
    `+ - * / ( )`. A missing card value (or a division by zero) yields None —
    the measurement is then missing, never guessed."""
    toks: list[tuple[str, str]] = []
    text, pos = expr.strip(), 0
    if not text or "\n" in text or "\r" in text:
        raise StartupRampError(f"expression {expr!r} must be one non-empty line")
    lowered = {k.lower() for k in card_values}
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if m is None or m.end() == pos:
            raise StartupRampError(f"expression {expr!r}: unsupported token at {text[pos:]!r}")
        if m.group(1) is not None:
            toks.append(("fn", "abs"))
        elif m.group(2) is not None:
            if m.group(2).lower() not in lowered:
                raise StartupRampError(
                    f"expression {expr!r} references {m.group(2)!r}, which is not a "
                    "leg meas card"
                )
            toks.append(("ref", m.group(2)))
        elif m.group(3) is not None:
            toks.append(("num", m.group(3)))
        else:
            toks.append(("op", m.group(4)))
        pos = m.end()

    values = {k.lower(): v for k, v in card_values.items()}
    p = 0

    def peek():
        return toks[p] if p < len(toks) else (None, None)

    def take():
        nonlocal p
        out = toks[p]
        p += 1
        return out

    def factor():
        kind, val = peek()
        if (kind, val) == ("op", "-"):
            take()
            v = factor()
            return None if v is None else -v
        if (kind, val) == ("op", "+"):
            take()
            return factor()
        if kind == "num":
            take()
            return _num(val)
        if kind == "fn":
            take()
            if peek() != ("op", "("):
                raise StartupRampError(f"expression {expr!r}: abs needs parentheses")
            take()
            v = expr_()
            if peek() != ("op", ")"):
                raise StartupRampError(f"expression {expr!r}: unbalanced parentheses")
            take()
            return None if v is None else abs(v)
        if kind == "ref":
            take()
            return values[val.lower()]
        if kind == "op" and val == "(":
            take()
            v = expr_()
            if peek() != ("op", ")"):
                raise StartupRampError(f"expression {expr!r}: unbalanced parentheses")
            take()
            return v
        raise StartupRampError(f"expression {expr!r}: unexpected {val!r}")

    def term():
        v = factor()
        while peek() in (("op", "*"), ("op", "/")):
            op = take()[1]
            r = factor()
            if v is None or r is None or (op == "/" and r == 0):
                v = None
            else:
                v = v * r if op == "*" else v / r
        return v

    def expr_() -> float | None:
        v = term()
        while peek() in (("op", "+"), ("op", "-")):
            op = take()[1]
            r = term()
            v = None if v is None or r is None else (v + r if op == "+" else v - r)
        return v

    out = expr_()
    if p != len(toks):
        raise StartupRampError(f"expression {expr!r}: trailing tokens")
    return out
