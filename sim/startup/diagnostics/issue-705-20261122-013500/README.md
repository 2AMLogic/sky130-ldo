# Issue #705 — rev2 qualification: start-up, line/load regulation, mismatch accuracy

Paired measurement of the production baseline DUT vs the #692 rev2 candidate
(`apply_candidate(raw, 2)`, the re-based #357 overlay with its REV[2] sizing)
on the four benches #702 needs beyond dropout: start-up, line regulation,
load regulation and mismatch-only MC output accuracy. A measured failure is a
valid qualification result; this is a measurement issue — no circuit change,
spec limit or record edit is made here.

Parent: #702 (adoption decision). Candidate source: #692 / PR #703, merged at
`7088aea6`. Out of scope per the issue: #704 (loop gain, load step, PSRR),
#706 (Iq, current limit, thermal, bias), #709 (R_CZ screen).

## DUT identity — one pinned production commit

Both DUTs of every pair below are netlisted from the same worktree state:

- **Pinned commit**: `1e328f6558ee68a1ea68ed78b14fd29487d79347` (`1e328f65`,
  "Merge pull request #722"), recorded per leg in each `runs/<leg>/leg.json`
  as `provenance.source_commit`. The recorded `provenance.git_state` is
  `dirty: true` on the six legs that carry it (`startup-*`, `line-*`,
  `load-*`; the worktree held this campaign's own untracked output files);
  the two MC legs and `runs/verify-overlay/verification.json` record no
  `git_state`. The guarantee that holds is narrower: the DUT schematic,
  testbench and `experiment.json` SHA-256s recorded in every leg equal
  those files' content at `1e328f65`.
- **Overlay**: `candidate.py` here is byte-identical (sha256
  `a08e93dce932ddd4…`) to the #692 campaign's
  `sim/dropout-vs-load/diagnostics/issue-692-20261120-235900/candidate.py`;
  rev 2 applied via `apply_candidate(raw, 2)` and verified with
  `check_candidate(raw, edited)` at leg-build time.
- **Invariant verification over every bench** (submits nothing):
  `runs/verify-overlay/verification.json` — all four benches clean
  (`invariant_problems: []`, 30 cards added per bench), hashes below.

| Bench | raw netlist sha256 (base = cand raw) | edited (rev2) sha256 |
|---|---|---|
| startup | `b268c1f922a13db5…` | `8ca608896a0efa7f…` |
| line-regulation | `682d7195f7b3…` | `d580a6bfc27f…` |
| load-regulation | `4fd7fceb56ae…` | `f37163446564…` |
| mc-output-accuracy | `01a12320fad9c94e…` | `69b1909f411ab776…` |

The base leg's raw hash equals the cand leg's raw hash on every bench (one
baseline, one edit), and the executed legs' hashes equal `verify-overlay`'s.

- **PDK**: sky130A @ open_pdks `c6d73a35f524070e…`, `matches_pin: true`
  against `sim/pdk.json` on every leg.
- **Tools** (every leg): ngspice-47, XSCHEM V3.4.7, Python 3.12.3,
  Linux x86_64; klt client 0.9.3.dev, batch runner klt 0.9.0 (compatibility
  `match`, probe `batch-preflight.py` ACCEPTED).
- **Solver settings**: each bench's own validated deck and measurement
  expressions, verbatim from its `experiment.json` / mc manifest — no
  stimulus, limit or `.spiceinit` change (netlists and diffs under
  `runs/<leg>/netlist.spice` and `runs/<leg>-cand/netlist.diff`).

## Commands

As executed: `commands.sh` (each multi-corner leg is one or more
`klt sim --backend batch` submissions with `batch.capacity_wait_s` set plus
the caller-side capacity wait; the only local work is netlisting and
grading). Reproduce any single leg with `python3 -B campaign.py <mode>` /
`python3 -B mc_pair.py <variant>` from this directory.

## Coverage and expected-vs-observed accounting

| Bench | Expected per DUT | Observed per DUT | Batch jobs per DUT |
|---|---|---|---|
| startup (45 corners × 12 cold-enable legs) | 540 conditions | 540 (both DUTs) | 36 |
| line-regulation (45 corners × 4 endpoints) | 45 corners | 45 (both DUTs) | 12 |
| load-regulation (45 corners × 2 endpoints) | 45 corners | 45 (both DUTs) | 6 |
| mc-output-accuracy (200 mismatch draws) | 200 draws | 200 returned / 200 valid (both DUTs) | 1 |

No missing trace, leg or draw. Tables: `tables/startup_pair.csv`,
`tables/line-regulation_pair.csv`, `tables/load-regulation_pair.csv`;
verdict machine-readably in `verdict.json`.

## Results

Classification: `both-pass` / `inherited-fail` (baseline fails, rev2 fails
the same way) / `improvement` / `regression` / `invalid` (no trustworthy
measurement on a side).

### Start-up — 540 conditions per DUT

- **Electrical axis** (peak ≤ 1.836 V, settled floor ≥ 1.764 V over 3.1–4 ms,
  window entry reached): **540/540 both-pass**. Extrema: base max vpk
  1.8246 V (ss_125c_2.97v, c4u7_0ma_esr0), cand max vpk 1.82792 V
  (fs_125c_3.63v, c4u7_0ma_esr500m); base min vfloor 1.79836 V, cand min
  vfloor 1.80112 V; max tramp 0.605 ms (base) / 0.629 ms (cand).
- **Strict ramp monotonicity (0 V tolerance)**: **540/540 inherited-fail** —
  every leg of both DUTs fails the zero-tolerance ramp verdict with
  microvolt-scale drawdowns (e.g. base 1.50e-5 V, cand 2.85e-5 V at
  ss_125c_3.30v/c330n_0ma_esr0). This is the historic pattern of
  `sim/startup/records/20261117-221657-efb6bd6b` (electrical passes, strict
  monotonicity failures on all 540 legs), unchanged by rev2 — an inherited
  failure, not a regression.
- **Named case ss/125 °C/3.30 V @ 50 mA** (cold start into 50 mA): electrical
  pass on all 6 legs of both DUTs; base vfloor_min 1.79848 V, cand
  1.80368 V; max drawdown ≤ 7.8e-6 V both.
- **Named case ff/27 °C/2.97 V @ no load**: electrical pass on all 6 legs of
  both DUTs; base vpk_max 1.81894 V, cand 1.81816 V.
- **Latch / VOUT above VIN / invalid solve retention classes**: none
  observed — `vout_above_vin` empty on both DUTs, 0 flagged corners in both
  `retention.json` records, no errored klt corner. Clean corners' rebuilt
  traces and waveform artifacts were dropped after grading (recorded by
  sha256; 540 transient rawfiles removed per DUT). Accounting note:
  startup-base's `retention.json` lists 120 of its 540 dropped rebuilt
  traces individually (its retention pass predates the final
  `apply_startup_retention`); startup-cand lists all 540. All 540
  per-corner measurements and ramp verdicts survive in both `leg.json`
  files either way.

### Line regulation — 45 corners per DUT, 2.97–3.63 V at 1 and 50 mA

- **All 14 checks × 45 corners both-pass** (slopes and endpoint averages /
  tails inside 1.764–1.836 V). 0 regressions, 0 inherited failures.
- Worst line slope: base 0.597 mV/V (line_reg_1ma, fs_125c_2.97v) —
  the candidate's worst is higher, 3.211 mV/V (1 mA, fs_125c_2.97v) and
  3.164 mV/V (50 mA, fs_125c_2.97v), still inside the < 5 mV/V row. Worst
  endpoint 1.8074 V (cand, 1 mA hi, fs_125c_2.97v) vs base 1.8013 V.
- Supply-axis identity check (this bench's `vsup` is a pure label post-#196):
  columns expected identical — confirmed identical.

### Load regulation — 45 corners per DUT, 0→50 mA

- **44/45 corners both-pass; 1 improvement, 0 regressions.**
- **Improvement** at `fs_125c_3.63v`: baseline FAILS the ratified row —
  load delta **19.944 mV / 1.108 %** vs the < 18 mV / < 1 % limit — while
  rev2 passes at **11.253 mV / 0.625 %**. This is the only electrical
  failure anywhere in the baseline pair, and rev2 removes it.
- Worst candidate load delta 11.253 mV (`fs_125c_3.63v`), vs baseline worst
  19.944 mV. Endpoints stay inside the output window on both DUTs.

### Mismatch accuracy — `sim/mc-output-accuracy`, 200 draws per DUT

Same sample configuration on both DUTs: tt_mm / 27 °C / 3.30 V / 1 mA,
`vary=mismatch`, `k_sigma=3`, base seed **20260817**, `uic` disabled-state
start with EN rising at 100 µs.

| DUT | attempted | returned | valid | out-of-window (1.764–1.836 V incl.) | errored/missing |
|---|---|---|---|---|---|
| base | 200 | 200 | 200 | 0 | 0 |
| rev2 | 200 | 200 | 200 | 0 | 0 |

Stats: base mean 1.80218 V, σ 8.318 mV, range 1.77888–1.82778 V; rev2 mean
1.80432 V, σ 6.657 mV, range 1.78571–1.82534 V. Same seed on both legs
(`same_seed: true`), klt status `pass` on both. No sample IDs to list — no
violations and no failed solves.

## Baseline spot-checks against published records

Nominal tt/27 °C baseline values reproduce the published records exactly:

- startup `tt_27c_3.30v` vpk 1.81257 V (0 mA legs) / 1.79883 V (50 mA legs)
  — matches `sim/startup/records/20261117-221657-efb6bd6b`.
- line `tt_27c` slopes 0.31515 / 0.29697 mV/V — match
  `sim/line-regulation/records/20260926-200304-35b7392`.
- load `tt_27c_3.30v` delta 3.553 mV / 0.197389 % — matches
  `sim/load-regulation/records/20260926-010432-228fbc7`.
- MC base mean 1.80218 V / σ 8.3175 mV (n=200) — matches
  `sim/mc-output-accuracy/records/20261112-110113-820ba8b3` to six digits.

## Verdict for #702

- **Regressions: none.** No check, corner, leg or draw passes on the
  baseline and fails on rev2 — `electrical_regressions`,
  `ramp_regressions`, and both regulation benches' `regressions` lists are
  empty; MC has zero new violations.
- **Improvement: one.** The baseline's single electrical failure (load
  delta 19.944 mV / 1.108 % at fs/125 °C/3.63 V) becomes a pass on rev2
  (11.253 mV / 0.625 %). MC spread also tightens (σ 8.32 → 6.66 mV).
- **Inherited failures: one family.** The zero-tolerance strict ramp
  monotonicity verdict fails all 540 start-up legs on both DUTs exactly as
  in the historic 20261117 record — pre-existing, unchanged by rev2, owned
  by the start-up bench's monotonicity question, not by the DUT pair.
- **Unresolved points: none.** Every expected condition was measured and
  graded on both DUTs; no missing traces, draws or solves.

Net: at the pinned commit the rev2 overlay qualifies on all four benches for
#702's Startup / Line regulation / Load regulation / Output rows — with the
historic strict-monotonicity caveat carried unchanged, and one real
improvement over the production baseline.

## Evidence map

- `runs/verify-overlay/verification.json` — overlay invariants, all benches
- `runs/{startup,line,load}-{base,cand}/leg.json` — per-corner measurements,
  ramp verdicts, batch execution (job ids), full provenance
- `runs/{startup,line,load}-{base,cand}/netlist.spice` (+ `netlist.diff` on
  cand legs) — exact DUT netlists
- `runs/{startup,line,load}-{base,cand}/klt-out/` — batch responses,
  receipts, per-corner ngspice logs (committed evidence, #692 precedent)
- `runs/mc-{base,cand}/` — MC request/response and per-sample analysis
- **Base-leg netlists live in the artifact store, not here.** The base DUT
  netlists are byte-identical to already-published objects, so they are not
  re-committed (`scripts/check_artifact_manifests.py`: bytes live in the store
  only). Read them at:
  - `runs/startup-base/klt-requests/<case>.spice` →
    `sim/startup/klt-request-netlists/20261117-221657-efb6bd6b.<case>.spice`
    (manifest `startup-20261117-221657-efb6bd6b.manifest.json`); the sibling
    `<case>.json` requests stay here unmodified (append-only evidence); their
    recorded `netlist` path is the original run-time location of that file.
  - `runs/mc-base/netlist.spice` →
    `sim/mc-output-accuracy/netlist-snapshots/20261112-110113-820ba8b3.spice`
    (manifest `mc-output-accuracy-20261112-110113-820ba8b3.manifest.json`).
- `tables/*.csv` — paired per-condition values and classifications
- `verdict.json` — machine-readable verdict for #702
