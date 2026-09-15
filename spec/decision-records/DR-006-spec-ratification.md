# DR-006: Ratification of the target specification

- **Status**: proposed — **Option A ruled by the operator 2026-09-15** (see
  §Operator ruling below), but this record still does not ratify itself. Per
  the 2026-08-19 ratification-via-PR standing policy
  ([2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357)) as the
  pipeline has since been refined by the two-key mechanism
  (2AMLogic/2am#372), the ratifying act is Judge review (→ `loom:pr`)
  followed by the two-key mechanism's release and the operator's/Champion's
  merge of the pull request this record ships in — not this record's text,
  and not the operator's substantive ruling on Option A vs. Option B taken
  alone. This PR had not yet gone through that pipeline when the ruling was
  given (2026-09-15 comment on #1); a Doctor pass rebased it, reconciled the
  disclosed-FAIL list against DR-007, and recorded the ruling here — Judge
  review and the two-key mechanism still gate the merge.
- **Date**: 2026-08-19 (drafted); Option A ruling 2026-09-15
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
methodology.** Between DR-002/003/004 landing (2026-08-15) and this record's
last refresh (2026-09-15, per the Doctor pass that reconciled it against
DR-007 — see below), the block acquired a full schematic (#14, #22, #25,
#26, #29, #36), a routed and LVS-matched layout (#33, #34, #39), DRC-clean
and post-layout PEX results (#16, #20), the full set of spec-row testbenches
(load-transient, psrr-dc, dropout-vs-load, mc-output-accuracy, loop-gain,
line-regulation, load-regulation, iq, current-limit, startup,
enable-shutdown, thermal), a 45-point PVT-corner + Monte Carlo verification
pass (#19, PR #37, rebased onto the current schematic by #40, extended by
later issues for the newer testbenches), and — the evidentiary input this
record relies on most directly — a generated, aggregated per-spec-row
characterization report (#21, PR #49, `measurements/characterization.md`)
rolling all of the above up against `spec/target-spec.md`'s current DRAFT
rows.

**That report's central finding: the current implementation does not meet
most of the DRAFT numeric rows it has a testbench for.** Verbatim from a
fresh run of `measurements/build_characterization_report.py` as of
`origin/main` @ `2b5a886` (2026-09-15 — refreshed from this record's original
2026-08-19 citation, which only had five of the rows below built yet):

| Row | Verdict (vs. current DRAFT) | Evidence |
|---|---|---|
| Output (1.8 V ±2 %) | **FAIL** | 177/200 mismatch samples pass (`sim/mc-output-accuracy` `20260825-083111-4cb27f8`); tail driven by a light-load pole, per the record's own "known-remaining-gaps" note |
| Dropout @ 50 mA (< 300 mV) | **FAIL** | 0/45 PVT corners pass (`sim/dropout-vs-load` `20260825-081240-4cb27f8`); best case 365 mV (`ss`/−40 °C) vs. the 300 mV ceiling |
| Line regulation (< 5 mV/V) | **FAIL** | 18/45 PVT corners pass (`sim/line-regulation` `20260910-030557-6c0436d`) |
| Load regulation (< 1 %) | **FAIL** | 34/45 PVT corners pass (`sim/load-regulation` `20260910-032854-6c0436d`) |
| Load transient (≤ 150 mV / ≤ 20 µs) | **FAIL** | 25/45 PVT corners pass (`sim/load-transient` `20260825-081255-4cb27f8`) |
| PSRR (> 50 dB @ 1 kHz, > 20 dB @ 100 kHz) | **FAIL — superseded-row proposal on the table** | 0/45 PVT corners pass (`sim/psrr-dc` `20260825-082845-4cb27f8`, at the one load point ~1 mA the testbench currently covers); DR-007 (below) recommends replacement numbers |
| Iq (< 30 µA) — **not itself a ratified target; see note** | FAIL (against the testbench's own DRAFT-row citation, not a ratified number) | 36/45 PVT corners pass (`sim/iq` `20260910-034648-6c0436d`) |
| Current limit | **PASS** | 45/45 PVT corners pass (`sim/current-limit` `20260825-105322-933dfdd`) |
| Startup / soft-start | **PASS** | 45/45 PVT corners pass (`sim/startup` `20260825-110456-933dfdd`) |
| Enable / shutdown | **PASS** | 45/45 PVT corners pass (`sim/enable-shutdown` `20260825-111526-933dfdd`) |
| Thermal | **FAIL** | 12/15 corners pass (`sim/thermal` `20260825-104426-933dfdd`, against DR-005's proposed 150 °C/135 °C trip/reset target — this record also ratifies DR-005, so the row is judged against what becomes the ratified number) |
| Stability (PM ≥ 45°, GM ≥ 10 dB) | **FAIL — superseded-row proposal on the table** | 7/45 PVT corners pass (`sim/loop-gain` `20260825-081257-4cb27f8`) — matches DR-002's own append: the 0 mA end of the load range is the binding failure, not the C_out/ESR window's low-`C_eff` corner it was drafted to worry about; DR-007 (below) recommends replacement numbers |

Three rows carry no testbench yet (Input, Load, Output noise, Area — reported
`N/A` by the generator, not `FAIL`) and are unaffected by this table.

**The Iq row is a special case, not a sixth ordinary FAIL.** `spec/
target-spec.md` leaves Iq explicitly `OPEN — not ratified. No number set.`
(DR-003 never proposed one), so there is no ratified target for the `iq`
testbench's FAIL verdict to be measured against — the generator reports FAIL
because the testbench itself cites the pre-existing DRAFT `< 30 µA` text as
its own working bound, not because this record is disclosing a gap against a
number it is ratifying. This row is carried forward exactly as before:
open, not ratified, not disclosed as a design gap, because there is no
ratified line yet for it to gap against.

**Reconciled against DR-007 (2026-09-14, PR #106, landed on `main` since this
record was first drafted).** DR-007 root-causes the PSRR and Stability
failures above to the shipped topology's single-stage current-mirror OTA and
un-cascoded bias generator — architecture-level, not merely "unbuilt" — after
two decomposed Builder attempts (issue #70/PR #82, issue #79/PR #88) each
returned a well-verified negative result. It recommends replacement target
rows (PSRR ≥ 18 dB @ 1 kHz / ≥ 28 dB @ 100 kHz; Stability PM ≥ 45°/GM ≥ 10 dB
for `I_load ≥ 1 mA` with no floor stated at literal 0 mA) as a **starting
point for #1's own market-comparison mechanism**, but DR-007 itself stays
`proposed` — it is an input to this ratification, not a self-ratifying
record, and does not edit `spec/target-spec.md`. Per the operator's
2026-09-15 ruling (Option A — see §Operator ruling below), this record does
**not** adopt DR-007's proposed numbers: PSRR and Stability keep their
original DRAFT/ratified values unchanged, exactly like every other row. What
changes is the *disclosure*: these two rows are no longer presented as
"unbuilt work, an unexploited remedy still on the table" the way the
remaining five FAIL rows are (see Decision below) — DR-007 already
root-caused them and already proposes a specific, named alternative, pending
its own ratification via the two-key mechanism. The other five FAIL rows
(Output, Dropout, Line regulation, Load regulation, Load transient) have no
comparable superseding record and remain open, unaddressed design gaps.

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
loosen any row to match the current implementation's measured shortfall,
including the PSRR and Stability rows DR-007 recommends replacing. Record
the shortfall explicitly, row by row, as a disclosed, tracked design gap for
follow-on work, per CLAUDE.md's "a row that proves unmeetable is superseded
by a new decision record, never silently loosened." DR-007 stays `proposed`
— it is an input this record discloses and cross-references, not something
this record ratifies; if and when DR-007's own market-comparison mechanism
ratifies it, that is a separate, later ratifying action on those two rows
specifically, per the append-only discipline every record in this directory
follows.**

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
8. **Every DRAFT numeric performance target row (Output, Dropout, Line
   regulation, Load regulation, Load transient, PSRR, Stability) keeps its
   current number, unchanged.** No number in the target table changes as a
   result of this record. Current limit, Startup, and Enable/shutdown are
   unaffected — their evidence already passes.
9. **PSRR and Stability row notes**: gain a cross-reference to DR-007
   (`proposed`), noting that DR-007 root-causes the failure to the shipped
   topology and recommends replacement numbers pending its own ratification
   — without adopting those numbers here.

### Why Option A (ratify unchanged, disclose the gap) over Option B (relax to match)

- **CLAUDE.md's default is explicit and directional**: "agents do not relax a
  spec line to make a result pass. A row that proves unmeetable is superseded
  by a new decision record, never silently loosened." Most of the failing
  rows above have not been shown *unmeetable* — each has a named, plausible,
  unexploited remedy still on the table:
  - **Dropout, Line regulation, Load regulation, Load transient, Output
    accuracy**: each testbench's own claim text names open items (a pass
    device sized below DR-003's own ≈ 2.5 mm recommendation, unmodeled
    series resistance DR-003's Appendix already flags as excluded from its
    screening numbers, unsized `C_CL`, the error-amplifier's light-load
    pole, the still-missing Iq budget) as the likely drivers — unbuilt
    remedies, not a proof of infeasibility.
  - **PSRR and Stability are a different case, reconciled against DR-007.**
    DR-002's append root-causes the Stability 0 mA-end failure to the pass
    stage's own `gm_pass/(2π·C_out)` pole falling with load current, and
    DR-007 (2026-09-14) goes further: it shows two decomposed Builder
    attempts to fix both rows (issue #70/PR #82, issue #79/PR #88) each
    returned a well-verified *negative* result, and root-causes both
    failures to the shipped topology's single-stage current-mirror OTA and
    un-cascoded bias generator — an architecture-level limit, not merely
    "unbuilt." DR-007 itself recommends treating these two rows as
    *reachable only with a topology change*, and proposes specific
    replacement numbers as a starting point for #1's own market-comparison
    mechanism. This record still does not adopt those numbers (see Decision)
    — DR-007 stays `proposed`, and ratifying its proposal is a distinct,
    later ratifying action reserved to DR-007 itself, not something this
    record's Option A vs. B choice pre-empts.
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

- **Option B — relax the failing rows to match currently-achievable numbers,
  backed by the cited evidence.** Named per the standing policy's own
  instruction to present this option, not dismissed reflexively. If chosen at
  PR review, the operator should specify per-row: Output accuracy (loosen the
  σ-window or narrow to a load/PVT subset the light-load pole doesn't hit),
  Dropout (raise the ceiling toward the measured ≈365–570 mV range at the
  currently-screened sizing, excluding the `sf`/125 °C non-convergent outlier
  as a simulation artifact requiring its own investigation), Line
  regulation / Load regulation / Load transient (narrow the qualifying
  PVT/load subset to the corners that already pass), Stability (add a
  stated minimum load, removing 0 mA from the row's scope, mirroring
  gf180-ldo's own minimum-load convention in its Load row). **PSRR and
  Stability now have a more rigorously argued Option B already on the
  table — DR-007 — which this ad hoc per-row sketch does not attempt to
  improve on for those two rows**; see the reconciliation above. **Not
  chosen here** because every one of these loosenings would be keyed to
  *this design's current state*, not to a sky130 device-physics ceiling — the
  exact distinction CLAUDE.md's "never silently loosened" rule polices. If the
  operator judges any of these genuinely unreachable on sky130 physics (not
  merely unbuilt), that ruling at PR review is the correct place to make it,
  and a superseding record should state which rows and why — DR-007 is
  exactly that record for PSRR and Stability, pending its own ratification.
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

- **Closes #1** once this PR merges — per the ratification-via-PR standing
  policy as refined by the two-key mechanism (see §Status above), the
  ratifying act is Judge review, the two-key mechanism's release, and the
  merge itself, not this record's own text and not the operator's
  2026-09-15 substantive ruling on Option A vs. B taken alone.
- **DR-001, DR-002, DR-003, DR-004, DR-005 all become `ratified`** (each
  record's own Status line is updated in the same PR to point back here).
  **DR-007 stays `proposed`** — this record discloses and cross-references
  it but does not ratify it; DR-007's own numbers, if ever ratified, are a
  separate, later ratifying action via its own market-comparison mechanism.
- **Advances the maturity ladder from pre-ladder to spec-ratified**, per
  issue #1's own Definition of Done — but explicitly does **not** advance it
  to a spec-conformance claim; `measurements/characterization.md` remains the
  live, regenerated record of where the implementation stands against the
  now-ratified table, and as of this record's 2026-09-15 refresh that rollup
  shows nine FAIL rows (Output, Dropout, Line regulation, Load regulation,
  Load transient, PSRR, Iq (against its own unratified DRAFT citation),
  Thermal, Stability) against three PASS rows (Current limit, Startup,
  Enable/shutdown).
- **Unblocks nothing new for layout** (already unblocked and complete per
  #14–#39) but **does** unblock treating `spec/target-spec.md` as the
  authoritative bar for any future design-iteration issue, rather than a
  moving target agents were previously forbidden from citing as final.
- **Hands to design, unresolved, exactly the items each input record already
  named**: the Iq budget (DR-003), the 0 mA stability corner (DR-002's
  append, now further root-caused and given a proposed disposition by
  DR-007), the dropout sizing/series-resistance gap (DR-003's own
  known-optimism caveats), the light-load pole behind the Output-accuracy
  tail (mc-output-accuracy's own claim text), the still-unsized `C_CL`
  (`design/README.md`'s "Known gaps"), and the still-uninvestigated Line
  regulation / Load regulation / Thermal shortfalls. This record does not
  file the follow-on issues for that work — that is a separate, subsequent
  step, not part of ratifying the spec itself.
- **If a future record finds any of these FAIL rows are not merely unbuilt
  but device-physics-unreachable on sky130**, that record supersedes the
  relevant row's ratification here (via this record or a fresh DR-NNNN,
  operator's call) rather than editing this one — per the append-only
  discipline every record in this directory already follows. For PSRR and
  Stability, DR-007 is already that record, pending its own ratification.

## Operator ruling (2026-09-15)

**Operator ruling: Option A — ratify the target spec unchanged, disclose the
currently-failing rows (including PSRR and Stability, which DR-007
separately proposes to supersede) as measured FAILs.** Sibling precedent:
[`sky130-bandgap` DR-009](https://github.com/2AMLogic/sky130-bandgap/blob/main/spec/decision-records/DR-009-tc-floor-disposition-defer-curvature-correction.md)
(same day, same disposition shape) — no ratified value relaxed, the gap
disclosed with its measured numbers, and a superseding-record path left open
rather than folded into the ratification itself.

This PR (#50) is the ratification vehicle for #1, but had not gone through
the pipeline the 2026-08-28 note asked for when this ruling was given: no
`loom:pr`, no Judge review, no two-key (`scripts/ratify-key.sh`) reviews, and
`mergeable_state: dirty` since 2026-09-12. The operator's ruling covers the
substantive Option A vs. B question; it does not itself complete the
pipeline. Per the operator's own sequencing comment, this Doctor pass
rebases the PR onto `main`, reconciles the disclosed-FAIL list against
DR-007, and records this ruling here and in `README.md` — Judge review
(→ `loom:pr`) and the two-key mechanism's release still gate the merge that
actually ratifies this record. **If the market key escalates on the
disclosed-FAIL carry-forward, the escalation is already ruled: Option A,
approve — a human does not need to be asked again;** cite the operator's
2026-09-15 comment on #1.

## Status notes

This record is `proposed`. The operator's substantive ruling (Option A) is
given — see §Operator ruling above — but per the ratification-via-PR standing
policy cited in Context, as refined by the two-key mechanism, this record
does not become `ratified` until the pull request it ships in completes
Judge review (→ `loom:pr`), the two-key mechanism's release, and merge. On
that completion: this record's own Status becomes `ratified`, DR-001 through
DR-005 are updated in the same commit to cross-reference it (already done by
this PR), and `spec/target-spec.md`'s banner changes from DRAFT to RATIFIED
(already done by this PR, ahead of the formal Status flip, so the merged
tree is internally consistent the moment it lands). If a future review
finds cause to revisit Option A vs. B, that is a fresh operator ruling and,
per the append-only discipline, a superseding record rather than an edit to
this one.
