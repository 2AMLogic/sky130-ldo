## The LDO's own testbenches (issues #18 and #25)

Each testbench below instantiates `design/ldo_3v3in_1v8out.sch` (issue #14,
including the current-limit and soft-start circuitry issue #22 added and the
current-mirror-OTA output stage plus sized compensation issue #25 added)
hierarchically, via its companion subcircuit symbol
`design/ldo_3v3in_1v8out.sym` (see `design/README.md` for why the symbol has
to be co-located with the schematic). All three share the same VIN/EN/VREF
stimulus convention (VIN and/or EN carry the corner runner's `'vsup'`; VREF is
a fixed 1.2 V placeholder — see `design/README.md`'s "VREF interface
caveat, and the reference common mode", which explains why 1.2 V/1:2-divider
is the value that actually regulates, unlike the earlier 0.6 V/2:1
convention) and the same output network (1 µF `C_OUT` + 10 mΩ `R_ESR`, a
representative point inside DR-002's ratified 0–500 mΩ window, not a sweep
of it). Full detail — exact stimulus, measurement expressions, and which
spec row each bound cites — lives in each experiment's own
`experiment.json` `claim` field, per this directory's own convention; this
section is a map, not a duplicate of that detail.

- **`load-transient/`** — `I_LOAD` steps 1↔50 mA (1 µs edges) at `VOUT`;
  measures undershoot/overshoot against `spec/target-spec.md`'s ratified
  "Load transient" row (peak excursion ≤150 mV). Latest quick-subset record
  (`20260818-014345-01b7905`, supersedes `20260817-212623-66b28fc`):
  **PASS** at `tt_27c_3.30v` and `ss_-40c_2.97v` (undershoot 0.136 V /
  0.125 V, improved from 0.146 V / 0.137 V), **FAIL** at `ff_125c_3.63v`
  (undershoot 0.156 V) — overall `FAIL`, but that corner improved from
  0.941 V to 0.156 V, i.e. from six times the bound to four percent over it.
  **Full 45-point PVT record** (`20260818-032755-81dc232`, issue #19,
  supersedes the pre-#36 `20260818-005853-879f035`): **23/45 PASS** — all five
  process corners pass at `-40 °C`/2.97 V, `27 °C`/3.30 V and `27 °C`/3.63 V,
  4/5 at `-40 °C`/3.30 V and 3/5 at `-40 °C`/3.63 V, and **0/15 at 125 °C**.
  The 22 failures split into 16 that miss by a plausible margin (0.150–0.311 V
  against the 0.15 V bound, worst `ff_27c_2.97v`) and the six degenerate
  `ff`/`sf` 125 °C corners described below — overall `FAIL`.
- **`psrr-dc/`** — small-signal AC sweep on VIN (1 kHz, 100 kHz) at **both**
  ratified load points (~1 mA and 50 mA, swept in one deck via
  `alter rload = 36`); measures PSRR against the "PSRR" row (>50 dB @ 1 kHz,
  >20 dB @ 100 kHz, at 1 mA and at 50 mA). Until #117 the deck measured only
  the ~1 mA point, because the pre-#25 amplifier had no regulating 50 mA
  operating point to linearize around; #25's output-stage rebuild removed
  that ceiling and #117 retired the simplification — see the testbench
  schematic's header. History below predates that change.
  Earlier quick-subset record (`20260818-015127-01b7905`, supersedes
  `20260817-212331-66b28fc`): `FAIL` at all three corners (1 kHz PSRR
  23.3 dB / 23.6 dB / 22.4 dB, all below the 50 dB bound). This is the one
  place the issue-#25 revision is a mixed result rather than an improvement.
  The `ff_125c_3.63v` corner went from **−1.2 dB** (the loop was *amplifying*
  1 kHz supply ripple, because that corner had no valid regulating operating
  point) to 22.4 dB; but the `tt`/`ss` 1 kHz figures fell from 26.1 dB /
  39.1 dB, and 100 kHz fell from 36.7 dB / 35.6 dB / 33.1 dB to 32.9 dB /
  31.7 dB / 34.6 dB. Lower 1 kHz PSRR is the expected price of a deliberately
  lower loop crossover — PSRR at a given frequency tracks loop gain at that
  frequency — and it is recorded rather than glossed, since neither the old
  nor the new number meets the row. Buying it back is coupled to the same
  Iq-budget question `design/README.md` and the DR-002 append both land on.
  **Full 45-point PVT record** (`20260818-032803-81dc232`, issue #19,
  supersedes the pre-#36 `20260818-014410-879f035`): **6/45 PASS** — the
  100 kHz bound (>20 dB) is met at **every** corner (31.5–105.3 dB), and the
  1 kHz bound (>50 dB) is met at only six (20.3 dB worst, `fs_125c_2.97v`).
  All six 1 kHz "passes" (76.6–76.8 dB) are `ff`/`sf` 125 °C corners — the same six
  that are degenerate in the other three testbenches, so they are not evidence
  of real PSRR headroom. No corner timed out (the two 300 s timeouts in the
  superseded pre-#36 record are gone) — overall `FAIL`.
  **Current record, both load points** (`20260923-125412-d71f4b3`, issue
  #117, supersedes `20260825-082845-4cb27f8`): **0/45 PASS**. The two 1 mA
  sub-metrics reproduce the superseded record digit-for-digit at every
  corner, so the deck change is a pure extension. Per sub-metric:
  `psrr_1khz_1ma_db` 20.31–25.68 dB (0/45), `psrr_100khz_1ma_db`
  31.53–34.77 dB (**45/45 PASS**), `psrr_1khz_50ma_db` 20.25–25.70 dB
  (0/45), `psrr_100khz_50ma_db` **13.80–16.06 dB (0/45)** — the last is the
  condition the one-load-point deck was not measuring, and it is the row's
  second failing sub-metric. The 1 kHz half is loop-bandwidth-bound and the
  100 kHz/50 mA half is supply-feedthrough-bound; both diagnoses, the
  measured `C_COMP` PSRR-vs-phase-margin frontier, and three screened-and-
  rejected circuit candidates are written up in `design/README.md` §"#117".
  **Superseded by `#179`** (`20260926-033606-4a9ec09`): the paragraph above
  is kept as written because its analysis is what that record actually says,
  but it is no longer the current record — `#179` seeded the deck's `ac`
  linearization points per the initial-condition contract and re-ran the
  matrix against the post-`#116`/`#139` DUT. Still **0/45 PASS**; current
  per-sub-metric numbers and the seeded/unseeded control are in "#179" above.
- **`dropout-vs-load/`** — DC VIN sweep at a fixed 50 mA load (the ratified
  spec row's own gf180-mirrored "sweep Vin toward Vout" method); measures the
  Vin–Vout margin against the ratified "Dropout @ 50 mA" row (<300 mV). Latest
  quick-subset record (`20260818-014918-01b7905`, supersedes
  `20260817-212426-66b28fc`):
  `FAIL` at all three corners (dropout 0.531 V / 0.365 V / 1.274 V, versus
  0.613 V / 0.365 V / 1.354 V before). Both records also carry a
  `vout_at_max_vin_v` sanity measurement that lands on a non-regulating
  branch at exactly one corner — `ss` in the older record (3.40 V), `tt` in
  this one (3.34 V) — while the same operating point regulates correctly in
  a plain `.op` (see `design/README.md`'s DC grid). That is a DC-sweep
  continuation artifact of this testbench, pre-dating and surviving the #25
  revision rather than caused by it; chasing it belongs with #19's fuller
  characterization. **Full 45-point PVT record** (`20260818-032811-81dc232`,
  issue #19, supersedes the pre-#36 `20260818-022803-879f035`): **0/45 PASS** —
  the best corner is 0.365 V (`ss`/−40 °C, all three supplies) against the
  300 mV bound, 33 of 45 corners land under 1 V, `ff`/−40 °C is ~1.55 V, and
  the three `sf_125c_*` corners return a nonsensical 32.6 V (see below) —
  overall `FAIL`. The `vout_at_max_vin_v` sanity measurement lands on a
  non-regulating branch at 6 of 45 corners, the same `ff`/`sf` 125 °C
  cluster.
  **`20260926-043132-eba96ae`** (issue #178, supersedes
  `20260923-123440-d71f4b3`, first run under the #171 initial-condition
  contract — the `dc VVIN` sweep is gone, replaced by a cold-start `uic`
  transient with a 266 V/s VIN down-ramp): **0/45 PASS, down from 6/45**, with
  **zero solver diagnostics on all 45 corners** (the superseded record carried
  one on all 45, 7070 hits in total). The six lost PASSes are exactly the
  superseded record's `ss`/−40 °C and `ss`/27 °C corners, and a static
  zero-rate hold test at `ss`/−40 °C confirms the new, larger numbers (VOUT
  settles at 1.7301 V with VIN held at 2.10 V, where the old 0.268 V reading
  would need regulation to hold at 2.032 V). The matrix is now a tight
  **0.330–0.673 V**: the five 125 °C corners the superseded record returned as
  1.41–1.83 V garbage now read in family with their siblings, so this bench's
  125 °C caution is discharged for `dropout_v`. One residual outlier remained,
  `fs_125c_2.97v`'s `vout_at_max_vin_v` at −7.45 V with no solver diagnostic.
  See "#178: dropout-vs-load and thermal" above for the full accounting.
  **Current record** (`20260926-102849-0b63ae4`, issue #187, supersedes
  `20260926-100003-0b63ae4` → `20260926-043132-eba96ae`): that outlier was this
  bench's own `EN`-below-VIN supply convention, not the design. `'vsup'` now sets
  VIN *and* `EN`'s rail, with the ramp's endpoint tracking `'vsup'` so the rate
  stays a constant 266.3 V/s. **Still 0/45 PASS at 0.32997–0.67307 V** — the
  largest `dropout_v` change at any corner is 0.010 mV, and the 3.63 V column is
  identical to six digits — but all 45 `vout_at_max_vin_v` readings are now
  inside the sanity band (1.79835–1.79913 V), `fs_125c_2.97v` included
  (−7.4521 V → 1.79839 V), with zero solver diagnostics. See "#187" above.

- **`loop-gain/`** (issue #25) — AC loop gain, phase margin and gain margin
  against `spec/target-spec.md`'s ratified "Stability" row (PM ≥ 45°, GM ≥ 10 dB
  worst corner). Unlike the three above it walks its own second axis: each
  PVT point runs **seven** AC sweeps, `alter`-ing `C_OUT`/`R_ESR`/`R_LOAD`
  across DR-002's ratified window (`C_eff` ∈ {0.33 µF, 4.7 µF} × load ∈
  {0, 1, 50 mA} at 10 mΩ, plus the 500 mΩ ESR ceiling), so the C_out/ESR axis
  is complete even in a `--quick` record. Because the block's feedback
  divider is internal — the LDO has no port a testbench can cut — the loop
  gain is recovered from closed-loop injection at `VREF` as `T = X/(1−X)`
  with `X = v(xldo.fb)`; the testbench header derives that and states the one
  approximation it makes. First record (`20260818-014128-01b7905`): `PASS` at
  `ff_125c_3.63v`, `FAIL` at `tt_27c_3.30v` and `ss_-40c_2.97v` — overall
  `FAIL`, and the failures are confined to the **0 mA** window points
  (15.6–19.3° at 0.33 µF, 38.1° at 4.7 µF/`ss`). DR-002's own low-`C_eff`
  corner measures 55.6–64.5° with 18.7–19.9 dB of gain margin. See the append
  this issue added to DR-002 for what the 0 mA shortfall does and does not
  settle. **Full 45-point PVT record** (`20260818-032819-81dc232`, issue #19,
  first full matrix for this experiment, supersedes nothing): **3/45 PASS** —
  and the full matrix confirms the quick record's shape rather than changing
  it. The dominant failure is still the **0 mA** window point
  (`pm_c033_0ma_deg` fails at 41 of 45 corners, `pm_c47_0ma_deg` at 20); the
  loaded points are healthy nearly everywhere (`pm_c033_50ma_deg` 45.9–78.9°
  with 17.0–21.7 dB of gain margin, failing only at the six degenerate
  corners) — overall `FAIL`.
  **Superseded by `#179`** (`20260926-040338-4a9ec09`): kept as written for
  the same reason as the `psrr-dc` paragraph above. Still **7/45 PASS**, but
  on a different seven corners — `#179` was this bench's first run against
  the post-`#116`/`#139` pass device, and it seeded all seven `ac` points per
  the initial-condition contract. See "#179" above.

- **`thermal/`** (issue #66) — trip/reset temperature and hysteresis for the
  thermal-shutdown circuit (#29/DR-005) against the spec's ratified "Thermal"
  row. Unlike the four above, it does not select `temperature_c` from the
  standard PVT corner axis — `TEMP` itself is the swept analysis variable
  (a continuous ngspice `.dc temp` sweep, 80→180 °C ascending then 180→80 °C
  descending in one session, DC continuation so the descending leg starts
  from the ascending leg's final operating point), walked across the full
  `process × supply_v` matrix. This required its own corner-coverage
  decision first (DR-005's 150 °C nominal trip target sits above DR-004's
  `{−40, 27, 125} °C` characterized axis) — see DR-005's `2026-08-25
  addendum` for the decision and `design/README.md`'s dated "Thermal-shutdown
  trip/hysteresis testbench" section for the full per-corner results and
  interpretation. First (and authoritative) full 15-point record
  (`20260825-054043-6fac47d`, supersedes `20260825-050729-6fac47d` — an
  ngspice `.meas`-interpolation artifact, not a circuit finding, see the
  experiment's own comments): **5/15 PASS** — `ff`/`sf` trip below the 125 °C
  operating ceiling at every supply corner (confirming and quantifying
  issue #69), and measured hysteresis is non-positive at every one of the
  15 corners (a new finding, filed as issue #77).
  **Superseded record** (`20260926-052517-eba96ae`, issue #178, supersedes
  `20260825-104426-933dfdd`, first run with both `dc temp` sweeps seeded from a
  measured untripped state): **13/15 PASS, up from 12/15**, and solver
  diagnostics down from **14 of 15** corner logs (132 hits) to **2 of 15**
  (18 hits) — `ss_27c_2.97v` and `sf_27c_2.97v`, which the #171 gate correctly
  forces to FAIL and which an ascending-sweep-only probe shows are *not* the
  shared-`.nodeset` limitation. Every trip temperature moved up 13–16 °C at the
  eleven undiagnosed corners — but this is *also* this bench's first run against
  the post-#69/#116 DUT (its Thermal row goes `STALE` → `fresh`), and #69
  re-sized the very thermal-shutdown circuit measured here, so that shift is not
  attributable to the seeding alone. See "#178: dropout-vs-load and thermal"
  above.
  **Current record** (`20260926-095154-f6ab418`, issue #189, supersedes
  `20260926-052517-eba96ae`): **15/15 PASS**, and **0 of 15** corner logs carry a
  solver diagnostic or a `Transient op` recovery — the `#171` gate is satisfied
  mechanically. The two residual corners were a single misclassified value in the
  seed card: `EA_TAIL`, the PMOS input pair's source node, was written
  `'vsup'`-relative although a three-supply measurement puts its supply slope at
  0.24 V/V, so the card sat 288 mV below the real node at `vsup` = 2.97 V. With
  that corrected their trip points move 150.658 → **163.001 °C** and 149.000 →
  **161.000 °C**, making the matrix monotonic in supply at every process corner
  but `fs`; the other thirteen corners are unchanged to three decimals. Matrix
  now trips 155.0–171.0 °C, all above the 125 °C bound. The `trip == reset`
  degeneracy (#77/#91) is still there — `hysteresis_c` is now exactly 0.00 °C at
  all fifteen corners, which passes the `min: 0` bound without being a measured
  window — but the two *negative* hysteresis readings turned out to be the same
  seeding defect, not a deeper form of it. See "#189" above, which also states
  what a conforming hysteretic-trip measurement would have to be.

None of the four fully meets its spec bound yet. This is an honest,
expected finding, not a harness bug — and the reason has moved. The #18
records were dominated by two gaps issue #25/#36 has now closed: an unsized
placeholder compensation and a five-transistor error amplifier whose output
could not swing to `VIN`. With those closed, `load-transient` passes 23 of 45
corners, `loop-gain`'s loaded points are comfortable everywhere the operating
point is valid, and `psrr-dc` meets its 100 kHz bound at every corner — while
`dropout-vs-load` still misses at every corner and both `psrr-dc`'s 1 kHz bound
and `loop-gain`'s 0 mA window point still fail widely. What remains is
documented in `design/README.md`'s "Known gaps / follow-on scope" and in the
DR-002 append: the pass device's own `gm_pass/(2π·C_out)` pole at no load and
an Iq budget that does not exist yet.

### The protection / transient testbenches (issue #65)

Three more benches cover the spec rows whose *circuitry* landed with issue
#22 but which had no testbench of their own, so
`measurements/characterization.md` reported them `N/A` — a coverage gap by
that report's own Limitations section, neither substantiated nor refuted.
They share the four benches' stimulus and output-network conventions above;
what is new is that two of them drive the DUT through an **event** (a held
short, an enable edge) rather than a steady condition, so each states in its
own `experiment.json` `claim` how the event is applied and which clause of
the ratified row it grades. First records are `--quick` subsets, same as #18/#25;
issue #74 then ran the full 45-point matrix each manifest declares for all
three (see each bullet's "Full 45-point PVT record" below).

Two of these rows carry clauses with **no number in them at all** ("window
TBD over PVT", "survives", "monotonic"). Where a clause has a number, it is
bounded; where it does not, the quantity is measured and reported **without**
a bound rather than graded against a limit nobody has ratified — inventing
one would be exactly the fabricated-settled-number the root `CLAUDE.md`
forbids. Issue #1 / DR-006 ratified these rows *with* those clauses left
numberless, so the missing bounds are a deliberate, ratified property of the
spec rather than a pending ratification — only a future decision record can
supply a number. Each such measurement's `note` says so explicitly, and says
what would have to change if such a record lands.

- **`current-limit/`** — forces `VOUT` through a `VFORCE`/`RFORCE` branch
  (`RFORCE` starts at 1e12 and the deck `alter`s it to 1 mΩ) in three legs:
  a settled 50 mA operating point at a 36 Ω load with the branch open
  (leg 1), a DC characteristic from a dead short up to the 1.75 V knee
  (leg 2), and a `Vout = 0` short applied as a transient event and **held for
  2 ms** (leg 3) — a sustained fault of defined duration, not one sampled
  instant, since "survives" is a claim about holding the fault. Legs 1 and 3
  are both `tran … uic` riding the same `EN` edge at t = 100 µs (a dual
  `dc 'vsup'` + rising `pwl` source); leg 2 is the one `dc` analysis, and the
  one that still solves with `EN` at its `dc` value, which is correct there
  because the forcing branch pins `VOUT` at every swept point. Leg 1 reads
  its 50 mA point from t = 0.9–1.0 ms, after the soft-start ramp settles, and
  leg 3's fault at t = 1.0 ms likewise lands on a block that reached
  regulation through a real enable edge rather than an already-enabled t = 0
  DC solve — see the harness-lesson paragraph below, and the
  initial-condition contract's "An EN edge alone does not satisfy the first
  shape" for why `uic` (added to both legs by **#177**, which also converted
  leg 1 from a bare `op`) is load-bearing on top of that edge. Bounded:
  `vout_50ma_v`
  inside the ratified Output row's ±2% window (the operative form of "never
  engages for I_load ≤ 50 mA") and both limit levels above 50 mA. Reported
  unbounded: the limit window itself, its brickwall-vs-foldback shape, and
  the sustained short current. Current record (`20260825-070327-d0bb614`,
  3-point subset, supersedes `20260825-045313-703a889` — issue #76):
  **2/3 PASS** — `tt_27c_3.30v` regulates at 1.798 V with a 162 mA
  short-circuit level against a 135 mA knee, `ss_-40c_2.97v` 1.798 V / 180 mA
  / 149 mA, and both hold the short for its full 2 ms with <0.1% supply-
  current ripple. The negative droop (−20%/−21%: more current into a dead
  short than at the knee) is the brickwall signature, not a foldback one.
  `ff_125c_3.63v` **FAILs** legs 1–2: the `op`/`dc` output collapses to ~2 µV
  and ~0 mA of limit current — the same thermal-clamp nuisance trip
  `design/README.md` root-causes as mechanism 1 (issue #69), read here
  through a resistive load instead of an ideal current sink, so the output
  sits at 0 V rather than at a non-physical negative voltage. Leg 3 at that
  same corner, by contrast, is now conclusive rather than inconclusive: with
  the enable-ramp fix, the block reaches a genuine current-limiting state
  before the fault and sustains 148 mA through the held short — in the same
  100–200 mA range as the other two corners' leg-3 results, not the ~0 mA
  the pre-#76 record showed. Overall `FAIL` is unchanged from the prior
  record, driven entirely by legs 1–2's design defect (none of leg 3's
  measurements carry a bound to begin with), but leg 3's `ff_125c_3.63v`
  result changed from inconclusive (a stuck, non-regulating branch reporting
  ~0 everywhere) to a real measurement of the clamp holding the short —
  which is what issue #76 fixed. **Full 45-point PVT record**
  (`20260825-085216-64c17cb`, issue #74, `--timeout 600` — the default 300 s
  budget genuinely wasn't enough at `tt_-40c_2.97v`/`tt_-40c_3.30v`, which
  needed 260–300 s+ even at their neighboring corners; re-run with the longer
  budget instead of accepting a timeout as the result, per this directory's
  own append-only-but-not-lazy convention. Supersedes `20260825-070327-d0bb614`,
  which supersedes the original `20260825-045313-703a889` — a two-hop chain
  now, both hops kept on disk): **39/45 PASS**. All 39 tt/ss/ff/sf/fs corners
  outside 125 °C regulate cleanly (short-circuit levels 108–236 mA against
  85–204 mA knees, −15.6%–−30.2% droop, all brickwall-shaped, <0.05% supply
  ripple through the full 2 ms hold). The six `ff_125c`/`sf_125c` corners
  **FAIL** legs 1–2 exactly as the quick subset's `ff_125c_3.63v` point
  showed — mechanism 1 (#69), not fixed here. Leg 3 (the held short, fixed by
  #76's EN ramp) is conclusive at all six of those corners now, but the two
  process corners tell different stories: `ff_125c` leg 3 reaches a genuine
  current-limiting state and sustains 108–148 mA through the short (in range
  with the neighboring corners), while `sf_125c` leg 3 shows the *same*
  thermal-shutdown collapse as its own legs 1–2 — sub-µA sustained short
  current (0.012–0.016 mA) rather than the 100+ mA the other corners show.
  That is a real, converged measurement (`ngspice` exit 0, well inside the
  600 s budget), not the pre-#76 stuck-branch artifact: the EN ramp does let
  `sf_125c` attempt soft-start, but the same mechanism-1 trip that kills
  legs 1–2 also kills the ramp before it reaches regulation, so leg 3 never
  gets a fault to "survive" at that corner. `ff_125c`'s escape from that
  trip during leg 3 (while legs 1–2 do not escape it) is a real,
  bench-observed asymmetry between the two process corners, filed as #93
  (why `sf` is more susceptible than `ff` to mechanism 1 during a ramped
  enable) rather than chased here — out of this issue's scope.
  **Record note (#177): every record above predates #177's deck change, and
  no re-run has replaced them.** The latest,
  `20260825-105322-933dfdd` (45/45 PASS, the authoritative one per "Which
  record set is authoritative" below), was graded before `corner-run.py`
  acquired #171's solver-diagnostic FAIL gate, and 16 of its 45 corner logs
  carry a `gmin stepping failed` / `singular matrix` diagnostic — under the
  gate as it now stands those 16 corners would be forced to **FAIL**
  regardless of their measured values. #177 fixed the deck that produced
  them (legs 1 and 3 to `tran … uic`; see the harness-lesson paragraph
  below), but **did not re-run the matrix**: `corner-run.py` has no
  remote/batch execution mode (`klt sim` has one, but this bench's
  multi-solve-per-corner `alter` chain is not expressible as a `klt sim`
  request — 2AMLogic/klayout-tools#2482), and the sweep host it would have
  run on forbids hand-launched local `ngspice` grids. So the committed
  records are evidence about the **pre-#177 deck only**, and this row's
  verdict against the current deck is **not established**. Closing that gap
  needs one `python3 sim/bin/corner-run.py sim/current-limit
  --supersedes 20260825-105322-933dfdd` on a host allowed to run it; the
  partial evidence #177 did gather (4 of the 45 corners, plus a per-leg probe
  at a 5th) is in its PR, not on disk here, precisely because an incomplete
  matrix must not be minted as a record.
- **`startup/`** — four independent **cold** enables in one deck (`C_out`
  0.33/4.7 µF × load 0/50 mA, the corners of the two ranges the ratified row
  quantifies over), each starting from `EN = 0` with `C_OUT` discharged and
  the soft-start ramp held down, with `EN` rising at t = 100 µs. Bounded:
  peak `VOUT` against the row's own overshoot ≤ +2%, and the *minimum* over
  the settled window (from 3 ms after the edge) against its "inside ±2%
  within a few ms" — a minimum, not a sample, so a ramp that reaches the
  window and sags back out of it fails. First record
  (`20260825-044139-703a889`, 3-point subset): **3/3 PASS** — worst peak
  1.826 V against the 1.836 V ceiling (the 4.7 µF/0 mA leg), worst settled
  floor 1.798 V, and ramp times 0.26–0.45 ms into all four load/C_out points,
  consistent with the ~290 µs soft-start screening in `design/README.md`.
  Note the honest limit stated in the manifest's own `claim`: a sample-by-
  sample monotonicity predicate is **not** computed — the peak/floor bounds
  capture the numeric consequence of a non-monotonic ramp (an excursion
  outside ±2%), and the ramp time is reported as the "controlled ramp"
  witness. **Full 45-point PVT record** (`20260825-073320-64c17cb`, issue
  #74, supersedes `20260825-044139-703a889`): **42/45 PASS** — the three
  quick-subset points still pass, `ff_125c` passes cleanly at all three
  supplies (its own worst peak 1.827 V against the 1.836 V ceiling, worst
  floor 1.796 V, ramp times 0.42–0.58 ms — comparable to the rest of the
  matrix), and 39 non-125 °C corners are inside bounds throughout. The full
  matrix surfaces a new failure the 3-point subset never reached:
  **`sf_125c` fails at all three supplies** — `VOUT` collapses to 7–11 mV
  instead of settling into the regulation window (`vpk`/`vfloor` both ≈ the
  collapsed value, `tramp` `n/a` since the settle threshold is never
  crossed). This is the same mechanism-1 thermal-shutdown false-trip (#69)
  documented for `ff`/`sf_125c` in the four core-regulation testbenches, now
  confirmed to reach `startup/`'s cold-enable path at the `sf` process corner
  specifically (`ff_125c` escapes it here, matching `current-limit/`'s leg-3
  finding above) — filed as #93.
- **`enable-shutdown/`** — one transient leg running a full enable →
  shutdown **cycle** (`EN` low at t = 0, rising at 100 µs, falling again at
  2 ms) plus three static `op` legs with `EN` held at 0. Bounded: shutdown Iq
  against the row's < 3 µA both statically and after the falling edge,
  `VIN`→`VOUT` leakage against its ≤ 1 µA with `VOUT` forced to 0 V, and the
  "no active discharge" clause as the residual output 2 ms after the disable
  edge (an active pull-down would empty `C_OUT` in microseconds; the
  divider's own R×C is seconds). First record
  (`20260825-044140-703a889`, 3-point subset): **3/3 PASS** — static
  shutdown Iq 0.13 nA–49 nA, post-edge worst-case 0.6 nA–21 nA,
  `VIN`→`VOUT` leakage 0.07 nA–52 nA, and `VOUT` still at 1.808–1.819 V two
  milliseconds after disable. All are two to four orders of magnitude inside
  the ratified bounds, which is as much a statement about that row's own
  "pending sky130 device data" note as about the design — the models'
  subthreshold/junction leakage is what sets these numbers. **Full 45-point
  PVT record** (`20260825-073259-64c17cb`, issue #74, supersedes
  `20260825-044140-703a889`): **42/45 PASS** — across the 42 passing corners,
  static shutdown Iq 0.13 nA–65.4 nA, post-edge worst-case 0.24 nA–32.3 nA,
  `VIN`→`VOUT` leakage 0.074 nA–75.8 nA, and `VOUT` 1.806–1.820 V two
  milliseconds after disable — the same orders-of-magnitude-inside-bound
  picture the quick subset showed, now confirmed everywhere the design
  actually reaches regulation. The three `sf_125c` corners **FAIL**: `EN`'s
  rising edge cannot bring the block into regulation there (`vout_pre_disable_v`
  ≈ 7–11 mV, not the ~1.8 V the other 42 corners settle to), so the static/
  post-edge Iq and leakage numbers at those three corners describe a block
  that was never on, not a real shutdown measurement — the same mechanism-1
  false-trip (#69) `startup/`'s full-matrix record hits at the identical
  three corners, and the flip side of `current-limit/`'s leg-3 finding
  above: `sf_125c` does not survive a ramped `EN` edge at all in this
  design's current state, `ff_125c` does — filed as #93.

The transient leg's *rising* edge in `enable-shutdown` is load-bearing, and
worth recording as a harness lesson: an earlier draft started that transient
already enabled and relied on ngspice's t = 0 DC solve landing on the
regulating branch. At `ff_125c_3.63v` it does not (mechanism 1 again), so the
draft failed that corner for a reason having nothing to do with the enable/
shutdown path. Ramping `EN` up from a disabled start lets the block reach
regulation the same way `startup/` shows it does, and the corner then passes —
the failure really was the solve, not the shutdown path. Issue #76 found the
same gap in `current-limit/`'s leg 3 (its `tran`) after this fix had already
landed in `enable-shutdown/` and `startup/`, and applied the identical fix
there. **Scope note, since `current-limit/` is not uniformly a transient
bench**: as of #76 the enable-edge lesson applied only to leg 3 — the `tran`
that applies and holds the `Vout = 0` short. Legs 1 and 2 were `op`/`dc`
analyses; an enable ramp cannot help a DC solve reach a different branch than
it otherwise would (there is no "before" state for a ramp to start from), so
their `ff_125c_3.63v` collapse is the design defect (#69) the record honestly
reports, not a bench artifact that fix was ever going to touch.

**#177 then moved leg 1 across that line, and added the missing half of the
lesson.** Leg 1 is no longer an `op`: it is a `tran … uic` that reaches the
50 mA point through the same enable edge leg 3 uses, so the enable-edge
lesson now covers legs 1 *and* 3, and only leg 2 remains a DC analysis it
cannot reach. The missing half is that an enable edge is **not sufficient on
its own** — a non-`uic` `tran` performs an operating-point solve before its
first timestep and reads a dual-form source's `dc` keyword there, so with
`VEN = dc 'vsup' pwl(…)` both transient legs were still solving the
fully-enabled loop from nowhere. Measured per-leg at `tt_27c_3.30v`: legs 1
and 3 each tripped `Warning: Dynamic gmin stepping failed` without `uic` and
neither does with it, at bit-identical measured values (leg 1
`vout_50ma` = 1.79883 V, leg 3 `ish_avg` = −1.53348e−01 A both ways). Whether
this changes any corner's PASS/FAIL verdict is **not yet established**: the
45-corner re-run that would settle it has not been performed — see the
`current-limit/` record note above.

### Which record set is authoritative (issue #19)

There are now **two generations** of full 45-point records on disk, and only
the newer one characterizes the design as it stands:

| Generation | Record ids | Pinned schematic | Status |
|---|---|---|---|
| Pre-#36 | `…-879f035` (`load-transient`, `psrr-dc`, `dropout-vs-load`) | `879f035` — before #35 (thermal shutdown) and #36 (rail-to-rail EA output stage + sized compensation) | **Superseded.** Kept per the append-only rule; do not cite. |
| Current *as of #19* | `…-81dc232` (all four testbenches) | `81dc232` — `main` at the time plus the `M_ENP4`/`M_ENP5` fix below | **Authoritative for issue #19's acceptance criteria**, and superseded since — see "part 2" below. |

> **Superseded again by issue #69 (2026-08-25).** The `…-81dc232` set is no
> longer authoritative for the design as it stands: #69's thermal-shutdown
> re-sizing changed the shared DUT, and a `…-4cb27f8` generation replaced all
> four of these records plus the four other experiments'. The table below is
> retained because it is the record of #19's own deliverable. See "Which
> record set is authoritative, part 2 (issue #69)".

The first generation was run before #35/#36 landed and blamed its failures on
gaps those two commits then closed, so re-running was a correctness matter, not
a refresh: the newer set is what issue #19's "full PVT + Monte Carlo
verification" deliverable rests on. Both sets stay on disk — the superseded
records point forward via the new records' `Supersedes` field, never by
deletion.

The re-run also turned up a defect in `main` itself: #35 and #36 each added an
EN-gated clamp named `M_ENP4` (on `TS_CMP` and `PB` respectively), so the
merged schematic netlisted two devices with the same instance name and ngspice
refused every deck outright (`device already exists, bail out` → "no
simulations run!"). No LDO simulation could run on `main` at `d0b244d` at all.
The minimal rename (#36's `PB` clamp → `M_ENP5`) is carried by this issue's
branch; issue #38 tracks the reason nothing caught it (nothing in
`npm run check:ci` netlists the LDO core).

### The six degenerate `ff`/`sf` 125 °C corners — diagnosed, and fixed in #69

`ff_125c_*` and `sf_125c_*` (six of the 45 points) returned values that are not
physically meaningful — 8.4–22.3 V of "undershoot" on a 1.8 V output, 32.6 V of
"dropout" from a ≤3.63 V supply, `vout_at_max_vin_v` of −19 V / −29 V, `n/a`
loop-gain measurements, and the only six 1 kHz PSRR "passes" in the matrix.
That is one signature seen four ways: at those corners the solve did not land
on a valid regulating operating point, so the number the measurement expression
extracted described the solver's excursion, not the circuit's behaviour. They
are recorded as `FAIL`/`n/a` rather than dropped (per this directory's own
rule), and they are excluded from the "worst plausible corner" figures quoted
above.

**Issue #60 root-caused this to a nuisance trip of the thermal shutdown
(#29/DR-005) inside the rated `Tj ≤ 125 °C` range, and issue #69 fixed it**
(re-sized CTAT sense/reference pair — see `design/README.md`'s "Sizing the
trip: what is a knob and what is not"). Every experiment that instantiates
`design/ldo_3v3in_1v8out.sch` was re-run against the fixed schematic on
2026-08-25; the `…-4cb27f8` record generation below is the result, and **none
of the six corners produces an out-of-range value in any experiment any
more**. The `…-81dc232` / `…-703a889` records that show the signature stay on
disk per the append-only rule and point forward via the new records'
`Supersedes` field.

### Which record set is authoritative, part 2 (issue #69, 2026-08-25)

There is now a **third generation** of records on disk. For the eight
experiments #69 re-ran it is the authoritative one, and the only generation
whose netlist snapshots match the current `design/ldo_3v3in_1v8out.sch`:

| Generation | Record ids | Pinned schematic | Status |
|---|---|---|---|
| Pre-#36 | `…-879f035` | before #35/#36 | **Superseded** (do not cite) |
| Pre-#69 | `…-81dc232` (four PVT + MC), `…-703a889` (the three #65 benches) | `81dc232` / `703a889` — thermal shutdown as first sized in #29 | **Superseded.** Contains the six degenerate corners above. |
| Post-#90 merge (#95) | `…-933dfdd` (`thermal`, `line-regulation`, `load-regulation`, `iq`, `current-limit`, `startup`, `enable-shutdown`) | `933dfdd` — post-#69/#90, on `main` after the merge conflicts that left these seven `STALE` | **Authoritative for these seven.** Closes the "parallel landings" gap below — see "#95: closing the parallel-landings gap" further down. |
| Current | `…-4cb27f8` (the eight experiments #69 re-ran) | `4cb27f8` — #69's thermal-shutdown re-sizing | **Authoritative.** |

**"Third generation" is not the same thing as "every record on disk".** Six
records that landed on `main` while #69's branch was open are *not* part of
the `…-4cb27f8` generation, and each is stale in a different, disclosed way:

| Record | Landed by | Why it is not `…-4cb27f8` | Freshness now |
|---|---|---|---|
| `sim/thermal/20260825-054043-6fac47d` | #66/#80 | Bench did not exist when #69 was cut; measures the **pre-#69** trip points | `STALE` at merge time. **Superseded by `…-933dfdd` (#95)** — see below. |
| `sim/line-regulation/20260825-040532-6fac47d` | #64/#73 | Bench did not exist when #69 was cut | `STALE` at merge time. **Superseded by `…-933dfdd` (#95)** — see below. |
| `sim/load-regulation/20260825-040748-6fac47d` | #64/#73 | Bench did not exist when #69 was cut | `STALE` at merge time. **Superseded by `…-933dfdd` (#95)** — see below. |
| `sim/iq/20260825-040934-6fac47d` | #64/#73 | Bench did not exist when #69 was cut | `STALE` at merge time. **Superseded by `…-933dfdd` (#95)** — see below. |
| `sim/current-limit/20260825-070327-d0bb614` | #76/#86 | Superseded by `…-4cb27f8`, but #86 revised `tb_current_limit.sch` **after** #69's re-run | `…-4cb27f8` reported `STALE`; the chain is now superseded further by `…-933dfdd` (#95, full 45-point matrix, fresh against the current deck) — see below. |
| `sim/dropout-vs-load/20260825-055423-c000414` | #71/#83 | Superseded by `…-4cb27f8`, but #83 revised the `dropout_v` deck **after** #69's re-run | see the methodology caveat below — **not** re-run by #95 (no further deck change since; the freshness-check blind spot itself remains open). |
| `sim/current-limit/20260825-085216-64c17cb`, `sim/startup/20260825-073320-64c17cb`, `sim/enable-shutdown/20260825-073259-64c17cb` | #74/#94 | The full 45-point matrices for the three #65 benches, run against the **pre-#69** DUT | `STALE` at merge time, and they collided with #69's 3-point re-runs — see "#74 and #69 crossed" below. **All three re-run at full breadth by #95, closing the collision** — see "#95: closing the parallel-landings gap" below. |

Two of those need reading carefully, because the re-run and the parallel
landing crossed:

- **`current-limit`.** #76/#86 gave leg 3 a cold `EN` ramp and moved the
  fault past soft-start, changing `tb_current_limit.sch` itself. #69's
  `…-4cb27f8` re-run predates that change, so its netlist snapshot no longer
  matches the current testbench and the report marks the row `STALE` — the
  freshness check catching exactly what it exists to catch. Its **3/3 overall
  PASS** therefore stands only for the pre-#86 deck.
- **`dropout-vs-load`.** #71/#83 rewrote the `dropout_v` measurement in
  `experiment.json` (downward `VIN` sweep, `.meas ... fall=1` at the −2%
  departure point) but touched only *comments* in the testbench schematic.
  The netlist-freshness check compares schematic netlists, not decks, so it
  reports `…-4cb27f8` as `fresh` even though that record was measured with
  the **superseded pre-#71 fixed-endpoint method**. Both records read 0/45
  `FAIL`, so no verdict turns on it — but the 45-corner `dropout_v` *numbers*
  to cite are #83's `20260825-055423-c000414` (0.310–0.554 V at −40/27 °C),
  not `…-4cb27f8`'s. This is a freshness-check blind spot, not a defect in
  either record; it is called out here rather than left for a reader to trip
  over.

#### #74 and #69 crossed: breadth on the old DUT vs. freshness on the new one

Issue #74 ran the full 45-point matrix for the three #65 benches against
`64c17cb` — i.e. against the **pre-#69** thermal shutdown — at the same time
#69 was re-running the 3-point subset against the re-sized one. Neither set
dominates the other, and `measurements/build_characterization_report.py`
picks per bench by record id (which sorts by run timestamp), so the merged
report lands on a mix:

| Bench | #74's full matrix | #69's 3-point re-run | Report cites | Why |
|---|---|---|---|---|
| `current-limit` | `20260825-085216-64c17cb`, **39/45** | `20260825-082847-4cb27f8`, 3/3 | #74's — **FAIL, `STALE`** | #74's run is later (08:52 vs 08:28) |
| `startup` | `20260825-073320-64c17cb`, **42/45** | `20260825-082906-4cb27f8`, 3/3 | #69's — **PASS (PVT subset), fresh** | #69's run is later (08:29 vs 07:33) |
| `enable-shutdown` | `20260825-073259-64c17cb`, **42/45** | `20260825-082908-4cb27f8`, 3/3 | #69's — **PASS (PVT subset), fresh** | #69's run is later (08:29 vs 07:33) |

Two consequences worth stating plainly rather than leaving to be inferred:

- **`startup` and `enable-shutdown` lose matrix breadth in the report.**
  Their rows revert from a 45-point verdict to a 3-point `(PVT subset)` one,
  and the subset reason those records carry — "the full 45-point matrix …
  remains issue #74's unit of work" — is now out of date, since #74
  delivered it. The narrower row is nonetheless the *fresher* one: it is the
  only measurement of these two benches against the schematic actually in
  the tree.
- **The `sf_125c` failures #74 found are #69's mechanism 1, unretested.**
  #74's full matrices fail exactly at `sf_125c` (all three supplies, in all
  three benches) and attribute it to the same nuisance trip #69 fixes —
  which is the strongest single argument for the re-run these tables point
  at. #93 (why `sf` is more susceptible than `ff` during a ramped enable) is
  posed entirely on pre-#69 evidence and should be re-read after it.

Per-experiment before/after (old → new record id, and the verdict change):

| Experiment | Superseded | Current | Verdict |
|---|---|---|---|
| `dropout-vs-load` | `20260818-032811-81dc232` | `20260825-081240-4cb27f8` | 0/45 → 0/45 PASS |
| `load-transient` | `20260818-032755-81dc232` | `20260825-081255-4cb27f8` | 23/45 → **25/45** PASS |
| `psrr-dc` | `20260818-032803-81dc232` | `20260825-082845-4cb27f8` | 6/45 → **0/45** PASS (a correction, see below) |
| `loop-gain` | `20260818-032819-81dc232` | `20260825-081257-4cb27f8` | 3/45 → **7/45** PASS |
| `current-limit` | `20260825-045313-703a889` | `20260825-082847-4cb27f8` | 2/3 → **3/3, overall PASS** |
| `startup` | `20260825-044139-703a889` | `20260825-082906-4cb27f8` | 3/3 → 3/3 PASS |
| `enable-shutdown` | `20260825-044140-703a889` | `20260825-082908-4cb27f8` | 3/3 → 3/3 PASS |
| `mc-output-accuracy` | `20260818-032827-81dc232` | `20260825-083111-4cb27f8` | 181/200 → 177/200 samples PASS |

**`psrr-dc`'s 6/45 → 0/45 is the evidence trail getting more honest, not a
regression.** All six of its old "passes" were the falsely-tripped corners
— AC gain measured around a collapsed bias point, which this file and #60
both already flagged as not-real PSRR. With the trip gone, the 1 kHz column
collapses from 20.31–76.79 dB to **20.31–25.68 dB** against the 50 dB spec
bound: PSRR now demonstrably fails everywhere, which is what #60 inferred
and #69's re-run measures. The underlying PSRR shortfall is issue #70's, and
is untouched by #69.

Full before/after detail, including the two `load-transient` corners that
changed verdict for a mechanism-(4) reason rather than a transient one, is
in `design/README.md` → "What the #69 re-run changed".

#### #95: closing the parallel-landings gap (2026-08-25)

Issue #95 re-ran the seven benches the "parallel landings" table above left
`STALE` (or, for `startup`/`enable-shutdown`, breadth-losing) after PR #90
merged #69 into `main`. Each new record is pinned to `933dfdd` — the merge
commit's `design/ldo_3v3in_1v8out.sch` — and carries a `Supersedes` field
back to the record it replaces:

| Bench | Superseded | New (`933dfdd`) | Verdict |
|---|---|---|---|
| `thermal` | `20260825-054043-6fac47d` | `20260825-104426-933dfdd` | 5/15 FAIL → **12/15 FAIL** |
| `line-regulation` | `20260825-040532-6fac47d` | `20260825-104914-933dfdd` | 2/3 FAIL → **1/3 FAIL** |
| `load-regulation` | `20260825-040748-6fac47d` | `20260825-105113-933dfdd` | 2/3 FAIL → **3/3 PASS** |
| `iq` | `20260825-040934-6fac47d` | `20260825-105157-933dfdd` | 3/3 PASS → **3/3 PASS** |
| `current-limit` | `20260825-085216-64c17cb` (#74's full matrix) | `20260825-105322-933dfdd` | 39/45 FAIL → **45/45 PASS** |
| `startup` | `20260825-082906-4cb27f8` (#69's 3-point re-run — the record the merged report was actually citing) | `20260825-110456-933dfdd` | 3/3 PASS (subset) → **45/45 PASS** |
| `enable-shutdown` | `20260825-082908-4cb27f8` (#69's 3-point re-run — the record the merged report was actually citing) | `20260825-111526-933dfdd` | 3/3 PASS (subset) → **45/45 PASS** |

`startup` and `enable-shutdown` point their `Supersedes` field at the
`…-4cb27f8` record rather than #74's `…-64c17cb` one, because `…-4cb27f8` is
what `measurements/characterization.md` was actually citing at merge time (a
straight replacement of the currently-cited evidence); the collision this
section documents above is resolved regardless, since the new record is both
fresher and carries #74's full 45-point breadth.

**This closes the "#74 and #69 crossed" collision above and confirms #74's
diagnosis.** `current-limit`, `startup` and `enable-shutdown` all read a
clean 45/45 `PASS` against the post-#69 schematic — the `sf_125c`/`ff_125c`
corners #74's pre-#69 matrices failed at (attributed to mechanism 1) now
pass, so #93's question (posed on that pre-#69 evidence) is answered: those
corners were mechanism 1, and #69 fixed them.

**`thermal` turns #69's `.op`-screened trip estimate into a measured
15-corner `sim/` record, and corroborates rather than changes #91's manual
re-screen** (`design/README.md` → "#91"): `trip_temp_c`/`reset_temp_c`/
`hysteresis_c` at all 15 corners match #91's table to three significant
figures, so the same three corners (`tt_27c_3.63v`, `ss_27c_2.97v`,
`ff_27c_3.63v`) still read a small negative hysteresis post-resize.
`20260825-054043-6fac47d` is no longer the authoritative `sim/thermal`
record; `20260825-104426-933dfdd` is.

**`line-regulation`'s failing corner moved, not just its count — flagged
here rather than silently absorbed into a lower FAIL count.** Pre-#69, only
`ff_125c_3.63v` failed (~1005–1010 mV/V, the mechanism-1 signature); post-#69
that corner now passes cleanly (~0.4–0.5 mV/V), but `tt_27c_3.30v` newly
fails both legs (~1739/1317 mV/V) and `ss_-40c_2.97v` newly fails its 50 mA
leg (~2477 mV/V). The magnitude matches this schematic's documented
DC-solution-multiplicity signature on sequential `alter`-based `.op` points
(the "six degenerate corners" above), now apparently landing on a different
corner subset post-resize — the most likely explanation, not a confirmed
root cause, since diagnosing it was outside #95's re-run scope. Worth a
follow-up issue if pursued further. `load-regulation` and `iq` show no
comparable new failure; both improve or hold cleanly at the same three
points.

`measurements/characterization.md` is regenerated against these seven new
records; `python3 measurements/build_characterization_report.py --check`
passes.

#### #104: full 45-point matrix for `line-regulation`/`load-regulation`/`iq`

Issue #104 ran the full 45-point PVT matrix that `line-regulation`,
`load-regulation` and `iq`'s manifests have always declared, closing the one
full-matrix gap these three benches still shared with the #65 protection
benches after #95. The schematic has not changed since `933dfdd` (the #90
merge commit those records are pinned to, `b53a8e7`), so each new record
supersedes #95's 3-point re-run directly and the fresh netlist snapshots
match the superseded records' byte-for-byte:

| Bench | Superseded | New (full matrix) | Verdict |
|---|---|---|---|
| `line-regulation` | `20260825-104914-933dfdd` (3-point subset) | `20260910-030557-6c0436d` | 1/3 FAIL (subset) → **18/45 PASS** |
| `load-regulation` | `20260825-105113-933dfdd` (3-point subset) | `20260910-032854-6c0436d` | 3/3 PASS (subset) → **34/45 PASS** |
| `iq` | `20260825-105157-933dfdd` (3-point subset) | `20260910-034648-6c0436d` | 3/3 PASS (subset) → **36/45 PASS** |

`load-regulation` and `iq` both lose their subset-era overall `PASS`
verdict: the narrow 3-point subset happened to sample only corners where the
DUT regulates, and the wider matrix finds 11 and 9 further corners
respectively where it does not — see each bench's own bullet below for the
failing-corner lists and, for `line-regulation`, the DC-solution-
multiplicity-vs-physical-reading split its 27 failing corners break into.

