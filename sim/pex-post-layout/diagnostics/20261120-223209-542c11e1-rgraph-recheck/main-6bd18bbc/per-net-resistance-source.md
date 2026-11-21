# Per-net resistance-source / fallback_reason table — leg: main-6bd18bbc

- klt build: 0.9.3.dev2575+g6bd18bbc8637 (klayout_git_commit `6bd18bbc8637f6d767b3c24e77bd5db7a39e4bbe`, 2AMLogic/klayout-tools `main` 2026-11-20 — first build carrying #6130's per-net `fallback_reason`; no PyPI release contains it yet, newest is 0.9.2 of 2026-11-14)
- GDS: layout/ldo-core/reports/20261112-110205-820ba8b3/ldo_core.gds (sha256 `5e6171873b24b8d4c7af6f55d59600d84099cd13790c8320d8ccf074e657c1ca`, = provenance.input.content_hash; byte-identical to the 2026-11-14 diagnostic's input, so this leg differs from that one by build only)
- flags: `klt pex <gds> --extract-only --deck sky130 --top ldo_core --pdk sky130A --resistance-graph --resistance-graph-r-cut 9.3 --format json` (exit 4 = --extract-only's documented success; PDK_ROOT=~/.volare)
- stderr: empty (0 bytes; see pex.stderr.log)

**Graph-derived nets: 1 of 28** (unchanged from the 2026-11-14 diagnostic's release legs). Reason census: none=1, terminal_count_not_two=22, graph_too_large=3, graph_status_skipped=1, pair_resistance_unavailable=1 — sums to 28.

| net | net_id | resistance_source | fallback_reason | selected_resistance_ohm | legacy_resistance_ohm |
|---|---|---|---|---|---|
| 0 | 29 | legacy | terminal_count_not_two | 3001.2008 | 3001.2008 |
| AMP_ENN | 17 | legacy | terminal_count_not_two | 11403.3919 | 11403.3919 |
| BIASP | 16 | legacy | terminal_count_not_two | 12009.641 | 12009.641 |
| BIAS_ENN | 18 | legacy | terminal_count_not_two | 1927.3301 | 1927.3301 |
| CL_CMP | 11 | legacy | terminal_count_not_two | 3616.1224 | 3616.1224 |
| CL_SNS | 15 | legacy | terminal_count_not_two | 3846.9258 | 3846.9258 |
| EA_CZ | 25 | legacy | graph_status_skipped | 487.7233 | 487.7233 |
| EA_D1 | 12 | legacy | terminal_count_not_two | 7128.9576 | 7128.9576 |
| EA_D2 | 13 | legacy | terminal_count_not_two | 8198.6003 | 8198.6003 |
| EA_OUT | 20 | legacy | graph_too_large | 30455.2525 | 30455.2525 |
| EA_TAIL | 1 | legacy | terminal_count_not_two | 7210.162 | 7210.162 |
| EN | 19 | legacy | terminal_count_not_two | 5629.0714 | 5629.0714 |
| ENB | 8 | legacy | terminal_count_not_two | 2604.8425 | 2604.8425 |
| FB | 22 | legacy | terminal_count_not_two | 2273.6971 | 2273.6971 |
| NB | 21 | legacy | terminal_count_not_two | 4517.6009 | 4517.6009 |
| N_FBB | 23 | graph | (none — graph) | 806.421633163928 | 768.4729 |
| PB | 14 | legacy | terminal_count_not_two | 8473.0159 | 8473.0159 |
| RC_A | 4 | legacy | terminal_count_not_two | 9472.4823 | 9472.4823 |
| RC_B | 3 | legacy | terminal_count_not_two | 8906.2011 | 8906.2011 |
| RC_TAIL | 7 | legacy | terminal_count_not_two | 4134.573 | 4134.573 |
| SS | 9 | legacy | terminal_count_not_two | 3625.335 | 3625.335 |
| TS_CMP | 2 | legacy | terminal_count_not_two | 6427.6234 | 6427.6234 |
| TS_MID | 10 | legacy | terminal_count_not_two | 9177.3001 | 9177.3001 |
| TS_REF | 6 | legacy | terminal_count_not_two | 5366.0559 | 5366.0559 |
| TS_SNS | 5 | legacy | terminal_count_not_two | 8585.9631 | 8585.9631 |
| VIN | 26 | legacy | graph_too_large | 162687.7448 | 162687.7448 |
| VOUT | 27 | legacy | graph_too_large | 153284.1077 | 153284.1077 |
| VREF | 28 | legacy | pair_resistance_unavailable | 1375.8883 | 1375.8883 |
