# Work Plan

Current roadmap derived from GitHub lifecycle labels. Maintained by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#467**: Bias re-topology so R_BIAS is not one long resistor: new DR, to meet the < 0.1 mm² Area row without a fold waiver (#461)

## Important

`loom:important`; taken before unlabelled work.

- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge

## In Progress

Issues currently being built (`loom:building`).

- **#314**: PSRR: decide and evidence the binding output-capacitor/ESR condition
- **#550**: Re-run signoff-graded benches made stale by the integrated comparator (split from #548)
- **#553**: Layout evidence: regenerate and re-run DRC/LVS/ERC/area for the integrated comparator netlist (split from #548)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#561**: sim: re-run five batch benches on integrated comparator; refresh characterization and item 8 pin

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#114**: Gap to T1: 6 of 12 ratified rows FAIL — replacement tracker (#58 closed on child-completion, not on verdict) *(curated)*
- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification *(curated)*
- **#267**: layout: fix locally-routed official-DRC families (via.1a_b, m2.5, via2.5, nwell.9) found by #260 *(curated)*
- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge *(curated)*
- **#314**: PSRR: decide and evidence the binding output-capacitor/ESR condition *(curated)*
- **#345**: Load transient: mint the COUT/ESR window-grid x 45 PVT campaign via --backend batch (blocked on fleet runner update) *(curated)*
- **#416**: Re-run folded-resistor MC at n>=1000 to firm up M2 sigma-ratio gate *(curated)*
- **#461**: T1 item 5 area: compact routed ldo_core under 0.1 mm² with capacitors drawn, re-mint records (part of #458) *(curated)*
- **#503**: measurements: characterization generator cannot see artifact-store-only sim records (iq 20261105-052332-05df7a01) *(curated)*
- **#550**: Re-run signoff-graded benches made stale by the integrated comparator (split from #548) *(curated)*
- **#553**: Layout evidence: regenerate and re-run DRC/LVS/ERC/area for the integrated comparator netlist (split from #548) *(curated)*

## Proposed (Architect / Hermit)

_None._

## Epics

- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 1 |
| Important | 1 |
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 3 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 0 |
| Curated | 11 |
| Architect / Hermit proposals | 0 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
