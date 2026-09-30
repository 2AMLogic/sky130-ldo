v {xschem version=3.4.7 file_version=1.2
* #169 re-test of #81 item 2 -- variant C: COLD start, EN edge, load applied
* after the loop is up.
*
* The question #169 asks: at 125 C / 50 mA, does this block have a second,
* stable, non-regulating equilibrium (#81 item 2: tt -> VOUT = 2.093 V), or
* was that the same unconstrained-solve artifact #164 measured at 27 C / 1 mA?
* This variant is the "cold" half of the answer: every node starts at 0 V
* (`tran ... uic`, declared in experiment.json), EN is LOW at t = 0 and rises
* at 100 us -- the same EN edge the shipped sim/startup and
* sim/mc-output-accuracy benches use -- so the transient starts from a state
* the block can actually be in (disabled, fully discharged) and nothing about
* the settled answer comes from an operating-point solve.
*
* The 50 mA load is an ideal current sink, exactly as in sim/dropout-vs-load
* (the bench #81 item 2 was reported against) and in the seeded variants of
* this screen, but it is RAMPED ON (0 -> 50 mA over 2.5 ms -> 2.6 ms) after
* the loop has started, rather than being present at t = 0. An ideal 50 mA
* sink on a disabled, discharged output is not a realizable state: with the
* pass device off it would pull VOUT to whatever negative voltage the models
* allow, which is exactly the kind of non-physical start this screen exists
* to rule out. From 2.6 ms on, this circuit is element-for-element the one
* the seeded variants (sim/ic-screen-125c-v/-f/-b) simulate from t = 0, so the
* settled node sets are directly comparable.
*
* VIN = 'vsup' (the corner runner's supply axis; #81 item 2 ran VIN = 3.60 V,
* which is on this screen's declared supply axis). VREF is the fixed 1.2 V
* placeholder every bench in sim/ uses (design/README.md "VREF interface
* caveat"). C_OUT = 1 uF / R_ESR = 10 mOhm, identical to sim/dropout-vs-load.
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
T {#169 item-2 re-test, variant C -- cold uic start, EN edge at 100us,
50mA ideal load ramped on 2.5ms-2.6ms; VIN = 'vsup'; VREF = 1.2V placeholder} -700 -650 0 0 0.3 0.3 {}

* ---- VIN: the corner runner's supply ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

* ---- EN: low at t=0, edge at 100us (house convention, sim/startup) ----
C {devices/vsource.sym} -400 -300 0 0 {name=VEN value="PULSE(0 'vsup' 100u 1u 1u 100 200)" savecurrent=true}
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

* ---- load: ideal 50mA sink, ramped on once the loop is up ----
C {devices/isource.sym} 900 -300 0 0 {name=ILOAD value="PWL(0 0 2.5m 0 2.6m 50m)"}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
