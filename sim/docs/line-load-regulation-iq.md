## Line regulation, load regulation and Iq (issue #64)

Three more testbenches against the same DUT (`design/ldo_3v3in_1v8out.sch`),
covering three spec rows `measurements/characterization.md` reported N/A
until this issue: **Line regulation** (<5 mV/V over 2.97–3.63 V, at 1 mA and
50 mA), **Load regulation (0–50 mA)** (<1%/18 mV) and **Iq (excl. load
current)** (<30 µA at no load and full load). The first two rows are ratified
(issue #1 / DR-006); the Iq row is the one DR-006 left open and is set by
`DR-009`, still `proposed` — `sim/iq/experiment.json`'s `claim` says so, and
cites DR-009's number rather than a ratified one. Same VIN/EN/VREF stimulus
convention and output network (1 µF `C_OUT`/10 mΩ `R_ESR`) as the four
testbenches above.

**All three use discrete `.op` points at each row's own named test
conditions, not a continuous `.dc` sweep** — a deliberate choice, not the
original plan. A continuous `dc vvin 2.97 3.63 ...` sweep (for line
regulation) and a continuous `dc iload 0 50m ...` sweep (for load regulation)
were both tried first and both hit this schematic's already-documented
DC-solution-multiplicity behavior (the "six degenerate corners" section
above, and design/README.md's dated 2026-08-25 root-cause section, issue #60
mechanism 4, tracked by #71): the VIN sweep repeatedly hit
gmin-stepping/singular-matrix non-convergence and did not complete in
minutes of wall-clock time per corner, and the `I_LOAD` sweep measured a
1.46 V peak-to-peak `vout` excursion at `tt`/27 °C — a solver-continuation
artifact, not a real 81%-of-target load regulation number (design/README.md's
own screening data puts the same two endpoints ~4 mV apart). Four (line
regulation: VIN × I_LOAD) or two (load regulation: I_LOAD only) independent
`.op` solves at each row's own endpoints — `alter`-ing VIN and/or the
load current source between them, mirroring `loop-gain`'s and `iq`'s
multi-point convention — complete in well under a second each and reproduce
`design/README.md`'s own screening numbers for the same points (its "DC
operating grid" and "Quiescent and shutdown current" sections both already
use discrete points, not a sweep, for exactly this reason).

- **`line-regulation/`** — VIN ∈ {2.97 V, 3.63 V} × `I_LOAD` ∈ {1 mA, 50 mA},
  four `.op` solves; `line_reg_<n>ma_mv_per_v` = `abs(1000*(vout_hi-vout_lo)/
  0.66)`. First record (`--quick`, 3-corner subset, `20260825-040532-6fac47d`):
  **PASS** at `tt_27c_3.30v` (0.295/0.378 mV/V) and `ss_-40c_2.97v`
  (0.217/0.369 mV/V), **FAIL** at `ff_125c_3.63v` (1005.8/1010.2 mV/V, three
  orders of magnitude over the 5 mV/V bound) — overall `FAIL`. The
  `ff_125c_3.63v` failure is the same degenerate-corner signature described
  above (thermal-shutdown false-trip, #69), not a new finding. #95 re-ran the
  same subset against #69/#90's re-sized DUT (`20260825-104914-933dfdd`,
  supersedes the record above): **1/3 PASS** — `tt_27c_3.30v`
  (1739/1317 mV/V) and `ss_-40c_2.97v`'s 50 mA leg (2477 mV/V) newly fail,
  `ff_125c_3.63v` now passes cleanly (0.500/0.422 mV/V) — see "`line-regulation`'s
  failing corner moved" above. **Full 45-point PVT record**
  (`20260910-030557-6c0436d`, issue #104, supersedes `20260825-104914-933dfdd`):
  **18/45 PASS**. Of the 27 failing corners, 25 show the same
  DC-solution-multiplicity signature described above — values ≥100 mV/V, up
  to 26186 mV/V at `fs_125c_2.97v`, three to four orders of magnitude over
  the 5 mV/V bound — while 2 are modest, physically plausible overshoots
  close to the bound rather than solver excursions: `tt_125c_2.97v`
  (32.5/50.5 mV/V) and `sf_125c_2.97v` (7.1/10.9 mV/V). The two corners the
  #95 subset flagged as "newly failing" both land in the multiplicity
  bucket here (`tt_27c_3.30v` 1739/1317 mV/V, `ss_-40c_2.97v`
  0.217/2477 mV/V), and `ff_125c_3.63v` again passes cleanly
  (0.500/0.422 mV/V), confirming rather than changing the subset's own
  result. As the #95 section above already notes, diagnosing why this
  signature lands on a different, wider corner set than the pre-#69 six
  degenerate `ff`/`sf`-125 °C corners is explicitly out of this issue's
  scope — recorded here as an observation, not root-caused.
  **Current record** (`20260925-114251-1f54ca6`, issue #118, supersedes
  `20260910-030557-6c0436d`, first run against the post-#116 5000 µm pass
  device): **24/45 PASS**, up from 18/45. #118 also root-caused the signature
  the paragraph above declined to: **this bench's `supply_v` corner axis is a
  negative control.** The testbench wires VIN to a fixed literal
  (`VVIN VIN 0 3.3`) and only EN to `'vsup'`, and the deck `alter`s VIN to
  2.97 V/3.63 V at all four measured points — so the corner's own supply
  cannot reach the measurement, and the three supply points inside one
  (process, temperature) group must return the same number. **22 of 30
  (group × measurement) cells vary by more than 2× across it, 21 of them by
  more than 10×**, while the one fully self-consistent group (`ff_-40c`)
  agrees to four significant figures. On the regulating branch the row is
  **0.017–1.62 mV/V** at 1 mA and **0.093–3.14 mV/V** at 50 mA against the
  5 mV/V bound; the five intermediate readings (6.7–85.2 mV/V) all sit at
  `*_125c_2.97v`. Read this bench's per-corner verdicts as branch-selection
  outcomes, not as supply-rejection measurements — see `design/README.md`
  → "#118: the three DC-accuracy rows do share one mechanism…".
  **Current record** (`20260926-001833-228fbc7`, issue #172, supersedes
  `20260925-114251-1f54ca6`, first run under the #171 initial-condition
  contract): **40/45 PASS**, up from 24/45, with **zero solver diagnostics on
  all 45 corners** (the superseded record carried one on all 45). Sixteen
  corners changed verdict, all FAIL → PASS, and every one of them read a gross
  branch-selection number in the superseded record (1042–2785 mV/V) that now
  reads 0.109–0.705 mV/V. The five survivors are all `*_125c_2.97v`, i.e. the
  same bucket #118 called "intermediate". See "…re-run under the #171 contract
  (issue #172)" below.
  **Record note (#196): this record is the last one taken under the old
  `EN`-at-`'vsup'` convention, and all five of its survivors are that
  convention's artifact** — the `VIN = 3.63 V` point of every `*_2.97v` corner
  ran with `EN` 0.66 V below VIN. Its numbers are evidence about the
  **pre-#196 deck only**; of its three supply columns only `*_3.63v` is
  unaffected by the convention (see "#196" above).
  **Current record** (`20260926-200304-35b7392`, issue #196 second increment
  / #200, supersedes `20260926-001833-228fbc7`, first run with `EN` at the
  instantaneous VIN): **45/45 PASS — the row's first overall PASS**, up from
  40/45, zero solver diagnostics and zero timeouts. `line_reg_1ma` spans
  0.216667–0.595454 mV/V and `line_reg_50ma` 0.271212–0.368182 mV/V against the
  5 mV/V bound. The five corners that changed verdict are exactly the
  `*_125c_2.97v` column; the `*_3.63v` column, which ran in contract under both
  conventions, is reproduced to within 0.0061 mV/V at all 30 of its cells, and
  the three supply columns of every (process, temperature) group now agree to
  0.000000 mV/V — `#118`'s negative control, finally negative. See "#196"
  above for the full diff and the runtime accounting.
- **`load-regulation/`** — `I_LOAD` ∈ {0 mA, 50 mA} at each corner's own VIN
  (`'vsup'`), two `.op` solves; `load_reg_v` = `abs(vout@50mA - vout@0mA)`.
  First record (`--quick`, `20260825-040748-6fac47d`): **PASS** at
  `tt_27c_3.30v` (4.2 mV / 0.23%) and `ss_-40c_2.97v` (3.3 mV / 0.18%),
  **FAIL** at `ff_125c_3.63v` (19.3 V) — overall `FAIL`, same degenerate
  corner. #95 re-ran the same subset against the re-sized DUT
  (`20260825-105113-933dfdd`, supersedes the record above): **3/3 PASS** —
  `ff_125c_3.63v` now regulates cleanly too. **Full 45-point PVT record**
  (`20260910-032854-6c0436d`, issue #104, supersedes `20260825-105113-933dfdd`):
  **34/45 PASS**. The 11 failing corners (`tt_27c_2.97v`, `tt_125c_3.63v`,
  `ss_-40c_3.30v`, `ss_27c_2.97v`, `ss_27c_3.30v`, `ff_-40c_2.97v`,
  `sf_-40c_3.63v`, `sf_27c_3.30v`, `sf_27c_3.63v`, `fs_-40c_3.63v`,
  `fs_27c_2.97v`) read `load_reg_v` of 0.31–1.62 V (17–90%) against the
  18 mV/1% bound — an order of magnitude smaller than line-regulation's
  multiplicity signature but still far outside plausible load-regulation
  behaviour, and none of them are the pre-#69 `ff`/`sf`-125 °C corners
  (those all pass here). This reads as the same family of non-regulating
  operating points the DC-solution-multiplicity note documents, but that is
  an observation, not a root cause — diagnosing it is out of this issue's
  scope.
  **Current record** (`20260925-111601-7701e7e`, issue #118, supersedes
  `20260910-032854-6c0436d`, first run against the post-#116 5000 µm pass
  device): **37/45 PASS**, up from 34/45 — and the distribution now separates
  into three groups, not two. **37 corners read 2.62–14.50 mV** against the
  18 mV bound; **7 read 881 mV–1.62 V**, with a **44× empty band** between
  19.93 mV and 881 mV that no continuum mechanism produces; and **one corner,
  `fs_125c_3.63v`, reads 19.93 mV (1.107 %)** — a marginal 11 % overshoot
  whose own group is monotone in VIN (10.99 / 14.50 / 19.93 mV). That single
  corner is the only genuine load-regulation shortfall in the matrix. Of the
  five (process, temperature) groups containing a gross failure, **four are
  non-monotonic in VIN** (a higher-headroom supply fails while a lower one
  passes), which a loop-gain-bound DC error cannot be. #118 attributes the
  seven gross failures to the non-regulating-branch family rather than to
  loop gain — see `design/README.md` → "#118: the three DC-accuracy rows do
  share one mechanism…".
  **Current record** (`20260926-010432-228fbc7`, issue #172, supersedes
  `20260925-111601-7701e7e`, first run under the #171 initial-condition
  contract): **44/45 PASS**, up from 37/45, with **zero solver diagnostics on
  all 45 corners** (the superseded record carried one on 44 of 45). Exactly
  the seven gross-failure corners changed verdict, all FAIL → PASS, and the
  44× empty band is gone: the 44 passing corners are a continuum from
  **2.62 mV to 14.50 mV** against the 18 mV bound. **The single survivor is
  `fs_125c_3.63v` at 19.94 mV (1.108 %)** — the same corner, to within
  0.01 mV of the same number, #118 had already isolated as "the only genuine
  DC-accuracy gap the three rows contain". #118's decomposition is confirmed
  here by an instrument that shares none of its seeding. See "…re-run under
  the #171 contract (issue #172)" below.
- **`iq/`** — `I_LOAD` ∈ {0 mA (no load), 50 mA (full load)} at each corner's
  own VIN, two `.op` solves; `iq_<point>_ua` = `-i(vvin)` minus the known
  load-current constant, per `design/README.md`'s own "Iq = total VIN
  current minus load current" convention. First record (`--quick`,
  `20260825-040934-6fac47d`): **PASS at all three corners**
  (13.3/25.5 µA at `tt_27c_3.30v`, 11.4/22.3 µA at `ss_-40c_2.97v`,
  14.7/8.8 µA at `ff_125c_3.63v`) — overall `PASS`. The `ff_125c_3.63v`
  point is the same degenerate corner as above (confirmed directly: `TS_CMP`
  = 0.39 V, tripped; `vout` collapses to 0.14 V at no load and −19.2 V at
  full load), but unlike line/load regulation the raw `-i(vvin)` figure there
  still happens to land inside the 30 µA budget rather than reading as an
  obviously non-physical number — so this testbench also records
  `vout_no_load_v`/`vout_full_load_v` (unbounded) alongside the Iq figures,
  specifically so a reader can see that corner's operating point is not
  really regulating before trusting its in-budget Iq "PASS", the same
  caution the PSRR "passes" above already need. #95 re-ran the same subset
  against the re-sized DUT (`20260825-105157-933dfdd`, supersedes the record
  above): **3/3 PASS** — same three corners, all now genuinely regulating
  (`vout_no_load_v`/`vout_full_load_v` both ≈1.80 V at all three). **Full
  45-point PVT record** (`20260910-034648-6c0436d`, issue #104, supersedes
  `20260825-105157-933dfdd`): **36/45 PASS**. The 9 failing corners
  (`tt_27c_2.97v`, `tt_125c_3.63v`, `ss_27c_2.97v`, `ss_27c_3.30v`,
  `sf_-40c_3.63v`, `sf_27c_3.30v`, `sf_27c_3.63v`, `fs_-40c_3.63v`,
  `fs_27c_2.97v`) all fail on the full-load leg, with `vout_full_load_v`
  reading 2.67–3.43 V instead of ≈1.80 V (one, `sf_27c_3.30v`, also fails its
  no-load leg at `vout_no_load_v` = 3.32 V) — the same "operating point
  isn't really regulating" signature this testbench's own unbounded
  `vout_*` sanity measurements exist to catch, now visible at 9 of 45 points
  instead of the one degenerate corner the quick subset ever reached.
  `iq_full_load_ua` at those 9 corners reads 3454–3582 µA against the 30 µA
  bound — obviously non-physical, not a genuine Iq measurement. None of the
  9 are the pre-#69 `ff`/`sf`-125 °C corners (all pass here); root-causing
  which corners this lands on is out of this issue's scope, same as
  line/load regulation above. **The 36/45 tally is not 36 genuine passes**:
  two corners marked PASS — `ss_-40c_3.30v` (`vout_no_load_v` = 3.31 V,
  `iq_no_load_ua` = −3348.6 µA) and `ff_-40c_2.97v` (`vout_full_load_v` =
  2.71 V, `iq_full_load_ua` = −3357.9 µA) — show the same non-regulating
  collapse signature as the 9 above with the sign flipped, and pass only
  because this bench's `iq_*_ua` measurements are bounded one-sided
  (`max: 30`, `min: null`) rather than `abs()`-wrapped the way
  line-regulation's and load-regulation's are, so a large negative excursion
  slips under the ceiling instead of tripping it. Both are independently
  confirmed genuinely non-regulating by this same issue's `load-regulation`
  record, where they are 2 of its 11 real FAILs (`load_reg_v` = 1.51 V and
  0.91 V) — so at most 34 of 45 corners here have a plausible regulating
  operating point, matching load-regulation's own 34/45. (A third corner,
  `sf_27c_3.30v`, reads the same negative no-load figure, −3350.0 µA, but is
  already counted among the 9 FAILs via its full-load leg.) The record and
  its raw data are correct as recorded and are left as-run — re-bounding the
  Iq measurement, re-classifying the tally, and root-causing the collapse are
  all out of this issue's scope; this note exists so the headline count is
  not read as 36 clean corners.

**Quick-subset first, by design, matching issue #18's own original
precedent** for newly-shipped testbenches (`load-transient`/`psrr-dc`/
`dropout-vs-load` also shipped `--quick`-only before #19's later full
45-point pass). Issue #104 then ran the full 45-point matrix each manifest
declares for all three, mirroring issue #74's extension of the #65
protection benches — see each bullet's "Full 45-point PVT record" above for
the per-bench tallies.

### Line regulation and load regulation re-run under the #171 contract (issue #172)

Both regulation benches' `alter`+`op` chains were the worst case of the
unconstrained-`.op` defect `#164` characterized: no transient, no `uic`, no
`.ic`, so **every** measured point was read straight off ngspice's own
from-nowhere Newton solve. `#172` converted both to the
"Initial-condition contract" above and re-ran both full 45-corner matrices
under `#171`'s new solver-diagnostic FAIL gate.

**Which contract shape, and why.** Both benches now use the contract's
**`uic` + EN edge** shape (`tran 10u 200m uic`, each bench's `VEN` changed
from a constant `'vsup'` to `dc 0 pwl(0 0 100u 0 101u 'vsup' 10 'vsup')`,
`v(vout)` averaged over the settled 199–200 ms tail), one transient per
measured point, exactly as PR #170 landed for `sim/mc-output-accuracy`. The
`alter` chain itself is unchanged — the points, the bounds and the
`abs(1000*Δv/0.66)` / `abs(Δv)` expressions are the same as before; only the
`opN.` plot prefixes become `tranN.`. The contract's *other* shape (an
`.ic`-seeded `.op`) was tried first and **cannot be expressed in ngspice for
this deck**, measured rather than assumed:

- `.ic` is applied only to the operating-point solve that *precedes* a
  non-`uic` transient (ngspice's MODETRANOP solve). A bare `op` command
  ignores it entirely.
- `.nodeset` *is* honoured by a bare `op`, but only as a first-iterations
  guess that is then released. With `sim/ic-screen-125c-b`'s full 11-node
  intended-branch node set applied as a `.nodeset` to the old `.op` chains,
  3 of 5 corners probed (`tt_27c_3.30v`, `fs_125c_3.63v`, `ss_-40c_2.97v`)
  still printed `singular matrix` *and* `Dynamic gmin stepping failed` — the
  exact markers `#171`'s gate fails on.

So a settled transient per point is the only shape that satisfies the
contract here. An `.ic`-seeded **non-`uic`** transient (the third possibility)
does work and was run as a cross-check — see "not steering the answer" below.

**Why the transient is 200 ms, and why that is `load-regulation`'s number
rather than a round one.** At the ratified load-regulation row's **0 mA**
endpoint the feedback divider is the only discharge path out of the 1 µF
`C_OUT`, so any start state above the no-load operating point bleeds down
through a high-impedance path. **Corrected by issue #184** (surfaced during
review of PR #182; the original numbers below do not reproduce on the deck
that shipped): the `uic` cold-start deck that actually ships here measures,
at `tt/27C/3.30V`, `v(vout)` = **1.81337 V** averaged over 0.8–1 ms, already
settled to **1.80239 V** by ~50 ms (flat to six digits from there through
200/300/400 ms) — an **11.0 mV** 1 ms-window artifact against the 18 mV
bound, i.e. a PASS, not a FAIL. The **1.85985 V / 1.83245 V / 1.80332 V**
trajectory and the "57 mV, 3× the bound, would fail all 45 corners"
conclusion this section originally stated were measured on the
`.ic`/`op`-seeded, non-`uic` cross-check variant tried first (see the table
below), not on this deck. 200 ms is nonetheless still the right window: that
seeded cross-check variant genuinely needs the long window to settle, and
every corner probed keeps margin under 200 ms even at the shipped deck's own
largest observed 1 ms-window artifact (1.75 mV at `fs_125c_3.63v`). The
50 mA endpoint, by contrast, settles inside 1 ms at every corner probed.
`line-regulation`'s four points all carry a real load current (1 mA or
50 mA) and likewise settle inside 1 ms — its 0.8–1 ms and 199–200 ms tail
averages agree to six digits at `tt/27C/3.30V` — but it carries the same
200 ms window anyway, so both benches share one convention.

**Errata (issue #184).** The `20260926-010432-228fbc7` (`load-regulation`)
and `20260926-001833-228fbc7` (`line-regulation`) records below, and this
section's prose as originally landed by #172, carried the uncorrected
1.85985 V / 1.83245 V / 1.80332 V / "57 mV, 3× the bound" trajectory above,
plus a "≤0.1 mV" figure for the three hottest corners' 99–100 ms vs.
199–200 ms tail-average agreement that is actually **0.13 mV** (worst case,
`fs_125c_3.63v`: 1.81869 V vs. 1.81856 V). Both records are append-only and
are not re-cut for a prose correction — no measurement, corner verdict, or
row verdict in either record is affected; see issue #184 for the full
before/after and how the corrected numbers were reproduced.

**Measured evidence the start state is not steering the answer** (the
property the contract is actually after — two independent start states
converging on one tail):

| Probe | `.ic`-seeded, non-`uic` | `uic` + EN edge | Agreement |
|---|---|---|---|
| `line-regulation`, `tt_27c_3.30v`, all four points | 1.80050 / 1.80071 / 1.79872 / 1.79892 V | identical to six digits | exact |
| `line-regulation`, `tt_125c_2.97v` | 31.2 / 43.9 mV/V | 31.2 / 43.9 mV/V | exact |
| `load-regulation` 0 mA, `tt_27c_3.30V` | 1.80239 V (400 ms) | 1.80239 V (200 ms) | exact |
| `load-regulation` 0 mA, `ff_125c_3.63V` | 1.81042 V (400 ms) | 1.81042 V (200 ms) | exact |
| `load-regulation` 0 mA, `fs_125c_3.63V` | 1.81860 V (400 ms) | 1.81856 V (200 ms) | 0.04 mV |

**Result — both matrices, re-run and re-graded under `#171`'s gate.**

| Bench | Superseded record | Corners with a solver diagnostic | New record | Corners with a solver diagnostic | PASS |
|---|---|---|---|---|---|
| `line-regulation` | `20260925-114251-1f54ca6` | 45 / 45 | `20260926-001833-228fbc7` | **0 / 45** | 24/45 → **40/45** |
| `load-regulation` | `20260925-111601-7701e7e` | 44 / 45 | `20260926-010432-228fbc7` | **0 / 45** | 37/45 → **44/45** |

Zero corners in either matrix trip the new gate. Both rows' **overall verdict
is still FAIL** against the ratified spec row, so
`measurements/characterization.md`'s row-level verdicts do not move (only the
cited record ids and the per-row corner tallies) — the conversion removed
non-circuit artifacts, it did not make either row pass.

**Per-corner verdict changes — this is `#118`'s open question, answered.**
`#118` concluded both matrices' corner verdicts were branch-selection
outcomes rather than regulation quality, and left open whether excluding
those branches would change the verdicts. It does, and in exactly the
direction `#118` predicted:

- **`line-regulation`: 16 corners changed, all FAIL → PASS.** Every one of
  them read a gross branch-selection number in the superseded record
  (1042–2785 mV/V) and now reads **0.109–0.705 mV/V** against the 5 mV/V
  bound. Nothing regressed. The 40 passing corners span 0.017–1.62 mV/V
  at 1 mA and 0.092–3.14 mV/V at 50 mA.
- **`line-regulation`'s five survivors are all `*_125c_2.97v`** — the same
  five cells `#118` had already separated out as the "intermediate readings"
  bucket (6.7–85.2 mV/V), and they reproduce: 6.7 / 13.1 / 31.2 / 85.2 mV/V
  at 1 mA for `sf` / `ss` / `tt` / `ff`, plus `fs_125c_2.97v`. Their
  mechanism is visible in the logs: at 125 °C the VIN = 2.97 V point
  regulates (1.8008 V) while the VIN = 3.63 V point droops (1.780 V at `tt`,
  1.745 V at `ff`) or, at `fs_125c_2.97v`, diverges outright to a
  **negative** `v(vout)` (−6.71 V at 1 mA, −14.06 V at 50 mA). Note what
  that `fs` corner means for the gate: a transient that diverges to a
  non-physical state is simulated without any solver complaint, so `#171`'s
  diagnostic gate does not see it — the **bounds** catch it (24026 mV/V vs
  5 mV/V). A solver-diagnostic gate is a floor, not a regulation check;
  `#118`/`#133`'s "was the DUT regulating?" gate is still unbuilt and still
  the right follow-up. This bench also still wires `EN` to the corner's
  `'vsup'` while `alter`-ing `VIN` independently (the negative-control
  wiring `#118` documented), so all five survivors are measured with `EN`
  660 mV *below* `VIN`; read them as a real, reproducible DUT behaviour
  under that stimulus, not as a clean supply-rejection number. **`#196`
  settled which of those two readings applies: that stimulus is off-contract
  for this DUT, and all five survivors are the `EN`-below-VIN artifact — with
  `EN` at the instantaneous VIN they read 0.44–0.60 mV/V at 1 mA and
  0.34–0.37 mV/V at 50 mA. See "#196" above.**
- **`load-regulation`: exactly the 7 gross-failure corners changed, all
  FAIL → PASS**, and `#118`'s "44× empty band between 19.93 mV and 881 mV
  that no continuum mechanism produces" is gone — the 44 passing corners are
  now a single continuum from **2.62 mV to 14.50 mV**.
- **`load-regulation`'s one survivor is `fs_125c_3.63v` at 19.94 mV
  (1.108 %)** against the 18 mV bound. `#118` had called that exact corner
  "the only genuine DC-accuracy gap the three rows contain" at 19.93 mV — an
  instrument sharing *none* of the superseded record's seeding lands within
  **0.01 mV** of it. That is the real remaining spec gap for this row, and
  it is a design question (`#118`'s own follow-up), not a harness one.

**What did not change, deliberately:** no bound in `spec/target-spec.md`, no
measurement expression, no `design/ldo_3v3in_1v8out.sch`, and no superseded
record file. `sim/iq`'s conversion is `#173`; the remaining benches' audit is
`#174` (verdict table in the contract section above).

### sim/iq re-run under the #171 contract, with #133's regulation gate (issue #173)

`sim/iq`'s two-`.op` chain (0 mA then 50 mA, via the same `alter iload`
convention as `line-regulation`/`load-regulation`) was the same unconstrained-
`.op` defect `#164` characterized and `#172` converted for its two siblings:
no transient, no `uic`, no `.ic`. All 45 corners of its latest record,
`20260910-034648-6c0436d`, carry a solver diagnostic (`singular matrix` or
`out of range for ^`), which `#171`'s gate now forces to FAIL outright. `#173`
converts the deck and, in the same PR, folds in `#133`'s regulation gate.

**Which contract shape, and why (same as `#172`, reused directly rather than
re-derived).** `sim/iq` now uses the contract's **`uic` + EN edge** shape:
`tran 10u 200m uic` per point, the testbench's `VEN` changed from a constant
`'vsup'` to `dc 0 pwl(0 0 100u 0 101u 'vsup' 10 'vsup')`, both `v(vout)` and
`i(vvin)` averaged over the settled 199-200 ms tail via `meas tran ... avg
... from=199m to=200m`. `sim/iq` shares `load-regulation`'s exact output
network (1 uF `C_OUT` / 10 mOhm `R_ESR`) and `iload` `alter` shape, so this
bench reuses `#172`'s own measured 199-200 ms settling window rather than
re-deriving it — the settling time is a property of the shared network, and a
hand-run cross-check (below) confirms the reuse. The `opN.`/`let` plot
prefixes become `tranN.`/`meas tran`; the `alter` chain, the two named load
points and the Iq sign convention (`-i(vvin)`, minus the deck's own known
50 mA constant at full load) are otherwise unchanged.

**`#133`'s regulation gate, folded into the same conversion.** Per `#133`'s
own curated scope, two changes land in `sim/iq/experiment.json` alongside the
seeding fix, both cited from `#133`: `iq_no_load_ua`/`iq_full_load_ua` gain a
`min: 0` floor (a genuinely regulating corner cannot draw negative VIN supply
current, so a negative reading is itself proof of a non-physical operating
point), and `vout_no_load_v`/`vout_full_load_v` — previously reported
unbounded — are now bounded to the ratified Output row's 1.764-1.836 V window,
mirroring `sim/enable-shutdown/experiment.json`'s existing `vout_pre_disable_v`
pattern rather than inventing a new mechanism. `#133`'s own scope item 4 (check
whether `sim/enable-shutdown`'s two shutdown-Iq measurements have the same
blind spot) was checked and found clear: `iq_shutdown_after_edge_ua` is
already gated in effect by `vout_pre_disable_v`'s existing regulating-window
bound on the leg it shares a transient with, and `iq_shutdown_static_ua`
(the static, EN=0 `op1` leg) has no negative or otherwise non-physical value
in its own latest record (`20260825-111526-933dfdd`, all 45 corners positive
and well inside the 3 uA bound) — the concrete failure mode `#133` reports
(a non-regulating corner reading a plausible-looking negative Iq) has no
analogue in a leg where the block is intentionally disabled rather than
attempting to regulate, so `sim/enable-shutdown/experiment.json` is left
unchanged; see `#133`'s closing comment for the full reasoning.

**Correctness confirmed by hand, formal 45-corner re-run deferred to `#213`.**
This session's sweep host carried a load average that swung between ~5 and
~20 on its 8 vCPUs while this issue was being built (many concurrent
`loom:sweep` processes sharing it), and per-corner wall time tracked that
swing directly — the identical `tt_27c_3.30v` corner completed a full
two-transient run in 25.1 s in isolation under light load, and had not
finished after several minutes moments later via `corner-run.py` once several
sibling sweeps were active. This is the same class of wall `#196` hit for the
sibling `line-regulation` bench (measured there: 578.9 s vs 41.7 s for one
corner on this same host class) — not a defect in this bench's deck: a
hand-extracted copy of the exact deck `corner-run.py --dry-run` generates for
`tt_27c_3.30v`, run directly via `ngspice -b` outside the harness under light
load, converged cleanly with **no solver diagnostic** at three transient
durations (5 ms, 50 ms, 200 ms), and the 50 ms and 200 ms results agree to
5-6 significant figures (`iq_no_load_ua` 13.733 vs 13.73304 uA;
`vout_no_load_v` 1.802386 vs 1.802385 V; `iq_full_load_ua`/`vout_full_load_v`
identical at both windows) — confirming both that the deck and its
measurement wiring (`tranN.` prefixes, the `min`/window gates) are correct,
and that `#172`'s 199-200 ms window is comfortably settled for this bench
too, not just reused by assumption. `corner-run.py` has no batch backend and
this bench's two-transient-per-corner `alter` chain is not expressible as a
`klt sim` request (2AMLogic/klayout-tools#2482, the same tracked gap `#196`/
`#200` cite) — so, as with those two issues, the full matrix is not re-run
here. **`20260910-034648-6c0436d` remains the record `measurements/
characterization.md`'s Iq row cites; its freshness reads `STALE`** (a live
`xschem` re-netlist of the corrected testbench no longer matches that
record's committed snapshot), same as `sim/current-limit` has carried since
`#177` and `line-regulation` carried between `#196` and `#200`. **`#213`**
tracks minting the superseding 45-corner record (and, per `#133`'s own test
plan, confirming whether its two named corners — `ss_-40c_3.30v` no-load,
`ff_-40c_2.97v` full-load — are still non-regulating once IC-seeded, since
seeding can change which corners regulate) on a host that can hold the run.

