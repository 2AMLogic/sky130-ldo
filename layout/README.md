# layout/ — the klayout-tools (`klt`) DRC/LVS flow

Issue #2's layout-flow deliverable: a headless, repeatable DRC/LVS flow driven
by [`klayout-tools`](https://github.com/2AMLogic/klayout-tools) (`klt`),
**proven on a trivial known-good cell only** — this is scoped to prove the
`klt` layout/DRC/LVS driver works on this repo, not to draw the LDO. The
LDO's own layout is future work once `spec/target-spec.md` is ratified
(issue #1) and the design is drawn.

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
  .venv/                      # gitignored -- `klt` install, created by setup-venv.sh
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

## Known klt-deck limitations relevant to later, LDO-specific layout issues

Not gaps to file (documented, deliberate scope limits of the curated
`sky130` deck, not bugs) but worth flagging now for whichever later issue
takes on the LDO's own layout, since this issue's own scope stops at the
trivial-cell proof:

- **No NMOS substrate-tap extraction.** The curated deck ties every NMOS
  body to a single global `vsubs` net rather than a real drawn tap
  (`docs/cli/extract.md` → "Coverage"). Harmless for this issue's trivial
  cell (see `record.md`'s `device.body_unverified` note) but means a future
  LVS reference netlist for the real LDO should also tie NMOS bodies to a
  single net, not model per-tap connectivity the extractor can't see.
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
