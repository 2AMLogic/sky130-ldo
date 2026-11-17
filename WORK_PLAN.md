# Work Plan

Current roadmap derived from GitHub lifecycle labels. Maintained by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#569**: docs: propose DR-014 binding capacitor condition for the PSRR row
- **#573**: docs(spec): reconcile DR-009's ratifying-act wording with the #301 ruling
- **#630**: docs: align DR-009 status wording with the #301 ruling across CLAUDE.md and target spec

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#467**: Bias re-topology so R_BIAS is not one long resistor: new DR, to meet the < 0.1 mm² Area row without a fold waiver (#461) *(held)*

## Important

`loom:important`; taken before unlabelled work.

- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge
- **#550**: Re-run signoff-graded benches made stale by the integrated comparator (split from #548)

## In Progress

Issues currently being built (`loom:building`).

- **#177**: Seed sim/current-limit's leg-1 operating point to conform to the initial-condition contract
- **#336**: Startup: extend cold-enable coverage to the ratified ESR boundaries
- **#624**: CLAUDE.md:35 still claims DR-009 'ratifies on its own PR merge' — the same stale claim #607 removed from README
- **#629**: characterization.md Output row reads PASS on light-load-only evidence; record 20261115-133911-1caff9b9 is full-load evidence against that same window
- **#639**: xschem pin migration: migrate sky130-ldo to the fleet 3.4.7

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#648**: sim(current-limit): batch adapter for the three chained legs; 45-corner fleet re-run supersedes the pre-gate record (#177)

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#569**: docs: propose DR-014 binding capacitor condition for the PSRR row
- **#573**: docs(spec): reconcile DR-009's ratifying-act wording with the #301 ruling
- **#630**: docs: align DR-009 status wording with the #301 ruling across CLAUDE.md and target spec

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
- **#550**: Re-run signoff-graded benches made stale by the integrated comparator (split from #548) *(curated)*
- **#623**: pex-post-layout batch runs: serial job-ceiling estimate can exceed the fleet's 3600 s max_job_seconds (shard via request.remote.hosts) *(curated)* *(held)*
- **#624**: CLAUDE.md:35 still claims DR-009 'ratifies on its own PR merge' — the same stale claim #607 removed from README *(curated)*
- **#629**: characterization.md Output row reads PASS on light-load-only evidence; record 20261115-133911-1caff9b9 is full-load evidence against that same window *(curated)*
- **#639**: xschem pin migration: migrate sky130-ldo to the fleet 3.4.7 *(curated)*
- **#645**: CI: nightly pdk-smoke red for 6+ nights — declared ngspice pin 42 vs resolved 45.2 (CI) / 47 (workers) *(curated)* *(held)*

## Proposed (Architect / Hermit)

- **#576**: Collapse layout/'s three klt pins into one: the main pin now descends from both the ERC and cap-rail pins *(hermit)* *(held)*
- **#591**: ci.yml: the 65-line check-inventory header restates package.json and has drifted from it in four places *(hermit)* *(held)*
- **#595**: Remove load_results() from sim/bin/_probe_common.py: the one advertised probe helper with no caller *(hermit)* *(held)*

## Epics

- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification *(held)*

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 3 |
| Very important | 1 |
| Important | 1 |
| Ready (`loom:issue`) | 2 |
| In Progress (`loom:building`) | 5 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 3 |
| Curated | 14 |
| Architect / Hermit proposals | 3 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
