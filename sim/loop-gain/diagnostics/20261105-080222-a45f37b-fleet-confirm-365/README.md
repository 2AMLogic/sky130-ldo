# Fleet confirmation of #365's baseline / R_CZ x16 loop-gain pairs (issue #370, stage 1)

Append-only. Driver: `sim/bin/rcz-fleet-confirm.py` (tests: `sim/tests/test_rcz_fleet_confirm_370.py`).
Source commit a45f37b0; design schematic and every earlier record untouched.

## Preflight (AC1)

`python3 sim/bin/batch-preflight.py` on 2026-11-05: **ACCEPTED (exit 0)**, job `klt-sim-2b1fecc16147`,
runner klt 0.9.0, client 0.9.1.dev17+gd76e6fe1cb7a, compatibility match. No evidence written by the probe.

## What ran

20 single-corner (tt / 27 C / 3.30 V, the condition #365 ran) AC requests, one per design x leg
(baseline and R_CZ L 52 -> 832 um, the 10 #365 legs), each through `klt sim --backend batch`
(`requests/`, raw `responses/`, job ids in `summary.json`). No local fallback was used; 0 submit errors, all 20
jobs completed. Translation reuses the #467 pattern (one linear VCVS, klt `transfer` metrics PM/GM/fc/DC gain),
not #365's `let`/`cph` control script, so this also cross-checks the two extractions.

## Result (AC2, AC pairs): CONFIRMED

All 20 legs reproduce #365's local numbers within 0.4 deg PM / 0.6 dB GM (full table: `comparison.md`).
The mechanism holds on the fleet: R_CZ x16 lifts 0 mA margin at 0.33 uF (PM 19.7 -> 65.0) and 4.7 uF
(53.1 -> 60.1) at every ESR boundary, but collapses loaded margins (1 mA: 82.5 -> 9.5 and 51.9 -> 30.8;
50 mA: 40.1 -> 10.1 and 83.2 -> 10.8 deg PM), so a fixed x16 is rejected and a light-load-only R_CZ is
still the open question. Iq for the pair is not re-measured here (the edit adds no current element; #365 table).

## NOT run (recorded, cannot count as PASS)

- The #365 load-transient baseline/R_CZ x16 pair: the batch window-grid adapter is schematic-driven and has no
  netlist-variant path, so it was not re-run. #365's transient numbers stay PROVISIONAL.
- Everything beyond tt / 27 C / 3.30 V, and every physical-realization step (sense path, adaptive R_CZ,
  Iq, current limit, transition transient). Gate (AC2) is passed for the AC pairs only.

## Verdict / next step

Proceed is justified for AC loop-gain; a follow-up must (a) add a variant-netlist path for the batch transient
pair (or confirm it another way) before building on the transient numbers, then (b) screen one physical
sub-mA adaptive R_CZ realization. This PR is stage 1 only; production schematic, spec and DRs unchanged.
