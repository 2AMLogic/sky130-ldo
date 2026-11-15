# Work Plan

Current roadmap derived from GitHub lifecycle labels. Maintained by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#569**: docs: propose DR-014 binding capacitor condition for the PSRR row
- **#573**: docs(spec): reconcile DR-009's ratifying-act wording with the #301 ruling

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#467**: Bias re-topology so R_BIAS is not one long resistor: new DR, to meet the < 0.1 mm² Area row without a fold waiver (#461)

## Important

`loom:important`; taken before unlabelled work.

- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#596**: Collapse the triplicated PM/GM spec thresholds in sim/bin onto _fleet_campaign.py
- **#606**: Collapse the duplicated 51-line item-5 envelope literal in signoff/make_item5_envelope.py
- **#609**: docs: four prose copies still instruct a raw headless `xschem -n -q -x -s` where `klt netlist` is the decided path

## In Progress

Issues currently being built (`loom:building`).

- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge
- **#314**: PSRR: decide and evidence the binding output-capacitor/ESR condition
- **#327**: sim(pex): run the 45-corner schematic-side PEX leg once the batch fleet runner accepts klt 0.7.x clients (split from #277)
- **#550**: Re-run signoff-graded benches made stale by the integrated comparator (split from #548)
- **#579**: Docs PRs touching README.md always fail signoff stage 1b (item 10 attestation drift)
- **#582**: README and signoff/README still say T1 5/11; the verdict of record says 9/11
- **#586**: Fold sim/bin/bias-retopo-grid.py onto _fleet_campaign.py: the one batch-fleet driver #574's dedup missed
- **#587**: Deduplicate the batch adapter test scaffolding: 113 identical lines across three test files
- **#598**: Remove corner-run.py's spiceinit_digest: byte-identical duplicate of _record_common.spiceinit_sha256
- **#613**: Thermal observation instants (T_COLD..T_REEN) are duplicated between run_hysteresis.py and batch_thermal_staircase.py

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#593**: refactor(sim): build the bias grid's requests and submits on _fleet_campaign
- **#600**: docs(signoff): correct "What would move the needle" for items 11 and 1/2/9/10
- **#614**: refactor(sim): derive hysteresis observation instants from batch_thermal_staircase

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#569**: docs: propose DR-014 binding capacitor condition for the PSRR row
- **#573**: docs(spec): reconcile DR-009's ratifying-act wording with the #301 ruling
- **#584**: feat(signoff): catch item-10 hygiene drift and T1 headline staleness in check:ci
- **#602**: refactor(sim): use _record_common.spiceinit_sha256 in corner-run.py
- **#603**: refactor(sim): extract one shared batch endpoint-adapter test contract

## Proposed

Issues carrying `loom:curated`.

- **#114**: Gap to T1: 6 of 12 ratified rows FAIL — replacement tracker (#58 closed on child-completion, not on verdict) *(curated)*
- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification *(curated)*
- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge *(curated)*
- **#314**: PSRR: decide and evidence the binding output-capacitor/ESR condition *(curated)*
- **#345**: Load transient: mint the COUT/ESR window-grid x 45 PVT campaign via --backend batch (blocked on fleet runner update) *(curated)*
- **#416**: Re-run folded-resistor MC at n>=1000 to firm up M2 sigma-ratio gate *(curated)*
- **#461**: T1 item 5 area: compact routed ldo_core under 0.1 mm² with capacitors drawn, re-mint records (part of #458) *(curated)*
- **#503**: measurements: characterization generator cannot see artifact-store-only sim records (iq 20261105-052332-05df7a01) *(curated)*
- **#550**: Re-run signoff-graded benches made stale by the integrated comparator (split from #548) *(curated)*
- **#579**: Docs PRs touching README.md always fail signoff stage 1b (item 10 attestation drift) *(curated)*
- **#582**: README and signoff/README still say T1 5/11; the verdict of record says 9/11 *(curated)*
- **#609**: docs: four prose copies still instruct a raw headless `xschem -n -q -x -s` where `klt netlist` is the decided path *(curated)*
- **#613**: Thermal observation instants (T_COLD..T_REEN) are duplicated between run_hysteresis.py and batch_thermal_staircase.py *(curated)*

## Proposed (Architect / Hermit)

- **#576**: Collapse layout/'s three klt pins into one: the main pin now descends from both the ERC and cap-rail pins *(hermit)*
- **#591**: ci.yml: the 65-line check-inventory header restates package.json and has drifted from it in four places *(hermit)*
- **#595**: Remove load_results() from sim/bin/_probe_common.py: the one advertised probe helper with no caller *(hermit)*
- **#607**: README.md's 16-row spec table is a second copy of the ratified gate and has drifted in four rows *(hermit)*

## Epics

- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 2 |
| Very important | 1 |
| Important | 1 |
| Ready (`loom:issue`) | 3 |
| In Progress (`loom:building`) | 10 |
| PRs awaiting review | 3 |
| Approved PRs awaiting merge | 5 |
| Curated | 13 |
| Architect / Hermit proposals | 4 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
