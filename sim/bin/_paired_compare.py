"""Shared verdict/report logic for the paired local/fleet comparison scripts.

Used by all four comparators: compare_dropout_paired.py (#375),
compare_line_regulation_paired.py (#384),
compare_load_regulation_paired.py (#381) and compare_loop_gain_paired.py
(#757). PDK-free.

Only the generic parts live here: the endpoint-response reader, engine-version
resolution, the row builder, verdict resolution (unresolved > rejected > engine_mismatch >
equivalent), the report dict, and row printing / exit code. Tolerances,
endpoint lists and derived-value functions stay in each script, next to
their docstring, and are passed in as a `{name: (tol, unit)}` table so a
result can never be rescued by widening them from a caller.
"""

from __future__ import annotations

import json
from pathlib import Path

from _record_common import is_finite_number
from batch_line_regulation import extract_step_values


def engine_version(versions) -> str | None:
    """The one engine version every required response supplies, or None.

    `versions` holds each response's raw `environment.engine_version`. A
    version comes back only when every response supplies one and they all
    agree; an absent or null version in any response, or any disagreement,
    is None -- never the string "None", which would equal a local engine
    passed as "None" and let an unversioned pair compare equivalent.
    """
    seen = {None if v is None else str(v) for v in versions}
    return seen.pop() if len(seen) == 1 and None not in seen else None


def load_endpoint_responses(
    d: Path, endpoint_cards: list[list[str]],
) -> tuple[dict, str | None, list[str]]:
    """Read each tran response against the bench's cards in deck order."""
    values, versions, errors = {}, [], []
    for index, cards in enumerate(endpoint_cards, 1):
        step = f"tran{index}"
        response = json.loads((d / "remote" / step / "response.json").read_text())
        versions.append(response.get("environment", {}).get("engine_version"))
        expected = [f"{step}.{card}" for card in cards]
        raw, reasons = extract_step_values(step, expected, response["corners"][0]["measurements"])
        values.update({name.split(".", 1)[1]: value for name, value in raw.items()})
        errors.extend(reasons)
    return values, engine_version(versions), errors


def compare(
    tols: dict,
    remote: dict,
    local: dict,
    remote_engine,
    local_engine,
    remote_pass=None,
    local_pass=None,
    extra: dict | None = None,
    remote_errors: list[str] | None = None,
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
    if remote_errors or missing or not verdict_match:
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
        **({"remote_errors": remote_errors} if remote_errors else {}),
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
    for error in rep.get("remote_errors", []):
        print(error)
    print(
        f"engines remote={rep['remote_engine']} local={rep['local_engine']} "
        f"-> verdict {rep['verdict']}"
    )
    return 0 if rep["verdict"] == "equivalent" else 2
