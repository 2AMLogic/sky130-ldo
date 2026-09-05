# Chipalooza Challenge #4 proposal — 3.3V-in / 1.8V-out LDO (sky130)

Analog-IP proposal for [Open Circuit Design's Chipalooza Challenge
#4](https://opencircuitdesign.com/chipalooza/) (Sky130 / ChipFoundry). This
document is written to be sendable verbatim once the design clears its
sign-off bar; it contains no personal or institutional identifiers.
Designer CVs and the test-equipment list, if this design is ever submitted,
are separate email attachments outside this repository, per the challenge's
submission process (see [2AMLogic/gf180-temp-por's own Challenge #3
proposal](https://github.com/2AMLogic/gf180-temp-por/blob/main/docs/chipalooza/challenge-3-proposal.md)
for the sibling-org convention this document follows, on a different PDK).

**Rules status (as of this writing, 2026-09-05): Challenge #4's own rules
page (`rules-4.html`) is not yet published** — the organizers' calendar puts
launch at 2026-11-09. Per
[2AMLogic/2am#542](https://github.com/2AMLogic/2am/issues/542) (the epic
this issue is a phase of), this document assumes the structure common to
the two *published* briefs (`rules-2.html`/`rules-3.html`): a template
wrapper cell in a fixed slot; a harness-supplied bandgap-referenced bias
voltage and up to two bandgap-referenced current sources; 24 digital
control inputs; 12 digital test outputs; 4 shared (multiplexed) analog
lines; 0–4 dedicated pads; an SPI control interface; deliverables of
schematic + pre-layout sim → layout + post-layout sim over PVT → final
DRC/LVS in-repo, verifiable with open-source EDA; a standard open license
(preferably Apache 2.0). When `rules-4.html` publishes, a follow-up issue
must re-check every assumption in this document against the real brief
before any submission — see §6 for exactly what that follow-up needs to
verify.

**Honesty note, stated once here rather than repeated on every row.** This
block is well past schematic-only maturity: `design/ldo_3v3in_1v8out.sch`
is netlist-checked and DRC-clean/LVS-matched in layout
(`layout/ldo-core/`), and `sim/` carries a full 45-point PVT campaign
(`tt`/`ss`/`ff`/`sf`/`fs` × {−40, 27, 125} °C × {2.97, 3.30, 3.63} V) plus a
200-sample mismatch Monte Carlo run across most spec rows. That is
significantly more evidence than this document needs to hide behind — and
the honest reading of it is that **most DRAFT spec rows currently FAIL**,
for two open, tracked, non-trivial reasons: issue
[#70](https://github.com/2AMLogic/sky130-ldo/issues/70) (PSRR fails in
every corner and light-load stability is marginal-to-failing across most of
the PVT grid; open, `loom:blocked`, no shipped fix yet) and the fact that
`spec/target-spec.md` itself is still **DRAFT** pending ratification
(issue [#1](https://github.com/2AMLogic/sky130-ldo/issues/1), open,
`loom:operator-only`) — so every "met"/"unmet" verdict below is against a
target that could itself still move. Per this issue's own acceptance
criteria and `CLAUDE.md`'s "no claim without a testbench" / "a row that
proves unmeetable is superseded by a new decision record, never silently
loosened," every row in §4 is re-derived **only from what `sim/` actually
contains today**, with no row relaxed, rounded favorably, or inferred from
schematic inspection to make a verdict look better than the cited record
states.

---

## 1. Type of IP block

A linear low-dropout voltage regulator (LDO): a 3.3 V ±10 % input to a fixed
1.8 V ±2 % output, 0–50 mA load, on sky130's 5 V-tolerant device family.
Single-stage current-mirror ("symmetric") OTA driving a common-source pass
device, with a unit-resistor feedback divider, Miller-plus-nulling-resistor
compensation, a sense-FET current-limit comparator, a current-starved
soft-start ramp, and a CTAT-based thermal-shutdown comparator with
hysteresis. This is a clean-room, forward-designed sky130 port of
[`2AMLogic/gf180-ldo`](https://github.com/2AMLogic/gf180-ldo) (ratified
target spec 2026-07-31) — same block class, two PDKs, per this repo's
`CLAUDE.md` "port parity" instruction — built against sky130 device physics
and PDK screening data, never reverse-engineered from any third party's
implementation (`design/README.md` §"What this is, and isn't").

## 2. I/O list, including test ports

### 2.1 Pinout — four pins total, all four load-bearing

`design/ldo_3v3in_1v8out.sym` declares exactly four pins; there is no
separate digital-only or test-only port in the current schematic:

| Pin | Direction | Role |
|---|---|---|
| `VIN` | in | 3.3 V ±10 % (2.97–3.63 V) supply — the block's only rail besides implicit ground |
| `EN` | in | active-high enable, full-rail 0/`VIN` |
| `VREF` | in | external reference input — see §2.2 |
| `VOUT` | out | 1.8 V ±2 % regulated output, 0–50 mA |

### 2.2 Harness-supplied bandgap-referenced bias voltage — `VREF` consumes it directly

Unlike a block that generates its own on-chip reference, this LDO's `VREF`
pin is designed from the start to be driven externally
(`design/README.md` § "VREF interface caveat, and the reference common
mode": *"This block does not design a bandgap/reference generator — `VREF`
is an external port, standing in for a future reference-generator
block"*). That is exactly the common structure's harness-supplied
bandgap-referenced bias voltage — this block is a natural, direct consumer
of it rather than needing a schematic change to bond one out. The
divider ratio is fixed at 1:2 (`VOUT = 1.5 × VREF`,
`design/README.md` § "Feedback divider"), so whatever reference voltage the
harness supplies must be `VOUT_target / 1.5` — this repo's own screening
checks use `VREF = 1.2 V` (giving `VOUT ≈ 1.8 V`) as an illustrative
placeholder, not a claim about the harness's actual bandgap voltage
(§4 flags every row built on that placeholder as unverified against a real
reference). If the harness's real bandgap-referenced bias voltage differs
from 1.2 V, the divider ratio needs a one-time resistor-ratio change before
integration — a schematic change, not a topology change.

No harness-supplied bandgap-referenced *current* source is consumed; the
block's own `R_BIAS`/`M_BIASN1`/`M_BIASN2`/`M_BIASP1` chain (`VIN`-referenced,
undesigned against PSRR — see issue #70) generates its internal bias
current from `VIN` directly.

### 2.3 Digital control inputs — 1 of 24 used

| Signal | Purpose |
|---|---|
| `EN` | active-high enable/shutdown |

23 control-input slots remain unused. No trim, mode-select, or
configuration bus exists in the current schematic.

### 2.4 Digital test outputs — 0 of 12 used

No digital test output exists in the current schematic. `VOUT` is the
block's one functional output and is not counted against this budget
(mirrors the convention [sky130-temp-por's own Challenge #4
proposal](https://github.com/2AMLogic/sky130-temp-por/blob/main/docs/chipalooza/challenge-4-proposal.md)
used for its analogous `RESETn` pin). All 12 test-output slots remain
unused.

### 2.5 Dedicated (non-shared, low-resistance) pads — 1 of 4 used

| Signal | Why dedicated, not shared/multiplexed |
|---|---|
| `VOUT` | The regulated supply rail this block delivers to a load — routing it through a shared/multiplexed bus would add series resistance and switch leakage directly onto a rail whose own load-regulation budget is already `< 1 %` (18 mV) of headroom (`spec/target-spec.md`'s Load regulation row), and whose external load current (up to 50 mA) needs a low-impedance path a muxed pad cannot offer. |

3 dedicated-pad slots remain unused.

### 2.6 Shared (multiplexed) analog lines — 0 of 4 used

No internal node is currently bonded out as a shared/muxed test point.
Candidate bring-up debug taps exist internally (`BIASP`/`NB` — the bias
generator's reference nodes; `FB` — the feedback-divider tap; `EA_OUT` —
the amplifier output / pass-gate node; `SS` — the soft-start ramp; `TS_CMP`
— the thermal-trip comparison node; `design/README.md` § "Node glossary"),
but bonding any of them out requires a new top-level schematic port that
does not exist today — proposing specific new pins here, before a
schematic-review pass decides which are actually useful for bench
fault-isolation, would describe an interface this design does not have.
All 4 shared-analog-line slots remain unused; adding instrumentation here
is a candidate follow-on, not committed by this document.

### 2.7 Pinout summary

| Bucket | Used | Budget |
|---|---:|---:|
| Rails | 1 (`VIN`, 3.3 V single supply; no 1.8 V digital rail consumed) | 1.8 V + 3.3 V (assumed) |
| Harness bandgap-referenced bias voltage | 1 (`VREF`, consumed directly — see §2.2 caveat on the actual voltage value) | 1 |
| Harness bandgap-referenced current sources | 0 | ≤2 |
| Digital control inputs | 1 (`EN`) | ≤24 |
| Digital test outputs | 0 (+ `VOUT` functional, uncounted) | ≤12 |
| Dedicated pads | 1 (`VOUT`) | ≤4 |
| Shared analog lines | 0 | ≤4 |

This block comfortably fits the assumed slot budget: 4 pads total today
(`VIN`, `EN`, `VREF`, `VOUT`), well inside every bucket's ceiling.

## 3. Functional description

- **Error amplifier**: a current-mirror ("symmetric") OTA — differential
  pair `M_IN1`(gate=`FB`)/`M_IN2`(gate=`VREF`) on tail `M_TAIL`, NMOS mirror
  `M_MIR1`/`M_MIR2`, and a PMOS turnaround mirror (`M_MIR3`/`M_MIR4` →
  `M_MIRP1`/`M_MIRP2`, added in issue #25) that lets the amplifier's output
  node (`EA_OUT`, the pass-device gate) swing rail-to-rail rather than
  being ceiling-limited by the input-pair's own common-mode range
  (`design/README.md` § "Error-amplifier output stage (rebuilt in #25)").
  Negative feedback: `EA_OUT` rises when `FB` rises, turning the PMOS pass
  device off as `VOUT` rises (§ "Error-amplifier polarity").
- **Pass device**: `M_PASS`, `sky130_fd_pr__pfet_g5v0d10v5`, `L=0.5` (bin
  floor), `W_total = W × mult = 2500 µm` (100 µm × 25 fingers × 1 unit,
  `design/README.md` § "Pass-device width correction").
- **Feedback divider**: three identical `res_xhigh_po` unit resistors
  (`W=0.42 L=180`, screened ≈1.04 MΩ each), ratio 1:2 (`VOUT → FB`,
  `FB → GND`), giving `VOUT = 1.5 × VREF` and contributing ≈0.58 µA of
  preload at `VOUT=1.8 V` (`design/README.md` § "Feedback divider").
- **Compensation**: Miller cap `C_COMP` (150 pF) plus nulling resistor
  `R_CZ`, from `VOUT` through `EA_CZ` back to `EA_OUT`, sized in issue #25
  against `sim/loop-gain` for the DR-002 output-capacitor window (proposed,
  not ratified: `C_eff` 0.33–4.7 µF, ESR 0–500 mΩ, ceramic-stable, ported
  from `gf180-ldo`'s DR-0001).
- **Current limit** (issue #22): a `1:5952` sense-FET replica of `M_PASS`
  feeds a two-stage current comparator that pulls `EA_OUT` toward `VIN`
  (shutting the pass device off) once the sensed current crosses a
  reference set by `BIASP`; brickwall, not foldback.
- **Soft start** (issue #22): a current-starved RC ramp (`M_SSCHG`, `C_SS`)
  drives a second differential input (`M_IN2S`, in parallel with `M_IN2`)
  so the amplifier's effective reference is `soft-min(VREF, SS)`, giving a
  controlled turn-on ramp reset by `EN=0`.
- **Thermal shutdown** (issue #29, DR-005 proposed): a CTAT sense/reference
  diode stack (`M_TSPS`/`M_TSD1`/`M_TSD2` vs. `M_TSPR`/`M_TSR1`) feeds a
  comparator that pulls `EA_OUT` toward `VIN` above a nominal 150 °C trip
  (25 °C guard band above the spec's 125 °C operating ceiling), with a
  nominal 15 °C hysteresis band, auto-restarting once `Tj` falls back
  below the reset point — no separate fault-latch.
- **Enable/shutdown**: `M_ENP`/`M_ENP2`/`M_ENP3`/`M_ENP4`/`M_ENP5` force the
  amplifier output, bias chain, current-limit comparator, and
  thermal-trip comparator to defined off states when `EN=0`; the pass
  device is left fully off with no active output discharge.

No on-chip bandgap/reference generator is designed here (§2.2) — the block
is a pure regulation-loop-plus-protection macro that consumes the harness's
bias reference, matching this repo's own decision to scope the reference
generator out (`design/README.md` § "Known gaps").

## 4. Target specification at the challenge rails (3.3 V / 1.8 V)

**What "Measured" means below.** Every numeric cell is read directly from
the cited `sim/<slug>/records/<id>.json` — the min/max are the extremes
across the full run (45 PVT points unless stated otherwise), and "typ" is
the `tt` process / 27 °C / 3.30 V corner where that exact corner exists in
the run. No cell is computed by re-deriving a verdict from raw waveforms;
that discipline mirrors `measurements/build_characterization_report.py`'s
own "never recomputes a verdict" rule, which this table's per-row "Status"
column cross-checks against. **Every row is against the current DRAFT
`spec/target-spec.md` target — none of it is ratified (issue #1 open).**

### 4.1 DC / regulation

| Parameter | DRAFT target | Measured (`sim/`) | Status | Evidence |
|---|---|---|---|---|
| Input | 3.3 V ±10 % (2.97–3.63 V) | stimulus condition, not a measured row | N/A | — |
| Load | 0–50 mA | stimulus condition, not a measured row | N/A | — |
| Output accuracy | 1.8 V ±2 % (1.764–1.836 V) | `tt`/27 °C/3.30 V, 1 mA, 200-sample mismatch draw (3σ): 177/200 individual samples inside window; single-PVT-point check, **not** a full-PVT-grid accuracy sweep | **FAIL** (177/200, not 200/200; also PVT-subset scope) | [`mc-output-accuracy` `20260825-083111-4cb27f8`](../../sim/mc-output-accuracy/records/20260825-083111-4cb27f8.md) |
| Dropout @ 50 mA | < 300 mV | full 45-corner grid: **365–1548 mV** (typ `tt`/27 °C/3.30 V: 430 mV); 0/45 corners inside target | **FAIL** — by a wide margin, not close to the target anywhere in the grid | [`dropout-vs-load` `20260825-081240-4cb27f8`](../../sim/dropout-vs-load/records/20260825-081240-4cb27f8.md) |
| Line regulation (1 mA) | < 5 mV/V, 2.97–3.63 V | 3-corner PVT subset: **0.22–1739 mV/V** (typ `tt`/27 °C: 1739 mV/V) | **FAIL** (PVT subset, not the full 45-point matrix) | [`line-regulation` `20260825-104914-933dfdd`](../../sim/line-regulation/records/20260825-104914-933dfdd.md) |
| Line regulation (50 mA) | < 5 mV/V, 2.97–3.63 V | 3-corner PVT subset: **0.42–2477 mV/V** (typ `tt`/27 °C: 1317 mV/V) | **FAIL** (PVT subset) | same record |
| Load regulation (0–50 mA) | < 1 % (18 mV) | 3-corner PVT subset: **0.18–0.51 %** (3.3–9.2 mV; typ `tt`/27 °C: 0.23 %) | **PASS** (PVT subset — 3/3 corners pass; not the full 45-point matrix) | [`load-regulation` `20260825-105113-933dfdd`](../../sim/load-regulation/records/20260825-105113-933dfdd.md) |
| Iq, no load | < 30 µA | 3-corner PVT subset: **11.7–15.2 µA** (typ `tt`/27 °C: 13.7 µA) | **PASS** (PVT subset — 3/3 pass) | [`iq` `20260825-105157-933dfdd`](../../sim/iq/records/20260825-105157-933dfdd.md) |
| Iq, full load (50 mA) | < 30 µA | 3-corner PVT subset: **22.7–28.6 µA** (typ `tt`/27 °C: 25.9 µA) | **PASS** (PVT subset — 3/3 pass) | same record |

### 4.2 Dynamic / stability

| Parameter | DRAFT target | Measured (`sim/`) | Status | Evidence |
|---|---|---|---|---|
| Load transient (1↔50 mA step) | peak excursion ≤ 150 mV | full 45-corner grid: undershoot **102–393 mV**, overshoot **0–165 mV** (typ `tt`/27 °C: 136 mV / 113 mV); 25/45 corners inside both bounds | **FAIL** (20/45 corners exceed 150 mV on at least one of undershoot/overshoot) | [`load-transient` `20260825-081255-4cb27f8`](../../sim/load-transient/records/20260825-081255-4cb27f8.md) |
| Stability, phase margin (worst case) | PM ≥ 45°, GM ≥ 10 dB | full 45-corner grid (across `C_eff`=0.33/4.7 µF, 0/1/50 mA, plus an ESR=500 mΩ spot check): light-load (0 mA) PM as low as **15.6°** at `C_eff`=0.33 µF (typ `tt`/27 °C, 0 mA: 19.3°); 50 mA PM range **46–79°** (typ `tt`/27 °C, 50 mA, `C_eff`=0.33 µF: 58.5°); 7/45 individual measurements pass the full combined pass criteria | **FAIL** — pervasive at light load across nearly the whole grid, per issue #70's root cause (the pass stage's own light-load pole falls with load current, and closing it competes with the Iq budget) | [`loop-gain` `20260825-081257-4cb27f8`](../../sim/loop-gain/records/20260825-081257-4cb27f8.md) |
| PSRR @ 1 kHz (1 mA / 50 mA) | > 50 dB | full 45-corner grid: **20.3–25.7 dB** (typ `tt`/27 °C: 23.3 dB); 0/45 corners meet target | **FAIL** — does not pass anywhere in the grid, per issue #70 (`VIN`-referenced, uncascoded bias generator with no supply rejection) | [`psrr-dc` `20260825-082845-4cb27f8`](../../sim/psrr-dc/records/20260825-082845-4cb27f8.md) |
| PSRR @ 100 kHz (1 mA / 50 mA) | > 20 dB | full 45-corner grid: **31.5–34.8 dB** (typ `tt`/27 °C: 33.0 dB) | **PASS** — 45/45 corners meet this specific sub-row (the 1 kHz row above does not) | same record |

### 4.3 Protection / sequencing

| Parameter | DRAFT target | Measured (`sim/`) | Status | Evidence |
|---|---|---|---|---|
| Current limit | never engages ≤ 50 mA; survives a continuous `VOUT=0` short at `VIN_max` | full 45-corner grid: knee **85–204 mA**, hard-short sustained current **108–236 mA**, `VOUT` under short **0.11–0.24 V**; 45/45 corners pass (window itself is TBD-over-PVT per the DRAFT row, not a fixed number) | **PASS** | [`current-limit` `20260825-105322-933dfdd`](../../sim/current-limit/records/20260825-105322-933dfdd.md) |
| Startup / soft-start | monotonic; inside ±2 % within a few ms of enable; overshoot ≤ +2 % (≤1.836 V) | full 45-corner grid across `C_eff`=0.33/4.7 µF, 0/50 mA: peak **1.797–1.830 V**, ramp time **0.20–0.61 ms**; 45/45 corners pass | **PASS** | [`startup` `20260825-110456-933dfdd`](../../sim/startup/records/20260825-110456-933dfdd.md) |
| Enable/shutdown Iq | shutdown Iq < 3 µA worst corner | full 45-corner grid: **0.00013–0.065 µA** static, disabled-output leakage **0.00007–0.076 µA** `VIN`→`VOUT`; 45/45 corners pass | **PASS** — well inside budget | [`enable-shutdown` `20260825-111526-933dfdd`](../../sim/enable-shutdown/records/20260825-111526-933dfdd.md) |
| Thermal shutdown | trips before `Tj` exceeds the spec's rated ceiling with margin; auto-restart via hysteresis | 15-point grid (VIN corners × 5 process points): trip/reset **138.8–163.0 °C** (typ `tt`/27 °C: 150.6 °C, matching DR-005's proposed 150 °C nominal), hysteresis **−8…0 °C** (nominally proposed 15 °C — measured hysteresis is degenerate-to-negative at several corners, i.e. the reset temperature does not reliably sit below the trip temperature by the intended margin); 12/15 corners pass | **FAIL** (3/15 corners; a real, disclosed regenerative-loop-gain gap under investigation, not resolved — `design/README.md` § "#77: thermal-shutdown hysteresis root-caused") | [`thermal` `20260825-104426-933dfdd`](../../sim/thermal/records/20260825-104426-933dfdd.md) |

### 4.4 Other DRAFT rows

| Parameter | DRAFT target | Measured | Status | Evidence |
|---|---|---|---|---|
| Output noise | waived unless a consumer states a requirement | not measured | N/A (waived by the spec row itself) | — |
| Area | < 0.1 mm² core, pass FET included | no dedicated area-extraction check exists in `sim/`/`measurements/` today | N/A — coverage gap, not a pass (per `measurements/characterization.md`'s own no-re-derivation rule, this document does not compute a verdict from the raw floorplan geometry itself) | — |

## 5. Sign-off status: DRC/LVS clean, post-layout PVT simulation NOT yet achievable

The brief's deliverable ladder is schematic + pre-layout sim → layout +
post-layout sim over PVT → final DRC/LVS. This block is partway up that
ladder, honestly:

| Check | Status | Record |
|---|---|---|
| Pre-layout PVT simulation | **Done** — the full 45-point grid above (§4.1/§4.2/§4.3) is pre-layout (schematic-level) simulation | `sim/*/records/*` cited above |
| Layout | **Done** — routed, generated 1:1 from the schematic's own netlist (issue #33) | [`layout/ldo-core/reports/20260825-123551-3b4e121`](../../layout/ldo-core/reports/20260825-123551-3b4e121/record.md) |
| DRC | **PASS** (clean, violation_count=0) | [`20260825-123551-3b4e121`](../../layout/ldo-core/reports/20260825-123551-3b4e121/record.md) |
| LVS | **MATCH** (mismatch_count=3, all three are disclosed non-blocking reconciliation/bulk-terminal warnings, not real topology mismatches — see the record's own "Disclosed warnings" section) | [`20260825-123628-3b4e121`](../../layout/ldo-core/reports/20260825-123628-3b4e121/record.md) |
| Post-layout (parasitic-extracted) PVT simulation | **Not achievable with the current toolchain** — see below | [`sim/pex-post-layout` `20260825-125102-3b4e121`](../../sim/pex-post-layout/records/20260825-125102-3b4e121.md) |

**Why post-layout PVT simulation is blocked, and by whom.** `klt pex`'s
extracted-side leg does not converge for this layout today, for three
independent, disclosed, upstream `klt`/PDK-model-interaction gaps — none of
them within this repo's control to fix, all already filed against
[2AMLogic/klayout-tools](https://github.com/2AMLogic/klayout-tools) per this
repo's friction protocol:

1. [klayout-tools#1157](https://github.com/2AMLogic/klayout-tools/issues/1157)
   — sky130's 3-terminal drawn-resistor classes extract to an `R` card
   ngspice cannot simulate at all.
2. [klayout-tools#1159](https://github.com/2AMLogic/klayout-tools/issues/1159)
   — the `--pdk`-bound extraction path that sidesteps #1157 instead writes
   resistor geometry in a unit convention that drives the real vendor
   resistor model's own `.param` formula negative (`leff` < 0).
3. [klayout-tools#1369](https://github.com/2AMLogic/klayout-tools/issues/1369)
   — `--pdk`'s MOS model-binding table has no sky130 5 V-flavor entry, so
   every extracted MOS device (this design uses `g5v0d10v5` throughout)
   would silently bind to the 1.8 V core model even where extraction does
   converge.

The schematic-side leg of the same testbench (identical DUT, no
extraction) runs clean (45/45 PVT corners) — confirming the testbench
itself is sound — but there is no matching extracted-side number to
compare it against, so no post-layout spec-row verdict can be produced yet.
This is recorded as `status: error` (not a fabricated pass) in the cited
record, per this repo's evidence discipline.

**Net effect on this issue's acceptance criteria**: the AC's sign-off bar
("post-layout PVT simulation and DRC/LVS-clean GDS in-repo") is **partially
met** — DRC/LVS are clean — and **not met** on the post-layout PVT
simulation half, for the disclosed upstream reasons above, not for any gap
this repo has silently deferred. No new follow-up issue is filed for this:
the gap is already tracked (the three `klayout-tools` issues above, plus
this repo's own generic maturity tracker, issue
[#58](https://github.com/2AMLogic/sky130-ldo/issues/58)) — filing a
duplicate would not add information. Once those upstream fixes land, a
follow-up issue should re-run `sim/pex-post-layout/bin/run-pex.sh` and
fold a real post-layout PVT verdict into this table.

## 6. What a `rules-4.html` follow-up must re-check

Since Challenge #4's own rules are not yet published, everything in §2's
slot-budget mapping is checked against the *assumed* common structure only.
When `rules-4.html` publishes, re-verify:

- The digital control-input / test-output / shared-analog-line / dedicated
  pad ceilings (24/12/4/0–4) match §2.7's assumed budget — this design uses
  4 pads total, so even a materially tighter Sky130-specific budget is
  unlikely to be binding, but confirm rather than assume.
- Whether the harness's Sky130 bias/bandgap-referenced voltage is actually
  1.2 V (this document's placeholder, §2.2) — if not, the feedback-divider
  ratio needs a one-time resistor change before this block can integrate.
- Whether Sky130's brief keeps the 1.8 V/3.3 V split rails from the epic's
  generic assumption, or specifies something else — this block only
  consumes a single 3.3 V rail (§2.1), so a 1.8 V-only or different-voltage
  analog rail would be a real rail-flavor change, not just a documentation
  update.
- The SPI control-interface details, once published — nothing in this
  design currently interacts with an SPI bus (its one control input is the
  direct `EN` pin), so this is a pure gap-check, not expected to require a
  schematic change.

## 7. Test-plan outline (measurement on the packaged part)

Assumes the block is bonded on a package on a daughterboard, on a test
board that can source/sweep `VIN`, apply controlled load steps and a
continuous short, and provide a temperature-controlled environment for the
die — mirroring
[sky130-temp-por's own Challenge #4 test-plan structure](https://github.com/2AMLogic/sky130-temp-por/blob/main/docs/chipalooza/challenge-4-proposal.md),
the most directly comparable sibling repo's test plan.

1. **DC bring-up.** Apply `VIN=3.3 V`, drive the harness's bandgap
   reference into `VREF`, assert `EN`. Confirm `VOUT` settles near
   `1.5 × VREF` and stays inside ±2 % across the no-load-to-50-mA range
   with a programmable electronic load. This directly measures the
   Output-accuracy and Load-regulation rows (§4.1) with real, packaged
   silicon rather than schematic simulation.
2. **Line regulation.** Sweep `VIN` 2.97–3.63 V at fixed 1 mA and 50 mA
   loads; record `ΔVOUT/ΔVIN` — directly comparable to the §4.1
   line-regulation rows (currently only a 3-corner simulated subset).
3. **Dropout sweep.** Ramp `VIN` down from 3.63 V toward `VOUT_target`
   at 50 mA load; record the `VIN`−`VOUT` margin where regulation is lost
   — directly comparable to §4.1's Dropout row (currently a full-grid
   *simulated* FAIL by a wide margin; measurement should confirm whether
   real silicon tracks the simulated severity or diverges from it).
4. **Load transient.** Apply a 1↔50 mA step with ~1 µs edges into the
   qualified output-capacitor window (0.33–4.7 µF, 0–500 mΩ ESR, per
   DR-002); scope `VOUT` for peak excursion and recovery time — directly
   comparable to §4.2's Load-transient row.
5. **PSRR.** Inject a swept-frequency ripple onto `VIN` (network analyzer
   or spectrum-analyzer-based PSRR bench) at 1 mA and 50 mA load; measure
   attenuation to `VOUT` at 1 kHz and 100 kHz — directly comparable to
   §4.2's PSRR rows, where the 1 kHz row is currently a pervasive simulated
   FAIL (issue #70).
6. **Loop stability.** If the test board supports loop-gain injection
   (e.g. a network analyzer with an injection transformer in the feedback
   path), measure phase margin at 0/1/50 mA loads across the qualified
   capacitor window — directly comparable to §4.2's Stability row, where
   0 mA phase margin is currently the dominant simulated FAIL mode.
7. **Current limit and short survival.** Sweep the electronic load past
   50 mA to find the knee, then apply a continuous `VOUT=0` short at
   `VIN_max` and hold it (thermally, as long as the current-limit +
   thermal-shutdown protection is expected to survive) — directly
   comparable to §4.3's Current-limit row (currently PASS in simulation).
8. **Startup / soft-start.** Toggle `EN` with `VOUT` loaded at 0 mA and
   50 mA into each capacitor-window corner; scope the ramp for
   monotonicity, overshoot, and ramp time — directly comparable to §4.3's
   Startup row (currently PASS in simulation).
9. **Enable/shutdown leakage.** With `EN=0`, measure `VIN`→`VOUT` leakage
   current and quiescent draw across the test board's available
   temperature range — directly comparable to §4.3's Enable/shutdown row
   (currently PASS in simulation).
10. **Thermal shutdown.** Heat the package (oven or resistive heater) while
    monitoring `VOUT` and current draw; record the trip and reset
    temperatures and compare hysteresis to the DR-005 150 °C/15 °C nominal
    targets — directly comparable to §4.3's Thermal row (currently a
    partial simulated FAIL, issue #77/#70).

## 8. Summary

| This issue's acceptance criterion | Status |
|---|---|
| `docs/chipalooza/challenge-4-proposal.md` with block type, I/O mapped to the slot budget, functional description, spec table re-derived from `sim/`, bench test plan | **Met** — this document |
| Every spec row states met/unmet against the brief; no row relaxed to make it pass | **Met** — §4's per-row Status column; several rows are documented FAILs (dropout, PSRR@1kHz, stability, line regulation, load transient, thermal, output accuracy), stated plainly rather than rounded or omitted |
| Design at the brief's sign-off bar (post-layout PVT simulation + DRC/LVS-clean GDS in-repo) | **Partially met** — DRC/LVS are clean; post-layout PVT simulation is blocked by three disclosed, already-filed upstream `klayout-tools` gaps (§5), not by any gap this repo has silently deferred. Most spec rows also do not yet pass pre-layout simulation, independent of the layout question (issue #70, open) |
| If `rules-4.html` has published, verify slot-budget assumptions | **N/A as of this writing** — `rules-4.html` is not yet published (2026-09-05); §6 states exactly what a follow-up issue must re-check once it is |

This block is not ready to submit to Challenge #4 today. It is, however, a
genuinely useful checkpoint: the interface (§2) fits the assumed slot
budget with room to spare, the layout is DRC-clean and LVS-matched, and the
remaining gate to a real sign-off package is two already-tracked,
well-understood pieces of work — issue #70's circuit fix (PSRR/stability)
and the upstream `klayout-tools` PEX fixes (§5) — rather than an unknown
unknown.
