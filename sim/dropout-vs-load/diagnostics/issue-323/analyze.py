#!/usr/bin/env python3
"""Tabulate wrdata output from make_probe_deck.py decks (issue #323). Pure stdlib."""
import sys
from bisect import bisect_left
src = open("make_probe_deck.py").read().replace("\nmain()\n", "\n")
ns = {}; exec(src, ns)
names = [f"v({n})" for n in ns["NODES"]] + ["i(vvin)"]
for n, (t, ps) in ns["DEV"].items():
    for p in ps: names.append(f"{n}.{p}")
rows = [list(map(float, l.split())) for l in open(sys.argv[1])]
t = [r[0] for r in rows]
cols = {nm: [r[1 + 2 * k] for r in rows] for k, nm in enumerate(names) if 1 + 2 * k < len(rows[0])}
names = [n for n in names if n in cols]
def interp(x, xs, ys):
    i = bisect_left(xs, x)
    if i <= 0: return ys[0]
    if i >= len(xs): return ys[-1]
    f = (x - xs[i-1]) / (xs[i] - xs[i-1]); return ys[i-1] + f * (ys[i] - ys[i-1])
def at(tt, nm): return interp(tt, t, cols[nm])
def show(label, tt):
    print(f"--- {label} (t={tt*1e3:.3f} ms)")
    for nm in names: print(f"  {nm:22s} {at(tt, nm):+.6g}")
vo = cols["v(vout)"]
idx = next(i for i in range(len(t)) if t[i] > 6e-3 and vo[i] < 1.764)
tx = t[idx-1] + (vo[idx-1] - 1.764) / (vo[idx-1] - vo[idx]) * (t[idx] - t[idx-1])
vx = at(tx, "v(vin)")
print("crossing t=%.6f ms vin=%.5f dropout=%.5f" % (tx*1e3, vx, vx - 1.764))
def t_of_vin(v):  # on the down ramp
    return next(t[i-1] + (cols["v(vin)"][i-1]-v)/(cols["v(vin)"][i-1]-cols["v(vin)"][i])*(t[i]-t[i-1]) for i in range(len(t)) if t[i] > 6e-3 and cols["v(vin)"][i] <= v)
if "full" in sys.argv:
    show("pre-ramp settled", 5.9e-3)
    show("VIN = crossing+0.5V", t_of_vin(vx + 0.5))
    show("VIN = crossing+0.1V", t_of_vin(vx + 0.1))
    show("crossing", tx)
    show("end of ramp", t[-1])
if "traj" in sys.argv:
    for k in range(0, 80, 1):
        v = 3.3 - 0.0 - k * 0.0
    for dv in (0, .2, .4, .6, .8, 1.0, 1.1, 1.14, 1.2):
        tt = t_of_vin(3.3 - dv)
        print("VIN=%.3f vout=%.4f ea_out=%.4f vsg_pass=%.4f vds=%.4f vdsat=%.4f vth=%.3f ipass=%.4g ivin=%.4g clim_id=%.3g tshut_id=%.3g" % (
            at(tt,"v(vin)"), at(tt,"v(vout)"), at(tt,"v(xldo.ea_out)"), -at(tt,"xm_pass.vgs"), -at(tt,"xm_pass.vds"), -at(tt,"xm_pass.vdsat"), at(tt,"xm_pass.vth"), -at(tt,"xm_pass.id"), -at(tt,"i(vvin)"), at(tt,"xm_clim.id"), at(tt,"xm_tshut.id")))
