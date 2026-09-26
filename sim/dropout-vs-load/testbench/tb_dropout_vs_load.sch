v {xschem version=3.4.7 file_version=1.2
* sky130-ldo dropout-vs-load testbench (issue #18).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym) with a DC VIN sweep at a
* fixed 50mA load, per spec/target-spec.md's ratified "Dropout @ 50 mA" row:
* "< 300 mV" (stretch < 200mV), using the row's own cited
* method: "gf180's ss/125C/Vin~=Vout+dropout convention" -- i.e. sweep Vin
* down toward Vout at the target load and find the margin at which
* regulation is lost, not a load sweep at a single ample Vin. That row is
* ratified by issue #1 / DR-006; the bound below cites it verbatim,
* not an invented final limit.
*
* I_LOAD is fixed at 50mA (the ratified row's own test point). VVIN sweeps
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
*   evaluated as real dropout results. **Root-caused by #81**: most of the
*   extreme campaign numbers are outright Newton non-convergence (garbage
*   that fails the divider's own algebra), but a settled UIC transient with
*   VOUT's own capacitor seeded exactly at the intended 1.8V point (the one
*   true reactive state in this loop) reliably drifts away to a DIFFERENT,
*   genuinely stable, non-regulating equilibrium at 125C (tt/ss/fs all
*   checked at Vin=3.60V/50mA) -- a real circuit robustness gap, not a
*   solver-seeding problem (`.nodeset`/`.ic`/`gminsteps=0` hardening tried,
*   none fixed it). Fix deferred to #79 (shares root cause with mechanism
*   2's light-load stability shortfall). See design/README.md's campaign
*   section ("#71/#81 resolved") for the full writeup and evidence.
*   CORRECTED BY #169 (2026-09-25): the second equilibrium above does not
*   exist. Re-run as committed experiments (sim/ic-screen-125c-v/-f/-b/-c,
*   plus -h on a frozen copy of #81's DUT), every initial condition --
*   #81's own included -- regulates at 125C/50mA with no solver diagnostic,
*   and #81's reported VOUT/FB/N_FBB values are the regulating state's
*   EA_OUT/TS_SNS/TS_REF. What still corrupts this bench's 125C corners is
*   the Newton non-convergence half alone: a bench (initial-condition)
*   problem tracked by #138/#168, not a circuit gap. See design/README.md
*   section #169.
*
* CONVERTED BY #178 (2026-09-26) to the #171 initial-condition contract
* (sim/README.md "Initial-condition contract"): the `dc VVIN 3.63 1.5 -0.02`
* sweep this bench used through record 20260923-123440-d71f4b3 is gone. VIN
* is now a PWL ramp inside ONE cold-start `uic` transient:
*   0 -> 3.63V by 100us (cold start; EN steps high at 100us, the same
*   PULSE(0 'vsup' 100u 1u 1u 100 200) edge sim/ic-screen-125c-c uses),
*   the ideal 50mA sink ramps on over 2.5-2.6ms once the loop is up
*   (ic-screen-125c-c's own PWL, verbatim -- an ideal sink on a disabled,
*   discharged output is not a realizable state), settled by 5.5ms,
*   then 3.63V -> 1.5V over 6ms-14ms: the same VIN range the `dc` sweep
*   covered, walked as a quasi-static line droop instead.
* WHY the analysis changed shape rather than just gaining a seed: for a `dc`
* analysis ngspice honours neither accepted seed shape. Measured on this very
* bench during #178 (tt/125C/3.30V, one corner, `.ic` card copied verbatim
* from sim/ic-screen-125c-b): adding the eleven-node `.ic` changes nothing --
* `singular matrix` x6, `Dynamic gmin stepping failed` x16 and
* `out of range for ^` x13 (iterates at 1e155-1e188 V on the
* sky130_fd_pr__res_xhigh_po body expressions xr_fb_b/xr_fb_c/xr_cz), the
* same flail as the unseeded run, because `.ic` is applied to the
* operating-point solve that precedes a non-`uic` transient, not to a `dc`
* sweep's own solves. #172 measured the other half on the regulation benches:
* `.nodeset`, which a bare solve does honour, still printed `singular matrix`
* plus `Dynamic gmin stepping failed` at 3 of 5 corners probed. And a seed
* could only ever fix the sweep's FIRST point: the superseded record's logs
* carry thousands of diagnostics per corner, i.e. the continuation re-derives
* (and re-loses) the branch at points all the way down the sweep. A `uic`
* transient has no operating-point solve at all, which is why it is the shape
* #170 (mc-output-accuracy) and #172 (line-/load-regulation) also landed on.
* QUASI-STATIC, MEASURED not assumed -- a three-point ramp-rate series at
* tt/27C/3.30V (a corner this bench's own header calls reliable), all three
* with zero solver diagnostics:
*     8ms ramp (266.3 V/s): dropout_v = 0.397657V
*    20ms ramp (106.5 V/s): dropout_v = 0.397295V
*    60ms ramp ( 35.5 V/s): dropout_v = 0.398492V
* The spread over a 7.5x rate range is 1.2mV with no monotone trend, i.e. the
* answer is rate-INDEPENDENT here, not merely "slow enough". The superseded
* `dc` record -- the zero-rate limit of the same experiment -- reads 0.399743V
* at this corner, 2.1mV above the 8ms ramp; that residual is the `dc` sweep's
* own 20mV grid interpolation, and the whole 2.4mV span sits against a 300mV
* ratified bound. The 8ms ramp is what the matrix runs: it is inside the
* rate-independent window and it costs 22s per corner where the 60ms ramp
* cost 471s (both measured on this host).
* SUPPLY AXIS, unchanged in meaning: VIN starts at 3.63V for every corner
* (exactly as the `dc` sweep's own first point did, independently of 'vsup'),
* and the corner runner's 'vsup' still sets EN's rail. So the supply axis
* still varies per corner point, and it still does so only through EN.
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
I_LOAD 50mA after the loop is up (ratified "Dropout @ 50mA" row)
VVIN cold-started to 3.63V then ramped down to 1.5V inside one uic transient (#178)
EN = 'vsup' as an edge at 100us (corner runner); VREF = 1.2V placeholder} -700 -650 0 0 0.3 0.3 {}

* ---- VIN: cold start to the sweep's own 3.63V top, then the down-ramp ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value="PWL(0 0 100u 3.63 6m 3.63 14m 1.5)" savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

* ---- EN (the corner runner's supply, as an edge -- issue #178) ----
C {devices/vsource.sym} -400 -300 0 0 {name=VEN value="PULSE(0 'vsup' 100u 1u 1u 100 200)" savecurrent=true}
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

* ---- load: fixed 50mA (the ratified "Dropout @ 50 mA" row's own test point) ----
C {devices/isource.sym} 900 -300 0 0 {name=ILOAD value="PWL(0 0 2.5m 0 2.6m 50m)"}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {I_LOAD: fixed 50mA -- the ratified "Dropout @ 50 mA" row's test point} 940 -300 0 0 0.2 0.2 {}
