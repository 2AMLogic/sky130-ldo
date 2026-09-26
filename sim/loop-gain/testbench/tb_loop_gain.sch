v {xschem version=3.4.7 file_version=1.2
* sky130-ldo loop-gain / phase-margin testbench (issue #25).
*
* Exercises design/ldo_3v3in_1v8out.sch (the issue-#25 current-mirror-OTA
* revision of the #14/#22 core loop), instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym, against
* spec/target-spec.md's ratified "Stability" row: "stable 0-50 mA over the
* ratified C_out/ESR window; PM >= 45 deg, GM >= 10 dB worst corner". That
* row is ratified by issue #1 / DR-006, and the C_out/ESR window it
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
* ---------------------------------------------------------------------
* Initial-condition seed (issue #179; contract in sim/README.md, #171)
* ---------------------------------------------------------------------
* Every `ac` analysis linearizes around an operating point that ngspice
* computes for itself, and it recomputes that point from scratch for each
* `ac` command -- a preceding `op`/`tran` in the same .control block does
* NOT carry over (measured: this deck's seven `ac` points each start their
* own Newton solve; adding a leading `op` produces an eighth, not a reuse
* of the first). So an unseeded deck hands all seven bias points to an
* unconstrained Newton start, which is exactly the hazard issue #164 /
* PR #170 characterized and issue #171 turned into a repo-wide contract.
*
* The seed below is the contract's second shape ("an .ic-seeded .op":
* constrain every node the loop needs to disambiguate, solve, then
* release) written with the card that an `.op`/`.ac` operating-point solve
* actually honours. ngspice applies `.ic` only to the TRANSIENT operating
* point, so an `.ic` card is inert in an ac-only deck -- `.nodeset` is the
* same constrain-then-release mechanism applied to every operating-point
* solve the deck performs, including the one inside each `ac`. It
* therefore covers all seven `alter`-reached points from a single card,
* with no per-point seeding required.
*
* WHICH nodes are seeded, and why only three. The card constrains
* VOUT = 1.8 and the two feedback-divider taps FB = 1.2 / N_FBB = 0.6 --
* the nodes that say WHICH BRANCH the solve is on -- and nothing else.
* Every remaining node of the loop (EA_OUT, EA_CZ, EA_TAIL, EA_D1/D2,
* BIASP, NB, SS) is left to the solver, because their values are set by
* the operating CURRENT and therefore differ between this deck's 0 mA,
* 1 mA and 50 mA points, while a .nodeset card is a single static card
* applied to all seven. Starting from sim/ic-screen-125c-b's eleven-node
* seed (its 125 C / 50 mA values) and cutting back was not a style
* preference -- it was measured, on this deck, at the corners that matter:
*
*   - no seed at all (the pre-#179 shape): 13 of 45 corners raise a solver
*     diagnostic, and THREE corners linearize an `ac` about a state where
*     the pass device is simply full on -- ff/-40C/3.63V and ff/27C/3.30V
*     at 0 mA (VOUT = 3.640 V / 3.287 V) and ss/-40C/3.63V at 1 mA
*     (VOUT = 3.633 V) -- which makes six of this deck's phase margins
*     unmeasurable.
*   - eleven-node seed (ic-screen's own values, i.e. its 125 C / 50 mA
*     operating point): 9 of 45 diagnostics and still two non-regulating
*     corners. It repairs ff/-40C/3.63V and breaks nothing new here, but in
*     the sibling sim/psrr-dc deck it leaves ss/-40C/3.63V reporting
*     0.017 dB of PSRR at 1 kHz instead of 25.7 dB.
*   - three-node seed (this card): 3 of 45 diagnostics -- a factor of four
*     better than no seed -- and NO non-regulating point anywhere in either
*     bench. All six previously-unmeasurable phase margins come back
*     (74.39 deg at ss/-40C/3.63V's 1 mA point; 20.58/55.58 deg at
*     ff/27C/3.30V's 0 mA points; 18.54/46.87 deg at ff/-40C/3.63V's).
*   - six-node seed (the three plus SS/NB/BIASP): 2 of 45 diagnostics, one
*     fewer than this card, but two non-regulating corners come back. Fewer
*     diagnostics is not the objective; landing on the regulating branch is.
*
* Everywhere else the seeded and unseeded numbers agree to five or six
* digits -- the unconstrained solve was already on the right branch at 42 of
* 45 corners. The contract exists because "usually" is not citable.
* Per-corner tables and a reproduction recipe: sim/README.md's "#179".
*
* The seed is a basin hint, not a forced answer -- ngspice releases it and
* re-converges, so the recorded operating point is the solver's, not the
* seed's. experiment.json records v(vout) from an `op` taken at each of
* the seven points (same circuit state, same seed, same solver => the same
* solve the following `ac` linearizes around) so the evidence that each
* point landed on the regulating branch is in the record itself, not just
* in this comment.
*
* What this does NOT do: it does not clear the #171 solver-diagnostic FAIL
* gate. A minority of corners still raise `singular matrix` on the
* resistor-string nodes -- see sim/README.md's "#179" section, which
* records the per-corner seeded/unseeded comparison and says plainly that
* the residue is a separate, unsolved defect rather than something this
* testbench suppresses.
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
points of the ratified Stability row's 0-50mA range.} 940 -300 0 0 0.2 0.2 {}

* ---- initial-condition seed for every `ac` point (#179, contract #171) ----
C {devices/code_shown.sym} -700 -100 0 0 {name=IC_SEED only_toplevel=false value=".nodeset v(VOUT)=1.8 v(xldo.FB)=1.2 v(xldo.N_FBB)=0.6"}
T {.nodeset, not .ic: ngspice honours .ic only for the TRANSIENT operating
point, so .ic is inert in an ac-only deck. .nodeset is the same
constrain-then-release seed applied to every operating-point solve --
including the one each `ac` performs for itself -- so one card covers all
seven `alter`-reached bias points. Only the three branch-defining nodes
are seeded; every current-dependent node is left to the solver, because
one static card cannot be right at 0mA, 1mA and 50mA at once. See the
header for the measured basis and sim/README.md's "Initial-condition
contract (issue #171)".} -660 -100 0 0 0.2 0.2 {}
