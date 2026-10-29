# LDO core area budget, DR-013 bias candidate: 20261029-study-467

Issue #467 (DR-013). **Geometric estimate only** -- no DRC/LVS/PEX on a full core with capacitors. The ratified Area row (< 0.1 mm^2, strict) is unchanged and is not claimed met. Extends the #459 study (`layout/area-study/20261028-study-459`, not edited): same inputs, only `R_BIAS` changes.

## Candidate

- `R_BIAS`: res_xhigh_po W=0.42 L=211 (single straight body, no fold); body 212.28 um wide.
- Charged to the budget as a full-width strip of height 2.88 um + 2 um gap = 2145 um^2 (upper bound: full-width strip at the #459 N=4 strip height).
- N/A: one segment, nothing to fold; #263 M1/M2/joint criteria compare folded vs unsplit.
- Rectangle before capacitors: 439.48 x 184.17 um = **83084 um^2 (0.0831 mm^2)**.

## Result

| scenario | cap block um^2 | fills overlay | total mm^2 | margin | < 0.1? |
|---|---|---|---|---|---|
| `caps_overlay_stacked_4fF_drawn` | 44830 | 58% | 0.0831 | 16.9% | yes |
| `caps_overlay_nominal_4fF` | 45431 | 58% | 0.0831 | 16.9% | yes |
| `caps_overlay_single_2fF_drawn_counterfactual` | 89038 | 114% | 0.0944 | 5.6% | yes |
| `caps_overlay_single_2fF_nominal` | 90862 | 117% | 0.0962 | 3.8% | yes |

Reference (#459, N=4 fold, not qualified): 0.08308 mm^2 stacked; straight `res_high_po` floor 0.27649 mm^2.

## Not established

- A drawn full core with capacitors (DRC/LVS/PEX); MiM-over-MOS coupling; the real straight-body routing.
- The area figure equals #459's because `R_BIAS` is charged the same full-width strip; the candidate removes the fold qualification dependency, it does not shrink the rectangle.

## Reproduce

```bash
python3 layout/bin/ldo-area-budget-dr013.py --record-id 20261029-study-467
```
