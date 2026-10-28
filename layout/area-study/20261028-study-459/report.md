# LDO core area budget with all four capacitors: 20261028-study-459

Issue #459 (part of #458, T1 item 5 `area`). **Geometric estimate only** -- no DRC/LVS/PEX on a full core with capacitors; the ratified Area row (< 0.1 mm^2, strict) is unchanged and is not claimed met.

## Sources

- Current routed floorplan `layout/ldo-core/reports/20261022-231908-56dd87fe/floorplan.json`: 48 MOS + 5 resistors, identical to the current schematic's device set (checked by the script); the MOS domain is **measured**, not estimated.
- Area record `layout/ldo-core/reports/20261023-170539-a8292e91/area.json` (GDS sha256 `1698311e6a2e9801...`): 2453.88 x 184.17 um = 0.4519 mm^2, capacitors undrawn.
- Capacitors: `layout/cap-rail-demo/reports/20261010-033947-80bc87e/summary.json` (#254 drawn stacked-MiM blocks, DRC/LVS clean on that demonstrator only). Resistors: `layout/folded-res-qual/reports/20261010-033502-704005c/geometry.json` (#253) and `layout/folded-res-qual/pvt-reports/20261017-031511-76e0ba72/record.md` (#263). Schematic `design/ldo_3v3in_1v8out.sch` at `a09aa83`; repo HEAD `c0766b6`.

## Budget

| item | um^2 | basis |
|---|---|---|
| MOS domain (337.48 x 184.17 um, substrate tie through pass device) | 62154 | measured, all 48 MOS |
| 2 um gap + 100 um bank column (width 439.48 um total) | 18785 | folded `R_FB_A/B/C`, `R_CZ`: 7 rows, bank height 21.7 um <= core height |
| `R_BIAS` N=4 strip (375.84 x 2.88 um + 2 um gap, full width) | 2145 | #253 geometry |
| **Rectangle before capacitors** | **83084** (0.0831 mm^2) | |
| Met3 rail keep-out above the pass device (no MiM) | 5321 | #254 |
| Overlay area usable for MiM | 77763 | rectangle - keep-out |

Capacitors C_COMP 150 pF, C_SS 10 pF, C_CL 1 pF, C_TS 1 pF (162 pF) are overlaid on occupied core area, so they add nothing to the rectangle while they fit.

## Result at 2 and 4 fF/um^2

| scenario | cap block um^2 | fills overlay | total mm^2 | margin | < 0.1? |
|---|---|---|---|---|---|
| `caps_overlay_stacked_4fF_drawn`: stacked MiM as drawn in #254 (effective 4.05 fF/um^2 of footprint, block overhead x1.122) | 44830 | 58% | 0.0831 | 16.9% | yes |
| `caps_overlay_nominal_4fF`: nominal 4 fF/um^2 footprint density with the same block overhead | 45431 | 58% | 0.0831 | 16.9% | yes |
| `caps_overlay_single_2fF_drawn_counterfactual`: single MiM level (2 fF/um^2), #254 counterfactual block area, overlay attempted | 89038 | 114% | 0.0944 | 5.6% | yes |
| `caps_overlay_single_2fF_nominal`: nominal 2 fF/um^2 footprint density with the stacked-block overhead | 90862 | 117% | 0.0962 | 3.8% | yes |

The 4 fF/um^2 rows are the stacked met3-met4-met5 pair drawn and extracted in #254 (measured effective 4.05 fF/um^2 of footprint; block overhead x1.122 for straps/taps). The 2 fF/um^2 rows are the single-MiM-level case: the block exceeds the overlay (114-117%) and the overflow lands beside the core, which still leaves the total just under the limit (margin 3.8-5.6%).

## Sensitivity

- Dominant capacitor: `C_COMP` = 93% of the capacitance. The rectangle does not move with capacitor value until the overlay is full.
- At the drawn stacked density the overlay holds 281 pF (1.74x the 162 pF); the total stays below 0.1 mm^2 up to 342 pF (2.11x).
- `R_BIAS` straight (no fold): the rectangle is at least 1501.3 um wide; at the current 184.17 um height that is 0.2765 mm^2, and the limit would need a height under 66.6 um while channel + rail bands alone are 82.8 um. This fails with or without capacitors.

## Verdict

**Feasible under 0.1 mm^2 on paper: 0.0831 mm^2** (16.9% margin), with all four capacitors, folded resistors and the measured current MOS domain. It holds only if:

1. the capacitors are overlaid on the core. At the drawn stacked density (~4 fF/um^2) the margin is 16.9%; at 2 fF/um^2 (single level) the overflow beside the core still keeps the total under the limit but the margin shrinks to 3.8-5.6%, thin for an estimate with no full-core routing; and
2. `R_BIAS` is folded to N=4 segments. #263 does **not** qualify that fold: the deterministic and mean-shift gates pass (worst +0.2226 % < 0.2462 %), but the mismatch gate M2 fails (sigma ratio 1.1316 > 1.1, already 1.1114 at N=2), and the 4x-joint sensitivity flips the deterministic verdict. No `R_BIAS` segment count is QUALIFIED. With `R_BIAS` straight the measured floor is 0.2765 mm^2.

So the answer is a conditional go, not a floor above 0.1 mm^2: the floor is set by the `R_BIAS` fold qualification, which is a design question (accept the N=4 fold's mismatch, or re-topologise the bias) and not an area measurement. No decision record is drafted here because the area itself does not force one; if the `R_BIAS` fold is finally rejected the floor becomes the straight-resistor figure above and a floor DR is then required. The Area row is unchanged. Nothing here is DRC/LVS/PEX verified for the full core.

## Not established

- A drawn full core with capacitors: the layout still omits them, and the overlay is checked only in the #254 demonstrator.
- Electrical requalification (loop stability, PSRR, start-up) with MiM parasitics and folded-resistor joints.
- MiM-over-MOS routing and coupling in the real core (the demonstrator has no MOS); the bank column height was checked against the core height only.

## Reproduce

```bash
python3 layout/bin/ldo-area-budget-4cap.py --record-id 20261028-study-459   # reads only the committed inputs above
```
