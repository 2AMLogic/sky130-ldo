#!/usr/bin/env python3
"""Issue #253: qualify folded series resistors on a resistor-only test block.

Mints one append-only record under
``layout/folded-res-qual/reports/<UTC timestamp>-<short sha>/`` and runs,
strictly sequentially (shared host -- no parallel fan-out):

1. ``gen-folded-res-qual.py`` -- unsplit / folded / open-chain /
   unmerged-marker GDS per case.
2. DRC: ``klt drc --deck sky130`` (this repo's DRC gate, same deck as the
   core records) on every stream, plus the PDK's own KLayout signoff runset
   (``libs.tech/klayout/drc/sky130A_mr.drc``, FEOL+BEOL) on the unsplit,
   folded and unmerged streams. The unmerged stream is an expected-to-fail
   control: the runset must report at least one rule class on it that the
   merged folded stream does not have.
3. Extraction: ``klt extract`` per stream (default; not the DRC-only
   unmerged control), the folded stream again
   with ``--defer-resistor-fixed-offset`` and with ``--parasitics``.
4. LVS: each stream against a one-element reference for the *unsplit*
   schematic resistor (``options.combine_devices``), plus a perturbed
   reference (R x 1.001) as a parameter-sensitivity negative control.
5. Electrical: one ngspice ``.op`` deck (one corner, one temperature) of the
   PDK model as an unsplit device and as N-segment chains, with and without
   the per-joint interconnect resistance measured in step 3.
6. ``summary.json`` + ``record.md`` with every verdict and the tolerance it
   was judged against.

Must run under ``layout/.venv/bin/python`` (needs ``klayout_tools`` for the
deck constants). Exit status is 0 only if every expected outcome held (DRC
gate clean, positive LVS matches, negative controls mismatch, unmerged-marker
control adds signoff violations); an electrical
NOT EQUIVALENT verdict is a finding, not a flow failure.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _folded_res_analysis as fra  # noqa: E402

LAYOUT_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = LAYOUT_DIR.parent
QUAL_DIR = LAYOUT_DIR / "folded-res-qual"
RES_CLASS = {"high": "res_high_po", "xhigh": "res_xhigh_po"}
PERTURB = 1.001
#: Streams that exist only as DRC controls: no extraction, LVS or klt-gate
#: verdict is taken on them.
DRC_ONLY = {"unmerged"}


def run(cmd: list[str], cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr}")
    return proc


def git(*args: str) -> str:
    return run(["git", "-C", str(REPO_ROOT), *args], check=True).stdout.strip()


def deck_constants() -> dict[str, tuple[float, float]]:
    from klayout_tools.decks import get_extraction_deck

    deck = get_extraction_deck("sky130")
    return {r.name: (r.sheet_rho_ohm_sq, r.fixed_offset_ohm) for r in deck.resistors}


def pdk_drc_counts(xml_path: Path) -> dict[str, int]:
    root = ET.parse(xml_path).getroot()
    return dict(
        Counter(
            (item.findtext("category") or "").strip("'")
            for item in root.iter("item")
        )
    )


def write_reference(path: Path, top: str, klass: str, r_ohm: float, l_um: float, w_um: float) -> None:
    path.write_text(
        "* Reference: the UNSPLIT schematic resistor (issue #253). R/A/P from the\n"
        "* same deck constants gen-ldo-reference-netlist.py uses.\n"
        f".SUBCKT {top} A B SUB\n"
        f"R1 A B {r_ohm:.6f} {klass} L={l_um:g}U W={w_um:g}U "
        f"A={l_um * w_um:g}P P={2 * (l_um + w_um):g}U\n"
        f".ENDS {top}\n"
    )


def lvs(klt: str, lvs_dir: Path, name: str, gds: str, top: str, ref: str, klass: str) -> dict[str, Any]:
    req = {
        "schema": "klt.lvs.request/1",
        "engine": "klayout",
        "layout": {"file": f"../{gds}", "deck": "sky130", "top": top, "declared_pins": ["A", "B", "SUB"]},
        "reference": {"netlist": ref, "top": top, "device_bulk": {klass: "SUB"}},
        "options": {"combine_devices": True},
    }
    req_path = lvs_dir / f"{name}.request.json"
    req_path.write_text(json.dumps(req, indent=2) + "\n")
    proc = run([klt, "lvs", req_path.name, "--format", "json"], cwd=lvs_dir)
    (lvs_dir / f"{name}.lvs.json").write_text(proc.stdout)
    data = json.loads(proc.stdout)
    errors = [m for m in data.get("mismatches", []) if m.get("severity") == "error"]
    return {
        "name": name,
        "status": data["status"],
        "counts": data.get("counts"),
        "category_counts": data.get("category_counts"),
        "error_properties": [
            {"name": m["property"]["name"], "layout": m["property"]["layout"], "reference": m["property"]["reference"]}
            for m in errors
            if m.get("category") == "device.property" and m.get("property")
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--klt", default=str(LAYOUT_DIR / ".venv" / "bin" / "klt"))
    ap.add_argument("--pdk-variant", default="sky130A")
    ap.add_argument("--cases", type=Path, default=QUAL_DIR / "cases.json")
    ap.add_argument("--out-root", type=Path, default=QUAL_DIR / "reports")
    ap.add_argument("--klayout", default=shutil.which("klayout") or "klayout")
    ap.add_argument("--ngspice", default=shutil.which("ngspice") or "ngspice")
    args = ap.parse_args()

    klt = str(Path(args.klt).resolve())
    # Captured before the record directory exists, so the record itself
    # (an untracked directory until committed) never reads as a dirty tree.
    git_sha = git("rev-parse", "HEAD")
    git_dirty = git("status", "--porcelain") != ""
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    record_id = f"{ts}-{git('rev-parse', '--short', 'HEAD')}"
    out = args.out_root / record_id
    if out.exists():
        raise SystemExit(f"record {out} already exists -- records are append-only")
    out.mkdir(parents=True)
    print(f"run-folded-res-qual-flow: record {record_id} -> {out}")

    cfg = json.loads(args.cases.read_text())
    shutil.copy(args.cases, out / "cases.json")

    pdk = json.loads(run([klt, "pdk", "find", "--pdk", args.pdk_variant, "--format", "json"], check=True).stdout)
    variant_dir = Path(pdk["root"]) / args.pdk_variant
    sim_pdk = json.loads((REPO_ROOT / "sim" / "pdk.json").read_text())
    lib_path = variant_dir / sim_pdk["ngspice_lib"]
    combined = lib_path.parent

    # --- 1. generate -------------------------------------------------------
    run([sys.executable, str(LAYOUT_DIR / "bin" / "gen-folded-res-qual.py"), "--klt", klt,
         "--pdk-variant", args.pdk_variant, "--cases", "cases.json",
         "--out-dir", "."], cwd=out, check=True)
    geometry = json.loads((out / "geometry.json").read_text())

    consts = deck_constants()
    drc_dir, ext_dir, lvs_dir, ele_dir = (out / d for d in ("drc", "extract", "lvs", "electrical"))
    for d in (drc_dir, ext_dir, lvs_dir, ele_dir):
        d.mkdir()

    failures: list[str] = []
    summary: dict[str, Any] = {"record_id": record_id, "cases": []}
    joint_ohm: dict[str, float] = {}

    for case in geometry["cases"]:
        name = case["case"]
        klass = RES_CLASS[case["flavor"]]
        rho, offset = consts[klass]
        L, W, N = case["schematic_l_um"], case["schematic_w_um"], case["segments"]
        cs: dict[str, Any] = {"case": name, "schematic_device": case["schematic_device"],
                              "class": klass, "l_um": L, "w_um": W, "segments": N,
                              "segment_l_um": case["segment_l_um"]}

        # --- 2. DRC ------------------------------------------------------
        cs["drc"] = {}
        for vname, v in case["variants"].items():
            gds = out / v["gds"]
            # klt echoes input paths into its JSON; run from the record dir
            # with record-relative paths so no host path is committed.
            proc = run([klt, "drc", v["gds"], "--deck", "sky130", "--format", "json"], cwd=out)
            (drc_dir / f"{v['top_cell']}.klt.json").write_text(proc.stdout)
            d = json.loads(proc.stdout)
            entry = {"klt_status": d["status"], "klt_violations": d["violation_count"],
                     "klt_rule_counts": d.get("rule_counts", {}),
                     "klt_rules_checked": d["coverage"].get("rules_checked", [])}
            if vname in ("unsplit", "folded", "unmerged"):
                xml = drc_dir / f"{v['top_cell']}.pdk.xml"
                # Relative input/report paths (cwd = record dir) keep host
                # paths out of the committed report XML.
                pproc = run([args.klayout, "-b", "-r", str(variant_dir / "libs.tech/klayout/drc/sky130A_mr.drc"),
                             "-rd", f"input={v['gds']}", "-rd", f"top_cell={v['top_cell']}",
                             "-rd", f"report={xml.relative_to(out)}", "-rd", "feol=true", "-rd", "beol=true"],
                            cwd=out)
                (drc_dir / f"{v['top_cell']}.pdk.log").write_text(pproc.stdout + pproc.stderr)
                # The report XML / log echo the runset's and the report's
                # absolute paths; replace the host-specific PDK prefix and the
                # record directory with placeholders (no other edit).
                for f in (xml, drc_dir / f"{v['top_cell']}.pdk.log"):
                    f.write_text(f.read_text().replace(str(variant_dir), f"$PDK_ROOT/{args.pdk_variant}")
                                 .replace(str(out.resolve()), "<record>"))
                entry["pdk_signoff_counts"] = pdk_drc_counts(xml)
            cs["drc"][vname] = entry
            if vname not in DRC_ONLY and d["status"] != "clean":
                failures.append(f"{name}/{vname}: klt drc {d['status']}")

        if "unmerged" in cs["drc"]:
            added = fra.added_rule_classes(cs["drc"]["unmerged"]["pdk_signoff_counts"],
                                           cs["drc"]["folded"]["pdk_signoff_counts"])
            cs["drc"]["unmerged"]["expected"] = "PDK signoff adds rule classes vs folded"
            cs["drc"]["unmerged"]["added_vs_folded"] = added
            if not added:
                failures.append(f"{name}/unmerged: PDK signoff added no rule class vs folded "
                                "(expected-to-fail control did not fail)")

        # --- 3. extraction -------------------------------------------------
        cs["extract"] = {}
        for vname, v in case["variants"].items():
            if vname in DRC_ONLY:
                continue
            flavours = [("default", [])]
            if vname == "folded":
                flavours += [("defer", ["--defer-resistor-fixed-offset"]), ("parasitics", ["--parasitics"])]
            if vname == "unsplit":
                flavours += [("parasitics", ["--parasitics"])]
            for tag, extra in flavours:
                stem = ext_dir / f"{v['top_cell']}.{tag}"
                proc = run([klt, "extract", v["gds"], "--deck", "sky130", "--top", v["top_cell"],
                            "--pins", "A,B,SUB", *extra, "-o", f"{stem.relative_to(out)}.spice",
                            "--format", "json"], cwd=out)
                (Path(f"{stem}.json")).write_text(proc.stdout)
                d = json.loads(proc.stdout)
                res = [x for x in d.get("devices", []) if x.get("class") == klass]
                e = {"device_count": len(res), "r_sum_ohm": fra.extracted_sum(res) if res else None,
                     "r_each_ohm": sorted({round(float(x["params"]["r_ohm"]), 6) for x in res})}
                if tag == "parasitics":
                    nets = d["parasitics"]["nets"]
                    e["nets"] = [
                        {"net": n["net"], "resistance_ohm": n["resistance_ohm"],
                         "by_layer": {b["layer"]: b["resistance_ohm"] for b in n["by_layer"]}}
                        for n in nets
                    ]
                cs["extract"][f"{vname}.{tag}"] = e

        r_unsplit_deck = fra.deck_resistance(rho, offset, L, W)
        fold_default = cs["extract"]["folded.default"]["r_sum_ohm"]
        fold_defer = cs["extract"]["folded.defer"]["r_sum_ohm"]
        internal = [n for n in cs["extract"]["folded.parasitics"]["nets"] if n["net"] not in ("A", "B", "SUB")]
        li1_joint = [n["by_layer"].get("metal0", 0.0) for n in internal]
        poly_joint = [n["by_layer"].get("poly", 0.0) for n in internal]
        cs["resistance"] = {
            "deck_sheet_rho_ohm_sq": rho,
            "deck_fixed_offset_ohm": offset,
            "unsplit_deck_r_ohm": r_unsplit_deck,
            "unsplit_extracted_r_ohm": cs["extract"]["unsplit.default"]["r_sum_ohm"],
            "folded_extracted_sum_ohm": fold_default,
            "folded_extracted_sum_delta_frac": fra.rel(fold_default, r_unsplit_deck),
            "folded_defer_sum_ohm": fold_defer,
            "folded_defer_plus_one_offset_ohm": fold_defer + offset,
            "joint_count": len(internal),
            "joint_li1_ohm_each": li1_joint,
            "joint_poly_head_ohm_each": poly_joint,
        }
        if li1_joint:
            joint_ohm[case["schematic_device"]] = max(joint_ohm.get(case["schematic_device"], 0.0),
                                                      max(li1_joint))

        # --- 4. LVS --------------------------------------------------------
        cs["lvs"] = {}
        for vname, v in case["variants"].items():
            if vname in DRC_ONLY:
                continue
            top = v["top_cell"]
            ref = f"{top}.reference.spice"
            write_reference(lvs_dir / ref, top, klass, r_unsplit_deck, L, W)
            cs["lvs"][vname] = lvs(klt, lvs_dir, top, v["gds"], top, ref, klass)
            if vname == "folded":
                pref = f"{top}.perturbed.reference.spice"
                write_reference(lvs_dir / pref, top, klass, r_unsplit_deck * PERTURB, L, W)
                cs["lvs"]["folded_perturbed"] = lvs(klt, lvs_dir, f"{top}.perturbed", v["gds"], top, pref, klass)
        expect = {"unsplit": "match", "folded": "match", "broken": "mismatch", "folded_perturbed": "mismatch"}
        for k, want in expect.items():
            if k in cs["lvs"] and cs["lvs"][k]["status"] != want:
                failures.append(f"{name}: LVS {k} is {cs['lvs'][k]['status']}, expected {want}")

        # --- area ----------------------------------------------------------
        cs["area"] = fra.area_summary(case["variants"]["unsplit"], case["variants"]["folded"], N,
                                      case["segment_l_um"], W)
        summary["cases"].append(cs)

    # --- 5. electrical (one deck, one .op) ---------------------------------
    ecfg = cfg["electrical"]
    # The deck names the model library through a `pdk` symlink to the
    # resolved PDK variant directory, created only for the run and removed
    # after, so the committed deck carries no host path.
    deck, variants = fra.build_op_deck(f"pdk/{sim_pdk['ngspice_lib']}", ecfg["corner"], ecfg["temp_c"],
                                       ecfg["devices"], joint_ohm)
    (ele_dir / "op.cir").write_text(deck)
    shutil.copy(REPO_ROOT / "sim" / "spiceinit", ele_dir / ".spiceinit")
    link = ele_dir / "pdk"
    link.symlink_to(variant_dir, target_is_directory=True)
    try:
        proc = run([args.ngspice, "-b", "op.cir"], cwd=ele_dir)
    finally:
        link.unlink()
    (ele_dir / "op.log").write_text(proc.stdout + proc.stderr)
    values = fra.parse_op_output(proc.stdout)
    missing = [v["tag"] for v in variants if v["tag"] not in values]
    if missing:
        raise SystemExit(f"ngspice output lacks {missing}; see {ele_dir / 'op.log'}")
    rows = fra.electrical_rows(variants, values)

    models_global = (combined / "continuous" / "models_global.spice").read_text()
    lib_text = (combined / "continuous" / "sky130.lib.spice").read_text()
    tolerances = {}
    for dev in ecfg["devices"]:
        tol = fra.tolerance(dev["model"], dev["w_um"], dev["l_um"], models_global, lib_text)
        corner_txt = {c: (combined / "continuous" / f"parameters_res_{c}.spice").read_text()
                      for c in ("low", "nom", "high")}
        tol["context_sheet_rho"] = {c: fra.read_corner_sheet(t, dev["model"]) for c, t in corner_txt.items()}
        tolerances[dev["schematic_device"]] = tol
    for r in rows:
        tol = tolerances[r["schematic_device"]]["tolerance_frac"]
        r["tolerance_frac"] = tol
        r["verdict"] = fra.verdict(r["delta_frac"], tol)
    summary["electrical"] = {"corner": ecfg["corner"], "temp_c": ecfg["temp_c"],
                             "lib": str(Path(sim_pdk["ngspice_lib"])), "joint_ohm": joint_ohm,
                             "tolerances": tolerances, "rows": rows}

    # --- provenance --------------------------------------------------------
    summary["provenance"] = {
        "git_sha": git_sha,
        "git_dirty": git_dirty,
        "klt_version": run([klt, "--version"], check=True).stdout.strip(),
        "klt_pin": [ln for ln in (LAYOUT_DIR / "requirements.txt").read_text().splitlines()
                    if ln.startswith("klayout-tools")][0],
        "klayout_version": run([args.klayout, "-v"]).stdout.strip(),
        "ngspice_version": next((ln.strip("* ").strip() for ln in run([args.ngspice, "-v"]).stdout.splitlines()
                                 if "ngspice-" in ln), "unknown"),
        "pdk_variant": args.pdk_variant,
        "pdk_version": pdk["version"],
        "open_pdks_commit_pinned": sim_pdk["open_pdks_commit"],
        "schematic_sha": git("log", "-1", "--format=%h", "--", "design/ldo_3v3in_1v8out.sch"),
        "pdk_drc_runset": "libs.tech/klayout/drc/sky130A_mr.drc (feol=true beol=true)",
    }
    summary["flow_failures"] = failures
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    run([sys.executable, str(LAYOUT_DIR / "bin" / "render-folded-res-qual-record.py"),
         "--record-dir", str(out)], check=True)
    (args.out_root / "LATEST").write_text(record_id + "\n")
    print(f"run-folded-res-qual-flow: done ({len(failures)} flow failure(s)); see {out / 'record.md'}")
    for f in failures:
        print(f"  FAIL: {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
