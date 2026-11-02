# Work Plan

Current roadmap derived from GitHub lifecycle labels. Maintained by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#482**: docs(spec): add ll/hh Iq corners and DR-0033 departure to DR-013 record

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

- **#478**: DR-013 follow-ups: ll/hh resistor-skew corners missing from the full-loop sweep; write the departure from gf180-ldo DR-0033 against it

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#482**: docs(spec): add ll/hh Iq corners and DR-0033 departure to DR-013 record

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
- **#478**: DR-013 follow-ups: ll/hh resistor-skew corners missing from the full-loop sweep; write the departure from gf180-ldo DR-0033 against it *(curated)*

## Proposed (Architect / Hermit)

- **#446**: Dedupe batch_iq/batch_load_regulation parse_deck and drop unused re-exports *(hermit)*

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
| Architect / Hermit proposals | 1 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
