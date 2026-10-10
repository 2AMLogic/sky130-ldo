"""Shared helpers for `layout/bin/gen-ldo-*.py` (issue #44).

Standard library only, matching every `layout/bin/` script's own convention.
`_merge_continuations()` was byte-identical (module docstring aside) across
`gen-ldo-reference-netlist.py` and `gen-ldo-blocks.py` before this module
existed -- pure extraction, no behavior change. `parse_x_card()` (issue #252)
does the same for the X-card token parsing the two generators repeated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Collection


def _merge_continuations(lines: list[str]) -> list[str]:
    """xschem wraps long device lines with a leading `+` continuation --
    merge those back onto the device line they belong to."""
    merged: list[str] = []
    for line in lines:
        if line.startswith("+") and merged:
            merged[-1] = merged[-1] + " " + line[1:].strip()
        else:
            merged.append(line)
    return merged


@dataclass(frozen=True)
class XCard:
    """One xschem `X<suffix> nets... <model> K=V ...` subcircuit card.

    ``model`` is ``None`` (and ``nets`` / ``params`` empty) when no token on
    the card is one of the caller's recognised models -- an explicit
    "unrecognised" result the caller reports in its own way.
    """

    suffix: str
    model: str | None
    nets: list[str]
    params: dict[str, str]


_X_CARD_RE = re.compile(r"^X(\S+)\s+(.*)$")


def parse_x_card(line: str, models: Collection[str]) -> XCard | None:
    """Tokenise an (already continuation-merged) X card.

    Returns ``None`` when ``line`` is not an X card at all (no ``X<name>``
    followed by whitespace). Otherwise the first token found in ``models``
    is the model; tokens before it are the nets and later ``K=V`` tokens are
    the parameters, kept as raw strings (split on the first ``=`` only;
    tokens without ``=`` are ignored). Which models are recognised, and what
    they map to, stays with the caller.
    """
    m = _X_CARD_RE.match(line)
    if not m:
        return None
    suffix, rest = m.group(1), m.group(2)
    toks = rest.split()
    model_idx = next((i for i, t in enumerate(toks) if t in models), None)
    if model_idx is None:
        return XCard(suffix, None, [], {})
    params: dict[str, str] = {}
    for tok in toks[model_idx + 1 :]:
        if "=" in tok:
            key, value = tok.split("=", 1)
            params[key] = value
    return XCard(suffix, toks[model_idx], toks[:model_idx], params)
