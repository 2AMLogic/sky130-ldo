# ff bisection upper bound lowered to 180 C (issue #231, operator ruling option a)

- ff decks at 190 C abort with `timestep_too_small` (all three supplies, hot and
  cold_exc; 12 lines in `failures.jsonl`). 190 C is outside what the sky130 device
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
- Not covered by this record: cold-start, EN-reenable, disturbance amplitude.
