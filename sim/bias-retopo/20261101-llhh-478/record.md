# DR-013 `ll`/`hh` resistor-skew Iq corners and merged 63-point re-tabulation: 20261101-llhh-478

Issue #478 (follow-up to #467 / DR-013). Append-only: `../20261029-fullloop-467/` is not edited; this record adds the
18 points that record omitted and re-tabulates the carried Iq FAILs at the **unchanged bound** (`< 30 uA`, DR-009; vout 1.764-1.836 V).

Candidate = DR-013 `R_BIAS` `res_xhigh_po` W=0.42 L=211, the same `../20261029-fullloop-467/candidate-R_BIAS.patch`, applied to
`design/ldo_3v3in_1v8out.sch` in the worktree for the run only and reverted (the schematic of record is NOT changed). The request
netlists (`requests/*.spice`) show `XR_BIAS VIN NB 0 sky130_fd_pr__res_xhigh_po W=0.42 L=211`.

## Method

`python3 sim/bin/corner-run.py sim/iq --backend batch --process ll,hh --timeout 1500 --no-write --subset-reason "..."`: same `sim/iq` deck
(two 200 ms cold-start transients per corner, no load then 50 mA), same grading expressions, same bounds as the 45-point record.
18 points = {ll, hh} x {-40, 27, 125 C} x {2.97, 3.30, 3.63 V}, as 6 `klt sim --backend batch` requests (one per VIN x load endpoint,
`requests/`; raw responses and batch receipts in `responses/`). All 6 jobs completed (`state: done`), 0 errored points; no local fallback
was used. `--no-write` was used on purpose: a `sim/iq/records/` entry would label candidate-schematic numbers as the design of record's.
`corner-run` exited 2 (overall FAIL) because of the Iq exceedances below. Graded figures are the runner's, copied from its console output
(`iq_full_load_ua` is quantised at ~0.1 uA, a difference of two 50 mA-scale numbers).

## Result: `ll`/`hh` Iq (18 points)

- `hh`: 9/9 in budget. No-load 9.9-14.4 uA, full-load 24.1-27.7 uA.
- `ll`: no-load 13.1-19.2 uA (all in budget); full-load 27.3-32.4 uA, **4 of 9 over 30 uA**:
  ll/-40C/3.63V 31.3, ll/27C/3.63V 31.9, ll/125C/3.30V 30.3, ll/125C/3.63V 32.4.
- vout in window at all 18 points (1.7984-1.8072 V).

`ll` (low-resistance skew) is the worst new corner and holds the worst full-load Iq of the whole matrix (32.4 uA, above the 31.9 uA
the 45-point record showed). The omission therefore mattered: the carried FAIL is 10 of 63, not 6 of 45.

## Merged 63-point table (45 from `../20261029-fullloop-467/`, 18 from this record)

Row count: 63 (5 process x 3 T x 3 VIN = 45, plus 2 x 3 x 3 = 18). Sorted by VIN, process, T.

| process | T(C) | VIN | Iq no-load (uA) | Iq full-load (uA) | >30? | source |
|---|---|---|---|---|---|---|
| tt | -40 | 2.97 | 11.23 | 25.5 |  | 467 |
| tt | 27 | 2.97 | 11.89 | 25.9 |  | 467 |
| tt | 125 | 2.97 | 12.49 | 26.2 |  | 467 |
| ss | -40 | 2.97 | 11.22 | 23.3 |  | 467 |
| ss | 27 | 2.97 | 11.86 | 23.8 |  | 467 |
| ss | 125 | 2.97 | 12.43 | 24.3 |  | 467 |
| ff | -40 | 2.97 | 11.36 | 28.0 |  | 467 |
| ff | 27 | 2.97 | 12.03 | 28.3 |  | 467 |
| ff | 125 | 2.97 | 12.66 | 28.5 |  | 467 |
| sf | -40 | 2.97 | 12.02 | 24.6 |  | 467 |
| sf | 27 | 2.97 | 12.64 | 25.1 |  | 467 |
| sf | 125 | 2.97 | 13.19 | 25.6 |  | 467 |
| fs | -40 | 2.97 | 10.51 | 26.6 |  | 467 |
| fs | 27 | 2.97 | 11.19 | 26.8 |  | 467 |
| fs | 125 | 2.97 | 11.82 | 27.0 |  | 467 |
| ll | -40 | 2.97 | 13.05 | 27.3 |  | 478 |
| ll | 27 | 2.97 | 13.83 | 27.8 |  | 478 |
| ll | 125 | 2.97 | 14.56 | 28.3 |  | 478 |
| hh | -40 | 2.97 | 9.87 | 24.1 |  | 478 |
| hh | 27 | 2.97 | 10.43 | 24.4 |  | 478 |
| hh | 125 | 2.97 | 10.93 | 24.7 |  | 478 |
| tt | -40 | 3.30 | 13.15 | 27.1 |  | 467 |
| tt | 27 | 3.30 | 13.83 | 27.6 |  | 467 |
| tt | 125 | 3.30 | 14.43 | 27.9 |  | 467 |
| ss | -40 | 3.30 | 13.19 | 25.1 |  | 467 |
| ss | 27 | 3.30 | 13.84 | 25.6 |  | 467 |
| ss | 125 | 3.30 | 14.42 | 26.1 |  | 467 |
| ff | -40 | 3.30 | 13.27 | 29.6 |  | 467 |
| ff | 27 | 3.30 | 13.97 | 29.9 |  | 467 |
| ff | 125 | 3.30 | 14.61 | 30.2 | **FAIL** | 467 |
| sf | -40 | 3.30 | 14.00 | 26.3 |  | 467 |
| sf | 27 | 3.30 | 14.64 | 26.8 |  | 467 |
| sf | 125 | 3.30 | 15.19 | 27.3 |  | 467 |
| fs | -40 | 3.30 | 12.36 | 28.2 |  | 467 |
| fs | 27 | 3.30 | 13.07 | 28.5 |  | 467 |
| fs | 125 | 3.30 | 13.73 | 28.7 |  | 467 |
| ll | -40 | 3.30 | 15.29 | 29.3 |  | 478 |
| ll | 27 | 3.30 | 16.09 | 29.8 |  | 478 |
| ll | 125 | 3.30 | 16.84 | 30.3 | **FAIL** | 478 |
| hh | -40 | 3.30 | 11.55 | 25.6 |  | 478 |
| hh | 27 | 3.30 | 12.14 | 25.9 |  | 478 |
| hh | 125 | 3.30 | 12.64 | 26.1 |  | 478 |
| tt | -40 | 3.63 | 15.11 | 28.9 |  | 467 |
| tt | 27 | 3.63 | 15.81 | 29.3 |  | 467 |
| tt | 125 | 3.63 | 16.42 | 29.7 |  | 467 |
| ss | -40 | 3.63 | 15.22 | 27.0 |  | 467 |
| ss | 27 | 3.63 | 15.89 | 27.5 |  | 467 |
| ss | 125 | 3.63 | 16.47 | 28.0 |  | 467 |
| ff | -40 | 3.63 | 15.22 | 31.2 | **FAIL** | 467 |
| ff | 27 | 3.63 | 15.95 | 31.6 | **FAIL** | 467 |
| ff | 125 | 3.63 | 16.60 | 31.9 | **FAIL** | 467 |
| sf | -40 | 3.63 | 16.03 | 28.0 |  | 467 |
| sf | 27 | 3.63 | 16.67 | 28.6 |  | 467 |
| sf | 125 | 3.63 | 17.22 | 29.1 |  | 467 |
| fs | -40 | 3.63 | 14.26 | 29.9 |  | 467 |
| fs | 27 | 3.63 | 15.00 | 30.2 | **FAIL** | 467 |
| fs | 125 | 3.63 | 15.68 | 30.4 | **FAIL** | 467 |
| ll | -40 | 3.63 | 17.56 | 31.3 | **FAIL** | 478 |
| ll | 27 | 3.63 | 18.38 | 31.9 | **FAIL** | 478 |
| ll | 125 | 3.63 | 19.15 | 32.4 | **FAIL** | 478 |
| hh | -40 | 3.63 | 13.28 | 27.0 |  | 478 |
| hh | 27 | 3.63 | 13.88 | 27.4 |  | 478 |
| hh | 125 | 3.63 | 14.39 | 27.7 |  | 478 |

**Summary: 10 of 63 points exceed 30 uA at full load** (6 from the 45-point record, 4 new, all `ll`); no-load Iq is in budget at all 63.
The bound is unchanged. Nothing here is loosened or re-judged.

## Attribution of the 10 exceedances (bias-only grid, `../20261029-bias-grid-467/record.md`)

The candidate changes only `R_BIAS`, so it can change Iq only through the bias current. The bias-only grid gives the candidate-vs-record
shift of the bias-pair current at every point (it covers `ll`/`hh` already). Where that shift is zero or negative, the candidate pushes
Iq *down* (or not at all), so the exceedance is not caused by it:

| point | Iq full-load (uA) | I_pair shift, candidate vs record | candidate-caused? |
|---|---|---|---|
| ff / -40C / 3.63 V | 31.2 | -0.45 % (4.6346 -> 4.6137 uA) | no (lowers it) |
| fs / 27C / 3.63 V | 30.2 | -0.34 % (4.5480 -> 4.5325 uA) | no (lowers it) |
| ll / -40C / 3.63 V | 31.3 | -2.85 % (5.4711 -> 5.3153 uA) | no (lowers it) |
| ll / 27C / 3.63 V | 31.9 | -0.08 % (5.4653 -> 5.4608 uA) | no (lowers it, negligibly) |
| ff / 125C / 3.30 V | 30.2 | +8.38 % (4.0380 -> 4.3766 uA) | can contribute |
| ff / 27C / 3.63 V | 31.6 | +2.37 % | can contribute |
| ff / 125C / 3.63 V | 31.9 | +8.40 % | can contribute |
| fs / 125C / 3.63 V | 30.4 | +5.54 % | can contribute |
| ll / 125C / 3.30 V | 30.3 | +5.80 % | can contribute |
| ll / 125C / 3.63 V | 32.4 | +5.81 % | can contribute |

So **4 of the 10 (2 of the original 6) cannot be candidate-caused**. For those, the design of record is **inferred** to be at or slightly
above the same value (the pair-current difference is only 0.005-0.16 uA; at most about that much higher, and for three of the four
within the ~0.1 uA quantisation of the full-load figure), i.e. already over 30 uA at ff/-40C/3.63 V, fs/27C/3.63 V and the two `ll` high-VIN cold/room points. This is an
inference from the bias-only grid, **not a measured baseline**: no same-method baseline Iq grid was run (not asked for; about 1.5 h of fleet
time per 45 points). Correction to the issue's wording: the issue's guess named ff/125C/3.30 V (30.2) as one of the two; that point has a
**+8.38 %** shift and is not ruled out, and the second non-candidate point of the original six is ff/-40C/3.63 V (31.2), not a hot one.

The other 6 points (all with a positive bias shift, five of them hot) are **not attributed**: the shift is in the direction of the
exceedance, which is consistent with, not proof of, the candidate causing it, and only a baseline run would separate the two.

## PSRR and stability: `ll`/`hh` are NOT established

`corner-run.py` still refuses `--backend batch` for `psrr-dc` and `loop-gain`, and local grids are not permitted on the dispatch host.
No `ll`/`hh` PSRR or loop-gain point was run for this record, and none is inferred. The PSRR / PM / GM evidence for the candidate
remains the single tt / 27 C / 3.30 V debug corner in `../20261029-fullloop-467/record.md`. A generic batch adapter for those two
experiments is a tool gap, not filed by this PR.
