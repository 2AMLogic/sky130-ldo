v {xschem version=3.4.7 file_version=1.2
* sky130-ldo load-transient testbench (issue #18).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym -- see that symbol's own
* header for how it was generated) with a load-current step, per
* spec/target-spec.md's DRAFT "Load transient" row: "1<->50 mA step, ~1us
* edges: peak excursion <=150mV, recover to +-1% in <=20us, over the
* ratified C_out/ESR window". That row is DRAFT (issue #1 not yet ratified)
* and the C_out/ESR window itself is spec/decision-records/DR-002
* (status: proposed, not ratified) -- this testbench cites DR-002's
* *proposed* 1uF nominal / representative-ESR point as a starting value,
* not a ratified spec number. Re-verify the bounds once #1 and DR-002 rule.
*
* VIN/EN share the corner runner's 'vsup' parameter (EN is active-high,
* full-rail 0/VIN per design/README.md, so tying it to VIN keeps the DUT
* enabled across the whole PVT matrix). VREF is a fixed 1.2V placeholder
* per design/README.md's "VREF interface caveat" -- matching the 1:2
* feedback-divider ratio issue #22 revised the schematic to (VOUT = 1.5 x
* VREF; #22's own screening data shows the earlier 0.6V/2:1 convention
* does not regulate against this schematic's amplifier output-swing
* ceiling -- see design/README.md's "VREF interface caveat, and the
* reference common mode" section). No reference-generator block exists
* yet.
*
* I_LOAD steps 1mA -> 50mA -> 1mA (PULSE, 1us edges) at VOUT, modelling the
* DRAFT spec's load-transient stimulus literally. C_OUT (1uF) + R_ESR
* (10mOhm, a ceramic-representative point inside DR-002's proposed
* 0-500mOhm window, not a sweep of that window -- full C_out/ESR
* corner-sweep is follow-on scope, e.g. #19) sit at VOUT as the external
* output network.
*
* Known-immature-design caveat (see design/README.md "Known gaps"): this
* schematic's compensation (C_COMP/C_CL) remains an unsized placeholder,
* and the error amplifier still has a light-load/high-VIN output-swing
* ceiling ("Known open item" in design/README.md) even though issue #22
* already added the current-limit and soft-start protection circuitry, so
* this testbench recording a FAIL against the DRAFT peak-excursion bound
* at some corners is an honest, expected verification finding at this
* design stage, not a harness defect. CLAUDE.md: "Verification is the
* product" -- a testbench that surfaces a real immaturity is doing its
* job.
*
* Deliberately NOT in this schematic (the corner runner injects them, so
* one schematic serves the whole PVT matrix): the .lib model corner
* include, .temp, and the .control analysis/measurement block. VIN's
* numeric value comes from 'vsup', same convention as
* sim/pdk-smoke/testbench/tb_pdk_smoke.sch.
}
G {}
K {}
V {}
S {}
E {}
T {load-transient testbench -- exercises design/ldo_3v3in_1v8out.sch (#14)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
VIN/EN = 'vsup' (corner runner); VREF = 1.2V placeholder (see design/README.md)
I_LOAD: PULSE 1mA<->50mA, 1us edges (spec/target-spec.md DRAFT "Load transient" row)
C_OUT/R_ESR: DR-002 proposed 1uF / representative ESR point (DR-002 is proposed, not ratified)} -700 -650 0 0 0.3 0.3 {}

* ---- VIN / EN (tied to the corner runner's supply) ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

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

* ---- output network: C_OUT + R_ESR (DR-002 proposed starting point) ----
C {devices/capa.sym} 600 -400 0 0 {name=COUT m=1 value=1u footprint=1206 device="ceramic capacitor (DR-002 proposed nominal)"}
C {devices/lab_pin.sym} 600 -430 0 0 {name=p11 lab=VOUT}
C {devices/lab_pin.sym} 600 -370 0 0 {name=p12 lab=VESR}
C {devices/res.sym} 600 -250 0 0 {name=RESR value=10m m=1}
C {devices/lab_pin.sym} 600 -280 0 0 {name=p13 lab=VESR}
C {devices/lab_pin.sym} 600 -220 0 0 {name=p14 lab=0}
T {R_ESR: 10mOhm -- a representative point inside DR-002's proposed
0-500mOhm window (no minimum ESR); not a sweep of the window itself} 640 -300 0 0 0.2 0.2 {}

* ---- load: I_LOAD steps 1mA -> 50mA -> 1mA, 1us edges ----
C {devices/isource.sym} 900 -300 0 0 {name=ILOAD value="PULSE(1m 50m 1m 1u 1u 1m 4m)"}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {I_LOAD: PULSE(1m 50m 1m 1u 1u 1m 4m) -- 1mA<->50mA step, 1us edges,
per spec/target-spec.md DRAFT "Load transient" row} 940 -300 0 0 0.2 0.2 {}
