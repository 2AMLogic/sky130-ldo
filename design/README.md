# `design/` — sky130-ldo core regulation loop + protection

Schematic source for issue #14 (item 1 of the T1/bronze re-read, #12/#13)
and issue #22 (protection/sequencing): `ldo_3v3in_1v8out.sch`, a clean-room,
forward-designed xschem schematic for the sky130 LDO's core regulation loop
(error amplifier + pass device + feedback divider + compensation +
enable/shutdown) plus the current-limit and soft-start circuitry. This is
genuinely original circuit-topology work — a textbook single-stage-OTA LDO
architecture (error amp driving a common-source pass device with Miller
compensation, e.g. Razavi *Design of Analog CMOS Integrated Circuits* ch. 5
& 11), a sense-FET current comparator, and a min-select soft-start input —
sized against this repo's own PDK screening data, not derived from,
reverse-engineered from, or ported from any third party's implementation —
per `CLAUDE.md`'s clean-room mandate.

## What this is, and isn't

- **Is**: a real, netlist-clean xschem schematic implementing the LDO block
  described in `spec/target-spec.md`'s DRAFT table, built on the framing
  ratified in `spec/decision-records/DR-001-pass-device-supply-framing.md`,
  with the pass device sized per
  `spec/decision-records/DR-003-sky130-device-characterization.md`'s
  methodology.
- **Isn't**: a `sim/`-evidentiary, corner-swept, spec-row-proving result.
  These issues are scoped to design *sources*, not verification — that is #18
  (block testbenches: `load-transient`, `psrr-dc`, `dropout-vs-load`) and
  #19 (full PVT/Monte Carlo). The OP checks described below are **screening
  sanity checks**, run the same way DR-001/DR-003's own appendices do
  (single process corner, single temperature, not committed as evidence) —
  they exist so this record's design claims cite something checkable rather
  than asserting circuit behaviour from memory, not to satisfy "verification
  is the product."

## Freshness

Originally written against `spec/target-spec.md` and
`spec/decision-records/{DR-001,DR-002,DR-003,DR-004}` as of commit `7de8d4b`
(2026-08-17) for issue #14; **re-verified against the same spec and
decision-record set as of commit `0e12b14` (2026-08-17), the tip of `main` at
the start of issue #22** — no spec file or decision record changed between
those two commits, so every citation below is still current.
`spec/target-spec.md` is entirely DRAFT pending #1; DR-001 is the only
**ratified** record among the four (framing only, no numeric row);
DR-002/003/004 are `proposed`. This schematic designs against the DRAFT
numbers and the `proposed` sizing methodology, per those issues' own
instruction not to block on #1.

## Topology

```
                         VIN
                          |
              +-----------+-----------+
              |                       |
          M_BIASP1 (diode)        M_TAIL (tail I-source)
              |                       |
            BIASP -----(gate)----->  EA_TAIL
              ^                       |
              |                 +-----+-----+-----------+
         M_BIASN2 (mirror)      |           |           |
              ^                M_IN1       M_IN2      M_IN2S
              |               (gate=FB)  (gate=VREF)  (gate=SS)
              |                 |           |           |
            [AMP_ENN]         EA_D1       EA_OUT <------+  --(gate)--> M_PASS --> VOUT
              ^                 |           |                                       |
           M_ENN2            M_MIR1      M_MIR2                                   R_FB_A
              |              (diode)    (mirror out)                                |
              0                 |           |                                       FB --> M_IN1.gate
                              [AMP_ENN]  [AMP_ENN]                                  |
                                 |           |                                    R_FB_B
                                 +---M_ENN2--+                                      |
                                                                                  N_FBB
                                                                                    |
                                                                                  R_FB_C
                                                                                    |
                                                                                    0

  R_BIAS: VIN -> NB -> [M_BIASN1 (diode)] -> [BIAS_ENN] -> M_ENN -> 0
  M_ENP:  VIN -> EA_OUT, gate=EN   (forces pass gate off when EN=0)
  M_ENP2: VIN -> BIASP,  gate=EN   (forces bias/tail chain off when EN=0)
  M_ENP3: VIN -> CL_CMP, gate=EN   (defined off state for the limit comparator)
  C_COMP: EA_OUT <-> VOUT (Miller compensation)

  current limit (issue #22):
    VIN -> M_SENSE (gate=EA_OUT, W 1:5952 replica of M_PASS) -> CL_SNS
    CL_SNS -> M_CLN1 (diode) -> [AMP_ENN]
    CL_SNS --(gate)--> M_CLN2 (20:1.6 attenuating mirror) -> CL_CMP -> [AMP_ENN]
    VIN -> M_CLP (gate=BIASP, ~2uA reference) -> CL_CMP
    CL_CMP --(gate)--> M_CLIM : VIN -> EA_OUT   (pulls the pass gate off)
    C_CL: CL_CMP <-> VIN (comparator dominant pole)

  soft start (issue #22):
    EN -> [M_INVP/M_INVN inverter] -> ENB
    ENB --(gate)--> M_SSDIS : SS -> 0            (reset the ramp at EN=0)
    VIN -> M_SSCHG (gate=BIASP, ~1/80 of the bias unit) -> SS
    C_SS: SS -> 0                                 (current-starved linear ramp)
    SS --(gate)--> M_IN2S, in parallel with M_IN2 on the amplifier's "-" input
                   => effective reference = soft-min(VREF, SS)
```

All active devices are `sky130_fd_pr__pfet_g5v0d10v5` /
`sky130_fd_pr__nfet_g5v0d10v5` — the whole amplifier and bias chain, not just
the pass device. DR-001's Consequences section states why: *"the amplifier's
output stage cannot be core-flavor regardless, since the pass gate must
swing to VIN"* — and once the output stage must be 5V-flavor, mixing core
devices into the rest of the chain (framing (C), a deferred refinement) adds
a verification burden (proving every core-device terminal stays inside
1.8V at every corner including startup and a continuous output short) that
is explicitly out of scope until (C) gets its own topology decision record.
This schematic stays entirely on the 5V-gate family, matching (A) as
ratified.

### Node glossary

| Net | Role |
|---|---|
| `VIN` | 3.3V ±10% input (ipin) |
| `EN` | active-high enable, full-rail 0/VIN (ipin) |
| `VREF` | external reference input (ipin) — see "VREF interface caveat" |
| `VOUT` | 1.8V ±2% regulated output (opin) |
| `FB` | feedback-divider tap, drives the amplifier's "+" input |
| `EA_TAIL` | error-amp differential-pair tail node |
| `EA_D1` | mirror-diode-side drain (M_IN1/M_MIR1) |
| `EA_OUT` | amplifier output = pass-device gate |
| `NB`, `BIASP` | bias-generator reference nodes (NMOS-diode, PMOS-diode) |
| `BIAS_ENN`, `AMP_ENN` | EN-gated pseudo-ground returns (see "Enable/shutdown") |
| `N_FBB` | midpoint of the two-unit bottom leg of the feedback divider |
| `CL_SNS` | current-limit sense node — `M_SENSE`'s drain into the `M_CLN1` diode |
| `CL_CMP` | current-limit comparison node (high-impedance); `≈VIN` = inactive, falls when the limit engages |
| `ENB` | logical inverse of `EN`, from the `M_INVP`/`M_INVN` inverter |
| `SS` | soft-start ramp voltage on `C_SS`; drives `M_IN2S`'s gate |

### Error-amplifier polarity (load-bearing, verified by simulation)

The 5T OTA's "+" input (mirror-diode side, `M_IN1`'s gate, drain = `EA_D1`)
is **`FB`**, and the "−" input (output side, `M_IN2`'s gate, drain =
`EA_OUT`) is **`VREF`**. This is the polarity that makes `EA_OUT` rise when
`FB` rises, which is what turns `M_PASS` *off* as `VOUT` rises — negative
feedback. An earlier draft of this schematic had the two swapped; it
netlisted and "ran" without any xschem/ngspice error, but a quick OP check
(no external load, `VIN=3.3V`, `EN=3.3V`, `VREF=0.6V`) showed `VOUT` railing
to ~`VIN` instead of regulating, which traced back to the swapped input
assignment producing net **positive** feedback. This is exactly why the
schematic alone — even a syntactically clean one — is not itself a
verification claim: the fix (swap `M_IN1`/`M_IN2` gate labels) is in the
committed `.sch`, and the polarity is now confirmed correct by the OP checks
below, but a real corner-swept loop-gain/stability sim (#18/#19) is still
what would actually verify it.

### Enable/shutdown (also revised after simulation)

`EN` is active-high, full-rail (0V / VIN). Three PMOS clamps force the analog
core off when `EN=0`:

- `M_ENP2` (`VIN -> BIASP`, gate=`EN`) forces the bias-generator's PMOS
  diode/mirror node to `VIN`, killing `M_BIASP1`, `M_TAIL`, `M_CLP` and
  `M_SSCHG` in one move (every PMOS current source in the block is gated by
  `BIASP`).
- `M_ENP` (`VIN -> EA_OUT`, gate=`EN`) forces the pass-device gate to `VIN`,
  guaranteeing `M_PASS` is off independent of the (now unbiased)
  amplifier's own output.
- `M_ENP3` (`VIN -> CL_CMP`, gate=`EN`, added in #22) gives the current-limit
  comparator's high-impedance output a defined off state instead of leaving
  `M_CLIM`'s gate floating.

Getting a *clean* shutdown (no DC path from `VIN` to `GND` anywhere in the
core) took two more iterations, found by simulation, not by inspection:

1. **First pass** gated only `M_BIASN1`'s ground return (via `M_ENN`,
   inserted in series between `M_BIASN1`'s source and `0`). This left
   `M_BIASN2` — whose *gate* is `NB`, and whose *source* still went straight
   to `0` — ungated. With `M_BIASN1` cut off, `NB` floated up to `VIN`
   through `R_BIAS` (no current, no drop), which then drove `M_BIASN2` on
   *hard* (`Vgs=VIN`), creating a `VIN -> M_ENP2 -> BIASP -> M_BIASN2 -> GND`
   shoot-through of **~1.2mA** at `EN=0` in the OP check — worse than doing
   nothing. Fix: route `M_BIASN2`'s source through the same `M_ENN` switch
   (shared `BIAS_ENN` node), so both NMOS bias-diode branches cut together.
2. **Second pass**, after fixing (1), still showed **~440µA** flowing from
   `VIN` at `EN=0`. Cause: `M_ENP`'s pull-up on `EA_OUT` is driven with the
   full `Vsg=VIN` (since `EN=0` directly, not a threshold-limited clamp), so
   it is a strong, low-impedance pull-up — and the amplifier's own mirror
   load (`M_MIR1`/`M_MIR2`, tied straight to `0`) was never disabled, giving
   that pull-up current a ready path to ground through the still-alive
   `M_MIR1`/`M_MIR2`/diff-pair. Fix: add `M_ENN2`, gating `M_MIR1`/`M_MIR2`'s
   shared source return (`AMP_ENN`) the same way.

After both fixes, every NMOS branch in the amplifier/bias core is EN-gated
(`M_ENN` or `M_ENN2`), matching the EN-gated PMOS clamps. The OP check below
confirms the fix: in the #14 record `EN=0` measured **`ipass` ≈ 46pA**
(leakage-floor, screening-model only) versus the ~440µA–1.2mA shoot-through
of the earlier drafts.

Issue #22's additions were designed to slot into that discipline rather than
work around it: the current-limit comparator's two NMOS branches
(`M_CLN1`/`M_CLN2`) return through the same `AMP_ENN` switch, the soft-start
ramp source `M_SSCHG` is gated by `BIASP`, and the only genuinely new
ground-referenced devices are `M_INVN`/`M_SSDIS`, which are a static CMOS
inverter and the capacitor-reset switch it drives — neither of which has a
static path. Measured `EN=0` supply current after the additions is
**≈150pA** (table below), i.e. still the leakage floor.

### VREF interface caveat, and the reference common mode (revised in #22)

This block does not design a bandgap/reference generator — `VREF` is an
external port, standing in for a future reference-generator block (a
sibling canary, `2AMLogic/sky130-bandgap`, exists but is not consulted here
beyond CLAUDE.md's harness-bootstrap pattern; its actual reference voltage
is not reverse-engineered or assumed). The OP checks below use
**`VREF = 1.2V`** as an illustrative placeholder purely to exercise the loop.
**`VREF`'s real value is an open interface item for whichever future issue
adds a reference generator or a testbench-level ideal source.**

Issue #14's first draft used `VREF = 0.6V` with a 2:1 divider. Issue #22
raised it to `1.2V` with a 1:2 divider (same three unit resistors, same
`VOUT` target) for a circuit reason, not an arbitrary one:

> In a PMOS-input 5T OTA the output node `EA_OUT` is the drain of an input
> PMOS whose source is the tail node, so **`EA_OUT` cannot rise above
> `EA_TAIL`, and `EA_TAIL` settles at roughly `V_in,cm + V_sg(M_IN2)`** —
> i.e. the amplifier's output ceiling is pinned to the *reference* common
> mode, not to `VIN`. With `VREF = 0.6V` that ceiling is ≈2.3V, leaving
> `V_sg(M_PASS) ≥ 1.0V` at `VIN = 3.3V` — and a 2.5mm pass device at
> `V_sg = 1.0V` still delivers ~1.7mA, which is more than a 1mA load can
> absorb, so the loop rails instead of regulating. Raising the reference
> common mode to 1.2V raises the ceiling to ≈2.5V and cuts the minimum pass
> current by orders of magnitude.

Screening measurement of the difference, everything else identical
(`tt`/27°C, `VIN = 3.3V`, corrected 2.5mm pass device, ~1mA load):
`VREF = 0.6V` / 2:1 → `VOUT = 2.89V`; `VREF = 1.2V` / 1:2 → `VOUT = 1.817V`.
This does **not** fully close the ceiling problem — see "Known open item"
below — it moves it from "fails at 1mA" to "fails at 0mA, and at 1mA only at
`VIN_max`". 1.2V is also the more natural value for a future on-chip
reference (a silicon bandgap lands near 1.2V), but that is a convenience,
not the argument.

### Feedback divider — measured, not invented, unit-resistor value

Per `spec/target-spec.md`'s Output row ("divider as a unit-resistor
string"), `R_FB_A`/`R_FB_B`/`R_FB_C` are three identical `res_xhigh_po` unit
resistors (`W=0.42 L=180`), ratio 1:2 (one unit `VOUT->FB`, two units
`FB->GND`) so `VOUT = 1.5 x VREF`. The unit value was **measured**, not
assumed, via a quick op screening deck against the pinned PDK
(`sky130A`, open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b`, same pin as
`sim/pdk.json`; `tt` corner, 27°C; method: 1V across the resistor to ground,
`R = 1V / I`) — mirroring DR-001/DR-003's own screening-deck convention:

| Resistor | Geometry | Measured value (tt/27°C, screening only) |
|---|---|---|
| `res_xhigh_po` unit (`R_FB_A/B/C`) | `W=0.42 L=180` | **≈1.04MΩ** |
| `res_high_po` (`R_BIAS`) | `W=0.42 L=1500` | **≈1.22MΩ** |

Total divider resistance ≈3.12MΩ, so at `VOUT=1.8V` the divider itself draws
≈0.58µA — a small, deliberate contribution to the Iq budget, consistent with
the DRAFT spec's "0mA = no external load; feedback divider is the only
inherent preload" note. **These are screening numbers** (single corner,
single bias point, not a `sim/` evidentiary record) — real values need
re-confirming across the full PVT matrix once a testbench exists (#18/#19),
and are not cited as a verified/ratified spec value.

### Pass-device width correction (found in #22)

`M_PASS` is now `L=0.5` (bin floor), `W=100 nf=25 mult=25` → **`W_total` =
2500µm (~2.5mm)**, matching DR-003's sizing methodology output
(`W_total ≥ 14.81kΩ·µm / 6Ω ≈ 2.47mm` at the dropout bias point /
`{ss,sf}`@125°C co-binding corner — DR-003's own screening-derived number,
not re-derived here).

Issue #14's committed instance was `W=100 nf=25 mult=1`, written in the
belief that the sky130 xschem symbols treat `W` as a per-finger width, so
that `W_total = W × nf = 2500µm`. **They do not**: `W` is the *total* device
width and `nf` only splits it into fingers. A screening deck settles it
directly (`tt`/27°C, `V_sg = V_sd = 1.5V`):

| Instance | Measured `I_d` |
|---|---|
| `L=0.5 W=10 nf=1` | 162 µA |
| `L=0.5 W=10 nf=2` | 162 µA (identical — `nf` alone does not scale current) |
| `L=0.5 W=100 nf=25` | 1.60 mA (10×, i.e. `W_total` = 100µm, **not** 2500µm) |

So the committed pass device was **25× narrower than its own documented
intent**, and could not deliver the spec's 50mA load at all: at `VIN=3.3V`
with a 36Ω load it collapsed to `VOUT = 0.56V` / 15.6mA, and its
full-gate-drive short-circuit current was only 16mA. That makes the DRAFT
current-limit row ("never engages for `I_load ≤ 50mA`") untestable, which is
why the correction lands in this issue rather than being deferred: the
protection circuitry has nothing meaningful to protect otherwise.
`mult=25` (25 parallel groups of `W=100 nf=25`, i.e. 625 fingers of 4µm)
instantiates the intended 2500µm with a layout-plausible finger width;
`W=2500 nf=625 mult=1` measures identically (405mA vs 405mA at full drive
into a short) but implies 100µm fingers.

With the correction in place the device does what DR-003 sized it for:
98mA at the dropout bias point (`V_sd = 0.3V`, full gate drive, `tt`/27°C),
comfortably above the 50mA row.

### Amplifier sizing revision (#22)

The corrected pass device is 25× wider, so the amplifier has to throttle it
over a 25× larger dynamic range. Issue #14's device lengths (`M_TAIL` `L=1`,
`M_IN1`/`M_IN2` `L=1`, `M_MIR1`/`M_MIR2` `L=0.5`) did not have the output
resistance for that — at `L=0.5` the mirror's channel-length modulation was
large enough that `M_MIR2` sank 2.3× its mirrored input current at high
`EA_OUT`, collapsing the loop gain. This schematic lengthens all three:
`M_TAIL` `L=2`, `M_IN1`/`M_IN2` `L=2`, `M_MIR1`/`M_MIR2` `L=4`, widths
unchanged. Screening effect (`tt`/27°C, `VIN=3.3V`, corrected pass device,
`VREF=1.2V`): load regulation across 0→50mA improves from ~9mV to **≤0.45mV
(0.025%)**, and the static error at 50mA from +0.5% to +0.4%. These are still
**illustrative sizings**, not calibrated against an Iq budget — DR-003
explicitly declines to set one, and none exists yet.

The bias generator (`R_BIAS`, `M_BIASN1`, `M_BIASN2`, `M_BIASP1`) is
unchanged from #14 and remains a functional starting point rather than a
budgeted design. Once an Iq budget decision record exists, the bias currents
here can be re-derived against it rather than the other way around.

### Compensation

`C_COMP` (Miller compensation, `EA_OUT -> VOUT`, value `2p`) and `C_CL`
(current-limit comparator dominant pole, `CL_CMP -> VIN`, value `1p`) are
both **placeholders**, not sized against a loop-gain simulation. DR-002 (the
C_out/ESR window) is `proposed`, not ratified, and explicitly sequences
itself *after* a topology exists to simulate against — this schematic is
that topology, but the loop-gain sim itself is out of scope here (#18/#19).
What *was* screened, and is reported below, is that the main loop settles
without ringing and the limit loop settles flat into a hard short across the
DR-002 C_out window at `tt`/27°C. That is a smoke test, not a phase-margin
claim.

### Current limit (#22)

Spec row: *"constant-current (brickwall) clamp, window TBD over PVT; never
engages for `I_load ≤ 50mA`; survives continuous `Vout = 0` short at
`Vin_max`."*

The implementation is a **sense-FET current comparator driving a gate
clamp** — a second feedback loop that is completely inactive in normal
operation and takes over `EA_OUT` when the pass current exceeds a threshold:

1. **Sense.** `M_SENSE` is a replica of `M_PASS` — same `L=0.5`, same gate
   (`EA_OUT`), same source (`VIN`) — at minimum width, giving a nominal
   0.42µm : 2500µm = **1:5952** current ratio. A sense FET rather than a
   series sense resistor because nothing may be inserted in the main current
   path: a 1Ω sense resistor would spend 50mV of the 300mV DRAFT dropout
   budget at 50mA.
2. **Attenuate and compare.** The sense current lands in the diode-connected
   `M_CLN1` and is mirrored down 20:1.6 (≈12.5:1) by `M_CLN2` into the
   high-impedance node `CL_CMP`, where it is opposed by `M_CLP`, a 1× copy of
   the `M_BIASP1` PMOS bias unit (~2µA). The attenuation is deliberate: the
   *reference* branch is always-on quiescent current, so it must stay at the
   bias level rather than scale with the trip current.
3. **Clamp.** While the attenuated sense current is below the reference,
   `CL_CMP` sits at `VIN` and `M_CLIM` is off. Above it, `CL_CMP` falls,
   `M_CLIM` turns on and pulls the pass gate toward `VIN`. Because this is a
   continuous loop rather than a latch, the result is a constant-current
   (brickwall) characteristic, which is what the spec row asks for — not a
   hiccup or a latching shutdown.

`M_CLN1`/`M_CLN2` return through the existing `AMP_ENN` switch and `M_CLP`'s
gate is `BIASP`, so the whole comparator dies at `EN=0` with no new
shutdown-current path; `M_ENP3` additionally forces `CL_CMP` to `VIN` at
`EN=0` so `M_CLIM`'s gate has a defined off state instead of floating.

**Known accuracy caveat.** `M_SENSE`'s drain sits at `V_gs(M_CLN1)` ≈ 0.9V,
not at `VOUT`, so the replica only tracks accurately while both devices are
saturated. That is true in the limit condition itself (where `VOUT` has
collapsed) and is why the measured characteristic below is as flat as it is,
but it does mean the ratio is *not* trimmed or `V_ds`-matched — and a
0.42µm-wide device matched against a 2500µm one has substantial random
`V_th` mismatch. The spec row says "window TBD over PVT" precisely because
this kind of limit is a window, not a number; establishing that window is
#19's job, not this record's.

**Iq interaction, stated rather than hidden.** The sense branch carries
`I_load / 5952`, so it adds ~8µA at the 50mA load point — about a quarter of
the DRAFT `Iq < 30µA at no load and full load` row, and the dominant term in
the measured full-load Iq below. It is ~0 at no load. Whether that is an
acceptable use of the Iq budget is a question for the (still nonexistent) Iq
budget decision record; the alternative levers are a narrower sense device
(0.42µm is already the width floor), a larger pass device, or a series sense
resistor paid for out of the dropout budget instead.

### Soft start (#22)

Spec row: *"monotonic into any load 0–50mA and any `C_out` in the stability
window; controlled ramp; inside ±2% within a few ms of enable; overshoot
≤ +2%."* Issue #14's enable was a hard on/off with no ramp control.

The implementation is a **current-starved ramp feeding a min-select input**:

- `M_INVP`/`M_INVN` invert `EN` to `ENB`. `ENB` drives `M_SSDIS`, which holds
  `SS` at 0 whenever the block is disabled, so every enable edge starts the
  ramp from zero rather than from leftover charge.
- `M_SSCHG` is a heavily scaled-down copy of the `M_BIASP1` bias unit
  (`W/L = 1/8` against `10/1`, so of order 1/80 of the bias current — tens of
  nA) charging `C_SS = 10p`. Charging from a *current source* rather than
  through a resistor is what makes `SS` a straight line; an RC ramp of the
  same duration would need a ~10MΩ/100pF combination, which is not affordable
  against the 0.1mm² DRAFT area row. `M_SSCHG`'s gate is `BIASP`, so the ramp
  cannot start before the bias generator is alive and stops for free at
  `EN=0`.
- `M_IN2S` is a replica of `M_IN2` (same `L`, `W`, `nf`) wired in parallel
  with it on the amplifier's "−" input — same source (`EA_TAIL`), same drain
  (`EA_OUT`) — but gated by `SS`. In a PMOS input pair the device with the
  *lower* gate dominates, so the "−" side behaves as the soft minimum of
  `VREF` and `SS`: the loop servos `FB` to `SS` while `SS < VREF` (so `VOUT`
  ramps as `1.5 × SS`) and hands over to `VREF` once `SS` passes it. There is
  no comparator, no switch, and no discontinuity for the output to overshoot
  through, and once `SS` has charged toward `VIN` the device is fully off and
  the amplifier is exactly the #14 5T OTA again.

This interacts cleanly with the two-iteration `EN` gating #14 arrived at: the
new devices add no ungated NMOS branch (`M_INVN`/`M_SSDIS` are driven by a
CMOS inverter with no static current, `M_IN2S`'s only ground path is the
already-gated `AMP_ENN`), and the measured shutdown current below is
unchanged at the leakage floor.

The ramp is deliberately fast relative to the spec row: 10–90% in ~290µs, so
"inside ±2% within a few ms of enable" is met with a large margin while the
inrush into the DR-002 `C_out` window stays well below the current limit. The
spec row bounds the *settling time*, it does not require a slow ramp.

## Screening checks (screening only — not `sim/` evidence)

Everything below was run against the pinned PDK (`sky130A`, open_pdks
`c6d73a35f524070e85faff4a6a9eef49553ebc2b`, same pin as `sim/pdk.json`), `tt`
corner, 27°C, `VREF = 1.2V` (placeholder, see above), **from the committed
schematic's own xschem-generated netlist** (`xschem -n … -o /tmp/… ; .include`
that `.spice` file into a throwaway deck). Nothing here is committed under
`sim/`: these issues are design sources only, and a real corner-swept
`load-transient` / `dropout-vs-load` / loop-gain testbench is #18's job with
the full PVT/Monte-Carlo matrix being #19's. Single process corner, single
temperature — **not** a spec-row-proving result.

### 1. DC operating grid — `VOUT` (target `1.5 × VREF` = 1.800V)

| `VIN` | 0mA (divider only) | 1mA (`1.8kΩ`) | 50mA (`36Ω`) |
|---|---|---|---|
| 2.97V | 1.859V (+3.3%) | 1.811V (+0.6%) | 1.804V (+0.2%) |
| 3.30V | **2.244V (+24.7%)** | 1.817V (+1.0%) | 1.808V (+0.4%) |
| 3.63V | **2.696V (+49.8%)** | **2.046V (+13.6%)** | 1.812V (+0.6%) |

Bold = outside the DRAFT ±2% Output row; see "Known open item" below.
Against the other DRAFT rows, honestly scored:

- **Load regulation** over 1→50mA is 6.7mV at `VIN=2.97V` and 9.4mV at
  `VIN=3.3V` — 0.37% and 0.52%, inside the DRAFT `<1%` row. Over the row's
  actual **0**→50mA range it is 55mV (3.0%) even at `VIN=2.97V`, i.e. **not**
  met, and the whole miss is the 0mA point.
- **Line regulation** at 50mA is (1.812−1.804)/0.66V ≈ **11mV/V**, outside
  the DRAFT `<5mV/V` row.

Both misses trace to the same ceiling mechanism as the 0mA failures, and both
are reported rather than waved away. For contrast, issue #14's committed
schematic measured 1.977V at ~1mA (+9.9%) and could not reach 50mA at all,
so every column here is an improvement — but "improved" is not "meets the
row", and no row is claimed as met.

### 2. Quiescent and shutdown current

| `VIN` | Iq @ 0mA | Iq @ 1mA | Iq @ 50mA | shutdown (`EN=0`, `1.8kΩ`) |
|---|---|---|---|---|
| 2.97V | 5.55µA | 6.17µA | 18.0µA | **0.134nA** |
| 3.30V | 6.45µA | 6.95µA | 18.6µA | — |
| 3.63V | 7.38µA | 7.89µA | 19.3µA | **0.167nA** |

Iq = total `VIN` current minus load current. All points are inside the DRAFT
`Iq < 30µA at no load and full load` row, and shutdown is five orders of
magnitude inside the DRAFT `< 3µA` row. The 0mA→50mA Iq growth is almost
entirely the current-limit sense branch (`I_load / 5952` ≈ 8µA at 50mA) —
see "Iq interaction" above. The #14 record's `EN=0` figure was ≈46pA; the
protection additions move it to ≈150pA, still the leakage floor.

### 3. Current limit

DC characteristic, `VOUT` forced by a source, `EN` high:

| `VIN` | `I_lim` @ `VOUT = 0` (dead short) | `I_lim` @ `VOUT = 1.75V` | short-circuit dissipation |
|---|---|---|---|
| 2.97V | 138.6mA | 112.4mA | 412mW |
| 3.30V | 161.0mA | 134.5mA | 531mW |
| 3.63V | **185.4mA** | 156.4mA | **673mW** |

- **Brickwall shape.** The limit varies only ~19% from `VOUT = 0` to
  `VOUT = 1.75V` at a given `VIN`, i.e. it is a constant-current clamp rather
  than a foldback, which is what the spec row asks for. It does rise with
  `VIN` (the reference current is `R_BIAS`-derived and therefore
  supply-dependent); making it supply-independent needs a real reference, not
  this bias generator.
- **Never engages at 50mA.** The lowest limit anywhere in the grid is
  112.4mA at `VIN_min` — **2.25× the 50mA spec load**. At the 50mA operating
  point `CL_CMP` is still within 33mV of `VIN` and `M_CLIM` conducts ~0.04pA,
  so the limit is not partially engaged either. Whether 2.25× survives
  process, temperature and the sense-FET mismatch is a #19 question; that
  margin is why the trip was set where it was rather than tighter.
- **Survives a continuous short.** Transient into a hard short (`1mΩ`) at
  `VIN = 3.63V` from a cold enable: settles at **185.5mA** with **1.4µA
  peak-to-peak** ripple on the supply current and 1.4nV on `VOUT` over
  0.6–1ms — flat, i.e. the limit loop does not oscillate in this screen.
- **Dissipation, stated not dodged.** 673mW at `VIN_max` into a dead short.
  The Thermal spec row sets no absolute figure ("θJA delegated to
  package/integration") but does say `Tj ≤ 125°C`; holding that at a 25°C
  ambient with this limit implies **θJA ≤ 149°C/W**. That is a real
  integration constraint, and it is the strongest argument for the thermal
  shutdown that this issue decomposed out (see below).

### 4. Soft start

Enable step at t = 100µs, `VIN = 2.97V` (the `VIN` where the loop regulates
at every load, so the ramp is not confounded by the ceiling gap),
`C_out = 1µF` (DR-002's nominal). "Overshoot" is peak `VOUT` above the value
at 1.9ms.

| Load | | 10–90% rise | overshoot | peak `I_VIN` |
|---|---|---|---|---|
| 0mA | **with soft start** | 292µs | **+0.013%** | 51.1mA |
| | without (`M_IN2S`/`C_SS`/`M_SSCHG`/`M_SSDIS` removed) | 12µs | did not settle within 2ms — parked at 2.043V | 178.1mA |
| 1mA | **with soft start** | 293µs | **+0.002%** | 51.1mA |
| | without | 11µs | **+12.7%** | 178.9mA |
| 50mA | **with soft start** | 294µs | **0.000%** | 51.1mA |
| | without | 14µs | **+5.6%** | 179.1mA |

The 0mA row without soft start is the worst case and the least obvious one:
the spec's Enable/shutdown row forbids active discharge, so an enable
overshoot at no load has only the ~3.1MΩ feedback divider to bleed it off
(τ ≈ 3s). The block would sit above target for seconds. With soft start it
never gets there.

Across the whole DR-002 `C_out` window at `VIN = 2.97V` (`C_out` ∈ {0.33µF,
1µF, 4.7µF} × load ∈ {0, 1mA, 50mA}, nine combinations): 10–90% rise
293–295µs, overshoot ≤ +0.02%, peak supply current 46–67mA — monotonic in
every case, and the ramp duration is essentially independent of `C_out` and
load, which is the point of ramping the *reference* rather than relying on
the output pole. At `VIN = 3.63V` the same is true at 50mA (10–90%
229–234µs, overshoot ≤ 0.03%), but at 0/1mA the ramp is bypassed — see the
open item below, and note that this is the ceiling gap asserting itself, not
a soft-start failure: the loop cannot hold `VOUT` down at those points with
or without a ramp.

### Known open item: light-load regulation, now diagnosed

`M_PASS` is sized for 50mA (`W_total ≈ 2.5mm`), so at 0mA it must be
throttled deep into sub-threshold. Issue #14 flagged that this failed at 0mA
and narrowed it to "a gain/sizing question". **This issue identifies the
mechanism, and it is a hard topology ceiling rather than a gain shortfall:**

> `EA_OUT` is the drain of the PMOS input device `M_IN2`, whose source is
> `EA_TAIL`. `EA_OUT` therefore cannot rise above `EA_TAIL`, and `EA_TAIL`
> settles near `V_in,cm + V_sg(M_IN2)` ≈ 2.4–2.5V regardless of `VIN`. The
> minimum achievable `V_sg(M_PASS)` is thus `VIN − 2.5V`, which *grows* with
> `VIN`: ≈0.5V at `VIN_min` (pass device essentially off, 0mA regulates to
> +3.3%), ≈1.1V at `VIN_max` (a 2.5mm device at `V_sg = 1.1V` still delivers
> more than a 1mA load can absorb, so the loop rails).

The screening OP data above is exactly this pattern: the failures are at low
load *and high `VIN`*, and the failure gets monotonically worse as `VIN`
rises. Adding gain does not fix it — the amplifier is already saturated
against its own ceiling at those points, as `EA_OUT ≈ EA_TAIL` to within
20mV confirms. **The fix is an amplifier output stage that can actually
swing to `VIN`.**

A candidate fix was built and screened during this issue and is **not**
committed, because it trades one failure for a worse one — recording it here
so the follow-on issue starts from data rather than from scratch:

> Adding a PMOS common-source second stage (`M_G2`: `VIN → EA_OUT`,
> `gate = EA1`, `L=4 W=1`; NMOS current-sink load `M_L2` from `NB`; stage-1
> inputs swapped so the polarity works through the extra inversion; the
> soft-start min-select moved to the mirror-diode side) gives **1.789–1.795V
> at all nine `VIN` × load points including 0mA**, load regulation 0.03%,
> line regulation 8.4mV/V — i.e. it closes this open item outright. It also
> needs two more devices to keep shutdown clean (`NB` must be pulled low and
> `R_BIAS` disconnected at `EN=0`, otherwise `M_L2` stays on and leaks ~18µA
> back through the mirror). **But with the placeholder `C_COMP = 2p` it
> oscillates**: 351mV peak-to-peak on `VOUT`, 135mA pp on the supply, at
> `C_out = 0.33µF` / 50mA / `VIN = 3.63V` — the low-`C_eff` corner DR-002
> itself flags as the risky one. `C_COMP = 10p` and `30p`, a Miller cap
> around stage 2, a lower-gain stage-1, and a higher stage-2 bias current
> were each screened and none of them fixed it. The committed single-stage
> loop is stable at that same corner (0.77µV pp).

So the honest state is: **the committed schematic is a stable regulator with
a light-load/high-`VIN` regulation gap, and the known cure for that gap has
to be co-designed with compensation** (DR-002 + a loop-gain testbench),
which is more than a sizing tweak. Flagged as a follow-on rather than
shipped half-done.

## Known gaps / follow-on scope

Closed by issue #22 and now in this schematic: **current limit** and
**soft-start** (both spec rows above), plus the pass-device width correction
and the reference-common-mode change those two required.

Still deliberately **not** in this schematic:

- **Thermal shutdown.** Decomposed to its own follow-on issue, which issue
  #22's acceptance criteria explicitly allow ("thermal shutdown may be
  decomposed further if it proves independently sizable"). The reason it is
  not designed here is not effort but a missing input: **`spec/target-spec.md`
  states no trip temperature.** The Thermal row gives a dissipation framing
  and `Tj ≤ 125°C` with "θJA delegated to package/integration", so there is
  no spec number for a trip circuit to be designed against, and inventing one
  would violate CLAUDE.md's spec-is-a-gate rule. Compounding that, a trip
  point needs something temperature-stable to compare a CTAT sense against,
  and this block has none — `VREF` is an external port whose tempco is
  explicitly undefined (see "VREF interface caveat"). A trip designed against
  it would be un-anchored. The follow-on therefore needs a spec/decision-record
  answer first (trip temperature + hysteresis, and what reference it is
  measured against), and probably depends on the reference-generator gap
  below. When it is built, the clean insertion point is the existing shutdown
  path — `M_ENP`/`M_ENP2`/`M_ENP3`/`M_ENN`/`M_ENN2` plus the `ENB` inverter
  this issue added — rather than a parallel shutdown mechanism. The
  measured 673mW worst-case short-circuit dissipation above (θJA ≤ 149°C/W
  implied) is the concrete motivation.
- **Error-amplifier output swing / light-load regulation.** See "Known open
  item" above: diagnosed precisely, with a screened candidate fix that closes
  the DC gap but oscillates under the placeholder compensation, so it has to
  be co-designed with DR-002 and a loop-gain testbench. Filed as its own
  follow-on.
- **Loop compensation.** `C_COMP` and `C_CL` remain placeholders; DR-002 is
  `proposed`, not ratified, and the loop-gain/phase-margin work is #18/#19.
- **An actual on-chip voltage reference.** `VREF` is an external port (see
  "VREF interface caveat" above).

These are real, trackable gaps, not silently dropped requirements.

## Validating this schematic

```bash
source sim/bin/pdk-env.sh
xschem --rcfile "$XSCHEM_RCFILE" design/ldo_3v3in_1v8out.sch   # interactive open

# headless netlist check (same invocation the sim harness uses):
xschem -n -q -x -s -o /tmp/ldo_out --rcfile sim/xschemrc design/ldo_3v3in_1v8out.sch
grep -c MISSING /tmp/ldo_out/ldo_3v3in_1v8out.spice   # expect 0
```

Netlists cleanly (0 `MISSING` warnings) against the pinned PDK as of this
commit. Connectivity is entirely by net label (`lab_pin`/`ipin`/`opin` on
every device pin), no drawn wires — the same convention as
`sim/pdk-smoke/testbench/tb_pdk_smoke.sch`.

To reproduce any screening number in this record, netlist as above and then
`.include` the generated `.spice` into a throwaway deck (it is emitted with
its `.subckt` line commented out, so its elements land at the top level with
`VIN` / `EN` / `VREF` / `VOUT` as ordinary nets) alongside
`.lib $SKY130_MODEL_LIB tt`, a `VIN` source, an `EN` source, a `VREF` source
and a load. Copy `sim/spiceinit` to `.spiceinit` in the working directory
first. Screening decks are intentionally not committed — they are not `sim/`
evidence.

## `ldo_3v3in_1v8out.sym` — companion subcircuit symbol (added for #18)

`ldo_3v3in_1v8out.sym`, alongside the schematic, is a mechanically-generated
companion artifact, not a redesign of the circuit above — it carries no
device content of its own. It exists so `sim/`'s testbenches (issue #18:
`load-transient`, `psrr-dc`, `dropout-vs-load`) can instantiate this
schematic hierarchically as a subcircuit (`xschem`'s standard pattern for a
DUT-under-testbench, already anticipated by `sim/xschemrc`'s "so this
project's own cells resolve by their repo-relative name" comment). xschem
resolves a subcircuit symbol's schematic body by co-locating the `.sym` next
to the `.sch` it names — a symbol filed anywhere else (e.g. under `sim/`)
silently netlists to an **empty** subcircuit with no warning, which is why
this file lives here rather than alongside the testbenches that use it.

Regenerate it (deterministic — byte-identical given the same schematic) with:

```bash
awk -f "$(brew --prefix xschem 2>/dev/null || echo /usr/local)/share/xschem/make_sym.awk" \
  150 design/ldo_3v3in_1v8out.sch
```

or interactively via xschem's own `make_symbol` (bound to the "K" key), which
runs the same `make_sym.awk` under the hood. The pin list (`VOUT`, `VREF`,
`EN`, `VIN`) is auto-extracted from the schematic's `opin`/`ipin` instances —
if a future revision of the schematic adds, removes, or renames a top-level
port, regenerate this file to match.
