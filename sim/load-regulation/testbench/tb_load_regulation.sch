v {xschem version=3.4.7 file_version=1.2
* sky130-ldo load-regulation testbench (issue #64, split 1/3 of #61).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym) with two discrete DC
* operating-point solves (I_LOAD in {0mA, 50mA}) at a fixed VIN, per
* spec/target-spec.md's DRAFT "Load regulation (0-50mA)" row: "< 1% (18mV),
* counted inside the +-2% window". That row is DRAFT (issue #1 not yet
* ratified); the bound below cites it directly, not an invented final
* limit, and needs re-verification once #1 rules.
*
* Two .op points, not a continuous .dc sweep (deliberate, found the hard
* way): a continuous 'dc iload 0 50m ...' sweep at this schematic's current
* revision does not track a single regulating branch across the whole
* range -- confirmed during this testbench's own bring-up (a full 51-point
* sweep at tt/27C/VIN=3.3V measured a 1.46V peak-to-peak vout excursion,
* over 80% of the 1.8V target, vs. the ~4mV design/README.md's own screening
* data reports at these endpoints). This is the same DC-solution-
* multiplicity family design/README.md's dated 2026-08-25 root-cause section
* documents for VIN sweeps (issue #60 mechanism 4, tracked by #71), now
* also observed load-current-side. Two independent .op solves at the DRAFT
* row's own endpoints (matching design/README.md's own "Load regulation"
* screening convention, which also uses discrete no-load/full-load points,
* not a sweep) complete in well under a second and reproduce that screening
* data. VIN is tied directly to the corner runner's 'vsup' (same convention
* load-transient/psrr-dc already use) -- this row's DRAFT bound is a
* function of load current at a given supply, not a function of VIN itself
* (that is the "Line regulation" row, see sim/line-regulation). EN also ties
* to 'vsup'. The load current source ILOAD is 'alter'ed between 0 and 50mA
* by the deck (mirrors sim/loop-gain's and sim/iq's multi-point-via-alter
* convention, #25).
*
* VREF is a fixed 1.2V placeholder per design/README.md's "VREF interface
* caveat" -- matching the 1:2 feedback-divider ratio issue #22 revised the
* schematic to (VOUT = 1.5 x VREF).
*
* Known-risk note (not a testbench defect): design/README.md's dated
* 2026-08-25 "full 45-point PVT + Monte Carlo campaign" section (issue #60,
* mechanism 1) documents a thermal-shutdown (#29/DR-005) false-trip at the
* ff/sf process corners at 125C, independent of load current -- tracked by
* issue #69. A corner point at that condition is expected to report a
* non-physical load-regulation number (pass device driven off), the same
* documented failure mode load-transient/dropout-vs-load/loop-gain already
* show at those corners -- not a bug in this testbench.
*
* Deliberately NOT in this schematic (the corner runner injects them, so
* one schematic serves the whole PVT matrix): the .lib model corner
* include, .temp, and the .control analysis/measurement block.
}
G {}
K {}
V {}
S {}
E {}
T {load-regulation testbench -- exercises design/ldo_3v3in_1v8out.sch (#14)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
VIN = 'vsup' (corner runner); EN = 'vsup'
I_LOAD: 'alter'ed between 0mA/50mA by the deck (2 discrete .op points,
not a sweep -- see header)} -700 -650 0 0 0.3 0.3 {}

* ---- VIN: tied to the corner runner's 'vsup' ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

* ---- EN (tied to the corner runner's supply -- always enabled) ----
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

* ---- load: 'alter'ed by the deck between 0A (no load) and 50mA (full load) ----
C {devices/isource.sym} 900 -300 0 0 {name=ILOAD value=0}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {I_LOAD: 0A is this schematic's placeholder component value (no load); the
deck's own .control block 'alter's it to 50mA (full load) for the second
.op, per the DRAFT "Load regulation (0-50mA)" row's own two endpoints} 940 -300 0 0 0.2 0.2 {}
