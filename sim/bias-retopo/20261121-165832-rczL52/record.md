# Loop-gain stability PVT grid, record: 20261121-165832-rczL52

Issue #467 / DR-013. Executed through `klt sim --backend batch` (no local fallback); translation per the `sim/bin/bias-retopo-pvt.py` docstring. Bounds are the unchanged ratified spec rows. Graded locally from raw responses.
Design: `record` (`dr013` = `R_BIAS` res_xhigh_po W=0.42 L=211; `record` = schematic of record).
Points requested: 45; rows returned: 810; failed submits: 0.

## Worst case per leg (min over the PVT points returned)

| C_out | ESR | load | worst PM (deg) | at | PM<45 pts | worst GM (dB) | at | GM<10 pts | pts |
|---|---|---|---|---|---|---|---|---|---|
| c033 | esr0 | 0ma | 15.45 | ss/-40C/2.97V | 33 | 66.44 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr0 | 1ma | 73.99 | sf/-40C/3.63V | 0 | 25.80 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr0 | 50ma | 31.00 | sf/-40C/3.63V | 34 | 14.79 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr10m | 0ma | 15.45 | ss/-40C/2.97V | 33 | 66.45 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr10m | 1ma | 74.05 | sf/-40C/3.63V | 0 | 25.90 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr10m | 50ma | 31.31 | sf/-40C/3.63V | 33 | 15.05 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr500m | 0ma | 15.47 | ss/-40C/2.97V | 33 | 67.04 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr500m | 1ma | 76.97 | sf/-40C/3.63V | 0 | 30.83 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr500m | 50ma | 45.65 | sf/-40C/3.63V | 0 | 26.44 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr0 | 0ma | 37.84 | ss/-40C/2.97V | 12 | 71.62 | sf/125C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr0 | 1ma | 44.90 | fs/125C/2.97V | 1 | 39.12 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr0 | 50ma | 73.73 | ff/-40C/3.63V | 0 | 26.83 | ff/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr10m | 0ma | 37.84 | ss/-40C/2.97V | 12 | 71.64 | sf/125C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr10m | 1ma | 44.93 | fs/125C/2.97V | 1 | 39.61 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr10m | 50ma | 74.42 | ff/-40C/3.63V | 0 | 28.09 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr500m | 0ma | 37.91 | ss/-40C/2.97V | 11 | 72.60 | sf/125C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr500m | 1ma | 46.72 | fs/125C/2.97V | 0 | n/a |  | 0 | 45 PM / 0 GM of 45 |
| c47 | esr500m | 50ma | 101.11 | ss/125C/3.63V | 0 | 47.89 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |

Total PM<45 deg points: 203; GM<10 dB points: 0. Unavailable (reported, not inferred, never counted as pass): PM at 0 points, GM at 45 points (klt `transfer_metric_unavailable`, typically `no_downward_phase_crossing`: the loop phase never reaches -180 deg in the band).
Every per-point value is in `summary.json`.
