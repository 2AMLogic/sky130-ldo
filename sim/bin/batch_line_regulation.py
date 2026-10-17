"""Translate the line-regulation endpoint deck into `klt sim` step requests (issue #379).

PDK-free, standard library only. corner-run.py's local path runs
`sim/line-regulation`'s deck as ONE ngspice process: four cold-start
`tran <tstep> <tstop> uic` points in sequence, each preceded by `alter`/`set`
cards that put the point's complete source state on the bench (VIN, EN's PWL
high level, the load current), each followed by `avg`/`min`/`max` `meas tran`
cards over the settled tail, with the line-regulation slopes graded from
plot-qualified expressions (`tran2.x - tran1.y`) that span two points.

A `klt sim` request cannot carry that block verbatim, and two klt properties
shape this adapter (see sim/README.md, "Line regulation endpoints on the batch
backend"):

* a step `alter` cannot retarget a source declared with an explicit PWL
  waveform (klt refuses it: ngspice's `alter name=value` has no effect on
  one), and EN is `pwl(...)` whose high level the deck re-points at VIN with
  `alter @ven[pwl]`. The per-point source state therefore travels in the
  NETLIST, one request per endpoint;
* a klt step sequence has no `reset` between steps (the window-grid adapter's
  reason for one request per leg), and each cold-start endpoint is
  independent by construction, so one request per endpoint is also the
  isolation the local deck gets from `uic`.

So each request holds ONE step, named `tran<N>` after the local plot it
replaces, with that endpoint's cards. Cards come back as `tran<N>.<card>` --
the same plot-qualified identity the manifest's expressions use -- and ALL
grading, including the cross-endpoint slopes, is done locally from those raw
card values by `evaluate`, never by klt.

This is deliberately NOT a SPICE interpreter: only the deck vocabulary below,
the card forms below and the expression grammar below are accepted; anything
else is refused before netlisting or submission.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

STEP_PREFIX = "tran"
LOAD_ELEMENT = "ILOAD"


class EndpointTranslationError(ValueError):
    """The deck, a measurement, the netlist or a response has no faithful form."""


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?[a-zA-Z]*"
_NODE = r"v\([A-Za-z0-9_]+\)"
_TRAN_RE = re.compile(rf"^tran\s+({_NUM})\s+({_NUM})\s+uic$", re.IGNORECASE)
_SET_RE = re.compile(rf"^set\s+vinpt\s*=\s*({_NUM})$", re.IGNORECASE)
_ALTER_ILOAD_RE = re.compile(rf"^alter\s+iload\s*=\s*({_NUM})$", re.IGNORECASE)
_ALTER_VVIN_RE = re.compile(r"^alter\s+vvin\s*=\s*\$vinpt$", re.IGNORECASE)
_ALTER_VEN_RE = re.compile(r"^alter\s+@ven\[pwl\]\s*=\s*\[\s*(.*?)\s*\]$", re.IGNORECASE)
# EN's PWL: low until 100us, steps to the point's VIN at 101us, held. Only this
# token pattern is accepted so EN's high level can never differ from VIN.
_EN_PWL_TOKENS = ["0", "0", "100u", "0", "101u", "$vinpt", "10", "$vinpt"]
_MEAS_RE = re.compile(
    rf"^meas\s+tran\s+({_IDENT})\s+(avg|min|max)\s+({_NODE})\s+from=\s*({_NUM})\s+to=\s*({_NUM})$",
    re.IGNORECASE,
)

# Netlist dot-cards that would change the cold-start state, add an analysis or
# measurement outside the step, or collide with klt's own control / temperature.
FORBIDDEN_NETLIST_CARDS = (
    ".ic", ".nodeset", ".control", ".endc", ".op", ".tran", ".dc", ".ac",
    ".meas", ".measure", ".temp",
)


@dataclass
class Endpoint:
    index: int  # 1-based: the local deck's tran<index> plot
    vin: str  # the point's one VIN literal (VVIN and EN's high level)
    iload: str  # the load current in force at this point
    tran_args: str
    cards: list[tuple[str, str, str]]  # (name, kind avg|min|max, "meas tran ..." text)

    @property
    def step_name(self) -> str:
        return f"{STEP_PREFIX}{self.index}"


def parse_deck(lines: list[str], baseline_iload: str) -> list[Endpoint]:
    """Parse `deck.analyses` into its endpoints (comments ignored), or raise
    naming the first line with no faithful form.

    Each point is, in order: an optional `alter iload = X` (it persists into
    later points, exactly as in the local deck), `set vinpt = V`,
    `alter vvin = $vinpt`, EN's `alter @ven[pwl] = [ ... $vinpt ... ]`, one
    cold-start `tran`, then one or more `avg|min|max` cards. The load current
    at point 1 is `baseline_iload`, the pinned netlist ILOAD value.
    """
    body = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("*")]
    if not body:
        raise EndpointTranslationError("deck.analyses declares no analysis")
    endpoints: list[Endpoint] = []
    iload = baseline_iload
    pos = 0
    names: set[str] = set()

    def need(regex: re.Pattern[str], what: str):
        nonlocal pos
        if pos >= len(body) or (m := regex.match(body[pos])) is None:
            got = body[pos] if pos < len(body) else "end of deck"
            raise EndpointTranslationError(
                f"endpoint {len(endpoints) + 1}: expected {what}; got {got!r}"
            )
        pos += 1
        return m

    while pos < len(body):
        if (m := _ALTER_ILOAD_RE.match(body[pos])) is not None:
            iload = m.group(1)
            pos += 1
        vin = need(_SET_RE, "`set vinpt = <volts>`").group(1)
        need(_ALTER_VVIN_RE, "`alter vvin = $vinpt`")
        tokens = need(_ALTER_VEN_RE, "`alter @ven[pwl] = [ ... ]`").group(1).split()
        if tokens != _EN_PWL_TOKENS:
            raise EndpointTranslationError(
                f"endpoint {len(endpoints) + 1}: EN's pwl must be `{' '.join(_EN_PWL_TOKENS)}` "
                f"(full-rail EN at the point's own VIN); got {' '.join(tokens)!r}"
            )
        tm = need(_TRAN_RE, "the cold-start `tran <tstep> <tstop> uic`")
        cards: list[tuple[str, str, str]] = []
        while pos < len(body) and (mm := _MEAS_RE.match(body[pos])) is not None:
            name = mm.group(1)
            if name.lower() in names:
                raise EndpointTranslationError(f"meas card name {name!r} is declared twice")
            names.add(name.lower())
            cards.append((name, mm.group(2).lower(), body[pos]))
            pos += 1
        if not cards:
            raise EndpointTranslationError(
                f"endpoint {len(endpoints) + 1}: no `meas tran <name> avg|min|max v(x) from=T1 to=T2` card"
            )
        endpoints.append(Endpoint(len(endpoints) + 1, vin, iload, f"{tm.group(1)} {tm.group(2)} uic", cards))
    if len(endpoints) != 4:
        raise EndpointTranslationError(f"expected exactly four endpoints, deck declares {len(endpoints)}")
    return endpoints


def endpoint_step(ep: Endpoint, units: dict[str, str]) -> dict:
    """The single `analysis_steps[]` entry of one endpoint's request.
    `units` maps `tran<N>.<card>` to the graded measurement's unit."""
    meas = []
    for name, _kind, text in ep.cards:
        entry = {"name": name, "spice": "." + text}
        unit = units.get(f"{ep.step_name}.{name}")
        if unit:
            entry["unit"] = unit
        meas.append(entry)
    return {"name": ep.step_name, "analysis": {"kind": "tran", "args": ep.tran_args}, "measurements": meas}


def klt_result_name(ep: Endpoint, card: str) -> str:
    return f"{ep.step_name}.{card}"


# ---- expressions (cross-endpoint slopes, identities) --------------------------------

_UNSIGNED_NUM = r"(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?[a-zA-Z]*"
_TOKEN_RE = re.compile(rf"\s*(?:({_IDENT}\.{_IDENT})|(abs)\b|({_UNSIGNED_NUM})|([-+*/()]))")


def _tokens(expr: str, refs_ok: set[str]) -> list[tuple[str, str]]:
    text, pos, out = expr.strip(), 0, []
    if not text or "\n" in text or "\r" in text:
        raise EndpointTranslationError(f"expression {expr!r} must be one non-empty line")
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if m is None or m.end() == pos:
            raise EndpointTranslationError(f"expression {expr!r}: unsupported token at {text[pos:]!r}")
        if m.group(1) is not None:
            if m.group(1).lower() not in refs_ok:
                raise EndpointTranslationError(
                    f"expression {expr!r} references {m.group(1)!r}, which is not an endpoint card"
                )
            out.append(("ref", m.group(1).lower()))
        elif m.group(2) is not None:
            out.append(("fn", "abs"))
        elif m.group(3) is not None:
            out.append(("num", m.group(3)))
        else:
            out.append(("op", m.group(4)))
        pos = m.end()
    return out


def _num(text: str) -> float:
    m = re.fullmatch(r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)([a-zA-Z]*)", text)
    scale = {"": 1.0, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "k": 1e3}
    if m is None or m.group(2).lower() not in scale:
        raise EndpointTranslationError(f"unsupported number {text!r} in expression")
    return float(m.group(1)) * scale[m.group(2).lower()]


def card_refs(endpoints: list[Endpoint]) -> set[str]:
    return {f"{ep.step_name}.{n}".lower() for ep in endpoints for n, _, _ in ep.cards}


def evaluate(expr: str, values: dict[str, float | None], refs_ok: set[str]) -> float | None:
    """Evaluate a manifest expression over endpoint card values: references
    `tran<N>.<card>`, numbers, `abs(...)`, `+ - * / ( )`. A missing value or a
    division by zero yields None (the measurement is then missing, never
    guessed). Anything else raises EndpointTranslationError."""
    toks = _tokens(expr, refs_ok)
    lowvals = {k.lower(): v for k, v in values.items()}
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else (None, None)

    def take():
        nonlocal pos
        pos += 1
        return toks[pos - 1]

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
            return _num(val)
        if kind == "ref":
            take()
            return lowvals.get(val)
        if kind == "fn":
            take()
            if take() != ("op", "("):
                raise EndpointTranslationError(f"expression {expr!r}: abs needs parentheses")
            v = expr_()
            if take() != ("op", ")"):
                raise EndpointTranslationError(f"expression {expr!r}: unbalanced parentheses")
            return None if v is None else abs(v)
        if (kind, val) == ("op", "("):
            take()
            v = expr_()
            if peek() != ("op", ")"):
                raise EndpointTranslationError(f"expression {expr!r}: unbalanced parentheses")
            take()
            return v
        raise EndpointTranslationError(f"expression {expr!r}: unexpected token {val!r}")

    try:
        v = expr_()
    except IndexError as exc:
        raise EndpointTranslationError(f"expression {expr!r}: incomplete") from exc
    if pos != len(toks):
        raise EndpointTranslationError(f"expression {expr!r}: trailing tokens")
    if v is not None and not math.isfinite(v):
        return None
    return v


def check_measurements(endpoints: list[Endpoint], measurements: list[tuple[str, str, str]]) -> dict[str, str]:
    """Every graded expression must parse over endpoint cards; returns the
    `tran<N>.<card>` -> unit map for identity measurements."""
    refs = card_refs(endpoints)
    units: dict[str, str] = {}
    for name, expr, unit in measurements:
        if not re.fullmatch(_IDENT, name):
            raise EndpointTranslationError(f"measurement name {name!r} is not a vector name")
        toks = _tokens(expr, refs)
        evaluate(expr, {}, refs)  # grammar check
        if len(toks) == 1 and toks[0][0] == "ref":
            units[toks[0][1]] = unit
    return units


# ---- netlist ---------------------------------------------------------------------

def check_netlist(
    body: list[str],
    stimulus: list[str],
    error_cls: type[ValueError] = EndpointTranslationError,
    context: str = "an endpoint request",
) -> None:
    """Refuse a netlist whose pinned stimulus sources are not the validated
    baseline (one definition each), or that carries a card altering the cold
    start. Shared by every batch adapter: `error_cls` / `context` only select
    the exception type and the message's noun."""
    lines = [ln.strip() for ln in body]
    for ln in lines:
        low = ln.lower()
        for card in FORBIDDEN_NETLIST_CARDS:
            if low == card or low.startswith(card + " ") or low.startswith(card + "\t"):
                raise error_cls(f"netlist carries `{ln}`: {card} is not allowed in {context}")
    for want in stimulus:
        elem = want.split()[0].lower()
        defs = [ln for ln in lines if ln.split() and ln.split()[0].lower() == elem]
        if defs != [want]:
            raise error_cls(
                f"stimulus element {want.split()[0]} is {defs!r}, expected exactly [{want!r}] "
                "(the validated stimulus; a testbench change needs renewed adapter validation)"
            )


def endpoint_source_lines(ep: Endpoint) -> dict[str, str]:
    """The endpoint's complete source state: element name -> netlist line.
    EN's high level and VVIN come from the one VIN literal."""
    return {
        "vvin": f"VVIN VIN 0 {ep.vin}",
        "ven": f"VEN EN 0 dc 0 pwl(0 0 100u 0 101u {ep.vin} 10 {ep.vin})",
        "iload": f"{LOAD_ELEMENT} VOUT 0 {ep.iload}",
    }


def replace_sources(body: list[str], sources: dict[str, str]) -> list[str]:
    """The circuit body with every element named in `sources` (element name ->
    full netlist line) replaced by that line (call `check_netlist` first: each
    is defined exactly once)."""
    repl = {v.split()[0].lower(): v for v in sources.values()}
    out = []
    for ln in body:
        parts = ln.split()
        out.append(repl.get(parts[0].lower(), ln) if parts else ln)
    return out


def endpoint_body(body: list[str], ep: Endpoint) -> list[str]:
    """The circuit body with VVIN, VEN and ILOAD replaced by the endpoint's
    source state."""
    return replace_sources(body, endpoint_source_lines(ep))


# ---- response --------------------------------------------------------------------

def extract_endpoint_values(ep: Endpoint, measurements: list) -> tuple[dict[str, float | None], list[str]]:
    """Raw card values of one endpoint from one klt corner's `measurements`
    (keyed by `tran<N>.<card>`), plus reasons the corner cannot PASS: a
    missing, duplicated, errored or non-finite value, or a result identity the
    request never asked for."""
    expected = {klt_result_name(ep, n): n for n, _, _ in ep.cards}
    by_name: dict[str, list] = {}
    for rm in measurements:
        if isinstance(rm, dict) and isinstance(rm.get("name"), str):
            by_name.setdefault(rm["name"], []).append(rm)
        else:
            by_name.setdefault("<malformed>", []).append(rm)
    reasons, values = [], {}
    for extra in sorted(set(by_name) - set(expected)):
        reasons.append(f"[{ep.step_name}] unexpected result identity {extra!r} in klt sim response")
    for klt_name in expected:
        entries = by_name.get(klt_name, [])
        value = None
        if not entries:
            reasons.append(f"[{ep.step_name}] endpoint value {klt_name} not found in klt sim response")
        elif len(entries) > 1:
            reasons.append(f"[{ep.step_name}] endpoint value {klt_name} reported more than once")
        else:
            e = entries[0]
            v = e.get("value")
            if e.get("status") not in (None, "pass", "fail", "ok"):
                reasons.append(f"[{ep.step_name}] {klt_name} status {e.get('status')!r}")
            elif isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                reasons.append(f"[{ep.step_name}] {klt_name} value is missing or non-finite ({v!r})")
            else:
                value = float(v)
        values[klt_name] = value
    return values, reasons
