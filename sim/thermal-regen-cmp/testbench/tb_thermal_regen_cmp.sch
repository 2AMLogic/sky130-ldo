v {xschem version=3.4.7 file_version=1.2
* sky130-ldo regenerative thermal-comparator standalone testbench (issue #229).
*
* DUT: design/thermal_cmp_regen.sch (via its symbol). Everything else is a
* REPLICA of blocks that live in design/ldo_3v3in_1v8out.sch, copied with
* identical device sizes so the DUT sees the same bias-generator-derived CTAT
* sense (TS_SNS) and reference (TS_REF) it would see in the LDO:
*   bias generator   R_BIAS, M_BIASN1/N2, M_BIASP1, M_ENN, M_ENP2, M_ENN2
*   #29 CTAT sense   M_TSPS, M_TSD1, M_TSD2
*   #29 reference    M_TSPR (W=7), M_TSR1
* Loading assumption: TS_CMP drives the gate of the real M_TSHUT (pfet, source VIN);
* its drain EA_STUB is held by a 100k resistor to a 2.4V source standing in for
* the error-amp output (EA_OUT sits ~2.4-2.5V regulating at 3.3V). EA_STUB ->
* VIN means "shutdown clamp engaged". The pass device, load and error amp are not
* present: the thermal sense is self-contained and does not depend on VOUT.
*
* Stimulus is set entirely by .param values the runner (sim/thermal-regen-cmp/
* run_demo.py) defines per scenario; nothing analysis-specific lives here:
*   vsup    supply (3.30V for the tt demonstration)
*   vx_amp  series offset injected between the sense node and the comparator
*           input for 20..40us (volts). 0 = no excursion. Negative = the sense
*           is pushed to look HOTTER (CTAT: lower), positive = COLDER. It is a
*           physical input disturbance that seeds the latch state; it is gone
*           (zero) from 41us on, so every observation after 41us is the circuit
*           HOLDING (or losing) the state it was driven to, at that temperature.
*   en_dip  EN level for 61..75us (vsup = no disable; 0 = EN disabled then re-enabled).
* TEMP comes from .temp (ngspice has no time-varying TEMP), so a temperature
* staircase is a set of separate runs.
}
G {}
K {}
V {}
S {}
E {}

C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value="'vsup'" savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p_VVIN_p lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p_VVIN_n lab=0}
C {devices/vsource.sym} -400 -300 0 0 {name=VEN value="PWL(0 0 2u 0 3u 'vsup' 60u 'vsup' 61u 'en_dip' 75u 'en_dip' 76u 'vsup')" savecurrent=true}
C {devices/lab_pin.sym} -400 -330 0 0 {name=p_VEN_p lab=EN}
C {devices/lab_pin.sym} -400 -270 0 0 {name=p_VEN_n lab=0}
C {devices/vsource.sym} -200 -300 0 0 {name=VVX value="PWL(0 0 20u 0 21u 'vx_amp' 40u 'vx_amp' 41u 0)" savecurrent=true}
C {devices/lab_pin.sym} -200 -330 0 0 {name=p_VVX_p lab=TS_SNS}
C {devices/lab_pin.sym} -200 -270 0 0 {name=p_VVX_n lab=SNS}

* ---- REPLICA of the LDO bias generator (design/ldo_3v3in_1v8out.sch: R_BIAS, M_BIASN1/N2, M_BIASP1, M_ENN, M_ENP2, M_ENN2) ----
C {sky130_fd_pr/res_high_po.sym} 400 -100 0 0 {name=R_BIAS W=0.42 L=1500 model=res_high_po spiceprefix=X mult=1}
C {devices/lab_pin.sym} 400 -70 0 0 {name=p_rb1 lab=VIN}
C {devices/lab_pin.sym} 400 -130 0 0 {name=p_rb2 lab=NB}
C {devices/lab_pin.sym} 380 -100 0 0 {name=p_rb3 lab=0}
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 400 -400 0 0 {name=M_BIASN1
L=1
W=4
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 420 -430 0 0 {name=p_M_BIASN1_d lab=NB}
C {devices/lab_pin.sym} 380 -400 0 0 {name=p_M_BIASN1_g lab=NB}
C {devices/lab_pin.sym} 420 -370 0 0 {name=p_M_BIASN1_s lab=BIAS_ENN}
C {devices/lab_pin.sym} 420 -400 0 0 {name=p_M_BIASN1_b lab=0}
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 700 -400 0 0 {name=M_BIASN2
L=1
W=4
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 720 -430 0 0 {name=p_M_BIASN2_d lab=BIASP}
C {devices/lab_pin.sym} 680 -400 0 0 {name=p_M_BIASN2_g lab=NB}
C {devices/lab_pin.sym} 720 -370 0 0 {name=p_M_BIASN2_s lab=BIAS_ENN}
C {devices/lab_pin.sym} 720 -400 0 0 {name=p_M_BIASN2_b lab=0}
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 1000 -400 0 0 {name=M_ENN
L=0.5
W=10
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1020 -430 0 0 {name=p_M_ENN_d lab=BIAS_ENN}
C {devices/lab_pin.sym} 980 -400 0 0 {name=p_M_ENN_g lab=EN}
C {devices/lab_pin.sym} 1020 -370 0 0 {name=p_M_ENN_s lab=0}
C {devices/lab_pin.sym} 1020 -400 0 0 {name=p_M_ENN_b lab=0}
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 400 -800 0 0 {name=M_BIASP1
L=1
W=10
nf=2
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 420 -770 0 0 {name=p_M_BIASP1_d lab=BIASP}
C {devices/lab_pin.sym} 380 -800 0 0 {name=p_M_BIASP1_g lab=BIASP}
C {devices/lab_pin.sym} 420 -830 0 0 {name=p_M_BIASP1_s lab=VIN}
C {devices/lab_pin.sym} 420 -800 0 0 {name=p_M_BIASP1_b lab=VIN}
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 700 -800 0 0 {name=M_ENP2
L=0.5
W=10
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 720 -770 0 0 {name=p_M_ENP2_d lab=BIASP}
C {devices/lab_pin.sym} 680 -800 0 0 {name=p_M_ENP2_g lab=EN}
C {devices/lab_pin.sym} 720 -830 0 0 {name=p_M_ENP2_s lab=VIN}
C {devices/lab_pin.sym} 720 -800 0 0 {name=p_M_ENP2_b lab=VIN}
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 1000 -800 0 0 {name=M_ENN2
L=0.5
W=10
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1020 -830 0 0 {name=p_M_ENN2_d lab=AMP_ENN}
C {devices/lab_pin.sym} 980 -800 0 0 {name=p_M_ENN2_g lab=EN}
C {devices/lab_pin.sym} 1020 -770 0 0 {name=p_M_ENN2_s lab=0}
C {devices/lab_pin.sym} 1020 -800 0 0 {name=p_M_ENN2_b lab=0}

* ---- REPLICA of the #29 CTAT sense (M_TSPS, M_TSD1/2) and reference (M_TSPR, M_TSR1); sizes unchanged from the LDO ----
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 1400 -100 0 0 {name=M_TSPS
L=1
W=1.25
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1420 -70 0 0 {name=p_M_TSPS_d lab=SNS}
C {devices/lab_pin.sym} 1380 -100 0 0 {name=p_M_TSPS_g lab=BIASP}
C {devices/lab_pin.sym} 1420 -130 0 0 {name=p_M_TSPS_s lab=VIN}
C {devices/lab_pin.sym} 1420 -100 0 0 {name=p_M_TSPS_b lab=VIN}
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 1400 -400 0 0 {name=M_TSD1
L=4
W=80
nf=16
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1420 -430 0 0 {name=p_M_TSD1_d lab=SNS}
C {devices/lab_pin.sym} 1380 -400 0 0 {name=p_M_TSD1_g lab=SNS}
C {devices/lab_pin.sym} 1420 -370 0 0 {name=p_M_TSD1_s lab=TS_MID}
C {devices/lab_pin.sym} 1420 -400 0 0 {name=p_M_TSD1_b lab=0}
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 1400 -700 0 0 {name=M_TSD2
L=4
W=80
nf=16
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1420 -730 0 0 {name=p_M_TSD2_d lab=TS_MID}
C {devices/lab_pin.sym} 1380 -700 0 0 {name=p_M_TSD2_g lab=TS_MID}
C {devices/lab_pin.sym} 1420 -670 0 0 {name=p_M_TSD2_s lab=AMP_ENN}
C {devices/lab_pin.sym} 1420 -700 0 0 {name=p_M_TSD2_b lab=0}
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 1800 -100 0 0 {name=M_TSPR
L=1
W=7
nf=1
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1820 -70 0 0 {name=p_M_TSPR_d lab=TS_REF}
C {devices/lab_pin.sym} 1780 -100 0 0 {name=p_M_TSPR_g lab=BIASP}
C {devices/lab_pin.sym} 1820 -130 0 0 {name=p_M_TSPR_s lab=VIN}
C {devices/lab_pin.sym} 1820 -100 0 0 {name=p_M_TSPR_b lab=VIN}
C {sky130_fd_pr/nfet_g5v0d10v5.sym} 1800 -400 0 0 {name=M_TSR1
L=2
W=0.42
nf=1
mult=1
model=nfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 1820 -430 0 0 {name=p_M_TSR1_d lab=TS_REF}
C {devices/lab_pin.sym} 1780 -400 0 0 {name=p_M_TSR1_g lab=TS_REF}
C {devices/lab_pin.sym} 1820 -370 0 0 {name=p_M_TSR1_s lab=AMP_ENN}
C {devices/lab_pin.sym} 1820 -400 0 0 {name=p_M_TSR1_b lab=0}

* ---- DUT and M_TSHUT integration load ----
C {design/thermal_cmp_regen.sym} 2400 -300 0 0 {name=xcmp}
C {devices/lab_pin.sym} 2250 -360 0 0 {name=p_xc_VIN lab=VIN}
C {devices/lab_pin.sym} 2250 -340 0 0 {name=p_xc_EN lab=EN}
C {devices/lab_pin.sym} 2250 -320 0 0 {name=p_xc_NB lab=NB}
C {devices/lab_pin.sym} 2250 -300 0 0 {name=p_xc_AMP_ENN lab=AMP_ENN}
C {devices/lab_pin.sym} 2250 -280 0 0 {name=p_xc_TS_SNS lab=TS_SNS}
C {devices/lab_pin.sym} 2250 -260 0 0 {name=p_xc_TS_REF lab=TS_REF}
C {devices/lab_pin.sym} 2550 -360 0 0 {name=p_xc_out lab=TS_CMP}
C {sky130_fd_pr/pfet_g5v0d10v5.sym} 2800 -300 0 0 {name=M_TSHUT
L=0.5
W=20
nf=4
mult=1
model=pfet_g5v0d10v5
spiceprefix=X}
C {devices/lab_pin.sym} 2820 -270 0 0 {name=p_M_TSHUT_d lab=EA_STUB}
C {devices/lab_pin.sym} 2780 -300 0 0 {name=p_M_TSHUT_g lab=TS_CMP}
C {devices/lab_pin.sym} 2820 -330 0 0 {name=p_M_TSHUT_s lab=VIN}
C {devices/lab_pin.sym} 2820 -300 0 0 {name=p_M_TSHUT_b lab=VIN}
C {devices/res.sym} 3100 -300 0 0 {name=R_EASTUB value=100k m=1}
C {devices/lab_pin.sym} 3100 -330 0 0 {name=p_rst1 lab=EA_STUB}
C {devices/lab_pin.sym} 3100 -270 0 0 {name=p_rst2 lab=EA_REF}
C {devices/vsource.sym} 3300 -300 0 0 {name=VEAREF value="2.4" savecurrent=true}
C {devices/lab_pin.sym} 3300 -330 0 0 {name=p_VEAREF_p lab=EA_REF}
C {devices/lab_pin.sym} 3300 -270 0 0 {name=p_VEAREF_n lab=0}
