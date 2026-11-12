# ff bisection upper bound lowered to 180 C (issue #231, operator ruling option a)

- ff decks at 190 C abort with `timestep_too_small` (all three supplies, hot and
  cold_exc; 6 points x 3 rounds = 18 lines in `failures.jsonl`). 190 C is outside what the sky130 device
  models solve for ff: a PDK-model extrapolation limit, not a spec change.
- ff bisection upper bound lowered to 180 C (highest ff grid point that converges);
  other 12 corners keep the 190 C grid. Solver options untouched. Recorded in
  `result.json` as `grid_top_c`.
- ff IS bracketed under 180 C at all three supplies (trip 173.6-179.8 C, reset
  160.5-166.7 C). ff_2.97V trip bracket is [179.69, 180] C, i.e. at the bound
  edge: the trip is found, but there is no margin above it.
- All 15 corners: min hysteresis (trip_lo - reset_hi) = 12.19 C > 2 C; lowest trip
  = 161.9 C (>= 150 C floor, DR-005). Thresholds unchanged. Hot/cold_exc
  scenarios only; tol 0.3125 C.

## Added by the dependent round (this record, `20261112-095143-16b7450c-qual-15corner-dependent`)

This record is a copy of `20261105-202028-97cd9a9e-qual-15corner` (which stays
byte-unchanged) resumed on the batch route; the 354 staircase points and the
failure lines above are carried over, and 328 cold-start / EN re-enable /
amplitude points were added (#541 route, 682 points total).

- Cold-start, EN re-enable (DR-005) and disturbance-amplitude points exist at all
  15 corners. Cold start is untripped below each corner's T_reset bracket and
  tripped above it; after the EN dip the state equals the state before it (nothing
  latches); amplitude points flip at the recorded bracket edges. States are
  recorded; no threshold is applied or relaxed.
- ff_2.97V `cold@188C` and `en@188C` fail with `timestep_too_small` (2 more lines
  in `failures.jsonl`). 188 C is above the lowered ff bound, so dependent points
  above it are not required or retried (`beyond_grid_top_not_run` in
  `result.json`); ff_3.30V `cold@185C` and ff_3.63V points converged and are kept.
  Same extrapolation limit as above; solver options untouched.
- Process note: the first resume skipped the three ff corners' dependent points
  because `corner_brackets` planned on the full grid (fixed in
  `sim/thermal/run_hysteresis.py`, with a test); the second resume added them.
  The first incomplete summary is kept as `result-incomplete-104154.json`.
