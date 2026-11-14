#!/usr/bin/env python3
"""Fail if README.md's T1 headline disagrees with the committed tier report.

README.md asserts of its own "T1 <met>/<total>, tier: X" headline that it
"is not prose" and is "re-run by CI on every push so it fails rather than goes
stale". Nothing compared the two, and the headline duly went stale by four
items (issue #579). This closes that loop, the same way
`measurements/check_spec_status_counts.py` does for the spec table.

The denominator is the number of `items` entries carrying a **numeric** `id`.
`signoff/records/t1-tier-report.json` also carries trailing rows with
`id: null` -- those are the T2/T3/T4 *tier* rows, not T1 items -- so counting
every entry gives the wrong total (14 rather than 11).

Reads only committed files; no klt, no network, no PDK.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
RECORD = ROOT / "signoff" / "records" / "t1-tier-report.json"

HEADLINE_RE = re.compile(
    r"^###\s+Where this block sits on the evidence ladder:\s*"
    r"\*\*T1\s+(\d+)\s*/\s*(\d+),\s*`tier:\s*([^`]*?)`\*\*\s*$"
)


class HeadlineError(Exception):
    """The record or the README could not be read as this check requires."""


def counts_from_record(record: dict) -> tuple[int, int, str]:
    """Return (met, total, tier) for the T1 items in a tier report.

    Only entries with a numeric (non-bool) `id` are T1 items; the `id: null`
    entries are the T2/T3/T4 tier rows.
    """
    items = record.get("items")
    if not isinstance(items, list) or not items:
        raise HeadlineError("tier report has no 'items' list")
    t1 = [
        it for it in items
        if isinstance(it, dict)
        and isinstance(it.get("id"), int)
        and not isinstance(it.get("id"), bool)
    ]
    if not t1:
        raise HeadlineError("tier report has no T1 items (no entry carries a numeric 'id')")
    met = sum(1 for it in t1 if it.get("status") == "met")
    tier = record.get("tier")
    tier_text = "null" if tier is None else str(tier)

    # The record also summarises itself. If it does, the two must agree --
    # a disagreement means the record is internally inconsistent and neither
    # number can be trusted as the thing the README should mirror.
    for key, derived in (("t1_item_count", len(t1)), ("t1_met_count", met)):
        claimed = record.get(key)
        if isinstance(claimed, int) and not isinstance(claimed, bool) and claimed != derived:
            raise HeadlineError(
                f"tier report is internally inconsistent: '{key}' is {claimed} but "
                f"{derived} was derived from its numeric-id items"
            )
    return met, len(t1), tier_text


def headline_from_readme(text: str) -> tuple[int, int, int, str]:
    """Return (line_number, met, total, tier) from the README's T1 headline."""
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("### Where this block sits on the evidence ladder"):
            m = HEADLINE_RE.match(line.strip())
            if m is None:
                raise HeadlineError(
                    f"README.md:{n}: evidence-ladder headline does not match the expected "
                    "shape '### Where this block sits on the evidence ladder: "
                    "**T1 <met>/<total>, `tier: <tier>`**'"
                )
            found.append((n, int(m.group(1)), int(m.group(2)), m.group(3).strip()))
    if not found:
        raise HeadlineError(
            "README.md has no '### Where this block sits on the evidence ladder:' "
            "headline -- the line this check keeps honest was removed or renamed"
        )
    if len(found) > 1:
        raise HeadlineError(
            "README.md has %d evidence-ladder headlines (lines %s); expected exactly one"
            % (len(found), ", ".join(str(f[0]) for f in found))
        )
    return found[0]


def main(argv: list[str]) -> int:
    readme = Path(argv[1]) if len(argv) > 1 else README
    record = Path(argv[2]) if len(argv) > 2 else RECORD

    # Every failure below exits non-zero. A check that cannot read its own
    # inputs must never look like one that passed.
    try:
        doc = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"check-t1-headline: {record}: unreadable or not valid JSON: {exc}", file=sys.stderr)
        return 2
    try:
        readme_text = readme.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"check-t1-headline: {readme}: unreadable: {exc}", file=sys.stderr)
        return 2
    try:
        met, total, tier = counts_from_record(doc)
        line, r_met, r_total, r_tier = headline_from_readme(readme_text)
    except HeadlineError as exc:
        print(f"check-t1-headline: {exc}", file=sys.stderr)
        return 2

    if (r_met, r_total, r_tier) == (met, total, tier):
        return 0

    print(
        f"{readme}:{line}: T1 headline says 'T1 {r_met}/{r_total}, tier: {r_tier}' but "
        f"{record.name} records 'T1 {met}/{total}, tier: {tier}'.\n"
        f"  The headline is not prose -- it mirrors the committed record. Correct it to:\n"
        f"    ### Where this block sits on the evidence ladder: "
        f"**T1 {met}/{total}, `tier: {tier}`**\n"
        f"  (Re-grade the record first with `bash signoff/check.sh --write` if the\n"
        f"  record itself is what moved.)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
