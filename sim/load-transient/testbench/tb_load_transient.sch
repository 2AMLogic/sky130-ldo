v {xschem version=3.4.7 file_version=1.2
* sky130-ldo load-transient testbench (issue #18).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym -- see that symbol's own
* header for how it was generated) with a load-current step, per
* spec/target-spec.md's ratified "Load transient" row: "1<->50 mA step, ~1us
* edges: peak excursion <=150mV, recover to +-1% in <=20us, over the
* ratified C_out/ESR window". That row is ratified by issue #1 / DR-006,
* and the C_out/ESR window itself is spec/decision-records/DR-002
* (status: ratified, 0.33-4.7uF / 0-500mOhm, no minimum ESR).
*
* VIN/EN share the corner runner's 'vsup' parameter (EN is active-high,
* full-rail 0/VIN per design/README.md, so tying it to VIN keeps the DUT
* enabled across the whole PVT matrix). VREF is a fixed 1.2V placeholder
* per design/README.md's "VREF interface caveat" -- matching the 1:2
* feedback-divider ratio issue #22 revised the schematic to (VOUT = 1.5 x
* VREF; #22's own screening data shows the earlier 0.6V/2:1 convention
* does not regulate against this schematic's amplifier output-swing
* ceiling -- see design/README.md's "VREF interface caveat, and the
* reference common mode" section). No reference-generator block exists
* yet.
*
* I_LOAD steps 1mA -> 50mA -> 1mA (PULSE, 1us edges) at VOUT, modelling the
* ratified spec's load-transient stimulus literally. C_OUT (4.7uF, issue
* #119) + R_ESR (10mOhm, a ceramic-representative point inside DR-002's
* ratified 0-500mOhm window, not a sweep of that window -- full C_out/ESR
* corner-sweep is follow-on scope, e.g. #19) sit at VOUT as the external
* output network. C_out moved from the superseded record's 1uF (DR-002's
* recommended nominal) to 4.7uF (DR-002's own ratified window ceiling,
* still 0-500mOhm ESR -- not a new number, not outside the window) in
* issue #119, specifically to address the row's peak-excursion clause:
* undershoot_v/overshoot_v are charge-limited (Q=C*dV against the loop's
* finite large-signal response time), so a larger in-window C_out reduces
* peak excursion roughly in proportion. See design/README.md's "#119"
* section and spec/decision-records/DR-002's append for the full
* per-corner evidence and for the row's OTHER clause (recovery time),
* which this C_out choice does not and cannot fix -- see that writeup.
*
* Known-immature-design caveat (see design/README.md "Known gaps"): this
* schematic's compensation (C_COMP/C_CL) remains an unsized placeholder,
* and the error amplifier still has a light-load/high-VIN output-swing
* ceiling ("Known open item" in design/README.md) even though issue #22
* already added the current-limit and soft-start protection circuitry, so
* this testbench recording a FAIL against the ratified peak-excursion bound
* at some corners is an honest, expected verification finding at this
* design stage, not a harness defect. CLAUDE.md: "Verification is the
* product" -- a testbench that surfaces a real immaturity is doing its
* job.
*
* Initial-condition contract (issue #171, applied by issue #180). This
* schematic carries an eleven-node `.ic` card (IC_SEED below) and
* experiment.json's transient is deliberately NOT `uic`: the operating-point
* solve that seeds the transient is constrained to the loop's intended
* regulating branch and then released from it. That is #164's variant-B
* shape (PR #170), the second of the two shapes sim/README.md's
* "Initial-condition contract (issue #171)" section accepts, and the same
* shape sim/ic-screen-125c-b uses. Before #180 this bench ran `tran 200n 3m`
* with no seed at all, so ngspice solved an unconstrained, loop-closed `.op`
* first: 23 of the 45 corner logs in the superseded
* 20260825-081255-4cb27f8 record carry a `singular matrix` /
* `gmin stepping failed` diagnostic from exactly that solve.
*
* Why variant B rather than `uic` + an EN edge here: this bench measures a
* LOAD step at an already-regulating condition (the PULSE is on I_LOAD, not
* on EN), and both its clauses are referred to the pre-step steady state.
* An EN-edge preamble would shift the deck's whole time axis (and with it
* every meas timestamp) and would leave C_OUT's pre-step charge state
* dependent on the soft-start ramp -- which #119's charge-limited
* peak-excursion finding (Q=C*dV, see experiment.json's claim) makes a
* variable this bench must hold fixed, not perturb. The `.ic` seed leaves
* the 1 mA pre-step operating point, the 1.000 ms / 2.001 ms step edges and
* the 3 ms span exactly where they were.
*
* Where the .ic values come from (not invented): a local probe of THIS
* circuit cold-started through its own EN edge (VEN as a PULSE, `tran 200n
* 1m uic`), sampled at t = 0.9 ms -- i.e. settled at the pre-step 1 mA load
* and before the 1.000 ms step -- at tt / 27 C / VIN = 3.30 V:
*   VOUT 1.80086, FB 1.20076, N_FBB 0.600477, EA_OUT 2.39066, EA_CZ 2.38961,
*   SS 3.27301, BIASP 2.23628, NB 0.864081, EA_TAIL 2.53164, EA_D1 0.887207,
*   EA_D2 0.887896 V
* rounded below. That state is realizable by the passive divider's own
* algebra (FB = VOUT/1.5, N_FBB = FB/2), which is the check #164 showed the
* unconstrained solve can violate. Nodes whose regulating value tracks VIN
* (the pass gate EA_OUT/EA_CZ, the PMOS bias rail BIASP, the amplifier tail
* EA_TAIL, the soft-start node SS) are written relative to 'vsup' so the
* seed stays realizable at every supply on the axis rather than sitting
* above VIN at 2.97 V; the ground-referenced ones (VOUT, the divider taps,
* NB, EA_D1/EA_D2) are absolute. EA_CZ is seeded at EA_OUT's value because
* XR_CZ ties them with no DC current through C_COMP -- they are the same
* node at DC, and the 1 mV the probe shows between them is transient
* residue.
*
* Deliberately NOT in this schematic (the corner runner injects them, so
* one schematic serves the whole PVT matrix): the .lib model corner
* include, .temp, and the .control analysis/measurement block. VIN's
* numeric value comes from 'vsup', same convention as
* sim/pdk-smoke/testbench/tb_pdk_smoke.sch.
}
G {}
K {}
V {}
S {}
E {}
T {load-transient testbench -- exercises design/ldo_3v3in_1v8out.sch (#14)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
VIN/EN = 'vsup' (corner runner); VREF = 1.2V placeholder (see design/README.md)
I_LOAD: PULSE 1mA<->50mA, 1us edges (spec/target-spec.md ratified "Load transient" row)
C_OUT/R_ESR: DR-002 ratified window's 4.7uF ceiling / representative ESR point (issue #119; see design/README.md)} -700 -650 0 0 0.3 0.3 {}

* ---- VIN / EN (tied to the corner runner's supply) ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

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

* ---- output network: C_OUT + R_ESR (DR-002 ratified window, C_out at the
* window's own ceiling -- issue #119, see this file's header comment) ----
C {devices/capa.sym} 600 -400 0 0 {name=COUT m=1 value=4.7u footprint=1210 device="ceramic capacitor (DR-002 ratified window ceiling -- issue #119)"}
C {devices/lab_pin.sym} 600 -430 0 0 {name=p11 lab=VOUT}
C {devices/lab_pin.sym} 600 -370 0 0 {name=p12 lab=VESR}
C {devices/res.sym} 600 -250 0 0 {name=RESR value=10m m=1}
C {devices/lab_pin.sym} 600 -280 0 0 {name=p13 lab=VESR}
C {devices/lab_pin.sym} 600 -220 0 0 {name=p14 lab=0}
T {R_ESR: 10mOhm -- a representative point inside DR-002's ratified
0-500mOhm window (no minimum ESR); not a sweep of the window itself} 640 -300 0 0 0.2 0.2 {}

* ---- load: I_LOAD steps 1mA -> 50mA -> 1mA, 1us edges ----
C {devices/isource.sym} 900 -300 0 0 {name=ILOAD value="PULSE(1m 50m 1m 1u 1u 1m 4m)"}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {I_LOAD: PULSE(1m 50m 1m 1u 1u 1m 4m) -- 1mA<->50mA step, 1us edges,
per spec/target-spec.md ratified "Load transient" row} 940 -300 0 0 0.2 0.2 {}

* ---- initial-condition seed (issue #171's contract, applied by #180):
* the eleven-node intended-branch `.ic` that constrains the transient's
* operating-point solve to the loop's regulating branch at the pre-step
* 1 mA load. See this file's header for where each value came from and why
* the supply-referred nodes are written relative to 'vsup'. ----
C {devices/code_shown.sym} -700 -100 0 0 {name=IC_SEED only_toplevel=false value=".ic v(VOUT)=1.8 v(xldo.FB)=1.2 v(xldo.N_FBB)=0.6 v(xldo.EA_OUT)=\{vsup-0.909\} v(xldo.EA_CZ)=\{vsup-0.909\} v(xldo.SS)=\{vsup-0.027\} v(xldo.BIASP)=\{vsup-1.064\} v(xldo.NB)=0.864 v(xldo.EA_TAIL)=\{vsup-0.768\} v(xldo.EA_D1)=0.887 v(xldo.EA_D2)=0.888"}
T {IC_SEED: #164's variant-B contract -- `.ic` constrains the operating-point
solve to the intended regulating branch, and the transient (no `uic`) is
released from it. sim/README.md "Initial-condition contract (issue #171)"} -640 -100 0 0 0.2 0.2 {}
