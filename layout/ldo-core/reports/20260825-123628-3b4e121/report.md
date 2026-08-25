## LVS Report: ldo_core.gds vs reference.spice
**Status:** ✅ match
- Top: ldo_core
- Engine: klayout

| Category | Severity | Side | Description |
| --- | --- | --- | --- |
| device.bulk_reconciled | warning | reference | request.reference.device_bulk reconciled reference device class 'RES_HIGH_PO' with the layout side: a 'W' terminal was added to the reference class (layout: ['A', 'B', 'W'], reference was: ['A', 'B']) and tied to reference net '0' on 1 device instance(s), an existing reference net -- that terminal's connectivity was asserted by the request, not read from the reference netlist, so this dimension of the compare is not independently verified (see docs/cli/lvs.md, 'device.bulk_reconciled') |
| device.bulk_reconciled | warning | reference | request.reference.device_bulk reconciled reference device class 'RES_XHIGH_PO' with the layout side: a 'W' terminal was added to the reference class (layout: ['A', 'B', 'W'], reference was: ['A', 'B']) and tied to reference net '0' on 3 device instance(s), an existing reference net -- that terminal's connectivity was asserted by the request, not read from the reference netlist, so this dimension of the compare is not independently verified (see docs/cli/lvs.md, 'device.bulk_reconciled') |
| topology | warning | layout | device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch |
