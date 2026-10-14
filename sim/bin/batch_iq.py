"""Translate the iq endpoint deck into `klt sim` step requests (issue #213).

PDK-free, standard library only. corner-run.py's local path runs `sim/iq`'s
deck as ONE ngspice process: two cold-start `tran 10u 200m uic` points in
sequence (no load, then `alter iload = 50m`), each followed by two `avg`
`meas tran` cards over the settled 199-200 ms tail: `v(vout)` and the VIN
supply current `i(vvin)`. The graded Iq figures are affine functions of the
raw `i(vvin)` card (`-1e6*x`, `1e6*(-x - 0.05)`).

This is the load-regulation adapter's shape (sim/bin/batch_load_regulation.py,
issue #381): one single-step request per endpoint, named `tran<N>`, VIN and
full-rail EN tied to the corner supply (`'vsup'`), only the load differing per
request and travelling in the request netlist. The differences are the card
set (exactly one `avg v(vout)` and one `avg i(vvin)` per endpoint, no tail
min/max) and that a card's probe may be a branch current. Source-state helpers
are shared with the load-regulation module; all grading is done locally from
the raw `tran<N>.<card>` values.
"""

from __future__ import annotations

import re

import batch_line_regulation as blr
from batch_line_regulation import Endpoint, EndpointTranslationError
from batch_load_regulation import (  # shared source state (identical stimulus)
    SUPPLY_LITERAL,
    endpoint_body,
    endpoint_source_lines,
)

__all__ = ["parse_deck", "endpoint_source_lines", "endpoint_body", "SUPPLY_LITERAL"]

EXPECTED_ENDPOINTS = 2
# per endpoint, in order: (kind, probe)
EXPECTED_CARDS = [("avg", "v(vout)"), ("avg", "i(vvin)")]

_NUM = blr._NUM
_IDENT = blr._IDENT
_TRAN_RE = blr._TRAN_RE
_ALTER_ILOAD_RE = re.compile(rf"^alter\s+iload\s*=\s*({_NUM})$", re.IGNORECASE)
_MEAS_RE = re.compile(
    rf"^meas\s+tran\s+({_IDENT})\s+(avg)\s+((?:v|i)\([A-Za-z0-9_]+\))\s+from=\s*({_NUM})\s+to=\s*({_NUM})$",
    re.IGNORECASE,
)


def parse_deck(lines: list[str], baseline_iload: str) -> list[Endpoint]:
    """Parse `deck.analyses` into its two endpoints (comments ignored), or
    raise naming the first line with no faithful form."""
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
            raise EndpointTranslationError(f"endpoint 2: expected `alter iload = <amps>`; got {body[pos]!r}")
        if pos >= len(body) or (tm := _TRAN_RE.match(body[pos])) is None:
            got = body[pos] if pos < len(body) else "end of deck"
            raise EndpointTranslationError(f"endpoint {n}: expected the cold-start `tran <tstep> <tstop> uic`; got {got!r}")
        pos += 1
        cards: list[tuple[str, str, str]] = []
        probes: list[tuple[str, str]] = []
        while pos < len(body) and (mm := _MEAS_RE.match(body[pos])) is not None:
            name = mm.group(1)
            if name.lower() in names:
                raise EndpointTranslationError(f"meas card name {name!r} is declared twice")
            names.add(name.lower())
            cards.append((name, mm.group(2).lower(), body[pos]))
            probes.append((mm.group(2).lower(), mm.group(3).lower()))
            pos += 1
        if probes != EXPECTED_CARDS:
            raise EndpointTranslationError(
                f"endpoint {n}: expected `avg v(vout)` then `avg i(vvin)` meas cards; got {probes}"
            )
        endpoints.append(Endpoint(n, SUPPLY_LITERAL, iload, f"{tm.group(1)} {tm.group(2)} uic", cards))
    if len(endpoints) != EXPECTED_ENDPOINTS:
        raise EndpointTranslationError(f"expected exactly {EXPECTED_ENDPOINTS} endpoints, deck declares {len(endpoints)}")
    if endpoints[0].iload == endpoints[1].iload:
        raise EndpointTranslationError("the two endpoints must have different loads")
    return endpoints
