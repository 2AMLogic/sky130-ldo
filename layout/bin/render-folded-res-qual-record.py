#!/usr/bin/env python3
"""Render ``record.md`` for one issue #253 folded-resistor qualification
record from its ``summary.json`` (written by ``run-folded-res-qual-flow.py``).

Standard library only. Re-runnable on a committed record: it reads nothing
but the record directory, so the prose can never drift from the numbers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def pct(x: float, digits: int = 3) -> str:
    return f"{x * 100:+.{digits}f}%"


def fmt_counts(c: dict[str, int] | None) -> str:
    if not c:
        return "0"
    return ", ".join(f"{k} x{v}" for k, v in sorted(c.items()))


def drawn_row(summary: dict[str, Any], case: dict[str, Any]) -> dict[str, Any] | None:
    for r in summary["electrical"]["rows"]:
        if (r["schematic_device"] == case["schematic_device"] and r["segments"] == case["segments"]
                and r["joints_included"] == (case["segments"] > 1)):
            return r
    return None


def displayed_verdict(row: dict[str, Any] | None) -> str:
    """The electrical verdict shown for a drawn case (issue #306): the matching
    electrical row's own `verdict`, copied verbatim, or `n/a` when no
    electrical row matches the case."""
    return row["verdict"] if row else "n/a"


def electrical_cells(row: dict[str, Any] | None) -> tuple[str, str, str]:
    """(R_eff shift, tolerance, verdict) cells of the drawn-configuration
    verdict table. A case with no matching electrical row renders `n/a` in
    all three rather than borrowing another row's numbers."""
    if not row:
        return "n/a", "n/a", displayed_verdict(row)
    return (f"{pct(row['delta_frac'])} ({row['delta_ohm']:+.1f} ohm)",
            f"{row['tolerance_frac'] * 100:.3f}%", displayed_verdict(row))


def render(summary: dict[str, Any]) -> str:
    p = summary["provenance"]
    e = summary["electrical"]
    out: list[str] = []
    w = out.append
    w(f"# Folded-resistor qualification record `{summary['record_id']}` (issue #253)")
    w("")
    w("Resistor-only test blocks. **Not** a full-core layout, **not** an area-compliance claim for the LDO "
      "(the ratified Area row is untouched), and no schematic value is changed: every folded bank keeps the "
      "schematic `W`, and its segment lengths sum to the schematic `L`.")
    w("")
    w("## Provenance")
    w("")
    w(f"- git: `{p['git_sha']}`{' (dirty tree)' if p['git_dirty'] else ''}; schematic last changed at `{p['schematic_sha']}`")
    w(f"- klt: `{p['klt_version']}` (pin: `{p['klt_pin']}`)")
    w(f"- KLayout (PDK signoff runset engine): `{p['klayout_version']}`; runset `{p['pdk_drc_runset']}`")
    w(f"- ngspice: `{p['ngspice_version']}`; model library `{e['lib']}` section `{e['corner']}`, {e['temp_c']} C")
    w(f"- PDK: `{p['pdk_variant']}` `{p['pdk_version']}` (repo pin `{p['open_pdks_commit_pinned']}`)")
    w("")
    w("## Equivalence tolerance (rule fixed before any result was computed)")
    w("")
    w("A folded bank is **EQUIVALENT** to the unsplit schematic resistor when its effective resistance at the "
      "stated operating point differs from the unsplit device's by no more than **3 x the local-mismatch sigma "
      "of the unsplit device**, read from the same PDK model library the sim harness uses "
      "(`rbody *= 1 + sw_mm * mismatch_factor * AGAUSS / sqrt(W*L)`). Rationale: a deterministic shift inside "
      "that band is indistinguishable from drawing a second copy of the same schematic device; anything larger "
      "is a real electrical change that would have to be requalified (or compensated) rather than assumed away. "
      "The global sheet-rho spread is shown for context only and does not gate the verdict.")
    w("")
    w("| device | W x L (um) | sw_mm | 1 sigma local | **tolerance (3 sigma)** | context: sheet rho low / nom / high (ohm/sq), process MC sigma |")
    w("|---|---|---|---|---|---|")
    for name, t in e["tolerances"].items():
        c = t["context_sheet_rho"]
        geo = next((cs for cs in summary["cases"] if cs["schematic_device"] == name), None)
        wl = f"{geo['w_um']:g} x {geo['l_um']:g}" if geo else "?"
        def corner(k: str, f: float) -> str:
            return f"{c[k]['nominal'] + f * c[k]['corner_delta']:g}"
        ctx = f"{corner('low', 1)} / {corner('nom', 1)} / {corner('high', 1)}"
        if "process_mc_sigma_frac" in c["nom"]:
            ctx += f", {c['nom']['process_mc_sigma_frac'] * 100:g}%"
        w(f"| {name} | {wl} | {t['mismatch_param_value']:g} | {t['sigma_frac'] * 100:.3f}% | "
          f"**{t['tolerance_frac'] * 100:.3f}%** | {ctx} |")
    w("")
    w("(The corner sheet-rho values assume `corner_factor = 1`, as each `parameters_res_<corner>.spice` "
      "line is written.)")
    w("")
    w("## Verdicts (drawn configurations)")
    w("")
    w("| case | device | N x segment L | DRC (klt gate) | LVS folded vs unsplit ref | negative controls | "
      "R_eff shift (model + li1 joints) | tolerance | electrical verdict |")
    w("|---|---|---|---|---|---|---|---|---|")
    for cs in summary["cases"]:
        shift, tol, verdict = electrical_cells(drawn_row(summary, cs))
        drc = "clean" if all(v["klt_status"] == "clean" for k, v in cs["drc"].items()
                             if k != "unmerged") else "VIOLATIONS"
        neg = []
        for k in ("broken", "folded_perturbed"):
            if k in cs["lvs"]:
                neg.append(f"{k}: {cs['lvs'][k]['status']}")
        w(f"| `{cs['case']}` | {cs['schematic_device']} ({cs['class']}) | {cs['segments']} x {cs['segment_l_um']:g} um | "
          f"{drc} | {cs['lvs']['folded']['status']} | {'; '.join(neg)} | "
          f"{shift} | {tol} | **{verdict}** |")
    w("")
    if summary.get("flow_failures"):
        w("**Flow failures** (an expected DRC/LVS outcome did not hold):")
        w("")
        for f in summary["flow_failures"]:
            w(f"- {f}")
        w("")

    for cs in summary["cases"]:
        a = cs["area"]
        res = cs["resistance"]
        w(f"## Case `{cs['case']}` -- {cs['schematic_device']} as {cs['segments']} series segments")
        w("")
        w(f"- Schematic: `{cs['class']}` W={cs['w_um']:g} um, L={cs['l_um']:g} um. "
          f"Drawn: {cs['segments']} segments x {cs['segment_l_um']:g} um (sum {cs['segments'] * cs['segment_l_um']:g} um), W unchanged.")
        w(f"- Connections: segment i's `R<i>_B` pad joined to segment i+1's `R<i+1>_A` pad by one li1 strap "
          f"spanning the row gap ({a['strap_count']} straps, {a['strap_li1_area_um2']:g} um^2 li1); chain ends "
          "labelled `A` (segment 0 `R0_A`) and `B`; one substrate tie labelled `SUB`. Exact strap coordinates: "
          "`geometry.json`.")
        w("")
        w("**Area** (bounding rectangle, um / um^2)")
        w("")
        w("| | width | height | area |")
        w("|---|---|---|---|")
        ub, fb, fr = a["unsplit_device_bbox"], a["folded_device_bbox"], a["folded_routed_bbox"]
        w(f"| unsplit device (as the core draws it) | {ub['width_um']:g} | {ub['height_um']:g} | {ub['area_um2']:g} |")
        w(f"| folded bank, generated | {fb['width_um']:g} | {fb['height_um']:g} | {fb['area_um2']:g} |")
        w(f"| folded bank, routed (straps + merged markers) | {fr['width_um']:g} | {fr['height_um']:g} | {fr['area_um2']:g} |")
        ut, ft = a["unsplit_with_tie_bbox"], a["folded_with_tie_bbox"]
        w(f"| unsplit + test substrate tie | {ut['width_um']:g} | {ut['height_um']:g} | {ut['area_um2']:g} |")
        w(f"| folded + test substrate tie | {ft['width_um']:g} | {ft['height_um']:g} | {ft['area_um2']:g} |")
        w("")
        w(f"Width reduced by {a['width_reduction_um']:g} um; folded/unsplit device-bbox area ratio "
          f"{a['folded_vs_unsplit_area_ratio']:g}. Routing overhead: strap bbox growth "
          f"{a['strap_bbox_growth_um2']:g} um^2 (straps sit inside the pad columns), strap li1 "
          f"{a['strap_li1_area_um2']:g} um^2. The test tie is a harness artefact (the core already has one "
          "substrate tie), not part of the bank's cost.")
        w("")
        w("**DRC**")
        w("")
        w("| stream | klt drc --deck sky130 | PDK signoff runset (sky130A_mr.drc) |")
        w("|---|---|---|")
        for vname, d in cs["drc"].items():
            pdk = fmt_counts(d.get("pdk_signoff_counts")) if "pdk_signoff_counts" in d else "not run"
            w(f"| {vname} | {d['klt_status']} ({d['klt_violations']}) | {pdk} |")
        rules = next(iter(cs["drc"].values()))["klt_rules_checked"]
        w("")
        um = cs["drc"].get("unmerged")
        if um is not None:
            added = um.get("added_vs_folded") or {}
            w("`unmerged` is an expected-to-fail DRC control: the folded bank with every strap but with the "
              "per-row psdm/rpm/urpm markers left as `res_array` draws them (no merge). It is not gated on the "
              "klt deck and gets no extraction or LVS. Rule classes the PDK signoff runset reports on it and "
              f"not on `folded`: {fmt_counts(added) if added else '**none (control did not fail)**'}.")
            w("")
        w(f"klt deck rules that had geometry to check: {', '.join(f'`{r}`' for r in rules)}.")
        w("")
        w("**LVS** (reference = one unsplit element, `options.combine_devices: true`)")
        w("")
        w("| layout | status | devices L/R/matched | property errors |")
        w("|---|---|---|---|")
        for k, l in cs["lvs"].items():
            dc = (l.get("counts") or {}).get("devices", {})
            perr = "; ".join(f"{x['name']}: layout {x['layout']:g} vs ref {x['reference']:g}"
                             for x in l["error_properties"]) or "-"
            w(f"| {k} | {l['status']} | {dc.get('layout', '?')}/{dc.get('reference', '?')}/{dc.get('matched', '?')} | {perr} |")
        w("")
        w("**Extraction-side resistance** (klt deck: R = rho*L/W + fixed offset per drawn body)")
        w("")
        w(f"- deck rho {res['deck_sheet_rho_ohm_sq']:g} ohm/sq, fixed offset {res['deck_fixed_offset_ohm']:g} ohm")
        w(f"- unsplit: deck formula {res['unsplit_deck_r_ohm']:.1f} ohm, extracted {res['unsplit_extracted_r_ohm']:.1f} ohm")
        w(f"- folded, per-primitive extraction summed: {res['folded_extracted_sum_ohm']:.1f} ohm "
          f"({pct(res['folded_extracted_sum_delta_frac'])} vs unsplit: (N-1) extra fixed offsets)")
        w(f"- folded, `--defer-resistor-fixed-offset` sum + one offset: {res['folded_defer_plus_one_offset_ohm']:.1f} ohm "
          "(the convention `klt lvs` applies once per post-combine device)")
        if res["joint_count"]:
            w(f"- {res['joint_count']} internal joint net(s), `--parasitics` lumped R each: li1 "
              f"{', '.join(f'{x:.2f}' for x in sorted(set(round(v, 2) for v in res['joint_li1_ohm_each'])))} ohm; "
              f"poly head outside the body "
              f"{', '.join(f'{x:.2f}' for x in sorted(set(round(v, 2) for v in res['joint_poly_head_ohm_each'])))} ohm "
              "(the head is already represented by the PDK model's own head term, so only the li1 strap is added "
              "in the electrical comparison)")
        w("")

    w("## Electrical comparison (single operating point)")
    w("")
    w(f"One ngspice `.op`, `{e['corner']}`, {e['temp_c']} C, bulk at 0 V, DC voltage forced across each variant "
      "(see `cases.json`). N=1 is the unsplit schematic device; `+li1` variants insert the measured per-joint li1 "
      f"strap resistance ({', '.join(f'{k}: {v:.2f} ohm' for k, v in e['joint_ohm'].items())}) at each joint. "
      "Deck: `electrical/op.cir`; log: `electrical/op.log`.")
    w("")
    w("| device | N | segment L (um) | joints | V | R_eff (ohm) | delta (ohm) | delta | tolerance | verdict |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for r in e["rows"]:
        w(f"| {r['schematic_device']} | {r['segments']} | {r['segment_l_um']:g} | "
          f"{'+li1' if r['joints_included'] else 'model only'} | {r['op_v']:g} | {r['r_eff_ohm']:.1f} | "
          f"{r['delta_ohm']:+.1f} | {pct(r['delta_frac'])} | {r['tolerance_frac'] * 100:.3f}% | {r['verdict']} |")
    w("")
    w("## Reproduce")
    w("")
    w("```bash")
    w("layout/bin/setup-venv.sh")
    w("layout/.venv/bin/python layout/bin/run-folded-res-qual-flow.py")
    w("```")
    w("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record-dir", required=True, type=Path)
    args = ap.parse_args()
    summary = json.loads((args.record_dir / "summary.json").read_text())
    (args.record_dir / "record.md").write_text(render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
