# DR-009: Iq budget — ratify the Iq row at < 30 µA (no load and full load)

- **Status**: proposed — does not ratify itself. Per the ratification-via-PR
  standing policy ([2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357)),
  as refined by the two-key mechanism (2AMLogic/2am#372), the ratifying act is
  Judge review (→ `loom:pr`), the two-key mechanism's release, and the merge of
  the pull request this record ships in — the same path DR-006 took.
- **Date**: 2026-09-23
- **Author**: Builder agent (per #121)
- **Ratifies against / input to**: #121 (the Iq row is unratified yet graded
  FAIL); closes the Iq item DR-003 §4 and DR-006 §Decision item 7 left open
- **Supersedes**: none. DR-003 §4 and DR-006 item 7 both declined to set a
  number and named "a future decision record" as the way to set one. This is
  that record. It fills a gap they left open on purpose and does not overturn
  anything they decided.

## Context

`spec/target-spec.md` was ratified in full by DR-006 (#1, closed
2026-09-18), with one exception: the Iq row reads `OPEN — not ratified. No
number set.` Yet `measurements/characterization.md` grades that row **FAIL**
(36/45 corners, `sim/iq` record `20260910-034648-6c0436d`), because the
`iq` testbench cites the pre-ratification DRAFT text (`< 30 µA at no load
and full load`) as its own working bound. A row with no target cannot
honestly be failed, and an LDO's quiescent current is a real product
parameter that every comparable datasheet headlines. Leaving it unset is not
a neutral choice. #121 asks for the row to be either ratified to a number or
removed.

**Why the row was left open, and whether those reasons still hold.**
DR-003 §4 (2026-08-15) declined to set an Iq number because *"no amplifier or
bias topology exists yet in this repo"*. It rejected, specifically, *scaling*
gf180-ldo's 30 µA by a device-size or gate-capacitance ratio as fabricated
precision. DR-006 carried the row forward open for the same reason. The
first of those conditions no longer holds. The block now has a complete
topology (`design/ldo_3v3in_1v8out.sch`: error amplifier, bias generator,
unit-resistor feedback divider, current-limit sense, internally-referenced
thermal shutdown per DR-005, enable network, `VREF` as a top-level port). So
its current *consumers* can be listed and budgeted from device facts. That
is different from reading their measured currents off a sim record. This
record does not scale gf180's number (see Alternatives).

**Where the number must not come from.** #121 requires the target to be set
from device data, competitive precedent, and design intent, **not** from the
measured 36/45 result. Writing a target to fit a measurement is the same
failure as relaxing one to make results pass. This record's number is
anchored on the three permitted sources below. The measured data appears
only in Consequences, where it is graded against the target rather than
used to derive it.

**Provenance check: the number predates every measurement.** The first
committed version of `spec/target-spec.md` (repo scaffold, before any
schematic existed) already carried `Iq (excl. load current) | < 30 µA at no
load and full load | < 10 µA | G+S`, mirrored from gf180-ldo's table. The
first `sim/iq` record is `20260825-040934-6fac47d`, later than that. The
testbench's own 30 µA bound was cited *from* that DRAFT row, not the other
way round. So the number this record ratifies is not fitted to any sky130
result. It predates all of them, and the latest result under it is a FAIL.

### Source 1 — port parity with gf180-ldo (G)

This block is a sky130 port of `2AMLogic/gf180-ldo`: same block, same
mission (3.3 V ±10 % in, 1.8 V out, 0–50 mA), two PDKs. gf180-ldo's ratified
table (its DR-0004, amendment A6) reads:

> Iq (excluding load current) — **< 30 µA at no load *and* at full load** —
> binds ff / 125 °C / 3.63 V. Stretch: **< 10 µA**, subordinate to its
> DR-0001's ESR window; not to be bought back by reintroducing a minimum ESR.

(Read from a local clone of `2AMLogic/gf180-ldo` at `a6c95f8e`, its
`README.md` spec table and `spec/decision-records/DR-0004-spec-ratification.md`.
This is the ratified sibling in our own organization, not third-party silicon.)

Every other product-level row in this table (Input, Output, Load, Dropout,
Line/Load regulation, Load transient, PSRR, Stability, Enable/shutdown,
Area) mirrors gf180-ldo's ratified number unchanged, per CLAUDE.md's "Port
parity: prefer aligning with it; where sky130 forces a departure, record the
divergence." Iq is a product-level parameter in exactly the same sense. The
question is therefore not "what number should sky130 invent?". It is
"**does sky130 force a departure from 30 µA?**" Sources 2 and 3 answer that.

### Source 2 — sky130 device facts and the block's own design intent (S)

Iq is the sum of the block's standing branch currents. With the block's
consumers now known (see above), each one can be bounded from pinned-PDK
device facts and the block's other ratified rows. This is a **design-intent
allocation**, a feasibility check on the number. It is not a measurement and
not a claim about the current sizing.

| Consumer | Allocation (design intent) | Device fact / ratified constraint it rests on |
|---|---|---|
| Feedback divider | ≲ 2 µA (1.8 V across a ≳ 1 MΩ-class string) | `res_xhigh_po` at W = 0.42 µm is ≈ 2.4 kΩ/□ at the pinned open_pdks commit (a 0.42 × 180 µm unit is ≈ 1.04 MΩ, `design/README.md`). A MΩ-class string is a few hundred squares, well inside the 0.1 mm² Area row. The Load row makes the divider the only inherent preload, so it cannot be made much stiffer without eating the budget. |
| Voltage reference | 0 µA in this block | `VREF` is a top-level interface port (`design/README.md`; same convention as gf180-ldo's DR-0021). The reference's own current belongs to the reference block's budget. |
| Error amplifier (tail + pass-gate drive) | ≈ 8–15 µA | Gate-slew floor from DR-003 §4: the `pfet_g5v0d10v5` pass device's ≈ 3.6–3.9 pF gate must move by an overdrive change of order a few hundred mV within the Load-transient row's ~1 µs edges. `I = C·dV/dt` gives a floor of order 1–2 µA of *available* slew current. A class-A gate-drive stage needs a standing bias several times that, and the input pair needs its own tail for gm. This consumer is the one the Stability, PSRR and Load-transient rows all draw on (DR-007). |
| Bias generator | ≈ 2–4 µA | Resistor-defined µA-class reference branches (MΩ-class `res_high_po`/`res_xhigh_po`). Branch current scales with `VIN` across 2.97–3.63 V, so it has to be budgeted at `VIN_max`. |
| Thermal shutdown (DR-005) | ≈ 1–3 µA | **sky130-specific addition**: DR-005 requires an internally-generated, bias-derived trip reference plus a comparator. That is a standing consumer gf180-ldo's own row does not carry. |
| Current-limit sense | ≈ 0 at no load, a few µA at full load | A sense mirror scaled off the pass device carries a load-proportional fraction of current. That is why the row binds at full load as well as no load. |
| Enable network | ≈ 0 static | Logic-level static current. The ratified Shutdown-Iq row (< 3 µA) already bounds the whole block when disabled, including the pass device's off-state leakage, so leakage is not a first-order on-state term. |
| **Total** | **≈ 12–26 µA** | Fits under 30 µA with margin that is real but not generous. |

What this establishes:

- **sky130 does not force a looser number.** The one sky130-specific
  consumer (DR-005's thermal shutdown) costs a few µA. gf180's own
  architecture survey allocated 3–5 µA to an on-block reference, and this
  block does not carry that load (`VREF` is a port). The two roughly offset.
  The 5 V pass device's larger gate costs slew *current*, which is dynamic,
  and does not force standing bias beyond the amplifier allocation above.
- **sky130 does not force a tighter number either.** Nothing about the
  sky130 device menu makes a 30 µA-class budget wasteful. Tightening it
  would take µA away from the one consumer (the error amplifier) that
  DR-007 and DR-006 identify as the lever for the currently-failing
  Stability, PSRR and Load-transient rows.
- **The < 10 µA stretch is materially tighter** and in tension with those
  same rows. It would need the leanest amplifier plus a lean bias chain and
  thermal-shutdown comparator. It is kept as a stretch, not a target, as in
  gf180-ldo.

### Source 3 — competitive precedent (public datasheets only)

The bundled public-sources comp table (`ratification/market-key/comps/ldo.md`)
and DR-007's cited parts give:

| Part (public datasheet) | Class | Iq |
|---|---|---|
| TI TLV70018 | general-purpose low-Iq CMOS LDO, 200 mA, 1.8 V | 31 µA typ |
| Microchip MCP1801 (per DR-007) | 150 mA CMOS LDO, 1.8 V option | 25 µA typ, 50 µA max |
| Diodes AP7215 | 600 mA CMOS LDO | 50 µA typ |
| TI TPS7A02 | nanopower LDO | 25 nA typ |
| onsemi NCP170 (per DR-007) | nanopower LDO | 0.5 µA typ |

A **< 30 µA worst-case-over-PVT** limit, at both no load and full load, is
at or better than the *typical* figure of the general-purpose low-Iq class
this block competes in (TLV70018, MCP1801, AP7215). A worst-case bound at
the class's typical value is a competitive position for that class. The
nanopower class (tens of nA to sub-µA) is a different product category.
Its parts buy that Iq with architecture (duty-cycled or adaptive biasing)
this block does not have, and targeting it would conflict directly with
this block's own ratified PSRR and Stability rows (DR-007). This record does
not claim competitiveness against that class. That gap is stated here for
the market key to weigh, not hidden.

## Decision

**Ratify the Iq row at `< 30 µA at no load and at full load (50 mA),
excluding load current, at every corner of the ratified PVT matrix`, with
stretch `< 10 µA`, subordinate to DR-002's C_out/ESR window (not to be bought
back by reintroducing a minimum ESR). Source `G+S`.** This record is
`proposed`. It ratifies on the merge path named in its Status line, not by
its own text.

Definition, carried into the row so the target is unambiguous:

- **Iq** = total `VIN` supply current minus load current, with `EN` asserted.
  This is `design/README.md`'s existing convention and the `iq` testbench's
  measurement definition.
- **Both load points bind**: 0 mA (no external load; the feedback divider is
  inside Iq) and 50 mA (current-limit sense and any load-proportional bias
  are inside Iq).
- **No named binding corner.** gf180-ldo's row names `ff`/125 °C/3.63 V as
  its binding corner. This record deliberately does **not** carry that over.
  DR-004's naming-severity caveat forbids inferring which corner binds from
  the corner letters for this PDK's devices. The row is verified across the
  full ratified 45-point matrix until a measurement shows which corner
  binds. **This is a recorded divergence from gf180-ldo, as CLAUDE.md
  requires**, and the only one on this row.

## Alternatives considered

- **Remove the Iq row from the table** (the other disposition #121 allows).
  Rejected. The case for it: this block is an IP macro, and the integrator's
  total-system Iq budget, not a block-level number, is what a product
  ultimately binds. But gf180-ldo binds the row. Every public comp in the
  block's class headlines Iq. And a missing row would let the error
  amplifier's bias grow without limit to buy back the failing Stability and
  PSRR rows, which is precisely the trade DR-007 shows is not free. A
  quiescent-current bound is a real, buyer-checked product parameter, and
  dropping it would be a loosening dressed as a scope decision.
- **Scale gf180-ldo's 30 µA by a sky130/gf180 device ratio** (gate
  capacitance, pass-device area). Rejected for the reason DR-003 §4 gave,
  which still holds: a ratio between two different pass devices looks
  precise but has no product meaning. This record mirrors the number
  *unscaled*, as a product-level parity choice like every other `G` row, and
  checks feasibility against sky130 device facts rather than deriving the
  number from them.
- **A tighter target (e.g. 10–20 µA) to be more competitive.** Rejected as
  the *target*. It has no parity basis (gf180-ldo ratified 30 µA). It would
  still not reach the nanopower class that would make tightening worth it
  commercially. And it would take bias from the amplifier while eight other
  rows are failing for reasons DR-006/DR-007 tie at least partly to that
  amplifier. Retained as the < 10 µA stretch.
- **A looser target (e.g. 50 µA, matching MCP1801's max or AP7215's typ) to
  give the amplifier more room for the Stability/PSRR fixes.** Rejected. That
  would be setting the Iq target to suit a *design need of the current
  implementation*: the same "keyed to this design's current state, not to
  sky130 device physics" pattern DR-006 rejected for Option B. It would also
  break port parity for no device-physics reason, and DR-007 already shows
  that more amplifier Iq alone did not fix those rows (its 6× `M_TAIL`
  data point). If a later record shows the Stability/PSRR rows are
  genuinely unreachable inside 30 µA on sky130 physics, that record
  supersedes this one explicitly.
- **Leave the row `OPEN` until the Stability/PSRR redesign (DR-007's
  topology-change path) settles the amplifier.** Rejected. That is the state
  #121 correctly identifies as wrong: it keeps producing a verdict against a
  non-target. And the redesign itself needs an Iq bound to design against.
  An open row is a target that moves with the design, which is the thing
  ratification exists to prevent.

## Consequences

- **The Iq row reads a real verdict.** The latest `sim/iq` record
  (`20260910-034648-6c0436d`) bounds both `iq_no_load_ua` and
  `iq_full_load_ua` at `max 30` µA over the full 45-point matrix. That is
  identical to the ratified target and its corner scope, so the record
  grades the ratified row directly and no re-run is needed for this
  decision. `measurements/characterization.md` is regenerated in the same
  PR, and the row now reads **FAIL (36/45 PVT corners)** against a ratified
  number, no longer against an open placeholder. This is a disclosed design
  gap, not a reason to revisit the number (DR-006's Option A discipline).
- **What that FAIL consists of**, disclosed here, not used to set anything.
  The record already reports `vout_no_load_v`/`vout_full_load_v` next to each
  Iq figure so a reader can tell whether a corner was regulating. Reading
  the record's own per-corner lines:
  - **9 FAIL corners.** At each one the loop was not regulating at the
    50 mA point (`vout_full_load_v` between 2.67 and 3.43 V against 1.8 V),
    and the supply current in that state is ≈ 3.5 mA. These are the
    non-regulating DC branch `design/README.md` root-causes (#71/#81, a
    genuine second stable equilibrium, fix deferred to #79). They are not
    bias branches exceeding 30 µA. `sf_27c_3.30v` is non-regulating at both
    load points.
  - **2 PASS corners that do not count as genuine passes**: `ss_-40c_3.30v`
    (no load) and `ff_-40c_2.97v` (full load). Each reports a *negative* Iq
    (≈ −3.35 mA) at a non-regulating point (`vout` = 3.31 V / 2.71 V). The
    testbench scores a max-only bound, so a negative figure "passes". A
    non-physical, non-regulating operating point is not evidence of
    conformance. Filed as a follow-up harness issue (#133), since the
    evidence record is append-only and the fix is a new record.
  - **34 corners** regulate at both load points, and every one of them is
    inside the ratified < 30 µA at both points.

  So the row's FAIL is in substance the same DC-operating-point robustness
  defect that also appears in the Output, Line- and Load-regulation and
  Load-transient rows. It closes when that defect closes (#79 / #115 /
  #118), not by spending less Iq. **Headroom is thin, and this record says
  so plainly**: the regulating corners already sit close to the line at full
  load. Any future fix that spends amplifier bias (DR-007's topology-change
  path, #115, #117) is now bound by a ratified number rather than a draft
  citation.
- **DR-003 §4's open TODO and DR-006 §Decision item 7 are closed by this
  record** once it ratifies. Neither is edited (append-only). Both named a
  future record as the way to close them.
- **`spec/target-spec.md`** changes in the same PR: the Iq row gains its
  number, stretch, `G+S` source and a note citing this record. The status
  banner, "Where these numbers come from" and "Open items" sections drop
  their "except Iq" carve-outs. `README.md`'s mirrored table and its note 5
  change to match. No other row changes.
- **Hands to design, unresolved**: the thin full-load headroom above; the
  negative-Iq harness gap (#133); whether the < 10 µA stretch is ever pursued
  (in tension with Stability/PSRR, as in gf180-ldo); and measuring which
  corner actually binds, so a later record can name it (DR-004).

## Status notes

This record is `proposed`. It ratifies when the pull request it ships in
completes Judge review (→ `loom:pr`), the two-key mechanism's release
(2AMLogic/2am#372), and merge, per 2AMLogic/2am#357. That is the same path
DR-006 took. `spec/target-spec.md` and `README.md` are updated in the same
PR, ahead of this record's formal Status flip, so the merged tree is
internally consistent the moment it lands (DR-006's own convention). If the
market key or EE key escalates, the escalation belongs at PR review. Any
change to the number after that is a superseding record, not an edit to
this one.
