# Full-LDO evidence with the DR-013 `R_BIAS` candidate: 20261029-fullloop-467

Issue #467 / DR-013. Candidate = `R_BIAS` `res_xhigh_po` W=0.42 L=211 in place of `res_high_po` W=0.42 L=1500
(`candidate-R_BIAS.patch`, applied to `design/ldo_3v3in_1v8out.sch` for the runs only; the schematic of record is NOT changed by this PR).

## Iq: full 45-point PVT matrix (batch fleet)

Method: `sim/iq` deck, 200 ms cold-start transients, graded locally with the experiment's own bounds
(`iq_no_load_ua = -1e6*i(vvin)`, `iq_full_load_ua = 1e6*(-i(vvin)-0.05)`, both `< 30`; vout in 1.764-1.836 V).
Executed with `sim/bin/corner-run.py sim/iq --backend batch --timeout 1500`. The first attempt
(`sim/iq/records/20261029-063823-5ba605f.md`) is a recorded FAIL: every unit hit the 300 s per-unit cap (`klt` diagnostic `timeout`),
no values. The second attempt's runner process died after 4 of 6 requests had returned; the last two requests were completed by hand with
`klt sim --attach` / a direct `klt sim` submit of the runner's own request files (`requests/*.json`; the netlists are in `sim/iq/klt-request-netlists/20261029-063823-5ba605f.*`, identical bytes), raw responses in `responses/`.
Because the runner did not finish, **no `corner-run` record or manifest exists for this run**: `iq-graded.json` and the table below are a
manual aggregate of the six raw klt responses (45/45 points `pass` at the engine level, 0 errors). Treat as screening evidence, not a minted record.

Summary: no-load Iq 10.5 - 17.2 uA (all in budget); full-load Iq 23.3 - 31.9 uA; vout in window at all 45 points;
**6 of 45 points exceed 30 uA at full load** (ff/125C/3.30V 30.2; ff/-40C/3.63V 31.2; ff/27C/3.63V 31.6; ff/125C/3.63V 31.9; fs/27C/3.63V 30.2; fs/125C/3.63V 30.4).
`iq_full_load_ua` is quantised at ~0.1 uA (a ~1e-7 A difference of two 50 mA-scale numbers).
No same-method baseline run of the unmodified schematic was made for Iq (a second 45-point x 2 grid costs ~1.5 h of fleet time), so the
excess is **not attributed**: the bias-only grid (`../20261029-bias-grid-467`) shows the candidate raises bias current by up to +8.4 % at 125 C, which
is in the direction of the exceedances at the hot / high-VIN points, but that is consistent with, not proof of, the cause.

| process | T(C) | VIN | Iq no-load (uA) | Iq full-load (uA) | >30? |
|---|---|---|---|---|---|
| ff | -40 | 2.97 | 11.36 | 28.0 |  |
| ff | 27 | 2.97 | 12.03 | 28.3 |  |
| ff | 125 | 2.97 | 12.66 | 28.5 |  |
| fs | -40 | 2.97 | 10.51 | 26.6 |  |
| fs | 27 | 2.97 | 11.19 | 26.8 |  |
| fs | 125 | 2.97 | 11.82 | 27.0 |  |
| sf | -40 | 2.97 | 12.02 | 24.6 |  |
| sf | 27 | 2.97 | 12.64 | 25.1 |  |
| sf | 125 | 2.97 | 13.19 | 25.6 |  |
| ss | -40 | 2.97 | 11.22 | 23.3 |  |
| ss | 27 | 2.97 | 11.86 | 23.8 |  |
| ss | 125 | 2.97 | 12.43 | 24.3 |  |
| tt | -40 | 2.97 | 11.23 | 25.5 |  |
| tt | 27 | 2.97 | 11.89 | 25.9 |  |
| tt | 125 | 2.97 | 12.49 | 26.2 |  |
| ff | -40 | 3.30 | 13.27 | 29.6 |  |
| ff | 27 | 3.30 | 13.97 | 29.9 |  |
| ff | 125 | 3.30 | 14.61 | 30.2 | **FAIL** |
| fs | -40 | 3.30 | 12.36 | 28.2 |  |
| fs | 27 | 3.30 | 13.07 | 28.5 |  |
| fs | 125 | 3.30 | 13.73 | 28.7 |  |
| sf | -40 | 3.30 | 14.00 | 26.3 |  |
| sf | 27 | 3.30 | 14.64 | 26.8 |  |
| sf | 125 | 3.30 | 15.19 | 27.3 |  |
| ss | -40 | 3.30 | 13.19 | 25.1 |  |
| ss | 27 | 3.30 | 13.84 | 25.6 |  |
| ss | 125 | 3.30 | 14.42 | 26.1 |  |
| tt | -40 | 3.30 | 13.15 | 27.1 |  |
| tt | 27 | 3.30 | 13.83 | 27.6 |  |
| tt | 125 | 3.30 | 14.43 | 27.9 |  |
| ff | -40 | 3.63 | 15.22 | 31.2 | **FAIL** |
| ff | 27 | 3.63 | 15.95 | 31.6 | **FAIL** |
| ff | 125 | 3.63 | 16.60 | 31.9 | **FAIL** |
| fs | -40 | 3.63 | 14.26 | 29.9 |  |
| fs | 27 | 3.63 | 15.00 | 30.2 | **FAIL** |
| fs | 125 | 3.63 | 15.68 | 30.4 | **FAIL** |
| sf | -40 | 3.63 | 16.03 | 28.0 |  |
| sf | 27 | 3.63 | 16.67 | 28.6 |  |
| sf | 125 | 3.63 | 17.22 | 29.1 |  |
| ss | -40 | 3.63 | 15.22 | 27.0 |  |
| ss | 27 | 3.63 | 15.89 | 27.5 |  |
| ss | 125 | 3.63 | 16.47 | 28.0 |  |
| tt | -40 | 3.63 | 15.11 | 28.9 |  |
| tt | 27 | 3.63 | 15.81 | 29.3 |  |
| tt | 125 | 3.63 | 16.42 | 29.7 |  |

## PSRR and stability: single corner only

`corner-run.py` refuses `--backend batch` for `psrr-dc` and `loop-gain`, and local grids are not permitted on the dispatch host, so these are
ONE debug corner (tt / 27 C / 3.30 V), not PVT evidence: records `sim/psrr-dc/records/20261029-092008-5ba605f.md`,
`sim/loop-gain/records/20261029-092024-5ba605f.md` (both overall FAIL, as the latest prior records are: DR-007's known gaps).

| metric (tt/27C/3.30V) | prior record 20260926-033606 (psrr) | candidate |
|---|---|---|
| PSRR 1 kHz @1 mA / @50 mA (dB) | 23.23 / 23.33 | 23.21 / 23.31 |
| PSRR 100 kHz @1 mA / @50 mA (dB) | 33.52 / 11.32 | 33.52 / 11.31 |

Loop gain, same-method baseline (unmodified schematic, run with `--no-write` at this corner) vs candidate: PM 0.33 uF/10 m/50 mA 40.48 -> 40.54 deg,
GM 17.51 -> 17.53 dB, fc 178.3 -> 178.1 kHz, PM 0.33 uF/0 mA 19.66 -> 19.63 deg, PM 4.7 uF/1 mA 51.86 -> 51.84 deg. No movement at this corner.
The ss/ff/-40/125 C and supply-extreme behaviour of PSRR and stability is NOT established.
