#!/usr/bin/env python3
"""Issue #357 sizing derivation benches (one ngspice -b each, tt / 27 C, DC only).

Isolated device benches used to *derive* the candidate's bias numbers before any
loop run (no closed-loop DUT here, nothing is graded):

  vref-vi    XM_VRF (nfet_g5v0d10v5 L=1 W=10 nf=2, gate = 1.2 V, body = 0) with its
             drain held at 1.0 V and its source swept 0 -> 0.6 V: gives the source
             voltage V_NVR at which Id = I_R, hence R_VR = V_NVR / I_R.
  headroom   the complete candidate bias chain (VREF V-to-I + PBR diode + PBN/NBR
             mirror + NTAIL tail sink + the clamp reference XM_CLP into a
             resistive dummy) with VIN swept 3.63 -> 1.5 V: shows where each
             branch current leaves its 3.3 V value (compliance limit).

usage: sizing.py <mode> <run_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parents[2]
sys.path.insert(0, str(SIM / "bin"))
sys.path.insert(0, str(HERE))
import _probe_common as pc  # noqa: E402
import candidate as cand  # noqa: E402

cr = pc.load_corner_run()

P = "@m.{n}.msky130_fd_pr__{t}[{p}]"


def vref_vi_deck(lib: str) -> str:
    return "\n".join([
        "* issue #357 sizing: XM_VRF source-voltage vs drain current (tt / 27 C)",
        ".option wnflag=1", ".temp 27", f'.lib "{lib}" tt',
        "VD D 0 1.0", "VG G 0 1.2", "VS S 0 0.3",
        "XM_VRF D G S 0 sky130_fd_pr__nfet_g5v0d10v5 " + cand.NFET_GEOM["L1W10"],
        ".control", "save all " + P.format(n="xm_vrf", t="nfet_g5v0d10v5", p="id")
        + " " + P.format(n="xm_vrf", t="nfet_g5v0d10v5", p="vgs"),
        "dc VS 0 0.6 0.005",
        "wrdata vref_vi.dat " + P.format(n="xm_vrf", t="nfet_g5v0d10v5", p="id")
        + " " + P.format(n="xm_vrf", t="nfet_g5v0d10v5", p="vgs"),
        "quit", ".endc", ".end", ""])


def headroom_deck(lib: str, rev: int) -> str:
    cards = cand.bias_cards(rev)
    return "\n".join([
        f"* issue #357 sizing: candidate rev{rev} bias chain compliance vs VIN (tt / 27 C)",
        ".option wnflag=1", ".temp 27", f'.lib "{lib}" tt',
        "VVIN VIN 0 3.3", "VVREF VREF 0 1.2", "VGND AMP_ENN 0 0",
        # tail sink drain held at its expected operating point (VREF - Vgs_in)
        "VTL NTAIL_PROBE 0 0.35", "VTLM NTAIL NTAIL_PROBE 0",
        # clamp reference into a dummy load at its untripped level region
        "VCLM CL_CMP 0 1.0",
        *cards,
        "XM_NTAIL NTAIL NBR AMP_ENN 0 sky130_fd_pr__nfet_g5v0d10v5 " + cand.ntail_geom(rev),
        "XM_CLP CL_CMP PBR VIN VIN sky130_fd_pr__pfet_g5v0d10v5 " + cand.PFET_GEOM["L1W10"],
        ".control", "save all",
        "dc VVIN 3.63 1.5 -0.01",
        "wrdata headroom.dat i(vvin) i(vtlm) i(vclm) v(pbr) v(nbr) v(nvr)",
        "quit", ".endc", ".end", ""])


def main(argv):
    mode, run = argv[1], Path(argv[2])
    if run.exists():
        sys.exit(f"{run} exists: evidence is append-only")
    run.mkdir(parents=True)
    (run / ".spiceinit").write_text((SIM / "spiceinit").read_text())
    pdk = cr.resolve_pdk(cr.load_pin())
    if mode == "vref-vi":
        deck = vref_vi_deck(str(pdk.lib_file))
    elif mode.startswith("headroom"):
        deck = headroom_deck(str(pdk.lib_file), int(mode.split("-rev")[1]) if "-rev" in mode else 0)
    else:
        raise SystemExit(__doc__)
    (run / "deck.spice").write_text(deck)
    log, el, rc = pc.run_ngspice_deck(run)
    rec = {"mode": mode, "ngspice_exit": rc, "elapsed_s": round(el, 2),
           "solver_diagnostic": cr.detect_solver_diagnostic(log),
           "deck_sha256": pc.sha(deck.encode()), "source_commit": pc.git_provenance(),
           "tools": cr.tool_versions(), "pdk_commit": pdk.installed_commit}
    (run / "result.json").write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec))


if __name__ == "__main__":
    main(sys.argv)
