v {xschem version=3.4.7 file_version=1.2
* sky130-ldo core regulation loop + protection/sequencing (issues #14, #22, #25).
*
* Clean-room forward design against spec/target-spec.md (DRAFT) and the
* ratified framing in spec/decision-records/DR-001-pass-device-supply-framing.md
* (pass device sky130_fd_pr__pfet_g5v0d10v5, 3.3V +-10% in / 1.8V out /
* 0-50mA, port parity with 2AMLogic/gf180-ldo). Sizing methodology follows
* spec/decision-records/DR-003-sky130-device-characterization.md: pass-device
* sizing point is V_sg = V_out + dropout (~2.10V), NOT V_in_min, and the
* binding corner is {ss, sf} at 125C (co-binding, size to the worse of the
* two). See design/README.md for the full design-intent writeup, node
* glossary and open items.
*
* Topology (all active devices are sky130_fd_pr__*_g5v0d10v5 -- DR-001's
* Consequences section notes the amplifier output stage cannot be
* core-flavor regardless, since the pass gate must swing to VIN; this
* schematic keeps the *whole* amplifier/bias/protection chain on the 5V-gate
* family rather than adopting the deferred framing (C) core-device-amplifier
* refinement):
*   - M_PASS: pfet_g5v0d10v5 series pass device, VIN -> VOUT.
*   - M_IN1/M_IN2 + M_MIR1/M_MIR2 + M_MIR3/M_MIR4 + M_MIRP1/M_MIRP2 +
*     M_TAIL: single-stage current-mirror ("symmetric") OTA error amplifier.
*     "+" input = FB (M_IN1), "-" input = VREF (M_IN2) -- this polarity is
*     load-bearing: EA_OUT must rise when FB rises so the pass gate turns
*     OFF as VOUT rises (negative feedback). See design/README.md
*     "Error-amplifier polarity" for the derivation (verified by an OP
*     sanity sweep, not derivation alone -- an earlier draft had this
*     swapped and latched to a rail).
*     Issue #25 promoted this stage from the #14/#22 five-transistor OTA,
*     in which EA_OUT was the *drain of the PMOS input device M_IN2* and so
*     could never rise above EA_TAIL ~= V_in,cm + V_sg ~= 2.5V. That ceiling
*     -- not a gain shortfall -- is what made the loop rail at light load and
*     high VIN. Here the VREF-side branch current is turned around twice
*     (M_MIR3/M_MIR4 -> PB -> M_MIRP1/M_MIRP2) so that EA_OUT is the drain of
*     a PMOS whose SOURCE is VIN, and the pass gate can be driven to VIN. The
*     amplifier stays a SINGLE gain stage: both turnaround nodes (EA_D2, PB)
*     are diode-loaded and therefore low-impedance, so their poles sit
*     decades above crossover and the loop keeps the two-pole shape Miller
*     compensation is designed for. That is the difference from the
*     second-gain-stage candidate screened and rejected during #22, which
*     added a third low-frequency pole and oscillated.
*   - R_BIAS + M_BIASN1 + M_BIASN2 + M_BIASP1: simple resistor-referenced
*     self-biased current mirror (textbook technique, e.g. Razavi ch.5;
*     not derived from any third party's implementation) supplying BIASP to
*     the PMOS current sources. No Iq budget exists yet (DR-003 declines to
*     set one) -- these sizes are an illustrative, functional starting point,
*     not a calibrated/verified budget.
*   - M_ENP / M_ENP2 / M_ENP3 / M_ENN / M_ENN2: enable/shutdown. EN is
*     active-high, full-rail (0/VIN). EN=0 drives M_ENP2 to force BIASP->VIN
*     (kills the whole PMOS bias/tail chain), M_ENP to force EA_OUT->VIN
*     (forces M_PASS fully off), and M_ENP3 to force CL_CMP->VIN (gives the
*     current-limit comparator a defined off state); M_ENN/M_ENN2 cut every
*     NMOS ground return in the bias/amp core.
*   - R_FB_A/R_FB_B/R_FB_C: three identical "unit" res_xhigh_po resistors
*     forming the feedback divider per spec/target-spec.md's "divider as a
*     unit-resistor string" note. Ratio 1:2 (one unit VOUT->FB, two units
*     FB->GND) sets VOUT = 1.5 x VREF; see design/README.md for the assumed
*     VREF interface value, why the reference common mode was raised from the
*     first draft's 0.6V, and the measured (not invented) unit value.
*   - C_COMP + R_CZ: Miller compensation with a nulling resistor, VOUT ->
*     EA_CZ -> EA_OUT, across the inverting EA_OUT->VOUT pass stage. Sized in
*     issue #25 against sim/loop-gain (an AC loop-gain/phase-margin testbench
*     walking DR-002's proposed C_out/ESR window), not from transient smoke
*     tests -- see design/README.md "Compensation (sized in #25)".
*
* Protection / sequencing added by issue #22 (spec rows "Current limit" and
* "Startup / soft-start"):
*   - M_SENSE + M_CLN1/M_CLN2 + M_CLP + M_CLIM + C_CL: constant-current
*     (brickwall) limit. M_SENSE is a scaled replica of M_PASS (same L, same
*     gate, same source) so its drain current tracks the pass current at a
*     nominal 0.42um : 2500um = 1:5952 ratio; M_CLN1/M_CLN2 mirror that sense
*     current down by 20:1.6 and compare it against the bias-referenced
*     current in M_CLP at the high-impedance node CL_CMP. Over-current pulls
*     CL_CMP low, turning M_CLIM on, which pulls the pass gate EA_OUT toward
*     VIN -- a second, normally-inactive feedback loop that throttles M_PASS
*     rather than latching it off. See design/README.md for the measured
*     limit characteristic and its VIN dependence.
*   - M_INVP/M_INVN + M_SSDIS + M_SSCHG + C_SS + M_IN2S: soft start. The EN
*     inverter produces ENB, which discharges C_SS whenever the block is
*     disabled so every enable starts from SS = 0. On enable, M_SSCHG (a
*     heavily scaled-down mirror of the PMOS bias unit) charges C_SS with a
*     near-constant current, giving a linear ramp on SS. M_IN2S is a replica
*     of M_IN2 wired in parallel with it on the amplifier's "-" input, so the
*     effective reference the loop servos to is the (soft) minimum of VREF
*     and SS: VOUT tracks 1.5 x SS on the way up and hands over to 1.5 x VREF
*     when SS passes it. This replaces the hard on/off enable of issue #14.
*
* Closed by issue #25: the error-amplifier output-swing ceiling (the
* current-mirror OTA above) and the compensation placeholder (C_COMP/R_CZ
* are now sized against sim/loop-gain).
*
* Explicitly NOT in this schematic (see design/README.md "Known gaps /
* follow-on scope"): thermal shutdown (decomposed to its own issue -- the
* spec table states no trip temperature and this block has no
* temperature-stable on-chip reference to trip against), an actual on-chip
* voltage reference (VREF is an external port here), and phase margin at the
* no-load / minimum-C_eff end of DR-002's window, which sim/loop-gain records
* below the DRAFT Stability row's 45 deg (with a very large gain margin --
* see the DR-002 append and design/README.md for why that corner is a
* pole/zero doublet dip rather than a near-oscillation).
*
* Connectivity is entirely by net label (lab_pin / ipin / opin on every
* device pin), no drawn wires -- same convention as
* sim/pdk-smoke/testbench/tb_pdk_smoke.sch. Netlists cleanly with:
*   xschem -n -q -x -s -o <outdir> --rcfile sim/xschemrc design/ldo_3v3in_1v8out.sch
}
G {}
K {}
V {}
S {}
E {}
T {sky130-ldo core regulation loop + current limit + soft start -- issues #14, #22, #25
pass device: sky130_fd_pr__pfet_g5v0d10v5 (DR-001 ratified framing A)
error amp + bias + protection: all 5V-gate flavor (DR-001 Consequences)
connectivity by net label (lab_pin/ipin/opin), no drawn wires
see design/README.md for node glossary, sizing rationale and open items} -700 -1400 0 0 0.35 0.35 {}

* ---- ports ----
C {devices/ipin.sym} -700 -100 0 0 {name=p_vin lab=VIN}
T {VIN: 3.3V +-10% input (2.97-3.63V, DRAFT)} -680 -100 0 0 0.25 0.25 {}
C {devices/ipin.sym} -700 -300 0 0 {name=p_en lab=EN}
T {EN: active-high enable, full-rail (0/VIN)} -680 -300 0 0 0.25 0.25 {}
C {devices/ipin.sym} -700 -500 0 0 {name=p_vref lab=VREF}
T {VREF: external reference input (assumed ~1.2V; see README)} -680 -500 0 0 0.25 0.25 {}
C {devices/opin.sym} -700 -700 0 0 {name=p_vout lab=VOUT}
T {VOUT: 1.8V +-2% output (DRAFT), 0-50mA} -680 -700 0 0 0.25 0.25 {}

* ---- bias generator: R_BIAS + M_BIASN1/M_BIASN2 (NMOS mirror) + M_BIASP1 (PMOS diode) ----
C {sky130_fd_pr/res_high_po.sym} 0 -100 0 0 {name=R_BIAS W=0.42 L=1500 model=res_high_po spiceprefix=X mult=1}
C {devices/lab_pin.sym} 0 -70 0 0 {name=p_rbias1 lab=VIN}
C {devices/lab_pin.sym} 0 -130 0 0 {name=p_rbias2 lab=NB}
C {devices/lab_pin.sym} -20 -100 0 0 {name=p_rbias3 lab=0}
T {R_BIAS: res_high_po, W=0.42 L=1500 -- measured ~1.22Mohm (tt/27C screening
deck, not sim/ evidence, see README) -> ~1-2uA reference current} 40 -100 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 0 -400 0 0 {name=M_BIASN1
L=1
W=4
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 20 -430 0 0 {name=p_mbn1_d lab=NB}
C {devices/lab_pin.sym} -20 -400 0 0 {name=p_mbn1_g lab=NB}
C {devices/lab_pin.sym} 20 -370 0 0 {name=p_mbn1_s lab=BIAS_ENN}
C {devices/lab_pin.sym} 20 -400 0 0 {name=p_mbn1_b lab=0}
T {M_BIASN1: diode-connected NMOS reference, sets I_BIAS with R_BIAS.
Source returns through M_ENN (below), not straight to 0 -- see M_ENN.} 40 -400 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 250 -400 0 0 {name=M_ENN
L=0.5
W=10
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 270 -430 0 0 {name=p_menn_d lab=BIAS_ENN}
C {devices/lab_pin.sym} 230 -400 0 0 {name=p_menn_g lab=EN}
C {devices/lab_pin.sym} 270 -370 0 0 {name=p_menn_s lab=0}
C {devices/lab_pin.sym} 270 -400 0 0 {name=p_menn_b lab=0}
T {M_ENN: EN-gated ground return for R_BIAS/M_BIASN1. Without this switch
the NMOS bias-reference branch would keep drawing I_BIAS even at EN=0,
defeating the shutdown-Iq intent -- found via the OP sanity check in
design/README.md, not by inspection alone. EN=0 -> M_ENN off -> R_BIAS's
branch current drops to leakage; EN=1 -> M_ENN a near-short (few-uA level,
negligible added IR drop at this current).} 40 -520 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 0 -700 0 0 {name=M_BIASN2
L=1
W=4
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 20 -730 0 0 {name=p_mbn2_d lab=BIASP}
C {devices/lab_pin.sym} -20 -700 0 0 {name=p_mbn2_g lab=NB}
C {devices/lab_pin.sym} 20 -670 0 0 {name=p_mbn2_s lab=BIAS_ENN}
C {devices/lab_pin.sym} 20 -700 0 0 {name=p_mbn2_b lab=0}
T {M_BIASN2: 1:1 NMOS mirror of M_BIASN1, sinks I_BIAS through M_BIASP1.
Source also returns through the shared M_ENN switch, not straight to 0:
found by simulation that gating only M_BIASN1 let NB float up to VIN when
EN=0 (no ground return to hold it down), which then drove M_BIASN2 ON hard
via its NB gate and shot current from VIN through M_ENP2 -> BIASP ->
M_BIASN2 during "shutdown" -- the opposite of the intent. Both NMOS
bias-diode sources must be cut together.} 40 -700 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 0 -1000 0 0 {name=M_BIASP1
L=1
W=10
nf=2
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 20 -970 0 0 {name=p_mbp1_d lab=BIASP}
C {devices/lab_pin.sym} -20 -1000 0 0 {name=p_mbp1_g lab=BIASP}
C {devices/lab_pin.sym} 20 -1030 0 0 {name=p_mbp1_s lab=VIN}
C {devices/lab_pin.sym} 20 -1000 0 0 {name=p_mbp1_b lab=VIN}
T {M_BIASP1: diode-connected PMOS, sets BIASP -- the "unit" PMOS bias size
that M_TAIL, M_CLP and M_SSCHG below are scaled against} 40 -1000 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 0 -1300 0 0 {name=M_ENP2
L=0.5
W=10
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 20 -1270 0 0 {name=p_menp2_d lab=BIASP}
C {devices/lab_pin.sym} -20 -1300 0 0 {name=p_menp2_g lab=EN}
C {devices/lab_pin.sym} 20 -1330 0 0 {name=p_menp2_s lab=VIN}
C {devices/lab_pin.sym} 20 -1300 0 0 {name=p_menp2_b lab=VIN}
T {M_ENP2: EN=0 forces BIASP->VIN, killing the whole PMOS bias/tail chain
(quiescent current cut at the bias-generator root, not just the tail)} 40 -1300 0 0 0.2 0.2 {}

* ---- error amplifier: 5T OTA, PMOS input pair + NMOS mirror load ----
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 600 -100 0 0 {name=M_TAIL
L=2
W=40
nf=8
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 620 -70 0 0 {name=p_mtail_d lab=EA_TAIL}
C {devices/lab_pin.sym} 580 -100 0 0 {name=p_mtail_g lab=BIASP}
C {devices/lab_pin.sym} 620 -130 0 0 {name=p_mtail_s lab=VIN}
C {devices/lab_pin.sym} 620 -100 0 0 {name=p_mtail_b lab=VIN}
T {M_TAIL: tail current source. L raised 1 -> 2 in issue #22 together with
the input pair and the mirror load: the corrected (25x wider) M_PASS needs a
much higher-gain amplifier to be throttled at light load. See README
"Amplifier sizing revision".
W raised 20 -> 40 (nf 4 -> 8, same finger width) in issue #25: the tail
sets the amplifier's transconductance Gm, and under Miller compensation the
loop's unity-gain frequency is Gm/(2*pi*C_COMP). At the no-load / minimum-
C_out corner the loop has to cross ABOVE a low-frequency pole/zero doublet
to keep phase margin, which needs a higher Gm -- see README "Compensation
(sized in #25)" for the measured phase-margin-vs-tail data and for the Iq
cost this buys it with (the DRAFT Iq row is the binding constraint on how
far this can go, which is why it stops at 2x rather than 6x).} 640 -100 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 600 -400 0 0 {name=M_IN1
L=2
W=10
nf=2
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 620 -370 0 0 {name=p_min1_d lab=EA_D1}
C {devices/lab_pin.sym} 580 -400 0 0 {name=p_min1_g lab=FB}
C {devices/lab_pin.sym} 620 -430 0 0 {name=p_min1_s lab=EA_TAIL}
C {devices/lab_pin.sym} 620 -400 0 0 {name=p_min1_b lab=VIN}
T {M_IN1: "+" input = FB (mirror-diode side, EA_D1) -- see README
"Error-amplifier polarity" for why this side must be FB, not VREF} 640 -400 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 600 -700 0 0 {name=M_IN2
L=2
W=10
nf=2
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 620 -670 0 0 {name=p_min2_d lab=EA_D2}
C {devices/lab_pin.sym} 580 -700 0 0 {name=p_min2_g lab=VREF}
C {devices/lab_pin.sym} 620 -730 0 0 {name=p_min2_s lab=EA_TAIL}
C {devices/lab_pin.sym} 620 -700 0 0 {name=p_min2_b lab=VIN}
T {M_IN2: "-" input = VREF. Its drain is EA_D2, the second mirror-diode
node (issue #25) -- NOT the pass gate. In the issue-#14/#22 5T OTA this
drain WAS EA_OUT, which capped the pass-gate voltage at EA_TAIL and is
exactly the light-load/high-VIN ceiling issue #25 removes; the VREF side
now reaches EA_OUT through the EA_D2 -> PB -> M_MIRP2 mirror path instead.
M_IN2S (soft-start column) is wired in parallel with this device, so the
"-" side still sees the soft minimum of VREF and the soft-start ramp SS.} 640 -700 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 600 -1000 0 0 {name=M_MIR1
L=4
W=10
nf=2
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 620 -1030 0 0 {name=p_mmir1_d lab=EA_D1}
C {devices/lab_pin.sym} 580 -1000 0 0 {name=p_mmir1_g lab=EA_D1}
C {devices/lab_pin.sym} 620 -970 0 0 {name=p_mmir1_s lab=AMP_ENN}
C {devices/lab_pin.sym} 620 -1000 0 0 {name=p_mmir1_b lab=0}
T {M_MIR1: diode-connected NMOS mirror reference (mirror-diode side).
Source returns through M_ENN2 (below), not straight to 0 -- see M_ENN2.
L raised 0.5 -> 4 in issue #22 (output resistance / gain, see README).} 640 -1000 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 600 -1300 0 0 {name=M_MIR2
L=4
W=10
nf=2
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 620 -1330 0 0 {name=p_mmir2_d lab=EA_OUT}
C {devices/lab_pin.sym} 580 -1300 0 0 {name=p_mmir2_g lab=EA_D1}
C {devices/lab_pin.sym} 620 -1270 0 0 {name=p_mmir2_s lab=AMP_ENN}
C {devices/lab_pin.sym} 620 -1300 0 0 {name=p_mmir2_b lab=0}
T {M_MIR2: 1:1 NMOS mirror output, pulls down at EA_OUT. Source also
returns through the shared M_ENN2 switch -- see M_ENN2.} 640 -1300 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 900 -1300 0 0 {name=M_ENN2
L=0.5
W=10
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 920 -1330 0 0 {name=p_menn2_d lab=AMP_ENN}
C {devices/lab_pin.sym} 880 -1300 0 0 {name=p_menn2_g lab=EN}
C {devices/lab_pin.sym} 920 -1270 0 0 {name=p_menn2_s lab=0}
C {devices/lab_pin.sym} 920 -1300 0 0 {name=p_menn2_b lab=0}
T {M_ENN2: EN-gated ground return for the NMOS mirror load (M_MIR1/M_MIR2)
and for the current-limit comparator's NMOS branches (M_CLN1/M_CLN2).
Found by simulation: with only the bias generator's NMOS branch gated
(M_ENN), M_ENP's EN=0 pull-up on EA_OUT (Vsg=VIN, driven hard) had a ready
shoot-through path to ground through the still-alive M_MIR1/M_MIR2/diff
pair (measured ~440uA from VIN during "shutdown"). Cutting the mirror
load's own ground return removes that path -- every NMOS branch in the
amplifier/bias/protection core is EN-gated (M_ENN or M_ENN2), matching the
EN-gated PMOS clamps (M_ENP, M_ENP2, M_ENP3), so EN=0 leaves no DC path
from VIN to GND through this core other than device leakage.} 940 -1300 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 600 -1600 0 0 {name=M_ENP
L=0.5
W=10
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 620 -1570 0 0 {name=p_menp_d lab=EA_OUT}
C {devices/lab_pin.sym} 580 -1600 0 0 {name=p_menp_g lab=EN}
C {devices/lab_pin.sym} 620 -1630 0 0 {name=p_menp_s lab=VIN}
C {devices/lab_pin.sym} 620 -1600 0 0 {name=p_menp_b lab=VIN}
T {M_ENP: EN=0 forces EA_OUT->VIN, i.e. forces M_PASS gate high (off) --
independent of the (now-unbiased) amplifier's own output} 640 -1600 0 0 0.2 0.2 {}

* ---- issue #25: second mirror path (5T OTA -> current-mirror OTA) ----
* The VREF-side drain current leaves the input pair at EA_D2, is turned
* around by the NMOS mirror M_MIR3/M_MIR4 into PB, and is turned around a
* second time by the PMOS mirror M_MIRP1/M_MIRP2 to become the PULL-UP at
* EA_OUT. EA_OUT is therefore the drain of a PMOS whose SOURCE is VIN, so it
* can swing all the way to VIN -- the whole point of issue #25. The FB-side
* current still reaches EA_OUT as the pull-down through M_MIR1/M_MIR2, so
* EA_OUT is a rail-to-rail push/pull node between two 1:1-mirrored copies of
* the two input-pair drain currents.
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 3000 -100 0 0 {name=M_MIR3
L=4
W=10
nf=2
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3020 -130 0 0 {name=p_mmir3_d lab=EA_D2}
C {devices/lab_pin.sym} 2980 -100 0 0 {name=p_mmir3_g lab=EA_D2}
C {devices/lab_pin.sym} 3020 -70 0 0 {name=p_mmir3_s lab=AMP_ENN}
C {devices/lab_pin.sym} 3020 -100 0 0 {name=p_mmir3_b lab=0}
T {M_MIR3: diode-connected NMOS load on the VREF/soft-start side of the
input pair -- the mirror twin of M_MIR1 on the FB side, same L=4 W=10 nf=2,
so the two input-pair branches see identical drain loads and the systematic
offset of the extra path stays small. Source returns through the shared
M_ENN2 switch (AMP_ENN), so it dies at EN=0 like every other NMOS branch.} 3040 -100 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 3000 -400 0 0 {name=M_MIR4
L=4
W=10
nf=2
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3020 -430 0 0 {name=p_mmir4_d lab=PB}
C {devices/lab_pin.sym} 2980 -400 0 0 {name=p_mmir4_g lab=EA_D2}
C {devices/lab_pin.sym} 3020 -370 0 0 {name=p_mmir4_s lab=AMP_ENN}
C {devices/lab_pin.sym} 3020 -400 0 0 {name=p_mmir4_b lab=0}
T {M_MIR4: 1:1 NMOS mirror output of M_MIR3, sinking the VREF-side branch
current out of the PMOS diode M_MIRP1. L=4 for the same output-resistance
reason M_MIR1/M_MIR2 were lengthened in issue #22.} 3040 -400 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 3000 -700 0 0 {name=M_MIRP1
L=4
W=20
nf=4
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3020 -670 0 0 {name=p_mmirp1_d lab=PB}
C {devices/lab_pin.sym} 2980 -700 0 0 {name=p_mmirp1_g lab=PB}
C {devices/lab_pin.sym} 3020 -730 0 0 {name=p_mmirp1_s lab=VIN}
C {devices/lab_pin.sym} 3020 -700 0 0 {name=p_mmirp1_b lab=VIN}
T {M_MIRP1: diode-connected PMOS reference of the output pull-up mirror.
Source = VIN. Sized W=20 L=4 (wider and longer than the bias unit) so the
mirror's own Vsg stays modest and its output resistance is high -- PB sits
around VIN - 0.9V in normal operation.} 3040 -700 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 3000 -1000 0 0 {name=M_MIRP2
L=4
W=20
nf=4
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3020 -970 0 0 {name=p_mmirp2_d lab=EA_OUT}
C {devices/lab_pin.sym} 2980 -1000 0 0 {name=p_mmirp2_g lab=PB}
C {devices/lab_pin.sym} 3020 -1030 0 0 {name=p_mmirp2_s lab=VIN}
C {devices/lab_pin.sym} 3020 -1000 0 0 {name=p_mmirp2_b lab=VIN}
T {M_MIRP2: 1:1 PMOS mirror output -- THE device that removes the issue-#25
ceiling. Its source is VIN, so when the loop needs the pass device fully off
it can drive EA_OUT all the way to VIN (into triode), instead of stalling at
EA_TAIL ~= V_in,cm + V_sg ~= 2.5V the way the 5T OTA's PMOS input drain did.
Together with the M_MIR2 pull-down this makes EA_OUT a push-pull, rail-to-
rail node while the amplifier stays a SINGLE gain stage: both mirror
turnaround nodes (EA_D2, PB) are diode-loaded and therefore low-impedance,
so their poles sit far above the loop crossover and the loop keeps the
two-pole (EA_OUT / VOUT) shape that Miller compensation is designed for.
That is the difference from the second-gain-stage candidate screened and
rejected in issue #22, which added a third low-frequency pole and
oscillated.} 3040 -1000 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 3000 -1300 0 0 {name=M_ENP5
L=0.5
W=2
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3020 -1270 0 0 {name=p_menp5_d lab=PB}
C {devices/lab_pin.sym} 2980 -1300 0 0 {name=p_menp5_g lab=EN}
C {devices/lab_pin.sym} 3020 -1330 0 0 {name=p_menp5_s lab=VIN}
C {devices/lab_pin.sym} 3020 -1300 0 0 {name=p_menp5_b lab=VIN}
T {M_ENP5: EN=0 forces PB->VIN, which forces the pull-up M_MIRP2 hard off.
Same rationale as M_ENP3 on CL_CMP: at EN=0 both of PB's drivers (M_MIRP1
and M_MIR4, the latter cut by M_ENN2/AMP_ENN) are off, so PB would otherwise
be a floating gate node on a device that sources current straight from VIN.
This is the shutdown-leakage defence the rejected issue-#22 candidate fix
needed two devices for: because M_MIR3/M_MIR4 return through the existing
AMP_ENN switch rather than straight to ground, no NB pull-down or R_BIAS
disconnect is required here -- one clamp is enough.} 3040 -1300 0 0 0.2 0.2 {}

* ---- output stage: pass device, compensation, feedback divider ----
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 1200 -100 0 0 {name=M_PASS
L=0.5
W=100
nf=25
mult=25
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1220 -70 0 0 {name=p_mpass_d lab=VOUT}
C {devices/lab_pin.sym} 1180 -100 0 0 {name=p_mpass_g lab=EA_OUT}
C {devices/lab_pin.sym} 1220 -130 0 0 {name=p_mpass_s lab=VIN}
C {devices/lab_pin.sym} 1220 -100 0 0 {name=p_mpass_b lab=VIN}
T {M_PASS: L=0.5 (bin floor), 25 parallel groups of W=100 nf=25
-> W_total = 25 x 100um = 2500um (~2.5mm), per DR-003's sizing methodology
(W_total >= 14.81 kohm.um / 6 ohm ~= 2.47mm at the dropout bias point /
{ss,sf}@125C corner). NOTE: in the sky130 xschem symbols W is the TOTAL
device width and nf only splits it into fingers -- the first draft of this
schematic (issue #14) used W=100 nf=25 mult=1 believing that meant
W_total = W x nf = 2500um, but it netlists 100um, 25x under the DR-003
number. mult=25 is what actually instantiates 2500um. See README
"Pass-device width correction".} 1240 -100 0 0 0.2 0.2 {}

C {devices/capa.sym} 1200 -400 0 0 {name=C_COMP m=1 value=150p footprint=1206 device="mim cap (compensation)"}
C {devices/lab_pin.sym} 1200 -370 0 0 {name=p_ccomp_m lab=EA_CZ}
C {devices/lab_pin.sym} 1200 -430 0 0 {name=p_ccomp_p lab=VOUT}
T {C_COMP: Miller compensation, VOUT -> EA_CZ -> (R_CZ) -> EA_OUT, across the
inverting EA_OUT->VOUT pass stage. 100p, sized in issue #25 against the
sim/loop-gain testbench over the DR-002 C_out/ESR window -- no longer the
#14/#22 placeholder. It is deliberately large: under Miller compensation the
loop's unity-gain frequency is Gm/(2*pi*C_COMP), and it has to sit below the
pass stage's own gm_pass/(2*pi*C_out) pole at the light-load/high-C_eff end
of the DR-002 window. See README "Compensation (sized in #25)" for the
measured phase-margin map and for the area note (a 100p MIM is ~50000um2 of
cap_mim, stackable over the pass device rather than beside it).} 1240 -400 0 0 0.2 0.2 {}

C {sky130_fd_pr/res_xhigh_po.sym} 1200 -250 0 0 {name=R_CZ W=0.42 L=52 model=res_xhigh_po spiceprefix=X mult=1}
C {devices/lab_pin.sym} 1200 -220 0 0 {name=p_rcz1 lab=EA_CZ}
C {devices/lab_pin.sym} 1200 -280 0 0 {name=p_rcz2 lab=EA_OUT}
C {devices/lab_pin.sym} 1180 -250 0 0 {name=p_rcz3 lab=0}
T {R_CZ: the compensation network's nulling resistor, in series with C_COMP
(issue #25). res_xhigh_po W=0.42 L=52 -- the same unit-resistor flavor the
feedback divider uses, so ~300kOhm at the L=180 -> ~1.04MOhm screening slope
in README's "Feedback divider" table.

Why it is here and not just a bare Miller cap: a bare C_COMP shorts EA_OUT to
VOUT at high frequency, which turns the pass device into a follower and puts
a floor under the loop gain -- past that floor, making C_COMP bigger stops
lowering the crossover at all (measured: 100p -> 250p moved the light-load
crossover only 2671Hz -> 1677Hz). R_CZ breaks that feedthrough and places a
left-half-plane zero at 1/(2*pi*R_CZ*C_COMP) ~= 5kHz, which is what actually
buys the phase margin back at the light-load/high-C_eff corner. Its value is
a genuine two-sided optimum, not a "bigger is better" knob: too small and the
light-load corners lose margin, too large and the Miller pole splitting stops
working at 50mA/0.33uF. See README "Compensation (sized in #25)".} 1240 -250 0 0 0.2 0.2 {}

C {sky130_fd_pr/res_xhigh_po.sym} 1200 -700 0 0 {name=R_FB_A W=0.42 L=180 model=res_xhigh_po spiceprefix=X mult=1}
C {devices/lab_pin.sym} 1200 -670 0 0 {name=p_rfba1 lab=VOUT}
C {devices/lab_pin.sym} 1200 -730 0 0 {name=p_rfba2 lab=FB}
C {devices/lab_pin.sym} 1180 -700 0 0 {name=p_rfba3 lab=0}
T {R_FB_A: unit resistor 1 of 3 (VOUT->FB), res_xhigh_po W=0.42 L=180
-- measured ~1.04Mohm (tt/27C screening, not sim/ evidence, see README)} 1240 -700 0 0 0.2 0.2 {}

C {sky130_fd_pr/res_xhigh_po.sym} 1200 -1000 0 0 {name=R_FB_B W=0.42 L=180 model=res_xhigh_po spiceprefix=X mult=1}
C {devices/lab_pin.sym} 1200 -970 0 0 {name=p_rfbb1 lab=FB}
C {devices/lab_pin.sym} 1200 -1030 0 0 {name=p_rfbb2 lab=N_FBB}
C {devices/lab_pin.sym} 1180 -1000 0 0 {name=p_rfbb3 lab=0}
T {R_FB_B: unit resistor 2 of 3 (FB->N_FBB), identical W/L to R_FB_A/R_FB_C
-- together the bottom leg (R_FB_B+R_FB_C) is 2 units, top leg 1 unit} 1240 -1000 0 0 0.2 0.2 {}

C {sky130_fd_pr/res_xhigh_po.sym} 1200 -1300 0 0 {name=R_FB_C W=0.42 L=180 model=res_xhigh_po spiceprefix=X mult=1}
C {devices/lab_pin.sym} 1200 -1270 0 0 {name=p_rfbc1 lab=N_FBB}
C {devices/lab_pin.sym} 1200 -1330 0 0 {name=p_rfbc2 lab=0}
C {devices/lab_pin.sym} 1180 -1300 0 0 {name=p_rfbc3 lab=0}
T {R_FB_C: unit resistor 3 of 3 (N_FBB->GND). Ratio 1:2 -> VOUT = 1.5 x VREF
(VREF~1.2V assumed -> VOUT~1.8V). Issue #14 used the inverse ratio 2:1 with
VREF~0.6V; issue #22 raised the reference common mode because a PMOS-input
5T OTA cannot drive EA_OUT above roughly V_in_cm + V_sg(M_IN2), and with the
corrected 2.5mm pass device a 0.6V common mode left that ceiling too low to
throttle M_PASS at light load. See README "Reference common mode".} 1240 -1300 0 0 0.2 0.2 {}

* ================= issue #22: current limit =================
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 1700 -100 0 0 {name=M_SENSE
L=0.5
W=0.42
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1720 -70 0 0 {name=p_msense_d lab=CL_SNS}
C {devices/lab_pin.sym} 1680 -100 0 0 {name=p_msense_g lab=EA_OUT}
C {devices/lab_pin.sym} 1720 -130 0 0 {name=p_msense_s lab=VIN}
C {devices/lab_pin.sym} 1720 -100 0 0 {name=p_msense_b lab=VIN}
T {M_SENSE: current-sense replica of M_PASS -- same L (0.5, bin floor), same
gate (EA_OUT) and same source (VIN), minimum width. Nominal sense ratio
0.42um : 2500um = 1:5952, so 50mA of pass current shows up as ~8uA here and
the limit threshold (~110-180mA, see README) as ~19-31uA. A sense FET is
used rather than a series sense resistor so nothing is inserted in the main
current path and no dropout budget is spent. Accuracy caveat: M_SENSE's
drain sits at V_gs(M_CLN1) ~ 0.9V rather than at VOUT, so the replica only
tracks well while both devices are saturated -- which is the case in the
limit condition that matters. Not a trimmed/verified ratio.} 1740 -100 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 1700 -400 0 0 {name=M_CLN1
L=1
W=20
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1720 -430 0 0 {name=p_mcln1_d lab=CL_SNS}
C {devices/lab_pin.sym} 1680 -400 0 0 {name=p_mcln1_g lab=CL_SNS}
C {devices/lab_pin.sym} 1720 -370 0 0 {name=p_mcln1_s lab=AMP_ENN}
C {devices/lab_pin.sym} 1720 -400 0 0 {name=p_mcln1_b lab=0}
T {M_CLN1: diode-connected load for the sense current, and the reference
leg of the 20:1.6 attenuating mirror into M_CLN2. Source returns through the
shared M_ENN2 switch (AMP_ENN) so the whole comparator dies at EN=0.} 1740 -400 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 1700 -700 0 0 {name=M_CLN2
L=1
W=1.6
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1720 -730 0 0 {name=p_mcln2_d lab=CL_CMP}
C {devices/lab_pin.sym} 1680 -700 0 0 {name=p_mcln2_g lab=CL_SNS}
C {devices/lab_pin.sym} 1720 -670 0 0 {name=p_mcln2_s lab=AMP_ENN}
C {devices/lab_pin.sym} 1720 -700 0 0 {name=p_mcln2_b lab=0}
T {M_CLN2: attenuating mirror output, 20:1.6 = 12.5:1 down from M_CLN1.
The attenuation is what keeps the *reference* branch (M_CLP) at the ~2uA
bias level instead of needing a tens-of-uA always-on reference current --
the reference current is quiescent, the sense current is not.
The 1.6um width is the knob that sets the trip threshold.} 1740 -700 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 1700 -1000 0 0 {name=M_CLP
L=1
W=10
nf=2
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1720 -970 0 0 {name=p_mclp_d lab=CL_CMP}
C {devices/lab_pin.sym} 1680 -1000 0 0 {name=p_mclp_g lab=BIASP}
C {devices/lab_pin.sym} 1720 -1030 0 0 {name=p_mclp_s lab=VIN}
C {devices/lab_pin.sym} 1720 -1000 0 0 {name=p_mclp_b lab=VIN}
T {M_CLP: threshold reference -- a 1x copy of the M_BIASP1 PMOS bias unit
feeding the high-impedance comparison node CL_CMP. While the attenuated
sense current is below this reference, CL_CMP sits at VIN and M_CLIM is off,
so the limit is completely inactive in normal operation. Gate = BIASP means
it also dies automatically at EN=0.} 1740 -1000 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 1700 -1300 0 0 {name=M_CLIM
L=0.5
W=20
nf=4
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1720 -1270 0 0 {name=p_mclim_d lab=EA_OUT}
C {devices/lab_pin.sym} 1680 -1300 0 0 {name=p_mclim_g lab=CL_CMP}
C {devices/lab_pin.sym} 1720 -1330 0 0 {name=p_mclim_s lab=VIN}
C {devices/lab_pin.sym} 1720 -1300 0 0 {name=p_mclim_b lab=VIN}
T {M_CLIM: the clamp itself. When the sense current exceeds the reference,
CL_CMP falls, M_CLIM turns on and pulls the pass gate EA_OUT toward VIN,
throttling M_PASS. This is a continuous second feedback loop, not a latch,
which is what makes the limit a constant-current (brickwall) clamp per the
spec row rather than a hiccup or shutdown. It only has to overpower the
error amplifier's own ~uA-level pull-down at EA_OUT, so it is sized for
drive, not for gain.} 1740 -1300 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 1700 -1600 0 0 {name=M_ENP3
L=0.5
W=2
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1720 -1570 0 0 {name=p_menp3_d lab=CL_CMP}
C {devices/lab_pin.sym} 1680 -1600 0 0 {name=p_menp3_g lab=EN}
C {devices/lab_pin.sym} 1720 -1630 0 0 {name=p_menp3_s lab=VIN}
C {devices/lab_pin.sym} 1720 -1600 0 0 {name=p_menp3_b lab=VIN}
T {M_ENP3: EN=0 forces CL_CMP->VIN. Without it CL_CMP is a floating node in
shutdown (both M_CLP and M_CLN2 are off), which leaves M_CLIM's gate
undefined; harmless in principle -- M_CLIM can only pull EA_OUT toward VIN,
which is the shutdown state anyway -- but a defined off state keeps the DC
solve well posed and matches the M_ENP/M_ENP2 convention.} 1740 -1600 0 0 0.2 0.2 {}

C {devices/capa.sym} 1700 -1900 0 0 {name=C_CL m=1 value=1p footprint=1206 device="mim cap (current-limit comparator)"}
C {devices/lab_pin.sym} 1700 -1870 0 0 {name=p_ccl_m lab=CL_CMP}
C {devices/lab_pin.sym} 1700 -1930 0 0 {name=p_ccl_p lab=VIN}
T {C_CL: dominant-pole cap on the current-limit comparator node, referenced
to VIN so it does not inject supply noise into CL_CMP. The limit path has
two high-impedance nodes (CL_CMP and EA_OUT) and is therefore a second
two-pole loop; this cap makes CL_CMP the dominant one. Value is a
PLACEHOLDER, same status as C_COMP -- a screening transient into a hard
short settles flat (see README), but that is not a stability proof.} 1740 -1900 0 0 0.2 0.2 {}

* ================= issue #22: soft start =================
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 2200 -100 0 0 {name=M_INVP
L=0.5
W=2
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 2220 -70 0 0 {name=p_minvp_d lab=ENB}
C {devices/lab_pin.sym} 2180 -100 0 0 {name=p_minvp_g lab=EN}
C {devices/lab_pin.sym} 2220 -130 0 0 {name=p_minvp_s lab=VIN}
C {devices/lab_pin.sym} 2220 -100 0 0 {name=p_minvp_b lab=VIN}
T {M_INVP/M_INVN: a plain static CMOS inverter on EN, producing ENB. Needed
because the soft-start capacitor has to be *discharged* while the block is
disabled, which takes an NMOS whose gate is high at EN=0. Static current is
zero in both states, so it costs nothing in the shutdown-Iq budget.} 2240 -100 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 2200 -400 0 0 {name=M_INVN
L=0.5
W=1
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 2220 -430 0 0 {name=p_minvn_d lab=ENB}
C {devices/lab_pin.sym} 2180 -400 0 0 {name=p_minvn_g lab=EN}
C {devices/lab_pin.sym} 2220 -370 0 0 {name=p_minvn_s lab=0}
C {devices/lab_pin.sym} 2220 -400 0 0 {name=p_minvn_b lab=0}
T {M_INVN: NMOS half of the EN inverter (see M_INVP).} 2240 -400 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 2200 -700 0 0 {name=M_SSDIS
L=0.5
W=2
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 2220 -730 0 0 {name=p_mssdis_d lab=SS}
C {devices/lab_pin.sym} 2180 -700 0 0 {name=p_mssdis_g lab=ENB}
C {devices/lab_pin.sym} 2220 -670 0 0 {name=p_mssdis_s lab=0}
C {devices/lab_pin.sym} 2220 -700 0 0 {name=p_mssdis_b lab=0}
T {M_SSDIS: holds SS at 0 whenever EN=0, so every enable edge starts the
ramp from zero rather than from whatever charge survived the last shutdown.
Without this the "soft" start is only soft the first time.} 2240 -700 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 2200 -1000 0 0 {name=M_SSCHG
L=8
W=1
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 2220 -970 0 0 {name=p_msschg_d lab=SS}
C {devices/lab_pin.sym} 2180 -1000 0 0 {name=p_msschg_g lab=BIASP}
C {devices/lab_pin.sym} 2220 -1030 0 0 {name=p_msschg_s lab=VIN}
C {devices/lab_pin.sym} 2220 -1000 0 0 {name=p_msschg_b lab=VIN}
T {M_SSCHG: the ramp generator -- a heavily scaled-down copy of the
M_BIASP1 PMOS bias unit (W/L = 1/8 against 10/1, so of order 1/80 of the
bias current, tens of nA). Charging C_SS from a current source rather than
through a resistor makes SS a straight line, which is what turns into a
straight-line VOUT ramp through the min-select input. Gate = BIASP also
means it is off in shutdown for free, and that the ramp cannot start before
the bias generator itself is alive.} 2240 -1000 0 0 0.2 0.2 {}

C {devices/capa.sym} 2200 -1300 0 0 {name=C_SS m=1 value=10p footprint=1206 device="mim cap (soft start)"}
C {devices/lab_pin.sym} 2200 -1270 0 0 {name=p_css_m lab=0}
C {devices/lab_pin.sym} 2200 -1330 0 0 {name=p_css_p lab=SS}
T {C_SS: soft-start capacitor. 10p against the tens-of-nA charge current
gives a ramp that takes the output from 10% to 90% in a few hundred us --
comfortably inside the spec row's "inside +-2% within a few ms of enable"
while being slow enough that the inrush into the DR-002 C_out window stays
well under the current limit. Value is a screening choice, not a verified
one, and the area cost of a real MIM instance is a layout-time item.} 2240 -1300 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 2200 -1600 0 0 {name=M_IN2S
L=2
W=10
nf=2
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 2220 -1570 0 0 {name=p_min2s_d lab=EA_D2}
C {devices/lab_pin.sym} 2180 -1600 0 0 {name=p_min2s_g lab=SS}
C {devices/lab_pin.sym} 2220 -1630 0 0 {name=p_min2s_s lab=EA_TAIL}
C {devices/lab_pin.sym} 2220 -1600 0 0 {name=p_min2s_b lab=VIN}
T {M_IN2S: the min-select input. A replica of M_IN2 (same L/W/nf) wired in
parallel with it -- same source (EA_TAIL), same drain (EA_D2, issue
#25's second mirror-diode node) -- but gated
by SS instead of VREF. In a PMOS input pair the device with the *lower* gate
dominates, so the "-" side behaves as the soft minimum of VREF and SS: the
loop servos FB to SS while SS < VREF (VOUT ramps as 1.5 x SS) and hands over
to VREF once SS passes it, with no comparator, no switch and no discontinuity
to overshoot through. Once SS has charged toward VIN this device is fully
off and the amplifier is exactly the issue #14 5T OTA again.} 2240 -1600 0 0 0.2 0.2 {}

* ============ issue #29: thermal shutdown (DR-005) ============
* Two CTAT branches at different current densities (DR-005's "internally
* generated, bias-generator-derived" reference -- not VREF, not a bandgap),
* compared by a 5T OTA whose output drives an EA_OUT clamp. TS_CMP ~ VIN =
* not tripped, falls when the die is hot -- the same polarity convention as
* the current limit's CL_CMP node.
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 2700 -100 0 0 {name=M_TSPS
L=1
W=1.25
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 2720 -70 0 0 {name=p_mtsps_d lab=TS_SNS}
C {devices/lab_pin.sym} 2680 -100 0 0 {name=p_mtsps_g lab=BIASP}
C {devices/lab_pin.sym} 2720 -130 0 0 {name=p_mtsps_s lab=VIN}
C {devices/lab_pin.sym} 2720 -100 0 0 {name=p_mtsps_b lab=VIN}
T {M_TSPS: sense-branch current source -- a 1/8-width copy of the M_BIASP1
PMOS bias unit (W=1.25 against 10, same L) so the sense stack runs at ~200nA
rather than the full bias unit. Gate = BIASP, so the whole thermal sensor
dies at EN=0 for free, exactly like M_CLP and M_SSCHG.
The low current density is load-bearing, not an Iq economy: it puts the
stack devices in weak inversion, which is what makes the branch steeply
CTAT *and* nearly insensitive to the bias current itself (see
design/README.md "Thermal shutdown (#29)").
RE-SIZED IN #69 (was W=2.5): halving the sense-branch current is one of the
two knobs that place the trip window; the other is M_TSPR's width. Together
they set Tj_trip without disturbing the M_TSD*/M_TSR1 geometry ratio that
#69 chose to cancel the corner-Vth skew.} 2740 -100 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 2700 -400 0 0 {name=M_TSD1
L=4
W=80
nf=16
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 2720 -430 0 0 {name=p_mtsd1_d lab=TS_SNS}
C {devices/lab_pin.sym} 2680 -400 0 0 {name=p_mtsd1_g lab=TS_SNS}
C {devices/lab_pin.sym} 2720 -370 0 0 {name=p_mtsd1_s lab=TS_MID}
C {devices/lab_pin.sym} 2720 -400 0 0 {name=p_mtsd1_b lab=0}
T {M_TSD1/M_TSD2: the thermal sense element -- two diode-connected NMOS
stacked between TS_SNS and the EN-gated pseudo-ground AMP_ENN, so
V(TS_SNS) = Vgs1 + Vgs2 at a low current density. Each Vgs is CTAT, and
stacking two doubles the slope. Wide (W=80, nf=16 -> 5um fingers) and at
~200nA so both devices stay in weak/moderate inversion; that is what makes
the branch's dV/dln(I) small enough that the trip point barely moves with
the supply-dependent bias current. Source returns through the shared
M_ENN2 switch (AMP_ENN).
RE-SIZED IN #69: L=1 -> L=4. THE CHANNEL LENGTH IS A PROCESS-SPREAD KNOB,
not just a density knob. sky130's HV-nfet corner model applies its Vth0
skew as delvto = swx_vth * (0.10*8/L + 0.90) * (0.045*7/W + 0.955) * ...,
i.e. a SHORT channel AMPLIFIES the corner Vth shift (1.63x at L=1, 1.06x at
L=4 for W=80). Because the sense side contributes TWO Vgs terms to the
trip comparison and the reference only one, that amplification was doubled
on the sense side and did not cancel -- which is why the trip moved 65C
across the five process corners and nuisance-tripped at ff/sf/125C (#69).
See design/README.md "Thermal shutdown (#29)" for the full derivation.} 2740 -400 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 2700 -700 0 0 {name=M_TSD2
L=4
W=80
nf=16
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 2720 -730 0 0 {name=p_mtsd2_d lab=TS_MID}
C {devices/lab_pin.sym} 2680 -700 0 0 {name=p_mtsd2_g lab=TS_MID}
C {devices/lab_pin.sym} 2720 -670 0 0 {name=p_mtsd2_s lab=AMP_ENN}
C {devices/lab_pin.sym} 2720 -700 0 0 {name=p_mtsd2_b lab=0}
T {M_TSD2: bottom device of the sense stack (see M_TSD1). Identical
geometry to M_TSD1 -- the stack is a ratio of *counts*, not of widths.
Re-sized in #69 with M_TSD1 (L=1 -> L=4); the two must stay identical or
the "counts, not widths" argument above stops holding.} 2740 -700 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 2700 -1000 0 0 {name=M_TSPR
L=1
W=7
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 2720 -970 0 0 {name=p_mtspr_d lab=TS_REF}
C {devices/lab_pin.sym} 2680 -1000 0 0 {name=p_mtspr_g lab=BIASP}
C {devices/lab_pin.sym} 2720 -1030 0 0 {name=p_mtspr_s lab=VIN}
C {devices/lab_pin.sym} 2720 -1000 0 0 {name=p_mtspr_b lab=VIN}
T {M_TSPR: reference-branch current source -- a 0.7x-width copy of the
M_BIASP1 PMOS bias unit (W=7 against 10, same L). Same gate (BIASP) as
M_TSPS, so the bias current's own supply/temperature drift is still
common-mode to the comparison; what is NOT common-mode any more is the
branch-current RATIO, and that is deliberate.
RE-SIZED IN #69 (was W=2.5, i.e. identical to M_TSPS): the reference is in
strong inversion, where Vgs grows as sqrt(I), while the weak-inversion
sense stack barely moves with its own current. Widening this device alone
therefore raises TS_REF and pulls the trip temperature DOWN, which is the
knob that places the trip window after M_TSD*/M_TSR1's geometry has been
fixed by the corner-Vth cancellation argument. Cost: ~+0.5uA of Iq,
measured against the DRAFT Iq < 30uA row (design/README.md).} 2740 -1000 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 2700 -1300 0 0 {name=M_TSR1
L=2
W=0.42
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 2720 -1330 0 0 {name=p_mtsr1_d lab=TS_REF}
C {devices/lab_pin.sym} 2680 -1300 0 0 {name=p_mtsr1_g lab=TS_REF}
C {devices/lab_pin.sym} 2720 -1270 0 0 {name=p_mtsr1_s lab=AMP_ENN}
C {devices/lab_pin.sym} 2720 -1300 0 0 {name=p_mtsr1_b lab=0}
T {M_TSR1: the trip reference -- a single diode-connected NMOS of the same
family as the sense stack but at a far higher current density (W/L =
0.42/2 = 0.21 against the stack's 80/4 = 20, ~95x, and on top of that a
~7x larger branch current), which puts it in strong inversion. Its Vgs is
therefore only weakly CTAT (Vth falls with temperature but the overdrive
grows as mobility drops), while the two-high weak-inversion sense stack
falls twice as fast. The two curves cross, and that crossing is the trip
temperature -- DR-005's "ratioed diode/CTAT pair at different current
densities", with the stack height supplying the slope asymmetry a
same-height pair cannot have.
RE-SIZED IN #69 (was W=2 L=10). W and L here are NOT a free trip-temperature
knob any more -- they are pinned by the corner-Vth cancellation. sky130's
HV-nfet corner model weights its Vth0 skew by
  k(L,W) = (0.10*8/L + 0.90) * (0.045*7/W + 0.955) * (-0.0007*56/(L*W) + 1.0007)
and the trip comparison is 2*Vgs(sense) - 1*Vgs(reference), so the trip's
corner sensitivity goes as (2*k_sense - k_reference). W=0.42/L=2 gives
k=2.114 against 2*k(L=4,W=80)=2.111 -- a residual of 0.003 instead of the
old sizing's 2.17. W=0.42 is the PDK's minimum drawn width; that is what
makes k large enough to match twice the sense device's. The trip
temperature itself is placed by the two branch currents (M_TSPS/M_TSPR)
instead. See design/README.md "Thermal shutdown (#29)".} 2740 -1300 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 3200 -100 0 0 {name=M_TCTAIL
L=1
W=1
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3220 -130 0 0 {name=p_mtctail_d lab=TC_TAIL}
C {devices/lab_pin.sym} 3180 -100 0 0 {name=p_mtctail_g lab=NB}
C {devices/lab_pin.sym} 3220 -70 0 0 {name=p_mtctail_s lab=AMP_ENN}
C {devices/lab_pin.sym} 3220 -100 0 0 {name=p_mtctail_b lab=0}
T {M_TCTAIL: tail sink for the trip comparator -- a 1/4-width copy of the
M_BIASN1 NMOS bias unit (W=1 against 4, same L), gate = NB. Its source
returns through M_ENN2 (AMP_ENN), so at EN=0 the comparator has no ground
return at all and cannot draw static current no matter what its inputs do.} 3240 -100 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 3200 -400 0 0 {name=M_TCN1
L=2
W=10
nf=2
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3220 -430 0 0 {name=p_mtcn1_d lab=TC_D1}
C {devices/lab_pin.sym} 3180 -400 0 0 {name=p_mtcn1_g lab=TS_SNS}
C {devices/lab_pin.sym} 3220 -370 0 0 {name=p_mtcn1_s lab=TC_TAIL}
C {devices/lab_pin.sym} 3220 -400 0 0 {name=p_mtcn1_b lab=0}
T {M_TCN1: trip-comparator input on the mirror-diode side, gate = TS_SNS.
NMOS input pair (not PMOS like the error amp) because the input common
mode here is 1.3-2.1V, comfortably above an NMOS pair's own Vgs + Vdsat and
too close to VIN for a PMOS pair's tail to stay saturated at VIN_min.} 3240 -400 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 3200 -700 0 0 {name=M_TCN2
L=2
W=10
nf=2
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3220 -730 0 0 {name=p_mtcn2_d lab=TS_CMP}
C {devices/lab_pin.sym} 3180 -700 0 0 {name=p_mtcn2_g lab=TS_REF}
C {devices/lab_pin.sym} 3220 -670 0 0 {name=p_mtcn2_s lab=TC_TAIL}
C {devices/lab_pin.sym} 3220 -700 0 0 {name=p_mtcn2_b lab=0}
T {M_TCN2: trip-comparator input on the output side, gate = TS_REF. This
assignment is the load-bearing polarity choice: the mirror copies the
TS_SNS-side current into TS_CMP where the TS_REF side sinks it, so
TS_CMP is pulled UP while TS_SNS > TS_REF (cold) and falls when the sense
stack drops below the reference (hot). "Falling = engaged" matches the
current limit's CL_CMP convention, which is what lets a plain PMOS clamp
(M_TSHUT) do the shutdown with no inverter in between.} 3240 -700 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 3200 -1000 0 0 {name=M_TCP1
L=2
W=10
nf=2
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3220 -970 0 0 {name=p_mtcp1_d lab=TC_D1}
C {devices/lab_pin.sym} 3180 -1000 0 0 {name=p_mtcp1_g lab=TC_D1}
C {devices/lab_pin.sym} 3220 -1030 0 0 {name=p_mtcp1_s lab=VIN}
C {devices/lab_pin.sym} 3220 -1000 0 0 {name=p_mtcp1_b lab=VIN}
T {M_TCP1: diode-connected PMOS mirror reference of the comparator load.} 3240 -1000 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 3200 -1300 0 0 {name=M_TCP2
L=2
W=10
nf=2
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3220 -1270 0 0 {name=p_mtcp2_d lab=TS_CMP}
C {devices/lab_pin.sym} 3180 -1300 0 0 {name=p_mtcp2_g lab=TC_D1}
C {devices/lab_pin.sym} 3220 -1330 0 0 {name=p_mtcp2_s lab=VIN}
C {devices/lab_pin.sym} 3220 -1300 0 0 {name=p_mtcp2_b lab=VIN}
T {M_TCP2: mirror output of the comparator load, driving the high-impedance
trip node TS_CMP.} 3240 -1300 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 3200 -1600 0 0 {name=M_TSHUT
L=0.5
W=20
nf=4
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3220 -1570 0 0 {name=p_mtshut_d lab=EA_OUT}
C {devices/lab_pin.sym} 3180 -1600 0 0 {name=p_mtshut_g lab=TS_CMP}
C {devices/lab_pin.sym} 3220 -1630 0 0 {name=p_mtshut_s lab=VIN}
C {devices/lab_pin.sym} 3220 -1600 0 0 {name=p_mtshut_b lab=VIN}
T {M_TSHUT: the shutdown clamp itself -- VIN -> EA_OUT, gate = TS_CMP.
Structurally identical to M_ENP (the EN=0 clamp) and to M_CLIM (the
current-limit clamp), and deliberately so: DR-005 chose auto-restart
(non-latching) precisely because this insertion point is level-driven, so
the trip needs no memory element and no reset pin. Over temperature the
trip forces the pass gate to VIN, M_PASS off, dissipation to ~0; the die
cools, TS_CMP snaps back to VIN and the loop resumes on its own.
NOTE it clamps the *pass gate*, not the bias generator: the sense stack,
the reference branch and this comparator must stay biased while tripped or
the circuit could not detect the reset threshold. The pass device is the
dissipating element, so turning it off is what actually removes the heat.} 3240 -1600 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 3200 -1900 0 0 {name=M_TSHYSB
L=2
W=4.5
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3220 -1870 0 0 {name=p_mtshysb_d lab=TS_HYS}
C {devices/lab_pin.sym} 3180 -1900 0 0 {name=p_mtshysb_g lab=BIASP}
C {devices/lab_pin.sym} 3220 -1930 0 0 {name=p_mtshysb_s lab=VIN}
C {devices/lab_pin.sym} 3220 -1900 0 0 {name=p_mtshysb_b lab=VIN}
T {M_TSHYSB: the hysteresis current, set by a scaled-down copy of the
M_BIASP1 bias unit (W/L = 4.5/2 against 10/1) rather than by the switch
M_TSHYS's own drive. Sizing the *current* rather than the switch is what
keeps the hysteresis a device ratio instead of a strong function of VIN --
a bare switch PMOS with Vsg = VIN would inject a supply-dependent tens of
uA and swamp the reference branch.
RE-SIZED IN #69 (was W=1.5): the hysteresis in DEGREES is the injected
reference lift divided by the sense-vs-reference gap slope, and #69's
re-sizing both steepened that slope (3.7 -> ~4.1mV/C) and stiffened the
reference branch (7x the current, so a given injected current moves TS_REF
less). W=4.5 restores DR-005's 15C nominal: measured 13.6-21.7C over the
5 process corners x 3 supplies. Costs nothing when untripped -- M_TSHYS is
off, so this branch carries no quiescent current in normal operation.} 3240 -1900 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 3200 -2200 0 0 {name=M_TSHYS
L=0.5
W=2
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3220 -2170 0 0 {name=p_mtshys_d lab=TS_REF}
C {devices/lab_pin.sym} 3180 -2200 0 0 {name=p_mtshys_g lab=TS_CMP}
C {devices/lab_pin.sym} 3220 -2230 0 0 {name=p_mtshys_s lab=TS_HYS}
C {devices/lab_pin.sym} 3220 -2200 0 0 {name=p_mtshys_b lab=VIN}
T {M_TSHYS: the hysteresis switch. While TS_CMP ~ VIN (not tripped) its
Vsg is ~0 and it is off, so hysteresis costs no quiescent current in
normal operation. Once TS_CMP falls (tripped) it steers M_TSHYSB's current
into TS_REF, raising the reference by tens of mV -- i.e. making the
comparison look hotter than it is, so the die must cool below the trip
point before the block restarts. That is positive feedback around the
comparator: it also snaps the transition, so the trip is a clean edge
rather than a slow slide through the comparator's linear range.
DR-005 fixes the target at 15C nominal; the ratio here is the knob.} 3240 -2200 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 3200 -2500 0 0 {name=M_ENP4
L=0.5
W=2
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 3220 -2470 0 0 {name=p_menp4_d lab=TS_CMP}
C {devices/lab_pin.sym} 3180 -2500 0 0 {name=p_menp4_g lab=EN}
C {devices/lab_pin.sym} 3220 -2530 0 0 {name=p_menp4_s lab=VIN}
C {devices/lab_pin.sym} 3220 -2500 0 0 {name=p_menp4_b lab=VIN}
T {M_ENP4: EN=0 forces TS_CMP -> VIN, i.e. "not tripped" -- the fourth
member of the M_ENP/M_ENP2/M_ENP3 family and the same argument as M_ENP3:
in shutdown every device that drives TS_CMP is off, so without this clamp
the node floats and M_TSHUT's and M_TSHYS's gates are undefined. Forcing it
to VIN also guarantees the thermal clamp cannot hold EA_OUT while the block
is disabled, and gives the DC solve a well-posed shutdown state.} 3240 -2500 0 0 0.2 0.2 {}

C {devices/capa.sym} 3200 -2800 0 0 {name=C_TS m=1 value=1p footprint=1206 device="mim cap (thermal trip comparator)"}
C {devices/lab_pin.sym} 3200 -2770 0 0 {name=p_cts_m lab=TS_CMP}
C {devices/lab_pin.sym} 3200 -2830 0 0 {name=p_cts_p lab=VIN}
T {C_TS: dominant-pole cap on the trip node, referenced to VIN so it does
not inject supply noise into TS_CMP -- same construction and same status as
C_CL on the current-limit comparator. It sets the time constant of the
hysteretic trip/reset cycle together with the ~0.4uA available at TS_CMP.
Value is a PLACEHOLDER: the thermal loop's real time constant is the die's,
which is orders of magnitude slower than anything this cap sets, so its job
is only to keep the electrical comparator from chattering. Not sized
against a transient simulation.} 3240 -2800 0 0 0.2 0.2 {}
