# Work Plan

Current roadmap derived from GitHub lifecycle labels. Maintained by the Loom Guide role.

<!-- guide:plan-body:start -->
_Generated: 2026-11-26T02:32:33Z (snapshot; compare against live labels)_
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#569**: docs: propose DR-014 binding capacitor condition for the PSRR row

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#467**: Bias re-topology so R_BIAS is not one long resistor: new DR, to meet the < 0.1 mm² Area row without a fold waiver (#461) *(held)*

## Important

`loom:important`; taken before unlabelled work.

- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge *(held)*
- **#786**: Verify the graded PSRR batch adapter and publish its 45-corner fleet record *(held)*

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues closed by an open `loom:pr` PR (listed under Approved).

- **#629**: characterization.md Output row reads PASS on light-load-only evidence; record 20261115-133911-1caff9b9 is full-load evidence against that same window
- **#639**: xschem pin migration: migrate sky130-ldo to the fleet 3.4.7

## In Progress

Issues currently being built (`loom:building`).

- **#767**: sim/pdk.json pins a volare sky130A build while every worker run uses the ciel store (--allow-pdk-mismatch on every record)
- **#791**: Batch-mode PDK provenance: the pinned-PDK guard and the record's PDK line are blind to the fleet worker's own stamp
- **#805**: DR-008 ratification: reconcile the thermal-restart market escalation with integrated-comparator evidence
- **#808**: Remove the second corner lookup that loses chained batch diagnostics

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#810**: docs(spec): append DR-008 restart-evidence reconciliation for the fresh ratification review

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#569**: docs: propose DR-014 binding capacitor condition for the PSRR row *(held)*
- **#794**: fix: verify the executed worker PDK before publishing simulation records
- **#811**: fix: keep chained batch corner diagnostics on the validated pairing

## Proposed

Issues carrying `loom:curated`.

- **#114**: Gap to T1: 6 of 12 ratified rows FAIL — replacement tracker (#58 closed on child-completion, not on verdict) *(curated)* *(held)*
- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification *(curated)* *(held)*
- **#301**: spec: decide whether DR-008 through DR-012 ratified on merge *(curated)* *(held)*
- **#314**: PSRR: decide and evidence the binding output-capacitor/ESR condition *(curated)*
- **#345**: Load transient: mint the COUT/ESR window-grid x 45 PVT campaign via --backend batch (blocked on fleet runner update) *(curated)* *(held)*
- **#416**: Re-run folded-resistor MC at n>=1000 to firm up M2 sigma-ratio gate *(curated)* *(held)*
- **#461**: T1 item 5 area: compact routed ldo_core under 0.1 mm² with capacitors drawn, re-mint records (part of #458) *(curated)* *(held)*
- **#503**: measurements: characterization generator cannot see artifact-store-only sim records (iq 20261105-052332-05df7a01) *(curated)* *(held)*
- **#550**: Re-run signoff-graded benches made stale by the integrated comparator (split from #548) *(curated)* *(held)*
- **#629**: characterization.md Output row reads PASS on light-load-only evidence; record 20261115-133911-1caff9b9 is full-load evidence against that same window *(curated)*
- **#639**: xschem pin migration: migrate sky130-ldo to the fleet 3.4.7 *(curated)*
- **#645**: CI: nightly pdk-smoke red for 6+ nights — declared ngspice pin 42 vs resolved 45.2 (CI) / 47 (workers) *(curated)* *(held)*
- **#691**: Stability: screen a compensation candidate that closes the 10-300 uA band at both C_out endpoints and the 0.33 uF / 50 mA shortfall (follow-on to #370) *(curated)* *(held)*
- **#767**: sim/pdk.json pins a volare sky130A build while every worker run uses the ciel store (--allow-pdk-mismatch on every record) *(curated)*
- **#786**: Verify the graded PSRR batch adapter and publish its 45-corner fleet record *(curated)* *(held)*
- **#791**: Batch-mode PDK provenance: the pinned-PDK guard and the record's PDK line are blind to the fleet worker's own stamp *(curated)*
- **#805**: DR-008 ratification: reconcile the thermal-restart market escalation with integrated-comparator evidence *(curated)*
- **#812**: Resync Loom so large private defaults no longer abort create-pr.sh and create-issue.sh *(curated)*

## Proposed (Architect / Hermit)

- **#813**: Reuse the batch measurement validator so startup cannot pass an errored peak-voltage reading *(hermit)*

## Epics

- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification *(held)*

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 1 |
| Important | 2 |
| Ready (`loom:issue`, net of holds/building/merge-pending) | 2 |
| In Progress (`loom:building`) | 4 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 3 |
| Curated | 18 |
| Architect / Hermit proposals | 1 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
