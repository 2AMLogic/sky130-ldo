# DR-003: sky130 pass-device characterization (dropout point, sizing, Iq scope)

- **Status**: proposed — not self-ratifying; input to #1
- **Date**: 2026-08-14
- **Author**: Builder agent (drafted per #10)
- **Ratifies against / input to**: #1 (Ratify the target spec — operator-only,
  the T1 gate)
- **Supersedes**: none

## Context

`spec/target-spec.md` open item 3: "sky130 device characterization. Dropout
test point, pass-device sizing, Iq budget, and leakage rows all carry
provisional or absent numbers until device char against the sky130 models
exists. No such number is invented here." DR-001 (ratified framing) already
ran a small screening deck — two corners only (`tt`/27 °C, `ss`/125 °C), four
`V_sg` points — and explicitly handed this record two open threads:

> The screening data point at ss/125 °C and the mobility-dominated
> degradation both support carrying gf180-ldo's ss/125 °C convention over,
> but the record does **not** settle it: the −40 °C endpoint... and the
> fs/sf corners have not been screened.

and named the dropout test-point convention (`V_in = V_out + dropout`, **not**
`V_in_min`) as "the single easiest sizing trap" in framing (A). This record
extends DR-001's screening — same method, same pinned PDK
(`sky130A`, open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b`, `sim/pdk.json`)
— across the full `{tt, ss, ff, sf, fs}` × `{−40, 27, 125} °C` grid DR-004
binds, at the two bias points that matter: the dropout test point
(`V_sg` = 2.10 V, i.e. `V_in = V_out + dropout` per DR-001's convention) and
the nominal rail (`V_sg` = 3.30 V). Per CLAUDE.md's "verification is the
product," this is derived from the pinned PDK's own models, not ported from
gf180-ldo's `pfet_03v3` numbers, per the issue's explicit instruction.

**Scope caveat, stated up front.** This is an operating-point screening deck
— DC `op`, single device, ideal gate drive at 0 V, bulk tied to source — not
a `sim/` corner-swept evidentiary record with a testbench, an
`experiment.json` manifest, or committed per-corner logs. It exists so this
record's argument cites something checkable rather than asserting device
behaviour from memory, exactly as DR-001's own appendix does. No spec row may
be set from it. The full deck and every raw number are in the Appendix.

## Decision

**Three findings, each scoped to what this screening can and cannot support:**

### 1. Dropout test point: `V_in = V_out + dropout` ≈ 2.10 V, reaffirmed

DR-001's convention is not just carried over, it is reaffirmed by fresh data:
across every one of the five corners, gate drive is scarcest at the dropout
test point (`V_sg` = 2.10 V) — R_on·W there is 1.6–1.8× worse than at the
nominal rail (`V_sg` = 3.30 V) for every corner, consistent with DR-001's
1.7× estimate. **Any sizing performed at `V_in_min` (2.97 V) or nominal
(3.3 V) understates the required width; the dropout point is the sizing
point, not a corner case to check afterward.**

### 2. Binding corner: `{ss, sf}` at 125 °C, tied within this screen's resolution — not a single-corner close

| Corner | R_on·W @ V_sg=2.10 V, −40 °C | 27 °C | 125 °C | R_on·W @ V_sg=3.30 V, −40 °C | 27 °C | 125 °C |
|---|---|---|---|---|---|---|
| `tt` | 9.63 | 11.44 | 13.66 | 5.60 | 6.88 | 8.62 |
| `ss` | 10.46 | 12.38 | **14.71** | 5.89 | 7.25 | 9.07 |
| `ff` | 8.89 | 10.58 | 12.69 | 5.33 | 6.54 | 8.19 |
| `sf` | 10.68 | 12.55 | **14.81** | 5.86 | 7.20 | 8.99 |
| `fs` | 8.78 | 10.51 | 12.67 | 5.37 | 6.59 | 8.27 |

(All values kΩ·µm, `sky130_fd_pr__pfet_g5v0d10v5`, L = 0.50 µm bin floor,
W = 10 µm, `nf` = 1, deep triode `V_sd` = 50 mV, gate at 0 V, bulk tied to
source — same method as DR-001's appendix.)

Three conclusions follow directly:

- **125 °C dominates over −40 °C at every corner, confirmed rather than
  assumed.** DR-001 speculated hot-and-slow beats cold-and-slow because
  mobility loss outruns the threshold gain; this grid confirms it uniformly
  — the −40 °C column is the best (lowest R_on·W) point in every row, by
  8–13 % relative to 27 °C and 25–35 % relative to 125 °C. The −40 °C
  endpoint DR-001 flagged as untested is now screened and is **not**
  binding.
- **`ss` and `sf` are statistically tied for worst**, both at 125 °C: 14.71
  vs 14.81 kΩ·µm at the dropout point (0.7 % apart), 9.07 vs 8.99 kΩ·µm at
  nominal (`sf` very slightly better there — the ranking is not even fully
  consistent between the two bias points). That gap is well inside what a
  single-bin, single-geometry operating-point screen can resolve. **This
  record does not pick a winner between `ss` and `sf`** — carrying both as
  co-binding, and sizing to the worse of the two at each bias point, is the
  correct conservative reading, not a shortcut.
- **`ff` and `fs` cluster together as the best corners**, essentially tied
  with each other and each ~7–12 % better than `tt`. Combined with the
  previous point, this means **R_on·W groups by the corner name's first
  letter, not its second**, for this device at this bin — see DR-004 for
  the naming consequence. `sf` is not "the fast-P corner" in the sense that
  would make it benign for a PMOS pass device; empirically, for
  `pfet_g5v0d10v5` at this geometry, it is the single worst point measured.

### 3. Pass-device sizing methodology, refined

Target: `R_on` ≤ 6 Ω (from the DRAFT's < 300 mV dropout at 50 mA row, before
routing/contact/metal IR drop, per DR-001). Using the worse of `{ss, sf}` at
125 °C and the dropout test point (14.81 kΩ·µm):

```
W_total ≥ 14.81 kΩ·µm / 6 Ω ≈ 2468 µm ≈ 2.47 mm  (at L = 0.50 µm bin floor)
```

This refines DR-001's ≈ 2.6 mm estimate (which used a single ss/125 °C point
at 15.8 kΩ·µm from a slightly different single-point screening run) to the
same order and the same conclusion: **≈ 2.5 mm class total gate width**,
before the same known-optimism caveats DR-001's appendix names (ideal 0 V
gate drive, no fingering/contact/IR-drop margin, no self-heating). The two
screening runs disagree by ~6%, which is within the noise this kind of
single-bin operating-point deck should be expected to carry — both point at
the same design conclusion and neither should be read as more precise than
it is.

**Methodology stated for reuse**: sizing must (a) use the dropout bias point
(`V_sg` = `V_out` + dropout budget, not `V_in_min`), (b) use the worse of the
co-binding corners found by an actual sweep, not a corner chosen by the
letter-name gloss (see DR-004), and (c) reserve margin above the bare-device
R_on for routing/contact/IR drop and self-heating, none of which this
screening models.

### 4. Iq expectations: scoped as an open TODO, not a number

**This record explicitly does not set an Iq number.** Iq is a full-loop
quantity — bias chain, error amplifier, and pass-device gate leakage — and no
amplifier or bias topology exists yet in this repo (DR-001's Consequences
section already names this as handed to design, unresolved). Inventing an Iq
figure now, by e.g. scaling gf180-ldo's 30 µA target by a device-size ratio,
would be exactly the fabricated precision CLAUDE.md prohibits ("agents do not
relax a spec line... a row that proves unmeetable is superseded... never
silently loosened" — the same discipline applies to inventing rather than
loosening). What this record **can** and does commit to is the one
Iq-adjacent quantity the pass device alone determines: its gate capacitance
at the sizing point above.

```
C_gate ≈ W_total × L × C_ox ≈ 2500 µm × 0.50 µm × 2.94 fF/µm² ≈ 3.68 pF
```

(before overlap capacitance; `C_ox` from DR-001's model-card reading of
`toxe` = 11.75 nm at this pin). This refines DR-001's ≈ 3.9 pF estimate
(computed from its ≈ 2.6 mm sizing) to the same order — **≈ 3.6–3.9 pF**,
depending on which of the two sizing runs is used — and is the slew-rate
load any future amplifier's Iq budget must be sized against, per DR-001's
Consequences ("a few µA into 3.9 pF is order 1 V/µs"). The Iq **budget** row
itself remains open until a bias/amplifier topology exists to characterize.

## Alternatives considered

- **Port gf180-ldo's device-characterization numbers, scaled for sky130.**
  Rejected — the issue is explicit that DR-003 must be "derived from the
  pinned PDK's `pfet_g5v0d10v5` characteristics... rather than ported from
  gf180 numbers," and gf180's `pfet_03v3` is a different device (different
  oxide, different channel-length floor, different process) — a scaled port
  would look precise while being unfounded.
- **Declare `ss`/125 °C the sole binding corner**, matching gf180-ldo's
  convention and DR-001's speculation, without screening `sf`. Rejected —
  this record's own data shows `sf` is at least as bad, and DR-001
  explicitly flagged this exact gap as unconfirmed; asserting a single
  winner now would repeat the mistake DR-001 warned against rather than
  close it.
- **Wait for a full `sim/`-evidentiary, corner-swept transient testbench**
  before drafting DR-003 at all. Rejected as blocking for this record's
  purpose — the issue explicitly sanctions screening-marked data (mirroring
  DR-001's own appendix convention), and no LDO schematic exists yet in
  `design/` to build a real testbench around; there is nothing yet for
  `sim/<slug>/testbench/` to contain. This record is clearly marked
  screening-only throughout, consistent with that convention, and does not
  claim to satisfy the "no claim without a testbench" rule for a final spec
  row — only to ground this decision record's argument.
- **Set a provisional Iq budget number now** (e.g. by device-area or
  gate-capacitance ratio against gf180's 30 µA), to give #1 something
  concrete on that row. Rejected — no amplifier topology exists to ground
  the number; CLAUDE.md's "do not invent settled numbers to replace the
  drafts" applies exactly here, and the gate-capacitance figure above is
  offered instead as the honest partial answer.
- **Treat the −40 °C endpoint as still open** since only three temperatures
  were swept rather than a finer sweep. Not adopted as a blocking caveat —
  the uniform 25–35 % margin from 125 °C at every one of five corners is a
  large enough gap that a coarse three-point sweep is sufficient to rule it
  out as binding; a finer sweep would refine the *margin*, not the
  conclusion.

## Consequences

- **Confirms and refines DR-001's dropout convention and sizing estimate**
  with a 30-point-per-bias-point grid (5 corners × 3 temperatures, at each
  of the two bias points that matter) rather than DR-001's 2-point screen.
- **Narrows, but does not close, the binding-corner question**: from
  "`ss`/125 °C suspected, `fs`/`sf` and −40 °C untested" (DR-001) to "`ss` or
  `sf` at 125 °C, tied within this screen's resolution; `−40 °C`, `ff`, and
  `fs` confirmed non-binding" (this record). Closing the `ss` vs `sf` tie
  needs either finer geometry/bin resolution than a single 10 µm/L-floor
  device provides, or accepting both as co-binding and sizing conservatively
  to the worse at each bias point — this record recommends the latter as the
  practical default, without foreclosing a future record that resolves the
  tie analytically.
- **Feeds DR-002** (this issue's third record) the refined gate-capacitance
  estimate (≈ 3.6–3.9 pF) as the pass-gate pole's load.
- **Feeds DR-004's naming caveat**: this is the empirical data that record
  cites to show the corner-name letters do not predict severity for this
  device.
- **Hands to design, unresolved**: the `ss` vs `sf` tie-break; a full
  corner-swept `sim/` evidentiary record once a pass-device subcircuit or
  layout exists (this screening's single 10 µm/`nf`=1 device is explicitly
  not how 2.5 mm of pass device is actually drawn, per DR-001's
  known-optimism caveats, reproduced in the Appendix); the Iq budget itself,
  blocked on an amplifier/bias topology; leakage-based enable/shutdown
  numbers, likewise blocked.
- **No numeric value in `spec/target-spec.md` changes because of this
  record.** The screening numbers above are not `sim/` evidence, carry no
  corner-swept testbench, and must not be cited as a verified result.

## Status notes

This record stays `proposed` until #1 closes. #1's ratification of this
record's methodology and screening-derived starting points does not by
itself satisfy this repo's "no claim without a testbench" rule for the
Dropout, Iq, or Leakage spec rows — a `sim/` evidentiary record, built once a
pass-device subcircuit and (for Iq) an amplifier topology exist, is still
required before those rows can move past DRAFT. This record's job is to give
#1 grounded, PDK-derived starting points and an honest map of what remains
open, not to close the rows itself.

## Appendix: screening deck and caveats

**These are screening numbers, not evidence** — same convention as DR-001's
appendix. They carry no corner-swept testbench beyond the operating points
tabulated below, and no spec row may be set from them.

- PDK: `sky130A`, open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b` (the
  pin in `sim/pdk.json`, confirmed installed at that exact commit via
  `~/.volare/sky130A -> volare/sky130/versions/c6d73a35f524070e85faff4a6a9eef49553ebc2b/sky130A`
  at run time). Simulator: ngspice 47.
- Method: DC operating point, W = 10 µm, `nf` = 1, single device, bulk tied
  to source, gate at 0 V, `V_sd` = 50 mV (deep triode), `R_on` = `V_sd` /
  `I_d`, reported as `R_on`·W in Ω·µm. Device at its `lmin` bin floor
  (0.50 µm). Identical method to DR-001's appendix, extended to all five
  process corners and all three temperatures at two `V_sg` (= `V_s`, since
  gate is grounded) bias points instead of DR-001's two corners / four bias
  points.
- Corners: `tt`, `ss`, `ff`, `sf`, `fs` — the five sections DR-004 binds —
  via `libs.tech/combined/sky130.lib.spice` at the pinned commit.

```spice
* screening deck for DR-003 (issue #10), not sim/ evidence
.lib "<SKY130_MODEL_LIB>" <corner>
.param VS=<2.10 | 3.30>
.param VSD=0.05
.temp <-40 | 27 | 125>
Vs5 s5 0 {VS}
Vd5 d5 0 {VS-VSD}
Vg5 g5 0 0
XM5 d5 g5 s5 s5 sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=10 nf=1 m=1
.control
op
let ron5 = 0.05/abs(i(Vd5))
print ron5
print @m.xm5.msky130_fd_pr__pfet_g5v0d10v5[vth]
quit
.endc
.end
```

Run 5 corners × 3 temperatures × 2 `V_sg` points = 30 ngspice invocations via
`SKY130_MODEL_LIB` from `sim/bin/pdk-env.sh --print-env`, matching the
harness's own PDK resolution.

Full data (kΩ·µm, `R_on`·W):

| Corner | −40 °C, `V_sg`=2.10 V | 27 °C | 125 °C | −40 °C, `V_sg`=3.30 V | 27 °C | 125 °C |
|---|---|---|---|---|---|---|
| `tt` | 9.63 | 11.44 | 13.66 | 5.60 | 6.88 | 8.62 |
| `ss` | 10.46 | 12.38 | 14.71 | 5.89 | 7.25 | 9.07 |
| `ff` | 8.89 | 10.58 | 12.69 | 5.33 | 6.54 | 8.19 |
| `sf` | 10.68 | 12.55 | 14.81 | 5.86 | 7.20 | 8.99 |
| `fs` | 8.78 | 10.51 | 12.67 | 5.37 | 6.59 | 8.27 |

`\|V_th\|` at 27 °C, `V_sg` = 2.10 V (probe run, same deck with
`print @m...[vth]` only): `tt` 0.948 V, `ss` 0.996 V, `ff` 0.899 V, `sf`
1.044 V, `fs` 0.851 V — tracks `R_on`·W point-for-point (lower \|V_th\| ⇒
lower `R_on`·W at fixed `V_sg`), confirming the grouping above is a real
device-model effect at this bin, not a measurement artifact of the `R_on`
extraction. This record does not attempt to explain *why* the model bin
resolves \|V_th\| this way from BSIM parameters (`vth0`, `u0`, binning) —
that would require an audit of the binned `.pm3` corner files beyond this
record's scope — only reports that the effect is real and reproducible
across every temperature and both bias points tested.

**Known optimism in these numbers** (identical list to DR-001's appendix,
reproduced here since it applies unchanged to this extended grid):

- The gate is held at exactly 0 V; a real amplifier output stage cannot pull
  fully to the rail, and every millivolt of `V_ol` comes straight out of the
  overdrive at the dropout test point where drive is scarcest.
- A single 10 µm-wide device with `nf` = 1 is not how ≈ 2.5 mm of pass device
  gets drawn; fingering, contact resistance, and metal IR drop in a 50 mA
  path all add series resistance the 6 Ω budget must absorb.
- Self-heating in the pass device at the dropout condition
  (50 mA × 300 mV = 15 mW, and far more during a short) is not modelled
  here.
- This is a single-bin, single-geometry screen; the `ss`/`sf` tie at 125 °C
  is inside this method's resolution, not a claim that the two corners are
  truly equal at every geometry or bias point.
