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
- **PDK**: two different statements, both true. The *submitter* resolved sky130A @ open_pdks
  `c6d73a35` (matches the `sim/pdk.json` pin). The *batch workers* reported a different
  revision: in all 18 iq/clamp reports (`runs/{iq,cl}-{base,cand}/klt-out/*/report.json`)
  `environment.remote.worker_environment.pdk_stamp_comparison.status` is **`mismatch`** and the
  executed stamp is `open_pdks f6eeac7d…` (the 2 `cl-pair-*` reports say the same), while the
  top-level `models_lib_comparison` is `match`. Readers must judge applicability to the
  production pin themselves; no result here is claimed to have run on `c6d73a35`. For the
  **thermal** legs the committed point records omit the worker stamp, so the executed thermal
  revision is **unverified**.
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
- **rev2 passes all 45** (harness grade); per-corner ΔIq (full load) is −3.7…+0.9 µA, joined by
  corner in `tables/iq_pair.csv`. The **largest cut is −3.7 µA at `ss_-40c_3.63v`, a corner
  production already passes**; at production's five failing corners the cuts are only
  −0.7…−2.9 µA (`summary.json` → `iq.paired`). The largest increase is +0.9 µA at
  `ff_125c_2.97v`.
- **Resolution (printed and solver reported separately).** The full-load card prints the
  ~0.05 A supply current with 6 significant digits (`iq_full_load_raw = -5.00300e-02` A at
  `ff_125c_3.63v`), so the last printed digit is 1e-7 A = **0.1 µA**; the manifest's
  subtraction of the ideal 0.05 A load does not refine that. Solver settings are ngspice's
  defaults (reltol 1e-3, abstol 1e-12 A, vntol 1e-6 V) and a convergence setting alone is not
  an error bound on that difference; no precision/tolerance comparison was run.
- **ff/125 °C/3.63 V (the AC's named row)**: production 15.38 / **30.70 µA** (FAIL; the 0.7 µA
  exceedance is larger than the 0.1 µA print quantum); rev2 14.61 / **29.999999999995 µA** —
  the harness grade is PASS, but the margin (~5e-12 µA) is far inside the print quantum, so
  **strict-bound compliance at this corner is unresolved** and no solver-resolved margin is
  claimed. The PASS is a floating-point inequality, not evidence of margin.

### Current limit (row window TBD per spec — values reported, never graded against an invented window)

- 45 corner keys per variant, forced-output DC curve + short-circuit hold, including the
  **Vin_max (3.63 V) short at every process/temperature**. Valid (solver-gate-passing)
  corners from `base_pass`/`cand_pass`: **41/45 production, 43/45 rev2**; paired statistics use
  the 39 corners where both passed.
- **Non-engagement ≤ 50 mA** holds on valid corners for both DUTs: `vout_50ma` 1.7978–1.7991 V
  (production) / 1.8007–1.8044 V (rev2), inside the ratified 1.764–1.836 V window; minimum
  forced-output knee 74.6 mA (production, `ff_125c_2.97v`) / 71.8 mA (rev2, `ff_-40c_2.97v`).
  *The knee is the forced-output current sampled at Vout = 1.75 V; it is a proxy for
  engagement current, not a measured engagement point.*
- **The clamp moves substantially across PVT — it is not a uniform 2–3 % shift.** Paired
  rev2/production − 1 on the knee over the 39 paired corners spans **−46.6 %** (`fs_-40c_3.30v`:
  137.980 → 73.688 mA; short −44.0 %) to **+84.1 %** (`sf_125c_2.97v`: 95.540 → 175.861 mA;
  short +81.8 %); the knee falls at 18 and rises at 21 corners. The overlay's clamp-visible
  change (XM_CLP gate BIASP → PBR) tracks the measured bias currents (I_R 1.73–2.48 µA
  production vs 0.49–1.00 µA rev2, `tables/ir_spread.csv`), so the adoption trade-off should
  be read from the paired per-corner changes. The clamp window stays TBD; nothing is graded
  against an invented window.
- **Reported window values (valid corners)**: `ilim_short` 97.7–231.7 mA (production) /
  94.5–228.9 mA (rev2); short sustained the full 2 ms hold everywhere; peak ripple on a valid
  corner 0.123384 % (production, `ff_125c_2.97v`) / 0.122516 % (rev2, `fs_-40c_3.30v`).
- **Solver-invalid corners, reported separately (not valid)**: production 4 — `tt_27c_3.63v`,
  `ff_27c_3.63v`, `fs_27c_3.63v`, `fs_125c_3.63v` (all Vin_max; reproduces #647's baseline
  diagnostics; retained shorts 160.5–189.6 mA); rev2 2 — `fs_-40c_3.63v` (Vin_max; retained
  short **102.8 mA**, knee 73.9 mA) and `ff_27c_3.30v` (**not** Vin_max; retained short
  **131.3 mA**, knee 99.7 mA). Both rev2 diagnostic keys are new relative to production, and
  their retained values are **outside** the 160–195 mA family of the other solver-invalid
  corners; they are retained but not counted valid.
- **Batch adapter disclosure (#648)**: the three chained current-limit legs ran
  through `batch_current_limit.py`, imported verbatim from PR #648 head
  `befb83fb` (**unmerged at campaign time**; `loom:merge-conflict` +
  `loom:changes-requested`) — main's batch backend had no current-limit entry
  then. One compatibility shim at the call site
  (`blr._tokens = blr._EXPR.tokenize`; main had removed `_tokens` after #648's
  branch point). Coverage gap at campaign time: none — the adapter ran every
  leg; the gap was that the *graded* backend path for current-limit did not
  exist on main, so grading used the campaign's local evaluator over the same
  manifest expressions and bounds. **Since superseded:** #648 merged
  (2026-11-22T21:20:53Z), so `sim/bin/batch_current_limit.py` and a
  `"current-limit"` entry in `sim/bin/_batch_backend.py` now exist on `main`
  and the shim's premise (`_tokens`) is gone. The local-evaluator grading is a
  campaign-time condition; #702 may re-grade against the merged backend path.

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

Joined by corner, production's I_R and tail maxima are both at **`sf_27c_3.63v`**
(2.48 µA / 4.06 µA), which is not one of its failing Iq corners; rev2's maxima are at
`sf_125c_3.63v` (1.00 µA / 2.37 µA). The production Iq failures are in the 3.63 V column at
full load (`ff`/`fs`), and rev2's largest Iq cut (−3.7 µA) is at `ss_-40c_3.63v`, so the Iq
gain is attributed to the lower tail/bias level across the 3.63 V column, not to a match with
the I_R peak. Classification of every limitation found:

| Limitation | Class | Note |
|---|---|---|
| Iq > 30 µA at 3.63 V full load (5 corners) | **inherited (production)** | fixed by rev2 — the campaign's only spec-row violation among the three benches, removed |
| Iq strict-bound compliance at ff/125 °C/3.63 V unresolved | shared | printed resolution 0.1 µA at full load; production *fails* that corner (30.7 µA), rev2 sits at 29.9999… µA (margin ≪ print quantum; no solver-resolved margin claimed) |
| Clamp solver-diag at Vin_max (prod 4, rev2 1 of them) | **inherited** | reproduces #647 exactly; #171 gate working as designed |
| Clamp solver-diag `ff_27c_3.30v` and `fs_-40c_3.63v` (rev2 only; the first not Vin_max) | **introduced** | retained values (131.3 mA short at `ff_27c_3.30v`; 102.8 mA short at `fs_-40c_3.63v`) fall outside the 160–195 mA family of the other solver-invalid corners; not counted valid |
| Clamp trip moves −46.6 % … +84.1 % (paired knee) across PVT | **introduced** | not a uniform shift; window stays TBD |
| Thermal nominal offsets (trip >150, hyst <15) | **inherited** | identical on both DUTs; binding sign bound passes everywhere |
| >125 °C model extrapolation (thermal bench) | **inherited** | DR-005/DR-004 caveat, unchanged |

## Coverage reconciliation (attempted vs expected keys)

| Leg | Expected keys | Attempted | Graded/valid | Gaps |
|---|---|---|---|---|
| iq base / cand | 45 / 45 | 45 / 45 | 45 / 45 | none |
| clamp base / cand | 45 / 45 | 45 / 45 | 41 / 43 valid (4 + 2 solver-diag corners listed separately, not valid) | none |
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
benches: clamp never engages ≤ 50 mA on valid corners (forced-output knee ≥ 71.8 mA) and
thermal trip/reset are unchanged within one bisection step. **The clamp trip itself is not
within noise of production**: the paired knee moves −46.6 % … +84.1 % across PVT. The costs are
two new solver-diagnostic corners in the clamp bench (one non-Vin_max) and an Iq whose strict
bound compliance is unresolved at ff/125 °C/3.63 V (harness PASS without resolved margin).
The executed worker PDK revision differs from the submitter's pin (`mismatch`, above). Dynamics
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
