# `design/` — sky130-ldo core regulation loop + protection

Schematic source for issue #14 (item 1 of the T1/bronze re-read, #12/#13),
issue #22 (protection/sequencing) and issue #25 (error-amplifier output
stage + compensation): `ldo_3v3in_1v8out.sch`, a clean-room, forward-designed
xschem schematic for the sky130 LDO's core regulation loop (error amplifier +
pass device + feedback divider + compensation + enable/shutdown) plus the
current-limit and soft-start circuitry. This is genuinely original
circuit-topology work — a textbook single-stage-OTA LDO architecture (a
current-mirror/"symmetric" OTA driving a common-source pass device with
Miller-plus-nulling-resistor compensation, e.g. Razavi *Design of Analog CMOS
Integrated Circuits* ch. 5 & 11), a sense-FET current comparator, and a
min-select soft-start input — sized against this repo's own PDK screening
data and (for the compensation) against `sim/loop-gain`, not derived from,
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
  (block testbenches: `load-transient`, `psrr-dc`, `dropout-vs-load`), #25
  (`loop-gain`, the one testbench this record's compensation was actually
  sized against) and #19 (full PVT/Monte Carlo). Except where a section names
  a `sim/` record explicitly, the OP checks described below are **screening
  sanity checks**, run the same way DR-001/DR-003's own appendices do
  (single process corner, single temperature, not committed as evidence) —
  they exist so this record's design claims cite something checkable rather
  than asserting circuit behaviour from memory, not to satisfy "verification
  is the product."

## Freshness

Originally written against `spec/target-spec.md` and
`spec/decision-records/{DR-001,DR-002,DR-003,DR-004}` as of commit `7de8d4b`
(2026-08-17) for issue #14; re-verified against the same spec and
decision-record set as of commit `0e12b14` (2026-08-17), the tip of `main` at
the start of issue #22** — no spec file or decision record changed between
those two commits, so every citation below is still current. **Re-verified a
third time against `e500d71` (2026-08-17), the tip of `main` at the start of
issue #25**: `DR-005-thermal-shutdown-trip.md` landed in between (it does not
change any row this record cites), and issue #25 itself appends to DR-002
rather than editing it, per the append-only decision-record rule.
`spec/target-spec.md` is entirely DRAFT pending #1; DR-001 is the only
**ratified** record among the five (framing only, no numeric row);
DR-002/003/004/005 are `proposed`. This schematic designs against the DRAFT
numbers and the `proposed` sizing methodology, per those issues' own
instruction not to block on #1. **Issue #29** additionally designs against
`spec/decision-records/DR-005-thermal-shutdown-trip.md` (also `proposed`,
tip of `main` at commit `e500d71`, 2026-08-17) — the thermal-shutdown trip
temperature, hysteresis, reference, and auto-restart decision.

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
            [AMP_ENN]         EA_D1       EA_D2 <-------+
              ^                 |           |
           M_ENN2            M_MIR1      M_MIR3 (diode) --(gate)--> M_MIR4
              |              (diode)       |                           |
              0              [AMP_ENN]  [AMP_ENN]                      PB
                                 |                                     ^
                              M_MIR2 (mirror out)          M_MIRP1 (PMOS diode, source=VIN)
                                 |                                     |
                              EA_OUT <----- M_MIRP2 (source=VIN) <------+
                                 |
                                 +--(gate)--> M_PASS --> VOUT
                                                           |
                                                         R_FB_A
                                                           |
                                                           FB --> M_IN1.gate
                                                           |
                                                         R_FB_B
                                                           |
                                                         N_FBB
                                                           |
                                                         R_FB_C
                                                           |
                                                           0

  EA_OUT is a push/pull node between M_MIRP2 (pull-up, source = VIN) and
  M_MIR2 (pull-down), so it can be driven all the way to VIN -- see
  "Error-amplifier output stage (rebuilt in #25)". M_ENP5 forces PB -> VIN
  at EN=0 so the new pull-up has a defined off state.

  R_BIAS: VIN -> NB -> [M_BIASN1 (diode)] -> [BIAS_ENN] -> M_ENN -> 0
  M_ENP:  VIN -> EA_OUT, gate=EN   (forces pass gate off when EN=0)
  M_ENP2: VIN -> BIASP,  gate=EN   (forces bias/tail chain off when EN=0)
  M_ENP3: VIN -> CL_CMP, gate=EN   (defined off state for the limit comparator)
  C_COMP + R_CZ: VOUT <-> EA_CZ <-> EA_OUT (Miller compensation with a
                 nulling resistor; sized in #25 against sim/loop-gain)

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

  thermal shutdown (issue #29, DR-005):
    VIN -> M_TSPS (gate=BIASP) -> TS_SNS -> [M_TSD1 (diode)] -> TS_MID
                                          -> [M_TSD2 (diode)] -> [AMP_ENN]  (CTAT sense stack)
    VIN -> M_TSPR (gate=BIASP) -> TS_REF -> [M_TSR1 (diode)] -> [AMP_ENN]  (CTAT reference)
    TS_SNS --(gate)--> M_TCN1 -+
    TS_REF --(gate)--> M_TCN2 -+--> TC_TAIL -> M_TCTAIL (gate=NB) -> [AMP_ENN]
    M_TCP1 (diode) / M_TCP2 (mirror) -> TS_CMP           (comparator load)
    TS_CMP --(gate)--> M_TSHUT : VIN -> EA_OUT            (pulls pass gate off)
    TS_CMP --(gate)--> M_TSHYS : M_TSHYSB's current -> TS_REF  (hysteresis, tripped only)
    M_ENP4: VIN -> TS_CMP, gate=EN        (defined off state, same role as M_ENP3)
    C_TS: TS_CMP <-> VIN                  (comparator dominant pole)
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
| `EA_D1` | FB-side input-pair drain, into the `M_MIR1` diode |
| `EA_D2` | VREF-side input-pair drain, into the `M_MIR3` diode (added in #25) |
| `PB` | PMOS-mirror turnaround node, `M_MIR4` drain into the `M_MIRP1` diode (added in #25) |
| `EA_OUT` | amplifier output = pass-device gate |
| `EA_CZ` | compensation-network mid node, between `C_COMP` and `R_CZ` (added in #25) |
| `NB`, `BIASP` | bias-generator reference nodes (NMOS-diode, PMOS-diode) |
| `BIAS_ENN`, `AMP_ENN` | EN-gated pseudo-ground returns (see "Enable/shutdown") |
| `N_FBB` | midpoint of the two-unit bottom leg of the feedback divider |
| `CL_SNS` | current-limit sense node — `M_SENSE`'s drain into the `M_CLN1` diode |
| `CL_CMP` | current-limit comparison node (high-impedance); `≈VIN` = inactive, falls when the limit engages |
| `ENB` | logical inverse of `EN`, from the `M_INVP`/`M_INVN` inverter |
| `SS` | soft-start ramp voltage on `C_SS`; drives `M_IN2S`'s gate |
| `TS_SNS`, `TS_MID` | thermal CTAT sense-stack nodes (`M_TSD1`/`M_TSD2`) |
| `TS_REF` | thermal CTAT reference node (`M_TSR1`), also the hysteresis injection point |
| `TC_D1`, `TC_TAIL` | thermal trip comparator's mirror-diode and tail nodes |
| `TS_CMP` | thermal-trip comparison node (high-impedance); `≈VIN` = not tripped, falls when the trip engages |
| `TS_HYS` | hysteresis current-source node (`M_TSHYSB` -> `M_TSHYS`) |

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
below, and issue #25's `sim/loop-gain` record is now a real corner-swept
loop-gain measurement of it, the polarity is confirmed by measurement rather
than by derivation alone.

### Error-amplifier output stage (rebuilt in #25)

Issue #14 and issue #22 used a **five-transistor OTA**: the tail `M_TAIL`,
the input pair `M_IN1`/`M_IN2`, and the NMOS mirror `M_MIR1`/`M_MIR2`. Its
output node — the pass gate — was the *drain of the PMOS input device
`M_IN2`*, whose source is `EA_TAIL`. That is a hard ceiling:

> `EA_OUT` cannot rise above `EA_TAIL`, and `EA_TAIL` settles near
> `V_in,cm + V_sg(M_IN2)` ≈ 2.4–2.5 V **regardless of `VIN`**. The minimum
> achievable `V_sg(M_PASS)` is therefore `VIN − 2.5 V`, which *grows* with
> `VIN` — ≈0.5 V at `VIN_min`, ≈1.1 V at `VIN_max`. A 2.5 mm pass device at
> `V_sg = 1.1 V` still sources far more than a 1 mA load can absorb, so the
> loop rails instead of regulating.

That is a topology problem, not a gain problem — more gain cannot help an
amplifier that is already saturated against its own supply ceiling. Issue #25
removes the ceiling by promoting the stage to a **current-mirror (a.k.a.
"symmetric") OTA**, which is the standard textbook way to give a
PMOS-input OTA a rail-to-rail output (Razavi ch. 9's mirrored-OTA family; the
naming is textbook vocabulary, not a reference to anyone's implementation):

| Device | Role |
|---|---|
| `M_MIR3` | NMOS diode on the VREF-side drain `EA_D2` — the twin of `M_MIR1` on the FB side, same `L=4 W=10 nf=2`, so both input-pair branches see identical loads |
| `M_MIR4` | 1:1 NMOS mirror of `M_MIR3`, sinking that branch current out of `M_MIRP1` at `PB` |
| `M_MIRP1` | diode-connected PMOS reference of the output pull-up mirror, source = `VIN` |
| `M_MIRP2` | 1:1 PMOS mirror output — **the device that removes the ceiling**. Source = `VIN`, drain = `EA_OUT` |
| `M_ENP5` | `VIN → PB`, gate = `EN`: forces the new pull-up hard off at `EN=0` (see "Enable/shutdown") |

`EA_OUT` is now a push/pull node between `M_MIRP2` (pull-up from `VIN`) and
`M_MIR2` (pull-down), i.e. two 1:1-mirrored copies of the two input-pair
drain currents, and it can be driven into triode against `VIN`. The screening
grid below shows exactly that: at `VIN = 3.63 V` / 0 mA, `EA_OUT` now sits at
**3.072 V** — 0.44 V *above* the old `EA_TAIL` ceiling — and `VOUT` regulates.

Two properties of this choice are load-bearing and worth stating explicitly:

- **It is still a single gain stage.** Both new turnaround nodes (`EA_D2`,
  `PB`) are diode-loaded and therefore low-impedance, so their poles sit
  decades above crossover and the loop keeps the two-pole (`EA_OUT`, `VOUT`)
  shape Miller compensation is designed for. This is the difference from the
  PMOS-common-source **second gain stage** that was built and screened during
  issue #22 and rejected: that candidate closed the same DC gap but added a
  third low-frequency pole and produced a 351 mV pp limit cycle at
  `C_out = 0.33 µF` / 50 mA / `VIN = 3.63 V`. The measured transient at that
  same corner for *this* topology is **3.8 mV pp** after a 10 mA load step
  (screening; and `sim/loop-gain` measures 55.6–64.5° of phase margin there
  across the quick-subset corners).
- **It costs one clamp, not two.** The rejected candidate needed two extra
  devices to restore shutdown leakage (`NB` pulled low and `R_BIAS`
  disconnected). Here `M_MIR3`/`M_MIR4` return through the *existing*
  `AMP_ENN` switch, so the only new shutdown device is `M_ENP5` on `PB`, and
  measured `EN=0` supply current stays at the ~150 pA leakage floor (table
  below).

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
This did **not** fully close the ceiling problem — it moved it from "fails at
1mA" to "fails at 0mA, and at 1mA only at `VIN_max`". 1.2V is also the more
natural value for a future on-chip reference (a silicon bandgap lands near
1.2V), but that is a convenience, not the argument.

**Superseded as a stability argument by #25.** The blockquote above describes
the *five-transistor* amplifier. Issue #25 removed the ceiling at its source
(see "Error-amplifier output stage (rebuilt in #25)"), so the reference
common mode no longer sets the pass gate's reachable range and `VREF = 1.2 V`
is now purely an interface placeholder plus a divider-ratio choice. The
open interface question — what `VREF`'s real value and tempco are — is
unchanged and still belongs to whichever future issue adds a reference
generator.

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

### Compensation (sized in #25)

`C_COMP` (**150 pF**) in series with `R_CZ` (`res_xhigh_po` `W=0.42 L=52`,
≈300 kΩ) from `VOUT` to `EA_OUT` is Miller compensation with a nulling
resistor. Unlike the `2p` placeholder it replaces, it was sized against a
real AC loop-gain measurement — `sim/loop-gain`, added by this issue, which
walks DR-002's *proposed* `C_out`/ESR window (seven points: `C_eff` ∈
{0.33 µF, 4.7 µF} × load ∈ {0, 1, 50 mA}, plus the 500 mΩ ESR ceiling) inside
one deck at every PVT corner the runner sweeps. `C_CL` (`1p`) is untouched
and remains the current-limit comparator's placeholder dominant pole.

**Why the compensation looks the way it does.** Under Miller compensation
the loop's unity-gain frequency is `Gm/(2π·C_COMP)`, and it has to stay below
the *pass stage's own* pole `gm_pass/(2π·C_out)`. That second pole is the
binding constraint and it moves with load: ≈72 kHz at 50 mA/0.33 µF but only
≈900 Hz at 1 mA/4.7 µF, because `gm_pass` in weak inversion is `I_load/(nV_T)`
and is therefore proportional to the load current. Two consequences fall out
of that, and both are why the answer is not a small cap:

1. **`C_COMP` has to be large.** The crossover has to be pushed down to the
   low-hundreds-of-Hz/low-kHz range to sit under that pole at the light-load
   end. As a MIM (`cap_mim_m3_1`, ≈2 fF/µm²) 150 pF is ≈75,000 µm² — real
   area, but MIM sits between met3 and met4 and can be stacked *over* the
   2.5 mm pass device rather than beside it. That is a floorplan constraint
   for the layout issue, and it is recorded here rather than discovered
   there.
2. **A bare Miller cap is not enough — hence `R_CZ`.** A bare `C_COMP` shorts
   `EA_OUT` to `VOUT` at high frequency, which turns the pass device into a
   follower and puts a floor under the loop gain; past that floor, making
   `C_COMP` bigger stops lowering the crossover at all. Screening measured
   exactly that: at 1 mA/4.7 µF, going 100 pF → 250 pF moved the crossover
   only 2671 Hz → 1677 Hz (phase margin 12.4° → 18.5°). `R_CZ` breaks the
   feedthrough and places a left-half-plane zero at `1/(2π·R_CZ·C_COMP)` ≈
   3.5 kHz, which is what actually recovers the phase.

`R_CZ` is a genuine two-sided optimum rather than a "bigger is better" knob.
Screening at `tt`/27°C, `VIN = 3.63 V`, `C_COMP = 100 pF`, phase margin in
degrees:

| `R_CZ` | 0 mA / 0.33 µF | 1 mA / 4.7 µF | 50 mA / 0.33 µF |
|---|---|---|---|
| 100 kΩ | 16.3 | 21.7 | 122.0 |
| 200 kΩ | 17.3 | 30.6 | 107.7 |
| 400 kΩ | 19.2 | 46.8 | 56.2 |
| 1 MΩ | 24.8 | 74.1 | **25.7** |

Too small and the light-load/high-`C_eff` corner loses margin; too large and
Miller pole splitting stops working at the 50 mA/0.33 µF corner DR-002 flags
as the risky one. `M_TAIL`'s `W` was raised `20 → 40` in the same pass, for
`Gm`: the no-load corner has to cross over *above* a low-frequency pole/zero
doublet, which needs bandwidth. It stops at 2× rather than the 6× that
screening showed keeps improving that corner, because the DRAFT `Iq < 30 µA`
row is the binding constraint — 6× measured 33.6 µA at 50 mA, over the row;
2× measures 24.9 µA (table below), inside it.

**Measured result** (`sim/loop-gain` record `20260818-014128-01b7905`, the
`--quick` 3-corner subset; DRAFT bound is `spec/target-spec.md`'s Stability
row, PM ≥ 45° and GM ≥ 10 dB worst corner):

| Window point | `tt`/27°C/3.30V | `ss`/−40°C/2.97V | `ff`/125°C/3.63V |
|---|---|---|---|
| 0.33 µF, 10 mΩ, 50 mA (DR-002's low-`C_eff` corner) | **58.6°** | **55.6°** | **64.5°** |
| 0.33 µF, 10 mΩ, 1 mA | 90.1° | 89.2° | 91.2° |
| 0.33 µF, 10 mΩ, 0 mA | **19.3°** | **15.6°** | 82.0° |
| 4.7 µF, 10 mΩ, 50 mA | 90.4° | 90.4° | 90.7° |
| 4.7 µF, 10 mΩ, 1 mA | 50.8° | 53.9° | 46.7° |
| 4.7 µF, 10 mΩ, 0 mA | 52.0° | **38.1°** | 89.6° |
| 0.33 µF, 500 mΩ, 50 mA (ESR ceiling) | 70.5° | 68.3° | 75.2° |

Gain margin is 18.7–19.9 dB at the low-`C_eff` corner and 70.2–71.0 dB at the
0 mA points, i.e. above the 10 dB row everywhere the record measures it.
Crossover at the low-`C_eff` corner is 153–189 kHz and DC loop gain
58.1–59.9 dB.

**What still fails, stated plainly.** The **no-load** points are the binding
ones: 0 mA/0.33 µF measures 15.6–19.3° at the `tt` and `ss` corners, and
0 mA/4.7 µF measures 38.1° at `ss`. The record's overall verdict is therefore
`FAIL`, honestly. Two things are worth knowing about that number before
reading it as "nearly oscillating":

- Its **gain margin is ~70 dB**. The shape is a low-frequency pole/zero
  *doublet dip* — the phase dips toward −160° while the loop gain is still
  tens of dB away from unity — not a phase margin eroding toward an
  instability. In transient the signature is ringing/slow settling at no
  load, not a limit cycle.
- The fallback DR-002 itself names for a stability shortfall — requiring a
  **minimum ESR** — would not fix it. At 0 mA/0.33 µF the ESR zero sits at
  `1/(2π·ESR·C_out)`, i.e. ≈965 kHz even at DR-002's 500 mΩ ceiling, three
  decades above the ~300 Hz crossover. That is a real finding for DR-002 and
  it is written into the append this issue adds to that record.

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

### Thermal shutdown (#29)

Implements `spec/decision-records/DR-005-thermal-shutdown-trip.md`: trip
`Tj_trip` = 150°C nominal (untrimmed), hysteresis 15°C nominal (reset
`Tj_reset` ≈135°C), reference = internally generated / bias-generator-derived
(explicitly **not** `VREF`, **not** a bandgap), behavior = auto-restart
(non-latching), reusing the existing EN-gated shutdown path rather than a
parallel shutdown mechanism.

The implementation mirrors #22's current-limit structure exactly — a sense
element feeding a comparison node, an EN-gated clamp on that node:

1. **Sense (CTAT).** `M_TSD1`/`M_TSD2` are two diode-connected NMOS
   (`W=80`, `L=4`, `nf=16`) stacked between `TS_SNS` and the EN-gated
   pseudo-ground `AMP_ENN`, biased from a 1/8-width copy of the `M_BIASP1`
   bias unit (`M_TSPS`, `W=1.25`, gate=`BIASP`) at ~200 nA. Each `Vgs` is
   CTAT; stacking two doubles the slope, so `V(TS_SNS)` falls with
   temperature roughly twice as fast as a single diode-connected device
   would.
2. **Reference (also CTAT, but shallower).** `M_TSR1` is a single
   diode-connected NMOS of the same device family as the sense stack
   (`W=0.42`, `L=2`), at a ~95× higher current density than the stack's
   `80/4` **and** carrying ~7× the branch current, biased from `M_TSPR`
   (`W=7`, a 0.7× copy of the `M_BIASP1` bias unit). Both branches still
   hang off the same `BIASP` gate, so the bias generator's own
   supply/temperature drift is common-mode to the comparison; what is
   deliberately *not* common-mode is the branch-current ratio, which is one
   of the two knobs that place the trip temperature (see "Sizing the trip:
   what is a knob and what is not" below). At this much higher current
   density `M_TSR1` sits in strong inversion, where `Vgs` is only weakly
   CTAT, versus the sense stack's weak-inversion, steeply-CTAT behavior.
   Both quantities are internally generated and bias-generator-derived —
   neither is `VREF` — per DR-005's reference decision; the crossing of the
   two differently-sloped CTAT curves as temperature rises is the trip
   point.
3. **Compare.** `M_TCN1`/`M_TCN2` (gates `TS_SNS`/`TS_REF`) form an NMOS
   differential pair (NMOS rather than the error amp's PMOS pair, because the
   input common mode here — 1–2.2V — sits above an NMOS pair's headroom and
   too close to `VIN` for a PMOS tail to stay saturated), tailed by
   `M_TCTAIL` (a 1/4-width copy of `M_BIASN1`, gate=`NB`, source through
   `M_ENN2`/`AMP_ENN`) and loaded by the `M_TCP1`/`M_TCP2` diode/mirror pair,
   driving the high-impedance node `TS_CMP`. `TS_CMP ≈ VIN` = not tripped
   (cold: `TS_SNS > TS_REF`); `TS_CMP` falls once the die is hot enough that
   `TS_SNS` drops below `TS_REF` — the same "falling = engaged" convention
   `CL_CMP` already uses.
4. **Clamp into the existing shutdown path.** `M_TSHUT` (`VIN -> EA_OUT`,
   gate=`TS_CMP`) is structurally identical to `M_ENP` and `M_CLIM` — while
   not tripped it is off; once `TS_CMP` falls it turns on and pulls the pass
   gate to `VIN`, turning `M_PASS` off and driving dissipation toward zero,
   exactly the mechanism `M_CLIM` uses for an over-current fault. Because
   this is a level-driven clamp on the same node the enable and current-limit
   paths already drive, and not a new/parallel mechanism, auto-restart falls
   out for free per DR-005's Decision: once the die cools and `TS_CMP` snaps
   back toward `VIN`, `M_TSHUT` turns off and the loop resumes with no reset
   pin or latch needed. `M_ENP4` (`VIN -> TS_CMP`, gate=`EN`) is the fourth
   member of the `M_ENP`/`M_ENP2`/`M_ENP3` EN-gated-clamp family, giving
   `TS_CMP` — and therefore `M_TSHUT`'s gate — a defined off state at `EN=0`
   instead of floating, the same role `M_ENP3` plays for `CL_CMP`.
5. **Hysteresis.** `M_TSHYS` (`gate=TS_CMP`) is off while not tripped (its
   `Vsg ≈ 0`, costing no quiescent current), so hysteresis is free in normal
   operation. Once `TS_CMP` falls (tripped), `M_TSHYS` turns on and steers
   `M_TSHYSB`'s current (a scaled bias-unit copy, not the switch's own drive
   — sizing the *current* rather than the switch keeps the hysteresis a
   device ratio rather than a `VIN`-dependent injection) into `TS_REF`,
   raising the reference so the comparison looks hotter than it is until the
   die actually cools past `Tj_reset`. This is positive feedback around the
   comparator, giving a clean edge rather than a slow slide through the
   linear region. `M_TSHYSB`'s width is the sizing knob (`W=1.5` in #29,
   **`W=4.5`** since #69, `L=2` throughout), re-sized to restore DR-005's
   15°C nominal at #69's new slope and branch stiffness; #69's own screening
   puts the result at **13.9–20.4°C** over five process corners × three
   supplies (see "Sizing the trip" below).
   **Update (#77, 2026-08-25): the calibrated `sim/thermal` sweep found this
   feedback loop's gain is real but marginal, not the clean snap this
   qualitative description assumes — see the dated "#77" section below for
   the full diagnosis and why a fix was not shipped.** The two numbers are
   not in conflict and neither supersedes the other: #77 measured the
   *pre-#69* sizing with a `.dc temp` continuation sweep, while #69's
   13.9–20.4°C comes from solving the rising and falling branches separately
   on the *re-sized* pair — a technique #77's own Diagnostic 1 independently
   shows is needed to see the window that a vanilla continuation sweep loses.
   **Whether #69's re-size also repairs the hysteresis is therefore open**
   until `sim/thermal` is re-run against `4cb27f8`; see "Parallel landings on
   `main`, and what they leave stale" below.
6. **Dominant pole.** `C_TS` (`TS_CMP -> VIN`, 1p placeholder) is the same
   construction as `C_CL` on the current-limit comparator — it only damps
   electrical comparator chatter; the real time constant of a thermal event
   is the die's own thermal mass, orders of magnitude slower.

**EN-gating, following the established discipline.** Every new device is
gated by an existing EN-controlled node: `M_TSPS`/`M_TSPR`/`M_TSHYSB`'s gates
are `BIASP` (dead at `EN=0` via `M_ENP2`); `M_TSD1`/`M_TSD2`/`M_TSR1`/
`M_TCTAIL`'s ground returns are the shared `AMP_ENN` switch (`M_ENN2`); and
`M_ENP4` forces `TS_CMP` to `VIN` at `EN=0`, which turns `M_TSHUT` and
`M_TSHYS` off as a consequence rather than requiring a dedicated gate on
either. No new EN-gating primitive was added — the circuit reuses
`M_ENN`/`M_ENN2`/`BIASP` exactly as #22's current-limit and soft-start
additions did.

**Known accuracy caveat, same shape as the current limit's.** The reference
branch is bias-generator-derived, hence itself supply-dependent and
untrimmed (`design/README.md`'s own caveat for `M_CLP`), so the trip point's
absolute accuracy is loose and PVT-dependent — this is DR-005's stated,
accepted cost of not depending on a reference-generator gap that has no
closing date, not a hidden shortfall. The actual window is now measured, and
its residual supply dependence is the part that is still un-narrowed — see
immediately below.

### Sizing the trip: what is a knob and what is not (re-worked in #69)

**The defect #69 fixed.** As first sized in #29, this circuit's rising trip
moved **102–175°C across the five process corners** at `VIN = 3.30V` — so at
`ff` and `sf` it had *already tripped at 125°C*, the top of the spec's own
rated `Tj ≤ 125°C` range, forcing the pass gate off during legitimate rated
operation. That is precisely what DR-005's "25°C guard band above the
spec's own `Tj ≤ 125 °C` operating ceiling … or it would nuisance-trip"
clause exists to prevent, and it was the direct cause of the non-physical
numbers at the six `ff`/`sf`-at-125°C points in three of the 45-point
campaigns (see the campaign section near the end of this file).

**Root cause: an un-cancelled, geometry-amplified corner `Vth0` skew.**
sky130's continuous HV-device models implement a process corner *only* as a
`delvto` shift — `mulu0`/`mulvsat` are commented out in both
`sky130_fd_pr__nfet_g5v0d10v5` and `…__pfet_g5v0d10v5` in
`libs.tech/combined/continuous/models_fet.spice` at the pinned PDK commit —
and that shift is **geometry-weighted**:

```
delvto = swx_vth * (0.10*8/L + 0.90) * (0.045*7/W + 0.955)
                 * (-0.0007*56/(L*W) + 1.0007)          [HV nfet]
```

Write that weighting as `k(L,W)`. The trip is the crossing of
`2·Vgs(sense)` against `1·Vgs(reference)`, so the *difference* the
comparator sees carries `(2·k_sense − k_reference)·swx_vth` — a term that
does not cancel merely because both branches are the same device family.
With the #29 sizing, `k(1, 80) = 1.63` and `k(10, 2) = 1.09`, giving
`2·1.63 − 1.09 = 2.17`: a short-channel sense device *amplified* the corner
shift by 1.63×, and the 2-vs-1 count then doubled it. Across the corner
set's `swx_vth ∈ [−0.045, +0.045] V` that is ~195 mV of un-cancelled
comparison error against a gap slope of only ~3.7 mV/°C — i.e. tens of
degrees of trip movement, which is exactly what was measured. Note this also
corrects the hypothesis #60 recorded: `ff` and `sf` do **not** share a
fast-PMOS skew. In sky130 the corner name is *(pfet, nfet)*, so `sf` is
slow-p/**fast-n** and `ff` is fast-p/**fast-n** — what they share is the
fast **NMOS** skew, and the measured trip temperature is monotone in the
nfet `vth0` shift (`sf` −45 mV → lowest trip, `fs` +45 mV → highest) with
the PMOS skew barely visible.

**The fix, and what it makes rigid.** Choose the two geometries so
`2·k_sense ≈ k_reference`, and place the trip temperature with the *branch
currents* instead:

| Device | #29 | #69 | Role after the re-size |
|---|---|---|---|
| `M_TSD1`/`M_TSD2` | `W=80 L=1` | `W=80 **L=4**` | `k = 1.055`; long channel to stop amplifying the corner shift |
| `M_TSR1` | `W=2 L=10` | **`W=0.42 L=2`** | `k = 2.114 ≈ 2×1.055`; `W=0.42` is the PDK's minimum drawn width, which is what makes `k` large enough to match twice the sense device's |
| `M_TSPR` | `W=2.5` | **`W=7`** | trip-placement knob (reference is strong-inversion, so `Vgs ∝ √I`) |
| `M_TSPS` | `W=2.5` | **`W=1.25`** | second trip-placement knob, and it *saves* Iq |
| `M_TSHYSB` | `W=1.5` | **`W=4.5`** | restores DR-005's 15°C hysteresis at the new slope/branch stiffness |

`2·k_sense − k_reference` falls from **2.17 to 0.003**. `M_TSR1`'s `W/L` is
therefore **no longer the trip-temperature knob** the #29 sizing note called
it — it is pinned by the cancellation, and the currents move the trip.

**Measured result** (screening, from the committed schematic's own netlist,
5 process corners × 3 supplies, PDK `sky130A` @ `c6d73a35`; the rising and
falling branches are solved separately because the comparator is genuinely
bistable inside its own hysteresis window and a plain `.op` sweep of the
whole block lands on whichever branch the solver's homotopy finds):

| | #29 sizing | #69 sizing |
|---|---|---|
| Rising trip, 5 corners @ `VIN=3.30V` | 102–175°C | **159.1–171.5°C** |
| Rising trip, 5 corners × 3 supplies | (tripped inside the rated range) | **155.1–175.0°C** |
| Worst-case guard band above the 125°C ceiling | **−15°C** (i.e. tripped) | **+30.1°C** |
| Hysteresis | 13.5–15.1°C | **13.9–20.4°C** |
| Sense-vs-reference slope at the crossing | 3.65–3.95 mV/°C | **3.90–4.24 mV/°C** |
| `.op` over the repo's own 45 PVT points, 50 mA resistive load | **6/45 tripped** | **0/45 tripped**, `VOUT` 1.7972–1.7985 V |
| Iq at 50 mA over the same 45 points | 22.1–28.5 µA | **22.7–29.0 µA** |

**Three honest caveats on that result.**

1. **The nominal lands ~15°C above DR-005's 150°C.** The window is ~20°C
   wide (≈12°C process + ≈8°C supply), so holding DR-005's 25°C guard band
   at the **worst** corner — the strictly stronger reading, and the one a
   nuisance-trip defect demands — forces the nominal to ≈165°C rather than
   150°C. Centering at 150°C instead would put the worst corner back at
   ≈140°C, a 15°C guard band, i.e. it would re-open a weaker version of the
   same defect. That trade is recorded here rather than resolved by
   loosening a spec line; see the appendix appended to
   `spec/decision-records/DR-005-thermal-shutdown-trip.md`.
2. **The residual ~8°C of supply dependence is the bias generator's, not
   this circuit's.** `I_bias ≈ (VIN − Vgs)/R_BIAS` rises with `VIN`, and the
   strong-inversion reference's `Vgs ∝ √I` follows it. Narrowing that needs
   a supply-independent or cascoded bias generator — the same missing piece
   #70 tracks for PSRR — so it is deliberately out of this fix's scope.
3. **The cancellation is derived from the PDK's own corner model, and is
   only as real as that model.** The physically robust half of the fix is
   that a short channel makes `Vth` more process-sensitive (short-channel
   `Vth` roll-off is a real effect, and lengthening the sense devices is a
   real mitigation). The *exact* null at `2k_s − k_r = 0.003` is fitted to
   sky130's specific `delvto` polynomial and should not be read as a
   silicon-accurate cancellation. The design does not rely on the exact
   null: the ~12°C of residual process spread that remains comes from terms
   the polynomial does not describe, so the guard band above is what carries
   the margin, not the null.

**Mismatch is not in the numbers above.** The corner sweep varies process
globally; per-instance mismatch is a separate axis
(`sim/mc-output-accuracy` is the only experiment in this repo that samples
it). At ~4 mV/°C, 10 mV of comparator/device offset is ~2.5°C of trip
movement, which is one reason the worst corner is left at 155°C rather than
trimmed down to exactly 150°C. A Monte Carlo run of the trip point itself
does not exist yet and is named as a gap, not claimed.

## Screening checks (screening only — not `sim/` evidence)

Everything below was run against the pinned PDK (`sky130A`, open_pdks
`c6d73a35f524070e85faff4a6a9eef49553ebc2b`, same pin as `sim/pdk.json`), `tt`
corner, 27°C, `VREF = 1.2V` (placeholder, see above), **from the committed
schematic's own xschem-generated netlist** (`xschem -n … -o /tmp/… ; .include`
that `.spice` file into a throwaway deck). Nothing here is committed under
`sim/`: these issues are design sources only. The corner-swept versions live
under `sim/` — `load-transient` / `psrr-dc` / `dropout-vs-load` from #18 and
`loop-gain` from #25, each re-run against this revision — with the full
45-point PVT/Monte-Carlo matrix still being #19's job. Single process corner,
single temperature — **not** a spec-row-proving result.

### 1. DC operating grid — `VOUT` (target `1.5 × VREF` = 1.800V)

Re-measured after issue #25's amplifier revision (a `.op` analysis treats
capacitors as opens, so `C_COMP`/`R_CZ` cannot move these numbers; `M_TAIL`
and the new mirror branches can, and did):

| `VIN` | 0mA (divider only) | 1mA (`1.8kΩ`) | 50mA (`36Ω`) |
|---|---|---|---|
| 2.97V | 1.8021V (+0.11%) | 1.8003V (+0.02%) | 1.7978V (−0.12%) |
| 3.30V | 1.8022V (+0.12%) | 1.8004V (+0.02%) | 1.7980V (−0.11%) |
| 3.63V | 1.8025V (+0.14%) | 1.8005V (+0.03%) | 1.7981V (−0.11%) |

**Every point is inside the DRAFT ±2% Output row**, including the 0mA and 1mA
high-`VIN` points the #22 schematic missed by +24.7% and +13.6%. For direct
comparison, the same grid on the #22 (five-transistor OTA) schematic — the
"known open item" this issue closes:

| `VIN` | 0mA | 1mA | 50mA |
|---|---|---|---|
| 2.97V | 1.859V (+3.3%) | 1.811V (+0.6%) | 1.804V (+0.2%) |
| 3.30V | **2.244V (+24.7%)** | 1.817V (+1.0%) | 1.808V (+0.4%) |
| 3.63V | **2.696V (+49.8%)** | **2.046V (+13.6%)** | 1.812V (+0.6%) |

The pass-gate voltage is the tell. `EA_OUT` now tracks `VIN` instead of
stalling at the old ≈2.5V `EA_TAIL` ceiling:

| `VIN` | `EA_OUT` @ 0mA | @ 1mA | @ 50mA |
|---|---|---|---|
| 2.97V | 2.395V | 2.008V | 1.356V |
| 3.30V | 2.734V | 2.347V | 1.708V |
| 3.63V | **3.072V** | 2.685V | 2.057V |

Against the other DRAFT rows, honestly scored:

- **Load regulation** over the row's full 0→50mA range is 4.3mV at
  `VIN=2.97V` (**0.24%**), inside the DRAFT `<1%` row — where the #22
  schematic was 55mV (3.0%) and missed it.
- **Line regulation** at 50mA is (1.7981−1.7978)/0.66V ≈ **0.45mV/V**, inside
  the DRAFT `<5mV/V` row — where the #22 schematic was ≈11mV/V and missed it.
  At 0mA it is 0.61mV/V.

These are still **screening** numbers (single process corner, single
temperature, not `sim/` evidence); corner-swept versions of the same rows are
#19's job. What *is* `sim/` evidence for this revision is the
loop-gain/phase-margin record cited under "Compensation (sized in #25)", plus
the re-run `load-transient` / `dropout-vs-load` / `psrr-dc` records.

### 2. Quiescent and shutdown current

| `VIN` | Iq @ 0mA | Iq @ 1mA | Iq @ 50mA | `EN=0` supply current (`1.8kΩ`) |
|---|---|---|---|---|
| 2.97V | 9.71µA | 10.33µA | 22.12µA | **0.133nA** |
| 3.30V | 11.28µA | 11.87µA | 23.49µA | — |
| 3.63V | 12.88µA | 13.44µA | 24.91µA | **0.165nA** |

Iq = total `VIN` current minus load current. All points are inside the DRAFT
`Iq < 30µA at no load and full load` row, and the disabled state is four
orders of magnitude inside the DRAFT `< 3µA` row. The 0mA→50mA Iq growth is
almost entirely the current-limit sense branch (`I_load / 5952` ≈ 8µA at
50mA) — see "Iq interaction" above.

**Issue #25 spent Iq deliberately, and the row is what capped the spend.**
The #22 numbers were 5.55–7.38µA at 0mA and 18.0–19.3µA at 50mA; the increase
here is the two added mirror branches plus the 2× `M_TAIL` widening. Pushing
`M_TAIL` to 6× — which screening showed keeps improving the no-load phase
margin, up to ~40° — measured **33.6µA at 50mA**, i.e. *over* the DRAFT row,
so it was not taken. That trade is recorded rather than hidden, because it is
the reason the no-load corner in "Compensation (sized in #25)" is left short
of 45° instead of bought out with bias current: relaxing one DRAFT row to
make another DRAFT row pass is exactly what `CLAUDE.md` forbids.

**The disabled state is unchanged at the leakage floor.** `EN=0` measures
133pA at `VIN=2.97V` and 165pA at `VIN=3.63V` — the same ~150pA as the #22
record — confirming the new pull-up path (`M_MIRP1`/`M_MIRP2` and the `PB`
node that drives them) introduces no reverse-leakage path. At `EN=0`,
`M_ENP5` holds `PB` at `VIN` (measured `PB = VIN` exactly at both supplies)
so `M_MIRP2` is hard off, and `M_MIR3`/`M_MIR4` are cut by the existing
`AMP_ENN` switch; `VOUT` collapses to ~0.2µV. This is where the rejected #22
candidate needed *two* extra devices (`NB` pulled low and `R_BIAS`
disconnected) and this topology needs one. The #14 record's figure was ≈46pA;
the #22 protection additions moved it to ≈150pA and #25 leaves it there.

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
229–234µs, overshoot ≤ 0.03%), but at 0/1mA the ramp is bypassed — that was
the ceiling gap asserting itself, not a soft-start failure: the #22 loop
could not hold `VOUT` down at those points with or without a ramp. **Issue
#25 removed that ceiling** (see "Error-amplifier output stage (rebuilt in
#25)" and the re-measured DC grid), so the ramp is no longer bypassed at
0/1mA. The soft-start table itself has *not* been re-measured against the
new amplifier; re-taking it is follow-on work, and the numbers above should
be read as belonging to the #22 revision.

### 5. Thermal shutdown

> **Re-measured in #69, and the framing below changed with it.** The
> original text of this section (kept in the "(a)/(b)/(c)" tables below,
> which are #29-era numbers against the #29-era sizing) argued that no
> screening deck could say anything about a trip point above 125°C. That
> was too strong: what a temperature sweep past 125°C actually produces is
> a **model extrapolation**, not a non-result, and the distinction matters
> for exactly one reason — the thing this block must get right is not
> "where does it trip", it is "**does it stay untripped everywhere inside
> the rated range**", and that question is answered *inside* the
> characterized range. See "(d)" below.

**What a temperature sweep past 125°C is and is not.** DR-004 binds this
repo's verification temperature axis to `{−40, 27, 125}°C`, and DR-005
records that its 150°C target "sits outside this repo's own
model-characterized temperature range". Both remain true. Consequently the
trip temperatures quoted in "Sizing the trip" above (155–175°C) are
**extrapolations of the pinned sky130 models past their characterized
range** and are reported as a design window, not as verified silicon
behaviour. What is *not* an extrapolation, and is the claim this circuit
actually has to support, is the sign of the sense-vs-reference gap **at
125°C** — the top of the characterized range and the top of the spec's own
rated `Tj` range.

**(d) The rated-range check, #69 sizing, all 45 PVT points.** `.op` from the
committed schematic's own netlist, `VREF = 1.2V` (placeholder), `36Ω` load
(~50 mA), across the repo's own 5 process corners × {−40, 27, 125}°C ×
{2.97, 3.30, 3.63}V:

| Quantity | #29 sizing | #69 sizing |
|---|---|---|
| Points where `TS_CMP` has tripped | **6 / 45** (all `ff`/`sf` at 125°C) | **0 / 45** |
| Worst `TS_SNS − TS_REF` at 125°C | **−0.125 V** (`sf`, i.e. tripped) | **+0.121 V** |
| `VOUT` range over all 45 points | 0 V at the 6 tripped points | **1.7972–1.7985 V** |
| Iq at 50 mA over all 45 points | 22.1–28.5 µA (untripped points) | **22.7–29.0 µA** |

`+0.121 V` of worst-case margin against a ~4 mV/°C gap slope is ~30°C of
headroom, measured at a characterized temperature with no extrapolation.
That is the correctness claim; the 155–175°C figures are the (extrapolated)
consequence of it.

The three tables that follow are the **#29-era** screening data, kept
because the polarity and `EN=0` arguments they make are unchanged by the
re-size and because the "(b)" table is the historical record of the gap that
#69 turned out to be closing far too fast. Their absolute node voltages no
longer describe the committed schematic.

**(a) Polarity at `tt`/27°C** (#29 sizing), `VIN = 3.30V`, `EN` high,
`VREF = 1.2V` (placeholder), `1.8kΩ` load (~1mA):

| Node | Value | Reading |
|---|---|---|
| `TS_SNS` | 1.502V | sense-stack CTAT node |
| `TS_REF` | 1.085V | reference CTAT node |
| `TS_SNS − TS_REF` | **+0.417V** | cold, well away from the crossing |
| `TS_CMP` | 3.300V (`≈VIN`) | **not tripped**, correct polarity |
| `EA_OUT` | 2.346V | main loop unaffected — same operating point as the pre-#29 screening data |
| `VOUT` | 1.817V | matches the existing 1mA/`VIN=3.30V` row in "DC operating grid" above, confirming the new circuit does not perturb the main loop when untripped |

`TS_SNS > TS_REF` at 27°C is the expected cold-state ordering (sense stack
reads "not yet hot"), and `TS_CMP` sitting at `VIN` with that ordering
confirms the comparator's polarity is wired the way §"Thermal shutdown"
above describes — `TS_CMP` falls only once `TS_SNS` drops below `TS_REF`.

**(b) Direction with temperature, `tt`/125°C** (#29 sizing; top of DR-004's
characterized range, same bias/load conditions):

| Node | 27°C | 125°C | Direction |
|---|---|---|---|
| `TS_SNS − TS_REF` | +0.417V | **+0.067V** | gap closes by ~84% over the characterized range |
| `TS_CMP` | 3.300V | 3.277V | starts drooping off `VIN`, consistent with approaching the crossing |

The gap closes monotonically and `TS_CMP` moves in the tripped direction as
temperature rises — the qualitatively correct behavior for DR-005's design.

**This table is where the #69 defect was visible and was read too
charitably.** `+0.067V` of remaining gap at `tt`/125°C is only ~18°C of
headroom at the then-current 3.7 mV/°C slope, and this table was taken at
`tt` only. Reading it as "the mechanism points the right way" was correct;
not asking what that 18°C becomes at the other four process corners is what
let a corner that had *already tripped at 125°C* ship. The #69 sizing's
equivalent number is `+0.196V` at `tt`/125°C and `+0.121V` at the worst of
all 45 points — see "(d)" above, which is the check that should have been
run here in the first place.

**(c) Clean `EN=0` shutdown**, `tt`/27°C, same `VIN`/load:

| Node | Value |
|---|---|
| `TS_CMP` | 3.300000V (forced to `VIN` by `M_ENP4`) |
| `EA_OUT` | 3.300000V (forced to `VIN` by the existing `M_ENP`) |
| `BIASP`, `NB` | `≈VIN` (bias generator dead) |
| `VOUT` | ≈0V |
| `I_VIN` | **175pA** |

175pA is the same leakage floor the #22 record measured (≈150pA after
current limit + soft start); the thermal-shutdown additions do not open a
new static current path at `EN=0`, consistent with every new device routing
through the existing `AMP_ENN`/`BIASP`/`M_ENP4` gating described above.

### Closed in #25: light-load regulation (diagnosis and cure)

**Status: closed.** The DC grid above now sits inside the DRAFT ±2% row at
all nine `VIN` × load points. What follows is the history, kept because the
diagnosis is the reason the fix is a topology change and not a sizing tweak,
and because the *rejected* candidate is worth not repeating.

`M_PASS` is sized for 50mA (`W_total ≈ 2.5mm`), so at 0mA it must be
throttled deep into sub-threshold. Issue #14 flagged that this failed at 0mA
and narrowed it to "a gain/sizing question". **Issue #22 identified the
mechanism, and it was a hard topology ceiling rather than a gain shortfall:**

> `EA_OUT` is the drain of the PMOS input device `M_IN2`, whose source is
> `EA_TAIL`. `EA_OUT` therefore cannot rise above `EA_TAIL`, and `EA_TAIL`
> settles near `V_in,cm + V_sg(M_IN2)` ≈ 2.4–2.5V regardless of `VIN`. The
> minimum achievable `V_sg(M_PASS)` is thus `VIN − 2.5V`, which *grows* with
> `VIN`: ≈0.5V at `VIN_min` (pass device essentially off, 0mA regulates to
> +3.3%), ≈1.1V at `VIN_max` (a 2.5mm device at `V_sg = 1.1V` still delivers
> more than a 1mA load can absorb, so the loop rails).

The #22 screening OP data (second table under "DC operating grid") is exactly
this pattern: the failures are at low load *and high `VIN`*, and the failure
gets monotonically worse as `VIN` rises. Adding gain does not fix it — the
amplifier is already saturated against its own ceiling at those points, as
`EA_OUT ≈ EA_TAIL` to within 20mV confirms. **The fix is an amplifier output
stage that can actually swing to `VIN`**, which is what the current-mirror
OTA described above is.

A different candidate fix was built and screened during #22 and was **not**
committed, because it traded one failure for a worse one. It is recorded here
because #25 deliberately did *not* repeat it:

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
> were each screened and none of them fixed it. The #22 single-stage
> loop was stable at that same corner (0.77µV pp).

**Why #25's answer avoids that trap.** The rejected candidate bought output
swing by adding a *second gain stage*, which meant a second high-impedance
node and therefore a third low-frequency pole under a large DC gain — a
three-pole loop that no single Miller cap can compensate, which is exactly
what the screening found. The current-mirror OTA buys the same output swing
without adding a gain stage: the two turnaround nodes it introduces (`EA_D2`,
`PB`) are diode-loaded, so they are low-impedance and their poles land
decades above crossover. The loop stays two-pole, and a Miller cap with a
nulling resistor is then the right tool for it. Measured at the same corner
that broke the candidate (`C_out = 0.33µF` / 50mA / `VIN = 3.63V`,
`tt`/27°C): **3.8mV pp** on `VOUT` after a 10mA load step and 14mA pp on the
supply, versus 351mV pp / 135mA pp for the rejected candidate — and
`sim/loop-gain` measures 55.6–64.5° of phase margin there across its
quick-subset corners. Adding DR-002's 500mΩ ESR ceiling at the same corner
changes the transient by nothing measurable (3.8mV pp, 12.5mA pp).

The residual, stated plainly: the **no-load** end of DR-002's window is now
the binding stability point rather than the DC-accuracy point it used to be —
see "Compensation (sized in #25)" for the measured phase margins and the
DR-002 append for what that means for the record.

## Known gaps / follow-on scope

Closed by issue #22 and now in this schematic: **current limit** and
**soft-start** (both spec rows above), plus the pass-device width correction
and the reference-common-mode change those two required. Closed by issue #29:
**thermal shutdown** (CTAT sense + trip comparator, per DR-005), reusing the
same shutdown path.

Closed by issue #25: the **error-amplifier output-swing ceiling** (the
current-mirror OTA) and the **compensation placeholder** (`C_COMP`/`R_CZ`,
sized against `sim/loop-gain` over DR-002's proposed window).

Still deliberately **not** in this schematic:

- **`C_CL` is still a placeholder.** The current-limit comparator's dominant
  pole (`CL_CMP -> VIN`, `1p`) was not sized against a loop-gain sim; only
  the main loop's `C_COMP`/`R_CZ` were. The limit loop's screened behaviour
  (flat into a hard short, 1.4µA pp) is a smoke test, not a phase-margin
  claim.
- **Corner coverage.** The full 45-point PVT matrix and Monte Carlo campaign
  (#19/#37/#40) has since run against this schematic — see
  [`measurements/characterization.md`](../measurements/characterization.md)
  for the aggregated per-row verdict, and the dated "full 45-point PVT +
  Monte Carlo campaign" section below for the root-cause writeup (#60) and
  the follow-on issues (#69/#70/#71) tracking the open work to close these
  gaps. Thermal now has its own dedicated testbench (`sim/thermal`, #66) —
  see the dated "Thermal-shutdown trip/hysteresis testbench" section below
  for what it found.
- **An actual on-chip voltage reference.** `VREF` is an external port (see
  "VREF interface caveat" above).

These are real, trackable gaps, not silently dropped requirements.

### The full 45-point PVT + Monte Carlo campaign has run, and it fails every DRAFT row it substantiates (#19/#37/#40 ran it; #60 root-caused the results, 2026-08-25)

**Status update, superseding every "#19's job" / "3-corner `--quick` subset"
line elsewhere in this file.** Issues #19/#37/#40 closed having actually run
the full 45-point PVT matrix (`tt`/`ss`/`ff`/`sf`/`fs` × {−40, 27, 125}°C ×
{2.97, 3.30, 3.63}V) against `dropout-vs-load`, `load-transient`, `psrr-dc`
and `loop-gain`, plus a 200-sample Monte Carlo mismatch run against
`mc-output-accuracy` — all cited below are the freshest records in the repo
as of this section. Every one of them is **FAIL**. Issue #60 root-caused each
row against the actual schematic (screening decks reproducing the closed-loop
DC/AC behaviour the corner runner exercises — single corner, not `sim/`
evidence, same convention as every other screening deck in this file). This
section states what was actually found, in place of the stale "future work"
framing the rest of this file otherwise still carries from before #19/#37/#40
ran.

> **Mechanism 1 below is CLOSED as of 2026-08-25 (issue #69). Its numbers
> are kept because they are the diagnosis, but every record id quoted inside
> it is now superseded.** The thermal-shutdown circuit was re-sized (see
> "Sizing the trip: what is a knob and what is not" above) and all four
> affected campaigns were re-run against the fixed schematic. Jump to
> "What the #69 re-run changed" at the end of this section for the
> before/after table. Mechanisms 2–6 are unchanged and still open.

**Two distinct failure mechanisms were identified, plus one independent,
previously-undesigned-for gap (PSRR):**

1. **A previously-unconfirmed false-trip of thermal shutdown (#29/DR-005) at
   the `ff`/`sf` process corners at 125°C — the top of this repo's own rated
   operating range, not a fault condition.** DR-005's own Decision explicitly
   requires the 150°C nominal trip to sit a "25°C guard band above the spec's
   own `Tj ≤ 125°C` operating ceiling" specifically so the block "must not
   engage during legitimate rated operation at the 125°C ceiling, or it would
   nuisance-trip." A single-point `.op` screening check (this issue, `ff`
   process corner, 125°C, `VIN=3.30V`, `I_LOAD=50mA` — reproduced from the
   committed schematic's own netlist, not `sim/` evidence) shows exactly that
   nuisance trip happening: `TS_SNS=1.0097V` has already fallen *below*
   `TS_REF=1.0451V` (the tripped ordering), `TS_CMP=0.385V` (fully tripped,
   versus ≈`VIN` untripped), and `EA_OUT=3.298V` ≈ `VIN` — the thermal clamp
   `M_TSHUT` has pulled the pass gate fully off. The same check at `tt`/125°C
   (same bias/load) shows the correct untripped ordering
   (`TS_SNS=1.1026V > TS_REF=1.0310V`, `TS_CMP=3.279V` ≈ `VIN`). Both `ff` and
   `sf` (the two corners sharing a **fast PMOS** skew) show this at 125°C;
   `ss`, `fs` and `tt` do not trip on *this* mechanism (see the #71/#81
   correction below re: `tt`/125°C's pre-existing non-physical
   `dropout-vs-load` number, which is a *different* mechanism) — implicating
   the PMOS-biased CTAT sense/
   reference stack's (`M_TSPS`/`M_TSPR`, both PMOS current sources gated by
   `BIASP`) sensitivity to PMOS process skew as the mechanism, consistent
   with DR-005's own accepted "untrimmed, bias-generator-derived, PVT-loose"
   accuracy cost — but this is the specific, previously-unconfirmed *direction*
   of that looseness (trips early, inside the rated range) rather than late
   (which would only cost margin above 125°C, not correctness at it).
   **This single mechanism is the direct cause of every physically-impossible
   number in the `dropout-vs-load`, `load-transient` and `loop-gain` records
   at the six `ff`/`sf`-at-125°C corners** — e.g. `dropout-vs-load`'s
   `ff_125c_3.30v: vout_at_max_vin_v=-19.2011V`, `sf_125c_*: dropout_v=32.5871V`;
   `load-transient`'s `ff_125c_2.97v: undershoot_v=22.2895V`,
   `sf_125c_*: undershoot_v≈14.37V`; `loop-gain`'s `ff_125c_*`/`sf_125c_*:
   dcgain_c033_50ma_db≈-330dB` with most other measurements `n/a`. With the
   pass gate driven fully off by a falsely-tripped thermal clamp, a
   50mA-sinking ideal current-source load (the testbenches' own load model)
   has no physically consistent DC/transient solution near the target
   operating point, so the solver reports whatever extreme, non-physical
   value it converges to instead (confirmed reproducible: a screening `.op`
   at the exact same bias point returns `VOUT=-19.5043V`, matching the
   committed record's `-19.2011V` to within re-run/precision noise). **Read
   those specific numbers as "the pass device was driven off and the demanded
   50mA had nowhere physical to come from," not as literal voltages** — but
   the underlying finding (thermal shutdown nuisance-trips inside the rated
   temperature range at two of five process corners) is a real, actionable
   functional defect, not a reporting artifact.
2. **A genuine, now-fully-confirmed light-load stability shortfall,
   pervasive rather than confined to the 3-corner subset.** `sim/loop-gain`'s
   full 45-point run passes only 3/45 corners (versus the 3-corner quick
   subset's already-known 0mA shortfall at 2 of 3 corners). The `pm_c033_0ma`
   column is below the 45° DRAFT Stability row at nearly every corner outside
   125°C (typically 15–24° at −40/27°C, improving toward 30–90° as
   temperature rises), confirming the mechanism this file already named under
   "Compensation (sized in #25)" — the pass stage's own
   `gm_pass/(2π·C_out)` pole falling with load current, unclosable without
   spending amplifier bias current the DRAFT `Iq < 30µA` row does not have
   room for — generalizes across the full corner grid rather than being a
   quirk of the 3 quick-subset corners. The same marginal-margin/doublet-dip
   condition is the most likely driver of `mc-output-accuracy`'s 19/200 tail
   outliers (see below) and of the *non-pathological* (i.e. not
   thermal-shutdown-related) FAILs in `load-transient` and `dropout-vs-load`
   at `tt`/`ss`/`fs` corners.
3. **`dropout-vs-load`: a real, if smaller than initially apparent, dropout
   shortfall, distinct from (1) and (2) above at the non-`ff`/`sf`-125°C
   corners.** The `dropout_v` measurement reads `v(vin)-v(vout)` at the
   sweep's lowest point (`Vin=1.9V`, only 100mV above the 1.8V target) —
   deep inside the region where 50mA load has already forced the loop out of
   regulation, so the reported number is the pass device's residual
   `V_sd` well past dropout, not the classic "headroom at which regulation is
   just lost" definition. A screening re-sweep of the actual closed loop
   (`tt`/27°C, 50mA, `Vin` 1.9→2.5V, reproducible from the committed netlist)
   shows `Vout` climbing smoothly from 1.37V at `Vin=1.9V` to 1.79V by
   `Vin≈2.20–2.35V` — i.e. the closed loop's own actual dropout headroom is
   roughly **400–450mV**, worse than DR-003's pass-device-alone screening
   (98mA available at `V_sd=0.3V`, implying ~150mV for 50mA) because that
   screening forced full gate drive externally, while the closed loop's own
   amplifier — whose bias/tail chain also loses headroom as `Vin` approaches
   `Vout` — cannot quite reach full drive at this margin. 400–450mV is still
   above the DRAFT 300mV target, a real (if smaller than the raw 530mV–1.79V
   the record reports) gap. **Superseded by #71's fix** — see "#71 resolved"
   below for the confirmed, `sim/`-evidentiary number (0.310V–0.554V at
   −40°C/27°C across all five process corners) that replaces this screening
   estimate.
4. **The same sweep also surfaces a second, independent problem: the
   closed-loop DC operating point is not unique in parts of this region.**
   Sweeping `Vin` continuously from 1.9V to 3.63V at `tt`/27°C/50mA (screening,
   not `sim/` evidence) does not track a single monotonic branch — it jumps
   between a regulating branch (`Vout≈1.80V`) and a non-regulating one
   (`Vout` tracking well above target, e.g. 2.26–2.54V) several times before
   settling, with `ngspice` reporting `singular matrix` warnings at nodes
   `ea_cz`/`n_fbb`/`amp_enn` and, on a wider sweep starting below 1.8V,
   domain-error convergence failures in the `R_CZ` compensation resistor's
   body-junction model at nearly every swept point. This means the
   `dropout-vs-load` and `load-transient` records' per-corner numbers at
   several `tt`/`ss`/`fs` corners (not just the `ff`/`sf`-125°C corners
   mechanism (1) explains) should be read as "one of several DC solutions
   the solver's continuation history happened to land on," not as the unique
   physical answer — a genuine circuit robustness question (does a real,
   fabricated device actually exhibit multiple stable operating points in
   this region, or is this purely a simulator-continuation artifact?) that
   this issue's screening time did not resolve. **Diagnosed by #71/#81** —
   see "#71/#81 resolved" below: a genuine second stable equilibrium, worse
   at 125°C, root-caused but not yet fixed (deferred to #79).
5. **PSRR: a real, systematic, previously-undesigned-for shortfall, not a
   symptom of (1)/(2)/(4).** `sim/psrr-dc` fails 39/45 corners at 1kHz by a
   wide, consistent margin (measured 20.3–25.7dB against the 50dB DRAFT
   target — a real, non-pathological small-signal result, not a
   non-physical one); the 6 corners that pass (`ff`/`sf` at 125°C) are
   exactly the corners mechanism (1) shows are thermal-shutdown-tripped, so
   those "PASS" numbers (76–105dB) are AC gain measured around a collapsed,
   non-regulating bias point and should not be read as genuine PSRR either —
   **on the evidence available, PSRR does not actually pass anywhere.** The
   likely mechanism: this block's bias generator (`R_BIAS`/`M_BIASN1`/
   `M_BIASN2`/`M_BIASP1`, unchanged since #14) has no supply-independent
   reference or cascode — every PMOS current source in the amplifier,
   current limit, soft-start and thermal-shutdown chains inherits `VIN`
   ripple directly through `BIASP`. The current-mirror OTA's own pull-up path
   (`M_MIRP1`/`M_MIRP2`, both sourced from `VIN`) compounds this: unlike the
   NMOS pull-down side (returned through the fixed `AMP_ENN` rail), the
   pull-up mirror's reference is itself referred to `VIN`, so it does not
   independently attenuate `VIN` ripple the way a supply-independent-biased
   stage would. This was never a design target for #14/#22/#25's bias
   generator — this file already states it "remains a functional starting
   point rather than a budgeted design" — so this is a newly-confirmed,
   previously-out-of-scope gap, not a regression.
6. **`mc-output-accuracy`: the aggregate sigma-window FAIL is a tail-outlier
   artifact of (2)/(4) above, not evidence that mismatch itself is too
   large.** 181/200 samples individually pass the ±2% window; the aggregate
   `FAIL` comes from 19/200 tail samples, one of which reads `vout_ss=
   -19.345V` — a device-mismatch draw pushing an already-marginal light-load
   operating point (mechanism (2)) into the same kind of non-regulating
   branch mechanism (4) describes, at the record's own 1mA/`tt`/27°C/`VIN=
   3.3V` point (a condition that regulates cleanly with zero mismatch, per
   the "DC operating grid" table above). Fixing mechanisms (2)/(4) is very
   likely to close most or all of this row without any change to the
   mismatch model itself.

**What this means for the DRAFT spec rows.** None of Output, Dropout,
Load-transient, PSRR or Stability can be marked closed. None of the five
findings above is closable by a small, low-risk sizing tweak validated
against a single corner — each requires a design change (bias-generator
redesign for PSRR/supply-independence, a re-tuned/re-verified thermal-
shutdown sizing for the false-trip, and a compensation/bias-current rework
for the light-load margin that fits inside the DRAFT `Iq` budget) followed by
a full, expensive 45-point-per-testbench re-verification pass to confirm it
without regressing a different row — exactly the risk this issue's own
Curator enhancement flagged ("a wrong root cause or a fix that regresses a
different row could pass a shallow review unnoticed"). That work is
decomposed into follow-on issues rather than attempted speculatively in this
pass:

- **#69** — thermal-shutdown false-trip at `ff`/`sf`/125°C (mechanism 1).
- **#70** — PSRR (mechanism 5) and the pervasive light-load stability
  shortfall (mechanism 2), bundled together since both plausibly share a
  bias-generator-redesign fix and both compete for the same `Iq` budget.
- **#71** — the `dropout-vs-load` testbench's `dropout_v` measurement
  methodology (mechanism 3) and the DC-solution-multiplicity question
  (mechanism 4). **Resolved 2026-08-25** — see "#71/#81 resolved" below;
  spun off **#81** for the 125°C-wide convergence-fragility finding it
  surfaced.
- **#81** — root-caused mechanism 4's 125°C-wide severity: a genuine
  circuit robustness gap (a second, stable, non-regulating equilibrium the
  loop's own dynamics prefer at 125°C/50mA), not a solver-tuning problem.
  **Resolved (diagnosis) 2026-08-25** — see "#71/#81 resolved" below; the
  actual fix is deferred to **#79** (same bias-generator/compensation
  headroom bucket as mechanism 2).

`mc-output-accuracy`'s tail-outlier FAIL (mechanism 6) has no issue of its
own — it is expected to close mostly or entirely as a side effect of #70.

#### #71/#81 resolved: `dropout-vs-load`'s `dropout_v` methodology fixed, mechanism 4 diagnosed and root-caused (2026-08-25)

**Methodology (mechanism 3).** `sim/dropout-vs-load/experiment.json`'s deck
now sweeps `VIN` downward (3.63V → 1.5V, 20mV resolution, vs #18's original
50mV upward 1.9V → 3.63V) and `dropout_v` is measured as the `Vin`-`Vout`
margin at the `Vin` where `Vout`, decreasing, first falls through 98% of the
1.8V target (`.meas dc ... find v(vin) when v(vout)=1.764 fall=1`) — the
classic "regulation just lost" definition — rather than the old fixed
`Vin=1.9V` endpoint (which measured deep past dropout). The new full
45-point record (`20260825-055423-c000414`, supersedes
`20260818-032811-81dc232`) confirms the screening estimate: at −40°C/27°C,
across all five process corners, `dropout_v` ranges **0.310V–0.554V**
(worst: `ff`/27°C; best: `ss`/−40°C) — still above the DRAFT 300mV target (a
real gap, not a testbench artifact) but well below the raw 530mV–1.79V the
old fixed-endpoint measurement reported. 125°C corners are excluded from
this range for the reason below.

**Mechanism 4 (DC-solution-multiplicity) — diagnosed, not one finding but
two depending on temperature.**

- **At −40°C/27°C: predominantly a `dc`-sweep continuation artifact, not
  genuine circuit bistability.** Independent per-point checks at several
  jump points (a fresh, unseeded `.op` with no sweep-continuation history;
  the same `.op` with a `.ic` seed copied node-for-node from a neighboring
  regulating point; and `.options gminsteps=0` to disable `ngspice`'s
  gmin-stepping homotopy fallback, forcing a direct Newton-Raphson solve)
  reliably reconverge to the *regulating* branch, matching the physically
  continuous curve neighboring corners trace out — i.e. it is the default
  `dc` sweep's continuation path that occasionally lands on a second,
  reachable-but-not-physically-preferred algebraic solution, not a second
  stable equilibrium the real circuit would settle into. These jumps were
  confirmed to never dip below the 1.764V departure threshold at these
  temperatures, so the new `dropout_v` measurement is unaffected by them.
- **At 125°C: markedly worse, and NOT confined to the `ff`/`sf`
  thermal-shutdown false-trip (mechanism 1) — it affects all five process
  corners.** A downward sweep at `tt`/125°C, 50mA frequently fails to find
  or hold the regulating branch at all: independent `.op` checks at
  `Vin=3.51–3.53V` converge to non-physical states (e.g. `FB=-985.7V`,
  `N_FBB=-1974.5V` — exactly the nodes `ngspice`'s "singular matrix"
  warnings already flag), and the continued `dc` sweep produces an outright
  non-physical point (`Vout≈-20.29V`) at the same corner. **Confirmed NOT
  the thermal-shutdown false-trip**: `TS_SNS`/`TS_REF` stay in the correct
  untripped ordering at this `tt`/125°C point. This also **corrects** an
  inaccuracy in mechanism 1's original writeup above ("`ss`, `fs` and `tt`
  do not [show physically-impossible numbers at 125°C]") — the pre-#71
  record (`20260818-032811-81dc232`) already contained
  `tt_125c_3.30v: vout_at_max_vin_v=-20.3922V`, a non-physical number at a
  `tt` corner that mechanism 1's single-point `Vin=3.30V` screening check
  didn't catch because it wasn't itself sweeping `Vin`. `fs`/125°C stayed
  numerically well-behaved across all three supply-corner variants
  (`dropout_v≈0.44V`, consistent with the −40/27°C trend), so a real
  solution is reachable there — this reads as a solver-conditioning problem
  at 125°C, not "no valid regulating solution exists," but it was not
  further isolated within this issue's scope.

**Consequence for reading this record**: `dropout-vs-load`'s 125°C corners
(all five processes — this widens mechanism 1's `ff`/`sf`-only exclusion)
should be read with the same "solver artifact, not a literal measurement"
caution already applied to mechanism 1's numbers, not evaluated as real
dropout results. The −40°C/27°C corners are trustworthy under the new
methodology.

#### #81 resolved: mechanism 4's 125°C severity root-caused — a genuine circuit robustness gap, not a solver-tuning problem (2026-08-25)

**Isolated to two distinct, compounding phenomena, both worse at 125°C than
−40/27°C (screening, reproduced from the committed schematic's own netlist,
not `sim/` evidence):**

1. **Outright Newton non-convergence at many `Vin` points, giving
   physically self-inconsistent garbage.** An independent (no
   sweep-continuation history) `.op` scan at `tt`/125°C/50mA across
   `Vin=3.63V→3.30V` shows values that do not even satisfy the feedback
   divider's own algebra (e.g. `Vin=3.63V`: `Vout=3.320V` with
   `FB=-985.6V` — a passive resistor divider cannot produce a node voltage
   400x its input) at most points tried (`3.63V`, `3.60V`, `3.57V`,
   `3.54V`, `3.53V` all inconsistent), while `Vin=3.52V` alone converges to
   a fully self-consistent point (`Vout=1.798V`, `FB=1.199V`,
   `EA_OUT=2.008V`). This is the direct cause of the campaign's most
   extreme numbers (`FB=-985.7V`, `N_FBB=-1974.5V`, etc.) — not a second
   real solution, just the solver's last unconverged iterate at nodes its
   own "singular matrix" warnings already flag (`ea_cz`/`n_fbb`/`amp_enn`).
2. **A second, genuinely self-consistent, stable equilibrium that a
   settled transient reaches instead of the intended 1.8V point — the
   deeper root cause.** Rather than trusting a single-shot `.op`/`.nodeset`
   result (which mechanism 4's -40/27°C diagnosis already showed can be
   steered by the solver's continuation path, not real dynamics), this
   issue ran a `tran ... uic` with `VOUT`'s own capacitor (`C_OUT`, the one
   node with a true reactive state in this loop) initialized exactly at the
   intended `1.8V` operating point (`.ic v(vout)=1.8 ...`), at
   `Vin=3.60V`/50mA/125°C, run 800µs (long enough to fully settle — final
   values flat to 6 significant figures) — a check that does not depend on
   Newton converging to the "right" branch on the first try, since the
   physically real state variable starts exactly where the intended branch
   says it should be. At every process corner tried this way (`tt`, `ss`,
   `fs`), `VOUT` **reliably drifts away from 1.8V to a different, stable
   equilibrium**: `tt`→`Vout=2.093V` (`FB=1.114V`, `N_FBB=1.048V`),
   `ss`→`Vout=2.014V` (`FB=1.191V`, `N_FBB=1.073V`),
   `fs`→`Vout=2.199V` (`FB=1.286V`, `N_FBB=1.100V`) — all with `EA_OUT`
   mid-rail (not saturated to either supply) and `TS_SNS`/`TS_REF` in the
   correct untripped ordering (confirmed not mechanism 1's thermal-shutdown
   false-trip). **This is a real, reproducible finding, not solver noise**:
   the one true state variable in the loop was placed exactly at the
   intended answer and the circuit's own dynamics carried it somewhere
   else. At this second equilibrium the `FB`:`N_FBB` ratio (≈0.94:1) is far
   from the ≈2:1 a passive divider of three equal resistors
   (`R_FB_A`/`R_FB_B`/`R_FB_C`, all `sky130_fd_pr__res_xhigh_po`) would
   produce, implicating a non-resistive current path into these nodes —
   most likely the same resistor family's body-junction leakage this file
   already flagged as a 125°C convergence hazard ("domain-error convergence
   failures in the `R_CZ` compensation resistor's body-junction model")
   becoming large enough at 125°C (junction leakage is exponential in
   temperature) to measurably distort the divider. Not confirmed to a
   specific model-parameter level — that would need device-level probing
   beyond this issue's screening scope.

**Hardening attempted, did not fix it — supports "genuine circuit
robustness gap," not "needs better solver options":**

- `.nodeset` seeded exactly at the intended 1.8V/1.2V/0.6V point on a plain
  `.op` at `tt`/125°C/`Vin=3.51V`: **no effect** — converges to the
  identical non-physical result as the unseeded run.
- `.options gminsteps=0` (the option that reliably fixes the −40/27°C
  continuation artifact per the diagnosis above): **no effect** at
  `tt`/125°C/`Vin=3.51V` (identical non-physical result), and at
  `ss`/125°C/`Vin=3.51V` combined with `.nodeset` seeding, this option made
  the point **worse** — the solve did not converge at all within 2 minutes
  (versus sub-second solves at −40/27°C), where it timed out and was
  killed.
- A properly self-consistent `.ic`-seeded settled transient (item 2 above)
  is the strongest test available and still does not hold the intended
  branch.

Because the deeper cause (item 2) is a real second stable equilibrium the
closed loop's own dynamics prefer at 125°C/50mA, not a solver-seeding
problem, no harness-level fix (`.nodeset`, `.ic`, `gminsteps`, a per-point
independent `.op` mode) can make `dropout-vs-load`'s 125°C corners produce
trustworthy regulating-branch numbers — **this is recorded as a genuine
circuit robustness gap requiring a design change, not fixed in this
issue.** It most plausibly shares root cause with mechanism 2's
already-documented light-load stability shortfall and the bias-generator/
compensation headroom questions #70 investigated (reverted, no fix shipped)
and **#79** continues — the same generalization mechanism 2's own writeup
above already anticipated ("the pass stage's own pole falling with load
current... unclosable without spending amplifier bias current"), now shown
to be severe enough at 125°C to cost the *existence* of a robust intended
operating point at 50mA, not just phase margin. **Recommendation for
#79**: verify any bias-generator/compensation redesign candidate against
this specific check (a `tt`/`ss`/`fs`/125°C/`Vin≈3.60V`/50mA settled
transient seeded at the intended `Vout`) before considering it a fix for
mechanism 2, since a redesign that only restores phase margin at moderate
temperature would not by itself address this.

**Campaign re-run: not repeated for `dropout-vs-load`.** The just-landed
`20260825-055423-c000414` record already reflects the 125°C-wide exclusion
this issue's diagnosis confirms is correct (and, per the above, not
resolvable by a harness change) — no `experiment.json`/testbench deck
change was made by this issue, so a fresh 45-point run against the
identical deck and PDK pin would reproduce the same numbers, not add
verification value; not run here to avoid a purely-redundant append-only
record. A future campaign naturally supersedes this one once #79 (or a
successor) actually changes the circuit.

**`load-transient` checked, no widened issue found.** Unlike
`dropout-vs-load`'s `dc` sweep, `load-transient` is a transient analysis
that starts from a single computed operating point and applies a load
step, rather than continuation-sweeping across many `Vin` points — the
exact mechanism (a long, ill-conditioned continuation path) implicated
above. The existing record
(`sim/load-transient/records/20260818-032755-81dc232.md`) confirms this
in practice: at 125°C, `tt`/`ss`/`fs` all report plausible, physically
sane `undershoot_v`/`overshoot_v` values (0.157V–0.284V — real spec
misses against the 0.15V DRAFT target, not solver artifacts), while only
`ff`/`sf` show the extreme non-physical values (`undershoot_v` up to
22.29V) mechanism 1's thermal-shutdown false-trip already explains. No
re-run needed — the existing record already answers this issue's
check.

### Bias-generator redesign investigated, reverted (#70)

**Status: investigated, not shipped.** Issue #70 set out to fix the PSRR
shortfall (mechanism 5 above) and the pervasive light-load stability
shortfall (mechanism 2) via a bias-generator and/or compensation redesign,
per its own acceptance criteria's instruction to screen any candidate at a
single corner (PSRR at 1 kHz/100 kHz, phase margin at 0 mA) before
committing to an expensive full 45-point re-run. Two PSRR candidates and
one stability candidate were built and screened; **none was shippable**,
so `ldo_3v3in_1v8out.sch` is **unchanged** by this issue — this section is
the record of what was tried, per this repo's "verification is the
product" discipline (a well-verified negative result is still evidence).
Follow-on work continues in **#79**, seeded with the data below so the
next attempt does not repeat the same failed sizing.

**Candidate 1: self-biased ("beta-multiplier") bias-generator reference.**
The suspected root cause named a bias generator with "no supply-independent
reference or cascode" — the standard textbook fix (e.g. Razavi ch.5) is a
self-biased reference: a PMOS mirror (`M_BIASP1`/`M_BIASP2`) forcing two
NMOS legs' currents equal regardless of `VIN`, with an unequal-width pair
(`M_BIASN2`/`M_SBN2`, `K=4`) plus a degeneration resistor `R_SB` pinning
the equilibrium current to `R_SB` and the device ratio instead of to
`VIN/R`, and a passive startup trickle (`M_ENSTART`/`R_START`) to break the
loop's degenerate `I=0` solution. This was fully implemented in place of
`R_BIAS`/`M_BIASN1`/`M_BIASN2`/`M_BIASP1`.

- *A real bug, found and fixed en route.* Both new resistors (`R_SB`,
  `R_START`) were missing their third (body) `lab_pin` terminal that
  `sky130_fd_pr__res_high_po`/`res_xhigh_po` require — xschem silently
  auto-named the unconnected pin a floating net (`net1`/`net2`) rather than
  erroring, and ngspice reported `"singular matrix: check node net1"` on
  every `.op`. Fixed by tying the body pin to `0`, the same convention
  `R_BIAS` already used.
- *After that fix, the loop still does not settle at its intended
  operating point.* A real transient startup check (`EN` ramping 0→`VIN`
  over a few µs, not a bare cold `.op` — this repo's own established
  convention for exactly this class of question, see "Thermal shutdown"
  and the `enable-shutdown` testbench's rising-edge note in
  `sim/README.md`) settles into a genuine, stable-but-wrong high-current
  branch at every load point tried (`tt`/27°C, `VIN=3.3V`, 0/1/50 mA):
  `NB` pulled to ≈3.297 V (≈`VIN`), `BIASP` pulled to ≈0.673 V, and total
  supply current ≈1 mA at 0 mA external load — over 30× the DRAFT
  `Iq < 30 µA` row, with `VOUT` collapsed to a few hundred µV to a few mV.
  This reproduces from a *settled* transient (500 µs, values steady well
  before the end of the run), not a one-shot `.op` artifact, and is
  independent of `.nodeset` hints biasing the solver toward the intended
  low-current point — the solver keeps returning to the same bad branch.
- *Working, not-fully-proven diagnosis.* `M_BIASN2` (narrow, its gate
  driven externally by `NB`) and the `M_BIASP1`/`M_BIASP2` mirror appear to
  form a positive-feedback path: `NB` rising turns `M_BIASN2` on harder,
  which pulls `BIASP` down, which raises `M_BIASP1`/`M_BIASP2`'s own
  `Vsg`, which mirrors *more* current back into `NB` — reinforcing the rise
  rather than correcting it. A rough hand estimate of the *intended*
  equilibrium (weak inversion, `Vgs1−Vgs2 ≈ n·V_T·ln(K)` with `K=4`, set
  against `R_SB≈1.22MΩ`) lands at tens of nA — three orders of magnitude
  below where the simulated bad branch actually settles — suggesting the
  positive-feedback loop's gain may never actually drop below unity at the
  intended weak-inversion point with this sizing, rather than this being a
  simple startup-kick sizing problem. Confirming that (and re-deriving a
  sizing where the loop gain genuinely does cross unity, a real large-
  signal stability analysis, not a trial-and-error re-tune) is **#79**'s
  scope, not this issue's.

**Candidate 2: cascode only the OTA's own PMOS pull-up mirror.** Narrower
than Candidate 1: keep the original `R_BIAS`-referenced generator
unchanged, and address only the second mechanism #60/#70's root-cause data
named — "the current-mirror OTA's own pull-up path (`M_MIRP1`/`M_MIRP2`)...
unlike the NMOS pull-down side..., the pull-up mirror's reference is
itself referred to `VIN`." Added `M_MIRP1C` (a diode-connected PMOS
stacked below `M_MIRP1`, generating a cascode-bias node `PBC`) and
`M_MIRP2C` (cascoding `M_MIRP2`, gate=`PBC`, inserted between `M_MIRP2`'s
drain and `EA_OUT`) — a standard low-voltage cascode-mirror bias generation
(Razavi ch.9), not a new gain stage (both new turnaround nodes are still
low-impedance/diode-loaded).

- Netlisted cleanly and **regulated correctly at all three DR-002 load
  points** (0/1/50 mA, `tt`/27°C/3.3V: `VOUT` 1.8007–1.8035V), unlike
  Candidate 1 — this alone is a real, isolated, working change.
- **Screened PSRR at 1 kHz did not show a material improvement, and
  regressed at one corner.** Quick 3-corner subset (`tt_27c_3.30v`/
  `ss_-40c_2.97v`/`ff_125c_3.63v`), against the pre-#70 baseline
  (`sim/psrr-dc` record `20260818-015127-01b7905`, 1 kHz: 23.3/23.6/22.4 dB):

  | Corner | Baseline (pre-#70) | Candidate 2 (cascode only) |
  |---|---|---|
  | `tt_27c_3.30v` | 23.3 dB | 23.2 dB (unchanged) |
  | `ss_-40c_2.97v` | 23.6 dB | **17.6 dB (regression)** |
  | `ff_125c_3.63v` | 22.4 dB | 76.6 dB* |

  \*`ff_125c_3.63v` is the thermal-shutdown false-trip corner #69 already
  root-caused — its high number is AC gain around a collapsed,
  non-regulating bias point, not real PSRR headroom, in either record.
  100 kHz PSRR improved modestly at `ss` (37.0 dB vs. the baseline record's
  31.7 dB) but both already clear the 20 dB bound there, so it changes no
  verdict. Given no material 1 kHz improvement and an outright regression
  at one corner, this candidate was **not committed** either.
- *Working theory for why cascoding the feedthrough path did not help.*
  1 kHz sits well below this bias point's own loop crossover — the
  0 mA/1 mA points' crossover is far lower than the 50 mA/0.33 µF corner's
  measured 150–190 kHz (see "Compensation (sized in #25)"), so PSRR at
  1 kHz is more likely **loop-gain-limited** than feedthrough-limited at
  this bias point, consistent with this file's existing "PSRR at a given
  frequency tracks loop gain at that frequency" note. Cascoding a
  feedthrough path that is not the dominant term at 1 kHz would not be
  expected to move the number much either way — which is what was measured.

**Candidate 3 (stability side): a preload resistor from `VOUT` to
ground.** Per #70's own "Suspected Cause" (b), raising the light-load pass
current should raise `gm_pass` and push the pass-stage pole up in
frequency, directly targeting the documented 15–24° 0 mA phase-margin
shortfall.

- A hand-rolled AC screening deck (fresh cold `.op`, `RLOAD` swept from
  1 MΩ down to 100 kΩ in parallel with the internal feedback divider, not
  routed through `corner-run.py`) showed the loop crossover frequency
  rising markedly — 283 Hz → 1647 Hz, ~5.8× — as total quiescent current
  rose from ≈13 µA to ≈31 µA. Directionally promising.
- **This result is not trustworthy evidence for the real 0 mA branch,
  and was not further pursued in this pass.** A real `sim/loop-gain
  --quick` corner run against the identical (Candidate-2, then fully
  reverted) schematic measured `pm_c033_0ma_deg` = 19.19°/15.64° at
  `tt`/`ss` — matching this file's already-documented baseline almost
  exactly. But the hand-rolled deck's own phase-margin figure at the
  nominal same operating point computed to ≈177°, wildly different. The
  most likely explanation: `corner-run.py`'s deck reaches the 0 mA point
  by `alter`-ing `rload` down from the 50 mA point's already-converged
  operating point, while the hand-rolled deck solved a fresh cold `.op`
  directly at the light-load point — and this schematic already has a
  documented DC-solution-multiplicity finding (mechanism 4 above, sibling
  issue **#71**'s scope) where a cold solve and an alter-continuation
  solve can land on different valid branches for the same nominal bias
  condition. **The crossover-frequency trend is real evidence the preload
  current changes the small-signal behaviour, but it was measured on a
  branch that is not confirmed to be the same branch the documented
  15–24° PM shortfall lives on**, so it is not treated as a validated fix
  here.
- Independent of that ambiguity, the `Iq` headroom for any preload is
  tight regardless: "Quiescent and shutdown current" above measures
  24.9 µA at 50 mA against the DRAFT `Iq < 30 µA` row, leaving only ≈5 µA
  of room for a preload that adds current at *every* load point (not just
  at 0 mA) before that row itself would be missed.

**Net effect on the DRAFT spec rows.** PSRR and Stability remain **open**,
exactly as mechanisms 2 and 5 in the campaign section above describe —
this investigation did not close either. Per `CLAUDE.md`'s "a row that
proves unmeetable is superseded by a new decision record, never silently
loosened" discipline, no DRAFT row was touched: both the 50 dB PSRR row
and the 45° Stability row stand as written, and the two screened-but-
rejected candidates above are recorded as real, if negative, findings
rather than folded into a claim of progress. **#79** carries the
investigation forward with this section's data as its starting point.

### Self-biased bias-generator re-derived and fixed; preload re-validated against the real branch — neither closes PSRR/Stability (#79, 2026-08-25)

**Status: both candidates investigated to a real, verified conclusion;
`ldo_3v3in_1v8out.sch` is unchanged by this issue too.** #70's own writeup
left two open threads: (1) whether Candidate 1's self-biased reference
could be *fixed* rather than merely re-tuned (its own working diagnosis:
"this needs a genuine large-signal loop-gain/stability re-derivation... not
a trial-and-error re-tune"), and (2) whether Candidate 3's preload-resistor
trend was real on the *actual* branch `sim/loop-gain`'s corner runner
reaches (its own finding: measured on a branch "not confirmed to be the
same branch the documented 15-24° PM shortfall lives on"). This issue
resolves both questions — (1) with a genuine fix, (2) with a real
negative result — and neither, once resolved, closes the PSRR or
Stability DRAFT rows.

#### 1. Self-biased reference: root-caused #70's regenerative-loop defect and fixed it

**Root cause, derived by hand before any resizing (per this issue's own
scope instruction).** #70's Candidate 1 wired the textbook beta-multiplier
with `M_BIASN1` (diode-connected, drain=gate=`NB`) as the *wide* (`K=4`)
device and `M_BIASN2` (externally driven, gate=`NB`, drain=`BIASP`) as the
*narrow*, source-degenerated-by-`R_SB` device. Writing the loop's DC
small-signal return ratio around `NB` (`M_BIASP1`/`M_BIASP2` PMOS mirror,
ratio `m`, closing the loop back into `NB` through the diode-connected
NMOS) gives, in the strong-inversion square-law approximation:

```
LG(m, K) = sqrt(m/K) + 2*(1 - sqrt(m/K))   [R_SB on the WIDE/diode leg]
         = 2 - sqrt(m/K)
```

For a 1:1 PMOS mirror (`m=1`, the natural default and what #70 built),
`LG = 2 - 1/sqrt(K)`, which is **strictly greater than 1 for every `K>1`**
— this specific device-role assignment is *structurally* regenerative, not
merely mis-sized. That single derivation explains #70's entire finding:
the loop was never going to settle at its intended few-µA point regardless
of which `K`/`R_SB` values were tried, because the topology as wired makes
the intended equilibrium an unstable fixed point (a latch, not a
regulator) — consistent with the ~1mA rail-clamped branch #70 actually
measured.

**The fix: put `R_SB` on the externally-driven (narrow) leg instead of the
diode leg, and re-derive.** Re-deriving the same loop with `R_SB` moved to
`M_BIASN2`'s source (leaving `M_BIASN1` an *undegenerated* diode) and
solving the same KVL/KCL gives a materially different result:

```
LG(m, K) = sqrt(m/K) / (2*sqrt(m/K) - 1)          [R_SB on the NARROW/driven leg]
```

This is monotonically *decreasing* in `r = sqrt(m/K)`, from `LG=1` at the
`m=K` boundary down to `LG->0.5` as `m/K->infinity` — i.e. **any mirror
ratio `m` exceeding the width ratio `K` gives `LG<1`**, the opposite
requirement from the failed placement, and with a comfortable design
margin available (not just barely crossing 1). This also resolves the
apparent contradiction in the R_SB-placement choice: with `R_SB` on the
diode leg, a physically valid (`R_SB>0`) solution requires `m<K`, which is
incompatible with `LG<1`(`m>K`) — the two requirements can never both hold
for that placement, which is *why* Candidate 1 could not have been fixed
by resizing alone, only by moving the resistor.

**Verified in SPICE (sky130 device models, not just the hand square-law
formula) three independent ways, per this issue's "not just `.op`/`.tran`"
instruction:**

1. **`.dc` loop-break sweep of the candidate feedback node**, `K=1`
   (`M_BIASN1`/`M_BIASN2` both `W=4 L=1`, no width mismatch needed — the
   derivation above shows only the ratio `r=sqrt(m/K)` matters, so `K`
   does not need to be large), `m=1.7` (`M_BIASP2` `W=17 nf=2` vs.
   `M_BIASP1`'s `W=10 nf=2`), `R_SB` tuned (`res_high_po` `W=0.42 L=16`,
   ~13.8kΩ) to reproduce the pre-#79 design's own `BIASP`/`I1` operating
   point (see below). Breaking the loop at `NB` and sweeping an
   independent drive from 0V to `VIN` finds **exactly one self-consistent
   crossing** across the full range (`NB_drive ≈ NB_out ≈ 0.89V`) with a
   measured local return-ratio slope of **0.74** — matching the hand
   estimate (`LG≈0.81` at this `m`,`K`) in both sign and rough magnitude,
   and confirming *no second (bad) branch exists anywhere in the swept
   range* — unlike #70's Candidate 1, which settled onto a real,
   reachable second branch.
2. **A settled transient startup check** (`EN` ramping 0→`VIN` over 1-3µs,
   the same convention #70 used and #70's Candidate 1 failed), with a
   passive startup trickle `R_START` (`res_high_po` `W=0.42 L=10000`,
   ~8.1MΩ, `VIN`→`NB` — replacing #70's reverted switched
   `M_ENSTART`/`R_START`; self-quenches at `EN=0` the same way the
   original `R_BIAS` did, since `M_ENN` cutting `M_BIASN1`'s ground return
   lets `NB` float to `VIN`, leaving 0V across `R_START` too): settles
   within ~3µs to `NB=0.900V`, `BIASP=2.237V` and holds flat through
   500µs — matching the `.op`/loop-break equilibrium, not a rail-clamped
   branch.
3. **A 15-point process×temperature spot-check** (`{tt,ss,ff,sf,fs}` x
   `{-40,27,125}°C`, `VIN=3.3V`, `.op` with a `.nodeset` near the expected
   point to work around a `125°C` cold-Newton convergence slowness this
   circuit shares with the rest of the schematic — see "#71/#81 resolved"
   above for the same phenomenon on the main loop): every corner converges
   to a physically sane point, `I1` ranging **1.46-3.56µA** monotonically
   with temperature and only mildly with process — no runaway branch found
   at any of the 15 points.

**Sizing was chosen to reproduce the pre-#79 operating point, not to
minimize current.** The pre-#79 `R_BIAS`-referenced design measures
`NB=0.864V`, `BIASP=2.236V`, `I1≈2.0µA` (`tt`/27°C/`VIN=3.3V`, `M_BIASP1`
unchanged `W=10 nf=2` in both designs) — `M_TAIL`/`M_CLP`/`M_SSCHG`/
`M_TSPS`/`M_TSPR`/`M_TSHYSB` all mirror off `BIASP`'s *voltage*, not off
`I1` directly, so matching `BIASP` (not just qualitatively "a few µA")
keeps every downstream bias current within its pre-#79 value and avoids
re-triggering #22's current-limit/soft-start timing or #25's compensation
sizing, which is out of this issue's scope. The chosen `R_SB`/`m` hit
`BIASP=2.238V`/`I1=2.05µA` at `tt`/27°C — a close match. The unavoidable
cost of the fix is the second leg's own current, `I2≈m*I1≈3.2-3.4µA`
(measured via total `VIN` current minus `I1`), which the pre-#79 topology
did not have to pay (a single-leg resistor reference has no second leg).
Against "Quiescent and shutdown current" above (24.91µA measured at
50mA/3.63V against the DRAFT `Iq<30µA` row, ~5µA headroom), this ~3.3µA
addition is real but survivable in isolation.

**Does not move PSRR or 0mA phase margin — the reference-loop-stability
question and the PSRR/Stability spec gaps are different questions.**
Per this issue's own instruction ("re-screen PSRR at 1kHz/100kHz and 0mA
phase margin... before committing to any full 45-point re-run"), this
candidate was screened with the schematic edit actually in place (single
run, then reverted — see below) against the same 3-corner quick subset
#70 used:

| Corner | Baseline PSRR@1kHz (pre-#70/#79) | This candidate |
|---|---|---|
| `tt_27c_3.30v` | 23.3dB | 23.5dB (unchanged) |
| `ss_-40c_2.97v` | 23.6dB | **22.3dB (regression)** |
| `ff_125c_3.63v` | 22.4dB* | 76.6dB* |

\*`ff_125c_3.63v` is the #69 thermal-shutdown false-trip corner in both
records — not real PSRR evidence either way, same caveat as #70's table.

`pm_c033_0ma_deg` (0mA phase margin, `loop-gain --quick`): `tt=19.65°`,
`ss=14.63°` — statistically identical to the already-documented baseline
(`19.19°`/`15.64°`), not the material improvement a shippable candidate
would need. A standalone VIN-sensitivity check of the reference current
itself (independent `.op` at `VIN={2.97, 3.3, 3.63}V`, avoiding the same
`.dc`-continuation-branch pitfall "#71/#81 resolved" flags) shows a real
but modest reduction in `I1`'s own fractional VIN-sensitivity — **26.3%
(baseline `R_BIAS`) → 16.1% (this candidate)** across the ±10% `VIN`
window, roughly a 4dB improvement referred to the bias current alone —
but `BIASP`'s own *voltage* still tracks `VIN` at ~0.98V/V in both
designs (an inherent property of a PMOS-diode-referenced rail, not fixed
by what sets the diode's current), so the downstream mirror gate rail
still passes most of any `VIN` ripple through. This is consistent with
this file's own pre-existing diagnosis ("PSRR at a given frequency tracks
loop gain at that frequency") and with #70's Candidate 2 finding (cascoding
a feedthrough path that is not dominant at 1kHz does not move the number)
— **1kHz PSRR here is genuinely loop-gain-limited, and a bias-generator
supply-rejection fix, however well-verified its own internal stability is,
does not reach the actual bottleneck.** `pm_c033_0ma_deg` is independently
already explained by this file's "pass stage's own pole falling with load
current" mechanism (see the 45-point campaign section above), which a
bias-generator change does not touch either.

**Net effect: reverted, per the same "no material improvement -> not
committed" discipline #70 used for its own Candidate 2.** The derivation
and verification above are recorded as a genuine, useful result in their
own right — the open question of *whether a stable self-biased reference
is achievable for this topology at all* is now answered (yes, with `R_SB`
on the correct leg and `m>K`), closing that specific thread #70 left open
— but since it does not move either target metric and costs real,
non-refundable `Iq` budget (~3.3µA against a ~5µA headroom) for no
measured benefit, it is not shipped. `ldo_3v3in_1v8out.sch` is unchanged.

#### 2. Preload resistor: re-validated against the real corner-runner branch — does not cleanly fix it either

**Per this issue's scope, re-validated against `sim/loop-gain`'s actual
`corner-run.py` deck** (which reaches the 0mA point via `alter rload`
from the already-converged 50mA operating point — see its
`experiment.json`), not #70's hand-rolled cold-`.op` deck. A screening
`R_PRELOAD` (`res_xhigh_po`, `VOUT`->`0`) was added to the schematic (not
part of any shipped change — reverted after screening, see below) and run
through `sim/loop-gain --quick` at two sizes:

| Measurement | Baseline (no preload) | `R_PRELOAD≈300kΩ` (~6µA) | `R_PRELOAD≈600kΩ` (~3µA) |
|---|---|---|---|
| `tt_27c_3.30v` `pm_c033_0ma_deg` | 19.31° | **22.67° (+3.4°)** | 19.24° (~unchanged) |
| `tt_27c_3.30v` `pm_c47_0ma_deg` | 52.03° (PASS) | **20.12° (regression, now FAIL)** | 24.39° (regression, now FAIL) |
| `ss_-40c_2.97v` `pm_c033_0ma_deg` | 15.60° | **24.14° (+8.5°)** | 19.67° (+4.1°) |
| `ss_-40c_2.97v` `pm_c47_0ma_deg` | 38.06° | **16.88° (regression)** | 19.30° (regression) |

The 300kΩ preload's `pm_c033_0ma_deg` improvement (#70's own hoped-for
result, now confirmed real on the branch that matters, closing #70's own
"not confirmed to be the same branch" caveat) is genuine — but it comes
at the cost of a *larger* regression at the 4.7µF/0mA corner, which
**passed** at baseline and now fails by a wider margin than the 0.33µF
corner used to fail by. The 600kΩ (lighter) preload nearly eliminates
both the gain and the damage, netting out close to a wash. **Working
explanation, consistent with this file's own existing "two-sided
optimum, not a bigger-is-better knob" note about `R_CZ`:** the preload's
extra `gm_pass` shifts the pass-stage's output pole relative to the fixed
compensation zero (`R_CZ`/`C_COMP`) differently depending on `C_out`,
improving the pole/zero spacing at 0.33µF (where the pole was too low)
while worsening it at 4.7µF (where the pole was already reasonably
placed and gets pushed past the zero the other way) — a single passive
preload current cannot independently tune both corners of DR-002's
C_eff window at once, the same structural limit a fixed-value `R_CZ` has.

**Iq cost is real and, like the self-biased candidate, not free**: 300kΩ
costs ≈6µA and 600kΩ ≈3µA against the same ~5µA headroom "Quiescent and
shutdown current" above measures, present at *every* load point (not
just 0mA) as #70 already flagged — on top of costing budget, neither size
is a clean net win on phase margin. **Net effect: reverted, not shipped.**
`ldo_3v3in_1v8out.sch` is unchanged.

**What this resolves for #70's own open question.** #70 could not tell
whether its promising crossover-frequency trend was measured on the real
branch. It now is confirmed to be real *and* to genuinely raise
`pm_c033_0ma_deg` on the actual `sim/loop-gain` branch — but that trend
alone was never sufficient evidence of a net fix, and checking it against
the DR-002 window's *other* corner (`pm_c47_0ma_deg`) — which #70's
screening never covered — shows why: a preload is a one-parameter knob
being asked to fix a two-corner problem.

**Net effect on the DRAFT spec rows.** PSRR and Stability remain **open**,
same as after #70. Both avenues #70 identified as promising have now been
carried to a definitive, verified conclusion (one fixed a real defect but
does not move the metric; one is confirmed real on the correct branch but
does not net a clean win) rather than left as an open question for a
future issue to re-litigate. Per `CLAUDE.md`'s discipline, no DRAFT row
is touched. **What remains unexplored**, based on this and #70's combined
findings: closing `pm_c033_0ma_deg`/PSRR appears to require spending
additional amplifier-side (not bias-generator- or preload-side) `Iq` —
directly raising `M_TAIL`'s own tail current, which issue #25's own
"Quiescent and shutdown current" section already measured as effective
("keeps improving the no-load phase margin, up to ~40°" at 6x `M_TAIL`)
but rejected for exceeding the DRAFT `Iq` row (33.6µA vs. 30µA) — meaning
a durable fix plausibly needs either a compensation/amplifier topology
change that does not cost `Iq` linearly, or a revisit of the DRAFT
`Iq<30µA` row itself once issue #1 ratifies the spec (a decision this
repo's `CLAUDE.md` reserves for a spec decision record, not a Builder
default). Filing a further follow-on issue for that specific, narrower
question is left to Curator/human triage rather than decided here.

### Thermal-shutdown trip/hysteresis testbench ships (issue #66, 2026-08-25)

The Thermal DRAFT spec row's evidence gap — no dedicated `sim/` testbench for
the thermal-shutdown circuit's (#29/DR-005) actual trip/reset behavior — is
now closed by `sim/thermal/`. Two things had to happen first, per this
issue's own acceptance criteria:

1. **The 125 °C-vs-150 °C corner-coverage decision.** DR-005's Consequences
   section named this gap in advance: DR-004 pins this repo's PVT-corner
   verification temperature axis at `{−40, 27, 125} °C`, but DR-005's
   150 °C nominal trip target sits above it. **Decided: extend, scoped to
   this one testbench** — see DR-005's `2026-08-25 addendum` for the full
   reasoning, the empirical check that justified it, and the accepted
   tradeoff (points above 125 °C run the pinned models in extrapolation
   beyond DR-004's characterized range). This does not touch DR-004's
   binding for `load-transient`/`psrr-dc`/`dropout-vs-load`/`loop-gain`.
2. **An ngspice measurement-technique pitfall, found and worked around
   before the authoritative record.** `.meas dc ... find/when ... fall=1`
   returns a nonsensical result (observed: `1.15e7` instead of ≈`101`) when
   the crossing falls inside the sweep's very first interval. The first
   run (`20260825-050729-6fac47d`, superseded) hit this at `sf_27c_3.30v`
   with a 100 °C sweep floor; widening the floor to 80 °C (safely below
   every corner's actual trip point) fixed it for the authoritative record.
   See `sim/thermal/experiment.json`'s own comments for the full writeup —
   this is a testbench/tooling limitation, not a circuit finding.

**Method**: a continuous ngspice `.dc temp` sweep, 80→180 °C ascending then
180→80 °C descending in one session (DC continuation, so the descending leg
starts from the ascending leg's final operating point — the standard
technique for characterizing a hysteretic comparator's two trip points),
watching `V(VOUT)` collapse (trip) and recover (reset, auto-restart) across
the full `process × supply_v` matrix (`temperature_c` is a fixed manifest
placeholder — the real temperature axis is the swept analysis variable, not
a corner-matrix dimension, so `sim/thermal`'s auto-generated record's "Full
PVT matrix declared..." line renders the standard −40/27/125 °C boilerplate
inherited from the shared harness; read the experiment's own `claim` and
this section for the accurate picture instead).

**Authoritative record**: `sim/thermal/records/20260825-054043-6fac47d`
(supersedes `20260825-050729-6fac47d`), full 15-point `process × supply_v`
matrix:

| Corner | `trip_temp_c` | `reset_temp_c` | `hysteresis_c` | Verdict |
|---|---|---|---|---|
| `tt_27c_2.97v` | 135.0 | 137.0 | −2.0 | FAIL (hysteresis) |
| `tt_27c_3.30v` | 135.0 | 137.0 | −2.0 | FAIL (hysteresis) |
| `tt_27c_3.63v` | 135.0 | 135.0 | 0.0 | PASS |
| `ss_27c_2.97v` | 149.0 | 157.0 | −8.0 | FAIL (hysteresis) |
| `ss_27c_3.30v` | 145.0 | 145.0 | 0.0 | PASS |
| `ss_27c_3.63v` | 145.0 | 149.0 | −4.0 | FAIL (hysteresis) |
| `ff_27c_2.97v` | 121.0 | 121.0 | 0.0 | FAIL (trip < 125 °C) |
| `ff_27c_3.30v` | 117.0 | 123.0 | −6.0 | FAIL (trip < 125 °C, hysteresis) |
| `ff_27c_3.63v` | 115.0 | 121.0 | −6.0 | FAIL (trip < 125 °C, hysteresis) |
| `sf_27c_2.97v` | 99.0 | 105.0 | −6.0 | FAIL (trip < 125 °C, hysteresis) |
| `sf_27c_3.30v` | 101.0 | 101.0 | 0.0 | FAIL (trip < 125 °C) |
| `sf_27c_3.63v` | 95.0 | 105.0 | −10.0 | FAIL (trip < 125 °C, hysteresis) |
| `fs_27c_2.97v` | 165.0 | 165.0 | 0.0 | PASS |
| `fs_27c_3.30v` | 167.0 | 167.0 | 0.0 | PASS |
| `fs_27c_3.63v` | 165.0 | 165.0 | 0.0 | PASS |

**Overall: FAIL (5/15 PASS)** — an honest, expected finding given #69 was
already open before this testbench existed. Two distinct findings:

1. **Confirms and substantially quantifies #69.** `ff` trips at
   115.0–121.0 °C and `sf` at 95.0–101.0 °C — both process corners fall
   below the spec's own 125 °C operating ceiling at **every** supply corner
   tested, more severe than #69's single confirmed `.op` point (`ff`/125 °C/
   3.30 V) suggested. `tt` (135.0 °C), `ss` (145.0–149.0 °C) and `fs`
   (165.0–167.0 °C) all trip comfortably above 125 °C — `fs` in fact trips
   *above* the 150 °C nominal target. Still #69's job to fix, not re-scoped
   here.
2. **New finding, filed as #77: measured hysteresis is non-positive at every
   one of the 15 corners.** DR-005's Decision requires `reset_temp_c` to sit
   *below* `trip_temp_c` (auto-restart only after cooling further than the
   trip point). The data shows the opposite or a wash at every corner tested
   — `reset_temp_c ≥ trip_temp_c` at 10/15, exactly `0 °C` measured
   hysteresis at the remaining 5. See DR-005's `2026-08-25 addendum` and #77
   for the full writeup; not fixed by this issue.

### #77: thermal-shutdown hysteresis root-caused — a marginal regenerative loop gain, not a simple sign error (investigated, not shipped, 2026-08-25)

**Status: investigated, not shipped.** #77 set out to determine whether the
non-positive hysteresis the `#66` section above measured at every one of 15
corners is a real circuit-sizing defect or a DC-continuation
measurement-methodology artifact, and to fix it if a real defect was found.
**Answer: both, and neither cleanly** — a genuine but *marginal*
(corner-dependent) regenerative loop gain around `M_TSHYS`'s current
injection into `TS_REF`, which the default measurement technique also
mismeasures. `ldo_3v3in_1v8out.sch` is **unchanged** by this issue — this
section is the record of what was found and tried, per this repo's
"verification is the product" discipline, the same shape as the
"Bias-generator redesign investigated, reverted (#70)" section above.
Follow-on work continues in **#91**, seeded with this section's data.

**Diagnostic 1 — a nodeset-forced bistability probe proves a real (if
narrow) hysteresis window exists at `tt_27c_3.30v`, and that the default
sweep loses it.** At `T=134°C` — one 2°C grid step below the vanilla `.dc
temp` sweep's measured 0°C-hysteresis crossing (135°C) — an independent
`.op` seeded with a `.nodeset` biasing every hysteresis-path node toward the
*tripped* state converges to a genuine, self-consistent tripped solution:
`V(TS_REF)`≈1.065V (matching this same corner's naturally-tripped value at
`T=136°C`, ≈1.064V, and matching the schematic's own "raising the reference
by tens of mV" design-intent comment above — the boost mechanism does
exactly what it was designed to do), `V(TS_CMP)`≈0.48V (tripped),
`V(VOUT)`≈0 (collapsed). The default sweep's Newton continuation — despite
starting from the immediately-prior tripped point at 136°C — does not track
this branch, reconverging to the untripped branch at the very next 2°C step
instead. Re-running with `.options gminsteps=1` (reducing ngspice's default
gmin-stepping homotopy fallback — the same option the `#71`/`#81` section
above already found disrupts DC continuation on this schematic for an
unrelated bistability question) surfaces the real branch: measured
hysteresis flips from 0°C to a small, correctly-signed **+2°C**
(`trip_temp_c=133°C`, `reset_temp_c=131°C`) at this one corner.

**Diagnostic 2 — a fine-grid re-sweep at the worst-offending corner shows no
clean crossing exists at all.** `ss_27c_2.97v` (screening-reproduced against
current `HEAD`: `trip_temp_c≈147°C`, `reset_temp_c≈157°C`,
`hysteresis_c≈−10°C` — a couple of degrees off the
`20260825-054043-6fac47d` record's `149°C`/`157°C`/`−8°C` for this corner,
plausibly that record's own noted "working tree dirty at run time" rather
than a schematic difference; `git log 6fac47d..HEAD --
design/ldo_3v3in_1v8out.sch` returns no commits) does **not** show a clean
single crossing in either sweep direction even at a 0.25°C grid: `V(VOUT)`
flickers erratically between the tripped (~0V) and untripped (~1.8V) states
across a ~12°C-wide band (144–156°C on the ascending leg), including at
least one spurious intermediate operating point (~2.98V — matching neither
the regulated nor the tripped state), which a converged DC solve should not
produce. `.options gminsteps=1` does **not** resolve this corner (hysteresis
stays ≈−10°C) — unlike `tt_27c_3.30v`, this corner's loop gain is apparently
close enough to unity that the algebraic DC system has no single
well-defined answer over a wide band, not merely a narrow window the default
methodology loses track of.

**Interpretation: one root cause, two failure signatures.** A marginal,
corner-dependent regenerative loop gain explains both patterns the `#66`
section's table shows: the exact-`0°C` corners (`tt_27c_3.63v`,
`ss_27c_3.30v`, all three `fs` corners) most plausibly have a narrow, real,
correctly-signed window the default continuation-plus-gmin-stepping
methodology loses (as demonstrated for `tt_27c_3.30v` above); the strongly
negative corners (`ss`, `ff`, `sf` at several supplies) most plausibly sit in
a genuinely marginal/flickering regime where no single crossing is
well-defined and the first-crossing `.meas` reports whichever branch the
solver's exact numerical path happens to land on.

**Hardening attempted at `ss_27c_2.97v`, none shippable:**

- Scaling `M_TSHYSB`'s injected current 2×/3×/4×/13×/20×/30× the baseline
  width (`W=1.5, L=2`): none produced a clean, well-separated,
  correctly-signed trip/reset pair. Because `M_TSHYS`'s pre-trip "off"
  conduction is not exactly zero — the comparator's own finite gain lets
  `TS_CMP` droop gradually as the die approaches the crossing, so
  `Vsg(M_TSHYS)` is not exactly 0 pre-trip — a larger `M_TSHYSB` also couples
  progressively more current into `TS_REF`'s *pre-trip baseline*, dragging
  the entire transition colder as the boost grows (trip fell from ≈147°C at
  baseline to ≈95–97°C at the largest boosts tried). At those magnitudes
  this pushes the trip point well below the already-open #69 floor
  violation — worsening that finding rather than fixing this one
  independently.
- Strengthening the comparator's own gain instead (4× `M_TCTAIL`'s tail
  current, `W=1→4`, injection current unchanged): reduced but did not
  eliminate the sign inversion (−10°C → −4°C) without the trip-point
  collapse the injection-current approach caused — directionally the more
  promising of the two single-knob attempts on its own. Combining it with
  even a modest (2×, `W=1.5→3`) injection increase made the result *worse*
  (−12°C), evidence this is a multi-parameter loop-gain problem, not a
  single-knob fix reachable by trial-and-error sizing within this issue's
  own screening budget.

**Net effect.** Per `CLAUDE.md`'s "a row that proves unmeetable is
superseded by a new decision record, never silently loosened" discipline, no
DRAFT row or DR-005 Decision text is touched — DR-005's own `2026-08-25`
addendum (second one) records the same finding formally. This needs a
genuine large-signal loop-gain redesign of the trip-comparator/hysteresis
cluster (most plausibly a real regenerative latch/Schmitt-style element,
rather than a linear current injected into a diode-connected reference node
whose own DC operating point that same injection perturbs) — **#91** carries
the investigation forward with this section's data as its starting point.
**No new `sim/thermal` record was minted**: neither the testbench deck nor
the circuit changed, so a fresh 15-point run against the identical schematic
and PDK pin would reproduce the same numbers, not add verification value
(the same "no purely-redundant record" reasoning the `#71`/`#81` section
above already applied to `dropout-vs-load`) — `20260825-054043-6fac47d`
remains the authoritative record, and
`measurements/build_characterization_report.py --check` still passes
against it unchanged. **#69 unaffected**: none of the hardening attempts
above were shipped, so #69's own (still-open) `ff`/`sf` nuisance-trip
finding is neither worsened nor improved by this issue landing.

#### What the #69 re-run changed (2026-08-25): mechanism 1 closed, campaign re-run

Issue #69 re-sized the thermal shutdown (see "Sizing the trip: what is a
knob and what is not" above) and re-ran **every** experiment that
instantiates this schematic, because changing the shared DUT invalidates all
of their netlist snapshots at once. New append-only records, all pinned to
`4cb27f8`, each carrying a `Supersedes` pointer at the record it replaces:

| Experiment | Superseded record | New record | Verdict |
|---|---|---|---|
| `dropout-vs-load` | `20260818-032811-81dc232` | `20260825-081240-4cb27f8` | 0/45 → **0/45** PASS |
| `load-transient` | `20260818-032755-81dc232` | `20260825-081255-4cb27f8` | 23/45 → **25/45** PASS |
| `loop-gain` | `20260818-032819-81dc232` | `20260825-081257-4cb27f8` | 3/45 → **7/45** PASS |
| `psrr-dc` | `20260818-032803-81dc232` | `20260825-082845-4cb27f8` | 6/45 → **0/45** PASS (see below — this is a *correction*, not a regression) |
| `current-limit` | `20260825-045313-703a889` | `20260825-082847-4cb27f8` | 2/3 → **3/3 PASS, overall PASS** (3-point subset) |
| `startup` | `20260825-044139-703a889` | `20260825-082906-4cb27f8` | 3/3 → 3/3 PASS (3-point subset) |
| `enable-shutdown` | `20260825-044140-703a889` | `20260825-082908-4cb27f8` | 3/3 → 3/3 PASS (3-point subset) |
| `mc-output-accuracy` | `20260818-032827-81dc232` | `20260825-083111-4cb27f8` | 181/200 → 177/200 samples PASS, overall still FAIL |

**Every non-physical number mechanism 1 was blamed for is gone.** Not one of
the six `ff`/`sf`-at-125°C corners produces an out-of-range value in any of
the three campaigns any more:

| Quantity | Before (#60's evidence) | After (#69's re-run) |
|---|---|---|
| `dropout-vs-load` `dropout_v`, 45-corner range | 0.365 … **32.59 V** | 0.365 … **1.548 V** (no corner above 2 V; was 3) |
| `dropout-vs-load` `vout_at_max_vin_v`, negative values | **−19.2 V, −20.4 V, −29.0 V ×3** | **none** — every corner is now positive and physical |
| `load-transient` `undershoot_v`, 45-corner range | 0.102 … **22.29 V** | 0.102 … **0.393 V** (no corner above 1 V; was 6) |
| `loop-gain` measurements returning `n/a` | 6–9 corners per measurement | **0** |
| `loop-gain` `dcgain_c033_50ma_db`, 45-corner range | **−349.7** … 61.72 dB | **56.33 … 61.72 dB** |
| `loop-gain` `pm_c033_50ma_deg` failures | 6/45 (all the degenerate corners) | **0/45** |
| `current-limit` at `ff`/125°C/3.63 V | output collapsed to ~2 µV, ~0 mA of limit current, **FAIL** | regulates at **1.7977 V**, 148 mA short-circuit level, **PASS** |

**Three results in that table need reading carefully rather than
celebrating.**

- **`psrr-dc` went from 6/45 to 0/45 PASS, and that is the report becoming
  *more* accurate.** All six of the old "passes" (76–105 dB at 1 kHz) were
  the falsely-tripped corners — AC gain measured around a collapsed,
  non-regulating bias point, which #60 already flagged as not-real PSRR
  ("on the evidence available, PSRR does not actually pass anywhere"). With
  the trip gone those corners return honest numbers and the whole 1 kHz
  column collapses to **20.31–25.68 dB** (was 20.31–76.79 dB) against the
  50 dB DRAFT bound. #60's inference is now a measurement. Mechanism 5
  (#70) is untouched and unchanged by this fix.
- **`load-transient` gained four corners and lost two.** The two that
  regressed (`ff_27c_3.30v`, `ff_27c_3.63v`) did not get a worse transient
  — they moved onto the anomalous DC branch mechanism (4) describes. That
  branch is identifiable in the data: it is exactly the set of corners
  reporting `overshoot_v ≈ 0`, and it **shrank from 9/45 corners to 4/45**.
  Within the healthy branch every corner now measures `undershoot_v ≤
  0.268 V`; before, the same branch spanned up to 22.29 V. So the net
  movement is a smaller anomalous set and a strictly smaller spread, with
  two corners' membership reshuffled — a mechanism-(4)/#71 effect, not a
  transient regression.
- **`mc-output-accuracy` moved slightly the wrong way (181 → 177 of 200
  samples) and that is expected to be noise, not signal.** Its single
  sampled point is `tt`/27°C/1 mA, where the thermal clamp never tripped
  under any sizing, so #69 cannot help it; changing the DUT simply
  reshuffles which mismatch draws land on mechanism (4)'s non-regulating
  branch. The distribution actually tightened (stddev 2.154 → 1.544 V, worst
  outlier −19.3 → −18.8 V) while the individual-sample count moved the other
  way. Mechanism 6 still closes with #70/#71, not here.

**What is still open after #69.** Mechanisms 2, 4, 5 and 6 above are
untouched by this fix: `psrr-dc` is now honestly 0/45 (#70/#79),
`loop-gain`'s light-load `pm_c033_0ma` column still fails 36/45 (#70/#79),
`mc-output-accuracy`'s tail still fails its sigma window, and mechanism 4's
125 °C non-regulating equilibrium — root-caused above as a genuine circuit
robustness gap, with its fix deferred to **#79** — is untouched too and is
what moves two `load-transient` corners in the table above. Mechanism 3 is
no longer open: #71/#83 fixed `dropout-vs-load`'s `dropout_v` methodology
while this branch was in flight (see the "#71/#81 resolved" section above),
though the row is still `FAIL` — 0/45 before and after, on either method.
**The one DRAFT row #69 does move all the way is Current limit**, whose
only failing corner was this nuisance trip read through a resistive load.

Two further gaps #69 opens rather than closes, both named and neither
hidden: the layout (`layout/ldo-core`) has **not** been redrawn for the new
device sizes, so its DRC/LVS records join the already-stale PEX record in
being correctly reported `STALE` by `measurements/characterization.md`
(**issue #89** tracks the redraw and the re-run); and no Monte Carlo run of
the *trip point itself* exists, so the trip window's mismatch sensitivity is
estimated (≈2.5 °C per 10 mV of offset) rather than measured.

##### Parallel landings on `main`, and what they leave stale

#69's re-run covered every experiment that existed when its branch was cut.
Six records landed on `main` in parallel and are therefore **not** part of
the `…-4cb27f8` generation. None of them is wrong; each is simply pinned to
a tree that differs from the merged one, and the merge makes that visible
rather than papering over it:

| Landed by | Record(s) | Interaction with #69 | State after the merge |
|---|---|---|---|
| #66/#80 — `sim/thermal` ships | `20260825-054043-6fac47d` | Bench did not exist when #69 was cut; it measures the **pre-#69** CTAT pair | `STALE`. Its 5/15 verdict and every `trip_temp_c`/`reset_temp_c` in the table above are "before the fix" numbers. |
| #64/#73 — `line-regulation`, `load-regulation`, `iq` ship | `20260825-0405/0407/0409-6fac47d` | Benches did not exist when #69 was cut; all three instantiate the re-sized DUT | `STALE` — re-run needed before their PASS/FAIL is cited against the current schematic. |
| #76/#86 — `current-limit` leg-3 cold EN ramp | `20260825-070327-d0bb614` | Revised `tb_current_limit.sch` **after** #69's re-run | #69's `…-4cb27f8` supersedes it by date but predates the bench revision, so the row reports `STALE`. Its **3/3 overall PASS** holds for the pre-#86 deck only. |
| #71/#83 — `dropout-vs-load` `dropout_v` methodology | `20260825-055423-c000414` | Rewrote the deck in `experiment.json`; touched only comments in the `.sch` | The freshness check compares schematic netlists, not decks, so `…-4cb27f8` still reads `fresh` despite being measured with the **superseded fixed-endpoint method**. Verdict is 0/45 either way; the `dropout_v` *numbers* to cite are #83's (0.310–0.554 V at −40/27 °C). |
| #77/#92 — hysteresis root-cause, nothing shipped | (no new record) | Investigated the **pre-#69** sizing; `ldo_3v3in_1v8out.sch` unchanged by it | Its "a fresh 15-point run against the identical schematic would reproduce the same numbers" reasoning was correct on `main`, and stops holding here: #69 *does* change the schematic, so the re-run below now adds verification value rather than being redundant. |
| #74/#94 — full 45-point matrices for the three #65 benches | `20260825-085216-64c17cb` (`current-limit`), `…-073320-64c17cb` (`startup`), `…-073259-64c17cb` (`enable-shutdown`) | Ran breadth against the **pre-#69** DUT while #69 ran freshness against the new one | All three `STALE`. `current-limit`'s is the later run, so the report cites **39/45 FAIL** there rather than #69's 3/3; `startup`/`enable-shutdown` keep #69's fresher 3-point rows and so lose matrix breadth. Full breakdown in `sim/README.md` → "#74 and #69 crossed". |

**#74's failures are this fix's own strongest re-run argument.** All three
of its full matrices fail at `sf_125c` on all three supplies and attribute
it to mechanism 1 — the very nuisance trip re-sized here — so those six
`ff`/`sf` 125 °C corners are, in the merged tree, *diagnosed but not
retested* at full-matrix breadth. #93 (`sf` more susceptible than `ff`
during a ramped enable) rests entirely on that pre-#69 evidence.

**The consequential one is `sim/thermal`.** It is the only bench that
measures the very circuit #69 re-sized, so its record is the direct
before-picture of this fix (`ff` 115–121 °C, `sf` 95–101 °C — both below the
125 °C ceiling) and re-running it against `4cb27f8` is what will turn #69's
`.op`-screened trip estimate into a measured 15-corner result. It is also
the only way to settle whether #69's re-size moves #77's non-positive
hysteresis, which #92 root-caused as a marginal regenerative loop gain on
the old sizing and carried forward to **#91** — #69 changes `M_TSHYSB`
(`W=1.5 → 4.5`), one of the two knobs #92's screening swept, so that
question is genuinely re-opened rather than answered here. That re-run is
follow-on work, not part of this fix: it needs the same append-only
treatment every other record here gets, and #92's own `.options gminsteps=1`
/ nodeset-seeded technique rather than a vanilla continuation sweep.

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
