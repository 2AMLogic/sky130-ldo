"""Shared, dependency-neutral xschem netlist normalization (issues #288, #277).

Used by sim/bin/corner-run.py and sim/pex-post-layout/bin/gen-pex-testbench.py
so both xschem-to-ngspice paths apply one guarded evaluator.
"""

from __future__ import annotations

import re

_EXPR_RE = re.compile(r"expr\('([^']*)'\)")
_EXPR_SAFE_RE = re.compile(r"^[0-9a-zA-Z_.+\-*/()\s]*$")


def eval_xschem_exprs(text: str) -> tuple[str, int]:
    """Evaluate `expr('...')` geometry parameters (ad/as/pd/ps/nrd/nrs).

    The pinned toolchain (xschem 3.4.7) writes these sky130 symbol parameters
    as numbers. An older xschem (3.4.4, what Ubuntu's apt ships -- the CI
    `pdk-smoke` job and the dispatch workers) writes the symbol's raw
    `expr('...')` template, which ngspice cannot evaluate: the whole deck then
    fails to parse and every measurement is unavailable (issue #288). This
    applies the PDK symbol's own formulae to each device's own instance
    parameters (`@nf`, `@W`, ...), so the numbers equal what 3.4.7 writes.
    A no-op on text that has no `expr('...')`. Returns (text, substitutions).
    """
    n = 0
    out = []
    for stmt in re.split(r"\n(?!\+)", text):
        if "expr(" in stmt:
            params = {
                k.lower(): v
                for k, v in re.findall(r"(?<![\w@])(\w+)=([0-9.eE+-]+)(?=\s|$)", stmt)
            }

            def ev(m: re.Match) -> str:
                nonlocal n
                f = m.group(1)
                for name in set(re.findall(r"@(\w+)", f)):
                    if name.lower() not in params:
                        return m.group(0)  # unknown parameter: leave it visible
                    f = re.sub(rf"@{name}\b", f"({params[name.lower()]})", f)
                if not _EXPR_SAFE_RE.match(f) or set(re.findall(r"[A-Za-z_]\w*", f)) - {"int"}:
                    return m.group(0)
                try:
                    val = eval(f, {"__builtins__": {}}, {"int": int})
                except (SyntaxError, ArithmeticError, TypeError, NameError):
                    return m.group(0)
                n += 1
                return f"{val:.6g}"

            stmt = _EXPR_RE.sub(ev, stmt)
        out.append(stmt)
    return "\n".join(out), n


def find_unresolved_exprs(text: str) -> list[str]:
    """Return every `expr(` occurrence left in non-comment netlist text.

    Callers that must not hand ngspice an unevaluated template (the PEX
    generator) use this to fail closed after eval_xschem_exprs.
    """
    return [
        ln.strip()
        for ln in text.splitlines()
        if not ln.lstrip().startswith("*") and "expr(" in ln
    ]
