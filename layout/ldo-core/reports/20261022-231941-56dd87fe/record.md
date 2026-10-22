# LDO core LVS record: 20261022-231941-56dd87fe

`klt extract` + `klt lvs` against the LDO core layout (issue #17's driver), comparing `layout/ldo-core/reports/20261022-231908-56dd87fe/ldo_core.gds` against a reference netlist mechanically translated from `design/ldo_3v3in_1v8out.sch`'s own xschem netlist by `layout/bin/gen-ldo-reference-netlist.py`. Both sides are derived from that one netlist -- the layout's device set comes from it too (`layout/bin/gen-ldo-blocks.py`, issue #33) -- so neither side can silently describe a different circuit than the schematic.

## Overall verdict: MISMATCH -- not LVS-clean

- [ ] `klt lvs` reports `status: match`

**This does not satisfy issue #17's acceptance criteria (`status: match`).** Filed as a real, committed negative result (`CLAUDE.md`'s "Verification is the product": append-only evidence, not a silently-dropped attempt). The findings `klt lvs` actually reported are summarised below -- read `lvs.json` for the full list.

## Flow

1. `xschem -n -q -x -s -o ... design/ldo_3v3in_1v8out.sch` -- headless netlist, same invocation `design/README.md`'s "Validating this schematic" section documents.
2. `layout/bin/gen-ldo-reference-netlist.py` translates that netlist into an LVS reference (MOS model names -> `klt extract`'s generic `nfet`/`pfet` classes, `W_total = W * mult`; each resistor's expected `R`/`A`/`P` computed from its drawn geometry using `klt`'s own deck constants; capacitors dropped -- the schematic's MiM capacitors are not drawn and are dropped from the reference on both sides -- `klt gen` has no capacitor/MiM generator at this repo's pinned commit (https://github.com/2AMLogic/klayout-tools/issues/1117)).
3. `klt extract ldo_core.gds --deck sky130 --top ldo_core --pins ...` (the schematic's own four ports; every other labelled net stays an internal node).
4. `klt lvs` (extracted layout vs. the translated reference), with `options.combine_devices`, `layout.declared_pins` and `reference.device_bulk` -- see `run-ldo-lvs-flow.sh`'s header for what each one reconciles and why. Every one of them is disclosed as its own `warning` entry in `lvs.json`.

## Results

| Stage | Status | Detail |
| --- | --- | --- |
| Extract | extracted | device_count=102, net_count=28, pin_count=4, device_counts={'nfet': 19, 'pfet': 78, 'res_high_po': 1, 'res_xhigh_po': 4} |
| LVS | mismatch | mismatch_count=6, category_counts={'device.bulk_reconciled': 2, 'device.geometry_not_compared': 2, 'device.property': 1, 'topology': 1}, nets(layout/reference/matched)={'layout': 27, 'reference': 27, 'matched': 24}, devices(layout/reference/matched)={'layout': 51, 'reference': 51, 'matched': 50}, pins(layout/reference/matched)={'layout': 4, 'reference': 4, 'matched': 4} |

## Findings (`severity: error`)

| Category | Side | Description | Device / net |
| --- | --- | --- | --- |
| `device.property` | both | matched device parameter 'r' differs | `{'layout': '\\$98', 'reference': '_BIAS', 'class': 'res_high_po'}` |

Error findings by category: `{'device.property': 1}`.

## Disclosed warnings (non-blocking)

- `device.bulk_reconciled` -- request.reference.device_bulk reconciled reference device class 'RES_HIGH_PO' with the layout side: a 'W' terminal was added to the reference class (layout: ['A', 'B', 'W'], reference was: ['A', 'B']) and tied to reference net '0' on 1 device instance(s), an existing reference net -- that terminal's connectivity was asserted by the request, not read from the reference netlist, so this dimension of the compare is not independently verified (see docs/cli/lvs.md, 'device.bulk_reconciled')
- `device.bulk_reconciled` -- request.reference.device_bulk reconciled reference device class 'RES_XHIGH_PO' with the layout side: a 'W' terminal was added to the reference class (layout: ['A', 'B', 'W'], reference was: ['A', 'B']) and tied to reference net '0' on 3 device instance(s), an existing reference net -- that terminal's connectivity was asserted by the request, not read from the reference netlist, so this dimension of the compare is not independently verified (see docs/cli/lvs.md, 'device.bulk_reconciled')
- `device.geometry_not_compared` -- device class 'res_high_po' is a resistor class, whose ['A', 'L', 'P', 'W'] parameter(s) KLayout declares *secondary*: kdb.NetlistComparer compares primary parameters only, so none of them took part in this compare and each is NOT verified -- this resistor's geometry could differ between the two sides by any amount and this run would still report 'match'. The compared parameter(s) were ['R']. Name them in options.compare_parameters to compare them (see docs/cli/lvs.md, 'device.geometry_not_compared')
- `device.geometry_not_compared` -- device class 'res_xhigh_po' is a resistor class, whose ['A', 'L', 'P', 'W'] parameter(s) KLayout declares *secondary*: kdb.NetlistComparer compares primary parameters only, so none of them took part in this compare and each is NOT verified -- this resistor's geometry could differ between the two sides by any amount and this run would still report 'match'. The compared parameter(s) were ['R']. Name them in options.compare_parameters to compare them (see docs/cli/lvs.md, 'device.geometry_not_compared')
- `topology` -- device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch: 'pnp'

A `warning` entry never changes `status`; each one records a dimension this compare could not verify structurally, or a request-level reconciliation it was given. Read them alongside the verdict, not instead of it.

## Provenance

- Record ID: `20261022-231941-56dd87fe`
- `klt` version: `klt 0.7.1.dev2457+gdc136150a49e` (pinned commit, see `layout/requirements.txt`)
- KLayout engine version: `0.30.12`
- PDK: `sky130A`, `open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`
- PDK pin cross-check: compare `version` above against `sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself enforce the pin, consistent with `layout/README.md`'s trivial-cell flow.
- Schematic freshness: `design/ldo_3v3in_1v8out.sch` as of commit `a09aa83f`.
- Layout freshness: `layout/ldo-core/` as of commit `f604ae04`; GDS taken from layout record `20261022-231908-56dd87fe`.
- Repo state: `56dd87fe0ae69ccba559098a3b46a82b1023c333` on `feature/issue-162` (dirty)

## Links

- [`ldo_core.gds`](ldo_core.gds) -- copy of the layout record's composed GDS
- [`xschem_out/ldo_3v3in_1v8out.spice`](xschem_out/ldo_3v3in_1v8out.spice) -- headless schematic netlist
- [`reference.spice`](reference.spice) -- translated LVS reference
- [`extract.json`](extract.json), [`ldo_core.extract.spice`](ldo_core.extract.spice)
- [`lvs.request.json`](lvs.request.json), [`lvs.json`](lvs.json)
- [`report.md`](report.md) -- `klt report --format github-summary` rendering of `lvs.json`

