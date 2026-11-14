"""Shared data model and pure helpers for the sky130-ldo sim harness.

`sim/bin/corner-run.py`'s filename has a hyphen, so it cannot be `import`ed --
every consumer reaches it through `_record_common.load_corner_run_module()`.
That makes it an unusable home for the types and graders the importable
`sim/bin/_batch_backend.py` needs, so they live here instead (issue #580):
both the runner and the batch backend import this module, and neither imports
the other.

Nothing here does I/O beyond reading its own module-level paths, and nothing
here knows about a backend. `corner-run.py` re-exports every name below, so
`corner_run.<name>` keeps resolving for the `load_corner_run_module()`
consumers exactly as before.

Standard library only, matching every `sim/bin/*.py` script's own convention.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from _record_common import is_finite_number as _finite_number

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
PDK_PIN_FILE = SIM_DIR / "pdk.json"
SPICEINIT_FILE = SIM_DIR / "spiceinit"
XSCHEMRC_FILE = SIM_DIR / "xschemrc"
BUILD_DIR = SIM_DIR / "build"


class HarnessError(RuntimeError):
    """A problem the operator has to fix; never produces a record."""


@dataclass
class Pdk:
    pin: dict
    root: Path
    variant: str
    dir: Path
    installed_commit: str
    lib_file: Path

    @property
    def matches_pin(self) -> bool:
        return self.installed_commit == self.pin["open_pdks_commit"]


_VERSION_TOKEN = {
    # ngspice: "ngspice-42 : Circuit level simulation program"
    "ngspice": re.compile(r"ngspice-(\d+(?:\.\d+)*)"),
    # xschem: "XSCHEM V3.4.4"
    "xschem": re.compile(r"V(\d+(?:\.\d+)*)", re.IGNORECASE),
}


def parse_tool_version(tool: str, line: str) -> str | None:
    """The bare version token from a tool's first version line, else None."""
    m = _VERSION_TOKEN[tool].search(line)
    return m.group(1) if m else None


def compare_tool_versions(declared: dict, versions: dict) -> list[tuple[str, str, str]]:
    """(tool, declared, actual) for every declared tool not on its declared version."""
    drift = []
    for tool, want in declared.items():
        line = versions.get(tool, "not found")
        got = parse_tool_version(tool, line) if tool in _VERSION_TOKEN else None
        if got != want:
            drift.append((tool, want, got or line))
    return drift


@dataclass
class Measurement:
    name: str
    expr: str
    unit: str = ""
    min: float | None = None
    max: float | None = None
    # Bound inclusivity (issue #335). Default inclusive (value == bound passes);
    # `false` makes the bound strict (value == bound fails), implementing a
    # ratified `<` / `>` row. Validated by grade_bounds().
    min_inclusive: bool = True
    max_inclusive: bool = True
    note: str = ""
    # Window-grid support (issue #313). A manifest measurement with
    # `per_leg: true` is a TEMPLATE that load_experiment() expands once per
    # declared `window_grid` leg; the expanded copies carry `leg`/`cout_f`/
    # `esr_ohm` and are evaluated inside that leg's own deck block.
    per_leg: bool = False
    direction: str | None = None
    leg: str | None = None
    cout_f: float | None = None
    esr_ohm: float | None = None


@dataclass
class Experiment:
    dir: Path
    raw: dict
    measurements: list[Measurement] = field(default_factory=list)
    # Window-grid leg execution order override (issue #313 smoke check); None
    # means the declared order. Always a permutation of the declared legs.
    leg_order: list[str] | None = None

    @property
    def slug(self) -> str:
        return self.raw["slug"]

    @property
    def schematic(self) -> Path:
        return (self.dir / self.raw["schematic"]).resolve()


def window_legs(raw: dict) -> list[dict]:
    """The declared COUT/ESR legs of a manifest's `window_grid` (issue #313),
    or [] for an experiment that does not declare one."""
    return list((raw.get("window_grid") or {}).get("legs") or [])


def grade_bounds(m: Measurement, value: float | None) -> tuple[bool, str]:
    """Single grader for a measurement's [min, max] window (issue #335), shared
    by the local, window-grid (local, per-leg) and klt-batch paths so they
    cannot drift. Missing/non-finite values fail. A bound is inclusive unless
    its `*_inclusive` flag is exactly False; non-bool flags are malformed.
    """
    for flag in ("min_inclusive", "max_inclusive"):
        if not isinstance(getattr(m, flag), bool):
            raise HarnessError(
                f"measurement {m.name!r}: {flag} must be a JSON boolean, got {getattr(m, flag)!r}"
            )
    for bound in ("min", "max"):
        b = getattr(m, bound)
        if b is not None and (isinstance(b, bool) or not _finite_number(b)):
            raise HarnessError(f"measurement {m.name!r}: {bound} must be a finite number or null, got {b!r}")
    if value is None:
        return False, "measurement not found in ngspice output"
    if not _finite_number(value):
        return False, "non-finite measurement value"
    if m.min is not None and (value < m.min or (value == m.min and not m.min_inclusive)):
        return False, f"below min {m.min:g}" if value < m.min else f"not above strict min {m.min:g}"
    if m.max is not None and (value > m.max or (value == m.max and not m.max_inclusive)):
        return False, f"above max {m.max:g}" if value > m.max else f"not below strict max {m.max:g}"
    return True, ""


@dataclass(frozen=True)
class Corner:
    process: str
    temp_c: float
    supply_v: float

    @property
    def id(self) -> str:
        temp = f"{self.temp_c:g}"
        return f"{self.process}_{temp}c_{self.supply_v:.2f}v"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.id


def unique_in_order(values) -> list:
    seen, out = set(), []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def leg_values(grid: dict, leg: dict) -> dict[str, float]:
    """Numeric values of a leg's `{placeholder}`s in `leg_analyses`, shared by
    the local deck walk and the klt-batch step request (issue #326) so the two
    paths cannot drift."""
    cout, esr = float(leg["cout_f"]), float(leg["esr_ohm"])
    values = {
        "cout_esr_f": cout if esr > 0 else 0.0,
        "cout_dir_f": cout if esr == 0 else 0.0,
        # RESR is parked at its netlist value in the ESR=0 leg (it sits in
        # series with a 0 F capacitor and carries no current).
        "resr_f": esr if esr > 0 else float(grid.get("resr_park_ohm", 0.01)),
    }
    if "rload_ohm" in leg:
        # A leg that also walks the DC load (issue #336 startup grid) names it.
        values["rload_f"] = float(leg["rload_ohm"])
    return values


# Markers ngspice prints to stdout/stderr when a `.op`/`.tran`/`.ac`/`.dc`
# solve did not land on a genuine circuit state -- e.g. it fell back to
# gmin/source stepping and either that fallback itself failed, or it
# "succeeded" onto a numerically spurious branch (a poly resistor's
# voltage-coefficient extrapolation admitting a solution thousands of volts
# outside the physical range is the concrete mechanism issue #164 found).
# ngspice does NOT treat any of these as a fatal error -- the run still
# exits 0 and still prints what looks like a converged result -- so a corner
# that hits one must be forced to FAIL regardless of its measured values.
# See sim/README.md's "Initial-condition contract" (issue #171) for the full
# rationale and for why this list is deliberately these three confirmed
# forms rather than an attempt at an exhaustive ngspice diagnostic catalog.
SOLVER_DIAGNOSTIC_MARKERS = (
    "singular matrix",
    "gmin stepping failed",  # matches both "Dynamic" and "True" gmin stepping
    "out of range for ^",
)


def detect_solver_diagnostic(text: str) -> str | None:
    """Return the first ngspice solver-diagnostic line found in *text*, or
    None if none of SOLVER_DIAGNOSTIC_MARKERS appears.

    *text* is expected to be a corner's combined stdout+stderr. The returned
    string is the matched line itself (stripped), so it can be surfaced
    verbatim as a FAIL reason -- see sim/README.md's "Initial-condition
    contract" (issue #171).
    """
    for line in text.splitlines():
        stripped = line.strip()
        if any(marker in stripped for marker in SOLVER_DIAGNOSTIC_MARKERS):
            return stripped
    return None
