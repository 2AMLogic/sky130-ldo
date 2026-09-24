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

   **Update (2026-09-23, issue #122): #1369 is fixed upstream.** PR #1381
   (already contained in release `v0.5.0`) added the marker-scoped
   `("sky130", "sky130")["hvi"]` -> `sky130_fd_pr__{n,p}fet_g5v0d10v5`
   entry to `_MOS_MODEL_FLAVOURS`, with the `hvi` 75/20 pair
   cross-checked against three independent PDK sources, plus a follow-up
   (`a261706c`, #1912) fixing the `klt gen` side. The binding is
   **marker-scoped**: a device binds the g5v0d10v5 model only when its
   gate region overlaps an `hvi` (75/20) polygon. At that point the landed
   `ldo_core` GDS contained **no** `hvi` polygons at all (verified by a
   direct layer scan of `layout/ldo-core/reports/<LVS-record>/ldo_core.gds`:
   15 layer/datatype pairs, 75/20 absent), so all 67 MOS devices still bound
   `*_01v8` -- no longer an upstream gap but a repo-local layout omission,
   tracked in #142.

   **Update (2026-09-24, issue #142): the repo-local half is closed too.**
   `layout/bin/gen-ldo-blocks.py` now passes `voltage_flavor="hvi"` on every
   MOS block, keyed on the schematic's own model token
   (`MOS_VOLTAGE_FLAVORS`, the same schematic-derived discipline its
   `MOS_MODELS` map already followed) rather than a hand-transcribed
   per-device list, and hard-fails if `klt gen`'s
   `drc_hints.voltage_flavor_mark_present` comes back false instead of
   silently drawing nothing. The marker is now really in the stream and the
   bind really follows it -- both measured on the 2026-09-24 record, not
   assumed; see the record note at the end of this file for the numbers.

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

**Update (2026-09-23, issue #122): fixed upstream.** #1159 (and #1157
with it) closed COMPLETE via `2dc66ece` (PR #2336: "bare-mode 3-terminal
resistor cards become X subckt calls (#1157); lock sky130 resistor bare-um
geometry + vendor proof (#1159)"). The 2026-09-23 run below confirms both
fixes live at the pinned commit: the extracted netlist's resistor X-cards
carry bare-micron geometry (`l=180 w=0.42`) and the real
`sky130_fd_pr__res_{high,xhigh}_po` vendor models converge.

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

**Update (2026-09-23, issue #122): the extracted-side leg now runs --**
**108/135 delta rows pass; the 27 surviving errors share one repo-local**
**root cause.** With the `klt` pin moved to the `040f3406b485` main-branch
commit (see the pin section below -- no release contained the #1157/#1159
fixes at recording time), the extracted leg converges and produces real
extracted-vs-schematic numbers: record
[`20260923-183915-d9900b5`](records/20260923-183915-d9900b5.md) reports
`passed: 108, failed: 0, errored: 27` (superseding
`20260825-125102-3b4e121` above), the 27 being 9 `ss`-corner delta rows x
3 measurements. Their root cause is the flavour substitution described in
the #1369 update above: with no `hvi` markers in the layout, all 67 MOS
devices bind `*_01v8` at g5v0d10v5 geometries, and at `ss` corners the
substituted model's binning fails ngspice's BSIM4 parameter check
outright (`Fatal: Pclm = -0.00876203 is not positive`, `dc
simulation(s) aborted` -- read in the run's own
`sim/build/pex-post-layout/<record-id>/pex/.../extracted/ss_*/ngspice.log`).
That is a **repo-local** layout task now (#142 draws the marker), not an
upstream gap; the residual upstream friction -- `klt extract --pdk` stays
silent when a deck declares flavour markers but the layout contains none
-- is filed as
[klayout-tools#2417](https://github.com/2AMLogic/klayout-tools/issues/2417)
(friction protocol, generic). Until #142 lands and this experiment is
re-run, **T1 item 7 remains unmet** (item 7 accepts a `klt pex` report
and nothing else; 27 errored corners are 27 errored corners).

**Update (2026-09-24, issue #142): every corner now runs -- and what that
exposes is a *different* problem, one this repo owns.** With the `hvi`
marker drawn (see the #142 update above), record
[`20260924-181248-50554fe`](records/20260924-181248-50554fe.md) reports
`status: pass, passed: 135, failed: 0, errored: 0`, exit code `0`
(superseding `20260923-183915-d9900b5`). The 27 `ss`-corner aborts are gone:
the extracted netlist binds `sky130_fd_pr__{n,p}fet_g5v0d10v5` on all 92 MOS
devices (18 n + 74 p, counted directly out of
`netlist-snapshots/20260924-181248-50554fe.pex.extract.spice`), so ngspice
no longer hits the `Pclm` BSIM4 parameter check that the substituted
`*_01v8` model's binning failed. Every `ss` extracted-corner log under
`sim/build/pex-post-layout/20260924-181248-50554fe/pex/.../extracted/ss_*/`
is clean.

**Do not read that `pass` as agreement between the two legs.** This
experiment's request (`testbench/tb_pex_post_layout.request.json`) declares
**no limits** on any of its three measurements, so `klt pex` grades every
`delta[]` row against nothing and `pass` means only "both legs produced a
number". The record's own `delta[]`-spread table is the number that matters,
and it is large:

| Measurement | median \|delta\| % | max \|delta\| % |
| --- | --- | --- |
| `vout_light_load_v` (1 mA) | 1.9 | 161 |
| `vout_full_load_v` (50 mA) | 385 | 3543 |
| `vin_minus_vout_full_load_v` (50 mA) | 633 | 4775 |

At light load the extracted leg tracks the schematic within ~2% at most
corners -- a plausible parasitic delta. At **full load it is non-physical**:
the extracted `VOUT` lands at -5.7 V (`tt/2.970V/-40C`) to -61.9 V
(`ss/3.300V/-40C`).

The traced cause is this flow's routing, not the flavour fix and not the
extraction: `gen-ldo-blocks.py` draws every net as a `TRUNK_W_UM = 0.30`um
met1 trunk -- signal-grade, and the same "says nothing about whether the
signal-grade routing this flow draws is adequate for the load current
`VIN`/`VOUT` actually carry" caveat `layout/README.md` has carried since
issue #17. The extracted `VOUT` net's lumped star resistance runs 102 Ω to
**64.3 kΩ** per terminal across its 51 terminals (`VIN`: 259 Ω to 29.4 kΩ
across 145), so at 50 mA the IR drop swamps the loop and the solver leaves
the regulating branch entirely. **This is a real layout defect the
flavour-substitution error was previously masking** -- it is tracked
as #154 and is *not* in #142's scope, which was to make the extracted
netlist describe the design's own transistors.

**T1 item 7 status.** A `klt pex` report now exists that ran the design's
real devices at all 45 corners, which is what item 7 asks for -- but the
full-load rows it contains are non-physical, so nothing in it is comparable
to `spec/target-spec.md` at full load yet. Treat item 7 as *substantiable in
kind but not yet in substance*: the blocker is the power routing above (#154),
and a fresh record after that is fixed is what should be read against the
spec. The light-load rows are the only ones worth quoting today, and only with
the "no declared limits" caveat attached. `signoff/block-manifest.json`
therefore still cites the older, erroring `klt pex` run for item 7 rather than
this record -- deliberately; see `signoff/README.md`, "Item 7 has a passing
record that this manifest declines to cite".

**`body_bias` (read per issue #122's scope).** The same report's
`body_bias` block reads `status: "biased", unbiased_device_count: 0,
unbiased_nets: []` -- no device body sits on an anonymous deck-synthesized
net, so the physically-wrong-resimulation hazard of
[klayout-tools#1983](https://github.com/2AMLogic/klayout-tools/issues/1983)
does not bite for this layout as landed. Any claim made from this
experiment must state this alongside the numbers (`klt signoff` surfaces
the block but does not grade on it).

**On the standalone schematic-side leg's timeouts.** The same record's
standalone `klt sim` leg reports 36/45 passed with 9 `timeout` errors
(`ngspice did not complete within 120s, killed` -- the testbench's own
`options.timeout_s: 120` knob) at cold/low-supply corners, while the pex
run's own schematic leg *completed* those same corners (every delta row
carries a real schematic value). The timeouts are host-load-induced under
the 120 s per-corner cap, not a model or deck failure; raise `timeout_s`
in `testbench/tb_pex_post_layout.request.json` if the standalone leg is
needed standalone again.

## Narrative summary for the latest record (hand-maintained here, not in `measurements/characterization.md`)

`measurements/characterization.md` is generated end-to-end by
[`measurements/build_characterization_report.py`](../../measurements/build_characterization_report.py),
and its "Post-layout PEX detail" paragraph can only ever reproduce the terse
`- Result:` lines that this directory's own `records/<record-id>.md` carries.
The triage *conclusions* below -- the `klt` pin, the per-corner root-cause
attribution, the issue cross-references -- are not fields in the record's
companion `.json` and cannot be regenerated from it, so **this file is where
they live**.

Hand-editing that generated paragraph (or its matching "Limitations" bullet)
into a richer form makes `build_characterization_report.py --check` report
`characterization.md` as stale indefinitely, because no generator run can ever
reproduce prose the record does not contain -- exactly the failure issue #146
was filed for. **When a new record is minted, update this section and re-run
the generator; do not hand-edit `characterization.md`.**

### Record `20260924-181248-50554fe` (`klt 0.6.0+g040f3406b485`) — current

First record cut against a layout that carries the `hvi` (75/20)
voltage-domain marker (issue #142), and the first in which the extracted-side
leg re-simulates the design's own transistors.

- `klt sim` (schematic-side leg, standalone): `status=pass, corners=45,
  passed=45, failed=0, errored=0`. The nine `timeout` errors the previous
  record's standalone leg carried did not recur — consistent with the
  "host-load-induced, not a model or deck failure" reading above (same 120 s
  `options.timeout_s` cap, unchanged).
- `klt pex` (schematic + extracted legs + delta): `status=pass, passed=135,
  failed=0, errored=0, pin_count_mismatch=None`, exit code `0`. Extraction:
  `deck=sky130, device_count=97, net_count=28`.
- **Flavour binding is correct for the first time.** All 92 MOS devices in
  `netlist-snapshots/20260924-181248-50554fe.pex.extract.spice` bind
  `sky130_fd_pr__nfet_g5v0d10v5` (18) / `sky130_fd_pr__pfet_g5v0d10v5` (74) —
  counted out of the netlist, not inferred. The prior record's 27 `ss`-corner
  `Pclm` aborts are gone.
- **`pass` here is ungraded — read the spread, not the verdict.** The request
  declares no limits on any measurement, so every `delta[]` row's `pass`
  means only that both legs produced a number. The record's own
  `delta[]`-spread table: `vout_light_load_v` median 1.9% / max 161%,
  `vout_full_load_v` median 385% / max 3543%,
  `vin_minus_vout_full_load_v` median 633% / max 4775%.
- **The full-load rows are non-physical, and the cause is this flow's power
  routing.** Extracted `VOUT` reaches −5.7 V to −61.9 V at 50 mA. The
  extracted `VOUT` net carries 102 Ω–64.3 kΩ of lumped star series resistance
  across its 51 terminals (`VIN`: 259 Ω–29.4 kΩ across 145), because
  `gen-ldo-blocks.py` draws every net — power rails included — as a 0.30 µm
  met1 trunk. Out of #142's scope (which was the device flavour); tracked as
  #154.
- `body_bias`: `status=biased, unbiased_device_count=0, unbiased_nets=[]` —
  unchanged from the prior record, so the
  [klayout-tools#1983](https://github.com/2AMLogic/klayout-tools/issues/1983)
  physically-wrong-resimulation hazard still does not bite for this layout.
- Layout under test: `layout/ldo-core/reports/20260924-181216-50554fe` (LVS
  `status: match`, 47/47 devices, 27/27 nets) on
  `20260924-181155-50554fe`'s GDS (DRC `clean`, `violation_count=0` with
  75/20 present in `layers_in_stream_without_rules` — the marker is drawn and
  is DRC-neutral, measured). Both were re-cut for this record against the
  DR-011-resized `M_PASS`/`M_SENSE` schematic, so the device count moved
  67 → 92 MOS.

### Record `20260923-183915-d9900b5` (`klt 0.6.0+g040f3406b485`) — superseded

- `klt sim` (schematic-side leg, standalone): `status=error, corners=45,
  passed=36, failed=0, errored=9`. All nine errors are `timeout` under the
  testbench's own 120 s `options.timeout_s` cap at cold/low-supply corners --
  host-load-induced, not a model or deck failure; the `klt pex` run's own
  schematic leg completed those same corners (see "On the standalone
  schematic-side leg's timeouts" above).
- `klt pex` (schematic + extracted legs + delta): `status=error, passed=108,
  failed=0, errored=27, pin_count_mismatch=None`. The 27 are 9 `ss` corners x
  3 measurements, all one root cause: the landed layout draws no `hvi` (75/20)
  markers, so every MOS binds the `*_01v8` core model at g5v0d10v5 geometries
  and the substituted model's binning fails ngspice's BSIM4 parameter check at
  `ss`. Drawing the marker is a repo-local layout task tracked in #142; the
  residual upstream friction (`klt extract --pdk` staying silent when a deck
  declares flavour markers the layout does not contain) is filed as
  [klayout-tools#2417](https://github.com/2AMLogic/klayout-tools/issues/2417).
- `body_bias`: `status=biased, unbiased_device_count=0` -- no device body sits
  on an anonymous deck-synthesized net, so the
  [klayout-tools#1983](https://github.com/2AMLogic/klayout-tools/issues/1983)
  physically-wrong-resimulation hazard does not bite for this layout as
  landed.
- All three previously-disclosed upstream gaps --
  [#1157](https://github.com/2AMLogic/klayout-tools/issues/1157),
  [#1159](https://github.com/2AMLogic/klayout-tools/issues/1159) and
  [#1369](https://github.com/2AMLogic/klayout-tools/issues/1369) -- are fixed
  upstream as of this record's `klt` pin (see the two "Update (2026-09-23,
  issue #122)" notes above). What bounds the extracted-side leg today is
  therefore repo-local (#142), not upstream.

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

**Note on the `klt` pin.** Historically `layout/requirements.txt` pinned a
`klt` commit (`acb0ae6`) predating `klt pex`'s introduction --
`layout/.venv/bin/klt --version` reported `0.2.0` and its `<command>` list
had no `pex` verb -- so this experiment recorded its own, separate pin below
rather than reusing `layout/`'s.

**Update (2026-09-24, issue #142): the two pins have converged.**
`layout/requirements.txt` now pins `040f3406`, the same commit this
experiment's 2026-09-23 run already used, because the layout flow itself now
needs sky130 voltage-flavor support from that build (see that file's "Pin
history"). `layout/.venv/bin/klt` is therefore a valid `--klt` argument here
and is what the 2026-09-24 record below was run with -- which also means the
layout under test and the `klt pex` run against it are, for the first time,
the same `klt` build end to end. They are still *separately* pinned: nothing
forces them to stay equal, so a future bump on either side must re-check the
other rather than assume. `layout/` remains a read-only dependency of this
experiment.

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
- **2026-09-23 run (issue #122, record `20260923-183915-d9900b5`):** `klt`
  commit `040f3406b4858ac7a5b8faa8df5327fd62a65afa` (2AMLogic/klayout-tools
  `main`, 300 commits past `v0.5.0`), `klt --version` reports
  `0.6.0+g040f3406b485` (verified end-to-end: installing the pin reproduces
  the exact version string the run's own `provenance.klt_version` records).
  A git-commit pin rather than a release, because the #1157/#1159 fixes
  (`2dc66ece`) postdate `v0.5.0`, the latest release at recording time --
  the same move sky130-pll#46 already made. Install:
  `uv tool install "klayout-tools @ git+https://github.com/2AMLogic/klayout-tools@040f3406b4858ac7a5b8faa8df5327fd62a65afa"`.
  PDK pin unchanged.
- **2026-09-24 run (issue #142, record `20260924-181248-50554fe`):** same
  `klt` commit `040f3406b4858ac7a5b8faa8df5327fd62a65afa`, same reported
  version `0.6.0+g040f3406b485` (confirmed in the run's own
  `provenance.klt_version`). Not re-bumped — #142 needed no newer `klt`, it
  needed the *layout* to start using what this build already had. The
  difference from the 2026-09-23 run is therefore the drawn `hvi` marker and
  the DR-011 schematic resize, not the tool. Run with `--klt
  layout/.venv/bin/klt`, which `layout/requirements.txt` now pins to this
  same commit (see "Note on the `klt` pin" above). PDK pin unchanged.
- PDK: `sky130A`, `open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b` (same
  pin as `sim/pdk.json`).

## Evidence discipline

Same convention as `sim/<slug>/records/`: a later run mints a new
timestamped record under `records/` rather than overwriting an earlier one.
