# sky130-ldo roadmap

A 3.3 V-in / 1.8 V-out / 0-50 mA low-dropout regulator on the sky130 open PDK,
designed forward from a ratified spec through the open flow (xschem, ngspice, `klt`).

Status as of 2026-11-13, `main` @ `8aebd9b8`.

Verdicts of record: [`measurements/characterization.md`](../measurements/characterization.md)
per row, [`signoff/records/t1-tier-report.json`](../signoff/records/t1-tier-report.json)
per T1 item. Where this file disagrees with them, it is stale.

## Where it stands

**Evidence ladder: `tier: null`, T1 9 of 11 items met** (`klt signoff` 0.9.0).
Met: 1 design sources, 2 layout, 3 DRC clean, 4 LVS clean, 6 Monte Carlo
evidence, 8 characterization report, 9 testbenches, 10 repo hygiene, 11 power
delivery. Unmet, both `check_failed`: **5** (full corner verification against
the ratified spec) and **7** (post-layout verification).
[`signoff/README.md`](../signoff/README.md) has the per-item reading.

**Item 5, row by row** (verdict and freshness are separate facts):

| Row | Verdict | Record state |
|---|---|---|
| Output, Line regulation, Current limit, Startup, Enable/shutdown | PASS | STALE against the current schematic |
| Thermal | PASS, 15/15 corners | integrated-comparator hysteresis record (PR #555, #559) |
| Dropout @ 50 mA | FAIL | STALE, single-corner subset |
| Load regulation 44/45, Load transient 0/45, PSRR 0/45, Iq 36/45, Stability 7/45 | FAIL | STALE |
| Area | FAIL, 0.4519 mm² against < 0.1 mm² | fresh (GDS sha256) |

The staleness has one cause: the regenerative thermal comparator was integrated
into the schematic (#230), so earlier netlist snapshots no longer match. The
layout was brought current on 2026-11-12: core regenerated, DRC clean on both
decks, LVS match, items 3, 4 and 11 re-pinned (PR #557, #566).

**Item 7**: the post-layout record `20261022-232148-56dd87fe` is STALE against
the regenerated GDS and has no single PASS/FAIL. On the current `klt` pin every
net fell back to the legacy lumped-R model (`unsupported_geometry`; see
[`sim/pex-post-layout/README.md`](../sim/pex-post-layout/README.md)). The two
upstream issues that file names (klayout-tools#2391, #2458) are closed, nothing
here has re-measured since, and no open issue tracks item 7.

**Decision records**: DR-001 to DR-006 and DR-013 (bias re-topology, per its
2026-11-04 amendment) are ratified. DR-007 to DR-012 are `proposed`; DR-008 to
DR-012 need fresh ratification under the #301 ruling. DR-014 is PR #569.

## Now

Can start today, one pull request each.

1. **Make the README's ladder paragraph match the verdict of record.**
   `README.md` says "T1 5/11", as do two passages of `signoff/README.md`. Done
   when all say 9/11, a unit test fails if the count drifts again, and the item
   10 attestation is re-minted for the changed `README.md`. No issue yet.
2. **Re-measure what blocks item 7.** Run the extraction step alone (no corner
   grid) on the current `LATEST` GDS, at the repo's pin and at the newest `klt`
   release, and count graph-derived nets (0 of 28 on the last record). Done
   when a diagnostic record exists under `sim/pex-post-layout/diagnostics/` and
   both READMEs name the current blocker. No issue yet.
3. **Finish the #301 wording.** `README.md`, `spec/target-spec.md` (two places)
   and `CLAUDE.md` still say DR-009 "ratifies on" merge; the ruling says fresh
   ratification. Done when `grep -n 'ratifies on' README.md CLAUDE.md
   spec/target-spec.md` is empty. Issue #301 (in progress; the DR-009 file
   itself is PR #573, approved and held).
4. **Re-probe the batch backend for the parked runs.** #375 and #327 are parked
   on a runner/client version mismatch seen on 2026-10-11, yet batch records
   were minted on 2026-11-12 (PR #556, #561). Done when
   `python3 sim/bin/batch-preflight.py` exits 0 and #375's paired local/remote
   dropout check is recorded, or the current refusal is written on the issue.
   Issue #375 (still labelled blocked; needs release).

## Next

- **Fresh records for Dropout, Line regulation, Load regulation, Iq, Load
  transient.** The runs exist in PR #561. Done when it merges with item-5
  envelopes that verify. Issue #550; waits on the #565 decision.
- **Fresh records for the benches with no batch route** (`psrr-dc`,
  `loop-gain`, `startup`, `enable-shutdown`, `current-limit`). Done when each
  has a record whose netlist snapshot matches the current schematic. Waits on
  the #554 route decision; #177 (current-limit seeding) rides on the same route.
  `mc-output-accuracy` already has one (`20261112-110113-820ba8b3`, PR #556)
  that the report does not cite yet (#503).
- **45-corner schematic-side PEX leg** on the regenerated layout: a new record
  compared with baseline `20260924-230726-a947aa8`. Issue #327; after Now 4.
- **PSRR on its binding capacitor condition**: add the DR-014 legs to
  `sim/psrr-dc/experiment.json`. Issue #314; after PR #569 is ratified.
- **Bias re-topology, second candidate.** PR #537 attributed the DR-013
  candidate's ten full-load Iq exceedances as 7 pre-existing and 3 caused,
  which under the ruling on #467 means a new candidate aimed at high-VIN Iq.
  Done when it has a record on the same 63-point matrix. Issue #467, whose
  scope must be rewritten first. **Area** follows it: the routed core with all
  four capacitors under 0.1 mm², layout records re-minted (#461, #458).
- **Load-transient window grid** (C_out/ESR x 45 PVT). #345; after Now 4.

## Later

- **Close the failing electrical rows.** Dropout, Load regulation, Load
  transient, PSRR, Stability and Iq fail, and their design issues (#115 to
  #121) are all closed. First: once fresh records exist, which failures share a
  cause? #114 suggests stability first; that coupling is unconfirmed.
- **PSRR and Stability topology** (DR-007, proposed 2026-09-14). First: is its
  recommendation still the one to ratify after DR-013 and DR-014?

## Blocked and waiting

On a maintainer decision:

- #565: how item-5 envelopes read records whose JSON lives only in the artifact
  store (holds PR #561 and #550; #503 is the same gap in the report generator).
- #554: batch route for the benches without one.
- PR #569 (DR-014), PR #573 (DR-009 wording): approved, held because merging
  ratifies. #301: fresh ratification of DR-008 to DR-012. #467: re-scope.
- #416: the n=4000 folded-resistor Monte Carlo job failed at startup and its
  log is not readable by an agent.
- #345 (upstream blocker closed without a fix), #131 (close the thermal epic
  or not), #576 (collapse the three `klt` pins), #336 (startup at the ESR boundaries).

On a tool: `startup`'s monotonicity check needs raw traces from the batch path
(#554 names klayout-tools#3360, now closed; not re-verified here).

**No issue is labelled ready today.** What can be drawn is Now 1 and 2 once
filed, and Now 3 and 4, existing issues (one in progress, one parked).

## Not planned

- Relaxing a ratified row to make a result pass (`CLAUDE.md`).
- An output-noise measurement (the spec waives the row) or a yield target (the
  spec ratifies none; item 6 reads `reported`).
- Folding `R_BIAS` to meet the Area row: ruled out on #461 (fails #263's gate).
- Evidence tiers above T1: nothing here has been fabricated.
