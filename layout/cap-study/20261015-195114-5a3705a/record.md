# Capacitor-implementation comparison: 20261015-195114-5a3705a

Issue #341 (completion of the #319 study). **Study only.** Nothing in `spec/`, `design/` or any other record changes. The earlier record `20261011-094917-7a4e0cc/` is untouched (append-only).

**Outcome: (c) inconclusive/unmeasured**, with 105 of 126 operating points now measured. See the last section.

`matrix.json` is the machine-readable form. `python3 layout/cap-study/run-cap-study.py matrix --record <this dir>` regenerates it.

## Provenance

- Minted 2026-10-15 on top of `5a3705a` (branch `feature/issue-341`). PDK, schematic and testbench are the same as in `20261011-094917-7a4e0cc/record.md` (pinned `sky130A`).
- Precondition: `python3 sim/bin/batch-preflight.py` returned **ACCEPTED (exit 0)**, job `klt-sim-7edd87355ae4`, runner klt `0.7.0`, client klt `0.7.1.dev517+gebd6e9c71ae3`, compatibility `match`.
- All multi-corner work went to `klt sim --backend batch`. Nothing was run locally. No local fallback was used for the failed jobs.

## Batch results

| Request | Points | Result | Job |
|---|---|---|---|
| `v2.97_0ma` | 21 | pass | `klt-sim-5a3d732619fe` |
| `v2.97_50ma` | 21 | pass | `klt-sim-15be82ea1e79` |
| `v3.30_0ma` | 21 | pass | `klt-sim-a0281fc9c741` |
| `v3.30_50ma` | 21 | pass | `klt-sim-149c592ada42` |
| `v3.63_0ma` | 21 | pass | `klt-sim-649f18677223` |
| `v3.63_50ma` | 21 | **not run** (no response, no job) | none |
| C(V) grid (`cv --backend batch`, 7 corners x 3 temperatures) | 21 | **not run** (no response, no job) | none |

Both failures have the same cause, recorded in each `submission.json`: the fleet provisioner refused the launch because the shared fleet was already at its cap (`9 instance(s) already running + 1 requested exceeds BATCH_MAX_CONCURRENT_INSTANCES=8` for `v3.63_50ma`; `8 ... + 1` for the C(V) job). This is a fleet-capacity refusal, not a runner/client version mismatch: preflight and five jobs ran on the same runner. The driver does not retry a failed job and skips an already-submitted one on rerun (append-only), so these two were left as recorded.

## Measured

Capacitor plate voltage ranges over the 105 measured points (`matrix.json`, `options[mos_varactor].plate_voltage_range`; all marked `complete: false`):

| Cap | min (V) | max (V) |
|---|---|---|
| C_COMP | -1.67026 | 1.19618 |
| C_CL | 0.0 | 0.84252 |
| C_SS | 2.96344 | 3.63 |
| C_TS | 0.0223 | 0.0476 |

Verdicts from `matrix.json`: `mim_stacked` fits (conditional, #254 drawn evidence), `vpp` does-not-fit, `mim_m3_1` and `mos_varactor` not-established.

## Outcome: (c) inconclusive/unmeasured

**Missing evidence (the `evidence_gaps` in `matrix.json`):**

1. The 21 operating points of `v3.63_50ma` (3.63 V supply, 50 mA load, 7 process corners x 3 temperatures): `unmeasured`, reason: batch launch refused by the fleet instance cap.
2. The varactor C(V) grid: 21/21 corner x temperature runs missing, same reason. The varactor verdict therefore stays `not-established`.
3. The varactor cell footprint (no fixed PDK cell, no klt generator; klayout-tools#3100) and a priced mixed placement for one-level MiM. Both are unchanged from the earlier record.

Missing data never becomes outcome (b). No decision record is proposed and the spec is unchanged.

**Next measurement:** in a new record directory, submit `v3.63_50ma` and `cv --backend batch` when the fleet has free capacity. Tracked in #341.
