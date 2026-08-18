v {xschem version=3.4.7 file_version=1.2
* sky130-ldo loop-gain / phase-margin testbench (issue #25).
*
* Exercises design/ldo_3v3in_1v8out.sch (the issue-#25 current-mirror-OTA
* revision of the #14/#22 core loop), instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym, against
* spec/target-spec.md's DRAFT "Stability" row: "stable 0-50 mA over the
* ratified C_out/ESR window; PM >= 45 deg, GM >= 10 dB worst corner". That
* row is DRAFT (issue #1 not yet ratified) and the C_out/ESR window it
* refers to is DR-002's *proposed* one (C_eff 0.33-4.7 uF, ESR 0-500 mOhm,
* no minimum ESR) -- the bounds in experiment.json cite those directly
* rather than inventing a final limit.
*
* ---------------------------------------------------------------------
* How the loop gain is measured (the load-bearing part of this testbench)
* ---------------------------------------------------------------------
* This LDO's feedback divider is INTERNAL: the block's only ports are
* VOUT / VREF / EN / VIN, so there is no node a testbench can cut to
* insert the usual series voltage-injection source. Cutting VOUT does not
* break the loop either -- the pass device drives, and the divider senses,
* the same pin.
*
* So this testbench uses closed-loop injection at the amplifier's other
* input instead, and transforms the measured closed-loop response back
* into the loop gain:
*
*   - VREF carries a 1 V AC stimulus on top of its DC placeholder value.
*   - The error amplifier compares FB against VREF, so with
*     VOUT = A * (VREF - FB) and FB = beta * VOUT, the measured
*     X(s) = FB/VREF = T/(1+T), where T = beta*A is the loop gain.
*   - Therefore T = X/(1-X), which is what experiment.json's measurement
*     expressions evaluate. Phase margin is 180 deg + phase(T) at the
*     first |T| = 1 crossing; gain margin is -20*log10|T| where the phase
*     first reaches -180 deg.
*   - FB is read hierarchically as v(xldo.fb): the transform then makes no
*     assumption at all about the divider ratio or its frequency response,
*     because the *measured* FB already contains both.
*
* Known approximation, stated rather than hidden: the transform is exact
* only if a disturbance injected at VREF traverses the same forward path
* as one injected at FB. In this amplifier the FB side reaches EA_OUT
* through one current mirror (M_MIR1/M_MIR2) and the VREF side through two
* (M_MIR3/M_MIR4 -> PB -> M_MIRP1/M_MIRP2), so the two paths differ by the
* extra mirror's pole. Both mirror nodes are diode-loaded and sit in the
* MHz decade, i.e. two to three decades above every crossover this
* testbench measures, so the error at crossover is a fraction of a degree.
* A future testbench that wants an assumption-free number would need a
* loop-break port on the block itself, which is a change to the DUT's
* interface and therefore out of this issue's scope.
*
* ---------------------------------------------------------------------
* Why one testbench covers seven (C_out, ESR, load) points
* ---------------------------------------------------------------------
* The DR-002 window is a *window*, not a point, and the whole question the
* record leaves open is whether phase margin holds across it. The corner
* runner already owns the process/temperature/supply axes, so this
* experiment's deck walks the C_out/ESR/load axis itself, inside one deck,
* with ngspice `alter` between AC sweeps (see experiment.json "analyses").
* The seven points are the window's corners plus its nominal:
*
*   1. C_out 0.33 uF, ESR 10 mOhm, 50 mA  <- DR-002's low-C_eff corner;
*                                            the one that broke the
*                                            candidate fix screened in #22
*   2. C_out 0.33 uF, ESR 10 mOhm,  1 mA
*   3. C_out 0.33 uF, ESR 10 mOhm,  0 mA  (divider preload only)
*   4. C_out 4.7 uF,  ESR 10 mOhm, 50 mA
*   5. C_out 4.7 uF,  ESR 10 mOhm,  1 mA
*   6. C_out 4.7 uF,  ESR 10 mOhm,  0 mA
*   7. C_out 0.33 uF, ESR 500 mOhm, 50 mA <- the window's ESR ceiling
*
* ESR sits at 10 mOhm for points 1-6 on purpose: DR-002 takes a
* "no minimum ESR, ceramic-stable" posture, so the low-ESR end is the
* stressing end (no ESR zero to help), and point 7 exists to show the
* ceiling end is not the binding one.
*
* "0 mA" is modelled as R_LOAD = 1e12 rather than by deleting the resistor,
* so the same element can be walked by `alter` across all seven points.
* The block's feedback divider is its own inherent preload, per
* spec/target-spec.md's note on the Load-regulation row.
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
T {loop-gain testbench -- exercises design/ldo_3v3in_1v8out.sch (#14/#22/#25)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
VREF = DC 1.2V + AC 1V (the injection point); VIN/EN = DC 'vsup' only
loop gain T = X/(1-X) with X = v(xldo.fb); PM = 180 + phase(T) at |T| = 1
C_OUT / R_ESR / R_LOAD are walked over DR-002's window by `alter` in the deck} -700 -750 0 0 0.3 0.3 {}

* ---- VIN (DC only -- the AC stimulus goes into VREF, not the supply) ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

* ---- EN (DC only, tied to the corner runner's supply) ----
C {devices/vsource.sym} -400 -300 0 0 {name=VEN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -400 -330 0 0 {name=p3 lab=EN}
C {devices/lab_pin.sym} -400 -270 0 0 {name=p4 lab=0}

* ---- VREF: DC placeholder + the 1V AC injection this testbench measures ----
C {devices/vsource.sym} -200 -300 0 0 {name=VVREF value="DC 1.2 AC 1" savecurrent=true}
C {devices/lab_pin.sym} -200 -330 0 0 {name=p5 lab=VREF}
C {devices/lab_pin.sym} -200 -270 0 0 {name=p6 lab=0}
T {VREF: 1.2V DC placeholder per design/README.md's "VREF interface caveat"
(matching the 1:2 divider issue #22 revised the schematic to, VOUT = 1.5 x VREF),
plus AC 1 -- the small-signal injection this experiment transforms into loop gain} -160 -300 0 0 0.2 0.2 {}

* ---- DUT: the LDO core regulation loop ----
C {design/ldo_3v3in_1v8out.sym} 200 -300 0 0 {name=xldo}
C {devices/lab_pin.sym} 50 -320 0 0 {name=p7 lab=VREF}
C {devices/lab_pin.sym} 50 -300 0 0 {name=p8 lab=EN}
C {devices/lab_pin.sym} 50 -280 0 0 {name=p9 lab=VIN}
C {devices/lab_pin.sym} 350 -320 0 0 {name=p10 lab=VOUT}
T {xldo: instance name is load-bearing -- the deck reads the internal
feedback node as v(xldo.fb). Renaming this instance breaks every
measurement in experiment.json.} 240 -300 0 0 0.2 0.2 {}

* ---- output network: C_OUT + R_ESR, walked across DR-002's window ----
C {devices/capa.sym} 600 -400 0 0 {name=COUT m=1 value=0.33u footprint=1206 device="ceramic capacitor (DR-002 low-C_eff corner)"}
C {devices/lab_pin.sym} 600 -430 0 0 {name=p11 lab=VOUT}
C {devices/lab_pin.sym} 600 -370 0 0 {name=p12 lab=VESR}
C {devices/res.sym} 600 -250 0 0 {name=RESR value=10m m=1}
C {devices/lab_pin.sym} 600 -280 0 0 {name=p13 lab=VESR}
C {devices/lab_pin.sym} 600 -220 0 0 {name=p14 lab=0}
T {C_OUT / R_ESR start at DR-002's low-C_eff, low-ESR corner (0.33uF, 10mOhm)
-- the corner DR-002 itself flags as the risky one and the corner the
candidate fix screened during #22 oscillated at. The deck then `alter`s both
across the rest of the proposed window.} 640 -300 0 0 0.2 0.2 {}

* ---- load: walked 50mA -> 1mA -> 0mA by `alter` ----
C {devices/res.sym} 900 -300 0 0 {name=RLOAD value=36 m=1}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {R_LOAD: 36 Ohm (~50mA) at the first analysis point; the deck `alter`s it
to 1.8k (~1mA) and 1e12 ("0mA", divider preload only) for the light-load
points of the DRAFT Stability row's 0-50mA range.} 940 -300 0 0 0.2 0.2 {}
