"""Translate the load-regulation endpoint deck into `klt sim` step requests (issue #381).

PDK-free, standard library only. corner-run.py's local path runs
`sim/load-regulation`'s deck as ONE ngspice process: two cold-start
`tran 10u 200m uic` points in sequence (no load, then `alter iload = 50m`),
each followed by `avg`/`min`/`max` `meas tran` cards over the settled
199-200 ms tail, with the load-regulation delta graded from plot-qualified
expressions (`tran2.x - tran1.y`) that span the two points.

Like the line-regulation adapter (sim/bin/batch_line_regulation.py, issue
#379) each endpoint becomes ONE single-step request named `tran<N>`, because a
klt step sequence has no `reset` and each cold-start endpoint must be
independent. The difference that matters here: VIN and full-rail EN are NOT
fixed literals. The testbench ties VIN to the corner supply (`'vsup'`) and
EN's PWL high level to `'vsup'` too, and the request netlist keeps
`.param vsup=<supply>` as the corner supply. So the only per-endpoint source
state is the load: the complete load (0 A or 50 mA) is written into each
request's netlist, so no request inherits another's state.

This is NOT a SPICE interpreter and shares only small helpers (the endpoint
dataclass, expression evaluator, measurement checks, response extraction and
netlist forbidden-card/one-definition checks) with the line-regulation module;
the admission rules here are separate and strict. Raw card values come back as
`tran<N>.<card>`; every graded expression, including the cross-endpoint
delta, is evaluated locally.
"""

from __future__ import annotations

import re

import batch_line_regulation as blr
from batch_line_regulation import (  # re-exported helpers
    Endpoint,
    EndpointTranslationError,
    card_refs,
    check_measurements,
    check_netlist,
    endpoint_step,
    evaluate,
    extract_endpoint_values,
    klt_result_name,
)

__all__ = [
    "Endpoint", "EndpointTranslationError", "card_refs", "check_measurements", "check_netlist",
    "endpoint_step", "evaluate", "extract_endpoint_values", "klt_result_name",
    "parse_deck", "endpoint_source_lines", "endpoint_body", "SUPPLY_LITERAL",
]

# VIN and EN's high level are the corner supply parameter, never a copied number.
SUPPLY_LITERAL = "'vsup'"
EXPECTED_KINDS = ["avg", "min", "max"]
EXPECTED_ENDPOINTS = 2

_NUM = blr._NUM
_TRAN_RE = blr._TRAN_RE
_MEAS_RE = blr._MEAS_RE
_ALTER_ILOAD_RE = re.compile(rf"^alter\s+iload\s*=\s*({_NUM})$", re.IGNORECASE)


def parse_deck(lines: list[str], baseline_iload: str) -> list[Endpoint]:
    """Parse `deck.analyses` into its two endpoints (comments ignored), or
    raise naming the first line with no faithful form.

    Point 1 is, in order, the cold-start `tran` then `avg|min|max` cards at the
    pinned netlist load (`baseline_iload`); point 2 is the same preceded by
    exactly one `alter iload = X` with X different from the baseline. There is
    no `set`, no `alter` of VIN or EN, and nothing else: any other line is
    refused.
    """
    body = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("*")]
    if not body:
        raise EndpointTranslationError("deck.analyses declares no analysis")
    endpoints: list[Endpoint] = []
    iload = baseline_iload
    pos = 0
    names: set[str] = set()
    while pos < len(body):
        n = len(endpoints) + 1
        if (m := _ALTER_ILOAD_RE.match(body[pos])) is not None:
            if n == 1:
                raise EndpointTranslationError(
                    "endpoint 1 must run at the netlist's own load; `alter iload` before the first tran"
                )
            iload = m.group(1)
            pos += 1
        elif n == 2:
            raise EndpointTranslationError(
                f"endpoint 2: expected `alter iload = <amps>`; got {body[pos]!r}"
            )
        if pos >= len(body) or (tm := _TRAN_RE.match(body[pos])) is None:
            got = body[pos] if pos < len(body) else "end of deck"
            raise EndpointTranslationError(f"endpoint {n}: expected the cold-start `tran <tstep> <tstop> uic`; got {got!r}")
        pos += 1
        cards: list[tuple[str, str, str]] = []
        while pos < len(body) and (mm := _MEAS_RE.match(body[pos])) is not None:
            name = mm.group(1)
            if name.lower() in names:
                raise EndpointTranslationError(f"meas card name {name!r} is declared twice")
            names.add(name.lower())
            cards.append((name, mm.group(2).lower(), body[pos]))
            pos += 1
        if [k for _, k, _ in cards] != EXPECTED_KINDS:
            raise EndpointTranslationError(
                f"endpoint {n}: expected one avg, one min and one max `meas tran` card in that order; "
                f"got {[k for _, k, _ in cards]}"
            )
        endpoints.append(Endpoint(n, SUPPLY_LITERAL, iload, f"{tm.group(1)} {tm.group(2)} uic", cards))
    if len(endpoints) != EXPECTED_ENDPOINTS:
        raise EndpointTranslationError(
            f"expected exactly {EXPECTED_ENDPOINTS} endpoints, deck declares {len(endpoints)}"
        )
    if endpoints[0].iload == endpoints[1].iload:
        raise EndpointTranslationError("the two endpoints must have different loads")
    return endpoints


def endpoint_source_lines(ep: Endpoint) -> dict[str, str]:
    """The endpoint's complete source state: element name -> netlist line. VIN
    and EN's high level are the corner supply; only the load differs."""
    return {
        "vvin": f"VVIN VIN 0 {SUPPLY_LITERAL}",
        "ven": f"VEN EN 0 dc 0 pwl(0 0 100u 0 101u {SUPPLY_LITERAL} 10 {SUPPLY_LITERAL})",
        "iload": f"{blr.LOAD_ELEMENT} VOUT 0 {ep.iload}",
    }


def endpoint_body(body: list[str], ep: Endpoint) -> list[str]:
    """The circuit body with VVIN, VEN and ILOAD replaced by the endpoint's
    source state (this module's supply-literal form)."""
    return blr.replace_sources(body, endpoint_source_lines(ep))


