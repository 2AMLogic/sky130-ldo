# `layout/cap-rail-demo/` -- MiM capacitor + supply-rail overlay demonstrator (issue #254)

A **bounded geometry demonstrator**, not the LDO core. It answers one question
the #246 area study left open: can the schematic's capacitors be realised as a
supported sky130 MiM structure laid *over* the core, with the supply-rail metal
conflict resolved, inside the ratified `< 0.1 mm^2` Area row -- or not?

It draws, inside the planned core outline:

- the schematic's four capacitors, read from `design/ldo_3v3in_1v8out.sch`'s own
  xschem netlist (never transcribed), as parallel arrays of **stacked MiM units**;
- the two load-current rails over the pass-device column, re-sized by the
  unchanged #154 rule from the ratified Load and Dropout rows, on the metal
  levels of the assignment below, plus their sense tails and the VIN risers that
  must cross the VOUT rail.

It does **not** draw any MOS device, resistor or signal route, so it says nothing
about their DRC/LVS. Full-core integration and electrical requalification
(loop stability, PSRR, start-up with these parasitics) are separate work
coordinated with #231; the folded resistors are #253.

Records: `reports/<YYYYMMDD-HHMMSS>-<sha>/record.md` (read first),
`summary.json` (machine-readable), `plan.json` (everything the generator drew
and why), plus every klt envelope. `reports/LATEST` names the newest.
Append-only: a re-run mints a new directory.

## Capacitors, checked against the schematic

The #246 study's four-device list is confirmed against the schematic's netlist:
exactly four `capa` instances, no others.

| Instance | Nets (schematic) | Value | Outer plates (met3 + met5) | Inner plate (met4) |
|---|---|---|---|---|
| `C_COMP` | `VOUT` - `EA_CZ` | 150 pF | `VOUT` | `EA_CZ` |
| `C_SS` | `SS` - `0` | 10 pF | `0` | `SS` |
| `C_CL` | `VIN` - `CL_CMP` | 1 pF | `VIN` | `CL_CMP` |
| `C_TS` | `VIN` - `TS_CMP` | 1 pF | `VIN` | `TS_CMP` |

Observation, not changed here: the free-text annotation next to `C_COMP` in the
schematic still says "100p" (its #25 sizing history); the instance's `value=`
attribute -- what the netlist, the simulations and this demonstrator use -- is
150p, matching `design/README.md`.

**Plate assignment rule**: the low-impedance terminal (supply, ground, regulated
output) takes the outer plates; the high-impedance node takes the inner plate,
which is then sandwiched between its own capacitor's other terminal above and
below instead of facing the circuitry under it. The record's coupling table
checks this: no inner node couples to any net other than its own capacitor's
outer one.

## The MiM structure

Each unit is a sky130 `cap_mim_m3_1` (met3 bottom / `capm` top, via3 array to
met4) directly under a `cap_mim_m3_2` (met4 bottom / `capm2` top, via4 array to
met5) of the same footprint; met4 is both the first's top-plate landing and the
second's bottom plate, so the two are in parallel and the stack has ~2x the
single-level density. Unit sides stay inside 2-30 um, the range sky130's own
device generator offers; larger capacitors are arrays of units on one shared
plate set. Unit side is solved so the extraction law the klt deck states (2.00
fF/um^2 + 0.19 fF/um perimeter, per level) reproduces the schematic value.

The outer plates are joined at each block's left edge (met3 -> via2 -> met2 ->
via2 -> separate met3 island -> via3 -> met4 island -> via4 -> met5). The island is
deliberately a separate met3 polygon: the pinned `klt extract` silently drops a
via3 that lands anywhere on a met3 polygon carrying `capm`
([klayout-tools#3020](https://github.com/2AMLogic/klayout-tools/issues/3020)).
The inner plate is tapped at the right edge onto a labelled met2 pad.

`klt gen cap_array` is not used: it draws independent single-level units with
one top via each, no shared plate and no second MiM level
([klayout-tools#3022](https://github.com/2AMLogic/klayout-tools/issues/3022)).

## Proposed metal assignment (core-wide)

| Level | Use |
|---|---|
| li1 | device pads, stubs (unchanged) |
| met1 | signal trunks and risers (unchanged); VOUT rail lower level over the pass device (unchanged); **VOUT sense tail now met1 only**, widened 0.30 -> 0.60 um so its ohm/um is unchanged |
| met2 | gate risers (unchanged); VOUT rail upper level and VIN rail lower level over the pass device (unchanged); **VIN sense tail now met2 only**, widened 0.32 -> 1.175 um (ohm/um no worse); **non-pass VIN risers now cross the VOUT tail on met2** |
| met3 | **only** inside the pass-device rail column: VIN rail upper level and the 50 pass-device VIN risers crossing the VOUT rail (both unchanged). Everywhere else: MiM outer plates and plate-tap islands |
| met4 | MiM inner plates; outer-plate strap islands |
| met5 | MiM outer (top) plates |

So the met3 conflict #246 named is resolved by confining met3 rail use to the
column above the pass device (a MiM keep-out, ~5300 um^2) and moving the two
sense tails off the level they shared with the MiM; the wide rail segments keep
their measured levels and widths, so the drawn IR drop per rail stays at the
ratified 5%-of-dropout share (7.5 mV each). That rail arithmetic is the #154
rule recomputed, not an extraction of the rail -- `klt extract --parasitics`
reports one lumped R per net and still cannot measure a rail's IR drop.

## What the record establishes, and what it does not

Establishes, for the drawn demonstrator: clean under the curated `klt drc` deck
and under the PDK's own `sky130A_mr.drc` (which also checks `capm.2b/2b_a/11` and
the two-adjacent-edge via enclosures the curated deck documents as not modelled);
an LVS match against a reference derived from the schematic netlist, with two
negative controls (a wrong value, a moved terminal) that must and do mismatch;
extracted capacitance per schematic capacitor; plate-to-plate, plate-to-rail and
inner-node coupling as the pinned extractor models it; the footprint arithmetic.

Disclosed LVS conditions: each schematic capacitor is stated in the reference as
one element per MiM class carrying half its value (the two halves are physically
in parallel); `parameter_tolerance` 0.1% (grid rounding leaves < 0.04%); the
top-level pins are name-anchored (`anchor_top_level_pins`), because a cell made
only of capacitors gives the comparer no other structure to pair devices by
([klayout-tools#3023](https://github.com/2AMLogic/klayout-tools/issues/3023)).
The verdict compares the netlist `klt extract` wrote for the record's GDS
(`layout.netlist`); the same compare on the GDS directly (`layout.file`) is kept
as `lvs-gds-shape.json` and does not match, because that path mis-combines the
two stacked capacitor classes
([klayout-tools#3019](https://github.com/2AMLogic/klayout-tools/issues/3019)).

Coupling caveats: the extractor charges plate overlap inside the MiM footprint
on top of the MiM device (a double count, ~3.8% here,
[klayout-tools#3021](https://github.com/2AMLogic/klayout-tools/issues/3021)); the
record separates that from the residual real parasitic. It also models only
adjacent-level overlap, so coupling from a met3 plate to li1/met1/poly under it is
not computed; the record reports the measured device-row met2 area under each
block and the deck coefficient's estimate for it, and leaves the rest to the
full-core PEX.

Does **not** establish: that the LDO core meets the Area row; anything about the
MOS devices, resistors or signal routing; antenna/ERC on the large plates; any
electrical effect of the parasitics. The footprint verdict assumes the measured
MOS-domain width (the comparator devices added in #230 are assumed to fit in the
bank column's free height) and the #246 conservative folded-resistor bank.

## Tool friction

Filed generically at `2AMLogic/klayout-tools` per the friction protocol:

- [#3019](https://github.com/2AMLogic/klayout-tools/issues/3019) -- `klt lvs`
  `layout.file` vs `layout.netlist` disagree after `combine_devices` when two
  MiM classes are stacked in parallel (why the verdict uses `layout.netlist`
  and `lvs-gds-shape.json` is kept as evidence).
- [#3020](https://github.com/2AMLogic/klayout-tools/issues/3020) -- the MiM
  top-plate-via exclusion still cuts a via on the bottom-plate polygon outside
  the top plate (false open; why the outer-plate strap uses a separate island).
- [#3021](https://github.com/2AMLogic/klayout-tools/issues/3021) --
  `--parasitics` double-counts plate overlap inside a recognised MiM.
- [#3022](https://github.com/2AMLogic/klayout-tools/issues/3022) -- `gen
  cap_array` has no parallel-connected or stacked mode (why it is not used).
- [#3023](https://github.com/2AMLogic/klayout-tools/issues/3023) --
  `parameter_tolerance` cannot pair devices in a passive-only cell without
  `anchor_top_level_pins`.

Found on the way, filed in this repo: the measured `ldo_core` layout is not
clean under the PDK's own `sky130A_mr.drc` although the curated deck passes it
(#260).

## Reproduce

```bash
layout/bin/run-cap-rail-demo-flow.sh        # mints reports/<id>/, moves LATEST
python3 -m unittest layout/tests/test_cap_rail_plan.py   # stdlib-only arithmetic tests
```

The klt pin is `layout/cap-requirements.txt` (why a separate pin: see that
file). The flow uses `layout/.venv-cap` if present
(`layout/bin/setup-venv.sh --requirements layout/cap-requirements.txt`),
otherwise runs the same pin through `uvx --from` -- nothing is installed
host-wide. `klayout` and `xschem` must be on `PATH`. No simulation runs here.
