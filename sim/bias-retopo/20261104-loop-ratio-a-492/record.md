# Loop-gain stability PVT grid, dr013: 20261104-loop-ratio-a-492

Issue #492 / DR-013 alternative (a) (ratio-a patch, see ../20261104-ratio-a-492/record.md). Executed through `klt sim --backend batch` (no local fallback); translation per the `sim/bin/bias-retopo-pvt.py` docstring. Bounds are the unchanged ratified spec rows. Graded locally from raw responses.
Design: ratio-a candidate: `R_BIAS` res_high_po W=0.42 L=750, `M_BIASN2` W=2 (header text hand-corrected; the script prints fixed #467 wording).
Points requested: 45; rows returned: 810; failed submits: 0.

## Worst case per leg (min over the PVT points returned)

| C_out | ESR | load | worst PM (deg) | at | PM<45 pts | worst GM (dB) | at | GM<10 pts | pts |
|---|---|---|---|---|---|---|---|---|---|
| c033 | esr0 | 0ma | 14.76 | fs/-40C/2.97V | 34 | 66.44 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr0 | 1ma | 74.00 | sf/-40C/3.63V | 0 | 25.80 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr0 | 50ma | 31.01 | sf/-40C/3.63V | 30 | 14.79 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr10m | 0ma | 14.76 | fs/-40C/2.97V | 34 | 66.45 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr10m | 1ma | 74.06 | sf/-40C/3.63V | 0 | 25.90 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr10m | 50ma | 31.32 | sf/-40C/3.63V | 29 | 15.05 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr500m | 0ma | 14.78 | fs/-40C/2.97V | 34 | 67.04 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr500m | 1ma | 76.98 | sf/-40C/3.63V | 0 | 30.84 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr500m | 50ma | 45.66 | sf/-40C/3.63V | 0 | 26.44 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr0 | 0ma | 36.06 | ss/-40C/2.97V | 15 | 71.62 | sf/125C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr0 | 1ma | 44.18 | fs/125C/2.97V | 3 | 39.12 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr0 | 50ma | 73.79 | sf/-40C/3.63V | 0 | 26.84 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr10m | 0ma | 36.06 | ss/-40C/2.97V | 15 | 71.64 | sf/125C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr10m | 1ma | 44.21 | fs/125C/2.97V | 3 | 39.62 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr10m | 50ma | 74.47 | sf/-40C/3.63V | 0 | 28.10 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr500m | 0ma | 36.12 | ss/-40C/2.97V | 15 | 72.60 | sf/125C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr500m | 1ma | 45.90 | fs/125C/2.97V | 0 | n/a |  | 0 | 45 PM / 0 GM of 45 |
| c47 | esr500m | 50ma | 101.14 | sf/125C/3.63V | 0 | 47.89 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |

Total PM<45 deg points: 212; GM<10 dB points: 0. Unavailable (reported, not inferred, never counted as pass): PM at 0 points, GM at 45 points (klt `transfer_metric_unavailable`, typically `no_downward_phase_crossing`: the loop phase never reaches -180 deg in the band).
Every per-point value is in `summary.json`.
