"""Translate `sim/current-limit`'s three-leg chained deck into `klt sim` steps (issue #177).

PDK-free, standard library only. corner-run.py's local path runs
`sim/current-limit`'s deck as ONE ngspice process per corner: leg 2, two
`alter`s (`rload` open, `rforce` down to 1 mOhm) and a `dc vforce 0 1.75
0.125` sweep with `find i(vforce) at=` cards; leg 1, a cold-start
`tran 5u 1.0m uic` (the initial-condition contract's first accepted shape,
uic + an EN edge -- sim/README.md, issue #171) with window-avg `meas tran`
cards; leg 3, `rforce` back at 1 mOhm and a second cold-start
`tran 500n 3.0m uic` whose VFORCE PWL applies the Vout = 0 short as an event
at t = 1.001 ms and holds it to tstop, again with window cards.

Leg 2 LEADS the deck (issue #647): it is the seeded analysis -- the
testbench's IC_SEED `.nodeset` card (the contract's seed shape for a `dc`
analysis, #178/#189 precedent) must be the guess the sweep's first solve
starts from, which measured clean at every probed corner only in this
position (chained after leg 1's transient, fs_125c_3.63v still tripped the
#171 gate). The two `tran ... uic` legs are order-independent by
construction (`uic` starts every node at 0) and each leg's element values
are restored with `alter` before it runs. The conceptual leg numbering
(1 = 50 mA point, 2 = DC characteristic, 3 = held short) is unchanged; only
the run order moved.

The legs are chained on purpose: the alters are cumulative in run order
(leg 1 restores the netlist's own RLOAD/RFORCE after the DC leg walked
them; leg 3 keeps RFORCE at 1 mOhm so its pre-fault window is a live loop
delivering into a node held at the forcing source's 1.8 V), and solver
state is shared between steps. klt's `analysis_steps[]` sequence without
`reset` shares circuit AND solver state in exactly that way, so the
faithful translation is ONE three-step request per supply group -- not
three independent requests. Step names are fixed (`dc1`, `tran1`,
`tran2` -- named by analysis, not by position) so the manifest's graded
expressions -- already written plot-qualified as `tran1.vout_50ma`,
`1000*dc1.ilim_short`, `-1000*tran2.ish_avg`, ... -- carry over VERBATIM as
klt top-level derived measurements (`<step>.<card>` references), graded by
the harness's own bounds exactly as the local path grades its
`let meas_<name> = <expr>` lines.

This is deliberately NOT a SPICE interpreter: only the card forms below are
accepted and anything else is refused before any netlisting, submission or
local ngspice. The stimulus lives in the netlist, which is sent verbatim;
`blr.check_netlist` (called by the batch backend,
`_batch_backend._check_pinned_netlist`) pins the sources and load elements
the legs depend on, pins the IC_SEED `.nodeset` card the seeded sweep depends
on (issue #647), and refuses anything else that would alter the legs'
semantics or fight klt's control block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import batch_line_regulation as blr

# Fixed by content, not position (the dc leg leads the deck, issue #647):
# the DC characteristic's step is dc1; the two cold-start transients keep
# tran1 (leg 1) and tran2 (leg 3), assigned in encounter order, so the
# manifest's plot-qualified graded expressions carry over verbatim.
DC_STEP_NAME = "dc1"
TRAN_STEP_NAMES = ("tran1", "tran2")

# The testbench's IC_SEED card, pinned verbatim (issue #647): the seeded dc
# leg's #171 conformance is measured WITH this guess, so the batch netlist
# must carry exactly it -- a different seed is a different experiment and
# refuses until re-validated. Values are the measured settled held-short
# state at tt/27C/vsup=3.30V (see the testbench header); `{vsup-x}` forms
# ride the request's own fixed `.param vsup` per supply group.
NODESET_CARD = (
    ".nodeset v(VOUT)=0.00015 v(xldo.FB)=0.0001 v(xldo.N_FBB)=0.00005 "
    "v(xldo.EA_OUT)={vsup-1.6915} v(xldo.EA_CZ)={vsup-1.6915} "
    "v(xldo.EA_TAIL)=1.6169 v(xldo.SS)={vsup-0.0001} "
    "v(xldo.BIASP)={vsup-1.0637} v(xldo.NB)=0.8641 "
    "v(xldo.CL_CMP)={vsup-0.9038} v(xldo.CL_SNS)=0.9447 v(xldo.AMP_ENN)=0.0087"
)


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

    Exactly, in run order (issue #647: the seeded dc leg leads): leg 2 =
    `alter rload`, `alter rforce`, `dc vforce <a> <b> <step>` + find cards;
    leg 1 = `alter rload`, `alter rforce`, `tran <tstep> <tstop> uic` +
    window cards; leg 3 = `alter rforce`, `tran <tstep> <tstop> uic` +
    window cards -- the chained shape the bench's claim and graded
    expressions name. Step names follow content (`dc1`; `tran1`/`tran2` in
    encounter order), so the manifest's plot-qualified expressions are
    position-independent.
    """
    body = blr.deck_body(lines)
    if not body:
        raise CurrentLimitTranslationError("deck.analyses declares no analysis")
    names: set[str] = set()
    legs: list[Leg] = []

    # leg 2 (first in run order): the seeded DC limit characteristic, VOUT
    # forced through RFORCE = 1 mOhm, RLOAD open
    alters: list[tuple[str, float]] = []
    pos = 0
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
    legs.append(Leg(DC_STEP_NAME, "dc", f"vforce {m.group(2)} {m.group(3)} {m.group(4)}", alters, cards))

    # leg 1 (second): the 50 mA cold-start tran at the netlist's own
    # RLOAD/RFORCE (forcing branch absent again after the DC leg walked both)
    alters1: list[tuple[str, float]] = []
    for what in ("alter rload = <ohms>", "alter rforce = <ohms>"):
        m, pos = _expect(body, pos, _ALTER_RE, f"leg 1's `{what}`")
        alters1.append((m.group(1).lower(), _num(m.group(2))))
    if [a for a, _ in alters1] != ["rload", "rforce"]:
        raise CurrentLimitTranslationError(f"leg 1's alters must be rload then rforce; got {alters1}")
    m, pos = _expect(body, pos, _TRAN_RE, "leg 1's cold-start `tran <tstep> <tstop> uic`")
    cards, pos = _collect_cards(body, pos, _MEAS_TRAN_RE, names)
    if not cards:
        raise CurrentLimitTranslationError("leg 1 declares no `meas tran` card")
    legs.append(Leg(TRAN_STEP_NAMES[0], "tran", f"{m.group(1)} {m.group(2)} uic", alters1, cards))

    # leg 3 (last): cold EN ramp with the held short (RLOAD already 36 from
    # leg 1; RFORCE returns to the DC leg's 1 mOhm -- the short is applied
    # through the forcing branch, so it must conduct)
    m, pos = _expect(body, pos, _ALTER_RE, "leg 3's `alter rforce = <ohms>`")
    if m.group(1).lower() != "rforce":
        raise CurrentLimitTranslationError(f"leg 3 alters {m.group(1)!r}; only rforce may change (rload stays at leg 1's 36 Ohm)")
    alter3 = [(m.group(1).lower(), _num(m.group(2)))]
    m, pos = _expect(body, pos, _TRAN_RE, "leg 3's cold-start `tran <tstep> <tstop> uic`")
    cards, pos = _collect_cards(body, pos, _MEAS_TRAN_RE, names)
    if not cards:
        raise CurrentLimitTranslationError("leg 3 declares no `meas tran` card")
    legs.append(Leg(TRAN_STEP_NAMES[1], "tran", f"{m.group(1)} {m.group(2)} uic", alter3, cards))

    if pos != len(body):
        raise CurrentLimitTranslationError(
            f"deck carries commands after leg 3: {body[pos:]!r} (exactly three chained legs)")
    if legs[1].analysis_args == legs[2].analysis_args:
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
