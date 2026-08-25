# DR-005: Thermal-shutdown trip temperature, hysteresis, and reference

- **Status**: proposed — not self-ratifying; input to #1
- **Date**: 2026-08-17
- **Author**: Builder agent (drafted per #28, split from #24)
- **Ratifies against / input to**: #1 (Ratify the target spec — operator-only,
  the T1 gate)
- **Supersedes**: none

## Context

`spec/target-spec.md`'s Thermal row states a dissipation framing and
`Tj ≤ 125 °C`, with "θJA delegated to package/integration" — no trip
temperature for a thermal-shutdown circuit to be designed against, and
CLAUDE.md's spec-is-a-gate rule forbids inventing one silently. Issue #22
(current limit + soft start) explicitly decomposed thermal shutdown out of
its own scope for exactly this reason, and `design/README.md`'s "Known gaps"
section restates it: *"a trip point needs something temperature-stable to
compare a CTAT sense against, and this block has none... the follow-on
therefore needs a spec/decision-record answer first."* This record is that
answer.

**The concrete motivation.** `design/README.md` §"3. Current limit" measured
the worst-case short-circuit dissipation with the #22 current limit in
place: **673 mW at `VIN_max = 3.63 V`** into a dead short (185.4 mA brickwall
limit, `tt`/27 °C screening, PDK `sky130A`, open_pdks
`c6d73a35f524070e85faff4a6a9eef49553ebc2b` — the pin in `sim/pdk.json`, as of
`origin/main` @ `9fb6861`, 2026-08-17). Holding `Tj ≤ 125 °C` at a 25 °C
ambient with that dissipation implies **θJA ≤ 149 °C/W** — a real, already
cited, integration constraint, and the reason the current limit alone is not
sufficient protection: a package with worse θJA than 149 °C/W, or a short at
elevated ambient, drives `Tj` past the spec's own operating ceiling with the
current limit fully engaged and doing nothing to stop it, because the current
limit is a *current* clamp, not a *temperature* one.

**The reference gap, stated precisely.** A thermal sense is naturally CTAT —
a diode-connected device's `Vgs` at fixed bias current falls roughly
1–2 mV/°C as temperature rises (device physics, not a sky130-specific
number; `sky130_fd_pr__pfet_g5v0d10v5`'s own measured `|Vth|` tempco in
DR-003's appendix — 0.948 V at `tt`/27 °C dropping with temperature at the
other corners in that same table — is consistent with this direction and
order of magnitude for the same device family). Comparing a CTAT sense
against *something* to produce a trip decision requires that something to
have a known tempco. `VREF` is an external port whose tempco is explicitly
undefined (`design/README.md`, "VREF interface caveat", as of `9fb6861`) —
this block has no on-chip bandgap, and the sibling `2AMLogic/sky130-bandgap`
canary is explicitly not consulted for its actual reference behaviour per
CLAUDE.md's clean-room mandate (harness patterns only, not reference
values). A trip pinned to `VREF` would therefore be un-anchored — its
accuracy claim would be meaningless, since nothing in this repo can state
what `VREF`'s absolute value does as `Tj` moves.

**Checked for a port-parity precedent, found none.** CLAUDE.md's port-parity
clause directs preferring alignment with the ratified `2AMLogic/gf180-ldo`
where sky130 does not force a departure. That repo's own spec-ratification
record (`DR-0004-spec-ratification.md`, item A10) sets a Thermal row with
continuous and short-circuit dissipation figures but **delegates θJA and
sustained-short survivability to package/integration and defines no
thermal-shutdown trip circuit** — gf180-ldo has no DR-NNNN for a thermal trip
point to align with. This decision therefore has to originate here; it is
not a translation of an existing ratified choice.

**PDK model-characterization bound, relevant to the number chosen below.**
DR-004 binds this repo's verification temperature axis to `{−40, 27, 125} °C`
— the three points `sim/bin/corner-run.py` and the pinned
`libs.tech/combined/sky130.lib.spice` corner sections are exercised at.
**125 °C is the top of this repo's own characterized temperature range.**
Any trip temperature chosen above 125 °C is, by construction, a design
target this repo cannot yet simulate-verify against its own pinned corner
set — that gap is carried forward explicitly in Consequences rather than
hidden.

## Decision

**Thermal shutdown is defined as a window, not a trimmed absolute — the same
discipline `design/README.md`'s current-limit section already uses ("the
spec row says window TBD over PVT precisely because this kind of limit is a
window, not a number"). Four things are fixed:**

| Item | Decision |
|---|---|
| Trip temperature `Tj_trip` (rising) | **150 °C nominal, untrimmed** — a 25 °C guard band above the spec's own `Tj ≤ 125 °C` operating ceiling (target-spec.md's Thermal row), not an externally cited "absolute maximum" figure |
| Hysteresis | **15 °C nominal** — reset/resume at `Tj_reset` (falling) ≈ 135 °C |
| Reference | **Internally generated, bias-generator-derived — not `VREF`, not a bandgap.** The CTAT sense compares against a second, fixed-current-density diode/CTAT element drawn from this block's own bias generator (the same `R_BIAS` → `M_BIASN1`/`M_BIASP1` chain the current-limit comparator's `M_CLP` reference branch already draws from), so the comparison never touches `VREF` or requires an on-chip bandgap to exist |
| Behavior | **Auto-restart (non-latching)** |

### Trip temperature and hysteresis: guard-banded above the spec ceiling, not an invented absolute

`target-spec.md`'s Thermal row already states the number this design has to
respect during *normal, rated* operation: `Tj ≤ 125 °C`. A thermal-shutdown
circuit's job is different — it is a fault-only backstop for conditions the
current limit does not catch (bad θJA, high ambient, sustained short at
`VIN_max`), and it must **not** engage during legitimate rated operation at
the 125 °C ceiling, or it would nuisance-trip the block under conditions the
spec already declares acceptable. The only number this repo can defend
without inventing an external "absolute maximum junction temperature" figure
it has not sourced (per CLAUDE.md's two permitted sources — gf180-ldo's
ratified numbers, which name none, and published sky130 references, which
this record does not have an accessible citation for) is a **margin above the
repo's own already-drafted ceiling**: 125 °C + 25 °C = 150 °C. This is the
same move DR-002 made for the ESR window (mirror + explicitly flag the
sky130-specific risk) applied in the opposite direction — here there is no
number to mirror, so the record derives one from this repo's own spec row
rather than from an uncited third-party figure.

15 °C of hysteresis is sized the same way the current limit's own accuracy
is described — qualitatively, not from a trimmed budget, because no trip
circuit exists yet to characterize (that circuit is #29's job, per this
issue's decomposition from #24). It needs to be large enough that comparator
offset and CTAT/reference device mismatch (the same category of untrimmed
mismatch the current-limit sense-FET/reference-mirror pairing already
tolerates, per `design/README.md`'s "Known accuracy caveat") do not chatter
the shutdown on and off near the trip point, and small enough that recovery
after a fault clears happens promptly rather than requiring the die to cool
tens of degrees below the point that caused the trip. 15 °C sits inside the
same order-of-magnitude window generic thermal-protection engineering
practice uses for untrimmed CTAT-based trips (a handful of degrees to a few
tens of degrees) — cited as a design-practice order of magnitude, not a
number ported from any specific implementation.

### Reference: internally generated, deliberately not `VREF` and not a bandgap

The decision that answers the acceptance criterion's "what reference" is:
**do not use `VREF` at all.** `VREF`'s tempco is undefined and this block has
no bandgap, so anchoring a trip decision to it would produce an unfounded
accuracy claim — the exact failure mode this record's Context section
established. Instead, the CTAT sense compares against a second internally
generated CTAT/diode reference biased at a different, fixed current density,
drawn from the bias generator this schematic already has (`R_BIAS`,
`M_BIASN1`, `M_BIASP1`) — structurally the same move `design/README.md`'s
current-limit comparator already makes: `M_CLP`'s ~2 µA reference branch is
also bias-generator-derived, not `VREF`-derived, precisely because the limit
comparator needed something available without a bandgap. A ratioed
diode/CTAT pair (two devices at different current densities, same family as
the bias generator's existing diode-connected devices) gives a comparison
whose *both* sides move with temperature in a related, physically-linked way,
rather than comparing a moving CTAT quantity against a reference whose
temperature behavior is unknown.

**This does not close the accuracy gap — it sidesteps the dependency.** A
bias-generator-derived reference is itself supply-dependent (the same caveat
`design/README.md` states for the current-limit reference: "it does rise
with `VIN`... making it supply-independent needs a real reference, not this
bias generator") and untrimmed, so the trip point's absolute accuracy is
**loose** — expected to vary meaningfully across process corners and supply,
in the same spirit as the current limit's own "window TBD over PVT" framing.
That is an accepted, stated cost of not depending on a reference-generator
gap that has no closing date, not a hidden one.

### Behavior: auto-restart, reusing the existing shutdown path

Latch and auto-restart were both weighed (see Alternatives). Auto-restart is
chosen because:

1. **A thermal fault is physically self-clearing.** Once `Tj` falls back
   below `Tj_reset`, the condition that caused the trip is, by definition,
   no longer present — unlike an electrical fault (e.g. a persistent output
   short) that can recur the instant protection releases, a thermal trip's
   root cause (excess dissipation exceeding what the package can remove) is
   gone as soon as the temperature has actually dropped.
2. **It reuses the existing shutdown path rather than adding a new
   mechanism.** `design/README.md`'s own "Known gaps" section already
   names the intended insertion point: *"the clean insertion point is the
   existing shutdown path — `M_ENP`/`M_ENP2`/`M_ENP3`/`M_ENN`/`M_ENN2` plus
   the `ENB` inverter... rather than a parallel shutdown mechanism."* That
   path is a **level-driven** disable (gated by `EN`, forcing the analog core
   off while the gating condition holds), not a stored state — wiring a
   thermal comparator's output into it the same way naturally produces
   auto-restart behavior for free. A latch would need a genuinely new
   element (an SR-latch or equivalent memory, plus a reset path) that
   nothing in the existing schematic anticipates.
3. **A latch needs a reset mechanism this block's interface does not have.**
   `spec/target-spec.md` defines no reset pin, and inventing one to support
   a latch would silently expand the block's pin list — a decision this
   record is not positioned to make unilaterally, since it would ripple into
   the Enable/shutdown spec row and the pinout, neither of which is this
   record's scope.

## Alternatives considered

- **Reference the trip against `VREF`.** Rejected — this is exactly the
  un-anchored construction the Context section rules out: `VREF`'s tempco is
  explicitly undefined, so a trip point measured against it would carry an
  accuracy claim this repo cannot support. If a future reference-generator
  block gives `VREF` a characterized tempco, that would be grounds for a
  *superseding* record, not an edit to this one.
- **Block this record entirely on the on-chip-reference gap closing** (i.e.
  wait for a bandgap or a characterized `VREF` before drafting DR-005 at
  all). Rejected as unnecessarily blocking — the internally generated,
  bias-generator-derived reference above is a "good enough" answer that does
  not require that gap to close, with its accuracy cost stated plainly
  rather than hidden. This mirrors DR-003's own choice not to block the
  pass-device sizing record on an Iq budget that also did not exist yet.
- **Set `Tj_trip` at or just above 125 °C** (e.g. 130 °C), minimizing margin
  to protect silicon as aggressively as possible. Rejected — this leaves
  almost no guard band between rated operation (which the spec already
  permits up to 125 °C) and the fault trip, risking nuisance shutdowns
  during legitimate high-load/high-ambient operation that is within spec.
  The whole point of a *separate* thermal-shutdown row from the `Tj ≤ 125 °C`
  operating ceiling is that it protects against conditions beyond normal
  operation, not conditions already declared acceptable.
- **Set `Tj_trip` well above 150 °C** (e.g. 175–200 °C, common absolute
  maximum figures for some CMOS processes), reasoning that more margin above
  125 °C is always safer. Rejected for this record — this repo has no
  sourced, citable sky130-specific number in that range (CLAUDE.md permits
  citing gf180-ldo's ratified numbers or published sky130 references, and
  neither supplies one here), and DR-004's model characterization only
  extends to 125 °C — pushing the target further from that boundary does not
  make it more verifiable, only harder to eventually confirm by simulation.
  150 °C is offered as the smallest guard band this record can defend from
  the repo's own spec row; a future record with a sourced destructive-limit
  figure could supersede it with a higher target.
- **Latching thermal shutdown, requiring `EN` toggling (power-cycle) to
  clear.** Considered seriously — some system designers prefer a latch for
  a thermal event specifically because repeated auto-restart cycling into a
  still-hot ambient can itself be a reliability risk (thermal cycling
  fatigue on the package/die), and a latch forces a human or system-level
  decision to re-enable rather than letting the part free-run in and out of
  shutdown indefinitely. This is a legitimate concern, which is why it is
  recorded fully rather than dismissed — but it was not chosen here because
  (a) it needs a reset mechanism this block's spec does not currently define
  a pin for, and (b) the existing shutdown-path insertion point
  `design/README.md` names is level-driven, not latching, so choosing latch
  would mean designing a materially different circuit than the one the
  existing schematic's shutdown discipline anticipates. If #1 or a later
  operator ruling prefers latching behavior, a superseding record — and a
  spec-row change adding a reset interface — would be the right path, not an
  edit to this one.
- **Derive the reference from a resistor-divided fraction of `VIN` instead
  of a bias-generator diode.** Considered as a simpler alternative (no
  second diode-connected device needed) — but rejected because a
  resistor-divided `VIN` fraction has no CTAT component of its own (poly
  resistor tempco is a different, much smaller effect than a `Vgs` tempco),
  so it would not track temperature at all — it would behave as a
  supply-referenced threshold, not a thermal one, defeating the purpose of
  comparing against something that also has a defined temperature
  relationship to the sense element.

## Consequences

- **Fixes the four items this record set out to fix**: trip temperature
  (150 °C nominal), hysteresis (15 °C nominal, reset ≈135 °C), the reference
  (internally generated, bias-generator-derived — explicitly not `VREF`, not
  a bandgap), and behavior (auto-restart, reusing the existing EN-gated
  shutdown path).
- **Unblocks #29** (the circuit-implementation half of the #24 decomposition)
  to design against a concrete target rather than a missing spec input,
  the same way DR-002/003/004 unblocked the schematic work in #14/#22.
- **Does not depend on the on-chip-reference gap closing.** Stated
  explicitly, per this issue's acceptance criteria: the reference choice
  above sidesteps `VREF`'s undefined tempco and the absence of a bandgap
  entirely, rather than waiting on either.
- **Hands to design, unresolved**: the actual sizing of the two CTAT/diode
  elements and their comparator (device widths, bias currents, the exact
  ratio that yields ≈150 °C/≈135 °C at the pinned PDK's `tt` corner) — that
  sizing work, and any screening deck to check it, belongs to #29, per this
  issue's own scope (a decision record, not a schematic).
- **150 °C sits outside this repo's own model-characterized temperature
  range.** DR-004 binds the verification temperature axis to
  `{−40, 27, 125} °C`; nothing in this repo has yet simulated device
  behavior at 150 °C against the pinned `sky130A` models. #29 (or a future
  `sim/` record) will need to either extend temperature coverage past 125 °C
  for the specific devices used in the trip/reference pair, or accept that
  the exact numeric trip point cannot be simulation-verified against the
  pinned corner set the same way DR-003's sizing work was — this is a real,
  named gap, not a silently dropped requirement.
- **The trip point's absolute accuracy is loose and PVT-dependent**,
  consistent with (and for the same underlying reason as) the current
  limit's own "window TBD over PVT" characteristic — an untrimmed,
  bias-generator-derived reference will not hold 150 °C/135 °C to tight
  tolerance across process and supply. Establishing the actual window is a
  #29/#19-scoped simulation question, not something this record can state
  a number for.
- **No numeric value in `spec/target-spec.md` changes because of this
  record.** The Thermal row stays DRAFT; if #1 ratifies this record, the
  row's notes should gain a cross-reference to DR-005 for the trip/hysteresis
  target, but the row's existing `Tj ≤ 125 °C` operating-ceiling text is
  unaffected — that number describes rated operation, and this record's
  150 °C describes a fault-only backstop above it, not a replacement.

## 2026-08-25 addendum: the 125 °C-vs-150 °C corner-coverage decision (issue #66)

This addendum resolves the gap this record's own Consequences section named
above verbatim: *"#29 (or a future `sim/` record) will need to either extend
temperature coverage past 125 °C for the specific devices used in the
trip/reference pair, or accept that the exact numeric trip point cannot be
simulation-verified against the pinned corner set."* Per CLAUDE.md's
append-only decision-record convention, this is an addendum, not an edit —
the Decision, Alternatives and Consequences sections above are unchanged.

**Decision: extend, not accept the gap — scoped to this one testbench.**
`sim/thermal/` (issue #66) sweeps `TEMP` continuously from 80 °C to 180 °C
(ascending, then descending in the same ngspice session, so the descending
leg continues from the operating point the ascending leg left behind — the
standard DC-continuation technique for characterizing a hysteretic
comparator's two trip points) against the actual CTAT-sense + comparator +
hysteresis circuit #29 added. This is option (a) from this record's own
Consequences section, not option (b) (formally accepting the gap). (The
sweep floor is 80 °C rather than DR-004's 100 °C+ characterized region
because ngspice's own `.meas dc ... find/when ... fall=1` has a confirmed
edge-of-sweep interpolation artifact — a crossing landing in the very first
swept interval, with no preceding data point, returns a nonsensical
interpolated result rather than failing cleanly. `sim/thermal`'s first run
hit exactly this at `sf_27c_3.30v` with a 100 °C floor [superseded record
`20260825-050729-6fac47d`]; widening the floor to 80 °C — safely below every
corner's actual trip point, all of which land at 95 °C or above — resolved
it for the authoritative record cited below. This is an ngspice
measurement-technique limitation, not a circuit finding; see
`sim/thermal/experiment.json`'s own comments for the full explanation.)

**Why extend rather than accept.** An empirical check (2026-08-25, this
issue): a `.dc temp` sweep of the pinned `sky130A` open_pdks
`c6d73a35f524070e85faff4a6a9eef49553ebc2b` models against this schematic
solves without NaN/divergence at every point from 80 °C up to 180 °C at
every one of the 15 full-PVT-matrix points `sim/thermal/experiment.json`
declares. (A `.dc` sweep continuing past ~190 °C does hit a `singular
matrix` convergence failure at the `M_SSCHG` soft-start charge-pump PFET's
source node — a different device than the thermal sense/reference pair this
record is about, and not evidence the *models themselves* break down at that
temperature, but a real, separate convergence limit of this specific
schematic. `sim/thermal`'s 180 °C sweep ceiling stays comfortably clear of
it.) Extending was therefore mechanically possible, and doing so is the only
way to actually locate the real trip/reset crossing rather than reporting a
qualitative "gap closes but has not crossed by 125 °C" finding forever, per
`design/README.md`'s pre-#66 screening note.

**Scope: this extension is for `sim/thermal` only.** It does **not** change
DR-004's `{−40, 27, 125} °C` binding for the other four PVT testbenches
(`load-transient`, `psrr-dc`, `dropout-vs-load`, `loop-gain`) or for spec
verification generally — those stay pinned to DR-004's characterized axis.
`sim/thermal`'s corner matrix instead fixes `temperature_c` as a manifest
placeholder (`[27]`, unused — see the experiment's own comment) and sweeps
`TEMP` itself as the analysis variable across `process` × `supply_v`, per
the deck documented in `sim/thermal/experiment.json`.

**The accepted tradeoff, stated plainly.** Every point above 125 °C in this
sweep runs the pinned BSIM models in extrapolation beyond DR-004's
characterized range — not confirmed against silicon. The measured
trip/reset numbers below therefore carry lower confidence than a PVT-corner
point inside the pinned axis, and `sim/thermal`'s own record says so
explicitly rather than presenting them as equally trustworthy. This is the
named cost this record's Consequences section already flagged, now actually
paid rather than deferred.

**What the authoritative run found** (2 °C sweep resolution; record
`sim/thermal/records/20260825-054043-6fac47d`, the full 15-point PVT matrix
substantiating the numbers cited in `measurements/characterization.md`'s
Thermal row). Two distinct findings, neither closable by this record (a
decision record does not resize a circuit):

1. **Confirms and substantially quantifies issue #69's `ff`/`sf`-at-125 °C
   nuisance-trip finding.** Where `design/README.md`'s prior single-point
   `.op` screening (one corner, one supply) could only show the
   sense/reference gap had not yet crossed by 125 °C, a full sweep across
   all three supply corners locates the actual crossing: `ff` trips at
   115.0–121.0 °C and `sf` trips at 95.0–101.0 °C — **both process corners
   fall below the spec's own 125 °C operating ceiling at every one of the
   three supply corners tested**, more severe than #69's single confirmed
   point suggested. `tt` (135.0 °C), `ss` (145.0–149.0 °C) and `fs`
   (165.0–167.0 °C) all trip comfortably above 125 °C. This addendum does
   not re-open #69's scope; the fix (re-sizing the CTAT sense/reference
   stack) is still #69's job.
2. **A new, previously-unconfirmed finding: the measured hysteresis sign is
   non-positive at every one of the 15 corners `sim/thermal`'s first
   evidentiary run covers.** This record's Decision states the reset
   temperature should sit *below* the trip temperature (positive hysteresis,
   `Tj_reset ≈ 135 °C` under a `Tj_trip ≈ 150 °C` nominal). The measured data
   instead shows `reset_temp_c ≥ trip_temp_c` at 10 of 15 corners (e.g.
   `ss_27c_2.97v`: trip 149.0 °C / reset 157.0 °C; `sf_27c_3.63v`: trip
   95.0 °C / reset 105.0 °C) and exactly `0 °C` measured hysteresis at the
   remaining 5 (`tt_27c_3.63v`, `ss_27c_3.30v`, and all three `fs` corners)
   — i.e. during the cooling (descending) sweep, `M_TSHUT` releases *before*
   or *at* the temperature at which it originally tripped on the way up, the
   opposite of the intended "must cool further before restart" behavior, at
   every corner tested. This is a real, additional circuit-sizing question
   this record's own accepted "loose, PVT-dependent" cost (see Decision,
   above) already anticipated could happen, but had not been confirmed
   until this testbench existed to check it. **Not fixed by this addendum
   or by #66** — tracked as its own follow-on issue, **#77**, rather than
   folded into #69, since the mechanism (hysteresis-injection sizing/
   polarity, or possibly a DC-continuation measurement-methodology bias —
   #77 does not prejudge which) is distinct from #69's sense/reference
   crossing-point mechanism.

## 2026-08-25 addendum: #77 root-caused the hysteresis-sign finding — a marginal regenerative loop gain, not a simple sign error

This addendum resolves — as far as it can be resolved without a shipped
circuit change — the open question the `2026-08-25 addendum` above left
unanswered: whether the non-positive hysteresis `sim/thermal`'s first
evidentiary run measured at every one of 15 corners is a real circuit
defect or a DC-continuation measurement artifact (that addendum explicitly
said "#77 does not prejudge which"). Per CLAUDE.md's append-only convention,
this is an addendum, not an edit — the Decision, Alternatives and
Consequences sections above, and the `2026-08-25` addendum before this one,
are unchanged.

**Answer: both, and neither cleanly. A genuine but marginal regenerative
loop gain in the `M_TSHYS`/`M_TSHYSB` positive-feedback path, which the
default DC-continuation measurement technique also mismeasures.**

**Diagnostic method 1 — nodeset-forced bistability probe.** At
`tt_27c_3.30v`, `T=134°C` (one 2°C grid step below the vanilla `.dc temp`
sweep's measured 0°C-hysteresis crossing at 135°C), an independent `.op`
seeded with a `.nodeset` biasing every hysteresis-path node toward the
*tripped* state converges to a genuine, self-consistent tripped solution:
`V(TS_REF)` settles at ≈1.065V (matching the ≈1.064V this same corner's own
naturally-tripped state at `T=136°C` shows, and matching the schematic's own
"raising the reference by tens of mV" design-intent comment — the boost
mechanism is doing exactly what it was designed to do), `V(TS_CMP)`≈0.48V
(low, tripped), `V(VOUT)`≈0 (collapsed). This proves a real, locally stable
tripped branch exists at `T=134°C` that the default sweep's Newton
continuation — despite starting from the immediately-prior tripped point at
136°C — does not track, instead reconverging to the untripped branch at the
very next 2°C step. Re-running the same corner with `.options gminsteps=1`
(reducing ngspice's default gmin-stepping homotopy fallback, which
`design/README.md`'s `#71`/`#81`-resolved section already identified as a
continuation-path disruptor for an unrelated bistability question in this
same schematic) surfaces the real branch: measured hysteresis flips from 0°C
to a small,
correctly-signed **+2°C** (`trip_temp_c=133°C`, `reset_temp_c=131°C`) at
this one corner.

**Diagnostic method 2 — fine-grid re-sweep at the worst-offending corner.**
`ss_27c_2.97v` (screening-reproduced against current `HEAD`: `trip_temp_c
≈147°C`, `reset_temp_c≈157°C`, `hysteresis_c≈−10°C` — a couple of degrees
off the `20260825-054043-6fac47d` record's own `149°C`/`157°C`/`−8°C` for
this corner, plausibly explained by that record's own noted "working tree
dirty at run time" caveat rather than a schematic difference; `git log
6fac47d..HEAD -- design/ldo_3v3in_1v8out.sch` returns no commits, so the
committed schematic itself has not changed) does **not** show a clean single
crossing in either sweep direction at a 0.25°C grid: `V(VOUT)` flickers
erratically between the tripped (~0V) and untripped (~1.8V) states across a
~12°C-wide band (144–156°C on the ascending leg), including at least one
spurious intermediate operating point (~2.98V — matching neither the
regulated nor the tripped state) that a converged DC solve should not
produce. `.options gminsteps=1` does **not** resolve this corner (hysteresis
stays ≈−10°C) — unlike `tt_27c_3.30v`, this corner's positive-feedback loop
gain is apparently close enough to unity that the algebraic DC system has no
single well-defined answer over a wide temperature band, not merely a narrow
window the default methodology loses track of.

**Interpretation.** This single mechanism — a real but *marginal*
(corner-dependent, sometimes barely-above-unity, sometimes barely-below-unity)
regenerative loop gain around `M_TSHYS`'s current injection into `TS_REF` —
explains both failure signatures the `2026-08-25` addendum above reported
under one root cause rather than two: the exact-`0°C` corners (`tt_27c_3.63v`,
`ss_27c_3.30v`, all three `fs` corners) most plausibly have a narrow, real,
correctly-signed hysteresis window the default continuation-plus-gmin-stepping
methodology loses (as demonstrated for `tt_27c_3.30v` above); the strongly
negative corners (`ss`, `ff`, `sf` at several supplies) most plausibly sit in
a genuinely marginal/flickering regime where no single crossing is
well-defined and the first-crossing `.meas` reports whichever branch the
solver's exact numerical path happens to land on.

**Hardening attempted at the `ss_27c_2.97v` corner, none shippable** (full
data, and the physical reasoning for why each attempt did what it did, is in
`design/README.md`'s dated "#77" section under "Thermal shutdown (#29)" —
not reproduced here to keep this record from duplicating `design/`'s
screening-detail convention):

- Scaling `M_TSHYSB`'s injected current 2×–30× the baseline width: widens
  neither corner's window cleanly, and — because `M_TSHYS`'s pre-trip "off"
  conduction is not exactly zero (the comparator's own finite gain lets
  `TS_CMP` droop gradually pre-trip, so `Vsg(M_TSHYS)` is not exactly 0
  before the nominal crossing) — a larger `M_TSHYSB` also couples
  progressively more current into `TS_REF`'s *pre-trip baseline*, dragging
  the entire transition colder (trip fell from ≈147°C at baseline to
  ≈95–97°C at the largest boosts tried) — at those magnitudes this pushes
  the trip point well below the already-open #69 floor violation, making
  that finding worse rather than fixing this one independently.
- Strengthening the comparator's own gain instead (4× `M_TCTAIL`'s tail
  current, injection current unchanged): reduced but did not eliminate the
  sign inversion (−10°C → −4°C) without the trip-point collapse the
  injection-current approach caused — directionally the more promising of
  the two single-knob attempts — but combining it with even a modest (2×)
  injection increase made the result worse (−12°C), which is evidence this
  is a multi-parameter loop-gain problem, not a single-knob fix reachable by
  trial-and-error sizing within this issue's own screening budget.

**Not fixed by this addendum.** Per the reasoning above, this needs a
genuine large-signal loop-gain redesign of the trip-comparator/hysteresis
cluster (most plausibly a real regenerative latch/Schmitt-style element,
rather than a linear current injected into a diode-connected reference node
whose own DC operating point that same injection perturbs) — the same shape
of conclusion, and the same "investigated, not shipped, follow-on issue
carries the data forward" disposition, `design/README.md`'s "Bias-generator
redesign investigated, reverted (#70)" section already used for the
PSRR/stability shortfall. `ldo_3v3in_1v8out.sch` is **unchanged** by #77.
Follow-on work continues in **#91**, seeded with this addendum's and
`design/README.md`'s data. No new `sim/thermal` record was minted — neither
the testbench deck nor the circuit changed, so a fresh 15-point run against
the identical schematic and PDK pin would reproduce the same numbers, not
add verification value (the same "no purely-redundant record" reasoning
`design/README.md`'s `#71`/`#81` section already applied to
`dropout-vs-load`); `20260825-054043-6fac47d` remains the authoritative
record.

## Status notes

This record stays `proposed` until #1 closes. #1's ratification of this
record's trip temperature, hysteresis, reference strategy, and auto-restart
choice does not by itself satisfy this repo's "no claim without a
testbench" rule — a `sim/` evidentiary record for the actual trip/reference
circuit (#29's output) is still required before any thermal-shutdown
behavior can be cited as verified, and that circuit's screening/simulation
work will additionally need to address the 150 °C model-characterization gap
named in Consequences. If #29's implementation finds the internally
generated reference cannot hold a defensible window, or that 150 °C is not
achievable/appropriate once real device data exists, a superseding record
replaces this one — this record is not edited after the fact.

---

## Append (2026-08-25, issue #69): the sizing this record handed to design, and where it actually landed

**This is an append, not an edit.** Nothing above has been changed. Per
`spec/decision-records/TEMPLATE.md` — and per this record's own Status
notes — a record that turns out to be wrong is superseded, never quietly
rewritten. This append reports what the sizing work this record explicitly
"hands to design, unresolved" produced, and states plainly one place where
the result does **not** match a number in the Decision table above, so that
#1 can rule on it with the measurement in hand rather than discovering it
later. The record's **Status stays `proposed`** and **no number above is
changed**.

### What happened first: the nuisance trip this record's guard band exists to prevent

Issue #29 implemented this record's circuit. Issue #60's root-cause pass of
the full 45-point PVT campaign found that at the `ff` and `sf` process
corners at **125 °C — the top of `spec/target-spec.md`'s own rated `Tj`
range, not a fault condition** — the comparator had already tripped, forcing
the pass gate off. That is exactly the failure this record's "Trip
temperature and hysteresis" section names ("it must **not** engage during
legitimate rated operation at the 125 °C ceiling, or it would nuisance-trip
the block under conditions the spec already declares acceptable"). Issue #69
measured the rising trip across all five corners and confirmed it:
**102–175 °C at `VIN = 3.30 V`**, i.e. two of five corners trip below the
rated ceiling.

### Root cause, and the correction it forces to this record's own framing

This record predicted the trip's absolute accuracy would be "loose and
PVT-dependent" — which was right — but framed that looseness as the accepted
cost of a *bias-generator-derived reference* being supply-dependent and
untrimmed. **That is not what dominated.** The dominant term was a
geometry-amplified, un-cancelled process `Vth0` skew between the two CTAT
branches: sky130's continuous HV models implement a process corner purely as
a geometry-weighted `delvto`, so a short-channel sense device amplifies the
corner shift, and the "ratioed diode/CTAT pair" this record specifies
compares *two* sense `Vgs` terms against *one* reference `Vgs` term, leaving
that amplified shift un-cancelled. The full derivation and the measured
numbers are in `design/README.md` → "Sizing the trip: what is a knob and
what is not (re-worked in #69)".

The consequence for this record is narrow but real: its Reference row's
rationale — that a ratioed diode/CTAT pair gives "a comparison whose *both*
sides move with temperature in a related, physically-linked way" — is true
for *temperature* and silently false for *process*. A 2-vs-1 comparison of
same-family devices does not cancel a process `Vth` shift; it doubles one
side of it. That is a constraint on the sizing, not on the Decision, and #69
resolved it inside the sizing (matching the two branches' geometry weightings
so `2·k_sense − k_reference` falls from 2.17 to 0.003).

### Where the result lands against the Decision table

Measured from the committed schematic's own netlist, 5 process corners ×
3 supplies, PDK `sky130A` @ `c6d73a35f524070e85faff4a6a9eef49553ebc2b`
(the `sim/pdk.json` pin), screening decks — not `sim/` evidence:

| Decision item | This record | #69 measured |
|---|---|---|
| `Tj_trip` nominal | 150 °C | **165 °C** (`tt`, `VIN = 3.30 V`) |
| Must not trip at the 125 °C ceiling | required, 25 °C guard band | **met at every corner**: worst-case trip 155.1 °C, i.e. a **30.1 °C** guard band |
| Hysteresis | 15 °C nominal | **13.9–20.4 °C** |
| Reference | internally generated, bias-generator-derived, not `VREF`/bandgap | **unchanged** — still the `R_BIAS`/`M_BIASN1`/`M_BIASP1` chain |
| Behavior | auto-restart, non-latching | **unchanged** |

**The one mismatch, stated plainly: the nominal is ~15 °C above this
record's 150 °C.** It is not an oversight and it is not a relaxed spec line
— it is forced by the two requirements in the Decision table interacting
with a measured window width this record could not have known:

- The untrimmed trip window is **~20 °C wide** over the corner set
  (≈12 °C process + ≈8 °C supply) even after #69's cancellation.
- This record requires a 25 °C guard band above 125 °C. Applied at the
  **worst** corner — the only reading a nuisance-trip defect permits, since
  a guard band that holds only at nominal is exactly what failed — the
  window's floor must sit at ≥150 °C, which puts its centre at ≈165 °C.
- Centering the nominal at 150 °C instead would put the worst corner back at
  ≈140 °C: a 15 °C guard band, i.e. a weaker version of the same defect,
  with no mismatch headroom left (per-instance mismatch is a further,
  unmeasured axis; at the measured ~4 mV/°C slope, 10 mV of offset is
  ~2.5 °C).

`design/README.md` also records the residual ~8 °C of *supply* dependence as
the bias generator's, not this circuit's — narrowing it needs the
supply-independent/cascoded bias generator #70 tracks, which this record
already anticipated in its "accuracy gap … sidestepped, not closed" framing.

### What this append does and does not do

- It does **not** change 150 °C, or any other number, in the Decision table.
- It records that the as-built circuit's nominal is ≈165 °C with a
  155–175 °C window, and *why* holding this record's own guard-band
  requirement at the worst corner is what put it there.
- **The choice belongs to #1, not to this append.** If #1 ratifies "150 °C
  nominal" as literal, then either the window has to be narrowed further
  (a supply-independent bias generator — #70 — is the only in-repo lever
  identified) or the guard band has to be read as a nominal-only
  requirement, which #69's defect argues against. If #1 instead ratifies the
  guard band as the binding clause and the 150 °C as its derivation, this
  record needs no change at all. Either way the resolution is a ruling or a
  **superseding record**, not an edit to the Decision above.
- The 150 °C-outside-the-characterized-range gap this record named in
  Consequences is **still open, and is now sharper**: the 155–175 °C window
  above is a model extrapolation past DR-004's `{−40, 27, 125} °C` axis. The
  part that is *not* extrapolated — and is the part the guard band actually
  rests on — is the sign and size of the sense-vs-reference gap at 125 °C
  itself: **+0.121 V worst case over all 45 PVT points, ~30 °C of headroom
  at the measured slope**, versus a negative (already-tripped) gap at six of
  those points before #69.

---

## Append (2026-08-25, issue #91): the hysteresis loop-gain question re-opened by this append's own re-size, and re-closed the same way

**This is an append, not an edit.** Nothing above has changed, including the
`2026-08-25` `#77` addendum. The append immediately above (issue #69)
re-sized `M_TSD1`/`M_TSD2`/`M_TSR1`/`M_TSPR`/`M_TSPS`/`M_TSHYSB` — one of
those, `M_TSHYSB`, is a knob the `#77` addendum's own screening swept — so
`design/README.md`'s "Parallel landings on `main`" table (dated 2026-08-25)
flagged the `#77` addendum's non-positive-hysteresis finding as genuinely
re-opened against the re-sized circuit rather than answered by it. #91 is
that re-opening, closed the same way #77 closed the original question: **the
marginal regenerative loop gain persists, essentially unchanged in
character, on the re-sized circuit.**

**Full re-screen (15 corners, vanilla `.dc temp` continuation, the exact
`sim/thermal` methodology) and a new candidate knob (comparator
differential-pair/mirror channel length, `M_TCN1`/`M_TCN2`/`M_TCP1`/
`M_TCP2`) are in `design/README.md`'s dated "`#91`" section — not
reproduced here, per the same convention the `#77` addendum above used.
Summary: the new candidate fixes the single worst-behaved corner
(`ss_27c_2.97v`: `−2.4 °C → +23.1 °C`, the cleanest single-corner result
either issue produced) but leaves 14 of 15 corners unmoved at exactly
`0 °C`, and is a knife-edge rather than a margin at the one corner it does
move — bracketing shows a 50% step in `L` fixes it, the next 33% step undoes
it, and one more turns it into a **permanent trip that never auto-restarts**
within the swept range, a direct DR-005 violation rather than a measurement
miss. A second attempt combining the new knob with a further `M_TSHYSB`
increase at one of the flat corners produced no change in hysteresis while
reproducing the `#77` addendum's already-known "bigger `M_TSHYSB` drags the
baseline colder" side effect. Two independent checks (fine-grid re-sweep;
`.options gminsteps=1`) confirm the flat corners are genuinely
near-zero-gain at this sizing, not a lost window the measurement technique
merely failed to find.

**Not fixed by this append**, for the same reason the `#77` addendum was
not fixed: this needs a genuine large-signal regenerative-latch/
Schmitt-style redesign, not a further linear-sizing knob on the existing
current-injection topology — three independent knobs across `#77` and `#91`
(injection current, comparator tail current, comparator channel length)
have each moved exactly one corner at a time without ever producing a
margin that holds across the corner set simultaneously. `#91` does not file
a further follow-on issue for the redesign itself; a future builder taking
this on should file it fresh once ready to spend a full circuit-design
cycle on it, using this append's and `#77`'s data as the starting point,
rather than inheriting a third open issue number for the same unsolved
problem. `ldo_3v3in_1v8out.sch` is **unchanged** by #91. **No new
`sim/thermal` record was minted**: the committed schematic did not change,
so a fresh 15-point run would reproduce `design/README.md`'s `#91` table
rather than add verification value; `20260825-054043-6fac47d` remains the
authoritative (and correctly `STALE`-flagged, per
`measurements/characterization.md`, against the `#69`/`#90` schematic
change) record. Nothing in the Decision table above, or in either append
before this one, is changed.
