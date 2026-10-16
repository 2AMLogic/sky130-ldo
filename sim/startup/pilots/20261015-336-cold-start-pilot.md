# Startup ESR-grid cold-start pilot (issue #336, step 1)

**This is NOT an evidence record.** It is a single-corner wiring/independence
pilot for the 12-leg C_out x load x ESR startup grid; no PVT campaign was run,
no `records/` entry is minted, and nothing here qualifies the ratified Startup
row. The full append-only 45-point campaign is step 2 of #336 and is pending
(see sim/README.md, "Startup ESR grid (issue #336)").

- Date: 2026-10-15; base commit `0181bad` + the #336 change.
- Corner: tt, 27 C, VIN 3.30 V (one corner, one local `ngspice -b` process, ~5 s).
- Tools: ngspice-42; xschem 3.4.7 netlist produced by `klt netlist` (klt 0.7.1.dev515);
  sky130A open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b` (matches sim/pdk.json).
- Deck: `corner_run.build_deck` output, declared leg order. Checker settings: the
  manifest's `ramp_monotonicity` block, `tolerance_v = 0` (strict, unchanged).

## What the pilot establishes

1. **Independent cold starts.** The deck was run twice, in declared leg order and
   in exactly reversed leg order. All 36 `meas_*` values are identical and all 12
   raw `V(VOUT)` traces are byte-identical (same sha256) across the two orders,
   so no leg inherits state from its predecessor.
2. **Traces produced and graded.** 12 `wrdata` traces (time, V(VOUT)), 442 lines each,
   graded by `ramp_monotonicity.py` (traces are scratch files, reproducible from the
   deck; only their sha256 prefixes are kept below). Worst sample gap 10 us, >= 66 samples between enable and window entry.
3. **ESR = 0 is a real boundary.** The `CDIR` branch carries the full C_out in the
   ESR = 0 legs (no stand-in resistor); ESR = 0 and 10 mOhm legs differ in the
   6th digit, ESR = 500 mOhm differs in the 4th-5th.

## Per-leg results (tt / 27 C / 3.30 V)

| leg | vpk (V) | vfloor (V) | tramp (ms) | max drawdown (uV) | worst gap (us) | window samples | ramp verdict | trace sha256[:16] |
|---|---|---|---|---|---|---|---|---|
| `c330n_0ma_esr0` | 1.81257 | 1.80711 | 0.3274 | 31.65 | 10 | 67 | FAIL | `fd46b65d93500ec6` |
| `c330n_0ma_esr10m` | 1.81257 | 1.80711 | 0.3274 | 31.66 | 10 | 67 | FAIL | `98b780a07aa895d6` |
| `c330n_0ma_esr500m` | 1.81258 | 1.80712 | 0.3274 | 32.01 | 10 | 67 | FAIL | `d9b5d07c65c98788` |
| `c330n_50ma_esr0` | 1.79885 | 1.79884 | 0.3477 | 19.80 | 10 | 70 | FAIL | `8fde4d7c64a2d546` |
| `c330n_50ma_esr10m` | 1.79885 | 1.79884 | 0.3477 | 19.80 | 10 | 70 | FAIL | `9bed68c6dbb4ed03` |
| `c330n_50ma_esr500m` | 1.79885 | 1.79884 | 0.3478 | 19.88 | 10 | 70 | FAIL | `bff2d20207f6821a` |
| `c4u7_0ma_esr0` | 1.81745 | 1.81706 | 0.3205 | 2.22 | 10 | 67 | FAIL | `8cc23479e99bcfeb` |
| `c4u7_0ma_esr10m` | 1.81745 | 1.81707 | 0.3205 | 2.23 | 10 | 67 | FAIL | `57aafb58a396e8a0` |
| `c4u7_0ma_esr500m` | 1.81762 | 1.81723 | 0.3211 | 2.66 | 10 | 66 | FAIL | `1ca21444d4634c0b` |
| `c4u7_50ma_esr0` | 1.79883 | 1.79883 | 0.3339 | 2.15 | 10 | 68 | FAIL | `79b470e6d5cef06a` |
| `c4u7_50ma_esr10m` | 1.79883 | 1.79883 | 0.3339 | 2.16 | 10 | 68 | FAIL | `90e2b96338068c28` |
| `c4u7_50ma_esr500m` | 1.79883 | 1.79883 | 0.3341 | 2.62 | 10 | 71 | FAIL | `097efdcf13bd7e8c` |

Ratified bounds (unchanged): vpk <= 1.836 V, vfloor >= 1.764 V — every leg is
inside both at this corner.

## Honest finding: strict monotonicity FAILs on all 12 legs

Every leg FAILs the strict `tolerance_v = 0` ramp-monotonicity check with a
2-32 uV drawdown in the first ~18 us after the enable edge (t = 100.1-118 us), while
VOUT is still at the sub-mV pre-ramp level. This is the same behaviour #309
recorded as its first single-corner observation for the four 10 mOhm legs (see
sim/README.md, "Startup ramp monotonicity"); the ESR boundaries neither remove
nor materially worsen it (largest at 0.33 uF, ~32 uV; ESR changes it by < 0.5 uV
within any (C_out, load) pair). The tolerance is deliberately NOT raised: whether such a dip is acceptable, and over what
window, is the open decision-record question in sim/README.md. Until a decision
record answers it, a campaign at `tolerance_v = 0` will record these legs as FAIL.
