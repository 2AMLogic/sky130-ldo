v {xschem version=3.4.7 file_version=1.2
* sky130-ldo PSRR testbench (issue #18).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym) with a small-signal AC
* sweep on VIN, per spec/target-spec.md's ratified "PSRR" row: ">50dB @ 1kHz
* and >20dB @ 100kHz, at 1mA (light-load, binding) and at 50mA". That row
* is ratified by issue #1 / DR-006; the bounds below cite it verbatim,
* not an invented final limit.
*
* VIN carries both the corner runner's DC 'vsup' bias and a 1V AC
* stimulus, so vdb(vout) from the AC analysis directly gives the
* Vin->Vout small-signal gain in dB; PSRR(dB) = -vdb(vout).
*
* Load points (BOTH of the row's, since #117). The ratified row names
* four conditions -- two frequencies x two load points -- and the corner
* runner's deck now measures all four, sweeping both load points inside
* one deck: first the 1.8kOhm load instantiated below (~1mA), then
* 'alter rload = 36' for the 50mA point, the same single-deck/multi-point
* pattern sim/loop-gain uses for the DR-002 C_out window. RLOAD stays
* 1.8k in this schematic because that is the DC operating point the deck
* starts from; the 50mA value lives in sim/psrr-dc/experiment.json's
* 'analyses' list, not here.
*
* History of the one-load-point v1 (kept because it explains the change):
* the v1 deck measured only the ~1mA point, because the pre-#25
* five-transistor amplifier had an output-swing ceiling pinned to the
* reference common mode and did not hold regulation at 50mA -- a
* small-signal AC analysis needs a valid regulating DC operating point to
* linearize around, so an AC sweep there would not have been a meaningful
* PSRR number, merely an unmet bound. Issue #25's current-mirror-OTA
* rebuild removed that ceiling (design/README.md, "Error-amplifier output
* stage (rebuilt in #25)"), and #117 re-checked the 50mA operating point
* directly: VOUT = 1.798V at tt/27C/3.30V, regulating. The row's 50mA
* half is therefore no longer un-testbenched, and the v1 simplification
* is retired.
*
* EN is tied to VIN's DC value via a separate DC-only source (EN does not
* need the AC stimulus -- only VIN does, per the ratified PSRR row). VREF is
* a fixed 1.2V placeholder per design/README.md's "VREF interface caveat"
* -- matching the 1:2 feedback-divider ratio issue #22 revised the
* schematic to (VOUT = 1.5 x VREF); the earlier 0.6V/2:1 convention does
* not regulate against this schematic's amplifier output-swing ceiling.
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
T {psrr-dc testbench -- exercises design/ldo_3v3in_1v8out.sch (#14)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
VIN = DC 'vsup' + AC 1V (corner runner sets 'vsup'); VREF = 1.2V placeholder
PSRR(dB) = -vdb(vout); both ratified load points (1mA here, 50mA via
'alter rload = 36' in the deck) -- see header} -700 -650 0 0 0.3 0.3 {}

* ---- VIN: DC bias from the corner runner's 'vsup' + 1V AC stimulus ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value="DC 'vsup' AC 1" savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

* ---- EN (DC only, tied to the corner runner's supply) ----
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

* ---- load: 1.8kOhm (~1mA) as the deck's starting point, see header ----
C {devices/res.sym} 900 -300 0 0 {name=RLOAD value=1.8k m=1}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {R_LOAD: 1.8kOhm, ~1mA class at VOUT~1.8V -- the first of the two
ratified load points. The deck re-runs the same AC sweep after
'alter rload = 36' for the 50mA point (see header "Load points")} 940 -300 0 0 0.2 0.2 {}
