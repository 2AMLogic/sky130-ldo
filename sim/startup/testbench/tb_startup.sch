v {xschem version=3.4.7 file_version=1.2
* sky130-ldo startup / soft-start testbench (issue #65).
*
* Exercises the soft-start circuitry issue #22 added to the LDO core
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym) -- the M_SSCHG/C_SS
* current-starved ramp feeding the M_IN2S min-select input, see
* design/README.md's "Soft start (#22)" -- against spec/target-spec.md's
* DRAFT "Startup / soft-start" row:
*
*   "monotonic into any load 0-50 mA and any C_out in the stability window;
*    controlled ramp; inside +-2% within a few ms of enable; overshoot
*    <= +2%"
*
* That row is DRAFT (issue #1 not yet ratified) and the stability window it
* refers to is DR-002's *proposed* one (C_eff 0.33-4.7 uF, ESR 0-500 mOhm),
* also unratified -- the bounds in experiment.json cite those directly
* rather than inventing a final limit.
*
* ---------------------------------------------------------------------
* How the enable edge is produced
* ---------------------------------------------------------------------
* VIN is already up and settled; EN is a PULSE that sits at 0 V until
* t = 100 us and then rises to the corner runner's 'vsup' in 1 us, with a
* period long enough that it never falls again inside the run. ngspice
* computes a transient's own t = 0 operating point from each source's
* time-zero value, so every leg below starts from a genuinely disabled,
* fully discharged block (EN = 0, C_OUT at 0 V, the soft-start ramp held at
* 0 by M_SSDIS) rather than from a settled regulating solution -- which is
* what makes this a startup measurement and not a small-signal one. The
* 100 us of pre-enable idle exists so the disabled state is visible in the
* waveform rather than being inferred from a single point at t = 0.
*
* ---------------------------------------------------------------------
* Why one testbench covers four (load, C_out) points
* ---------------------------------------------------------------------
* The row's claim is quantified over TWO ranges at once ("any load 0-50 mA
* and any C_out in the stability window"), so a single-point startup
* transient would substantiate almost none of it. The corner runner already
* owns process/temperature/supply, so this experiment walks the load/C_out
* axis itself inside one deck with ngspice `alter` between transients --
* the same convention sim/loop-gain uses for the DR-002 window. The four
* points are the corners of the two ranges:
*
*   1. C_out 0.33 uF,  0 mA  <- least damping, and no discharge path for an
*                               overshoot except the feedback divider
*   2. C_out 0.33 uF, 50 mA
*   3. C_out 4.7 uF,   0 mA  <- slowest to settle
*   4. C_out 4.7 uF,  50 mA  <- largest inrush (charging the biggest cap
*                               while also feeding the biggest load)
*
* "0 mA" is modelled as R_LOAD = 1e12 rather than by deleting the resistor,
* so the same element can be walked by `alter` across all four points; the
* block's own feedback divider is its only inherent preload there, per
* spec/target-spec.md's Load row.
*
* Every leg restarts from its own t = 0 operating point, so the four points
* are four independent cold enables, not one run with the load changed
* underneath it.
*
* VREF is a fixed 1.2 V placeholder per design/README.md's "VREF interface
* caveat, and the reference common mode" -- matching the 1:2 feedback
* divider (VOUT = 1.5 x VREF). It is held at 1.2 V from t = 0, i.e. the
* reference is assumed already up when EN rises; sequencing the block
* against a reference that ramps WITH it is a different (and currently
* unbuildable) experiment, since no reference-generator block exists yet.
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
T {startup / soft-start testbench -- exercises design/ldo_3v3in_1v8out.sch (#14/#22)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
VIN = 'vsup' (already up); EN = PULSE 0 -> 'vsup' at t = 100us (the enable edge)
VREF = 1.2V placeholder (see design/README.md); C_OUT / R_LOAD walked by `alter`
DRAFT "Startup / soft-start" row: monotonic, inside +-2% within a few ms, overshoot <= +2%} -700 -750 0 0 0.3 0.3 {}

* ---- VIN (already up and settled before the enable edge) ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

* ---- EN: the enable edge this experiment is about ----
C {devices/vsource.sym} -400 -300 0 0 {name=VEN value="PULSE(0 'vsup' 100u 1u 1u 100 200)" savecurrent=true}
C {devices/lab_pin.sym} -400 -330 0 0 {name=p3 lab=EN}
C {devices/lab_pin.sym} -400 -270 0 0 {name=p4 lab=0}
T {EN: 0V until t = 100us, then a 1us rise to the corner runner's 'vsup'
(active-high, full-rail 0/VIN per design/README.md). The pulse width/period
(100s/200s) are far longer than any run here, so EN never falls again --
this measures the enable edge, not an on/off cycle.} -360 -300 0 0 0.2 0.2 {}

* ---- VREF (fixed placeholder, see design/README.md interface caveat) ----
C {devices/vsource.sym} -200 -300 0 0 {name=VVREF value=1.2 savecurrent=true}
C {devices/lab_pin.sym} -200 -330 0 0 {name=p5 lab=VREF}
C {devices/lab_pin.sym} -200 -270 0 0 {name=p6 lab=0}

* ---- DUT: the LDO core regulation loop + soft start (#14/#22) ----
C {design/ldo_3v3in_1v8out.sym} 200 -300 0 0 {name=xldo}
C {devices/lab_pin.sym} 50 -320 0 0 {name=p7 lab=VREF}
C {devices/lab_pin.sym} 50 -300 0 0 {name=p8 lab=EN}
C {devices/lab_pin.sym} 50 -280 0 0 {name=p9 lab=VIN}
C {devices/lab_pin.sym} 350 -320 0 0 {name=p10 lab=VOUT}

* ---- output network: C_OUT + R_ESR, C_OUT walked across DR-002's window ----
C {devices/capa.sym} 600 -400 0 0 {name=COUT m=1 value=0.33u footprint=1206 device="ceramic capacitor (DR-002 proposed low-C_eff corner)"}
C {devices/lab_pin.sym} 600 -430 0 0 {name=p11 lab=VOUT}
C {devices/lab_pin.sym} 600 -370 0 0 {name=p12 lab=VESR}
C {devices/res.sym} 600 -250 0 0 {name=RESR value=10m m=1}
C {devices/lab_pin.sym} 600 -280 0 0 {name=p13 lab=VESR}
C {devices/lab_pin.sym} 600 -220 0 0 {name=p14 lab=0}
T {C_OUT starts at DR-002's proposed low-C_eff corner (0.33uF) and the deck
`alter`s it to the 4.7uF ceiling for legs 3 and 4. R_ESR stays at 10mOhm --
DR-002's posture is "no minimum ESR", so the low-ESR end is the stressing
one for startup damping; the ESR axis itself is sim/loop-gain's job.} 640 -300 0 0 0.2 0.2 {}

* ---- load: walked 0mA <-> 50mA by `alter` ----
C {devices/res.sym} 900 -300 0 0 {name=RLOAD value=1e12 m=1}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {R_LOAD: 1e12 ("0mA", the feedback divider is the only preload) at the
first leg; the deck `alter`s it to 36 Ohm (~50mA at the 1.8V DRAFT output
target) for the loaded legs, covering both ends of the DRAFT row's
"any load 0-50 mA".} 940 -300 0 0 0.2 0.2 {}
