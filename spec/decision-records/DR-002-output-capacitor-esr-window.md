# DR-002: Output-capacitor / ESR window

- **Status**: **ratified** — window ratified by #1 (DR-006), pending operator
  PR approval per the 2026-08-19 ratification-via-PR standing policy
  ([2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357)). The
  window's numeric boundaries (0.33–4.7 µF, 0–500 mΩ, no minimum ESR) are
  ratified; the "no minimum ESR" *stability claim* is only partially
  substantiated — see DR-006 for the disclosed 0 mA-corner gap this record's
  own 2026-08-17 append already found.
- **Date**: 2026-08-14
- **Author**: Builder agent (drafted per #10)
- **Ratifies against / input to**: #1 (Ratify the target spec — operator-only,
  the T1 gate)
- **Supersedes**: none

## Context

`spec/target-spec.md`'s Load transient and Stability rows both reference "the
ratified C_out/ESR window" without a window existing yet — open item 2:
"Output-capacitor / ESR window. Mirror gf180-ldo's DR-0001 or re-derive for
sky130. Decision record required." DR-001 (ratified framing) explicitly
sequenced this record to come *after* framing and device characterization:

> The C_out/ESR window (open item 2) must be decided *after* this one, not in
> parallel. It depends on framing (A) twice over: the C_out floor is set by
> the excursion budget and the loop's large-signal response time... and the
> pass gate's ~3.9 pF against the amplifier's output resistance forms an
> internal pole that is close enough to the loop bandwidth to be a
> first-class stability element... Sequencing: ratify (A) → characterize the
> device (open item 3) → size the pass device → then draft the C_out/ESR
> record.

This record follows that sequencing, using DR-003's refined sizing
(W ≈ 2.5 mm at L = 0.50 µm bin floor, `C_gate` ≈ 3.6–3.9 pF at the
worst-case corner) in place of DR-001's earlier rough estimate.

The porting baseline is `2AMLogic/gf180-ldo`'s DR-0001 (ratified 2026-07-31),
which sets that block's window at **C_eff 0.33–4.7 µF, ESR 0–500 mΩ, no
minimum ESR (ceramic-stable)**, with capless as a separate design fork.
CLAUDE.md's port-parity clause explicitly sanctions consulting gf180-ldo as
this repo's porting baseline: "the spec and structure mirror the ratified
`2AMLogic/gf180-ldo`... where sky130 forces a departure, record the
divergence in `spec/` rather than diverging silently." The external output
capacitor is a board component, not a PDK device, so nothing about it is
sky130-specific by itself — but the *loop* it sits in front of is, because
the pass device is different.

**gf180-ldo's own record already names the exact risk this repo now faces.**
DR-0001's cross-consequences section states:

> **DR-0002 (input flavor)**: deferring the 5 V flavor keeps the pass device
> on `pfet_03v3`, whose lower `Cgate` per unit `Rds(on)` makes the high-`p2`
> requirement above materially easier. A 5 V-now decision would have made
> this record's no-minimum-ESR posture harder to hold.

sky130-ldo's DR-001 ratified exactly the "5 V-now" scenario gf180-ldo's own
authors flagged as harder for a ceramic-stable posture. Mirroring gf180's
window verbatim without addressing that flag would ignore a warning written
by the port's own source record.

## Decision

**Propose mirroring gf180-ldo DR-0001's numeric window as sky130-ldo's DRAFT
starting point — C_eff 0.33–4.7 µF (1 µF nominal, X5R/X7R, ≥ 6.3 V rating),
ESR 0–500 mΩ, no minimum ESR, ceramic-stable as the primary design with
capless as a separate fork — while explicitly flagging, not resolving, the
elevated stability risk sky130's larger pass-gate capacitance creates for
that "no minimum ESR" posture, and stating what must be true before the
window is treated as more than a starting point.**

| Item | Proposed value (mirrors gf180-ldo DR-0001) |
|---|---|
| Recommended component | 1 µF ± 20 %, X5R or X7R, ≥ 6.3 V rating |
| Verified effective capacitance `C_eff` | 0.33 µF ≤ `C_eff` ≤ 4.7 µF, inclusive of tolerance, DC-bias derating at 1.8 V, temperature coefficient over −40…125 °C, and aging |
| Verified ESR window | 0 ≤ ESR ≤ 500 mΩ over the same range (no minimum ESR) |
| Load range | 0–50 mA (0 mA = no external load; feedback-divider preload only) |
| Stability criterion | worst-corner phase margin ≥ 45° and gain margin ≥ 10 dB across the full matrix |
| Capless | out of scope for the primary design; a forked variant, own compensation architecture |

### Why the numbers are proposed unchanged, but the posture is flagged

The gf180-ldo derivation of 0.33–4.7 µF is about the *external capacitor's*
derating (tolerance × DC-bias × temperature-coefficient × aging), which is a
board-component property independent of which PDK or pass device sits behind
it — nothing sky130-specific changes that arithmetic, so this record does not
re-derive it. The 500 mΩ ESR ceiling is likewise set by the load-transient
budget (50 mA × 0.5 Ω = 25 mV, 1.4 % of 1.8 V) against the *same* ±2 % output
window and the *same* 0–50 mA load range this repo's DRAFT spec states — also
unchanged by the pass-device swap. **What does change is whether the loop can
actually hold phase margin at the low-`C_eff`/low-ESR corner with no minimum
ESR to help it**, and that is a sky130-specific question this record can
flag but not answer without a loop-gain simulation.

Quantifying the flag: DR-001 estimated sky130's pass device needs ≈ 2.7×
gf180's `pfet_03v3` width for the same on-resistance at equal overdrive
(0.50 µm vs 0.28 µm `lmin`, 11.75 nm vs 7.9 nm `toxe`), and DR-003 now grounds
a concrete gate capacitance at the actual sizing point: **`C_gate` ≈ 3.6–3.9
pF**, versus gf180-ldo's presumably smaller `pfet_03v3` gate capacitance at
its own (narrower) sizing — this record does not have gf180-ldo's `Cgate`
figure to cite precisely (out of scope to re-derive gf180's own numbers
here), but the ≈ 2.7× width ratio at comparable or thinner oxide means
sky130's pass-gate pole

```
p2 = 1 / (2π · Rgate · Cgate)
```

sits at a **lower** frequency than gf180's for the same amplifier output
resistance, which tightens exactly the margin between `p2` and loop crossover
that a ceramic-stable, no-minimum-ESR posture depends on (`architecture-
survey.md` §"loop-gain-dominated regime" in gf180-ldo develops this
formula's role in that block's own stability argument; sky130-ldo has no
architecture survey yet — this record cites the formula, not gf180's
conclusions from it, since this repo's amplifier topology does not exist).
**This record does not know whether that tightened margin is still
survivable** — no amplifier/compensation topology exists yet in this repo to
simulate against — and says so plainly rather than asserting either outcome.

## Alternatives considered

- **Adopt gf180's window unconditionally, as ratified-by-analogy.** Rejected
  — port parity is a starting point per CLAUDE.md, not a substitute for
  arguing the sky130-specific case, and gf180-ldo's *own* DR-0001 already
  flags this exact risk under a 5 V pass device. Silently inheriting the
  window without carrying that flag forward would ignore a warning written
  into the port's own source record.
- **Re-derive an entirely new window from first principles now.** Deferred,
  not rejected. Doing so honestly requires a loop-gain simulation against a
  real amplifier/compensation topology, and none exists yet — issue #10's
  brief does not include standing up an amplifier, and CLAUDE.md's
  no-invented-numbers rule applies here as much as to any spec row. Once a
  topology exists, its own decision record should either confirm this
  window or supersede it with simulated evidence.
- **Require a minimum ESR (classic ESR-zero compensation) to buy back
  margin cheaply.** Named, not chosen, for the same reason gf180-ldo's
  DR-0001 rejected it: modern 1 µF MLCCs have 5–20 mΩ of ESR, so any
  meaningful minimum excludes the ceramic parts a user would actually fit,
  forcing a discrete series resistor and forfeiting the transient
  performance low ESR buys. **If a future loop-gain sim shows ceramic-stable
  is unreachable at sky130's `Cgate`, this is the fallback a superseding
  record should evaluate first**, ahead of narrowing the `C_eff` window.
- **Narrow the `C_eff`/ESR window pre-emptively** (e.g. raise the ESR floor,
  or narrow `C_eff` to build in headroom against the larger `Cgate`, without
  waiting for a loop-gain sim). Rejected for now — this would be inventing a
  number the repo has not earned, exactly what CLAUDE.md prohibits. Flagging
  the risk in Consequences, rather than pre-emptively pricing it into the
  window, is judged the more honest move at this proposed-record stage.
- **Widen the ceiling (10 µF, or "no maximum")** or otherwise diverge from
  gf180's envelope for reasons unrelated to the pass-device risk above.
  Not raised — nothing in DR-001 or DR-003 gives a sky130-specific reason to
  move the capacitance ceiling; the risk this record identifies is about the
  ESR floor and phase margin, not capacitance range.

## Consequences

- If #1 ratifies this record's proposed window, C_out/ESR verification for
  sky130-ldo proceeds on the **identical numeric envelope** gf180-ldo uses
  (0.33–4.7 µF, 0–500 mΩ), preserving the cross-PDK comparison CLAUDE.md and
  `README.md` frame as this repo's purpose — same block's transient/stability
  matrix is directly comparable across the two PDKs once both are verified.
- **Hands to design, unresolved**: a compensation architecture that places
  `p2` (now credibly larger-`Cgate` than gf180's) far enough above loop
  crossover to hold the no-minimum-ESR posture at the 0.33 µF/0 mΩ corner.
  This record does not pick a topology (two-stage Miller vs. a
  low-impedance/buffered gate driver, in gf180-ldo survey terms) — that is a
  later topology record's job — but puts the requirement on record now so
  that record inherits it explicitly rather than discovering it late.
- **If the eventual loop-gain simulation shows the ceramic-stable window is
  not reachable at sky130's `Cgate`**, the correct response is a superseding
  DR-002 — evaluating a minimum-ESR fallback first, per Alternatives — not
  silently narrowing the window or requiring a minimum ESR in layout
  guidance without a record.
- **Feeds the future stability/load-transient testbench matrix directly**,
  same sweep shape as gf180-ldo's DR-0001 Consequences section:
  `I_load × C_eff × ESR × T × Vin × process`, with `process` bound to the
  five names DR-004 confirms and carrying `ss` *and* `sf` as co-binding per
  DR-003, not `ss` alone.
- **No numeric value in `spec/target-spec.md` changes because of this
  record.** The Stability and Load-transient rows stay DRAFT until #1
  rules, and even after #1 ratifies the window's boundary numbers, the "no
  minimum ESR" stability *claim* remains unverified until a loop-gain `sim/`
  record exists.

## Status notes

**Ratified by DR-006 / #1, pending operator PR approval (2026-08-19).** This
record's proposed window (0.33–4.7 µF, 0–500 mΩ, no minimum ESR) is adopted
as the ratified C_out/ESR window feeding `spec/target-spec.md`'s Load-transient
and Stability rows. Per this record's own 2026-08-17 append, the "no minimum
ESR" stability *claim* is **confirmed at every load ≥ 1 mA** across the tested
subset but **not confirmed at 0 mA** (15.6–19.3° PM at 0.33 µF, 38.1° at
4.7 µF/`ss` — below the DRAFT 45° row). Ratifying the window's boundary
numbers does not retroactively close that gap; see DR-006 for how the
ratified spec treats it (a disclosed, tracked design gap, not a reason to
widen the window or add a minimum ESR — the append's own root-cause analysis
already shows a minimum ESR would not fix it). If a future simulation shows
this window's stability posture is unreachable at any *design-fixable* point,
a superseding record replaces this one; this record is not edited after the
fact.

---

## Append (2026-08-17, issue #25): the loop-gain record this record asked for

**This is an append, not an edit.** Nothing above has been changed. Per
`spec/decision-records/TEMPLATE.md` a record that turns out to be wrong is
superseded, never quietly rewritten; this append adds the measurement the
record above explicitly sequenced itself in front of, and states what that
measurement does and does not settle. The record's **Status stays
`proposed`** and its **numeric window is unchanged** — 0.33–4.7 µF,
0–500 mΩ, no minimum ESR.

### What was measured

Issue #25 rebuilt the error-amplifier output stage (a current-mirror OTA
whose output is the drain of a PMOS sourced from `VIN`, so the pass gate can
be driven to `VIN`) and sized its compensation — `C_COMP = 150 pF` in series
with a ≈300 kΩ nulling resistor `R_CZ` — against a new AC loop-gain
testbench, `sim/loop-gain`. That testbench walks this record's proposed
window inside one deck at every PVT point the corner runner sweeps: `C_eff` ∈
{0.33 µF, 4.7 µF} × load ∈ {0, 1, 50 mA} at 10 mΩ ESR, plus the 500 mΩ ESR
ceiling at 0.33 µF/50 mA. First record: `20260818-014128-01b7905`, a 3-corner
`--quick` subset (`tt`/27 °C/3.30 V, `ss`/−40 °C/2.97 V, `ff`/125 °C/3.63 V);
the 45-point matrix remains issue #19's job.

Phase margin, degrees, against `spec/target-spec.md`'s DRAFT Stability row
(PM ≥ 45°, GM ≥ 10 dB worst corner) and the window row above:

| Window point | `tt`/27 °C | `ss`/−40 °C | `ff`/125 °C |
|---|---|---|---|
| 0.33 µF, 10 mΩ, 50 mA — **this record's low-`C_eff` corner** | 58.6 | 55.6 | 64.5 |
| 0.33 µF, 10 mΩ, 1 mA | 90.1 | 89.2 | 91.2 |
| 0.33 µF, 10 mΩ, 0 mA | **19.3** | **15.6** | 82.0 |
| 4.7 µF, 10 mΩ, 50 mA | 90.4 | 90.4 | 90.7 |
| 4.7 µF, 10 mΩ, 1 mA | 50.8 | 53.9 | 46.7 |
| 4.7 µF, 10 mΩ, 0 mA | 52.0 | **38.1** | 89.6 |
| 0.33 µF, 500 mΩ, 50 mA — the ESR ceiling | 70.5 | 68.3 | 75.2 |

Gain margin is 18.7–19.9 dB at the low-`C_eff` corner and 70.2–71.0 dB at the
0 mA points, i.e. above the 10 dB row wherever the record measures it.

### What this settles, and what it does not

**Settles, in this record's favour, the corner it was most worried about.**
The Context and Consequences sections above single out "the 0.33 µF/0 mΩ
corner" and the "elevated stability risk sky130's larger pass-gate
capacitance creates" as the reason the no-minimum-ESR posture was a claim
rather than a result. At 50 mA that corner now measures 55.6–64.5° of phase
margin with 18.7–19.9 dB of gain margin, and it does so with 10 mΩ of ESR —
i.e. with no ESR zero helping. The `p2` requirement this record "handed to
design, unresolved" was met by a single-gain-stage topology plus
Miller-with-nulling-resistor compensation, not by requiring ESR.

**Does not settle the no-load end of the load range.** The 0 mA points are
now the binding ones: 15.6–19.3° at 0.33 µF and 38.1° at 4.7 µF/`ss`. Two
observations matter for whichever record acts on this:

1. **The minimum-ESR fallback this record names first under Alternatives
   would not fix it.** The ESR zero sits at `1/(2π·ESR·C_out)`, which is
   ≈965 kHz even at this record's 500 mΩ ceiling with 0.33 µF — roughly three
   decades above the ~300 Hz crossover at that operating point. Requiring a
   minimum ESR buys nothing here. That is a concrete result against the
   Alternatives section's own preferred fallback, and it is the single most
   useful thing this append contributes.
2. **The shape is a low-frequency pole/zero doublet dip, not an erosion
   toward oscillation.** Gain margin at those points is ~70 dB — the phase
   dips toward −160° while the loop gain is still tens of dB from unity. The
   transient signature is ringing and slow settling at no load, not a limit
   cycle. This is stated so a later reader does not equate "19°" with
   "nearly unstable", and it is *not* offered as a reason to treat the DRAFT
   45° row as met. It is not met at those points.

**Root cause, so a superseding record does not have to re-derive it.** Under
Miller compensation the loop crossover must stay below the pass stage's own
pole `gm_pass/(2π·C_out)`. In weak inversion `gm_pass = I_load/(nV_T)`, so
that pole falls in proportion to load current: ≈72 kHz at 50 mA/0.33 µF but
≈7 Hz at the 0 mA operating point, where the only load is the block's own
~3.1 MΩ feedback divider (≈0.6 µA). No value of `C_COMP` reaches that: the
two levers that would are more amplifier bias current or a real preload, and
both spend the DRAFT `Iq < 30 µA` row, which issue #25 already took to
24.9 µA at 50 mA. Screening confirmed the trade directly — a 6× amplifier
tail lifted the 0 mA/0.33 µF margin to ~40° and pushed Iq to 33.6 µA, over
the row, so it was not taken. Relaxing one DRAFT row to make another pass is
what `CLAUDE.md` forbids.

### What this append does NOT do

- It does **not** narrow the `C_eff` or ESR window. Consequences above says a
  shortfall gets a superseding record, not a quiet narrowing, and the
  shortfall here is on the *load* axis (0 mA), not the capacitor axis.
- It does **not** introduce a minimum ESR. Point 1 above shows it would not
  help, which is a stronger reason to leave the posture alone than the
  original argument (that 1 µF MLCCs have 5–20 mΩ anyway).
- It does **not** change the record's Status, and it does not claim to
  ratify anything. Issue #1 still ratifies this record; issue #19 still owns
  the 45-point matrix that would turn a 3-corner subset into a worst-corner
  claim.

### What a superseding record would need

A superseding DR-002 (or a new record on the load range / minimum-load
question) is warranted if #19's full matrix confirms the no-load shortfall
across the remaining corners. The candidates it should weigh, in the order
this measurement suggests rather than the order the Alternatives section
above guessed:

1. **A stated minimum load** (or an internal preload) as a datasheet-style
   condition on the Stability row — the direct lever on `gm_pass`, and the
   one the physics points at. Costs Iq, so it is coupled to the still
   non-existent Iq budget record DR-003 declined to write.
2. **An Iq budget record**, which this design has now hit twice as a hard
   constraint (once here, once in issue #25's amplifier sizing). Without one,
   "spend more bias current" is unarbitrable.
3. **A minimum ESR**, ranked *below* the two above by this measurement rather
   than above them as Alternatives assumed.
