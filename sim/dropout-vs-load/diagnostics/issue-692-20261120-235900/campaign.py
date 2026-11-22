#!/usr/bin/env python3
"""Issue #692 paired 45-point PVT campaign driver (baseline vs #357 rev1).

Runs the dropout-vs-load cold-start crossing bench and the iq bench through
`klt sim --backend batch` (the #374 cold-start adapter and the #213/#381 iq
endpoint adapter, both via corner-run.py's own batch backend library), for
the committed baseline DUT and for the re-based #357 rev1 candidate
(candidate.py, copied from ../issue-357/ and re-verified against the current
netlist). All evidence lands in this diagnostics directory; no records/ entry
is minted and no production file changes.

Per-corner observables beyond the two graded manifest measurements are added
as EXTRA `meas tran` step measurements (read-only cards, appended to the
validated single-step request after `prepare_batch_requests` has done its
stimulus/shape validation) plus deck-level `.save` cards for the device
currents they read. The analysis/stimulus cards of the validated request are
not modified.

Modes (one batch submit set each; see commands.sh for the as-executed order):

  syntax-probe  ONE local `ngspice -b` per variant at tt / 27 C / 3.30 V
                (single-corner debug probe, allowed on this host) validating
                the extra meas-card / .save syntax before anything is
                submitted. Not campaign evidence; the recorded evidence is
                the batch runs.
  pair          the tt / 27 C / 3.30 V pair as two single-corner batch
                requests (baseline, candidate) -- the #357 reproduction leg.
  dropout-base / dropout-cand   the full 45-point matrix, one variant each
                (one request per supply, 15 corners per request).
  iq-base / iq-cand             the full 45-point iq matrix, one variant each
                (one request per supply x endpoint, 15 corners per request).
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parents[2]
REPO = SIM.parent
sys.path.insert(0, str(SIM / "bin"))
sys.path.insert(0, str(HERE))
import _probe_common as pc  # noqa: E402

cr = pc.load_corner_run()
import candidate as cand  # noqa: E402

PF = "pfet_g5v0d10v5"
NF = "nfet_g5v0d10v5"
V = "@m.xldo.{n}.msky130_fd_pr__{t}[{p}]"


def vec(n: str, t: str, p: str) -> str:
    return V.format(n=n, t=t, p=p)


def dev(n: str, t: str, props: list[str]) -> list[str]:
    return [vec(n, t, p) for p in props]


CROSS_VOUT = "when v(vout)=1.764 fall=1 td=6m"
CROSS_VIN_EDGE = "when v(vin)=2.064 fall=1 td=6m"

TAIL = {"base": ("xm_tail", PF), "cand": ("xm_ntail", NF)}
BIASREF = {"base": ("xm_biasp1", PF), "cand": ("xm_vrf", NF)}


def extra_saves(variant: str) -> list[str]:
    tn, tt_ = TAIL[variant]
    bn, bt = BIASREF[variant]
    vecs = dev(tn, tt_, ["id"]) + dev("xm_clim", PF, ["id", "vgs"]) + dev(bn, bt, ["id"]) + dev("xm_clp", PF, ["id"])
    return [f".save {v}" for v in vecs]


def extra_cards(variant: str) -> list[dict]:
    tn, tt_ = TAIL[variant]
    bn, bt = BIASREF[variant]
    tail_i = vec(tn, tt_, "id")
    bias_i = vec(bn, bt, "id")
    clim_i = vec("xm_clim", PF, "id")
    clim_vgs = vec("xm_clim", PF, "vgs")
    cards = [
        (f"meas tran ea_out_at_x find v(xldo.ea_out) {CROSS_VOUT}"),
        (f"meas tran tail_i_at_x find {tail_i} {CROSS_VOUT}"),
        (f"meas tran mclim_i_at_x find {clim_i} {CROSS_VOUT}"),
        (f"meas tran vout_at_2v064 find v(vout) {CROSS_VIN_EDGE}"),
        (f"meas tran mclim_vgs_at_2v064 find {clim_vgs} {CROSS_VIN_EDGE}"),
        (f"meas tran mclim_i_at_2v064 find {clim_i} {CROSS_VIN_EDGE}"),
        (f"meas tran tail_i_set avg {tail_i} from=5.5m to=6m"),
        (f"meas tran biasref_i_set avg {bias_i} from=5.5m to=6m"),
    ]
    return [{"name": c.split()[2], "spice": "." + c} for c in cards]


EXTRA_NAMES = ["ea_out_at_x", "tail_i_at_x", "mclim_i_at_x", "vout_at_2v064",
               "mclim_vgs_at_2v064", "mclim_i_at_2v064", "tail_i_set", "biasref_i_set"]


def full_matrix(exp) -> list:
    c = exp.raw["corners"]
    return [cr.Corner(p, float(t), float(v)) for p in c["process"]
            for t in c["temperature_c"] for v in c["supply_v"]]


def variant_body(exp, pdk, variant: str, rev: int) -> tuple[list[str], dict]:
    """Netlist body of the bench with the variant applied (+ .save cards)."""
    with tempfile.TemporaryDirectory(prefix="i692-nl-") as nl:
        net = cr.netlist_with_xschem(exp.schematic, Path(nl), pdk)
        raw = "\n".join(cr.netlist_body(net)) + "\n"
    notes, problems = [], []
    if variant == "cand":
        edited, notes = cand.apply_candidate(raw, rev)
        problems = cand.check_candidate(raw, edited)
        if problems:
            raise SystemExit("candidate invariant check failed: " + "; ".join(problems))
    else:
        edited = raw
    body = edited.splitlines() + extra_saves(variant)
    return body, {"raw": raw, "edited": edited, "notes": notes, "problems": problems}


def extend_requests(prepared, variant: str, dropout: bool) -> None:
    """Append the extra read-only meas cards to each written request JSON."""
    if not dropout:
        return
    for _group, request_path, _request in prepared:
        req = json.loads(request_path.read_text())
        steps = req.get("analysis_steps") or []
        if len(steps) != 1:
            raise SystemExit(f"{request_path}: expected one analysis step")
        have = {m.get("name") for m in steps[0].get("measurements", [])}
        for e in extra_cards(variant):
            if e["name"] not in have:
                steps[0]["measurements"].append(e)
        request_path.write_text(json.dumps(req, indent=2, sort_keys=True) + "\n")


def extract_extras(response: dict, supply_v: float | None = None) -> dict[str, dict[str, float | None]]:
    """{corner key 'proc|temp|supply': {extra name: value|None}} from a response.

    The supply is not a klt corner axis (it is a fixed netlist `.param` per
    request), so it must come from the caller -- without it the three supply
    responses of a matrix leg would collide on proc|temp."""
    out: dict[str, dict[str, float | None]] = {}
    for rc in response.get("corners", []):
        if not isinstance(rc, dict) or not isinstance(rc.get("process"), str):
            continue
        key = f"{rc['process']}|{rc.get('temperature_c')}" + (
            f"|{supply_v:g}" if supply_v is not None else "")
        vals: dict[str, float | None] = {}
        by_name = {}
        for rm in rc.get("measurements", []):
            if isinstance(rm, dict) and isinstance(rm.get("name"), str):
                by_name[rm["name"]] = rm.get("value")
        for n in EXTRA_NAMES:
            v = by_name.get(f"dropout.{n}")
            vals[n] = float(v) if isinstance(v, (int, float)) else None
        out[key] = vals
    return out


def run_leg(leg: str, exp_slug: str, variant: str, rev: int, quick_matrix=None,
            timeout: int = 300, allow_pdk_mismatch: bool = False) -> dict:
    run_dir = HERE / "runs" / leg
    if run_dir.exists():
        raise SystemExit(f"{run_dir} exists: evidence is append-only")
    run_dir.mkdir(parents=True)
    pdk = cr.resolve_pdk(cr.load_pin())
    pin = cr.load_pin()
    exp = cr.load_experiment(SIM / exp_slug)
    dropout = exp_slug == "dropout-vs-load"
    body, provenance = variant_body(exp, pdk, variant, rev)
    (run_dir / "netlist.spice").write_text("\n".join(body) + "\n")
    if variant == "cand":
        diff = "".join(difflib.unified_diff(
            provenance["raw"].splitlines(True), provenance["edited"].splitlines(True),
            "netlist.raw.spice", "netlist.edited.spice"))
        (run_dir / "netlist.diff").write_text(diff)
    matrix = quick_matrix if quick_matrix is not None else full_matrix(exp)
    prepared = cr.prepare_batch_requests(exp, pdk, matrix, quick_matrix is not None,
                                         body, run_dir, timeout)
    extend_requests(prepared, variant, dropout)
    results, logs, execution = cr.run_batch(exp, pdk, pin, prepared, matrix, run_dir,
                                            timeout, allow_pdk_mismatch)
    rec = {
        "leg": leg, "experiment": exp_slug, "variant": variant, "candidate_rev": rev if variant == "cand" else None,
        "matrix": [[c.process, c.temp_c, c.supply_v] for c in matrix],
        "corner_ids": [c.id for c in matrix],
        "results": results, "execution": execution,
        "provenance": {
            "source_commit": pc.git_provenance(REPO),
            "driver_sha256": pc.sha(Path(__file__).read_bytes()),
            "candidate_py_sha256": pc.sha((HERE / "candidate.py").read_bytes()),
            "netlist_sha256": pc.sha(("\n".join(body) + "\n").encode()),
            "dut_sch_sha256": pc.sha((REPO / "design" / "ldo_3v3in_1v8out.sch").read_bytes()),
            "testbench_sha256": pc.sha(exp.schematic.read_bytes()),
            "experiment_json_sha256": pc.sha((SIM / exp_slug / "experiment.json").read_bytes()),
            "edit_notes": provenance["notes"],
            "candidate_invariant_problems": provenance["problems"],
            "pdk": {"open_pdks_commit": pdk.installed_commit, "matches_pin": pdk.matches_pin,
                    "lib_sha256": pc.sha(Path(pdk.lib_file).read_bytes())},
            "tools": cr.tool_versions(),
        },
    }
    if dropout:
        extras = {}
        for resp_path in sorted((run_dir / "klt-out").glob("*/response.json")):
            m = re.fullmatch(r"v([0-9.]+)", resp_path.parent.name)
            supply = float(m.group(1)) if m else None
            extras.update(extract_extras(json.loads(resp_path.read_text()), supply))
        rec["extras"] = extras
        rec["extras"] = extras
    (run_dir / "leg.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    for cid, text in logs.items():
        (run_dir / "logs").mkdir(exist_ok=True)
        (run_dir / "logs" / f"{cid}.log").write_text(text)
    n_pass = sum(1 for r in results if r["pass"])
    print(f"[{leg}] {n_pass}/{len(results)} corners harness-pass; "
          f"jobs: {', '.join(str(r.get('job_id')) for r in execution['requests'])}")
    return rec


def syntax_probe(rev: int = 1) -> None:
    pdk = cr.resolve_pdk(cr.load_pin())
    exp = cr.load_experiment(SIM / "dropout-vs-load")
    corner = cr.Corner("tt", 27.0, 3.3)
    out = HERE / "runs" / ("local-syntax-r2" if rev != 1 else "local-syntax")
    if out.exists():
        raise SystemExit(f"{out} exists: append-only")
    for variant in ("base", "cand"):
        body, prov = variant_body(exp, pdk, variant, rev)
        deck = cr.build_deck(exp, pdk, corner, body)
        i = deck.index(".control")
        ctl = deck[i:]
        ins = "\n".join(c["spice"].lstrip(".") for c in extra_cards(variant))
        anchor = "meas tran vout_at_max_vin_v avg v(vout) from=5.5m to=6m\n"
        if ctl.count(anchor) != 1:
            raise SystemExit("manifest meas card not found")
        ctl = ctl.replace(anchor, anchor + ins + "\n", 1)
        deck = deck[:i] + ctl
        rd = out / variant
        rd.mkdir(parents=True)
        (rd / "deck.spice").write_text(deck)
        (rd / ".spiceinit").write_text((SIM / "spiceinit").read_text())
        log, elapsed, rcode = pc.run_ngspice_deck(rd, timeout=900)
        got = {}
        for n in EXTRA_NAMES + ["dropout_vin_x", "vout_at_max_vin_v"]:
            m = re.search(rf"^{n}\s*=\s*(-?[0-9.]+(?:[eE][-+]?[0-9]+)?)", log, re.M)
            got[n] = float(m.group(1)) if m else None
        rec = {"variant": variant, "ngspice_exit": rcode, "elapsed_s": round(elapsed, 1),
               "solver_diagnostic": cr.detect_solver_diagnostic(log), "cards": got,
               "netlist_sha256": pc.sha(("\n".join(body) + "\n").encode()),
               "edit_notes": prov["notes"], "source_commit": pc.git_provenance(REPO)}
        (rd / "result.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
        print(json.dumps(rec))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["syntax-probe", "pair", "dropout-base", "dropout-cand",
                                     "iq-base", "iq-cand", "dropout-cand-r2", "iq-cand-r2"])
    ap.add_argument("--rev", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--allow-pdk-mismatch", action="store_true")
    a = ap.parse_args(argv)
    if a.mode == "syntax-probe":
        syntax_probe(a.rev)
        return
    pair = [cr.Corner("tt", 27.0, 3.3)]
    if a.mode == "pair":
        run_leg("pair-base", "dropout-vs-load", "base", a.rev, quick_matrix=pair,
                timeout=a.timeout, allow_pdk_mismatch=a.allow_pdk_mismatch)
        run_leg("pair-cand", "dropout-vs-load", "cand", a.rev, quick_matrix=pair,
                timeout=a.timeout, allow_pdk_mismatch=a.allow_pdk_mismatch)
        return
    variant = "base" if a.mode.endswith("-base") else "cand"
    if a.mode.endswith("-r2"):
        a.rev = 2
    exp = "dropout-vs-load" if a.mode.startswith("dropout") else "iq"
    run_leg(a.mode, exp, variant, a.rev, timeout=a.timeout, allow_pdk_mismatch=a.allow_pdk_mismatch)


if __name__ == "__main__":
    main()
