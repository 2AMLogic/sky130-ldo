# DR-014: PSRR binding capacitor condition

- **Status**: proposed — operator approval of this PR ratifies only the PSRR
  capacitor condition. Phase 3 verifies performance against that condition.
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
point only: 1 µF / 10 mΩ, labelled "DR-002 proposed nominal". As loop gain
rolls off, the output impedance of the pass device and capacitor has more
influence on supply-ripple rejection. DR-002 identifies a pass-gate pole near
the loop bandwidth. Changing C_eff or ESR can change rejection at 100 kHz
in either direction.

Phase 1 of #314 mints the evidence: record
`sim/psrr-dc/records/20261112-123922-1177e742.{json,md}`
(`evidence_kind: psrr-cap-esr-sweep`, sky130A pinned at
`c6d73a35f524070e85faff4a6a9eef49553ebc2b`). It samples C_eff ∈ {0.33, 1, 4.7}
µF × ESR ∈ {0, 10 m, 500 m} Ω at three corners — (tt, 27 °C, 3.3 V),
(ss, −40 °C, 2.97 V), (ff, 125 °C, 3.63 V) — and both loads. All 54 points are
populated. The run used a dirty working tree and off-baseline tools (ngspice
46 and xschem 3.4.7, declared versions 42 and 3.4.4). The archived sweep
deck adds a direct capacitor branch (`CDIR`) for exact zero ESR. At tt/27 °C
the nominal point reproduces all four metrics in `20260926-033606-4a9ec09`
to |Δ| ≤ 0.0001 dB.

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

1. **All four sampled minima occur at 0 Ω ESR.** At 1 kHz the 0 and 10 mΩ
   values at the worst corner and capacitance agree to three decimal places.
   At 100 kHz / 50 mA the ESR ordering reverses with capacitance. At ss,
   raising ESR from 0 to 500 mΩ raises PSRR from 10.982 to 13.539 dB at
   1 µF and lowers it from 25.046 to 22.691 dB at 4.7 µF.
2. **Different sub-metrics select opposite capacitance endpoints.** Both
   1 kHz minima occur at 4.7 µF, and the 100 kHz / 1 mA minimum at 0.33 µF.
3. **The worst 100 kHz / 50 mA point is interior** (1 µF), not a window edge.
   At tt/27 °C the 0 Ω column reads 11.882 dB (0.33 µF), 11.252 dB (1 µF),
   25.972 dB (4.7 µF): the minimum is not at an endpoint, so an edge-only
   evaluation would miss it.

How far the 1 µF / 10 mΩ nominal is from these (minimum over the three
corners, same record): 1 kHz / 1 mA 22.400 vs 21.304 dB (1.1 dB); 100 kHz /
1 mA 31.974 vs 21.165 dB (10.8 dB); 1 kHz / 50 mA 22.616 vs 22.536 dB
(0.08 dB); 100 kHz / 50 mA 11.049 vs 10.982 dB (0.07 dB).

**Status of the row against these numbers.** At every sampled point, both
1 kHz clauses fall below 50 dB. At 100 kHz the 50 mA minimum misses
the > 20 dB target by 9.018 dB. All three clauses also fail at the nominal
capacitor. The 100 kHz / 1 mA minimum clears 20 dB by 1.165 dB on this grid.
It falls below DR-007's proposed ≥ 28 dB floor, derived from nominal-capacitor
measurements at 1 mA. The PSRR shortfall remains an open design issue.

## Decision

**Bind all four PSRR clauses to the full DR-002 window (alternative (c)).**
Each clause must meet its existing threshold throughout 0.33–4.7 µF effective
capacitance and 0–500 mΩ ESR, including exact zero ESR. The operator can
ratify this condition on the Phase 1 evidence. Phase 3 begins with refinement
to select the finite evaluation set used for qualification.

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

The gf180-ldo sibling ratified its PSRR row at 1 µF nominal (DR-0004,
amendment A7) and later narrowed its stability envelope to 1 µF (DR-0018).
For sky130, nominal-only reporting would conceal the measured 10.8 dB loss
at 100 kHz / 1 mA. The interior minimum at 100 kHz / 50 mA also calls for
coverage between the endpoints.

**(c) Bind to the full window (recommended).** The case against it: it is the
strictest option, it needs a finite set of evaluation points to be testable,
and with the row already failing it adds evidence cost without changing any
verdict today. It is recommended because it is the only option whose
condition does not depend on which grid was sampled, it matches how DR-002's
window is used for Stability and Load transient ("over the ratified C_out/ESR
window"), and it is robust to the interior-minimum behaviour the 100 kHz /
50 mA data shows. The window defines the requirement independently of any
grid. Phase 3 tests both capacitance endpoints and the interior capacitances
identified by refinement, each at 0, 10 and 500 mΩ ESR at minimum.

## Consequences

- **Spec rows unchanged.** `spec/target-spec.md` and all thresholds are
  untouched; no `sim/` record is edited.
- **Unmeetable-at-window report.** On the sampled grid the row is unmet at
  every point, including the nominal. Nothing here relaxes it. If ratified,
  the redesign must be measured against the whole window, not 1 µF / 10 mΩ.
- **Phase 3 of #314.** On ratification, the operator opens the qualification
  follow-up. First refine the joint grid as described below. Once the PSRR
  design is settled, qualify the resulting evaluation set across all 45 PVT
  corners at both loads. Add independently reset legs to
  `sim/psrr-dc/experiment.json`, retaining the direct-capacitor path for
  exact zero ESR. Record C_eff and ESR for every result and report which
  conditions each record covers.
- **Handed to design unresolved:** the PSRR shortfall itself, and the
  interaction with DR-007 and the Iq budget.

### Sampled-grid limit

The Phase 1 grid is 3 C_eff × 3 ESR points at 3 corners. It cannot prove the
continuous-window worst case or the all-45-corner worst case. After
ratification, Phase 3 requires the following evidence to select the
qualification points:

- **Joint C_eff × ESR refinement.** Keep 0.33, 1 and 4.7 µF and add interior
  capacitances on both sides of 1 µF, where the 100 kHz / 50 mA sampled
  minimum occurs. At **every** capacitance, including each new interior
  point, sweep at least 0, 10 and 500 mΩ ESR. Include additional points
  around any lower minima found for each load and frequency.
- **Other corners.** The worst corner is ff for the 1 kHz sub-metrics and ss
  for the 100 kHz ones on this grid; the remaining 42 of the 45 corners are
  unsampled. The 45-corner record already exists at the nominal; a wider
  corner sample at the refined points should test whether the worst corner
  shifts with C_eff or ESR.
- **ESR between 0 and 10 mΩ.** At the sampled 100 kHz / 50 mA minimum,
  the two values differ by only 0.07 dB. Add intermediate ESR samples to
  check for a lower value between them and carry any such point into the
  45-corner evaluation set.

## Status notes

`proposed`. Operator approval of this PR decides where the thresholds apply.
The three measured failures stay open for design, and a claim of compliance
requires Phase 3 qualification evidence.
