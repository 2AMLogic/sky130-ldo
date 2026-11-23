"""Translate `sim/current-limit`'s three-leg chained deck into `klt sim` steps (issue #177).

PDK-free, standard library only. corner-run.py's local path runs
`sim/current-limit`'s deck as ONE ngspice process per corner: leg 1, a
cold-start `tran 5u 1.0m uic` (the initial-condition contract's first accepted
shape, uic + an EN edge -- sim/README.md, issue #171) with window-avg
`meas tran` cards; leg 2, two `alter`s (`rload` open, `rforce` down to 1 mOhm)
and a `dc vforce 0 1.75 0.125` sweep with `find i(vforce) at=` cards; leg 3,
`rload` restored and a second cold-start `tran 500n 3.0m uic` whose VFORCE PWL
applies the Vout = 0 short as an event at t = 1.001 ms and holds it to tstop,
again with window cards.

The legs are chained on purpose: the alters are cumulative (leg 3 keeps the
DC leg's `rforce = 1m`, so its pre-fault window is a live loop delivering into
a node held at the forcing source's 1.8 V), and every solve starts from the
previous one's solution. klt's `analysis_steps[]` sequence without `reset`
shares circuit AND solver state in exactly that way, so the faithful
translation is ONE three-step request per supply group -- not three
independent requests. Step names are fixed (`tran1`, `dc1`, `tran2`) so the
manifest's graded expressions -- already written plot-qualified as
`tran1.vout_50ma`, `1000*dc1.ilim_short`, `-1000*tran2.ish_avg`, ... -- carry
over VERBATIM as klt top-level derived measurements (`<step>.<card>`
references), graded by the harness's own bounds exactly as the local path
grades its `let meas_<name> = <expr>` lines.

This is deliberately NOT a SPICE interpreter: only the card forms below are
accepted and anything else is refused before any netlisting, submission or
local ngspice. The stimulus lives in the netlist, which is sent verbatim;
`check_netlist` pins the sources and load elements the legs depend on and
refuses anything that would alter the legs' semantics or fight klt's control
block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import batch_line_regulation as blr

STEP_NAMES = ("tran1", "dc1", "tran2")


class CurrentLimitTranslationError(ValueError):
    """The deck, a measurement or the netlist has no faithful step form."""


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_NUM = blr._NUM
_PROBE = r"[vi]\([A-Za-z0-9_.]+\)"  # node names may be hierarchical (v(xldo.cl_cmp))
# Cold-start legs: exactly `tran <tstep> <tstop> uic` (uic is load-bearing:
# without it ngspice's pre-transient operating-point solve reads VEN's DC
# value and starts the fully-enabled loop from nowhere -- the hazard #177
# fixed). No tstart/tmax, uic last, like every other cold-start adapter.
_TRAN_RE = re.compile(rf"^tran\s+({_NUM})\s+({_NUM})\s+uic$", re.IGNORECASE)
_ALTER_RE = re.compile(rf"^alter\s+({_IDENT})\s*=\s*({_NUM})$", re.IGNORECASE)
_DC_RE = re.compile(rf"^dc\s+({_IDENT})\s+({_NUM})\s+({_NUM})\s+({_NUM})$", re.IGNORECASE)
_MEAS_TRAN_RE = re.compile(
    rf"^meas\s+tran\s+({_IDENT})\s+(avg|min|max)\s+({_PROBE})\s+from=\s*{_NUM}\s+to=\s*{_NUM}$",
    re.IGNORECASE,
)
_MEAS_DC_RE = re.compile(
    rf"^meas\s+dc\s+({_IDENT})\s+find\s+i\(({_IDENT})\)\s+at=\s*{_NUM}$", re.IGNORECASE
)


def _num(text: str) -> float:
    """A SPICE number (`1e12`, `1m`, `36`) as the float klt's `alter` map takes."""
    m = re.fullmatch(rf"({_NUM})", text)
    if m is None:
        raise CurrentLimitTranslationError(f"unsupported alter value {text!r}")
    m2 = re.fullmatch(r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)([a-zA-Z]*)", text)
    scale = {"": 1.0, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "k": 1e3}
    if m2 is None or m2.group(2).lower() not in scale:
        raise CurrentLimitTranslationError(f"unsupported alter value {text!r}")
    return float(m2.group(1)) * scale[m2.group(2).lower()]


@dataclass
class Leg:
    """One translated leg: its fixed step name, alters, analysis and cards."""

    step_name: str
    kind: str  # "tran" | "dc"
    analysis_args: str
    alters: list[tuple[str, float]]  # (element, value), declaration order
    cards: list[tuple[str, str]]  # (name, deck line)


def _collect_cards(body: list[str], pos: int, meas_re: re.Pattern[str],
                   names: set[str]) -> tuple[list[tuple[str, str]], int]:
    cards: list[tuple[str, str]] = []
    while pos < len(body) and (mm := meas_re.match(body[pos])) is not None:
        name = mm.group(1)
        if name.lower() in names:
            raise CurrentLimitTranslationError(f"meas card name {name!r} is declared twice")
        names.add(name.lower())
        cards.append((name, body[pos]))
        pos += 1
    return cards, pos


def _expect(body: list[str], pos: int, pattern: re.Pattern[str], what: str):
    if pos >= len(body):
        raise CurrentLimitTranslationError(f"deck ends where {what} was expected")
    m = pattern.match(body[pos])
    if m is None:
        raise CurrentLimitTranslationError(f"expected {what}; got {body[pos]!r}")
    return m, pos + 1


def parse_deck(lines: list[str]) -> list[Leg]:
    """Parse `deck.analyses` into its three legs (comments ignored), or raise
    naming the first line with no faithful step form.

    Exactly: leg 1 = `tran <tstep> <tstop> uic` + window cards; leg 2 =
    `alter rload`, `alter rforce`, `dc vforce <a> <b> <step>` + find cards;
    leg 3 = `alter rload`, `tran <tstep> <tstop> uic` + window cards, in that
    order -- the chained shape the bench's claim and graded expressions name.
    """
    body = blr.deck_body(lines)
    if not body:
        raise CurrentLimitTranslationError("deck.analyses declares no analysis")
    names: set[str] = set()
    legs: list[Leg] = []

    # leg 1: cold-start tran at the netlist's own RLOAD/RFORCE (forcing branch absent)
    m, pos = _expect(body, 0, _TRAN_RE, "leg 1's cold-start `tran <tstep> <tstop> uic`")
    cards, pos = _collect_cards(body, pos, _MEAS_TRAN_RE, names)
    if not cards:
        raise CurrentLimitTranslationError("leg 1 declares no `meas tran` card")
    legs.append(Leg(STEP_NAMES[0], "tran", f"{m.group(1)} {m.group(2)} uic", [], cards))

    # leg 2: the DC limit characteristic, VOUT forced through RFORCE = 1 mOhm
    alters: list[tuple[str, float]] = []
    for what in ("alter rload = <ohms>", "alter rforce = <ohms>"):
        m, pos = _expect(body, pos, _ALTER_RE, f"leg 2's `{what}`")
        alters.append((m.group(1).lower(), _num(m.group(2))))
    if [a for a, _ in alters] != ["rload", "rforce"]:
        raise CurrentLimitTranslationError(f"leg 2's alters must be rload then rforce; got {alters}")
    m, pos = _expect(body, pos, _DC_RE, "leg 2's `dc vforce <start> <stop> <step>` sweep")
    if m.group(1).lower() != "vforce":
        raise CurrentLimitTranslationError(f"leg 2 sweeps {m.group(1)!r}, not vforce")
    cards, pos = _collect_cards(body, pos, _MEAS_DC_RE, names)
    if not cards:
        raise CurrentLimitTranslationError("leg 2 declares no `meas dc` card")
    for _, ln in cards:
        if _MEAS_DC_RE.match(ln).group(2).lower() != "vforce":
            raise CurrentLimitTranslationError(f"leg 2 card `{ln}` reads something other than i(vforce)")
    legs.append(Leg(STEP_NAMES[1], "dc", f"vforce {m.group(2)} {m.group(3)} {m.group(4)}", alters, cards))

    # leg 3: cold EN ramp with the held short (RFORCE stays at the DC leg's 1 mOhm:
    # cumulative alters are the point, so leg 3 alters ONLY rload back)
    m, pos = _expect(body, pos, _ALTER_RE, "leg 3's `alter rload = <ohms>`")
    if m.group(1).lower() != "rload":
        raise CurrentLimitTranslationError(f"leg 3 alters {m.group(1)!r}; only rload may change (rforce must stay at the DC leg's 1 mOhm)")
    alter3 = [(m.group(1).lower(), _num(m.group(2)))]
    m, pos = _expect(body, pos, _TRAN_RE, "leg 3's cold-start `tran <tstep> <tstop> uic`")
    cards, pos = _collect_cards(body, pos, _MEAS_TRAN_RE, names)
    if not cards:
        raise CurrentLimitTranslationError("leg 3 declares no `meas tran` card")
    legs.append(Leg(STEP_NAMES[2], "tran", f"{m.group(1)} {m.group(2)} uic", alter3, cards))

    if pos != len(body):
        raise CurrentLimitTranslationError(
            f"deck carries commands after leg 3: {body[pos:]!r} (exactly three chained legs)")
    if legs[0].analysis_args == legs[2].analysis_args:
        raise CurrentLimitTranslationError(
            "legs 1 and 3 declare the same tran grid; leg 3 must resolve the short edge (finer tstep)")
    return legs


def card_refs(legs: list[Leg]) -> set[str]:
    """Every `<step>.<card>` reference the deck's cards define."""
    return {f"{leg.step_name}.{name}".lower() for leg in legs for name, _ in leg.cards}


def check_measurements(legs: list[Leg], measurements: list[tuple[str, str, str]]) -> None:
    """Every graded expression must parse over the deck's `<step>.<card>`
    refs (blr's grammar: dotted refs, numbers, arithmetic, one line). klt
    re-validates the same references when the request is built."""
    refs = card_refs(legs)
    for name, expr, _unit in measurements:
        if not re.fullmatch(_IDENT, name):
            raise CurrentLimitTranslationError(f"measurement name {name!r} is not a vector name")
        blr._tokens(expr, refs)
        blr.evaluate(expr, {}, refs)


def chained_steps(legs: list[Leg]) -> list[dict]:
    """The `analysis_steps[]` sequence: one step per leg, in declaration order."""
    return [
        {
            "name": leg.step_name,
            **({"alter": {elem: value for elem, value in leg.alters}} if leg.alters else {}),
            "analysis": {"kind": leg.kind, "args": leg.analysis_args},
            "measurements": [
                {"name": name, "spice": "." + ln}  # card, leading dot restored
                for name, ln in leg.cards
            ],
        }
        for leg in legs
    ]


def check_netlist(body: list[str], stimulus: list[str]) -> None:
    """Refuse a request netlist whose pinned stimulus / load elements are not
    the validated baseline, or that carries a card that would alter the legs'
    semantics / fight klt's control block."""
    blr.check_netlist(body, stimulus, CurrentLimitTranslationError,
                      "a current-limit chained-step request")
