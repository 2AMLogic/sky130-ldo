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
  described in `spec/target-spec.md`'s table (ratified by issue #1 / DR-006,
  except the Iq row, which is set separately by DR-009 and is still
  `proposed`), built on the framing
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

The spec this schematic designs against is `spec/target-spec.md`, which is
RATIFIED (issue #1 / DR-006), plus the decision records under
`spec/decision-records/` (DR-001 onward; each record states its own status).
Treat those as authoritative; this README carries no commit pin. Where a
passage below was written before ratification, the spec and DRs win.

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

**"Full-rail" is a hard interface requirement, and #187 measured what it costs
to violate it.** The clamps above are PMOS with their *sources at VIN*, so their
gate drive is `VIN - EN`: an `EN` high level below VIN leaves them partly
conducting, and there is no level-shifter or threshold-referenced receiver on
this pin. Measured at fs/125 °C, VIN = 3.63 V (`sim/README.md` → "#187", from a
scratch flattened netlist with series ammeters — no schematic change):

| `EN` high level | I(`M_ENP`) → `EA_OUT` | I(`M_ENP2`) → `BIASP` | I(`M_TAIL`) | settled V(VOUT) |
|---|---|---|---|---|
| 3.63 V (at the rail) | 39 pA | 62 pA | 3.476 µA | 1.79862 V |
| 3.30 V | — | — | — | 1.79793 V |
| 3.10 V | — | — | — | 1.78256 V |
| 3.00 V | — | — | — | 1.68637 V |
| 2.97 V | 1.377 µA | 1.639 µA | 1.003 µA | **collapsed** |

The compounding is the point: `M_ENP2`'s residual current lifts `BIASP` by
90.6 mV, which starves every BIASP-gated PMOS current source (the amplifier's
tail current falls to 1.003 µA), while `M_ENP`'s residual current into `EA_OUT`
*rises* to 1.377 µA — so the clamp out-drives the whole amplifier, `EA_OUT` is
pulled to VIN and `M_PASS` turns off. It is a static limit, not a start-up
branch: dropping `EN` to 2.97 V at 1 ms while the loop is already regulating
collapses it. 125 °C maximizes the clamps' subthreshold conduction and `fs`
(slow PMOS) minimizes the currents that must overcome it, so fs/125 °C is the
worst case of the corner matrix, but the whole 125 °C/`EN` = VIN − 0.66 V column
reads low (1.717–1.792 V).

**This is a documented-interface fact, not a known gap**: nothing about it needs
a circuit change, and no bench that honours the `0 V / VIN` contract sees it.
`sim/enable-shutdown` — the row's own bench, which exercises the `EN` edges
themselves — drives `EN` at `'vsup'` *with* VIN at `'vsup'`, as does every other
bench in `sim/`. `sim/dropout-vs-load` was the single exception (VIN pinned at
3.63 V while `'vsup'` drove `EN` alone), which is what produced the −7.4521 V
`vout_at_max_vin_v` outlier in record `20260926-043132-eba96ae`; #187 corrected
that bench's convention rather than this circuit. If a *system* ever needs a
logic-level (e.g. 1.8 V) enable against a 3.3 V VIN, that is a new
level-shifter/receiver requirement for the spec to state, not a defect in this
implementation of a full-rail pin.

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

**2am reuse rule 9, `sky130-bandgap` edge (#136, 2026-09-23): no
`reuse.lock.json` entry today.** `2am/repos.yml` records `consumes:
[sky130-opamp, sky130-bandgap]` on this repo; #123/DR-010 closed the
`sky130-opamp` half (an in-tree error amplifier, kept). The `sky130-bandgap`
half is different in kind, not degree: there is no in-tree bandgap/reference
block here to adopt or keep — `VREF` is only ever the external port described
above — so rule 9's `in_tree` adopt-or-keep ledger has nothing to evaluate,
and no bytes are fetched or vendored from `sky130-bandgap` for an `imports`
entry to pin either.
[`DR-012`](../spec/decision-records/DR-012-no-bandgap-reuse-lock-entry-yet.md)
records this as an explicit "no lock entry yet" decision — an unrealized
future dependency, not a silently-dropped one — and names what would change
that: a future issue actually wiring in a `sky130-bandgap` output (an
`imports` entry), or this repo growing its own in-tree reference (an
`in_tree` entry). `sky130-bandgap`#286 was checked and is **not** this edge's
counterpart (it resolves a different rule-9 pairing, bandgap's own
`error_amp` versus `sky130-opamp`); no `sky130-bandgap`-side issue currently
names this edge.

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
the ratified spec's "0mA = no external load; feedback divider is the only
inherent preload" note. **These are screening numbers** (single corner,
single bias point, not a `sim/` evidentiary record) — real values need
re-confirming across the full PVT matrix once a testbench exists (#18/#19),
and are not cited as a verified/ratified spec value.

### Pass-device width correction (found in #22)

> **Superseded as a *width* by #116/DR-011 (2026-09-23).** Everything in this
> section about `mult` semantics still holds and is still how the instance is
> written — but the 2500 µm it lands on is no longer the shipped width. `M_PASS`
> is now `mult=50` → `W_total` = **5000 µm**, because DR-003's 2.47 mm *target*
> turned out to be derived at the wrong bias point. See
> "[Pass-device re-size (#116/DR-011)](#pass-device-re-size-116dr-011)" below
> for the re-derivation; read this section as the `mult`-semantics history it
> is. The paragraphs below are left as written (append-only house style).

`M_PASS` was, from #22 until #116, `L=0.5` (bin floor), `W=100 nf=25 mult=25`
→ **`W_total` = 2500µm (~2.5mm)**, matching DR-003's sizing methodology output
(`W_total ≥ 14.81kΩ·µm / 6Ω ≈ 2.47mm` at the dropout bias point /
`{ss,sf}`@125°C co-binding corner — DR-003's own screening-derived number,
not re-derived there).

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

> **#116 footnote on that last paragraph.** That 98 mA is `tt`/27 °C at *full*
> (0 V) gate drive — the benign corner at an unreachable bias. At the binding
> `sf`/125 °C corner the same device delivers 44.0 mA at the same `V_sd`, and
> at the gate drive the amplifier can actually supply it delivers 33.7 mA. The
> "comfortably above the 50mA row" reading is what DR-011 corrects.

### Pass-device re-size (#116/DR-011)

**`M_PASS`: `W_total` 2500 µm → 5000 µm (`mult` 25 → 50). `M_SENSE`: 0.42 µm →
0.84 µm (`mult` 1 → 2), holding the current-limit sense ratio at 1:5952.**

Issue #116 was filed because `Dropout @ 50 mA` (ratified, `< 300 mV`) failed
**0/45** corners, best case 365 mV, and pointed at the sibling `gf180-ldo#139`
— where the same block in a different PDK shipped a pass device at half the
width its own sizing review assumed — asking this port to run the same check
first. **Outcome, from the real full-matrix record: 0/45 → 6/45 PASS** — real
progress, not a clean closure; see "Dropout: 0/45 → 6/45" in `investigation-log.md` for the corner-by-corner picture and DR-011 for the corrected
evidence.

**That check comes back negative.** The committed instance was `W_total` =
2500 µm against DR-003's `≥ 2468 µm`: the schematic matched its derivation to
1 %. There was no transcription gap of the `gf180-ldo#139` kind here.

**The derivation was wrong instead**, in two compounding ways DR-003 named in
its own scope caveats but never quantified:

1. **`R_on` was measured in deep triode (`V_sd` = 50 mV) and spent at the
   row's own `V_sd` = 300 mV**, where the device is no longer triode-linear.
   Re-measured at the row's bias point, `sf`/125 °C, `V_sg` = 2.10 V:
   **17.03 kΩ·µm**, not 14.81 — 15 % optimistic.
2. **DR-003 assumed an ideal 0 V gate.** Closed-loop screening measures
   `EA_OUT` **flooring at 0.24–0.31 V** through and below the dropout region,
   so the achievable `V_sg(M_PASS)` is ≲1.80 V, never the 2.10 V DR-003 sized
   at — worth a further ~30 % of drive current.

Compounded, DR-003's 2468 µm requirement becomes **3709 µm**
(`2468 × 1.150 × 1.306 = 3707 µm`, which reproduces the directly-measured
number). The decisive consequence, and the reason this is a re-size and not a
tuning exercise:

> At the binding `sf`/125 °C corner the committed 2500 µm device delivers
> **44.0 mA** at `V_sd` = 300 mV **with an ideal 0 V gate** — against a 50 mA
> row. It missed the ratified row at *every* gate drive, including one the
> amplifier cannot reach. No compensation change, amplifier fix or layout work
> could have closed that 0/45.

5000 µm is 1.35× the 3709 µm requirement — deliberately not tighter, because
that requirement inherits DR-003's own unquantified caveats (no fingering,
contact or IR-drop margin, no self-heating) — and is exactly 2× the existing
instance, so the layout generator's `W * mult` convention and the `W=100 nf=25`
`mult`-group unit are both unchanged. Full derivation, the per-corner screening
tables, and the alternatives weighed (including two that were built and
measured before being rejected) are in
[`spec/decision-records/DR-011-pass-device-resize.md`](../spec/decision-records/DR-011-pass-device-resize.md).

**`M_SENSE` had to move with it.** `M_SENSE` is a ratio'd replica of `M_PASS`,
and the current limit is set by that *ratio*, not by either width. Doubling
`M_PASS` alone would have halved the sense signal and silently doubled the
limit threshold — invalidating the ratified `Current limit` row's 45/45 PASS
without touching anything that mentions current limiting. `mult=1 → 2` keeps
0.84 µm : 5000 µm = 1:5952, exactly where #22 put it.

**What this does not claim.** The re-size is *not* asserted to be
stability-neutral: a wider pass device moves the output pole and raises
`gm_pass`, `C_COMP`/`R_CZ` are **not** re-derived here, and the `Stability` row
was already failing 7/45 before this change. #116's own scope note calls for
coordinating the two rather than landing them independently; this change lands
the dropout row with its own full-matrix evidence and hands the interaction to
a named follow-up, rather than bundling an unmeasured compensation re-design
into it. Every other `sim/` bench instantiates this DUT and therefore goes
`STALE` against it — see the dated `#116` campaign section in `investigation-log.md`.

#### Rejected here, but real: the amplifier's tail headroom at low `VIN`

A partial earlier attempt at #116 hypothesised that the *amplifier's* input
common mode, not the pass device, set the dropout, and built the fix for it:
re-tap the feedback divider 1:2 → 2:1 and add a matched 1:1 `VREF` attenuator,
so the input pair sits at 0.6 V while the external `VREF` = 1.2 V interface is
unchanged.

The observation behind it is **correct and worth keeping**. With the shipped
1.2 V common mode, `EA_TAIL` is pinned near `V_cm + V_sg(M_IN)` ≈ 2.09 V
*regardless of* `VIN`, so at the ratified dropout test point (`VIN` = 2.10 V)
`M_TAIL` has **6.7 mV** of `V_sd` — the tail current source is collapsed at the
exact operating point the row is measured at.

It is simply not this row's root cause, which is why it is not in this change:
built and screened (`tt`/27 °C, `VIN` = 2.100 V, 50 mA) it moves `VOUT` from
1.6738 V to 1.6805 V — **7 mV**, against the ~90 mV needed to reach the 1.764 V
departure threshold. It restores tail headroom (`V_sd(M_TAIL)` 6.7 mV → 351 mV)
without restoring drive, because `EA_OUT`'s floor barely moves with it
(0.313 V → 0.306 V). Bundling a divider-ratio, soft-start-gain and loop-gain
change into a dropout fix would also have confounded the very measurement that
had to be taken. Preserved as a follow-up issue rather than discarded.

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
screening showed keeps improving that corner, because the `Iq < 30 µA` row
(set by DR-009, `proposed`) is the binding constraint — 6× measured 33.6 µA
at 50 mA, over the row; 2× measures 24.9 µA (table below), inside it.

**Measured result** (`sim/loop-gain` record `20260818-014128-01b7905`, the
`--quick` 3-corner subset; ratified bound is `spec/target-spec.md`'s Stability
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
   (`EA_OUT`), same source (`VIN`) — at two minimum-width units, giving a
   nominal 0.84µm : 5000µm = **1:5952** current ratio. (#22 wrote this as
   0.42µm : 2500µm; #116/DR-011 doubled *both* devices together, so the ratio
   — the thing that actually sets the limit — is unchanged. Doubling `M_PASS`
   alone would have halved the sense signal and silently doubled the trip
   threshold.) A sense FET rather than a
   series sense resistor because nothing may be inserted in the main current
   path: a 1Ω sense resistor would spend 50mV of the 300mV ratified dropout
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
0.84µm-wide device matched against a 5000µm one has substantial random
`V_th` mismatch. The spec row says "window TBD over PVT" precisely because
this kind of limit is a window, not a number; establishing that window is
#19's job, not this record's.

**Iq interaction, stated rather than hidden.** The sense branch carries
`I_load / 5952`, so it adds ~8µA at the 50mA load point — about a quarter of
the `Iq < 30µA at no load and full load` row (set by DR-009, `proposed`), and
the dominant term in
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
  against the 0.1mm² ratified area row. `M_SSCHG`'s gate is `BIASP`, so the ramp
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

> **Superseded in part by #230:** the trip comparator and the linear hysteresis
> injection described below (`M_TCN1/2`, `M_TCP1/2`, `M_TCTAIL`, `M_TSHYS`,
> `M_TSHYSB`) were replaced by the regenerative comparator, see "Regenerative
> comparator integrated into the LDO (#230)". The sense/reference text, the
> `M_TSHUT`/`M_ENP4` clamp and the measured history (#69, #77, #91) are kept as
> the record of how the design got here; numbers quoted for the old comparator
> are not measurements of the current schematic.

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
   qualitative description assumes — see the dated "#77" section in `investigation-log.md` for
   the full diagnosis and why a fix was not shipped.** The two numbers are
   not in conflict and neither supersedes the other: #77 measured the
   *pre-#69* sizing with a `.dc temp` continuation sweep, while #69's
   13.9–20.4°C comes from solving the rising and falling branches separately
   on the *re-sized* pair — a technique #77's own Diagnostic 1 independently
   shows is needed to see the window that a vanilla continuation sweep loses.
   **Update (#91, 2026-08-25): re-screened against the #69/#90-resized
   circuit — the marginal loop gain persists, essentially unchanged in
   character.** #90 re-sized the CTAT sense/reference pair and re-confirmed
   `M_TSHYSB` at `W=4.5`, but did not touch the comparator
   (`M_TCTAIL`/`M_TCN1`/`M_TCN2`/`M_TCP1`/`M_TCP2`) or `M_TSHYS` itself, and
   did not re-run `sim/thermal`. #91 answers the "is it open" question this
   paragraph left open: **no**, #69/#90's re-size does not repair the
   hysteresis — see the dated "#91" section in `investigation-log.md` for the full re-screen and
   an additional candidate (comparator channel length) that also proved
   unshippable.
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

## Regenerative thermal comparator (#229, standalone development cell)

`thermal_cmp_regen.sch`/`.sym` is a **standalone** replacement candidate for the
#29 trip comparator (`M_TCN1`/`M_TCN2`/`M_TCP1`/`M_TCP2` + the linear
`M_TSHYS`/`M_TSHYSB` current injection). It is **not wired into
`ldo_3v3in_1v8out.sch`** (that is the integration child of #131). #77/#91 showed
the linear injection has loop gain ~1 and cannot hold a window; here positive
feedback is a large-signal property of the load.

**Topology.** NMOS differential pair (`M_RCN1` gate `TS_SNS`, `M_RCN2` gate
`TS_REF`, `nfet_g5v0d10v5` L=2 W=10 nf=2, as `M_TCN1`) on a tail `M_RCTAIL`
(gate `NB`, source `AMP_ENN`, L=1 W=1 — the same bias-generator mirror copy as
`M_TCTAIL`). The load on each drain (`RC_A`, `RC_B`) is a diode-connected PMOS
(`M_RCD1/2`, `pfet_g5v0d10v5` L=2 W=10 nf=2) **in parallel with a cross-coupled
PMOS** (`M_RCC1/2`, L=2 W=17 nf=2). With cross-coupled/diode width ratio 1.7 > 1
the differential load conductance is negative, so the cell is bistable; the
width ratio (not an absolute current) is the single window knob. Output:
`M_RCOP` (pull-up, gate `RC_A`) with `M_RCOS` (NB-mirror pull-down, W=0.5 L=2)
drives `TS_CMP`, same polarity as #29 (`~VIN` = not tripped, falling = engaged),
so the real `M_TSHUT` and its EN clamp are unchanged. `M_RCEA/B/EO` (EN=0 pulls
`RC_A`, `RC_B`, `TS_CMP` to `VIN`) reset the latch symmetrically while disabled.

**Reference and DR-005 behaviour.** Inputs are the existing #29 CTAT sense and
reference, both derived from the block's own bias generator (no `VREF`, no
bandgap). Nothing is latched across a temperature excursion: both flip points are
crossed by the input difference alone, and an EN cycle returns the state the
input demands. Auto-restart (non-latching) is preserved.

**Interface** (symbol `thermal_cmp_regen.sym`): in `VIN`, `EN`, `NB`
(bias-generator NMOS mirror gate), `AMP_ENN` (shared EN-gated pseudo-ground),
`TS_SNS`, `TS_REF`; out `TS_CMP` (drives `M_TSHUT` gate, `W=20 L=0.5 nf=4`).
Loading assumed in the bench: `M_TSHUT` into a 100 kohm / 2.4 V stub for
`EA_OUT`. Input pair and load add gate load on the sense/reference nodes
comparable to the #29 pair (same input-device geometry).

**Result (development evidence, tt/3.30 V only):** record
`sim/thermal-regen-cmp/records/20261008-130329-19114c8-dev1`: `T_reset`
158.906 °C, `T_trip` 172.031 °C, **hysteresis 13.1 °C** (+-0.3 °C bisection
uncertainty; the existing grid is 2 °C), 0 of 50 runs with solver diagnostics,
EN disable/re-enable not latching. Method, limits and uncertainty:
`sim/thermal-regen-cmp/README.md`. Caveats that carry to integration: the
single-corner result does **not** prove DR-005's `>= 150 °C` worst-corner trip
floor (it must be re-established over PVT; the ~172 °C rising trip here is the
unchanged #29 sense/reference at tt/3.30 V, not re-centred); a cold start that
lands inside the window resolves to the tripped (safe) state; hysteresis in °C
scales with the sense/reference tempco (~4 mV/°C here) and the width ratio.
Full PVT, mismatch and integration into the LDO remain with the sibling
children of #131.

## Regenerative comparator integrated into the LDO (#230)

`ldo_3v3in_1v8out.sch` now carries the #229 regenerative trip comparator
**flat** (devices `M_RCTAIL`, `M_RCN1/2`, `M_RCD1/2`, `M_RCC1/2`, `M_RCEA/B`,
`M_RCOP`, `M_RCOS`, `M_RCEO`, sizes unchanged from `thermal_cmp_regen.sch`) in
place of the #29 5T-OTA comparator and its linear current-injection hysteresis.
Flat rather than a hierarchical instance because this block is one hand-captured
schematic whose layout/LVS flow is driven device-by-device from its netlist
(`layout/bin/gen-ldo-blocks.py`); `thermal_cmp_regen.sch` stays as the
standalone development cell and the sizing source of truth.

**Removed:** `M_TCTAIL`, `M_TCN1`, `M_TCN2`, `M_TCP1`, `M_TCP2`, `M_TSHYS`,
`M_TSHYSB` (and nets `TC_TAIL`, `TC_D1`, `TS_HYS`). **Added:** the twelve
`M_RC*` devices above (nets `RC_TAIL`, `RC_A`, `RC_B`). **Unchanged and still the
contract:** the CTAT sense and reference stacks (`M_TSPS`, `M_TSD1/2`, `M_TSPR`,
`M_TSR1`; bias-generator-derived, no `VREF`/bandgap), `TS_CMP` polarity (~`VIN` =
not tripped, falling = engaged), `M_TSHUT` (`VIN` -> `EA_OUT`), the `M_ENP4`
EN clamp (plus `M_RCEA/B/EO`, which put both latch nodes and `TS_CMP` at `VIN`
while `EN` = 0), the EN-gated `AMP_ENN` ground return on every branch, `C_TS`
(1 pF, kept; it only loads `TS_CMP`), and DR-005's auto-restart (non-latching)
behaviour. Port list is unchanged. `NB` loading: `M_RCTAIL` (W=1) replaces
`M_TCTAIL` (W=1) and `M_RCOS` (W=0.5, L=2) is a second, small `NB` mirror copy,
so the comparator draws one extra tail-class branch of bias current (see the Iq
note below).

**Result (development evidence, tt / 3.30 V only):** `sim/thermal/hysteresis/20261008-190150-0275a8b-dev1`,
50 independent transients of the real LDO bench (method and limits:
`sim/README.md`, "Integrated regenerative comparator (#230)"). `T_reset`
(falling) 159.22 C [159.06, 159.38], `T_trip` (rising) 172.34 C [172.19, 172.50],
**hysteresis 13.1 C** (12.8 to 13.4 C by the bisection bracket; the old DC
grid resolution is 2 C). 0 of 50 runs with a solver diagnostic. The integrated
cell reproduces the standalone #229 result (13.1 C, 158.9 / 172.0 C) to within
the bracket-plus-simulator-version scatter. EN disable/re-enable and cold start
behave as in the standalone cell (nothing latched across an EN cycle; a cold
start inside the window resolves to the tripped, safe side).

**What this does not show.**
- It is not PVT: one process corner, one supply, one temperature axis. DR-005's
  `>= 150 C` worst-corner trip floor is **not** established here, and nothing in
  this section claims it.
- The rising trip at tt/3.30 V is 172.3 C, i.e. above DR-005's 150 C nominal
  (the previous comparator read 165.0 C at tt/27 C/3.30 V with zero resolved
  hysteresis in record `20260926-095154-f6ab418`). The sense/reference stacks
  are unchanged, so this is a property of the comparator's thresholds
  (about -27 mV / +26 mV of `TS_SNS - TS_REF` at the two flip points, converted at
  about 4 mV/C), not a re-centring. Re-centring (the `M_TSPR` width knob from #69)
  and the PVT spread are the qualification child's job (#231).
- 13.1 C is below DR-005's 15 C nominal target; DR-005 treats 15 C as an
  untrimmed, PVT-loose nominal and this change does not edit it.
- Mismatch/Monte Carlo of the comparator offset is not run.
- `Iq` was not re-measured. The comparator branch current changes (see the
  device list); `sim/iq`'s record is stale and the qualification child must
  re-run it before any Iq statement is made.

**Measurement interface.** `sim/thermal/testbench/tb_thermal_trip.sch` gained a
removable disturbance current `IX` at `xldo.TS_SNS` and an `EN` source that is
`dc 'vsup'` for DC analyses and a PWL for transients (inert defaults through
`experiment.json` `deck.params`), so the same schematic still serves the existing
`dc temp` deck and now the staircase runner `sim/thermal/run_hysteresis.py`.

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

**Every point is inside the ratified ±2% Output row**, including the 0mA and 1mA
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

Against the other ratified rows, honestly scored:

- **Load regulation** over the row's full 0→50mA range is 4.3mV at
  `VIN=2.97V` (**0.24%**), inside the ratified `<1%` row — where the #22
  schematic was 55mV (3.0%) and missed it.
- **Line regulation** at 50mA is (1.7981−1.7978)/0.66V ≈ **0.45mV/V**, inside
  the ratified `<5mV/V` row — where the #22 schematic was ≈11mV/V and missed it.
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

Iq = total `VIN` current minus load current. All points are inside the Iq
`< 30µA at no load and full load` row (set by DR-009, `proposed`), and the
disabled state is four orders of magnitude inside the ratified `< 3µA` row.
The 0mA→50mA Iq growth is
almost entirely the current-limit sense branch (`I_load / 5952` ≈ 8µA at
50mA) — see "Iq interaction" above.

**Issue #25 spent Iq deliberately, and the row is what capped the spend.**
The #22 numbers were 5.55–7.38µA at 0mA and 18.0–19.3µA at 50mA; the increase
here is the two added mirror branches plus the 2× `M_TAIL` widening. Pushing
`M_TAIL` to 6× — which screening showed keeps improving the no-load phase
margin, up to ~40° — measured **33.6µA at 50mA**, i.e. *over* the Iq row (set
by DR-009, `proposed`), so it was not taken. That trade is recorded rather
than hidden, because it is the reason the no-load corner in "Compensation
(sized in #25)" is left short of 45° instead of bought out with bias current:
relaxing one row to make another ratified row pass is exactly what
`CLAUDE.md` forbids.

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

**Status: closed.** The DC grid above now sits inside the ratified ±2% row at
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

Current open gaps (verdicts: [`measurements/characterization.md`](../measurements/characterization.md);
decisions: `spec/decision-records/`):

- **Several ratified rows still FAIL** (dropout, load regulation, load
  transient, PSRR, stability, area as of the latest rollup) -- see the
  characterization report for the live verdicts and DR-007 / DR-011 for the
  PSRR/Stability and pass-device-sizing decisions.
- **`C_CL` is a placeholder**: the current-limit comparator pole is not sized
  against a loop-gain sim (screened only as a smoke test).
- **No on-chip voltage reference**: `VREF` is an external port (see "VREF
  interface caveat").
- **Corner coverage** beyond the 45-point PVT + Monte Carlo campaign is only
  as recorded under `sim/`; thermal has its own testbench (`sim/thermal`).

The full dated history of how these were investigated (issues #19 through
#169 and later; reverted bias-generator candidates, root-cause write-ups)
is archived verbatim in [`investigation-log.md`](investigation-log.md).

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
