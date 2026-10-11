#!/usr/bin/env python3
"""Replay one committed #339 deck VERBATIM (byte-identical copy) with this host's
ngspice, as a tool-version anchor: separates ngspice/xschem drift from any DUT or
candidate effect. One ngspice -b per call; #339's own analyze_tran gates.

usage: replay339.py <probe-name e.g. probe0> <run-id>
"""
from __future__ import annotations

import gzip
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parents[2]
sys.path.insert(0, str(SIM / "bin"))
sys.path.insert(0, str(HERE))
import _probe_common as pc  # noqa: E402
import analyze as an  # noqa: E402

cr = pc.load_corner_run()
D339 = HERE.parent / "issue-339"


def main(argv):
    name, rid = argv[1], argv[2]
    run = HERE / "runs" / rid
    if run.exists():
        sys.exit(f"{run} exists: evidence is append-only")
    run.mkdir(parents=True)
    src = D339 / f"{name}.deck.spice"
    shutil.copyfile(src, run / "deck.spice")
    shutil.copyfile(D339 / f"{name}.dat.columns.json", run / f"{name}.dat.columns.json")
    (run / ".spiceinit").write_text((SIM / "spiceinit").read_text())
    log, el, rc = pc.run_ngspice_deck(run)
    dat = run / f"{name}.dat"
    names = json.loads((run / f"{name}.dat.columns.json").read_text())
    scale, cols = an.a339.parse_wrdata(dat.read_text(), len(names)) if dat.is_file() else (None, "no data")
    res = (an.a339.analyze_tran(scale, dict(zip(names, cols)), log) if scale is not None
           else {"valid": False, "reasons": [f"malformed data: {cols}"], "dropout_v": None})
    ref = json.loads((D339 / f"{name}.result.json").read_text())
    rec = {"run_id": rid, "issue": 357, "replay_of": f"issue-339/{name}.deck.spice",
           "deck_sha256": pc.sha(src.read_bytes()), "ngspice_exit": rc, "elapsed_s": round(el, 2),
           "solver_diagnostic": cr.detect_solver_diagnostic(log),
           "valid": res["valid"], "reasons": res["reasons"], "dropout_v": res["dropout_v"],
           "dropout_v_339_recorded": ref["dropout_v"],
           "delta_vs_339_v": (res["dropout_v"] - ref["dropout_v"]) if res["dropout_v"] is not None else None,
           "data_sha256": pc.sha(dat.read_bytes()) if dat.is_file() else None,
           "data_sha256_339_recorded": json.loads((D339 / "provenance.json").read_text())["sha256_raw_files"].get(f"{name}.dat"),
           "source_commit": pc.git_provenance(), "tools": cr.tool_versions()}
    if dat.is_file():
        with open(dat, "rb") as f, gzip.open(str(dat) + ".gz", "wb", compresslevel=9) as g:
            shutil.copyfileobj(f, g)
        dat.unlink()
    (run / "result.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: rec[k] for k in ("run_id", "valid", "reasons", "dropout_v", "dropout_v_339_recorded",
                                          "delta_vs_339_v", "elapsed_s")}))


if __name__ == "__main__":
    main(sys.argv)
