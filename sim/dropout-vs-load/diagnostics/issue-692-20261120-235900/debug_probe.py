#!/usr/bin/env python3
"""Issue #692 single-corner debug probe (LOCAL, one ngspice per call).

For the two iq-bench corners the campaign found in a non-regulating state
(ss / 125 C / 3.30 V full-load, ff / 27 C / 2.97 V no-load): run the iq
manifest deck verbatim for the candidate (or baseline), plus a wrdata of the
loop nodes, so the state can be diagnosed from the trace. One corner per
invocation; no grid, never batch evidence -- the recorded evidence is the
campaign's batch runs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parents[2]
sys.path.insert(0, str(SIM / "bin"))
sys.path.insert(0, str(HERE))
import _probe_common as pc  # noqa: E402

cr = pc.load_corner_run()
import candidate as cand  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["base", "cand"], required=True)
    ap.add_argument("--process", required=True)
    ap.add_argument("--temp", type=float, required=True)
    ap.add_argument("--supply", type=float, required=True)
    ap.add_argument("--rev", type=int, default=1)
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args(argv)
    run = HERE / "runs" / a.run_id
    if run.exists():
        raise SystemExit(f"{run} exists")
    run.mkdir(parents=True)
    pdk = cr.resolve_pdk(cr.load_pin())
    exp = cr.load_experiment(SIM / "iq")
    import tempfile
    with tempfile.TemporaryDirectory(prefix="i692-dbg-") as nl:
        net = cr.netlist_with_xschem(exp.schematic, Path(nl), pdk)
        raw = "\n".join(cr.netlist_body(net)) + "\n"
    if a.variant == "cand":
        edited, _notes = cand.apply_candidate(raw, a.rev)
        problems = cand.check_candidate(raw, edited)
        if problems:
            raise SystemExit("; ".join(problems))
    else:
        edited = raw
    body = edited.splitlines()
    corner = cr.Corner(a.process, a.temp, a.supply)
    deck = cr.build_deck(exp, pdk, corner, body)
    i = deck.index(".control")
    ctl = deck[i:]
    nodes = ["v(vin)", "v(vout)", "v(xldo.ea_out)", "v(xldo.ss)", "v(xldo.ntail)",
             "v(xldo.nd1)", "v(xldo.nd2)", "v(xldo.pbr)", "v(xldo.cl_cmp)",
             "@m.xldo.xm_pass.msky130_fd_pr__pfet_g5v0d10v5[id]"]
    ctl = ctl.replace("alter iload = 50m\n",
                      "wrdata data_no.dat " + " ".join(nodes) + "\nalter iload = 50m\n", 1)
    ctl = ctl.replace("quit\n", "wrdata data.dat " + " ".join(nodes) + "\nquit\n", 1)
    deck = deck[:i] + ctl
    (run / "deck.spice").write_text(deck)
    (run / ".spiceinit").write_text((SIM / "spiceinit").read_text())
    log, elapsed, rcode = pc.run_ngspice_deck(run, timeout=1800)
    got = {}
    for n in ("vout_no_load", "iq_no_load_raw", "vout_full_load", "iq_full_load_raw"):
        m = re.search(rf"^{n}\s*=\s*(-?[0-9.]+(?:[eE][-+]?[0-9]+)?)", log, re.M)
        got[n] = float(m.group(1)) if m else None
    rec = {"run_id": a.run_id, "variant": a.variant, "rev": a.rev if a.variant == "cand" else None,
           "corner": [a.process, a.temp, a.supply], "ngspice_exit": rcode,
           "elapsed_s": round(elapsed, 1), "solver_diagnostic": cr.detect_solver_diagnostic(log),
           "cards": got, "source_commit": pc.git_provenance(SIM.parent)}
    (run / "result.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    print(json.dumps(rec))


if __name__ == "__main__":
    main()
