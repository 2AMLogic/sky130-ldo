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
* each corner run.
*
* Methodology fixed by issue #71 (superseding #18's original method, which
* measured Vin-Vout at a fixed low-VIN sweep endpoint 1.9V -- deep past the
* point regulation is actually lost, so it reported the pass device's
* residual V_sd rather than classic dropout voltage). experiment.json's deck
* now sweeps VIN DOWNWARD, from a comfortably-regulating value toward a
* value well below the 1.8V target, at finer (20mV, vs #18's 50mV)
* resolution; "dropout_v" is the Vin-Vout margin at the VIN where VOUT first
* falls through 98% of the 1.8V target as VIN decreases (a `.meas dc ...
* fall=1`, interpolated between the two bracketing sweep points -- the
* classic "regulation just lost" definition). "vout_at_max_vin_v" is a
* light-headroom regulation sanity check at the sweep's first-swept
* (highest-VIN) point.
*
* #71 also investigated the DC-solution-multiplicity this sweep direction
* surfaces at several high/mid-VIN points (isolated points landing on a
* non-regulating branch, "singular matrix" ngspice warnings at
* ea_cz/n_fbb/amp_enn) -- the diagnosis differs by temperature:
* - At -40C/27C: independent per-point checks (a fresh `.op` with NO sweep
*   continuation history, both with and without a `.ic` seed copied node-for-
*   node from a neighboring regulating point, and with `.options gminsteps=0`
*   to disable ngspice's gmin-stepping homotopy fallback) reliably reconverge
*   to the *regulating* branch at every jump point checked -- i.e. the
*   default `dc` sweep's continuation path, not a second physically-real
*   equilibrium, is what lands on the non-regulating branch. Confirmed the
*   jumps never dip below the 1.764V departure threshold at these
*   temperatures, so they do not corrupt this measurement.
* - At 125C, across ALL FIVE process corners (not only the ff/sf
*   thermal-shutdown false-trip #69 tracks): the same multiplicity is
*   markedly worse -- the sweep frequently fails to find or hold the
*   regulating branch at all, including converging to non-physical states
*   (e.g. FB/N_FBB divider nodes at hundreds of volts, at the exact nodes
*   ngspice already flags "singular matrix" on) rather than a second
*   legitimate solution. This is NOT the ff/sf thermal-shutdown false-trip
*   (confirmed: TS_SNS/TS_REF stay in the correct untripped ordering at the
*   affected tt/125C point) -- it is this same mechanism (2)/(4), just much
*   less numerically stable at the top of the temperature range. It DOES
*   corrupt dropout_v/vout_at_max_vin_v at the affected 125C corners, so
*   dropout-vs-load's 125C corners (all processes, widening the existing
*   ff/sf-only exclusion) should be read with the same "solver artifact, not
*   a real measurement" caution already applied to ff/sf's 125C numbers, not
*   evaluated as real dropout results -- tracked as a follow-up, #81. See
*   design/README.md's campaign section for the full writeup and evidence.
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
