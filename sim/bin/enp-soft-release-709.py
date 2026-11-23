#!/usr/bin/env python3
"""EA_OUT/PB clamp soft-release wake-shaping screen (issue #709, post-#714).

Committed, reproducible replacement for the unrecoverable w1 scratch run of
pilot note 20261121-709 section 4: that gate-RC "soft release" was
100 kOhm x 1 pF = 100 ns on a gate that cannot be confirmed, and a ~100 us
release was never measured. This driver applies the deck delta the 2026-11-23
re-curation asked for -- the EN-gated clamps XM_ENP (EA_OUT clamp, W=10 L=0.5)
and XM_ENP5 (PB clamp, W=2 L=0.5) released through a gate RC with tau = 100 us
(R = 100 kOhm gate-to-EN, C = tau/R = 1 nF gate-to-VIN) -- and measures the
enable-edge charge packet and the ramp bounds at the two screen corners
(tt/27C/3.30V, sf/-40C/2.97V) on the production DUT (R_CZ L=52).

Local single-corner debug probes only: one sequential `ngspice -b` per
variant x corner through corner-run.py's own run_corner(), so deck minting,
the 12-leg window walk and all grading are the bench's own code path; the
ramp-monotonicity settings come verbatim from sim/startup/experiment.json.
Scratch decks live under gitignored sim/build/issue709-ws/; the committed
delta is this script plus the per-deck sha256 recorded in the pilot note.
Writes no evidence record, touches no schematic, changes no spec.

    python3 sim/bin/enp-soft-release-709.py [--variants base,enp,enp5,both]
        [--corners tt,sf] [--tau-us 100] [--timeout 1200]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location("corner_run_709", HERE / "corner-run.py")
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)

from _corner_model import BUILD_DIR, Corner, SPICEINIT_FILE  # noqa: E402

SCREEN_CORNERS = {
    "tt": Corner("tt", 27.0, 3.30),
    "sf": Corner("sf", -40.0, 2.97),
}
VARIANTS = ("base", "enp", "enp5", "both")
R_GATE_OHM = 100e3

GATE_CARDS = {
    "enp": ("XM_ENP", "EA_OUT", "GENP"),
    "enp5": ("XM_ENP5", "PB", "GENP5"),
}


def patch_gate(body: list[str], device: str, drain: str, gate_node: str, r_ohm: float, c_f: float) -> list[str]:
    """Rewrite `<device> <drain> EN VIN VIN ...` to gate node `gate_node` and
    append the soft-release RC (R gate-to-EN, C gate-to-VIN) right after the
    card, inside the same subcircuit. Exactly one card must match."""
    out: list[str] = []
    n = 0
    pending = None
    for ln in body:
        st = ln.strip()
        if pending is not None and not st.startswith("+"):
            out.extend(pending)
            pending = None
        if st.split()[:1] == [device] and st.split()[1:3] == [drain, "EN"]:
            tokens = st.split()
            out.append(" ".join([device, drain, gate_node, *tokens[3:]]))
            pending = [
                f"R{device[1:]}S {gate_node} EN {r_ohm:g}",
                f"C{device[1:]}S {gate_node} VIN {c_f:g}",
            ]
            n += 1
        else:
            out.append(ln)
    if pending is not None:
        out.extend(pending)
    if n != 1:
        sys.exit(f"expected exactly one {device} {drain} EN card, found {n}")
    return out


def variant_body(base: list[str], variant: str, c_f: float) -> list[str]:
    if variant == "base":
        return list(base)
    keys = [variant] if variant in GATE_CARDS else ["enp", "enp5"]
    body = list(base)
    for key in keys:
        device, drain, gate_node = GATE_CARDS[key]
        body = patch_gate(body, device, drain, gate_node, R_GATE_OHM, c_f)
    return body


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--corners", default="tt,sf")
    ap.add_argument("--tau-us", type=float, default=100.0)
    ap.add_argument("--timeout", type=int, default=1200)
    args = ap.parse_args(argv)

    c_f = args.tau_us * 1e-6 / R_GATE_OHM
    pin = cr.load_pin()
    pdk = cr.resolve_pdk(pin)
    exp = cr.load_experiment(cr.REPO_ROOT / "sim" / "startup")
    cout_by_leg = {leg["id"]: float(leg["cout_f"]) for leg in cr.window_legs(exp.raw)}

    runs: dict[str, dict] = {}
    for ckey in [c.strip() for c in args.corners.split(",")]:
        corner = SCREEN_CORNERS[ckey]
        shared = BUILD_DIR / "issue709-ws" / f"netlist-{corner.id}"
        shared.mkdir(parents=True, exist_ok=True)
        netlist = cr.netlist_with_xschem(exp.schematic, shared, pdk)
        base_body = cr.netlist_body(netlist)
        for variant in [v.strip() for v in args.variants.split(",")]:
            body = variant_body(base_body, variant, c_f)
            run_dir = BUILD_DIR / "issue709-ws" / f"{variant}-tau{args.tau_us:g}us" / corner.id
            run_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SPICEINIT_FILE, run_dir / ".spiceinit")
            res = cr.run_corner(exp, pdk, corner, body, run_dir, None, args.timeout)
            deck = run_dir / f"{corner.id}.deck.spice"
            res["deck_sha256"] = (
                hashlib.sha256(deck.read_bytes()).hexdigest() if deck.is_file() else None
            )
            runs[f"{variant}|{corner.id}"] = res

    leg_ids = [leg["id"] for leg in cr.window_legs(exp.raw)]
    for key, res in runs.items():
        variant, corner_id = key.split("|")
        by_name = {m["name"]: m for m in res["measurements"]}
        print(f"\n## {variant} (tau={args.tau_us:g} us) @ {corner_id} -- deck sha256 {res['deck_sha256'][:16] if res['deck_sha256'] else '?'}")
        print("| leg | drawdown (uV) | Q=dd*C_out (pC) | vpk_v | vfloor_v | tramp_ms |")
        print("|---|---|---|---|---|---|")
        for leg in leg_ids:
            ramp = next(r for r in res["ramp_monotonicity"] if r["leg"] == leg)
            dd = ramp["max_drawdown_v"]
            q = dd * cout_by_leg[leg] * 1e12 if dd is not None else None
            cells = []
            for tpl in ("vpk_v", "vfloor_v", "tramp_ms"):
                m = by_name.get(f"{tpl}__{leg}")
                cells.append(
                    "n/a" if m is None or m["value"] is None
                    else f"{m['value']:.6g}" + ("" if m["pass"] else " FAIL")
                )
            dd_s = "n/a" if dd is None else f"{dd * 1e6:.3f}"
            q_s = "n/a" if q is None else f"{q:.3f}"
            print(f"| {leg} | {dd_s} | {q_s} | {cells[0]} | {cells[1]} | {cells[2]} |")
        verdict = {r["leg"]: (r["status"], "; ".join(r["reasons"])[:120]) for r in res["ramp_monotonicity"]}
        bounds_fail = [m["name"] for m in res["measurements"] if not m["pass"]]
        print(f"\ncorner pass: {res['pass']}; ngspice exit {res['ngspice_exit']}; "
              f"bounds failures: {bounds_fail or 'none'}")
        for leg, (status, reasons) in verdict.items():
            if status != "FAIL":
                print(f"  {leg}: {status} {reasons}".rstrip())
        summary_path = BUILD_DIR / "issue709-ws" / f"{variant}-tau{args.tau_us:g}us" / f"{corner_id}.summary.json"
        summary_path.write_text(json.dumps(res, indent=1)[: 4_000_000] + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
