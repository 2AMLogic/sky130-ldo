"""Translate `sim/enable-shutdown`'s chained deck into `klt sim` steps (issue #755).

PDK-free, standard library only. corner-run.py's local path runs the bench's
deck as ONE ngspice process per corner: a `tran 5u 4.5m` enable -> shutdown
cycle with four `meas tran` cards, then three EN = 0 operating points -- `op`
with the output free, `alter rforce = 1m` + `op` (output forced to 0 V), and
`alter vforce = 1.8` + `op` (output held at 1.8 V through the 1 mOhm path).

The faithful translation is ONE four-step `analysis_steps[]` request per
supply group (same chained-request pattern as `batch_current_limit`, #177):
`tran1`, `op1`, `op2`, `op3`, named by analysis in encounter order so the
manifest's plot-qualified graded expressions (`tran1.vpre`,
`-1e6*op1.i(vvin)`, ...) are position-independent.

klt top-level derived measurements may only reference declared
`<step>.<measurement>` names, never raw plot vectors, so each manifest
expression over an `opN.<vector>` plot vector is split in two:

* a STEP measurement on `opN`, named like the manifest measurement, whose
  `expr` is the manifest expression with its `opN.` qualifier dropped
  (`-1e6*op1.i(vvin)` -> `-1e6*i(vvin)`), and
* a top-level derived measurement `meas_<name>` = `opN.<name>`.

Expressions over `tranN.<card>` stay verbatim as top-level derived rows, as in
#177. All eight rows therefore come back as `meas_<name>`, graded locally with
the harness's own bounds, exactly like the other backends.

Alters are cumulative in the deck (`rforce` stays 1 mOhm for the 1.8 V point).
The `op3` step repeats `rforce = 1m` next to `vforce = 1.8`: identical if klt
carries alters across chained steps, and still correct if it resets them.

Deliberately NOT a SPICE interpreter: only the card forms below are accepted
and anything else is refused before any netlisting, submission or local
ngspice. The stimulus lives in the netlist (sent verbatim) and is pinned by
`blr.check_netlist`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import batch_line_regulation as blr

TRAN_STEP_NAME = "tran1"
OP_STEP_NAMES = ("op1", "op2", "op3")

# `alter rforce = 1m` (op2) then `alter vforce = 1.8` (op3), pinned by value.
OP2_ALTERS = (("rforce", 1e-3),)
OP3_ALTERS = (("rforce", 1e-3), ("vforce", 1.8))


class EnableShutdownTranslationError(ValueError):
    """The deck, a measurement or the netlist has no faithful step form."""


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_NUM = blr._NUM
_PROBE = r"[vi]\([A-Za-z0-9_.]+\)"
# No `uic`: EN starts low, so the pre-transient operating point is the
# disabled state and the leg is a genuine enable -> shutdown cycle.
_TRAN_RE = re.compile(rf"^tran\s+({_NUM})\s+({_NUM})$", re.IGNORECASE)
_ALTER_RE = re.compile(rf"^alter\s+({_IDENT})\s*=\s*({_NUM})$", re.IGNORECASE)
_OP_RE = re.compile(r"^op$", re.IGNORECASE)
_MEAS_FIND_RE = re.compile(
    rf"^meas\s+tran\s+({_IDENT})\s+find\s+({_PROBE})\s+at=\s*{_NUM}$", re.IGNORECASE
)
_MEAS_WIN_RE = re.compile(
    rf"^meas\s+tran\s+({_IDENT})\s+(avg|min|max)\s+({_PROBE})\s+from=\s*{_NUM}\s+to=\s*{_NUM}$",
    re.IGNORECASE,
)
# A manifest expression over one op plot vector: optional numeric scale.
_OP_EXPR_RE = re.compile(
    rf"^(?P<scale>(?:{_NUM})\s*\*\s*)?(?P<step>op[1-3])\.(?P<vec>{_PROBE})$", re.IGNORECASE
)


@dataclass
class Leg:
    """One translated step: its fixed name, alters, analysis and cards."""

    step_name: str
    kind: str  # "tran" | "op"
    analysis_args: str
    alters: list[tuple[str, float]]
    cards: list[tuple[str, str]] = field(default_factory=list)  # (name, deck line)
    # step measurements with an `expr` (op quantities): (name, expr, unit)
    exprs: list[tuple[str, str, str]] = field(default_factory=list)


def _tran_card(line: str) -> str | None:
    for rx in (_MEAS_FIND_RE, _MEAS_WIN_RE):
        m = rx.match(line)
        if m:
            return m.group(1)
    return None


def parse_deck(lines: list[str]) -> list[Leg]:
    """Parse `deck.analyses` into its four steps (comments ignored), or raise
    naming the first line with no faithful step form."""
    body = blr.deck_body(lines)
    if not body:
        raise EnableShutdownTranslationError("deck.analyses declares no analysis")
    pos = 0

    def take(what: str, rx: re.Pattern[str]):
        nonlocal pos
        if pos >= len(body):
            raise EnableShutdownTranslationError(f"deck ends where {what} was expected")
        m = rx.match(body[pos])
        if m is None:
            raise EnableShutdownTranslationError(f"expected {what}; got {body[pos]!r}")
        pos += 1
        return m

    m = take("`tran <tstep> <tstop>` (enable -> shutdown cycle)", _TRAN_RE)
    tran = Leg(TRAN_STEP_NAME, "tran", f"{m.group(1)} {m.group(2)}", [])
    names: set[str] = set()
    while pos < len(body) and (name := _tran_card(body[pos])) is not None:
        if name.lower() in names:
            raise EnableShutdownTranslationError(f"meas card name {name!r} is declared twice")
        names.add(name.lower())
        tran.cards.append((name, body[pos]))
        pos += 1
    if not tran.cards:
        raise EnableShutdownTranslationError("the tran leg declares no `meas tran` card")
    legs = [tran]

    take("op1's `op`", _OP_RE)
    legs.append(Leg(OP_STEP_NAMES[0], "op", "", []))
    for step, want in ((OP_STEP_NAMES[1], OP2_ALTERS), (OP_STEP_NAMES[2], OP3_ALTERS[1:])):
        elem, value = want[0]
        m = take(f"`alter {elem} = <value>` before {step}", _ALTER_RE)
        got = (m.group(1).lower(), _num(m.group(2)))
        if got != (elem, value):
            raise EnableShutdownTranslationError(
                f"{step} must `alter {elem} = {value:g}`; got {body[pos - 1]!r}")
        take(f"{step}'s `op`", _OP_RE)
        alters = list(OP2_ALTERS if step == OP_STEP_NAMES[1] else OP3_ALTERS)
        legs.append(Leg(step, "op", "", alters))
    if pos != len(body):
        raise EnableShutdownTranslationError(
            f"deck carries commands after the third op: {body[pos:]!r} (exactly four steps)")
    return legs


def _num(text: str) -> float:
    m = re.fullmatch(r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)([a-zA-Z]*)", text)
    scale = {"": 1.0, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "k": 1e3}
    if m is None or m.group(2).lower() not in scale:
        raise EnableShutdownTranslationError(f"unsupported alter value {text!r}")
    return float(m.group(1)) * scale[m.group(2).lower()]


def split_measurements(
    legs: list[Leg], measurements: list[tuple[str, str, str]]
) -> list[tuple[str, str, str]]:
    """Attach each op-vector manifest expression to its op step as a step
    `expr` measurement (mutating `legs` idempotently) and return the
    top-level derived rows `(meas_<name>, expr, unit)` in manifest order.
    Raises on any expression that is neither over card refs nor one op vector."""
    by_step = {leg.step_name: leg for leg in legs}
    for leg in legs:
        leg.exprs = []
    card_refs = {f"{leg.step_name}.{n}".lower() for leg in legs for n, _ in leg.cards}
    derived: list[tuple[str, str, str]] = []
    for name, expr, unit in measurements:
        if not re.fullmatch(_IDENT, name):
            raise EnableShutdownTranslationError(f"measurement name {name!r} is not a vector name")
        m = _OP_EXPR_RE.match(expr.strip())
        if m:
            step = m.group("step").lower()
            if step not in by_step or by_step[step].kind != "op":
                raise EnableShutdownTranslationError(f"{name!r} reads unknown op step {step!r}")
            scale = (m.group("scale") or "").replace(" ", "")
            by_step[step].exprs.append((name, f"{scale}{m.group('vec')}", unit))
            derived.append((f"meas_{name}", f"{step}.{name}", unit))
        else:
            blr.evaluate(expr, {}, card_refs)
            derived.append((f"meas_{name}", expr, unit))
    return derived


def check_measurements(legs: list[Leg], measurements: list[tuple[str, str, str]]) -> None:
    """Every graded expression must translate (see `split_measurements`)."""
    split_measurements(legs, measurements)


def chained_steps(legs: list[Leg]) -> list[dict]:
    """The `analysis_steps[]` sequence (call `check_measurements` first so op
    step expressions are attached)."""
    steps = []
    for leg in legs:
        step: dict = {"name": leg.step_name}
        if leg.alters:
            step["alter"] = {elem: value for elem, value in leg.alters}
        step["analysis"] = {"kind": leg.kind, "args": leg.analysis_args}
        step["measurements"] = [{"name": n, "spice": "." + ln} for n, ln in leg.cards] + [
            {"name": n, "expr": e, "unit": u} for n, e, u in leg.exprs
        ]
        steps.append(step)
    return steps


def request_measurements(legs: list[Leg], measurements: list[tuple[str, str, str]]) -> list[dict]:
    """The request's top-level derived measurements (all eight manifest rows)."""
    return [
        {"name": n, "expr": e, "unit": u} for n, e, u in split_measurements(legs, measurements)
    ]


def step_result_names(legs: list[Leg]) -> list[str]:
    """Every `<step>.<name>` result the steps themselves report."""
    return [f"{leg.step_name}.{n}" for leg in legs for n, _ in leg.cards] + [
        f"{leg.step_name}.{n}" for leg in legs for n, _, _ in leg.exprs
    ]
