# DR-001: sky130 pass-device and supply framing

- **Status**: **ratified** — framing (A) ratified by the operator's ruling on #1,
  2026-08-14
  ([comment](https://github.com/2AMLogic/sky130-ldo/issues/1#issuecomment-5297123803)).
  Ratification is scoped to the *framing* (pass-device family, input-rail
  mission, port parity); every numeric row in `spec/target-spec.md` remains
  DRAFT — see "Status notes" below.
- **Date**: 2026-08-13
- **Author**: Builder agent (drafted per #4)
- **Ratifies against / input to**: #1 (Ratify the target spec — operator-only,
  the T1 gate). #1 is the only thing that can turn any of this into a ratified
  spec row.
- **Supersedes**: none

> **Scope.** This record argues the *framing* — which sky130 device family the
> pass device (and therefore the block's input rail) is built on. It sets **no
> numeric value** in `spec/target-spec.md`; every row there remains DRAFT until
> #1 rules. The numbers below exist to make the cost of each framing visible to
> the ratifying decision, not to fill in the table.

This record follows the drafting *mechanism* used by the sibling canaries
`2AMLogic/sky130-pll` and `2AMLogic/sky130-bandgap` (agents draft and argue the
scope; the operator ratifies it in the corresponding ratification issue). It
does **not** follow their conclusions — see "Why sky130-pll's ratified answer
does not transfer" below. The argument here is written from the sky130 device
menu as it exists in this repo's pinned PDK, not by analogy to another block.

## Context

`spec/target-spec.md` § "The central sky130 porting question (must be resolved
before ratification)" names this as open item 1 and as "the single most
consequential decision" in the draft: several rows depend on it (Input, Output,
Load, Dropout, Current limit, Thermal, Area). The spec states the two candidate
framings and requires a decision record to pick one. That record is this one.

### The block being ported

`2AMLogic/gf180-ldo` (ratified 2026-07-31) is a 3.3 V-in / 1.8 V-out, 0–50 mA
LDO whose pass device is gf180mcu's 3.3 V PMOS (`pfet_03v3`). This repo's stated
purpose is *the same block on a second PDK* — "same block, two PDKs is the
portability proof" (`README.md`). Port parity is not decoration here; it is the
experiment.

### What the sky130 device menu actually offers

sky130 has no 3.3 V *core* flavor. Its MOS menu splits into a 1.8 V core family
and a 5 V-gate / 10.5 V-drain family (plus 20 V extended-drain devices and ESD
variants that are not general-purpose analog devices). The relevant PMOS
candidates, with parameters read from this repo's **pinned** PDK — `sky130A`,
open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b`, as pinned in
`sim/pdk.json`:

| | `sky130_fd_pr__pfet_01v8` | `sky130_fd_pr__pfet_g5v0d10v5` |
|---|---|---|
| Rating encoded in the device name | 1.8 V gate | 5.0 V gate, 10.5 V drain |
| Shortest modelled channel (`lmin` bin floor) | 0.15 µm | 0.50 µm |
| Narrowest modelled width (`wmin` bin floor) | 0.42 µm | 0.42 µm |
| Gate oxide `toxe` | 4.23 nm | 11.75 nm |
| ⇒ C_ox = ε_ox/`toxe` | 8.16 fF/µm² | 2.94 fF/µm² |
| `u0` (model card, long-channel bin) | 0.0105 m²/V·s | 0.0210 m²/V·s |
| \|V_th\| at the operating point, tt/27 °C | 0.803 V | 0.946 V |
| \|V_th\| at the operating point, ss/125 °C | 0.638 V | 0.822 V |

(The `lmin`/`wmin`/`toxe`/`u0` figures are model-card parameters; the \|V_th\|
figures are operating-point values from the screening runs in the appendix. The
core device also has `_lvt`/`_hvt` threshold variants; they change V_th, not the
1.8 V terminal rating, so they do not change any conclusion below.)

The two facts that dominate everything else: the 5 V device's channel is **3.3×
longer** at its floor and its oxide is **2.8× thicker**, so it is intrinsically a
much worse switch per unit width — and the core device is rated for **1.8 V**,
which a 3.3 V ±10 % rail exceeds by roughly 2×.

## Decision

**Recommend framing (A): build the pass device on
`sky130_fd_pr__pfet_g5v0d10v5`, and keep the block's mission — 3.3 V ±10 % in,
1.8 V out, 0–50 mA — as the port of `2AMLogic/gf180-ldo` that this repo exists
to be.** Framing (B) (all-1.8 V-core re-scope) is not recommended, on the
grounds the spec already states and this record substantiates below. Framing
(C) (5 V pass device with a core-device error-amplifier core) is named as a
*refinement inside* (A), to be settled by a later topology decision record, not
as a competing framing.

This is a **recommendation for #1 to rule on**, not a ratification. If #1 rules
for (B), this record is superseded by a new record rather than edited.

### Why (A): the core device is disqualified by rating, not by performance

This is the decisive point, and it is worth separating from the performance
argument because it is categorical rather than a trade-off.

A PMOS series-pass device in an LDO has its source at V_in and its bulk (n-well)
tied to its source. In normal regulation with the loop driving hard, the error
amplifier pulls the gate toward ground, so the device sees **\|V_gs\| ≈ V_in**.
With V_out shorted to ground — a case the draft spec's current-limit row
explicitly requires the block to survive continuously at V_in_max — it also sees
**\|V_ds\| ≈ V_in**. At V_in_max = 3.63 V both terminal stresses are roughly
**2× the core device's 1.8 V rating**, and the gate-oxide one is the sustained,
lifetime-limiting kind, not a momentary transient.

So framing (B) is not "a cheaper way to build the same block". On a 3.3 V rail
there is no core-device pass element to compare against: the comparison is
between building the specified block and building a different one.

By contrast the 5 V device's ratings cover the required cases with margin, and
the short-circuit case is covered by the **drain** rating (10.5 V) rather than by
a protection scheme: at V_in_max = 3.63 V with V_out shorted, the pass device
stands off 3.63 V against a 10.5 V-rated drain. That converts the draft spec's
"survives continuous V_out = 0 short at V_in_max" row from a device-survival
question into a dissipation-and-current-limit question, which is the tractable
kind.

### Why (A): what it costs, quantified

Screening runs against the pinned models (full deck and caveats in the appendix)
give on-resistance per unit width, R_on·W, for a fully-driven pass PMOS
(gate at 0 V, bulk tied to source, deep triode):

| Device (L at bin floor) | V_sg | tt / 27 °C | ss / 125 °C |
|---|---|---|---|
| `pfet_g5v0d10v5` (0.50 µm) | 3.30 V | 6.5 kΩ·µm | 9.5 kΩ·µm |
| `pfet_g5v0d10v5` (0.50 µm) | 2.97 V | — | 10.5 kΩ·µm |
| `pfet_g5v0d10v5` (0.50 µm) | 2.10 V | 11.0 kΩ·µm | 15.8 kΩ·µm |
| `pfet_g5v0d10v5` (0.50 µm) | 1.62 V | 17.7 kΩ·µm | 23.9 kΩ·µm |
| `pfet_01v8` (0.15 µm) | 1.62 V | 3.4 kΩ·µm | 4.2 kΩ·µm |
| `pfet_01v8` (0.15 µm) | 1.50 V | — | 4.7 kΩ·µm |

Three consequences fall out of that table.

1. **Gate drive shrinks exactly where dropout is measured.** The draft dropout
   row (< 300 mV at 50 mA) is measured, by gf180-ldo's convention, at
   V_in ≈ V_out + dropout ≈ 2.10 V — *not* at V_in_min = 2.97 V. Since the pass
   PMOS's source is V_in and its gate can be pulled no lower than ground, the
   available gate drive **is** V_in at the test point. At 2.10 V with
   \|V_th\| ≈ 0.82 V (ss/125 °C), roughly 39 % of the drive is consumed by the
   threshold, and R_on·W is 1.5× worse than at 2.97 V and 1.7× worse than at
   3.30 V. Any sizing done at the nominal rail understates the requirement by
   about 1.7×. This is the single easiest way to get framing (A) wrong.
2. **The binding corner is slow-and-hot.** At fixed drive, R_on·W degrades ~43 %
   from tt/27 °C to ss/125 °C even though \|V_th\| *falls* by 124 mV over that
   span — mobility loss beats the threshold gain, because the device runs at
   large overdrive where the V_th term is not dominant. That is consistent with
   gf180-ldo's ss/125 °C dropout convention and supports carrying it over. It
   should still be confirmed against the fs/sf corners and the −40 °C endpoint
   (where the threshold gain is largest) rather than assumed.
3. **Width and area.** 300 mV at 50 mA means R_on ≤ 6 Ω. At the dropout test
   point on the binding corner (15.8 kΩ·µm) that is **≈ 2.6 mm** of total gate
   width, versus ≈ 1.75 mm if sized at V_in_min. Active gate area is
   2.6 mm × 0.5 µm ≈ **1.3 × 10³ µm² ≈ 0.0013 mm²**. Against the draft area row
   (< 0.1 mm² core area) that is ~1.3 % before layout overhead — fingering,
   contacts, guard rings, and the wide metal a 50 mA path needs will multiply it
   several-fold, but the pass device does not look like the row's binding
   constraint. **This qualifies the spec's own worry**: the spec's note that
   "the area target may need revisiting under framing (A)" is a real effect but,
   on these first-order numbers, a small one. The area row's risk lives in the
   rest of the block, not in the pass FET.

For reference, the same 6 Ω target built on a core device at a 1.62 V rail
(i.e. framing (B)'s world) needs ≈ 0.70 mm of width and ≈ 105 µm² of gate area —
roughly **12× less area**. That is the honest size of (A)'s area penalty; it is
just not, by itself, a reason to change what the block is.

### Why (A): the port penalty relative to gf180 is real but bounded

gf180mcu's `pfet_03v3` (gf180-ldo's pass device) has an `lmin` bin floor of
0.28 µm and `toxe` = 7.9 nm, against 0.50 µm and 11.75 nm for sky130's 5 V PMOS
(both read from the locally installed PDKs). On channel length and oxide
thickness alone that is ~1.8× and ~1.5×, i.e. roughly **2.7× more width for the
same on-resistance at equal overdrive**, before accounting for mobility and
velocity-saturation differences between the two processes. So sky130 costs this
port a meaningfully bigger pass device than gf180mcu — expected, since sky130 is
being asked to do at 5 V-flavor what gf180mcu does at its native 3.3 V flavor —
but not a different order of magnitude, and not enough to make the port
pointless. A cross-PDK dropout/area comparison of the *same* block is exactly
the kind of result the two-PDK experiment exists to produce.

### Why (B) is not recommended — and the fair case for it

**The disqualifying fact** is the one the spec already states and § "the core
device is disqualified by rating" substantiates: a 1.8 V-core LDO cannot produce
1.8 V from a 1.8 V-class input. Dropout is not a free parameter; even with the
core device's much better R_on·W, at V_in_min = 1.62 V the block would be trying
to deliver 1.8 V from a rail 180 mV *below* the target. There is no pass-device
sizing that fixes this. So (B) is not "the same LDO, cheaper" — it necessarily
re-scopes the output as well as the input.

**What the block would then be.** Framing (B)'s honest product is a *core-rail
post-regulator*: roughly 1.8 V ±10 % in, ~1.2 V out (a plausible ±2 %-class
target leaving ~420 mV of dropout budget at V_in_min), 0–50 mA, built entirely
on `pfet_01v8`/`nfet_01v8`. That is a genuinely useful block — a PSRR-cleanup /
point-of-load regulator for a noisy core rail, and a natural companion to
`2AMLogic/sky130-bandgap` in a power-management group. If #1 rules for (B), the
spec's Input, Output, Dropout, Current limit, Thermal, and Area rows must all be
re-derived, and this repo should stop describing itself as a port of gf180-ldo.

**The fair case for (B)**, stated as its advocate would state it:

- **It is where sky130 is strongest and best exercised.** The 1.8 V core devices
  are sky130's best-characterized, most-used, smallest devices, and the ones the
  standard-cell libraries and the bulk of open sky130 analog work are built on.
  A block on those devices is more likely to be reused downstream than one that
  requires an off-chip 3.3 V rail.
- **It is ~12× smaller in the pass device** and correspondingly cheaper in gate
  capacitance (≈ 0.86 pF vs ≈ 3.9 pF, appendix), which relaxes the coupling
  between the Iq budget and the load-transient row that framing (A) tightens
  (see Consequences).
- **It avoids the whole 5 V-flavor tooling surface** — separate DRC rules, well
  and spacing constraints, and a device family with less open-source precedent
  in analog blocks than the core devices have.
- **Port parity is a means, not the end.** If the operator's objective for this
  canary is "grow the catalog's inventory of verified open-PDK analog blocks on
  the devices sky130 users actually use", (B) serves it better than (A) does.

**Why the recommendation still goes to (A)**: the disagreement above is not a
device-physics disagreement — on the physics, (A) is the only framing that
builds the specified block, and (B)'s advantages are all real. It is a
disagreement about *what this repo is for*, and both `CLAUDE.md` ("Port parity:
the spec and structure mirror the ratified `2AMLogic/gf180-ldo` — same block,
two PDKs") and `README.md` ("same block, two PDKs is the portability proof")
answer that question already: the port *is* the objective, and the cross-PDK
comparison is the deliverable. (B) forfeits that deliverable, and the catalog
would then hold two non-comparable LDOs rather than one block proven in two
PDKs. That is the operator's call to confirm or overturn in #1, and it is
squarely an objective question rather than a technical one — which is why this
record recommends rather than rules.

### Why sky130-pll's ratified answer does not transfer

`2AMLogic/sky130-pll`'s DR-001 ratified an all-1.8 V-core scope (2026-08-13).
That precedent is cited here **only for the mechanism** — how a scoping record
is drafted, argued, and ratified in the operator-only issue. Its answer does not
carry over, for a structural reason:

- A ring PLL is mostly fast digital logic (ring stages, PFD, dividers) around
  one analog element, so its device family follows the standard-cell library it
  clocks. Nothing in its interface contract requires standing off a rail above
  the core supply.
- An LDO's pass device is defined by **the input rail it must stand off and the
  headroom it must deliver**. That is a terminal-rating constraint, not a
  library-affinity preference. A 3.3 V input is outside the 1.8 V core devices'
  rating, full stop.

The device family follows the block's function, not a repo-to-repo precedent.

## Alternatives considered

- **(A) 5 V pass device (`pfet_g5v0d10v5`), 3.3 V in / 1.8 V out.**
  **Recommended.** Argued above.
- **(B) All-1.8 V-core re-scope.** Not recommended. It cannot produce 1.8 V from
  a 1.8 V-class input; it changes the block's mission and forfeits port parity.
  Its fair case is stated above. It would become the right answer if #1 states
  an objective other than "port gf180-ldo to sky130" — that is the axis on which
  it turns, and it is the operator's to state.
- **(C) Mixed: 5 V pass device with a core-device error-amplifier core.**
  Named, and deliberately **not** treated as a competing framing: the pass
  device is 5 V-flavor in this option too, so (C) sits *inside* (A) rather than
  against it, and choosing (A) does not foreclose it. Its attraction is real —
  core devices give more gm per µA and per µm² for the amplifier, which matters
  under a < 30 µA Iq budget. Its cost is a verification burden: every
  core-device terminal must be shown to stay within 1.8 V at **every** corner,
  including enable/startup, load transients, and a continuous output short, and
  that guarantee normally requires an internal clamped or pre-regulated rail
  whose own startup behaviour must be proven. The amplifier's output stage
  cannot be core-flavor regardless, since the pass gate must swing to V_in to
  turn the device off. **Deferred to a later topology decision record**, after
  (A) is ratified; noting it here so it is on the record as available rather
  than accidentally excluded.
- **(D) Stacked/cascoded core devices as the pass element** (two `pfet_01v8` in
  series with an intermediate bias, each nominally seeing half the rail).
  **Ruled out.** It protects drain–source stress but not the gate-oxide stress
  of the top device's driver, requires an intermediate bias that is guaranteed
  at *all* times — including power-up before any bias exists, and during a fast
  short where the stack collapses — and puts at least twice the channel length
  in the pass path, in the one place the block has no resistance to spare. It
  also complicates the n-well/body tie for the lower device. sky130 publishes no
  qualified stacked-usage guidance for the core devices, so the entire
  reliability argument would have to be constructed and defended here, to save
  an area cost that § "Width and area" shows is ~1.3 % of the area row.
- **(E) NMOS pass device on `nfet_g5v0d10v5`** (source follower, gate driven
  above V_out + V_th from the 3.3 V rail — no charge pump needed at this ratio).
  **Orthogonal to this decision, not an alternative to it**: it is still the 5 V
  family, i.e. still framing (A). Whether the pass device is PMOS or NMOS is a
  topology question (it trades dropout and quiescent current against PSRR and
  output-pole placement) and belongs to a later record. Naming it here so the
  ratification of (A) is understood as a *device-family* ruling, which holds
  under either pass topology, and not as a topology ruling.
- **(F) 20 V extended-drain devices (`pfet_20v0`).** Ruled out. Vastly more
  standoff than a 3.63 V maximum needs, with the on-resistance and area penalty
  that comes with it. There is no requirement they satisfy that
  `pfet_g5v0d10v5` does not.
- **(G) Port gf180's `pfet_03v3` flavor unchanged.** Not an available option —
  sky130 has no 3.3 V core device family. Named only to rule out the category
  error of "just port the flavor".

## Consequences

### What ratifying (A) fixes

- **The Input row stays 3.3 V ±10 % (2.97–3.63 V) and the Output row stays
  1.8 V**, i.e. the port-parity rows survive as drafted, and the DRAFT table's
  stated basis ("written against framing (A) as the parity-preserving default")
  becomes the ratified basis rather than a provisional one.
- **Pass-device sizing acquires a concrete starting point** — order 2–3 mm of
  total width at L = 0.50 µm for the drafted 6 Ω — which unblocks the device
  characterization campaign (open item 3) with a target to characterize *around*
  rather than an open-ended sweep.
- **The short-survival row becomes a dissipation problem, not a device-survival
  problem**, since 3.63 V is comfortably inside a 10.5 V drain rating.

### What (A) hands to design, unresolved

- **Dropout, and its binding corner.** The screening data point at ss/125 °C and
  the mobility-dominated degradation both support carrying gf180-ldo's
  ss/125 °C convention over, but the record does **not** settle it: the −40 °C
  endpoint (maximum \|V_th\|, best mobility) and the fs/sf corners have not been
  screened, and the corner-model names are still open item 4. The binding-corner
  assignment must be fixed by measurement, and the dropout test point must be
  stated explicitly as V_in = V_out + dropout (≈ 2.10 V) rather than V_in_min —
  the 1.7× sizing error between those two conventions is the largest single
  numerical trap in framing (A). The 6 Ω budget must also absorb routing, contact
  and metal IR drop in a 50 mA path; those are not free at this resistance level.
- **The load-transient excursion budget is now coupled to the Iq budget.** The
  pass device's gate capacitance under (A) is ≈ 3.9 pF (2.6 mm × 0.5 µm ×
  2.94 fF/µm², before overlap) — roughly 4.5× the ≈ 0.86 pF a core-device pass
  element would present. The draft rows "peak excursion ≤ 150 mV on a 1↔50 mA
  step with ~1 µs edges" and "Iq < 30 µA" therefore interact: after C_out has
  absorbed the first microsecond, recovery is limited by how fast the amplifier
  can slew that gate, and a few µA into 3.9 pF is order 1 V/µs. If both rows
  are ratified as drafted, the design owes either a class-AB / slew-boosted
  output stage (which spends area and complexity, not necessarily static Iq) or
  a superseding record relaxing one of the two rows. **This record does not
  relax either row** — it names the coupling so #1 rules with it visible.
- **The C_out/ESR window (open item 2) must be decided *after* this one, not in
  parallel.** It depends on framing (A) twice over: the C_out floor is set by
  the excursion budget and the loop's large-signal response time (a first-order
  estimate for a 49 mA step held for ~1.5 µs at 150 mV puts the floor in the
  sub-µF to µF range — illustrative only, not a proposed value), and the pass
  gate's ~3.9 pF against the amplifier's output resistance forms an internal
  pole that is close enough to the loop bandwidth to be a first-class stability
  element rather than a distant parasitic. Sequencing: ratify (A) → characterize
  the device (open item 3) → size the pass device → then draft the C_out/ESR
  record.
- **PSRR at light load.** A large 5 V-flavor pass device with V_in on both its
  source and its n-well presents a substantial gate-to-source and
  bulk-referenced parasitic path from the input rail to the gate node; at the
  1 mA light-load condition the draft calls binding, that path is a direct
  high-frequency PSRR leak. The drafted > 20 dB at 100 kHz is not obviously free
  under (A) and is a characterization target, not an inherited number.
- **Area.** The pass device itself is ~1.3 % of the < 0.1 mm² row before layout
  overhead, so the spec's flagged concern is real but small; the row's risk is
  elsewhere in the block. It should still be re-checked once the amplifier and
  bias topology exist, since framing (A) forces 5 V-flavor devices anywhere a
  node can exceed the core rating — which is most of the bias chain unless
  framing (C) is later adopted.

### What is explicitly *not* settled here

No numeric value in `spec/target-spec.md` changes because of this record. The
screening numbers in the appendix are not `sim/` evidence, do not carry a
corner-swept testbench, and must not be cited as a verified result — the
recorded characterization is open item 3, and every drafted row remains DRAFT
until #1.

## Status notes

This record stays `proposed` until #1 closes. #1 is the operator-only
ratification issue for `spec/target-spec.md`; only the operator's ruling
there — not this record on its own — moves the Input/Output/pass-device rows
from DRAFT to ratified. If #1 rules differently from this record's
recommendation, a superseding record is filed to match the ratified outcome;
this record is not edited after the fact (decision records are append-only per
`CLAUDE.md`).

**Ratification update (2026-08-14).** #1's operator ruling accepted this
record's recommendation: framing (A) — pass device `sky130_fd_pr__pfet_g5v0d10v5`,
3.3 V ±10 % in / 1.8 V out / 0–50 mA, port parity with `2AMLogic/gf180-ldo` — is
ratified
([ruling comment](https://github.com/2AMLogic/sky130-ldo/issues/1#issuecomment-5297123803)).
The ruling is explicitly scoped to the framing only: it does **not** ratify any
numeric row in `spec/target-spec.md`, and #1 stays open as the gate for those —
consistent with the sibling-canary precedent (sky130-pll / sky130-sar-adc) the
ruling cites, that ratifying a framing record does not ratify the values.
Framing (C) — a 5 V pass device with a core-device error-amplifier core —
remains an open refinement *inside* (A), deferred to a later topology decision
record as this record already proposed. This paragraph is appended per this repo's append-only
decision-record convention; the argument above is unedited.

Filed under this repo's `DR-NNN-<slug>.md` convention
(`spec/decision-records/README.md`). Note that `spec/target-spec.md`'s closing
paragraph says "four-digit `DR-NNNN-<slug>.md`" while the decision-records
README says three-digit; the three-digit form is used here to match the README,
the sibling repos, and #4's own definition of done. Reconciling that wording is
`spec/target-spec.md`'s business and is deliberately left alone by this record,
which does not touch that file.

## Appendix: screening deck and caveats

**These are screening numbers, not evidence.** They exist so the framing
argument cites something checkable instead of asserting device behaviour from
memory. They are not a `sim/` record, they carry no corner sweep beyond the two
points shown, and no spec row may be set from them.

- PDK: `sky130A`, open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b` (the pin
  in `sim/pdk.json`). Simulator: ngspice 47.
- Method: DC operating point, W = 10 µm, `nf` = 1, single device, bulk tied to
  source, gate at 0 V, V_sd = 50 mV (deep triode), R_on = V_sd / I_d, reported
  as R_on·W in Ω·µm. Each device at its `lmin` bin floor (0.50 µm for
  `pfet_g5v0d10v5`, 0.15 µm for `pfet_01v8`).
- Corners: `tt` at 27 °C and `ss` at 125 °C, via the corner sections of
  `libs.tech/combined/sky130.lib.spice`.

```spice
.lib "$PDK_ROOT/sky130A/libs.tech/ngspice/sky130.lib.spice" ss
.param VS=2.10
.param VSD=0.05
.temp 125
Vs5 s5 0 {VS}
Vd5 d5 0 {VS-VSD}
Vg5 g5 0 0
XM5 d5 g5 s5 s5 sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=10 nf=1 m=1
Vs1 s1 0 {VS}
Vd1 d1 0 {VS-VSD}
Vg1 g1 0 0
XM1 d1 g1 s1 s1 sky130_fd_pr__pfet_01v8 L=0.15 W=10 nf=1 m=1
.control
op
let ron5 = 0.05/abs(i(Vd5))
let ron1 = 0.05/abs(i(Vd1))
print ron5 ron1
print @m.xm5.msky130_fd_pr__pfet_g5v0d10v5[vth]
print @m.xm1.msky130_fd_pr__pfet_01v8[vth]
quit
.endc
.end
```

**Known optimism in these numbers** — a real design should expect to need more
width than they imply:

- The gate is held at exactly 0 V; a real amplifier output stage cannot pull
  fully to the rail, and every millivolt of V_ol comes straight out of the
  overdrive at the dropout test point where drive is scarcest.
- A single 10 µm-wide device with `nf` = 1 is not how 2.6 mm of pass device gets
  drawn; fingering, contact resistance, and metal IR drop in a 50 mA path all
  add series resistance that the 6 Ω budget must absorb.
- Self-heating in the pass device at the dropout condition (50 mA × 300 mV =
  15 mW, and far more during a short) is not modelled here.
- The core-device rows are deliberately shown at 1.62 V and 1.50 V only, i.e.
  within its 1.8 V rating. The deck also solves the core device at 2.10 V and
  3.30 V, but those points describe an operating condition that **violates the
  rating**, so they are not tabulated and are not a basis for any comparison
  here: the models will happily return a current for a device that would not
  survive in service.
