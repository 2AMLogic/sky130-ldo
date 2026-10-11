#!/usr/bin/env python3
"""Issue #339 analysis: validated crossing/contour extraction + comparison tables.

Pure stdlib. Every gate failure makes a result INVALID with named reasons; an
invalid result never yields a dropout number that can be read as a pass
(`dropout_v` is None). Reads wrdata files (optionally .gz) written by
make_probe_deck.py.

usage:
  analyze.py tran <name>                      # <name>.dat + .columns.json + .stdout.txt
  analyze.py calib-points <name> <out.json>   # saved-terminal replay points
  analyze.py calib <calib.dat> <points.json> <out.txt>
  analyze.py rounded <calib.dat> <refine.dat> <out.txt>
  analyze.py contour <dat> <label> <out.txt>  # 50 mA contour from a nested DC
  analyze.py compare <name> [<name> ...]      # side-by-side table
  analyze.py provenance <out.json> <file> ...
"""
import gzip
import hashlib
import json
import math
import re
import sys
from bisect import bisect_left
from pathlib import Path

VTARGET = 1.764       # 98 % of 1.8 V, the experiment's dropout crossing
VSUP = 3.3
RAMP_T0, RAMP_T1 = 6e-3, 14e-3
PRE_T = 5.9e-3
LOAD_A = 0.050
SPEC_DROPOUT_V = 0.300
MEAS_AGREE_V = 5e-4   # ngspice `meas` vs this interpolation, declared tolerance

SOLVER_BAD = [r"warning", r"error", r"timestep too small", r"singular matrix",
              r"no convergence", r"convergence", r"failed", r"gmin stepping",
              r"source stepping", r"trouble"]


# ----------------------------------------------------------------- parsing
def read_text(path):
    p = Path(path)
    if p.exists():
        return p.read_text()
    gz = Path(str(path) + ".gz")
    with gzip.open(gz, "rt") as f:
        return f.read()


def parse_wrdata(text, ncols):
    """rows of [scale, v0, scale, v1, ...] -> (scale list, {k: values}).
    Returns (None, reason) on a malformed file; nonfinite values are kept so the
    validity gate can name them."""
    scale, cols, bad = [], [[] for _ in range(ncols)], []
    for ln, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = [float(x) for x in line.split()]
        except ValueError:
            return None, f"unparseable token on line {ln}"
        if len(r) != 2 * ncols:
            bad.append(ln)
            continue
        scale.append(r[0])
        for k in range(ncols):
            cols[k].append(r[1 + 2 * k])
    if bad:
        return None, f"{len(bad)} rows with wrong width (first line {bad[0]})"
    if not scale:
        return None, "no data rows"
    return scale, cols


def interp(x, xs, ys):
    i = bisect_left(xs, x)
    if i <= 0:
        return ys[0]
    if i >= len(xs):
        return ys[-1]
    if xs[i] == xs[i - 1]:
        return ys[i]
    f = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
    return ys[i - 1] + f * (ys[i] - ys[i - 1])


def solver_findings(log):
    """Lines of an ngspice log that indicate a solver problem. The benign
    `option SCALE` notices and the PDK's own banner are ignored."""
    out = []
    for ln in log.splitlines():
        low = ln.lower()
        if "option scale" in low:
            continue
        if any(re.search(p, low) for p in SOLVER_BAD):
            out.append(ln.strip())
    return out


def log_meas(log, name="meas_dropout_v"):
    m = re.search(rf"^{name}\s*=\s*([-+0-9.eE]+)", log, flags=re.M)
    return float(m.group(1)) if m else None


# ----------------------------------------------------------- transient gate
def analyze_tran(t, cols, log, load_a=LOAD_A):
    """cols: {label: values}. Returns dict with valid, reasons, and numbers.
    dropout_v is None unless every gate passes."""
    res = {"valid": True, "reasons": [], "dropout_v": None}

    def bad(msg):
        res["valid"] = False
        res["reasons"].append(msg)

    n = len(t)
    for need in ("v(vin)", "v(vout)", "v(en)", "xm_pass.id"):
        if need not in cols:
            bad(f"missing column {need}")
    if not res["valid"]:
        return res
    if any(len(v) != n for v in cols.values()):
        bad("column length mismatch")
        return res
    nonfin = sorted(k for k, v in cols.items() if not all(math.isfinite(x) for x in v))
    if not all(math.isfinite(x) for x in t):
        nonfin.append("time")
    if nonfin:
        bad("nonfinite values in " + ", ".join(nonfin))
        return res
    if any(t[i] <= t[i - 1] for i in range(1, n)):
        bad("time not strictly increasing")
        return res
    if t[-1] < RAMP_T1 - 1e-9:
        bad(f"run ends at {t[-1]*1e3:.3f} ms, before the {RAMP_T1*1e3:.0f} ms ramp end")
        return res

    vin, vout, en = cols["v(vin)"], cols["v(vout)"], cols["v(en)"]
    # initial-condition contract: uic cold start, EN low, output discharged
    if abs(vout[0]) > 0.1 or abs(en[0]) > 0.1:
        bad(f"not a cold start (vout[0]={vout[0]:.3g}, en[0]={en[0]:.3g})")
    # regulating at the starting supply
    sel = [vout[i] for i in range(n) if 5.5e-3 <= t[i] <= 6.0e-3]
    if not sel:
        bad("no samples in the 5.5-6 ms pre-ramp window")
        return res
    vpre = sum(sel) / len(sel)
    res["vout_pre"] = vpre
    if not (VTARGET + 0.01 <= vpre <= 1.836):
        bad(f"not regulating at the starting supply (mean VOUT 5.5-6 ms = {vpre:.4f} V)")
    ipre = abs(interp(PRE_T, t, cols["xm_pass.id"]))
    res["ipass_pre"] = ipre
    if not (0.9 * load_a <= ipre <= 1.1 * load_a):
        bad(f"load not established at the start (pass Id = {ipre*1e3:.3f} mA)")
    # crossing: first fall through VTARGET after the ramp starts
    ix = None
    for i in range(1, n):
        if t[i] > RAMP_T0 and vout[i - 1] >= VTARGET > vout[i]:
            ix = i
            break
    if ix is None:
        bad("missing crossing: VOUT never falls through the target during the ramp")
    else:
        f = (vout[ix - 1] - VTARGET) / (vout[ix - 1] - vout[ix])
        tx = t[ix - 1] + f * (t[ix] - t[ix - 1])
        vx = interp(tx, t, vin)
        res.update(t_cross=tx, vin_cross=vx, dropout_interp=vx - VTARGET)
    # solver gates
    sf = solver_findings(log)
    if sf:
        bad(f"solver diagnostics present ({len(sf)}): {sf[0]}")
    mv = log_meas(log)
    if mv is None:
        bad("ngspice meas_dropout_v missing from log (meas failed or run incomplete)")
    elif ix is not None and abs(mv - res["dropout_interp"]) > MEAS_AGREE_V:
        bad(f"ngspice meas {mv:.6f} disagrees with trajectory crossing "
            f"{res['dropout_interp']:.6f} by more than {MEAS_AGREE_V*1e3:.1f} mV")
    res["dropout_meas"] = mv
    if res["valid"]:
        res["dropout_v"] = res["dropout_interp"]
    return res


def observations(t, cols, tt):
    """Selected quantities at time tt (interpolated)."""
    o = {}
    for k, v in cols.items():
        o[k] = interp(tt, t, v)
    return o


# ------------------------------------------------------------ isolated pass
def pass_rows(text):
    scale, cols = parse_wrdata(text, 10)
    if scale is None:
        return None, cols
    names = ["g", "d", "s", "i_vd", "i_vs", "id", "vgs", "vds", "vdsat", "gm"]
    return {n: cols[k] for k, n in enumerate(names)}, None


def contour_50mA(rows, target=LOAD_A):
    """Group by gate; per gate find the terminal |Vsd| where |Id|=target.
    Returns list of dicts (status ok | no_crossing | invalid:<why>)."""
    n = len(rows["g"])
    for k, v in rows.items():
        if not all(math.isfinite(x) for x in v):
            return [{"status": f"invalid: nonfinite in {k}"}]
    groups = {}
    for i in range(n):
        groups.setdefault(round(rows["g"][i], 6), []).append(i)
    out = []
    for g in sorted(groups, reverse=True):
        idx = sorted(groups[g], key=lambda i: rows["s"][i] - rows["d"][i])
        vsd = [rows["s"][i] - rows["d"][i] for i in idx]
        idd = [abs(rows["id"][i]) for i in idx]
        vds = [abs(rows["vds"][i]) for i in idx]
        src = rows["s"][idx[0]]
        rec = {"vg": g, "vsg": src - g, "n": len(idx)}
        if any(idd[j] < idd[j - 1] - 1e-9 for j in range(1, len(idd))):
            rec["status"] = "invalid: Id not monotone in Vsd"
        elif idd[-1] < target:
            rec.update(status="no_crossing", id_max=idd[-1], vsd_max=vsd[-1])
        elif idd[0] >= target:
            rec["status"] = "invalid: target already exceeded at the first grid point"
        else:
            j = next(j for j in range(1, len(idd)) if idd[j] >= target)
            f = (target - idd[j - 1]) / (idd[j] - idd[j - 1])
            rec.update(status="ok", vsd=vsd[j - 1] + f * (vsd[j] - vsd[j - 1]),
                       vds_model=vds[j - 1] + f * (vds[j] - vds[j - 1]))
        out.append(rec)
    return out


def polarity_problems(rows):
    p = []
    for i in range(len(rows["g"])):
        idd = abs(rows["id"][i])
        if idd < 1e-6:
            continue
        if rows["i_vd"][i] < 0 or rows["i_vs"][i] > 0:
            p.append(f"row {i}: current direction i(vd)={rows['i_vd'][i]:.3g} i(vs)={rows['i_vs'][i]:.3g}")
        elif abs(abs(rows["i_vd"][i]) - idd) > 1e-3 * idd + 1e-9:
            p.append(f"row {i}: |i(vd)| != |Id| ({abs(rows['i_vd'][i]):.6g} vs {idd:.6g})")
        if rows["s"][i] < rows["d"][i]:
            p.append(f"row {i}: source below drain")
    return p[:5]


def rounded_tolerance(gm, gds):
    """Predeclared tolerance for comparing against #323's rounded figures
    (Vsg 1.446 V, Vds 0.389 V, ~49.7 mA): the half-LSB of each rounded voltage
    mapped through the local sensitivities, plus half-LSB of the 0.1 mA figure."""
    return gm * 0.5e-3 + gds * 0.5e-3 + 0.05e-3


# ------------------------------------------------------------------- tables
def fmt(x, spec=".4g"):
    return "n/a" if x is None else format(x, spec)


def tran_report(name, res, t, cols):
    L = [f"== {name}: {'VALID' if res['valid'] else 'INVALID'} =="]
    for r in res["reasons"]:
        L.append(f"  invalid reason: {r}")
    L.append(f"dropout_v (valid only) = {fmt(res['dropout_v'], '.6f')}  "
             f"interp = {fmt(res.get('dropout_interp'), '.6f')}  meas = {fmt(res.get('dropout_meas'), '.6f')}")
    if "t_cross" in res:
        L.append(f"crossing t = {res['t_cross']*1e3:.6f} ms  VIN = {res['vin_cross']:.5f} V")
    if res.get("vout_pre") is not None:
        L.append(f"pre-ramp mean VOUT = {res['vout_pre']:.5f} V  pass Id = {res.get('ipass_pre', 0)*1e3:.3f} mA")
    if cols and res["reasons"] and not all(k in cols for k in ("v(vin)",)):
        return "\n".join(L) + "\n"
    snaps = [("pre-ramp settled (5.9 ms)", PRE_T)]
    if "t_cross" in res:
        snaps.append(("crossing", res["t_cross"]))
    snaps.append(("end of ramp", t[-1]))
    for lab, tt in snaps:
        L.append(f"--- {lab} (t={tt*1e3:.3f} ms)")
        try:
            for k, v in observations(t, cols, tt).items():
                L.append(f"  {k:20s} {v:+.6g}")
        except Exception as e:  # noqa: BLE001 -- report, do not hide
            L.append(f"  observation failed: {e}")
    return "\n".join(L) + "\n"


def load_run(name):
    cols_names = json.loads(Path(f"{name}.dat.columns.json").read_text())
    text = read_text(f"{name}.dat")
    scale, cols = parse_wrdata(text, len(cols_names))
    log = read_text(f"{name}.stdout.txt")
    if scale is None:
        return None, None, log, cols
    return scale, dict(zip(cols_names, cols)), log, None


def cmd_tran(name):
    t, cols, log, err = load_run(name)
    if t is None:
        res = {"valid": False, "reasons": [f"malformed data: {err}"], "dropout_v": None}
        txt = f"== {name}: INVALID ==\n  invalid reason: malformed data: {err}\n"
    else:
        res = analyze_tran(t, cols, log)
        txt = tran_report(name, res, t, cols)
        if res["valid"] or "t_cross" in res:
            res["pre"] = {k: abs(v) for k, v in observations(t, cols, PRE_T).items()
                          if k.startswith(("xm_", "i("))}
            res["pre"].update({k: v for k, v in observations(t, cols, PRE_T).items() if k.startswith("v(")})
            res["at_cross"] = observations(t, cols, res["t_cross"]) if "t_cross" in res else None
            eo = cols["v(xldo.ea_out)"]
            kmin = min((i for i in range(len(t)) if t[i] > RAMP_T0), key=lambda i: eo[i])
            res["ea_out_min"] = {"v": eo[kmin], "vin": cols["v(vin)"][kmin], "t": t[kmin]}
    Path(f"{name}.analysis.txt").write_text(txt)
    Path(f"{name}.result.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(txt)


def cmd_calib_points(name, out):
    t, cols, _log, err = load_run(name)
    assert t is not None, err
    res = analyze_tran(t, cols, read_text(f"{name}.stdout.txt"))
    pts, meta = [], []
    targets = [("pre-ramp", None, 5.9e-3)]
    for v in (2.9, 2.5, 2.3, 2.2):
        targets.append((f"VIN~{v}", v, None))
    targets.append(("crossing", None, res["t_cross"]))
    for lab, vt, tt in targets:
        if vt is not None:
            i = next(i for i in range(len(t)) if t[i] > RAMP_T0 and cols["v(vin)"][i] <= vt)
        else:
            i = min(range(len(t)), key=lambda i: abs(t[i] - tt))
        vs, vg, vd = cols["v(vin)"][i], cols["v(xldo.ea_out)"][i], cols["v(vout)"][i]
        pts.append([vs, vg, vd])
        meta.append({"label": lab, "t": t[i], "id": abs(cols["xm_pass.id"][i]),
                     "vgs": abs(cols["xm_pass.vgs"][i]), "vds": abs(cols["xm_pass.vds"][i]),
                     "ivin": cols["i(vvin)"][i], "dvout_dt_load_a": None})
    Path(out).write_text(json.dumps(pts) + "\n")
    Path(out.replace(".json", ".expected.json")).write_text(json.dumps(meta, indent=1) + "\n")


def cmd_calib(dat, points, out, rtol=2e-3, vds_tol=1e-3):
    rows, err = pass_rows(read_text(dat))
    exp = json.loads(Path(points.replace(".json", ".expected.json")).read_text())
    L = [f"calibration: replay of #323-style saved terminal voltages (declared tolerances: "
         f"|dId|/Id <= {rtol}, |d Vds_model| <= {vds_tol*1e3:.1f} mV)"]
    ok = rows is not None
    if rows is None:
        L.append(f"INVALID: {err}")
    else:
        prob = polarity_problems(rows)
        L += [f"polarity problem: {p}" for p in prob]
        ok = ok and not prob and len(rows["id"]) == len(exp)
        for k, e in enumerate(exp):
            i_b, v_b = abs(rows["id"][k]), abs(rows["vds"][k])
            good = (abs(i_b - e["id"]) <= rtol * e["id"]) and (abs(v_b - e["vds"]) <= vds_tol)
            ok = ok and good
            L.append(f"  {e['label']:10s} Vsg={rows['s'][k]-rows['g'][k]:.4f} V  "
                     f"Id bench={i_b*1e3:.4f} mA saved={e['id']*1e3:.4f} mA (d={((i_b-e['id'])/e['id']):+.2e})  "
                     f"Vds_model bench={v_b:.5f} saved={e['vds']:.5f}  "
                     f"{'ok' if good else 'MISMATCH'}")
    L.append("CALIBRATION " + ("VALID" if ok else "INVALID"))
    Path(out).write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return ok


def cmd_rounded(calib_dat, refine_dat, out):
    """Compare the saved #323 ROUNDED crossing figures (model-internal Vgs 1.446 V,
    model-internal Vds 0.389 V, ~49.7 mA) with the calibrated bench's crossing
    replay, using the predeclared half-LSB tolerance (rounded_tolerance)."""
    cal, e1 = pass_rows(read_text(calib_dat))
    ref, e2 = pass_rows(read_text(refine_dat))
    L = []
    ok = cal is not None and ref is not None
    if not ok:
        L.append(f"INVALID: {e1 or e2}")
    else:
        k = len(cal["id"]) - 1  # crossing replay is the last calibration point
        gm = abs(cal["gm"][k])
        idx = sorted((i for i in range(len(ref["g"])) if abs(ref["g"][i] - 0.714) < 1e-6),
                     key=lambda i: abs(ref["vds"][i]))
        vds = [abs(ref["vds"][i]) for i in idx]
        idd = [abs(ref["id"][i]) for i in idx]
        j = next(j for j in range(1, len(vds)) if vds[j] >= abs(cal["vds"][k]))
        gds = (idd[j] - idd[j - 1]) / (vds[j] - vds[j - 1])
        tol = rounded_tolerance(gm, gds)
        i_b = abs(cal["id"][k])
        vgs_m, vds_m = abs(cal["vgs"][k]), abs(cal["vds"][k])
        checks = [("model Vgs", vgs_m, 1.446, 0.5e-3), ("model Vds", vds_m, 0.389, 0.5e-3),
                  ("Id", i_b, 49.7e-3, tol)]
        L.append(f"rounded-figure check at the replayed crossing sample (gm={gm:.4g} S, "
                 f"gds={gds:.4g} S, declared Id tolerance={tol*1e3:.3f} mA = gm*0.5mV + gds*0.5mV + 0.05mA)")
        for nm, got, want, tl in checks:
            good = abs(got - want) <= tl
            ok = ok and good
            L.append(f"  {nm:10s} bench={got:.6g} saved(rounded)={want:.6g} tol={tl:.3g} {'ok' if good else 'MISMATCH'}")
    L.append("ROUNDED-FIGURE CHECK " + ("VALID" if ok else "INVALID"))
    Path(out).write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return ok


def cmd_contour(dat, label, out):
    rows, err = pass_rows(read_text(dat))
    if rows is None:
        txt = f"{label}: INVALID data: {err}\n"
    else:
        L = [f"{label}: 50 mA contour (terminal |Vsd| and model-internal |Vds|)",
             "   Vg[V]   Vsg[V]   Vsd_term[V]  Vds_model[V]  (term-model)[mV]  status"]
        pol = polarity_problems(rows)
        L += [f"polarity problem: {p}" for p in pol]
        for r in contour_50mA(rows):
            if r["status"] == "ok":
                L.append(f"  {r['vg']:6.3f}  {r['vsg']:7.3f}  {r['vsd']:11.4f}  {r['vds_model']:11.4f}  "
                         f"{(r['vsd']-r['vds_model'])*1e3:14.1f}      ok")
            else:
                L.append(f"  {r.get('vg', float('nan')):6.3f}  {r.get('vsg', float('nan')):7.3f}  {'-':>11}  {'-':>11}  {'':>14}      {r['status']}")
        txt = "\n".join(L) + "\n"
    Path(out).write_text(txt)
    print(txt)


def cmd_compare(names):
    hdr = (f"{'run':8s} {'valid':6s} {'dropout[V]':>10s} {'VINx[V]':>8s} {'EA_OUT@x':>8s} "
           f"{'Vds/Vdsat@x[V]':>16s} {'tailId@x[uA]':>12s} {'climId@x[nA]':>12s} "
           f"{'ivin pre/x[mA]':>16s} {'ivina pre/x[uA]':>16s}")
    L = [hdr]
    for nm in names:
        r = json.loads(Path(f"{nm}.result.json").read_text())
        if r.get("at_cross"):
            a, p = r["at_cross"], r["pre"]
            tail = abs(a["xm_tail.id"]) * 1e6 if "xm_tail.id" in a else float("nan")
            ivina = (f"{abs(p.get('i(vvina)', 0))*1e6:.2f}/{abs(a.get('i(vvina)', 0))*1e6:.2f}"
                     if "i(vvina)" in a else "-")
            tail_s = f"{tail:.3f}" if tail == tail else "ideal"
            L.append(f"{nm:8s} {str(r['valid']):6s} {fmt(r['dropout_v'], '.4f'):>10s} {r['vin_cross']:8.4f} "
                     f"{a['v(xldo.ea_out)']:8.3f} {abs(a['xm_pass.vds']):7.3f}/{abs(a['xm_pass.vdsat']):.3f}   "
                     f"{tail_s:>12s} {abs(a['xm_clim.id'])*1e9:12.3f} "
                     f"{abs(p['i(vvin)'])*1e3:7.3f}/{abs(a['i(vvin)'])*1e3:.3f}  {ivina:>16s}")
        else:
            L.append(f"{nm:8s} {str(r['valid']):6s} {'n/a':>10s}  reasons: {'; '.join(r['reasons'])}")
    txt = "\n".join(L) + "\n"
    print(txt)
    return txt


def sha256(path):
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def cmd_provenance(out, files):
    Path(out).write_text(json.dumps({f: sha256(f) for f in files}, indent=1, sort_keys=True) + "\n")


def main(argv):
    c = argv[1]
    if c == "tran":
        cmd_tran(argv[2])
    elif c == "calib-points":
        cmd_calib_points(argv[2], argv[3])
    elif c == "calib":
        sys.exit(0 if cmd_calib(argv[2], argv[3], argv[4]) else 1)
    elif c == "rounded":
        sys.exit(0 if cmd_rounded(argv[2], argv[3], argv[4]) else 1)
    elif c == "contour":
        cmd_contour(argv[2], argv[3], argv[4])
    elif c == "compare":
        cmd_compare(argv[2:])
    elif c == "provenance":
        cmd_provenance(argv[2], argv[3:])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
