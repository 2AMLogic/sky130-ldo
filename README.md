# sky130-ldo

A low-dropout linear regulator (LDO) targeting the [sky130](https://github.com/google/skywater-pdk)
open PDK, built entirely on the open-source analog flow:
[xschem](https://xschem.sourceforge.io/) for schematic capture,
[ngspice](https://ngspice.sourceforge.io/) for simulation, and
[klayout-tools](https://github.com/2AMLogic/klayout-tools) (`klt`) for layout,
DRC, and LVS.

**Status: spec-ratified — designed, laid out, and simulated, not yet meeting
its own ratified spec.** Nothing here has been fabricated. `spec/target-spec.md`
is now **RATIFIED** (issue #1, [`DR-006`](spec/decision-records/DR-006-spec-ratification.md)
— see the scoreboard below). A schematic, a routed layout, DRC/LVS reports,
and a full 45-point PVT + Monte Carlo corner campaign (with a post-layout PEX
attempt) all exist, and the aggregated result is
[`measurements/characterization.md`](measurements/characterization.md) —
which currently shows the design **failing** most rows of the now-ratified
target specification; the open PVT-fix work is tracked in issue #60, and two
rows (PSRR, Stability) additionally have a topology-level root cause and a
proposed replacement disclosed in [`DR-007`](spec/decision-records/DR-007-psrr-stability-vs-iq.md)
(pending its own ratification). Read every number in this repo as either a
ratified target or a simulation result against an open PDK's models, with the
corner and testbench that produced it recorded alongside it.

## A design canary, not a reverse-engineering one

This block is a **clean-room DESIGN canary**: it is designed forward from a
written specification and first-principles device physics, not reverse-engineered
from anyone's silicon, netlist, or layout. No competitor part is measured,
delayered, decapped, or netlisted here, and none is needed — the LDO is a
textbook block, and the point is to design one honestly in the open PDK, not to
copy one. Keep it that way: if a task seems to want another party's implementation
detail, that is the signal to stop, because this canary's whole value is that it
owes nothing to anyone else's work.

The canary earns its keep two ways:

- **Dogfood for `klayout-tools`.** Driving a real analog block through the
  `klt` layout / DRC / LVS flow is the forcing function that surfaces the tool's
  rough edges. Every awkwardness or gap becomes a generic issue on the public
  [klayout-tools](https://github.com/2AMLogic/klayout-tools) tracker — see the
  friction protocol in [`CLAUDE.md`](CLAUDE.md).
- **Catalog inventory.** An LDO is a natural companion to a voltage reference in
  a power-management block; standing one up on sky130 alongside
  [sky130-bandgap](https://github.com/2AMLogic/sky130-bandgap) grows the
  inventory of verified open-PDK analog blocks the catalog can draw on.

## Built by agents

This block is designed by AI agents. The agents write the testbenches, run the
corners, argue the trade-offs in decision records, and open the pull requests;
the repository's conventions exist to keep that process honest rather than to
dress it up.

- **Verification is the product.** No claim lands without a testbench behind it,
  and every recorded result carries its PVT corners.
- **Evidence is append-only.** Files under `sim/` are never edited or deleted
  after they are written — a later run mints a new record rather than
  overwriting an inconvenient one.
- **The spec is a gate, not a suggestion.** Agents may not relax a spec line to
  make a result pass; changing it requires a decision record in `spec/`.

## Port parity with gf180-ldo

The specification and structure are deliberately mirrored from the ratified
[gf180-ldo](https://github.com/2AMLogic/gf180-ldo) — **same block, two PDKs is
the portability proof.** Where sky130 forces a departure from the gf180mcu design
(most notably the pass-device voltage flavor — sky130 has no native 3.3 V device,
so a 3.3 V-in / 1.8 V-out LDO reaches for the 5.0 V `pfet_g5v0d10v5`), the
divergence is called out in `spec/target-spec.md` and resolved through a decision
record, not assumed. That framing question was ratified first: the operator's
ruling on #1
([2026-08-14](https://github.com/2AMLogic/sky130-ldo/issues/1#issuecomment-5297123803))
ratified
[DR-001](spec/decision-records/DR-001-pass-device-supply-framing.md)'s
recommendation — `sky130_fd_pr__pfet_g5v0d10v5` as the pass device, 3.3 V ±10% in
/ 1.8 V out / 0–50 mA, preserving port parity with gf180-ldo. The full numeric
target table is now ratified too, unchanged from its gf180-ldo-mirrored
starting point — see the scoreboard below.

## Private, for now

This repo is **private** while the spec is drafted and the harness is stood up.
Two consequences that matter even before it opens:

- The [klayout-tools](https://github.com/2AMLogic/klayout-tools) issue tracker
  this repo files friction against **is already public**. The friction protocol's
  "describe the tool gap, not this design" rule is therefore load-bearing today,
  not a future concern — see [`CLAUDE.md`](CLAUDE.md).
- Going public is an operator decision, not an agent one, and inherits the
  workspace's disclosure and firewall rules. Until then, write commits, issues,
  and documents as private working material.

## Target specification (RATIFIED — see [`spec/target-spec.md`](spec/target-spec.md))

Ratified by the operator on issue #1 via
[`spec/decision-records/DR-006-spec-ratification.md`](spec/decision-records/DR-006-spec-ratification.md),
which also ratifies DR-001 (pass-device/supply framing), DR-002 (output
capacitor / ESR window), DR-003 (sky130 device characterization), DR-004
(corner-model names) and DR-005 (thermal-shutdown trip/hysteresis/reference).
Changing a line below requires a new decision record; it may not be relaxed
to make a result pass — see DR-006 for why the currently-failing rows below
were ratified unchanged rather than loosened. Two rows (PSRR, Stability) are
additionally covered by
[`DR-007`](spec/decision-records/DR-007-psrr-stability-vs-iq.md), which
root-causes their failure to the shipped topology and proposes replacement
numbers as a starting point for a future ratification — **not adopted by the
table below**, which keeps DR-007's rows exactly as originally ratified,
pending DR-007's own market-comparison mechanism.

| Parameter | Target | Stretch |
|---|---|---|
| Input | 3.3 V ±10% (2.97–3.63 V) | 5 V flavor — separate follow-on variant (DR-001) |
| Output | 1.8 V ±2% (fixed; divider as a unit-resistor string) | programmable 1.2–3.0 V — deferred |
| Load | 0–50 mA (0 mA = no external load; feedback divider is the only inherent preload) | 100 mA |
| Dropout @ 50 mA | < 300 mV (note 1) | < 200 mV |
| Line regulation | < 5 mV/V over 2.97–3.63 V, at 1 mA and 50 mA (note 2) | — |
| Load regulation (0–50 mA) | < 1% (18 mV), counted inside the ±2% window (note 2) | — |
| Load transient | 1↔50 mA step, ~1 µs edges: peak excursion ≤ 150 mV, recover to ±1% in ≤ 20 µs, over the ratified C_out/ESR window (note 3) | peak ≤ 100 mV |
| PSRR | > 50 dB @ 1 kHz and > 20 dB @ 100 kHz, at 1 mA and 50 mA (note 4) | > 60 dB @ 1 kHz, > 30 dB @ 100 kHz |
| Iq (excl. load current) | < 30 µA at no load and at full load (50 mA), every PVT corner (note 5) | < 10 µA |
| Current limit | constant-current (brickwall) clamp, window TBD over PVT; never engages for I_load ≤ 50 mA; survives continuous Vout = 0 short at Vin_max (note 6) | — |
| Startup / soft-start | monotonic into any load 0–50 mA and any C_out in the stability window; controlled ramp; inside ±2% within a few ms of enable; overshoot ≤ +2% (note 6) | — |
| Enable / shutdown | shutdown Iq < 3 µA worst corner; disabled output = pass device fully off, no active discharge; Vin→Vout leakage ≤ 1 µA (note 6) | — |
| Thermal | continuous worst-case dissipation set by Vin_max × I_load; specified to Tj ≤ 125 °C; fault-only shutdown backstop 150 °C trip / 135 °C reset (note 7) | — |
| Output noise | not specified — waived unless a consumer states a requirement | µVrms row if a consumer asks |
| Area | < 0.1 mm² total core area, pass FET included, excluding pads and sealring | — |
| Stability | stable 0–50 mA over the ratified C_out/ESR window; PM ≥ 45°, GM ≥ 10 dB worst corner (note 4) | capless variant (separate fork) |

Notes — these are part of the ratified spec, not commentary:

1. **Dropout**, test point `V_in = V_out + dropout`, binding corners `{ss,
   sf}` at 125 °C (DR-003). **Current verdict: FAIL** — 0/45 PVT corners
   pass, best case 365 mV (`ss`/−40 °C). Tracked design gap, no superseding
   record proposed.
2. **Line regulation / Load regulation** have no dedicated sky130 porting
   note beyond the ratified numbers themselves. **Current verdict: FAIL** —
   18/45 and 34/45 PVT corners pass respectively. Tracked design gaps, no
   superseding record proposed.
3. **Load transient**, over the ratified C_out/ESR window (0.33–4.7 µF,
   0–500 mΩ, no minimum ESR, ceramic-stable — DR-002). **Current verdict:
   FAIL** — 25/45 PVT corners pass. Tracked design gap, no superseding
   record proposed.
4. **PSRR and Stability** are disclosed FAIL — PSRR 0/45 PVT corners, now
   measured at **both** ratified load points (#117): the 1 kHz sub-metric
   fails at 1 mA and at 50 mA alike (20.25–25.70 dB against the 50 dB floor),
   and the 100 kHz sub-metric passes 45/45 at 1 mA (31.53–34.77 dB) but fails
   0/45 at 50 mA (13.80–16.06 dB against the 20 dB floor); Stability 7/45 PVT corners,
   confirmed stable at every load ≥ 1 mA within the window (DR-002 append),
   with the 0 mA end the binding, unresolved gap. Unlike the other FAIL rows,
   both have a topology-level root cause and a named superseding proposal:
   [`DR-007`](spec/decision-records/DR-007-psrr-stability-vs-iq.md)
   (`proposed`) recommends PSRR ≥ 18 dB @ 1 kHz / ≥ 28 dB @ 100 kHz and a
   Stability floor scoped to `I_load ≥ 1 mA` only — not adopted here, and
   pending its own ratification via the two-key market-comparison mechanism.
5. **Iq** is set by
   [`DR-009`](spec/decision-records/DR-009-iq-budget.md) (`proposed`; it
   ratifies on merge of its PR, per 2AMLogic/2am#357). The number comes from
   gf180-ldo parity, checked against a sky130 device-fact budget and public
   comps, not from the measured result. It closes the item DR-003/DR-006 left
   open. No named binding corner (DR-004 caveat). **Current verdict: FAIL**
   — 36/45 PVT corners pass. All 9 failing corners are non-regulating DC
   operating points (#71/#81 → #79), not bias overspend (DR-009
   Consequences).
6. **Current limit, Startup/soft-start, and Enable/shutdown** all **PASS**
   (45/45 PVT corners each) — the only three rows with a testbench that
   currently meet their ratified target.
7. **Thermal**'s fault-only 150 °C/135 °C trip/reset backstop is
   internally-generated (not `VREF`, not a bandgap), auto-restart, per
   DR-005; it sits outside this repo's characterized 125 °C temperature
   ceiling and is PVT-loose. **Current verdict: FAIL** — 12/15 corners pass.
   Tracked design gap, no superseding record proposed.

**Current verdict per row**: this table states the ratified target, not the
current pass/fail state of the evidence behind it — for that, see
[`measurements/characterization.md`](measurements/characterization.md), a
generated (not hand-maintained) rollup that cites the exact `sim/<slug>/records/`
record behind every row's current verdict. Regenerate it with
`python3 measurements/build_characterization_report.py` after any `sim/`
record lands or `design/` changes; this table (the ratified spec + notes
above) stays the authority on what is required, `measurements/characterization.md`
on what the evidence currently shows.

Maturity ladder: spec-ratified → simulation-complete → layout DRC/LVS-clean →
shuttle seat → measured silicon over temperature. **Current position:
spec-ratified** — simulation and layout work are underway (see the scoreboard
above) but do not yet clear most ratified rows.

## Repository layout

```
spec/          ratified spec + decision records
design/        schematics / netlists (xschem)
sim/           testbenches + PVT corner results (ngspice)
layout/        GDS + DRC/LVS reports (klayout-tools driven)
measurements/  generated characterization report (see characterization.md)
```

## Environment setup

The open-source flow (xschem + ngspice + the sky130 PDK fetched via `volare`,
plus `klt` for the layout flow) is bootstrapped (issue #2), seeded from the
working harnesses in [sky130-bandgap](https://github.com/2AMLogic/sky130-bandgap)
(sky130 flow, `klt` layout/DRC/LVS driver) and
[gf180-ldo](https://github.com/2AMLogic/gf180-ldo) (LDO testbench structure).
See [`docs/environment-setup.md`](docs/environment-setup.md) for the
reproducible bring-up, [`sim/README.md`](sim/README.md) for the sim harness,
and [`layout/README.md`](layout/README.md) for the layout flow. The harness
was proven end to end (env check, sim selftest, trivial-cell DRC/LVS flow)
before LDO design content — schematic, layout, testbenches — began landing
against the (at the time still-DRAFT) target spec; `spec/target-spec.md` is
now ratified (issue #1, DR-006) and the design work described above and in
`design/`/`sim`/`layout/` targets that ratified table.

## License

The sky130 PDK is not distributed here; it is fetched separately and carries its
own Apache-2.0 license from Google and SkyWater. This repo's own license is set
at creation.
