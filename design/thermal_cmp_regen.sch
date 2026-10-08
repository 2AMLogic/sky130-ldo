v {xschem version=3.4.7 file_version=1.2
* sky130-ldo thermal-shutdown REGENERATIVE comparator (issue #229, parent #131).
*
* Standalone development cell -- NOT yet wired into design/ldo_3v3in_1v8out.sch.
* Replaces the #29 5T-OTA-plus-current-injection trip comparator
* (M_TCN1/M_TCN2/M_TCP1/M_TCP2 + M_TSHYS/M_TSHYSB) with a differential pair
* whose load is a diode-connected PMOS pair in parallel with a CROSS-COUPLED
* PMOS pair (a Schmitt-trigger / regenerative-load comparator). #77 and #91
* showed the linear current-injection feedback has loop gain ~1 and cannot hold
* a window; here the loop ratio is set by a device-width ratio (cross-coupled W
* over diode W) that is chosen > 1, so the hysteresis is a large-signal property
* of the load, not a marginal small-signal gain.
*
* Inputs are the existing #29 CTAT sense/reference nodes (TS_SNS, TS_REF, both
* bias-generator-derived per DR-005: no VREF, no bandgap). Output TS_CMP keeps
* the #29 polarity and drive convention (~VIN = not tripped, falling = engaged),
* so M_TSHUT (VIN -> EA_OUT) and its EN clamp are used unchanged.
*
* Auto-restart (DR-005): nothing here is latched across a temperature excursion.
* Both flip points are crossed by the input difference alone; the cell holds
* state only while the input difference sits inside the window.
*
* Interface: VIN, EN, NB (bias-generator NMOS mirror gate), AMP_ENN (shared EN-gated
* pseudo-ground), TS_SNS, TS_REF (inputs), TS_CMP (output, drives M_TSHUT's gate).
* Sizing, measured thresholds and caveats: design/README.md "Regenerative thermal
* comparator (#229)" and sim/thermal-regen-cmp/.
}
G {}
K {}
V {}
S {}
E {}

* ---- ports ----
C {devices/ipin.sym} -700 -100 0 0 {name=p_vin lab=VIN}
C {devices/ipin.sym} -700 -300 0 0 {name=p_en lab=EN}
C {devices/ipin.sym} -700 -500 0 0 {name=p_nb lab=NB}
C {devices/ipin.sym} -700 -700 0 0 {name=p_amp_enn lab=AMP_ENN}
C {devices/ipin.sym} -700 -900 0 0 {name=p_ts_sns lab=TS_SNS}
C {devices/ipin.sym} -700 -1100 0 0 {name=p_ts_ref lab=TS_REF}
C {devices/opin.sym} -700 -1300 0 0 {name=p_ts_cmp lab=TS_CMP}

* ---- tail + input pair ----
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 0 -400 0 0 {name=M_RCTAIL
L=1
W=1
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 20 -430 0 0 {name=p_M_RCTAIL_d lab=RC_TAIL}
C {devices/lab_pin.sym} -20 -400 0 0 {name=p_M_RCTAIL_g lab=NB}
C {devices/lab_pin.sym} 20 -370 0 0 {name=p_M_RCTAIL_s lab=AMP_ENN}
C {devices/lab_pin.sym} 20 -400 0 0 {name=p_M_RCTAIL_b lab=0}
T {M_RCTAIL: tail sink, the same 1/4-width NB copy as the #29 comparator's M_TCTAIL (gate NB, source on the EN-gated AMP_ENN). Sets the comparator branch current; the regeneration ratio below is independent of it.} 60 -420 0 0 0.2 0.2 {}
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 300 -400 0 0 {name=M_RCN1
L=2
W=10
nf=2
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 320 -430 0 0 {name=p_M_RCN1_d lab=RC_A}
C {devices/lab_pin.sym} 280 -400 0 0 {name=p_M_RCN1_g lab=TS_SNS}
C {devices/lab_pin.sym} 320 -370 0 0 {name=p_M_RCN1_s lab=RC_TAIL}
C {devices/lab_pin.sym} 320 -400 0 0 {name=p_M_RCN1_b lab=0}
T {M_RCN1: input device, gate = TS_SNS (cold: TS_SNS > TS_REF, so RC_A is pulled low). Drain RC_A. L=2 W=10 nf=2 as M_TCN1.} 360 -420 0 0 0.2 0.2 {}
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 600 -400 0 0 {name=M_RCN2
L=2
W=10
nf=2
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 620 -430 0 0 {name=p_M_RCN2_d lab=RC_B}
C {devices/lab_pin.sym} 580 -400 0 0 {name=p_M_RCN2_g lab=TS_REF}
C {devices/lab_pin.sym} 620 -370 0 0 {name=p_M_RCN2_s lab=RC_TAIL}
C {devices/lab_pin.sym} 620 -400 0 0 {name=p_M_RCN2_b lab=0}
T {M_RCN2: input device, gate = TS_REF. Drain RC_B. Matched to M_RCN1.} 660 -420 0 0 0.2 0.2 {}

* ---- regenerative load: diode pair + cross-coupled pair ----
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 0 -800 0 0 {name=M_RCD1
L=2
W=10
nf=2
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 20 -770 0 0 {name=p_M_RCD1_d lab=RC_A}
C {devices/lab_pin.sym} -20 -800 0 0 {name=p_M_RCD1_g lab=RC_A}
C {devices/lab_pin.sym} 20 -830 0 0 {name=p_M_RCD1_s lab=VIN}
C {devices/lab_pin.sym} 20 -800 0 0 {name=p_M_RCD1_b lab=VIN}
T {M_RCD1: diode-connected load on RC_A (L=2 W=10 nf=2, the #29 M_TCP1 geometry). Sets the linear-region load conductance gmd.} 60 -820 0 0 0.2 0.2 {}
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 300 -800 0 0 {name=M_RCD2
L=2
W=10
nf=2
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 320 -770 0 0 {name=p_M_RCD2_d lab=RC_B}
C {devices/lab_pin.sym} 280 -800 0 0 {name=p_M_RCD2_g lab=RC_B}
C {devices/lab_pin.sym} 320 -830 0 0 {name=p_M_RCD2_s lab=VIN}
C {devices/lab_pin.sym} 320 -800 0 0 {name=p_M_RCD2_b lab=VIN}
T {M_RCD2: diode-connected load on RC_B, matched to M_RCD1.} 360 -820 0 0 0.2 0.2 {}
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 600 -800 0 0 {name=M_RCC1
L=2
W=17
nf=2
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 620 -770 0 0 {name=p_M_RCC1_d lab=RC_A}
C {devices/lab_pin.sym} 580 -800 0 0 {name=p_M_RCC1_g lab=RC_B}
C {devices/lab_pin.sym} 620 -830 0 0 {name=p_M_RCC1_s lab=VIN}
C {devices/lab_pin.sym} 620 -800 0 0 {name=p_M_RCC1_b lab=VIN}
T {M_RCC1: cross-coupled load, gate = RC_B, drain = RC_A. W=17 against the diode's 10 gives a loop ratio gmc/gmd ~ 1.7 > 1: the differential load conductance is negative, the load is bistable, and the input window between the two flip points is the hysteresis. W=17 is the single sizing knob (the width ratio, not an absolute current, sets the window).} 660 -820 0 0 0.2 0.2 {}
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 900 -800 0 0 {name=M_RCC2
L=2
W=17
nf=2
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 920 -770 0 0 {name=p_M_RCC2_d lab=RC_B}
C {devices/lab_pin.sym} 880 -800 0 0 {name=p_M_RCC2_g lab=RC_A}
C {devices/lab_pin.sym} 920 -830 0 0 {name=p_M_RCC2_s lab=VIN}
C {devices/lab_pin.sym} 920 -800 0 0 {name=p_M_RCC2_b lab=VIN}
T {M_RCC2: cross-coupled load, gate = RC_A, drain = RC_B; matched to M_RCC1.} 960 -820 0 0 0.2 0.2 {}

* ---- EN reset of the latch ----
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 0 -1200 0 0 {name=M_RCEA
L=0.5
W=2
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 20 -1170 0 0 {name=p_M_RCEA_d lab=RC_A}
C {devices/lab_pin.sym} -20 -1200 0 0 {name=p_M_RCEA_g lab=EN}
C {devices/lab_pin.sym} 20 -1230 0 0 {name=p_M_RCEA_s lab=VIN}
C {devices/lab_pin.sym} 20 -1200 0 0 {name=p_M_RCEA_b lab=VIN}
T {M_RCEA: EN=0 pulls RC_A to VIN (gate = EN, same family as M_ENP4). Both latch nodes are forced to the SAME potential while disabled, so an EN rising edge starts the regeneration from a symmetric state and the input sign (not a leftover latch state) decides the outcome.} 60 -1220 0 0 0.2 0.2 {}
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 300 -1200 0 0 {name=M_RCEB
L=0.5
W=2
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 320 -1170 0 0 {name=p_M_RCEB_d lab=RC_B}
C {devices/lab_pin.sym} 280 -1200 0 0 {name=p_M_RCEB_g lab=EN}
C {devices/lab_pin.sym} 320 -1230 0 0 {name=p_M_RCEB_s lab=VIN}
C {devices/lab_pin.sym} 320 -1200 0 0 {name=p_M_RCEB_b lab=VIN}
T {M_RCEB: EN=0 pulls RC_B to VIN; matched to M_RCEA.} 360 -1220 0 0 0.2 0.2 {}

* ---- single-ended output stage ----
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 0 -1600 0 0 {name=M_RCOP
L=1
W=2
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 20 -1570 0 0 {name=p_M_RCOP_d lab=TS_CMP}
C {devices/lab_pin.sym} -20 -1600 0 0 {name=p_M_RCOP_g lab=RC_A}
C {devices/lab_pin.sym} 20 -1630 0 0 {name=p_M_RCOP_s lab=VIN}
C {devices/lab_pin.sym} 20 -1600 0 0 {name=p_M_RCOP_b lab=VIN}
T {M_RCOP: output pull-up, gate = RC_A. Cold (untripped) RC_A sits ~0.8V below VIN so M_RCOP conducts and TS_CMP ~ VIN; hot (tripped) RC_A latches to ~VIN, M_RCOP cuts off and M_RCOS pulls TS_CMP to ~0. Same polarity as #29: TS_CMP ~ VIN = not tripped, falling = engaged.} 60 -1620 0 0 0.2 0.2 {}
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 300 -1600 0 0 {name=M_RCOS
L=2
W=0.5
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 320 -1630 0 0 {name=p_M_RCOS_d lab=TS_CMP}
C {devices/lab_pin.sym} 280 -1600 0 0 {name=p_M_RCOS_g lab=NB}
C {devices/lab_pin.sym} 320 -1570 0 0 {name=p_M_RCOS_s lab=AMP_ENN}
C {devices/lab_pin.sym} 320 -1600 0 0 {name=p_M_RCOS_b lab=0}
T {M_RCOS: output pull-down (NB-mirror bias current source, a few tens of nA), gate = NB, source = AMP_ENN. EN-gated like every other branch.} 360 -1620 0 0 0.2 0.2 {}
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 600 -1600 0 0 {name=M_RCEO
L=0.5
W=2
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 620 -1570 0 0 {name=p_M_RCEO_d lab=TS_CMP}
C {devices/lab_pin.sym} 580 -1600 0 0 {name=p_M_RCEO_g lab=EN}
C {devices/lab_pin.sym} 620 -1630 0 0 {name=p_M_RCEO_s lab=VIN}
C {devices/lab_pin.sym} 620 -1600 0 0 {name=p_M_RCEO_b lab=VIN}
T {M_RCEO: EN=0 forces TS_CMP to VIN (not tripped), the M_ENP4 role.} 660 -1620 0 0 0.2 0.2 {}

