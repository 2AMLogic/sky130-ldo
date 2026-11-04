# DR-013 alternative (a): smaller `R_BIAS` plus mirror ratio, simulated: 20261104-ratio-a-492

Issue #492 (operator ruling r5-q42; parent #467 / DR-013). Append-only: nothing earlier is edited. The bounds are the unchanged ratified
rows (Iq `< 30 uA` DR-009; PSRR > 50 dB @1 kHz, > 20 dB @100 kHz; PM >= 45 deg; GM >= 10 dB). No spec row or bound is changed; DR-013 stays `proposed`.

## Candidate and ratio (one ratio run)

`candidate-ratio-a.patch` (applied to `design/ldo_3v3in_1v8out.sch` for netlisting/runs only, then reverted; the schematic of record is unchanged):

- `R_BIAS` stays `res_high_po` W=0.42 and goes **L=1500 -> L=750** (no new resistor type), i.e. about half the resistance, so the reference branch
  (`R_BIAS` -> `M_BIASN1`, gated by `M_ENN`) carries about **k = 2** times the current.
- `M_BIASN2` goes **W=4 -> W=2** (mirror 1:1 -> 1:0.5), so the current mirrored into `M_BIASP1`/the bias tail is nominally unchanged.

Why k = 2: it is the smallest integer ratio that halves the resistor (a straight body of 751 um instead of 1501 um) with an exact W ratio on the
mirror (W=2 vs W=4, same L, so no L-dependent ratio error). Larger k saves more resistor but adds more reference current to Iq (below); a smaller k
saves less area. **k = 2 misses Iq on its face (21 of 63 points, worst 34.4 uA), so the issue's optional second ratio is open; it was not run**
(reason below). The reference branch current is `(k-1)` times the mirrored pair current *extra*, and this branch current is **not** in the
pre-existing pair/tail path; the measured Iq delta vs the candidate is +0.4 to +3.5 uA at full load, consistent with that.

Harness: `sim/bin/bias-retopo-pvt.py` gained a `--patch` option (default unchanged) so the PSRR/loop runner can netlist this patch; its generated
record headers still print the fixed #467 text ("Issue #467", "res_xhigh_po" in the `Design:` line); those two lines were corrected by hand in
the new dirs `../20261104-psrr-ratio-a-492/` and `../20261104-loop-ratio-a-492/`. The design there is this ratio-a patch.

## Method (same as the candidate's runs; all on the Spot batch fleet, no local grids, no local fallback)

- Iq: `python3 sim/bin/corner-run.py sim/iq --backend batch --timeout 1500 --no-write ...` (45 points) and the same with `--process ll,hh` (18 points). Same
  `sim/iq` deck, grading, models, bounds as `../20261029-fullloop-467/` and `../20261101-llhh-478/`. 12 `klt sim --backend batch` requests, all completed,
  0 errored points. Consoles: `iq45.console`, `iqllhh.console`; requests `requests/iq45`, `requests/iqllhh`; raw responses `responses/iq45-klt-out`, `responses/iqllhh-klt-out`.
  `--no-write` on purpose (a `sim/iq/records/` entry would label candidate numbers as the design of record's). `corner-run` exited 2 (overall FAIL) on the Iq exceedances.
- PSRR and loop gain: `python3 sim/bin/bias-retopo-pvt.py psrr|loop --patch <patch>` -> `../20261104-psrr-ratio-a-492/`, `../20261104-loop-ratio-a-492/` (same legs, 45 points, same translation as `20261101-psrr-pvt-467`, `20261101-loop-pvt-467`).
  All submits completed, 0 failed submits.

## Iq: 63-point table, (a) beside the candidate's numbers (candidate from `../20261101-llhh-478/record.md` merged table)

**(a) k=2: 21 of 63 points exceed 30 uA at full load** (candidate: 10 of 63). 6 are at VIN 3.30 V and 15 at 3.63 V; none at 2.97 V. By process: tt 3,
ff 6, sf 3, fs 3, ll 6, ss 0, hh 0. Worst **34.4 uA at ll/27C/3.63V** (candidate worst 32.4 uA, ll/125C/3.63V). Full-load delta vs the candidate is +0.4 to +3.5 uA;
no-load delta +0.5 to +3.4 uA; **no-load stays in budget at all 63** (max 20.9 uA, ll/27C/3.63V). vout is in window (1.764-1.836 V) at all 63 points
(full-load 1.7983-1.7991 V; no-load up to 1.8166 V at fs/125C/3.63V, inside). Every point graded by the runner; none "not defined".

| process | T(C) | VIN | cand no-load (uA) | (a) no-load (uA) | cand full-load (uA) | (a) full-load (uA) | delta full (uA) | (a) >30? |
|---|---|---|---|---|---|---|---|---|
| tt | -40 | 2.97 | 11.23 | 12.92 | 25.5 | 27.1 | +1.6 |  |
| tt | 27 | 2.97 | 11.89 | 13.42 | 25.9 | 27.4 | +1.5 |  |
| tt | 125 | 2.97 | 12.49 | 13.47 | 26.2 | 27.2 | +1.0 |  |
| ss | -40 | 2.97 | 11.22 | 12.76 | 23.3 | 24.9 | +1.6 |  |
| ss | 27 | 2.97 | 11.86 | 13.30 | 23.8 | 25.3 | +1.5 |  |
| ss | 125 | 2.97 | 12.43 | 13.39 | 24.3 | 25.2 | +0.9 |  |
| ff | -40 | 2.97 | 11.36 | 13.18 | 28.0 | 29.8 | +1.8 |  |
| ff | 27 | 2.97 | 12.03 | 13.65 | 28.3 | 29.9 | +1.6 |  |
| ff | 125 | 2.97 | 12.66 | 13.65 | 28.5 | 29.5 | +1.0 |  |
| sf | -40 | 2.97 | 12.02 | 14.55 | 24.6 | 27.1 | +2.5 |  |
| sf | 27 | 2.97 | 12.64 | 14.89 | 25.1 | 27.4 | +2.3 |  |
| sf | 125 | 2.97 | 13.19 | 14.74 | 25.6 | 27.2 | +1.6 |  |
| fs | -40 | 2.97 | 10.51 | 11.45 | 26.6 | 27.5 | +0.9 |  |
| fs | 27 | 2.97 | 11.19 | 12.08 | 26.8 | 27.7 | +0.9 |  |
| fs | 125 | 2.97 | 11.82 | 12.31 | 27.0 | 27.4 | +0.4 |  |
| ll | -40 | 2.97 | 13.05 | 15.03 | 27.3 | 29.3 | +2.0 |  |
| ll | 27 | 2.97 | 13.83 | 15.61 | 27.8 | 29.6 | +1.8 |  |
| ll | 125 | 2.97 | 14.56 | 15.69 | 28.3 | 29.4 | +1.1 |  |
| hh | -40 | 2.97 | 9.87 | 11.42 | 24.1 | 25.6 | +1.5 |  |
| hh | 27 | 2.97 | 10.43 | 11.87 | 24.4 | 25.8 | +1.4 |  |
| hh | 125 | 2.97 | 10.93 | 11.90 | 24.7 | 25.6 | +0.9 |  |
| tt | -40 | 3.30 | 13.15 | 15.19 | 27.1 | 29.3 | +2.2 |  |
| tt | 27 | 3.30 | 13.83 | 15.68 | 27.6 | 29.4 | +1.8 |  |
| tt | 125 | 3.30 | 14.43 | 15.63 | 27.9 | 29.1 | +1.2 |  |
| ss | -40 | 3.30 | 13.19 | 15.07 | 25.1 | 27.0 | +1.9 |  |
| ss | 27 | 3.30 | 13.84 | 15.60 | 25.6 | 27.4 | +1.8 |  |
| ss | 125 | 3.30 | 14.42 | 15.59 | 26.1 | 27.2 | +1.1 |  |
| ff | -40 | 3.30 | 13.27 | 15.45 | 29.6 | 31.8 | +2.2 | **FAIL** |
| ff | 27 | 3.30 | 13.97 | 15.90 | 29.9 | 31.8 | +1.9 | **FAIL** |
| ff | 125 | 3.30 | 14.61 | 15.80 | 30.2 | 31.3 | +1.1 | **FAIL** |
| sf | -40 | 3.30 | 14.00 | 16.99 | 26.3 | 29.2 | +2.9 |  |
| sf | 27 | 3.30 | 14.64 | 17.28 | 26.8 | 29.5 | +2.7 |  |
| sf | 125 | 3.30 | 15.19 | 17.00 | 27.3 | 29.1 | +1.8 |  |
| fs | -40 | 3.30 | 12.36 | 13.56 | 28.2 | 29.4 | +1.2 |  |
| fs | 27 | 3.30 | 13.07 | 14.21 | 28.5 | 29.6 | +1.1 |  |
| fs | 125 | 3.30 | 13.73 | 14.36 | 28.7 | 29.3 | +0.6 |  |
| ll | -40 | 3.30 | 15.29 | 17.68 | 29.3 | 31.6 | +2.3 | **FAIL** |
| ll | 27 | 3.30 | 16.09 | 18.24 | 29.8 | 31.9 | +2.1 | **FAIL** |
| ll | 125 | 3.30 | 16.84 | 18.20 | 30.3 | 31.7 | +1.4 | **FAIL** |
| hh | -40 | 3.30 | 11.55 | 13.43 | 25.6 | 27.4 | +1.8 |  |
| hh | 27 | 3.30 | 12.14 | 13.86 | 25.9 | 27.6 | +1.7 |  |
| hh | 125 | 3.30 | 12.64 | 13.80 | 26.1 | 27.3 | +1.2 |  |
| tt | -40 | 3.63 | 15.11 | 17.51 | 28.9 | 31.3 | +2.4 | **FAIL** |
| tt | 27 | 3.63 | 15.81 | 17.98 | 29.3 | 31.5 | +2.2 | **FAIL** |
| tt | 125 | 3.63 | 16.42 | 17.83 | 29.7 | 31.1 | +1.4 | **FAIL** |
| ss | -40 | 3.63 | 15.22 | 17.46 | 27.0 | 29.2 | +2.2 |  |
| ss | 27 | 3.63 | 15.89 | 17.97 | 27.5 | 29.6 | +2.1 |  |
| ss | 125 | 3.63 | 16.47 | 17.86 | 28.0 | 29.3 | +1.3 |  |
| ff | -40 | 3.63 | 15.22 | 17.77 | 31.2 | 33.8 | +2.6 | **FAIL** |
| ff | 27 | 3.63 | 15.95 | 18.19 | 31.6 | 33.8 | +2.2 | **FAIL** |
| ff | 125 | 3.63 | 16.60 | 18.00 | 31.9 | 33.3 | +1.4 | **FAIL** |
| sf | -40 | 3.63 | 16.03 | 19.48 | 28.0 | 31.5 | +3.5 | **FAIL** |
| sf | 27 | 3.63 | 16.67 | 19.72 | 28.6 | 31.7 | +3.1 | **FAIL** |
| sf | 125 | 3.63 | 17.22 | 19.31 | 29.1 | 31.2 | +2.1 | **FAIL** |
| fs | -40 | 3.63 | 14.26 | 15.73 | 29.9 | 31.4 | +1.5 | **FAIL** |
| fs | 27 | 3.63 | 15.00 | 16.39 | 30.2 | 31.6 | +1.4 | **FAIL** |
| fs | 125 | 3.63 | 15.68 | 16.47 | 30.4 | 31.2 | +0.8 | **FAIL** |
| ll | -40 | 3.63 | 17.56 | 20.38 | 31.3 | 34.1 | +2.8 | **FAIL** |
| ll | 27 | 3.63 | 18.38 | 20.92 | 31.9 | 34.4 | +2.5 | **FAIL** |
| ll | 125 | 3.63 | 19.15 | 20.77 | 32.4 | 34.0 | +1.6 | **FAIL** |
| hh | -40 | 3.63 | 13.28 | 15.48 | 27.0 | 29.2 | +2.2 |  |
| hh | 27 | 3.63 | 13.88 | 15.90 | 27.4 | 29.4 | +2.0 |  |
| hh | 125 | 3.63 | 14.39 | 15.75 | 27.7 | 29.0 | +1.3 |  |

## Where it fails, and what that implies for the next ruling

(a) also fails Iq at the low-R / hot / high-VIN corners, and it fails **more** points and **worse** than the candidate, including `tt` (3 points, 31.1-31.5 uA at 3.63 V)
and the cold `sf`/`fs`/`ff` points that the candidate passed. Plainly: the `< 30 uA` bound is not met by (a) at k=2 across PVT. The reference-branch current that the
ratio adds is the cost; it is the same mechanism that makes the candidate's Iq sensitive to the resistor's low skew (`ll` worst in both). The candidate already
carries 4 of its 10 exceedances that it cannot have caused (#478 attribution), so the full-load Iq of this topology family is at the bound at high VIN even before the bias
change; the evidence therefore points at the **30 uA bound at VIN 3.63 V (or the load-current share of Iq) together with DR-007**, not at the resistor choice.
That attribution is an inference from the numbers here and in #478, not a measured baseline of the design of record (none was run).

A second ratio was not run: the extra reference-branch current grows with k, so Iq is expected (inferred, not measured) to rise with k: the candidate (single branch, about k=1) fails 10/63 and k=2 fails 21/63, so a k between them would be expected to land between those counts and k>2 to be worse. A k<2 run would be expected only to interpolate and would buy less resistor area; the ruling bounds the sweep at two ratios *if the first
misses Iq*, and the answer needed (does (a) beat the candidate on Iq) is already no. This is a judgement, flagged for the next ruling; the operator can ask for it.

## PSRR and phase margin (same legs/points as the candidate's; full tables in the new dirs)

PSRR (worst over 45 points; candidate's value from `20261101-psrr-pvt-467`):

| load | freq | (a) worst PSRR (dB) | candidate worst (dB) | bound |
|---|---|---|---|---|
| 1 mA | 100 kHz | 31.86 (fs/-40C/3.63V) | 31.81 | > 20 PASS both |
| 1 mA | 1 kHz | 19.57 (fs/125C/2.97V) | 20.64 | > 50 FAIL both |
| 50 mA | 100 kHz | 10.07 (fs/-40C/2.97V) | 10.38 | > 20 FAIL both |
| 50 mA | 1 kHz | 19.76 (fs/125C/2.97V) | 20.79 | > 50 FAIL both |

Loop gain (worst PM over 45 points per leg; the table in `../20261104-loop-ratio-a-492/record.md`): total PM < 45 deg points **212 (a) vs 197 (candidate)**; GM < 10 dB points **0 vs 0**.
Worst PM at c033/esr0/0 mA: 14.76 deg (fs/-40C/2.97V) vs 15.18 deg; c033/esr0/50 mA: 31.01 vs 31.25 deg; c47/esr0/0 mA: 36.06 vs 37.09 deg. Counts of unavailable metrics differ
(PM at 0 points here vs 6 candidate; GM at 45 here vs 51 for the candidate; klt `transfer_metric_unavailable`, never counted as a pass). The pre-existing DR-007 PSRR / stability gaps are **unchanged
in kind and slightly worse** with (a): PSRR at the worst points is lower by up to about 1.1 dB at 1 kHz and 0.3 dB at 50 mA/100 kHz (about equal at 1 mA/100 kHz), worst PM by 0.2-1.0 deg. (a) does not close any DR-007 gap.
Leg `loop-c47-esr500m-1ma` printed `error` per VIN in the runner for GM (no -180 deg phase crossing, `GM n/a`), the same as the candidate's record; PM exists at 45 of 45.

## EN=0 leakage of the added branch vs the ~150 pA floor

The ratio change adds no new device: the reference branch (`R_BIAS`/`M_BIASN1`) already exists and is gated by `M_ENN`, `M_BIASN2` is just narrower. Measured with the existing
`sim/enable-shutdown` deck (same method, graded by the runner) at the single worst-leakage corner **ff/125C/3.63V**, run locally as one unit (`--backend local`; the
batch backend does not support this experiment, and a 45-point grid is not permitted locally on the dispatch host, so only this one corner was run; `enshut-ff125-3.63.console`):
`iq_shutdown_static_ua` = 0.0863 uA (**86 pA**, below the ~150 pA floor), after-edge 0.0392 uA, VIN->VOUT leakage 0.103 uA, PASS on the deck's own bounds
(3 uA / 1 uA). Other corners are **not established**; this is a one-corner check, hot-fast being the expected worst case for leakage but not proven here.

## Current-ratio matching on `M_BIASN1/N2`

The pinned PDK (`c6d73a35...`) **does** carry a mismatch model for `nfet_g5v0d10v5`. In `sky130_fd_pr__nfet_g5v0d10v5__mismatch.corner.spice`, `vth0_slope = 0.000`, but
`toxe_slope = 0.80e-2` (`toxe_slope2 = 1.00e-2` for the W=3 L=1 um bin), `voff_slope = 0.13` and `nfactor_slope = 0.12` are nonzero (`invariant.spice` agrees on `nfactor_slope`).
sky130 models device mismatch mainly through `toxe`, `voff` and `nfactor`, not `vth0`. A Monte Carlo mismatch run is therefore **available on this pin and was not run here**.
No sigma was derived from these parameters. The +-1/3/10 % ratio errors below are an **assumed range, not a PDK-derived or measured sigma**; the +-10 % figure is not shown to cover 3 sigma
for a W=2 L=1 thick-oxide device (an order-of-magnitude estimate suggests 3 sigma could be 15-30 %; not measured). The mirror here is W=4 (N1) vs W=2 (N2), same L=1, ratio 2:1
by area; the smaller device (W=2) has the larger relative mismatch (sigma ~ 1/sqrt(W*L)), a factor sqrt(2) over a 1:1 W=4 pair. Effect on Iq: the pair current enters Iq one-for-one at least,
and the bias-only grid (`../20261029-bias-grid-467/record.md`) puts I_pair at about 4.0-5.5 uA, so a ratio error of d changes I_pair by d x I_pair: **+-1% -> +-0.04 to +-0.06 uA; +-3% -> +-0.12 to +-0.17 uA;
+-10% -> +-0.4 to +-0.55 uA; +-30% -> +-1.2 to +-1.65 uA**, before any downstream gain (not established here; the pair-to-Iq gain was not measured). No Monte Carlo was run. Against the 34.4 uA worst point,
a ratio error of that size moves Iq by less than the 4.4 uA overshoot even at +-30 %. A ratio error of either sign moves Iq either way, so mismatch **cannot rescue** (a); this conclusion does not depend on the PDK-sigma question.

## `R_BIAS` area and the Area row (`< 0.1 mm^2`)

Inputs: `layout/bin/ldo-area-budget-dr013.py` / `ldo-area-budget-4cap.py` (read-only; geometric estimate, no DRC/LVS/PEX, no layout drawn). Core rectangle width 439.48 um, height 184.17 um.
A straight `res_high_po` W=0.42 L=750 body is 751.28 um wide, **wider than the 439.48 um core**; as a straight resistor it costs 751.28 x 184.17 = 0.138 mm^2 (> 0.1) at the current height.
To fit, it must be **folded** (about 2 segments of ~376 um, which fit the width; the #459 N=4 strip is 375.84 um wide and adds 2144.7 um^2, giving 0.08308 mm^2 for the stacked-cap
scenarios, 0.0944/0.0962 mm^2 for the single-2fF counterfactuals). So: **Area `< 0.1 mm^2` holds only with a fold, and the fold is the unqualified #263 fold; the answer to "met without a fold waiver" is NO.**
(The N=2 strip would be no larger than the N=4 strip charged above, so 0.083 mm^2 is an upper bound for the folded case; not re-run as a new study.) The candidate's `res_xhigh_po` L=211 is a single straight body (no fold), which is the only variant that avoids
the waiver. This is the one place where (a) loses to the candidate on a structural point, in addition to Iq.

## Not established

- A second ratio; Monte Carlo of the mirror (available on this pin, not run); EN=0 leakage at the other 44 corners; a measured baseline Iq grid of the schematic of record; layout/DRC/LVS; the pair-to-Iq gain used for the mismatch figures.
- Whether the 30 uA bound or DR-007 is "the" issue: the numbers above are consistent with both, and the choice is the next ruling's.

## Reproduce

```bash
git apply sim/bias-retopo/20261104-ratio-a-492/candidate-ratio-a.patch   # netlisting/run only; `git checkout design` afterwards
python3 sim/bin/corner-run.py sim/iq --backend batch --timeout 1500 --no-write --subset-reason "..."
python3 sim/bin/corner-run.py sim/iq --backend batch --process ll,hh --timeout 1500 --no-write --subset-reason "..."
python3 sim/bin/bias-retopo-pvt.py psrr --patch sim/bias-retopo/20261104-ratio-a-492/candidate-ratio-a.patch --record-id <new>
python3 sim/bin/bias-retopo-pvt.py loop --patch sim/bias-retopo/20261104-ratio-a-492/candidate-ratio-a.patch --record-id <new>
```

Note: the per-corner `transfer_*.raw` waveform files klt kept for the loop run (about 50 MB) were deleted before commit, as in `../20261101-loop-pvt-467/`; every value traces to `../20261104-loop-ratio-a-492/responses/<key>/klt.stdout` and `summary.json`.
