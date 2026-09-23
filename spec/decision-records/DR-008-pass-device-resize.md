# DR-008: pass-device re-sizing — DR-003's sizing point was the wrong bias point

- **Status**: **proposed** — not self-ratifying. DR-003's *sizing methodology*
  is ratified (via #1/DR-006), and this record contradicts part of it, so it
  is input to #1's ratification authority in the same way DR-007 is. The
  circuit change it justifies lands under issue #116 against a DRAFT-free,
  already-ratified spec row (`Dropout @ 50 mA`, `< 300 mV`) — **no spec row is
  edited, relaxed, or proposed for relaxation by this record.**
- **Date**: 2026-09-23
- **Author**: Builder agent (drafted per #116)
- **Ratifies against / input to**: #1 (Ratify the target spec — operator-only,
  the T1 gate); implemented by #116
- **Supersedes**: **DR-003 finding 3 only** ("Pass-device sizing methodology,
  refined", and its `W_total ≈ 2.47 mm` output). DR-003 findings 1 (the
  `V_in = V_out + dropout` test-point convention) and 2 (the `{ss, sf}`@125 °C
  co-binding corner) are **re-confirmed, not superseded** — this record's own
  screening reproduces both.

## Context

`spec/target-spec.md`'s ratified `Dropout @ 50 mA` row (`< 300 mV`) fails
**0/45 PVT corners**, best case 365 mV, on record
`sim/dropout-vs-load/records/20260825-081240-4cb27f8.md`. Issue #116 was filed
against that result, pointing at the sibling `gf180-ldo#139` — where the same
block in a different PDK was found shipping a pass device at **half** the width
its own sizing review assumed — and asking this port to run the same check
first: *is `M_PASS` built to the width this repo's own derivation called for?*

**It is.** The committed instance is `L=0.5 W=100 nf=25 mult=25`, i.e.
`W_total = 2500 µm`, against DR-003 finding 3's `W_total ≥ 2468 µm`. There is
no transcription gap of the `gf180-ldo#139` kind here — the schematic matches
its derivation to 1 %.

**The derivation is what is wrong.** DR-003 finding 3 named its own scope
caveats honestly — *"ideal 0 V gate drive, no fingering/contact/IR-drop
margin, no self-heating"*, and a screening deck taken at **deep triode
`V_sd` = 50 mV** — but never quantified what those caveats cost. They cost a
factor of 1.5, which is the entire gap between a row that fails everywhere and
a row that passes.

All device data below is fresh screening against the same pinned PDK every
other record here uses (`sky130A`, open_pdks
`c6d73a35f524070e85faff4a6a9eef49553ebc2b`, `sim/pdk.json`), same single-device
`op` method as DR-001/DR-003's own appendices. Per those records' convention
this is **screening, not `sim/` evidence** — no spec row is set from it. The
`sim/` evidence for the resulting circuit change is the full 45-corner
`dropout-vs-load` record minted by #116.

### Error 1: `R_on` was measured in deep triode and spent at 300 mV

DR-003's grid is `R_on·W` at `V_sd` = 50 mV — deep triode, where the device is
still linear. The spec row's own operating point is **`V_sd` = 300 mV at
50 mA**, six times further out, where it is not. Re-measuring at the row's own
bias point, binding corner, `V_sg` = 2.10 V:

| Quantity | DR-003 (`V_sd` = 50 mV) | This record (`V_sd` = 300 mV) |
|---|---|---|
| `R_on·W`, `sf`@125 °C, `V_sg` = 2.10 V | 14.81 kΩ·µm | **17.03 kΩ·µm** |

DR-003's number is **15 % optimistic** when spent where the row actually spends
it. (17.03 = 300 mV / 44.03 mA × 2500 µm, from the table below.)

### Error 2: the gate drive DR-003 sized at is not reachable

DR-003 screened with the gate held at a hard 0 V, giving `V_sg = V_in`. The
error amplifier cannot deliver that. Closed-loop screening of the shipped
schematic at 50 mA, stepping `V_in` down, measures `EA_OUT` **flooring at
0.24–0.31 V** — it does not approach 0 V at any `V_in` in or below the dropout
region, at either screened corner:

| `V_in` | `EA_OUT` (`tt`/27 °C) | `EA_OUT` (`sf`/125 °C) |
|---|---|---|
| 2.400 V | 0.711 V | 0.632 V |
| 2.200 V | 0.394 V | 0.319 V |
| 2.100 V | 0.313 V | 0.264 V |
| 2.064 V | 0.290 V | 0.241 V |

So the achievable gate drive at the row's test point is `V_sg ≲ 1.80 V`, not
2.10 V. This record deliberately reports the **measured floor** and does not
claim to have isolated its mechanism: the pull-down NMOS `M_MIR2`'s own
saturation voltage is the obvious candidate, but sizing needs the floor, not
its cause, and asserting a cause this screen did not separate would be the same
kind of unquantified assumption this record exists to correct.

### The two errors compound

Drive capability of the **committed 2500 µm** device at the row's own
`V_sd` = 300 mV (single-device screening, `I_d` in mA):

| Corner | `V_sg` = 2.10 V | 1.90 V | 1.80 V | 1.70 V |
|---|---|---|---|---|
| `tt`/27 °C | 55.17 | 45.93 | 41.02 | 35.91 |
| `ss`/125 °C | 44.10 | 37.65 | 34.26 | 30.75 |
| **`sf`/125 °C** | **44.03** | **37.27** | **33.71** | **30.03** |
| `ss`/−40 °C | 57.48 | 45.42 | 38.97 | 32.25 |
| `ff`/125 °C | 52.33 | 45.47 | 41.85 | 38.10 |
| `fs`/125 °C | 52.12 | 45.57 | 42.13 | 38.56 |

Two things fall straight out of that table, and the second is the finding:

- **DR-003 finding 2 is re-confirmed at the corrected bias point.** `sf` and
  `ss` at 125 °C remain the binding pair (44.03 / 44.10 mA, 0.2 % apart —
  still a tie this screen cannot resolve, still correctly carried as
  co-binding), and `ff`/`fs` remain the benign pair. The ranking groups by the
  corner name's *first* letter, exactly as DR-003 found.
- **The committed device misses the ratified row at *every* gate drive,
  including one it cannot reach.** At the binding corner it delivers
  **44.0 mA** at `V_sd` = 300 mV with an ideal 0 V gate — and the row needs
  50 mA. No amplifier improvement, no compensation change and no layout work
  can close a 0/45 that is bounded by the pass device's own drive capability
  at the test point. This is why the record's headline is a re-size and not a
  tuning exercise.

Required width at the binding corner, `V_sd` = 300 mV, 50 mA:

```
at DR-003's assumed (unreachable) V_sg = 2.10 V:  50 mA / 17.61 uA/um = 2839 um
at the achievable          V_sg = 1.80 V:        50 mA / 13.48 uA/um = 3709 um
```

and the same 3709 µm is reproduced by applying the two error factors to
DR-003's own output, which is the cross-check that they are the whole story:

```
2468 um  x  1.150 (deep-triode R_on)  x  1.306 (gate-drive floor)  =  3707 um
```

## Decision

**`M_PASS` is re-sized from `W_total` = 2500 µm to `W_total` = 5000 µm**
(`L=0.5 W=100 nf=25`, `mult` 25 → 50), and **`M_SENSE` is re-sized with it**
(`mult` 1 → 2, 0.42 µm → 0.84 µm) so the current-limit sense ratio stays at its
`#22`-sized 1:5952.

`DR-003 finding 3`'s `W_total ≥ 2468 µm` is superseded by **`W_total ≥ 3709 µm`
at the binding corner**, derived at the ratified row's own bias point
(`V_sd` = 300 mV) and at the amplifier's *measured* gate-drive floor rather
than at an ideal 0 V gate.

This record is **proposed**, not ratified; DR-003's superseded finding is
ratified, so only #1's ratification authority can complete the supersession.
The circuit change does not wait on that — it is a design change against an
already-ratified spec row, and #116 lands it with full-matrix `sim/` evidence.

**Amended sizing rule, for whoever sizes a pass device here next:** size at the
spec row's own `V_sd`, not at a deep-triode convenience point, and at the
amplifier's measured output floor, not at an ideal rail. A pass-device sizing
screen that holds the gate at 0 V is measuring a device the loop will never
build.

## Alternatives considered

**1. Lower the amplifier's output floor instead of widening the pass device.**
The attractive option: `EA_OUT` floors ~0.3 V above ground, and recovering that
would hand the pass device its full designed `V_sg` for a few µm² of NMOS
rather than 2500 µm of PMOS. **Rejected on arithmetic, not on preference**: it
only addresses error 2. Even with a *perfect* 0 V gate the committed device
delivers 44.0 mA at the binding corner against a 50 mA row — error 1 alone
leaves it 12 % short. Recovering the floor would reduce the required width
(2839 µm rather than 3709 µm) but cannot avoid a re-size, so it is a
*width-reduction* option, not a *width-avoidance* one. Worth revisiting as
such once the row passes, if area proves binding.

**2. Lower the error amplifier's input common mode from 1.2 V to 0.6 V.**
A partial earlier attempt at #116 built exactly this — re-tap the feedback
divider 1:2 → 2:1 and add a matched 1:1 attenuator so the external
`VREF` = 1.2 V interface is unchanged — on the hypothesis that the PMOS input
pair's common mode, not the pass device, set the dropout. The hypothesis has a
real observation behind it: with the 1.2 V common mode `EA_TAIL` is pinned near
`V_cm + V_sg(M_IN)` ≈ 2.09 V regardless of `V_in`, leaving `M_TAIL` just
**6.7 mV** of `V_sd` at `V_in` = 2.10 V — the tail current source is collapsed
at the ratified test point. **Rejected for this row because it was measured and
it does not move it**: built and screened at `tt`/27 °C, `V_in` = 2.100 V,
50 mA, it moves `V_out` from 1.6738 V to 1.6805 V — **7 mV**, against the
~90 mV needed to reach the 1.764 V departure threshold. It restores tail
headroom (`V_sd(M_TAIL)` 6.7 mV → 351 mV) without restoring drive, because
`EA_OUT`'s floor barely moves with it (0.313 V → 0.306 V). The underlying
headroom observation is real and is preserved as a follow-up issue rather than
discarded; it is simply not this row's root cause, and bundling a
divider-ratio, soft-start-gain and loop-gain change into a dropout fix would
have confounded the very measurement that had to be taken.

**3. A larger `W_total` than 5000 µm.** 5000 µm is 1.35× the 3709 µm
requirement; more would buy margin toward the DRAFT stretch (`< 200 mV`) that
this record does **not** claim or chase. Deferred: area is a ratified row
(`< 0.1 mm²`) that currently carries no verdict at all, so spending width
beyond what the ratified 300 mV row needs would be spending an unmeasured
budget. Revisit if and when the stretch row is ratified *and* an area check
exists.

**4. A smaller `W_total` (e.g. 4000 µm).** Closer to the 3709 µm requirement
and cheaper in area, but the requirement is itself derived from a single-bin
`op` screen carrying DR-003's own unquantified caveats (no fingering, contact
or IR-drop margin, no self-heating). 4000 µm is 1.08× a number with more than
8 % of acknowledged optimism in it. 5000 µm is also exactly 2× the existing
instance, which keeps the layout generator's `W * mult` convention and the
`mult`-group unit unchanged (50 groups of the same `W=100 nf=25` unit).

## Consequences

> **Correction (2026-09-23, same day as the rest of this record).** The
> paragraph below originally claimed, from a single closed-loop `.op` screen
> at `V_in` = 2.000 V, that the re-sized device "regulates down to `V_in` =
> 2.000 V at both screened corners... dropout below 236 mV at both." **That
> claim does not reproduce and is wrong; do not cite it.** Re-running the
> identical screening script against the identical (already-resized) schematic
> — three independent times, including the exact saved variant the original
> number came from — gives two different answers depending on solver path: a
> "healthy" `V_out` = 1.7951 V matching the original claim, *and* a broken,
> non-physical solve (`FB` pinned at hundreds of volts, the singular-matrix
> signature this repo's own `design/README.md` "mechanism 4" section already
> documents) at the *same* `V_in`/corner/schematic. A single isolated `.op`
> point near the dropout knee is demonstrably not a reliable measurement for
> this circuit at this device size — it lands on whichever of several
> Newton-convergent solutions the solver's internal path happens to find, not
> necessarily the one the closed loop would actually settle into. **The
> amended sizing rule this record's own "Decision" section states should be
> read as additionally requiring the continuation-based `dc` sweep
> (`sim/bin/corner-run.py`'s own methodology) for any closed-loop dropout
> claim — never a single isolated `.op` point — because this record is the
> cautionary example of what trusting the latter costs.** The real,
> full-45-corner `sim/` evidence is below, superseding every number in this
> paragraph.

**What this fixes, per the real `sim/` record (`dropout-vs-load`
record `20260923-123440-d71f4b3`, superseding `20260825-081240-4cb27f8`,
`sim/dropout-vs-load/records/`).** The `Dropout @ 50 mA` row goes from a
whole-matrix **0/45 PASS** (best case 365 mV) to **6/45 PASS** (best case
268 mV). The improvement is real, substantial, and physically coherent — not
a wash:

- **At −40 °C and 27 °C, across all five process corners (29 of the 30
  corner points at these temperatures; the 30th, `ff_-40c_3.63v`, hit a new
  300 s harness timeout), dropout drops by 60–880 mV** relative to the
  pre-resize record, matching the direction and rough magnitude device
  physics predicts for a 2× wider pass device. `ss` closes the row outright
  (6/6 PASS at −40 °C/27 °C, was 0/6, dropout now 268–298 mV); `tt` narrows
  from 530–570 mV to 398–406 mV (still FAIL); `sf`/`fs` narrow from
  420–730 mV to 363–433 mV (still FAIL, `fs`/−40 °C at 363 mV is the closest
  miss in the record).
- **At 125 °C, the picture is not uniform.** 10 of 15 125 °C points still
  improve (100–590 mV lower), but 5 — `ss_125c` at all three supplies,
  `ff_125c_2.97v`, `fs_125c_2.97v` — get numerically *worse* (0.55–1.83 V,
  one (`fs_125c_2.97v`) reporting a non-physical `V_out` = −14.06 V). This is
  not a new failure mode: `design/README.md`'s "mechanism 4" section already
  documents a genuine, root-caused (#81) dc-solution-multiplicity /
  second-equilibrium problem at 125 °C for the pre-resize device, with the
  standing caution to read 125 °C `dropout-vs-load` numbers as "solver
  artifact, not a literal measurement." The re-sized device's 125 °C numbers
  should be read with the same caution, more so — the resize appears to have
  made an already-documented fragility *more* pervasive (more corners hit it,
  larger excursions) rather than introducing a new one. This is handed to a
  follow-up rather than investigated further here (see "What it costs"
  below).

The full corner-by-corner comparison is in the `sim/` record itself; this
record does not restate all 45 rows.

**What it costs — stated, not buried:**

- **125 °C dc-sweep reliability.** As above: the resize appears to widen the
  already-documented mechanism-4 dc-solution-multiplicity fragility's
  footprint at 125 °C (more corners, larger excursions) rather than introduce
  a new mechanism. Filed as follow-up #138 rather than root-caused here — the
  existing #79/#81 owners are the natural place for it, since it is the same
  underlying loop-dynamics question.
- **Area.** The pass device roughly doubles: its floorplan block goes from
  ~43.4 µm × 101.12 µm (≈ 4.4 × 10³ µm²) to about twice that. The ratified
  `Area < 0.1 mm²` row has **no verdict today** (`measurements/characterization.md`
  reports it `N/A` — no area-extraction check exists), so this cost is
  currently unmeasured rather than cheap. It is handed to design unresolved.
- **Stability.** `#116` flags this explicitly: a larger pass device moves the
  output pole and raises `gm_pass`, and the `Stability` row is already failing
  7/45. This record does **not** claim the re-size is stability-neutral and
  does not re-derive `C_COMP`/`R_CZ`. Handed to design unresolved, as a
  named follow-up.
- **Gate capacitance.** Doubling `W_total` doubles the load `EA_OUT` drives,
  which interacts with both the compensation above and the `Load transient`
  row (25/45). Not re-derived here.
- **Layout.** `layout/ldo-core` must be regenerated; its committed DRC/LVS
  records characterize the 2500 µm device and are stale against this change by
  construction.
- **Every other `sim/` bench.** All benches instantiate this DUT, so their
  committed netlist snapshots go stale — `measurements/characterization.md`
  will report them `STALE` exactly as it correctly did after #69. That is the
  report working, not failing.

**What it does not touch.** No spec row is edited or relaxed. The current-limit
threshold is deliberately held constant by re-sizing `M_SENSE` in the same
ratio — without that, doubling `M_PASS` alone would have halved the sense
signal and silently doubled the limit, invalidating the ratified `Current
limit` row's current 45/45 PASS. DR-003 findings 1 and 2 stand, re-confirmed.

## Status notes

Stays **proposed** until #1 (spec ratification, operator-only) rules on the
supersession of DR-003's ratified finding 3, under the same
ratification-via-PR standing policy DR-003 and DR-007 both cite. Nothing in
this record ratifies itself.

The design change it justifies is **not** gated on that: #116 lands the
re-size with full 45-corner `sim/` evidence against an already-ratified row,
and the record exists so the sizing argument is checkable rather than
asserted. If #1 rejects the supersession, what must change is this record and
the width it justifies — not the spec row, and not the evidence.
