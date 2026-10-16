# Capacitor-implementation comparison: 20261016-004951-5125358

Issue #341 (completion of the #319 study). **Study only.** Nothing in `spec/`, `design/` or any other record changes. The earlier records `20261011-094917-7a4e0cc/` and `20261015-195114-5a3705a/` are untouched (append-only).

**Outcome: (c) inconclusive/unmeasured.** The operating-point matrix (126/126) and the varactor C(V) grid (21/21) are now complete. The remaining gaps are not missing runs: see the last section.

`matrix.json` is the machine-readable form. `python3 layout/cap-study/run-cap-study.py matrix --record <this dir>` regenerates it.

## Provenance

- Minted 2026-10-16 on top of `5125358` (branch `feature/issue-341`). PDK, schematic and testbench are the same as in `20261011-094917-7a4e0cc/record.md` (pinned `sky130A`, open_pdks `c6d73a35...`).
- Precondition: `python3 sim/bin/batch-preflight.py` returned **ACCEPTED (exit 0)**, job `klt-sim-e86ce5fc2f5a`, runner klt `0.7.0`, client klt `0.7.1.dev558+g7d6433a83285`, compatibility `match`.
- All multi-corner work went to `klt sim --backend batch`. Nothing was run locally.

## Batch results

| Request | Points | Result | Job |
|---|---|---|---|
| `v2.97_0ma` | 21 | pass | `klt-sim-c506c36c9048` |
| `v2.97_50ma` | 21 | pass | `klt-sim-56be7b30d03a` |
| `v3.30_0ma` | 21 | pass | `klt-sim-f9f953eace41` |
| `v3.30_50ma` | 21 | pass | `klt-sim-8a751f49f8f1` |
| `v3.63_0ma` | 21 | pass | `klt-sim-4cd0ff1f5f36` |
| `v3.63_50ma` | 21 | pass | `klt-sim-1950371f8774` |
| C(V) grid (`cv --backend batch`, 7 corners x 3 temperatures) | 21 | pass | `klt-sim-c9f01fce5aef` |

No diagnostics on any of the 126 operating points. The fleet instance-cap refusals of the previous record did not recur.

**Interrupted submissions (disclosure).** The Builder's own background-task time limit stopped the driver process twice, so the driver was re-run to resume (it skips any request that already has a `submission.json`):

- During `v2.97_50ma`, in the first `op` run. No job id was captured and no artifacts were left. The re-run submitted it again and it returned as `klt-sim-56be7b30d03a`.
- During `v3.63_50ma`, in the second `op` run (90-minute cap). No job id was captured. The third run submitted it again and it returned as `klt-sim-1950371f8774`.

An interrupted client submit may have left a fleet job running whose result was discarded. These were client-side stops, not fleet refusals, and nothing was run locally. Individual requests took tens of minutes to return, in line with the slow returns noted on the issue.

## Measured

Capacitor plate voltage ranges over all 126 points (`matrix.json`, `options[mos_varactor].plate_voltage_range`, all `complete: true`):

| Cap | min (V) | max (V) |
|---|---|---|
| C_COMP | -1.67026 | 0.3708 |
| C_CL | 0.0 | 0.08895 |
| C_SS | 2.96344 | 3.63 |
| C_TS | 0.0223 | 0.0476 |

Verdicts from `matrix.json`: `mim_stacked` fits (conditional, #254 drawn evidence), `vpp` does-not-fit, `mim_m3_1` and `mos_varactor` not-established.

**Varactor.** Over the 126 points C_COMP, C_CL and C_TS stay inside the model's SOA (|V| <= 2.301 V) for both plate orientations, for all four devices swept (lvt/hvt, 10 x 10 and 5 x 0.5 um). **C_SS is outside the SOA** (its plate pair reaches 3.63 V), so its density is `unmeasured` and a plain accumulation varactor cannot hold C_SS at this supply. C at the 178273 Hz crossover differs from C at 1 kHz by at most 1.4e-3 relative (5 x 0.5 devices) and 1e-5 (10 x 10 devices).

## Difference from the previous record at one point

The same deck gave a different settled state at `ff / 27 C / 2.97 V / 50 mA` (`op/batch/v2.97_50ma`) than in `20261015-195114-5a3705a`. Of the 105 points present in both records, it is the only one whose C_CL plate voltage differs by more than 1 mV (only C_CL was compared across all points):

| | C_CL (VIN - CL_CMP) | C_COMP (VOUT - EA_CZ) |
|---|---|---|
| `20261015-195114-5a3705a` | 0.84252 V | 1.19618 V |
| this record | 0.07923 V | 0.13962 V |

This is why the C_CL and C_COMP maxima are lower here than in the previous record. The cause was not investigated (one run per point; the scope here is the evidence grid). It may be a start-up settling sensitivity at that corner. It does not change any verdict or the outcome, but that point's terminal voltages should not be treated as reproducible until it is re-run. Neither value was edited.

## Outcome: (c) inconclusive/unmeasured

Both measurement gaps of the previous record (the 21 `v3.63_50ma` points and the C(V) grid) are closed. The #319 rules still give (c), because the fit of two options is not established:

1. **One-level MiM (`mim_m3_1`):** beside the core it breaks the limit and it cannot all go over the core, but a mixed overlay-plus-beside placement has not been drawn or priced by any record.
2. **MOS varactor (`mos_varactor`):** the cell footprint is `unmeasured` (no fixed PDK cell, no klt generator, klayout-tools#3100). Only the gate-area lower bound is known (19713 um^2 at tt Cmax), and C_SS is outside the model SOA.

Missing data never becomes outcome (b). No decision record is proposed and the spec is unchanged.
