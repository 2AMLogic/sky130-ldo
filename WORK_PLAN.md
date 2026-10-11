# Work Plan

Current roadmap derived from GitHub lifecycle labels. Maintained by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs stuck under a `loom:operator` merge-risk hold — implementation work is done, only a human merge decision is missing.

_None._

## Operator Priority

Issues the operator starred (`loom:operator-priority`); land these first.

_None._

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#263**: Qualify folded resistor electrical equivalence across process, temperature and mismatch

## In Progress

Issues currently being built (`loom:building`).

- **#277**: sim: post-layout PEX schematic-side corners fail with 'Undefined parameter [swx_nrds]'; no PEX evidence for #267 geometry

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification *(curated)*
- **#177**: Seed sim/current-limit's leg-1 operating point to conform to the initial-condition contract *(curated)*
- **#213**: sim(iq): mint the 45-corner record under #173's seeded deck + #133's regulation gate — deck fixed, matrix not re-run (host contention) *(curated)*
- **#263**: Qualify folded resistor electrical equivalence across process, temperature and mismatch *(curated)*
- **#267**: layout: fix locally-routed official-DRC families (via.1a_b, m2.5, via2.5, nwell.9) found by #260 *(curated)*
- **#277**: sim: post-layout PEX schematic-side corners fail with 'Undefined parameter [swx_nrds]'; no PEX evidence for #267 geometry *(curated)*
- **#313**: Load transient: qualify the ratified capacitor and ESR window *(curated)*
- **#314**: PSRR: decide and evidence the binding output-capacitor/ESR condition *(curated)*

## Proposed (Architect / Hermit)

- **#313**: Load transient: qualify the ratified capacitor and ESR window *(architect)*
- **#314**: PSRR: decide and evidence the binding output-capacitor/ESR condition *(architect)*
- **#318**: layout: regenerate ldo_core from the current schematic and re-mint the area record *(architect)*
- **#319**: Area: compare capacitor implementations (MiM, vpp, MOS-cap) for the 162 pF compensation/soft-start budget *(architect)*

## Epics

- **#131**: Thermal shutdown: track regenerative auto-restart hysteresis design, integration, and qualification

## Backlog Balance

| Tier | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Operator priority | 0 |
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 1 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 0 |
| Curated | 8 |
| Architect / Hermit proposals | 4 |
| Active epics | 1 |
<!-- guide:plan-body:end -->
