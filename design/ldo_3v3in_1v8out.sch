v {xschem version=3.4.7 file_version=1.2
* sky130-ldo core regulation loop + protection/sequencing (issues #14, #22).
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
*   - M_IN1/M_IN2 + M_MIR1/M_MIR2 + M_TAIL: single-stage 5T OTA error
*     amplifier. "+" input = FB (M_IN1, mirror-diode side), "-" input = VREF
*     (M_IN2, output side) -- this polarity is load-bearing: EA_OUT must rise
*     when FB rises so the pass gate turns OFF as VOUT rises (negative
*     feedback). See design/README.md "Error-amplifier polarity" for the
*     derivation (verified by an OP sanity sweep, not derivation alone --
*     an earlier draft had this swapped and latched to a rail).
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
*   - C_COMP: Miller compensation cap, EA_OUT (pass gate) -> VOUT, across the
*     inverting EA_OUT->VOUT gain stage. Value is a placeholder pending the
*     DR-002 C_out/ESR window and an actual loop-gain simulation -- NOT a
*     verified/stable value.
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
* Explicitly NOT in this schematic (see design/README.md "Known gaps /
* follow-on scope"): thermal shutdown (decomposed to its own issue -- the
* spec table states no trip temperature and this block has no
* temperature-stable on-chip reference to trip against), an actual on-chip
* voltage reference (VREF is an external port here), the error-amplifier
* output-swing/gain gap that still costs light-load regulation at high VIN,
* and loop compensation (C_COMP is a placeholder; DR-002 is not ratified).
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
T {sky130-ldo core regulation loop + current limit + soft start -- issues #14, #22
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
W=20
nf=4
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
"Amplifier sizing revision".} 640 -100 0 0 0.2 0.2 {}

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
C {devices/lab_pin.sym} 620 -670 0 0 {name=p_min2_d lab=EA_OUT}
C {devices/lab_pin.sym} 580 -700 0 0 {name=p_min2_g lab=VREF}
C {devices/lab_pin.sym} 620 -730 0 0 {name=p_min2_s lab=EA_TAIL}
C {devices/lab_pin.sym} 620 -700 0 0 {name=p_min2_b lab=VIN}
T {M_IN2: "-" input = VREF (output side, EA_OUT = pass gate node).
M_IN2S (soft-start column) is wired in parallel with this device, so the
"-" side sees the soft minimum of VREF and the soft-start ramp SS.} 640 -700 0 0 0.2 0.2 {}

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

C {devices/capa.sym} 1200 -400 0 0 {name=C_COMP m=1 value=2p footprint=1206 device="mim cap (compensation)"}
C {devices/lab_pin.sym} 1200 -370 0 0 {name=p_ccomp_m lab=EA_OUT}
C {devices/lab_pin.sym} 1200 -430 0 0 {name=p_ccomp_p lab=VOUT}
T {C_COMP: Miller compensation, EA_OUT->VOUT. value is a PLACEHOLDER --
not sized against a loop-gain sim; pending DR-002 C_out/ESR window} 1240 -400 0 0 0.2 0.2 {}

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
C {devices/lab_pin.sym} 2220 -1570 0 0 {name=p_min2s_d lab=EA_OUT}
C {devices/lab_pin.sym} 2180 -1600 0 0 {name=p_min2s_g lab=SS}
C {devices/lab_pin.sym} 2220 -1630 0 0 {name=p_min2s_s lab=EA_TAIL}
C {devices/lab_pin.sym} 2220 -1600 0 0 {name=p_min2s_b lab=VIN}
T {M_IN2S: the min-select input. A replica of M_IN2 (same L/W/nf) wired in
parallel with it -- same source (EA_TAIL), same drain (EA_OUT) -- but gated
by SS instead of VREF. In a PMOS input pair the device with the *lower* gate
dominates, so the "-" side behaves as the soft minimum of VREF and SS: the
loop servos FB to SS while SS < VREF (VOUT ramps as 1.5 x SS) and hands over
to VREF once SS passes it, with no comparator, no switch and no discontinuity
to overshoot through. Once SS has charged toward VIN this device is fully
off and the amplifier is exactly the issue #14 5T OTA again.} 2240 -1600 0 0 0.2 0.2 {}
