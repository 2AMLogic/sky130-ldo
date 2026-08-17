# `layout/ldo-core/` floorplan

Issue #15's deliverable: a physical layout for the sky130 LDO's core
regulation loop, corresponding 1:1 (per active device) to
`design/ldo_3v3in_1v8out.sch` (issue #14). Scope is a **DRC-clean placed
floorplan skeleton** — one `klt gen` device block per schematic device,
positioned by function group via `klt gen-compose`'s
`placement.strategy: "explicit"`. No inter-block routing, no extraction, no
LVS: that mirrors the closest real precedent for this kind of issue,
`2AMLogic/sky130-bandgap`'s own issue #15 (floorplan + placed skeleton,
DRC-clean, LVS deferred to a follow-on), and lines up with this repo's own
issue split — #16 (DRC-report closure) and #17 (LVS) both explicitly depend
on this issue rather than arguing for a different scope for it.

## Device-to-block mapping

Every active device in the schematic gets exactly one `klt gen` block,
sized to match the schematic's own `model`/`L`/`W`/`nf` fields:

| Schematic device(s) | `klt gen` generator | Params (schematic → generator) |
|---|---|---|
| `M_BIASN1`, `M_ENN`, `M_BIASN2`, `M_MIR1`, `M_MIR2`, `M_ENN2` | `mos_array`, `flavor: "nfet"` | `w_um`=schematic `W`, `l_um`=schematic `L`, `fingers`=schematic `nf`, `rows=1 cols=1 dummy=0` (one physical device, not a matched array) |
| `M_BIASP1`, `M_ENP2`, `M_TAIL`, `M_IN1`, `M_IN2`, `M_ENP`, `M_PASS` | `mos_array`, `flavor: "pfet"` | same mapping, `pfet` flavor draws the well sky130's PMOS devices need |
| `R_BIAS` (`res_high_po`, `W=0.42 L=1500`) | `res_array`, `flavor: "high"` | `length_um=1500 width_um=0.42 num=1 dummy=0` — a single unit, not a matched pair, so no dummy protection needed |
| `R_FB_A`/`R_FB_B`/`R_FB_C` (three identical `res_xhigh_po`, `W=0.42 L=180`, in series) | `res_array`, `flavor: "xhigh"` | `length_um=180 width_um=0.42 num=3 dummy=1` — one block draws all three unit resistors of the divider string in series, which is the more faithful physical rendering of "three identical unit resistors in series" than three separate single-unit blocks, and `dummy=1` protects the matching the divider's 2:1 ratio accuracy depends on |
| `C_COMP` (Miller compensation cap, MiM, `2p`, placeholder value) | *(none — known gap, see below)* | not drawn |

13 MOS devices + 2 resistor blocks (covering all 4 resistor instances) =
**15 `klt gen` blocks**, one JSON generator report + GDS per block, checked
into each run's `reports/<record-id>/` directory alongside the composed
top-level GDS.

### Known gap: no `klt gen` capacitor generator for `C_COMP`

At this repo's pinned `klt` commit, `klt gen --list` has no capacitor/MiM
family member alongside `mos_array`/`res_array`/`diff_pair`/`bjt_array`,
even though `klt extract` recognises a MiM `CapacitorDevice` class. `C_COMP`
is therefore not drawn in this layout. This is not scope creep to defer:
`design/README.md` already documents `C_COMP`'s `2p` value as a
**placeholder**, not sized against a loop-gain simulation (pending DR-002,
`proposed` not ratified) — so there is no verified value to lay out yet
either way. Filed as a generic capability gap per `CLAUDE.md`'s friction
protocol:
[`2AMLogic/klayout-tools#1117`](https://github.com/2AMLogic/klayout-tools/issues/1117)
("no capacitor/MiM generator in `klt gen`'s device-generator family") — no
design-specific detail in that filing.

## Row grouping and placement rationale

Blocks are grouped into five floorplan rows (bottom to top), matching
`design/README.md`'s own functional grouping of the schematic:

1. **`bias_resistor`** — `R_BIAS` alone (`res_high_po`, `W=0.42 L=1500`).
2. **`fb_resistor`** — `R_FB` (the 3-unit divider string, `res_xhigh_po`).
3. **`bias_enable`** — the resistor-referenced bias generator and its
   EN-gated ground return: `M_BIASN1`, `M_ENN`, `M_BIASN2`, `M_BIASP1`,
   `M_ENP2`.
4. **`error_amp`** — the 5T OTA and its own EN-gated mirror-load return:
   `M_TAIL`, `M_IN1`, `M_IN2`, `M_MIR1`, `M_MIR2`, `M_ENN2`, `M_ENP`.
5. **`output_pass`** — `M_PASS`, the series pass device, alone.

Within a row, blocks are packed left-to-right with a flat 5µm gap between
adjacent bounding boxes; rows are stacked with a flat 20µm gap. Both margins
were chosen generously above sky130's own well/tap/diffusion spacing rules
(sub-2µm) specifically so a first floorplan pass would not need a
DRC-violation-driven iteration loop — confirmed DRC-clean on the first
composed run (see the newest `reports/<record-id>/record.md`).

**Why the two resistor blocks get their own dedicated rows, separate from
the compact MOS core**: `R_BIAS` (a single straight `L=1500` poly strip) and
`R_FB` (three `L=180` units plus dummies, ≈900µm end to end) are both
physically enormous next to any of the MOS devices (the largest of which,
`M_PASS`, is ≈24µm × 101µm) — a direct, unavoidable consequence of
`res_high_po`/`res_xhigh_po`'s low sheet resistivity: reaching the
MΩ-class values `design/README.md`'s own measured-value table reports
(`R_FB` unit ≈1.04MΩ, `R_BIAS` ≈1.22MΩ) at `W=0.42µm` requires hundreds to
thousands of µm of poly length. `klt gen res_array` draws each resistor as
a single straight body (no meander/fold support for a single logical
resistor at this repo's pinned `klt` commit — `res_array`'s own `rows`
param folds multiple *separate* unit elements into parallel rows, which
does not apply to `R_BIAS`'s single `num=1` element). Interleaving these
two long, thin blocks into the same rows as the compact MOS devices would
force every row to the resistor's width for no matching benefit; keeping
them in their own rows (a "resistor farm" beneath the compact analog core)
is a real, deliberate floorplan choice, not an artifact of the packing
algorithm, and mirrors a common real analog-IC convention.

The result is intentionally lopsided (≈1500µm × ≈214µm total, dominated
by `R_BIAS`'s own single-element width) — see the newest
`reports/<record-id>/floorplan.json` for the exact per-row packing this
run produced, and `record.md`'s "Composed cell" section for the resolved
overall bounding box.

## Explicitly out of scope for this issue

- **Inter-block routing.** `klt gen-compose`'s `connectivity[]`/`routing`
  fields support 2-pin point-to-point Manhattan routing at this repo's
  pinned `klt` commit, but wiring this schematic's actual nets (several of
  which fan out to 3+ pins — e.g. `VIN` connects to every PMOS source/body
  in the chain) is a real, separate design task in its own right (device
  orientation, port-side selection, bus planning), not a mechanical
  follow-on to placement. Left unrouted, matching the bandgap-#15
  precedent's own scope line.
- **Extraction/LVS.** Issue #17's job. `layout/README.md`'s "Known klt-deck
  limitations" section already flags two caveats a future LVS reference
  netlist will need to account for: no NMOS substrate-tap extraction (every
  NMOS body ties to a synthesized `vsubs` net) and no voltage-flavor
  distinction on MOS devices (`klt extract`'s `nfet`/`pfet` classes don't
  disambiguate the `_g5v0d10v5` flavor this schematic uses throughout from
  a core-voltage device) — this floorplan draws the well/tap isolation the
  mixed-voltage-adjacent devices need, but a DRC-clean, unextracted result
  does not itself certify that isolation is electrically correct.
- **`C_COMP`'s physical layout** (see "Known gap" above).
