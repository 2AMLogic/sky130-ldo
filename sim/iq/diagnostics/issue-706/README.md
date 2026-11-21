# Issue #706 — rev2 bias/protection characterization: Iq, clamp, thermal hysteresis

Paired candidate-vs-production campaign for the **#702 rev2 adoption decision**
(parent: #702; candidate source: #692 / PR #703; sibling evidence: #704 dynamics).
Three benches — `sim/iq`, `sim/current-limit`, `sim/thermal` (DR-005 hysteresis
procedure) — each run on the **committed production DUT** and on the **rev2
candidate** at one pinned base. This directory is the summary; the three
append-only records are the evidence of record:

| Bench | Record | Verdict data |
|---|---|---|
| Iq | `sim/iq/records/20261121-042335-db9f161a-i706-paired.md` | `tables/iq_pair.csv`, `tables/summary.json` |
| Current limit | `sim/current-limit/records/20261121-042335-db9f161a-i706-paired.md` | `tables/clamp_pair.csv`, `tables/summary.json` |
| Thermal | `sim/thermal/records/20261121-092243-db9f161a-i706-paired.md` | `tables/summary.json` (thermal) |

All grids ran on the Spot batch fleet via `klt sim` (batch job ids in each
record and in `runs/*/leg.json`, `runs/*/klt-out/*/report.json`
`environment.remote`, and the hysteresis `result.json` job lists). No local
grid was launched; the only local runs are the single-corner syntax probes in
`runs/local-syntax/`. Declared command sequence with deviations:
`commands.sh`. Full pairing/adapter provenance: `provenance.json`.

## Pairing and provenance (shared contract with #704)

- **Production base**: `db9f161a` (= `origin/main` at campaign time, clean
  tree), schematic `design/ldo_3v3in_1v8out.sch`, actual cards
  `C_COMP = 150p m=1`, `XR_CZ = sky130_fd_pr__res_xhigh_po W=0.42 L=52 mult=1
  m=1` (the #691 shelf).
- **Candidate**: the same netlist after `apply_candidate(raw, 2)` from
  `candidate.py` in this directory — imported **verbatim** from PR #703 head
  `01dfd695` (branch `feature/issue-692`; PR still **open** at campaign time
  and at record time, so the overlay is NOT on `origin/main` — the two SHAs
  above are the pinned pair). Lineage: `sim/dropout-vs-load/diagnostics/issue-357/candidate.py`
  (on main). The rev2 lever is NTAIL W12/nf3 → W7/nf2 (tail mirror 4.8x → 2.8x
  of NBR) plus the preserved #691 compensation; per-leg netlist diffs and
  per-corner engine logs are committed under `runs/`.
- **Invariant check**: `check_candidate` passed with 0 problems on every leg of
  every bench. The candidate's one clamp-visible change is XM_CLP's gate
  BIASP → PBR.
- **PDK**: sky130A @ open_pdks `c6d73a35` — matches `sim/pdk.json` pin.
- **#467 (bias re-topology)**: still `loom:operator`, **not landed** as of
  this campaign — no pairs need repeating yet. If it lands before #702's
  review, the affected pairs (bias-sensitive: Iq and the I_R column of the
  clamp legs) must be repeated on the new baseline; clamp trip and thermal
  sense are bias-derived too, so the safest reading is: repeat all three.

## Verdict summary

### Iq (spec row: < 30 µA strict, no load AND 50 mA; DR-009 proposed)

- 45/45 corners per variant, harness-graded by the bench's own endpoint
  adapter (identical bounds and gates to a records run).
- **Production FAILS 5 corners**, all 3.63 V at full load:
  `ff_-40c_3.63v` (31.3 µA), `ff_27c_3.63v`, `ff_125c_3.63v` (30.7 µA),
  `fs_-40c_3.63v`, `fs_27c_3.63v` (30.2–31.3 µA range).
- **rev2 passes all 45**; per-corner ΔIq is −3.7…+0.9 µA (largest cuts exactly
  at production's failing `ff`/`fs` 3.63 V corners; small increases at some
  `tt`/`ss` 125 °C corners, where production was already ~4 µA inside the
  bound).
- **ff/125 °C/3.63 V (the AC's named row)**: production 15.38 / **30.70 µA**
  (FAIL, resolved exceedance); rev2 14.61 / **29.999999999995 µA** — raw card
  `-0.05003` A (6 sig. digits), derived value coincides with the bound at
  print resolution and the ~0.03 µA solver band (default reltol 1e-3) straddles
  it: **positive margin is NOT resolved**. The strict-bound PASS there is a
  floating-point inequality, not evidence of margin (full statement in the iq
  record; resolution rule: margin called resolved only when > 0.1 µA = 3x
  solver band + print quantum, never from the last printed digit).

### Current limit (row window TBD per spec — values reported, never graded against an invented window)

- 45/45 corners per variant, forced-output DC curve + short-circuit hold,
  including the **Vin_max (3.63 V) short at every process/temperature**.
- **Non-engagement ≤ 50 mA holds for both DUTs at all 45 corners**:
  `vout_50ma` stays 1.7978–1.7991 V (production) / 1.8007–1.8043 V (rev2),
  both inside the ratified 1.764–1.836 V output window; minimum forced-output
  knee current 74.6 mA (production) / 71.8 mA (rev2) — ≥ 21.8 mA headroom.
- **Reported window values**: `ilim_short` 97.7–231.7 mA (production) /
  94.5–228.9 mA (rev2); short sustained the full 2 ms hold everywhere; ripple
  < 0.1 %. rev2's trip sits ~2–3 % below production's per corner (overlay
  preserves, not re-targets, the 3.3 V trip point).
- **Solver-invalid corners, reported separately**: production 4 — `tt_27c_3.63v`,
  `ff_27c_3.63v`, `fs_27c_3.63v`, `fs_125c_3.63v` (all Vin_max; reproduces
  #647's known baseline diagnostics exactly); rev2 2 — `fs_-40c_3.63v`
  (Vin_max, same class) and `ff_27c_3.30v` (**not** Vin_max — new, see
  classification). All six returned healthy values (160–195 mA); the #171 gate
  flags them, their numbers are retained but not counted harness-clean.
- **Batch adapter disclosure (#648)**: the three chained current-limit legs ran
  through `batch_current_limit.py`, imported verbatim from PR #648 head
  `befb83fb` (**unmerged**; `loom:merge-conflict` + `loom:changes-requested`)
  — main's batch backend has no current-limit entry. One compatibility shim at
  the call site (`blr._tokens = blr._EXPR.tokenize`; main removed `_tokens`
  after #648's branch point). Coverage gap: none for this campaign — the
  adapter ran every leg; the gap is that the *graded* backend path for
  current-limit does not exist on main, so grading used the campaign's local
  evaluator over the same manifest expressions and bounds.

### Thermal (DR-005 fault backstop: 150/135 °C nominal, auto-restart, hysteresis positive)

- 15/15 corners per variant on the bench's own staircase bisection
  (`run_hysteresis.py`, 676 points per variant, tolerance 0.3125 °C).
- **Both crossings bisected at every corner for both variants — no missing or
  invalid crossings;** auto-restart confirmed by the EN-dip dependent round
  everywhere.
- Production trip 162.0–181.4 °C, reset 148.9–168.9 °C; rev2 trip
  161.7–181.4 °C, reset 148.9–168.9 °C. Hysteresis **+12.5 to +13.4 °C,
  positive at all 30 corner/variant pairs** — the spec row's binding
  hysteresis-sign bound passes everywhere. Both DUTs sit above the 150/135
  nominals and ~2 °C below the 15 °C nominal hysteresis, identically.
- |Δtrip| ≤ 0.3125 °C (exactly one bisection step) at every corner: **rev2
  does not move the thermal trip/reset outside the measurement's own
  resolution.**
- >125 °C points run the pinned models in extrapolation beyond DR-004's
  characterized axis — inherited bench caveat, unchanged.

## Binding to I_R (bias current), worst conditions, inherited vs introduced

`tables/ir_spread.csv` (measured on the clamp legs' 50 mA operating point at
all 45 corner keys):

| Quantity | production | rev2 | worst condition |
|---|---|---|---|
| I_R (bias set) | 1.73–2.48 µA | 0.49–1.00 µA | prod peak `sf_27c_3.63v` 2.48 µA; rev2 peak `sf_125c_3.63v` 1.00 µA |
| EA tail | 2.40–4.06 µA | 1.36–2.37 µA | 3.63 V column, both DUTs |

The production DUT's worst Iq corners (`ff`/`fs` at 3.63 V, full load) are
exactly where its VIN-scaled bias/tail peaks; rev2's Iq gain tracks its tail
cut at the same corner keys. Classification of every limitation found:

| Limitation | Class | Note |
|---|---|---|
| Iq > 30 µA at 3.63 V full load (5 corners) | **inherited (production)** | fixed by rev2 — the campaign's only spec-row violation among the three benches, removed |
| Iq margin at ff/125 °C/3.63 V unresolved at the bound | shared | measurement-resolution statement; production *fails* that corner (30.7 µA), rev2 sits at 29.9999… µA |
| Clamp solver-diag at Vin_max (prod 4, rev2 1 of them) | **inherited** | reproduces #647 exactly; #171 gate working as designed |
| Clamp solver-diag `ff_27c_3.30v` (rev2 only, not Vin_max) | **introduced** | convergence flag only; measured values in-family (131.3 mA short, 99.7 mA knee vs rev2's own ff_27c neighbors); watch it if rev2 is adopted |
| Thermal nominal offsets (trip >150, hyst <15) | **inherited** | identical on both DUTs; binding sign bound passes everywhere |
| >125 °C model extrapolation (thermal bench) | **inherited** | DR-005/DR-004 caveat, unchanged |

## Coverage reconciliation (attempted vs expected keys)

| Leg | Expected keys | Attempted | Graded/valid | Gaps |
|---|---|---|---|---|
| iq base / cand | 45 / 45 | 45 / 45 | 45 / 45 | none |
| clamp base / cand | 45 / 45 | 45 / 45 | 45 / 45 (4+2 solver-diag listed separately) | none |
| thermal base / cand | 15 / 15 | 15 / 15 | 15 / 15, dependent rounds complete | none |

Deviations, all evidence-preserving: (1) first chained clamp submission
refused by klt over dotted `.meas` card names — kept in
`runs/attic-cl-pair-base-attempt1-cardname/`, cards renamed, resubmitted;
(2) `iq-base` interrupted mid-leg by a session timeout after 4/6 responses —
the in-flight remote job completed and was recovered via `klt sim --attach`,
one discarded recovery response (wrong client-side PDK root) and a re-attach
with `PDK_ROOT=/home/ubuntu/.volare`, then the bench's resume mode; every
condition key graded through the harness's own normalizer; (3) the thermal
candidate leg finished after the iq/clamp records were minted, so the thermal
record (`20261121-092243`) is a separate append-only mint.

## Implications for #702

On the bias/protection side, rev2 **removes the only measured spec-row
violation** (production Iq at 3.63 V full load) and keeps the protection
benches within noise of production: clamp never engages ≤ 50 mA with ≥ 21.8 mA
knee headroom, survives the Vin_max short everywhere, and thermal trip/reset
are unchanged within one bisection step. The costs are one new (non-Vin_max)
solver-diagnostic corner in the clamp bench and an Iq that sits exactly at the
30 µA bound at ff/125 °C/3.63 V — a pass without resolved margin. Dynamics
(load transient, loop gain) are #704's evidence, not this campaign's. This
characterization takes no position on adoption; it supplies the paired
records above.

## Reproducing / extending

`commands.sh` is the declared sequence as executed (all grids via `klt sim`
batch, `--wait-for-capacity 600`; single-corner syntax probes local).
Drivers in this directory: `campaign.py` (iq + clamp legs), `thermal_pair.py`
(thermal staircase pair), `analyze.py` (tables + `tables/summary.json`),
`write_records.py` / `write_thermal_record.py` (append-only record mints).
`sim/README.md`'s append-only rule governs every record and run directory
here.
