# DR-006: Ratification of the target specification

- **Status**: proposed — this record does not ratify itself; #1's ratifying
  action is the operator's PR approval on the pull request this record ships
  in, per the 2026-08-19 ratification-via-PR standing policy
  ([2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357)): "a builder
  drafts the ratification/DR as a PR on the evidence, and the operator's PR
  approval is the ratification act."
- **Date**: 2026-08-19
- **Author**: Builder agent (drafted per #1, ratification-via-PR policy)
- **Ratifies against / input to**: #1 (Ratify the target spec — the T1 gate)
- **Supersedes**: none

## Context

`spec/target-spec.md` has been DRAFT since the repo was scaffolded, gated on
#1. DR-001 (2026-08-14) already ratified the block's *framing* — pass device
`sky130_fd_pr__pfet_g5v0d10v5`, 3.3 V ±10 % in / 1.8 V out / 0–50 mA, port
parity with `2AMLogic/gf180-ldo` — but explicitly scoped that ruling to the
framing question alone, leaving every numeric row DRAFT and #1 open as the
gate for the remaining three open items: the C_out/ESR window (item 2),
sky130 device characterization (item 3), and corner-model names (item 4).

Since then, three more decision records were drafted against those items —
DR-002 (C_out/ESR window), DR-003 (device characterization), DR-004
(corner-model names), all `proposed` as of PR #11 (merged 2026-08-15) — and a
fourth, DR-005 (thermal-shutdown trip/hysteresis/reference/behavior), was
drafted per #28 (PR #31, merged 2026-08-17) to answer a spec gap `design/
README.md`'s own "Known gaps" section surfaced once thermal-shutdown circuitry
work began. All four record their own Status notes identically: "stays
`proposed` until #1 closes… does not ratify itself."

**What has changed since DR-001: this repo now has real evidence, not just
methodology.** Between DR-002/003/004 landing (2026-08-15) and this record
(2026-08-19), the block acquired a full schematic (#14, #22, #25, #26, #29,
#36), a routed and LVS-matched layout (#33, #34, #39), DRC-clean and
post-layout PEX results (#16, #20), five spec-row testbenches (#18, #25:
load-transient, psrr-dc, dropout-vs-load, mc-output-accuracy, loop-gain), a
45-point PVT-corner + Monte Carlo verification pass (#19, PR #37, rebased onto
the current schematic by #40), and — the evidentiary input this record relies
on most directly — a generated, aggregated per-spec-row characterization
report (#21, PR #49, `measurements/characterization.md`) rolling all of the
above up against `spec/target-spec.md`'s current DRAFT rows.

**That report's central finding: the current implementation does not meet
most of the DRAFT numeric rows it has a testbench for.** Verbatim from
`measurements/characterization.md` as of `origin/main` @ `9a60c4c`:

| Row | Verdict (vs. current DRAFT) | Evidence |
|---|---|---|
| Output (1.8 V ±2 %) | **FAIL** | 181/200 mismatch samples pass at one nominal PVT point (`tt`/27 °C/1 mA); tail driven by a light-load pole, per the record's own "known-remaining-gaps" note |
| Dropout @ 50 mA (< 300 mV) | **FAIL** | 0/45 PVT corners pass; best case 365 mV (`ss`/−40 °C) vs. the 300 mV ceiling |
| Load transient (≤ 150 mV / ≤ 20 µs) | **FAIL** | 23/45 PVT corners pass |
| PSRR (> 50 dB @ 1 kHz, > 20 dB @ 100 kHz) | **FAIL** | 6/45 PVT corners pass, at the one load point (~1 mA) the testbench currently covers |
| Stability (PM ≥ 45°, GM ≥ 10 dB) | **FAIL** | 3/45 PVT corners pass — matches DR-002's own append: the 0 mA end of the load range is the binding failure, not the C_out/ESR window's low-`C_eff` corner it was drafted to worry about |

This is precisely the situation the ratification-via-PR standing policy names
explicitly: *"Failing-spec cases (a measured result missing a ratified target)
present the tradeoff options in the DR draft; the operator rules at PR
review."* This record is that presentation.

## Decision

**Ratify DR-002, DR-003, DR-004, and DR-005 as proposed — none of the four
change any pass/fail numeric threshold in `spec/target-spec.md`'s target
table; they set the C_out/ESR window boundaries, the dropout test-point
convention and sizing methodology (with the Iq budget explicitly left open),
the corner-name binding, and the thermal-shutdown trip/hysteresis/reference/
behavior respectively. Ratify `spec/target-spec.md`'s existing DRAFT numeric
targets unchanged from their gf180-ldo-mirrored starting point — do not
loosen any row to match the current implementation's measured shortfall.
Record the shortfall explicitly, row by row, as a disclosed, tracked design
gap for follow-on work, per CLAUDE.md's "a row that proves unmeetable is
superseded by a new decision record, never silently loosened."**

This is Option A of the two presented below. Option B (relax specific rows to
match measured results) is presented in Alternatives for the operator to
choose instead at PR review, per the standing policy's own instruction — this
record's recommendation is Option A, for the reasons stated there.

### What ratification changes in `spec/target-spec.md`

1. **Status banner**: "DRAFT" → "RATIFIED" for the framing and the numeric
   targets; the document gains an explicit statement that ratification fixes
   the *targets*, not a certification that the current implementation meets
   them — that status lives in `measurements/characterization.md`, which
   continues to be regenerated as the append-only rollup of current
   conformance, per issue #21's own design.
2. **Open items 1–4**: all four now resolved, citing DR-001/002/003/004.
3. **Verification corners**: gains DR-004's naming-severity caveat (corner
   letters do not predict severity for this device — `sf` groups with `ss`,
   not `ff`) so a future implementer does not shortcut the sweep.
4. **Dropout row note**: gains DR-003's test-point convention (`V_in = V_out +
   dropout`, not `V_in_min`) and co-binding-corner finding (`{ss, sf}` at
   125 °C).
5. **Load transient / Stability row notes**: gain the ratified C_out/ESR
   window (0.33–4.7 µF, 0–500 mΩ, no minimum ESR, ceramic-stable) from DR-002,
   with an explicit citation of the disclosed 0 mA stability gap rather than
   an implication that "ratified window" means "verified stable everywhere
   in it."
6. **Thermal row note**: gains a cross-reference to DR-005's fault-only
   150 °C/135 °C trip/reset window; the row's own `Tj ≤ 125 °C` rated-operation
   ceiling is unchanged — DR-005 sets a backstop above it, not a replacement.
7. **Iq row**: stays explicitly open/provisional (not ratified to a number) —
   DR-003 declined to set one, and none of the other three records touch it.
   `design/README.md` already reports the current design's own bias budget
   (≈24.9 µA at 50 mA per the loop-gain sizing work) as a data point for
   whichever future record sets this row, not as a ratified target itself.
8. **Every DRAFT numeric performance target row (Output, Dropout, Load
   transient, PSRR, Stability) keeps its current number, unchanged.** No
   number in the target table changes as a result of this record.

### Why Option A (ratify unchanged, disclose the gap) over Option B (relax to match)

- **CLAUDE.md's default is explicit and directional**: "agents do not relax a
  spec line to make a result pass. A row that proves unmeetable is superseded
  by a new decision record, never silently loosened." None of the five
  failing rows above has been shown *unmeetable* — each failure has a named,
  plausible, unexploited remedy still on the table:
  - **Stability (0 mA end)**: DR-002's append already root-causes this to the
    pass stage's own `gm_pass/(2π·C_out)` pole falling with load current, and
    names two concrete levers (a stated minimum load / internal preload, or
    an Iq budget record that funds more bias current) — neither has been
    tried and rejected, both are simply unbuilt.
  - **Dropout**: the measured shortfall (365 mV best case vs. 300 mV target)
    is consistent with a pass device sized below DR-003's own ≈ 2.5 mm
    recommendation, or unmodeled series resistance (routing/contact/IR drop,
    which DR-003's Appendix already flags as excluded from its screening
    numbers) rather than a target proven unreachable on this device family.
  - **PSRR / Load transient / Output accuracy**: all three testbenches'
    own claim text names the same open items (unsized `C_CL`, the
    error-amplifier's light-load pole, the still-missing Iq budget) as the
    likely drivers — again, unbuilt remedies, not a proof of infeasibility.
- **Relaxing now would be premature**: every failing row's own evidence
  record already states, in its own words, that the failure is "an honest,
  expected finding at this design stage… not a harness defect" — i.e., the
  testbenches themselves already frame these as design-maturity gaps. Writing
  that framing into a *spec* change would be circular: using "the design
  doesn't meet it yet" as the reason to lower the bar the design has to meet.
- **The alternative would forfeit the port-parity comparison.** `README.md`
  and CLAUDE.md frame this repo's purpose partly as a same-block,
  cross-PDK comparison against `2AMLogic/gf180-ldo`. Loosening sky130-ldo's
  targets below gf180-ldo's ratified numbers (DR-0004) for reasons that are
  about this design's current maturity, not sky130 device physics, would
  break that comparability for no device-physics reason.
- **The cost of Option A, stated plainly**: this ratification does not
  unblock any claim that the block currently meets spec. Follow-on design
  work (tracked via new issues, out of this record's scope to file) is
  required before the T1/bronze maturity ladder can advance past
  "spec-ratified" to a claim of spec-conformance. That is an accepted,
  disclosed cost — the alternative (silently loosening the bar) is worse.

## Alternatives considered

- **Option B — relax the five failing rows to match currently-achievable
  numbers, backed by the cited evidence.** Named per the standing policy's own
  instruction to present this option, not dismissed reflexively. If chosen at
  PR review, the operator should specify per-row: Output accuracy (loosen the
  σ-window or narrow to a load/PVT subset the light-load pole doesn't hit),
  Dropout (raise the ceiling toward the measured ≈365–570 mV range at the
  currently-screened sizing, excluding the `sf`/125 °C non-convergent outlier
  as a simulation artifact requiring its own investigation), Load transient /
  PSRR (narrow the qualifying PVT/load subset to the corners that already
  pass), Stability (add a stated minimum load, removing 0 mA from the row's
  scope, mirroring gf180-ldo's own minimum-load convention in its Load row).
  **Not chosen here** because every one of those loosenings would be keyed to
  *this design's current state*, not to a sky130 device-physics ceiling — the
  exact distinction CLAUDE.md's "never silently loosened" rule polices. If the
  operator judges any of these genuinely unreachable on sky130 physics (not
  merely unbuilt), that ruling at PR review is the correct place to make it,
  and a superseding record should state which rows and why.
- **Defer ratification until every row passes.** Rejected, for the same
  reason gf180-ldo's own DR-0004 rejected the symmetric option: it inverts
  the dependency. Layout, DRC/LVS, PEX, and the testbench suite were all
  scoped *from* the DRAFT spec table (issue #12's T1/bronze re-read chain,
  #14–#21) precisely so design work would not stall waiting on ratification;
  #1 has been the acknowledged critical-path gate the whole time, and holding
  it open until every row passes would block the maturity ladder on exactly
  the design work this ratification is meant to unblock as trackable,
  spec-conformant follow-on work.
- **Ratify only the framing + methodology records (DR-002/003/004/005),
  leave the numeric target table itself DRAFT.** Considered — it would be a
  smaller, lower-risk change. Rejected because issue #1's own Definition of
  Done requires "a ratified `spec/target-spec.md`," and the four input
  records were each drafted specifically to remove the blockers (window,
  test-point convention, corner names, thermal target) that were keeping the
  table's own rows from being ratifiable — ratifying the inputs but not the
  table they feed would leave #1 open with no remaining open item to close it.
- **Silently omit the FAIL findings from this record and let
  `measurements/characterization.md` speak for itself.** Rejected — the
  ratification-via-PR standing policy explicitly requires presenting
  failing-spec tradeoffs *in the DR draft*, not merely leaving them
  discoverable elsewhere. This record's Context section states them in full.

## Consequences

- **Closes #1** once the operator approves the PR this record ships in — the
  ratifying act is that PR approval, per the standing policy, not this
  record's own text and not a later comment.
- **DR-001, DR-002, DR-003, DR-004, DR-005 all become `ratified`** (each
  record's own Status line is updated in the same PR to point back here).
- **Advances the maturity ladder from pre-ladder to spec-ratified**, per
  issue #1's own Definition of Done — but explicitly does **not** advance it
  to a spec-conformance claim; `measurements/characterization.md` remains the
  live, regenerated record of where the implementation stands against the
  now-ratified table, and today that rollup shows five FAIL rows.
- **Unblocks nothing new for layout** (already unblocked and complete per
  #14–#39) but **does** unblock treating `spec/target-spec.md` as the
  authoritative bar for any future design-iteration issue, rather than a
  moving target agents were previously forbidden from citing as final.
- **Hands to design, unresolved, exactly the items each input record already
  named**: the Iq budget (DR-003), the 0 mA stability corner and its two
  named remedies (DR-002's append), the dropout sizing/series-resistance gap
  (DR-003's own known-optimism caveats), the light-load pole behind the
  Output-accuracy tail (mc-output-accuracy's own claim text), and the
  still-unsized `C_CL` (`design/README.md`'s "Known gaps"). This record does
  not file the follow-on issues for that work — that is a separate,
  subsequent step, not part of ratifying the spec itself.
- **If a future record finds any of these five rows are not merely unbuilt
  but device-physics-unreachable on sky130**, that record supersedes the
  relevant row's ratification here (via this record or a fresh DR-NNNN,
  operator's call) rather than editing this one — per the append-only
  discipline every record in this directory already follows.

## Status notes

This record is `proposed` until the operator approves the PR it ships in,
per the ratification-via-PR standing policy cited in Context. On approval:
this record's own Status becomes `ratified`, DR-001 through DR-005 are
updated in the same commit to cross-reference it, and `spec/target-spec.md`'s
banner changes from DRAFT to RATIFIED. If the operator instead rules for
Option B (or a hybrid) at PR review, that ruling is recorded as a PR comment
and this record is revised before merge to match — commit history on the open
PR, not a post-merge edit, carries that iteration; once merged, this record
is append-only like every other one in this directory.
