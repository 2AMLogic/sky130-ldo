# Issue #786 — paired reference-vs-fleet check, psrr-dc, TT / 27 °C / 3.30 V

Same checkout (`f6089144`), same host, local side on the pinned PDK (open_pdks `c6d73a35`, matches `sim/pdk.json`); fleet side see the caveat below.

| Side | Engine | Job |
|---|---|---|
| reference (`--backend local`) | ngspice-47, local | n/a |
| fleet (`--backend batch`) | ngspice-47 (binary sha256 `e12148ba…`, `engine_build_comparison: match`) | `klt-sim-7a400ce98ee7` (aws-batch-fleet, spot c7i.4xlarge, us-east-1) |

| Measurement | local | fleet | difference | grade |
|---|---|---|---|---|
| psrr_1khz_1ma_db (>50 dB) | 23.2333 | 23.2333 | 0 | FAIL |
| psrr_100khz_1ma_db (>20 dB) | 33.5185 | 33.5185 | 0 | PASS |
| psrr_1khz_50ma_db (>50 dB) | 23.3297 | 23.3297 | 0 | FAIL |
| psrr_100khz_50ma_db (>20 dB) | 11.3201 | 11.3201 | 0 | FAIL |
| vout_seed_1ma_v | 1.8006 | 1.8006 | 0 | n/a |
| vout_seed_50ma_v | 1.79883 | 1.79883 | 0 | n/a |

Values are the six-significant-digit figures the runner prints; no difference was visible at that precision, so
no tolerance is needed (the agreement bound is the print resolution, <1e-4 dB and <1e-5 V). The fleet's first/last AC points
(`-vdb(vout)[0]`, `[2]`) therefore agree with the reference's 1 kHz / 100 kHz readings at both loads, including
after `alter rload = 36`. Both sides grade FAIL overall; the circuit fails the PSRR bounds, as in the prior record.

## Caveat (not hidden)

The fleet worker's own PDK stamp is `open_pdks f6eeac7d…`, not the pin (`pdk_stamp_comparison: mismatch` in
`paired-batch-report.json`). The worker's `models_lib_comparison` is `match` (models lib sha256 `48de7c67…`),
and the numbers are identical to the local pinned run, so the pair is equivalent for this bench — but the stamp
mismatch is a property of the fleet image and is not resolved here.

Raw outputs: `paired-local-*.txt`, `paired-batch-*.txt`, `paired-batch-report.json`.
Full campaign: `../../records/20261125-113226-f6089144.md`.
