# PSRR PVT grid, dr013: 20261104-psrr-ratio-a-492

Issue #492 / DR-013 alternative (a) (ratio-a patch, see ../20261104-ratio-a-492/record.md). Executed through `klt sim --backend batch` (no local fallback); translation per the `sim/bin/bias-retopo-pvt.py` docstring. Bounds are the unchanged ratified spec rows. Graded locally from raw responses.
Design: ratio-a candidate: `R_BIAS` res_high_po W=0.42 L=750, `M_BIASN2` W=2 (header text hand-corrected; the script prints fixed #467 wording).
Points requested: 45; rows returned: 90; failed submits: 0.

## Worst case per metric

| load | freq | worst PSRR (dB) | at |
|---|---|---|---|
| 1ma | 100k | 31.86 | fs/-40C/3.63V |
| 1ma | 1k | 19.57 | fs/125C/2.97V |
| 50ma | 100k | 10.07 | fs/-40C/2.97V |
| 50ma | 1k | 19.76 | fs/125C/2.97V |

## All points

| load | VIN | process | T(C) | PSRR 1k (dB) | >50 | PSRR 100k (dB) | >20 |
|---|---|---|---|---|---|---|---|
| 1ma | 2.97 | tt | -40 | 22.64 | FAIL | 32.06 | PASS |
| 1ma | 2.97 | tt | 27 | 21.75 | FAIL | 33.54 | PASS |
| 1ma | 2.97 | tt | 125 | 20.34 | FAIL | 35.55 | PASS |
| 1ma | 2.97 | ss | -40 | 22.61 | FAIL | 32.03 | PASS |
| 1ma | 2.97 | ss | 27 | 21.71 | FAIL | 33.56 | PASS |
| 1ma | 2.97 | ss | 125 | 20.31 | FAIL | 35.55 | PASS |
| 1ma | 2.97 | ff | -40 | 22.88 | FAIL | 32.04 | PASS |
| 1ma | 2.97 | ff | 27 | 21.96 | FAIL | 33.56 | PASS |
| 1ma | 2.97 | ff | 125 | 20.51 | FAIL | 35.52 | PASS |
| 1ma | 2.97 | sf | -40 | 23.61 | FAIL | 32.04 | PASS |
| 1ma | 2.97 | sf | 27 | 22.57 | FAIL | 33.58 | PASS |
| 1ma | 2.97 | sf | 125 | 21.06 | FAIL | 35.56 | PASS |
| 1ma | 2.97 | fs | -40 | 21.58 | FAIL | 32.03 | PASS |
| 1ma | 2.97 | fs | 27 | 20.86 | FAIL | 33.56 | PASS |
| 1ma | 2.97 | fs | 125 | 19.57 | FAIL | 35.51 | PASS |
| 1ma | 3.30 | tt | -40 | 23.85 | FAIL | 32.00 | PASS |
| 1ma | 3.30 | tt | 27 | 22.86 | FAIL | 33.53 | PASS |
| 1ma | 3.30 | tt | 125 | 21.41 | FAIL | 35.54 | PASS |
| 1ma | 3.30 | ss | -40 | 23.83 | FAIL | 31.98 | PASS |
| 1ma | 3.30 | ss | 27 | 22.83 | FAIL | 33.54 | PASS |
| 1ma | 3.30 | ss | 125 | 21.39 | FAIL | 35.57 | PASS |
| 1ma | 3.30 | ff | -40 | 24.11 | FAIL | 32.02 | PASS |
| 1ma | 3.30 | ff | 27 | 23.08 | FAIL | 33.52 | PASS |
| 1ma | 3.30 | ff | 125 | 21.61 | FAIL | 35.50 | PASS |
| 1ma | 3.30 | sf | -40 | 24.73 | FAIL | 32.00 | PASS |
| 1ma | 3.30 | sf | 27 | 23.59 | FAIL | 33.54 | PASS |
| 1ma | 3.30 | sf | 125 | 22.07 | FAIL | 35.55 | PASS |
| 1ma | 3.30 | fs | -40 | 22.90 | FAIL | 32.00 | PASS |
| 1ma | 3.30 | fs | 27 | 22.06 | FAIL | 33.46 | PASS |
| 1ma | 3.30 | fs | 125 | 20.72 | FAIL | 35.53 | PASS |
| 1ma | 3.63 | tt | -40 | 24.86 | FAIL | 31.95 | PASS |
| 1ma | 3.63 | tt | 27 | 23.78 | FAIL | 33.50 | PASS |
| 1ma | 3.63 | tt | 125 | 22.31 | FAIL | 35.53 | PASS |
| 1ma | 3.63 | ss | -40 | 24.85 | FAIL | 31.93 | PASS |
| 1ma | 3.63 | ss | 27 | 23.77 | FAIL | 33.52 | PASS |
| 1ma | 3.63 | ss | 125 | 22.30 | FAIL | 35.57 | PASS |
| 1ma | 3.63 | ff | -40 | 25.16 | FAIL | 31.96 | PASS |
| 1ma | 3.63 | ff | 27 | 24.05 | FAIL | 33.48 | PASS |
| 1ma | 3.63 | ff | 125 | 22.55 | FAIL | 35.49 | PASS |
| 1ma | 3.63 | sf | -40 | 25.65 | FAIL | 31.95 | PASS |
| 1ma | 3.63 | sf | 27 | 24.45 | FAIL | 33.51 | PASS |
| 1ma | 3.63 | sf | 125 | 22.90 | FAIL | 35.54 | PASS |
| 1ma | 3.63 | fs | -40 | 24.00 | FAIL | 31.86 | PASS |
| 1ma | 3.63 | fs | 27 | 23.06 | FAIL | 33.50 | PASS |
| 1ma | 3.63 | fs | 125 | 21.68 | FAIL | 35.52 | PASS |
| 50ma | 2.97 | tt | -40 | 22.69 | FAIL | 10.48 | FAIL |
| 50ma | 2.97 | tt | 27 | 21.82 | FAIL | 11.06 | FAIL |
| 50ma | 2.97 | tt | 125 | 20.49 | FAIL | 12.28 | FAIL |
| 50ma | 2.97 | ss | -40 | 22.65 | FAIL | 10.63 | FAIL |
| 50ma | 2.97 | ss | 27 | 21.78 | FAIL | 11.31 | FAIL |
| 50ma | 2.97 | ss | 125 | 20.45 | FAIL | 12.60 | FAIL |
| 50ma | 2.97 | ff | -40 | 22.92 | FAIL | 10.44 | FAIL |
| 50ma | 2.97 | ff | 27 | 22.02 | FAIL | 10.85 | FAIL |
| 50ma | 2.97 | ff | 125 | 20.66 | FAIL | 11.94 | FAIL |
| 50ma | 2.97 | sf | -40 | 23.63 | FAIL | 10.96 | FAIL |
| 50ma | 2.97 | sf | 27 | 22.61 | FAIL | 11.27 | FAIL |
| 50ma | 2.97 | sf | 125 | 21.18 | FAIL | 12.35 | FAIL |
| 50ma | 2.97 | fs | -40 | 21.66 | FAIL | 10.07 | FAIL |
| 50ma | 2.97 | fs | 27 | 20.96 | FAIL | 10.89 | FAIL |
| 50ma | 2.97 | fs | 125 | 19.76 | FAIL | 12.21 | FAIL |
| 50ma | 3.30 | tt | -40 | 23.93 | FAIL | 11.07 | FAIL |
| 50ma | 3.30 | tt | 27 | 22.96 | FAIL | 11.17 | FAIL |
| 50ma | 3.30 | tt | 125 | 21.61 | FAIL | 12.04 | FAIL |
| 50ma | 3.30 | ss | -40 | 23.90 | FAIL | 11.16 | FAIL |
| 50ma | 3.30 | ss | 27 | 22.94 | FAIL | 11.37 | FAIL |
| 50ma | 3.30 | ss | 125 | 21.58 | FAIL | 12.34 | FAIL |
| 50ma | 3.30 | ff | -40 | 24.18 | FAIL | 11.14 | FAIL |
| 50ma | 3.30 | ff | 27 | 23.18 | FAIL | 11.05 | FAIL |
| 50ma | 3.30 | ff | 125 | 21.80 | FAIL | 11.74 | FAIL |
| 50ma | 3.30 | sf | -40 | 24.78 | FAIL | 11.65 | FAIL |
| 50ma | 3.30 | sf | 27 | 23.68 | FAIL | 11.47 | FAIL |
| 50ma | 3.30 | sf | 125 | 22.23 | FAIL | 12.16 | FAIL |
| 50ma | 3.30 | fs | -40 | 23.00 | FAIL | 10.53 | FAIL |
| 50ma | 3.30 | fs | 27 | 22.19 | FAIL | 10.91 | FAIL |
| 50ma | 3.30 | fs | 125 | 20.95 | FAIL | 11.93 | FAIL |
| 50ma | 3.63 | tt | -40 | 24.95 | FAIL | 11.78 | FAIL |
| 50ma | 3.63 | tt | 27 | 23.91 | FAIL | 11.46 | FAIL |
| 50ma | 3.63 | tt | 125 | 22.52 | FAIL | 11.95 | FAIL |
| 50ma | 3.63 | ss | -40 | 24.94 | FAIL | 11.83 | FAIL |
| 50ma | 3.63 | ss | 27 | 23.89 | FAIL | 11.61 | FAIL |
| 50ma | 3.63 | ss | 125 | 22.51 | FAIL | 12.22 | FAIL |
| 50ma | 3.63 | ff | -40 | 25.24 | FAIL | 11.96 | FAIL |
| 50ma | 3.63 | ff | 27 | 24.17 | FAIL | 11.44 | FAIL |
| 50ma | 3.63 | ff | 125 | 22.76 | FAIL | 11.70 | FAIL |
| 50ma | 3.63 | sf | -40 | 25.73 | FAIL | 12.40 | FAIL |
| 50ma | 3.63 | sf | 27 | 24.56 | FAIL | 11.81 | FAIL |
| 50ma | 3.63 | sf | 125 | 23.09 | FAIL | 12.10 | FAIL |
| 50ma | 3.63 | fs | -40 | 24.11 | FAIL | 11.16 | FAIL |
| 50ma | 3.63 | fs | 27 | 23.21 | FAIL | 11.13 | FAIL |
| 50ma | 3.63 | fs | 125 | 21.93 | FAIL | 11.80 | FAIL |
