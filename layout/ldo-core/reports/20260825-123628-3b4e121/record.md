# LDO core LVS record: 20260825-123628-3b4e121

`klt extract` + `klt lvs` against the LDO core layout (issue #17's driver), comparing `layout/ldo-core/reports/20260825-123551-3b4e121/ldo_core.gds` against a reference netlist mechanically translated from `design/ldo_3v3in_1v8out.sch`'s own xschem netlist by `layout/bin/gen-ldo-reference-netlist.py`. Both sides are derived from that one netlist -- the layout's device set comes from it too (`layout/bin/gen-ldo-blocks.py`, issue #33) -- so neither side can silently describe a different circuit than the schematic.

## Overall verdict: MATCH

- [x] `klt lvs` reports `status: match`

## Flow

1. `xschem -n -q -x -s -o ... design/ldo_3v3in_1v8out.sch` -- headless netlist, same invocation `design/README.md`'s "Validating this schematic" section documents.
2. `layout/bin/gen-ldo-reference-netlist.py` translates that netlist into an LVS reference (MOS model names -> `klt extract`'s generic `nfet`/`pfet` classes, `W_total = W * mult`; each resistor's expected `R`/`A`/`P` computed from its drawn geometry using `klt`'s own deck constants; capacitors dropped -- the schematic's MiM capacitors are not drawn and are dropped from the reference on both sides -- `klt gen` has no capacitor/MiM generator at this repo's pinned commit (https://github.com/2AMLogic/klayout-tools/issues/1117)).
3. `klt extract ldo_core.gds --deck sky130 --top ldo_core --pins ...` (the schematic's own four ports; every other labelled net stays an internal node).
4. `klt lvs` (extracted layout vs. the translated reference), with `options.combine_devices`, `layout.declared_pins` and `reference.device_bulk` -- see `run-ldo-lvs-flow.sh`'s header for what each one reconciles and why. Every one of them is disclosed as its own `warning` entry in `lvs.json`.

## Results

| Stage | Status | Detail |
| --- | --- | --- |
| Extract | extracted | device_count=72, net_count=28, pin_count=4, device_counts={'nfet': 18, 'pfet': 49, 'res_high_po': 1, 'res_xhigh_po': 4} |
| LVS | match | mismatch_count=3, category_counts={'device.bulk_reconciled': 2, 'topology': 1}, nets(layout/reference/matched)={'layout': 27, 'reference': 27, 'matched': 27}, devices(layout/reference/matched)={'layout': 47, 'reference': 47, 'matched': 47}, pins(layout/reference/matched)={'layout': 4, 'reference': 4, 'matched': 4} |

## Disclosed warnings (non-blocking)

- `device.bulk_reconciled` -- request.reference.device_bulk reconciled reference device class 'RES_HIGH_PO' with the layout side: a 'W' terminal was added to the reference class (layout: ['A', 'B', 'W'], reference was: ['A', 'B']) and tied to reference net '0' on 1 device instance(s), an existing reference net -- that terminal's connectivity was asserted by the request, not read from the reference netlist, so this dimension of the compare is not independently verified (see docs/cli/lvs.md, 'device.bulk_reconciled')
- `device.bulk_reconciled` -- request.reference.device_bulk reconciled reference device class 'RES_XHIGH_PO' with the layout side: a 'W' terminal was added to the reference class (layout: ['A', 'B', 'W'], reference was: ['A', 'B']) and tied to reference net '0' on 3 device instance(s), an existing reference net -- that terminal's connectivity was asserted by the request, not read from the reference netlist, so this dimension of the compare is not independently verified (see docs/cli/lvs.md, 'device.bulk_reconciled')
- `topology` -- device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch

A `warning` entry never changes `status`; each one records a dimension this compare could not verify structurally, or a request-level reconciliation it was given. Read them alongside the verdict, not instead of it.

## Provenance

- Record ID: `20260825-123628-3b4e121`
- `klt` version: `klt 0.2.0` (pinned commit, see `layout/requirements.txt`)
- KLayout engine version: `0.30.11`
- PDK: `sky130A`, `open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b`
- PDK pin cross-check: compare `version` above against `sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself enforce the pin, consistent with `layout/README.md`'s trivial-cell flow.
- Schematic freshness: `design/ldo_3v3in_1v8out.sch` as of commit `b53a8e7`.
- Layout freshness: `layout/ldo-core/` as of commit `2de5026`; GDS taken from layout record `20260825-123551-3b4e121`.
- Repo state: `3b4e121e246a33b9387593e4fd5cc6f668ee4958` on `feature/issue-89` (dirty)

## Links

- [`ldo_core.gds`](ldo_core.gds) -- copy of the layout record's composed GDS
- [`xschem_out/ldo_3v3in_1v8out.spice`](xschem_out/ldo_3v3in_1v8out.spice) -- headless schematic netlist
- [`reference.spice`](reference.spice) -- translated LVS reference
- [`extract.json`](extract.json), [`ldo_core.extract.spice`](ldo_core.extract.spice)
- [`lvs.request.json`](lvs.request.json), [`lvs.json`](lvs.json)
- [`report.md`](report.md) -- `klt report --format github-summary` rendering of `lvs.json`

