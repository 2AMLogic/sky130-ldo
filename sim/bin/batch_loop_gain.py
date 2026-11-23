"""Translate `sim/loop-gain`'s 18-leg `ac_leg_grid` deck into `klt sim` steps (issue #754).

PDK-free, standard library only. corner-run.py's local path runs
`sim/loop-gain`'s deck as ONE ngspice process per corner: `set units=degrees`,
then eighteen legs, each `[alter cout|hesr gain|rload ...]`, `op` +
`let vseed = v(vout)`, `ac dec 30 1e-2 1e9`, the loop-gain helper vectors
(`lg`, `lgdb`, `lgph`) and three `meas ac` cards (`fc`, `phc`, `gmdb`), with
leg 1 also `let dcg = lgdb[0]`. The manifest then grades `180 + ac<i>.phc`
(PM), `-ac<i>.gmdb` (GM), `op<i>.vseed` (the operating-point branch gate) and
the leg-1 `ac1.fc` / `ac1.dcg` over those results.

Why three requests per supply and not eighteen
-----------------------------------------------
`klt sim`'s step `alter` map takes V/I/R/C/L elements only; the ESR is the CCVS
`HESR` (gain = ESR, an exact short at 0 -- a 0-ohm resistor is floored by
ngspice), which it cannot retarget. So `HESR`'s gain travels in the request
NETLIST, and the manifest's three contiguous six-leg ESR blocks (`esr10m`,
`esr500m`, `esr0`) become three requests, each rewriting ONLY the `HESR` line.
Inside a request the six legs are an `analysis_steps[]` sequence (`op<i>` +
`ac<i>` per leg, in manifest order), each `op` step carrying an explicit
`alter {COUT, RLOAD}` so every ESR group is self-contained (leg 13 starts at
4.7 uF while the baseline netlist holds 0.33 uF).

Step names are the manifest's own plot names (`op<i>`, `ac<i>`), so its graded
expressions carry over verbatim -- but they are NOT sent as klt top-level
derived measurements: a leg whose loop never crosses -180 degrees has no `gmdb`
(klt reports the `on_unreached: "null"` step card `not_reached`, value null),
and a derived row over it would raise a corner-level `derived_input_unavailable`
error instead of the local deck's plain FAIL for that measurement. All 56
manifest expressions are therefore evaluated LOCALLY over the returned step
card values (`evaluate`), exactly as the local backend grades them.

This is deliberately NOT a SPICE interpreter: only the deck vocabulary below
is accepted, replayed against the manifest's own `ac_leg_grid` (which the
record input-fingerprint digests do not cover), and anything else is refused
before netlisting or submission.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import _meas_expr
import batch_line_regulation as blr

NODESET_CARD = ".nodeset v(VOUT)=1.8 v(xldo.FB)=1.2 v(xldo.N_FBB)=0.6"
# `cph(lg)` reports degrees only under this setting (the local deck's first
# control line); it travels as an extra ngspice init line.
NGSPICE_INIT_EXTRA = ["set units=degrees"]
HESR_BASELINE = "HESR VESRS 0 VESRSENSE 10m"
BASELINE_COUT_F = 0.33e-6
BASELINE_HESR = 0.01
BASELINE_RLOAD = 36.0
AC_ARGS = "dec 30 1e-2 1e9"
# The ESR groups, in manifest order: (key, ESR in ohms, HESR gain literal).
ESR_GROUPS = (("esr10m", 0.01, "10m"), ("esr500m", 0.5, "0.5"), ("esr0", 0.0, "0"))
LEGS_PER_GROUP = 6
N_LEGS = 18
GROUP_KEYS = [g[0] for g in ESR_GROUPS]

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_NUM = blr._NUM
_ALTER_RE = re.compile(rf"^alter\s+(cout|rload|hesr\s+gain)\s*=\s*({_NUM})$", re.IGNORECASE)

# One leg's fixed body after its alters (order and text are the pinned shape).
LEG_BODY = (
    "op",
    "let vseed = v(vout)",
    f"ac {AC_ARGS}",
    "let lg = v(xldo.fb)/(1-v(xldo.fb))",
    "let lgdb = db(lg)",
    "let lgph = cph(lg)",
    "meas ac fc when lgdb=0 cross=1",
    "meas ac phc find lgph when lgdb=0 cross=1",
    "meas ac gmdb find lgdb when lgph=-180 cross=1",
)
LEG1_EXTRA = "let dcg = lgdb[0]"
INTERMEDIATES = (("lg", "v(xldo.fb)/(1-v(xldo.fb))"), ("lgdb", "db(lg)"), ("lgph", "cph(lg)"))
CARDS = (
    ("fc", "meas ac fc when lgdb=0 cross=1"),
    ("phc", "meas ac phc find lgph when lgdb=0 cross=1"),
    ("gmdb", "meas ac gmdb find lgdb when lgph=-180 cross=1"),
)
# Cards a step may legitimately not reach (no crossing): value null,
# status `not_reached`; the manifest then grades the measurement FAIL.
UNREACHABLE = ("fc", "phc", "gmdb")


class LoopGainTranslationError(ValueError):
    """The deck, a measurement, the ac_leg_grid or the netlist has no faithful form."""


def _num(text: str) -> float:
    try:
        return float(_meas_expr.MeasExprEvaluator(r"(?!)", LoopGainTranslationError)
                     .evaluate(text, {}, set()))
    except LoopGainTranslationError as exc:
        raise LoopGainTranslationError(f"unsupported alter value {text!r}") from exc


@dataclass
class Leg:
    index: int  # 1-based: the local deck's op<i>/ac<i> plots
    cout_f: float
    esr_ohm: float
    rload_ohm: float
    id: str
    group: str  # ESR group key

    @property
    def op_step(self) -> str:
        return f"op{self.index}"

    @property
    def ac_step(self) -> str:
        return f"ac{self.index}"


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=0.0)


def parse_deck(lines: list[str], grid: dict) -> list[Leg]:
    """Parse `deck.analyses` into its eighteen legs, replaying every `alter`
    from the netlist baseline and requiring each leg's resulting state to equal
    the manifest's `ac_leg_grid` leg (ids, order, C_out, ESR, load resistor),
    or raise naming the first line with no faithful form. Legs are grouped
    into the three contiguous six-leg ESR blocks (10 m, 500 m, 0 ohm)."""
    body = blr.deck_body(lines)
    if not body or body[0].lower() != "set units=degrees":
        raise LoopGainTranslationError("deck must open with `set units=degrees`")
    body = body[1:]
    grid_legs = (grid or {}).get("legs")
    load_ohm = (grid or {}).get("load_resistor_ohm")
    if not isinstance(grid_legs, list) or len(grid_legs) != N_LEGS or not isinstance(load_ohm, dict):
        raise LoopGainTranslationError(f"ac_leg_grid must declare exactly {N_LEGS} legs and load_resistor_ohm")
    cout, esr, rload = BASELINE_COUT_F, BASELINE_HESR, BASELINE_RLOAD
    pos, legs = 0, []
    for i, gl in enumerate(grid_legs, start=1):
        seen: set[str] = set()
        while pos < len(body) and (m := _ALTER_RE.match(body[pos])) is not None:
            what = re.sub(r"\s+", " ", m.group(1).lower())
            if what in seen:
                raise LoopGainTranslationError(f"leg {i}: `alter {what}` appears twice")
            seen.add(what)
            value = _num(m.group(2))
            if what == "cout":
                cout = value
            elif what == "rload":
                rload = value
            else:
                esr = value
            pos += 1
        expected = list(LEG_BODY) + ([LEG1_EXTRA] if i == 1 else [])
        got = body[pos:pos + len(expected)]
        if [g.lower() for g in got] != [e.lower() for e in expected]:
            raise LoopGainTranslationError(f"leg {i}: expected {expected!r}; got {got!r}")
        pos += len(expected)
        want = (gl.get("cout_f"), gl.get("esr_ohm"), load_ohm.get(gl.get("load")))
        if gl.get("ac_index") != i or None in want or not all(
            isinstance(w, (int, float)) for w in want
        ) or not (_close(cout, want[0]) and _close(esr, want[1]) and _close(rload, want[2])):
            raise LoopGainTranslationError(
                f"leg {i}: deck state (C_out {cout:g}, ESR {esr:g}, R_load {rload:g}) does not "
                f"equal ac_leg_grid leg {gl.get('id')!r} {gl!r}"
            )
        legs.append(Leg(i, cout, esr, rload, str(gl.get("id")), ""))
    if pos != len(body):
        raise LoopGainTranslationError(f"deck carries commands after leg {N_LEGS}: {body[pos:]!r}")
    for gi, (key, gesr, _lit) in enumerate(ESR_GROUPS):
        block = legs[gi * LEGS_PER_GROUP:(gi + 1) * LEGS_PER_GROUP]
        if any(not _close(l.esr_ohm, gesr) for l in block):
            raise LoopGainTranslationError(
                f"legs {gi * LEGS_PER_GROUP + 1}-{(gi + 1) * LEGS_PER_GROUP} must all run at ESR {gesr:g} "
                f"({key}): the ESR travels in the request netlist, one request per contiguous block"
            )
        for l in block:
            l.group = key
    return legs


def group_legs(legs: list[Leg], key: str) -> list[Leg]:
    return [l for l in legs if l.group == key]


# ---- measurements (graded locally) -------------------------------------------------

_EXPR = _meas_expr.MeasExprEvaluator(r"(?:op|ac)\d+\.[A-Za-z_][A-Za-z0-9_]*", LoopGainTranslationError)


def card_refs(legs: list[Leg]) -> set[str]:
    refs = {f"{l.op_step}.vseed" for l in legs}
    for l in legs:
        refs |= {f"{l.ac_step}.{n}" for n, _ in CARDS}
    refs.add("ac1.dcg")
    return {r.lower() for r in refs}


def evaluate(expr: str, values: dict[str, float | None], refs_ok: set[str]) -> float | None:
    """Evaluate a manifest expression over step-card values. A missing value
    (including a `not_reached` card) or a division by zero yields None."""
    v = _EXPR.evaluate(expr, values, refs_ok)
    return None if v is not None and not math.isfinite(v) else v


def check_measurements(legs: list[Leg], measurements: list[tuple[str, str, str]],
                       grid: dict) -> None:
    """Every graded expression must parse over the deck's step refs, names must
    be unique, and each `ac_leg_grid` leg's PM / GM / validity measurement must
    be the exact expression over that leg's own steps."""
    refs = card_refs(legs)
    by_name: dict[str, str] = {}
    for name, expr, _unit in measurements:
        if not re.fullmatch(_IDENT, name):
            raise LoopGainTranslationError(f"measurement name {name!r} is not a vector name")
        if name in by_name:
            raise LoopGainTranslationError(f"measurement {name!r} is declared twice")
        by_name[name] = expr
        evaluate(expr, {}, refs)  # grammar + ref check
    for leg, gl in zip(legs, grid["legs"]):
        for key, want in (
            ("pm_measurement", f"180 + {leg.ac_step}.phc"),
            ("gm_measurement", f"-{leg.ac_step}.gmdb"),
            ("validity_measurement", f"{leg.op_step}.vseed"),
        ):
            name = gl.get(key)
            if by_name.get(name) != want:
                raise LoopGainTranslationError(
                    f"leg {leg.index}: {key} {name!r} must be `{want}`, got {by_name.get(name)!r}"
                )
    for name, want in (("fc_c033_50ma_hz", "ac1.fc"), ("dcgain_c033_50ma_db", "ac1.dcg")):
        if by_name.get(name) != want:
            raise LoopGainTranslationError(f"measurement {name!r} must be `{want}`, got {by_name.get(name)!r}")
    if len(by_name) != 3 * N_LEGS + 2:
        raise LoopGainTranslationError(
            f"expected {3 * N_LEGS + 2} measurements (PM, GM, validity per leg + fc + dcgain), got {len(by_name)}"
        )


# ---- request ------------------------------------------------------------------------


def group_steps(legs: list[Leg], key: str) -> list[dict]:
    """The `analysis_steps[]` sequence of one ESR group: op<i> + ac<i> per leg."""
    steps: list[dict] = []
    for leg in group_legs(legs, key):
        steps.append({
            "name": leg.op_step,
            "alter": {"COUT": leg.cout_f, "RLOAD": leg.rload_ohm},
            "analysis": {"kind": "op", "args": ""},
            "measurements": [{"name": "vseed", "expr": "v(vout)", "unit": "V"}],
        })
        meas: list[dict] = [{"name": n, "expr": e, "intermediate": True} for n, e in INTERMEDIATES]
        for name, card in CARDS:
            meas.append({"name": name, "spice": "." + card, "on_unreached": "null"})
        if leg.index == 1:
            meas.append({"name": "dcg", "expr": "lgdb[0]", "unit": "dB"})
        steps.append({"name": leg.ac_step, "analysis": {"kind": "ac", "args": AC_ARGS},
                      "measurements": meas})
    return steps


def expected_results(legs: list[Leg], key: str) -> list[str]:
    """The `<step>.<name>` results a group's response must carry, once each."""
    out: list[str] = []
    for leg in group_legs(legs, key):
        out.append(f"{leg.op_step}.vseed")
        out += [f"{leg.ac_step}.{n}" for n, _ in CARDS]
        if leg.index == 1:
            out.append("ac1.dcg")
    return out


def hesr_literal(key: str) -> str:
    return next(lit for k, _e, lit in ESR_GROUPS if k == key)


def hesr_body(body: list[str], key: str) -> list[str]:
    """The circuit body with the one pinned `HESR` line's gain set to the
    group's ESR (call `check_netlist` first: it is defined exactly once)."""
    want = f"HESR VESRS 0 VESRSENSE {hesr_literal(key)}"
    return [want if ln.split() and ln.split()[0].lower() == "hesr" else ln for ln in body]


def extract_values(
    legs: list[Leg], key: str, measurements: list,
) -> tuple[dict[str, float | None], list[str]]:
    """Read one corner's step-card results for a group: raw values keyed
    `<step>.<card>` plus the reasons the corner cannot PASS. Every expected
    result must be present exactly once; a result the request never asked for,
    an errored one or a non-finite value is a reason. A `not_reached`
    crossing card is a legitimate missing value (graded FAIL, never PASS)."""
    want = expected_results(legs, key)
    wanted = {w.lower(): w for w in want}
    found: dict[str, list[dict]] = {}
    reasons: list[str] = []
    for rm in measurements:
        if not isinstance(rm, dict) or not isinstance(rm.get("name"), str):
            reasons.append(f"malformed result entry {rm!r:.120}")
            continue
        low = rm["name"].lower()
        if low not in wanted:
            reasons.append(f"result {rm['name']!r} is not one the request asked for")
            continue
        found.setdefault(low, []).append(rm)
    values: dict[str, float | None] = {}
    for low, name in wanted.items():
        entries = found.get(low, [])
        values[name] = None
        if len(entries) != 1:
            reasons.append(f"result {name!r} reported {len(entries)} time(s) in klt sim response (expected once)")
            continue
        e = entries[0]
        card = name.split(".", 1)[1]
        if e.get("status") == "error":
            reasons.append(f"result {name!r} is errored in klt sim response")
        elif e.get("status") == "not_reached" and card in UNREACHABLE and e.get("value") is None:
            continue  # no crossing: a missing value, graded FAIL by the manifest bound
        elif isinstance(e.get("value"), bool) or not isinstance(e.get("value"), (int, float)) \
                or not math.isfinite(e["value"]):
            reasons.append(f"result {name!r} value is missing or non-finite ({e.get('value')!r})")
        else:
            values[name] = float(e["value"])
    return values, reasons


def adapter_info(exp_raw: dict, legs: list[Leg], allowed: dict, graded: list[str]) -> dict:
    """Provenance of the issue #754 adapter for a batch record / dry run."""
    return {
        "name": "loop-gain-ac-leg-grid",
        "issue": 754,
        "analysis": f"op + ac {AC_ARGS} per leg",
        "ngspice_init_extra": list(NGSPICE_INIT_EXTRA),
        "esr_groups": [
            {"key": k, "esr_ohm": e, "hesr_line": f"HESR VESRS 0 VESRSENSE {lit}",
             "legs": [l.id for l in group_legs(legs, k)]}
            for k, e, lit in ESR_GROUPS
        ],
        "cards": [c for _, c in CARDS],
        "graded": list(graded),
        "validated_manifest_sections": dict(allowed["manifest_sections"]),
        "validated_stimulus": list(allowed["stimulus"]) + [NODESET_CARD],
    }
