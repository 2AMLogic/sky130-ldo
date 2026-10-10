# LDO core layout record: 20261010-045715-e17e713

Placed and routed layout for the sky130 LDO's core regulation loop (issues #15/#33), generated from `design/ldo_3v3in_1v8out.sch`'s own headless xschem netlist: one `klt gen` block per active schematic device, placed by `klt gen-compose` and wired net-for-net by `layout/bin/gen-ldo-blocks.py`'s channel router. LVS against the schematic is its own driver and its own record -- see `layout/bin/run-ldo-lvs-flow.sh` and `reports/LATEST-LVS`.

## Overall verdict: FAIL

- [x] Curated-deck DRC (`klt drc --deck sky130`) on the routed ldo-core layout is clean
- [ ] Official-deck DRC (PDK `sky130A_mr.drc`) ran to completion and reports zero markers (15060 markers in 7 rule families)
- [x] Every schematic MOS/resistor device has exactly one placed `klt gen` block (53 devices)
- [x] Every schematic net the drawn devices touch is routed (28 nets, 301 terminals)

## Flow

1. `xschem -n -q -x -s ...` -- headless netlist of `design/ldo_3v3in_1v8out.sch`, the single source this layout's device set and connectivity are both derived from.
2. `layout/bin/gen-ldo-blocks.py` runs `klt gen mos_array` / `klt gen res_array` once per schematic device (48 MOS + 5 resistor blocks), computes an explicit single-row placement (see `layout/ldo-core/floorplan.md`), runs `klt gen-compose` to place them, then draws the inter-block routing and the two body ties.
3. `klt drc ldo_core.gds --deck sky130` (curated deck)
4. `klayout -b -r sky130A_mr.drc` on the same `ldo_core.gds` (the PDK's official deck; FEOL/BEOL/offgrid on, floating-metal and seal off, mirroring `layout/bin/run-cap-rail-demo-flow.sh`), then `layout/bin/diagnose-official-drc.py` to attribute any markers

## Composed cell

- Cell name: `ldo_core`
- Block count: 53
- Placed bbox (um), before routing: {'x0': 0.0, 'y0': 0.0, 'x1': 2450.679999999994, 'y1': 101.12}
- Device row: 2452.68um x 101.12um
- Routing channel: 28 met1 trunks on a 0.8um pitch below the row, 301 terminals landed

### Function groups (x extent within the row)

Blocks are ordered resistors -> every NMOS -> every PMOS, and inside each of those spans by function group, so a group that has both flavors (e.g. the error amplifier) occupies two x ranges rather than one contiguous block. The flavor split is load-bearing: the PMOS bodies are tied through one n-well drawn across the whole PMOS span, and `klt extract` decides a device's flavor by n-well containment.

| Group | Blocks | x0 (um) | x1 (um) | height (um) |
| --- | --- | --- | --- | --- |
| bias_resistor | R_BIAS | 0.00 | 1500.84 | 0.42 |
| feedback_divider | R_FB_A, R_FB_B, R_FB_C | 1502.84 | 2049.36 | 0.42 |
| compensation | R_CZ | 2051.36 | 2104.20 | 0.42 |
| bias_enable | M_BIASN1, M_ENN, M_BIASN2, M_ENN2, M_BIASP1, M_ENP2, M_ENP, M_ENP5, M_ENP3, M_ENP4 | 2122.20 | 2253.20 | 11.12 |
| error_amp | M_MIR1, M_MIR2, M_MIR3, M_MIR4, M_TAIL, M_IN1, M_IN2, M_MIRP1, M_MIRP2, M_IN2S | 2137.76 | 2288.04 | 41.12 |
| current_limit | M_CLN1, M_CLN2, M_SENSE, M_CLP, M_CLIM | 2166.32 | 2299.46 | 21.12 |
| soft_start | M_INVN, M_SSDIS, M_INVP, M_SSCHG | 2174.60 | 2314.24 | 3.12 |
| thermal_shutdown | M_TSD1, M_TSD2, M_TSR1, M_RCTAIL, M_RCN1, M_RCN2, M_RCOS, M_TSPS, M_TSPR, M_TSHUT, M_RCD1, M_RCD2, M_RCC1, M_RCC2, M_RCEA, M_RCEB, M_RCOP, M_RCEO | 2181.88 | 2361.78 | 81.12 |
| output_pass | M_PASS | 2363.78 | 2450.68 | 101.12 |

### Devices drawn as parallel unit arrays

| Device | W_total (um) | Units | Unit W (um) |
| --- | --- | --- | --- |
| `M_PASS` | 5000 | 50 | 100 |

A device wider than 100.0um is drawn as that many equal parallel unit devices with their terminals strapped, rather than as one enormous single-finger device. `klt lvs`'s `options.combine_devices` folds them back into one device of the summed width for the compare.

### Voltage-domain marking

Every MOS block is drawn inside the sky130 voltage-domain marker its own schematic model implies (issue #142), so `klt extract --pdk` binds the model the schematic actually instantiates instead of defaulting to the 1.8V core flavour:

| `voltage_flavor` | Marker layer | MOS blocks |
| --- | --- | --- |
| `hvi` | 75/20 | 48 |

DRC neutrality is measured here, not assumed: the marker layer(s) ['75/20'] appear in this record's own `drc.json` coverage under `layers_in_stream_without_rules` -- i.e. the geometry is really in the stream, and no rule in the curated sky130 deck reads it, so every rule kept applying its general-case threshold. The verdict above (`clean`, violation_count=0) is the authority.

## Results

| Stage | Status | Detail |
| --- | --- | --- |
| DRC, curated deck (`klt drc --deck sky130`) | clean | violation_count=0 |
| DRC, official deck (`sky130A_mr.drc`) | violations | 15060 markers in 7 rule families |

The two decks are separate gates and neither substitutes for the other: the curated deck is a hand-transcribed subset that is clean on this layout, while the PDK's own deck is the authority a tapeout would be checked against.

### Official-deck markers per rule family

| Rule | Markers |
| --- | --- |
| `via.1a_b` | 13468 |
| `licon.1` | 1204 |
| `m2.5` | 271 |
| `via2.5` | 77 |
| `nwell.9` | 35 |
| `urpm.1a` | 4 |
| `rpm.1a` | 1 |
| **total** | **15060** |

Marker totals are raw deck markers (edges / edge-pairs / polygons), not distinct defects: for example every undersized via contributes one marker per edge.

### Rule-family attribution (issue #260)

Each line separates what was measured from this record's own GDS (`official-drc-diagnosis.json`) from hypotheses about the fix. A hypothesis is not a claim until a later record demonstrates it.

- `licon.1`: 1204 markers. Measured: 53 generated block cells (resistor and MOS `klt gen` blocks) contain licons whose size is not 0.17um (sizes: ['0.220x0.220']); the flow's own body-tie licons are 0.17um and are not flagged. Owner: upstream `klt gen` (generic tool gap, see PR notes). Deck marker cell names (`mos_array$N`) are the deck's own renumbering and are not block names.
- `m2.5`: 271 markers. Measured, all in the top cell (local routing): 97 x marker 0.160x0.160 um; enclosure(um) l0.07 r0.07 b0.2 t0.07; 97 x marker 0.160x0.160 um; enclosure(um) l0.07 r0.07 b0.07 t0.2; 77 x marker 0.160x0.160 um; enclosure(um) l0.07 r0.07 b0.07 t0.07. The rule flags a via with <0.085um met2 enclosure on two ADJACENT edges. Owner: local routing (met2 riser ends / landing pad). Hypothesis: extend riser ends >=0.085um past the via and/or widen the pad; needs LVS/PEX re-run.
- `nwell.9`: 35 markers. Measured: n-well area 23286.558um2 vs hvi marker 10927.643um2; n-well not covered by hvi = 13623.747um2, of which 0.0um2 lies inside a generated block's own bbox (so the uncovered well is the local overhang: the 1um margins and the inter-block gaps). Owner: local routing (the single n-well rectangle). Hypothesis: extend the voltage-domain marker over the well; changes the marked area and needs LVS re-run.
- `rpm.1a`: 1 markers. Measured resistor-marker extents by block: {'R_BIAS__R_BIAS': {'marker_bbox_um': '1500.000x0.420', 'polygons': 1}}. The marker is drawn exactly the resistor body width (0.42um), below the deck's 1.27um minimum marker width. Owner: upstream `klt gen res_array` (generic tool gap, see PR notes).
- `urpm.1a`: 4 markers. Measured resistor-marker extents by block: {'R_FB_A__R_FB_A': {'marker_bbox_um': '180.000x0.420', 'polygons': 1}, 'R_FB_B__R_FB_B': {'marker_bbox_um': '180.000x0.420', 'polygons': 1}, 'R_FB_C__R_FB_C': {'marker_bbox_um': '180.000x0.420', 'polygons': 1}, 'R_CZ__R_CZ': {'marker_bbox_um': '52.000x0.420', 'polygons': 1}}. The marker is drawn exactly the resistor body width (0.42um), below the deck's 1.27um minimum marker width. Owner: upstream `klt gen res_array` (generic tool gap, see PR notes).
- `via.1a_b`: 13468 markers. Measured: every via1 in the layout is drawn by the flow's own router in the top cell, sizes (um) {'0.160x0.160': 3367}; inside generated blocks: none. The deck's cap is a 0.15um via. Owner: local routing (`VIA1_UM` in `gen-ldo-blocks.py`). Hypothesis: shrinking to 0.15um removes this family but changes metal enclosure (see `m2.5`); needs LVS/PEX re-run.
- `via2.5`: 77 markers. Measured, all in the top cell (local routing): 77 x marker 0.200x0.200 um; enclosure(um) l0.05 r0.05 b0.05 t0.05. The rule flags a via with <0.085um met2 enclosure on two ADJACENT edges. Owner: local routing (met2 riser ends / landing pad). Hypothesis: extend riser ends >=0.085um past the via and/or widen the pad; needs LVS/PEX re-run.

DRC coverage: layers_checked=['64/20', '65/20', '65/44', '66/20', '66/44', '67/20', '67/44', '68/20', '68/44', '69/20', '69/44', '70/20'], rules_skipped=26.

## Known gap: the schematic's capacitors are not drawn

4 schematic element(s) have no corresponding `klt gen` generator at this repo's pinned `klt` commit -- there is no capacitor/MiM family member alongside `mos_array`/`res_array`, filed generically per `CLAUDE.md`'s friction protocol as https://github.com/2AMLogic/klayout-tools/issues/1117:

- `C_COMP`
- `C_CL`
- `C_SS`
- `C_TS`

`layout/bin/gen-ldo-reference-netlist.py` drops the same elements from the LVS reference, so the compare stays symmetric -- their absence is a disclosed coverage gap in both directions, not a silent one.

## Provenance

- Record ID: `20261010-045715-e17e713`
- `klt` version: `klt 0.6.0+g040f3406b485` (pinned commit, see `layout/requirements.txt`)
- KLayout engine version: `0.30.12`
- Official deck: `sky130A_mr.drc` sha256 `caf4a6b08cb12f78d6bb2d120737424c786b3bae8d6489234b9b269e91107bfc` from the resolved PDK; switches `feol=true beol=true offgrid=true floating_met=false seal=false`; `klayout -v`: `KLayout 0.28.16`
- PDK: `sky130A`, `open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b`
- PDK pin cross-check: compare `version` above against `sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself enforce the pin (unlike `sim/bin/corner-run.py`), consistent with `layout/README.md`'s trivial-cell flow.
- Schematic freshness: `design/ldo_3v3in_1v8out.sch` as of commit `a09aa83` (see `design/README.md`'s own Freshness note). This record's device set was read from that schematic at run time, not from a table.
- Repo state: `e17e713c5b61dfa05105c41639e3a6b4b83e3e44` on `feature/issue-260` (dirty)

## Links

- [`floorplan.json`](floorplan.json) -- resolved placement, per-device sizing, and the routed net table
- [`compose.request.json`](compose.request.json), [`compose.json`](compose.json)
- [`ldo_core.gds`](ldo_core.gds) -- the routed layout
- [`ldo_core.placed.gds`](ldo_core.placed.gds) -- `klt gen-compose`'s own output, before this flow's routing was drawn
- [`drc.json`](drc.json) -- curated-deck envelope
- [`mr-drc.lyrdb`](mr-drc.lyrdb), [`mr-drc.run.json`](mr-drc.run.json) -- the official deck's report database and the run record (deck sha256, switches, exit status)
- [`official-drc-diagnosis.json`](official-drc-diagnosis.json) -- per-family attribution measured from this record's `ldo_core.gds`
- `gen.<device>.json` / `<device>.gds` -- per-device `klt gen` report and standalone cell, one pair per schematic device
- [`report.md`](report.md) -- `klt report --format github-summary` rendering of `drc.json`

