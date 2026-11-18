"""Translate a `window_grid` leg block into a `klt sim` step request (issue #326).

PDK-free, standard library only. corner-run.py's local path walks every
COUT/ESR leg of `window_grid.leg_analyses` inside ONE ngspice deck (`reset`,
`save all`, the leg's `alter` cards, one `tran`, `meas tran` cards and `let`
helpers). A `klt sim` request cannot carry that block verbatim: klt owns the
deck's `.control` block. What it can carry is `analysis_steps[]` (klt
>= 0.7): a named step with element `alter` overrides, one analysis, and
step-scoped measurements that are either verbatim `.meas` cards or single-line
`expr` evaluated in that step's own plot.

This module maps one leg onto one single-step request body:

* `reset` -> one request per leg. Each leg is its own `klt sim` request, so
  each (corner, leg) is a separate ngspice process: nothing (circuit state,
  solver state, altered values) can carry over between legs. That is a
  stronger isolation than the local deck's in-process `reset`, never a weaker
  one. klt's step sequence itself has no `reset` between steps, which is why
  legs are NOT packed as several steps of one request.
* `save all` -> klt's generated control block already opens with `save all`.
* `alter <elem> = {placeholder}` -> the step's `alter` map, with the same
  numeric value the local path substitutes.
* `tran <args>` -> the step's analysis (exactly one per leg).
* `meas tran <name> ...` -> a step measurement whose `spice` is the card with
  its leading dot restored (klt emits it back as the same `meas` command).
* `let <name> = <expr>` helpers -> inlined, parenthesised, into every
  measurement expression that uses them (a klt step measurement is graded
  and must be a scalar, so ungraded vector helpers cannot be declared).
* `wrdata {corner_id}.{leg_id}.trace.dat <signal>` -> NO step form: the
  `{corner_id}` placeholder cannot be instantiated (one request covers many
  corners) and klt owns the control block. Recognised and REMEMBERED as the
  leg's trace signal, never emitted: a trace-returning experiment (issue
  #336 startup, `ramp_traces` in `_batch_backend.BATCH_ALLOWLIST`) runs each
  leg as its own scalar-analysis request with `options.waveforms`, and the
  harness rebuilds the identical `.trace.dat` from the returned waveform
  artifact (see `batch_startup_ramp.py`).

Anything else in the template is refused rather than guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import batch_line_regulation as blr


class TranslationError(ValueError):
    """The leg template (or a measurement) has no faithful klt step form."""


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_ALTER_RE = re.compile(rf"^alter\s+([A-Za-z][A-Za-z0-9_]*)\s*=\s*\{{({_IDENT})\}}$", re.IGNORECASE)
_TRAN_RE = re.compile(r"^tran\s+(\S.*)$", re.IGNORECASE)
_MEAS_RE = re.compile(rf"^meas\s+tran\s+({_IDENT})\s+\S.*$", re.IGNORECASE)
_LET_RE = re.compile(rf"^let\s+({_IDENT})\s*=\s*(\S.*)$", re.IGNORECASE)
# The per-leg trace dump (issue #336 startup): `wrdata
# {corner_id}.{leg_id}.trace.dat <signal>`. It has NO klt step form (a step's
# control block is klt's own), and its `{corner_id}` placeholder cannot even be
# instantiated — one klt request covers 15 corners. A trace-returning request
# carries the signal back as each corner's waveform artifact
# (`options.waveforms`, klayout-tools#3488/#3360) instead; the signal is
# remembered on the template so the request builder can pin the artifact's
# variable and the harness reconstructs the same `.trace.dat` locally.
_WRDATA_RE = re.compile(
    r"^wrdata\s+\{corner_id\}\.\{leg_id\}\.trace\.dat\s+(\S+)\s*$", re.IGNORECASE
)
# A signal accessor (v(x), i(vdd), vdb(out)): its argument is a node/branch
# name, never a helper reference, so it is passed through untouched.
_SIGNAL_RE = re.compile(r"\b[vi][a-z]{0,2}\s*\([^()]*\)", re.IGNORECASE)
# A bare identifier that is not a function call, not plot-qualified and not
# the unit suffix of a number (`1.0m`, `1e-18`: \b fails between digit+letter).
_BARE_RE = re.compile(rf"(?<![\w.$@{{}}])({_IDENT})\b(?!\s*\()")


@dataclass
class LegTemplate:
    alters: list[tuple[str, str]]  # (element, placeholder), declared order
    tran_args: str
    meas_cards: list[tuple[str, str]]  # (name, ".meas tran ..." card)
    lets: dict[str, str] = field(default_factory=dict)  # name -> fully inlined expr
    wrdata_signal: str | None = None  # per-leg trace signal (issue #336), never emitted


def _inline(expr: str, lets: dict[str, str]) -> str:
    """Replace every bare reference to a helper `let` with its (already
    inlined) expression in parentheses; signal accessors are left alone."""
    out, pos = [], 0
    for sig in _SIGNAL_RE.finditer(expr):
        out.append(_inline_plain(expr[pos:sig.start()], lets))
        out.append(sig.group(0))
        pos = sig.end()
    out.append(_inline_plain(expr[pos:], lets))
    return "".join(out)


def _inline_plain(text: str, lets: dict[str, str]) -> str:
    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        return f"({lets[name]})" if name in lets else name

    return _BARE_RE.sub(sub, text)


def parse_leg_template(lines: list[str]) -> LegTemplate:
    """Parse `window_grid.leg_analyses` into its translatable parts, or raise
    TranslationError naming the first line that has no faithful step form."""
    body = blr.deck_body(lines)
    if body[:2] != ["reset", "save all"]:
        raise TranslationError(
            "leg_analyses must open with `reset` then `save all` (each leg becomes its own "
            f"klt request, i.e. its own ngspice process); got {body[:2]!r}"
        )
    alters: list[tuple[str, str]] = []
    tran_args: str | None = None
    meas_cards: list[tuple[str, str]] = []
    lets: dict[str, str] = {}
    template_wrdata = [None]  # boxed: the loop's wrdata branch assigns it
    for ln in body[2:]:
        if (m := _ALTER_RE.match(ln)) is not None:
            if tran_args is not None:
                raise TranslationError(f"`{ln}` comes after the leg's tran; alters must precede it")
            alters.append((m.group(1), m.group(2)))
        elif (m := _TRAN_RE.match(ln)) is not None:
            if tran_args is not None:
                raise TranslationError("a leg may run exactly one tran (klt step: one analysis)")
            tran_args = m.group(1).strip()
        elif (m := _MEAS_RE.match(ln)) is not None:
            if tran_args is None:
                raise TranslationError(f"`{ln}` precedes the leg's tran")
            meas_cards.append((m.group(1), "." + ln))
        elif (m := _WRDATA_RE.match(ln)) is not None:
            if tran_args is None:
                raise TranslationError(f"`{ln}` precedes the leg's tran")
            if template_wrdata[0] is not None:
                raise TranslationError("a leg may dump exactly one wrdata trace")
            signal = m.group(1)
            if _SIGNAL_RE.fullmatch(signal) is None:
                raise TranslationError(
                    f"wrdata signal `{signal}` is not a single signal accessor "
                    "(v(x)/i(vdd)-shaped); refusing to guess what to return"
                )
            template_wrdata[0] = signal
        elif (m := _LET_RE.match(ln)) is not None:
            if tran_args is None:
                raise TranslationError(f"`{ln}` precedes the leg's tran")
            lets[m.group(1)] = _inline(m.group(2).strip(), lets)
        else:
            raise TranslationError(
                f"leg_analyses line `{ln}` has no klt step form (supported: reset, save all, "
                "alter <elem> = {placeholder}, one tran, meas tran, let, one wrdata trace)"
            )
    if tran_args is None:
        raise TranslationError("leg_analyses declares no tran")
    if not alters:
        raise TranslationError("leg_analyses declares no alter cards")
    names = [n.lower() for n, _ in meas_cards] + [n.lower() for n in lets]
    if len(set(names)) != len(names):
        raise TranslationError("leg_analyses reuses a meas/let name")
    return LegTemplate(alters, tran_args, meas_cards, lets, template_wrdata[0])


def leg_step(
    template: LegTemplate,
    leg_id: str,
    values: dict[str, float],
    measurements: list[tuple[str, str, str]],
) -> dict:
    """One `analysis_steps[]` entry for one leg.

    `values` maps each alter placeholder to its numeric value; `measurements`
    is the leg's graded measurements as (template name, expr, unit). The step
    is named after the leg, so klt reports `<leg>.<template name>`.
    """
    alter = {}
    for elem, placeholder in template.alters:
        if placeholder not in values:
            raise TranslationError(f"leg {leg_id}: no value for alter placeholder {{{placeholder}}}")
        alter[elem] = float(values[placeholder])
    reserved = {n.lower() for n, _ in template.meas_cards}
    steps_meas = [{"name": n, "spice": card} for n, card in template.meas_cards]
    for name, expr, unit in measurements:
        if name.lower() in reserved:
            raise TranslationError(f"measurement {name!r} collides with a leg meas card name")
        inlined = _inline(expr, template.lets)
        if "\n" in inlined or "\r" in inlined:
            raise TranslationError(f"measurement {name!r}: expression must be one line")
        steps_meas.append({"name": name, "expr": inlined, "unit": unit})
    return {
        "name": leg_id,
        "analysis": {"kind": "tran", "args": template.tran_args},
        "alter": alter,
        "measurements": steps_meas,
    }
