# Work Plan

Current roadmap derived from GitHub lifecycle labels. Maintained by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#395**: Bump Repo Skills 0.24.1 -> 0.24.3

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#263**: Qualify folded resistor electrical equivalence across process, temperature and mismatch

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#263**: Qualify folded resistor electrical equivalence across process, temperature and mismatch

## In Progress

Issues currently being built (`loom:building`).

_None._

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#275**: layout: fix via.1a_b, m2.5, via2.5, nwell.9 official-DRC families (#267)

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#395**: Bump Repo Skills 0.24.1 -> 0.24.3

## Proposed

Issues carrying `loom:curated`.

- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification *(curated)*
- **#177**: Seed sim/current-limit's leg-1 operating point to conform to the initial-condition contract *(curated)*
- **#213**: sim(iq): mint the 45-corner record under #173's seeded deck + #133's regulation gate — deck fixed, matrix not re-run (host contention) *(curated)*
- **#263**: Qualify folded resistor electrical equivalence across process, temperature and mismatch *(curated)*
- **#267**: layout: fix locally-routed official-DRC families (via.1a_b, m2.5, via2.5, nwell.9) found by #260 *(curated)*
- **#314**: PSRR: decide and evidence the binding output-capacitor/ESR condition *(curated)*
- **#381**: Sim: admit load-regulation cold-start endpoints to the batch backend *(curated)*

## Proposed (Architect / Hermit)

_None._

## Epics

- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 0 |
| Important | 1 |
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 0 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 1 |
| Curated | 7 |
| Architect / Hermit proposals | 0 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
