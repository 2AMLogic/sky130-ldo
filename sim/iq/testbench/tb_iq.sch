v {xschem version=3.4.7 file_version=1.2
* sky130-ldo Iq (quiescent current, excl. load current) testbench (issue
* #64, split 1/3 of #61).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym) with two DC operating-point
* solves -- no load, then full (50mA) load -- per spec/target-spec.md's
* "Iq (excl. load current)" row: "< 30uA at no load and full load". That row
* is the one row DR-006 left open when issue #1 ratified the rest of the
* table: its number is set by spec/decision-records/DR-009-iq-budget.md,
* whose status is 'proposed' -- DR-009 does not ratify itself, and ratifies
* only when the pull request it ships in merges (the same path DR-006 took).
* The bound below cites DR-009's number verbatim, not an invented final
* limit, and needs re-verification if that record changes before it merges.
*
* VIN is tied directly to the corner runner's 'vsup' (same convention
* load-transient/psrr-dc already use). Iq is defined, per
* design/README.md's own "Iq = total VIN current minus load current"
* convention, as -i(vvin) at no load (I_LOAD=0, so no subtraction needed)
* and as -i(vvin)-50m at full load (subtracting the deck's own known 50mA
* load-current constant, not a measured quantity) -- see
* sim/iq/experiment.json's "deck.analyses" for the exact sequence (mirrors
* sim/loop-gain's multi-point-via-alter convention, #25).
*
* Initial-condition contract (issue #171, converted by #173). Each of the
* two points is a COLD-START, SETTLED transient ('tran 10u 200m uic' with
* VEN below stepping high at 101us, measured over its settled 199ms-200ms
* tail) -- the same 'uic' + EN-edge shape #172 landed for the sibling
* line-regulation/load-regulation benches, which share this schematic's
* output network (1uF COUT / 10mOhm RESR) and the same iload 'alter'
* convention. NOT the bare unconstrained two-'.op' chain this bench used
* through record 20260910-034648-6c0436d: 45 of that record's 45 corners
* carried a solver diagnostic ('singular matrix' or 'out of range for ^'),
* which sim/bin/corner-run.py's #171 gate now forces to FAIL outright. Every
* node starts at its natural cold value with the block disabled and powers
* up through its own soft-start ramp, so there is no operating-point solve
* in the deck at all. Reusing load-regulation's own measured 199ms-200ms
* settling window here (rather than re-measuring it from scratch) is safe
* because both benches share the same COUT/RESR output network and the same
* iload 'alter' shape -- the settling time is a property of that shared
* network, not of what is measured once it settles -- and Iq itself needs
* the same settled window a vout reading does: any residual COUT charging
* current at an earlier window would show up as extra -i(vvin), not just as
* an unsettled vout.
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
* unmistakably out-of-range number. vout_no_load_v/vout_full_load_v are now
* bounded to the ratified Output row's 1.764-1.836V window (issue #133,
* folded into #173) rather than merely reported: a corner whose operating
* point is not really regulating now fails outright instead of relying on a
* reader to notice a plausible-looking, in-budget Iq figure next to an
* out-of-window vout, the same regulation-gate pattern
* sim/enable-shutdown/experiment.json's vout_pre_disable_v already uses.
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
VIN = 'vsup' (corner runner)
EN: 0V until 101us, then 'vsup' (the contract's EN edge, #171/#173)
I_LOAD: 'alter'ed between 0mA/50mA by the deck (2 discrete cold-start settled
'uic' transients, not a bare .op -- see header)} -700 -650 0 0 0.3 0.3 {}

* ---- VIN: tied to the corner runner's 'vsup' ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

* ---- EN: 0V (disabled) until 101us, then the corner runner's supply. This is
*      the initial-condition contract's own EN edge (#171, converted by
*      #173): with 'tran ... uic' every node starts cold and the block
*      powers up through its own soft-start ramp, so no measured point is
*      read off an unconstrained DC solve. Same 'dc 0 pwl(...)' form
*      sim/load-regulation/sim/enable-shutdown already use. ----
C {devices/vsource.sym} -400 -300 0 0 {name=VEN value="dc 0 pwl(0 0 100u 0 101u 'vsup' 10 'vsup')" savecurrent=true}
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
* (post-#173: each Iq point is now a settled 'tran ... uic' rather than a
* bare .op, so C_OUT is a real part of the circuit being settled -- the
* 199ms-200ms measurement window is chosen so its charging current has
* already died out, per the header's initial-condition contract note.)
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
.control block 'alter's it to 50mA ("full load") for the second cold-start
'uic' transient, per the "Iq (excl. load current)" row's own two test points
(bound set by DR-009, `proposed`)} 940 -300 0 0 0.2 0.2 {}
