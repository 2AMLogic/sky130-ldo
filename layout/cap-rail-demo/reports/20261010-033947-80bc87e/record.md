# MiM capacitor + supply-rail overlay demonstrator: 20261010-033947-80bc87e

Issue #254. **A bounded geometry demonstrator, not the LDO core.** It draws the schematic's four capacitors as stacked MiM arrays and the two load-current rails on the proposed metal assignment inside the planned core outline; no MOS device, resistor or signal route is drawn. The ratified Area row (< 0.1 mm^2, strict) is unchanged and is **not** claimed met by the core. Full-core integration and electrical requalification belong to #231.

## Provenance

- klt `0.7.0+gb82427b30c96` (pin `layout/cap-requirements.txt`), KLayout in klt `0.30.12`
- Official DRC: PDK `sky130A_mr.drc` run by system `KLayout 0.28.16` (FEOL+BEOL+offgrid; 247 rule categories evaluated)
- Schematic `design/ldo_3v3in_1v8out.sch` @ `a09aa83` (capacitors read from its own xschem netlist, `xschem_out/`)
- Measured inputs: `layout/ldo-core/reports/20260924-221821-a947aa8/floorplan.json`, `layout/ldo-core/reports/20260924-221821-a947aa8/ldo_core.gds`, `layout/area-study/20261009-study-246/budget.json`; spec `spec/target-spec.md`
- MiM law from the klt deck: 2.00 fF/um^2 + 0.19 fF/um (efabless/sky130_klayout_pdk:libs.tech/klayout/lvs/sky130.lvs@c6d73a35f524070e85faff4a6a9eef49553ebc2b)

## Gates

| Check | Result |
|---|---|
| `klt drc --deck sky130` | PASS -- clean, 0 violations |
| PDK `sky130A_mr.drc` (official) | PASS -- 0 markers |
| `klt lvs` extracted netlist vs schematic-derived reference | PASS -- `match`; devices 8/8, nets 7/7; `parameter_tolerance` 0.1% (largest used 0.0312%), top-level pins name-anchored |
| Negative control: C_COMP stated as 100 pF | PASS -- `mismatch` (must mismatch) |
| Negative control: C_TS outer terminal moved from `VIN` to `0` | PASS -- `mismatch` (must mismatch) |
| `klt lvs` on the GDS directly (`layout.file`) | evidence only -- `mismatch` {"device.geometry_not_compared": 2, "device.property": 16, "hints.rejected": 7, "topology": 3, "topology.top_level_pins_anchored": 1}; see README 'Tool friction' |

## Capacitors (values and nets from the schematic; extraction from the drawn GDS)

| Cap | Nets | Outer plates (met3+met5) | Inner plate (met4) | Array x unit | Schematic | Extracted MiM | Error | Block um^2 |
|---|---|---|---|---|---|---|---|---|
| C_COMP | VOUT-EA_CZ | VOUT | EA_CZ | 5x9 x 28.68 um | 150.000 pF | 150.0193 pF | +0.013% | 41048 |
| C_SS | SS-0 | 0 | SS | 2x2 x 24.81 um | 10.000 pF | 9.9994 pF | -0.006% | 3017 |
| C_CL | VIN-CL_CMP | VIN | CL_CMP | 1x1 x 15.625 um | 1.000 pF | 1.0003 pF | +0.031% | 383 |
| C_TS | VIN-TS_CMP | VIN | TS_CMP | 1x1 x 15.625 um | 1.000 pF | 1.0003 pF | +0.031% | 383 |

Each unit is a `cap_mim_m3_1` (met3/capm) under a `cap_mim_m3_2` (met4/capm2) of the same footprint, in parallel; both classes extract (`by_class_f` in `summary.json`) and each carries half the value.

## Coupling (`klt extract --parasitics`, adjacent-level overlap model)

| Cap | Reported plate-plate overlap | of which inside MiM footprint (double count) | Residual parallel parasitic | Inner node to ground | Inner node to any other net | Measured device-row met2 under block -> est. coupling to outer plate |
|---|---|---|---|---|---|---|
| C_COMP | 6108.6 fF | 5639.5 fF | 469.1 fF (0.31% of value) | 31.2 fF | none | 259 um^2 -> 22.3 fF |
| C_SS | 409.1 fF | 375.1 fF | 34.0 fF (0.34% of value) | 8.1 fF | none | 369 um^2 -> 31.8 fF |
| C_CL | 42.1 fF | 37.2 fF | 4.9 fF (0.49% of value) | 3.0 fF | none | 0 um^2 -> 0.0 fF |
| C_TS | 42.1 fF | 37.2 fF | 4.9 fF (0.49% of value) | 3.0 fF | none | 0 um^2 -> 0.0 fF |

- VIN-VOUT coupling reported: 69.4 fF (rail/tail crossings and the met2 VIN risers under C_COMP's VOUT plate).
- The extractor models adjacent-level overlap only: li1/met1 under a met3 plate (non-adjacent) is not charged to the plate at all, so device-row coupling beyond met2 is **not quantified** here (areas are in `summary.json`).

## Rails (unchanged #154 sizing rule, proposed levels)

| Net | Wide segment levels | Width (measured) | R / IR drop | Sense tail | Tail ohm/um (measured) |
|---|---|---|---|---|---|
| VIN | met2+met3 | 19.415 um (19.415) | 0.150 ohm / 7.50 mV | met2 only, 1.175 um (was met2+met3 0.32 um) | 0.1064 (0.1067) |
| VOUT | met1+met2 | 35.525 um (35.525) | 0.150 ohm / 7.50 mV | met1 only, 0.600 um (was met1+met2 0.30 um) | 0.2083 (0.2083) |

- met3 rail column (MiM keep-out): x 328.04-417.78, y 124.57-183.86 um (5321 um^2): the VIN band's met3 and the 50 pass-device VIN risers that cross the VOUT band on met3.
- 21 other VIN risers now cross the met1-only VOUT tail on met2.

## Footprint and feasibility verdict

- Planned core rectangle: 417.78 x 183.86 um = **0.0768 mm^2** (measured MOS domain 315.78 um + 2 um + 100 um folded-resistor bank column; channel 23.15 + row 101.12 + rail bands 59.59 um).
- Ratified limit 0.1 mm^2: below by 23.2% -> below the limit.
- Capacitor blocks (incl. straps/taps): 44830 um^2 in 71492 um^2 of overlay area outside the met3 rail column (62.7% used); MiM top-plate footprint 39965 um^2.
- Density: 3.61 fF/um^2 over the drawn blocks (the #246 study assumed 4 fF/um^2 unverified).
- Counterfactual, same blocks beside the core: 0.1216 mm^2 -> NOT below the limit.
- Counterfactual, one MiM level (no stacking): 89038 um^2 of blocks -> does NOT fit in the overlay area.

**Verdict: geometrically feasible on this plan** -- stacked MiM over the core, with the met3 rail column kept out, holds all four schematic capacitors DRC-clean and LVS-matched inside a rectangle below the limit. It depends on stacking (one MiM level does not fit) and on overlay (beside-the-core fails). This is conditional on every assumption below and is NOT a statement that the LDO core meets the Area row.

## Assumptions this verdict rests on (not verified here)

- The MOS domain keeps its measured width; the 12 comparator devices added since that layout (#230) fit in the bank column's free height and the 7 removed ones free nothing (#231 owns the refreshed layout).
- The folded resistor banks reproduce the #246 conservative 100 um estimate (#253 qualifies them).
- Coupling of the plates to the device row beyond met2, to poly resistors, and its electrical effect (loop, PSRR) is unquantified; the electrical requalification is #231's.
- Antenna/ERC on the large plates is not run here (`klt erc` belongs to the full-core flow).

