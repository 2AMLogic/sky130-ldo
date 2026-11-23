#!/bin/sh
# Issue #706 -- declared command sequence, as executed (ALL grids on the Spot batch
# fleet via `klt sim`; local runs are strictly single-corner probes). Run from this
# directory. Deviations from the happy path are recorded inline below.
set -e

# --- 0. local syntax probe: one ngspice -b per variant, tt/27C/3.30V, iq bench ---
python3 campaign.py syntax-probe

# --- 1. clamp pair legs (quick tt/27C/3.30V chained batch probes) ---
# DEVIATION: the first cl-pair-base submission was refused by klt because the
# extra dc-curve card names embedded dots (klt requires measurement name ==
# .meas card name). Attempt kept in runs/attic-cl-pair-base-attempt1-cardname/;
# cards renamed (i_at_375mv, ...) and resubmitted.
python3 campaign.py cl-pair-base
python3 campaign.py cl-pair-cand

# --- 2. iq legs: full 45-point matrix per variant (validated #213 endpoint adapter) ---
python3 campaign.py iq-base
# DEVIATION: iq-base was interrupted mid-leg by a session tool timeout after 4/6
# responses; the in-flight job klt-sim-7ee8035068d3 completed remotely and was
# recovered with `klt sim <request> --attach klt-sim-7ee8035068d3 -o <outdir>`
# (run twice: once without PDK_ROOT, whose response named the wrong client-side
# PDK root and was discarded, once with PDK_ROOT=/home/ubuntu/.volare), then the
# leg was finished with the resume mode (submits only missing responses, grades
# all six through the harness's own endpoint normalizer):
python3 campaign.py iq-resume iq-base
python3 campaign.py iq-cand

# --- 3. clamp legs: full 45-point matrix per variant (#648 chained adapter, PR head) ---
python3 campaign.py cl-base
python3 campaign.py cl-cand

# --- 4. thermal: paired re-bisection of trip/reset over the 15 process x supply grid ---
# (bench's own DR-005 procedure, batch staircase, ~680 points per variant)
python3 thermal_pair.py --variant base
python3 thermal_pair.py --variant cand

# --- 5. analysis + records ---
python3 analyze.py
python3 write_records.py
