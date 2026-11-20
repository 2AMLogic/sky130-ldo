# Per-net resistance_graph status / reason / diagnostics — leg: extract-main-6bd18bbc

Companion `klt extract` leg on the same GDS, build and r-cut. The pex echo (`fallback_reason`) collapses the graph `status` + first diagnostic `code` into one token (`pex_resistance_graph._resistance_graph_fallback_reason`); this table carries the underlying `resistance_source_reason`, terminal count and diagnostic codes so each mechanism is named exactly.

- flags: `klt extract <gds> --deck sky130 --top ldo_core --pdk sky130A --parasitics --resistance-graph --resistance-graph-r-cut 9.3 -o ldo_core.extract.spice --format json` (exit 0; stderr is a benign progress line, kept in extract.stderr.log)
- build/GDS: identical to the pex leg (see main-6bd18bbc/)

| net | graph status | resistance_source_reason | terminals | nodes | edges | diagnostics |
|---|---|---|---|---|---|---|
| 0 | ok | terminal_count_not_two | 6 | 218 | 337 |  |
| AMP_ENN | ok | terminal_count_not_two | 11 | 366 | 563 |  |
| BIASP | ok | terminal_count_not_two | 15 | 710 | 1159 | terminals_disconnected |
| BIAS_ENN | ok | terminal_count_not_two | 3 | 102 | 155 |  |
| CL_CMP | ok | terminal_count_not_two | 5 | 215 | 349 | terminals_disconnected |
| CL_SNS | ok | terminal_count_not_two | 6 | 277 | 450 | terminals_disconnected |
| EA_CZ | skipped | graph_status_skipped | 1 | 53 | 82 | too_few_terminals |
| EA_D1 | ok | terminal_count_not_two | 6 | 277 | 450 | terminals_disconnected |
| EA_D2 | ok | terminal_count_not_two | 7 | 314 | 511 | terminals_disconnected |
| EA_OUT | unsupported | graph_status_unsupported | 0 | 0 | 0 | graph_too_large(108>64) |
| EA_TAIL | ok | terminal_count_not_two | 4 | 135 | 206 |  |
| EN | ok | terminal_count_not_two | 24 | 1143 | 1850 | terminals_disconnected |
| ENB | ok | terminal_count_not_two | 4 | 178 | 288 | terminals_disconnected |
| FB | ok | terminal_count_not_two | 4 | 212 | 346 | terminals_disconnected |
| NB | ok | terminal_count_not_two | 10 | 492 | 803 | terminals_disconnected |
| N_FBB | ok | two_terminal_graph | 2 | 103 | 162 |  |
| PB | ok | terminal_count_not_two | 7 | 314 | 511 | terminals_disconnected |
| RC_A | ok | terminal_count_not_two | 10 | 450 | 734 | terminals_disconnected |
| RC_B | ok | terminal_count_not_two | 8 | 351 | 572 | terminals_disconnected |
| RC_TAIL | ok | terminal_count_not_two | 3 | 102 | 155 |  |
| SS | ok | terminal_count_not_two | 4 | 178 | 288 | terminals_disconnected |
| TS_CMP | ok | terminal_count_not_two | 6 | 252 | 410 | terminals_disconnected |
| TS_MID | ok | terminal_count_not_two | 4 | 178 | 288 | terminals_disconnected |
| TS_REF | ok | terminal_count_not_two | 6 | 277 | 450 | terminals_disconnected |
| TS_SNS | ok | terminal_count_not_two | 6 | 277 | 450 | terminals_disconnected |
| VIN | unsupported | graph_status_unsupported | 0 | 0 | 0 | graph_too_large(77>64) |
| VOUT | unsupported | graph_status_unsupported | 0 | 0 | 0 | graph_too_large(metal1 poly0), graph_too_large(metal2 poly0) |
| VREF | ok | pair_resistance_unavailable | 2 | 98 | 156 | terminals_disconnected |
