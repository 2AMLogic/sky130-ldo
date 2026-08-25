v {xschem version=3.4.7 file_version=1.2
* sky130-ldo line-regulation testbench (issue #64, split 1/3 of #61).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym) with four discrete DC
* operating-point solves (VIN in {2.97V, 3.63V} x I_LOAD in {1mA, 50mA}),
* per spec/target-spec.md's DRAFT "Line regulation" row: "< 5 mV/V over
* 2.97-3.63V, at 1mA and 50mA". That row is DRAFT (issue #1 not yet
* ratified); the bound below cites it directly, not an invented final
* limit, and needs re-verification once #1 rules.
*
* Four .op points, not a continuous .dc sweep (deliberate, found the hard
* way): a continuous 'dc vvin 2.97 3.63 ...' sweep at this schematic's
* current revision repeatedly hits gmin-stepping/singular-matrix
* non-convergence partway through the range (design/README.md's dated
* 2026-08-25 root-cause section, issue #60 mechanism 4, tracked by #71,
* documents the same DC-solution-multiplicity behavior for VIN sweeps at
* 50mA load) -- confirmed during this testbench's own bring-up: a 34-point
* sweep over this exact range did not complete in minutes of wall-clock
* time. Four independent .op solves at the DRAFT range's own two endpoints
* (matching design/README.md's own "DC operating grid" screening
* convention, which also uses discrete VIN points, not a sweep) complete in
* well under a second and reproduce that screening data's line-regulation
* numbers. VIN and I_LOAD are both 'alter'ed between .op solves (mirrors
* sim/loop-gain's and sim/iq's multi-point-via-alter convention, #25) --
* see sim/line-regulation/experiment.json's "deck.analyses" for the exact
* sequence. line_reg_*_mv_per_v is computed as
* abs(1000*(vout_hi-vout_lo)/(3.63-2.97)), i.e. mV per V of VIN span over
* the DRAFT range's two endpoints -- the same convention design/README.md's
* own line-regulation screening numbers use.
*
* VIN's own component value below (3.3V) is a placeholder the deck's first
* 'alter' immediately overwrites; it is never simulated as-is.
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
* non-physical line-regulation number (pass device driven off), the same
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
T {line-regulation testbench -- exercises design/ldo_3v3in_1v8out.sch (#14)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
VVIN 'alter'ed between 2.97V/3.63V by the deck (4 discrete .op points,
not a sweep -- see header); EN = 'vsup' (corner runner)
I_LOAD: 'alter'ed between 1mA/50mA by the deck} -700 -650 0 0 0.3 0.3 {}

* ---- VIN: independent of the corner runner's 'vsup'; 'alter'ed by the deck ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value=3.3 savecurrent=true}
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

* ---- load: current source, 'alter'ed by the deck between 1mA and 50mA ----
C {devices/isource.sym} 900 -300 0 0 {name=ILOAD value=1m}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {I_LOAD: 1mA is this schematic's placeholder component value; the deck's
own .control block 'alter's it between 1mA and 50mA across the four .op
points, per the DRAFT "Line regulation" row's own two test points} 940 -300 0 0 0.2 0.2 {}
