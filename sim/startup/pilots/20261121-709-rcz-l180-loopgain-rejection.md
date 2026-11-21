# Qualification note 20261121-709: R_CZ L=180 loop-gain rejection and the EA_OUT wake-shaping screen

**Status: qualification note (issue #709), not an evidence record.** Append-only
note under `sim/startup/pilots/`; the graded evidence behind it is the four
fleet records named below. Nothing here changes `tolerance_v`, the ratified
Startup row, `spec/` or any decision record; no startup record is superseded
and no envelope is minted (there is no adopted design change to re-mint on).

## Verdict (one line)

**L=180 is REJECTED by loop-gain co-verification and no wake-shaping
alternative was shown to qualify (the one that was run is not reproducible and
a 100 us soft release was never measured, section 4): adoption of a
compensation change stays OPEN, the
schematic keeps `R_CZ` L=52 (candidate landed as 7fd5183b and reverted as
28b0ae5e on `feature/issue-709`), and the 20261117-221657-efb6bd6b startup
record remains the record of record.** The startup screen itself reproduced
exactly (85.5-87.9 % packet reduction; the peak-overshoot, floor and ramp-time
bounds pass; no oscillatory sag) but L=180 does **not** make the Startup row
pass: ramp-drawdown monotonicity at `tolerance_v = 0` still FAILS (3.715 and
9.515 uV at the two screened no-load conditions), and the Startup signoff grade
stays **FAIL** (see "Startup grade" below). The rejection is the compensation
zero moving ~3.5x down: phase margin collapses on the loaded legs (the 0.33 uF
legs at 1 mA and the 4.7 uF legs at 50 mA, except 4.7 uF / 500 mOhm) while the
no-load legs improve, so L=180 is past the two-sided optimum on the loaded
side, the direction the #25 screening table had already flagged.

### Startup grade (unchanged: FAIL)

`klt signoff --manifest signoff/block-manifest.json --format json`, run with the
repository-pinned `klayout-tools==0.9.0`, exits 3 and reports the startup row's
20261117 envelope (`signoff/evidence/item5-startup-20261117-221657-efb6bd6b.sim.json`)
as `status=unmet`, `reason=check_failed`. `measurements/characterization.md`
reports Startup / soft-start FAIL, 0/45 corners, with the 12 `ramp_drawdown_*`
measurements failing at 45 corners each (540 of 2160 grid conditions; 1620
pass). Two results are distinct and must not be conflated: the **peak
overshoot passes** (worst 1.8246 V at ss/125C/2.97V against the limit, 11.4 mV
margin) while the **positive drawdown fails** the 0 V monotonicity check. The
L=180 candidate does not change that grade: its two screened no-load
conditions still show positive drawdown. Whether to set a nonzero
`tolerance_v` is the open decision; this note makes no such change.

## 1. Two-corner startup screen, production DUT (reproduction of #693's step-4 screen)

`corner-run.py sim/startup --backend local --process {tt,sf} --temp {27,-40}
--supply {3.30,2.97} --no-write`, all 12 window-grid legs per corner, graded by
the bench's own checker; base decks are the harness-minted corner decks at repo
state `303d2449` (L=52) and `7fd5183b` (L=180):

| DUT | corner | dd c330n/0mA/ESR10m (uV) | Q = dd x C_out (pC) | dd c4u7/0mA (uV) | vpk/vfloor/tramp bounds |
|---|---|---|---|---|---|
| L=52 | tt/27C/3.30V | 30.733 | 10.142 | 2.165 | pass (drawdown > 0: FAIL at tolerance 0) |
| L=180 | tt/27C/3.30V | 3.715 | 1.226 | 0.264 | pass (tramp 0.321-0.431 ms); drawdown > 0: FAIL at tolerance 0 |
| L=52 | sf/-40C/2.97V | 65.492 | 21.612 | 4.615 | pass (drawdown > 0: FAIL at tolerance 0) |
| L=180 | sf/-40C/2.97V | 9.515 | 3.140 | 0.675 | pass (tramp 0.249-0.391 ms); drawdown > 0: FAIL at tolerance 0 |

The "bounds" column is the peak-overshoot, floor and ramp-time bounds only;
the drawdown columns are positive in every row, so every row fails the
ratified 0 V monotonicity check (`tolerance_v = 0`) regardless of the
reduction.

Packet reduction 87.9 % (tt) / 85.5 % (worst corner), matching the #693 screen
(1.226 / 3.140 pC exactly). Loaded legs stay small single-digit-uV drawdowns
(c330n/50mA: 4.09 uV tt, 7.43 uV sf; still positive, so still a monotonicity
FAIL) — the 0.33 uF/50 mA traces were inspected
post-ramp (0.5-4 ms): zero large-swing (>200 uV) direction changes, i.e. none
of the oscillatory sag the screen saw at L=520/L=1800 (3.9-20.6 mV).

## 2. Loop-gain co-verification (the rejection)

`python3 sim/bin/bias-retopo-pvt.py loop --design record` over the full
45-corner x 18-leg grid (C_out {0.33u, 4.7u} x ESR {0, 10m, 500m} x load
{0, 1mA, 50mA}), one fleet request per leg x supply (54 each,
`batch.capacity_wait_s = 10800` embedded in every request, verified in the
committed request JSONs — the >= 600 s capacity wait the issue asks for):

- baseline (L=52, clean tree @ 303d2449): `sim/bias-retopo/20261121-165832-rczL52/`
- candidate (L=180 @ 7fd5183b): `sim/bias-retopo/20261121-171327-rczL180/`

Worst-PM-per-leg (deg, worst case over the 45 PVT points of each leg; ratified
bounds PM >= 45, GM >= 10). Every one of the 18 legs is listed, with the
paired per-point change (L=180 minus L=52, same corner/supply/leg key; 810
paired keys), computed from the two `summary.json` files:

| leg (C_out / ESR / load) | worst PM L=52 | worst PM L=180 | PM<45 pts L=52 -> L=180 | paired dPM range |
|---|---|---|---|---|
| c033 / 0 / 0 mA | 15.45 | 26.99 | 33 -> 33 | +0.0 .. +13.1 |
| c033 / 10m / 0 mA | 15.45 | 26.99 | 33 -> 33 | +0.0 .. +13.1 |
| c033 / 500m / 0 mA | 15.47 | 27.01 | 33 -> 33 | +0.0 .. +13.1 |
| c033 / 0 / 1 mA | 73.99 | 27.03 | **0 -> 45** | -50.9 .. -47.0 |
| c033 / 10m / 1 mA | 74.05 | 27.12 | **0 -> 45** | -50.8 .. -46.9 |
| c033 / 500m / 1 mA | 76.97 | 31.42 | **0 -> 45** | -49.3 .. -45.6 |
| c033 / 0 / 50 mA | 31.00 | 12.98 | 34 -> 45 | -32.0 .. -17.9 |
| c033 / 10m / 50 mA | 31.31 | 13.25 | 33 -> 45 | -32.0 .. -18.0 |
| c033 / 500m / 50 mA | 45.65 | 26.08 | **0 -> 45** | -33.6 .. -19.5 |
| c4u7 / 0 / 0 mA | 37.84 | 40.15 | 12 -> 10 | +0.0 .. +2.3 |
| c4u7 / 10m / 0 mA | 37.84 | 40.15 | 12 -> 10 | +0.0 .. +2.3 |
| c4u7 / 500m / 0 mA | 37.91 | 40.21 | 11 -> 10 | +0.0 .. +2.3 |
| c4u7 / 0 / 1 mA | 44.90 | 70.51 | 1 -> 0 | +12.4 .. +31.0 |
| c4u7 / 10m / 1 mA | 44.93 | 70.70 | 1 -> 0 | +12.6 .. +31.0 |
| c4u7 / 500m / 1 mA | 46.72 | 79.57 | 0 -> 0 | +18.1 .. +32.9 |
| c4u7 / 0 / 50 mA | 73.73 | 27.00 | **0 -> 45** | -50.5 .. -46.6 |
| c4u7 / 10m / 50 mA | 74.42 | 28.01 | **0 -> 45** | -50.2 .. -46.3 |
| c4u7 / 500m / 50 mA | 101.11 | 67.80 | **0 -> 0** | -35.6 .. -31.9 |

The collapse is therefore **not** uniform across ESR. At 4.7 uF / 50 mA the
0 and 10 mOhm legs fail at 45/45 PVT points (worst 27.00 / 28.01 deg), but the
500 mOhm leg has zero failures (worst PM 67.80 deg at ff/27C/3.30V, still 33
deg below its L=52 value). At 4.7 uF / 1 mA the margin improves at all three
ESRs. At 0.33 uF / 1 mA all three ESRs cross below 45 deg at all 45 points,
500 mOhm included (31.42 deg worst); the 0.33 uF / 50 mA 500 mOhm leg also
goes 0 -> 45 failures (worst 26.08 deg at ss/-40C/3.63V). Each "worst" in
this table is the minimum over that leg's 45 PVT points, not a typical value.

Totals: sub-45 PM points **203 -> 489 of 810**; GM < 10 dB stays **0**
(candidate worst GM 10.71 dB at c033/ESR0/50mA sf/-40C/3.63V vs baseline 14.79
dB there; the c4u7/ESR500m/1mA GM unavailability of the baseline record
disappears at L=180). Per-point deltas: 405 points worse by >5 deg against 237
better by >5 deg. The no-load legs improve (0.33 uF: +0..+13 deg; 4.7 uF only
+0..+2.3 deg) and the 4.7 uF / 1 mA legs improve +12..+33 deg, while the
loaded legs regress as tabulated: the two-sided optimum of the #25 table,
re-measured: the lower zero buys the light-load corners and takes the margin
out of the loaded ones. The baseline's own no-load shortfall (documented in
design/README.md "Compensation") is unchanged in character (33 -> 33 sub-45
points at 0.33 uF / 0 mA); what is NEW at L=180 is the loaded-leg collapse
above, so L=180 fails the issue's "evidence supporting stability" adoption
clause.

## 3. Load-transient co-verification (matched DUTs)

`corner-run.py sim/load-transient --backend batch`, full 45-corner x 6-leg
grid, both directions:

- baseline (L=52 @ 303d2449): `sim/load-transient/records/20261121-173242-303d2449.md`
- candidate (L=180 @ 7fd5183b): `sim/load-transient/records/20261121-173321-7fd5183b.md`

Both records FAIL the ratified row overall, as the pre-#709 design already
does. Counts below are recomputed from the 45 per-corner rows of each record
(corner x leg x metric keys, 2160 rows each; excursion limit 150 mV, recovery
limit 20 us):

| failing conditions | L=52 | L=180 |
|---|---|---|
| rise undershoot > 150 mV | 129 | 121 |
| fall overshoot > 150 mV | 50 | 30 |
| **excursion total** | **179** | **151** |
| recovery > 20 us (rise 270 + fall 270) | **540** | **540** |
| grid conditions passing | 1441/2160 | 1469/2160 |

The paired keys show 28 excursion checks recovered (all recovered, none of
the recovery checks) and **zero** newly failing checks. Margin at the
conditions that fail in both records is mixed, not uniformly better: rise
undershoot and fall overshoot shrink at all 121 / 30 shared failures (by
4.8-13.1 mV), the falling-edge recovery time improves at 255 of 270
conditions (up to 595 us shorter) but worsens at 15 (up to +16.6 us, e.g. 0.33 uF /
500 mOhm at fs/125C/2.97V, 106.7 -> 123.3 us), and the rising-edge recovery
time worsens at 150 of 270 conditions (up to +61.2 us) and improves at 120 (up to
-40.8 us); e.g. rising-edge recovery at fs/125C/2.97V, 4.7 uF / 0 mOhm,
worsens from 132.7 to 193.9 us. Load-transient therefore shows a marginal
improvement in excursion counts, no new failure class, and a recovery-time
change that goes both ways; it neither rejects nor rescues L=180, and the
rejection is the loop-gain grid above. (The candidate record's repo state
cites 7fd5183b, the landed-then-reverted candidate commit, which is why the
candidate commit is preserved in history rather than reset.)

## 4. EA_OUT wake-shaping screen (the alternative the attribution opened)

**Reproducibility caveat (read first).** The scratch decks and driver for this
section lived under the git-ignored `sim/build/` (`sim/build/issue709/`,
`sim/build/issue709-screen.py`) and were not committed; they are no longer
retrievable, so neither experiment below can be replayed from this repository.
The numbers are recorded as originally measured, with the corrections the
review of this note required, and they are **evidence of what was run, not a
reproducible record**. Same two screen corners, production DUT at L=52,
graded by the bench checker.

Circuit facts, from the committed baseline deck
`sim/bias-retopo/20261121-165832-rczL52/requests/loop-c033-esr0-1ma-v3.30.spice`
(the same netlist the L=52 screen deck derives from):

- `XM_ENP` (line 56): `EA_OUT EN VIN VIN` pfet, W=10 L=0.5 — it clamps
  **EA_OUT** to VIN while EN is low. It is *not* the PB clamp.
- `XM_ENP5` (line 66): `PB EN VIN VIN` pfet, W=2 L=0.5 — this is the **PB**
  clamp.
- `XM_MIRP2` (line 64): `EA_OUT PB VIN VIN` pfet, W=20 L=4 nf=4 — the
  gain-stage PMOS mirror on the signal path.

- **w1 gate-RC "soft release" — what was run is not recoverable.** The
  earlier text called this a 100 us soft release of "M_ENP (PB clamp)". That
  was wrong on two counts: the cited RC (`REN5`/`CEN5` = 100 kOhm x 1 pF) is a
  time constant of **100 ns**, not 100 us; and the PB clamp is `XM_ENP5`, not
  `XM_ENP` (which sits on EA_OUT), so the label named the wrong device. Which
  gate (`XM_ENP`, `XM_ENP5` or both) the RC was actually placed on cannot be
  established because the deck is gone (recorded sha256 prefixes 2278231b tt /
  059522b5 sf identify files that are not retrievable). Measured as run:
  Q = 8.562 pC (tt) / 21.326 pC (sf/-40C/2.97V), i.e. a 15.6 % / 1.3 %
  reduction, all bounds passing, no sag. Because the time constant was
  100 ns, **this result does not rule out a 100 us soft release**, and a 100 us
  release has not been measured.
- **w2 PB-branch slew trade (`XM_MIRP2` W=20/nf=4 -> W=40/nf=8)** — deck
  sha256 prefixes 20db30d7 tt / ddf40466 sf (also not retrievable): the output
  settles 60-90 mV BELOW regulation at every leg of both corners (vfloor
  1.716-1.740 V vs the 1.764 V bound): `XM_MIRP2` is the gain stage's PMOS
  mirror (signal path), so its sizing is not a wake-only knob. BOUNDS FAIL;
  direction not adopted.
- **ceiling already measured by #693**: deleting M_ENP5 entirely (p3, 6.65 pC)
  cuts only ~35 % and breaks the EN=0 clamp contract; slowing soft-start 10x
  (p2b) makes the packet 3.4x WORSE.

What this supports: of the wake-shaping variants that were run, none gave a
reduction near L=180's 85-88 %, and the one that moved the packet at all
(w2) broke regulation. What it does **not** support is a claim that wake
shaping as a class "does not qualify": the 100 us EA_OUT/PB soft release is
untested. Wake shaping is left **open**, with the L=180 loop-gain rejection
(section 2) as the only rejection this note establishes. A follow-up must
commit a deck delta (gate connection, R and C values) for both corners before
claiming either result.

## 5. What this note does NOT change

`tolerance_v` stays 0.0; the ratified Startup row, `spec/` and every decision
record are untouched; the startup record 20261117-221657-efb6bd6b is NOT
superseded (no 540-condition re-mint is run — there is no selected schematic
to mint it on) and `measurements/characterization.md` / the item-5 envelope /
`signoff/` keep citing it; `design/ldo_3v3in_1v8out.sch` keeps R_CZ L=52
(net design change of this issue's PR is zero). The residual packet (1.2-22 pC
at the screened conditions) still FAILs strict `tolerance_v = 0` (positive
drawdown at every screened leg; Startup signoff grade FAIL, see "Startup
grade"); whether a nonzero tolerance is acceptable remains the open
decision-record question it already was (see `sim/README.md`, "Startup ramp
monotonicity").
Follow-ups this note leaves open: an intermediate L (the PM cliff sits between
L=52 and L=180 — c033/1mA falls 74 -> 27 deg across it), a zero that moves
with load, or a C_COMP reduction (which the same loop-gain bench would have to
re-qualify), plus a reproducible 100 us EA_OUT/PB soft-release screen
(section 4); none is screened here.
