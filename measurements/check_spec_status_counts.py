#!/usr/bin/env python3
"""Fail if spec/target-spec.md table rows carry hand-copied PVT corner counts.

Measured status (n/45, n/15, n/200 corner/sample counts) belongs to the
generated `measurements/characterization.md`; a copy inside a spec table row
goes stale and contradicts the report (#325). Only markdown table rows
(lines starting with `|`) are scanned, so prose elsewhere (e.g. the
verification-corner definition) is not affected.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SPEC = Path(__file__).resolve().parent.parent / "spec" / "target-spec.md"
COUNT_RE = re.compile(r"(?<![\w/])\d+/(?:45|15|200)(?![\w/])")


def find_violations(text: str) -> list[tuple[int, str]]:
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("|"):
            out.extend((n, m.group(0)) for m in COUNT_RE.finditer(line))
    return out


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else SPEC
    bad = find_violations(path.read_text())
    for n, tok in bad:
        print(f"{path}:{n}: hand-copied status count '{tok}' in a table row; "
              "defer to measurements/characterization.md", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
