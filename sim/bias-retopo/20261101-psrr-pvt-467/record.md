# PSRR PVT grid, dr013: 20261101-psrr-pvt-467

Issue #467 / DR-013. Executed through `klt sim --backend batch` (no local fallback); translation per the `sim/bin/bias-retopo-pvt.py` docstring. Bounds are the unchanged ratified spec rows. Graded locally from raw responses.
Design: `dr013` (`dr013` = `R_BIAS` res_xhigh_po W=0.42 L=211; `record` = schematic of record).
Points requested: 45; rows returned: 90; failed submits: 0.

## Worst case per metric

| load | freq | worst PSRR (dB) | at |
|---|---|---|---|
| 1ma | 100k | 31.81 | fs/-40C/3.63V |
| 1ma | 1k | 20.64 | fs/125C/2.97V |
| 50ma | 100k | 10.38 | fs/-40C/2.97V |
| 50ma | 1k | 20.79 | fs/125C/2.97V |

## All points

| load | VIN | process | T(C) | PSRR 1k (dB) | >50 | PSRR 100k (dB) | >20 |
|---|---|---|---|---|---|---|---|
| 1ma | 2.97 | tt | -40 | 23.02 | FAIL | 32.04 | PASS |
| 1ma | 2.97 | tt | 27 | 22.17 | FAIL | 33.52 | PASS |
| 1ma | 2.97 | tt | 125 | 21.04 | FAIL | 35.53 | PASS |
| 1ma | 2.97 | ss | -40 | 23.08 | FAIL | 32.01 | PASS |
| 1ma | 2.97 | ss | 27 | 22.20 | FAIL | 33.56 | PASS |
| 1ma | 2.97 | ss | 125 | 21.04 | FAIL | 35.56 | PASS |
| 1ma | 2.97 | ff | -40 | 23.16 | FAIL | 32.02 | PASS |
| 1ma | 2.97 | ff | 27 | 22.32 | FAIL | 33.55 | PASS |
| 1ma | 2.97 | ff | 125 | 21.18 | FAIL | 35.51 | PASS |
| 1ma | 2.97 | sf | -40 | 23.49 | FAIL | 32.07 | PASS |
| 1ma | 2.97 | sf | 27 | 22.59 | FAIL | 33.58 | PASS |
| 1ma | 2.97 | sf | 125 | 21.42 | FAIL | 35.55 | PASS |
| 1ma | 2.97 | fs | -40 | 22.51 | FAIL | 32.02 | PASS |
| 1ma | 2.97 | fs | 27 | 21.73 | FAIL | 33.53 | PASS |
| 1ma | 2.97 | fs | 125 | 20.64 | FAIL | 35.52 | PASS |
| 1ma | 3.30 | tt | -40 | 24.16 | FAIL | 31.99 | PASS |
| 1ma | 3.30 | tt | 27 | 23.21 | FAIL | 33.52 | PASS |
| 1ma | 3.30 | tt | 125 | 22.04 | FAIL | 35.52 | PASS |
| 1ma | 3.30 | ss | -40 | 24.22 | FAIL | 31.96 | PASS |
| 1ma | 3.30 | ss | 27 | 23.24 | FAIL | 33.53 | PASS |
| 1ma | 3.30 | ss | 125 | 22.04 | FAIL | 35.56 | PASS |
| 1ma | 3.30 | ff | -40 | 24.33 | FAIL | 32.01 | PASS |
| 1ma | 3.30 | ff | 27 | 23.39 | FAIL | 33.51 | PASS |
| 1ma | 3.30 | ff | 125 | 22.21 | FAIL | 35.49 | PASS |
| 1ma | 3.30 | sf | -40 | 24.59 | FAIL | 32.01 | PASS |
| 1ma | 3.30 | sf | 27 | 23.59 | FAIL | 33.54 | PASS |
| 1ma | 3.30 | sf | 125 | 22.38 | FAIL | 35.54 | PASS |
| 1ma | 3.30 | fs | -40 | 23.71 | FAIL | 31.97 | PASS |
| 1ma | 3.30 | fs | 27 | 22.82 | FAIL | 33.50 | PASS |
| 1ma | 3.30 | fs | 125 | 21.68 | FAIL | 35.51 | PASS |
| 1ma | 3.63 | tt | -40 | 25.11 | FAIL | 31.94 | PASS |
| 1ma | 3.63 | tt | 27 | 24.09 | FAIL | 33.49 | PASS |
| 1ma | 3.63 | tt | 125 | 22.87 | FAIL | 35.52 | PASS |
| 1ma | 3.63 | ss | -40 | 25.17 | FAIL | 31.91 | PASS |
| 1ma | 3.63 | ss | 27 | 24.11 | FAIL | 33.51 | PASS |
| 1ma | 3.63 | ss | 125 | 22.87 | FAIL | 35.56 | PASS |
| 1ma | 3.63 | ff | -40 | 25.34 | FAIL | 31.95 | PASS |
| 1ma | 3.63 | ff | 27 | 24.32 | FAIL | 33.47 | PASS |
| 1ma | 3.63 | ff | 125 | 23.09 | FAIL | 35.48 | PASS |
| 1ma | 3.63 | sf | -40 | 25.49 | FAIL | 31.96 | PASS |
| 1ma | 3.63 | sf | 27 | 24.42 | FAIL | 33.51 | PASS |
| 1ma | 3.63 | sf | 125 | 23.17 | FAIL | 35.53 | PASS |
| 1ma | 3.63 | fs | -40 | 24.71 | FAIL | 31.81 | PASS |
| 1ma | 3.63 | fs | 27 | 23.74 | FAIL | 33.47 | PASS |
| 1ma | 3.63 | fs | 125 | 22.56 | FAIL | 35.51 | PASS |
| 50ma | 2.97 | tt | -40 | 23.05 | FAIL | 10.64 | FAIL |
| 50ma | 2.97 | tt | 27 | 22.23 | FAIL | 11.12 | FAIL |
| 50ma | 2.97 | tt | 125 | 21.16 | FAIL | 12.23 | FAIL |
| 50ma | 2.97 | ss | -40 | 23.11 | FAIL | 10.81 | FAIL |
| 50ma | 2.97 | ss | 27 | 22.25 | FAIL | 11.36 | FAIL |
| 50ma | 2.97 | ss | 125 | 21.16 | FAIL | 12.54 | FAIL |
| 50ma | 2.97 | ff | -40 | 23.19 | FAIL | 10.57 | FAIL |
| 50ma | 2.97 | ff | 27 | 22.37 | FAIL | 10.91 | FAIL |
| 50ma | 2.97 | ff | 125 | 21.30 | FAIL | 11.90 | FAIL |
| 50ma | 2.97 | sf | -40 | 23.51 | FAIL | 10.90 | FAIL |
| 50ma | 2.97 | sf | 27 | 22.63 | FAIL | 11.27 | FAIL |
| 50ma | 2.97 | sf | 125 | 21.52 | FAIL | 12.33 | FAIL |
| 50ma | 2.97 | fs | -40 | 22.56 | FAIL | 10.38 | FAIL |
| 50ma | 2.97 | fs | 27 | 21.80 | FAIL | 10.97 | FAIL |
| 50ma | 2.97 | fs | 125 | 20.79 | FAIL | 12.12 | FAIL |
| 50ma | 3.30 | tt | -40 | 24.23 | FAIL | 11.26 | FAIL |
| 50ma | 3.30 | tt | 27 | 23.31 | FAIL | 11.28 | FAIL |
| 50ma | 3.30 | tt | 125 | 22.21 | FAIL | 12.04 | FAIL |
| 50ma | 3.30 | ss | -40 | 24.28 | FAIL | 11.39 | FAIL |
| 50ma | 3.30 | ss | 27 | 23.34 | FAIL | 11.48 | FAIL |
| 50ma | 3.30 | ss | 125 | 22.21 | FAIL | 12.34 | FAIL |
| 50ma | 3.30 | ff | -40 | 24.40 | FAIL | 11.30 | FAIL |
| 50ma | 3.30 | ff | 27 | 23.48 | FAIL | 11.16 | FAIL |
| 50ma | 3.30 | ff | 125 | 22.37 | FAIL | 11.77 | FAIL |
| 50ma | 3.30 | sf | -40 | 24.64 | FAIL | 11.55 | FAIL |
| 50ma | 3.30 | sf | 27 | 23.67 | FAIL | 11.46 | FAIL |
| 50ma | 3.30 | sf | 125 | 22.53 | FAIL | 12.17 | FAIL |
| 50ma | 3.30 | fs | -40 | 23.79 | FAIL | 10.97 | FAIL |
| 50ma | 3.30 | fs | 27 | 22.93 | FAIL | 11.10 | FAIL |
| 50ma | 3.30 | fs | 125 | 21.88 | FAIL | 11.92 | FAIL |
| 50ma | 3.63 | tt | -40 | 25.20 | FAIL | 11.97 | FAIL |
| 50ma | 3.63 | tt | 27 | 24.21 | FAIL | 11.60 | FAIL |
| 50ma | 3.63 | tt | 125 | 23.07 | FAIL | 12.01 | FAIL |
| 50ma | 3.63 | ss | -40 | 25.25 | FAIL | 12.07 | FAIL |
| 50ma | 3.63 | ss | 27 | 24.23 | FAIL | 11.76 | FAIL |
| 50ma | 3.63 | ss | 125 | 23.06 | FAIL | 12.27 | FAIL |
| 50ma | 3.63 | ff | -40 | 25.42 | FAIL | 12.11 | FAIL |
| 50ma | 3.63 | ff | 27 | 24.43 | FAIL | 11.58 | FAIL |
| 50ma | 3.63 | ff | 125 | 23.29 | FAIL | 11.80 | FAIL |
| 50ma | 3.63 | sf | -40 | 25.57 | FAIL | 12.27 | FAIL |
| 50ma | 3.63 | sf | 27 | 24.53 | FAIL | 11.79 | FAIL |
| 50ma | 3.63 | sf | 125 | 23.35 | FAIL | 12.14 | FAIL |
| 50ma | 3.63 | fs | -40 | 24.81 | FAIL | 11.67 | FAIL |
| 50ma | 3.63 | fs | 27 | 23.87 | FAIL | 11.40 | FAIL |
| 50ma | 3.63 | fs | 125 | 22.78 | FAIL | 11.88 | FAIL |
