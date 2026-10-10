# #263 resume attempts, 2026-10-10 (append-only)

All runs batch-only (`KLT_SIM_BACKEND=batch`), no local grid.

| record | client | result |
|---|---|---|
| 20261010-053334-24f4faf | klt 0.6.0, .meas form | det batch job klt-sim-e47f924ea292: 63/63 pass (raw `det.report.json`). Session killed by a daemon version roll before the MC request and summary; no summary.json. |
| 20261010-065609-0eb9b4b | klt 0.7.0 | BLOCKED: fleet runner klt 0.5.0, all 63 units `batch_runner_version_mismatch` (job klt-sim-0d2e93937003). |
| 20261010-065704-0eb9b4b | klt 0.6.0, .meas form | det batch job klt-sim-9ba5cf558fc7: 63/63 pass (raw `det.report.json`). Run was cut off by a tool timeout before MC; no summary.json. |
| 20261010-070658-0eb9b4b | klt 0.6.0, .meas form | BLOCKED: no capacity in any of the 30 pools after 3 attempts. |

The seeded-mismatch (Monte Carlo) request has not completed in any attempt, so gates M1/M2
are unevaluated and no segment-count recommendation or no-qualified-candidate verdict is made.
The raw deterministic reports are kept as evidence only; they have not been analysed against the gates.
Re-run `python3 layout/bin/run-folded-res-pvt.py` once the fleet runner matches the client and has capacity.
