"""The shared recursive-descent evaluator for manifest measurement expressions.

Extracted from the two batch adapters that had drifted into parallel copies
(`batch_line_regulation.evaluate`, issue #379, and
`batch_startup_ramp.evaluate_measurement`, issue #336; consolidation #666).
One grammar:
    expr   := term (+|- term)*
    term   := factor (*|/ factor)*
    factor := (+|-) factor | number | abs(expr) | ref | (expr)
and one None-propagation rule: a missing ref value or a division by zero
yields None — a missing measurement is recorded missing, never guessed.

Only two things legitimately differ per adapter, and both are constructor
parameters: the reference-token grammar (dotted `tranN.card` for the endpoint
adapters, a bare card name for the startup ramp) and the error class raised.
The SPICE number-suffix table is the deliberate exception — unified here as
the superset of the two former per-adapter tables, so the same expression
text now grades identically wherever it appears (the former line-regulation
copy stopped at `k` and rejected `t`/`g`/`meg`/`f`).

`abs` lexes ahead of the ref branch: a bare-name ref grammar would otherwise
swallow the function, and a dotted ref grammar is disjoint from the literal,
so the order is safe for both. Standard library only, matching every
`sim/bin/*.py` script's own convention; importable filename, so the adapters
reach it with a plain `import` (the `_corner_model.py` pattern).
"""

from __future__ import annotations

import re

IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_UNSIGNED_NUM = r"(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?[a-zA-Z]*"
_NUM_RE = re.compile(r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)([a-zA-Z]*)")
# SPICE scale suffixes — the superset of both former per-adapter tables,
# additive only: `m` is milli and `meg` is mega, never ambiguous.
_SCALE = {"": 1.0, "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3,
          "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}


class MeasExprEvaluator:
    """Evaluate manifest expressions over measurement values (grammar in the
    module docstring). `ref_re` is the reference token's regex alternation
    branch; `error_cls` is the adapter's own ValueError subclass, raised on
    every malformed or out-of-grammar expression."""

    def __init__(self, ref_re: str, error_cls: type[ValueError]):
        self._token_re = re.compile(rf"\s*(?:(abs)\b|({ref_re})|({_UNSIGNED_NUM})|([-+*/()]))")
        self._err = error_cls

    def _num(self, text: str) -> float:
        m = _NUM_RE.fullmatch(text)
        if m is None or m.group(2).lower() not in _SCALE:
            raise self._err(f"unsupported number {text!r} in expression")
        return float(m.group(1)) * _SCALE[m.group(2).lower()]

    def tokenize(self, expr: str, refs_ok: set[str]) -> list[tuple[str, str]]:
        """Lex `expr` to (kind, text) tokens: fn/ref/num/op. Every ref must
        already be known (`refs_ok`, compared case-insensitively)."""
        text, pos, out = expr.strip(), 0, []
        if not text or "\n" in text or "\r" in text:
            raise self._err(f"expression {expr!r} must be one non-empty line")
        ok = {r.lower() for r in refs_ok}
        while pos < len(text):
            m = self._token_re.match(text, pos)
            if m is None or m.end() == pos:
                raise self._err(f"expression {expr!r}: unsupported token at {text[pos:]!r}")
            if m.group(1) is not None:
                out.append(("fn", "abs"))
            elif m.group(2) is not None:
                if m.group(2).lower() not in ok:
                    raise self._err(
                        f"expression {expr!r} references {m.group(2)!r}, "
                        "which is not a measurement reference"
                    )
                out.append(("ref", m.group(2).lower()))
            elif m.group(3) is not None:
                out.append(("num", m.group(3)))
            else:
                out.append(("op", m.group(4)))
            pos = m.end()
        return out

    def evaluate(self, expr: str, values: dict[str, float | None],
                 refs_ok: set[str]) -> float | None:
        """Evaluate `expr` over `values` (keyed by reference token). A ref
        with a missing/None value or a division by zero propagates None."""
        toks = self.tokenize(expr, refs_ok)
        lowvals = {k.lower(): v for k, v in values.items()}
        pos = 0

        def peek():
            return toks[pos] if pos < len(toks) else (None, None)

        def take():
            nonlocal pos
            out = toks[pos]
            pos += 1
            return out

        def expr_():
            v = term()
            while peek() in (("op", "+"), ("op", "-")):
                op = take()[1]
                r = term()
                v = None if v is None or r is None else (v + r if op == "+" else v - r)
            return v

        def term():
            v = factor()
            while peek() in (("op", "*"), ("op", "/")):
                op = take()[1]
                r = factor()
                if v is None or r is None or (op == "/" and r == 0):
                    v = None
                else:
                    v = v * r if op == "*" else v / r
            return v

        def factor():
            kind, val = peek()
            if (kind, val) == ("op", "-"):
                take()
                v = factor()
                return None if v is None else -v
            if (kind, val) == ("op", "+"):
                take()
                return factor()
            if kind == "num":
                take()
                return self._num(val)
            if kind == "ref":
                take()
                return lowvals.get(val)
            if kind == "fn":
                take()
                if peek() != ("op", "("):
                    raise self._err(f"expression {expr!r}: abs needs parentheses")
                take()
                v = expr_()
                if peek() != ("op", ")"):
                    raise self._err(f"expression {expr!r}: unbalanced parentheses")
                take()
                return None if v is None else abs(v)
            if kind == "op" and val == "(":
                take()
                v = expr_()
                if peek() != ("op", ")"):
                    raise self._err(f"expression {expr!r}: unbalanced parentheses")
                take()
                return v
            raise self._err(f"expression {expr!r}: unexpected token {val!r}")

        v = expr_()
        if pos != len(toks):
            raise self._err(f"expression {expr!r}: trailing tokens")
        return v
