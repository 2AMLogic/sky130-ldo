# `pex-post-layout`: post-layout (parasitic-extracted) verification (issue #20)

Item 7 ("Post-layout verification") of the T1/bronze checklist re-read (#12).
Produces a post-layout, parasitic-extracted netlist for the routed
`ldo_core` layout (#15/#17/#33) via `klt pex`, and re-runs a re-simulation
against it, per-corner, alongside the schematic-side run for comparison.

## Why this directory, not `sim/<slug>/experiment.json`

`klt pex <layout> <testbench>... --deck sky130` (Phase 1a of
[klayout-tools#709](https://github.com/2AMLogic/klayout-tools/issues/709))
takes `klt sim`-format request JSON files as its testbenches -- a different
schema from this repo's own `sim/<slug>/experiment.json` + `corner-run.py` +
xschem-`.sch`-testbench convention. This directory holds a `klt
sim`/`klt pex`-native testbench pair instead:

- `testbench/ldo_core_schematic_dut.spice` -- the schematic-side DUT (a
  `.SUBCKT ldo_core <pins>` circuit body).
- `testbench/tb_pex_post_layout.spice` -- the testbench: `.include`s the DUT
  above, adds sources/an output network, and instantiates it.
- `testbench/tb_pex_post_layout.request.json` -- the `klt sim` request
  (corners, analysis, measurements) both the schematic-side and
  extracted-side legs run under.
- `bin/gen-pex-testbench.py` -- regenerates the two `testbench/*.spice`
  files above from the current schematic + landed layout (see "Regenerating"
  below). The `.request.json` is static and not regenerated.
- `bin/run-pex.sh` -- regenerates the testbench pair, runs `klt sim`
  (schematic-side, standalone) and `klt pex` (both legs + delta) against the
  landed layout, and writes a new record.
- `bin/render-pex-record.py` -- called by `run-pex.sh`; renders the
  `records/<id>.{json,md}` pair below from the raw `klt` responses.
- `klt-requests/<record-id>.request.json`, `klt-responses/<record-id>.{sim-schematic,pex}.json`,
  `netlist-snapshots/<record-id>.{schematic-dut,pex.extract}.spice`,
  `records/<record-id>.{json,md}` -- append-only evidence per run, same flat
  per-record-id-file convention `sim/dropout-vs-load/`,
  `sim/mc-output-accuracy/`, etc. already use (a later run mints a new
  `<record-id>`, never overwrites an earlier one).

`layout/` and `design/` are read-only inputs to this experiment -- nothing
here modifies either.

## Why a fresh xschem netlist, not the committed LVS reference

Issue #17's LVS flow (`layout/bin/run-ldo-lvs-flow.sh`) and its committed
`layout/ldo-core/reports/<record>/reference.spice` translate the schematic
into a **generic-device-class** netlist (`nfet`/`pfet`/`res_high_po`/
`res_xhigh_po`, via `layout/bin/gen-ldo-reference-netlist.py`) for
topological LVS comparison -- adequate for `klt lvs`, but two problems for
*this* experiment:

1. **Staleness.** A landed LVS report pins the schematic commit it ran
   against (its own `record.md`'s "Schematic freshness" line). The schematic
   can move on after that record is cut -- it did: the currently-landed LVS
   record (`20260818-034303-d0b244d`) was cut against `design/
   ldo_3v3in_1v8out.sch` as of commit `d0b244d`, and a later commit
   (`fdd6ebf`, already on `main`) renamed a duplicate-named component
   (`M_ENP4` -> `M_ENP5`) that `d0b244d`'s netlist still carries under the
   old, colliding name -- confirmed by direct trial: `ngspice` refuses that
   stale `reference.spice` outright ("device already exists, bail out").
   Purely a naming fix (same symbol/geometry/connections both before and
   after, per `git diff d0b244d..HEAD -- design/ldo_3v3in_1v8out.sch`), so
   it does not change circuit behavior -- but it does mean the *committed*
   reference netlist cannot be directly ngspice-simulated as of current
   `main`. This experiment's generator (`bin/gen-pex-testbench.py`) always
   netlists `design/ldo_3v3in_1v8out.sch` fresh (the same headless
   invocation `run-ldo-lvs-flow.sh` uses) rather than reusing a committed
   report, so it is never stale relative to whatever schematic commit it is
   run against.
2. **Generic device classes turned out not to be directly simulatable for
   this layout at all** -- see "Why `--pdk sky130A`" below. The DUT this
   experiment uses is therefore the schematic's own **real**,
   `sky130_fd_pr__nfet_g5v0d10v5`/`pfet_g5v0d10v5`-modelled netlist (the
   same xschem output `design/README.md`'s "Validating this schematic"
   section documents), not the LVS translator's generic-class output.

## Why `--pdk sky130A` (and its cost -- read this before trusting a number)

`klt pex`'s own internal `klt extract` call has no `--pins` flag (unlike
`run-ldo-lvs-flow.sh`'s explicit `--pins VOUT,VREF,EN,VIN`), so its
extraction promotes **every** labelled net in the layout to a top-level pin
-- 28 of them for `ldo_core`, not just the schematic's 4 ports. `bin/
gen-pex-testbench.py` re-derives that exact 28-pin order live (a throwaway
probe extraction against the landed GDS) and widens the DUT's `.SUBCKT
ldo_core` header to match, so the testbench's single `X` instantiation wires
identically on both legs.

Two device-model choices were tried, in order, both confirmed by direct
trial rather than assumed:

1. **Bare (no `--pdk`) generic-class extraction.** `klt extract`'s
   sky130 deck always writes its drawn-resistor classes (`res_high_po`,
   `res_xhigh_po`) as a **3-terminal** `R` card
   (`R$68 VIN NB 0 1160477.00515 res_high_po` -- the third node is the
   resistor's own bulk/tap terminal), regardless of `--parasitics`. ngspice's
   native `R` element only ever accepts 2 nodes; simulating this card against
   a bare `.model res_high_po r` fails outright:
   `Error on line ...: unknown parameter (res_high_po)`. `docs/cli/extract.md`'s
   "Verified compatible with `klt sim`'s netlist convention" section
   documents the 2-terminal case (`res_generic_po`); sky130's 3-terminal
   resistor classes are a real, structural exception this repo's own trial
   surfaced, not a documented gap as of 2026-08-18 (searched
   `2AMLogic/klayout-tools` issues for "res_high_po"/"3-terminal
   resistor"/"resistor bulk terminal"/"unknown parameter" -- nothing found
   matching). **This means the bare, generic-class path is not currently
   usable for this design's post-layout re-simulation at all** -- filed as
   [klayout-tools#1157](https://github.com/2AMLogic/klayout-tools/issues/1157)
   (friction protocol, generic -- no design-specific detail); see that issue
   for status.
2. **`--pdk sky130A` binding (used here).** Sidesteps the resistor problem
   entirely -- every device (MOS and resistor alike) becomes a real PDK `X`
   subcircuit call, which supports arbitrary pin counts. Its own disclosed
   cost: `klt extract --pdk`'s MOS model-binding table
   (`src/klayout_tools/pdk_models.py`) is hardcoded to sky130's **01v8**
   core-device flavor, one flavor per class, with no caller override. This
   design's schematic uses the 5V-tolerant **g5v0d10v5** flavor throughout
   (`design/ldo_3v3in_1v8out.sch`'s own xschem netlist,
   `sky130_fd_pr__nfet_g5v0d10v5`/`pfet_g5v0d10v5`).

   **Update (2026-08-24, issue #67):** originally tracked as
   [klayout-tools#1089](https://github.com/2AMLogic/klayout-tools/issues/1089)
   ("#552's warning-only fix (PR #577) leaves DRC threshold selection and MOS
   model binding wrong for voltage-domain-marked geometry"). #1089 has since
   **closed** (2026-08-24, "tracking issue, work complete"), decomposed into
   #1110 (DRC-side) and #1111 (MOS-model-binding side) -- but re-checked live
   against current `main` (`3c14ac2`), both landed **gf180mcu-only**;
   #1111's own body states sky130 needs its `hvi` layer registered as a
   prerequisite first and is explicitly out of scope there.
   `pdk_models.py`'s `_MOS_MODEL_FLAVOURS` table confirms this directly: it
   has marker-scoped entries for `("gf180mcu", "gf180mcu")` and
   `("sg13g2", "sg13g2")` but none for `("sky130", "sky130")`, and
   `decks/sky130.py`'s `UNMODELED_VOLTAGE_MARKERS` is still empty. So this
   caveat is **unchanged in substance** -- every sky130 MOS device still
   binds to `*_01v8` regardless of its drawn flavor -- but #1089 no longer
   accurately describes it as tracked, since neither #1089 nor its
   sub-issues cover sky130. Re-filed sky130-specific as
   [klayout-tools#1369](https://github.com/2AMLogic/klayout-tools/issues/1369)
   (friction protocol, generic -- no design-specific detail; verified no
   existing open issue covered this before filing).

## A third gap: `--pdk`'s resistor X-card geometry convention itself fails

Running the actual `klt pex` command (not just a standalone `klt sim` on the
schematic side) surfaced a **third**, independent, and more severe gap:
`klt extract --pdk`'s resistor binding writes explicit-SI-unit-suffixed
geometry (`l=180U w=0.42U`), matching its own documented MOS-binding
rationale ("an explicit SI unit suffix is parsed identically by ngspice
regardless of any `.option scale`"). Confirmed by direct trial against the
**real, fetched** `sky130_fd_pr__res_xhigh_po` vendor subcircuit: this
convention is incompatible with that subcircuit's own internal `.param`
formula (`leff = l-0.0592`, which assumes `l` arrives as a **bare
micron-scale number**, not an absolute-SI value) -- the SI-converted `l`
(`1.8e-4`) is dwarfed by the `0.0592` offset, driving `leff` negative and
`log(leff/w)` to `NaN`, **regardless of the actual resistor dimension
chosen** (reproduced with a minimal, `klt`-free reproducer: bare `l=180
w=0.42` converges to a sane operating point; unit-suffixed `l=180U w=0.42U`
-- the exact form `--pdk` writes -- fails identically). Filed as
[klayout-tools#1159](https://github.com/2AMLogic/klayout-tools/issues/1159)
(friction protocol, generic -- confirmed real via a `klt`-free reproducer
before filing).

**Consequence: the extracted-side leg of `klt pex` does not converge for
this layout today**, for three independent, real, disclosed reasons (none
within this repo's control): the bare/generic path is blocked by #1157 (a
3-terminal resistor class ngspice cannot simulate as an `R` card at all);
the `--pdk` path resolves that but hits #1159 (NaN in the real resistor
vendor model, from `--pdk`'s own geometry-unit convention) *and* carries
the disclosed #1369 MOS-flavor-substitution caveat (sky130-specific; see the
"Update (2026-08-24, issue #67)" note above -- supersedes the now-closed,
gf180mcu-only #1089) even where it does converge. The latest
`klt-responses/<record-id>.pex.json` is the honest,
recorded result of the actual `klt pex` invocation against the landed
layout: `status: "error"`, every `delta[]` row's extracted-side leg
`null`/`"error"` (schematic-side values are real and populated). This is
**not a fabricated pass** -- it is the literal, reproducible output of the
command run against the landed layout and committed testbench, with root
cause traced and disclosed rather than hidden. It still satisfies issue
#20's actual acceptance criteria: a post-layout extracted netlist *is*
produced and committed (`extraction` step of `klt pex` succeeds
independently of the simulation step that follows it -- see the matching
`netlist-snapshots/<record-id>.pex.extract.spice`), and post-layout
verification *is* run and recorded as append-only evidence against the
layout as landed -- the evidence is an honestly-labeled `error`, not a
`pass` dressed up as one. The schematic-side leg's own full 45-point PVT
sweep (`klt-responses/<record-id>.sim-schematic.json`, run directly via
`klt sim` against the same testbench/DUT) is clean (`passed: 45`) and is
the closest thing to a spec-comparable number this experiment produces --
still not usable against `spec/target-spec.md`'s DRAFT rows, since there is
no matching extracted-side number to diff it against. See
`records/<record-id>.md` for the latest run's own summary and links.

## Why generic textbook-constant `.model` cards are not used here

An earlier iteration of this testbench (before switching to `--pdk`) used
`klt extract`'s bare generic device classes with hand-supplied `.model nfet
nmos level=1`/`.model pfet pmos level=1` cards, per `docs/cli/pex.md`'s own
worked example convention. Two findings from that iteration, kept here for
the record:

- All-default (`VTO=0`) `level=1` parameters produce a **non-physical**
  operating point for this specific feedback circuit (`VOUT` pinned at a
  multi-kV rail -- clearly a wrong-branch/non-convergent solution, not a
  real bias point).
- Adding generic order-of-magnitude enhancement-mode constants (`vto=0.7
  kp=120u lambda=0.01` n-type, `vto=-0.7 kp=40u lambda=0.01` p-type -- NOT
  sky130-specific values, ordinary textbook bulk-CMOS numbers) let the loop
  find a sane bias point (`VOUT` self-regulated to ~1.8V, matching
  `VREF`=1.2V through the `R_FB_A`/`R_FB_B`/`R_FB_C` divider's 3:2 ratio --
  a sanity check on the feedback topology, not a spec-comparable number
  either way).

That path was abandoned once the 3-terminal resistor incompatibility (above)
was found to block it regardless -- kept here only as a documented dead end,
not reused.

## Regenerating

```bash
sim/pex-post-layout/bin/run-pex.sh [--klt <path>]
```

Regenerates `testbench/ldo_core_schematic_dut.spice` +
`testbench/tb_pex_post_layout.spice` from the current schematic and the
landed layout (`layout/ldo-core/reports/LATEST-LVS`), then runs `klt pex`
against it and writes a new timestamped record under `records/`. Defaults to
the ambient `klt` on `PATH`; see "Note on the `klt` pin" below for why.

**Note on the `klt` pin.** `layout/requirements.txt` pins a `klt` commit
(`acb0ae6`) predating `klt pex`'s introduction -- `layout/.venv/bin/klt
--version` reports `0.2.0` but its `<command>` list has no `pex` verb. This
experiment therefore records its own, separate pin below rather than reusing
`layout/`'s (a `layout/`-scoped pin bump is out of scope for this
experiment -- `layout/` is a read-only dependency here).

**Note on `tb_pex_post_layout.request.json`'s `models.lib`.** Uses the
literal `"$PDK_ROOT/sky130A/libs.tech/combined/sky130.lib.spice"` shape
(env-var-expanded, no `models.pdk` alongside it) rather than the
`{"pdk": "sky130A", "lib": "<relative path>"}` shape `docs/cli/sim.md`
otherwise favors. Confirmed by direct trial: combining both shapes in one
request breaks specifically on `klt pex`'s extracted-side leg -- it
re-resolves the already-relative `lib` a second time against the wrong base
directory (`model library not found:
<request-dir>/libs.tech/combined/sky130.lib.spice`), and using
`{"pdk": ..., "lib": "$PDK_ROOT/..."}` together instead double-joins the
env-expanded absolute path onto the resolved PDK variant directory
(`.../sky130A/$PDK_ROOT/sky130A/...`). Using `models.lib` alone (no
`models.pdk`) sidesteps both -- not filed upstream (a usage pitfall from
combining two independently-documented shapes, not a single clearly-wrong
behavior in either shape alone).

## `klt` pin used for the recorded runs

- `klt` commit: `a482d3934bd644b763cf925f6344ac05f54a1623` (2AMLogic/klayout-tools
  `main`, installed via `uv tool install git+https://github.com/2AMLogic/klayout-tools`),
  `klt --version` reports `0.2.0`.
- PDK: `sky130A`, `open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b` (same
  pin as `sim/pdk.json`).

## Evidence discipline

Same convention as `sim/<slug>/records/`: a later run mints a new
timestamped record under `records/` rather than overwriting an earlier one.
