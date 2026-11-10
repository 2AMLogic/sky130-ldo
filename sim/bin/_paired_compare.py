"""Shared verdict/report logic for the paired local/fleet comparison scripts.

Used by compare_line_regulation_paired.py (#384) and
compare_load_regulation_paired.py (#381). PDK-free.

Only the generic parts live here: the row builder, the verdict resolution
(unresolved > rejected > engine_mismatch > equivalent), the report dict, and
row printing / exit code. Tolerances, endpoint lists and derived-value
functions stay in each script, next to their docstring, and are passed in as a
`{name: (tol, unit)}` table so a result can never be rescued by widening them
from a caller.
"""

from __future__ import annotations

from _record_common import is_finite_number


def compare(
    tols: dict,
    remote: dict,
    local: dict,
    remote_engine,
    local_engine,
    remote_pass=None,
    local_pass=None,
    extra: dict | None = None,
) -> dict:
    """Compare `remote` vs `local` over the names in `tols` (insertion order).

    `extra` keys are placed in the report right after `local_engine`.
    """
    rows, missing, breaches = [], [], []
    for name, (tol, unit) in tols.items():
        r, l = remote.get(name), local.get(name)
        if not (is_finite_number(r) and is_finite_number(l)):
            missing.append(name)
            rows.append(
                dict(name=name, remote=r, local=l, delta=None, tol=tol, unit=unit, ok=False)
            )
            continue
        d = l - r
        ok = abs(d) <= tol
        if not ok:
            breaches.append(name)
        rows.append(dict(name=name, remote=r, local=l, delta=d, tol=tol, unit=unit, ok=ok))
    engines_equal = remote_engine is not None and str(remote_engine) == str(local_engine)
    verdict_match = remote_pass is not None and remote_pass == local_pass
    if missing or not verdict_match:
        verdict = "unresolved"
    elif breaches:
        verdict = "rejected"
    elif not engines_equal:
        verdict = "engine_mismatch"
    else:
        verdict = "equivalent"
    return {
        "verdict": verdict,
        "equivalence_claimable": verdict == "equivalent",
        "engines_equal": engines_equal,
        "remote_engine": remote_engine,
        "local_engine": local_engine,
        **(extra or {}),
        "spec_verdicts": {
            "remote_pass": remote_pass,
            "local_pass": local_pass,
            "match": verdict_match,
        },
        "missing": missing,
        "breaches": breaches,
        "rows": rows,
    }


def print_report(rep: dict, name_width: int) -> int:
    """Print each row and the verdict line; return the process exit code."""
    for r in rep["rows"]:
        d = "n/a" if r["delta"] is None else f"{r['delta']:+.6g}"
        print(
            f"{r['name']:{name_width}s} remote={r['remote']} local={r['local']} "
            f"d={d} {r['unit']} {'ok' if r['ok'] else 'OUT'}"
        )
    print(
        f"engines remote={rep['remote_engine']} local={rep['local_engine']} "
        f"-> verdict {rep['verdict']}"
    )
    return 0 if rep["verdict"] == "equivalent" else 2
