"""Capacitor-implementation comparison helpers (issue #319). Standard library only.

Pure functions used by ``layout/cap-study/run-cap-study.py``: SPICE parameter parsing
and evaluation (the pinned PDK's own model files), magic ``.mag`` bounding
boxes for the PDK's fixed vpp cells, ngspice log parsing, the area arithmetic
and the outcome rule. Nothing here runs a simulator or touches the network,
so every function is unit-testable on small fixtures
(``layout/tests/test_cap_study_*.py``).

Cell convention used throughout the study's ``matrix.json``: a number is a
``{"value": <float>, "unit": ..., "source": ...}`` dict whose ``source`` names
the PDK file/parameter, the local run log or the existing record it came
from. Anything not measured and not read from a PDK file is
``{"value": "unmeasured", "reason": ...}`` -- see :func:`unmeasured`.
"""

from __future__ import annotations

import ast
import math
import re
from pathlib import Path

UNMEASURED = "unmeasured"
LIMIT_UM2 = 0.1e6  # ratified Area row: < 0.1 mm^2 (strict); read-only here

# SPICE magnitude suffixes (case-insensitive; "meg" before "m").
_SUFFIX = {
    "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3, "u": 1e-6,
    "n": 1e-9, "p": 1e-12, "f": 1e-15, "a": 1e-18,
}
_NUM_RE = re.compile(
    r"(?<![A-Za-z_0-9.])([0-9]+\.?[0-9]*|\.[0-9]+)([eE][-+]?[0-9]+)?(meg|[tgkmunpfa])?(?![A-Za-z_0-9])",
    re.IGNORECASE,
)


def cell(value: float, unit: str, source: str, note: str | None = None) -> dict:
    """A measured or PDK-sourced matrix cell."""
    out = {"value": value, "unit": unit, "source": source}
    if note:
        out["note"] = note
    return out


def unmeasured(reason: str) -> dict:
    """A cell nobody measured and no PDK file states. Never a number."""
    return {"value": UNMEASURED, "reason": reason}


def is_unmeasured(c) -> bool:
    return isinstance(c, dict) and c.get("value") == UNMEASURED


# --------------------------------------------------------------------------
# SPICE numbers and expressions
# --------------------------------------------------------------------------


def spice_number(tok: str) -> float:
    """'150p' -> 1.5e-10, '0.0455u' -> 4.55e-08, '2e-15' -> 2e-15."""
    t = tok.strip()
    m = re.fullmatch(r"([-+]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?)(meg|[tgkmunpfa])?[a-zA-Z]*", t,
                     re.IGNORECASE)
    if not m:
        raise ValueError(f"not a SPICE number: {tok!r}")
    scale = _SUFFIX[m.group(2).lower()] if m.group(2) else 1.0
    return float(m.group(1)) * scale


def _expand_suffixes(expr: str) -> str:
    def repl(m: re.Match) -> str:
        base = m.group(1) + (m.group(2) or "")
        if m.group(3):
            return repr(float(base) * _SUFFIX[m.group(3).lower()])
        return base
    return _NUM_RE.sub(repl, expr)


# Nominal (mean) value of the statistical functions; every use in the pinned
# PDK is multiplied by an MC switch that is 0 outside Monte Carlo sections.
_FUNCS = {
    "agauss": lambda nom, *a: nom,
    "gauss": lambda nom, *a: nom,
    "aunif": lambda nom, *a: nom,
    "unif": lambda nom, *a: nom,
    "exp": math.exp,
    "sqrt": math.sqrt,
    "abs": abs,
    "log": math.log,
}


def eval_expr(expr: str, env: dict[str, float]) -> float:
    """Evaluate a SPICE parameter expression (``{...}`` or ``'...'``) with the
    names in *env* (case-insensitive). Only arithmetic and the nominal value
    of agauss/gauss/exp/sqrt are allowed; an unknown name raises KeyError."""
    e = expr.strip()
    if (e.startswith("{") and e.endswith("}")) or (e.startswith("'") and e.endswith("'")):
        e = e[1:-1]
    e = _expand_suffixes(e)
    lenv = {k.lower(): v for k, v in env.items()}
    tree = ast.parse(e.replace("^", "**"), mode="eval")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            ops = {ast.Add: lambda: a + b, ast.Sub: lambda: a - b, ast.Mult: lambda: a * b,
                   ast.Div: lambda: a / b, ast.Pow: lambda: a ** b}
            for k, f in ops.items():
                if isinstance(node.op, k):
                    return f()
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            if isinstance(node.op, ast.USub):
                return -v
            if isinstance(node.op, ast.UAdd):
                return v
        if isinstance(node, ast.Name):
            key = node.id.lower()
            if key not in lenv:
                raise KeyError(node.id)
            return float(lenv[key])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = _FUNCS.get(node.func.id.lower())
            if fn is not None:
                return float(fn(*[ev(a) for a in node.args]))
        raise ValueError(f"unsupported expression element in {expr!r}: {ast.dump(node)[:80]}")

    return ev(tree)


_ASSIGN_RE = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\{[^}]*\}(?:\s*\+\s*[^\s;]+)?|'[^']*'|[^\s;]+)"
)


def parse_params(text: str) -> dict[str, str]:
    """``name -> raw value`` from every ``.param`` line and ``+`` continuation
    in *text* (comments after ``;`` and ``*`` comment lines ignored). A
    ``.subckt`` header's own ``w=1 l=1`` defaults are included."""
    out: dict[str, str] = {}
    in_param = False
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].rstrip()
        s = line.strip()
        if not s or s.startswith("*"):
            continue
        low = s.lower()
        if low.startswith(".param"):
            in_param = True
            body = s[len(".param"):]
        elif s.startswith("+") and in_param:
            body = s[1:]
        elif low.startswith(".subckt"):
            in_param = True  # header '+ w=1 l=1' continuations
            body = " ".join(t for t in s.split()[2:] if "=" in t)
        else:
            in_param = False
            continue
        for m in _ASSIGN_RE.finditer(body):
            out[m.group(1)] = m.group(2)
    return out


def eval_corner_param(raw: str) -> float:
    """Evaluate a ``{nom+corner_factor*delta} + process_mc_factor*MC_PR_SWITCH*...``
    corner parameter at ``corner_factor=1`` with the Monte Carlo switches off."""
    env = {"corner_factor": 1.0, "process_mc_factor": 1.0, "mc_pr_switch": 0.0,
           "mc_mm_switch": 0.0, "mismatch_factor": 1.0}
    m = re.fullmatch(r"\s*(\{[^}]*\})\s*(?:\+\s*(.+))?", raw)
    if not m:
        return eval_expr(raw, env)
    nominal = eval_expr(m.group(1), env)
    if m.group(2):
        tail = m.group(2)
        if "MC_PR_SWITCH" not in tail and "MC_MM_SWITCH" not in tail:
            raise ValueError(f"corner parameter tail is not a Monte Carlo term: {raw!r}")
        nominal += eval_expr(tail, env)
    return nominal


# --------------------------------------------------------------------------
# Devices
# --------------------------------------------------------------------------

MIM_FORMULA_RE = re.compile(
    r"wc\s*=\s*\{w\+sw_cap_mim_dw\*1e6\}.*?lc\s*=\s*\{l\+sw_cap_mim_dw\*1e6\}.*?carea\s*=\s*\{sw_cap_mim_ca\*wc\*lc",
    re.S,
)


def mim_subckt_formula_ok(models_capacitors_text: str, name: str) -> bool:
    """True iff *name*'s subckt in the combined ``models_capacitors.spice`` is
    the area-only law ``C = sw_cap_mim_ca*(w+dw)*(l+dw)`` this study evaluates."""
    m = re.search(rf"\.subckt\s+{re.escape(name)}\b(.*?)\.ends", models_capacitors_text, re.S | re.I)
    return bool(m and MIM_FORMULA_RE.search(m.group(1)))


def mim_cap_f(ca_f_per_um2: float, dw_um: float, w_um: float, l_um: float) -> float:
    return ca_f_per_um2 * (w_um + dw_um) * (l_um + dw_um)


def vpp_ctot(model_text: str, env: dict[str, float]) -> float | None:
    """The model's nominal plate-to-plate capacitance ``ctot_a`` (F) under the
    corner factors in *env*; None when the model has no evaluable ``ctot_a``."""
    p = parse_params(model_text)
    raw = p.get("ctot_a")
    if raw is None:
        return None
    full = dict(env)
    full.update({"mult": 1.0, "mc_mm_switch": 0.0, "mc_pr_switch": 0.0, "mf": 1.0})
    try:
        return eval_expr(raw, full)
    except (KeyError, ValueError, ZeroDivisionError):
        return None


def vpp_rat_sum(model_text: str) -> float | None:
    """Sum of the model's ``rat_*`` split fractions (1.0 when ``ctot_a`` is
    the whole plate-to-plate capacitance split across levels)."""
    p = parse_params(model_text)
    rats = [v for k, v in p.items() if re.fullmatch(r"rat_[a-z0-9]+", k, re.I)]
    if not rats:
        return None
    try:
        return round(sum(eval_expr(v, {}) for v in rats), 6)
    except (KeyError, ValueError):
        return None


VPP_NAME_RE = re.compile(r"sky130_fd_pr__cap_vpp_(\d+)p(\d+)x(\d+)p(\d+)_(.+)$")


def vpp_name_dims(name: str) -> tuple[float, float] | None:
    """Nominal W x L the PDK encodes in a vpp cell name (informational only;
    the study's area uses the measured .mag bbox)."""
    m = VPP_NAME_RE.match(name)
    if not m:
        return None
    return float(f"{m.group(1)}.{m.group(2)}"), float(f"{m.group(3)}.{m.group(4)}")


MAG_LAYER_MAP = {
    "locali": "li1", "metal1": "met1", "metal2": "met2", "metal3": "met3",
    "metal4": "met4", "metal5": "met5", "poly": "poly",
}


def mag_bbox(text: str) -> dict | None:
    """Bounding box (um) and conductor levels of a flat magic cell.

    Units: magic's internal unit is 0.01 um x (magscale denominator/numerator)
    for sky130 (``magscale 1 2`` -> 0.005 um). Returns None for a cell that
    instantiates subcells (``use``) -- its bbox is not the union of its own
    rects -- or that has no geometry."""
    scale = None
    xs: list[int] = []
    ys: list[int] = []
    layers: set[str] = set()
    cur = None
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("magscale"):
            a, b = s.split()[1:3]
            scale = 0.01 * int(a) / int(b)
            continue
        if s.startswith("use "):
            return None
        m = re.match(r"<< (\S+) >>", s)
        if m:
            cur = m.group(1)
            continue
        if s.startswith("rect ") and cur not in (None, "labels", "properties", "checkpaint", "end"):
            x0, y0, x1, y1 = (int(v) for v in s.split()[1:5])
            xs += [x0, x1]
            ys += [y0, y1]
            if cur in MAG_LAYER_MAP:
                layers.add(MAG_LAYER_MAP[cur])
    if scale is None or not xs:
        return None
    w = (max(xs) - min(xs)) * scale
    h = (max(ys) - min(ys)) * scale
    order = ["poly", "li1", "met1", "met2", "met3", "met4", "met5"]
    return {"w_um": round(w, 6), "h_um": round(h, 6), "area_um2": round(w * h, 6),
            "levels": [lv for lv in order if lv in layers], "unit_um": scale}


def var_soa(model_text: str, flavor: str) -> dict[str, float] | None:
    """The varactor model file's own ``__vgs_min`` / ``__vgs_max`` parameters."""
    p = parse_params(model_text)
    lo = p.get(f"sky130_fd_pr__cap_var_{flavor}__vgs_min")
    hi = p.get(f"sky130_fd_pr__cap_var_{flavor}__vgs_max")
    if lo is None or hi is None:
        return None
    return {"vgs_min_v": eval_expr(lo, {}), "vgs_max_v": eval_expr(hi, {})}


# --------------------------------------------------------------------------
# Netlist / logs
# --------------------------------------------------------------------------


def netlist_caps(netlist_text: str) -> list[dict]:
    """Every capacitor element (``C<name> n1 n2 value``) inside the DUT
    subcircuit ``ldo_3v3in_1v8out`` -- terminals and value, read, not typed."""
    out = []
    inside = False
    for raw in netlist_text.splitlines():
        toks = raw.split()
        if not toks:
            continue
        if toks[0].lower() == ".subckt":
            inside = len(toks) > 1 and toks[1] == "ldo_3v3in_1v8out"
            continue
        if toks[0].lower() == ".ends":
            inside = False
            continue
        if inside and toks[0][0] in "Cc" and len(toks) >= 4:
            out.append({"name": toks[0], "nets": [toks[1], toks[2]], "value_f": spice_number(toks[3])})
    return out


def set_load(netlist_text: str, value: str) -> str:
    """Rewrite the testbench's single ``ILOAD VOUT 0 <v>`` line."""
    pat = re.compile(r"^(ILOAD\s+VOUT\s+0\s+)(\S+)(.*)$", re.M)
    hits = pat.findall(netlist_text)
    if len(hits) != 1:
        raise ValueError(f"expected exactly one ILOAD line, found {len(hits)}")
    return pat.sub(lambda m: m.group(1) + value + m.group(3), netlist_text)


def node_ident(net: str) -> str:
    """Vector name of a DUT net as seen from the testbench (instance xldo)."""
    return net.lower() if net.upper() in ("VIN", "VOUT", "0") else f"xldo.{net.lower()}"


def meas_name(prefix: str, net: str) -> str:
    return f"{prefix}_{re.sub(r'[^a-z0-9]', '_', net.lower())}"


# --------------------------------------------------------------------------
# Area arithmetic and verdicts
# --------------------------------------------------------------------------


def c_from_vi(vi: float | None, freq_hz: float) -> float | None:
    """Capacitance from the imaginary part of the node voltage of a capacitor
    driven by a 1 A AC current source: V = R + 1/(j w C)  =>  C = -1/(w Im V).
    A series resistance only moves the real part. None if not capacitive."""
    if vi is None or not math.isfinite(vi) or vi >= 0 or freq_hz <= 0:
        return None
    return -1.0 / (2.0 * math.pi * freq_hz * vi)


def area_for(c_f: float, density_f_per_um2: float) -> float:
    if density_f_per_um2 <= 0:
        raise ValueError("density must be positive")
    return c_f / density_f_per_um2


def beside_total_um2(core_without_caps_um2: float, cap_area_um2: float) -> float:
    """#246 scenario-E style: capacitors placed beside the core."""
    return core_without_caps_um2 + cap_area_um2


def fit_verdict(beside_drawn_total_um2: float, keepout_known: bool, overlay_possible: bool,
                overlay_evidenced_below_limit: bool, limit_um2: float = LIMIT_UM2) -> str:
    """One option's placement verdict.

    - ``fits``: a drawn, DRC/LVS-checked overlay record puts it below the limit;
    - ``does-not-fit``: even the drawn-capacitor area alone (a lower bound)
      breaks the limit beside the core, and the option cannot overlay;
    - ``not-established``: anything else (e.g. drawn area fits but the
      keep-out-inclusive area is unmeasured). Missing data is never a no-fit.
    """
    if overlay_evidenced_below_limit:
        return "fits"
    if beside_drawn_total_um2 >= limit_um2 and not overlay_possible:
        return "does-not-fit"
    return "not-established"


def outcome(option_verdicts: dict[str, str], evidence_complete: bool) -> str:
    """The record's single terminal outcome.

    (a) a recommendation that fits -- only with complete evidence;
    (b) "no option fits" -- only with complete evidence AND every option
        ``does-not-fit``;
    (c) inconclusive/unmeasured -- everything else. Missing evidence can never
        produce (b).
    """
    if not evidence_complete:
        return "c"
    if any(v == "fits" for v in option_verdicts.values()):
        return "a"
    if option_verdicts and all(v == "does-not-fit" for v in option_verdicts.values()):
        return "b"
    return "c"


def interp(xs: list[float], ys: list[float], x: float) -> float | None:
    """Linear interpolation on sorted *xs*; None outside the range."""
    if not xs or x < xs[0] or x > xs[-1]:
        return None
    for i in range(1, len(xs)):
        if x <= xs[i]:
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return ys[-1]


def rel_path(p: Path, root: Path) -> str:
    try:
        return str(p.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(p)
