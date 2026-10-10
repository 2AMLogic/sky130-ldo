# Execution attempts leading to this BLOCKED record (issue #263, 2026-10-10)

All attempts used `klt sim` through the batch fleet (`KLT_SIM_BACKEND=batch`).
No grid was run locally. Each attempt re-used the same predeclared matrix
(`matrix.json`); only the request form and client differed. The first four
were not minted as records because they never produced a valid request or
result (the driver was still being debugged); they are listed here so the
trail is complete.

| # | client | form | outcome |
|---|---|---|---|
| 1 | klt 0.7.0+g8eec069c7576 (host default) | `measurements[].expr` | det job `klt-sim-9344ec19fbec` and MC job `klt-sim-96679de3e39c` ran on Spot (c7i.4xlarge, us-east-1) for ~5 s and exited 87: runner klt 0.5.0 vs client 0.7.0, `batch_runner_version_mismatch`, every one of 63 + 3000 units `error`. No results. |
| 2 | klayout-tools 0.5.0 (`uvx`, matches the runner) | expr | client refuses `--backend batch` ("supported: local, local-parallel, remote"). |
| 3 | klayout-tools 0.6.0 (`uvx`) | expr | client refuses `measurements[].expr`. |
| 4 | klayout-tools 0.6.0 | `.meas dc` form (this record's request files) | this record: `batch-fleet-provision.sh launch failed ... no capacity in any of the 30 pools after 3 attempt(s)`. An identical retry about 100 s earlier (`20261010-045854-509c688`, discarded unminted) gave the same capacity refusal. |

Upstream tracker already covers the version skew and capacity visibility
(2AMLogic/klayout-tools#2948, #2851, #3015, #2894); nothing new was filed.
One additional generic gap observed here: `corners.supply_v` accepts a key
that names a `.param` and generates `alter <param>=<v>`, which ngspice 42
rejects ("no such device or model name"); klt still reports the corner as
`pass` and the voltage axis silently does nothing (this matches the
"silent no-op supply_v key" item in #2894, so it was not filed again; this
study works around it by using a named voltage source as the key).

## What was validated locally (single corner, debug probe only, not evidence)

One-corner `klt sim --backend local` runs (tt, 27 C, three voltage points; and a
2-sample mismatch run) confirmed the deck: R_BIAS N=1 = 1215106.716311 ohm and
R_FB N=1 = 1040766.37 ohm at 0.6 V reproduce the #253 record, the voltage axis
moves the xhigh value (1040766.415 / .372 / .328 ohm at 0.588 / 0.6 / 0.612 V),
and `tt_mm` draws differ between samples (resistor mismatch is live). The
`.meas` form quantises R to 1 ohm on ngspice 42 (about 8e-7 relative), small
against every gate in `matrix.json`.
