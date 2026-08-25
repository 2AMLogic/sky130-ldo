#!/usr/bin/env python3
"""Regenerate this experiment's `klt pex` testbench pair (issue #20).

`klt pex` has no `--pins` flag on its own internal `klt extract` call (unlike
`layout/bin/run-ldo-lvs-flow.sh`'s explicit `--pins VOUT,VREF,EN,VIN`), so its
extraction promotes *every* labelled net in the layout to a top-level pin --
28 of them for `ldo_core`, not just the schematic's own 4 ports. Per
docs/cli/pex.md's DUT-`.include`-swap convention, the schematic-side DUT this
experiment's testbench `.include`s must declare a `.SUBCKT ldo_core <pins>`
header with the *same* pin set, in the *same* order, as whatever `klt pex`'s
own extraction actually produces -- otherwise the `X` instantiation the
testbench reuses byte-identically on both legs would wire the two sides'
nodes differently.

This script:

1. Netlists `design/ldo_3v3in_1v8out.sch` headlessly (the same invocation
   `layout/bin/run-ldo-lvs-flow.sh` and `design/README.md`'s "Validating this
   schematic" section document) to get the **real**, PDK-bound schematic
   netlist (sky130_fd_pr__nfet_g5v0d10v5/pfet_g5v0d10v5 devices, bare
   micrometre-literal geometry) -- freshly derived from the current
   schematic, not a possibly-stale committed report. See README.md's "Why a
   fresh xschem netlist, not the committed LVS reference" for why this
   experiment does not reuse `layout/bin/gen-ldo-reference-netlist.py`'s
   generic-device-class translation the way issue #17's LVS flow does.
2. Re-derives the current 28-pin extraction interface directly (a throwaway
   `--parasitics --pdk sky130A` extraction against the same GDS `klt pex`
   will extract from, deck `sky130` -- see README.md for why `--pdk` is used
   here despite its own disclosed limitation).
3. Emits `testbench/ldo_core_schematic_dut.spice` (the xschem netlist's
   device body, stripped of its own `.end` card, rewrapped with a `.SUBCKT
   ldo_core <28 pins>` header) and `testbench/tb_pex_post_layout.spice` (the
   `klt sim`/`klt pex` testbench: sources, an output network, and an `X`
   instantiation using that same 28-pin list -- no `.model` cards needed,
   `corners.process` resolves the real sky130 `.lib`).

Both output files are committed, generated artifacts (like
layout/ldo-core/reports/*/reference.spice) -- regenerate rather than
hand-edit after a layout/schematic change.

Usage:
    sim/pex-post-layout/bin/gen-pex-testbench.py \
        --klt <klt binary implementing `pex`> \
        --gds layout/ldo-core/reports/<LATEST-LVS>/ldo_core.gds \
        --repo-root . \
        --outdir sim/pex-post-layout/testbench
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SUBCKT_RE = re.compile(r"^\.SUBCKT\s+(\S+)\s+(.*)$", re.IGNORECASE)
CONT_RE = re.compile(r"^\+\s*(.*)$")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(f"gen-pex-testbench.py: command failed (exit {result.returncode}): {' '.join(cmd)}")
    return result


def parse_subckt_pins(netlist_text: str, subckt_name: str) -> list[str]:
    lines = netlist_text.splitlines()
    pins: list[str] | None = None
    for i, line in enumerate(lines):
        m = SUBCKT_RE.match(line.strip())
        if m and m.group(1).lower() == subckt_name.lower():
            tokens = m.group(2).split()
            j = i + 1
            while j < len(lines):
                cm = CONT_RE.match(lines[j])
                if not cm:
                    break
                tokens.extend(cm.group(1).split())
                j += 1
            pins = tokens
            break
    if pins is None:
        raise SystemExit(f"gen-pex-testbench.py: no .SUBCKT {subckt_name} found")
    return pins


def schematic_device_body(schem_netlist_text: str) -> str:
    """Strip the xschem-emitted `.end` card, keep everything else verbatim.

    xschem's own `**.subckt`/`**.ends`/`*.ipin`/`*.opin` lines are ordinary
    SPICE comments (leading `*`) -- inert, left in place for provenance. Only
    the trailing `.end` is an actual directive, and the netlist convention
    this DUT file must follow (docs/cli/sim.md's "Netlist convention: a
    circuit body, not a full deck") forbids a `.end` card of its own.
    """
    lines = [
        line
        for line in schem_netlist_text.splitlines()
        if line.strip().upper() != ".END"
    ]
    return "\n".join(lines)


def wrap_pins(pins: list[str], indent: str = "+ ", width: int = 78) -> str:
    out_lines: list[str] = []
    cur = ".SUBCKT ldo_core"
    for p in pins:
        candidate = f"{cur} {p}"
        if len(candidate) > width and cur != ".SUBCKT ldo_core":
            out_lines.append(cur)
            cur = f"{indent}{p}"
        else:
            cur = candidate
    out_lines.append(cur)
    return "\n".join(out_lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--klt", required=True, help="path to a klt binary implementing `klt pex` (Epic #709 Phase 1a)")
    ap.add_argument("--gds", required=True, help="path to the landed ldo_core.gds")
    ap.add_argument("--repo-root", required=True, help="repository root (containing design/, layout/, sim/)")
    ap.add_argument("--outdir", required=True, help="directory to write the DUT + testbench into")
    ap.add_argument("--deck", default="sky130")
    ap.add_argument("--top", default="ldo_core")
    ap.add_argument("--pdk", default="sky130A")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    gds = Path(args.gds).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    schematic = repo_root / "design" / "ldo_3v3in_1v8out.sch"
    xschemrc = repo_root / "sim" / "xschemrc"

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # --- 1. Netlist the current schematic headlessly (same invocation
        #        run-ldo-lvs-flow.sh / design/README.md document) -----------
        xschem_out = tmp / "xschem_out"
        xschem_out.mkdir()
        run([
            "xschem", "-n", "-q", "-x", "-s", "-o", str(xschem_out),
            "--rcfile", str(xschemrc), str(schematic),
        ])
        schem_netlist = xschem_out / "ldo_3v3in_1v8out.spice"
        if not schem_netlist.is_file():
            raise SystemExit(f"gen-pex-testbench.py: expected {schem_netlist} after xschem netlisting")
        schem_netlist_text = schem_netlist.read_text()

        # --- 2. Probe the current pin-promotion order from a throwaway,
        #        --parasitics --pdk extraction against the landed GDS -------
        probe_out = tmp / "pin_probe.spice"
        result = run([
            args.klt, "extract", str(gds),
            "--deck", args.deck, "--top", args.top, "--parasitics",
            "--pdk", args.pdk,
            "-o", str(probe_out), "--format", "json",
        ])
        probe_text = probe_out.read_text()

    pins = parse_subckt_pins(probe_text, args.top)
    envelope = json.loads(result.stdout)
    pin_count_reported = envelope.get("pin_count")
    if pin_count_reported is not None and pin_count_reported != len(pins):
        raise SystemExit(
            f"gen-pex-testbench.py: parsed {len(pins)} pins but extract.json reports pin_count={pin_count_reported}"
        )

    device_body = schematic_device_body(schem_netlist_text)
    pin_header = wrap_pins(pins)
    pin_line_for_x = " ".join(pins)

    dut_path = outdir / "ldo_core_schematic_dut.spice"
    dut_path.write_text(
        "\n".join(
            [
                "* Schematic-equivalent DUT for `klt pex` post-layout verification",
                "* (issue #20). Regenerated by sim/pex-post-layout/bin/gen-pex-testbench.py",
                "* -- do not hand-edit.",
                "*",
                "* Device body: a fresh headless xschem netlisting of",
                "* design/ldo_3v3in_1v8out.sch (`xschem -n -q -x -s ...`, the same",
                "* invocation layout/bin/run-ldo-lvs-flow.sh and design/README.md use),",
                "* unchanged except its own trailing `.end` card is dropped -- this file is",
                "* a circuit body `.include`d by a testbench, not a standalone deck (see",
                "* docs/cli/sim.md's netlist convention). Uses the design's real",
                "* sky130_fd_pr__nfet_g5v0d10v5/pfet_g5v0d10v5 (5V-tolerant HV) devices,",
                "* bare-micrometre-literal geometry -- relies on the testbench's `.lib`",
                "* corner section pulling in models_global.spice's `.option scale=1.0u`",
                "* (same convention this repo's other sim/ testbenches rely on).",
                "*",
                "* Pin list: widened from the schematic's own 4-pin interface (VOUT VREF EN",
                "* VIN) to all 28 top-level nets `klt pex`'s own internal `klt extract`",
                "* call promotes to pins (it has no --pins flag) -- re-derived from a live",
                f"* `klt extract --deck {args.deck} --top {args.top} --parasitics --pdk",
                f"* {args.pdk}` probe run against the same landed GDS, so this header always",
                "* matches whatever `klt pex` itself extracts. See",
                "* sim/pex-post-layout/README.md.",
                pin_header,
                device_body,
                f".ENDS {args.top}",
                "",
            ]
        )
    )

    tb_path = outdir / "tb_pex_post_layout.spice"
    tb_path.write_text(
        "\n".join(
            [
                "* klt pex testbench for the LDO core post-layout verification (issue #20).",
                "* Regenerated by sim/pex-post-layout/bin/gen-pex-testbench.py -- do not",
                "* hand-edit.",
                "*",
                "* `.include`s the schematic-equivalent DUT (ldo_core_schematic_dut.spice,",
                "* same file); `klt pex` re-points this one line at its own freshly",
                "* `--parasitics --pdk sky130A`-extracted netlist for the extracted-side",
                "* leg, reusing every source/analysis/measurement below byte-identically on",
                "* both legs. No `.model`/`.lib` line is needed here -- the klt-sim request's",
                "* own `corners.process` + `models.lib` fields resolve sky130's combined",
                "* `.lib` (which both this file's `sky130_fd_pr__*_g5v0d10v5` devices and the",
                "* extracted side's PDK-bound X-cards read from) per-corner. See",
                "* sim/pex-post-layout/README.md's \"models.lib\" note for why the request",
                "* uses `models.lib` alone rather than pairing it with `models.pdk`.",
                "*",
                "* Runs `klt pex` with `--pdk sky130A` (unlike a from-scratch pex testbench",
                "* might default to): the bare, non-PDK `klt extract` device-class output",
                "* (`nfet`/`pfet`/`res_high_po`/`res_xhigh_po`) is NOT directly",
                "* ngspice-simulatable for this layout -- sky130's `res_high_po`/",
                "* `res_xhigh_po` drawn-resistor classes always carry a 3rd (bulk/tap)",
                "* terminal (`R$n a b 0 <value> res_high_po`), which ngspice's native 2-node",
                "* `R` element rejects outright (\"unknown parameter (res_high_po)\") --",
                "* confirmed by direct trial, not assumed; not already tracked upstream as",
                "* of 2026-08-18 (see sim/pex-post-layout/README.md). `--pdk` sidesteps it",
                "* by writing every device (MOS and resistor alike) as a real PDK `X`",
                "* subcircuit call, which supports arbitrary pin counts.",
                "*",
                "* `--pdk`'s own disclosed cost: `klt extract --pdk`'s MOS model-binding",
                "* table is hardcoded to sky130's 01v8 core-device flavor",
                "* (src/klayout_tools/pdk_models.py), while this design's schematic (this",
                "* DUT file, above) uses the 5V-tolerant g5v0d10v5 flavor throughout -- a",
                "* real, tracked upstream gap (klayout-tools#1369, sky130-specific; open",
                "* as of 2026-08-24 -- supersedes the now-closed #1089, whose own follow-on",
                "* fix (#1111) landed gf180mcu-only, not sky130). The extracted-side leg's",
                "* MOS devices are therefore",
                "* systematically the wrong flavor; every delta[] row this experiment",
                "* records conflates that model-substitution error with genuine post-layout",
                "* parasitics and MUST NOT be read as a clean parasitics-only fidelity",
                "* measurement or as spec-compliance evidence. See",
                "* sim/pex-post-layout/README.md for the full caveat.",
                '.include "ldo_core_schematic_dut.spice"',
                "",
                ".param vvin=3.3",
                ".param iload=1m",
                "",
                "Vvin   VIN   0 DC {vvin}",
                "Ven    EN    0 DC {vvin}",
                "Vvref  VREF  0 DC 1.2",
                "Cout   VOUT  VESR 1u",
                "Resr   VESR  0    10m",
                "Iload  VOUT  0    DC {iload}",
                "",
                f"Xldo {pin_line_for_x} {args.top}",
                "",
            ]
        )
    )

    print(f"gen-pex-testbench.py: wrote {dut_path}")
    print(f"gen-pex-testbench.py: wrote {tb_path}")
    print(f"gen-pex-testbench.py: pin_count={len(pins)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
