# Target specification — DRAFT

**Status: DRAFT. Nothing in this file is ratified.** Every value below is marked
"DRAFT — to be ratified" and is a **starting point for engineering ratification,
not a settled datasheet number.** Ratification is gated on issue #1 and is an
operator decision (the T1 gate). Until then, no design or simulation work may
treat any row here as final, and agents must not replace a draft with an invented
"final" number — a value becomes settled only when a decision record ratifies it.

## Where these numbers come from

Two sources, cited per row, neither of which is silicon:

1. **gf180-ldo (ratified).** The primary source. This block is a sky130 port of
   [`2AMLogic/gf180-ldo`](https://github.com/2AMLogic/gf180-ldo), whose target
   spec was ratified 2026-07-31. Same block, two PDKs — so the DRAFT starts by
   mirroring gf180-ldo's ratified table, then flags every place sky130 forces a
   departure. gf180-ldo's own numbers are simulation results against the gf180mcu
   open PDK, not measured silicon.
2. **Published sky130 references (starting point only).** The SkyWater sky130 PDK
   documentation and its published device menu — the 1.8 V core devices
   (`pfet_01v8`, `nfet_01v8`), the 5.0 V devices (`pfet_g5v0d10v5`,
   `nfet_g5v0d10v5`), and the poly resistors (`res_high_po`, `res_xhigh_po`) — plus
   the general body of open sky130 analog work. These inform what is *achievable*
   on sky130; they are **not** transcribed as this block's targets. No number
   below is copied from a third-party datasheet as a settled spec.

Where a value cannot yet be sourced from either — because it depends on a
sky130-specific device measurement this repo has not run — the row says so and
carries no number rather than an invented one.

## The central sky130 porting question (must be resolved before ratification)

gf180-ldo uses the gf180mcu 3.3 V PMOS (`pfet_03v3`) as its pass device for a
3.3 V input. **sky130 has no native 3.3 V flavor.** A 3.3 V-in / 1.8 V-out LDO on
sky130 therefore has two candidate framings, and issue #1 must pick one via a
decision record:

- **(A) 5.0 V pass device.** Use `pfet_g5v0d10v5` for a 3.3 V input, preserving
  gf180-ldo's 3.3 V → 1.8 V port-parity intent. Costs area and gate drive; buys
  headroom and short-tolerance.
- **(B) 1.8 V-core re-scope.** Keep everything on `pfet_01v8`/`nfet_01v8` and
  re-scope the input toward the core rail. Cheaper and denser, but **cannot
  produce 1.8 V out from a 1.8 V-class input** — it changes the block's mission
  and breaks port parity with gf180-ldo.

The DRAFT below is written against framing **(A)** as the parity-preserving
default, and every affected row is flagged. Choosing (B) at ratification changes
several rows at once.

## DRAFT target table

Every row is **DRAFT — to be ratified (issue #1)**. "Src" cites gf180-ldo's
ratified row (G) and/or sky130 published references (S).

| Parameter | DRAFT target (starting point) | DRAFT stretch | Src | sky130 porting note |
|---|---|---|---|---|
| Input | 3.3 V ±10% (2.97–3.63 V) | 5 V flavor as a separate follow-on variant | G | Needs a >3.3 V-tolerant pass device; `pfet_g5v0d10v5` under framing (A). To be ratified. |
| Output | 1.8 V ±2% (fixed; divider as a unit-resistor string) | programmable 1.2–3.0 V — deferred | G | 1.8 V is the sky130 core rail; a 1.8 V output from a 1.8 V input is not achievable, which is why the input flavor question gates this row. To be ratified. |
| Load | 0–50 mA (0 mA = no external load; feedback divider is the only inherent preload) | 100 mA | G | Pass-device W scales with the chosen sky130 flavor; sizing pending device characterization. To be ratified. |
| Dropout @ 50 mA | < 300 mV | < 200 mV | G+S | Binding corner and test point to be set from sky130 device data; gf180's ss/125 °C/Vin≈Vout+dropout convention is the DRAFT starting point. To be ratified. |
| Line regulation | < 5 mV/V over 2.97–3.63 V, at 1 mA and 50 mA | — | G | To be ratified. |
| Load regulation (0–50 mA) | < 1% (18 mV), counted inside the ±2% window | — | G | To be ratified. |
| Load transient | 1↔50 mA step, ~1 µs edges: peak excursion ≤ 150 mV, recover to ±1% in ≤ 20 µs, over the ratified C_out/ESR window | peak ≤ 100 mV | G | C_out/ESR window is a separate DRAFT decision (mirrors gf180 DR-0001). To be ratified. |
| PSRR | > 50 dB @ 1 kHz and > 20 dB @ 100 kHz, at 1 mA (light-load, binding) and at 50 mA | > 60 dB @ 1 kHz, > 30 dB @ 100 kHz | G+S | Achievable PSRR depends on sky130 pass-device and loop; number is a starting point pending loop sim. To be ratified. |
| Iq (excl. load current) | < 30 µA at no load and full load | < 10 µA | G+S | sky130 bias-device menu differs; budget to be re-derived from sky130 device char. To be ratified. |
| Current limit | constant-current (brickwall) clamp, window TBD over PVT; never engages for I_load ≤ 50 mA; survives continuous Vout = 0 short at Vin_max | — | G | Short-survival dissipation depends on the chosen sky130 pass flavor. To be ratified. |
| Startup / soft-start | monotonic into any load 0–50 mA and any C_out in the stability window; controlled ramp; inside ±2% within a few ms of enable; overshoot ≤ +2% | — | G | To be ratified. |
| Enable / shutdown | shutdown Iq < 3 µA worst corner; disabled output = pass device fully off, no active discharge; Vin→Vout leakage ≤ 1 µA | — | G | Leakage numbers pending sky130 device data. To be ratified. |
| Thermal | continuous worst-case dissipation set by Vin_max × I_load; short-circuit ceiling set by the current limit; specified to Tj ≤ 125 °C; θJA delegated to package/integration | — | G | Absolute mW figures depend on the chosen pass flavor. To be ratified. |
| Output noise | not specified — waived unless a consumer states a requirement | µVrms row if a consumer asks | G | To be ratified (waiver mirrors gf180 note 7). |
| Area | < 0.1 mm² total core area, pass FET included, excluding pads and sealring | — | G+S | sky130 5.0 V devices are larger than gf180's 3.3 V devices; the area target may need revisiting under framing (A). To be ratified. |
| Stability | stable 0–50 mA over the ratified C_out/ESR window; PM ≥ 45°, GM ≥ 10 dB worst corner | capless variant (separate fork) | G | To be ratified. |

## Verification corners (DRAFT)

Starting point mirrored from gf180-ldo, to be ratified against the sky130 corner
set: process {tt, ff, ss, fs, sf} × T {−40, 27, 125} °C × Vin {2.97, 3.3, 3.63} V,
plus the ratified output-capacitor window. The exact sky130 corner-model names and
any binding-corner assignments (e.g. dropout, Iq, current limit) are to be fixed at
ratification.

## Open items that must close before ratification

1. **Pass-device flavor (A vs B above).** The single most consequential decision;
   several rows depend on it. Decision record required.
2. **Output-capacitor / ESR window.** Mirror gf180-ldo's DR-0001 or re-derive for
   sky130. Decision record required.
3. **sky130 device characterization.** Dropout test point, pass-device sizing, Iq
   budget, and leakage rows all carry provisional or absent numbers until device
   char against the sky130 models exists. No such number is invented here.
4. **Corner-model names.** Bind the DRAFT corner set to the actual sky130 model
   corner identifiers.

Decision records live in `spec/decision-records/` (copy `TEMPLATE.md`, four-digit
`DR-NNNN-<slug>.md`, one decision per record, append-only — supersede, never
edit). A row is ratified only when a decision record says so.
