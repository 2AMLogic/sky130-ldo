"""Shared helpers for `layout/bin/gen-ldo-*.py` (issue #44).

Standard library only, matching every `layout/bin/` script's own convention.
`_merge_continuations()` was byte-identical (module docstring aside) across
`gen-ldo-reference-netlist.py` and `gen-ldo-blocks.py` before this module
existed -- pure extraction, no behavior change.
"""

from __future__ import annotations


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
