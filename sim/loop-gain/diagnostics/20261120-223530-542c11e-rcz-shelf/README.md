# Frequency-dependent R_CZ screen for issue #691

**REVISE the screen.** The batch smoke request stopped during upload. Baseline and candidate each have 0 of 42 valid tt measurements. Worst phase margin and gain margin are unknown for both designs. The next run should measure this candidate as drawn. There is no electrical evidence yet for changing a component value. [Point-by-point tables](tables.md) · [Machine verdict](verdict.json)

## Candidate and rationale

The shelf candidate replaces the 52 µm R_CZ resistor with two series xhigh_po segments of the same 0.42 µm width. The first is 26 µm. The second is 806 µm with an 18 pF capacitor in parallel. At low frequencies their combined length is 832 µm, the ×16 choice that repaired zero and light load in the earlier screen. Using the earlier nominal 301 kΩ for 52 µm gives about 4.67 MΩ for the shunted section and a bypass pole near 1.9 kHz. [Earlier measurements](../20261105-125812-89a1200-adaptive-rcz/tables.md)

The hypothesis is that the two output capacitors can use the same network because they cross unity at different frequencies. At 100 µA the earlier baseline crossed near 0.96 kHz with 4.7 µF and 4.53 kHz with 0.33 µF. The bypass therefore reduces the compensation impedance more for the smaller output capacitor. At 0.33 µF and 50 mA the residual resistance approaches half the baseline value, targeting the separate heavy-load shortfall. These frequencies guided component selection. Every comparison in this screen requires new data. The passive network has no control state and adds no connection to the current-limit mirror. [Earlier AC data](../20261105-125812-89a1200-adaptive-rcz/summary.json)

## Batch refusal

The DUT source was pinned to `542c11e1959d6f174a8a69fdee2f8c13607c0844`. The client was `klt 0.9.2.dev111+g978f7464fae1`. The batch preflight exited 1. The client reserved submission ID `klt-sim-8c101d9cf1e8`, then AWS refused the S3 input upload because the worker lacked the `batch-runner-submit` profile. No runner started or reported a version. The capacity wait did not apply. [Probe output](preflight/probe.txt) · [Smoke request](preflight/batch-preflight-dn9wqeue/klt-requests/q1-tt_27c_1.80v.json) · [Batch stderr](preflight/batch-preflight-dn9wqeue/klt-out/q1-tt_27c_1.80v/klt.stderr)

Separately, an offline check netlisted the pinned schematic once and expanded all 118 possible batch requests with `klt sim --backend batch --dry-run`. Both decks contain the regenerative comparator. This checks the request grid and deck construction. It provides no electrical measurements.

## NOT run

- The 42 tt points per design require an accepted preflight. All 84 PM/GM pairs are unmeasured.
- The 56 ss/ff points per design require a complete passing candidate tt screen with matched baseline data. Each point uses 10 mΩ ESR at 3.30 V.
- Paired Iq at 0 and 50 mA and the rising and falling 1 ↔ 50 mA transients require both AC stages to clear. Switch-state and added mirror-load checks do not apply to this passive circuit.

## Reproduction

From the repository root, set `record` to this directory and regenerate its tables with `python3 -I sim/bin/rcz-shelf-691-report.py "$record"`. To collect a fresh screen on an enrolled batch worker, set `record` to a new diagnostics directory and run the following commands. The driver runs the smoke preflight and writes the fresh baseline before the candidate at each AC stage. The report reads only that directory's responses.

```sh
python3 sim/bin/rcz-shelf-691.py --outdir "$record"
python3 -I sim/bin/rcz-shelf-691-report.py "$record"
```
