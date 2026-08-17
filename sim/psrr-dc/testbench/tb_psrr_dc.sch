v {xschem version=3.4.7 file_version=1.2
* sky130-ldo PSRR testbench (issue #18).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym) with a small-signal AC
* sweep on VIN, per spec/target-spec.md's DRAFT "PSRR" row: ">50dB @ 1kHz
* and >20dB @ 100kHz, at 1mA (light-load, binding) and at 50mA". That row
* is DRAFT (issue #1 not yet ratified); the bounds below cite it directly,
* not an invented final limit, and need re-verification once #1 rules.
*
* VIN carries both the corner runner's DC 'vsup' bias and a 1V AC
* stimulus, so vdb(vout) from the AC analysis directly gives the
* Vin->Vout small-signal gain in dB; PSRR(dB) = -vdb(vout).
*
* Scope note (deliberate v1 simplification, not an oversight): this
* testbench characterizes ONE load point (1.8kOhm, ~1mA -- the load the
* screening OP check in design/README.md confirms actually regulates for
* this schematic's current maturity), not both 1mA and 50mA the DRAFT row
* names. A small-signal AC analysis needs a valid regulating DC operating
* point to linearize around; design/README.md's OP check and this issue's
* own sim/load-transient/sim/dropout-vs-load records already show this
* schematic's placeholder compensation and single-stage OTA do not hold
* regulation at 50mA load (large excursion into an invalid, non-regulating
* OP), so an AC sweep around that OP would not be a meaningful PSRR number
* -- not just an unmet spec bound. Extending to a real 50mA-load PSRR
* point is follow-on scope once the amplifier/compensation matures (or is
* covered by #19's fuller characterization).
*
* EN is tied to VIN's DC value via a separate DC-only source (EN does not
* need the AC stimulus -- only VIN does, per the DRAFT PSRR row). VREF is
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
PSRR(dB) = -vdb(vout); one load point only (~1mA) -- see header for why} -700 -650 0 0 0.3 0.3 {}

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

* ---- load: fixed 1.8kOhm (~1mA at the light-load OP), see header ----
C {devices/res.sym} 900 -300 0 0 {name=RLOAD value=1.8k m=1}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {R_LOAD: 1.8kOhm, ~1mA class at VOUT~1.8V -- the single load point this
v1 testbench characterizes (see header "Scope note")} 940 -300 0 0 0.2 0.2 {}
