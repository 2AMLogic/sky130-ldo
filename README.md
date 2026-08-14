# sky130-ldo

A low-dropout linear regulator (LDO) targeting the [sky130](https://github.com/google/skywater-pdk)
open PDK, built entirely on the open-source analog flow:
[xschem](https://xschem.sourceforge.io/) for schematic capture,
[ngspice](https://ngspice.sourceforge.io/) for simulation, and
[klayout-tools](https://github.com/2AMLogic/klayout-tools) (`klt`) for layout,
DRC, and LVS.

**Status: bootstrapping. Nothing here has been fabricated, and nothing has been
verified yet.** The repo starts with a DRAFT target specification (see
[`spec/target-spec.md`](spec/target-spec.md)) and no design, no simulation
evidence, and no layout. Read every number in this repo as a target awaiting
ratification, or — once work begins — as a simulation result against an open
PDK's models, with the corner and testbench that produced it recorded alongside
it.

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
record, not assumed.

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

## Target specification (DRAFT — see [`spec/target-spec.md`](spec/target-spec.md), ratify on issue #1)

The full DRAFT table, with every value marked "DRAFT — to be ratified" and each
sourced from gf180-ldo's ratified spec plus published sky130 references, lives in
[`spec/target-spec.md`](spec/target-spec.md). It is a **starting point for
engineering ratification, not a settled datasheet.** Ratification is gated on
issue #1 and is an operator decision.

Maturity ladder: spec-ratified → simulation-complete → layout DRC/LVS-clean →
shuttle seat → measured silicon over temperature. **Current position: pre-ladder**
— the spec is still a draft.

## Repository layout

```
spec/          target spec (DRAFT) + decision records
design/        schematics / netlists (xschem)
sim/           testbenches + PVT corner results (ngspice)
layout/        GDS + DRC/LVS reports (klayout-tools driven)
measurements/  silicon characterization (empty until tape-out)
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
is proven end to end (env check, sim selftest, trivial-cell DRC/LVS flow) but
carries no LDO design content yet — no schematic, no LDO layout — that starts
once `spec/target-spec.md` is ratified (issue #1).

## License

The sky130 PDK is not distributed here; it is fetched separately and carries its
own Apache-2.0 license from Google and SkyWater. This repo's own license is set
at creation.
