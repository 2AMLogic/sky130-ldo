# Qualification note 20261123-709: EA_OUT/PB soft-release wake-shaping screen (issue #709, post-#714 follow-up)

**Status: qualification note (issue #709), not an evidence record.** Append-only
note under `sim/startup/pilots/`. This is the committed, reproducible screen the
2026-11-23 re-curation asked for: the ~100 us soft release of the EN-gated
clamps that #714's unrecoverable w1 scratch run (100 kOhm x 1 pF = **100 ns**,
unconfirmable gate, uncommitted deck) never measured. The graded evidence
remains the four fleet records named in the 20261121-709 note; nothing here
changes `tolerance_v`, the ratified Startup row, `spec/` or any decision record,
and no startup record, envelope or characterization output is superseded.

## Verdict (one line)

**The EA_OUT wake-shaping alternative is measured and REJECTED: at the
qualification time constant (tau = 100 us) every variant leaves the ramp
drawdown positive at every leg of both screen corners -- the strict
`tolerance_v = 0` monotonicity FAIL and the Startup signoff grade are unchanged
-- while the packet reduction is corner-inconsistent (best per-corner cuts of
70.2 % tt / 44.1 % sf, far short of the R_CZ screen's 85-88 %, itself
loop-gain-rejected), and stretching tau to 300 us makes the packet WORSE than
baseline (EA_OUT clamp) or breaks the ratified peak-overshoot bound by ~10 %
(PB clamp). Adoption of a compensation change therefore stays OPEN with no
qualifying candidate left on the issue: R_CZ L=180/520/1800 rejected
(loop-gain / startup screen), wake shaping rejected here, and the schematic
keeps `R_CZ` L=52. This satisfies the issue's rejection path ("a committed,
measured wake-shaping rejection fully satisfies the issue's rejection path").**

## The committed deck delta

The delta is `sim/bin/enp-soft-release-709.py` (this repository), applied to the
harness-minted startup corner deck; the script is the reproducible definition
and the sha256 of every deck it minted is recorded below. Gate connection and
values, exactly as they appear in the minted decks (the only netlist changes;
the rest of the deck is byte-identical to the baseline):

```
XM_ENP  EA_OUT GENP  VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=10 ...   (gate EN -> GENP)
RM_ENPS GENP   EN    100000
CM_ENPS GENP   VIN   1e-09            tau = R*C = 100 us      (300 us decks: C = 3e-09)

XM_ENP5 PB     GENP5 VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=2  ...   (gate EN -> GENP5)
RM_ENP5S GENP5 EN    100000
CM_ENP5S GENP5 VIN   1e-09            tau = R*C = 100 us      (300 us decks: C = 3e-09)
```

R = 100 kOhm gate-to-EN, C = tau/R gate-to-VIN (1 nF at 100 us, 3 nF at
300 us): with EN at 0 V the gate sits at 0 V (clamp fully on, identical to
baseline), and on the enable edge the gate rises toward VIN with tau, so the
clamp releases softly instead of with the 1 us EN edge. Variants: `enp` (EA_OUT
clamp `XM_ENP` only), `enp5` (PB clamp `XM_ENP5` only), `both`.

## Provenance

- Driver: `sim/bin/enp-soft-release-709.py`, which reuses corner-run.py's own
  `netlist_with_xschem` / `netlist_body` / `build_deck` / `run_corner`, so deck
  minting, the 12-leg window walk and all grading are the bench's own code path
  (per-leg `reset` + `alter` + cold-enable `tran 10u 4m` + `wrdata`).
- Grading: the bench's own checker via `run_corner` (ramp_monotonicity settings
  verbatim from `sim/startup/experiment.json`: t_enable 100 us, v_low 1.764 V,
  max_dt 20 us, min_samples 20, tolerance 0.0 V; vpk <= 1.836 V, vfloor >=
  1.764 V over 3.1-4 ms, tramp reported).
- Runs: local single-corner debug probes (`ngspice -b`, one sequential run per
  variant x corner, `.spiceinit` copied per the harness), production DUT at
  `R_CZ` L=52, repo state 8d3fc34e; PDK sky130A per `sim/pdk.json`; scratch
  under gitignored `sim/build/issue709-ws/`.
- Reproduction gate: the `base` variant reproduces #714's L=52 screen exactly
  (30.733 uV / 10.142 pC at tt c330n_0ma_esr10m; 65.492 uV / 21.612 pC at sf)
  and the tt base deck is **byte-identical to the #693 baseline deck** (sha256
  prefix `424a29ae`, the same prefix that pilot recorded).

## 1. Packet table (c330n/0mA/ESR10m, the #693/#714 screen metric)

Q = drawdown x C_out (0.33 uF); dd = drawdown. Every bounds column lists
vpk/vfloor/tramp for all 12 legs of that run.

| variant | tau | tt dd (uV) | tt Q (pC) | tt delta | sf dd (uV) | sf Q (pC) | sf delta | bounds |
|---|---|---|---|---|---|---|---|---|
| base | -- | 30.733 | 10.142 | -- | 65.492 | 21.612 | -- | pass (dd > 0: FAIL at tol 0) |
| enp (EA_OUT clamp) | 100 us | 16.248 | 5.362 | -47.2 % | 36.603 | 12.079 | -44.1 % | pass |
| enp5 (PB clamp) | 100 us | 9.163 | 3.024 | -70.2 % | 53.524 | 17.663 | -18.3 % | pass |
| both | 100 us | 13.350 | 4.406 | -56.6 % | 41.018 | 13.536 | -37.4 % | pass |
| enp | 300 us | 38.819 | 12.810 | **+26.3 %** | 72.621 | 23.965 | **+10.9 %** | pass; tramp blows out to 0.539/0.464 ms |
| enp5 | 300 us | 9.163 | 3.024 | -70.2 % | 53.524 | 17.663 | -18.3 % | **vpk FAIL: 2.013/2.035 V (tt), 1.926/1.955 V (sf) vs 1.836** |

Reference points: the R_CZ L=180 screen measured 1.226 pC (tt) / 3.140 pC (sf)
(-87.9 % / -85.5 %) and was loop-gain-rejected; #693's p3 (deleting `M_ENP5`
entirely) cut only ~35 %; #714's w1 (100 ns RC) cut 15.6 % / 1.3 %.

## 2. Full 12-leg tables, tau = 100 us (drawdown uV; Q = dd x C_out, pC)

tt/27C/3.30V (worst vpk over all legs/variants 1.8176 V vs 1.836 bound; worst
vfloor 1.79883 V vs 1.764; tramp 0.321-0.359 ms):

| leg | base | enp | enp5 | both |
|---|---|---|---|---|
| c330n_0ma_esr0 | 30.728 / 10.140 | 16.241 / 5.360 | 9.158 / 3.022 | 13.345 / 4.404 |
| c330n_0ma_esr10m | 30.733 / 10.142 | 16.248 / 5.362 | 9.163 / 3.024 | 13.350 / 4.406 |
| c330n_0ma_esr500m | 31.010 / 10.233 | 16.585 / 5.473 | 9.376 / 3.094 | 13.603 / 4.489 |
| c330n_50ma_esr0 | 19.261 / 6.356 | 8.610 / 2.841 | 8.082 / 2.667 | 4.390 / 1.449 |
| c330n_50ma_esr10m | 19.263 / 6.357 | 8.613 / 2.842 | 8.082 / 2.667 | 4.391 / 1.449 |
| c330n_50ma_esr500m | 19.383 / 6.396 | 8.755 / 2.889 | 8.075 / 2.665 | 4.456 / 1.470 |
| c4u7_0ma_esr0 | 2.159 / 10.148 | 1.140 / 5.360 | 0.643 / 3.022 | 0.937 / 4.404 |
| c4u7_0ma_esr10m | 2.165 / 10.175 | 1.147 / 5.393 | 0.647 / 3.043 | 0.942 / 4.429 |
| c4u7_0ma_esr500m | 2.517 / 11.832 | 1.554 / 7.303 | 1.203 / 5.653 | 1.265 / 5.943 |
| c4u7_50ma_esr0 | 2.018 / 9.486 | 0.722 / 3.393 | 0.627 / 2.945 | 1.408 / 6.618 |
| c4u7_50ma_esr10m | 2.088 / 9.814 | 0.726 / 3.410 | 0.623 / 2.927 | 1.424 / 6.695 |
| c4u7_50ma_esr500m | 2.701 / 12.693 | 1.165 / 5.474 | 1.169 / 5.494 | 1.010 / 4.747 |

sf/-40C/2.97V (worst vpk 1.81261 V; worst vfloor 1.79882 V; tramp 0.248-0.313 ms):

| leg | base | enp | enp5 | both |
|---|---|---|---|---|
| c330n_0ma_esr0 | 65.474 / 21.606 | 36.582 / 12.072 | 53.504 / 17.656 | 40.997 / 13.529 |
| c330n_0ma_esr10m | 65.492 / 21.612 | 36.603 / 12.079 | 53.524 / 17.663 | 41.018 / 13.536 |
| c330n_0ma_esr500m | 66.368 / 21.901 | 37.591 / 12.405 | 54.479 / 17.978 | 42.077 / 13.885 |
| c330n_50ma_esr0 | 37.950 / 12.523 | 20.465 / 6.753 | 37.149 / 12.259 | 23.314 / 7.694 |
| c330n_50ma_esr10m | 37.948 / 12.523 | 20.475 / 6.757 | 37.151 / 12.260 | 23.324 / 7.697 |
| c330n_50ma_esr500m | 37.893 / 12.505 | 20.944 / 6.911 | 37.266 / 12.298 | 23.807 / 7.856 |
| c4u7_0ma_esr0 | 4.598 / 21.609 | 2.569 / 12.073 | 3.757 / 17.656 | 2.879 / 13.530 |
| c4u7_0ma_esr10m | 4.615 / 21.693 | 2.589 / 12.167 | 3.776 / 17.748 | 2.900 / 13.631 |
| c4u7_0ma_esr500m | 5.541 / 26.041 | 3.634 / 17.078 | 4.780 / 22.468 | 4.007 / 18.833 |
| c4u7_50ma_esr0 | 4.130 / 19.412 | 1.171 / 5.504 | 3.976 / 18.689 | 2.406 / 11.307 |
| c4u7_50ma_esr10m | 4.126 / 19.392 | 1.195 / 5.615 | 3.978 / 18.694 | 2.424 / 11.394 |
| c4u7_50ma_esr500m | 5.059 / 23.779 | 2.608 / 12.258 | 4.023 / 18.910 | 3.356 / 15.772 |

Every drawdown in both tables is positive, so every leg of every variant FAILs
the ratified 0 V monotonicity check exactly as the baseline does -- identical
verdict, smaller number. (The ESR = 500 m rows carry the same current times the
ESR on top of the packet, per #693's convention; the packet view is the ESR = 0
/ 10 m rows.) Loaded legs stay at tens-of-uV drawdowns or below -- none of the
oscillatory sag the L=520/L=1800 screen saw (that class was 3.9-20.6 mV).

## 3. Why wake shaping does not qualify

- **No verdict changes anywhere.** The 0 V monotonicity check fails identically
  (positive drawdown at all 24 leg-rows of every variant at both corners), so
  the Startup row grade cannot move; landing two ideal gate RCs in the
  schematic would buy a 44-70 % packet reduction that changes no recorded
  result, at the cost of new unverified elements on the enable path.
- **Corner-inconsistent and bounded.** The PB clamp gives -70.2 % at tt but only
  -18.3 % at sf (the record's worst corner); the EA_OUT clamp is the consistent
  one (-47 %/-44 %) but weaker. Neither approaches the R_CZ screen's 85-88 %.
- **The tau trade is closed on both sides.** tau = 300 us: the EA_OUT clamp's
  packet rises ABOVE baseline at both corners (12.81/23.97 pC) with tramp
  stretching to 0.54 ms; the PB clamp leaves the packet where tau = 100 us put
  it but breaks the ratified overshoot bound (vpk up to 2.035 V vs 1.836). A
  longer release can only re-trade packet against bounds; it cannot reach zero.
- **Mechanism.** The residual rides on the amplifier's own wake (the
  bias/diff-pair balance `M_ENP2`/`M_ENN`/`M_ENN2` per #693's attribution) and
  on intrinsic device caps: shaping the two clamp gates cannot reach it. This
  confirms, from the other direction, #693's p3 ceiling (deleting `M_ENP5`
  entirely cuts only ~35 %) and p6 neutrality (a 50x slower EN edge changes
  nothing).

Loop-gain and load-transient grids were **not** run for wake shaping: the issue
conditions them on a candidate worth adopting, and no variant changes any
verdict or approaches the rejected R_CZ candidate's reduction, so there is no
candidate to co-verify.

## 4. Deck sha256 (all runs; regenerate with the driver)

| variant | tau | corner | deck sha256 (first 16) |
|---|---|---|---|
| base | -- | tt_27c_3.30v | 424a29ae6b2e8e9f (= #693 baseline deck) |
| base | -- | sf_-40c_2.97v | a98d623035a47fba |
| enp | 100 us | tt_27c_3.30v | d46339c6e63326b5 |
| enp | 100 us | sf_-40c_2.97v | f6113510385ce561 |
| enp5 | 100 us | tt_27c_3.30v | 63b32448c63607fc |
| enp5 | 100 us | sf_-40c_2.97v | 70356c69c044b409 |
| both | 100 us | tt_27c_3.30v | ebb09c6fc728181a |
| both | 100 us | sf_-40c_2.97v | d5fd739b2d9cc956 |
| enp | 300 us | tt_27c_3.30v | 96ad105d3efb442f |
| enp | 300 us | sf_-40c_2.97v | f48af9bac86e623d |
| enp5 | 300 us | tt_27c_3.30v | 34c2636fb42953b3 |
| enp5 | 300 us | sf_-40c_2.97v | cbec21cd9160c298 |

## 5. What this note does NOT change

`tolerance_v` stays 0.0; the ratified Startup row, `spec/` and every decision
record are untouched; the startup record 20261117-221657-efb6bd6b is NOT
superseded and `measurements/characterization.md` / the item-5 envelope /
`signoff/` keep citing it; `design/ldo_3v3in_1v8out.sch` keeps `R_CZ` L=52 and
the EN-gated clamps exactly as they are (the soft release exists only in the
screen decks above). The residual packet (3.0-17.7 pC at the screened
conditions across variants) still FAILs strict `tolerance_v = 0`; whether a
nonzero tolerance is acceptable remains the open decision-record question it
already was (`sim/README.md`, "Startup ramp monotonicity").
