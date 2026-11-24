# Issue #702 (deliverable re-homed to #763): rev2 adoption review — low-headroom amplifier/clamp dropout candidate

This is the written adoption review #702 was split open for, delivered by #763 after
children #704, #705 and #706 closed with their evidence on `main`. It is a review of
existing evidence only: no bench was run or extended, nothing under any `sim/*/records/`
is minted, and `design/`, `spec/` and every threshold are untouched. Per #357 section 8
item 1, moving the candidate into `design/ldo_3v3in_1v8out.sch` requires a human-approved
review; this document is that review's **input**. The candidate ("rev2") is the #357
rev1 topology (NMOS-input symmetrical OTA + VREF-referenced bias + re-referenced clamp,
pass device and protection chain preserved) with its one evidence-driven revision:
NTAIL W12/nf3 → W7/nf2 (tail mirror 4.8x → 2.8x of NBR), cutting Iq everywhere without
touching the clamp reference chain. A defer/reject recommendation is a valid outcome;
the Human disposition at the end is left `pending` for a human.

## 1. Inputs, pairing contract, and where the campaigns differ

| campaign | evidence | pinned production base | DUT / overlay identity | bench conditions |
|---|---|---|---|---|
| #692/#703 dropout + Iq screen | `sim/dropout-vs-load/diagnostics/issue-692-20261120-235900/README.md`, `verdict.json` | both designs at one commit `218e3e99` | `candidate.py` re-based from `../issue-357/`; rev1 card output byte-identical to #357's module (verified at run time), `REV[2]` added | dropout + iq ratified manifests, full 45-point PVT, cold-start |
| #704 loop gain / load step / PSRR | `sim/loop-gain/diagnostics/issue-704/README.md`, `verdict.json` | `cd7a9d60` (schematic sha256 `1378c2d4…`) | overlay `apply_candidate(raw, 2)`, `candidate.py` sha256 `a08e93dc…`; `check_candidate` 0 problems every deck; compensation byte-identical in every pair | loop: tt/27 °C/3.30 V, 7 loads × 2 caps × 3 ESR = 42 legs/DUT; load-step: 6 cap/ESR legs × 3 `quick_subset` corners; PSRR: 45 corners × 2 loads |
| #705 start-up / line / load reg / MC | `sim/startup/diagnostics/issue-705-20261122-013500/README.md`, `verdict.json` | `1e328f65` | same overlay sha256 `a08e93dc…` (byte-identical to #692's); raw netlist hashes equal between base and cand legs on every bench | startup 45 × 12 legs; line 45 corners × 4 endpoints; load 45 corners 0→50 mA; MC tt_mm/27 °C/3.30 V/1 mA, 200 draws, seed 20260817 |
| #706 Iq / current limit / thermal | `sim/iq/diagnostics/issue-706/README.md`, `sim/iq/records/20261121-042335-db9f161a-i706-paired.md`, `sim/current-limit/records/20261121-042335-db9f161a-i706-paired.md`, `sim/thermal/records/20261121-092243-db9f161a-i706-paired.md` | `db9f161a` (schematic sha256 `1378c2d4…`) | overlay imported verbatim from PR #703 head `01dfd695`, sha256 `a08e93dc…`; `check_candidate` 0 problems every leg | iq 45 × {0, 50 mA}; clamp 45 keys, forced-output DC + 2 ms held short incl. Vin_max; thermal 15 corners, staircase bisection tol 0.3125 °C |

**Why the pairs may be combined.** `design/ldo_3v3in_1v8out.sch` last changed at
`a09aa83f` (2026-10-08, #230) — before every pin above — and its sha256 on current
`main` still begins `1378c2d440e6ffc2`, matching what #704 and #706 recorded. The
production DUT is therefore card-identical at all four pins; the campaigns differ only
in harness-side state. The overlay module is byte-identical (`a08e93dc…`) across
#704/#705/#706 and originates from the #692 campaign itself (PR #703 head `01dfd695`).
Cross-campaign rows below are combined on that basis.

**Disclosed differences a reader must carry (none hidden):**

- **Pinned commits differ** (`218e3e99` / `cd7a9d60` / `1e328f65` / `db9f161a`) — DUT
  content identical (above), so this affects harness provenance only.
- **#706 batch workers' PDK stamp mismatch**: all 18 iq/clamp reports record
  `pdk_stamp_comparison.status = mismatch`, executed stamp `open_pdks f6eeac7d…` vs the
  `sim/pdk.json` pin `c6d73a35…`; `models_lib_comparison` is `match`. No #706 number is
  claimed to have executed on the pin revision. #705 records `matches_pin: true` per
  leg; #704 records preflight compatibility `match` (146 batch jobs).
- **Thermal revision unverified**: the thermal point records omit the worker stamp, and
  no worker report was retained — whether those jobs ran on `f6eeac7d` or the pin is
  not established.
- **#705 dirty-tree note**: `git_state dirty: true` on six legs (the campaign's own
  untracked outputs); the narrower guarantee — schematic/testbench/`experiment.json`
  SHA-256s equal to `1e328f65` content — holds on every leg.
- **#704 bench adaptations, disclosed in its README**: the load-step `.ic` seed drops
  the three tokens the overlay removes (ngspice rejects the whole card otherwise); the
  rev2 loop-gain extraction check (VREF also gates the bias V-to-I) moves PM ≤ 0.041°
  and shows GM as-drawn 0.5–2.0 dB optimistic — worst corrected GM 16.17 dB, no GM
  verdict changes.
- **#706 current-limit adapter**: legs ran through PR #648's `batch_current_limit.py`
  (unmerged at campaign time; merged 2026-11-22) with a local-evaluator grading —
  #702 may re-grade against the merged backend path if it wishes.

## 2. Review table — one row per #702 bench row

Classes: **inherited failure** (baseline fails, rev2 fails the same way) /
**candidate regression** (new or worse on rev2) / **candidate improvement** (baseline
fails, rev2 passes, or measurably better) / **unresolved** (no trustworthy margin).
The first row records the dropout screen that motivated the candidate (delivered by
#692/#703 before the split); rows 1–9 are #702's original checklist verbatim in order
(with #705's line- and load-regulation benches from #702's Dependencies / #357 §8
item 1 listed alongside start-up as rows 3b–3c).

| # | bench row (ratified bound) | baseline | rev2 | worst condition | coverage | class | source |
|---|---|---|---|---|---|---|---|
| 0 | Dropout @ 50 mA < 300 mV (strict) | 0/45 pass; binding 0.6731 V | **45/45 pass**; binding **0.2202 V** (79.8 mV margin) | ff/-40 °C/2.97 V (rev2); ff/125 °C/3.63 V (base) | 45 PVT corners, both designs one commit | **candidate improvement** | #692 `tables/dropout_pair.csv`, `README.md` §4 |
| 1a | Stability PM ≥ 45° | 23/42 legs below; worst 17.45° | 26/42 below; worst 14.27° | 4.7 µF·0 mΩ·10 µA (rev2); 4.7 µF·0 mΩ·30 µA (base) | tt/27 °C/3.30 V only, 42 legs/DUT (other 44 PVT corners not attempted) | **candidate regression** (3 new PM failures at 4.7 µF, 0 mA, one per ESR: 53.12→38.37°, 53.12→38.37°, 53.17→38.42°) on top of an **inherited failure** (23 legs fail both; DR-006 0 mA gap) | #704 `tables/loop_pair.csv`, `README.md` verdict table |
| 1b | Stability GM ≥ 10 dB | 0/37 below; worst 16.95 dB | 0/38 below; worst 16.65 dB (16.17 dB corrected) | 0.33 µF·0 mΩ·50 mA | as 1a; 5 pairs GM-unavailable (reported, never passed) | inherited pass (no regressions) | #704 `tables/loop_pair.csv`, `verdict.json` (extraction check) |
| 2a | Load-step peak ≤ 150 mV | rise 9/18 fail (worst 215 mV); fall 2/18 (11/36 direction-legs) | rise 9/18 (worst **242 mV**); fall **8/18** (17/36 direction-legs) | 0.33 µF·ESR0, ff/125 °C/3.63 V (rise, both) | 6 cap/ESR legs × 3 `quick_subset` corners = 18 rise + 18 fall (36 direction-legs) per DUT | **candidate regression** (6 new falling legs; paired peak deltas ≤ +42 mV) over **inherited failure** (rise legs fail both) | #704 `tables/loadstep_pair.csv`, `verdict.json` |
| 2b | Load-step recovery ≤ 20 µs (±1 %) | 36/36 direction-legs above; worst 651.9 µs | 36/36 direction-legs above; worst 733.7 µs | 4.7 µF·ESR0, ff/125 °C/3.63 V | as 2a (18/18 rise + 18/18 fall); all within window, no ceiling artifact | **inherited failure** | #704 `tables/loadstep_pair.csv`, `verdict.json` |
| 2c | PSRR > 50 dB @ 1 kHz | 0/86 valid pass; worst 20.30 dB | 0/84 valid pass; worst 20.10 dB | 1 mA, fs/125 °C/2.97 V | 45 corners × 2 loads; solver-invalid load measurements excluded, not counted: 4 baseline / 6 rev2 = 2 baseline and 3 rev2 distinct PVT corners (each invalid at both loads; the sets are disjoint, so all 3 rev2 corners — ff/−40 °C/3.30 V, tt/−40 °C/2.97 V, tt/−40 °C/3.63 V — are rev2-only gaps) | **inherited failure** | #704 `tables/psrr_pair.csv`, `verdict.json` |
| 2d | PSRR > 20 dB @ 100 kHz | 1 mA 43/43 pass; 50 mA 0/43 (worst 10.46 dB) | 1 mA 42/42 pass; 50 mA 0/42 (worst 9.79 dB) | 50 mA, fs/−40 °C; supply 2.97 V (baseline) / 3.30 V (rev2) | as 2c; deltas −2.1…+0.03 dB (mean −0.4) | **inherited failure** (50 mA clause; DR-007) | #704 `tables/psrr_pair.csv`, `verdict.json` |
| 3a | Start-up over PVT (electrical: peak ≤ 1.836 V, floor ≥ 1.764 V, entry reached) | 540/540 pass; vpk ≤ 1.8246 V, floor ≥ 1.79836 V | 540/540 pass; vpk ≤ 1.82792 V, floor ≥ 1.80112 V | max peak: `ss_125c_2.97v/c4u7_0ma_esr0` (base), `fs_125c_3.63v/c4u7_0ma_esr500m` (rev2); min floor: `ss_125c_2.97v/c330n_50ma_esr0` (base), `ss_-40c_2.97v/c330n_50ma_esr0` (rev2) | 45 corners × 12 cold-enable legs per DUT | pass both; strict ramp monotonicity (0 V tol) fails **540/540 both** — **inherited failure** (historic 20261117-221657 pattern, µV drawdowns). Rev1's two non-regulating states (ss/125 °C/3.30 V clamp latch; ff/27 °C/2.97 V VOUT > VIN) are cleared by rev2's weaker tail; no latch, no `vout_above_vin`, no invalid retention on either DUT | #705 `tables/startup_pair.csv`, `README.md` |
| 3b | Line regulation (< 5 mV/V over 2.97–3.63 V, 1 mA & 50 mA) | 45/45 pass; worst 0.597 mV/V (1 mA), 0.370 mV/V (50 mA) | 45/45 pass; worst **3.211 mV/V** (1 mA), **3.164 mV/V** (50 mA) | `fs_125c_2.97v` (1 mA both, 50 mA rev2); `ff_125c_2.97v` (50 mA base) | 45 corners × 4 endpoints (all 14 checks) per DUT | inherited pass (`both-pass` all 45 corners, 0 regressions; noteworthy behavior change: worst 1 mA line slope increases ~5.4× on rev2, still `< 5 mV/V`) | `sim/startup/diagnostics/issue-705-20261122-013500/tables/line-regulation_pair.csv`, `verdict.json` |
| 3c | Load regulation (< 1 % / 18 mV, 0→50 mA) | 44/45 pass; **FAIL** at `fs_125c_3.63v` (19.944 mV / 1.108 %) | **45/45 pass**; worst **11.253 mV / 0.625 %** | `fs_125c_3.63v` (both) | 45 corners (0→50 mA, all 8 checks) per DUT | **candidate improvement** (44/45 `both-pass`, 1 improvement at `fs_125c_3.63v`: 19.944→11.253 mV, 0 regressions) | `sim/startup/diagnostics/issue-705-20261122-013500/tables/load-regulation_pair.csv`, `verdict.json` |
| 4 | MC output accuracy (mismatch, 200 draws) | 200/200 valid, 0 out-of-window; σ 8.318 mV (mean 1.80218 V) | 200/200 valid, 0 out-of-window; σ **6.657 mV** (mean 1.80432 V) | — | tt_mm/27 °C/3.30 V/1 mA, `vary=mismatch`, k_sigma 3, seed 20260817, same seed both legs | **candidate improvement** (σ −20 %) | #705 `README.md` (MC table), `verdict.json` |
| 5 | Iq re-measure at ff/125 °C/3.63 V (< 30 µA strict, DR-009 proposed) | 30.70 µA full load — **FAIL** (0.7 µA exceedance > 0.1 µA print quantum) | 29.999999999995 µA — harness PASS, margin ~5e-12 µA ≪ 0.1 µA print quantum | ff/125 °C/3.63 V, 50 mA | 45 corners per DUT, both load endpoints | **unresolved** at the named corner. Context: production fails 5 corners (3.63 V full load, ff/fs: 30.2–31.3 µA), rev2 passes 45/45 at harness grade — those 5 are a **candidate improvement** | #706 `tables/iq_pair.csv`, `sim/iq/records/20261121-042335-db9f161a-i706-paired.md` |
| 6 | Current limit (window TBD; never engages ≤ 50 mA; survives short at Vin_max) | 41/45 valid; v50 1.7978–1.7991 V; knee ≥ 74.6 mA; short 97.7–231.7 mA | 43/45 valid; v50 1.8007–1.8044 V; knee ≥ 71.8 mA; short 94.5–228.9 mA | knee −46.6 % at fs/−40 °C/3.30 V (137.98→73.688 mA); +84.1 % at sf/125 °C/2.97 V (95.54→175.861 mA) | 45 corner keys per DUT, forced-output DC + 2 ms held short incl. Vin_max | numeric clauses pass both (50 mA clause measured as regulated output at 50 mA on valid corners; actual engagement current and its margin **unresolved**); **introduced**: shift of the forced-VOUT = 1.75 V knee proxy −46.6…+84.1 % (falls at 18, rises at 21 of 39 valid pairs) and **2 rev2-only solver-invalid corners** (`ff_27c_3.30v` non-Vin_max, retained short 131.3 mA; `fs_-40c_3.63v` Vin_max, 102.8 mA — both outside the 160–195 mA family of production's 4 inherited Vin_max diagnostics) | #706 `tables/clamp_pair.csv`, `sim/current-limit/records/20261121-042335-db9f161a-i706-paired.md` |
| 7 | Thermal trip/reset re-bisection (150/135 °C nominal; binding bound = hysteresis sign) | trip 162.0–181.4 °C, reset 148.9–168.9 °C, hyst +12.5–13.4 °C | trip 161.7–181.4 °C, reset 148.9–168.9 °C, hyst +12.5–13.4 °C | identical worst-case behavior (highest fs_2.97V, lowest sf/ss_3.63V) | 15 corners × both crossings per DUT, 676 staircase points, tol 0.3125 °C | unchanged within one bisection step (absolute trip shift ≤ 0.3125 °C everywhere); nominal offsets and >125 °C model extrapolation are **inherited**; worker PDK stamp unverified (§1) | `sim/thermal/records/20261121-092243-db9f161a-i706-paired.md` |
| 8 | V-to-I spread disposition (I_R over PVT) | 1.73–2.48 µA (1.44x, BIASP-referenced) | 0.486–1.002 µA (**2.06x**, VREF-referenced) | rev2 peak sf/125 °C/3.63 V; production peak sf/27 °C/3.63 V | 45 corner keys, measured at the clamp legs' 50 mA point | **introduced** widening (2.06x vs 1.44x); tail, clamp threshold and Iq inherit it — the measured driver of row 6's knee spread | #692 `README.md` §5; #706 `tables/ir_spread.csv` |
| 9 | Re-base against #467 if it lands first | n/a — screen ran against the committed bias | n/a | n/a | #467 checked 2026-11-24: **open**, `loom:operator`, not landed | **no pair invalidated at review time**; see §4 | #706 `README.md` §"#467"; issue tracker |

Spot-check record (this review re-derived, not copied): row 1a's three regression legs
from `loop_pair.csv` (53.12→38.37, 53.12→38.37, 53.17→38.42) and worst rev2 PM 14.27°;
row 2a's rise/fall counts 9/18→9/18 and 2/18→8/18 (11/36→17/36 direction-legs) from
`loadstep_pair.csv` (`peak_rise_v` / `peak_fall_v` > 0.150 V); row 2c's
20.299→20.100 dB at fs/125 °C/2.97 V from `psrr_pair.csv`; row 3b's worst line slopes
(0.597→3.211 mV/V at 1 mA, 0.370→3.164 mV/V at 50 mA) from `line-regulation_pair.csv`;
row 3c's 19.944→11.253 mV load-reg improvement from `load-regulation_pair.csv` and
row 4's MC σ from #705's `verdict.json`; row 5's raw `-0.05003` A full-load supply
current (= 29.999999999995 µA after the 50 mA subtraction) from `iq_pair.csv`;
row 6's paired knees and row 8's I_R ranges from `clamp_pair.csv`/`ir_spread.csv`.

## 3. Compensation: C_COMP/R_CZ were not re-derived for rev2

The candidate preserves the committed compensation byte-identical in every pair of all
three campaigns: `C_COMP VOUT EA_CZ 150p`, `XR_CZ res_xhigh_po W=0.42 L=52` (the #691
shelf, sized in #36). The rev2 OTA's gm and pole placement differ from the production
amplifier (that is the #357 mechanism), so the shelf is un-retuned for the candidate —
the natural first suspect for the row-1a PM regressions and row-2a falling-step
failures, both worst at light load where the pass stage's load-dependent pole binds
(DR-006). Relative to the pinned baselines:

- **#349** (closed; PR #352) screened a load-adaptive compensation prototype at
  diagnostics level with verdict REVISE — it changed no production card; every pinned
  baseline above still carries the #36/#691 shelf. Its 0.33 µF·50 mA reference
  condition is the one #704 reproduces (both DUTs meet GM ≥ 10 dB at all three ESRs;
  45° PM only at 500 mΩ).
- **#709** (closed; PR #714) qualified R_CZ L=52 → L=180 and **rejected** it by
  loop-gain co-verification; the schematic keeps L=52 and compensation adoption stays
  open. No production card changed, so the campaigns' compensation-equality guarantee
  holds against current `main` as well.

Consequence for adoption: a compensation re-derivation for the rev2 OTA is outstanding
work, not a reason to disbelieve the measured rows above (both DUTs wore the identical
shelf in every pair, so the regressions are attributable to the OTA change itself).

## 4. #467 (bias re-topology) — invalidation status

#467 is open (`loom:operator`, `loom:very-important`) and **has not landed** as of
2026-11-24, so **no pair in this review is invalidated at review time**. Per #706's
reading, if it lands before a disposition, the bias-sensitive pairs must be repeated on
the new baseline: Iq and the I_R column of the clamp legs at minimum, and since clamp
trip and thermal sense are bias-derived too, the safest reading is to repeat all three
#706 benches. #702's own checklist adds that every #692 conclusion (hence the dropout
row) depends on the committed bias as well, so a landed #467 re-bases this entire
review, not just the #706 rows.

## 5. Recommendation

**Revise — do not adopt rev2 as-is; do not reject it either.**

Reasons:

1. **The headline holds everywhere**: rev2 closes the ratified dropout gap (#114) at
   all 45 PVT corners (binding 0.2202 V vs 300 mV) where production passes none
   (binding 0.6731 V). It resolves 4 of production's 5 full-load Iq failures at
   3.63 V (ff/−40 °C, ff/27 °C, fs/−40 °C, fs/27 °C); the fifth, ff/125 °C/3.63 V,
   stays unresolved (29.999999999995 µA, row 5). It also fixes the one
   load-regulation failure (`fs_125c_3.63v`, 19.944→11.253 mV, row 3c). Production's
   other measured failures (PM, recovery, PSRR) are inherited, not removed. There are
   no start-up,
   line-regulation (worst slope rises ~5.4× to 3.211 mV/V but stays `< 5 mV/V`,
   row 3b), thermal or MC regressions anywhere. Rejecting would discard a real,
   fully-covered improvement.
2. **But rev2 introduces dynamic regressions** that adoption would ratify as new
   failures: 3 new PM failures at 0 mA/4.7 µF (≈ −14.75° each) and 6 new falling
   load-step legs over 150 mV (fall failures 2/18→8/18, worst rising peak 215→242 mV; falling peak 155.3→172.7 mV). These sit on
   top of the inherited light-load stability/recovery gaps (DR-006/DR-007) but are
   attributable to the candidate, and the compensation was never re-derived for the
   new OTA (§3) — the obvious revision lever before any adopt decision.
3. **The clamp is not within noise of production**: the paired knee moves −46.6 % to
   +84.1 % across 39 valid pairs (row 6). That is the shift of the knee proxy (current
   sampled at forced VOUT = 1.75 V), not a measured engagement current. The
   VREF-referenced V-to-I's 2.06x spread (row 8) is the measured driver. The spec
   window is deliberately TBD, so no row fails, but adopting means accepting a
   substantially moved proxy — a conscious trade-off, not a formality. At 50 mA the
   output stays regulated on the valid corners (1.8007–1.8043 V rev2 vs
   1.7978–1.7991 V production). The actual engagement current and its margin above
   50 mA are unresolved: the 71.8 / 74.6 mA minimum proxy values do not establish
   them.
4. **Unresolved margins and missing results** (the complete list, each visible above):
   - ff/125 °C/3.63 V full-load Iq at-bound: 29.999999999995 µA against a 0.1 µA
     print quantum — harness PASS is a floating-point inequality, not margin (row 5).
   - The 3 PM regressions and 6 new falling load-step failures (rows 1a, 2a).
   - The 2 rev2-only solver-invalid clamp corners, one of them not Vin_max, with
     retained values outside the inherited family (row 6).
   - The knee-proxy shift −46.6…+84.1 % and unresolved engagement current (row 6) and the V-to-I 2.06x spread (row 8).
   - Coverage gaps, inherited unless noted: loop gain measured at tt/27 °C/3.30 V only
     (42 legs; 44 PVT corners unattempted); load-step at 3 `quick_subset` corners only;
     PSRR: 6 rev2 load measurements invalid = 3 distinct PVT corners, all rev2-only (baseline: 4 measurements = 2 corners, disjoint); MC at a single tt_mm condition; strict ramp
     monotonicity fails all 540 legs on both DUTs (zero-tolerance verdict, historic);
     thermal points extrapolate the pinned models beyond DR-004's 125 °C axis.
   - Provenance caveats: #706 executed on worker PDK `f6eeac7d…` (stamp mismatch,
     models_lib match); thermal worker stamp unverified; #705 dirty-tree legs carry
     only the file-hash guarantee (§1).
5. A revision cycle has a defined shape: re-derive C_COMP/R_CZ for the rev2 OTA and
   re-run the #704 dynamic pairs; re-measure the at-bound Iq corner at higher
   resolution; disposition the clamp spread (or ratify a window for it through
   `spec/`); clear the 2 rev2-only solver-invalid clamp corners. Adoption is then a
   re-review against this table's structure, not a fresh campaign.

The human may still defer (waiting on #467's bias re-topology is a coherent reason —
§4) or reject (if the clamp movement is unacceptable for the protected load). Neither
is argued against here; the evidence supports "worth revising, not yet adoptable".

## 6. Human disposition

Human disposition: **pending**

(To be filled by a human: adopt / revise / defer / reject, with rationale. Filing the
adoption issue is a separate step that follows an "adopt" disposition only.)

## 7. Provenance of this document

- Written for #763 (deliverable re-homed from parent #702, whose split children
  #704/#705/#706 are all closed). No simulation was run; every number above traces to
  a cited file on `origin/main` (worktree at `d0bee518`, 2026-11-24) and the raw-table
  spot-checks in §2 were re-derived during this review from the committed CSVs and
  records.
- Read-only references: `../issue-357/README.md` (source adoption checklist, section 8
  item 1), `spec/target-spec.md` (ratified comparison criteria; its "Current
  implementation status" columns are generated elsewhere and are not restated here).
- Out of scope, per #763: editing `design/ldo_3v3in_1v8out.sch`, `spec/`, thresholds or
  decision records; re-running or extending benches; re-deriving compensation or the
  bias network.
