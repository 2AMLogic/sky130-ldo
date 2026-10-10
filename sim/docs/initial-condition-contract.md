## Initial-condition contract (issue #171)

**A bench's `.op`/`.tran`/`.ac`/`.dc` analysis chain must start from a
physically realizable state of the circuit — never from ngspice's own
unconstrained `.op` solve.** Three shapes satisfy this:

- **`uic` + an EN edge** — every node starts at its natural cold-start value
  (0 V unless a source forces otherwise), `EN` starts low (block disabled),
  and the deck's first analysis is a `tran … uic` (or a `.dc`/`.op` chained
  off one) whose stimulus brings `EN` high at some later time so the block
  powers up through its own soft-start ramp, exactly like a real power-on
  event. `sim/mc-output-accuracy` (post-#164) uses this convention; see its
  `experiment.json`'s `mc_analysis.note` for the worked example. A bench
  whose analysis never leaves the disabled (`EN = 0`) state before the
  measurement window it cares about — e.g. `sim/startup`'s cold-enable legs,
  which measure the ramp *through* the EN edge itself rather than a settled
  ON-state — can rely on an ordinary (non-`uic`) `.op`/`.tran` seed instead,
  because the disabled state has no closed feedback loop to disambiguate; the
  hazard this contract exists for is specific to seeding a solve that must
  land on the loop's **regulating** operating point.
- **An `.ic`-seeded `.op`** — every node the loop needs to disambiguate is
  given an explicit `.ic` value close to the block's expected operating
  point (a `.ic v(node)=<value> …` card in the netlist body), and the `.op`
  solve is released from that seed rather than from ngspice's own guess.
  `sim/ic-screen-125c-b` (`tran 10u 3m` — no `uic` — with an `.ic` card
  constraining every node the loop needs) is a worked example of this shape
  (see design/README.md "#164" for the multi-variant screen that established
  it as equivalent to `uic` + EN edge for this circuit).
- **A `.nodeset`-seeded `.ac`/`.op`** — the same constrain-then-release seed
  as the shape above, written with the card an **`ac`** analysis's own
  operating-point solve actually honours. `sim/loop-gain` and `sim/psrr-dc`
  (post-#179) are the worked examples; both carry a
  `.nodeset v(VOUT)=1.8 v(xldo.FB)=1.2 v(xldo.N_FBB)=0.6` card in the
  testbench schematic (`devices/code_shown.sym`, exactly as
  `sim/ic-screen-125c-b` carries its `.ic`), and both record `v(vout)` from
  an `op` taken at every bias point as evidence the seeded solve landed on
  the regulating branch.

  **Seed only the branch-defining nodes.** A `.nodeset` card is a *single
  static card* applied to every operating-point solve in the deck, while
  both of these benches walk several load points via `alter`. So the card
  may only constrain nodes whose value says *which branch* the solve is on
  — here `VOUT` and the two feedback-divider taps `FB`/`N_FBB` — and must
  leave every node whose value is set by the operating **current**
  (`EA_OUT`, `EA_CZ`, `EA_TAIL`, `EA_D1/D2`, `BIASP`, `NB`, `SS`) to the
  solver. Seeding those too is actively harmful, and #179 measured how
  (see "#179" below): `sim/ic-screen-125c-b`'s eleven-node seed, whose
  values are its 125 °C/50 mA operating point, drags the *1 mA* point of
  `ss/−40 °C/3.63 V` onto a non-regulating branch (`VOUT = 3.633 V = VIN`)
  in both benches. This is the `.ac` counterpart of the `.ic` rule, not a
  contradiction of it: `sim/ic-screen-125c-b` seeds eleven nodes correctly
  because it is a *single-operating-point* transient screen.

  **Why `.nodeset` rather than `.ic` for an `ac` deck** (measured during
  #179, ngspice-46, not inferred from the manual):

  1. **`.ic` is inert in an ac-only deck.** ngspice applies `.ic` to the
     *transient* operating point only. Adding an eleven-node `.ic` card to
     `sim/psrr-dc`'s deck changed neither a measurement nor a solver
     diagnostic; adding it to a deck with a leading `op` instead *introduced*
     two `Warning: singular matrix: check node xldo.xr_fb_b.t2` lines — i.e.
     the `.ic` shape is the wrong tool here, and forcing it would have
     tripped the FAIL gate rather than satisfied the contract.
  2. **Each `ac` re-solves its operating point from scratch, so a seed
     carried by a preceding analysis does not survive.** On `sim/loop-gain`'s
     seven-point deck the baseline logs one Newton continuation per `ac`
     (seven); prepending a bare `op` produces *eight*, not a reuse of the
     first. A per-point `.ic`/`op` seed is therefore impossible to chain,
     which is the specific question #179 raised about the `alter`-reached
     points — and the reason the seed has to be a card the *analysis itself*
     honours rather than a preceding analysis.
  3. **`.nodeset` is applied to every operating-point solve the deck
     performs**, including the one inside each `ac`, so a single card covers
     all seven `alter`-reached points. That it is genuinely applied (not
     silently dropped on hierarchical node names) is visible in the result:
     on the current DUT it takes `sim/loop-gain` from three corners whose
     `ac` linearized about `VOUT = VIN` down to none, and `sim/psrr-dc` from
     one to none, while *releasing* to bit-identical measurements at every
     corner that was already on the regulating branch — the seed is a basin
     hint, not a forced result. Per-variant counts: "#179" below.

**An EN edge alone does not satisfy the first shape — a non-`uic` `tran`
still solves an operating point first, and it reads a source's `dc` keyword
value there (issue #177).** This is the one mechanical detail the contract's
first shape depends on, and it was stated wrongly here and in #174's audit
until #177 measured it. Before the first timestep of a `tran` **without**
`uic`, ngspice computes a transient operating point; for an independent
source written with *both* a `dc` value and a transient function
(`dc <X> pwl(…)`, `dc <X> PULSE(…)`), that solve uses the **`dc` value**, not
the transient function's t = 0 value. ngspice announces it on stderr, once
per such source, on every run:

```
Note: <source>: dc value used for op instead of transient time=0 value.
```

The transient *waveform* afterwards does start from the transient function's
t = 0 value — so a deck can look correctly cold-started in its own waveforms
while its operating-point solve was the fully-enabled, loop-closed,
from-nowhere Newton start this contract exists to forbid. A minimal repro
settles both halves: `V1 n1 0 dc 3.3 pwl(0 0 100u 0 …)` feeding `R1 n1 n2 1k`
/ `C1 n2 0 1u` prints `v(n1) = v(n2) = 0` at t = 0 under `tran` (τ = 1 ms, so
a 3.3 V seed could not have decayed away by then), while ngspice still prints
the note above for the op it performed.

**The practical rule, therefore: write `uic` on the transient.** `uic` skips
that operating-point solve outright, which is what makes the EN edge the
*only* thing establishing the start state. The consequence is per-source, not
per-bench, and depends entirely on what the `dc` value is:

| `VEN` form | Transient op solves with | Exposed? |
|---|---|---|
| `dc 'vsup' pwl(0 0 …)` | `EN = 'vsup'` — **enabled, loop closed** | **Yes** — needs `uic` |
| `dc 0 pwl(0 0 …)` | `EN = 0` — disabled | No (the carve-out above) |
| `PULSE(0 'vsup' …)`, no `dc` keyword | `EN = 0` (the pulse's initial value) | No (the carve-out above) |
| `'vsup'` (a plain DC source) | `EN = 'vsup'` — enabled, loop closed | **Yes** |

`sim/current-limit` is the only bench in `sim/` whose dual-form `VEN` carries
an *enabled* `dc` value, so it is the only bench this correction moves;
`sim/enable-shutdown` (`dc 0 pwl(…)`) and `sim/startup` /
`sim/mc-output-accuracy` / `sim/ic-screen-125c-c` (`PULSE(…)`, no `dc`
keyword) keep their **Clear** verdicts on their own merits, and the benches
with a plain `'vsup'` `VEN` were already verdicted **Exposed**.

**Why an unconstrained `.op` is not acceptable for a claim against
`spec/target-spec.md`:** ngspice's Newton solver on a from-nowhere `.op` is
not guaranteed to land on the circuit's actual operating point — it can
converge to a numerically spurious branch instead, and it does not always
tell you when it has. Issue #164 (closed via PR #170, merged `3a7d2bc6`) is
the precedent: `mc-output-accuracy`'s original testbench seeded its transient
from an unconstrained `.op`, and on the committed N=200 sample sequence, 12
of the 200 draws settled with `FB` at up to 1.3e15 V while `VOUT` sat at
`VIN` — a state that violates the passive feedback divider's own algebra
(`FB` is a tap fed only by `VOUT` through a resistor string, so `FB` can
never exceed `VOUT`). The mechanism was `sky130_fd_pr__res_xhigh_po`'s
non-monotone voltage-coefficient extrapolation admitting a numerical "solution"
thousands of volts off the physical range; a nominal-device `.nodeset`
reproduces it with no mismatch involved, so it is a solver-seeding defect, not
a device-mismatch finding. The fix was to seed the transient from a
physically realizable state (`uic`, `EN` as an edge) instead — see
`sim/mc-output-accuracy/experiment.json`'s `mc_analysis.note` and
design/README.md "#164" for the full measurement.

**The harness now detects the hazard mechanically, not just by testbench
convention.** When an unconstrained (or otherwise poorly seeded) `.op` chain
hits this failure mode, ngspice's Newton solver falls back to gmin/source
stepping before it gives up, and — whether or not that fallback itself
"succeeds" — it prints one or more diagnostic lines to stdout/stderr:

- `Warning: singular matrix:  check node <node>`
- `Warning: Dynamic gmin stepping failed` (also catches `Warning: True gmin
  stepping failed` — both contain the substring `gmin stepping failed`)
- `Error: <value>, 2 out of range for ^` — the solver evaluated an expression
  (e.g. a poly-resistor's voltage-coefficient term) at a value so far outside
  its intended domain that `pow()` itself errors

`sim/bin/corner-run.py`'s `SOLVER_DIAGNOSTIC_MARKERS` is deliberately the
three forms above, confirmed against real committed logs at the time of
writing (issue #171) — not an attempt at an exhaustive catalog of every
ngspice non-convergence message. In particular, `Warning: source stepping
failed` (a fourth ngspice fallback, seen in some already-committed 125 °C
corners of `sim/dropout-vs-load` and `sim/thermal`) is evidence of the same
underlying class of hazard but is **not yet matched** — widening the marker
set is a small, low-risk follow-up, not a blocker for this contract.

Critically, ngspice does **not** treat any of these as fatal — the run still
exits `0` and still prints what looks like a converged `.op`/`.meas` result,
so a harness that only checks the exit code and the measurement bounds grades
the corner as a clean PASS even though the state it measured may not be a
circuit state at all. `sim/bin/corner-run.py`'s `run_corner()` scans the raw
ngspice stdout+stderr for these markers on every corner and forces the corner
to **FAIL** — regardless of whether its measurements happen to land inside
their bounds — with a `reason` of the form `solver diagnostic: <the matched
line>`, distinct from an ordinary measurement-bound failure. The raw
stdout/stderr (where the diagnostic came from) is always written unchanged to
the corner's `.log` file, so the diagnostic that triggered the FAIL is visible
in the committed evidence, not just summarized.

This detection mechanism lives entirely inside `sim/bin/corner-run.py` — it
covers every bench that runner drives (`sim/pdk-smoke`, `sim/dropout-vs-load`,
`sim/loop-gain`, `sim/line-regulation`, `sim/load-regulation`,
`sim/ic-screen-125c-*`, etc.), not `sim/bin/mc-run.py`'s Monte Carlo/`klt sim`
benches (`sim/mc-output-accuracy`, `sim/mc-ic-screen-*`) — those already carry
their own per-sample `diagnostics` field in the `klt sim` response, which this
issue does not touch (the equivalent capability at that tool layer is tracked
by `2AMLogic/klayout-tools#2489`, not this repo's issue).

**#171 was the detection mechanism only — it did not convert any bench's own
analysis chain.** `sim/line-regulation` and `sim/load-regulation` chained
four (respectively two) `.op` solves via `alter` cards with no `uic`/`.ic`
seed at all (`experiment.json` → `deck.analyses`), which did **not** meet
this contract; their 45-corner records up to and including
`20260925-114251-1f54ca6` / `20260925-111601-7701e7e` predate the check and
were graded before it existed. **Issue #172 converted both** — see
"Line regulation and load regulation re-run under the #171 contract
(issue #172)" below for the conversion, the settling measurement behind it,
and the verdict changes. **Issue #173 converted `sim/iq`** and folded in
`#133`'s regulation gate — see "sim/iq re-run under the #171 contract, with
#133's regulation gate (issue #173)" below for the deck conversion; its
45-corner re-run is deferred to `#213` (host-contention wall, same shape as
`#196`/`#200` below). The remaining benches' audit is #174 (verdict table
below). `sim/ic-screen-125c-*`
(`uic` or `.ic`-seeded, per above) and `sim/startup` (disabled-state seed,
per above) already meet this contract: re-running them under the new check
should report no diagnostic and leave their verdict unchanged.

**Issue #178 converted the two benches whose exposed analysis was a bare `dc`
sweep** — `sim/dropout-vs-load` (a VIN sweep) and `sim/thermal` (two `dc temp`
sweeps). That turned out to be a case neither #170 nor #172 could have covered,
because ngspice honours `.ic` only for the operating-point solve preceding a
non-`uic` transient: a `dc` analysis cannot be given either of the two seed
shapes this contract names. See "#178: dropout-vs-load and thermal" below for
the measurement behind that statement and for what each bench did instead.

**#174 audited the remaining benches (`current-limit`, `dropout-vs-load`,
`loop-gain`, `load-transient`, `psrr-dc`, `thermal`, plus a re-confirmation
of `startup`/`enable-shutdown`) against this contract, read-only — no
bench's `experiment.json`/`testbench/*.sch` was changed by that issue.**
Verdicts (verified against `origin/main` @ `2a2c0e6`, 2026-09-25 — see #174
for the full evidence trail and #177/#178/#179/#180 for the follow-up
conversions):

| Bench | Verdict | Mechanism |
|---|---|---|
| `current-limit` | **Exposed** — on **all** of legs 1 and 3, not just leg 1 (corrected by #177, see below) | Leg 1's `op` (`experiment.json:24`) runs with `VEN`'s `dc` value (`'vsup'`, fully enabled) per `testbench/tb_current_limit.sch:145` — an unconstrained, loop-closed solve. ~~(Leg 3's `tran` is *not* exposed: ngspice's non-`uic` transient uses the source's PWL value at t=0, which starts at 0/disabled, per the same line's comment.)~~ **That parenthesis is wrong**, and #177 measured it wrong: a non-`uic` `tran` performs an operating-point solve first and reads the `dc` keyword value there, so leg 3's `tran` was exposed by the same mechanism as leg 1's `op` — see "An EN edge alone does not satisfy the first shape" above. Run per-leg at `tt_27c_3.30v` with no `uic`, legs 1 and 3 each tripped `Warning: Dynamic gmin stepping failed`; leg 2's `dc` sweep did not. Converted by #177: both transient legs now carry `uic`. |
| `dropout-vs-load` | **Exposed** → **converted (#178)** | Its only analysis, `dc VVIN 3.63 1.5 -0.02` (`experiment.json:23`), ran with `VEN` held at a constant `'vsup'` (`testbench/tb_dropout_vs_load.sch:108`, no PWL/PULSE at all) — unconstrained, loop-closed. **#178 replaced the `dc` sweep with a cold-start `uic` transient whose VIN is a quasi-static down-ramp** — see "#178: dropout-vs-load and thermal" below. |
| `loop-gain` | **Exposed** → **converted (#179)** | Its first analysis, `ac dec 30 1e-2 1e9` (`experiment.json:24` as audited), ran with `VEN` held at a constant `'vsup'` (`testbench/tb_loop_gain.sch:102`) — the implicit linearization-point solve ngspice performs before an `ac` analysis is unconstrained, and it is redone from scratch for each of the deck's seven `alter`-reached points. **Converted by #179** to the `.nodeset`-seeded `.ac` shape above. |
| `load-transient` | **Exposed → CONVERTED (#180)** | Was `tran 200n 3m` with no `uic`, with `VEN` held at a constant `'vsup'` (`testbench/tb_load_transient.sch`) — the same "`tran` with no `uic`" defect `#164` fixed for `mc-output-accuracy`. **#180 converted it** to the `.ic`-seeded shape (variant B): `testbench/tb_load_transient.sch`'s `IC_SEED` card constrains the operating-point solve to the loop's regulating branch at the pre-step 1 mA load and the (still non-`uic`) transient is released from it. See "`load-transient` after #180" below. |
| `psrr-dc` | **Exposed** → **converted (#179)** | Its first analysis, `ac lin 3 1e3 1e5` (`experiment.json:24` as audited), ran with `VEN` held at a constant `'vsup'` (`testbench/tb_psrr_dc.sch:67`), for both its 1 mA and its `alter`-reached 50 mA point. **Converted by #179** to the `.nodeset`-seeded `.ac` shape above. |
| `thermal` | **Exposed** → **seeded (#178)** | Its first analysis, `dc temp 80 180 2` (`experiment.json:48`), ran with `VEN` held at a constant `'vsup'` (`testbench/tb_thermal_trip.sch:78`). **#178 seeded both `dc temp` sweeps with a `.nodeset` measured from a settled cold-start transient** — the only mechanism available to a temperature sweep, see "#178: dropout-vs-load and thermal" below. |
| `startup` | **Clear** | `VEN` is `PULSE(0 'vsup' 100u 1u 1u 100 200)` (`testbench/tb_startup.sch:89`) — no separate `dc` keyword, so its `.op`/`.tran` default DC value is the pulse's own initial level (0 V, disabled). The disabled state has no closed feedback loop to disambiguate, per this contract's own carve-out above. |
| `enable-shutdown` | **Clear** | `VEN` is `dc 0 pwl(0 0 100u 0 101u 'vsup' 2m 'vsup' 2.001m 0 10 0)` (`testbench/tb_enable_shutdown.sch:117`) — the **`dc 0`** is what earns this verdict (not the PWL's t=0 value: #177 showed a non-`uic` `tran`'s op reads the `dc` keyword, so an enabled `dc` value would have exposed it). Leg 1's `tran` therefore solves its op at `EN = 0`, disabled, and reaches regulation through an EN edge (the contract's `uic` + EN-edge shape, informally: no `uic` keyword is present, but the disabled start makes the distinction moot the same way it does for `startup`); legs 2-4's `op`s carry the same `dc 0`, landing on the same disabled state. |

### #178: dropout-vs-load and thermal — and what a `dc` analysis can and cannot be seeded with

Both benches #178 owns ran a bare `dc` sweep as their only (`dropout-vs-load`)
or first (`thermal`) analysis. Converting them measured something the contract
above did not yet say, and that the other conversions (#170, #172) never had to
find out, because none of them had a `dc` sweep to keep:

- **`.ic` does not reach a `dc` analysis at all.** ngspice applies `.ic` to the
  operating-point solve that precedes a *non-`uic` transient*; a `dc`/`op`
  solve ignores it. Measured directly on `dropout-vs-load` (tt/125 °C/3.30 V,
  one corner): adding the eleven-node `.ic` card copied verbatim from
  `sim/ic-screen-125c-b` left the sweep's flail completely intact — `singular
  matrix` ×6, `Dynamic gmin stepping failed` ×16, `out of range for ^` ×13,
  with iterates at 1e155–1e188 V on the `sky130_fd_pr__res_xhigh_po` body
  expressions (`xr_fb_b`, `xr_fb_c`, `xr_cz`) — i.e. indistinguishable from the
  unseeded run. #172 had already measured the other half on the regulation
  benches: `.nodeset`, which a bare solve *does* honour, still printed
  `singular matrix` plus `Dynamic gmin stepping failed` at 3 of 5 corners
  probed there.
- **A seed can only ever fix a sweep's first point.** `dropout-vs-load`'s
  superseded record carries *thousands* of diagnostics per corner log, not one
  each: the continuation re-derives — and repeatedly re-loses — the regulating
  branch all the way down the sweep. Seeding the start cannot address that.

So the two benches took different routes, for a reason that is about ngspice's
capabilities, not about taste:

- **`dropout-vs-load` stopped being a `dc` sweep.** VIN is now a PWL ramp
  inside one cold-start `uic` transient (`tran 10u 14m uic`): 0 → 3.63 V by
  100 µs with `VEN` stepping high at 100 µs, the ideal 50 mA sink ramped on
  over 2.5–2.6 ms once the loop is up (`sim/ic-screen-125c-c`'s own cold-start
  convention, verbatim — an ideal sink on a disabled, discharged output is not
  a realizable state), settled by 5.5 ms, then VIN walked down 3.63 → 1.5 V
  over 6–14 ms at 266.3 V/s. There is no operating-point solve in the deck at
  all: the contract's `uic` + EN-edge shape, the same one #170 and #172 landed.
  **Quasi-static, measured not assumed** (tt/27 °C/3.30 V): the 20 ms ramp
  reads `dropout_v` = 0.397295 V, a 3× slower 60 ms ramp reads 0.398492 V, and
  the superseded `dc` record — the zero-rate limit of the same experiment —
  reads 0.399743 V. ~1.2 mV per 3× rate change, moving *toward* the DC answer
  as the ramp slows, 2.4 mV of total span against a 300 mV ratified bound. The
  supply axis keeps its pre-#178 meaning exactly: VIN starts at 3.63 V for
  every corner (as the `dc` sweep's own first point did, independently of
  `'vsup'`) and `'vsup'` still sets `EN`'s rail alone.
- **`thermal` could not stop being a `dc` sweep.** ngspice has no
  time-varying `TEMP`, so a temperature sweep cannot be a transient, and the
  `uic` + EN-edge shape is unavailable to this bench — a `dc` analysis
  evaluates a time-dependent source at t = 0, so giving `VEN` a PULSE edge
  would hold `EN` at 0 and disable the block for the whole sweep. That leaves
  `.nodeset` as the only seed mechanism that reaches the solve at all. The card
  seeds the **ascending** sweep's own 80 °C starting point with the node set of
  a settled cold-start `uic` transient of that same testbench at
  tt/80 °C/3.30 V (V(VOUT) 1.80076 V, regulating, zero solver diagnostics), so
  the values are a *measured* realizable state rather than a guess. Two limits
  are recorded in the testbench header rather than papered over: `.nodeset` is
  a netlist card, so both sweeps share it (right at 80 °C ascending, a
  deliberately wrong — but first-guess-only — state at the descending sweep's
  180 °C start, where the block is expected to be tripped; ngspice offers no
  per-analysis nodeset), and this bench's `trip == reset` degeneracy is the
  pre-existing DC-continuation limitation #77 found and #91 carries forward,
  which #178 neither fixes nor worsens.

Because `.nodeset` is the weaker mechanism (a first-iteration constraint that
is then released, not a held state), `thermal`'s conformance is established by
the measured absence of solver diagnostics in its post-#178 record, not by the
mechanism's pedigree.

#### What `dropout-vs-load`'s re-run found (record `20260926-043132-eba96ae`)

**Zero solver diagnostics on all 45 corners, and zero timeouts** — against
**45 of 45** corner logs carrying one in the superseded `20260923-123440-d71f4b3`
(7070 marker hits in total there, plus `source stepping failed` on 3 of them;
the new record has 0 of each, that fourth marker included). The `#171` gate is
therefore satisfied mechanically, not by assertion.

**The verdict changed, and not in the flattering direction: 6/45 → 0/45 PASS.**
All six of the superseded record's PASSes were `ss`/−40 °C and `ss`/27 °C
(0.268–0.298 V against the 300 mV bound); those same corners now read 0.513 V
and 0.400 V. The rest of the matrix mostly *agrees* with the old numbers —
`tt`/27 °C to 2 mV, `ff`/−40 °C and `ff`/27 °C to 7 mV, `sf`/125 °C and
`fs`/125 °C (3.30/3.63 V) to 4 mV — so this is not a wholesale shift; it is the
`ss` column moving.

**That flip is validated at zero ramp rate, at the exact corner, rather than
argued.** A static two-point hold at `ss`/−40 °C/2.97 V (cold start, settle at
3.63 V, step to a held VIN, 6 ms of settling at each hold, no ramp anywhere
near the measurement) reads:

| Held VIN | Settled V(VOUT) | Regulating (≥ 1.764 V)? |
|---|---|---|
| 2.28 V | 1.79746 V | yes, by 33 mV |
| 2.10 V | 1.73008 V | **no** |

So the static crossing lies just below 2.28 V — i.e. `dropout_v` just under
0.516 V, within 3 mV of the ramp's own 0.5134 V — and the superseded record's
0.268 V would require regulation to hold at VIN = 2.032 V, where this test
shows the block is already 34 mV out of regulation at 2.10 V. **The old PASSes
were an artifact of the unseeded sweep, not a capability the design has.**

**The 125 °C caution this bench has carried since #71/#81 is discharged for
`dropout_v`.** The five corners the superseded record returned as obvious
garbage — `ss_125c_*` at 1.41–1.83 V, `ff_125c_2.97v` at 1.82 V,
`fs_125c_2.97v` at 1.83 V — now read 0.330 V, 0.673 V and 0.432 V, i.e. in
family with their own process/temperature siblings to within a few mV, and the
whole matrix now spans a tight **0.330–0.673 V** with supply scatter below
1 mV (as it should: VIN is the same ramp at every corner, and `'vsup'` only
sets `EN`'s rail). `ff_-40c_3.63v`, a 300 s timeout with no measurement at all
in the superseded record, now completes and reads 0.6585 V.

**One residual, reported rather than suppressed**: `fs_125c_2.97v`'s
`vout_at_max_vin_v` sanity measurement reads **−7.45 V** (it was −14.06 V in
the superseded record) while its `dropout_v` reads a perfectly in-family
0.432 V. It is the only one of the 45 corners outside the sanity band — the
superseded record had 7 (six on a non-regulating 3.17–3.49 V branch, plus that
−14 V) — and it carries **no** solver diagnostic, so it is not the seeding
defect: the block is not coming up at all at that corner, and the ideal 50 mA
sink then drags the discharged output negative. Note what is peculiar to it:
`'vsup'` = 2.97 V sets `EN` 0.66 V *below* the 3.63 V VIN the ramp starts from,
which is this bench's own pre-#178 convention (see "SUPPLY AXIS" in the
testbench header), and the `*_125c_2.97v` column is where both records put
their worst `vout_at_max_vin_v` outliers. That is a finding for a follow-up,
not something #178 fixes. **That follow-up is #187, and the hunch was right** —
see "#187" below: the convention, not the design, and the whole
`*_125c_2.97v` column was reading low because of it.

**Ramp-rate caveat, stated because it is real**: rate independence was measured
at tt/27 °C (1.2 mV over a 7.5× rate range) and confirmed against a static hold
at ss/−40 °C (3 mV). It is *not* rate-independent everywhere: a 765 V/s hold
probe at ss/−40 °C read 0.581 V against the 266 V/s matrix's 0.513 V, so at the
cold/slow corners a faster ramp does inflate the number. 266 V/s is inside the
validated window at both corners checked; a bench-wide per-corner rate sweep
was not run.

#### What `thermal`'s re-run found (record `20260926-052517-eba96ae`)

> **Superseded by `#189` (`20260926-095154-f6ab418`, 15/15 PASS, 0 of 15 corner
> logs carrying a diagnostic).** This subsection is kept as written — the same
> convention the `psrr-dc` and `loop-gain` paragraphs below use — because its two
> candidate mechanisms are exactly what `#189` had to discriminate between, and
> **neither** of them was the answer. See "#189" immediately below for the
> located failures, the measured cause (one node's supply classification in the
> seed card) and the superseding record.

**Not zero diagnostics — 2 of 15 corners still trip the `#171` gate, and that is
reported rather than suppressed.** The count falls from **14 of 15** corner logs
(132 marker hits) in the superseded `20260825-104426-933dfdd` to **2 of 15**
(18 hits): `ss_27c_2.97v` and `sf_27c_2.97v`, both on
`Dynamic gmin stepping failed` → `True gmin stepping failed` →
`source stepping failed`, each time recovered by ngspice's own "Transient op"
fallback. `corner-run.py` forces both to `FAIL` with
`solver diagnostic: Warning: Dynamic gmin stepping failed`, which is the gate
working as designed.

**The residual is not the one-card seeding limitation.** Re-running the
**ascending** sweep *alone* at `ss_27c_2.97v` — the sweep whose own 80 °C start
point the `.nodeset` describes exactly — still prints 6 `gmin stepping failed`
plus 3 `source stepping failed`, and returns `trip_temp_c` = 150.6582 °C, the
same value to four decimals as the full two-sweep run. So the descending sweep's
deliberately-wrong 180 °C seed is *not* what produces them: a correctly seeded
ascending sweep flails too, somewhere along its own path rather than at its
start. Two candidate mechanisms, neither isolated here:

1. **The trip transition itself.** A `dc` continuation has no continuous branch
   to follow across a comparator threshold with positive feedback around it —
   VOUT collapses and the comparator latches over, so the solver has to jump. A
   *start* seed cannot help with a difficulty located at the crossing. This
   would make the residual a methodology limit of `dc temp` continuation, of the
   same family as (though distinct from) the `trip == reset` degeneracy #77
   found and #91 carries.
2. **The seed being derived at one supply.** Both surviving corners are
   `*_2.97v`, and the `.nodeset`'s VIN-relative values were measured at
   `vsup` = 3.30 V. A per-supply seed would settle this; 3.63 V is equally far
   from 3.30 V and is clean, which argues against it, but not decisively.

**Verdict: 12/15 → 13/15 PASS**, with three corners changing in each direction's
favour: `tt_27c_3.63v` and `ff_27c_3.63v` go FAIL → PASS (their −2.00 °C and
−8.00 °C hysteresis readings are now 0.00 °C), and `sf_27c_2.97v` goes
PASS → FAIL (0.00 °C → −12.00 °C, alongside its diagnostic). `ss_27c_2.97v`
stays FAIL with its negative hysteresis deepening from −2.37 °C to −12.34 °C.

**Every trip temperature moved up, substantially and consistently**: +13 to
+16 °C at eleven of the fifteen corners (e.g. `ss_27c_3.63v` 138.914 → 155.001,
`sf_27c_3.63v` 138.769 → 155.001, `tt_27c_3.30v` 150.587 → 165.001), while the
two corners that still carry a diagnostic barely moved (`ss_27c_2.97v` 150.632 →
150.658, `sf_27c_2.97v` 149.000 → 149.000). The whole matrix now trips between
**149.0 °C and 171.0 °C**, i.e. every corner above the 125 °C `min` bound and
closer to DR-005's 150 °C nominal target than the superseded record's
138.8–163.0 °C suggested.

**That shift must NOT be attributed to the seeding.** This record is also this
bench's **first run against the current DUT**: `thermal` was one of the four
benches deliberately left out of #69's re-run generation (see the 2026-08-25
record-generation note above) and was not part of #116's either, so its
superseded record was reported `STALE` in `measurements/characterization.md`
precisely because its netlist snapshot no longer matched the schematic — and #69
**re-sized the thermal-shutdown circuit this bench measures**, while #116
re-sized the pass device. The Thermal row's freshness goes `STALE` → `fresh`
with this record. Seeding and two DUT re-sizes changed together here; the two
effects are not separable from these two records, and this section does not
claim they are. (`dropout-vs-load` has no such confound: its superseded record
*was* #116's own re-run, i.e. the same DUT.)

**The `trip == reset` degeneracy is untouched, as #178 said it would be**:
hysteresis reads exactly 0.00 °C at thirteen corners and negative at the two
diagnosed ones. That is #77's finding, carried by #91, and a seed at the
sweep's start was never going to address it.

**Both benches' bullets under "The LDO's own testbenches" carry the same
numbers.**

Every "Exposed" verdict above is corroborated by the bench's own latest
committed corner logs already carrying a `singular matrix` / `gmin stepping
failed` / `out of range for ^` / `source stepping failed` diagnostic on a
majority of corners (see #174/#177/#178/#179/#180 for the exact counts) —
the same fingerprint `#164`/`#171` used to characterize the hazard, not just
an inference from the deck/testbench text.

**#177's correction to the two "Clear" rows is a strengthening, not a
weakening.** Both were graded on the wrong reason (the PWL's t = 0 value) and
both survive re-grading on the right one (`dc 0`, and no `dc` keyword at
all) — see the per-source table in "An EN edge alone does not satisfy the
first shape" above for the full four-way case split. No bench's verdict
changes except `current-limit`'s, which gains leg 3.

### #189: `thermal`'s last two corners — one node's supply classification in the seed card

**Verdict first: `15/15 PASS`, and `0 of 15` corner logs carry a `singular
matrix` / `gmin stepping failed` / `out of range for ^` / `source stepping
failed` marker, nor a single `Transient op` recovery.** Record
`20260926-095154-f6ab418` supersedes `20260926-052517-eba96ae`. The `#171`
solver-diagnostic gate is now satisfied mechanically on this bench, which it was
not after #178 (2 of 15) and emphatically was not before it (14 of 15).

**Neither of #178's two candidate mechanisms was the cause.** It was not the trip
bifurcation, and it was not that the seed had been derived at one supply. It was
that **one of the thirteen seeded nodes was written as if it tracked VIN when it
does not**.

#### Where the failures actually were

Answering that first, because it is what pointed at the cause. Re-running
`ss_27c_2.97v`'s ascending sweep alone under a pty (so ngspice's stderr
interleaves with its own ` Reference value : ` progress line and each diagnostic
can be attributed to a sweep point) puts all three failure rounds at **TEMP =
144, 146 and 148 °C** — the three points immediately *below* the 150.658 °C
crossing that run then reported, each one `Dynamic gmin stepping failed` → `True
gmin stepping failed` → `source stepping failed` → `Transient op finished
successfully`. Points 80–142 °C converge, and 152–162 °C converge with no gmin
stepping at all.

So the failures are in the crossing's own neighbourhood — which is exactly what
candidate 1 predicts, and is why it had to be ruled out by a *fix* rather than by
location. With the seed corrected (below) the same sweep crosses at
**163.001 °C** and prints **zero** failure markers anywhere, the real crossing
included. A `dc temp` continuation across this comparator's threshold is
therefore *not* intrinsically unsolvable here; the 144–148 °C flail was a badly
seeded solve breaking down just before a crossing it then mislocated.

#### The cause: `EA_TAIL` is not a VIN-tracking node

#178's card wrote `v(xldo.EA_TAIL)={vsup-0.836}`, putting it in the
"VIN-tracking, so write it relative to `'vsup'`" group with `EA_OUT`, `EA_CZ`,
`SS`, `BIASP` and `TS_CMP`. But `EA_TAIL` is the **source** node of the error
amplifier's PMOS input pair (`M_IN1`/`M_IN2`/`M_IN2S`): it sits one |Vgs| *above*
the pair's ground-referenced gate voltages (`FB`/`VREF` ≈ 1.2 V), not one drop
below VIN. Three cold-start `uic` settles of the unmodified testbench at
ss/80 °C, one per supply on the corner axis (each clean — zero solver
diagnostics), measure the difference directly:

| Seeded node | 2.97 V | 3.30 V | 3.63 V | slope (V/V) | classification |
|---|---|---|---|---|---|
| `EA_OUT` = `EA_CZ` | 2.09175 | 2.42993 | 2.76773 | 1.02 | VIN-tracking |
| `SS` | 2.96992 | 3.29992 | 3.62992 | 1.00 | VIN-tracking |
| `BIASP` | 1.96056 | 2.28001 | 2.60046 | 0.97 | VIN-tracking |
| `TS_CMP` | 2.96975 | 3.29967 | 3.62955 | 1.00 | VIN-tracking |
| **`EA_TAIL`** | **2.42179** | **2.50138** | **2.57694** | **0.24** | **not VIN-tracking** |
| `TS_REF` | 1.16139 | 1.19974 | 1.23646 | 0.11 | ground-referenced |
| `TS_SNS` | 1.48843 | 1.50963 | 1.52813 | 0.06 | ground-referenced |
| `NB` | 0.831276 | 0.841784 | 0.851316 | 0.03 | ground-referenced |
| `VOUT` | 1.80059 | 1.80070 | 1.80085 | 0.00 | ground-referenced |

Imposing slope 1.0 on a 0.24-slope node is a **−288 mV** error at
`vsup` = 2.97 V (2.134 V seeded against 2.42179 V measured) and **+217 mV** at
3.63 V. Only the low-supply side flailed; the sign-asymmetry of the circuit's
tolerance to a mis-seeded tail is *measured here, not explained* — it is why
#178 could note that "3.63 V is equally far from 3.30 V and is clean" and
correctly treat that as evidence against a supply-derivation story, when the real
variable was the node's slope rather than the derivation supply.

**The fix carries no new number.** The card now reads
`v(xldo.EA_TAIL)=2.4637` — the *same* value #178 measured at tt/80 °C/3.30 V,
with only its supply classification corrected from `'vsup'`-relative to absolute.
No per-supply seed mechanism was needed, and none was added: the acceptance
criterion that asked for one ("every node relative to `'vsup'`, or a
`.param`-driven card") turns out to describe a mechanism the card *already had* —
it was one node's membership in the group that was wrong.

#### A `.nodeset` is re-applied at *every* `dc` sweep point, not just the first

Worth recording separately, because it contradicts the natural reading that "a
seed can only fix a sweep's first point" — the reading that made candidate 1
attractive. At `ss_27c_2.97v`, ascending, 51 points:

| Ascending sweep at `ss_27c_2.97v` | gmin-stepping attempts | failure rounds | `trip_temp_c` |
|---|---|---|---|
| no `.nodeset` at all | ~every point, plus `singular matrix` | yes | — (probe stopped) |
| #178 card (`EA_TAIL={vsup-0.836}`) | essentially all 51 | 3 (at 144/146/148 °C) | 150.658 °C |
| #189 card (`EA_TAIL=2.4637`) | 3 (168/170/178 °C, all "completed") | **0** | **163.001 °C** |

A card that only constrained the 80 °C point could not change how 82–180 °C
solve — those start from their predecessor's solution — so ngspice must be
re-applying the nodeset as the first-iteration guess at each point. Two
consequences for this bench: a wrong value biases the *whole* continuation rather
than costing one point, and the one-card limitation (#178's limit 1, both sweeps
sharing the card) is a little less benign than "a wrong first guess at 180 °C"
suggested — though the descending sweep is now diagnostic-free too, so it is
still not costing anything measurable.

#### What the corrected matrix says

| Corner | #178 `trip_temp_c` | #189 `trip_temp_c` | #178 verdict | #189 verdict |
|---|---|---|---|---|
| `ss_27c_2.97v` | 150.658 °C (diagnosed) | **163.001 °C** | FAIL | PASS |
| `sf_27c_2.97v` | 149.000 °C (diagnosed) | **161.000 °C** | FAIL | PASS |
| the other 13 | unchanged | unchanged, to 3 decimals | PASS | PASS |

**The two diagnosed numbers were artifacts, and the corrected matrix is now
monotonic in supply at every process corner but `fs`.** Each process corner's
trip temperature should fall as the supply rises (it does: `tt` 169.0 → 165.0 →
161.0, `ss` **163.0** → 159.0 → 155.0, `ff` 171.0 → 169.0 → 165.0, `sf`
**161.0** → 159.0 → 155.0). Under #178's card `ss` read 150.658 → 159.0 → 155.0
and `sf` read 149.0 → 159.0 → 155.0 — both non-monotonic, both with the anomaly
at the diagnosed corner. `fs` remains non-monotonic (167.0 → 165.0 → 167.0) and
carries no diagnostic in either record, so it is not this defect.
The whole matrix now trips between **155.0 °C and 171.0 °C**, every corner above
the 125 °C `min` bound, and the run is also much cheaper: `ss_27c_2.97v` goes
from 457.0 s to 39.1 s of wall clock, the 15-corner total from ~1620 s to ~955 s.

**The `trip == reset` degeneracy is still there and is still not this issue's.**
`hysteresis_c` now reads exactly 0.00 °C at all fifteen corners, which *passes*
the `min: 0` bound but is not a measured 15 °C window either — it is #77's
finding, carried by #91. What #189 does settle is that the two **negative**
readings (−12.34 °C and −12.00 °C) were not a second, deeper form of it: they
were the same seeding defect as the diagnostics, and they are gone.

**What a conforming measurement of a hysteretic trip point would have to be**, if
#91 is ever to close: not one `dc temp` continuation but **two decks** — a
temperature staircase of *independent* cold-start `uic` transients, one run per
TEMP point, each starting from `EN` = 0 with `C_OUT` discharged and the
soft-start ramp held down (giving the trip direction by asking "does the block
come up at all at this TEMP?"), and the same staircase released from a
tripped-state seed for the reset direction. ngspice has no time-varying `TEMP`,
which is what forces the staircase to be a grid of separate runs rather than one
analysis, and is why this was sketched in #178 and again here rather than
attempted: it is a per-TEMP-point corner grid on top of the existing
process × supply matrix, and it is not needed for the trip point this bench
actually bounds.

#### How it was run

`corner-run.py` has no remote/batch backend (see `--backend` under "Writing a new
Monte Carlo experiment" and 2AMLogic/klayout-tools#2482), so the 15-corner matrix
ran through the runner itself — one `ngspice` process at a time, sequentially,
~16 minutes total — and the probes above are single-corner debug runs, one
`ngspice -b` each. No `ngspice` grid was hand-launched.

### #187: `dropout-vs-load`'s `EN`-below-VIN supply convention — an enable-path headroom limit, and the bench convention that walked into it

`dropout-vs-load` was the only bench in `sim/` that drove `EN` off the VIN rail.
Every other bench sets `VVIN` to `'vsup'` and `EN`'s high level to that same
`'vsup'`; this one pinned VIN at 3.63 V for *every* corner and let `'vsup'`
drive `EN` alone — a convention inherited unchanged from the pre-#178 `dc`
sweep, whose first swept point was 3.63 V independently of the supply axis. At
the `*_2.97v` corners that put `EN` **0.66 V below VIN**, and at
`fs_125c_2.97v` it stopped the block coming up at all: record
`20260926-043132-eba96ae` reported `vout_at_max_vin_v` = **−7.4521 V** there
(−14.0589 V in the record before it) with **zero** solver diagnostics — a
physically realizable solution of the circuit *as the bench drove it*, not a
Newton artifact, which is exactly why the `#171` gate did not catch it.

**It is a static enable-path headroom limit, not a start-up branch.** Bring the
loop up with `EN` = VIN = 3.63 V at fs/125 °C (VOUT = 1.82019 V averaged over
0.85–0.95 ms), then drop `EN` to 2.97 V at 1 ms while it is regulating: `BIASP`
steps 2.81460 → 2.90516 V, `EA_OUT` is pushed to 3.60697 V (≈ VIN), and VOUT
collapses to −6.99 V by 5.5 ms. Nothing about the cold start is implicated — the
block cannot *hold* regulation off-rail. The dependence on (VIN − `EN`) is a
monotone cliff, not a coin flip:

| `EN` high level (VIN = 3.63 V) | VIN − `EN` | settled V(VOUT), fs/125 °C |
|---|---|---|
| 2.97 V | 0.66 V | **−7.45 V** (collapsed) |
| 3.00 V | 0.63 V | 1.68637 V (out of the ±2 % window) |
| 3.10 V | 0.53 V | 1.78256 V |
| 3.20 V | 0.43 V | 1.79529 V |
| 3.30 V | 0.33 V | 1.79793 V |
| 3.63 V | 0 V | 1.79862 V |

**Mechanism, with series ammeters in the clamps' drains** (a scratch flattened
netlist — `design/ldo_3v3in_1v8out.sch` is untouched). `EN` gates five PMOS
shutdown clamps whose *sources are VIN* (`design/README.md` →
"Enable/shutdown"), so their gate drive is VIN-referenced, not
threshold-referenced:

| fs/125 °C, VIN = 3.63 V | I(`M_ENP`) → `EA_OUT` | I(`M_ENP2`) → `BIASP` | I(`M_TAIL`) (EA tail) | `BIASP` |
|---|---|---|---|---|
| `EN` = 3.63 V (at the rail) | 39 pA | 62 pA | 3.476 µA | 2.81460 V |
| `EN` = 2.97 V (0.66 V down) | 1.377 µA | 1.639 µA | **1.003 µA** | 2.90516 V |

Both clamps come up four to five decades off the leakage floor, and the damage
compounds: `M_ENP2`'s injection lifts `BIASP` by 90.6 mV, and `BIASP` gates
*every* PMOS current source in the block, so the error amplifier's own tail
current falls to a third. The clamp current into `EA_OUT` (1.377 µA) then
exceeds the entire tail current that has to sink it (1.003 µA) — `EA_OUT` is
dragged to VIN, `M_PASS` turns off, and the bench's ideal 50 mA sink discharges
VOUT below ground. The −7.45 V magnitude is pure bench artifact (−I·t/C_OUT,
with no clamp diode in the testbench); only its *sign* carries information.

**Attribution, one clamp at a time** (same corner, same deck, each clamp's gate
moved to a full-rail node in turn while the rest keep 2.97 V): re-railing
`M_ENP` alone gives 1.96001 V, `M_ENP2` alone gives 1.69625 V, `M_ENP5` alone
leaves it collapsed at −7.48 V, and all six PMOS clamps together give
1.79839 V. So it takes *both* dominant clamps to explain it, and each alone
leaves a residual error in the opposite direction — which is why the failure is
a cliff rather than a gradual droop.

**Why that corner and no other, and the column that was quietly low.** 125 °C
maximizes the clamps' subthreshold conduction while `fs` (slow PMOS) minimizes
the intended PMOS currents that must overcome it. The superseded record's whole
`*_125c_2.97v` column was already reading low for the same reason, which is the
signature that says "systematic mechanism", not "one flaky corner":

| Corner | `vout_at_max_vin_v` @ 2.97 V | @ 3.30 V | @ 3.63 V |
|---|---|---|---|
| `tt_125c` | 1.76943 V | 1.79848 V | 1.79864 V |
| `ss_125c` | 1.78627 V | 1.79851 V | 1.79858 V |
| `sf_125c` | 1.79211 V | 1.79859 V | 1.79863 V |
| `ff_125c` | 1.71701 V | 1.79833 V | 1.79870 V |
| `fs_125c` | **−7.4521 V** | 1.79793 V | 1.79862 V |

**Verdict: a testbench-convention artifact, not a design limitation.**
`design/README.md`'s "Enable/shutdown" section specifies `EN` as "active-high,
full-rail (0 V / VIN)" — the enable input is VIN-referenced by construction, and
`sim/enable-shutdown` exercises the `EN` edges themselves with `'vsup'` = VIN.
This bench was the only one driving `EN` off-rail, so the fix restores the
documented interface rather than retuning the circuit (which #187 is explicitly
out of scope to touch).

**The fix.** `VVIN` now ramps 0 → `'vsup'` by 100 µs, holds to 6 ms and walks
down to **`'vsup'` − 2.13 V** by 14 ms, with `EN`'s high level at that same
`'vsup'` — i.e. `'vsup'` finally means the DUT's actual supply on this bench
too. `vout_at_max_vin_v` is consequently VOUT at VIN = `'vsup'` rather than at a
pinned 3.63 V, so a light-headroom regulation check finally varies with the
supply axis it is indexed by (its 0.5–3.7 V sanity band is unchanged).

**Why the ramp's endpoint tracks `'vsup'` instead of staying at 1.5 V — measured,
and it took two matrix runs to get right.** The obvious version of the fix keeps
the endpoint pinned at 1.5 V, which makes the *rate* per-supply
(183.8 / 225.0 / 266.3 V/s) because the 6–14 ms window is fixed. #187's first
full re-run did exactly that (record `20260926-100003-0b63ae4`) and it moved
`dropout_v` by **up to 20.4 mV across the supply axis** at the cold/slow
corners — where the superseded record's supply spread had been under 0.1 mV:

| Corner | 2.97 V (183.8 V/s) | 3.30 V (225.0 V/s) | 3.63 V (266.3 V/s) | spread |
|---|---|---|---|---|
| `ss_27c` | 0.379823 V | 0.390724 V | 0.400265 V | 20.4 mV |
| `sf_-40c` | 0.535094 V | 0.545444 V | 0.554380 V | 19.3 mV |
| `tt_-40c` | 0.452920 V | 0.463248 V | 0.472185 V | 19.3 mV |
| `fs_125c` | 0.432667 V | 0.432425 V | 0.432251 V | 0.4 mV |

It is monotone with rate and in the direction #178's own ramp-rate caveat
records (a slower ramp reads *lower*, i.e. closer to the zero-rate answer), so
it is real rate-dependence at those corners, not noise — and it would have made
the supply axis carry a ramp-rate effect it has no business carrying. Holding
the endpoint at `'vsup'` − 2.13 V instead keeps the rate at a constant
**266.3 V/s** at all 45 corners, the same rate every earlier record ran, and
`'vsup'` − 2.13 V (0.84 / 1.17 / 1.50 V) still ends far below every corner's
crossing (the largest is `ff`'s ~2.44 V). Held that way the dropout number is
not merely close to the superseded record's, it is **identical**:
`fs_125c_2.97v`'s crossing VIN reads 2.19615 V under both conventions, i.e.
`dropout_v` = 0.432153 V to six digits. So the correction moves
`vout_at_max_vin_v` and nothing else.

Both runs are kept as evidence, per the append-only rule: the shipped record
`20260926-102849-0b63ae4` supersedes `20260926-100003-0b63ae4`, which supersedes
#178's `20260926-043132-eba96ae`. The intermediate record is the measurement that
motivated the constant-rate endpoint, not a discarded draft.

#### What the corrected bench measures (record `20260926-102849-0b63ae4`)

**The outlier is gone and nothing else moved.** All 45 corners'
`vout_at_max_vin_v` now land in **1.79835–1.79913 V**, inside the 0.5–3.7 V
sanity band — including the whole `*_125c_2.97v` column that was reading
1.717–1.792 V, and `fs_125c_2.97v` itself, which goes from −7.4521 V to
1.79839 V. Zero solver diagnostics and zero timeouts on all 45 corners, as in
the record it supersedes.

**`dropout_v` is reproduced, not merely "in family": the largest change at any
of the 45 corners is 0.010 mV**, and the 3.63 V column — the one column whose
stimulus is byte-identical to #178's — agrees to all six digits at every
process/temperature point. The supply spread is back under 0.104 mV (it was up
to 20.4 mV in the intermediate run), so the corrected convention costs the
dropout measurement nothing:

| Corner | 2.97 V | 3.30 V | 3.63 V | supply spread |
|---|---|---|---|---|
| `ss_125c` | 0.329970 V | 0.329990 V | 0.330005 V | 0.035 mV |
| `fs_125c` | 0.432147 V | 0.432207 V | 0.432251 V | 0.104 mV |
| `ff_125c` | 0.672974 V | 0.673028 V | 0.673069 V | 0.095 mV |
| `tt_-40c` | 0.472192 V | 0.472188 V | 0.472185 V | 0.007 mV |

**The verdict against the ratified row is unchanged: 0/45 PASS**, matrix spanning
**0.32997–0.67307 V** against the 300 mV bound. That is the design's standing gap
(#116/DR-011 owns it), and #187 deliberately did not touch it — the point of this
re-run is that the Dropout row's evidence no longer contains a corner whose
sanity measurement is a bench artifact nobody could explain.

**One convention mismatch left standing, deliberately out of scope**:
`sim/line-regulation` also drives `EN` at `'vsup'` while its `VVIN` is its own
source (a line step, not `'vsup'`), so the same off-rail geometry is reachable
there. Nothing in #187's evidence says that bench is *currently* wrong — its
step range and corner set differ — and re-running it is a separate bench's
re-verification, so it is filed rather than folded in here. **Resolved by #196
— it *was* reachable there, and it was the whole of that bench's failing
column: see the next section.**

### #196: `line-regulation`'s `EN`-below-VIN convention — the same geometry, and the five corners it accounted for

`line-regulation` was the last bench in `sim/` driving `EN` off the VIN rail,
and the reason it survived #187 is that the easy fix does not apply to it.
`dropout-vs-load` could simply let `'vsup'` set VIN *and* `EN`, because its VIN
axis was an artifact. Here VIN is the **independent variable**: `VVIN` is this
bench's own source, `alter`-ed between 2.97 V and 3.63 V *inside* every corner,
while `'vsup'` is fixed per corner. So at the `*_2.97v` corners the
VIN = 3.63 V point ran with `EN` **0.66 V below VIN** — #187's geometry exactly,
including the part that makes it invisible: the clamps out-drive the amplifier
without producing a single solver diagnostic, so `#171`'s gate never sees it.

**The convention, and why this one.** `EN`'s high level is now the
**instantaneous VIN** at every measured point: each point sets one literal
(`set vinpt = <v>`) and points both `alter vvin` and
`alter @ven[pwl] = [ 0 0 100u 0 101u $vinpt 10 $vinpt ]` at it, so VIN and
`EN` cannot drift apart in a later edit. `design/README.md` →
"Enable/shutdown" specifies `EN` as "active-high, full-rail (0 V / VIN)", so
this is the documented interface at 2.97 V and at 3.63 V alike. The two
alternatives #196 tabled were both rejected on the record: **`EN` = 3.63 V at
every corner** puts `EN` *above* VIN at the low point — not the #187 collapse
(the VIN-sourced PMOS clamps go harder off, not on), but a second departure
from the documented interface and an over-drive of the `EN`-gated NMOS
switches, for no gain; **collapsing the supply axis** for this row is a change
to the ratified corner matrix's meaning, which `CLAUDE.md` routes through a
decision record. Nothing in `design/` or `spec/` moves — this is a bench
convention, and #196 was explicitly out of scope to touch either.

**Confirmed, corner by corner: all five failures were the artifact.** The
`*_125c_2.97v` column of record `20260926-001833-228fbc7` was the entire set of
FAILs, and re-running those five corners with `EN` at the instantaneous VIN
takes every one of them into the band the other 40 corners already occupied.
The `VIN = 2.97 V` points are **not** changed by the convention (`EN` =
`'vsup'` = 2.97 V = VIN there already), and they reproduce the superseded
record's own settled values on a different host to within 0.03 mV — so the
whole of the change is at the `VIN = 3.63 V` points:

| Corner | `v(vout)` @ 3.63 V, 1 mA | `line_reg_1ma` | `line_reg_50ma` |
|---|---|---|---|
| `tt_125c_2.97v` | 1.78023 V → **1.80114 V** | 31.167 → **0.496970** | 43.918 → **0.340909** |
| `ss_125c_2.97v` | 1.79206 V → **1.80106 V** | 13.147 → **0.475758** | 18.309 → **0.336364** |
| `ff_125c_2.97v` | 1.74468 V → **1.80125 V** | 85.161 → **0.513636** | 123.409 → **0.371212** |
| `sf_125c_2.97v` | 1.79628 V → **1.80103 V** | 6.745 → **0.443939** | 9.536 → **0.343939** |
| `fs_125c_2.97v` | **−6.70668 V** → **1.80126 V** | 12890.2 → **0.595454** | 24026.1 → **0.353030** |

(mV/V against the row's 5 mV/V bound. `fs` is the corner #187 found collapsed on
the other bench; its four points are the 200 ms ones of the behavioural-source
cross-check below. The other four rows' "after" numbers are a **short-window**
re-run — the same four points and the same `EN` convention, but `tran 10u 2m
uic` measured over its 1–2 ms tail instead of 200 ms/199–200 ms, for the
runtime reason in "The 45-corner matrix, re-run under this convention" below,
which also reports what those two corners read at the full 200 ms window.)

**The short window is validated, not assumed.** `v(vout)` is flat to six
digits across the 1–2 ms window at every one of these corners
(`min` = `max` = 1.80081 V at `tt`, for instance), the 1–2 ms average
reproduces the superseded record's own 199–200 ms average at the two
unchanged VIN = 2.97 V points, and where the same corner was run **both** ways
under the new convention the two windows agree far inside the effect being
measured:

| Corner | `line_reg_1ma`, 2 ms | 200 ms | `line_reg_50ma`, 2 ms | 200 ms |
|---|---|---|---|---|
| `ss_125c_2.97v` | 0.475758 | 0.483333 | 0.336364 | 0.336364 |
| `ff_125c_2.97v` | 0.513636 | 0.563636 | 0.371212 | 0.368182 |

**Independent cross-check on the implementation itself.** "`EN` = the
instantaneous VIN" can also be written continuously rather than per-point, as a
behavioural source multiplying a dimensionless 0 → 1 enable ramp by the supply
node: `BEN EN 0 V='v(VIN)*v(ENRAMP)'`. Built and run at `fs_125c_2.97v`, the
worst corner of the superseded record, over the shipped 200 ms points it
returns `v(vout)` = 1.80087 / 1.80126 / 1.79839 / 1.79862 V, i.e.
**0.595454 / 0.353030 mV/V**. The shipped deck keeps the plain `vsource` +
`alter` shape instead, so `EN` stays a `.save i(ven)`-able independent source
in the form `sim/enable-shutdown` and the `#171`/`#172` contract describe — and
the 45-corner record below reproduces that behavioural-source cross-check at
that corner to **all six digits on all four points** (1.80087 / 1.80126 /
1.79839 / 1.79862 V), so the two ways of writing "`EN` = the instantaneous VIN"
are not merely close, they agree exactly.

**What `'vsup'` means on this bench now: nothing in the stimulus.** It is a
pure corner *label* here — the decks for a corner's 2.97 V / 3.30 V / 3.63 V
variants differ only in a `.param vsup=` line this bench no longer references,
so the three supply columns are the same experiment and are expected to come
back identical. That is worth keeping rather than collapsing: the supply axis
becomes a reproducibility check on the harness instead of a stimulus axis.
`#118` had already classified this axis as a *negative control* ("the deck
`alter`s VIN itself, so that axis cannot reach the measured quantity") and
found 22 of 30 cells disagreeing across it by more than 2×. That disagreement
was harness-side in two instalments: **22/30 → 15/30** when `#172` replaced the
unconstrained `.op` with the `#171` cold-start contract, and **15/30 → 0/30**
here. In the 45-corner re-run below it is **identically zero**: across all 15
(process, temperature) groups and both measurements, the largest spread between
a group's 2.97 V, 3.30 V and 3.63 V columns is **0.000000 mV/V**. `#118`'s
negative control is finally negative.

#### The rest of `sim/` — swept for the same geometry, and clean

Every other bench in `sim/` was re-read for #196 (at `origin/main` `d9a46fa`,
2026-09-26). `line-regulation` was the last holdout, and with it fixed **no
bench drives `EN` below VIN at any simulated point**:

| Bench(es) | `VVIN` | `EN` | Geometry |
|---|---|---|---|
| `iq`, `load-transient`, `loop-gain`, `thermal`, `psrr-dc`, `ic-screen-125c-{b,h,v}`, `mc-ic-screen-{a,b}` | `'vsup'` | `'vsup'` (plain DC) | `EN` = VIN |
| `enable-shutdown`, `load-regulation`, `current-limit` | `'vsup'` | `pwl(… 'vsup' …)` | `EN` = VIN when asserted |
| `startup`, `mc-output-accuracy`, `ic-screen-125c-c` | `'vsup'` | `PULSE(0 'vsup' …)` | `EN` = VIN when asserted |
| `dropout-vs-load` | `PWL(0 0 100u 'vsup' 6m 'vsup' 14m 'vsup-2.13')` | `PULSE(0 'vsup' …)` | `EN` = VIN at the plateau, `EN` ≥ VIN on the down-ramp (post-#187) |
| `pex-post-layout` | `DC {vvin}` | `DC {vvin}` | `EN` = VIN |
| `pdk-smoke` | — | — | no DUT enable |
| **`line-regulation`** | **`alter`-ed 2.97/3.63 V per point** | **`alter`-ed to the same per-point literal** | **`EN` = VIN (this issue)** |

One nuance found while sweeping, deliberately **not** folded in here:
`psrr-dc` drives `VVIN` as `DC 'vsup' AC 1` and `EN` as a plain DC `'vsup'`, so
in the `ac` analysis the 1 V supply perturbation appears on VIN while `EN` is a
small-signal *ground*. At DC the geometry is clean (`EN` = VIN, which is all
#196 asked about), but per the documented full-rail interface a real supply
ripple would appear on `EN` too, which is a different question about a
different analysis type — **filed as #201** rather than decided here.
**Answered, and the answer is "immaterial": see "#201" below.** Both
conventions were run over the full 45-corner matrix; the largest movement in
any graded PSRR measurement at any corner is **0.0017 dB**, so the bench keeps
its AC-grounded `EN` and now says in its header why.

#### The 45-corner matrix, re-run under this convention (#196 second increment / #200)

**Record `20260926-200304-35b7392` supersedes `20260926-001833-228fbc7`** and is
this bench's first full matrix under the `EN`-at-the-instantaneous-VIN
convention: **45/45 corners PASS, overall PASS**, zero solver diagnostics, zero
timeouts (3914.8 s serial, worst corner 306.7 s at `ss_-40c_3.30v`).

**The row's verdict on its own merits.** `line_reg_1ma_mv_per_v` spans
**0.216667–0.595454 mV/V** (worst at the whole `fs_125c` row) and
`line_reg_50ma_mv_per_v` **0.271212–0.368182 mV/V** (worst at `ff_125c`),
against the ratified **< 5 mV/V** bound — better than 8× margin at the binding
corner. The Line regulation row of `measurements/characterization.md` therefore
moves **FAIL → PASS** and its freshness **STALE → fresh**. That is a bench
correction removing an artifact, **not** a design change: nothing in `design/`
or `spec/` moved in #196 or here, and the DUT is the same post-#116/#139
schematic the superseded record ran against.

**The five `*_125c_2.97v` corners land where #196's short-window probes said
they would** (predicted band 0.44–0.60 at 1 mA, 0.34–0.37 at 50 mA):

| Corner | `line_reg_1ma` | `line_reg_50ma` |
|---|---|---|
| `tt_125c_2.97v` | 31.16667 → **0.510606** | 43.91818 → **0.337879** |
| `ss_125c_2.97v` | 13.14697 → **0.483333** | 18.30909 → **0.336364** |
| `ff_125c_2.97v` | 85.16061 → **0.563636** | 123.4091 → **0.368182** |
| `sf_125c_2.97v` | 6.745455 → **0.450000** | 9.536364 → **0.342424** |
| `fs_125c_2.97v` | 12890.22 → **0.595454** | 24026.12 → **0.353030** |

The three corners #196 probed at the shipped 200 ms window (`ss`, `ff`, `fs`)
reproduce to **all seven stored digits**; the two it could only probe at the
2 ms window (`tt`, `sf`) land 0.014 / 0.006 mV/V away, which is the window
difference that section already quantified, not a new effect.

**The supply axis is now exactly the negative control `#118` said it should
be.** Across all 15 (process, temperature) groups and both measurements, the
spread between a group's 2.97 V / 3.30 V / 3.63 V columns is **0.000000 mV/V** —
the 45-corner matrix is 15 distinct experiments repeated three times, and the
three repeats agree bit-for-bit. `'vsup'` is referenced by nothing in this
bench's stimulus, so this is the prediction #196 committed to, confirmed at full
length rather than argued.

**The control that says the re-run changed the artifact and not the
measurement: the `*_3.63v` column.** Under *both* conventions that column ran
`EN` = VIN = 3.63 V at the high endpoint — it is the one column the old deck
measured in contract at the endpoint that moved. It is reproduced across the new
record to within **0.0061 mV/V** at all 30 of its cells (largest:
`fs_125c_3.63v`, `line_reg_50ma`, 0.346970 → 0.353030), mirroring #197's own
"largest change 0.010 mV" check on the sibling bench. The other two columns
move, and by more than the five FAILs alone suggest:

| Column | `EN` − VIN at the VIN = 3.63 V point (old deck) | cells changed by > 0.01 mV/V | largest change |
|---|---|---|---|
| `*_2.97v` | −0.66 V | 21 / 30 | 24025.8 mV/V (`fs_125c_2.97v`, 50 mA) |
| `*_3.30v` | −0.33 V | 10 / 30 | 0.486364 mV/V (`fs_125c_3.30v`, 1 mA) |
| `*_3.63v` | 0 V | **0 / 30** | 0.006061 mV/V (`fs_125c_3.63v`, 50 mA) |

So the artifact was not confined to the five corners that *failed*: it
perturbed 30 of 45 corners, including at the milder 0.33 V offset, and most of
that perturbation simply stayed inside the 5 mV/V bound. The largest
non-failing example is `fs_27c_2.97v`, `line_reg_50ma`: 3.13636 → 0.287879
mV/V, a PASS both times. **Read every pre-#196 `line-regulation` number in this
file with that in mind** — only the `*_3.63v` column of those records is
unaffected by the convention.

**Why this took a second increment, and what it cost.** #196's own PR could not
hold the run: on that sweep host (shared 8-vCPU) one corner of this deck took
**578.9 s** against 41.7 s for the same corner in the superseded record,
extrapolating to ~7 h of serial `ngspice`, and an incomplete matrix must not be
minted as a record (the rule `#177` followed). The gap was filed as **#200** and
is closed here by running the same one command on a host that could hold it. The
runtime figures that follow settle what that 578.9 s was: on an arm64 Darwin
host of the same class as the superseded record's, the matrix takes **3914.8 s
against that record's 2757.3 s**, and `tt_-40c_2.97v` **60.5 s against 41.7 s**
— i.e. the new convention costs about **1.4×** (four `alter`-ed `pwl`
re-evaluations instead of one fixed `EN` rail), and the remaining ~10× was the
sweep host. `corner-run.py` still has no batch backend and this bench's
four-solve `alter` chain still is not expressible as a `klt sim` request
(2AMLogic/klayout-tools#2482), so the matrix still runs one `ngspice` at a time.

### #201: `psrr-dc`'s `EN` is an AC ground — checked over the full matrix, and immaterial

This is the nuance the #196 bench sweep above found and deferred, now settled by
measurement. **Outcome: the bench does not change.** `sim/psrr-dc` keeps
`VEN value='vsup'` (no `AC` component), and the testbench header now carries an
"EN stimulus convention (issue #201)" section saying so deliberately, with these
numbers behind it.

#### The question

`psrr-dc` drives `VVIN` as `DC 'vsup' AC 1` and `VEN` as a plain DC `'vsup'`, so
inside the `ac` analysis `EN` is a **small-signal ground** while VIN carries the
1 V perturbation. `design/README.md` → "Enable/shutdown" specifies `EN` as
"active-high, full-rail (0 V / VIN)", and **#187** established that the five
shutdown clamps `M_ENP`/`M_ENP2`/`M_ENP3`/`M_ENP4`/`M_ENP5` are PMOS **with
their sources at VIN**, so their gate drive is `VIN − EN`. An `EN` driven off
the VIN rail itself would hold `VIN − EN` constant under supply ripple; this
bench ripples it at the full 1 V amplitude. The two EN-gated NMOS switches
`M_ENN`/`M_ENN2` (sources at 0) see the mirror image — quiet here, rippling
under the other convention. Whether any of that reached the reported PSRR was
unmeasured.

Note the scope difference from #196/#187, because the family resemblance is
misleading: those were **DC / large-signal** faults — `EN` sitting 0.66 V *below*
the instantaneous VIN at a simulated operating point, turning the clamps on and
breaking regulation. `psrr-dc`'s DC geometry was never in question (`EN` = VIN =
`'vsup'` at every corner, clamps at `Vgs` = 0). Only the small-signal partition
of the perturbation between the two sources was.

#### How it was measured

The **full 45-corner matrix, twice on one host**, one run per convention, with
`--no-write` so neither arm mints an evidence record — neither is a new claim
about the DUT, and an off-convention variant record would pollute this bench's
append-only record set with a deck that is not the shipped one. (Same disposition
#179 used for its seeded/unseeded comparison: per-corner numbers plus a recipe
here, no alternate record.)

- **Arm A** — the shipped stimulus, exactly as committed.
- **Arm B** — the one-line change `VEN value="DC 'vsup' AC 1"`, so `EN` carries
  the identical perturbation and `VIN − EN` is quiet at small signal.

Serial on one x86_64 Linux sweep host (shared, load average 7–9 during arm A):
**≈1420 s** for arm A and **≈890 s** for arm B. As in #196, `corner-run.py` has
no batch backend and this deck's `alter`-chained two-point `ac` shape is not
expressible as a `klt sim` request (2AMLogic/klayout-tools#2482), so both arms
ran one `ngspice` at a time.

#### Arm A first: the committed record reproduces, across a host change

Before comparing anything, arm A was checked against the record the issue names.
**Record `20260926-033606-4a9ec09` reproduces at all 270 measurement cells** (45
corners × 6 measurements) to the six significant digits `corner-run.py` prints —
and it does so across a platform change, that record having been taken on arm64
Darwin and this run on x86_64 Linux. That is the control that makes the arm-A /
arm-B delta below attributable to the stimulus and to nothing else.

#### The comparison, per corner

The corners #201 named, all four graded measurements, arm A → arm B in dB:

| Corner | `psrr_1khz_1ma_db` | `psrr_100khz_1ma_db` | `psrr_1khz_50ma_db` | `psrr_100khz_50ma_db` |
|---|---|---|---|---|
| `tt_27c_3.30v` | 23.2333 → 23.2334 (+0.0001) | 33.5185 → 33.5191 (+0.0006) | 23.3297 → 23.3298 (+0.0001) | 11.3201 → 11.3207 (+0.0006) |
| `ff_125c_2.97v` | 20.5327 → 20.5321 (−0.0006) | 35.5209 → 35.5209 (0.0000) | 20.6837 → 20.6828 (−0.0009) | 11.9587 → 11.9585 (−0.0002) |
| `ff_125c_3.30v` | 21.5483 → 21.5477 (−0.0006) | 35.5061 → 35.5061 (0.0000) | 21.7400 → 21.7391 (−0.0009) | 11.7621 → 11.7618 (−0.0003) |
| `ff_125c_3.63v` | 22.4002 → 22.3996 (−0.0006) | 35.4940 → 35.4940 (0.0000) | 22.6159 → 22.6150 (−0.0009) | 11.7135 → 11.7133 (−0.0002) |
| `fs_125c_2.97v` | 20.2970 → 20.2959 (−0.0011) | 35.5237 → 35.5231 (−0.0006) | 20.4618 → 20.4601 (−0.0017) | 12.1666 → 12.1656 (−0.0010) |
| `fs_125c_3.30v` | 21.3564 → 21.3553 (−0.0011) | 35.5170 → 35.5164 (−0.0006) | 21.5612 → 21.5596 (−0.0016) | 11.9448 → 11.9437 (−0.0011) |
| `fs_125c_3.63v` | 22.2429 → 22.2417 (−0.0012) | 35.5135 → 35.5130 (−0.0005) | 22.4704 → 22.4687 (−0.0017) | 11.8705 → 11.8694 (−0.0011) |

And the whole matrix, not just those seven:

| Quantity | Result over all 45 corners |
|---|---|
| Largest \|Δ\| in any graded PSRR cell (180 cells) | **0.0017 dB** — `psrr_1khz_50ma_db` at `fs_125c_3.63v`, 22.4704 → 22.4687 dB, **0.0076 % of the reading** |
| Per-measurement worst \|Δ\| | `psrr_1khz_1ma_db` 0.0012 · `psrr_100khz_1ma_db` 0.0006 · `psrr_1khz_50ma_db` 0.0017 · `psrr_100khz_50ma_db` 0.0011 |
| `vout_seed_1ma_v` / `vout_seed_50ma_v` | **identical at all 45 corners** — the DC operating point each `ac` linearizes around does not move at all, which is the direct confirmation that this is a small-signal-only question |
| Verdicts | **none change.** 0/45 corners PASS under both arms; `psrr_100khz_1ma_db` passes 45/45 under both; the other three fail 45/45 under both |

For scale: the row's standing FAIL is a ~27 dB shortfall at 1 kHz and ~8 dB at
100 kHz / 50 mA. **0.0017 dB is four orders of magnitude below the thing in
question**, and no plausible tightening of the bound would make it visible.

#### The residue behaves the way the mechanism predicts

Worth one paragraph, because "the numbers barely moved" is only convincing if
the little that *did* move moved where it should. At `EN` = VIN the five clamps
sit at `Vgs` = 0, so the only route from `VIN − EN` into the loop is their
subthreshold `gm` plus overlap capacitance — a path that strengthens with
temperature and with fast PMOS. Accordingly **all 30 negative-going cells of the
180 lie in the 125 °C plane**, and within it the ordering is `fs_125c` (all four
measurements move) → `ff_125c` (three) → `tt_125c` (two) → `ss_125c` (one) →
`sf_125c` (none). Those are the same corners where #187 measured these clamps
carrying 1.377 µA / 1.639 µA once they were genuinely biased on. Everywhere else
the difference is a uniform +0.0001 / +0.0006 dB, i.e. the print floor.

#### The convention, and where it is written down

**Chosen: keep the AC-grounded `EN`.** Written into
`sim/psrr-dc/testbench/tb_psrr_dc.sch`'s header ("EN stimulus convention (issue
#201)") and into `sim/psrr-dc/experiment.json`'s `claim`, so the record minted by
any future run carries it. The reasons, in the order that decided it:

1. **It is measured to be immaterial**, not argued to be — the table above.
2. **It is the one-stimulus supply-rejection measurement.** Exactly one
   small-signal source is live (the supply); `EN` and `VREF` are held quiet, so
   `-vdb(vout)` is the VIN → VOUT path and nothing else. Arm B measures the
   supply path *in parallel with* an enable-path term — a different quantity
   from the one the ratified row names, even though here the two agree to
   0.002 dB.
3. **The DC contract is already satisfied**, which is what #196 was actually
   about, and the identical `vout_seed_*` readings prove it directly.

Because the deck does not change, **no superseding record is minted**: the PSRR
row of `measurements/characterization.md` still cites `20260926-033606-4a9ec09`
and stays `fresh` (the header edits are xschem metadata and do not netlist —
`build_characterization_report.py --check` passes unchanged), and no signoff pin
moves. This is a documentation-of-a-measurement change, and deliberately nothing
more.

**Re-check this if the DUT changes.** It is a measurement about the present
`M_PASS` / `M_ENP*` sizing, not a theorem. A material resize of the pass device
or the clamps should re-run the recipe below before the conclusion is recited.

#### `sim/loop-gain` — confirmed unaffected, not assumed

`psrr-dc` and `loop-gain` are the only two `ac` benches in `sim/` (checked
mechanically: every other `experiment.json` has zero `ac` commands in its
`analyses`, and `pex-post-layout` has no `ac` deck at all). `loop-gain`'s
netlisted sources are:

```
VVIN VIN 0 'vsup'
VEN  EN  0 'vsup'
VVREF VREF 0 DC 1.2 AC 1
```

The supply is **not** perturbed — the injection is at `VREF`. So VIN and `EN`
are *both* AC grounds, `VIN − EN` has zero AC component, and the clamps see
exactly the constant gate drive the full-rail interface specifies. #201's
question cannot arise there, under either convention.

#### Reproducing this

```bash
# arm A -- the shipped stimulus, as committed
python3 sim/bin/corner-run.py sim/psrr-dc --no-write \
  --subset-reason "issue #201 EN-stimulus A/B, arm A (shipped)"

# arm B -- EN carries the same perturbation as VIN
#   in sim/psrr-dc/testbench/tb_psrr_dc.sch, change the VEN line from
#     {name=VEN value='vsup' savecurrent=true}
#   to
#     {name=VEN value="DC 'vsup' AC 1" savecurrent=true}
python3 sim/bin/corner-run.py sim/psrr-dc --no-write \
  --subset-reason "issue #201 EN-stimulus A/B, arm B (EN tracks VIN)"

# then restore the shipped stimulus
git checkout -- sim/psrr-dc/testbench/tb_psrr_dc.sch
```

`--no-write` is the important flag: both arms run every corner for real but
neither writes into `sim/psrr-dc/`, so the A/B leaves the append-only record set
untouched. Compare the `[ n/45]` summary lines of the two runs.

### `load-transient` after #180

**Shape chosen: variant B (`.ic`-constrained `.op`, released into a non-`uic`
transient)**, not `uic` + an EN-edge preamble. Both shapes satisfy this
contract; this bench picks the `.ic` one for two reasons specific to what it
measures:

- It steps the **load**, not `EN` (`PULSE(1m 50m 1m 1u 1u 1m 4m)` on
  `I_LOAD`), at an already-regulating condition, and both clauses of the
  ratified row are referred to the *pre-step* steady state. An EN-edge
  preamble would shift the deck's whole time axis and with it every `meas`
  timestamp.
- More importantly, an EN preamble makes `C_OUT`'s pre-step charge state a
  function of the soft-start ramp. `#119` root-caused this bench's
  peak-excursion clause as **charge-limited** (`Q = C·dV` against the loop's
  finite large-signal response time, not phase-margin-limited), so the
  pre-step charge state is precisely the variable the bench must hold fixed.
  The `.ic` seed leaves the 1 mA pre-step operating point, the 1.000 ms /
  2.001 ms step edges and the 3 ms span exactly where they were — **no
  `meas`/`let` timestamp moved.**

The seed itself is the eleven-node `IC_SEED` card in
`sim/load-transient/testbench/tb_load_transient.sch` (same eleven nodes and
the same `vsup`-relative convention as `sim/ic-screen-125c-b`). Its values are
not invented: they come from a local probe of *this* circuit cold-started
through its own EN edge (`VEN` as a `PULSE`, `tran 200n 1m uic`) sampled at
t = 0.9 ms — settled at the pre-step 1 mA load, before the step — at
tt / 27 °C / 3.30 V. The schematic's header records the raw numbers and the
rounding. The seeded state satisfies the passive divider's own algebra
(`FB = VOUT/1.5`, `N_FBB = FB/2`), which is the realizability check `#164`
showed an unconstrained solve can violate.

**Two measurement expressions were re-expressed, and it is a consequence of
the seed, not a bound change.** Under an `.ic` seed, `v(vout)[0]` is the seed
value (`VOUT` clamped to 1.8 exactly), not the corner's own settled 1 mA
point, and the seed's relaxation toward that point during 0–1 ms is not a
load-step excursion. So the pre-step reference became a 0.800–0.999 ms average
(`v_pre`) and the peak searches became windowed (`v_post_min` / `v_post_max`
over 1.000–2.999 ms, matching `w_fall`'s own end). `undershoot_v` and
`overshoot_v` measure the same physical quantity against the same ratified
150 mV bound; only the reference sample and the search window changed. No
bound, stimulus, `C_out`/ESR point or measured quantity was touched.

**Isolation probe (local, three corners, same DUT and manifest, control deck
identical but with the `.ic` line deleted):**

| corner | unseeded control (under / over / rise / fall) | seeded | unseeded diagnostics |
|---|---|---|---|
| tt/27 °C/3.30 V | 0.084470 V / 0.065478 V / 99.5 µs / 606.1 µs | 0.084470 / 0.065478 / 99.5 / 606.1 | `singular matrix: xldo.xr_fb_b.t2` |
| ss/−40 °C/2.97 V | 0.076325 / 0.059782 / 91.3 / 546.1 | 0.076322 / 0.059784 / 91.3 / 546.1 | none |
| ff/125 °C/3.63 V | 0.098869 / 0.074635 / 113.7 / 651.5 | 0.098793 / 0.074678 / 113.5 / 651.3 | `singular matrix: xldo.xr_cz.t1` ×2, `Dynamic gmin stepping failed` |

Every measurement agrees with the unseeded control to ≤0.1 %, and both corners
that emitted a solver diagnostic unseeded emit none seeded — the seed removes
the numerical hazard without moving the physics. (The residual `Eta0 is
negative` lines are PDK model-card warnings, not one of `corner-run.py`'s
`SOLVER_DIAGNOSTIC_MARKERS`.)

**The 45-corner re-run: `20260926-013955-6449a98`** (supersedes
`20260825-081255-4cb27f8`; the superseded record and its logs are untouched,
per the append-only rule).

- **The hazard is gone: 0 of 45 corner logs carry a solver-diagnostic marker**,
  against **23 of 45** in the superseded record (`grep -lE 'singular
  matrix|gmin stepping failed|out of range for \^|source stepping failed'` over
  each record's `corners/*.log`). No corner was forced to `FAIL` by `#171`'s
  gate — every `solver_diagnostic` field in the new record's `.json` is empty.
  (The superseded record's JSON has no `solver_diagnostic` field at all: it was
  written before `#171` landed, which is exactly why its 23 hazard corners were
  graded on their measurement bounds alone.)
- **Verdict: 0/45 PASS, against the superseded record's 25/45.** Twenty-five
  corners moved `PASS` → `FAIL`; twenty were already `FAIL` and stayed `FAIL`;
  none moved `FAIL` → `PASS`.

**That verdict change is not caused by the seed, and reading it as such would
be wrong.** The two records do not measure the same manifest:

| | superseded `…-4cb27f8` (2026-08-25) | new `…-6449a98` |
|---|---|---|
| measurements | `undershoot_v`, `overshoot_v` only | + `recovery_rise_us`, `recovery_fall_us` (added by `#119`), + `settle_err_50ma_pct` |
| `C_out` | 1 µF | 4.7 µF (`#119`) |
| failing measurements | `undershoot_v` ×20, `overshoot_v` ×4 | `recovery_rise_us` ×45, `recovery_fall_us` ×45 |
| peak excursion (ratified ≤150 mV) | 0.102–0.393 V — **20 corners over** | 0.063–0.119 V — **every corner inside** |

So the **peak-excursion clause now passes at all 45 corners** (it failed at 20
before), and every one of the 45 new failures is the **recovery-time clause**
(`recovery_rise_us` 74.7–132.1 µs and `recovery_fall_us` 425.7–796.1 µs against
the ratified ≤20 µs) — a clause the superseded record never measured. Both
movements are the expected, already-documented sign of `#119`'s `C_out`
1 µF → 4.7 µF change: the peak excursion is charge-limited (`Q = C·dV`, so more
`C_out` helps it) and the recovery time runs the opposite way against the same
capacitor. `#119` recorded that tradeoff from a 3-corner subset; **this is the
first full 45-corner record of the post-`#119` manifest**, so it also completes
the re-verification `#166` was filed to get. The `.ic` seed's own contribution
is bounded by the three-corner isolation probe above: ≤0.1 %, which cannot move
a 74.7 µs measurement across a 20 µs bound.

`0/45 PASS` is therefore an honest design finding against a ratified row, not a
harness regression — the recovery-time gap is real and was previously
under-measured. No bound in `spec/target-spec.md` was touched.

Two incidental differences between the two records, neither affecting the
comparison above: the new record ran on a different host (`ngspice-46` /
`Darwin 27.0.0` vs the superseded record's `ngspice-47` / `Darwin 25.6.0`), and
`measurements/characterization.md`'s "Load transient" row moves from `STALE` to
`fresh` because the new netlist snapshot again matches a live re-netlist of the
current testbench.

### `#179` — converting `sim/loop-gain` and `sim/psrr-dc` (the two `ac` benches)

`#179` converted the two `ac`-analysis benches the table above lists as
**Exposed**. Both now carry the `.nodeset`-seeded `.ac` shape defined above,
and both new records supersede their predecessor:

| Bench | New record | Supersedes | Verdict | Corners PASS |
|---|---|---|---|---|
| `loop-gain` | [`20260926-040338-4a9ec09`](../loop-gain/records/20260926-040338-4a9ec09.md) | `20260825-081257-4cb27f8` | **FAIL** (unchanged) | 7/45 (was 7/45) |
| `psrr-dc` | [`20260926-033606-4a9ec09`](../psrr-dc/records/20260926-033606-4a9ec09.md) | `20260923-125412-d71f4b3` | **FAIL** (unchanged) | 0/45 (was 0/45) |

**Neither row's verdict changed, and neither row's verdict is comparable
corner-for-corner with its predecessor** — both superseded records were cut
*before* `#116`/`#139` re-sized the shared DUT's pass device, so their
netlist snapshots were `STALE` and their numbers are "against the 2500 µm
pass device". `loop-gain` lands on 7/45 again but on a *different* seven
corners (`tt_125c_2.97v`, `ss_125c_3.30v` and `ff_125c_2.97v` in, and
`tt_125c_3.63v`, `ss_125c_3.63v` and `ff_125c_3.63v` out). That movement is
the pass-device resize, not the seed — see the seeded/unseeded control
below, in which every measurement that both variants can compute agrees to
five or six digits.

**Why three seeded nodes and not eleven.** All four variants below were run
over the full 45-corner matrix on the *same* committed decks (extracted from
the new records' own corner logs, with only the `.nodeset` card swapped) and
with `sim/spiceinit` in place, so they are harness-equivalent and directly
comparable. "non-regulating points" counts `vout_seed_*` measurements that
did not land within 50 mV of 1.8 V — i.e. `ac` analyses that linearized
about a state where the pass device is simply full-on (`VOUT = VIN`):

| Seed | `loop-gain` diag. corners | `loop-gain` non-reg. corners / points | `psrr-dc` diag. corners | `psrr-dc` non-reg. corners / points |
|---|---|---|---|---|
| none (the pre-`#179` shape) | 13 / 45 | 3 / 6 | 2 / 45 | 1 / 1 |
| **three nodes (`VOUT`, `FB`, `N_FBB`) — shipped** | **3 / 45** | **0 / 0** | **2 / 45** | **0 / 0** |
| six nodes (the three + `SS`, `NB`, `BIASP`) | 2 / 45 | 2 / 4 | 1 / 45 | 1 / 1 |
| eleven nodes (`sim/ic-screen-125c-b`'s seed verbatim) | 9 / 45 | 2 / 4 | 6 / 45 | 1 / 1 |

The three-node seed is the only variant that leaves **no** `ac` analysis
linearized about a non-circuit state, in either bench. The six-node variant
shaves one more solver diagnostic but leaves four non-regulating points
standing, and diagnostic count is not the thing the contract is for —
landing on the regulating branch is. The eleven-node variant is worse on
both axes, for the reason the contract section states: its values *are*
`ic-screen`'s 125 °C/50 mA operating point, and a `.nodeset` card is one
static card applied to every bias point in the deck.

**What the seed actually bought, in measurements.** Three corners the
unseeded deck got wrong on the current DUT:

| Bench / corner | Point | Unseeded | Three-node seed |
|---|---|---|---|
| `psrr-dc` `ss/−40 °C/3.63 V` | 1 mA | `VOUT` = 3.6333 V → PSRR 0.017 dB @ 1 kHz, 5.20 dB @ 100 kHz | `VOUT` = 1.8004 V → 25.66 dB, 31.88 dB |
| `loop-gain` `ss/−40 °C/3.63 V` | 1 mA (pts 2, 5) | `VOUT` = 3.6333 V → `pm_c033_1ma_deg` / `pm_c47_1ma_deg` unmeasurable | `VOUT` = 1.8004 V → 74.39° |
| `loop-gain` `ff/27 °C/3.30 V` | 0 mA (pts 3, 6) | `VOUT` = 3.2870 V → `pm_c033_0ma_deg` / `pm_c47_0ma_deg` unmeasurable | `VOUT` = 1.8025 V → 20.58° / 55.58° |
| `loop-gain` `ff/−40 °C/3.63 V` | 0 mA (pts 3, 6) | `VOUT` = 3.6402 V → both unmeasurable | `VOUT` = 1.8019 V → 18.54° / 46.87° |

The `psrr-dc` row is the sharpest illustration of why `#171` exists: 5.20 dB
at 100 kHz is a *number*, it is inside the record, and it is not a PSRR — it
is the small-signal response of a circuit with no loop closed around it.
Everywhere else the seeded and unseeded numbers are identical to five or six
digits, which is the reassuring half of the same result: the unconstrained
solve was landing on the right branch at 42 of 45 corners, and the contract
exists because "usually" is not a property you can cite.

**FINDING — the seed does NOT clear `#171`'s solver-diagnostic FAIL gate,
and that is reported rather than suppressed.** Three `loop-gain` corners
(`tt_-40c_2.97v`, `tt_-40c_3.63v`, `ss_-40c_3.30v`) and two `psrr-dc`
corners (`tt_-40c_2.97v`, `tt_-40c_3.63v`) still raise
`Warning: singular matrix:  check node xldo.ea_cz` and are therefore forced
to **FAIL** by the gate. Four facts about that residue, all measured:

1. **It is not made worse by the conversion.** Unseeded, the same matrices
   raise 13 and 2; seeded, 3 and 2. The `loop-gain` count *improved* by a
   factor of four.
2. **No corner's verdict turns on it.** Every one of those five corners
   already fails at least one ratified measurement bound, so removing the
   gate would not turn any of them into a PASS. The gate is currently
   reporting, not deciding, on these two benches.
3. **The node it names is a poly-resistor terminal inside the
   compensation network (`EA_CZ`), not a node the feedback loop
   disambiguates** — the same `sky130_fd_pr__res_*` family whose
   voltage-coefficient extrapolation `#164` identified as the mechanism. A
   node-voltage seed cannot reach it; `.nodeset` only constrains node
   voltages, and this is a device-model-domain problem.
4. **It is not reproducible from the committed deck alone.** Re-running a
   corner's embedded deck by hand in a directory *without* `.spiceinit`
   emits no warning and produces bit-identical measurements; the same deck
   run with `sim/spiceinit` present (i.e. with `option klu`) emits it. Any
   attempt to reproduce one of these diagnostics must copy `sim/spiceinit`
   to `.spiceinit` first, exactly as `sim/bin/corner-run.py` does. `#190`
   generalized this fact from a footnote of this section into the evidence
   itself: corner logs now embed the `.spiceinit` they ran under next to the
   deck, and the summary record carries its `sha256` — see "Reproducing a
   corner by hand" above.

Fact 3 is why `#179` does not attempt to fix it: the residue belongs to the
resistor-model mechanism `#164` characterized, not to the initial-condition
contract, and closing it is a separate piece of work.

**Reproducing the control (no PDK-side setup beyond the usual pin).** Every
number in the two tables above comes from the committed corner logs, which
embed the deck ngspice was given (these logs predate `#190`, so they do not
also embed the `.spiceinit` — hence the explicit `cp` below):

```bash
# extract one corner's deck, strip (or swap) its .nodeset card, re-run it
python3 - <<'EOF'
import re
txt = open("sim/loop-gain/corners/20260926-040338-4a9ec09/ff_27c_3.30v.log").read()
# these logs predate #190, so their deck header reads "(exact input given to
# ngspice)"; logs written after it read "(1st input: ...)". Match either.
i = re.search(r"^# ==== deck \(", txt, re.M).start()
deck = []
for line in txt[i:].split("\n")[1:]:
    if not line.startswith("| "):
        break
    deck.append(line[2:])
deck = [l for l in deck if not l.startswith(".nodeset")]   # <- the "none" variant
open("/tmp/ab/ff_27c_3.30v.spice", "w").write("\n".join(deck) + "\n")
EOF
cp sim/spiceinit /tmp/ab/.spiceinit     # REQUIRED -- see fact 4 above
cd /tmp/ab && ngspice -b ff_27c_3.30v.spice < /dev/null | grep -E "^meas_|singular"
```

---

