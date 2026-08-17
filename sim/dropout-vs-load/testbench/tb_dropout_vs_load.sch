v {xschem version=3.4.7 file_version=1.2
* sky130-ldo dropout-vs-load testbench (issue #18).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym) with a DC VIN sweep at a
* fixed 50mA load, per spec/target-spec.md's DRAFT "Dropout @ 50 mA" row:
* "< 300 mV" (DRAFT stretch < 200mV), using the DRAFT row's own cited
* method: "gf180's ss/125C/Vin~=Vout+dropout convention" -- i.e. sweep Vin
* down toward Vout at the target load and find the margin at which
* regulation is lost, not a load sweep at a single ample Vin. That row is
* DRAFT (issue #1 not yet ratified); the bound below cites it directly,
* not an invented final limit, and needs re-verification once #1 rules.
*
* I_LOAD is fixed at 50mA (the DRAFT row's own test point). VVIN sweeps
* independently of the corner runner's 'vsup' -- EN uses 'vsup' instead
* (always comfortably above the enable threshold across the whole
* 2.97-3.63V corner axis), so PVT corners (process/temp, and EN's rail via
* 'vsup') still vary per corner point while VIN is finely swept inside
* each corner run. "dropout_v" reports the Vin-Vout margin at the lowest
* swept Vin (worst-case headroom); "vout_at_max_vin_v" is a light-headroom
* regulation sanity check at the sweep's top end.
*
* VREF is a fixed 1.2V placeholder per design/README.md's "VREF interface
* caveat" -- matching the 1:2 feedback-divider ratio issue #22 revised the
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
T {dropout-vs-load testbench -- exercises design/ldo_3v3in_1v8out.sch (#14)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
I_LOAD fixed 50mA (DRAFT "Dropout @ 50mA" row); VVIN DC-swept by the deck
EN = 'vsup' (corner runner, always well above threshold); VREF = 1.2V placeholder} -700 -650 0 0 0.3 0.3 {}

* ---- VIN: DC-swept independently of the corner runner's 'vsup' ----
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

* ---- load: fixed 50mA (the DRAFT "Dropout @ 50 mA" row's own test point) ----
C {devices/isource.sym} 900 -300 0 0 {name=ILOAD value=50m}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {I_LOAD: fixed 50mA -- the DRAFT "Dropout @ 50 mA" row's test point} 940 -300 0 0 0.2 0.2 {}
