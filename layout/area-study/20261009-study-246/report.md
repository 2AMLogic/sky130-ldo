# LDO core area budget and compaction feasibility: 20261009-study-246

Issue #246 study. **Geometric estimate only** -- no DRC/LVS/PEX/simulation on any compacted layout; the ratified Area row (< 0.1 mm^2, strict) is unchanged and is not claimed met.

## Sources and conventions

- Measured area record: `layout/ldo-core/reports/20261008-161046-f4fbb86/area.json` (GDS sha256 `3e7f504b56ea85cd...`), from layout record `20260924-221821-a947aa8`; per-device table `layout/ldo-core/reports/20260924-221821-a947aa8/floorplan.json`.
- Schematic: `design/ldo_3v3in_1v8out.sch`, last changed at `a09aa83`. Repo HEAD for this study: `16bac1b`.
- Resistor segment probe: klt `0.7.0+gb82427b30c96` (recorded); units um / um^2; area = bounding rectangle width x height (see `budget.json` `geometry_convention`).
- **Historical vs current**: the routed layout predates comparator integration (#230). The floorplan has 43 MOS + 5 resistors; the current schematic has 48 MOS + 5 resistors + 4 capacitors. MOS not in the layout: M_RCC1, M_RCC2, M_RCD1, M_RCD2, M_RCEA, M_RCEB, M_RCEO, M_RCN1, M_RCN2, M_RCOP, M_RCOS, M_RCTAIL; in layout but not in schematic: M_TCN1, M_TCN2, M_TCP1, M_TCP2, M_TCTAIL, M_TSHYS, M_TSHYSB; sized differently: none. #231 owns refreshing the layout.
- Observed: the layout's `M_PASS` is 5000 um total width; `layout/ldo-core/floorplan.md` still quotes 2500 um (stale prose, not changed here).

## Where the 0.4468 mm^2 goes

- Footprint 2430.17 x 183.86 um = 0.4468 mm^2 (4.47x limit).
- Occupied device bboxes: MOS 10810 um^2 + resistors 880.4 um^2 = 2.6% of the rectangle. A device-area sum is therefore NOT the footprint; the rest is spacing, tap slots, the routing channel, rail bands and empty corners.
- Width: the resistor span is 2104.2 um = 86.6% of the width; `R_BIAS` alone is 1500.8 um (61.8%). The MOS domain (substrate-tie slot through the pass device) is 315.8 um (13.0%).
- Height 183.86 um = routing channel 23.15 (13%) + device row 101.12 (55%, set by the pass device unit height) + rail bands 59.59 (32%, widths computed from the ratified dropout budget, `layout/ldo-core/floorplan.md`).
- Tap slots (4.0 um each) and block gaps (2.0 um) are second-order here.

## Does placement alone reach < 0.1 mm^2?

No. The straight `R_BIAS` makes any single-rectangle floorplan at least 1500.8 um wide; < 0.1 mm^2 then requires a total height under 66.6 um. The channel + rail-band reservations alone are 82.7 um (before any device row), so the bound fails even with every other device free. Multi-row placement cannot split the resistor (the pinned generator draws one straight body per logical resistor), so row count does not reduce the 1500 um dimension. At the current height the straight-resistor rectangle would be 0.276 mm^2.

## Folded-resistor direction (separate NMOS/PMOS wells kept, existing rail sizing kept)

Model: each logical resistor is cut into N equal straight series segments (body lengths sum to the schematic L; W unchanged), stacked as rows in a bank per flavor (`high` / `xhigh` masks must not mix). Segment length overhead and pad height come from the single-unit probe; row pitch = pad bbox height + min spacing (conservative) or body width + spacing (optimistic, staggered pads, not claimed).

| bank width (um) | pitch | R_BIAS bank rows / area | xhigh bank rows / area | total (um^2) |
|---|---|---|---|---|
| 50 | conservative | 31 / 4805 | 14 / 2170 | 6975 |
| 50 | optimistic | 31 / 1426 | 14 / 644 | 2070 |
| 100 | conservative | 16 / 4960 | 7 / 2170 | 7130 |
| 100 | optimistic | 16 / 1472 | 7 / 644 | 2116 |
| 200 | conservative | 8 / 4960 | 4 / 2480 | 7440 |
| 200 | optimistic | 8 / 1472 | 4 / 736 | 2208 |

The resistors then cost roughly 0.01 mm^2, not 0.3 mm^2: the width problem is real but removable. Assumptions (all to be verified later): resistors sit on field oxide needing no well (only the existing substrate-tie reach), the 0.4 um foreign clearance and 0.5 um spacing from the generator hints suffice, series joints are short li1/met1 jogs, and the N-segment series string reproduces the original resistance within tolerance (joint/contact resistance and end-pad contribution are NOT yet evaluated; electrical requalification is required). `klt gen res_array` units are independent matched elements (`rows` re-arranges `num` units, it does not chain them in series), so the series connection must be routed by `gen-ldo-blocks.py` (a tool gap, filed generically as 2AMLogic/klayout-tools#2997). `klt lvs` `options.combine_devices` has handled series resistor arrays in past upstream work (fixed-offset corrections were issues #559/#1557 there); whether it folds this repo's pinned build's N-segment string to the schematic's single element is UNVERIFIED and is part of follow-up (a).

## Whole-footprint scenarios (current reservations, MOS domain re-used as measured)

| scenario (B-D omit the undrawn capacitors, so a 'yes' is not a pass claim) | mm^2 | < 0.1? |
|---|---|---|
| A. Measured routed core (record) | 0.4468 | no |
| B. MOS domain only (no resistors, NO caps), full channel/rails height | 0.0581 | yes |
| C. B + folded resistor banks (100 um, conservative; NO caps) | 0.0652 | yes |
| D. C + estimated net MOS change (12 added, 7 removed) to the current schematic | 0.0654 | yes |
| E1. D + all four capacitors beside the core, 2 fF/um^2 | 0.1464 | no |
| E2. D + capacitors beside, 4 fF/um^2 (stacked MiM, unverified) | 0.1059 | no |

**The dominant blocker is not the resistor.** The four capacitors (C_COMP 150 pF, C_SS 10 pF, C_CL 1 pF, C_TS 1 pF = 162 pF) are not drawn in the measured layout (known gap, `layout/ldo-core/floorplan.md`), so the 0.4468 mm^2 figure omits them. At 2 fF/um^2 they need 81000 um^2 (0.081 mm^2) by themselves -- 81% of the limit -- and 40500 um^2 at an assumed 4 fF/um^2. `design/README.md` already notes MiM (met3-met4) can sit over the pass device, but the VIN rail's upper band uses met2+met3 above it, so overlaying needs a rail-level change that is not evaluated here. Placing capacitors beside the core fails in E1 and is marginal-to-failing in E2 (before any capacitor spacing/routing); only overlay on already-occupied core area, with the metal-stack conflict resolved, leaves a geometric path.

## Conclusion

1. Placement alone cannot reach the limit (straight R_BIAS width, rail+channel height).
2. Folded series resistors plus separate NMOS/PMOS wells replace the 2104 um resistor row with ~100 um banks (~0.007 mm^2) and, with the MOS domain unchanged, estimate ~0.06-0.07 mm^2 WITHOUT capacitors (scenarios C/D) -- a feasible-looking but unverified bounded path.
3. Capacitor area (0.081 mm^2 at 2 fF/um^2) is an evidenced blocker for any side-by-side plan; feasibility hinges on overlaying MiM above the core (met3/met4), which conflicts with the current upper rail band (met2+met3) and needs separate rail/MiM-level planning, or on a spec decision record -- not a loosened spec line here.
4. Nothing here is DRC/LVS/PEX verified.

## Bounded follow-up scope

- (a) Generate the series-folded resistor with the router (or a tool capability) and confirm LVS series folding (`combine_devices`) or extend the reference; verify DRC/LVS on a resistor-only test block; re-measure R by extraction and a single-corner check.
- (b) Add the four MiM capacitors (`klt gen cap_array` exists on the host klt 0.7.0, newer than this repo's pin 040f3406) and plan a rail-level change so the 150 pF MiM overlays the core; DRC/LVS it.
- (c) Refresh the layout to the current schematic (#231), re-mint the area record (append-only), then only compare against the limit. Final DRC/LVS and electrical qualification remain required.

## Reproduce

```bash
python3 layout/bin/ldo-area-budget.py            # uses recorded probe constants
python3 layout/bin/ldo-area-budget.py --probe-klt   # one local single-unit klt gen
```
