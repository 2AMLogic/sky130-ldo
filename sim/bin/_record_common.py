"""Shared `record.md` header/footer rendering for `sim/bin/corner-run.py`
and `sim/bin/mc-run.py` (issue #46).

Standard library only, matching every `render-*.py` / `*-run.py` script's
own convention. The "who/what/where" provenance framing (record id,
experiment identity, PDK/tool/repo state header; timestamp/supersedes
footer) was byte-identical modulo one Tools-line clause between the two
scripts before this module existed -- pure extraction, no behavior change.

Mirrors the `layout/bin/_record_common.py` convention from issue #41/#44
(PR #42/#45), one directory over.

Also home to `git()` (issue #51), a `-C <repo_root>` git subprocess helper
shared by `corner-run.py` and `measurements/build_characterization_report.py`
-- both previously carried byte-identical copies.

Also home to `load_corner_run_module()` (issue #96), the importlib-by-path
loader for `corner-run.py` (its filename has a hyphen, so it can't be
`import`ed directly) -- `sim/bin/mc-run.py` and
`measurements/build_characterization_report.py` previously carried
byte-identical copies of this same importlib dance.

Also home to `klt_binary()` (issue #224), the `shutil.which("klt")`
fail-fast check -- `sim/bin/mc-run.py` and `sim/bin/yield-run.py` previously
carried byte-identical copies of this function, differing only in the
trailing usage phrase of their error message.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path


def git(repo_root: Path, *args: str) -> str:
    """Run `git -C <repo_root> <args>`, returning stripped stdout on
    success or `""` on any subprocess failure (non-zero exit, missing
    git, timeout)."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


# --------------------------------------------------------------------------
# effective-input fingerprint (issue #237)
# --------------------------------------------------------------------------
#
# A campaign record's schematic freshness (a live re-netlist compared against
# the committed netlist snapshot) says nothing about the OTHER inputs of a run:
# the experiment manifest's analyses, measurement expressions/bounds and
# declared matrix, and the solver settings. This block fingerprints exactly
# those, so `measurements/build_characterization_report.py` can compare a
# record against the current tree without xschem or the PDK.
#
# Every section is built from an explicit ALLOW-LIST of execution-relevant
# manifest keys (never a deny-list), so prose keys -- `claim`, `title`,
# `note`s, `corners_note`, `unit`, ... -- can be edited freely without
# invalidating a simulation. Bump INPUT_FINGERPRINT_VERSION whenever an
# allow-list or the serialization changes: the checker reports a version
# mismatch as "unverified", never as a (false) match or mismatch.

INPUT_FINGERPRINT_VERSION = 1

PVT_FINGERPRINT_SECTIONS = ("analyses", "measurements", "matrix", "solver")
MC_FINGERPRINT_SECTIONS = ("analyses", "measurements", "matrix", "netlist_patch")


def _canon(value):
    """Normalize a JSON value so numerically-equal spellings serialize alike
    (`27` vs `27.0`)."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else float(value)
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in value.items()}
    return str(value)


def canonical_digest(value) -> str:
    """sha256 of the deterministic (sorted-key, compact) JSON of *value*."""
    text = json.dumps(_canon(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _code_lines(lines) -> list[str]:
    """Drop whole-line `*` SPICE comments and blank lines (prose inside a
    deck's `analyses` list); every other line is execution input."""
    out = []
    for ln in lines or []:
        stripped = str(ln).strip()
        if stripped and not stripped.startswith("*"):
            out.append(stripped)
    return out


def spiceinit_sha256(text: str) -> str:
    """sha256 of an ngspice init-settings file (same digest corner-run.py
    records as `tools.spiceinit_sha256`, issue #190)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pvt_input_sections(raw: dict, spiceinit_text: str | None) -> dict[str, str]:
    """Per-dimension digests of a PVT (`corner-run.py`) manifest's effective
    inputs, plus the `sim/spiceinit` solver settings ngspice reads."""
    deck = raw.get("deck") or {}
    corners = raw.get("corners") or {}
    sections = {
        "analyses": canonical_digest(
            {
                "options": list(deck.get("options") or []),
                "params": deck.get("params") or {},
                "analyses": _code_lines(deck.get("analyses") or ["op"]),
            }
        ),
        "measurements": canonical_digest(
            {
                "measurements": [
                    {k: m.get(k) for k in ("name", "expr", "min", "max")}
                    for m in raw.get("measurements") or []
                ],
                "spread_checks": [
                    {k: c.get(k) for k in ("measurement", "min_spread")}
                    for c in raw.get("spread_checks") or []
                ],
            }
        ),
        "matrix": canonical_digest(
            {
                "process": corners.get("process"),
                "temperature_c": corners.get("temperature_c"),
                "supply_v": corners.get("supply_v"),
                "quick_subset": raw.get("quick_subset"),
            }
        ),
    }
    if spiceinit_text is not None:
        sections["solver"] = spiceinit_sha256(spiceinit_text)
    return sections


def mc_input_sections(raw: dict) -> dict[str, str]:
    """Per-dimension digests of a Monte Carlo (`mc-run.py`) manifest's
    effective inputs.

    No `solver` section, deliberately: the klt backend runs ngspice under its
    own configuration and this harness cannot show it reads `sim/spiceinit`,
    so claiming that file as an MC input would be a fabricated dependency.
    The sample count / vary / k_sigma / seed are CLI-overridable, so they are
    recorded in the record's own `monte_carlo_request`, not fingerprinted
    against the manifest's defaults.
    """
    corner = raw.get("mc_corner") or {}
    analysis = raw.get("mc_analysis") or {}
    patch = raw.get("netlist_patch")
    return {
        "analyses": canonical_digest({k: v for k, v in analysis.items() if k in ("kind", "args")}),
        "measurements": canonical_digest(
            [
                {"name": m.get("name"), "spice": m.get("spice"), "limits": m.get("limits")}
                for m in raw.get("mc_measurements") or []
            ]
        ),
        "matrix": canonical_digest(
            {k: corner.get(k) for k in ("process", "temperature_c", "vsup")}
        ),
        "netlist_patch": canonical_digest(
            None
            if not patch
            else [
                {k: s.get(k) for k in ("match", "replace", "count")}
                for s in patch.get("substitutions") or []
            ]
        ),
    }


def build_input_fingerprint(kind: str, sections: dict[str, str]) -> dict:
    """The record's `input_fingerprint` block: version, backend kind
    (`pvt` | `mc`), per-dimension digests, and one overall digest."""
    return {
        "version": INPUT_FINGERPRINT_VERSION,
        "kind": kind,
        "sections": dict(sections),
        "sha256": canonical_digest({"version": INPUT_FINGERPRINT_VERSION, "kind": kind, "sections": sections}),
    }


def load_corner_run_module(bin_dir: Path):
    """Import `corner-run.py` by file path and return the loaded module.

    `corner-run.py`'s filename has a hyphen, so it can't be `import`ed
    directly -- this is the importlib-by-path workaround, shared by
    `sim/bin/mc-run.py` and `measurements/build_characterization_report.py`
    (issue #96).

    `bin_dir` is the directory containing `corner-run.py` (`sim/bin/`). It is
    inserted at the front of `sys.path` (if not already present) so that
    `corner-run.py`'s own `from _record_common import ...` resolves, then the
    module is loaded, registered as `sys.modules["corner_run"]` (`dataclass()`
    needs this in `sys.modules` to resolve), and executed.
    """
    bin_dir_str = str(bin_dir)
    if bin_dir_str not in sys.path:
        sys.path.insert(0, bin_dir_str)
    spec = importlib.util.spec_from_file_location("corner_run", Path(bin_dir) / "corner-run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["corner_run"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def klt_binary(usage_context: str, error_cls: type[Exception] = RuntimeError) -> str:
    """Return the path to the `klt` binary on `PATH`, or raise `error_cls`
    with an install hint if it is missing.

    `usage_context` is the trailing phrase describing what the caller needs
    `klt` for (e.g. `"run Monte Carlo experiments"`), since that's the one
    part of the error message that differs between callers. `error_cls`
    lets each caller preserve its own exception type for an existing
    `except HarnessError` handler (`mc-run.py` uses `corner_run.HarnessError`;
    `yield-run.py` defines its own `HarnessError`).
    """
    exe = shutil.which("klt")
    if not exe:
        raise error_cls(
            "klt not found on PATH; install klayout-tools "
            f"(https://github.com/2AMLogic/klayout-tools) to {usage_context}"
        )
    return exe


def render_record_header(record: dict, tools_line: str) -> list[str]:
    """Render the shared Record ID/Experiment/Claim/Netlist provenance/PDK/
    Tools/Repo state header lines common to both runners' `record.md`.

    `tools_line` is the already-formatted `- **Tools**: ...` value, since
    that's the one line whose content differs between the two callers
    (`mc-run.py` adds a `klt {version}` clause `corner-run.py` doesn't have).
    """
    r = record
    lines = [f"# Record {r['record_id']}", ""]
    lines.append(f"- **Record ID**: {r['record_id']}")
    lines.append(f"- **Experiment**: `{r['experiment']['slug']}` — {r['experiment']['title']}")
    lines.append(f"- **Claim**: {r['experiment']['claim']}")
    lines.append(
        f"- **Netlist provenance**: {r['experiment']['provenance']} "
        f"(`{r['experiment']['provenance_source']}`)"
    )
    pdk = r["pdk"]
    pin_state = "matches sim/pdk.json pin" if pdk["matches_pin"] else "**MISMATCH vs sim/pdk.json pin**"
    lines.append(
        f"- **PDK**: {pdk['variant']} @ open_pdks `{pdk['installed_commit']}` ({pin_state}); "
        f"models `{pdk['lib_file']}`"
    )
    lines.append(f"- **Tools**: {tools_line}")
    lines.append(
        f"- **Repo state**: `{r['git']['sha']}` on `{r['git']['branch']}`"
        + (" (working tree dirty at run time)" if r["git"]["dirty"] else " (clean working tree)")
    )
    return lines


def render_record_footer(record: dict, script_name: str) -> list[str]:
    """Render the shared Timestamp/Supersedes/Written-by footer lines common
    to both runners' `record.md`, parameterized by the writing script's name
    (e.g. `"corner-run.py"`) for the append-only-evidence note."""
    r = record
    lines = [f"- **Timestamp / author**: {r['timestamp']}, {r['author']}"]
    lines.append(f"- **Supersedes**: {r['supersedes'] or '(none)'}")
    lines.append("")
    lines.append(
        f"Written by `sim/bin/{script_name}`. Append-only: never edit this file — "
        "a correction is a new record with a `Supersedes` field (see `sim/README.md`)."
    )
    lines.append("")
    return lines
