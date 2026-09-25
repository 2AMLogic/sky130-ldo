#!/usr/bin/env python3
"""Read the ratified electrical constants the layout flow needs out of
`spec/target-spec.md` itself, rather than transcribing them into a layout
script (issue #154).

Why parse the spec instead of writing the numbers down
------------------------------------------------------
`gen-ldo-blocks.py` sizes the block's power conductors from the current they
actually carry. That current, and the voltage budget the resulting IR drop is
allowed to eat into, are *spec* quantities -- they belong to
`spec/target-spec.md`'s ratified table, which is the repo's gate (root
`CLAUDE.md`: "The spec is a gate"). A hand-copied `FULL_LOAD_A = 0.05` in a
layout script is exactly the drift class issue #33 removed from this flow's
device table: it would keep passing silently after a decision record moved the
number.

So this module reads the two rows the layout needs straight out of the
ratified table, the same way `gen-ldo-reference-netlist.py` reads its resistor
sheet-rho constants out of `klt`'s own extraction deck. Every failure to find
a row, or to parse it, is a hard error -- never a default.

Rows read
---------
* **Load** -- the ratified load-current range (`0-50 mA`); its upper end is
  the current every load-current conductor in the block must carry.
* **Dropout @ 50 mA** -- the ratified dropout budget (`< 300 mV`), and, from
  the row's own label, the load current that budget is stated at. That label
  current is cross-checked against the Load row's upper end, so a future spec
  edit that moves one without the other fails here instead of silently
  producing a conductor sized against a stale pair.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Unit suffixes accepted in a spec cell, as a multiplier into SI base units.
_SI_PREFIX = {
    "": 1.0,
    "m": 1e-3,
    "u": 1e-6,
    "µ": 1e-6,
    "n": 1e-9,
    "k": 1e3,
}

#: Both the ASCII hyphen and the en dash the spec table actually uses.
_RANGE_DASH = r"[-–—]"


class SpecError(RuntimeError):
    """The ratified spec table does not carry a row this layout flow needs."""


@dataclass(frozen=True)
class SpecConstants:
    """The ratified numbers `gen-ldo-blocks.py` sizes conductors from."""

    #: Upper end of the ratified `Load` row, amperes.
    full_load_a: float
    #: The ratified `Dropout @ 50 mA` target, volts.
    dropout_target_v: float
    #: The load current the dropout row states its budget at, amperes --
    #: cross-checked against `full_load_a`.
    dropout_at_a: float
    #: The spec file these were read from, for the record's provenance.
    source: str


def _row_cells(text: str, label_pattern: str) -> list[str]:
    """The `|`-separated cells of the first markdown table row whose first
    cell matches ``label_pattern`` (anchored, case-sensitive)."""
    matcher = re.compile(rf"^\|\s*({label_pattern})\s*\|", re.MULTILINE)
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        if matcher.match(line.strip()):
            return [cell.strip() for cell in line.strip().strip("|").split("|")]
    raise SpecError(
        f"no ratified spec row whose first cell matches /{label_pattern}/ "
        "-- spec/target-spec.md's table shape changed, or the row was renamed"
    )


def _quantity(cell: str, unit: str) -> float:
    """The single ``<number><si-prefix><unit>`` quantity in ``cell``."""
    pattern = rf"(\d+(?:\.\d+)?)\s*([muµnk]?){re.escape(unit)}\b"
    match = re.search(pattern, cell)
    if match is None:
        raise SpecError(f"no <number>{unit} quantity in spec cell {cell!r}")
    return float(match.group(1)) * _SI_PREFIX[match.group(2)]


def _range_upper(cell: str, unit: str) -> float:
    """The upper end of a ``<low>-<high><unit>`` range in ``cell``."""
    pattern = (
        rf"(\d+(?:\.\d+)?)\s*{_RANGE_DASH}\s*(\d+(?:\.\d+)?)\s*"
        rf"([muµnk]?){re.escape(unit)}\b"
    )
    match = re.search(pattern, cell)
    if match is None:
        raise SpecError(f"no <low>-<high>{unit} range in spec cell {cell!r}")
    return float(match.group(2)) * _SI_PREFIX[match.group(3)]


def read_spec_constants(spec_path: Path) -> SpecConstants:
    """Parse the ratified rows this layout flow sizes conductors from.

    Raises :class:`SpecError` -- never falls back to a default -- if a row is
    missing, unparseable, or internally inconsistent.
    """
    text = Path(spec_path).read_text()

    load_cells = _row_cells(text, r"Load")
    if len(load_cells) < 2:
        raise SpecError("the ratified `Load` row has no Target cell")
    full_load_a = _range_upper(load_cells[1], "A")

    dropout_cells = _row_cells(text, r"Dropout @[^|]*")
    if len(dropout_cells) < 2:
        raise SpecError("the ratified `Dropout` row has no Target cell")
    dropout_at_a = _quantity(dropout_cells[0], "A")
    dropout_target_v = _quantity(dropout_cells[1], "V")

    if abs(dropout_at_a - full_load_a) > 1e-12:
        raise SpecError(
            f"the ratified Dropout row states its budget at {dropout_at_a} A "
            f"but the ratified Load row's upper end is {full_load_a} A -- the "
            "two rows disagree, so a conductor sized from them would be sized "
            "against a stale pair"
        )

    return SpecConstants(
        full_load_a=full_load_a,
        dropout_target_v=dropout_target_v,
        dropout_at_a=dropout_at_a,
        source=str(spec_path),
    )
