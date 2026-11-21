# Qualification note 20261121-709: R_CZ L=180 loop-gain rejection and the EA_OUT wake-shaping screen

**Status: qualification note (issue #709), not an evidence record.** Append-only
note under `sim/startup/pilots/`; the graded evidence behind it is the four
fleet records named below. Nothing here changes `tolerance_v`, the ratified
Startup row, `spec/` or any decision record; no startup record is superseded
and no envelope is minted (there is no adopted design change to re-mint on).

## Verdict (one line)

**L=180 is REJECTED by loop-gain co-verification and no wake-shaping
alternative qualifies: adoption of a compensation change stays OPEN, the
schematic keeps `R_CZ` L=52 (candidate landed as 7fd5183b and reverted as
28b0ae5e on `feature/issue-709`), and the 20261117-221657-efb6bd6b startup
record remains the record of record.** The startup screen itself reproduced
exactly (85.5-87.9 % packet reduction, every electrical bound passing, no
oscillatory sag) — the rejection is the compensation zero moving ~3.5x down:
loaded-leg phase margin collapses while the no-load legs improve, so L=180 is
past the two-sided optimum on the loaded side, the direction the #25 screening
table had already flagged.

## 1. Two-corner startup screen, production DUT (reproduction of #693's step-4 screen)

`corner-run.py sim/startup --backend local --process {tt,sf} --temp {27,-40}
--supply {3.30,2.97} --no-write`, all 12 window-grid legs per corner, graded by
the bench's own checker; base decks are the harness-minted corner decks at repo
state `303d2449` (L=52) and `7fd5183b` (L=180):

| DUT | corner | dd c330n/0mA/ESR10m (uV) | Q = dd x C_out (pC) | dd c4u7/0mA (uV) | vpk/vfloor/tramp bounds |
|---|---|---|---|---|---|
| L=52 | tt/27C/3.30V | 30.733 | 10.142 | 2.165 | pass |
| L=180 | tt/27C/3.30V | 3.715 | 1.226 | 0.264 | pass (tramp 0.321-0.431 ms) |
| L=52 | sf/-40C/2.97V | 65.492 | 21.612 | 4.615 | pass |
| L=180 | sf/-40C/2.97V | 9.515 | 3.140 | 0.675 | pass (tramp 0.249-0.391 ms) |

Packet reduction 87.9 % (tt) / 85.5 % (worst corner), matching the #693 screen
(1.226 / 3.140 pC exactly). Loaded legs stay small single-digit-uV drawdowns
(c330n/50mA: 4.09 uV tt, 7.43 uV sf) — the 0.33 uF/50 mA traces were inspected
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

Worst-PM-per-leg (deg, over 45 PVT points; ratified bounds PM >= 45, GM >= 10):

| leg | L=52 worst PM | L=180 worst PM | PM<45 pts L=52 -> L=180 |
|---|---|---|---|
| c033/0mA (all ESR) | 15.45 (ss/-40C/2.97V) | 26.99 (fs/-40C/2.97V) | 33 -> 33 |
| c033/1mA (all ESR) | 74.0 | 27.0 (sf/-40C/3.63V) | **0 -> 45** |
| c033/50mA (ESR0/10m) | 31.0 (sf/-40C/3.63V) | 13.0 (sf/-40C/3.63V) | 33-34 -> 45 |
| c033/50mA (ESR500m) | 45.65 | 26.08 (ss/125C/3.63V) | **0 -> 45** |
| c4u7/0mA (all ESR) | 37.84 (ss/-40C/2.97V) | 40.15 (ss/-40C/2.97V) | 11-12 -> 10 |
| c4u7/1mA (all ESR) | 44.90 (fs/125C/2.97V) | 70.51 (sf/-40C/3.63V) | 0-1 -> 0 |
| c4u7/50mA (all ESR) | 73.73 (ff/-40C/3.63V) | 27.00 (ff/-40C/3.63V) | **0 -> 45** |

Totals: sub-45 PM points **203 -> 489 of 810**; GM < 10 dB stays **0**
(candidate worst GM 10.71 dB at c033/ESR0/50mA sf/-40C/3.63V vs baseline 14.79
dB there; the c4u7/ESR500m/1mA GM unavailability of the baseline record
disappears at L=180). Per-point deltas: 405 points worse by >5 deg against 237
better by >5 deg; c033/1mA regresses -47..-51 deg at ALL 45 points, c4u7/50mA
by -32..-51 deg, c033/50mA by -18..-34 deg, while the 0 mA legs improve
+0..+13 deg and c4u7/1mA +12..+33 deg — the two-sided optimum of the #25 table,
re-measured: the lower zero buys the light-load corners and takes the margin
out of the loaded ones. The baseline's own no-load shortfall (documented in
design/README.md "Compensation") is unchanged in character; what is NEW at
L=180 is the loaded-leg collapse, so L=180 fails the issue's "evidence
supporting stability" adoption clause.

## 3. Load-transient co-verification (matched DUTs)

`corner-run.py sim/load-transient --backend batch`, full 45-corner x 6-leg
grid, both directions:

- baseline (L=52 @ 303d2449): `sim/load-transient/records/20261121-173242-303d2449.md`
- candidate (L=180 @ 7fd5183b): `sim/load-transient/records/20261121-173321-7fd5183b.md`

Both records FAIL the ratified row overall, as the pre-#709 design already
does (known-excursion/recovery findings). Matched comparison: excursion
>150 mV conditions 185 (L=52) -> 156 (L=180), recovery >20 us 554 -> 555,
grid conditions passing 1441/2160 -> 1469/2160. Load-transient therefore shows
a marginal improvement and no new failure class — it neither rejects nor
rescues L=180; the rejection is the loop-gain grid above. (The candidate
record's repo state cites 7fd5183b, the landed-then-reverted candidate commit,
which is why the candidate commit is preserved in history rather than reset.)

## 4. EA_OUT wake-shaping screen (the alternative the attribution opened)

Same two screen corners, production DUT at L=52, scratch decks under
`sim/build/issue709/` graded by the bench checker (driver
`sim/build/issue709-screen.py`):

- **w1 soft-release of M_ENP (PB clamp)** — gate RC REN5/CEN5 tau = 100k x 1p
  = 100 us inside the subckt (deck sha256 prefixes 2278231b tt / 059522b5 sf):
  Q = 8.562 pC (tt) / 21.326 pC (sf/-40C/2.97V) — a 15.6 % / 1.3 % reduction.
  All bounds pass, no sag; the packet is essentially unchanged at the worst
  corner. Consistent with #693's attribution: the balance of the packet rides
  on the bias/diff-pair wake (M_ENP2/M_ENN/M_ENN2), not on the PB release.
- **w2 PB-branch slew trade (M_MIRP2 W=20/nf=4 -> W=40/nf=8)** — deck sha256
  prefixes 20db30d7 tt / ddf40466 sf: the output settles 60-90 mV BELOW
  regulation at every leg of both corners (vfloor 1.716-1.740 V vs the 1.764 V
  bound): M_MIRP2 is the gain stage's PMOS mirror (signal path), so its sizing
  is not a wake-only knob. BOUNDS FAIL; direction rejected.
- **ceiling already measured by #693**: deleting M_ENP5 entirely (p3, 6.65 pC)
  cuts only ~35 % and breaks the EN=0 clamp contract; slowing soft-start 10x
  (p2b) makes the packet 3.4x WORSE.

The wake-shaping route therefore tops out far below L=180's 85-88 % packet
reduction while either leaving regulation/shutdown contracts intact (w1: no
meaningful reduction) or breaking them (w2, p3). It does not qualify.

## 5. What this note does NOT change

`tolerance_v` stays 0.0; the ratified Startup row, `spec/` and every decision
record are untouched; the startup record 20261117-221657-efb6bd6b is NOT
superseded (no 540-condition re-mint is run — there is no selected schematic
to mint it on) and `measurements/characterization.md` / the item-5 envelope /
`signoff/` keep citing it; `design/ldo_3v3in_1v8out.sch` keeps R_CZ L=52
(net design change of this issue's PR is zero). Whether the residual 0.8-22 pC
packet still FAILs strict `tolerance_v = 0` remains the open decision-record
question it already was (see `sim/README.md`, "Startup ramp monotonicity").
Follow-ups this note leaves open: an intermediate L (the PM cliff sits between
L=52 and L=180 — c033/1mA falls 74 -> 27 deg across it), a zero that moves
with load, or a C_COMP reduction (which the same loop-gain bench would have to
re-qualify); none is screened here.
