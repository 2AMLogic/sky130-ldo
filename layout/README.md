# layout/ — the klayout-tools (`klt`) DRC/LVS flow

Issue #2's layout-flow deliverable: a headless, repeatable DRC/LVS flow driven
by [`klayout-tools`](https://github.com/2AMLogic/klayout-tools) (`klt`),
**first proven on a trivial known-good cell** (`trivial-cell/`, below) before
being extended to the LDO's own layout (`ldo-core/`, issue #15 — see
"Extending to the LDO core" below): a placed floorplan skeleton for
`design/ldo_3v3in_1v8out.sch`, DRC-clean, with extraction/LVS deferred to
issue #17.

Two rules from the root `CLAUDE.md` shape this directory the same way they
shape `sim/`:

- **Verification is the product.** A DRC/LVS "pass" claim ships with the
  actual reports it came from, plus a negative control proving the flow can
  also report failure.
- **Friction protocol, with force.** Every `klt` gap/awkwardness hit while
  standing this up gets checked against the public
  [`2AMLogic/klayout-tools`](https://github.com/2AMLogic/klayout-tools)
  tracker and filed (or, if already tracked, cross-confirmed) there —
  tool-gap description only, never this repo's design/spec content.

## Quick start (cold machine)

```bash
# 1. install the pinned klt build (~10-60s; see requirements.txt for the pin)
layout/bin/setup-venv.sh

# 2. sanity-check the sky130A PDK resolves (same pin as sim/pdk.json)
layout/.venv/bin/klt pdk find --pdk sky130A

# 3. run the trivial-cell DRC/LVS proof (~a few seconds)
layout/bin/run-trivial-cell-flow.sh
```

The last command writes a fresh, timestamped record under
`trivial-cell/reports/<record-id>/` and updates
`trivial-cell/reports/LATEST` to point at it. **Read the newest
`trivial-cell/reports/<record-id>/record.md` first** — it is the actual
pass/fail evidence this issue delivers, not this README.

## Why `klt`, and why a git-commit pin (not a PyPI version)

`klayout-tools`'s PyPI release lags `main` by several verbs. This flow needs
`gen` (to build the trivial cell), `extract`, and `lvs` — documented on
`main` but not yet in a PyPI release
([2AMLogic/klayout-tools#342](https://github.com/2AMLogic/klayout-tools/issues/342)
tracks cutting one). The project's own README names installing from a git ref
as the sanctioned way to get the latest development verbs; `requirements.txt`
pins an **exact commit**, not floating `main`, for the same reproducibility
discipline `sim/pdk.json` applies to the PDK version. This repo's pin is the
same commit the sibling `sky130-bandgap` repo's own trivial-cell flow already
proved against this same sky130 PDK pin, so this repo's first layout-flow run
starts from a known-good baseline rather than an unverified new pin.

## The flow

```
klt gen mos_array --pdk sky130A         (1) build the trivial known-good cell
        |
        v
klt drc <cell>.gds --deck sky130        (2) DRC against the sky130 deck
        |
        v
klt extract <cell>.gds --deck sky130    (3) layout -> schematic-equivalent netlist
        |
        v
klt lvs (extracted vs. hand-written      (4) LVS: topology compare
         reference netlist)
```

**The trivial cell**: `klt gen mos_array`'s documented defaults (a 2x2 array
of unit NMOS devices with a one-column dummy guard on each side, `nfet`
flavor, no well) are chosen because the project's own docs guarantee every
generator's default `params` pass `klt drc --deck sky130` clean — exactly a
"trivial known-good cell". `res_array` (the resistor-array generator — closer
in spirit to this repo's own poly-resistor-heavy topology, matching the
sibling `sky130-bandgap` finding) is not used for this proof: as of this
repo's `klt` pin, its output does not round-trip through `klt extract`'s
resistor recognition (already tracked upstream, see "Friction protocol"
below) — `mos_array` has no such gap.

**The reference netlist** (`trivial-cell/reference.spice`) is hand-written to
match `mos_array`'s pinned-default topology: 4 independent *real* unit NMOS
devices, each with its own isolated source/drain/gate net, bodies tied to one
shared `vsubs` pin. `klt lvs`/`NetlistComparer` compares topology, not net
*names* (see
[`docs/cli/lvs.md`](https://github.com/2AMLogic/klayout-tools/blob/main/docs/cli/lvs.md)
in the `klayout-tools` repo), so the reference's arbitrary net names do not
need to match the extracted netlist's own arbitrary `$N`-style names.
`mos_array` still physically draws 8 units (4 real + 4 dummy); at this repo's
pinned `klt` commit, sky130's curated deck recognizes the 4 dummy-column
units as dummies (no schematic counterpart by construction) and `klt extract`
drops them from the comparison, so the reference only needs to state the 4
that matter.

**Two negative controls** (`reference.broken-device.spice`,
`reference.broken-topology.spice`) prove the flow actually *fails* on a real
defect, not just that it produces a report — per `klt lvs`'s own documented
guidance, a device-parameter-only corruption and an independent topology
(shorted-net) corruption, since a single corruption class can pass by
accident on a compare that ignores the other axis. Both must (and do) report
`status: "mismatch"`.

## Directory layout

```
layout/
  README.md                  # this file
  requirements.txt           # pinned `klt` install (git commit SHA)
  bin/
    setup-venv.sh             # create/refresh layout/.venv from requirements.txt
    run-trivial-cell-flow.sh  # the repeatable driver: gen -> drc -> extract -> lvs -> report
    render-record.py          # renders + verdict-checks a record's record.md
    run-ldo-layout-flow.sh    # LDO-core driver: xschem netlist -> gen -> gen-compose -> route -> drc -> report
    gen-ldo-blocks.py         # netlist-driven klt gen + placement + gen-compose + the channel router
    render-ldo-record.py      # renders + verdict-checks an ldo-core record's record.md
    run-ldo-lvs-flow.sh       # issue #17: LDO-core LVS driver: xschem netlist -> reference -> extract -> lvs -> report
    gen-ldo-reference-netlist.py  # translates the schematic's xschem netlist into an LVS reference
    render-ldo-lvs-record.py  # renders + verdict-checks an ldo-core LVS record's record.md
  .venv/                      # gitignored -- `klt` install, created by setup-venv.sh
  ldo-core/                   # the real LDO layout (see "Extending to the LDO core")
    floorplan.md               # device-to-block mapping, placement + routing rationale
    reports/
      LATEST                    # newest gen/compose/route/drc record
      LATEST-LVS                 # newest LVS record
      <record-id>/             # xschem_out/, gen.<device>.json/<device>.gds per device,
                                # compose.*.json, floorplan.json, ldo_core.placed.gds,
                                # ldo_core.gds, drc.json, report.md, record.md
      <lvs-record-id>/         # xschem_out/, reference.spice, extract.json,
                                # ldo_core.extract.spice, lvs.request.json, lvs.json,
                                # report.md, record.md (see "LVS" below)
  trivial-cell/
    reference.spice                    # known-good LVS reference netlist
    reference.broken-device.spice      # negative control 1: device.property corruption
    reference.broken-topology.spice    # negative control 2: net.merged corruption
    reports/
      LATEST                    # plain-text pointer to the newest record id
      <record-id>/              # <YYYYMMDD-HHMMSS>-<short-git-sha>, one per run
        gen.json, trivial_mos_array.gds
        drc.json
        extract.json, trivial_mos_array.extract.spice
        lvs.request.json, lvs.json
        lvs.broken-device.request.json, lvs.broken-device.json
        lvs.broken-topology.request.json, lvs.broken-topology.json
        reference*.spice           # snapshot of the reference(s) used for this record
        report.md                  # `klt report --format github-summary` rendering
        record.md                  # human-readable pass/fail summary (read this first)
```

`<record-id>` mirrors `sim/`'s `<YYYYMMDD>-<HHMMSS>-<short-git-sha>` (UTC)
convention (see `sim/README.md`) so the two evidence trails read the same
way. Unlike `sim/`, this flow does not yet enforce a PDK-version pin the way
`sim/bin/corner-run.py` does — `record.md` surfaces the resolved PDK version
as a manual cross-check against `sim/pdk.json` instead.

## Friction protocol: what was found

Standing this flow up on this repo surfaced no *new* `klt` gaps — the same
trivial-cell flow was already proven end to end against this same sky130 PDK
pin by the sibling `sky130-bandgap` repo, whose own friction filing already
covers the two real gaps that flow hit
([`klt gen res_array` doesn't draw the resistor-ID marker its own PDK deck
needs](https://github.com/2AMLogic/klayout-tools/issues/369),
[PyPI lagging `main` by several verbs](https://github.com/2AMLogic/klayout-tools/issues/342)).
Confirming this repo's own run reproduces the identical four-way verdict
(DRC clean, LVS match on the good reference, LVS mismatch on both negative
controls) is itself evidence those two gaps are still the only ones live at
this pin — no re-filing needed.

If a *new* gap (not already covered by the above) turns up in follow-on
layout issues — most likely once real LDO device geometry (poly resistors,
the `pfet_g5v0d10v5`/`pfet_01v8` pass-device candidates once #1 ratifies) is
drawn — file it at `2AMLogic/klayout-tools` per the root `CLAUDE.md`:
tool-gap description only, no spec values or design content from this repo.

### What routing the LDO core hit (issue #33)

Two `klt` gaps shaped how `ldo-core/` is generated. **Both were already
tracked upstream**, so this repo cross-confirmed rather than re-filed
(`klayout-tools` [#1116](https://github.com/2AMLogic/klayout-tools/issues/1116)),
and both have since been resolved on `klayout-tools`' `main` — *after* the
commit `layout/requirements.txt` pins:

- **`gen-compose`'s router was two-pin only**, and rejected any route
  crossing another block's bounding box — so no shared rail or fanout net in
  a real block was routable
  ([#1073](https://github.com/2AMLogic/klayout-tools/issues/1073), closed by
  bundle routing; the broader "no netlist -> placed+routed layout verb" gap
  is [#1116](https://github.com/2AMLogic/klayout-tools/issues/1116), still
  open). `gen-ldo-blocks.py` draws its own channel route instead.
- **`mos_array`'s `fingers>1` drew a series chain** with unstrapped interior
  diffusions and uncontactable gates, which extracts as N series devices
  rather than one folded device
  ([#777](https://github.com/2AMLogic/klayout-tools/issues/777)). Every
  device here is therefore drawn with `fingers=1`, splitting width across
  parallel `cols` units instead.

Bumping the pin to pick those up is a deliberate act (see
`requirements.txt`'s own note) that would need the whole ldo-core flow
re-verified against the new build — worth doing on its own issue, not as a
side effect of a layout change.

## Extending to the LDO core (issues #15/#33)

`ldo-core/` is the real block layout for `design/ldo_3v3in_1v8out.sch`: one
`klt gen` block per active schematic device, placed via `klt gen-compose`'s
`placement.strategy: "explicit"`, wired net-for-net, DRC-clean and
LVS-matched. It is separate from `trivial-cell/` above (that stays tool-flow
proof only).

```bash
layout/bin/setup-venv.sh            # once, or after bumping requirements.txt
layout/bin/run-ldo-layout-flow.sh   # regenerate the layout + DRC record
layout/bin/run-ldo-lvs-flow.sh      # extract + LVS against the schematic
```

Read the newest `ldo-core/reports/<record-id>/record.md` for the DRC
evidence, the newest `<lvs-record-id>/record.md` for the LVS verdict, and
`ldo-core/floorplan.md` for the device-to-block mapping, the placement
rationale, and the routing topology.

**The device set is read from the schematic at run time** — the flow
netlists `design/ldo_3v3in_1v8out.sch` with `xschem` and generates one block
per element it finds, so the layout cannot describe a different circuit than
the schematic. Issue #15's first cut instead carried a hand-transcribed
device table; that table is what went stale (see "LVS" below), which is why
issue #33 replaced it rather than extending it.

### DRC (issue #16)

Issue #16 formalized the DRC-clean claim for this block as its own T1 re-read
(#12) item 3 evidence: re-running the flow fresh and confirming the clean
result reproduces. That still holds, and the coverage caveat it recorded no
longer applies.

Issue #16's record ran against a placed-but-unrouted skeleton, so
`drc.json`'s `coverage.rules_skipped` listed every `met1`/`met2`/`via`/`mcon`
rule (no metal existed to check) and `coverage.layers_checked` covered 4 of
the deck's 8 layers. Now that the block is routed, the newest record checks
**all 8 layers with 0 rules skipped** — the metal/via rules that were
structurally unexercised before are exercised for the first time, and the
result is still `status: clean`.

## LVS against the schematic (issue #17)

```bash
layout/bin/setup-venv.sh          # once, or after bumping requirements.txt
layout/bin/run-ldo-layout-flow.sh # (re)generate the layout/DRC record first
layout/bin/run-ldo-lvs-flow.sh    # xschem netlist -> reference -> extract -> lvs -> report
```

Read the newest `ldo-core/reports/<lvs-record-id>/record.md` (also pointed to
by `ldo-core/reports/LATEST-LVS`) for the actual evidence. **As of issue #33
this reports `status: match`** — every schematic net, device and port paired.

Three request-level hooks make that compare well-posed, each disclosed as its
own `warning` in `lvs.json` so a match reached through them is never
indistinguishable from one reached without (see `run-ldo-lvs-flow.sh`'s
header):

- `options.combine_devices` folds the layout's parallel unit devices (a wide
  device is drawn as N strapped units) back into the single `W_total`-wide
  device the reference states;
- `layout.declared_pins` keeps the block's interface to the schematic's own
  four ports, since every routed net is labelled with its schematic name;
- `reference.device_bulk` supplies the bulk net for the third terminal
  `klt extract` gives a drawn poly resistor and a schematic netlist has no
  node for.

**The first run (issue #17) reported `mismatch`**, against the then-committed
placed-but-unrouted skeleton: a device table that had gone stale against the
schematic, `M_PASS` drawn at `W` rather than `W * mult`, and no inter-block
routing. That record is kept as append-only evidence; issue #33 closed all
three gaps — structurally for the first (netlist-driven generation), not by
re-transcribing the table.

### What a `match` here does and does not certify

- It **does** certify that every drawn MOS/resistor device and every drawn
  net corresponds 1:1 with the schematic's, including both body nets (the
  layout draws a real n-well tie and a real substrate tie).
- It **does not** cover the schematic's four capacitors: `klt gen` has no
  capacitor generator (klayout-tools#1117), so they are drawn on neither
  side. The compensation network is exactly what the loop's stability
  depends on most, so this is a real coverage gap, not a formality.
- It **does not** distinguish device voltage flavor (see "Known klt-deck
  limitations" below), and it says nothing about parasitics (issue #20) or
  about whether the signal-grade routing this flow draws is adequate for the
  load current `VIN`/`VOUT` actually carry.

## Known klt-deck limitations relevant to later, LDO-specific layout issues

Not gaps to file (documented, deliberate scope limits of the curated
`sky130` deck, not bugs) but worth flagging now for whichever later issue
takes on the LDO's own layout, since this issue's own scope stops at the
trivial-cell proof:

- **NMOS substrate-tap extraction needs a drawn tap** (superseded in
  practice, kept for the trivial cell). The curated deck falls back to a
  single global `vsubs` net when no substrate tie is drawn
  (`docs/cli/extract.md` → "Coverage"), which is what the trivial cell hits
  and what its `record.md`'s `device.body_unverified` note records. The deck
  *does* resolve a real tie: sky130's `tap.drawing` split by `nwell`
  containment gives a well tie inside the well and a substrate tie outside
  it. `ldo-core/` draws one of each, so its NMOS bodies extract as the
  schematic's own `0` rail and that warning does not appear on its LVS
  record.
- **No voltage-flavor distinction on MOS devices.** `klt extract`'s `nfet`/
  `pfet` classes are flavor-agnostic — a 5 V-flavor (thick-oxide) device and
  a core-voltage device both extract as the same generic class, with no
  `L`/`W`/oxide-thickness-based disambiguation. This matters directly once
  issue #1 ratifies the pass-device flavor (`pfet_g5v0d10v5` vs. the 1.8 V
  core devices): a future LVS reference netlist will need `hints`/manual
  review to confirm the *intended* flavor correspondence, since `klt lvs`
  cannot check it structurally.
- The deck does recognize `pnp` (vertical bipolar) and poly-resistor
  sheet-rho flavors as distinct device classes (see `klt extract`'s own
  `device_classes` field) — the primitive families this repo's LDO will
  need are already modeled in principle; the `res_array` generator gap
  above is the one concrete blocker on the resistor family specifically,
  and only for the `klt gen`-generated fixture path, not for hand-drawn or
  PCell-instanced resistor geometry that already carries the marker layer.
