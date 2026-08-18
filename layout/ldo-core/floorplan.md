# `layout/ldo-core/` floorplan and routing

The physical layout of the sky130 LDO's core regulation loop: one `klt gen`
block per active device in `design/ldo_3v3in_1v8out.sch`, placed by
`klt gen-compose` and wired net-for-net, DRC-clean and LVS-matched against
the schematic.

- Issue #15 built the first cut: a **placed floorplan skeleton**, no routing,
  no LVS, sized from a device table transcribed into
  `layout/bin/gen-ldo-blocks.py` by hand.
- Issue #17's first `klt lvs` run against that skeleton reported
  `status: mismatch` (0 of 28 reference devices matched), and root-caused it
  to three gaps: a device table that had gone stale against the schematic, a
  pass device drawn at `W` instead of `W * mult`, and no inter-block routing
  at all.
- Issue #33 closed all three, structurally: **the layout is now generated
  from the schematic's own netlist** rather than from a table, every device's
  drawn width is its schematic `W_total`, and the block is routed.

Read the newest `reports/<record-id>/record.md` for the DRC evidence and the
newest `reports/<lvs-record-id>/record.md` (pointed to by `reports/LATEST-LVS`)
for the LVS verdict; `reports/<record-id>/floorplan.json` carries the exact
per-device sizing, placement, and routed-net table each run produced.

## Where the device set comes from

`layout/bin/run-ldo-layout-flow.sh` netlists `design/ldo_3v3in_1v8out.sch`
headlessly with `xschem` and hands that netlist to
`layout/bin/gen-ldo-blocks.py`, which reads every MOS and resistor element
out of it. There is no device table in this repository to keep in sync: the
layout cannot describe a different device set than the schematic, because it
reads the same file the LVS reference netlist is translated from
(`layout/bin/gen-ldo-reference-netlist.py`).

That is the direct, structural fix for the failure mode that produced #17's
mismatch. The old hand-maintained table did not merely fall behind by the 11
devices issue #22 added -- by the time #33 was picked up it was also missing
the rail-to-rail output stage and the whole thermal-shutdown comparator, and
any hand-edited replacement would have started decaying again on the next
schematic commit.

| Schematic element | `klt gen` block | Params (schematic -> generator) |
|---|---|---|
| any `nfet_g5v0d10v5` instance | `mos_array`, `flavor: "nfet"` | `l_um`=`L`, `fingers=1`, `rows=1`, `cols`=units, `w_um`=`W * mult / units`, `dummy=0`, `gate_contact=true` |
| any `pfet_g5v0d10v5` instance | `mos_array`, `flavor: "pfet"` | same mapping; the `pfet` flavor draws the well sky130's PMOS devices need |
| any `res_high_po` / `res_xhigh_po` instance | `res_array`, `flavor: "high"`/`"xhigh"` | `length_um`=`L`, `width_um`=`W`, `num=1`, `dummy=0` -- one block per schematic instance, so the layout is 1:1 with the reference netlist's own per-instance resistor elements |
| `C_COMP`, `C_CL`, `C_SS`, `C_TS` | *(none -- known gap, see below)* | not drawn |

### Width: `W_total = W * mult`, and why `fingers` is not used

`design/README.md`'s "Pass-device width correction" note is load-bearing:
the xschem symbol's `W` is a per-`mult`-group width, so a device's real total
width is `W * mult`. The pass device is `W=100 mult=25` -- 2500um, not 100um.

Two generator parameters could nominally reach that total, and only one of
them survives extraction:

- **`fingers=N` does not work.** `klt gen`'s multi-finger unit device leaves
  the interior diffusions unstrapped and each finger's gate unconnected, so
  `klt extract` reads an N-finger device as N devices in *series*, each with
  a floating gate. That is neither the schematic's topology nor something
  `combine_devices` can fold. (The pre-#33 layout drew every device with the
  schematic's `nf` as `fingers`, which is part of why not one device matched.)
- **`cols=N` parallel units does.** A device wider than 100um is drawn as
  `ceil(W_total / 100)` equal unit devices whose S/D/G terminals the router
  straps together, which is exactly what `mult` means physically. `klt lvs`'s
  `options.combine_devices` folds the strapped units back into one device of
  the summed width, so the reference's single `W=2500U` element matches. Only
  the pass device is wide enough to split today (25 x 100um).

Drawing the pass device as one 2500um-wide single-finger device would also
extract with the right width, but it would make the block 2500um tall for no
benefit; a parallel-unit array is both the physically sensible construction
and the smaller one.

## Placement

One bottom-aligned row, blocks packed left to right with a 2um gap (6um
between super-groups), ordered:

1. **resistors** -- `R_BIAS`, the feedback divider (`R_FB_A/B/C`), `R_CZ`;
2. **every NMOS block**, preceded by a reserved slot for the substrate tie;
3. **every PMOS block**, preceded by a reserved slot for the n-well tie.

Within each of those spans, blocks are grouped by function (bias/enable,
error amplifier, current limit, soft start, thermal shutdown, output pass),
mirroring `design/README.md`'s own grouping of the schematic.

**The flavor split is load-bearing, not cosmetic.** The PMOS bodies are tied
through a single n-well drawn across the whole PMOS span, and `klt extract`
decides a device's flavor by n-well containment (`pfet_active = active &
nwell`): a well drawn over an interleaved NMOS block would re-type that
device. Keeping every PMOS contiguous is what makes one shared well -- and
therefore one drawn `VIN` body tie instead of 25 of them -- possible at all.
The cost is that a function group with both flavors occupies two x ranges;
`record.md`'s group table shows both.

The resistors keep their own span at the left for the reason issue #15
already documented: `R_BIAS` (a single straight `L=1500` poly strip) is
physically enormous next to any MOS device, a direct consequence of
`res_high_po`'s sheet resistivity, and `klt gen res_array` draws each unit
resistor as one straight body (no meander/fold for a single logical resistor
at this repo's pinned `klt` commit). The result is a deliberately lopsided
block, ~2384um x ~101um for the device row, dominated by that one resistor.

## Routing

`klt gen-compose`'s own `connectivity[]` router is not used. It draws
**two-pin** point-to-point nets only, and rejects any route whose backbone
crosses another block's bounding box; this schematic's nets fan out to
between 2 and 50 terminals each (`VIN` alone reaches every PMOS source and
the well tie), across a 2384um-wide row. `layout/bin/gen-ldo-blocks.py`
therefore draws the wiring itself, as a single-channel two-layer channel
route. That gap was already tracked upstream and is cross-confirmed rather
than re-filed -- see `layout/README.md`'s "What routing the LDO core hit"
section, which also records that `klayout-tools` has since added bundle
routing on a commit *newer* than this repo's pin.

The topology is deliberately uniform, so that no two nets can share drawn
metal by construction rather than by inspection:

- **One met1 trunk per net**, in a routing channel below the device row, on a
  0.8um track pitch. Each trunk owns a unique y.
- **Source/drain terminals drop straight down** from their own li1 pad (the
  pads already run the full device height) onto their net's trunk, through an
  mcon. Each drop owns a unique x -- ports within a block are >=0.46um apart
  and blocks are gapped -- so parallel drops never touch each other, and a
  drop crossing an unrelated trunk is a li1-over-met1 crossing, not a short.
- **Gate terminals rise** out of the top of their block on li1, transfer to
  met2 (mcon -> met1 landing pad -> via1), run back down *over their own
  block* on met2, and land on their trunk through a second via1. The second
  routing level exists precisely so a gate can reach the channel without
  crossing the met1 trunks stacked in it.
- **Every trunk is labelled** on `met1.pin` with its schematic net name, so
  the extracted netlist reads in schematic terms and `klt lvs` has no net
  name/identity conflict to report. `klt extract --pins VOUT,VREF,EN,VIN`
  keeps the block's interface to the schematic's own four ports; every other
  labelled net stays an internal node.

All drawn dimensions sit at or above the sky130 deck's own minimums (li1
0.19um wide vs. a 0.17um rule; met1/met2 trunks 0.30um wide vs. 0.14um;
mcon/via1 at the deck's own contact size with >=0.055um enclosure), chosen
with enough margin that the first routed run came back DRC-clean rather than
needing a violation-driven iteration loop.

### Body ties

Both body nets are drawn and extracted, not left on the deck's synthesized
fallback:

- an **n-well tie** (`tap.drawing` inside the shared n-well, licon + li1)
  drops onto the `VIN` trunk, so every PMOS body terminal extracts as `VIN`;
- a **substrate tie** (`tap.drawing` outside every well) drops onto the `0`
  trunk, so every NMOS body -- and every poly resistor's `bulk_to_substrate`
  bulk terminal -- extracts as the schematic's own `0` rail rather than the
  deck's `vsubs` global.

This is why the LVS record no longer carries the `device.body_unverified`
warning that `layout/README.md`'s "no NMOS substrate-tap extraction" note
predicted: the deck *does* resolve a real drawn tie, and this layout draws
one.

## Known gap: no `klt gen` capacitor generator

At this repo's pinned `klt` commit, `klt gen --list` still has no
capacitor/MiM family member alongside `mos_array`/`res_array`/`diff_pair`/
`bjt_array`, even though `klt extract` recognises MiM `CapacitorDevice`
classes. The schematic's four capacitors (`C_COMP`, `C_CL`, `C_SS`, `C_TS`)
are therefore not drawn. Filed generically per `CLAUDE.md`'s friction
protocol as
[`2AMLogic/klayout-tools#1117`](https://github.com/2AMLogic/klayout-tools/issues/1117).

`layout/bin/gen-ldo-reference-netlist.py` drops the same four elements from
the LVS reference, so the compare stays symmetric: their absence is a
disclosed coverage gap on both sides, not a silent one. It is a real gap
nonetheless -- an LVS match on this layout says nothing about the
compensation capacitor, which is the component the loop's stability depends
on most.

## Still out of scope here

- **Parasitic extraction / post-layout simulation** (`klt pex`) -- issue #20.
  A DRC-clean, LVS-matched layout certifies topology and geometry rules; it
  says nothing about the li1 trunk resistance this deliberately simple
  channel route puts in series with, e.g., the pass device's source.
- **Real power routing.** Every net here is drawn at the same signal-grade
  width, including `VIN`/`VOUT`, which in the real block carry the full load
  current. Sizing those as power straps is a separate design task with its
  own electromigration/IR-drop acceptance criteria.
- **Matching-aware placement.** Blocks are packed in schematic order within
  their function group; the differential pairs and current mirrors are not
  common-centroid placed or interdigitated, and `klt gen`'s own
  `matched_group_id` hints are not yet used to check symmetry.
