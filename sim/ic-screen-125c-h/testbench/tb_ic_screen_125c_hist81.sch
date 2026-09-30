v {xschem version=3.4.7 file_version=1.2
* #169 re-test of #81 item 2 -- variant H: #81's OWN method on #81's OWN circuit.
*
* Identical to sim/ic-screen-125c-v/testbench/tb_ic_screen_125c_vout_only.sch
* (`.ic v(vout)=1.8` only, `tran ... uic` declared in experiment.json, EN a DC
* level, ideal 50 mA sink from t = 0, C_OUT = 1 uF / 10 mOhm, VREF = 1.2 V,
* VIN = 'vsup') except for ONE instance: the DUT is the frozen copy of
* design/ldo_3v3in_1v8out.sch at commit 64c17cb (#81's merge, before #90's
* thermal-shutdown re-size and #116's pass-device re-size), at
* sim/ic-screen-125c-h/dut/. Variants V/F/B/C answer "does the CURRENT circuit
* have #81 item 2's second equilibrium?"; this one answers the question they
* cannot: "did #81's circuit, under #81's method, ever reach it?" -- so a
* negative result on the current circuit cannot be explained away as "#90 or
* #116 fixed it in passing".
*
* It also dumps TS_SNS and TS_REF (the thermal-shutdown sense and reference
* nodes #81 says it checked) at #81's 800 us time point as well as at the 3 ms
* settle, because #81's reported (VOUT, FB, N_FBB) triple is compared against
* every dumped node in design/README.md "#169".
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
T {#169 item-2 re-test, variant H (historical: #81-era DUT at 64c17cb) -- #81's own method: .ic v(vout)=1.8 ONLY + uic,
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

* ---- DUT: FROZEN #81-era copy (commit 64c17cb) -- NOT the live design ----
C {sim/ic-screen-125c-h/dut/ldo_3v3in_1v8out_at81.sym} 200 -300 0 0 {name=xldo}
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

* ---- variant V's one card: #81 item 2's .ic, v(vout) ONLY ----
C {devices/code_shown.sym} -700 -100 0 0 {name=IC_SEED only_toplevel=false value=".ic v(VOUT)=1.8"}
