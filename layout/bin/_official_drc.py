"""Fail-closed reader for the PDK's official-deck KLayout report database
(`sky130A_mr.drc` -> `.lyrdb`), issue #260. Standard library only.

A tool exit status of 0 does not prove the deck ran to completion, and an
absent / truncated / structurally empty report must never read as "zero
violations". `parse_lyrdb` therefore raises :class:`OfficialDrcError` unless
the file is a well-formed report database that declares the deck's rule
categories and an `<items>` section; only then is a zero-marker result
trusted.
"""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?")


class OfficialDrcError(Exception):
    """The official-deck report is missing, unreadable or structurally invalid."""


@dataclass
class Marker:
    rule: str
    cell: str
    kind: str  # polygon | edge | edge-pair | box | other
    geometry: str
    bbox_um: tuple[float, float, float, float] | None


@dataclass
class Report:
    top_cell: str
    rule_count: int
    total: int
    by_rule: dict[str, list[Marker]] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in sorted(self.by_rule.items())}


def _bbox(geometry: str) -> tuple[float, float, float, float] | None:
    nums = [float(n) for n in _NUM.findall(geometry.split(":", 1)[-1])]
    if len(nums) < 4 or len(nums) % 2:
        return None
    xs, ys = nums[0::2], nums[1::2]
    return (min(xs), min(ys), max(xs), max(ys))


def parse_lyrdb(path: Path, expect_top_cell: str | None = None) -> Report:
    path = Path(path)
    try:
        if path.stat().st_size == 0:
            raise OfficialDrcError(f"{path.name}: empty file")
        root = ET.parse(path).getroot()
    except OSError as exc:
        raise OfficialDrcError(f"{path.name}: unreadable ({exc})") from exc
    except ET.ParseError as exc:
        raise OfficialDrcError(f"{path.name}: malformed XML ({exc})") from exc
    if root.tag != "report-database":
        raise OfficialDrcError(f"{path.name}: root element is <{root.tag}>, not <report-database>")
    top = (root.findtext("top-cell") or "").strip()
    if not top:
        raise OfficialDrcError(f"{path.name}: no <top-cell>")
    if expect_top_cell is not None and top != expect_top_cell:
        raise OfficialDrcError(f"{path.name}: top-cell '{top}', expected '{expect_top_cell}'")
    cats = root.find("categories")
    rule_count = 0 if cats is None else len(list(cats.iter("category")))
    if rule_count == 0:
        raise OfficialDrcError(f"{path.name}: declares no rule categories (deck did not run?)")
    items = root.find("items")
    if items is None:
        raise OfficialDrcError(f"{path.name}: no <items> section (truncated report?)")

    by_rule: dict[str, list[Marker]] = defaultdict(list)
    total = 0
    for item in items.findall("item"):
        rule = (item.findtext("category") or "").strip().strip("'")
        if not rule:
            raise OfficialDrcError(f"{path.name}: marker without a category")
        value = (item.findtext("values/value") or "").strip()
        kind = value.split(":", 1)[0].strip() if ":" in value else "other"
        by_rule[rule].append(
            Marker(rule, (item.findtext("cell") or "").strip(), kind, value, _bbox(value))
        )
        total += 1
    return Report(top, rule_count, total, dict(by_rule))


# --- marker-family summary (diagnosis seam) --------------------------------

def summarize_marker_families(report: Report, max_samples: int) -> dict[str, dict]:
    """Per-rule-family summary of an already parsed report (issue #306).

    Standard library only -- the PDK-free seam of `diagnose-official-drc.py`,
    whose KLayout geometry census stays in that script. Families are in sorted
    rule order; each carries its marker `count`, the six most frequent deck
    cells (`deck_cells`, a histogram in descending count) and up to
    `max_samples` markers in report order, geometry truncated to 200 chars.
    """
    fams: dict[str, dict] = {}
    for fam, items in sorted(report.by_rule.items()):
        cells = Counter(i.cell for i in items)
        samples = []
        for i in items[:max_samples]:
            samples.append({"cell": i.cell, "kind": i.kind, "geometry": i.geometry[:200]})
        fams[fam] = {
            "count": len(items),
            "deck_cells": dict(cells.most_common(6)),
            "sample_markers": samples,
        }
    return fams


# --- verdict ---------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class OfficialResult:
    """state: "clean" | "violations" | "error". Only "clean" may contribute to
    a PASS; "error" means the deck did not demonstrably run to completion."""

    state: str
    detail: str
    total: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    rule_count: int = 0
    run: dict = field(default_factory=dict)


def official_result(out_dir: Path, cell: str) -> OfficialResult:
    """Fail-closed verdict for the official deck in a flow output directory.

    Reads `mr-drc.run.json` (written by the flow driver: whether the deck and
    KLayout were found, the KLayout exit status, the switches) and
    `mr-drc.lyrdb`. A missing run record, a missing deck/tool, a nonzero
    KLayout exit, or a missing / empty / truncated / wrong-cell report is an
    "error", never "clean".
    """
    out_dir = Path(out_dir)
    try:
        run = json.loads((out_dir / "mr-drc.run.json").read_text())
        if not isinstance(run, dict):
            raise ValueError("not an object")
    except (OSError, ValueError) as exc:
        return OfficialResult("error", f"no usable mr-drc.run.json ({exc}); the official deck was not run by the flow")
    if not run.get("deck_present"):
        return OfficialResult("error", "official deck sky130A_mr.drc not found in the resolved PDK", run=run)
    if not run.get("klayout_found"):
        return OfficialResult("error", "klayout not found on PATH; official deck not run", run=run)
    if run.get("exit_code") != 0:
        return OfficialResult(
            "error", f"klayout exited with status {run.get('exit_code')!r} running the official deck", run=run
        )
    try:
        report = parse_lyrdb(out_dir / "mr-drc.lyrdb", expect_top_cell=cell)
    except OfficialDrcError as exc:
        return OfficialResult("error", f"official report invalid: {exc}", run=run)
    counts = report.counts()
    if report.total == 0:
        return OfficialResult(
            "clean",
            f"0 markers across {report.rule_count} declared rule categories",
            0, {}, report.rule_count, run,
        )
    return OfficialResult(
        "violations",
        f"{report.total} markers in {len(counts)} rule families",
        report.total, counts, report.rule_count, run,
    )


def overall_pass(curated_status: str | None, official: OfficialResult, device_ok: bool, routing_ok: bool) -> bool:
    return curated_status == "clean" and official.state == "clean" and device_ok and routing_ok
