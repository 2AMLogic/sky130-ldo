# Loop-gain stability PVT grid, dr013: 20261101-loop-pvt-467

Issue #467 / DR-013. Executed through `klt sim --backend batch` (no local fallback); translation per the `sim/bin/bias-retopo-pvt.py` docstring. Bounds are the unchanged ratified spec rows. Graded locally from raw responses.
Design: `dr013` (`dr013` = `R_BIAS` res_xhigh_po W=0.42 L=211; `record` = schematic of record).
Points requested: 45; rows returned: 810; failed submits: 0.

## Worst case per leg (min over the PVT points returned)

| C_out | ESR | load | worst PM (deg) | at | PM<45 pts | worst GM (dB) | at | GM<10 pts | pts |
|---|---|---|---|---|---|---|---|---|---|
| c033 | esr0 | 0ma | 15.18 | ss/-40C/2.97V | 32 | 66.54 | sf/-40C/3.63V | 0 | 44 PM / 44 GM of 45 |
| c033 | esr0 | 1ma | 74.47 | sf/-40C/3.63V | 0 | 25.91 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr0 | 50ma | 31.25 | ff/-40C/3.63V | 34 | 14.84 | ff/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr10m | 0ma | 15.18 | ss/-40C/2.97V | 32 | 66.56 | sf/-40C/3.63V | 0 | 44 PM / 44 GM of 45 |
| c033 | esr10m | 1ma | 74.53 | sf/-40C/3.63V | 0 | 26.01 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr10m | 50ma | 31.57 | ff/-40C/3.63V | 34 | 15.10 | ff/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr500m | 0ma | 15.19 | ss/-40C/2.97V | 32 | 67.14 | sf/-40C/3.63V | 0 | 44 PM / 44 GM of 45 |
| c033 | esr500m | 1ma | 77.40 | sf/-40C/3.63V | 0 | 30.90 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c033 | esr500m | 50ma | 45.93 | sf/-40C/3.63V | 0 | 26.50 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr0 | 0ma | 37.09 | ss/-40C/2.97V | 11 | 71.63 | sf/125C/3.63V | 0 | 44 PM / 44 GM of 45 |
| c47 | esr0 | 1ma | 45.18 | fs/125C/2.97V | 0 | 39.24 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr0 | 50ma | 73.80 | ff/-40C/3.63V | 0 | 26.84 | ff/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr10m | 0ma | 37.10 | ss/-40C/2.97V | 11 | 71.64 | sf/125C/3.63V | 0 | 44 PM / 44 GM of 45 |
| c47 | esr10m | 1ma | 45.21 | fs/125C/2.97V | 0 | 39.73 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr10m | 50ma | 74.50 | ff/-40C/3.63V | 0 | 28.11 | ff/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |
| c47 | esr500m | 0ma | 37.16 | ss/-40C/2.97V | 11 | 72.58 | sf/125C/3.63V | 0 | 44 PM / 44 GM of 45 |
| c47 | esr500m | 1ma | 47.04 | fs/125C/2.97V | 0 | n/a |  | 0 | 45 PM / 0 GM of 45 |
| c47 | esr500m | 50ma | 101.05 | sf/125C/3.63V | 0 | 47.89 | sf/-40C/3.63V | 0 | 45 PM / 45 GM of 45 |

Total PM<45 deg points: 197; GM<10 dB points: 0. Unavailable (reported, not inferred, never counted as pass): PM at 6 points, GM at 51 points (klt `transfer_metric_unavailable`, typically `no_downward_phase_crossing`: the loop phase never reaches -180 deg in the band).
Every per-point value is in `summary.json`.

Note: the per-corner `transfer_*.raw` waveform files klt kept were deleted before commit to keep the repo lean (about 50 MB); every value in the tables traces to `responses/<key>/klt.stdout` (the raw klt response) and `summary.json`. Request decks are in `requests/`.
