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
"""

from __future__ import annotations

import importlib.util
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
