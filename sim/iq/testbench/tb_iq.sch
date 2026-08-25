v {xschem version=3.4.7 file_version=1.2
* sky130-ldo Iq (quiescent current, excl. load current) testbench (issue
* #64, split 1/3 of #61).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym) with two DC operating-point
* solves -- no load, then full (50mA) load -- per spec/target-spec.md's
* DRAFT "Iq (excl. load current)" row: "< 30uA at no load and full load".
* That row is DRAFT (issue #1 not yet ratified); the bound below cites it
* directly, not an invented final limit, and needs re-verification once #1
* rules.
*
* VIN is tied directly to the corner runner's 'vsup' (same convention
* load-transient/psrr-dc already use). EN also ties to 'vsup'. Iq is
* defined, per design/README.md's own "Iq = total VIN current minus load
* current" convention, as -i(vvin) at no load (I_LOAD=0, so no subtraction
* needed) and as -i(vvin)-50m at full load (subtracting the deck's own
* known 50mA load-current constant, not a measured quantity) -- see
* sim/iq/experiment.json's "deck.analyses" for the exact .op/.op sequence
* (mirrors sim/loop-gain's multi-point-via-alter convention, #25).
*
* VREF is a fixed 1.2V placeholder per design/README.md's "VREF interface
* caveat" -- matching the 1:2 feedback-divider ratio issue #22 revised the
* schematic to (VOUT = 1.5 x VREF).
*
* Known-risk note (not a testbench defect, and confirmed during this
* testbench's own bring-up): design/README.md's dated 2026-08-25 "full
* 45-point PVT + Monte Carlo campaign" section (issue #60, mechanism 1)
* documents a thermal-shutdown (#29/DR-005) false-trip at the ff/sf process
* corners at 125C, independent of load current -- tracked by issue #69. A
* direct check at ff/125C/3.63V (screening, not sim/ evidence) confirms
* TS_CMP=0.39V (tripped) and vout collapsed to -19.2V at full load / 0.14V
* at no load at that exact corner -- yet -i(vvin) itself still reads a
* plausible-looking, in-budget microamp figure there, unlike
* line-regulation/load-regulation where the same false-trip produces an
* unmistakably out-of-range number. vout_no_load_v/vout_full_load_v below
* are reported (unbounded) specifically so a reader can catch this: an
* in-budget Iq "PASS" at a corner where vout is nowhere near 1.8V is not
* evidence of a genuine pass, the same caution design/README.md's mechanism
* 5 (PSRR) already states for its own falsely-tripped "PASS" corners.
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
T {iq testbench -- exercises design/ldo_3v3in_1v8out.sch (#14)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
VIN = 'vsup' (corner runner); EN = 'vsup'
I_LOAD: deck default 0A (no load), deck 'alter's to 50mA for the second .op} -700 -650 0 0 0.3 0.3 {}

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
* (a .op analysis treats capacitors as opens, so C_OUT does not affect
* these Iq measurements -- kept for structural consistency with the other
* testbenches, per design/README.md's own screening-check convention.)
C {devices/capa.sym} 600 -400 0 0 {name=COUT m=1 value=1u footprint=1206 device="ceramic capacitor (DR-002 proposed nominal)"}
C {devices/lab_pin.sym} 600 -430 0 0 {name=p11 lab=VOUT}
C {devices/lab_pin.sym} 600 -370 0 0 {name=p12 lab=VESR}
C {devices/res.sym} 600 -250 0 0 {name=RESR value=10m m=1}
C {devices/lab_pin.sym} 600 -280 0 0 {name=p13 lab=VESR}
C {devices/lab_pin.sym} 600 -220 0 0 {name=p14 lab=0}
T {R_ESR: 10mOhm -- a representative point inside DR-002's proposed
0-500mOhm window (no minimum ESR); not a sweep of the window itself} 640 -300 0 0 0.2 0.2 {}

* ---- load: 0A by default (no load), 'alter'ed to 50mA mid-deck ----
C {devices/isource.sym} 900 -300 0 0 {name=ILOAD value=0}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {I_LOAD: 0A by default (this schematic's component value, "no load" --
the feedback divider is the only inherent preload); the deck's own
.control block 'alter's it to 50mA ("full load") for the second .op, per
the DRAFT "Iq (excl. load current)" row's own two test points} 940 -300 0 0 0.2 0.2 {}
