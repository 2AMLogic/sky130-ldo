# DR-014: PSRR binding capacitor condition

- **Status**: proposed — not self-ratifying; ratifies on operator approval of
  the PR that adds it
- **Date**: 2026-11-12
- **Author**: Builder agent (drafted per #314, Phase 2)
- **Ratifies against / input to**: #314 (PSRR: decide and evidence the binding
  output-capacitor/ESR condition)
- **Supersedes**: none — this record does not edit `spec/target-spec.md`,
  DR-002 or DR-007, and changes no threshold

## Context

The PSRR row in `spec/target-spec.md` (> 50 dB @ 1 kHz and > 20 dB @ 100 kHz,
at 1 mA and at 50 mA) does not say which output-capacitor condition it binds
at. DR-002 ratifies the window (C_eff 0.33–4.7 µF, ESR 0–500 mΩ, no minimum
ESR, 1 µF nominal), and other window-sensitive rows already say how they use
it, but the PSRR bench (`sim/psrr-dc/testbench/tb_psrr_dc.sch`) evaluates one
point only: 1 µF / 10 mΩ, labelled "DR-002 proposed nominal". The 100 kHz
sub-metrics depend on the output impedance of the pass-device / C_out network,
so they are the ones most exposed to that gap.

Phase 1 of #314 mints the evidence: record
`sim/psrr-dc/records/20261112-123922-1177e742.{json,md}`
(`evidence_kind: psrr-cap-esr-sweep`, sky130A pinned at
`c6d73a35f524070e85faff4a6a9eef49553ebc2b`). It samples C_eff ∈ {0.33, 1, 4.7}
µF × ESR ∈ {0, 10 m, 500 m} Ω at three corners — (tt, 27 °C, 3.3 V),
(ss, −40 °C, 2.97 V), (ff, 125 °C, 3.63 V) — and both loads. All 54 points are
populated. The nominal point reproduces `20260926-033606-4a9ec09` to
|Δ| ≤ 0.0001 dB.

**Evidence finding (sampled grid only).** Under the selection rule fixed in
advance (minimum over the three corners, ties to the lower C_eff then lower
ESR), the worst sampled point per sub-metric is:

| Sub-metric | Worst sampled (C_eff, ESR) | PSRR (dB) | Corner |
|---|---|---|---|
| 1 kHz / 1 mA | 4.7 µF, 0 Ω | 21.304 | ff / 125 °C / 3.63 V |
| 100 kHz / 1 mA | 0.33 µF, 0 Ω | 21.165 | ss / −40 °C / 2.97 V |
| 1 kHz / 50 mA | 4.7 µF, 0 Ω | 22.536 | ff / 125 °C / 3.63 V |
| 100 kHz / 50 mA | 1 µF, 0 Ω | 10.982 | ss / −40 °C / 2.97 V |

Three things in the table matter to the decision:

1. **0 Ω ESR is worst in all four.** The 10 mΩ in the current bench is not
   the unfavourable ESR end.
2. **The worst point differs per sub-metric**, and two of the four are window
   edges (4.7 µF, 0.33 µF) at opposite ends of the C_eff range.
3. **The worst 100 kHz / 50 mA point is interior** (1 µF), not a window edge.
   At tt/27 °C the 0 Ω column reads 11.882 dB (0.33 µF), 11.252 dB (1 µF),
   25.972 dB (4.7 µF): the minimum is not at an endpoint, so an edge-only
   evaluation would miss it.

How far the 1 µF / 10 mΩ nominal is from these (minimum over the three
corners, same record): 1 kHz / 1 mA 22.400 vs 21.304 dB (1.1 dB); 100 kHz /
1 mA 31.974 vs 21.165 dB (10.8 dB); 1 kHz / 50 mA 22.616 vs 22.536 dB
(0.08 dB); 100 kHz / 50 mA 11.049 vs 10.982 dB (0.07 dB).

**Status of the row against these numbers.** The row is not met anywhere on
the sampled grid: every 1 kHz cell is 21–24 dB against > 50 dB, and every
100 kHz / 50 mA cell is below 27 dB, with the worst at 10.982 dB against
> 20 dB. That is already true at the 1 µF nominal, so this record does not
create the failure and does not absorb it. The row remains a tracked design
gap (DR-007 is the separate, still-`proposed` record on thresholds).

## Decision

**Proposed: bind the PSRR row to the full DR-002 window (alternative (c)) —
every sub-metric must satisfy its threshold at every point of the ratified
C_eff × ESR window, with ESR = 0 treated as a first-class evaluation point —
and require interior-point and further-corner refinement before ratification
(see "Sampled-grid limit").** No threshold changes. This record is
`proposed`: it states an evidence-based recommendation, and the specification
condition is a call that only the operator's approval of the adding PR can
ratify.

## Alternatives considered

**(a) Bind to the worst sampled point per sub-metric.** The case for it: it
is directly what Phase 1 measured, it is the tightest condition the data
supports, and it differs per sub-metric, so no sub-metric is evaluated at a
condition that flatters it. Rejected as the *specification* condition because
the worst sampled point is a property of a 3 × 3 × 3-corner sample, not of the
window. It moves when the grid is refined (the 100 kHz / 50 mA minimum is
interior, so a finer C_eff grid may find a lower value), and a spec row that
names a grid point would be rewritten by every new sweep. It is the right
*evidence* and the wrong *definition*.

**(b) Bind to the 1 µF DR-002 nominal and disclose window-edge values.** The
case for it: it matches how the bench is built and how DR-002 labels the
nominal, it keeps one number per sub-metric, and disclosure still shows the
edges. Rejected because the nominal hides the 100 kHz / 1 mA sub-metric by
about 10.8 dB: the row would read about 32 dB at 1 µF while 21.2 dB is
reachable inside the ratified window. A row that can close on paper at the
nominal and miss at a window edge is the failure #314 was filed to prevent.
Disclosure alone does not gate. It would only be revisited if a ratified
decision narrowed the window the PSRR row is guaranteed over (for example, if
the row were deliberately scoped to the recommended 1 µF part).

**(c) Bind to the full window (recommended).** The case against it: it is the
strictest option, it needs a finite set of evaluation points to be testable,
and with the row already failing it adds evidence cost without changing any
verdict today. It is recommended because it is the only option whose
condition does not depend on which grid was sampled, it matches how DR-002's
window is used for Stability and Load transient ("over the ratified C_out/ESR
window"), and it is robust to the interior-minimum behaviour the 100 kHz /
50 mA data shows. Its testable form is the window endpoints plus the
interior points that refinement finds, evaluated at ESR = 0.

## Consequences

- **Spec rows unchanged.** `spec/target-spec.md` and all thresholds are
  untouched; no `sim/` record is edited.
- **Unmeetable-at-window report.** On the sampled grid the row is unmet at
  every point, including the nominal. Nothing here relaxes it. If ratified,
  the redesign must be measured against the whole window, not 1 µF / 10 mΩ.
- **Follow-up (Phase 3 of #314), after ratification only:** add the
  evaluation set as legs in `sim/psrr-dc/experiment.json` (as
  `sim/startup/experiment.json` does), reset independently, covering all 45
  PVT corners with C_out/ESR coordinates in each result, with the report
  disclosing which capacitor conditions each record covered. That needs an
  off-host path: `BATCH_ALLOWLIST` for `psrr-dc` must be extended after
  verifying the batch backend supports these AC measurements. It should not
  run before the PSRR design state is settled, so that it is not run twice.
  It is not filed by this record.
- **Handed to design unresolved:** the PSRR shortfall itself, and the
  interaction with DR-007 and the Iq budget.

### Sampled-grid limit

The Phase 1 grid is 3 C_eff × 3 ESR points at 3 corners. It cannot prove the
continuous-window worst case or the all-45-corner worst case. Before
ratification, the following refinement is **needed**, not optional:

- **Interior C_eff.** The 100 kHz / 50 mA minimum sits at the middle C_eff
  sample, so the true minimum lies somewhere between 0.33 and 4.7 µF and may
  be lower than 10.982 dB. Add interior C_eff points (at least between 0.33
  and 4.7 µF, e.g. a log-spaced sweep) at ESR = 0.
- **Other corners.** The worst corner is ff for the 1 kHz sub-metrics and ss
  for the 100 kHz ones on this grid; the remaining 42 of the 45 corners are
  unsampled. The 45-corner record already exists at the nominal; a wider
  corner sample at the refined points should confirm the corner assignment.
- **ESR between 0 and 10 mΩ.** All four worst points are at 0 Ω, the lower
  bound of the window; the sample does not show whether a small nonzero ESR
  changes the ordering. 10 mΩ is within 0.07 dB of 0 Ω at the 100 kHz / 50 mA
  worst point, so this is low risk, but it is unsampled.

## Status notes

`proposed`. It is ratified by the operator's approval of the PR that adds
it (the 2026-08-19 ratification-via-PR standing policy,
[2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357)); an agent
does not ratify it. The refinement above is a precondition the operator may
choose to waive or defer, and the choice should be stated in the ratifying
action. DR-002's window and DR-007's `proposed` threshold recommendation are
unchanged by this record. Evidence path:
`sim/psrr-dc/records/20261112-123922-1177e742.{json,md}`.
