"""Pure helpers for the issue #253 folded-resistor qualification flow.

Standard library only, so `layout/tests/test_folded_res_qual.py` can
exercise every number the record's verdicts rest on without `klt`, KLayout
or ngspice installed. `run-folded-res-qual-flow.py` does the I/O.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Tolerance: read from the model library the repo's sim harness uses
# (sim/pdk.json's `ngspice_lib`, libs.tech/combined/sky130.lib.spice), never
# transcribed. The combined library's resistor body mismatch is
#   rbody *= 1 + sw_mm_<model> * mismatch_factor * AGAUSS(0,1,1) / sqrt(w*l*mult)
# (continuous/models_resistors.spice), so one local-mismatch sigma of a drawn
# W x L body, as a fraction, is sw_mm_<model> * mismatch_factor / sqrt(W*L).
# --------------------------------------------------------------------------

MISMATCH_PARAM = {
    "sky130_fd_pr__res_high_po": "sw_mm_sky130_fd_pr__res_high_po",
    "sky130_fd_pr__res_xhigh_po": "sw_mm_sky130_fd_pr__res_xhigh_po",
}
SHEET_PARAM = {
    "sky130_fd_pr__res_high_po": "sw_sky130_fd_pr__res_high_po_rs",
    "sky130_fd_pr__res_xhigh_po": "sw_sky130_fd_pr__res_xhigh_po_rs",
}

#: Multiplier on the local-mismatch sigma that defines the equivalence
#: tolerance. Stated before any result is computed (see the README's
#: "Equivalence tolerance" section): a deterministic layout-induced shift no
#: larger than 3 sigma of the unsplit device's own local mismatch is
#: indistinguishable from drawing a second copy of the same schematic device.
TOLERANCE_SIGMAS = 3.0


def read_param(text: str, name: str) -> float:
    """First numeric assignment ``name = <number>`` in a SPICE .param block."""
    m = re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}\s*=\s*([-+0-9.eE]+)", text)
    if not m:
        raise ValueError(f"no numeric assignment for {name!r}")
    return float(m.group(1))


def read_corner_sheet(text: str, model: str) -> dict[str, float]:
    """``{nominal, corner_delta}`` from a parameters_res_<corner>.spice line
    ``.param <sheet> = {NOM+corner_factor*DELTA} ...``."""
    name = SHEET_PARAM[model]
    m = re.search(
        rf"{re.escape(name)}\s*=\s*\{{\s*([-+0-9.eE]+)\s*\+\s*corner_factor\s*\*\s*([-+0-9.eE]+)\s*\}}"
        rf"(?:\s*\+\s*process_mc_factor\s*\*\s*MC_PR_SWITCH\s*\*\s*GAUSS\(\s*0\s*,\s*([-+0-9.eE]+)\s*,)?",
        text,
    )
    if not m:
        raise ValueError(f"no corner sheet-resistance line for {name!r}")
    out = {"nominal": float(m.group(1)), "corner_delta": float(m.group(2))}
    if m.group(3) is not None:
        out["process_mc_sigma_frac"] = float(m.group(3))
    return out


def local_sigma_frac(sw_mm: float, mismatch_factor: float, w_um: float, l_um: float) -> float:
    return sw_mm * mismatch_factor / math.sqrt(w_um * l_um)


def tolerance(
    model: str, w_um: float, l_um: float, models_global_text: str, lib_text: str
) -> dict[str, Any]:
    sw_mm = read_param(models_global_text, MISMATCH_PARAM[model])
    mismatch_factor = read_param(lib_text, "mismatch_factor")
    sigma = local_sigma_frac(sw_mm, mismatch_factor, w_um, l_um)
    return {
        "basis": "3 x local-mismatch sigma of the unsplit device (PDK combined model library)",
        "mismatch_param": MISMATCH_PARAM[model],
        "mismatch_param_value": sw_mm,
        "mismatch_factor": mismatch_factor,
        "sigma_frac": sigma,
        "sigmas": TOLERANCE_SIGMAS,
        "tolerance_frac": TOLERANCE_SIGMAS * sigma,
    }


# --------------------------------------------------------------------------
# Extraction-side resistance bookkeeping (klt's curated deck convention)
# --------------------------------------------------------------------------


def deck_resistance(sheet_rho: float, fixed_offset: float, l_um: float, w_um: float) -> float:
    """`klt extract`'s R for one drawn body: rho * L / W + fixed offset."""
    return sheet_rho * l_um / w_um + fixed_offset


def extracted_sum(devices: list[dict[str, Any]]) -> float:
    """Series sum of every extracted resistor's ``params.r_ohm``."""
    return sum(float(d["params"]["r_ohm"]) for d in devices)


def rel(a: float, b: float) -> float:
    """(a - b) / b."""
    return (a - b) / b


# --------------------------------------------------------------------------
# Electrical: single operating point, one ngspice deck for every variant
# --------------------------------------------------------------------------


def sim_tag(device: str, segments: int, joints: bool) -> str:
    return f"r_{device.lower()}_n{segments}{'_j' if joints else ''}"


def build_op_deck(
    lib_path: str,
    corner: str,
    temp_c: float,
    devices: list[dict[str, Any]],
    joint_ohm: dict[str, float],
) -> tuple[str, list[dict[str, Any]]]:
    """One deck, one `.op`: each variant is its own isolated source + chain.

    For every device and every N in ``sim_segments`` it draws an N-segment
    series chain of the PDK model (segment l = L/N, w unchanged, bulk to 0)
    across its own DC source at ``op_v``, plus -- for N >= 2 -- a twin chain
    with the layout's measured per-joint interconnect resistance
    (``joint_ohm[device]``) inserted at each of the N-1 joints. N=1 is the
    unsplit schematic device. Returns the deck text and the variant list.
    """
    lines = [
        "* issue #253 folded-resistor single-operating-point comparison",
        f".lib {lib_path} {corner}",
        f".temp {temp_c:g}",
    ]
    variants: list[dict[str, Any]] = []
    for dev in devices:
        name = dev["schematic_device"]
        for n in dev["sim_segments"]:
            for joints in (False, True):
                if joints and n == 1:
                    continue
                tag = sim_tag(name, n, joints)
                seg_l = dev["l_um"] / n
                rj = joint_ohm.get(name, 0.0) if joints else 0.0
                lines.append(f"* {tag}: {name} as {n} x l={seg_l:g} w={dev['w_um']:g}, joint R={rj:g}")
                lines.append(f"V{tag} {tag}_0 0 {dev['op_v']:g}")
                node = f"{tag}_0"
                for i in range(n):
                    nxt = "0" if i == n - 1 else f"{tag}_s{i}"
                    seg_out = nxt if (not joints or i == n - 1) else f"{tag}_j{i}"
                    lines.append(
                        f"X{tag}_{i} {node} {seg_out} 0 {dev['model']} w={dev['w_um']:g} l={seg_l:.6g}"
                    )
                    if joints and i < n - 1:
                        lines.append(f"RJ{tag}_{i} {seg_out} {nxt} {rj:.6g}")
                    node = nxt
                variants.append(
                    {
                        "tag": tag,
                        "schematic_device": name,
                        "segments": n,
                        "segment_l_um": seg_l,
                        "joints_included": joints,
                        "joint_ohm": rj,
                        "op_v": dev["op_v"],
                    }
                )
    lines.append(".control")
    lines.append("set numdgt=12")
    lines.append("op")
    for v in variants:
        lines.append(f"let {v['tag']} = -v({v['tag']}_0)/i(V{v['tag']})")
        lines.append(f"print {v['tag']}")
    lines.append(".endc")
    lines.append(".end")
    return "\n".join(lines) + "\n", variants


_PRINT_RE = re.compile(r"^\s*(r_[a-z0-9_]+)\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)


def parse_op_output(text: str) -> dict[str, float]:
    return {m.group(1): float(m.group(2)) for m in _PRINT_RE.finditer(text)}


def electrical_rows(
    variants: list[dict[str, Any]], values: dict[str, float]
) -> list[dict[str, Any]]:
    """Attach R_eff and the shift vs the same device's N=1 (unsplit) value."""
    base = {
        v["schematic_device"]: values[v["tag"]]
        for v in variants
        if v["segments"] == 1 and not v["joints_included"]
    }
    rows = []
    for v in variants:
        r = values[v["tag"]]
        r0 = base[v["schematic_device"]]
        rows.append({**v, "r_eff_ohm": r, "r_unsplit_ohm": r0, "delta_ohm": r - r0, "delta_frac": rel(r, r0)})
    return rows


def verdict(delta_frac: float, tol_frac: float) -> str:
    return "EQUIVALENT" if abs(delta_frac) <= tol_frac else "NOT EQUIVALENT"


# --------------------------------------------------------------------------
# DRC control: unmerged per-row markers
# --------------------------------------------------------------------------


def added_rule_classes(control: dict[str, int], reference: dict[str, int]) -> dict[str, int]:
    """PDK-signoff rule categories the control stream (per-row markers left
    unmerged) violates that the reference stream (merged markers) does not.

    The unmerged-marker control is *expected to fail*: a non-empty result is
    the evidence that the folded stream's marker merge removes violations
    that folding would otherwise add. An empty result means the control did
    not demonstrate anything, which the flow records as a flow failure.
    """
    return {k: v for k, v in sorted(control.items()) if v > 0 and not reference.get(k)}


# --------------------------------------------------------------------------
# Area
# --------------------------------------------------------------------------


def area_summary(unsplit: dict[str, Any], folded: dict[str, Any], segments: int,
                 segment_l_um: float, w_um: float) -> dict[str, Any]:
    """Bounding areas (device-only and with the substrate tie) and the
    routing overhead of the series straps.

    The straps are drawn inside the bank's own pad columns (they bridge the
    row gap between two vertically aligned pads), so they add li1 *area* but
    no bounding-box area; the routing overhead is therefore stated two ways:
    bbox growth from straps (measured: routed-bank bbox minus generated-bank
    bbox, expected 0) and drawn strap li1 area.
    """
    ub = unsplit["device_bbox"]
    fb = folded["device_bbox"]

    def dims(b: dict[str, float]) -> dict[str, float]:
        w = b["x1"] - b["x0"]
        h = b["y1"] - b["y0"]
        return {"width_um": round(w, 4), "height_um": round(h, 4), "area_um2": round(w * h, 4)}

    f_tie = dims(folded["bbox_with_tie_um"])
    u_tie = dims(unsplit["bbox_with_tie_um"])
    f_routed = dims(folded["bbox_without_tie_um"])
    return {
        "unsplit_device_bbox": ub,
        "folded_device_bbox": fb,
        "unsplit_with_tie_bbox": u_tie,
        "folded_with_tie_bbox": f_tie,
        "body_area_um2": round(segments * segment_l_um * w_um, 4),
        "folded_vs_unsplit_area_ratio": round(fb["area_um2"] / ub["area_um2"], 4),
        "width_reduction_um": round(ub["width_um"] - fb["width_um"], 4),
        "strap_count": folded["strap_count"],
        "strap_li1_area_um2": folded["strap_li1_area_um2"],
        "folded_routed_bbox": f_routed,
        "strap_bbox_growth_um2": round(f_routed["area_um2"] - fb["area_um2"], 4),
    }
