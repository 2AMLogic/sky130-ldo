# Per-net resistance-source table — leg: pinned

- klt build: klt 0.7.1.dev2457+gdc136150a49e
- klt_git_commit (response provenance): None
- GDS: layout/ldo-core/reports/20261112-110237-820ba8b3/ldo_core.gds (sha256 5e6171873b24b8d4c7af6f55d59600d84099cd13790c8320d8ccf074e657c1ca, response provenance.input.content_hash: sha256:5e6171873b24b8d4c7af6f55d59600d84099cd13790c8320d8ccf074e657c1ca)
- flags: klt pex <gds> --extract-only --deck sky130 --top ldo_core --pdk sky130A --resistance-graph --resistance-graph-r-cut 9.3 --format json (exit 4 = --extract-only's documented success)
- stderr: empty (0 bytes; see pex.stderr.log)

**Graph-derived nets: 0 of 28.** Sources: legacy=28

**Fallback reason/diagnostic emitted by this build: NONE.** No per-net reason field exists anywhere in the response (`extraction.resistance_graph.nets[]` entries carry exactly `net`, `net_id`, `resistance_source`, `selected_resistance_ohm`, `legacy_resistance_ohm`), and stderr is empty. Which mechanism blocked each legacy net (unsupported_geometry vs graph_too_large vs other) is not observable from tool output — filed upstream as klayout-tools#5747 (generic). This absence is itself a finding, recorded explicitly rather than left blank per AC-3 (revised).

| net | net_id | resistance_source | selected_resistance_ohm | legacy_resistance_ohm | fallback_reason |
|---|---|---|---|---|---|
| EA_TAIL | 1 | legacy | 7210.162 | 7210.162 | (no field emitted) |
| TS_CMP | 2 | legacy | 6427.6234 | 6427.6234 | (no field emitted) |
| RC_B | 3 | legacy | 8906.2011 | 8906.2011 | (no field emitted) |
| RC_A | 4 | legacy | 9472.4823 | 9472.4823 | (no field emitted) |
| TS_SNS | 5 | legacy | 8585.9631 | 8585.9631 | (no field emitted) |
| TS_REF | 6 | legacy | 5366.0559 | 5366.0559 | (no field emitted) |
| RC_TAIL | 7 | legacy | 4134.573 | 4134.573 | (no field emitted) |
| ENB | 8 | legacy | 2604.8425 | 2604.8425 | (no field emitted) |
| SS | 9 | legacy | 3625.335 | 3625.335 | (no field emitted) |
| TS_MID | 10 | legacy | 9177.3001 | 9177.3001 | (no field emitted) |
| CL_CMP | 11 | legacy | 3616.1224 | 3616.1224 | (no field emitted) |
| EA_D1 | 12 | legacy | 7128.9576 | 7128.9576 | (no field emitted) |
| EA_D2 | 13 | legacy | 8198.6003 | 8198.6003 | (no field emitted) |
| PB | 14 | legacy | 8473.0159 | 8473.0159 | (no field emitted) |
| CL_SNS | 15 | legacy | 3846.9258 | 3846.9258 | (no field emitted) |
| BIASP | 16 | legacy | 12009.641 | 12009.641 | (no field emitted) |
| AMP_ENN | 17 | legacy | 11403.3919 | 11403.3919 | (no field emitted) |
| BIAS_ENN | 18 | legacy | 1927.3301 | 1927.3301 | (no field emitted) |
| EN | 19 | legacy | 5629.0714 | 5629.0714 | (no field emitted) |
| EA_OUT | 20 | legacy | 30455.2525 | 30455.2525 | (no field emitted) |
| NB | 21 | legacy | 4517.6009 | 4517.6009 | (no field emitted) |
| FB | 22 | legacy | 2273.6971 | 2273.6971 | (no field emitted) |
| N_FBB | 23 | legacy | 768.4729 | 768.4729 | (no field emitted) |
| EA_CZ | 25 | legacy | 487.7233 | 487.7233 | (no field emitted) |
| VIN | 26 | legacy | 162687.7448 | 162687.7448 | (no field emitted) |
| VOUT | 27 | legacy | 153284.1077 | 153284.1077 | (no field emitted) |
| VREF | 28 | legacy | 1375.8883 | 1375.8883 | (no field emitted) |
| 0 | 29 | legacy | 3001.2008 | 3001.2008 | (no field emitted) |
