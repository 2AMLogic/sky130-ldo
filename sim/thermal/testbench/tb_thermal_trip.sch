v {xschem version=3.4.7 file_version=1.2
* sky130-ldo thermal-shutdown trip/hysteresis testbench (issue #66).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym), including the
* thermal-shutdown circuit #29 added per DR-005
* (spec/decision-records/DR-005-thermal-shutdown-trip.md): CTAT sense
* stack (TS_SNS/TS_MID), CTAT reference (TS_REF), NMOS differential-pair
* comparator (TC_D1/TC_TAIL/TS_CMP) and hysteresis injector (TS_HYS),
* wired into the existing EN-gated shutdown path via M_TSHUT.
*
* Method: a continuous ngspice '.dc temp <lo> <hi> <step>' sweep,
* ascending then descending, in a single ngspice session so the second
* (descending) sweep continues from the operating point the first
* (ascending) sweep left behind -- the standard DC-continuation
* technique for characterizing a hysteretic comparator's two trip
* points (this is a DC/quasi-static method: the die's own thermal mass
* is many orders of magnitude slower than the electrical settling this
* testbench cares about, so a DC operating-point sweep over TEMP is the
* right tool, not a transient). VOUT is the functional signal watched:
* while untripped the loop regulates near its nominal DC operating
* point (~1.7-1.9V at this load per design/README.md's DC operating
* grid); once M_TSHUT engages, M_PASS turns off and VOUT collapses
* toward 0V through R_LOAD -- a >100x, unambiguous swing, not a
* fractional-volt threshold call. The corner runner's own .control
* block (deck.analyses in experiment.json) defines the exact sweep
* range/step and the '.measure dc ... find temp when v(vout)=<thresh>'
* expressions that locate the trip/reset crossings; nothing analysis-
* specific lives in this schematic, per this directory's convention.
*
* 125C-vs-150C corner-coverage decision (see this issue's own
* documentation trail: spec/decision-records/DR-005-thermal-shutdown-trip.md
* "2026-08-25 addendum" and design/README.md's "Known gaps" section):
* DR-004 pins this repo's *PVT-corner* verification temperature axis at
* {-40, 27, 125}C. This testbench deliberately sweeps past that pin
* (up to 180C) because DR-005's own 150C nominal trip target sits
* above it and locating the actual trip/reset crossing needs it -- an
* explicit, scoped extension for this one testbench, not a change to
* DR-004's binding for the other four (load-transient/psrr-dc/
* dropout-vs-load/loop-gain) or for spec verification generally. Points
* above 125C run the pinned sky130 BSIM models in extrapolation beyond
* DR-004's characterized range; empirically confirmed (2026-08-25, this
* issue) to solve without numerical failure up to 200C on a simple
* diode-connected core-device sanity check, but not confirmed against
* silicon -- so trip/reset numbers from this testbench carry lower
* confidence than a PVT-corner point inside the pinned axis, and the
* record says so explicitly rather than presenting them as equally
* trustworthy.
*
* VIN and EN are DC-only (no AC/transient stimulus needed for a DC
* temperature sweep). VREF is a fixed 1.2V placeholder per
* design/README.md's "VREF interface caveat" -- matching the 1:2
* feedback-divider ratio (VOUT = 1.5 x VREF), same convention
* load-transient/psrr-dc/dropout-vs-load/loop-gain already use.
*
* Deliberately NOT in this schematic (the corner runner injects them,
* so one schematic serves the whole process/supply matrix): the .lib
* model corner include, the fixed .temp default (overridden here by the
* swept analysis anyway), and the .control analysis/measurement block.
}
G {}
K {}
V {}
S {}
E {}
T {thermal testbench -- exercises design/ldo_3v3in_1v8out.sch (#14, #29)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
DC temp sweep (ascending then descending) locates the auto-restart
trip/reset crossing of DR-005's thermal-shutdown circuit -- see header} -700 -650 0 0 0.3 0.3 {}

* ---- VIN: DC bias from the corner runner's 'vsup' (no AC needed) ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

* ---- EN (DC only, tied to the corner runner's supply -- always enabled) ----
C {devices/vsource.sym} -400 -300 0 0 {name=VEN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -400 -330 0 0 {name=p3 lab=EN}
C {devices/lab_pin.sym} -400 -270 0 0 {name=p4 lab=0}

* ---- VREF (fixed placeholder, see design/README.md interface caveat) ----
C {devices/vsource.sym} -200 -300 0 0 {name=VVREF value=1.2 savecurrent=true}
C {devices/lab_pin.sym} -200 -330 0 0 {name=p5 lab=VREF}
C {devices/lab_pin.sym} -200 -270 0 0 {name=p6 lab=0}

* ---- DUT: the LDO core regulation loop + thermal shutdown (#14, #29) ----
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

* ---- load: fixed 1.8kOhm (~1mA at the light-load OP), same point
*        design/README.md's own thermal-shutdown screening OP check uses ----
C {devices/res.sym} 900 -300 0 0 {name=RLOAD value=1.8k m=1}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {R_LOAD: 1.8kOhm, ~1mA class at VOUT~1.8V -- same load point
design/README.md's thermal-shutdown OP check and psrr-dc use} 940 -300 0 0 0.2 0.2 {}
