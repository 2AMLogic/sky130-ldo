#!/usr/bin/env python3
"""Bias-generator-only PVT grid for the DR-013 bias re-topology study (issue #467).

Compares the bias generator of record (`R_BIAS` = res_high_po W=0.42 L=1500) with
the DR-013 candidate (`R_BIAS` = res_xhigh_po W=0.42 L=211) across the ratified
PVT matrix (5 process x 3 temperature x 3 supply) plus the resistor-only skew
corners ll/hh. Every other bias device is copied verbatim from
`design/ldo_3v3in_1v8out.sch`. The downstream consumer is represented by one
`M_TAIL` copy (the error-amplifier tail, the largest BIASP mirror) sinking into
a fixed 1.0 V source.

The grid is expressed as `klt sim` requests (one per design x supply) and goes
to the batch fleet; there is NO local fallback. Output is a NEW append-only
record directory `sim/bias-retopo/<record-id>/` (request files, raw responses,
`summary.json`, `record.md`).

This is a bias-generator screening grid. It is NOT a PSRR / stability / Iq
record of the full LDO (those are `sim/psrr-dc`, `sim/loop-gain`, `sim/iq`).

The request / submit core it shares with the other batch-fleet campaign drivers
lives in `sim/bin/_fleet_campaign.py` (issue #574; this driver was folded onto it
by #586). Only this campaign's deck, grid, grading and record rendering are here.
Unlike its siblings this bench builds its deck by hand instead of netlisting a
testbench schematic, so it uses the shared core's request and submit halves and
not `fc.netlist()` / `fc.deck()`.

Usage:
    python3 sim/bin/bias-retopo-grid.py [--record-id ID] [--workers 2]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "sim" / "bin"))
import _fleet_campaign as fc  # noqa: E402

SUPPLIES = [2.97, 3.30, 3.63]
# A deliberate superset of `fc.PROCESS`: ll/hh are the resistor-only skew corners
# this bench adds (they move R_BIAS, which is what DR-013 changes). `pdk.json`
# declares them in `process_corners`; the MOS-corner campaigns do not run them.
PROCESS = [*fc.PROCESS, "ll", "hh"]
TEMPS = [-40.0, 27.0, 125.0]
DESIGNS = {
    "record": ("sky130_fd_pr__res_high_po", 1500),
    "dr013": ("sky130_fd_pr__res_xhigh_po", 211),
}
NFET = "sky130_fd_pr__nfet_g5v0d10v5"
PFET = "sky130_fd_pr__pfet_g5v0d10v5"
MEAS = [
    ("v_nb", "v(nb)", "V"),
    ("v_biasp", "v(biasp)", "V"),
    ("i_tail_ua", "1e6*i(vtail)", "uA"),
    ("i_bias_pair_ua", "1e6*(-i(vvin)-i(vtail))", "uA"),
]


def netlist(res: str, length: int, vsup: float) -> str:
    return f""".param vsup={vsup}
.option wnflag=1
VVIN VIN 0 'vsup'
.save i(vvin)
XR_BIAS VIN NB 0 {res} W=0.42 L={length} mult=1 m=1
XM_BIASN1 NB NB BIAS_ENN 0 {NFET} L=1 W=4 nf=1 mult=1 m=1
XM_ENN BIAS_ENN VIN 0 0 {NFET} L=0.5 W=10 nf=1 mult=1 m=1
XM_BIASN2 BIASP NB BIAS_ENN 0 {NFET} L=1 W=4 nf=1 mult=1 m=1
XM_BIASP1 BIASP BIASP VIN VIN {PFET} L=1 W=10 nf=2 mult=1 m=1
XM_TAIL EA_TAIL BIASP VIN VIN {PFET} L=2 W=40 nf=8 mult=1 m=1
VTAIL EA_TAIL 0 1.0
.save i(vtail)
.end
"""


def request(path: Path, pdk: dict) -> dict:
    """This bench's `klt sim` batch request, built on the shared core.

    `order=PROCESS` is the only departure from the sibling drivers: the shared
    core tabulates process sections in the ordering it is given, and this grid's
    ordering is `fc.PROCESS` plus ll/hh. The emitted JSON is byte-identical to
    the one the committed `20261029-bias-grid-467/requests/` tree holds, which
    `sim/tests/test_bias_retopo_grid_586.py` pins.
    """
    return fc.base_request(
        path,
        pdk,
        [(p, t) for p in PROCESS for t in TEMPS],
        {"kind": "op", "args": ""},
        [{"name": f"meas_{n}", "expr": e, "unit": u} for n, e, u in MEAS],
        order=PROCESS,
    )


def row(key: str, meta: dict, corner: dict, job: str | None) -> dict:
    """One `summary.json` row, in the shape this record family already uses.

    `fc.corner_base()` additionally carries `key`; this record family's committed
    rows do not, and `sim/` records are append-only evidence, so a re-run keeps
    emitting its own format (`_fleet_campaign.py`'s row-shaping note). Nothing is
    lost: `key` here is exactly `f"{design}-v{vsup:.2f}"`, both of which the row
    already carries.
    """
    base = fc.corner_base(key, meta, corner, job)
    del base["key"]
    vals = {x["name"].replace("meas_", ""): x["value"] for x in corner["measurements"]}
    return {**base, **vals}


def render(record_id: str, rows: list[dict], errors: list[dict]) -> str:
    """The A/B shift table. With no failed submits this is byte-for-byte the
    record the pre-#586 driver rendered; failed submits add named lines, because
    the shared core now reports a refusal and carries on instead of exiting."""
    lines = [
        f"# Bias-generator PVT grid: {record_id}",
        "",
        "Issue #467 / DR-013. `record` = res_high_po L=1500; `dr013` = res_xhigh_po L=211.",
        "Executed through `klt sim --backend batch` (no local fallback). Bias generator + one M_TAIL copy only.",
    ]
    if errors:
        lines.append("")
        lines += [
            f"- NOT ESTABLISHED: `{e['key']}` submit failed: {e['error'][:200]!r}"
            for e in errors
        ]
    lines += [
        "",
        "| process | T(C) | VIN | I_pair record (uA) | I_pair dr013 (uA) | shift % | I_tail record | I_tail dr013 | tail shift % |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    idx = {(r["design"], r["vsup"], r["process"], r["temp_c"]): r for r in rows}
    worst = 0.0
    worst_t = 0.0
    bad = 0
    for (d, v, p, t), r in sorted(idx.items(), key=lambda kv: (kv[0][2], kv[0][3], kv[0][1])):
        if d != "record":
            continue
        c = idx.get(("dr013", v, p, t))
        if c is None or r["status"] != "ok" and r["status"] != "passed" and r["i_bias_pair_ua"] is None:
            bad += 1
            continue
        try:
            s = 100 * (c["i_bias_pair_ua"] / r["i_bias_pair_ua"] - 1)
            st = 100 * (c["i_tail_ua"] / r["i_tail_ua"] - 1)
        except (TypeError, ZeroDivisionError):
            bad += 1
            continue
        worst = max(worst, abs(s))
        worst_t = max(worst_t, abs(st))
        lines.append(f"| {p} | {t:g} | {v:.2f} | {r['i_bias_pair_ua']:.4f} | {c['i_bias_pair_ua']:.4f} | {s:+.2f} | "
                     f"{r['i_tail_ua']:.4f} | {c['i_tail_ua']:.4f} | {st:+.2f} |")
    lines += ["", f"Worst |I_pair shift| = {worst:.2f} %; worst |I_tail shift| = {worst_t:.2f} %; unusable points = {bad}."]
    if errors:
        lines.append(
            f"Failed submits: {len(errors)} (reported above, NOT re-run locally; those points are not established)."
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record-id", default=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    out = REPO / "sim" / "bias-retopo" / args.record_id
    pdk, _pdk_root, env = fc.preamble(args.workers, out)
    (out / "requests").mkdir(parents=True)
    jobs = []  # (key, meta, request path)
    for name, (res, length) in DESIGNS.items():
        for vsup in SUPPLIES:
            key = f"{name}-v{vsup:.2f}"
            net = out / "requests" / f"{key}.spice"
            net.write_text(netlist(res, length, vsup))
            rp = out / "requests" / f"{key}.json"
            rp.write_text(json.dumps(request(net.resolve(), pdk), indent=2) + "\n")
            jobs.append((key, {"design": name, "vsup": vsup}, rp))

    rows, errors = [], []
    for k, m, resp, job in fc.submit_all(jobs, out, env, args.workers, errors):
        rows += [row(k, m, c, job) for c in resp["corners"]]
    (out / "summary.json").write_text(json.dumps(rows, indent=1) + "\n")
    text = render(args.record_id, rows, errors)
    (out / "record.md").write_text(text)
    print("\n".join(text.splitlines()[-3:]))
    print(f"record: {out}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
