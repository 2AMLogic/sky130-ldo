# DR-007: PSRR and Stability vs. the Iq budget — recommend superseding the DRAFT rows

- **Status**: proposed — not self-ratifying; input to #1
- **Date**: 2026-09-14
- **Author**: Builder agent (drafted per #70, operator-scoped 2026-09-14)
- **Ratifies against / input to**: #1 (Ratify the target spec — operator-only,
  the T1 gate), via the two-key market-comparison mechanism the operator's
  2026-09-14 comment on #70 names
- **Supersedes**: none — this record does not itself edit
  `spec/target-spec.md`; it recommends what a future ratification action
  should do with the PSRR and Stability rows

## Context

Issue #70 ("PSRR fails everywhere and light-load stability shortfall is
pervasive") was filed against `spec/target-spec.md`'s two DRAFT rows this
record concerns:

| Row | Current DRAFT text |
|---|---|
| PSRR | `> 50 dB @ 1 kHz and > 20 dB @ 100 kHz, at 1 mA (light-load, binding) and at 50 mA` |
| Stability | `stable 0–50 mA over the ratified C_out/ESR window; PM ≥ 45°, GM ≥ 10 dB worst corner` |

(`Iq (excl. load current) < 30 µA at no load and full load` is the third
DRAFT row this record's title names — not itself proposed for revision
here, but the resource both candidate fixes below had to spend against.)

**Both rows are confirmed failing on the current, shipped topology.**
`measurements/characterization.md` (as of `main` @ `4ba5531`) reads:

- PSRR: **FAIL**, 0/45 corners — [`sim/psrr-dc` record `20260825-082845-4cb27f8`](../../sim/psrr-dc/records/20260825-082845-4cb27f8.md).
  1 kHz PSRR ranges **20.31 dB** (`fs_125c_2.97v`, worst) to **25.68 dB**
  (`ss_-40c_3.63v`, best) across the full 45-point PVT grid — 24–30 dB short
  of the 50 dB floor everywhere. The **100 kHz sub-metric is not the
  problem**: it already clears the 20 dB floor with margin at every corner
  (31.53–34.77 dB).
- Stability: **FAIL**, 7/45 corners — [`sim/loop-gain` record `20260825-081257-4cb27f8`](../../sim/loop-gain/records/20260825-081257-4cb27f8.md).
  The shortfall is concentrated at the **0 mA** point: `pm_c033_0ma_deg`
  (phase margin at the DR-002 window's 0.33 µF corner) ranges **15.58°**
  (`tt_-40c_2.97v`, worst) up to 88.70° at 125 °C, where the pass-stage's
  own load-proportional pole (see below) is far enough up in frequency not
  to bind. Gain margin at 0 mA is **not** the problem — it measures
  68.85–72.30 dB everywhere, tens of dB above the 10 dB floor. The **50 mA
  sub-metric already clears 45°** at every corner (worst **45.91°**,
  `sf_-40c_3.63v`). The **1 mA sub-metric clears 45° at 40/45 corners**;
  the 5 misses are all at the `4.7 µF`/125 °C/2.97 V corner cluster and are
  near-misses, not collapses (**44.09–44.64°**, `pm_c47_1ma_deg`).

**Both prior decomposed attempts against this issue's own acceptance
criteria are complete, and both are verified-negative.** Per this repo's
"verification is the product" discipline, a well-verified negative result
is evidence, not a non-result:

1. **#70 / PR #82** (`design/README.md` §"Bias-generator redesign
   investigated, reverted (#70)"). Three candidates, each screened before
   any full corner re-run, per the issue's own acceptance criteria:
   - *Candidate 1*, a self-biased ("beta-multiplier") bias-generator
     reference replacing the plain `R_BIAS` chain — settled into a genuine,
     repeatable ~1 mA rail-clamped runaway branch on a real transient
     startup check (not a `.op` artifact), >30× the DRAFT Iq row, `VOUT`
     collapsed. A real missing-body-tie bug was found and fixed along the
     way, but did not fix the runaway.
   - *Candidate 2*, cascoding only the OTA's own PMOS pull-up mirror
     (`M_MIRP1`/`M_MIRP2`) — regulated correctly at all three DR-002 load
     points, but 1 kHz PSRR screening showed **no material improvement and
     a regression at one corner** (`ss_-40c_2.97v`: 17.6 dB vs. 23.6 dB
     baseline; `tt_27c_3.30v`: 23.2 dB vs. 23.3 dB baseline, unchanged).
   - *Candidate 3*, a light-load preload resistor — a promising
     crossover-frequency trend (283 Hz → 1647 Hz as Iq rose ≈13→31 µA) on a
     hand-rolled cold-`.op` deck, but not validated against the real 0 mA
     branch `sim/loop-gain`'s corner runner reaches (a real `--quick` run
     against the same schematic measured `pm_c033_0ma_deg` = 19.19°/15.64°
     at `tt`/`ss`, matching the documented baseline almost exactly — the
     hand-rolled deck's own number, ≈177°, was on a different DC branch).
2. **#79 / PR #88**, carrying both open threads to a definitive conclusion:
   - The self-biased reference was **root-caused and fixed** — hand-derived
     the loop's DC return ratio for both `R_SB` placements
     (`LG = 2 − √(m/K)` on the diode leg, structurally >1 for every `K>1`
     at the natural 1:1 mirror ratio Candidate 1 used, i.e. regenerative by
     construction, not a sizing bug; `LG = √(m/K) / (2√(m/K) − 1)` on the
     driven leg, <1 whenever mirror ratio `m` exceeds width ratio `K`) and
     verified the fix three independent ways in SPICE (`.dc` loop-break
     sweep — single crossing, slope 0.74; a settled `EN`-ramp transient; a
     15-point process×temperature `.op` spot-check, `I1` 1.46–3.56 µA, no
     runaway anywhere). **This fix does not move PSRR or 0 mA phase
     margin**: re-screened 1 kHz PSRR is unchanged/regressed
     (`tt_27c_3.30v` 23.5 dB vs. 23.3 dB baseline; `ss_-40c_2.97v` 22.3 dB
     vs. 23.6 dB baseline), and `pm_c033_0ma_deg` is statistically
     identical to baseline (`tt`=19.65° vs. 19.19°; `ss`=14.63° vs.
     15.64°) — confirming 1 kHz PSRR here is **loop-gain-limited, not
     supply-feedthrough-limited** (a standalone VIN-sensitivity check
     showed the reference's own current became 4 dB less VIN-sensitive,
     26.3%→16.1%, but `BIASP`'s *voltage* still tracks VIN at ~0.98 V/V in
     both designs, so the downstream mirror gate rail still passes most
     ripple through). Cost: **≈3.3 µA** against the ≈5 µA of Iq headroom
     the design has under the DRAFT 30 µA row, for no measured benefit —
     not shipped.
   - The preload resistor was **re-validated against the real
     `sim/loop-gain` `alter`-sequence deck** (which reaches 0 mA from the
     converged 50 mA point, not a cold `.op`). A 300 kΩ preload (≈6 µA)
     genuinely raises `pm_c033_0ma_deg` (+3.4° to +8.5°) — closing #70's
     own "not confirmed to be the same branch" caveat — but **regresses
     `pm_c47_0ma_deg` from a clean PASS to a worse FAIL than the corner it
     fixed** (52.03°→20.12° at `tt_27c_3.30v`; 38.06°→16.88° at
     `ss_-40c_2.97v`). A lighter 600 kΩ preload (≈3 µA) nets close to a
     wash on both ends. A single passive preload current cannot
     independently tune both ends of the DR-002 `C_eff` window — not
     shipped.

**The one lever that has ever moved 0 mA phase margin at all already
exceeds the Iq budget and still falls short.** Issue #25's own sizing
record (`design/README.md` §"Quiescent and shutdown current") screened a
6× `M_TAIL` widening: 0 mA phase margin kept improving up to **~40°** — but
Iq at 50 mA rose to **33.6 µA**, already **12% over** the DRAFT 30 µA row,
for a result still **5° short of the 45° floor**, and its effect on PSRR
was never measured. No tested lever — bias-generator side or amplifier-tail
side — has ever moved 1 kHz PSRR materially in either direction except
within measurement noise.

**Physical root cause, consistent across both attempts' diagnoses.** Per
`design/README.md`'s "Compensation (sized in #25)" section: in weak
inversion `gm_pass = I_load/(nV_T)`, so the pass stage's own output pole
falls in direct proportion to load current — ≈72 kHz at 50 mA/0.33 µF but
≈7 Hz at 0 mA, where the only load is the block's own ≈0.6 µA feedback
divider. No compensation network fixes a pole that moves with load current
without either raising `gm_pass` at light load (which is what a preload or
higher tail current does, at Iq cost, and which #70/#79 showed only
partially works and only for one end of the `C_eff` window) or raising the
amplifier's own DC gain (which raises loop gain — and hence 1 kHz PSRR —
but is bounded by the same 200 kHz-ish crossover the 50 mA corner already
sits near, meaning more DC gain alone, without a second gain stage or
cascode, runs into the same bandwidth wall).

**Market context (public datasheets, not reverse-engineered — clean-room
compliant per `CLAUDE.md`).** Two commercial CMOS LDOs in a comparable Iq
class each publish PSRR figures well above what this design's topology has
achieved at any tested Iq:

- **onsemi NCP170** (`NCP170/D`, Rev. 24, September 2022), 1.8 V option:
  `Iq` typ. **0.5 µA** (max 0.9 µA) at `IOUT` = 0 mA; PSRR **57 dB typ.** at
  1 kHz (`VIN` = 2.8 V + 200 mV pp modulation, `IOUT` = 150 mA — its rated
  max load, the harder-loaded end of its own PSRR test condition).
- **Microchip MCP1801** (`DS22051D`, 2010), 150 mA family with a 1.8 V
  option: `Iq` typ. **25 µA** (max 50 µA); PSRR **70 dB typ.** at 10 kHz
  (`IL` = 50 mA); its own PSRR-vs-frequency graph (`VR` = 3.3 V, `VIN` =
  4.3 V, `IOUT` = 100 µA) shows roughly 60–80 dB from 10 Hz through a few
  kHz, tapering toward ≈20 dB only near 1 MHz.

Both parts clear this design's 50 dB DRAFT target at Iq levels at or below
this design's own 30 µA budget — which means the 50 dB target is not
inherently physically unreasonable for this current/Iq class in general.
What it does show is that reaching it needs an amplifier/reference
architecture with materially more open-loop gain than a single-stage
current-mirror OTA with an un-cascoded bias generator — both commercial
parts' block diagrams show a dedicated error amplifier driven by a
separate, low-impedance reference, not the single shared bias-generator
node this design's PMOS pull-up and reference both currently draw from.
That is a topology-class difference, not a sky130-vs-other-process
physics difference, and a topology change is explicitly out of scope for
a decision record (and for the PR this record ships in) — CLAUDE.md's
no-invented-numbers discipline applies to unproven topologies as much as
to spec rows.

## Decision

**Recommend option (b): treat the two verified-negative decomposed
attempts (#70/PR #82, #79/PR #88) as evidence that the current DRAFT PSRR
and Stability rows are structurally unmeetable by the shipped topology
(the #25 single-stage current-mirror OTA plus its shared, un-cascoded bias
generator) within the current DRAFT Iq budget — not as an unexhausted
design space that a further "spend more Iq" decomposed attempt is likely
to close.** Two decomposed attempts, five candidates total, already spent
real engineering effort against exactly the acceptance criteria a third
attempt would repeat; the one candidate that ever moved phase margin at
all (6× `M_TAIL`) already exceeds the Iq budget by 12% and still misses the
target by 5°, with zero data on whether it helps PSRR at all; and the PSRR
shortfall itself has been independently root-caused twice (Candidate 2's
feedthrough-side fix, #79's supply-sensitivity-side fix) to be loop-gain-,
not feedthrough- or supply-sensitivity-, limited — a mechanism neither
tested lever ever targeted and that a bigger single-stage tail current is
not expected to close without also raising the amplifier's DC gain enough
to reopen the bandwidth/stability tradeoff #25's own compensation section
already fought to close.

Propose the following replacement rows as a **starting point for #1 and
the two-key market-comparison mechanism**, grounded in what this design's
shipped topology has actually measured — not a re-verified final claim
(no new `sim/` campaign was run for this record; per DR-002's own
precedent, that is a superseding/append record's job once a candidate
schematic exists):

| Row | Current DRAFT | Proposed replacement | Basis |
|---|---|---|---|
| PSRR @ 1 kHz | `> 50 dB` | `≥ 18 dB` | ≈2 dB below the worst measured corner (20.31 dB, `fs_125c_2.97v`), leaving a small margin rather than pinning the floor to the exact worst sample |
| PSRR @ 100 kHz | `> 20 dB` | `≥ 28 dB` | ≈3.5 dB below the worst measured corner (31.53 dB, `fs_-40c_3.63v`); this sub-metric was never the problem and the row should say so |
| Stability (PM/GM) | `PM ≥ 45°, GM ≥ 10 dB worst corner`, stated 0–50 mA | `PM ≥ 45°, GM ≥ 10 dB` for `I_load ≥ 1 mA`; **no PM/GM floor stated at 0 mA** (below the block's own ≈0.6 µA feedback-divider current, i.e. true no-load) | 50 mA sub-metric already clears 45° everywhere (worst 45.91°); 1 mA sub-metric clears at 40/45 corners with the 5 misses within 1° of the line (44.09–44.64°, `4.7 µF`/125 °C/2.97 V cluster); only the literal-0 mA point collapses structurally (worst 15.58°), for the load-proportional-pole reason above — a minimum-load condition is a stated, market-precedented way to scope a stability claim around a load-dependent compensation limit, not a loosening of the claim at any load this block is actually spec'd to serve |

**Iq (`< 30 µA`) is left untouched.** Neither verified-negative attempt
showed Iq itself to be the structurally binding row — the shipped
topology sits at 24.9 µA/50 mA, inside the row, and the one candidate that
did materially exceed it (6× `M_TAIL`) was never shipped precisely because
it didn't clear this row, not because the row itself is unreachable.

**This record expects the market-comparison mechanism may find the
proposed numbers non-competitive**, and states that plainly rather than
picking numbers to pass: NCP170 and MCP1801 both publish PSRR figures
20–50 dB above the ≥18 dB / ≥28 dB proposed here, at comparable-or-lower
Iq. That gap is real and, per the Context section's diagnosis, is a
topology-class gap this record's numbers do not paper over. If the
mechanism escalates on that basis, that is the protection the operator's
2026-09-14 comment names this mechanism for — not a defect in this
record's recommendation.

## Alternatives considered

- **Option (a): scope a third decomposed Builder attempt that spends
  amplifier Iq beyond the DRAFT 30 µA row.** This is the alternative the
  issue's own framing poses opposite this record's recommendation.
  Rejected, not merely deferred: the one existing Iq-spend data point (6×
  `M_TAIL`, 33.6 µA, ~40° PM, no PSRR data) already shows diminishing
  returns on the metric it was tested against while exceeding budget, and
  PSRR — the harder-failing of the two rows, 24–30 dB short everywhere —
  has never been shown to respond to any tested lever, Iq-costing or not.
  A third attempt in the same scoped class ("spend more Iq inside the
  current single-stage OTA/bias-generator topology") would very likely
  reproduce the pattern of the first two: a real, well-verified, negative
  result, at the cost of a third round of engineering effort against
  acceptance criteria that keep re-asking the same class of candidate to
  fix a mechanism (loop-gain-limited PSRR, load-proportional pass-stage
  pole) that class of candidate does not reach.
- **Do nothing — leave both rows DRAFT and unresolved indefinitely.**
  Rejected. This is the state #70 has been in since 2026-08-25 and is
  exactly what the operator's 2026-09-14 comment says to stop doing
  ("parking" via `loom:operator-only`/`loom:operator-decision` is removed
  for precisely this reason); it is also what `CLAUDE.md`'s "a row that
  proves unmeetable is superseded by a new decision record, never
  silently loosened" discipline argues against once two verified-negative
  attempts exist.
- **Propose a topology change (two-stage or cascoded-gain amplifier) as
  part of this record**, since the market comparables suggest that is the
  real fix. Rejected for this record. A circuit change is explicitly out
  of scope for the PR this record ships in (per the operator's 2026-09-14
  scoping comment), and proposing specific device sizings without a
  supporting `sim/` record would be inventing a claim this repo has no
  evidence for — the same discipline DR-002 followed when it named a
  compensation requirement without picking a topology to meet it. A
  topology redesign, if pursued, is a new, differently-shaped issue's
  job — not a further decomposition of #70's own lineage, which this
  record treats as closed by two verified-negative results.
- **Set the proposed replacement numbers to match the market comparables
  directly** (e.g., PSRR ≥ 57 dB @ 1 kHz to match NCP170) rather than to
  what this topology has measured. Rejected — this design has no verified
  path to that number with the shipped topology, and inventing an
  aspirational target the block cannot currently substantiate is the same
  no-invented-numbers violation CLAUDE.md prohibits for any other spec
  row. The honest number is what was measured, with the market gap
  recorded in Consequences, not hidden inside an optimistic floor.

## Consequences

- **If #1 ratifies this record's proposed rows**, `spec/target-spec.md`'s
  PSRR and Stability rows change to the table above (or to whatever the
  market-key/operator evaluation adjusts them to), and the DRAFT
  designation on those two rows can be resolved as part of #1's broader
  ratification pass rather than staying open indefinitely.
- **The two-key market-comparison mechanism the operator's 2026-09-14
  comment describes gets real, cited inputs to evaluate**: NCP170 (onsemi,
  `NCP170/D` Rev. 24) and MCP1801 (Microchip, `DS22051D`), both named with
  specific published Iq/PSRR figures above. This record expects that
  evaluation may find the proposed numbers uncompetitive and escalate to
  the operator — see Decision above.
- **Hands to design, unresolved**: a genuine fix for both rows most
  plausibly needs a higher-DC-gain amplifier architecture (two-stage or
  cascoded gain stage, per the Context section's diagnosis and the market
  comparables' own block diagrams) rather than further Iq spent inside the
  current single-stage current-mirror OTA. That is a new issue's scope,
  informed by this record and by #70/#79's data, not a further
  decomposition of #70 itself — this record treats #70's own acceptance
  criteria as answered (both candidate routes tried, both verified
  negative), not as still open.
- **`design/ldo_3v3in_1v8out.sch` is untouched by this record**, as
  instructed — no circuit or schematic change ships with this PR. The
  schematic remains exactly as #25 sized it and #70/#79 left it (all five
  screened candidates across both issues were reverted after failing
  screening).
- **The DRAFT `Iq < 30 µA` row is untouched** — this record does not
  propose relaxing it, and nothing in #70/#79's evidence shows it to be
  the binding constraint in its own right (see Decision).
- **This record does not itself re-verify the proposed numbers against a
  fresh 45-point campaign.** Per DR-002's own precedent for exactly this
  situation, the proposed floors are read directly off the existing
  `sim/psrr-dc` and `sim/loop-gain` records cited above; if a future
  topology change lands, that change's own `sim/` re-run is what
  substantiates (or supersedes) whatever numbers #1 ultimately ratifies —
  this record only proposes the starting point.

## Status notes

This record stays `proposed` until #1 rules on it, via the two-key
market-comparison mechanism the operator's 2026-09-14 comment on #70
establishes as the evaluation path for a relax-after-measured-FAIL
proposal like this one. If that mechanism finds the proposed numbers
non-competitive against the named public parts (NCP170, MCP1801) and
escalates to the operator, that is this record's anticipated outcome, not
a failure requiring this record to be rewritten — per the append-only
discipline `spec/decision-records/TEMPLATE.md` states, a record that turns
out to need different numbers is superseded by a new record, never
quietly edited. Implementation (any circuit/topology work informed by
this record's Consequences section) is explicitly deferred to a separate,
future issue — not part of this record or the PR it ships in.
