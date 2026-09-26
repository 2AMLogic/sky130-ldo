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
* Initial-condition seed (issue #179; contract in sim/README.md, #171).
* Every `ac` analysis linearizes around an operating point ngspice
* computes for itself, and it recomputes that point from scratch for each
* `ac` command -- a preceding `op`/`tran` in the same .control block does
* NOT carry over (measured on sim/loop-gain's seven-point deck: adding a
* leading `op` produces an eighth independent Newton solve, not a reuse of
* the first). So an unseeded deck hands both of this bench's bias points
* to an unconstrained Newton start, the hazard issue #164 / PR #170
* characterized and #171 turned into a repo-wide contract.
*
* The seed below is the contract's second shape ("an .ic-seeded .op":
* constrain every node the loop needs to disambiguate, solve, then
* release) written with the card that an `.op`/`.ac` operating-point solve
* actually honours. ngspice applies `.ic` only to the TRANSIENT operating
* point, so an `.ic` card is inert in an ac-only deck; `.nodeset` is the
* same constrain-then-release mechanism applied to every operating-point
* solve the deck performs, including the one inside each `ac`, so one card
* covers both the 1mA point and the `alter`-reached 50mA point.
*
* WHICH nodes are seeded, and why only three. The card constrains
* VOUT = 1.8 and the two feedback-divider taps FB = 1.2 / N_FBB = 0.6 --
* the nodes that say WHICH BRANCH the solve is on -- and nothing else.
* Every remaining node (EA_OUT, EA_CZ, EA_TAIL, EA_D1/D2, BIASP, NB, SS)
* is left to the solver, because their values are set by the operating
* CURRENT and so differ between the 1mA and 50mA points, while a .nodeset
* card is one static card applied to both. Starting from
* sim/ic-screen-125c-b's eleven-node seed (its 125C/50mA values) and
* cutting back was measured over the full 45-corner matrix, not assumed:
*
*   - no seed at all (the pre-#179 shape): 2 of 45 corners raise a solver
*     diagnostic, and ss/-40C/3.63V's 1mA `ac` linearizes about a
*     NON-regulating state (VOUT = 3.633 V = VIN, pass device full on),
*     reporting 0.017 dB of PSRR at 1kHz and 5.20 dB at 100kHz -- numbers
*     that are in the record and are not PSRR at all.
*   - eleven-node seed: 6 of 45 diagnostics and that corner STILL
*     non-regulating (the 50mA gate voltage is simply wrong at 1mA).
*   - three-node seed (this card): 2 of 45 diagnostics -- the unseeded
*     count -- and NO non-regulating point. ss/-40C/3.63V comes back to
*     VOUT = 1.8004 V, 25.66 dB at 1kHz and 31.88 dB at 100kHz.
*   - six-node seed (the three plus SS/NB/BIASP): 1 of 45 diagnostics but
*     the non-regulating corner returns. Fewer diagnostics is not the
*     objective; landing on the regulating branch is.
*
* Everywhere else the seeded and unseeded numbers agree to five or six
* digits. Per-corner tables and a reproduction recipe: sim/README.md's
* "#179". The seed is a basin hint, not a forced answer --
* ngspice releases it and re-converges, so the recorded operating point
* is the solver's. experiment.json records v(vout) from an `op` taken at
* each load point (same circuit state, same seed, same solver => the same
* solve the following `ac` linearizes around) so the evidence that each
* point landed on the regulating branch is in the record itself.
*
* What this does NOT do: it does not clear the #171 solver-diagnostic
* FAIL gate -- a minority of corners still raise `singular matrix` on the
* resistor-string nodes. See sim/README.md's "#179" section, which records
* the per-corner seeded/unseeded comparison and says plainly that the
* residue is a separate, unsolved defect rather than something suppressed.
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

* ---- initial-condition seed for both `ac` points (#179, contract #171) ----
C {devices/code_shown.sym} -700 -100 0 0 {name=IC_SEED only_toplevel=false value=".nodeset v(VOUT)=1.8 v(xldo.FB)=1.2 v(xldo.N_FBB)=0.6"}
T {.nodeset, not .ic: ngspice honours .ic only for the TRANSIENT operating
point, so .ic is inert in an ac-only deck. .nodeset is the same
constrain-then-release seed applied to every operating-point solve --
including the one each `ac` performs for itself -- so one card covers both
load points. Only the three branch-defining nodes are seeded; every
current-dependent node is left to the solver, because one static card
cannot be right at both 1mA and 50mA. See the header for the measured
basis and sim/README.md's "Initial-condition contract (issue #171)".} -660 -100 0 0 0.2 0.2 {}
