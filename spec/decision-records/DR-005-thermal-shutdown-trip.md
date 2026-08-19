# DR-005: Thermal-shutdown trip temperature, hysteresis, and reference

- **Status**: **ratified** — trip temperature, hysteresis, reference strategy,
  and auto-restart behavior ratified by #1 (DR-006), pending operator PR
  approval per the 2026-08-19 ratification-via-PR standing policy
  ([2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357)). The
  150 °C/135 °C figures remain outside this repo's own model-characterized
  temperature range and PVT-loose, per this record's own Consequences —
  ratification fixes the *design target*, not a verified accuracy window.
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

## Status notes

**Ratified by DR-006 / #1, pending operator PR approval (2026-08-19).**
Ratification of this record's trip temperature, hysteresis, reference
strategy, and auto-restart choice does not by itself satisfy this repo's "no
claim without a testbench" rule — a `sim/` evidentiary record for the actual
trip/reference circuit (#29 implemented the circuit; no dedicated thermal
testbench exists yet under `sim/`, per `measurements/characterization.md`'s
Thermal row) is still required before any thermal-shutdown behavior can be
cited as verified, and that circuit's screening/simulation work will
additionally need to address the 150 °C model-characterization gap named in
Consequences. If that future simulation finds the internally generated
reference cannot hold a defensible window, or that 150 °C is not
achievable/appropriate once real device data exists, a superseding record
replaces this one — this record is not edited after the fact.
