#!/usr/bin/env python3
"""Issue #339 diagnostic deck generator (bench copies only; production untouched).

Builds, from the verbatim #323 baseline deck (identical to what corner-run.py
hands ngspice for tt / 27 C / 3.30 V; design, testbench and experiment manifest
are unchanged since #323 -- see README), either

  * an instrumented transient probe with a COMPOSABLE set of explicit edits
        ideal_tail   XM_TAIL -> ideal 3.2744 uA from separate 3.3 V rail VINA
        no_clamps    XM_CLIM / XM_TSHUT drains -> private nodes, 1 Gohm bleeds
        frozen_bias  XR_BIAS -> ideal EN-gated current (value measured pre-ramp)
  * an isolated M_PASS DC bench (calibration points / contour / refinement).

Ideal sources and disabled protection are causal diagnostics, never circuits.

usage:
  make_probe_deck.py probe <out.deck> <dat> [edit ...] [--bias-ua X]
  make_probe_deck.py pass-calib <out.deck> <dat> <points.json>
  make_probe_deck.py pass-contour <out.deck> <dat> <source_v> <vd_step> [vg_step]
Each writes <out.deck>; probes also write <dat>.columns.json (wrdata layout).
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "baseline.deck.spice"

P = "@m.xldo.{n}.msky130_fd_pr__{t}[{p}]"
DEV = {  # name -> (type, params); superset of #323 plus the bias-chain devices
    "xm_pass": ("pfet_g5v0d10v5", ["id", "vgs", "vds", "vdsat", "vth", "gm"]),
    "xm_sense": ("pfet_g5v0d10v5", ["id", "vgs", "vds"]),
    "xm_clim": ("pfet_g5v0d10v5", ["id", "vgs", "vds", "vdsat"]),
    "xm_tshut": ("pfet_g5v0d10v5", ["id", "vgs", "vds"]),
    "xm_mirp2": ("pfet_g5v0d10v5", ["id", "vgs", "vds", "vdsat"]),
    "xm_mir2": ("nfet_g5v0d10v5", ["id", "vgs", "vds", "vdsat"]),
    "xm_in1": ("pfet_g5v0d10v5", ["id"]),
    "xm_in2": ("pfet_g5v0d10v5", ["id"]),
    "xm_tail": ("pfet_g5v0d10v5", ["id", "vds", "vdsat"]),
    "xm_biasn1": ("nfet_g5v0d10v5", ["id"]),  # == R_BIAS current (diode-connected)
    "xm_biasp1": ("pfet_g5v0d10v5", ["id"]),
}
NODES = ["vin", "vout", "en", "xldo.ea_out", "xldo.biasp", "xldo.ea_tail", "xldo.ea_d1",
         "xldo.ea_d2", "xldo.pb", "xldo.cl_cmp", "xldo.cl_sns", "xldo.ts_cmp",
         "xldo.amp_enn", "xldo.fb", "xldo.nb"]
EDIT_NAMES = ("ideal_tail", "no_clamps", "frozen_bias")
TAIL_I = "3.2744u"  # baseline settled pre-ramp tail current (#323)


def _sub1(pat, rep, d):
    d, n = re.subn(pat, rep, d, flags=re.M)
    assert n == 1, (pat, n)
    return d


def _add_aux_rail(d):
    """Idempotently expose a separate 3.3 V rail VINA to the DUT."""
    if "VVINA" in d:
        return d
    d = _sub1(r"^\.subckt ldo_3v3in_1v8out VOUT VREF EN VIN$",
              ".subckt ldo_3v3in_1v8out VOUT VREF EN VIN VINA", d)
    d = _sub1(r"^xldo VOUT VREF EN VIN ldo_3v3in_1v8out",
              "xldo VOUT VREF EN VIN VINA ldo_3v3in_1v8out", d)
    return _sub1(r"^VVREF VREF 0 1\.2", "VVREF VREF 0 1.2\nVVINA VINA 0 3.3", d)


def apply_edits(d, edits, bias_ua=None):
    """Return (deck_text, extra_netlist_lines) after the named explicit edits."""
    for e in edits:
        assert e in EDIT_NAMES, e
    extra = ""
    if "ideal_tail" in edits:
        d = _add_aux_rail(d)
        pat = r"^XM_TAIL EA_TAIL BIASP VIN VIN [^\n]*\n(?:\+[^\n]*\n)+"
        d = _sub1(pat, f"ITAIL_IDEAL VINA EA_TAIL DC {TAIL_I}\n", d)
    if "no_clamps" in edits:
        d = _sub1(r"^XM_CLIM EA_OUT ", "XM_CLIM XCLIM_D ", d)
        d = _sub1(r"^XM_TSHUT EA_OUT ", "XM_TSHUT XTSHUT_D ", d)
        extra += "RXCLIM XCLIM_D 0 1G\nRXTSHUT XTSHUT_D 0 1G\n"
    if "frozen_bias" in edits:
        if bias_ua is None:
            raise ValueError("frozen_bias needs bias_ua (measured pre-ramp R_BIAS current, uA)")
        d = _add_aux_rail(d)
        # EN-gated (same PULSE as VEN) so the cold start keeps its natural EN-low state.
        d = _sub1(r"^XR_BIAS VIN NB 0 [^\n]*\n",
                  f"IBIAS_FROZEN VINA NB PULSE(0 {bias_ua}u 100u 1u 1u 100 200)\n", d)
    return d, extra


def column_names(edits):
    """wrdata column labels in order (node voltages, source currents, devices)."""
    names = [f"v({n})" for n in NODES] + ["i(vvin)"]
    if "ideal_tail" in edits or "frozen_bias" in edits:
        names.append("i(vvina)")
    for n, (_t, ps) in DEV.items():
        if "ideal_tail" in edits and n == "xm_tail":
            continue  # device no longer exists
        names += [f"{n}.{p}" for p in ps]
    return names


def _spice_vec(label):
    m = re.fullmatch(r"(xm_\w+)\.(\w+)", label)
    if not m:
        return label
    n, p = m.groups()
    return P.format(n=n, t=DEV[n][0], p=p)


def build_probe(edits, dat, baseline_text=None, bias_ua=None):
    d = baseline_text if baseline_text is not None else BASELINE.read_text()
    d, extra = apply_edits(d, edits, bias_ua)
    cols = column_names(edits)
    saves = [_spice_vec(c) for c in cols if c.startswith("xm_")]
    i = d.index(".control")
    ctl = d[i:]
    assert "save all\n" in ctl and "let meas_dropout_v" in ctl
    ctl = ctl.replace("save all\n", "save all " + " ".join(saves) + "\n", 1)
    wr = "wrdata %s %s\n" % (dat, " ".join(_spice_vec(c) for c in cols))
    ctl = ctl.replace("let meas_dropout_v", wr + "let meas_dropout_v", 1)
    return d[:i] + extra + ctl, cols


def _lib_header(baseline_text):
    m = re.search(r"^\.temp [^\n]*\n\.lib [^\n]*\n", baseline_text, flags=re.M)
    assert m
    return ".option wnflag=1\n" + m.group(0)


def pass_instance(baseline_text):
    """The committed M_PASS instance (W/L/nf/mult/m verbatim), re-wired as
    D=drain, G=gate, S=source=body (matches 'XM_PASS VOUT EA_OUT VIN VIN')."""
    m = re.search(r"^XM_PASS VOUT EA_OUT VIN VIN (sky130_fd_pr__pfet_g5v0d10v5[^\n]*\n(?:\+[^\n]*\n)*)",
                  baseline_text, flags=re.M)
    assert m, "M_PASS instance not found in baseline"
    return "XM_PASS D G S S " + m.group(1)


PASS_VECS = ["v(g)", "v(d)", "v(s)", "i(vd)", "i(vs)",
             "@m.xm_pass.msky130_fd_pr__pfet_g5v0d10v5[id]",
             "@m.xm_pass.msky130_fd_pr__pfet_g5v0d10v5[vgs]",
             "@m.xm_pass.msky130_fd_pr__pfet_g5v0d10v5[vds]",
             "@m.xm_pass.msky130_fd_pr__pfet_g5v0d10v5[vdsat]",
             "@m.xm_pass.msky130_fd_pr__pfet_g5v0d10v5[gm]"]
PASS_COLS = ["v(g)", "v(d)", "v(s)", "i(vd)", "i(vs)", "id", "vgs", "vds", "vdsat", "gm"]


def build_pass_contour(source_v, vd_step, vg_start=0.714, vg_stop=0.0, vg_step=0.017,
                       vd_span=0.5, baseline_text=None, dat="pass_contour.dat"):
    """Nested DC: inner = drain voltage source_v -> source_v-vd_span (|Vsd| 0..span),
    outer = gate vg_start -> vg_stop. Source and body at source_v."""
    b = baseline_text if baseline_text is not None else BASELINE.read_text()
    lo = source_v - vd_span
    return (f"* issue #339 isolated M_PASS DC bench: source=body={source_v} V, tt / 27 C\n"
            + _lib_header(b)
            + f"VS S 0 {source_v}\nVG G 0 {vg_start}\nVD D 0 {source_v}\n"
            + pass_instance(b)
            + ".control\nsave all " + " ".join(v for v in PASS_VECS if v.startswith("@")) + "\n"
            + f"dc VD {source_v} {lo:.6f} {-vd_step} VG {vg_start} {vg_stop} {-vg_step}\n"
            + f"wrdata {dat} " + " ".join(PASS_VECS) + "\nquit\n.endc\n.end\n")


def build_pass_calib(points, baseline_text=None, dat="pass_calib.dat"):
    """One .op per (vs, vg, vd) triple via alter; prints a wrdata row per point."""
    b = baseline_text if baseline_text is not None else BASELINE.read_text()
    lines = ["* issue #339 isolated M_PASS calibration: replays saved #323 terminal voltages",
             _lib_header(b) + "VS S 0 2.16\nVG G 0 0.714\nVD D 0 1.77\n" + pass_instance(b)
             + ".control\nsave all " + " ".join(v for v in PASS_VECS if v.startswith("@"))]
    out = []
    for k, (vs, vg, vd) in enumerate(points):
        out.append(f"alter VS dc = {vs!r}\nalter VG dc = {vg!r}\nalter VD dc = {vd!r}\nop\n"
                   + f"wrdata {dat} " + " ".join(PASS_VECS) + "\n"
                   + ("set appendwrite\n" if k == 0 else ""))
    return "\n".join(lines) + "\n" + "".join(out) + "quit\n.endc\n.end\n"


def main(argv):
    mode = argv[1]
    if mode == "probe":
        out, dat = argv[2], argv[3]
        rest = argv[4:]
        bias = None
        if "--bias-ua" in rest:
            k = rest.index("--bias-ua")
            bias = rest[k + 1]
            rest = rest[:k] + rest[k + 2:]
        text, cols = build_probe(rest, dat, bias_ua=bias)
        Path(out).write_text(text)
        Path(dat + ".columns.json").write_text(json.dumps(cols) + "\n")
    elif mode == "pass-contour":
        out, dat, src, step = argv[2], argv[3], float(argv[4]), float(argv[5])
        vg_step = float(argv[6]) if len(argv) > 6 else 0.017
        Path(out).write_text(build_pass_contour(src, step, vg_step=vg_step, dat=dat))
    elif mode == "pass-calib":
        out, dat = argv[2], argv[3]
        pts = json.loads(Path(argv[4]).read_text())
        Path(out).write_text(build_pass_calib(pts, dat=dat))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
