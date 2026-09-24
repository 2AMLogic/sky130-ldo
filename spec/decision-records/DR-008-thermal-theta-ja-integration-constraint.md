# DR-008: Thermal row — what the 12/15 FAIL is (and is not), and the θJA integration constraint the block imposes on its package

- **Status**: proposed — not self-ratifying. It changes no number in
  `spec/target-spec.md`; it records an assumption the ratified Thermal row
  delegates, so its ratification is an operator decision (PR approval, per the
  ratification-via-PR standing policy cited in DR-005's header)
- **Date**: 2026-09-23
- **Author**: Builder agent (drafted per #120)
- **Ratifies against / input to**: #120; #114 (gap-to-T1 tracker, Thermal row)
- **Supersedes**: none. DR-005's Context-section figure (θJA ≤ 149 °C/W) is
  *refreshed*, not superseded — see Consequences

## Context

`spec/target-spec.md`'s Thermal row (ratified by DR-006 / #1) reads:
*continuous worst-case dissipation set by Vin_max × I_load; short-circuit
ceiling set by the current limit; specified to Tj ≤ 125 °C (rated-operation
ceiling); θJA delegated to package/integration*. Its Notes column adds the
DR-005 fault-only thermal-shutdown backstop (150 °C nominal trip / 135 °C
nominal reset, auto-restart).

`measurements/characterization.md` reports that row as **FAIL, 12/15**,
citing `sim/thermal` record
[`20260825-104426-933dfdd`](../../sim/thermal/records/20260825-104426-933dfdd.md).
Issue #120 asked, before treating that as a design defect: which θJA do the
failing corners assume, and is it stated anywhere ratified; are the failures
at short-circuit or continuous rated load; and is `Tj ≤ 125 °C` evaluated
against the right ambient.

### Finding 1 — the three failing corners, and what they failed on

From the record itself (not re-derived):

| Corner | `trip_temp_c` (bound ≥ 125 °C) | `reset_temp_c` | `hysteresis_c` (bound ≥ 0) | Failing bound |
|---|---|---|---|---|
| `tt_27c_3.63v` | 147.0 °C — PASS | 149.0 °C | −2.0 °C | `hysteresis_c` only |
| `ss_27c_2.97v` | 150.6 °C — PASS | 153.0 °C | −2.4 °C | `hysteresis_c` only |
| `ff_27c_3.63v` | 153.0 °C — PASS | 161.0 °C | −8.0 °C | `hysteresis_c` only |

`trip_temp_c` passes the bench's own `min: 125` bound at **all 15** corners
(lowest: 138.8 °C at `sf_27c_3.63v`, 13.8 °C above the rated ceiling). The
"27c" in each corner ID is a manifest placeholder — the bench sweeps `TEMP`
itself from 80 °C to 180 °C and back (`sim/thermal/experiment.json`). All
three FAILs are the known DR-005 auto-restart hysteresis defect root-caused
in #77 and re-confirmed on the re-sized circuit in #91 (DR-005's `#77`
addendum and `#91` append: a marginal regenerative loop gain in the
`M_TSHYS`/`M_TSHYSB` current-injection path, needing a
Schmitt/latch-style redesign, not a sizing knob).

**The hysteresis defect is wider than the three flagged corners.** The
other 12 corners "pass" `hysteresis_c` only because the bench's bound is
`≥ 0`: every one of them measures **exactly 0.0 °C**, against DR-005's
15 °C nominal target. No corner shows resolvable positive hysteresis. And
per `experiment.json`'s own `hysteresis_c` note, a value within ±2 °C of
zero reads as "no resolvable hysteresis at this grid step", not as a
confidently-signed inversion. So −2.0 °C (`tt_27c_3.63v`) and −2.4 °C
(`ss_27c_2.97v`) sit at or just past the 2 °C grid, and only
`ff_27c_3.63v` (−8.0 °C) is an unambiguous inversion. The accurate reading
is therefore that the auto-restart hysteresis is **absent at all 15
corners**, inverted outright at one. It is not "3 inverted corners and 12
working". #131's acceptance bar (> 0 with margin beyond the 2 °C grid at
all 15 corners) already covers this.

**The trip point is also short of DR-005's guard band under its
worst-corner reading.** DR-005's #69 append argues that the 25 °C guard band
above 125 °C must hold at the **worst** corner, which puts the trip-window
floor at ≥ 150 °C. In this record **6 of 15 corners trip below 150 °C**:
`tt_27c_3.63v` 147.0, `ss_27c_3.30v` 144.8, `ss_27c_3.63v` 138.9,
`sf_27c_2.97v` 149.0, `sf_27c_3.30v` 144.5 and `sf_27c_3.63v` 138.8 °C. The
bench does not flag this because its bound is the rated ceiling (125 °C),
not the guard band. Which reading of the guard band binds (worst-corner or
nominal-only) is still owed a ruling by #1, per that append; this record
does not make it. Like the hysteresis defect, this shortfall is a
junction-temperature property of the trip comparator measured directly on
the Tj axis. It is unrelated to θJA.

### Finding 2 — the bench assumes no θJA, no ambient, and no dissipation

- **No θJA.** `sim/thermal/testbench/tb_thermal_trip.sch` contains no
  thermal network, and ngspice's MOS models here have no self-heating. The
  swept `TEMP` is applied uniformly to every device: it *is* the junction
  temperature. There is no θJA value in the bench, the experiment manifest,
  or the record to be stated or mis-stated.
- **Neither short-circuit nor continuous rated load.** The bench's load is
  `RLOAD = 1.8 kΩ` (≈1 mA at the regulated output), a light-load functional
  probe of the shutdown comparator; the load does not set the temperature,
  the sweep does.
- **Ambient is never modelled, anywhere in `sim/`.** Every PVT bench's
  temperature axis (DR-004's `{−40, 27, 125} °C`) is likewise a uniform
  device temperature, i.e. Tj. The ratified row is specified in Tj, so
  evaluating it at the 125 °C corner is the right axis; ambient only enters
  through θJA, which the row delegates.

**Conclusion.** The 12/15 FAIL is not a θJA, ambient, or dissipation
finding. It is a real design defect in the DR-005 thermal-shutdown backstop
the row's Notes column carries: the auto-restart hysteresis is absent at
all 15 corners (0.0 °C at 12, within the ±2 °C grid at two, inverted at
`ff_27c_3.63v`), and the bench's `≥ 0` bound flags only three of them. The
backstop's trip point is also below DR-005's 150 °C worst-corner guard-band
floor at 6 of 15 corners (lowest 138.8 °C), pending #1's ruling on whether
that reading binds. Both are Tj-axis properties of the backstop. Neither is
a matter of an unstated θJA assumption. The FAIL verdict stands unchanged;
this record does not relax or reinterpret it.

What *is* true is #120's underlying observation: the θJA the row delegates
has never been written down as an explicit constraint derived from this
repo's own PVT evidence. DR-005's Context derived one number (θJA ≤
149 °C/W) from a single `tt`/27 °C screening point on an earlier circuit
revision, and nothing else in `spec/` states it. The Decision below records
it from the current `sim/` evidence.

## Decision

Record, as **the integration constraint this block imposes on its package**
(the row's delegated θJA, made explicit, not a new spec number), the two
limits below. `Ta` is the integrator's maximum ambient, which this block
does not own and this record does not choose. Evidence is from the current
records, PDK `sky130A` @ open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b`
(the `sim/pdk.json` pin).

**(A) Binding: continuous rated operation must hold `Tj ≤ 125 °C`.**

```
P_rated = (Vin_max − Vout_min) · I_load,max + Vin_max · I_q
        = (3.63 V − 1.764 V) · 50 mA + 3.63 V · 29.0 µA
        = 93.3 mW + 0.1 mW  ≈ 93.4 mW

θJA ≤ (125 °C − Ta) / 93.4 mW
```

Sources: `Vin_max` (Input row), `Vout_min = 1.8 V − 2 %` (Output row, the
worst case for pass-device drop), `I_load,max` (Load row), `I_q` = 29.0 µA,
the largest full-load bias draw at any of the 35 regulating corners of `sim/iq` record
[`20260910-034648-6c0436d`](../../sim/iq/records/20260910-034648-6c0436d.md)
(`ff_27c_3.63v`). That record's other 10 corners converged to non-regulating
DC solutions (Vout 2.7–3.4 V, mA-level supply current). Those are an Iq/DC
operating-point defect tracked under the Iq row, not a rated-operation
dissipation figure, so they are excluded here and not averaged in. The Iq
term is about 0.1 % of `P_rated`. Even a 10× larger bias draw would not move
the bound materially.

**(B) Informational: a sustained `Vout = 0` short at `Vin_max`.**
This is not bound by the 125 °C rated ceiling, because a short is a fault
and the DR-005 backstop covers it. It is recorded so that an integrator can
choose whether a short is held below the backstop's trip:

```
P_sc(Tj) = Vin_max · I_short(Tj)
θJA ≤ (125 °C − Ta) / P_sc(125 °C) = (125 °C − Ta) / 741 mW
```

`I_short` is the `ishort_sustained_ma` measurement of `sim/current-limit`
record
[`20260825-105322-933dfdd`](../../sim/current-limit/records/20260825-105322-933dfdd.md)
(45/45 PASS). At every process corner it falls monotonically with
temperature (e.g. `ss`: 236.0 → 221.5 → 204.1 mA at −40/27/125 °C, 3.63 V).
Because of that, holding `Tj ≤ 125 °C` under a short is governed by the
current at `Tj = 125 °C`. The worst process there is `ss` at 204.1 mA, which
gives 741 mW. The peak instantaneous short dissipation, into a cold die at
`ss`/−40 °C, is 3.63 V × 236.0 mA = 857 mW.

Illustrative values only. These are not ratified ambients: this block has
no ambient spec, and choosing one is the integrator's decision.

| `Ta` | (A) θJA ≤ (binding) | (B) θJA ≤ (short held below 125 °C) |
|---|---|---|
| 25 °C | 1071 °C/W | 135 °C/W |
| 85 °C | 428 °C/W | 54 °C/W |

If a package exceeds (B) but meets (A), the block is within its row: a
sustained short then drives Tj past 125 °C until the DR-005 backstop trips
(≥ 138.8 °C measured, model extrapolation beyond DR-004's axis) and
auto-restarts. The behaviour of that cycle is exactly what the open
`hysteresis_c` FAIL leaves unverified.

## Alternatives considered

- **Treat the 12/15 FAIL as a θJA-assumption artifact and add a θJA to the
  thermal bench.** Rejected. The bench has no θJA to correct, and the failing
  bound (`hysteresis_c ≥ 0`) does not depend on one. Adding a self-heating
  network would change what the bench measures, which is the shutdown
  comparator's trip/reset over Tj. It would not turn a negative hysteresis
  positive. Doing it to move the verdict would be the "relax a spec line to
  make a result pass" that CLAUDE.md forbids.
- **Close the gap by fixing the hysteresis in this issue.** Deferred, not
  rejected. #77 and #91 each spent a screening cycle on it and concluded it
  needs a regenerative latch/Schmitt redesign of the trip-comparator cluster,
  not another linear sizing knob. That is a full circuit-design cycle,
  outside #120's investigative scope. It is carried by **#131**, filed
  fresh as #91 instructed rather than inheriting an old issue number.
- **Set a ratified maximum ambient (e.g. 85 °C) and a single θJA number.**
  Rejected for this record. The row explicitly delegates θJA to
  package/integration, and there is no ratified ambient to derive a single
  number from. Inventing one would be the invented settled number CLAUDE.md
  forbids. The inequality in `Ta` is the constraint the block actually
  imposes; the table above is labelled illustrative.
- **Use the short-circuit bound (B) as the binding constraint.** Rejected.
  The row separates the continuous rated case (bounded by `Tj ≤ 125 °C`)
  from the short-circuit ceiling ("set by the current limit"), and DR-005
  places short-circuit protection above 125 °C with the backstop. Making (B)
  binding would add a requirement the ratified row does not state.
- **Port parity: take gf180-ldo's θJA figure.** Not applicable. DR-005's
  Context already records that `2AMLogic/gf180-ldo`'s ratified Thermal row
  (DR-0004, item A10) also delegates θJA to package/integration and states
  no θJA number, so there is none to align with. This record keeps the same
  structural choice (delegate, but state the constraint).

## Consequences

- **Answers #120's three questions.** (1) The failing corners assume no θJA;
  none exists in the bench, and none was needed for the failing bound.
  (2) They are neither short-circuit nor rated-load corners: a ≈1 mA
  functional sweep of the shutdown comparator. (3) Tj is evaluated directly
  (uniform device temperature); no bench models ambient, which is correct
  for a Tj-specified row.
- **The Thermal row's FAIL verdict is unchanged.** It is a design defect in
  the DR-005 backstop's auto-restart hysteresis, carried forward to #131. `measurements/characterization.md` now names the
  failing measurement (`hysteresis_c` at 3 corners) per row, so the verdict
  cannot be misread as a θJA question again. (The trip guard-band shortfall
  in Finding 1 is a Tj-axis concern the bench's bounds do not flag; it rests
  on #1's ruling on DR-005's #69 append.) The generator extracts this
  from the record's own per-measurement `pass` flags.
- **Records the delegated θJA constraint explicitly**, as inequalities (A)
  and (B) in the integrator's ambient. This refreshes DR-005's Context-section
  figure: 149 °C/W at 25 °C came from 673 mW, a `tt`/27 °C screening point on
  an earlier circuit revision. The worst-PVT short-circuit equivalent is now
  135 °C/W at 25 °C (741 mW at `ss`/125 °C). DR-005 is not edited. Its figure
  motivated the backstop and remains a correct statement of what it
  measured.
- **Hands to integration, unresolved**: the ambient, and so the actual θJA
  number. An integrator that also wants shorts held below the backstop's
  trip must meet (B), which is about 8× tighter than (A).
- **Hands to design, unresolved**: the hysteresis redesign (#131). Also: (A)'s rated-load term and (B)'s short-current term must be
  re-derived from fresh records if the pass device, output tolerance, or
  current limit changes. This record cites specific record IDs so that a
  stale input is detectable.

## Status notes

`proposed`. The record changes no ratified number; the Thermal row's target
text is unchanged, and its Notes column gains only a cross-reference to this
record. It becomes `ratified` on operator approval of the PR that lands it.
If a later ruling sets a ratified ambient, or moves θJA ownership into this
block, a superseding record replaces this one. This record is not edited.
