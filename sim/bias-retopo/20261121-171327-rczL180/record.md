# Loop-gain stability PVT grid, record: 20261121-171327-rczL180

Issue #467 / DR-013. Executed through `klt sim --backend batch` (no local fallback); translation per the `sim/bin/bias-retopo-pvt.py` docstring. Bounds are the unchanged ratified spec rows. Graded locally from raw responses.
Design: `record` (`dr013` = `R_BIAS` res_xhigh_po W=0.42 L=211; `record` = schematic of record).
Points requested: 45; rows returned: 810; failed submits: 0.

## Worst case per leg (min over the PVT points returned)

| C_out | ESR | load | worst PM (deg) | at | PM<45 pts | worst GM (dB) | at | GM<10 pts | pts |
|---|---|---|---|---|---|---|---|---|---|
| c033 | esr0 | 0ma | 26.99 | fs/-40C/2.97V | 33 | 55.14 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr0 | 1ma | 27.03 | sf/-40C/3.63V | 45 | 19.75 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr0 | 50ma | 12.98 | sf/-40C/3.63V | 45 | 10.71 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr10m | 0ma | 26.99 | fs/-40C/2.97V | 33 | 55.15 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr10m | 1ma | 27.12 | sf/-40C/3.63V | 45 | 19.92 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr10m | 50ma | 13.25 | sf/-40C/3.63V | 45 | 11.04 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr500m | 0ma | 27.01 | fs/-40C/2.97V | 33 | 55.61 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr500m | 1ma | 31.42 | sf/-40C/3.63V | 45 | 27.30 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr500m | 50ma | 26.08 | ss/-40C/3.63V | 45 | 25.21 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr0 | 0ma | 40.15 | ss/-40C/2.97V | 10 | 72.17 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr0 | 1ma | 70.51 | sf/-40C/3.63V | 0 | 32.29 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr0 | 50ma | 27.00 | ff/-40C/3.63V | 45 | 20.95 | ff/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr10m | 0ma | 40.15 | ss/-40C/2.97V | 10 | 72.26 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr10m | 1ma | 70.70 | sf/-40C/3.63V | 0 | 32.96 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr10m | 50ma | 28.01 | ff/-40C/3.63V | 45 | 23.00 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr500m | 0ma | 40.21 | ss/-40C/2.97V | 10 | 77.68 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr500m | 1ma | 79.57 | ff/125C/2.97V | 0 | 52.43 | tt/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr500m | 50ma | 67.80 | ff/27C/3.30V | 0 | 44.19 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |

Total PM<45 deg points: 489; GM<10 dB points: 0. Unavailable (reported, not inferred, never counted as pass): PM at 0 points, GM at 0 points (klt `transfer_metric_unavailable`, typically `no_downward_phase_crossing`: the loop phase never reaches -180 deg in the band).
Every per-point value is in `summary.json`.
