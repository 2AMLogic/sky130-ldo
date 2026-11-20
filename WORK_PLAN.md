# Work Plan

Current roadmap derived from GitHub lifecycle labels. Maintained by the Loom Guide role.

<!-- guide:plan-body:start -->
_Generated: 2026-11-20T03:52:52Z (snapshot; compare against live labels)_
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#569**: docs: propose DR-014 binding capacitor condition for the PSRR row
- **#681**: Clarify DR-012’s proposed status and fresh ratification requirement

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#467**: Bias re-topology so R_BIAS is not one long resistor: new DR, to meet the < 0.1 mm² Area row without a fold waiver (#461) *(held)*

## Important

`loom:important`; taken before unlabelled work.

- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues closed by an open `loom:pr` PR (listed under Approved).

- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge

## In Progress

Issues currently being built (`loom:building`).

- **#177**: Seed sim/current-limit's leg-1 operating point to conform to the initial-condition contract
- **#629**: characterization.md Output row reads PASS on light-load-only evidence; record 20261115-133911-1caff9b9 is full-load evidence against that same window
- **#639**: xschem pin migration: migrate sky130-ldo to the fleet 3.4.7
- **#683**: docs(sim): reconcile sim/iq/experiment.json's DR-009 ratifying-act claim with the #301 ruling

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#569**: docs: propose DR-014 binding capacitor condition for the PSRR row — closes #314
- **#681**: Clarify DR-012’s proposed status and fresh ratification requirement

## Proposed

Issues carrying `loom:curated`.

- **#114**: Gap to T1: 6 of 12 ratified rows FAIL — replacement tracker (#58 closed on child-completion, not on verdict) *(curated)* *(held)*
- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification *(curated)* *(held)*
- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge *(curated)*
- **#314**: PSRR: decide and evidence the binding output-capacitor/ESR condition *(curated)*
- **#345**: Load transient: mint the COUT/ESR window-grid x 45 PVT campaign via --backend batch (blocked on fleet runner update) *(curated)* *(held)*
- **#416**: Re-run folded-resistor MC at n>=1000 to firm up M2 sigma-ratio gate *(curated)* *(held)*
- **#461**: T1 item 5 area: compact routed ldo_core under 0.1 mm² with capacitors drawn, re-mint records (part of #458) *(curated)* *(held)*
- **#503**: measurements: characterization generator cannot see artifact-store-only sim records (iq 20261105-052332-05df7a01) *(curated)* *(held)*
- **#550**: Re-run signoff-graded benches made stale by the integrated comparator (split from #548) *(curated)* *(held)*
- **#629**: characterization.md Output row reads PASS on light-load-only evidence; record 20261115-133911-1caff9b9 is full-load evidence against that same window *(curated)*
- **#639**: xschem pin migration: migrate sky130-ldo to the fleet 3.4.7 *(curated)*
- **#645**: CI: nightly pdk-smoke red for 6+ nights — declared ngspice pin 42 vs resolved 45.2 (CI) / 47 (workers) *(curated)* *(held)*
- **#683**: docs(sim): reconcile sim/iq/experiment.json's DR-009 ratifying-act claim with the #301 ruling *(curated)*

## Proposed (Architect / Hermit)

- **#576**: Collapse layout/'s three klt pins into one: the main pin now descends from both the ERC and cap-rail pins *(hermit)* *(held)*
- **#591**: ci.yml: the 65-line check-inventory header restates package.json and has drifted from it in four places *(hermit)* *(held)*
- **#595**: Remove load_results() from sim/bin/_probe_common.py: the one advertised probe helper with no caller *(hermit)* *(held)*

## Epics

- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification *(held)*

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 2 |
| Very important | 1 |
| Important | 1 |
| Ready (`loom:issue`, net of holds/building/merge-pending) | 1 |
| In Progress (`loom:building`) | 4 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 2 |
| Curated | 13 |
| Architect / Hermit proposals | 3 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
