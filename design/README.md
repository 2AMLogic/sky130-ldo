# `design/` — sky130-ldo core regulation loop

Schematic source for issue #14 (item 1 of the T1/bronze re-read, #12/#13):
`ldo_3v3in_1v8out.sch`, a clean-room, forward-designed xschem schematic for
the sky130 LDO's core regulation loop (error amplifier + pass device +
feedback divider + compensation + enable/shutdown). This is genuinely
original circuit-topology work — a textbook single-stage-OTA LDO
architecture (error amp driving a common-source pass device with Miller
compensation, e.g. Razavi *Design of Analog CMOS Integrated Circuits* ch. 5
& 11) sized against this repo's own PDK screening data, not derived from,
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
  This issue is scoped to design *sources*, not verification — that is #18
  (block testbenches: `load-transient`, `psrr-dc`, `dropout-vs-load`) and
  #19 (full PVT/Monte Carlo). The OP checks described below are **screening
  sanity checks**, run the same way DR-001/DR-003's own appendices do
  (single corner, single bias point, not committed as evidence) — they exist
  so this record's design claims cite something checkable rather than
  asserting circuit behaviour from memory, not to satisfy "verification is
  the product."

## Freshness

Written against `spec/target-spec.md` and
`spec/decision-records/{DR-001,DR-002,DR-003,DR-004}` as of commit `7de8d4b`
(2026-08-17), the tip of `main` at the start of this issue. `spec/target-spec.md`
is entirely DRAFT pending #1; DR-001 is the only **ratified** record among
the four (framing only, no numeric row); DR-002/003/004 are `proposed`. This
schematic designs against the DRAFT numbers and the `proposed` sizing
methodology, per the issue's own instruction not to block on #1.

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
              |                 +-----+-----+
         M_BIASN2 (mirror)      |           |
              ^                M_IN1       M_IN2
              |               (gate=FB)  (gate=VREF)
              |                 |           |
            [AMP_ENN]         EA_D1       EA_OUT --(gate)--> M_PASS --> VOUT
              ^                 |           |                            |
           M_ENN2            M_MIR1      M_MIR2                        R_FB_A
              |              (diode)    (mirror out)                     |
              0                 |           |                          N_FBA
                              [AMP_ENN]  [AMP_ENN]                       |
                                 |           |                         R_FB_B
                                 +---M_ENN2--+                           |
                                                                         FB --> M_IN1.gate
                                                                          |
                                                                       R_FB_C
                                                                          |
                                                                          0

  R_BIAS: VIN -> NB -> [M_BIASN1 (diode)] -> [BIAS_ENN] -> M_ENN -> 0
  M_ENP:  VIN -> EA_OUT, gate=EN   (forces pass gate off when EN=0)
  M_ENP2: VIN -> BIASP, gate=EN    (forces bias/tail chain off when EN=0)
  C_COMP: EA_OUT <-> VOUT (Miller compensation)
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
| `N_FBA` | midpoint of the two-unit top leg of the feedback divider |

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

`EN` is active-high, full-rail (0V / VIN). Two PMOS clamps force the analog
core off when `EN=0`:

- `M_ENP2` (`VIN -> BIASP`, gate=`EN`) forces the bias-generator's PMOS
  diode/mirror node to `VIN`, killing `M_BIASP1` and `M_TAIL`.
- `M_ENP` (`VIN -> EA_OUT`, gate=`EN`) forces the pass-device gate to `VIN`,
  guaranteeing `M_PASS` is off independent of the (now unbiased)
  amplifier's own output.

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
(`M_ENN` or `M_ENN2`), matching the two EN-gated PMOS clamps (`M_ENP`,
`M_ENP2`). The OP check below confirms the fix: `EN=0` measured
**`ipass` ≈ 46pA** (leakage-floor, screening-model only) versus the ~440µA–
1.2mA shoot-through of the earlier drafts.

### VREF interface caveat

This block does not design a bandgap/reference generator — `VREF` is an
external port, standing in for a future reference-generator block (a
sibling canary, `2AMLogic/sky130-bandgap`, exists but is not consulted here
beyond CLAUDE.md's harness-bootstrap pattern; its actual reference voltage
is not reverse-engineered or assumed). The OP checks below use
**`VREF = 0.6V`** as an illustrative placeholder (a plausible sub-bandgap
reference value, not derived from any specific block) purely to exercise the
loop; the feedback-divider ratio, not this specific voltage, is what is
load-bearing. **`VREF`'s real value is an open interface item for whichever
future issue adds a reference generator or a testbench-level ideal source.**

### Feedback divider — measured, not invented, unit-resistor value

Per `spec/target-spec.md`'s Output row ("divider as a unit-resistor
string"), `R_FB_A`/`R_FB_B`/`R_FB_C` are three identical `res_xhigh_po` unit
resistors (`W=0.42 L=180`), ratio 2:1 (two units `VOUT->FB`, one unit
`FB->GND`) so `VOUT = 3 x VREF`. The unit value was **measured**, not
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

### Pass-device and bias-chain sizing

- `M_PASS`: `L=0.5` (bin floor) `W=100 nf=25` → `W_total=2500µm` (~2.5mm),
  matching DR-003's sizing methodology output (`W_total ≥ 14.81kΩ·µm /
  6Ω ≈ 2.47mm` at the dropout bias point / `{ss,sf}`@125°C co-binding
  corner). This is DR-003's own screening-derived number, not re-derived
  here — see that record's Appendix for the corner sweep.
- The bias generator (`R_BIAS`, `M_BIASN1`, `M_BIASN2`, `M_BIASP1`) and the
  error-amplifier device sizes (`M_TAIL`, `M_IN1`, `M_IN2`, `M_MIR1`,
  `M_MIR2`) are **illustrative, functional starting points**, sized only to
  get a working, correctly-biased loop — not calibrated against an Iq
  budget, because **no Iq budget exists yet**: DR-003 explicitly declines to
  set one ("no amplifier or bias topology exists yet in this repo to
  characterize" — issue #14 is exactly the topology this record was waiting
  on). Once a topology exists (this one), a future decision record can set
  an Iq budget and this schematic's bias currents can be re-derived against
  it, rather than the other way around.
- `C_COMP` (Miller compensation, `EA_OUT -> VOUT`, value `2p`) is a
  **placeholder**, not sized against a loop-gain simulation. DR-002 (the
  C_out/ESR window) is `proposed`, not ratified, and explicitly sequences
  itself *after* a topology exists to simulate against — this schematic is
  that topology, but the loop-gain sim itself is out of scope here (#18/#19).

## OP sanity checks (screening only — not `sim/` evidence)

Run against the pinned PDK (`tt` corner, 27°C), `VIN=3.3V`, `VREF=0.6V`
(placeholder, see above). Not committed under `sim/` — this issue is design
sources only; a real corner-swept load-transient/dropout testbench is #18's
job.

| Condition | `EN` | Load | `VOUT` | `FB` | Notes |
|---|---|---|---|---|---|
| Enabled, light load | 3.3V | `1.8kΩ` (~1mA class) | **1.977V** | 0.659V (target 0.6V) | Regulates within ~10% of target — consistent with a simple single-stage 5T OTA's finite loop gain, not a high-gain multi-stage amp. A future gain/topology iteration (cascode or two-stage) would tighten this; tracked as a follow-on item. |
| Enabled, no external load | 3.3V | none (divider only, the spec's own "0mA" definition) | **3.30V (rails to ~VIN)** | 1.10V | **Known open item** — see below. |
| Disabled | 0V | `1.8kΩ` | ~0V | ~0V | `M_PASS` and the whole bias/amp core cleanly off; `ipass` ≈ 46pA (leakage floor), vs. ~440µA–1.2mA shoot-through in the pre-fix drafts (see "Enable/shutdown" above). |

**Known open item: the true 0mA (divider-only) corner does not regulate in
this screening check.** `M_PASS` is sized for 50mA (`W_total≈2.5mm`), so at
0mA it must be throttled deep into sub-threshold (a >10,000:1 dynamic
range from full load) — this schematic's simple, low-current 5T OTA does
not have enough gain/output authority to find that operating point from a
cold DC solve; `VOUT` rails toward `VIN` instead of settling near 1.8V. This
is a real, common LDO design problem (very wide pass devices are
notoriously hard to throttle at no-load), not a wiring bug — the
light-load (~1mA) and disabled cases above both behave correctly, which
rules out a topology/connectivity error and narrows this to a gain/sizing
question. Flagging honestly rather than silently working around it or
over-claiming a fix: whoever builds the `dropout-vs-load` / `load-transient`
testbenches (#18) should expect to need either more amplifier gain
(cascoded first stage, or a second gain stage) or a minimum-bleed-current
design choice to close this corner, and should not be surprised if the
current sizing does not hold 1.8V at exactly 0mA.

## Known gaps / follow-on scope

Deliberately **not** in this schematic (per this issue's acceptance
criteria, which asks for the LDO's core regulation loop, not full PVT
verification or protection circuitry):

- **Current limit** (spec: constant-current brickwall clamp, survives a
  continuous `VOUT=0` short at `VIN_max`). Not designed here — needs a
  sense element (sense-FET or sense-resistor) and a clamp/foldback path,
  a meaningful circuit addition in its own right.
- **Soft-start / controlled turn-on ramp** (spec: monotonic into any load,
  overshoot ≤+2%). The current enable scheme is a hard on/off; no ramp
  control exists.
- **Thermal shutdown.** Not designed here.
- **An actual on-chip voltage reference.** `VREF` is an external port (see
  "VREF interface caveat" above).
- **The 0mA no-load regulation corner** (see OP sanity checks above).

These are real, trackable gaps, not silently dropped requirements — filed as
issue #22 (current limit / soft-start / thermal shutdown) as part of closing
out this issue.

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
