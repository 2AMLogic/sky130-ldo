# Work Plan

Current roadmap derived from GitHub lifecycle labels. Maintained by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#470**: docs(spec): propose DR-013 bias re-topology (straight res_xhigh_po R_BIAS) with area and PVT evidence

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge
- **#416**: Re-run folded-resistor MC at n>=1000 to firm up M2 sigma-ratio gate

## In Progress

Issues currently being built (`loom:building`).

- **#467**: Bias re-topology so R_BIAS is not one long resistor: new DR, to meet the < 0.1 mm² Area row without a fold waiver (#461)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#470**: docs(spec): propose DR-013 bias re-topology (straight res_xhigh_po R_BIAS) with area and PVT evidence

## Proposed

Issues carrying `loom:curated`.

- **#114**: Gap to T1: 6 of 12 ratified rows FAIL — replacement tracker (#58 closed on child-completion, not on verdict) *(curated)*
- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification *(curated)*
- **#177**: Seed sim/current-limit's leg-1 operating point to conform to the initial-condition contract *(curated)*
- **#213**: sim(iq): mint the 45-corner record under #173's seeded deck + #133's regulation gate — deck fixed, matrix not re-run (host contention) *(curated)*
- **#267**: layout: fix locally-routed official-DRC families (via.1a_b, m2.5, via2.5, nwell.9) found by #260 *(curated)*
- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge *(curated)*
- **#314**: PSRR: decide and evidence the binding output-capacitor/ESR condition *(curated)*
- **#381**: Sim: admit load-regulation cold-start endpoints to the batch backend *(curated)*
- **#416**: Re-run folded-resistor MC at n>=1000 to firm up M2 sigma-ratio gate *(curated)*
- **#423**: T1 items 1, 2, 9, 10: bump the signoff grading pin and attest with artifact-anchored envelopes (klt signoff --attest) *(curated)*
- **#461**: T1 item 5 area: compact routed ldo_core under 0.1 mm² with capacitors drawn, re-mint records (part of #458) *(curated)*
- **#467**: Bias re-topology so R_BIAS is not one long resistor: new DR, to meet the < 0.1 mm² Area row without a fold waiver (#461) *(curated)*

## Proposed (Architect / Hermit)

- **#446**: Dedupe batch_iq/batch_load_regulation parse_deck and drop unused re-exports *(hermit)*
- **#475**: Remove superseded ldo-area-budget.py (#246): replaced by 4cap budget (#459), helpers duplicated *(hermit)*

## Epics

- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 0 |
| Important | 1 |
| Ready (`loom:issue`) | 2 |
| In Progress (`loom:building`) | 1 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 1 |
| Curated | 12 |
| Architect / Hermit proposals | 2 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
