# LDO core layout record: 20260825-123551-3b4e121

Placed and routed layout for the sky130 LDO's core regulation loop (issues #15/#33), generated from `design/ldo_3v3in_1v8out.sch`'s own headless xschem netlist: one `klt gen` block per active schematic device, placed by `klt gen-compose` and wired net-for-net by `layout/bin/gen-ldo-blocks.py`'s channel router. LVS against the schematic is its own driver and its own record -- see `layout/bin/run-ldo-lvs-flow.sh` and `reports/LATEST-LVS`.

## Overall verdict: PASS

- [x] DRC on the routed ldo-core layout is clean
- [x] Every schematic MOS/resistor device has exactly one placed `klt gen` block (48 devices)
- [x] Every schematic net the drawn devices touch is routed (28 nets, 211 terminals)

## Flow

1. `xschem -n -q -x -s ...` -- headless netlist of `design/ldo_3v3in_1v8out.sch`, the single source this layout's device set and connectivity are both derived from.
2. `layout/bin/gen-ldo-blocks.py` runs `klt gen mos_array` / `klt gen res_array` once per schematic device (43 MOS + 5 resistor blocks), computes an explicit single-row placement (see `layout/ldo-core/floorplan.md`), runs `klt gen-compose` to place them, then draws the inter-block routing and the two body ties.
3. `klt drc ldo_core.gds --deck sky130`

## Composed cell

- Cell name: `ldo_core`
- Block count: 48
- Placed bbox (um), before routing: {'x0': 0.0, 'y0': 0.0, 'x1': 2380.0799999999995, 'y1': 101.12}
- Device row: 2382.08um x 101.12um
- Routing channel: 28 met1 trunks on a 0.8um pitch below the row, 211 terminals landed

### Function groups (x extent within the row)

Blocks are ordered resistors -> every NMOS -> every PMOS, and inside each of those spans by function group, so a group that has both flavors (e.g. the error amplifier) occupies two x ranges rather than one contiguous block. The flavor split is load-bearing: the PMOS bodies are tied through one n-well drawn across the whole PMOS span, and `klt extract` decides a device's flavor by n-well containment.

| Group | Blocks | x0 (um) | x1 (um) | height (um) |
| --- | --- | --- | --- | --- |
| bias_resistor | R_BIAS | 0.00 | 1500.84 | 0.42 |
| feedback_divider | R_FB_A, R_FB_B, R_FB_C | 1502.84 | 2049.36 | 0.42 |
| compensation | R_CZ | 2051.36 | 2104.20 | 0.42 |
| bias_enable | M_BIASN1, M_ENN, M_BIASN2, M_ENN2, M_BIASP1, M_ENP2, M_ENP, M_ENP5, M_ENP3, M_ENP4 | 2122.20 | 2242.66 | 11.12 |
| error_amp | M_MIR1, M_MIR2, M_MIR3, M_MIR4, M_TAIL, M_IN1, M_IN2, M_MIRP1, M_MIRP2, M_IN2S | 2136.56 | 2277.50 | 41.12 |
| current_limit | M_CLN1, M_CLN2, M_SENSE, M_CLP, M_CLIM | 2163.92 | 2288.92 | 21.12 |
| soft_start | M_INVN, M_SSDIS, M_INVP, M_SSCHG | 2171.60 | 2303.70 | 3.12 |
| thermal_shutdown | M_TSD1, M_TSD2, M_TSR1, M_TCTAIL, M_TCN1, M_TCN2, M_TSPS, M_TSPR, M_TCP1, M_TCP2, M_TSHUT, M_TSHYSB, M_TSHYS | 2178.28 | 2334.68 | 80.82 |
| output_pass | M_PASS | 2336.68 | 2380.08 | 101.12 |

### Devices drawn as parallel unit arrays

| Device | W_total (um) | Units | Unit W (um) |
| --- | --- | --- | --- |
| `M_PASS` | 2500 | 25 | 100 |

A device wider than 100.0um is drawn as that many equal parallel unit devices with their terminals strapped, rather than as one enormous single-finger device. `klt lvs`'s `options.combine_devices` folds them back into one device of the summed width for the compare.

## Results

| Stage | Status | Detail |
| --- | --- | --- |
| DRC | clean | violation_count=0 |

DRC coverage: layers_checked=['65/20', '66/20', '66/44', '67/20', '67/44', '68/20', '68/44', '69/20'], rules_skipped=0.

## Known gap: the schematic's capacitors are not drawn

4 schematic element(s) have no corresponding `klt gen` generator at this repo's pinned `klt` commit -- there is no capacitor/MiM family member alongside `mos_array`/`res_array`, filed generically per `CLAUDE.md`'s friction protocol as https://github.com/2AMLogic/klayout-tools/issues/1117:

- `C_COMP`
- `C_CL`
- `C_SS`
- `C_TS`

`layout/bin/gen-ldo-reference-netlist.py` drops the same elements from the LVS reference, so the compare stays symmetric -- their absence is a disclosed coverage gap in both directions, not a silent one.

## Provenance

- Record ID: `20260825-123551-3b4e121`
- `klt` version: `klt 0.2.0` (pinned commit, see `layout/requirements.txt`)
- KLayout engine version: `0.30.11`
- PDK: `sky130A`, `open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b`
- PDK pin cross-check: compare `version` above against `sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself enforce the pin (unlike `sim/bin/corner-run.py`), consistent with `layout/README.md`'s trivial-cell flow.
- Schematic freshness: `design/ldo_3v3in_1v8out.sch` as of commit `b53a8e7` (see `design/README.md`'s own Freshness note). This record's device set was read from that schematic at run time, not from a table.
- Repo state: `3b4e121e246a33b9387593e4fd5cc6f668ee4958` on `feature/issue-89` (dirty)

## Links

- [`floorplan.json`](floorplan.json) -- resolved placement, per-device sizing, and the routed net table
- [`compose.request.json`](compose.request.json), [`compose.json`](compose.json)
- [`ldo_core.gds`](ldo_core.gds) -- the routed layout
- [`ldo_core.placed.gds`](ldo_core.placed.gds) -- `klt gen-compose`'s own output, before this flow's routing was drawn
- [`drc.json`](drc.json)
- `gen.<device>.json` / `<device>.gds` -- per-device `klt gen` report and standalone cell, one pair per schematic device
- [`report.md`](report.md) -- `klt report --format github-summary` rendering of `drc.json`

