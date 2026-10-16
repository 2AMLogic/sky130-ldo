#!/usr/bin/env python3
"""Issue #323 diagnostic deck generator (diagnostic bench copies only).

Reads baseline.deck.spice (verbatim extract of the deck corner-run.py gave
ngspice for record 20261011-092557-7a4e0cc) and emits an instrumented copy
with extra saves + wrdata. Optional --edit applies a named, explicit
intervention (see EDITS); the production DUT is never modified.
"""
import sys, re
P = "@m.xldo.{n}.msky130_fd_pr__{t}[{p}]"
DEV = {  # name -> (type, params)
    "xm_pass": ("pfet_g5v0d10v5", ["id", "vgs", "vds", "vdsat", "vth", "gm"]),
    "xm_sense": ("pfet_g5v0d10v5", ["id", "vgs", "vds"]),
    "xm_clim": ("pfet_g5v0d10v5", ["id", "vgs", "vds", "vdsat"]),
    "xm_tshut": ("pfet_g5v0d10v5", ["id", "vgs", "vds"]),
    "xm_mirp2": ("pfet_g5v0d10v5", ["id", "vgs", "vds", "vdsat"]),
    "xm_mir2": ("nfet_g5v0d10v5", ["id", "vgs", "vds", "vdsat"]),
    "xm_in1": ("pfet_g5v0d10v5", ["id"]),
    "xm_in2": ("pfet_g5v0d10v5", ["id"]),
    "xm_tail": ("pfet_g5v0d10v5", ["id", "vds", "vdsat"]),
}
NODES = ["vin", "vout", "xldo.ea_out", "xldo.biasp", "xldo.ea_tail", "xldo.ea_d1",
         "xldo.ea_d2", "xldo.pb", "xldo.cl_cmp", "xldo.cl_sns", "xldo.ts_cmp",
         "xldo.amp_enn", "xldo.fb"]
EDITS = {
    # Probe A: isolate the gate-drive path -- remove ONLY M_CLIM, M_TSHUT (the two
    # EA_OUT pull-up clamps) from the gate node by deleting their drain tie
    # (drain -> private floating node). Pass device, EA and bias untouched.
    "no_clamps": [
        (r"^XM_CLIM EA_OUT ", "XM_CLIM XCLIM_D "),
        (r"^XM_TSHUT EA_OUT ", "XM_TSHUT XTSHUT_D "),
    ],
    # Probe B: slower ramp, same everything else (14ms->62ms end, same slope /8).
    "slow_ramp": [
        (r"6m 'vsup' 14m 'vsup-2.13'\)", "6m 'vsup' 54m 'vsup-2.13')"),
        (r"^tran 10u 14m uic", "tran 10u 54m uic"),
    ],
}
def ideal_tail(d):
    """Probe A: replace ONLY XM_TAIL (EA tail current source, 2-line instance)
    by an ideal 3.27uA source from a separate 3.3V rail (the baseline's settled
    pre-ramp tail current, xm_tail.id = 3.2744uA at 3.30V/50mA). Removes the
    tail's Vds-headroom dependence on the ramped VIN; every other device, the
    pass device and the clamp network are untouched."""
    pat = r"^XM_TAIL EA_TAIL BIASP VIN VIN [^\n]*\n(?:\+[^\n]*\n)+"
    d, n = re.subn(pat, "ITAIL_IDEAL VINA EA_TAIL DC 3.2744u\n", d, flags=re.M)
    assert n == 1
    d, n = re.subn(r"^\.subckt ldo_3v3in_1v8out VOUT VREF EN VIN$", ".subckt ldo_3v3in_1v8out VOUT VREF EN VIN VINA", d, flags=re.M); assert n == 1
    d, n = re.subn(r"^xldo VOUT VREF EN VIN ldo_3v3in_1v8out", "xldo VOUT VREF EN VIN VINA ldo_3v3in_1v8out", d, flags=re.M); assert n == 1
    d, n = re.subn(r"^VVREF VREF 0 1.2", "VVREF VREF 0 1.2\nVVINA VINA 0 3.3", d, flags=re.M); assert n == 1
    return d

def main():
    out, edit, dat = sys.argv[1], sys.argv[2], sys.argv[3]
    d = open("baseline.deck.spice").read()
    if edit == "ideal_tail":
        d = ideal_tail(d)
    for pat, rep in EDITS.get(edit, []):
        d, n = re.subn(pat, rep, d, flags=re.M)
        assert n == 1, (pat, n)
    saves = []
    vecs = [f"v({n})" for n in NODES] + ["i(vvin)"]
    if edit == "ideal_tail": vecs = vecs  # tail saves skipped below (wrdata width differs)
    for n, (t, ps) in DEV.items():
        if edit == "ideal_tail" and n == "xm_tail": continue
        for p in ps:
            saves.append(P.format(n=n, t=t, p=p))
    # a floating private node needs a bleed to stay solvable
    extra = ""
    if edit == "no_clamps":
        extra = "RXCLIM XCLIM_D 0 1G\nRXTSHUT XTSHUT_D 0 1G\n"
    i = d.index(".control")
    ctl = d[i:]
    ctl = ctl.replace("tran 10u", "save all " + " ".join(saves) + "\ntran 10u", 1) if False else ctl
    ctl = ctl.replace("let meas_dropout_v",
        "wrdata %s %s %s\nlet meas_dropout_v" % (dat, " ".join(vecs), " ".join(saves)), 1)
    ctl = ctl.replace("save all\n", "save all " + " ".join(saves) + "\n", 1)
    open(out, "w").write(d[:i] + extra + ctl)
main()
