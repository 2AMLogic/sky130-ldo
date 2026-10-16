# Issue #339 -- dropout screening: isolated pass capability + combined amplifier/clamp interventions

Diagnostic only -- NOT a record, not part of any characterization selection, no spec/DR/production
change. **tt / 27 C / VIN start 3.30 V / 50 mA ideal sink only** (single condition; no PVT, no
Monte Carlo, no fleet). The ratified `< 300 mV` dropout row is untouched and its PVT gap (#114) is
unresolved. Ideal sources and disabled protection below are causal diagnostics, never adoptable
circuits. Append-only: nothing under `../issue-323/` or `sim/*/records/` was changed.

## Inputs and provenance

- Baseline deck: `baseline.deck.spice`, byte-identical to `../issue-323/baseline.deck.spice` (the deck
  `corner-run.py` handed ngspice for record `20261011-092557-7a4e0cc`). `design/`, the dropout testbench
  and `experiment.json` are unchanged since #323's commit (`git diff 12230c8 HEAD`: empty); the only
  `corner-run.py` change since is the load-transient window-grid batch path, which does not touch
  dropout deck generation. So "current committed DUT" == #323's DUT; no current-DUT differences.
- Same PDK (sky130A, `c6d73a35...` pin), ngspice-42 (KLU), same `.spiceinit`, stimulus (cold-start
  `tran 10u 14m uic`, VEN step at 100 us, 50 mA load ramp 2.5-2.6 ms, VIN 3.3 V -> 1.17 V over 6-14 ms),
  crossing (`find v(vin) when v(vout)=1.764 fall=1 td=6m`) and solver settings.
- `provenance.json`: source commit, tool/PDK versions, sha256 of every deck, raw `.dat` (hash is of the
  *gunzipped* content) and script. Raw solver output: `*.stdout.txt`. Commands: `commands.sh`
  (strictly sequential, one ngspice at a time).

## Deliverables

| file | purpose |
|---|---|
| `make_probe_deck.py` | composable edits (`ideal_tail`, `no_clamps`, `frozen_bias`) on the baseline deck; isolated M_PASS DC benches |
| `analyze.py` | validity gates, crossing / 50 mA-contour extraction, calibration, comparison tables |
| `probe{0,A,B,AB}.*`, `probe{0r,ABr}.*` | decks, wrdata (`.dat.gz`), logs, `.analysis.txt`, `.result.json` |
| `pass_*.deck.spice/.dat.gz/.analysis.txt` | isolated pass bench: calibration, contour (source 2.16 V), refinement, supplement (2.064 V) |
| `compare.table.txt` | side-by-side intervention table |
| `../../../tests/test_dropout_diagnostics_339.py` | fixtures: missing crossing, non-regulating start, nonfinite, solver warnings, malformed data, deck-diff checks |

## Validity gates (invalid is never a pass; `dropout_v` is None when any fails)

cold start (VOUT, EN ~ 0 at t=0, `uic`); finite data; strictly increasing time; run reaches 14 ms;
regulating at the starting supply (mean VOUT 5.5-6 ms in [1.774, 1.836] V) with pass Id within 10 % of
50 mA; a real falling crossing exists after 6 ms; no solver diagnostics in the ngspice log
(warning/error/timestep/singular/convergence/...); ngspice `meas_dropout_v` agrees with the trajectory
crossing within 0.5 mV. All runs below pass every gate.

## 1. Isolated M_PASS bench (`pfet_g5v0d10v5`, committed W=100 L=0.5 nf=25 mult=50 m=50, body=source)

**Calibration (valid).** The bench replays six saved terminal triples (VIN, EA_OUT, VOUT) taken from the
probe0 trajectory (3.3 V pre-ramp ... crossing). Declared tolerance: |dId|/Id <= 2e-3 and |dVds_model|
<= 1 mV (2x ngspice reltol). Result: agreement to ~1e-8 relative at all six points. Polarity checked
(`i(VD) > 0`, `i(VS) < 0`, |i(VD)| = |Id|, source above drain). Against #323's *rounded* figures at the
crossing sample: model-internal Vgs 1.44574 (vs 1.446), model Vds 0.38855 (vs 0.389), Id 49.748 mA (vs
~49.7), within the predeclared half-LSB tolerance 0.145 mA (= gm*0.5 mV + gds*0.5 mV + 0.05 mA,
gm=0.146 S, gds=0.043 S) -- `pass_rounded.analysis.txt`. Notes: (i) #323's "Vsg 1.446 / Vds 0.389" are the
model-*internal* values; the terminal Vsg at the same sample is 1.4503 V. (ii) The "~49.7 mA" is not the
50.000 mA load: the quasi-static 266 V/s ramp makes the 1 uF COUT supply ~0.27 mA, so the pass device
carries 49.75 mA at the crossing; the 50 mA contour below is therefore ~0.02 V *more* demanding than
the crossing sample (0.419 vs 0.398 V at Vg=0.714).

**50 mA contour** (source = body = 2.16 V; gate 0.714 -> 0 V step 0.017 V; |Vsd| 0 -> 0.5 V step 5 mV;
linear interpolation; checked against a 0.5 mV-step refinement at Vg = 0.714/0.357/0 -- identical to
4 digits). Terminal |Vsd| vs model-internal |Vds| differ by a constant **9.2 mV** at 50 mA (= 0.184 ohm of
model series resistance, ~0.087 ohm on the source side per the 4.3 mV Vgs difference): that is the
known ~9 mV gap, now decomposed as series resistance, not an error.

| gate Vg [V] | terminal Vsg [V] | Vsd @ 50 mA [V] | model Vds [V] |
|---|---|---|---|
| 0.714 | 1.446 | 0.4194 | 0.4102 |
| 0.663 | 1.497 | 0.3103 | 0.3012 |
| 0.646 | 1.514 | 0.2914 | 0.2823 |
| 0.510 | 1.650 | 0.2103 | 0.2012 |
| 0.357 | 1.803 | 0.1683 | 0.1592 |
| 0.000 | 2.160 | 0.1221 | 0.1129 |

Supplement at the VIN that corresponds to the target edge (source 2.064 V = 1.764 + 0.300; no
crossing in the 0.5 V window for Vg >= 0.646, i.e. Vsg <= 1.418): <= 0.300 V terminal needs Vsg >= ~1.51
(gate <= ~0.55 V absolute); Vsg = 1.82 (gate 0.24 V) gives ~0.17 V; Vsg = 2.064 gives 0.131 V.

**Conclusion 1.** Pass-device capability is not the limit at tt / 27 C: with ample gate drive the same
device passes 50 mA at 0.12-0.17 V, i.e. <300 mV is reachable *without resizing* provided the amplifier
delivers Vsg >~ 1.51 V at VIN ~ 2.06 V (gate <= ~0.55 V). The unmodified DUT reaches only EA_OUT =
0.711 V (Vsg 1.45 V) at its crossing. (ss/125 C capability is unmeasured.)

## 2. Transient interventions (all VALID, `compare.table.txt`)

| run | edit vs baseline deck | dropout [V] | VIN at crossing [V] | EA_OUT @ x [V] | pass Vds / Vdsat @ x [V] | tail Id @ x | M_CLIM Id @ x |
|---|---|---|---|---|---|---|---|
| probe0 | none (instrumentation only) | **0.397658** | 2.1617 | 0.711 | 0.389 / 0.409 | 0.313 uA | 49 nA |
| A | `XM_TAIL` -> ideal 3.2744 uA from separate 3.3 V rail | 0.381108 | 2.1451 | 0.690 | 0.372 / 0.412 | 3.274 uA (ideal) | 456 nA |
| B | `XM_CLIM`,`XM_TSHUT` drains off EA_OUT (1 Gohm bleeds) | 0.362555 | 2.1266 | 0.662 | 0.353 / 0.417 | 0.177 uA | 0.02 nA |
| **A+B** | both | **0.164028** | 1.9280 | **0.107** | 0.155 / 0.630 | 3.274 uA (ideal) | 0.004 nA |

- Reproduction: probe0, A and B reproduce #323's 0.397658 / 0.381108 / 0.362555 V to all printed digits;
  re-runs `probe0r` and `probeABr` are byte-identical (`.dat`) to `probe0` / `probeAB` (declared
  tolerance 0.5 mV on dropout; observed 0). Generated decks differ from the baseline only by the listed
  edits plus `save`/`wrdata` instrumentation (`DeckGenerator` tests; `diff probe0.deck.spice probeAB.deck.spice`).
- **Non-additive.** Separate effects (-16.6 mV, -35.1 mV, sum -52 mV) vs combination **-233.6 mV**. Each
  alone leaves the other failure mode active (A: clamp still pulls EA_OUT up, 456 nA; B: amplifier
  tail/output-stage still collapses, 0.18 uA). Together EA_OUT is driven to 0.107 V at the crossing
  and M_MIR2 enters triode (Vds 0.099 V < Vdsat 0.115 V): the loop now runs out of *gate range* at
  VIN = 1.93 V, a hard floor at roughly this dropout, not the 0.71 V seen at baseline.
- Cross-check with section 1: the A+B crossing has terminal Vsg = 1.928 - 0.107 = 1.821 V; the isolated
  contour gives 0.165 V at Vsg 1.82 V; measured VIN - VOUT = 0.164 V (pass Id 49.79 mA).
- Probe C (frozen R_BIAS-derived bias) was permitted only if the valid combined residual stayed
  >= 0.300 V. It did not (0.164 V), so it was **not run**.
- Supply / auxiliary currents (reported separately; not excludable for Iq): VIN supply at the pre-ramp
  point 50.024-50.028 mA (includes the 50 mA load; unchanged within 4 uA between runs); the **auxiliary
  VINA rail supplies exactly the 3.2744 uA ideal tail current** in A and A+B (VVINA), i.e. the same
  current the real tail draws from VIN at 3.3 V -- an ideal tail that stays constant as VIN falls is
  what the real device cannot do. Clamp bleeds (1 Gohm) draw nothing measurable.
- Note: after loss of regulation the ideal 50 mA sink drives VOUT negative by end of ramp (all runs);
  that is the bench's idealized load, after the crossing, and outside the measured quantity.
- Initial-condition contract preserved: `uic`, EN low at t=0, same VEN/VIN/ILOAD sources, no .op/.dc
  on the DUT.

## 3. Decision

**Reject** "pass-device capability / gate-drive range is the limit at tt / 27 C" and **reject**
"either single intervention (tail headroom or clamp pull-up) is sufficient". **Advance** the
*combination* as the specific lever: restore amplifier tail/output-stage current headroom at low VIN
AND stop the current-limit clamp from pulling EA_OUT up at low VIN. Both ideal edits together
yield a valid 0.164 V (136 mV margin) at the sampled condition with the existing pass device, so no
DR-011 pass resizing is indicated by this screen. Limits: one condition (tt / 27 C / 50 mA); ideal
tail and removed clamps are not circuits (removing the clamps removes current limiting); ss/125 C
and the other 44 corners, mismatch, and temperature dependence of the clamp/bias are unmeasured; the
PVT dropout gap (#114) and the unchanged FAIL verdict stand.

## 4. Follow-up requirements (not done here)

1. **Realizable DUT candidate.** A tail whose current/compliance survives VIN down to ~1.9 V with the
   PMOS-input pair's common mode near VREF + |Vgs| (e.g. different input-pair polarity/topology or a
   tail referenced so it needs no extra headroom), and a current-limit clamp whose trip point does not
   depend on the VIN-scaled R_BIAS bias in the dropout region (or is disengaged/re-referenced there)
   while keeping current limiting functional (re-verify current-limit and thermal-shutdown benches).
   No device resizing is evidenced by this screen.
2. **Production adoption / DR-011 review.** Any change to the committed DUT is a separate, human-approved
   issue; any pass-device sizing departure needs a new decision record. None is proposed here.
3. **Off-host qualification path.** `BATCH_ALLOWLIST` in `sim/bin/corner-run.py` contains `pdk-smoke`
   and `load-transient`; dropout-vs-load has no qualified batch adapter. Qualify one with a small probe
   (retained runner evidence; a failed submit is recorded with no local-grid fallback) before running
   paired campaigns.
4. **Paired 45-point PVT evidence** of baseline vs candidate (same commit pairing), regenerating
   characterization with freshness, coverage, solver-failure disclosure and the unchanged target verdict.
   The historical `20260926-102849-0b63ae4` record is not a comparable baseline.

## Reproduce

```bash
cd sim/dropout-vs-load/diagnostics/issue-339   # .spiceinit lives here
sh commands.sh                                 # sequential, ~25 s total, local only
python3 -B ../../../tests/test_dropout_diagnostics_339.py
```
