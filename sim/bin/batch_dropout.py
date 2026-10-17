"""Translate the cold-start crossing deck into a `klt sim` step request (issue #374).

PDK-free, standard library only. corner-run.py's local path runs
`sim/dropout-vs-load`'s deck as ngspice control commands: ONE cold-start
`tran <tstep> <tstop> uic`, then `meas tran` cards (a `find ... when ...`
crossing and a window `avg`), then `let meas_<name> = <expr>`. A `klt sim`
request cannot carry that block verbatim (klt owns the deck's `.control`
block), but klt >= 0.7's `analysis_steps[]` reproduces it command for command
in a single step:

* `tran 10u 14m uic` -> the step's analysis, `args` passed verbatim (so the
  `uic` cold start and the time grid are unchanged). There is no operating
  point solve in either deck.
* `meas tran <name> ...` -> a step measurement whose `spice` is the card with
  its leading dot restored; klt emits it back as the same `meas tran ...`
  control command, evaluated against that step's own plot, right after its
  analysis -- exactly where the local deck evaluates it.
* a graded measurement `<name> = <expr>` -> a step `expr` measurement (klt
  emits `let <name> = <expr>` in the same plot), or, when the measurement IS a
  card (`name == expr == card name`), the card's own step result.

The stimulus (VIN ramp, EN edge, load step) lives in the netlist, which is
sent verbatim; `check_netlist` pins it and refuses anything that would alter
the cold-start initialisation or fight klt's control block.

This is deliberately NOT a SPICE interpreter: only the two card forms below
are accepted, the expression grammar is identifiers-that-name-a-card plus
numbers and arithmetic, and anything else is refused before submission.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import batch_line_regulation as blr

STEP_NAME = "dropout"


class DropoutTranslationError(ValueError):
    """The deck, a measurement or the netlist has no faithful step form."""


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?[a-zA-Z]*"
_NODE = r"v\([A-Za-z0-9_]+\)"
# Cold start: exactly `tran <tstep> <tstop> uic` (no tstart/tmax, uic last).
_TRAN_RE = re.compile(rf"^tran\s+({_NUM})\s+({_NUM})\s+uic$", re.IGNORECASE)
_MEAS_RE = re.compile(rf"^meas\s+tran\s+({_IDENT})\s+(\S.*)$", re.IGNORECASE)
# The two accepted card bodies. A crossing must name its edge and its
# search delay explicitly (`fall=1 td=6m`): both are part of the dropout
# definition (the first fall through the threshold after the start-up ramp).
_CROSSING_RE = re.compile(
    rf"^find\s+{_NODE}\s+when\s+{_NODE}\s*=\s*{_NUM}\s+(?:rise|fall|cross)=\d+\s+td=\s*{_NUM}$",
    re.IGNORECASE,
)
_AVG_RE = re.compile(rf"^avg\s+{_NODE}\s+from=\s*{_NUM}\s+to=\s*{_NUM}$", re.IGNORECASE)
# Expression grammar: card names, numbers, + - * / ( ) and whitespace.
_EXPR_TOKEN_RE = re.compile(rf"\s*(?:({_IDENT})|({_NUM})|([-+*/()]))")


@dataclass
class ColdStartDeck:
    tran_args: str
    cards: list[tuple[str, str]]  # (name, "meas tran ..." control text)
    crossing: list[str]  # names of the crossing cards


def parse_deck(lines: list[str]) -> ColdStartDeck:
    """Parse `deck.analyses` (comments ignored) into its translatable parts, or
    raise DropoutTranslationError naming the first line with no step form."""
    body = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("*")]
    if not body:
        raise DropoutTranslationError("deck.analyses declares no analysis")
    m = _TRAN_RE.match(body[0])
    if m is None:
        raise DropoutTranslationError(
            f"the first deck command must be the cold-start `tran <tstep> <tstop> uic`; got {body[0]!r}"
        )
    tran_args = f"{m.group(1)} {m.group(2)} uic"
    cards: list[tuple[str, str]] = []
    crossing: list[str] = []
    for ln in body[1:]:
        mm = _MEAS_RE.match(ln)
        if mm is None:
            raise DropoutTranslationError(
                f"deck line `{ln}` has no step form (supported after the tran: "
                "`meas tran <name> find v(a) when v(b)=X fall|rise|cross=N td=T` and "
                "`meas tran <name> avg v(a) from=T1 to=T2`)"
            )
        name, rest = mm.group(1), mm.group(2).strip()
        if _CROSSING_RE.match(rest):
            crossing.append(name)
        elif not _AVG_RE.match(rest):
            raise DropoutTranslationError(f"meas card `{ln}` is neither a td-delayed crossing nor a window avg")
        if name.lower() in {n.lower() for n, _ in cards}:
            raise DropoutTranslationError(f"meas card name {name!r} is declared twice")
        cards.append((name, ln))
    if not crossing:
        raise DropoutTranslationError("deck declares no crossing (`find ... when ...`) card")
    return ColdStartDeck(tran_args, cards, crossing)


def _expr_refs(expr: str, card_names: set[str]) -> list[str]:
    """Card names an expression references; refuses any other token."""
    refs, pos, text = [], 0, expr.strip()
    if not text or "\n" in text or "\r" in text:
        raise DropoutTranslationError(f"expression {expr!r} must be one non-empty line")
    while pos < len(text):
        m = _EXPR_TOKEN_RE.match(text, pos)
        if m is None or m.end() == pos:
            raise DropoutTranslationError(f"expression {expr!r}: unsupported token at {text[pos:]!r}")
        ident = m.group(1)
        if ident is not None:
            if ident.lower() not in card_names:
                raise DropoutTranslationError(
                    f"expression {expr!r} references {ident!r}, which is not a meas card of the deck"
                )
            refs.append(ident)
        pos = m.end()
    if not refs:
        raise DropoutTranslationError(f"expression {expr!r} references no meas card")
    return refs


def dropout_step(deck: ColdStartDeck, measurements: list[tuple[str, str, str]]) -> dict:
    """The single `analysis_steps[]` entry for the cold-start deck.

    `measurements` is the graded manifest measurements as (name, expr, unit).
    klt reports each as `<STEP_NAME>.<name>`.
    """
    card_names = {n.lower(): n for n, _ in deck.cards}
    direct: dict[str, str] = {}
    derived: list[dict] = []
    for name, expr, unit in measurements:
        if not re.fullmatch(_IDENT, name):
            raise DropoutTranslationError(f"measurement name {name!r} is not an ngspice vector name")
        if name.lower() in card_names:
            if expr.strip() != name:
                raise DropoutTranslationError(
                    f"measurement {name!r} reuses a meas card name with a different expression "
                    f"({expr!r}); only an identity measurement may share a card's name"
                )
            direct[name.lower()] = unit
            continue
        _expr_refs(expr, set(card_names))
        derived.append({"name": name, "expr": expr.strip(), "unit": unit})
    steps_meas = []
    for name, ln in deck.cards:
        entry = {"name": name, "spice": "." + ln}
        if name.lower() in direct:
            entry["unit"] = direct[name.lower()]
        steps_meas.append(entry)
    return {
        "name": STEP_NAME,
        "analysis": {"kind": "tran", "args": deck.tran_args},
        "measurements": steps_meas + derived,
    }


def klt_result_name(name: str) -> str:
    """The name klt reports a step measurement under."""
    return f"{STEP_NAME}.{name}"


def check_netlist(body: list[str], stimulus: list[str]) -> None:
    """Refuse a request netlist whose stimulus is not the pinned one, or that
    carries a card that would alter the cold start / fight klt's control."""
    blr.check_netlist(body, stimulus, DropoutTranslationError, "a cold-start crossing request")


# klt's batch backend (klt 0.7 sim_batch): status.json state "done" is a clean
# finish; a "failed" job whose `klt sim` exit is 0/3/4 still ran and reported.
_REMOTE_RAN_EXIT_CODES = (0, 3, 4)


def remote_completion_problem(response: dict) -> str | None:
    """None if `environment.remote` shows one finished, compatible batch job;
    otherwise why the response cannot be trusted as a completed remote run."""
    env = response.get("environment") if isinstance(response, dict) else None
    remote = env.get("remote") if isinstance(env, dict) else None
    if not isinstance(remote, dict):
        return "response carries no environment.remote block (not a batch run)"
    if not remote.get("job_id"):
        return "environment.remote names no job id"
    # Only a runner proven to run this client's klt counts: under "mismatch"
    # or "unknown" klt itself warns that request options may have been
    # ignored -- including `options.ngspice_init` (the solver settings) and
    # `expr` measurements (2AMLogic/klayout-tools#2917) -- so the numbers
    # would not be the local deck's.
    compat = remote.get("runner_compatibility")
    if compat != "match":
        return (
            f"runner_compatibility is {compat!r}, not 'match' "
            f"({remote.get('runner_compatibility_warning') or 'runner klt version not established'})"
        )
    state = remote.get("state")
    try:
        rc = int(str(remote.get("exit_code")).strip())
    except (TypeError, ValueError):
        rc = None
    if state == "done" or (state == "failed" and rc in _REMOTE_RAN_EXIT_CODES):
        return None
    return (
        f"remote job {remote.get('job_id')} state {state!r} (exit_code {remote.get('exit_code')!r}) "
        "is not a completed run"
    )


def corner_diagnostic_problems(corner: dict) -> list[str]:
    """klt-side error diagnostics on one corner (a failed step, an engine
    error): each is a reason the corner cannot PASS."""
    out = []
    diags = corner.get("diagnostics")
    if diags is None:
        return out
    if not isinstance(diags, list):
        return [f"klt diagnostics is not a list ({type(diags).__name__})"]
    for d in diags:
        if not isinstance(d, dict):
            out.append("malformed klt diagnostic entry")
        elif d.get("severity") == "error" or d.get("code") == "step_failed":
            out.append(f"klt diagnostic {d.get('code') or 'error'}: {str(d.get('message') or '')[:200]}")
    return out
