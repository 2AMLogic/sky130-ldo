# Pilot note 20261121-693: enable-edge charge-packet attribution (issue #693)

**Status: diagnostic pilot, not an evidence record.** Append-only note under
`sim/startup/pilots/`; it attributes the 0.016-66 uV pre-ramp drawdown behind the
`startup` row's ramp-monotonicity FAILs (record `sim/startup/records/20261117-221657-efb6bd6b`,
540/540 conditions FAIL at strict `tolerance_v = 0` V) and screens one bounded design
change at its source. Nothing here changes `tolerance_v`, the ratified row, `spec/` or
any decision record; no new evidence record is minted.

## Verdict (one line)

**Circuit behaviour, not solver noise**: the drawdown is a fixed charge packet leaving
C_out through the Miller compensation network -- `C_COMP` (150 pF, VOUT->EA_CZ) displaced
by the error amplifier's own wake transient (EA_OUT falls from VIN by ~0.5 V over the dip window
(~18 us) after enable, before the pass device conducts) -- decided by (a) drawdown x C_out
being C_out-invariant at all 45 corners (worst spread 0.21 %, dd ratio 14.212-14.248 vs
capacitance ratio 14.242), (b) the packet converging UP to a stable 12.6 pC under solver
tightening (10.14 pC at fleet defaults, 12.56/12.59 pC at reltol 1e-6 with and without
max-step 0.1 us) rather than shrinking toward zero, and (c) `C_COMP` 150 p -> 1 f removing
97 % of the 0 mA packet (10.142 -> 0.327 pC at tt/27 C/3.30 V) while the charge budget
150 pF x 87.1 mV(EA_CZ) = 13.1 pC closes the same path independently.

## Inputs, tools, provenance

- Read-only input: `sim/startup/records/20261117-221657-efb6bd6b.md` (the committed record
  text; its JSON/traces live in the artifact store per the record's sha256s).
- Probe engine: ngspice-47 local (`ngspice -b`, single-corner debug probes per the repo
  host rules; KLT batch fleet NOT used -- no deck in validated-adapter shape was edited,
  all probes are scratch decks under gitignored `sim/build/issue693/`).
- PDK: sky130A @ open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b` (the `sim/pdk.json`
  pin; installed at `~/.volare/sky130A`), `.lib ... {tt,sf}` sections, `.spiceinit` = the
  harness `sim/spiceinit` (sha256 in the baseline log).
- Baseline deck: the harness-minted `tt_27c_3.30v.deck.spice` from scratch run
  `sim/build/startup/20261121-084856-303d2449.ephemeral-2254185`
  (`corner-run.py sim/startup --backend local --process tt --temp 27 --supply 3.30
  --subset-reason "enable-edge attribution" --no-write`, exit OK, grid FAIL as expected);
  repo state `303d2449` (clean).
- Drawdown metric: every probe trace is graded by the bench's own checker
  `sim/bin/ramp_monotonicity.py` (`check_ramp_monotonicity`, settings verbatim from
  `sim/startup/experiment.json`'s `ramp_monotonicity`: t_enable 100 us, v_low 1.764 V,
  max_dt 20 us, min_samples 20, tolerance 0.0 V) so probe numbers are directly comparable
  with the record.
- Probe decks are the baseline deck plus the one text edit named per variant; driver and
  per-variant decks/logs/summaries live under `sim/build/issue693/` (gitignored scratch).
  Deck sha256s: base `424a29ae...`, s1 `c47e7f8e...`, s2 `8c644e46...`, s3 `169e9814...`,
  s4 `01b72436...`, p1_nocomp `956d250f...`, p2_nossdis `1301b2f6...`, p2b_bigcss
  `3fd1b1af...`, p3_noenp5 `93376ccd...`, p6_slowen `770e9965...`, aux `9e173b28...`,
  fix_tt(L=1800) `823ca320...`, fix_tt_l180 `b3065733...`, fix_tt_l520 `ad84a916...`,
  fix_worst_l180 `42ebfb1e...`, base_worst `d1ec11df...`.

## 1. Charge table: all 45 corners from the existing record (no new simulation)

Q = drawdown x C_out, computed for the ESR = 0 legs (the clean packet view; ESR > 0 only
adds the same current times the ESR). Drawdowns are the record's own per-corner
`ramp_drawdown_<leg>_v` values.

| corner | dd c330n/0mA/ESR0 (uV) | dd c4u7/0mA/ESR0 (uV) | ratio dd(c330n)/dd(c4u7) | Q0 c330n (pC) | Q0 c4u7 (pC) | Q50 c330n (pC) | Q50 c4u7 (pC) |
|---|---|---|---|---|---|---|---|
| tt_-40c_2.97v | 60.290 | 4.2358 | 14.23 | 19.896 | 19.908 | 9.119 | 18.535 |
| tt_-40c_3.30v | 48.278 | 3.3910 | 14.24 | 15.932 | 15.938 | 9.843 | 15.331 |
| tt_-40c_3.63v | 25.020 | 1.7565 | 14.24 | 8.257 | 8.256 | 7.696 | 11.679 |
| tt_27c_2.97v | 29.229 | 2.0520 | 14.24 | 9.646 | 9.644 | 7.377 | 12.180 |
| tt_27c_3.30v | 30.727 | 2.1592 | 14.23 | 10.140 | 10.148 | 6.356 | 9.486 |
| tt_27c_3.63v | 17.399 | 1.2215 | 14.24 | 5.742 | 5.741 | 6.074 | 9.155 |
| tt_125c_2.97v | 12.955 | 0.9098 | 14.24 | 4.275 | 4.276 | 1.624 | 2.667 |
| tt_125c_3.30v | 9.599 | 0.6740 | 14.24 | 3.168 | 3.168 | 1.263 | 1.798 |
| tt_125c_3.63v | 8.097 | 0.5683 | 14.25 | 2.672 | 2.671 | 0.796 | 1.059 |
| ss_-40c_2.97v | 45.754 | 3.2123 | 14.24 | 15.099 | 15.098 | 12.377 | 17.443 |
| ss_-40c_3.30v | 42.956 | 3.0156 | 14.24 | 14.175 | 14.173 | 9.563 | 14.809 |
| ss_-40c_3.63v | 40.885 | 2.8732 | 14.23 | 13.492 | 13.504 | 7.904 | 10.957 |
| ss_27c_2.97v | 44.281 | 3.1107 | 14.24 | 14.613 | 14.620 | 8.262 | 13.318 |
| ss_27c_3.30v | 20.125 | 1.4129 | 14.24 | 6.641 | 6.641 | 7.721 | 11.934 |
| ss_27c_3.63v | 24.497 | 1.7198 | 14.24 | 8.084 | 8.083 | 7.042 | 9.978 |
| ss_125c_2.97v | 17.685 | 1.2420 | 14.24 | 5.836 | 5.837 | 2.874 | 4.685 |
| ss_125c_3.30v | 14.952 | 1.0499 | 14.24 | 4.934 | 4.935 | 2.564 | 3.947 |
| ss_125c_3.63v | 12.660 | 0.8889 | 14.24 | 4.178 | 4.178 | 2.162 | 3.086 |
| ff_-40c_2.97v | 39.663 | 2.7844 | 14.24 | 13.089 | 13.086 | 9.329 | 17.345 |
| ff_-40c_3.30v | 31.585 | 2.2224 | 14.21 | 10.423 | 10.445 | 8.894 | 12.189 |
| ff_-40c_3.63v | 21.165 | 1.4858 | 14.24 | 6.984 | 6.983 | 8.000 | 11.142 |
| ff_27c_2.97v | 27.831 | 1.9539 | 14.24 | 9.184 | 9.183 | 5.602 | 10.443 |
| ff_27c_3.30v | 26.161 | 1.8376 | 14.24 | 8.633 | 8.637 | 5.085 | 7.969 |
| ff_27c_3.63v | 17.244 | 1.2107 | 14.24 | 5.690 | 5.690 | 4.756 | 7.164 |
| ff_125c_2.97v | 6.422 | 0.4510 | 14.24 | 2.119 | 2.120 | 0.388 | 0.508 |
| ff_125c_3.30v | 4.371 | 0.3070 | 14.24 | 1.442 | 1.443 | 0.169 | 0.182 |
| ff_125c_3.63v | 2.496 | 0.1753 | 14.24 | 0.824 | 0.824 | 0.107 | 0.110 |
| sf_-40c_2.97v | 65.474 | 4.5976 | 14.24 | 21.606 | 21.609 | 12.523 | 19.412 |
| sf_-40c_3.30v | 48.070 | 3.3751 | 14.24 | 15.863 | 15.863 | 10.594 | 16.866 |
| sf_-40c_3.63v | 36.017 | 2.5284 | 14.24 | 11.886 | 11.883 | 8.661 | 11.743 |
| sf_27c_2.97v | 46.318 | 3.2534 | 14.24 | 15.285 | 15.291 | 8.493 | 14.789 |
| sf_27c_3.30v | 38.480 | 2.7022 | 14.24 | 12.699 | 12.700 | 7.968 | 12.842 |
| sf_27c_3.63v | 18.612 | 1.3066 | 14.24 | 6.142 | 6.141 | 6.778 | 10.533 |
| sf_125c_2.97v | 19.774 | 1.3885 | 14.24 | 6.525 | 6.526 | 3.650 | 6.235 |
| sf_125c_3.30v | 17.306 | 1.2156 | 14.24 | 5.711 | 5.713 | 3.203 | 4.826 |
| sf_125c_3.63v | 14.486 | 1.0172 | 14.24 | 4.780 | 4.781 | 2.508 | 3.918 |
| fs_-40c_2.97v | 36.906 | 2.5909 | 14.24 | 12.179 | 12.177 | 8.503 | 15.837 |
| fs_-40c_3.30v | 37.623 | 2.6454 | 14.22 | 12.416 | 12.433 | 8.765 | 13.283 |
| fs_-40c_3.63v | 20.430 | 1.4342 | 14.24 | 6.742 | 6.741 | 6.869 | 10.783 |
| fs_27c_2.97v | 18.087 | 1.2698 | 14.24 | 5.969 | 5.968 | 5.189 | 9.678 |
| fs_27c_3.30v | 24.773 | 1.7401 | 14.24 | 8.175 | 8.178 | 5.031 | 7.938 |
| fs_27c_3.63v | 19.235 | 1.3515 | 14.23 | 6.347 | 6.352 | 4.366 | 6.504 |
| fs_125c_2.97v | 2.001 | 0.1405 | 14.24 | 0.660 | 0.660 | 0.113 | 0.119 |
| fs_125c_3.30v | 1.217 | 0.0855 | 14.24 | 0.402 | 0.402 | 0.090 | 0.093 |
| fs_125c_3.63v | 0.595 | 0.0418 | 14.24 | 0.196 | 0.196 | 0.072 | 0.073 |

Reading of the table:

- **Constant in C_out everywhere.** Per corner the two 0 mA ESR = 0 legs imply the same
  charge to within 0.21 % (worst case), and dd(c330n)/dd(c4u7) = 14.212-14.248 against the
  capacitance ratio 4.7 uF / 0.33 uF = 14.242. A charge packet, not a voltage- or
  current-scaled effect.
- **Falls with temperature, monotonically, at every process x supply column** (15/15
  columns strictly Q(-40 C) > Q(27 C) > Q(125 C); e.g. ff/2.97 V: 13.09 -> 9.18 -> 2.12 pC).
- **Falls with VIN in 11/15 columns** (strictly 2.97 > 3.30 > 3.63 V); the four
  non-monotone columns are tt_27c (9.65 / 10.14 / 5.74 pC), ss_27c (14.61 / 6.64 / 8.08),
  fs_-40c (12.18 / 12.42 / 6.74) and fs_27c (5.97 / 8.18 / 6.35) -- VIN is a secondary
  knob, not the ordering variable.
- **50 mA legs** do not show the clean packet (Q50 differs from Q0 and between C_out legs,
  e.g. tt/-40 C/2.97 V: 9.12 vs 18.54 pC): the 36 ohm load holds VOUT near 0 pre-enable
  and its current rides on the same window, so the implied "charge" there is packet +
  load interaction, as the issue anticipated. The attribution below therefore uses the
  0 mA legs; every mechanism finding reproduces on the 50 mA legs qualitatively.
- Range over all 540 recorded drawdowns: 0.0156 uV (fs_125c_3.63v, c4u7_50ma_esr0) to
  66.37 uV (sf_-40c_2.97v, c330n_0ma_esr500m). No leg has drawdown exactly 0, so no
  zero-denominator ratio arises.

Hand re-derivation (acceptance check): tt_-40c_2.97v 60.290 uV x 0.33 uF = 19.896 pC and
ff_125c_3.63v 2.496 uV x 0.33 uF = 0.824 pC, both matching the table rows.

## 2. Solver-convergence table (tt / 27 C / 3.30 V, the four 10 mOhm legs)

Settings beyond the deck's own `.option wnflag=1`:

| variant | options | tran | c330n_0mA dd (uV) | c330n_0mA Q (pC) | c4u7_0mA Q (pC) | c330n_50mA Q (pC) | c4u7_50mA Q (pC) |
|---|---|---|---|---|---|---|---|
| base (fleet-equivalent defaults) | -- | 10u 4m | 30.733 | 10.142 | 10.175 | 6.357 | 9.814 |
| s1 | reltol=1e-4 vntol=1e-7 abstol=1e-13 | 10u 4m | 34.755 | 11.469 | 11.511 | 7.207 | 11.800 |
| s2 | reltol=1e-6 vntol=1e-9 abstol=1e-15 | 10u 4m | 38.072 | 12.564 | 12.571 | 7.333 | 12.015 |
| s3 | reltol=1e-6 vntol=1e-9 abstol=1e-15 | 10u 4m 0 0.1u | 38.142 | 12.587 | 12.593 | 7.337 | 12.023 |
| s4 | reltol=1e-8 vntol=1e-11 abstol=1e-17 | 10u 4m 0 0.02u | (not evaluable, see below) | | | | |

- The packet **converges upward to a stable non-zero value**: s2 vs s3 agree to 0.2 % on
  every leg while their step controls are independent (LTE-only vs forced 0.1 us max step),
  and s1 sits 9 % below them. The fleet-default numbers (base, 10.14 pC) UNDER-report the
  packet by ~20 %: coarse LTE smears the first ~2 us of the edge transient and the trough
  depth. Converged packet at this corner: **~12.6 pC (0 mA)**.
- s4 (over-tightened) is not a usable ladder point: abstol 1e-17 degrades the pre-enable
  solve itself (VOUT baseline drifts to 1.39 mV vs 0.556 mV at every coarser setting --
  the pre-edge VOUT is a fA-leakage integral, i.e. numerically arbitrary in absolute
  terms), the OP solve emits singular-matrix warnings naming `xldo.ea_cz`, and the trace
  carries duplicated timestamps at the pulse breakpoints (the checker correctly calls the
  trace INVALID on non-strictly-increasing time; after deduplication the window itself
  changes shape because the drifted baseline resets the running maximum). The useful
  ladder ends at s3.
- Reproduction check (acceptance): re-running the s2 leg gives 38.072 uV; s3's independent
  step control gives 38.142 uV (0.18 % apart) -- the reported stable value.

**The drawdown does not shrink toward zero under solver tightening, it converges up to a
fixed ~12.6 pC packet; per the issue's criterion this is circuit behaviour.** (The fleet
record's 10.14 pC at this corner is the same circuit packet, LTE-smeared.)

## 3. Per-path attribution (tt / 27 C / 3.30 V, 12 legs unless noted; text edits on the baseline deck)

| variant | netlist text edit | 0 mA packet c330n / c4u7 (pC) | what it says |
|---|---|---|---|
| p1_nocomp | `C_COMP VOUT EA_CZ 150p` -> `1f` | 0.327 / 0.330 | Removes 97 % of the packet. The deliberate Miller cap IS the dominant coupling path. (50 mA legs blow up to 7.7-27 mV drawdowns: without C_COMP the loop is uncompensated -- the cap cannot simply be deleted.) |
| p3_noenp5 | delete `XM_ENP5` (PB clamp) | 6.650 / 6.691 | The PB-release branch shapes ~35 % of the packet (PB gates `M_MIRP2`, the PMOS side of EA_OUT's wake); the balance rides on the bias/diff-pair wake with `M_ENP2`/`M_ENN`/`M_ENN2`. Same C_out-invariant packet shape. |
| p2b_bigcss | `C_SS SS 0 10p` -> `100p` (10x slower soft-start) | 34.411 / 34.477 | The soft-start network MODULATES the packet (EA_OUT falls unopposed for longer before the SS handover starts the pass device: trough moves 118 -> 188 us, packet x3.4) but is not the coupling path. |
| p2_nossdis | delete `XM_SSDIS` (SS discharge switch) | 1.140 / 1.217 | Not a valid zeroing: without M_SSDIS the pre-enable OP leaves SS floating high, the cold-start premise breaks (trough 17 us early, ramp starts immediately). M_SSDIS is doing its job; no evidence it is a coupling path. |
| p6_slowen | EN rise 1 us -> 50 us | 11.983 / 12.185 | A 50x slower enable edge leaves the packet unchanged (within the base-vs-s3 numerical spread): NOT gate-slew feedthrough / charge injection from the EN edge; it is the charge the circuit must displace to reach its new state. |

### Internal-node evidence (aux dump, default settings, c330n_0mA_esr10m leg)

| time | EN (V) | EA_OUT (V) | EA_CZ (V) | PB (V) | BIASP (V) | SS (V) | VOUT (mV) |
|---|---|---|---|---|---|---|---|
| 52.8 us (pre-edge) | 0 | 3.3000 | 3.3000 | 3.3000 | 3.3000 | ~0 | 0.55626 |
| 100.49 us (edge+0.5) | 1.626 | 3.3006 | 3.29999 | 3.3026 | 2.2954 | -0.001 | 0.55625 |
| 104.05 us | 3.3 | 3.1740 | 3.2932 | 2.1725 | 2.2363 | 0.013 | 0.55265* |
| 118.16 us (trough) | 3.3 | 2.7953 | 3.2129 | 2.2065 | 2.2362 | 0.073 | 0.52553* |
| 133.46 us (ramp) | 3.3 | 2.3887 | 3.0510 | 2.2377 | 2.2362 | 0.138 | rising |
| 3.00 ms (settled) | 3.3 | 3.1477 | 3.1483 | 2.1689 | 2.2363 | 3.3000 | 1.8071 |

(*from the leg's graded trace; the aux table's own VOUT column is the same run.)

When EN rises, the EN-gated returns (`AMP_ENN` drops from 2.24 V to 2 mV within
0.5 us) and PMOS clamps release. As the mirror/amp core wakes, the `M_MIR2` mirror
sink and the PB-gated `M_MIRP2` branch balance at the pass gate. Its voltage,
`EA_OUT`, falls from VIN by ~0.5 V by the trough (~18 us) and by ~0.9 V by 35 us.
`EA_CZ` follows `EA_OUT` through `R_CZ` (~300 kΩ at W=0.42, L=52 in the
[compensation design](../../../design/README.md#compensation-sized-in-25)).
With `C_COMP` = 150 pF, the nominal time constant is 45 us. During the dip,
`EA_CZ`−VOUT falls by 87.1 mV. The charge that C_COMP pulls from C_out is
150 pF x 87.1 mV = **13.1 pC**. M_PASS (Vsg still << |Vth|) cannot yet
replace it. That is the packet: budget 13.1 pC vs the
converged measured 12.6 pC (4 %), vs 10.14 pC at fleet-tolerance LTE. The pass device
begins conducting near the trough; from there the soft-start ramp takes VOUT up and the
same C_COMP path quietly returns the charge during the rise.

The residual after `C_COMP -> 1f` (0.33 pC, itself C_out-invariant) is consistent
with coupling through the `M_PASS` gate-drain overlap and other stray device
capacitances. Each 100 µm-wide group includes all 25 fingers, so the 50 parallel
groups give a total gate width of 5 mm. [Pass-device sizing](../../../design/README.md#pass-device-re-size-116dr-011)

## 4. Design-change screen (circuit route, step 4)

Knob screened: **`R_CZ`** (`XR_CZ EA_CZ EA_OUT`, `res_xhigh_po` W=0.42, L=52 -> L' ), the
series resistor of the very path the attribution names (packet columns in the table above quote the ESR = 10 mOhm legs). Larger R_CZ slows EA_CZ's
in-window displacement (charge still moves, but later, during the ramp when M_PASS is
active), at the cost of moving the compensation zero down (f_z = 1/(2.pi.R_CZ.C_COMP),
~3.2-3.5 kHz at L=52).

| variant | corner | 0 mA packet (pC) | 50 mA behaviour | vpk/vfloor bounds | tramp (ms) |
|---|---|---|---|---|---|
| base | tt/27/3.30 | 10.14 | stable | pass | 0.320-0.348 |
| fix_tt L=1800 (x34.6) | tt/27/3.30 | 0.363 | **unstable**: c330n legs sag 9.8-20.6 mV, c4u7/50 mA sag 4.7-5.5 mV (esr0/10 m) | (moot) | -- |
| fix_tt_l520 (x10) | tt/27/3.30 | 0.749 | **unstable at c330n**: 3.9-6.6 mV sag | (moot) | -- |
| fix_tt_l180 (x3.46) | tt/27/3.30 | **1.226** | stable, dd 4.09 uV (c330n) / 0.37 uV (c4u7) | pass | 0.353-0.431 |
| base_worst | sf/-40/2.97 | 21.61 | stable | pass | 0.249-0.286 |
| fix_worst_l180 (x3.46) | sf/-40/2.97 | **3.140** | stable, dd 7.44 uV (c330n) / 0.69 uV (c4u7) | pass | 0.322-0.391 |

**Screen verdict: REVISE.** L=180 removes 85-88 % of the packet at both the nominal and
the record's worst corner with every electrical condition still passing and no leg
destabilized, but (a) a residual 1.2-3.1 pC packet remains -- at strict `tolerance_v = 0`
the row would still FAIL, so this is a reduction, not a cure, and (b) the compensation
zero moved 3.5x down, which this bench cannot qualify: the follow-up must co-verify
`sim/loop-gain` (and load-transient) before landing. L >= 520 is REJECTED by this screen
(loaded-start instability at c330n). The follow-up issue also owns the alternative
directions this attribution opens: shaping EA_OUT's wake itself (the driver of the
displacement), e.g. soft-release of `M_ENP` or a PB-branch slew trade, vs further R_CZ
tuning.

Follow-up: 2AMLogic/sky130-ldo#709 (land R_CZ co-design in the schematic, re-verify
loop gain, re-mint the startup record).

## 5. What this note does NOT change

`tolerance_v` stays 0.0; the ratified Startup row, `spec/` and every decision record are
untouched; no `sim/startup/records/` record and no `signoff/evidence/` envelope is minted,
superseded or edited; `measurements/characterization.md` is not regenerated (its FAIL
row cites the still-current 20261117 record). The batch adapter and its validated shape
are untouched (no deck in validated shape was edited; all probes are scratch decks).
