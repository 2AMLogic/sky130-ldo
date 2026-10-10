#!/usr/bin/env python3
"""Render one MiM-capacitor + supply-rail overlay demonstrator record
(issue #254) from the JSON envelopes `run-cap-rail-demo-flow.sh` wrote.

Standard library only. Writes `record.md` to stdout and `summary.json` next to
the inputs. Exits 0 only when every gate this record states holds: both DRC
decks clean, the LVS compare a match, and both negative controls a mismatch.
The feasibility verdict is reported either way; it is a geometric statement
about this demonstrator, never a claim that the ratified Area row is met by
the LDO core.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cap_rail_plan as plan  # noqa: E402


def load(path: Path) -> dict[str, Any]:
    """A klt JSON envelope; an empty/unparseable one (the tool errored to
    stderr) is reported as status "error" rather than crashing the record."""
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": f"{path.name}: {exc}"}


def lyrdb_counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for item in ET.parse(path).getroot().iter("item"):
        cat = item.find("category")
        if cat is not None and cat.text:
            counts[cat.text.strip("'")] += 1
    return dict(counts)


def lyrdb_rule_count(path: Path) -> int:
    root = ET.parse(path).getroot()
    cats = root.find("categories")
    return 0 if cats is None else len(list(cats.iter("category")))


def extracted_by_cap(extract: dict[str, Any], caps: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Sum extracted MiM capacitance per schematic capacitor (by net pair) and class."""
    by_pair: dict[frozenset[str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for dev in extract["devices"]:
        nets = frozenset(dev["nets"].values())
        by_pair[nets][dev["class"]] += dev["params"]["c_f"]
    out: dict[str, dict[str, float]] = {}
    for cap in caps:
        classes = dict(by_pair.get(frozenset(cap["nets"]), {}))
        out[cap["name"]] = {**classes, "total": sum(classes.values())}
    return out


def coupling_pairs(pex: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    for net in pex["parasitics"]["nets"]:
        for c in net.get("coupled", []):
            key = tuple(sorted((net["net"], c["net"])))
            pairs[key] = {"ff": c["capacitance_ff"], "levels": c["levels"]}
    return pairs


def single_layer_counterfactual(caps: list[dict[str, Any]], area_f: float, perim_f: float) -> dict[str, Any]:
    """Block area if every capacitor were a single MiM level (no stacking),
    each as the most compact array of <= 30 um units."""
    total = 0.0
    detail = {}
    for cap in caps:
        c_max = plan.unit_cap_f(plan.MAX_UNIT_SIDE_UM, area_f, perim_f)
        n = max(1, math.ceil(cap["target_f"] / c_max))
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        sized = plan.size_capacitor(cap["name"], cap["target_f"], rows, cols, 1, area_f, perim_f)
        ext = plan.block_extent_um(rows, cols, sized["unit_side_um"])
        area = ext["w_um"] * ext["h_um"]
        total += area
        detail[cap["name"]] = {"rows": rows, "cols": cols, "unit_side_um": sized["unit_side_um"],
                               "block_w_um": ext["w_um"], "block_h_um": ext["h_um"], "block_area_um2": area}
    return {"block_area_um2": total, "per_cap": detail}


def gate_flags(drc: dict[str, Any], mr: dict[str, int], mr_rules: int, lvs: dict[str, Any],
               neg_value: dict[str, Any], neg_net: dict[str, Any]) -> dict[str, bool]:
    """The record's gates (issue #306: pure, PDK-free tested). `gates_ok` is
    the exit decision: both DRC decks clean, the LVS compare a match, and both
    negative controls a mismatch."""
    drc_clean = drc.get("status") == "clean" and drc.get("violation_count", 0) == 0
    mr_clean = sum(mr.values()) == 0 and mr_rules > 0
    lvs_match = lvs.get("status") == "match"
    negs_ok = neg_value.get("status") == "mismatch" and neg_net.get("status") == "mismatch"
    return {
        "drc_clean": drc_clean, "mr_clean": mr_clean, "lvs_match": lvs_match, "negs_ok": negs_ok,
        "gates_ok": drc_clean and mr_clean and lvs_match and negs_ok,
    }


def feasibility_verdict(core: dict[str, Any], totals: dict[str, Any], single_block_area_um2: float,
                        gates_ok: bool) -> dict[str, Any]:
    """The `verdict` dictionary of summary.json (issue #306: pure, PDK-free
    tested). `feasible_geometrically` is the conjunction of the planned core
    rectangle being below the ratified limit, the capacitor blocks fitting in
    the overlay area, and every gate holding."""
    overlay_fits = totals["cap_block_um2"] <= totals["overlay_usable_um2"]
    return {
        "core_rectangle_um2": core["area_um2"],
        "core_rectangle_mm2": core["area_mm2"],
        "limit_um2": plan.LIMIT_UM2,
        "below_limit": core["below_limit"],
        "margin_fraction": core["margin_fraction"],
        "caps_fit_in_overlay": overlay_fits,
        "side_by_side_um2": totals["side_by_side_area_um2"],
        "side_by_side_below_limit": totals["side_by_side_area_um2"] < plan.LIMIT_UM2,
        "single_mim_level_block_um2": single_block_area_um2,
        "single_mim_level_fits_overlay": single_block_area_um2 <= totals["overlay_usable_um2"],
        "feasible_geometrically": core["below_limit"] and overlay_fits and gates_ok,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--record-id", required=True)
    ap.add_argument("--schematic-sha", required=True)
    ap.add_argument("--pin", required=True)
    args = ap.parse_args()
    d = args.out_dir

    pl = load(d / "plan.json")
    drc = load(d / "drc.json")
    mr = lyrdb_counts(d / "mr-drc.lyrdb")
    mr_rules = lyrdb_rule_count(d / "mr-drc.lyrdb")
    ex = load(d / "extract.json")
    pex = load(d / "pex.json")
    lvs = load(d / "lvs.json")
    lvs_gds = load(d / "lvs-gds-shape.json")
    neg_value = load(d / "lvs-neg-value.json")
    neg_net = load(d / "lvs-neg-net.json")
    kv = load(d / "klt-version.json")
    klayout_v = (d / "klayout-version.txt").read_text().strip() if (d / "klayout-version.txt").exists() else "?"

    caps = pl["capacitors"]
    core = pl["core"]
    coeff = pl["overlap_coefficients_f_um2"]
    extracted = extracted_by_cap(ex, caps)
    pairs = coupling_pairs(pex)
    pex_nets = {n["net"]: n for n in pex["parasitics"]["nets"]}

    g = gate_flags(drc, mr, mr_rules, lvs, neg_value, neg_net)
    drc_clean, mr_clean, lvs_match = g["drc_clean"], g["mr_clean"], g["lvs_match"]
    gates_ok = g["gates_ok"]

    tolerated = [m for m in lvs.get("mismatches", []) if m["category"] == "device.parameter_tolerated"]
    max_tol_pct = 0.0
    for m in tolerated:
        try:
            max_tol_pct = max(max_tol_pct, float(m["description"].split("differs by ")[1].split("%")[0]))
        except (IndexError, ValueError):
            pass

    # Coupling: the extractor charges adjacent-level overlap between the
    # plates of one capacitor on top of the recognised MiM device. Inside the
    # top-plate footprint that is a double count (the MiM model already is
    # the capacitance there); outside it (unit gaps, plate margins) it is a
    # real parallel parasitic.
    stack_coeff = coeff["met3-met4"] + coeff["met4-met5"]
    cap_rows = []
    coupling_rows = []
    for b in caps:
        n1, n2 = b["nets"]
        e = extracted[b["name"]]
        ext_err = (e["total"] - b["target_f"]) / b["target_f"]
        pair = pairs.get(tuple(sorted((n1, n2))), {"ff": 0.0})
        reported = pair["ff"] * 1e-15
        double = b["mim_footprint_um2"] * stack_coeff
        residual = reported - double
        inner = b["plates"]["inner"]
        inner_gnd = pex_nets.get(inner, {}).get("capacitance_ff", float("nan")) * 1e-15
        others = {k: v["ff"] for k, v in pairs.items() if inner in k and set(k) != {n1, n2}}
        under = b["measured_routing_under_um2"]
        dev_row = under["met2"] * coeff["met2-met3"]
        cap_rows.append({
            "name": b["name"], "nets": b["nets"], "outer": b["plates"]["outer"], "inner": inner,
            "array": f"{b['rows']}x{b['cols']}", "unit_side_um": b["unit_side_um"],
            "target_f": b["target_f"], "extracted_f": e["total"], "extracted_rel_error": ext_err,
            "by_class_f": {k: v for k, v in e.items() if k != "total"},
            "block_um2": b["block_area_um2"], "mim_footprint_um2": b["mim_footprint_um2"],
        })
        coupling_rows.append({
            "name": b["name"], "pair": [n1, n2], "reported_overlap_f": reported,
            "mim_footprint_double_count_f": double, "residual_parallel_parasitic_f": residual,
            "residual_rel": residual / b["target_f"], "inner": inner, "inner_to_ground_f": inner_gnd,
            "inner_coupled_to_other_nets_ff": others,
            "measured_device_row_met2_under_um2": under["met2"],
            "measured_device_row_met1_under_um2": under["met1"],
            "measured_device_row_li1_under_um2": under["li1"],
            "device_row_met2_to_outer_est_f": dev_row,
        })
    vin_vout = pairs.get(("VIN", "VOUT"), {"ff": 0.0})["ff"] * 1e-15

    t = pl["totals"]
    single = single_layer_counterfactual(caps, pl["deck"]["area_f_um2"], pl["deck"]["perim_f_um"])
    verdict = feasibility_verdict(core, t, single["block_area_um2"], gates_ok)
    summary = {
        "schema_version": 1, "issue": 254, "record_id": args.record_id,
        "klt_version": kv.get("version"), "klt_pin": args.pin, "klayout_system": klayout_v,
        "schematic_sha": args.schematic_sha,
        "gates": {"klt_drc_clean": drc_clean, "official_drc_clean": mr_clean,
                  "official_drc_rule_categories": mr_rules, "official_drc_counts": mr,
                  "lvs_status": lvs.get("status"), "lvs_counts": lvs.get("counts"),
                  "lvs_max_tolerated_pct": max_tol_pct,
                  "neg_value_status": neg_value.get("status"), "neg_net_status": neg_net.get("status"),
                  "lvs_gds_shape_status": lvs_gds.get("status"),
                  "lvs_gds_shape_category_counts": lvs_gds.get("category_counts"),
                  "all_ok": gates_ok},
        "capacitors": cap_rows, "coupling": coupling_rows, "vin_vout_coupling_f": vin_vout,
        "rails": pl["rails"], "met3_rail_zone": pl["met3_rail_zone"], "totals": t,
        "single_mim_level_counterfactual": single, "verdict": verdict,
        "claims_not_made": [
            "the LDO core meets the ratified Area row",
            "electrical requalification (loop stability, PSRR, start-up) with these parasitics",
            "DRC/LVS of any MOS device, resistor or signal route (none is drawn here)",
        ],
    }
    (d / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    def ok(flag: bool) -> str:
        return "PASS" if flag else "FAIL"

    w = []
    w.append(f"# MiM capacitor + supply-rail overlay demonstrator: {args.record_id}\n")
    w.append("Issue #254. **A bounded geometry demonstrator, not the LDO core.** It draws the schematic's "
             "four capacitors as stacked MiM arrays and the two load-current rails on the proposed metal "
             "assignment inside the planned core outline; no MOS device, resistor or signal route is drawn. "
             "The ratified Area row (< 0.1 mm^2, strict) is unchanged and is **not** claimed met by the core. "
             "Full-core integration and electrical requalification belong to #231.\n")
    w.append("## Provenance\n")
    w.append(f"- klt `{kv.get('version')}` (pin `layout/cap-requirements.txt`), KLayout in klt `{kv.get('klayout_version')}`")
    w.append(f"- Official DRC: PDK `sky130A_mr.drc` run by system `{klayout_v}` (FEOL+BEOL+offgrid; {mr_rules} rule categories evaluated)")
    w.append(f"- Schematic `design/ldo_3v3in_1v8out.sch` @ `{args.schematic_sha}` (capacitors read from its own xschem netlist, `xschem_out/`)")
    w.append(f"- Measured inputs: `{pl['sources']['floorplan']}`, `{pl['sources']['measured_gds']}`, `{pl['sources']['budget']}`; spec `{pl['sources']['spec']}`")
    w.append(f"- MiM law from the klt deck: {pl['deck']['area_f_um2'] * 1e15:.2f} fF/um^2 + {pl['deck']['perim_f_um'] * 1e15:.2f} fF/um ({pl['deck']['provenance']})\n")

    w.append("## Gates\n")
    w.append("| Check | Result |")
    w.append("|---|---|")
    w.append(f"| `klt drc --deck sky130` | {ok(drc_clean)} -- {drc.get('status')}, {drc.get('violation_count')} violations |")
    w.append(f"| PDK `sky130A_mr.drc` (official) | {ok(mr_clean)} -- {sum(mr.values())} markers{(' ' + json.dumps(mr)) if mr else ''} |")
    w.append(f"| `klt lvs` extracted netlist vs schematic-derived reference | {ok(lvs_match)} -- `{lvs.get('status')}`; "
             f"devices {lvs['counts']['devices']['matched']}/{lvs['counts']['devices']['reference']}, "
             f"nets {lvs['counts']['nets']['matched']}/{lvs['counts']['nets']['reference']}; "
             f"`parameter_tolerance` 0.1% (largest used {max_tol_pct:.4f}%), top-level pins name-anchored |")
    w.append(f"| Negative control: C_COMP stated as 100 pF | {ok(neg_value.get('status') == 'mismatch')} -- `{neg_value.get('status')}` (must mismatch) |")
    w.append(f"| Negative control: C_TS outer terminal moved from `VIN` to `0` | {ok(neg_net.get('status') == 'mismatch')} -- `{neg_net.get('status')}` (must mismatch) |")
    w.append(f"| `klt lvs` on the GDS directly (`layout.file`) | evidence only -- `{lvs_gds.get('status')}` "
             f"{json.dumps(lvs_gds.get('category_counts'))}; see README 'Tool friction' |\n")

    w.append("## Capacitors (values and nets from the schematic; extraction from the drawn GDS)\n")
    w.append("| Cap | Nets | Outer plates (met3+met5) | Inner plate (met4) | Array x unit | Schematic | Extracted MiM | Error | Block um^2 |")
    w.append("|---|---|---|---|---|---|---|---|---|")
    for r in cap_rows:
        w.append(f"| {r['name']} | {r['nets'][0]}-{r['nets'][1]} | {r['outer']} | {r['inner']} | {r['array']} x {r['unit_side_um']} um "
                 f"| {r['target_f'] * 1e12:.3f} pF | {r['extracted_f'] * 1e12:.4f} pF | {r['extracted_rel_error'] * 100:+.3f}% | {r['block_um2']:.0f} |")
    w.append("")
    w.append("Each unit is a `cap_mim_m3_1` (met3/capm) under a `cap_mim_m3_2` (met4/capm2) of the same footprint, in "
             "parallel; both classes extract (`by_class_f` in `summary.json`) and each carries half the value.\n")

    w.append("## Coupling (`klt extract --parasitics`, adjacent-level overlap model)\n")
    w.append("| Cap | Reported plate-plate overlap | of which inside MiM footprint (double count) | Residual parallel parasitic | Inner node to ground | Inner node to any other net | Measured device-row met2 under block -> est. coupling to outer plate |")
    w.append("|---|---|---|---|---|---|---|")
    for c in coupling_rows:
        w.append(f"| {c['name']} | {c['reported_overlap_f'] * 1e15:.1f} fF | {c['mim_footprint_double_count_f'] * 1e15:.1f} fF "
                 f"| {c['residual_parallel_parasitic_f'] * 1e15:.1f} fF ({c['residual_rel'] * 100:.2f}% of value) "
                 f"| {c['inner_to_ground_f'] * 1e15:.1f} fF | {json.dumps(c['inner_coupled_to_other_nets_ff']) if c['inner_coupled_to_other_nets_ff'] else 'none'} "
                 f"| {c['measured_device_row_met2_under_um2']:.0f} um^2 -> {c['device_row_met2_to_outer_est_f'] * 1e15:.1f} fF |")
    w.append("")
    w.append(f"- VIN-VOUT coupling reported: {vin_vout * 1e15:.1f} fF (rail/tail crossings and the met2 VIN risers under C_COMP's VOUT plate).")
    w.append("- The extractor models adjacent-level overlap only: li1/met1 under a met3 plate (non-adjacent) is not charged "
             "to the plate at all, so device-row coupling beyond met2 is **not quantified** here (areas are in `summary.json`).\n")

    w.append("## Rails (unchanged #154 sizing rule, proposed levels)\n")
    w.append("| Net | Wide segment levels | Width (measured) | R / IR drop | Sense tail | Tail ohm/um (measured) |")
    w.append("|---|---|---|---|---|---|")
    for net, r in sorted(pl["rails"].items()):
        s = r["sizing"]
        w.append(f"| {net} | met{r['levels'][0]}+met{r['levels'][1]} | {s['width_um']:.3f} um ({r['measured_width_um']:.3f}) "
                 f"| {s['resistance_ohm']:.3f} ohm / {s['ir_drop_v'] * 1e3:.2f} mV | met{r['tail_levels'][0]} only, {r['tail_w_um']:.3f} um "
                 f"(was met{r['measured_levels'][0]}+met{r['measured_levels'][1]} {r['measured_tail_w_um']:.2f} um) "
                 f"| {r['tail_r_per_um_ohm']:.4f} ({r['measured_tail_r_per_um_ohm']:.4f}) |")
    z = pl["met3_rail_zone"]
    w.append("")
    w.append(f"- met3 rail column (MiM keep-out): x {z['x0_um']:.2f}-{z['x1_um']:.2f}, y {z['y0_um']:.2f}-{z['y1_um']:.2f} um "
             f"({(z['x1_um'] - z['x0_um']) * (z['y1_um'] - z['y0_um']):.0f} um^2): the VIN band's met3 and the "
             f"{pl['risers']['pass_met3']} pass-device VIN risers that cross the VOUT band on met3.")
    w.append(f"- {pl['risers']['side_met2']} other VIN risers now cross the met1-only VOUT tail on met2.\n")

    w.append("## Footprint and feasibility verdict\n")
    w.append(f"- Planned core rectangle: {core['w_um']:.2f} x {core['h_um']:.2f} um = **{core['area_mm2']:.4f} mm^2** "
             f"(measured MOS domain {core['composition']['mos_domain_w_um']:.2f} um + {core['bank_column']['gap_um']:.0f} um + "
             f"{core['bank_column']['w_um']:.0f} um folded-resistor bank column; channel {core['composition']['channel_h_um']:.2f} + "
             f"row {core['composition']['row_h_um']:.2f} + rail bands {core['composition']['rail_bands_h_um']:.2f} um).")
    w.append(f"- Ratified limit {plan.LIMIT_UM2 / 1e6:.1f} mm^2: below by {core['margin_fraction'] * 100:.1f}% -> {'below' if core['below_limit'] else 'NOT below'} the limit.")
    w.append(f"- Capacitor blocks (incl. straps/taps): {t['cap_block_um2']:.0f} um^2 in {t['overlay_usable_um2']:.0f} um^2 of overlay "
             f"area outside the met3 rail column ({t['cap_block_fraction_of_usable'] * 100:.1f}% used); MiM top-plate footprint {t['mim_footprint_um2']:.0f} um^2.")
    w.append(f"- Density: {t['effective_density_f_um2'] * 1e15:.2f} fF/um^2 over the drawn blocks (the #246 study assumed 4 fF/um^2 unverified).")
    w.append(f"- Counterfactual, same blocks beside the core: {t['side_by_side_area_um2'] / 1e6:.4f} mm^2 -> "
             f"{'below' if verdict['side_by_side_below_limit'] else 'NOT below'} the limit.")
    w.append(f"- Counterfactual, one MiM level (no stacking): {single['block_area_um2']:.0f} um^2 of blocks -> "
             f"{'fits' if verdict['single_mim_level_fits_overlay'] else 'does NOT fit'} in the overlay area.\n")
    if verdict["feasible_geometrically"]:
        w.append("**Verdict: geometrically feasible on this plan** -- stacked MiM over the core, with the met3 rail column kept "
                 "out, holds all four schematic capacitors DRC-clean and LVS-matched inside a rectangle below the limit. "
                 "It depends on stacking (one MiM level does not fit) and on overlay (beside-the-core fails). "
                 "This is conditional on every assumption below and is NOT a statement that the LDO core meets the Area row.\n")
    else:
        w.append("**Verdict: NOT demonstrated** -- at least one gate failed or the blocks do not fit; see above.\n")
    w.append("## Assumptions this verdict rests on (not verified here)\n")
    w.append("- The MOS domain keeps its measured width; the 12 comparator devices added since that layout (#230) fit in the "
             "bank column's free height and the 7 removed ones free nothing (#231 owns the refreshed layout).")
    w.append("- The folded resistor banks reproduce the #246 conservative 100 um estimate (#253 qualifies them).")
    w.append("- Coupling of the plates to the device row beyond met2, to poly resistors, and its electrical effect (loop, PSRR) "
             "is unquantified; the electrical requalification is #231's.")
    w.append("- Antenna/ERC on the large plates is not run here (`klt erc` belongs to the full-core flow).")
    w.append("")
    sys.stdout.write("\n".join(w) + "\n")
    return 0 if gates_ok else 1


if __name__ == "__main__":
    sys.exit(main())
