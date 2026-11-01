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
    parse_two_load_endpoints,
)

__all__ = ["parse_deck", "endpoint_source_lines", "endpoint_body", "SUPPLY_LITERAL"]

EXPECTED_ENDPOINTS = 2
# per endpoint, in order: (kind, probe)
EXPECTED_CARDS = [("avg", "v(vout)"), ("avg", "i(vvin)")]

_NUM = blr._NUM
_IDENT = blr._IDENT
_MEAS_RE = re.compile(
    rf"^meas\s+tran\s+({_IDENT})\s+(avg)\s+((?:v|i)\([A-Za-z0-9_]+\))\s+from=\s*({_NUM})\s+to=\s*({_NUM})$",
    re.IGNORECASE,
)


def _check_iq_cards(n: int, cards: list[tuple[str, str, str]]) -> None:
    """Per-endpoint card check: `avg v(vout)` then `avg i(vvin)`."""
    probes = [(kind, _MEAS_RE.match(line).group(3).lower()) for _, kind, line in cards]
    if probes != EXPECTED_CARDS:
        raise EndpointTranslationError(
            f"endpoint {n}: expected `avg v(vout)` then `avg i(vvin)` meas cards; got {probes}"
        )


def parse_deck(lines: list[str], baseline_iload: str) -> list[Endpoint]:
    """Parse `deck.analyses` into its two endpoints (comments ignored), or
    raise naming the first line with no faithful form."""
    return parse_two_load_endpoints(lines, baseline_iload, _MEAS_RE, _check_iq_cards)
