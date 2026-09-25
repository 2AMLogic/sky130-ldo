v {xschem version=3.4.7 file_version=1.2
* #169 re-test of #81 item 2 -- the FULL-node-set seeded testbench
* (variants F and B share this file, exactly as #164's variants A and D
* shared one; they differ only in the analysis card each experiment.json
* declares):
*   - variant F (sim/ic-screen-125c-f): `tran ... uic` -- #81 item 2's own
*     analysis, but with every node #169 names given its intended-branch
*     value instead of only v(vout);
*   - variant B (sim/ic-screen-125c-b): `tran ...` without `uic` -- #164's
*     variant-B contract: `.ic` constrains the operating-point solve to the
*     regulating state, and the transient is then released from it.
*
* The circuit is sim/dropout-vs-load's (EN a DC level at 'vsup', ideal 50 mA
* sink from t = 0, C_OUT = 1 uF / 10 mOhm, VREF = 1.2 V) with VIN = 'vsup'
* instead of a DC sweep. It differs from
* sim/ic-screen-125c-v/testbench/tb_ic_screen_125c_vout_only.sch ONLY in the
* `.ic` card.
*
* Where the .ic values come from (not invented): the settled node set of
* variant C -- a cold, EN-edged start of this same circuit -- at tt / 125 C /
* VIN = 3.60 V / 50 mA, measured by a local probe before this screen ran
* (VOUT 1.79864, FB 1.19928, N_FBB 0.599735, EA_OUT = EA_CZ 2.35717,
* SS 3.59845, BIASP 2.69448, NB 0.761187, EA_TAIL 2.47303, EA_D1 0.793866,
* EA_D2 0.793155 V), rounded. Nodes whose regulating value tracks VIN (the pass
* gate EA_OUT/EA_CZ, the PMOS bias rail BIASP, the amplifier tail EA_TAIL and
* the soft-start node SS) are written relative to 'vsup' so the seed is a
* realizable state at every supply on the axis rather than one above VIN;
* the ground-referenced ones (VOUT, the divider taps, NB, EA_D1/EA_D2) are
* absolute. SS is seeded 2 mV below VIN (the rail it charges to).
*
* Deliberately NOT in this schematic (the corner runner injects them): the
* .lib model corner include, .temp, .param vsup, and the .control block.
* This slug substantiates NO spec row -- see experiment.json's claim.
}
G {}
K {}
V {}
S {}
E {}
T {#169 item-2 re-test, variants F/B -- full 11-node intended-branch .ic,
EN DC at 'vsup', ideal 50mA from t=0; VIN = 'vsup'; VREF = 1.2V placeholder} -700 -650 0 0 0.3 0.3 {}

* ---- VIN: the corner runner's supply ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

* ---- EN: a DC level at 'vsup' (as in sim/dropout-vs-load, the bench #81 item 2 used) ----
C {devices/vsource.sym} -400 -300 0 0 {name=VEN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -400 -330 0 0 {name=p3 lab=EN}
C {devices/lab_pin.sym} -400 -270 0 0 {name=p4 lab=0}

* ---- VREF (fixed placeholder, see design/README.md interface caveat) ----
C {devices/vsource.sym} -200 -300 0 0 {name=VVREF value=1.2 savecurrent=true}
C {devices/lab_pin.sym} -200 -330 0 0 {name=p5 lab=VREF}
C {devices/lab_pin.sym} -200 -270 0 0 {name=p6 lab=0}

* ---- DUT: the LDO core regulation loop (#14) ----
C {design/ldo_3v3in_1v8out.sym} 200 -300 0 0 {name=xldo}
C {devices/lab_pin.sym} 50 -320 0 0 {name=p7 lab=VREF}
C {devices/lab_pin.sym} 50 -300 0 0 {name=p8 lab=EN}
C {devices/lab_pin.sym} 50 -280 0 0 {name=p9 lab=VIN}
C {devices/lab_pin.sym} 350 -320 0 0 {name=p10 lab=VOUT}

* ---- output network: C_OUT + R_ESR (identical to sim/dropout-vs-load) ----
C {devices/capa.sym} 600 -400 0 0 {name=COUT m=1 value=1u footprint=1206 device="ceramic capacitor (DR-002 proposed nominal)"}
C {devices/lab_pin.sym} 600 -430 0 0 {name=p11 lab=VOUT}
C {devices/lab_pin.sym} 600 -370 0 0 {name=p12 lab=VESR}
C {devices/res.sym} 600 -250 0 0 {name=RESR value=10m m=1}
C {devices/lab_pin.sym} 600 -280 0 0 {name=p13 lab=VESR}
C {devices/lab_pin.sym} 600 -220 0 0 {name=p14 lab=0}

* ---- load: ideal 50mA sink from t=0 (identical to sim/dropout-vs-load) ----
C {devices/isource.sym} 900 -300 0 0 {name=ILOAD value=50m}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}

* ---- the full intended-branch seed (#169 Scope item 1) ----
C {devices/code_shown.sym} -700 -100 0 0 {name=IC_SEED only_toplevel=false value=".ic v(VOUT)=1.8 v(xldo.FB)=1.2 v(xldo.N_FBB)=0.6 v(xldo.EA_OUT)=\{vsup-1.243\} v(xldo.EA_CZ)=\{vsup-1.243\} v(xldo.SS)=\{vsup-0.002\} v(xldo.BIASP)=\{vsup-0.906\} v(xldo.NB)=0.761 v(xldo.EA_TAIL)=\{vsup-1.127\} v(xldo.EA_D1)=0.794 v(xldo.EA_D2)=0.794"}
