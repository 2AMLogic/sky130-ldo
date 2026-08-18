"""Shared `record.md` header/footer rendering for `sim/bin/corner-run.py`
and `sim/bin/mc-run.py` (issue #46).

Standard library only, matching every `render-*.py` / `*-run.py` script's
own convention. The "who/what/where" provenance framing (record id,
experiment identity, PDK/tool/repo state header; timestamp/supersedes
footer) was byte-identical modulo one Tools-line clause between the two
scripts before this module existed -- pure extraction, no behavior change.

Mirrors the `layout/bin/_record_common.py` convention from issue #41/#44
(PR #42/#45), one directory over.
"""

from __future__ import annotations


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
