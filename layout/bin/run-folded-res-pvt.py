#!/usr/bin/env python3
"""Issue #263: PVT + seeded-mismatch qualification of folded series resistors.

Reads the predeclared ``layout/folded-res-qual/pvt/matrix.json`` and mints one
append-only record under ``layout/folded-res-qual/pvt-reports/<id>/``:

* ``deck.cir`` + ``det.request.json`` + ``mc.request.json`` -- written first.
* ``klt sim`` is run for each request on the backend named by
  ``--backend`` (default: ``$KLT_SIM_BACKEND``, i.e. the Spot batch fleet on
  dispatch workers). There is NO local fallback: if a batch submit fails the
  record is minted as BLOCKED with the exact error and the process exits 2.
* ``det.report.json`` / ``mc.report.json.gz`` -- raw klt reports.
* ``summary.json`` + ``record.md`` -- every verdict, judged against the gates
  in matrix.json (unchanged #253 tolerance + mismatch gates M1/M2).

Standard library + a ``klt`` on PATH. Exit 0 = study complete (any mix of
QUALIFIED / not qualified is a finding); 1 = invalid study (control passed,
missing data); 2 = backend blocked.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _folded_res_analysis as fra  # noqa: E402
import _folded_res_pvt as pvt  # noqa: E402

LAYOUT_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = LAYOUT_DIR.parent
QUAL_DIR = LAYOUT_DIR / "folded-res-qual"


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def git(*a: str) -> str:
    return sh(["git", "-C", str(REPO_ROOT), *a]).stdout.strip()


def pct(x: float, d: int = 4) -> str:
    return f"{x * 100:+.{d}f} %"


def run_sim(klt: str, req: Path, backend: str, env: dict) -> tuple[dict | None, str, int]:
    cmd = [klt, "sim", str(req), "--backend", backend, "--format", "json"]
    proc = sh(cmd, env=env)
    try:
        rep = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        rep = None
    if rep is not None and "error" in rep:
        return None, json.dumps(rep["error"]), proc.returncode
    if rep is None:
        return None, (proc.stderr.strip() or "no stdout") , proc.returncode
    return rep, proc.stderr.strip(), proc.returncode


def render(summary: dict) -> str:
    L = []
    a = L.append
    a(f"# Folded-resistor PVT / mismatch qualification -- record {summary['record_id']}\n")
    a("Issue #263. Isolated passive devices only (PDK resistor model chains plus the measured li1 joint "
      "resistance). **Not** a full-core compliance claim and not a layout record. The matrix, the "
      "equivalence criterion (unchanged from #253) and the mismatch gates M1/M2 were committed in "
      "`layout/folded-res-qual/pvt/matrix.json` before any run.\n")
    if summary["status"] != "COMPLETE":
        a(f"## Status: {summary['status']}\n")
        a(f"```\n{summary.get('blocked_reason', '')}\n```\n")
        a("No local fallback was run (host rule: grids go to the batch fleet). The matrix and request "
          "files in this directory are the supportable deliverable; **no segment-count recommendation "
          "is made from this record.**\n")
        return "\n".join(L)
    p = summary["provenance"]
    a("## Provenance\n")
    for k, v in p.items():
        a(f"- **{k}**: {v}")
    a("")
    a("## Tolerance (unchanged from #253)\n")
    a("| resistor | sigma_local (unsplit) | tolerance (3 sigma) |\n|---|---|---|")
    for d, t in summary["tolerance"].items():
        a(f"| {d} | {t['sigma_frac'] * 100:.4f} % | {t['tolerance_frac'] * 100:.4f} % |")
    a("")
    a(f"## Deterministic matrix ({summary['det_points']} corner x temperature x voltage points)\n")
    a("Shift = R_chain / R_unsplit - 1, each taken at the same point. `j1` = measured pinned-geometry "
      "strap (37.79 ohm/joint), the judged column; `noj` = PDK model only; `j4` = 4x joint sensitivity.\n")
    for dev in summary["devices"]:
        a(f"### {dev}\n")
        a("| N | worst shift (j1) | at | min..max (j1) | noj worst | j4 worst | verdict (j1) | j4 verdict |\n|---|---|---|---|---|---|---|---|")
        for r in summary["det"]:
            if r["device"] != dev or r["mode"] != "j1":
                continue
            n = r["segments"]
            nj = next(x for x in summary["det"] if x["device"] == dev and x["segments"] == n and x["mode"] == "noj")
            j4 = next(x for x in summary["det"] if x["device"] == dev and x["segments"] == n and x["mode"] == "j4")
            ctl = " (control)" if n in summary["controls"].get(dev, []) else ""
            a(f"| {n}{ctl} | {pct(r['worst_shift'])} | `{r['worst_point']}` | {pct(r['min_shift'])} .. {pct(r['max_shift'])} "
              f"| {pct(nj['worst_shift'])} | {pct(j4['worst_shift'])} | {r['verdict']} | {j4['verdict']} |")
        a("")
    a(f"## Seeded mismatch Monte Carlo (n={summary['mc']['n']} per point, seed {summary['mc']['seed']}, "
      f"{summary['mc_points']} process x temperature points, joint mode j1)\n")
    a("M1: |mean shift| <= tolerance at every point. M2: sigma_chain/sigma_unsplit <= "
      f"{summary['mc']['sigma_ratio_max']} at every point. Mean-shift standard error is in the JSON.\n")
    a("| resistor | N | worst abs mean shift | worst sigma ratio | M1 | M2 |\n|---|---|---|---|---|---|")
    for r in summary["mc_rollup"]:
        a(f"| {r['device']} | {r['segments']} | {r['worst_abs_mean_shift'] * 100:.4f} % | {r['worst_sigma_ratio']:.4f} "
          f"| {'pass' if r['m1'] else 'FAIL'} | {'pass' if r['m2'] else 'FAIL'} |")
    a("")
    a("### Sigma detail at tt_mm / 27C (relative, j1)\n")
    a("| resistor | N | sigma unsplit | sigma chain | ratio | mean shift +- SE |\n|---|---|---|---|---|---|")
    for r in summary["mc_detail_tt27"]:
        a(f"| {r['device']} | {r['segments']} | {r['sigma_rel_unsplit'] * 100:.4f} % | {r['sigma_rel_chain'] * 100:.4f} % "
          f"| {r['sigma_ratio']:.3f} | {pct(r['mean_shift'])} +- {r['mean_shift_se'] * 100:.4f} % |")
    a("")
    a("## Qualification and recommendation\n")
    a("QUALIFIED = deterministic criterion (all points, j1) AND M1 AND M2.\n")
    a("| resistor | N | det worst | det | M1 | M2 | QUALIFIED | j4 flips verdict |\n|---|---|---|---|---|---|---|---|")
    for q in summary["qualification"]:
        ctl = " (control)" if q["control"] else ""
        a(f"| {q['device']} | {q['segments']}{ctl} | {q['det_worst_abs_shift'] * 100:.4f} % | {'ok' if q['det_ok'] else 'FAIL'} "
          f"| {'ok' if q['m1'] else 'FAIL'} | {'ok' if q['m2'] else 'FAIL'} | **{'YES' if q['qualified'] else 'no'}** | {'yes' if q['j4_flips'] else 'no'} |")
    a("")
    a("### Control check\n")
    a(summary["control_check"] + "\n")
    a("### Divider (R_FB) VOUT sensitivity, informational\n")
    a("Relative VOUT change of the 1:2 divider from the deterministic worst R_FB shift, if only R_FB_A is "
      "folded vs. all three units folded identically (common shift cancels to first order). Not a spec claim.\n")
    a("| N | worst unit shift | only R_FB_A folded | all three folded |\n|---|---|---|---|")
    for r in summary["divider"]:
        a(f"| {r['segments']} | {pct(r['shift'])} | {pct(r['vout_only_a'])} | {pct(r['vout_all'])} |")
    a("")
    a("### R_BIAS current sensitivity, informational\n")
    a("I_bias ~ 1/R_BIAS to first order; the worst deterministic R shift moves I_bias by the negative of it. "
      "Whether that is acceptable is a design/spec decision, not made here.\n")
    a("## Verdict\n")
    for dev, rec in summary["recommendation"].items():
        if rec is None:
            a(f"- **{dev}: NO QUALIFIED FOLD** among the candidates; only the unsplit device is supported.")
        else:
            a(f"- **{dev}: largest qualified segment count N = {rec}** (uncompensated, drawn L = schematic L). "
              "Candidates above it are not qualified in this record.")
    a("\nThese are passive-device electrical results. They do not touch the Area row, do not "
      "claim core compliance, and leave length compensation and schematic changes out of scope.\n")
    a("## Limitations\n")
    for lim in summary["limitations"]:
        a(f"- {lim}")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", type=Path, default=QUAL_DIR / "pvt" / "matrix.json")
    ap.add_argument("--out-root", type=Path, default=QUAL_DIR / "pvt-reports")
    ap.add_argument("--backend", default=os.environ.get("KLT_SIM_BACKEND", "batch"))
    ap.add_argument("--klt", default="klt")
    ap.add_argument("--pdk-root", type=Path, default=Path(os.environ.get("PDK_ROOT", Path.home() / ".volare")))
    ap.add_argument("--dry-run", action="store_true", help="write deck/requests and exit (no simulation)")
    args = ap.parse_args()

    matrix = json.loads(args.matrix.read_text())
    sim_pdk = json.loads((REPO_ROOT / "sim" / "pdk.json").read_text())
    pdk_variant_dir = args.pdk_root / sim_pdk["variant"]
    src = (pdk_variant_dir / "SOURCES").read_text() if (pdk_variant_dir / "SOURCES").exists() else ""
    m = re.search(r"open_pdks\s+([0-9a-f]{40})", src)
    pdk_commit = m.group(1) if m else "unknown"
    if pdk_commit != sim_pdk["open_pdks_commit"]:
        raise SystemExit(f"PDK at {pdk_variant_dir} is {pdk_commit}, pin is {sim_pdk['open_pdks_commit']}")
    lib_dir = pdk_variant_dir / "libs.tech" / "combined"
    lib_text = (lib_dir / "sky130.lib.spice").read_text()
    glob_text = (lib_dir / "continuous" / "models_global.spice").read_text()
    tol_info = {
        d["schematic_device"]: fra.tolerance(d["model"], d["w_um"], d["l_um"], glob_text, lib_text)
        for d in matrix["devices"]
    }
    tol = {k: v["tolerance_frac"] for k, v in tol_info.items()}

    git_sha = git("rev-parse", "HEAD")
    git_dirty = bool(git("status", "--porcelain", "--", "layout/bin", "layout/folded-res-qual/pvt"))
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    record_id = f"{ts}-{git('rev-parse', '--short', 'HEAD')}"
    out = args.out_root / record_id
    out.mkdir(parents=True, exist_ok=False)  # append-only: never reuse an id
    print(f"run-folded-res-pvt: record {record_id} -> {out}")

    (out / "matrix.json").write_text(args.matrix.read_text())
    (out / "deck.cir").write_text(pvt.build_deck(matrix))
    det_req = pvt.det_request(matrix, "deck.cir")
    mc_req = pvt.mc_request(matrix, "deck.cir")
    (out / "det.request.json").write_text(json.dumps(det_req, indent=2) + "\n")
    (out / "mc.request.json").write_text(json.dumps(mc_req, indent=2) + "\n")
    if args.dry_run:
        return 0

    env = dict(os.environ)
    env["PDK_ROOT"] = str(args.pdk_root)
    klt_ver = sh([args.klt, "--version"]).stdout.strip()
    summary: dict = {"record_id": record_id, "status": "COMPLETE"}
    reports = {}
    for name in ("det", "mc"):
        rep, msg, rc = run_sim(args.klt, out / f"{name}.request.json", args.backend, env)
        if rep is None:
            summary.update(status="BLOCKED", blocked_reason=f"{name}: klt sim --backend {args.backend} failed (rc {rc}): {msg}",
                           provenance={"klt": klt_ver, "backend": args.backend, "git_sha": git_sha})
            (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            (out / "record.md").write_text(render(summary))
            print(summary["blocked_reason"], file=sys.stderr)
            return 2
        reports[name] = rep
        raw = json.dumps(rep, indent=1).encode()
        if name == "mc":
            (out / "mc.report.json.gz").write_bytes(gzip.compress(raw))
        else:
            (out / "det.report.json").write_bytes(raw)
        print(f"{name}: {rep['corner_count']} units, status {rep['status']}, env.remote={rep['environment'].get('remote')}")

    det_pts = pvt.corner_values(reports["det"])
    mc_pts = pvt.corner_values(reports["mc"])
    nvar = len(pvt.variants(matrix))
    for label, pts in (("det", det_pts), ("mc", mc_pts)):
        bad = [c for c, v in pts if len(v) != nvar]
        if bad:
            raise SystemExit(f"{label}: {len(bad)} units lack a full measurement set (first: {bad[0]})")
    exp_det = len(matrix["deterministic"]["process"]) * len(matrix["deterministic"]["temperature_c"]) * len(matrix["devices"][0]["op_v"])
    mcm = matrix["monte_carlo"]
    exp_mc = len(mcm["process"]) * len(mcm["temperature_c"]) * mcm["n"]
    if len(det_pts) != exp_det or len(mc_pts) != exp_mc:
        raise SystemExit(f"unit counts det {len(det_pts)}/{exp_det} mc {len(mc_pts)}/{exp_mc}")

    det = pvt.det_shifts(det_pts, matrix, tol)
    groups = pvt.mc_groups(mc_pts)
    mc_rows = pvt.mc_stats(groups, matrix, tol)
    agg = pvt.mc_rollup(mc_rows)
    quals = pvt.qualification(det, agg, matrix)

    controls = {d["schematic_device"]: d["control_segments"] for d in matrix["devices"]}
    ctl_fail = [q for q in quals if q["control"] and q["det_ok"]]
    control_ok = not ctl_fail
    control_check = ("The known nonequivalent control(s) "
                     + ", ".join(f"{d} N={n}" for d, ns in controls.items() for n in ns)
                     + (" FAILED the deterministic criterion as required (study valid)." if control_ok
                        else " PASSED the deterministic criterion: the study is INVALID."))
    divider = []
    for r in det:
        if r["device"] == "R_FB_A" and r["mode"] == "j1" and r["segments"] > 1:
            s = r["worst_shift"]
            divider.append({"segments": r["segments"], "shift": s,
                            "vout_only_a": pvt.divider_vout_error(s, 1),
                            "vout_all": pvt.divider_vout_error(s, 3)})
    envs = {k: v["environment"] for k, v in reports.items()}
    summary.update(
        tolerance=tol_info, devices=[d["schematic_device"] for d in matrix["devices"]], controls=controls,
        det=det, det_points=len(det_pts), mc={"n": mcm["n"], "seed": mcm["seed"], "sigma_ratio_max": mcm["sigma_ratio_max"]},
        mc_points=len(groups), mc_stats=mc_rows,
        mc_rollup=[{"device": k[0], "segments": k[1], "mode": k[2], **v} for k, v in sorted(agg.items()) if k[2] == "j1"],
        mc_detail_tt27=[r for r in mc_rows if r["process"] == "tt_mm" and r["temp"] == "27C" and r["mode"] in ("j1", "noj") and
                        (r["mode"] == "j1" or r["segments"] == 1)],
        qualification=quals, control_check=control_check, divider=divider,
        recommendation={d["schematic_device"]: pvt.recommendation(quals, d["schematic_device"]) for d in matrix["devices"]},
        limitations=matrix["limitations_declared_up_front"] + [
            "klt reports resistor mismatch activity as 'not independently verified' for sky130; the nonzero unsplit sigma above is the evidence the draws are live.",
            "Seeds are klt-derived per sample from the base seed; the same seed is reused at every process/temperature point, so cross-corner comparisons share the derivation scheme but not necessarily draw values.",
        ],
        provenance={
            "git_sha": git_sha, "git_dirty_tooling": git_dirty, "klt": klt_ver, "backend": args.backend,
            "ngspice_det": f"{envs['det'].get('engine')} {envs['det'].get('engine_version')}",
            "ngspice_mc": f"{envs['mc'].get('engine')} {envs['mc'].get('engine_version')}",
            "remote_det": envs["det"].get("remote"), "remote_mc": envs["mc"].get("remote"),
            "pdk": f"sky130A open_pdks {pdk_commit} (pin {sim_pdk['open_pdks_commit']})",
            "models_lib_sha256_det": envs["det"].get("models_lib_sha256"),
            "models_lib_sha256_mc": envs["mc"].get("models_lib_sha256"),
            "joint_source": matrix["tool_pins"]["joint_source_record"],
            "mc_seed": mcm["seed"], "mc_n": mcm["n"],
        },
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out / "record.md").write_text(render(summary))
    (args.out_root / "LATEST").write_text(record_id + "\n")
    print((out / "record.md").read_text().split("## Verdict")[-1][:800])
    return 0 if control_ok else 1


if __name__ == "__main__":
    sys.exit(main())
