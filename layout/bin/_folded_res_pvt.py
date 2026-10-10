"""Pure helpers for the issue #263 folded-resistor PVT / mismatch study.

Standard library only (tests: ``layout/tests/test_folded_res_pvt.py``). The
I/O driver is ``run-folded-res-pvt.py``. The coverage matrix and the
pass/fail gates live in ``layout/folded-res-qual/pvt/matrix.json`` and were
committed before any run; nothing here may loosen them.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

JOINT_MODES = ("noj", "j1", "j4")  # model only / measured joint / 4x measured joint


def param_name(device: dict[str, Any]) -> str:
    """Name of the device's shared bias SOURCE (``corners.supply_v`` key).

    A source (its own name, which `alter` needs), not a `.param`: ngspice's ``alter`` rejects a bare parameter name
    (measured: "no such device or model name"), and klt reports no error for it.
    """
    return "Vop_" + device["schematic_device"].lower()


def bias_node(device: dict[str, Any]) -> str:
    return "nop_" + device["schematic_device"].lower()


def tag(device: str, n: int, mode: str) -> str:
    return f"r_{device.lower()}_n{n}_{mode}"


def variants(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    """Every chain in the deck: N=1 once (model only), N>=2 in all joint modes."""
    out: list[dict[str, Any]] = []
    joint = matrix["tool_pins"]["joint_ohm"]
    mult = matrix["tool_pins"]["joint_sensitivity_multiplier"]
    rj = {"noj": 0.0, "j1": joint, "j4": joint * mult}
    for dev in matrix["devices"]:
        for n in dev["candidate_segments"]:
            for mode in JOINT_MODES:
                if n == 1 and mode != "noj":
                    continue
                out.append(
                    {
                        "tag": tag(dev["schematic_device"], n, mode),
                        "device": dev["schematic_device"],
                        "segments": n,
                        "mode": mode,
                        "joint_ohm": rj[mode],
                    }
                )
    return out


def build_deck(matrix: dict[str, Any], meas_form: str = "expr") -> str:
    """One netlist, no `.lib`/`.temp` (klt sim injects those per corner).

    Each chain is its own source + N PDK resistor instances (segment
    l = L/N, same w, bulk 0) with, for the joint modes, a lumped resistor at
    each of the N-1 joints. The source voltage is a ``.param`` per device so
    ``corners.supply_v`` can step it by index.
    """
    lines = ["* issue #263 folded-resistor PVT/mismatch chains (isolated passive devices)"]
    if meas_form == "meas":
        # Older klt clients have no `expr` measurement: a B source computes R
        # as a node voltage and a two-point dc sweep of this idle source gives
        # `.meas dc` something to evaluate at.
        lines.append("Vsweep_idle sweep_idle 0 0")
        lines.append("Rsweep_idle sweep_idle 0 1k")
    for dev in matrix["devices"]:
        lines.append(f"{param_name(dev)} {bias_node(dev)} 0 {dev['mc_op_v']:g}")
    by_dev = {d["schematic_device"]: d for d in matrix["devices"]}
    for v in variants(matrix):
        dev = by_dev[v["device"]]
        n, t, rj = v["segments"], v["tag"], v["joint_ohm"]
        seg_l = dev["l_um"] / n
        lines.append(f"* {t}: {n} x l={seg_l:g} w={dev['w_um']:g} joint={rj:g}")
        # 0 V sense source in series with the shared device bias source.
        lines.append(f"VS{t} {bias_node(dev)} {t}_0 0")
        if meas_form == "meas":
            lines.append(f"B{t} m_{t} 0 V = v({bias_node(dev)})/i(VS{t})")
        node = f"{t}_0"
        for i in range(n):
            last = i == n - 1
            nxt = "0" if last else f"{t}_s{i}"
            seg_out = nxt if (last or rj == 0.0) else f"{t}_j{i}"
            lines.append(f"X{t}_{i} {node} {seg_out} 0 {dev['model']} w={dev['w_um']:g} l={seg_l:.6g}")
            if rj != 0.0 and not last:
                lines.append(f"RJ{t}_{i} {seg_out} {nxt} {rj:.6g}")
            node = nxt
    lines.append(".end")
    return "\n".join(lines) + "\n"


def measurements(matrix: dict[str, Any], meas_form: str = "expr") -> list[dict[str, Any]]:
    by_dev = {d["schematic_device"]: d for d in matrix["devices"]}
    if meas_form == "meas":
        return [
            {"name": v["tag"],
             "spice": f".meas dc {v['tag']} FIND v(m_{v['tag']}) AT=0",
             "unit": "ohm"}
            for v in variants(matrix)
        ]
    return [
        {"name": v["tag"],
         "expr": f"v({bias_node(by_dev[v['device']])})/i(VS{v['tag']})", "unit": "ohm"}
        for v in variants(matrix)
    ]


def analysis(meas_form: str) -> dict[str, str]:
    if meas_form == "meas":
        return {"kind": "dc", "args": "Vsweep_idle 0 1 1"}
    return {"kind": "op", "args": ""}


def det_request(matrix: dict[str, Any], netlist: str, meas_form: str = "expr") -> dict[str, Any]:
    ops = [d["op_v"] for d in matrix["devices"]]
    if len({len(o) for o in ops}) != 1:
        raise ValueError("op_v arrays must be equal length (supply_v steps by index)")
    return {
        "engine": "ngspice",
        "netlist": netlist,
        "analysis": analysis(meas_form),
        "models": {"pdk": "sky130A", "lib": matrix["lib"]},
        "corners": {
            "process": matrix["deterministic"]["process"],
            "temperature_c": matrix["deterministic"]["temperature_c"],
            "supply_v": {param_name(d): d["op_v"] for d in matrix["devices"]},
        },
        "measurements": measurements(matrix, meas_form),
        "options": {"keep_artifacts": False, "timeout_s": 120, "ngspice_init": ["set numdgt=12"]},
    }


def mc_request(matrix: dict[str, Any], netlist: str, meas_form: str = "expr") -> dict[str, Any]:
    mc = matrix["monte_carlo"]
    return {
        "engine": "ngspice",
        "netlist": netlist,
        "analysis": analysis(meas_form),
        "models": {"pdk": "sky130A", "lib": matrix["lib"]},
        "corners": {"process": mc["process"], "temperature_c": mc["temperature_c"]},
        "measurements": measurements(matrix, meas_form),
        "monte_carlo": {"n": mc["n"], "seed": mc["seed"], "vary": mc["vary"], "k_sigma": 3},
        "options": {"keep_artifacts": False, "timeout_s": 120, "ngspice_init": ["set numdgt=12"]},
    }


# --------------------------------------------------------------------------
# Report parsing
# --------------------------------------------------------------------------


def corner_values(report: dict[str, Any]) -> list[tuple[str, dict[str, float]]]:
    """``[(corner_id, {measurement: value})]`` from a `klt sim` JSON report."""
    out = []
    for c in report["corners"]:
        vals = {}
        for m in c.get("measurements", []):
            if m.get("value") is not None:
                vals[m["name"]] = float(m["value"])
        out.append((c["corner_id"], vals))
    return out


def split_corner_id(cid: str) -> tuple[str, str, str, str | None]:
    """``tt/1.620V/27C[/mc3]`` -> (process, voltage_token, temp_token, mc|None)."""
    parts = cid.split("/")
    mc = parts[-1] if parts[-1].startswith("mc") else None
    if mc:
        parts = parts[:-1]
    return parts[0], parts[1] if len(parts) > 2 else "", parts[-1], mc


# --------------------------------------------------------------------------
# Deterministic analysis
# --------------------------------------------------------------------------


def det_shifts(
    points: list[tuple[str, dict[str, float]]], matrix: dict[str, Any], tol: dict[str, float]
) -> list[dict[str, Any]]:
    """Per (device, N, mode): worst |shift| vs the same point's N=1, and where."""
    rows: dict[tuple[str, int, str], dict[str, Any]] = {}
    for cid, vals in points:
        for v in variants(matrix):
            if v["segments"] == 1 and v["mode"] != "noj":
                continue
            base = vals.get(tag(v["device"], 1, "noj"))
            r = vals.get(v["tag"])
            if base is None or r is None:
                raise ValueError(f"missing value for {v['tag']} or its unsplit base at {cid}")
            s = (r - base) / base
            key = (v["device"], v["segments"], v["mode"])
            row = rows.setdefault(
                key,
                {"device": v["device"], "segments": v["segments"], "mode": v["mode"],
                 "worst_abs_shift": -1.0, "worst_shift": 0.0, "worst_point": None,
                 "min_shift": math.inf, "max_shift": -math.inf, "points": 0},
            )
            row["points"] += 1
            row["min_shift"] = min(row["min_shift"], s)
            row["max_shift"] = max(row["max_shift"], s)
            if abs(s) > row["worst_abs_shift"]:
                row.update(worst_abs_shift=abs(s), worst_shift=s, worst_point=cid)
    for row in rows.values():
        t = tol[row["device"]]
        row["tolerance"] = t
        row["verdict"] = "EQUIVALENT" if row["worst_abs_shift"] <= t else "NOT EQUIVALENT"
    return sorted(rows.values(), key=lambda r: (r["device"], r["segments"], r["mode"]))


def divider_vout_error(delta_a: float, units_folded: int) -> float:
    """Relative VOUT change of the 1:2 divider (VOUT = VFB*(RA+RB+RC)/(RB+RC)),
    given every folded unit shifts by ``delta_a`` (fraction) and
    ``units_folded`` (1 = only R_FB_A, 3 = all three) of the three are folded."""
    ra = 1.0 + (delta_a if units_folded >= 1 else 0.0)
    rb = 1.0 + (delta_a if units_folded >= 2 else 0.0)
    rc = 1.0 + (delta_a if units_folded >= 3 else 0.0)
    return (ra + rb + rc) / (rb + rc) / 1.5 - 1.0


# --------------------------------------------------------------------------
# Monte Carlo analysis
# --------------------------------------------------------------------------


def mc_groups(points: list[tuple[str, dict[str, float]]]) -> dict[tuple[str, str], list[dict[str, float]]]:
    """Group samples by (process, temperature token)."""
    g: dict[tuple[str, str], list[dict[str, float]]] = {}
    for cid, vals in points:
        proc, _v, temp, _mc = split_corner_id(cid)
        g.setdefault((proc, temp), []).append(vals)
    return g


def mc_stats(
    groups: dict[tuple[str, str], list[dict[str, float]]],
    matrix: dict[str, Any],
    tol: dict[str, float],
    seeds: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    mc = matrix["monte_carlo"]
    ratio_max = mc["sigma_ratio_max"]
    out = []
    for (proc, temp), samples in sorted(groups.items()):
        for v in variants(matrix):
            if v["segments"] == 1 and v["mode"] != "noj":
                continue
            bt = tag(v["device"], 1, "noj")
            base = [s[bt] for s in samples if bt in s]
            xs = [s[v["tag"]] for s in samples if v["tag"] in s]
            if len(base) < 2 or len(xs) < 2:
                raise ValueError(f"too few samples for {v['tag']} at {proc}/{temp}")
            mb, mx = statistics.fmean(base), statistics.fmean(xs)
            sb, sx = statistics.stdev(base), statistics.stdev(xs)
            shift = (mx - mb) / mb
            se = math.sqrt((sb**2 / len(base)) + (sx**2 / len(xs))) / mb
            ratio = sx / sb
            t = tol[v["device"]]
            out.append(
                {
                    "device": v["device"], "segments": v["segments"], "mode": v["mode"],
                    "process": proc, "temp": temp, "n_unsplit": len(base), "n_chain": len(xs),
                    "mean_unsplit": mb, "mean_chain": mx, "mean_shift": shift, "mean_shift_se": se,
                    "sigma_rel_unsplit": sb / mb, "sigma_rel_chain": sx / mx, "sigma_ratio": ratio,
                    "m1_pass": abs(shift) <= t, "m2_pass": ratio <= ratio_max,
                }
            )
    return out


def mc_rollup(rows: list[dict[str, Any]]) -> dict[tuple[str, int, str], dict[str, Any]]:
    agg: dict[tuple[str, int, str], dict[str, Any]] = {}
    for r in rows:
        k = (r["device"], r["segments"], r["mode"])
        a = agg.setdefault(k, {"worst_abs_mean_shift": 0.0, "worst_sigma_ratio": 0.0, "m1": True, "m2": True, "points": 0})
        a["points"] += 1
        a["worst_abs_mean_shift"] = max(a["worst_abs_mean_shift"], abs(r["mean_shift"]))
        a["worst_sigma_ratio"] = max(a["worst_sigma_ratio"], r["sigma_ratio"])
        a["m1"] &= r["m1_pass"]
        a["m2"] &= r["m2_pass"]
    return agg


def qualification(
    det: list[dict[str, Any]], mc_agg: dict[tuple[str, int, str], dict[str, Any]], matrix: dict[str, Any]
) -> list[dict[str, Any]]:
    """Per (device, N): QUALIFIED iff the deterministic criterion (joint mode
    j1, the measured pinned-geometry strap), M1 and M2 all hold. N=1 is the
    reference. Also records whether the 4x-joint sensitivity would flip it."""
    d = {(r["device"], r["segments"], r["mode"]): r for r in det}
    out = []
    for dev in matrix["devices"]:
        name = dev["schematic_device"]
        for n in dev["candidate_segments"]:
            if n == 1:
                continue
            det_j1 = d[(name, n, "j1")]
            det_j4 = d[(name, n, "j4")]
            m = mc_agg.get((name, n, "j1"))
            det_ok = det_j1["verdict"] == "EQUIVALENT"
            m1 = bool(m and m["m1"])
            m2 = bool(m and m["m2"])
            out.append(
                {
                    "device": name, "segments": n,
                    "det_worst_abs_shift": det_j1["worst_abs_shift"],
                    "det_ok": det_ok, "m1": m1, "m2": m2,
                    "qualified": det_ok and m1 and m2,
                    "control": n in dev["control_segments"],
                    "j4_flips": (det_j4["verdict"] == "EQUIVALENT") != det_ok,
                }
            )
    return out


def recommendation(quals: list[dict[str, Any]], device: str) -> int | None:
    """Largest qualified N that is not a declared nonequivalent control.
    ``None`` means no qualified fold: only the unsplit device is supported."""
    ok = [q["segments"] for q in quals if q["device"] == device and q["qualified"] and not q["control"]]
    return max(ok) if ok else None
