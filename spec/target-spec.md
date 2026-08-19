# Target specification — RATIFIED

**Status: RATIFIED**, per issue #1 / [`DR-006`](decision-records/DR-006-spec-ratification.md)
(the operator's PR approval on the ratifying PR is the ratification act, per
the 2026-08-19 ratification-via-PR standing policy,
[2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357)). Ratification
fixes what this block's **target** numbers are — it is not a certification
that the current implementation meets them. As of this ratification, it does
not: see [`measurements/characterization.md`](../measurements/characterization.md)
for the live, regenerated rollup of current conformance, which shows several
rows FAIL against the targets below. That is a disclosed, tracked design gap
for follow-on work, per DR-006 — not a reason the targets themselves are
unsettled. One row remains explicitly open rather than ratified to a number:
Iq (see its row note) — DR-003 declined to set one, and no other record sets
it either; a future decision record is required before that row can be cited
as final. No other row is provisional.

## Where these numbers come from

Two sources, cited per row, neither of which is silicon:

1. **gf180-ldo (ratified).** The primary source. This block is a sky130 port of
   [`2AMLogic/gf180-ldo`](https://github.com/2AMLogic/gf180-ldo), whose target
   spec was ratified 2026-07-31. Same block, two PDKs — so this table starts by
   mirroring gf180-ldo's ratified table, then flags every place sky130 forces a
   departure. gf180-ldo's own numbers are simulation results against the gf180mcu
   open PDK, not measured silicon.
2. **Published sky130 references, plus this repo's own device characterization
   (DR-001, DR-003).** The SkyWater sky130 PDK documentation and its published
   device menu — the 1.8 V core devices (`pfet_01v8`, `nfet_01v8`), the 5.0 V
   devices (`pfet_g5v0d10v5`, `nfet_g5v0d10v5`), and the poly resistors
   (`res_high_po`, `res_xhigh_po`) — plus this repo's own screening decks
   against the pinned PDK's models (DR-001, DR-003), which ground the dropout
   test-point convention, binding-corner finding, and pass-device sizing. No
   number below is copied from a third-party datasheet.

Where a value cannot yet be sourced from either — because it depends on a
sky130-specific device measurement this repo has not run — the row says so and
carries no number rather than an invented one. As of this ratification, that
applies only to the Iq row.

## The central sky130 porting question — RATIFIED (framing A)

gf180-ldo uses the gf180mcu 3.3 V PMOS (`pfet_03v3`) as its pass device for a
3.3 V input. **sky130 has no native 3.3 V flavor.** A 3.3 V-in / 1.8 V-out LDO on
sky130 therefore had two candidate framings, argued in
[`spec/decision-records/DR-001-pass-device-supply-framing.md`](decision-records/DR-001-pass-device-supply-framing.md):

- **(A) 5.0 V pass device.** Use `pfet_g5v0d10v5` for a 3.3 V input, preserving
  gf180-ldo's 3.3 V → 1.8 V port-parity intent. Costs area and gate drive; buys
  headroom and short-tolerance.
- **(B) 1.8 V-core re-scope.** Keep everything on `pfet_01v8`/`nfet_01v8` and
  re-scope the input toward the core rail. Cheaper and denser, but **cannot
  produce 1.8 V out from a 1.8 V-class input** — it changes the block's mission
  and breaks port parity with gf180-ldo.

**(A) ratified per DR-001/#1** — the operator's ruling on #1
([2026-08-14](https://github.com/2AMLogic/sky130-ldo/issues/1#issuecomment-5297123803))
ratified framing (A): pass device `sky130_fd_pr__pfet_g5v0d10v5`, 3.3 V ±10% in /
1.8 V out / 0–50 mA, port parity with `2AMLogic/gf180-ldo`. That ruling was
scoped to the framing question only; the numeric table below has since been
ratified in full via DR-006 (see "Status" above) — every row is now RATIFIED
except Iq, which stays explicitly open. Framing (C) (5 V pass device with a
core-device error-amplifier core) remains an open refinement inside (A),
deferred to a later topology decision record.

## RATIFIED target table

Every row is **RATIFIED (DR-006/#1)** except Iq, which is explicitly open —
see its note. "Src" cites gf180-ldo's ratified row (G) and/or sky130 published
references / this repo's own device characterization (S). **Ratified means
this is the target**, not a claim the current implementation meets it — see
[`measurements/characterization.md`](../measurements/characterization.md) for
current conformance per row.

| Parameter | Target | Stretch | Src | sky130 porting note |
|---|---|---|---|---|
| Input | 3.3 V ±10% (2.97–3.63 V) | 5 V flavor as a separate follow-on variant | G | `pfet_g5v0d10v5` under ratified framing (A), DR-001. |
| Output | 1.8 V ±2% (fixed; divider as a unit-resistor string) | programmable 1.2–3.0 V — deferred | G | 1.8 V is the sky130 core rail. Current implementation: FAIL (181/200 mismatch samples at one PVT point) — light-load pole, tracked design gap, see `measurements/characterization.md`. |
| Load | 0–50 mA (0 mA = no external load; feedback divider is the only inherent preload) | 100 mA | G | Pass-device W = `sky130_fd_pr__pfet_g5v0d10v5` sized to DR-003's ≈2.5 mm-class methodology. |
| Dropout @ 50 mA | < 300 mV | < 200 mV | G+S | Test point `V_in = V_out + dropout` (not `V_in_min`), binding corners `{ss, sf}` co-binding at 125 °C — DR-003. Current implementation: FAIL (0/45 PVT corners; best case 365 mV), tracked design gap. |
| Line regulation | < 5 mV/V over 2.97–3.63 V, at 1 mA and 50 mA | — | G | No dedicated testbench yet — see `measurements/characterization.md`. |
| Load regulation (0–50 mA) | < 1% (18 mV), counted inside the ±2% window | — | G | No dedicated testbench yet — see `measurements/characterization.md`. |
| Load transient | 1↔50 mA step, ~1 µs edges: peak excursion ≤ 150 mV, recover to ±1% in ≤ 20 µs, over the ratified C_out/ESR window | peak ≤ 100 mV | G | C_out/ESR window: 0.33–4.7 µF, 0–500 mΩ, no minimum ESR, ceramic-stable — DR-002. Current implementation: FAIL (23/45 PVT corners), tracked design gap. |
| PSRR | > 50 dB @ 1 kHz and > 20 dB @ 100 kHz, at 1 mA (light-load, binding) and at 50 mA | > 60 dB @ 1 kHz, > 30 dB @ 100 kHz | G+S | Current implementation: FAIL (6/45 PVT corners at the ~1 mA point currently covered; 50 mA point not yet testbenched), tracked design gap. |
| Iq (excl. load current) | **OPEN — not ratified.** No number set. | — | — | DR-003 explicitly declines to set an Iq figure (no amplifier/bias topology existed when it was drafted); a future decision record is required. The current loop-gain-sized design's own bias draw (≈24.9 µA at 50 mA) is a data point for that future record, not a ratified target. |
| Current limit | constant-current (brickwall) clamp, window TBD over PVT; never engages for I_load ≤ 50 mA; survives continuous Vout = 0 short at Vin_max | — | G | Implemented per #22/#26; no dedicated clamp-threshold testbench yet — see `measurements/characterization.md`. |
| Startup / soft-start | monotonic into any load 0–50 mA and any C_out in the stability window; controlled ramp; inside ±2% within a few ms of enable; overshoot ≤ +2% | — | G | Implemented per #22/#26; no dedicated startup-transient testbench yet — see `measurements/characterization.md`. |
| Enable / shutdown | shutdown Iq < 3 µA worst corner; disabled output = pass device fully off, no active discharge; Vin→Vout leakage ≤ 1 µA | — | G | No dedicated testbench yet — see `measurements/characterization.md`. |
| Thermal | continuous worst-case dissipation set by Vin_max × I_load; short-circuit ceiling set by the current limit; specified to Tj ≤ 125 °C (rated-operation ceiling, unchanged); θJA delegated to package/integration | — | G | Fault-only thermal-shutdown backstop above this ceiling: 150 °C nominal trip / 135 °C nominal reset, auto-restart, internally-generated bias-derived reference (not `VREF`, not a bandgap) — DR-005. 150 °C sits outside this repo's characterized 125 °C temperature ceiling and is PVT-loose; no dedicated testbench yet — see DR-005 Consequences and `measurements/characterization.md`. |
| Output noise | not specified — waived unless a consumer states a requirement | µVrms row if a consumer asks | G | Waiver mirrors gf180 note 7. |
| Area | < 0.1 mm² total core area, pass FET included, excluding pads and sealring | — | G+S | No dedicated area-extraction check yet — see `measurements/characterization.md`. |
| Stability | stable 0–50 mA over the ratified C_out/ESR window; PM ≥ 45°, GM ≥ 10 dB worst corner | capless variant (separate fork) | G | Current implementation: FAIL (3/45 PVT corners) — confirmed stable at every load ≥ 1 mA within the window (DR-002 append); the 0 mA end of the load range is the binding, unresolved gap (15.6–19.3° PM at 0.33 µF, 38.1° at 4.7 µF/`ss`), root-caused to the pass stage's own load-dependent pole, tracked design gap. |

## Verification corners (RATIFIED, DR-004)

process {tt, ff, ss, fs, sf} × T {−40, 27, 125} °C × Vin {2.97, 3.3, 3.63} V,
plus the ratified output-capacitor window. The five process names bind
directly to the identically-named `.lib` sections in
`libs.tech/combined/sky130.lib.spice` at the pinned open_pdks commit — no
translation layer needed (DR-004). `ll`, `hh`, the combined resistor/cap-skew
sections, the `_mm` mismatch sections, and `mc` Monte Carlo are confirmed
available in the pinned library but are **not** bound by this matrix — a
future record specifying a resistor-topology or statistical-mismatch claim
extends or supersedes this binding.

**Naming-severity caveat (DR-004):** the corner-name letters do **not**
predict severity for `sky130_fd_pr__pfet_g5v0d10v5` at this block's sizing
point. DR-003's screening shows `R_on·W` and `|V_th|` group by the corner
name's *first* letter, not the second — `{ss, sf}` cluster worst, `{ff, fs}`
cluster best, with `sf` marginally the single worst point measured. No spec
row or design decision may infer which corner binds from the letters alone;
it must be measured, per device, per bias point.

## Open items — all resolved

1. **Pass-device flavor (A vs B above).** **Resolved: framing (A) ratified per
   DR-001/#1** (2026-08-14).
2. **Output-capacitor / ESR window.** **Resolved: ratified per DR-002/#1**
   (2026-08-19, DR-006) — 0.33–4.7 µF, 0–500 mΩ, no minimum ESR.
3. **sky130 device characterization.** **Resolved: ratified per DR-003/#1**
   (2026-08-19, DR-006) — dropout test-point convention and binding-corner
   finding ratified; the Iq budget number stays explicitly open (DR-003 never
   proposed one).
4. **Corner-model names.** **Resolved: ratified per DR-004/#1** (2026-08-19,
   DR-006) — bound to the sky130 `.lib` section names, no translation needed.

A fifth input, not in this list at the time it was originally written because
the need for it was discovered later (thermal-shutdown circuitry work, #24/
#28): **thermal-shutdown trip temperature, hysteresis, and reference
strategy — resolved: ratified per DR-005/#1** (2026-08-19, DR-006) — 150 °C
nominal trip, 135 °C nominal reset, internally-generated reference,
auto-restart.

Decision records live in `spec/decision-records/` (copy `TEMPLATE.md`, four-digit
`DR-NNNN-<slug>.md`, one decision per record, append-only — supersede, never
edit). The ratifying record for the table as a whole is
[`DR-006`](decision-records/DR-006-spec-ratification.md), which also records
that several rows' targets are not yet met by the current implementation —
see `measurements/characterization.md` for current conformance, and DR-006 for
why the targets were ratified unchanged rather than relaxed to match.
