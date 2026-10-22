# LDO core layout record: 20261022-231908-56dd87fe

Placed and routed layout for the sky130 LDO's core regulation loop (issues #15/#33), generated from `design/ldo_3v3in_1v8out.sch`'s own headless xschem netlist: one `klt gen` block per active schematic device, placed by `klt gen-compose` and wired net-for-net by `layout/bin/gen-ldo-blocks.py`'s channel router. LVS against the schematic is its own driver and its own record -- see `layout/bin/run-ldo-lvs-flow.sh` and `reports/LATEST-LVS`.

## Overall verdict: PASS

- [x] Curated-deck DRC (`klt drc --deck sky130`) on the routed ldo-core layout is clean
- [x] Official-deck DRC (PDK `sky130A_mr.drc`) ran to completion and reports zero markers (0 markers across 247 declared rule categories)
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
- Placed bbox (um), before routing: {'x0': 0.0, 'y0': 0.0, 'x1': 2452.879999999994, 'y1': 101.42}
- Device row: 2454.88um x 101.42um
- Routing channel: 28 met1 trunks on a 0.8um pitch below the row, 301 terminals landed

### Function groups (x extent within the row)

Blocks are ordered resistors -> every NMOS -> every PMOS, and inside each of those spans by function group, so a group that has both flavors (e.g. the error amplifier) occupies two x ranges rather than one contiguous block. The flavor split is load-bearing: the PMOS bodies are tied through one n-well drawn across the whole PMOS span, and `klt extract` decides a device's flavor by n-well containment.

| Group | Blocks | x0 (um) | x1 (um) | height (um) |
| --- | --- | --- | --- | --- |
| bias_resistor | R_BIAS | 0.00 | 1501.28 | 2.60 |
| feedback_divider | R_FB_A, R_FB_B, R_FB_C | 1503.28 | 2051.12 | 2.60 |
| compensation | R_CZ | 2053.12 | 2106.40 | 2.60 |
| bias_enable | M_BIASN1, M_ENN, M_BIASN2, M_ENN2, M_BIASP1, M_ENP2, M_ENP, M_ENP5, M_ENP3, M_ENP4 | 2124.40 | 2255.40 | 11.42 |
| error_amp | M_MIR1, M_MIR2, M_MIR3, M_MIR4, M_TAIL, M_IN1, M_IN2, M_MIRP1, M_MIRP2, M_IN2S | 2139.96 | 2290.24 | 41.42 |
| current_limit | M_CLN1, M_CLN2, M_SENSE, M_CLP, M_CLIM | 2168.52 | 2301.66 | 21.42 |
| soft_start | M_INVN, M_SSDIS, M_INVP, M_SSCHG | 2176.80 | 2316.44 | 3.42 |
| thermal_shutdown | M_TSD1, M_TSD2, M_TSR1, M_RCTAIL, M_RCN1, M_RCN2, M_RCOS, M_TSPS, M_TSPR, M_TSHUT, M_RCD1, M_RCD2, M_RCC1, M_RCC2, M_RCEA, M_RCEB, M_RCOP, M_RCEO | 2184.08 | 2363.98 | 81.42 |
| output_pass | M_PASS | 2365.98 | 2452.88 | 101.42 |

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
| DRC, official deck (`sky130A_mr.drc`) | clean | 0 markers across 247 declared rule categories |

The two decks are separate gates and neither substitutes for the other: the curated deck is a hand-transcribed subset that is clean on this layout, while the PDK's own deck is the authority a tapeout would be checked against.

DRC coverage: layers_checked=['64/20', '65/20', '65/44', '66/20', '66/44', '67/20', '67/44', '68/20', '68/44', '69/20', '69/44', '70/20', '75/20', '79/20', '86/20', '93/44', '94/20', '95/20'], rules_skipped=68.

## Known gap: the schematic's capacitors are not drawn

4 schematic element(s) have no corresponding `klt gen` generator at this repo's pinned `klt` commit -- there is no capacitor/MiM family member alongside `mos_array`/`res_array`, filed generically per `CLAUDE.md`'s friction protocol as https://github.com/2AMLogic/klayout-tools/issues/1117:

- `C_COMP`
- `C_CL`
- `C_SS`
- `C_TS`

`layout/bin/gen-ldo-reference-netlist.py` drops the same elements from the LVS reference, so the compare stays symmetric -- their absence is a disclosed coverage gap in both directions, not a silent one.

## Provenance

- Record ID: `20261022-231908-56dd87fe`
- `klt` version: `klt 0.7.1.dev2457+gdc136150a49e` (pinned commit, see `layout/requirements.txt`)
- KLayout engine version: `0.30.12`
- Official deck: `sky130A_mr.drc` sha256 `caf4a6b08cb12f78d6bb2d120737424c786b3bae8d6489234b9b269e91107bfc` from the resolved PDK; switches `feol=true beol=true offgrid=true floating_met=false seal=false`; `klayout -v`: `KLayout 0.28.16`
- PDK: `sky130A`, `open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`
- PDK pin cross-check: compare `version` above against `sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself enforce the pin (unlike `sim/bin/corner-run.py`), consistent with `layout/README.md`'s trivial-cell flow.
- Schematic freshness: `design/ldo_3v3in_1v8out.sch` as of commit `a09aa83f` (see `design/README.md`'s own Freshness note). This record's device set was read from that schematic at run time, not from a table.
- Repo state: `56dd87fe0ae69ccba559098a3b46a82b1023c333` on `feature/issue-162` (dirty)

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

