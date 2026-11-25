"""Translate `sim/psrr-dc`'s two-load AC deck into `klt sim` steps (issue #786).

PDK-free, standard library only. corner-run.py's local path runs the bench's
deck as ONE ngspice process per corner, twice over the same pattern: `op` +
`let vseed = v(vout)`, then `ac lin 3 1e3 1e5` and two `let` vectors
(`p1k = -vdb(vout)[0]`, `p100k = -vdb(vout)[2]`) at the schematic's 1.8 kOhm
load (1 mA); then `alter rload = 36` and the same block again (50 mA). The
manifest grades `ac1.p1k` / `ac1.p100k` / `ac2.p1k` / `ac2.p100k` (strict
50 dB / 20 dB lower bounds) and reports `op1.vseed` / `op2.vseed` unbounded.

The faithful translation is ONE four-step `analysis_steps[]` request per
supply group (the chained-request pattern of `batch_enable_shutdown`, #755):
`op1`, `ac1`, `op2`, `ac2`, named by analysis in encounter order so the
manifest's plot-qualified expressions carry over verbatim. Each `let` vector
becomes a STEP measurement on its `ac` step (`expr` = the let's right-hand
side, which klt evaluates over the step's AC result, the way `batch_loop_gain`
sends `lgdb[0]`), and each manifest row is a top-level derived measurement
`meas_<name>` = `<step>.<name>`, graded locally with the harness's own bounds.

The AC stimulus (`VVIN ... AC 1`; EN carries none), the 1 uF / 10 mOhm output
network, VREF and the three-node `.nodeset` seed all live in the netlist and
are pinned by `blr.check_netlist` (see BATCH_ALLOWLIST["psrr-dc"]).

Deliberately NOT a SPICE interpreter: only the card forms below are accepted
and anything else is refused before any netlisting, submission or local
ngspice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import _meas_expr
import batch_line_regulation as blr

# The testbench's IC_SEED card, pinned verbatim.
NODESET_CARD = ".nodeset v(VOUT)=1.8 v(xldo.FB)=1.2 v(xldo.N_FBB)=0.6"
AC_ARGS = "lin 3 1e3 1e5"
STEP_NAMES = (("op1", "ac1"), ("op2", "ac2"))
# the pinned `let` vectors: name -> right-hand side (index 0 = 1 kHz, 2 = 100 kHz)
AC_VECTORS = (("p1k", "-vdb(vout)[0]"), ("p100k", "-vdb(vout)[2]"))
SEED_VECTOR = ("vseed", "v(vout)")
LOAD2_ALTER = ("rload", 36.0)


class PsrrDcTranslationError(ValueError):
    """The deck, a measurement or the netlist has no faithful step form."""


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_NUM = blr._NUM
_ALTER_RE = re.compile(rf"^alter\s+({_IDENT})\s*=\s*({_NUM})$", re.IGNORECASE)
_LET_RE = re.compile(rf"^let\s+({_IDENT})\s*=\s*(.+)$", re.IGNORECASE)
_AC_RE = re.compile(r"^ac\s+(.+)$", re.IGNORECASE)
_REF_RE = re.compile(rf"^((?:op|ac)[12])\.({_IDENT})$", re.IGNORECASE)


@dataclass
class Leg:
    """One translated step: fixed name, alters, analysis and expr measurements."""

    step_name: str
    kind: str  # "op" | "ac"
    analysis_args: str
    alters: list[tuple[str, float]]
    vectors: list[tuple[str, str]]  # (name, expr)
    exprs: list[tuple[str, str, str]] = field(default_factory=list)  # (name, expr, unit)


def _num(text: str) -> float:
    return _meas_expr.parse_number(text, PsrrDcTranslationError)


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def parse_deck(lines: list[str]) -> list[Leg]:
    """Parse `deck.analyses` into its four steps (comments ignored), or raise
    naming the first line with no faithful step form."""
    body = blr.deck_body(lines)
    if not body:
        raise PsrrDcTranslationError("deck.analyses declares no analysis")
    pos = 0

    def take(what: str) -> re.Match[str] | str:
        nonlocal pos
        if pos >= len(body):
            raise PsrrDcTranslationError(f"deck ends where {what} was expected")
        pos += 1
        return body[pos - 1]

    def expect_let(want: tuple[str, str]) -> None:
        line = take(f"`let {want[0]} = {want[1]}`")
        m = _LET_RE.match(line)
        if m is None or m.group(1).lower() != want[0] or _squash(m.group(2)) != _squash(want[1]):
            raise PsrrDcTranslationError(f"expected `let {want[0]} = {want[1]}`; got {line!r}")

    legs: list[Leg] = []
    for i, (op_name, ac_name) in enumerate(STEP_NAMES):
        alters: list[tuple[str, float]] = []
        if i == 1:
            line = take("`alter rload = 36` (the 50 mA point)")
            m = _ALTER_RE.match(line)
            if m is None or (m.group(1).lower(), _num(m.group(2))) != LOAD2_ALTER:
                raise PsrrDcTranslationError(
                    f"the second point must `alter rload = 36`; got {line!r}")
            alters = [LOAD2_ALTER]
        line = take(f"{op_name}'s `op`")
        if line.lower() != "op":
            raise PsrrDcTranslationError(f"expected `op`; got {line!r}")
        expect_let(SEED_VECTOR)
        legs.append(Leg(op_name, "op", "", alters, [SEED_VECTOR]))
        line = take(f"`ac {AC_ARGS}`")
        m = _AC_RE.match(line)
        if m is None or _squash(m.group(1)) != _squash(AC_ARGS):
            raise PsrrDcTranslationError(f"expected `ac {AC_ARGS}`; got {line!r}")
        for vec in AC_VECTORS:
            expect_let(vec)
        legs.append(Leg(ac_name, "ac", AC_ARGS, [], list(AC_VECTORS)))
    if pos != len(body):
        raise PsrrDcTranslationError(
            f"deck carries commands after the second ac block: {body[pos:]!r} (exactly four steps)")
    return legs


def split_measurements(
    legs: list[Leg], measurements: list[tuple[str, str, str]]
) -> list[tuple[str, str, str]]:
    """Attach each manifest row `<step>.<vector>` to its step as a step `expr`
    measurement (mutating `legs` idempotently) and return the top-level derived
    rows `(meas_<name>, <step>.<vector>, unit)` in manifest order. Raises on any
    expression that is not exactly one `let` vector of the deck."""
    by_step = {leg.step_name: leg for leg in legs}
    for leg in legs:
        leg.exprs = []
    derived: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for name, expr, unit in measurements:
        if not re.fullmatch(_IDENT, name):
            raise PsrrDcTranslationError(f"measurement name {name!r} is not a vector name")
        m = _REF_RE.match(expr.strip())
        if m is None:
            raise PsrrDcTranslationError(
                f"{name!r}: expression {expr!r} is not a bare `<step>.<vector>` reference")
        step, vec = m.group(1).lower(), m.group(2).lower()
        leg = by_step.get(step)
        rhs = dict(leg.vectors).get(vec) if leg else None
        if rhs is None:
            raise PsrrDcTranslationError(f"{name!r} reads {expr!r}, which the deck does not define")
        if f"{step}.{vec}" in seen:
            raise PsrrDcTranslationError(f"{step}.{vec} is graded by two measurements")
        seen.add(f"{step}.{vec}")
        leg.exprs.append((name, rhs, unit))
        derived.append((f"meas_{name}", f"{step}.{name}", unit))
    return derived


def check_measurements(legs: list[Leg], measurements: list[tuple[str, str, str]]) -> None:
    """Every graded expression must translate (see `split_measurements`)."""
    split_measurements(legs, measurements)


def chained_steps(legs: list[Leg]) -> list[dict]:
    """The `analysis_steps[]` sequence (call `check_measurements` first)."""
    steps = []
    for leg in legs:
        step: dict = {"name": leg.step_name}
        if leg.alters:
            step["alter"] = {elem: value for elem, value in leg.alters}
        step["analysis"] = {"kind": leg.kind, "args": leg.analysis_args}
        step["measurements"] = [{"name": n, "expr": e, "unit": u} for n, e, u in leg.exprs]
        steps.append(step)
    return steps


def request_measurements(legs: list[Leg], measurements: list[tuple[str, str, str]]) -> list[dict]:
    """The request's top-level derived measurements (all six manifest rows)."""
    return [{"name": n, "expr": e, "unit": u} for n, e, u in split_measurements(legs, measurements)]


def step_result_names(legs: list[Leg]) -> list[str]:
    """Every `<step>.<name>` result the steps themselves report."""
    return [f"{leg.step_name}.{n}" for leg in legs for n, _, _ in leg.exprs]
