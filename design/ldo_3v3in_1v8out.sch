v {xschem version=3.4.7 file_version=1.2
* sky130-ldo core regulation loop (issue #14).
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
* schematic keeps the *whole* amplifier/bias chain on the 5V-gate family
* rather than adopting the deferred framing (C) core-device-amplifier
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
*   - M_ENP / M_ENP2: enable/shutdown. EN is active-high, full-rail (0/VIN).
*     EN=0 drives M_ENP2 to force BIASP->VIN (kills the whole PMOS bias/tail
*     chain) and M_ENP to force EA_OUT->VIN (forces M_PASS fully off), so
*     shutdown does not depend on the amplifier's own (now-unbiased) output.
*   - R_FB_A/R_FB_B/R_FB_C: three identical "unit" res_xhigh_po resistors
*     forming the feedback divider per spec/target-spec.md's "divider as a
*     unit-resistor string" note. Ratio 2:1 (two units VOUT->FB, one unit
*     FB->GND) sets VOUT = 3 x VREF; see design/README.md for the assumed
*     VREF interface value and the measured (not invented) unit-resistor
*     value.
*   - C_COMP: Miller compensation cap, EA_OUT (pass gate) -> VOUT, across the
*     inverting EA_OUT->VOUT gain stage. Value is a placeholder pending the
*     DR-002 C_out/ESR window and an actual loop-gain simulation -- NOT a
*     verified/stable value.
*
* Explicitly NOT in this schematic (see design/README.md "Known gaps /
* follow-on scope"): current limit, soft-start ramp control, thermal
* shutdown, and an actual on-chip voltage reference (VREF is an external
* port here, standing in for a future reference-generator block).
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
T {sky130-ldo core regulation loop -- issue #14
pass device: sky130_fd_pr__pfet_g5v0d10v5 (DR-001 ratified framing A)
error amp + bias chain: all 5V-gate flavor (DR-001 Consequences)
connectivity by net label (lab_pin/ipin/opin), no drawn wires
see design/README.md for node glossary, sizing rationale and open items} -700 -1400 0 0 0.35 0.35 {}

* ---- ports ----
C {devices/ipin.sym} -700 -100 0 0 {name=p_vin lab=VIN}
T {VIN: 3.3V +-10% input (2.97-3.63V, DRAFT)} -680 -100 0 0 0.25 0.25 {}
C {devices/ipin.sym} -700 -300 0 0 {name=p_en lab=EN}
T {EN: active-high enable, full-rail (0/VIN)} -680 -300 0 0 0.25 0.25 {}
C {devices/ipin.sym} -700 -500 0 0 {name=p_vref lab=VREF}
T {VREF: external reference input (assumed ~0.6V; see README)} -680 -500 0 0 0.25 0.25 {}
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
that M_TAIL below is scaled against (2x here)} 40 -1000 0 0 0.2 0.2 {}

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
L=1
W=20
nf=4
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 620 -70 0 0 {name=p_mtail_d lab=EA_TAIL}
C {devices/lab_pin.sym} 580 -100 0 0 {name=p_mtail_g lab=BIASP}
C {devices/lab_pin.sym} 620 -130 0 0 {name=p_mtail_s lab=VIN}
C {devices/lab_pin.sym} 620 -100 0 0 {name=p_mtail_b lab=VIN}
T {M_TAIL: tail current source, 2x M_BIASP1 unit -> ~2xI_BIAS tail current} 640 -100 0 0 0.2 0.2 {}

C {sky130_fd_pr/pfet_g5v0d10v5.sym} 600 -400 0 0 {name=M_IN1
L=1
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
L=1
W=10
nf=2
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 620 -670 0 0 {name=p_min2_d lab=EA_OUT}
C {devices/lab_pin.sym} 580 -700 0 0 {name=p_min2_g lab=VREF}
C {devices/lab_pin.sym} 620 -730 0 0 {name=p_min2_s lab=EA_TAIL}
C {devices/lab_pin.sym} 620 -700 0 0 {name=p_min2_b lab=VIN}
T {M_IN2: "-" input = VREF (output side, EA_OUT = pass gate node)} 640 -700 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 600 -1000 0 0 {name=M_MIR1
L=0.5
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
Source returns through M_ENN2 (below), not straight to 0 -- see M_ENN2.} 640 -1000 0 0 0.2 0.2 {}

C {sky130_fd_pr/nfet_g5v0d10v5.sym} 600 -1300 0 0 {name=M_MIR2
L=0.5
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
T {M_ENN2: EN-gated ground return for the NMOS mirror load (M_MIR1/M_MIR2).
Found by simulation: with only the bias generator's NMOS branch gated
(M_ENN), M_ENP's EN=0 pull-up on EA_OUT (Vsg=VIN, driven hard) had a ready
shoot-through path to ground through the still-alive M_MIR1/M_MIR2/diff
pair (measured ~440uA from VIN during "shutdown"). Cutting the mirror
load's own ground return removes that path -- every NMOS branch in the
amplifier/bias core is now EN-gated (M_ENN or M_ENN2), matching the two
EN-gated PMOS clamps (M_ENP, M_ENP2), so EN=0 leaves no DC path from VIN to
GND through this core other than device leakage.} 940 -1300 0 0 0.2 0.2 {}

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
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1220 -70 0 0 {name=p_mpass_d lab=VOUT}
C {devices/lab_pin.sym} 1180 -100 0 0 {name=p_mpass_g lab=EA_OUT}
C {devices/lab_pin.sym} 1220 -130 0 0 {name=p_mpass_s lab=VIN}
C {devices/lab_pin.sym} 1220 -100 0 0 {name=p_mpass_b lab=VIN}
T {M_PASS: L=0.5 (bin floor) W=100 nf=25 -> W_total=2500um (~2.5mm), per
DR-003's sizing methodology at the dropout bias point / {ss,sf}@125C corner} 1240 -100 0 0 0.2 0.2 {}

C {devices/capa.sym} 1200 -400 0 0 {name=C_COMP m=1 value=2p footprint=1206 device="mim cap (compensation)"}
C {devices/lab_pin.sym} 1200 -370 0 0 {name=p_ccomp_m lab=EA_OUT}
C {devices/lab_pin.sym} 1200 -430 0 0 {name=p_ccomp_p lab=VOUT}
T {C_COMP: Miller compensation, EA_OUT->VOUT. value is a PLACEHOLDER --
not sized against a loop-gain sim; pending DR-002 C_out/ESR window} 1240 -400 0 0 0.2 0.2 {}

C {sky130_fd_pr/res_xhigh_po.sym} 1200 -700 0 0 {name=R_FB_A W=0.42 L=180 model=res_xhigh_po spiceprefix=X mult=1}
C {devices/lab_pin.sym} 1200 -670 0 0 {name=p_rfba1 lab=VOUT}
C {devices/lab_pin.sym} 1200 -730 0 0 {name=p_rfba2 lab=N_FBA}
C {devices/lab_pin.sym} 1180 -700 0 0 {name=p_rfba3 lab=0}
T {R_FB_A: unit resistor 1 of 3 (VOUT->N_FBA), res_xhigh_po W=0.42 L=180
-- measured ~1.04Mohm (tt/27C screening, not sim/ evidence, see README)} 1240 -700 0 0 0.2 0.2 {}

C {sky130_fd_pr/res_xhigh_po.sym} 1200 -1000 0 0 {name=R_FB_B W=0.42 L=180 model=res_xhigh_po spiceprefix=X mult=1}
C {devices/lab_pin.sym} 1200 -970 0 0 {name=p_rfbb1 lab=N_FBA}
C {devices/lab_pin.sym} 1200 -1030 0 0 {name=p_rfbb2 lab=FB}
C {devices/lab_pin.sym} 1180 -1000 0 0 {name=p_rfbb3 lab=0}
T {R_FB_B: unit resistor 2 of 3 (N_FBA->FB), identical W/L to R_FB_A/R_FB_C
-- together the top leg (R_FB_A+R_FB_B) is 2 units, bottom leg 1 unit} 1240 -1000 0 0 0.2 0.2 {}

C {sky130_fd_pr/res_xhigh_po.sym} 1200 -1300 0 0 {name=R_FB_C W=0.42 L=180 model=res_xhigh_po spiceprefix=X mult=1}
C {devices/lab_pin.sym} 1200 -1270 0 0 {name=p_rfbc1 lab=FB}
C {devices/lab_pin.sym} 1200 -1330 0 0 {name=p_rfbc2 lab=0}
C {devices/lab_pin.sym} 1180 -1300 0 0 {name=p_rfbc3 lab=0}
T {R_FB_C: unit resistor 3 of 3 (FB->GND). Ratio 2:1 -> VOUT = 3 x VREF
(VREF~0.6V assumed -> VOUT~1.8V; see README for the interface caveat)} 1240 -1300 0 0 0.2 0.2 {}
