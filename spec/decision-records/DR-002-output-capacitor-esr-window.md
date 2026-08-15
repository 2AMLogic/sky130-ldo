# DR-002: Output-capacitor / ESR window

- **Status**: proposed — not self-ratifying; input to #1
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

This record stays `proposed` until #1 closes. #1's ratification of this
record settles the C_out/ESR **window's boundary numbers** as an input to
#1's own ratification of the Load-transient and Stability spec rows — it
does not, by itself, verify the "no minimum ESR" stability claim for
sky130-ldo's actual loop, which requires a `sim/` loop-gain record against a
real compensation topology that does not exist yet. If that future
simulation shows this window's stability posture is unreachable, a
superseding record replaces this one; this record is not edited after the
fact.
