v {xschem version=3.4.7 file_version=1.2
* sky130-ldo enable / shutdown testbench (issue #65).
*
* Exercises the disabled state of the LDO core
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym) -- the EN-gated clamp
* family M_ENP / M_ENP2 / M_ENP3 / M_ENP4 / M_ENP5 and the M_ENN / M_ENN2
* pseudo-ground switches described in design/README.md's
* "Enable/shutdown (also revised after simulation)" -- against
* spec/target-spec.md's DRAFT "Enable / shutdown" row:
*
*   "shutdown Iq < 3 uA worst corner; disabled output = pass device fully
*    off, no active discharge; Vin->Vout leakage <= 1 uA"
*
* That row is DRAFT (issue #1 not yet ratified); the bounds in
* experiment.json cite its own two numbers (3 uA, 1 uA) directly rather
* than inventing a final limit.
*
* ---------------------------------------------------------------------
* The three clauses, and how each is actually measured
* ---------------------------------------------------------------------
* 1. "shutdown Iq < 3 uA worst corner" is measured TWICE, on purpose:
*    once as a DC operating point with EN held at 0 (the static disabled
*    state), and once 1.5-2.5 ms after a falling EN edge that the block
*    reached by starting up and regulating first. The second is the one
*    that can catch a block which has a clean disabled SOLUTION but does
*    not actually reach it from an enabled one -- a DC-only check cannot
*    tell those apart, because it never visits the enabled state at all.
*
* 2. "Vin->Vout leakage <= 1 uA" is measured with EN = 0 and VOUT FORCED
*    to 0 V through the VFORCE/RFORCE branch below. Forcing the output to
*    ground is what isolates the clause: at VOUT = 0 the block's own
*    ~3.1 MOhm feedback divider carries no current, so the current the
*    forcing source collects is the VIN->VOUT path through the (off) pass
*    device and its junctions, and nothing else.
*
* 3. "disabled output = pass device fully off, no active discharge" is
*    measured in the transient leg, as the residual VOUT 2 ms after the
*    disable edge with NO external load: the only discharge path a
*    correctly disabled block has is the feedback divider, whose
*    R_div x C_OUT time constant is seconds, so the output should barely
*    move. An active pull-down would collapse it in microseconds. That
*    makes the clause checkable against a number the spec already states
*    (the DRAFT Output row's +-2% window) instead of an invented
*    discharge-current threshold. The static counterpart -- how much
*    current the disabled block draws from an output held at 1.8 V -- is
*    also measured, and reported rather than bounded, because separating
*    "the divider's inherent preload" from "an active discharge" by DC
*    current alone would need a divider value this experiment does not
*    independently measure.
*
* ---------------------------------------------------------------------
* How EN carries two different values at once
* ---------------------------------------------------------------------
* VEN is written as `dc 0 pwl(0 0 100u 0 101u 'vsup' ... )`: ngspice uses
* the DC value for `op`/`dc` analyses and the time-dependent function for
* `tran` (including a transient's own t = 0 operating point). So the same
* source gives the three `op` legs a statically-disabled block (EN = 0),
* and gives the transient leg a full enable -> shutdown CYCLE: EN is 0 at
* t = 0, rises at t = 100 us, the block starts up and regulates, and EN
* falls again at t = 2 ms.
*
* The rising edge is deliberate rather than incidental. An earlier draft of
* this testbench started the transient already enabled (EN = 'vsup' at
* t = 0) and disabled it at 0.5 ms, which made the leg depend on ngspice's
* t = 0 DC operating point being the REGULATING one -- and at the `ff`/`sf`
* 125 C corners it is not (design/README.md, "What the full 45-point
* PVT + Monte Carlo campaign's FAILs actually mean", mechanism 1: the
* thermal clamp nuisance-trips there, issue #69). That draft therefore
* failed those corners for a reason that has nothing to do with the enable/
* shutdown path this experiment is about. Ramping EN up from a disabled
* start instead lets the block reach regulation the same way sim/startup
* shows it does, so a failure of vout_pre_disable_v below now means the
* block genuinely did not regulate before the disable edge.
*
* vout_pre_disable_v (VOUT at t = 1.9 ms, just before the falling edge) is
* what keeps the two post-edge measurements from passing vacuously: if the
* block had not actually been enabled and regulating, that measurement
* lands far from the regulation window and the leg fails loudly instead of
* silently measuring a block that was never on.
*
* VOUT forcing branch, same convention as sim/current-limit: VFORCE (node
* VF) --> RFORCE (VOUT). RFORCE starts at 1e12 (branch effectively absent)
* and the deck `alter`s it to 1 mOhm for the forced legs. i(vforce) is
* positive when current flows from VOUT into the source, i.e. when the
* block DELIVERS current into the forced node -- which is the sense a
* VIN->VOUT leakage has, and the opposite of the sense the divider's
* preload has.
*
* VREF is a fixed 1.2 V placeholder per design/README.md's "VREF interface
* caveat, and the reference common mode" -- matching the 1:2 feedback
* divider (VOUT = 1.5 x VREF). C_OUT (1 uF) + R_ESR (10 mOhm) are the same
* representative point inside DR-002's *proposed* window that
* sim/load-transient uses.
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
T {enable / shutdown testbench -- exercises design/ldo_3v3in_1v8out.sch (#14/#22/#25/#29)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
VIN = 'vsup'; EN = dc 0 for the `op` legs, PWL 0 -> 'vsup' at 100us -> 0 at 2ms for the tran leg
VFORCE + RFORCE force VOUT to 0V (leakage) and to 1.8V (disabled-state load)
DRAFT "Enable / shutdown" row: shutdown Iq < 3uA, Vin->Vout leakage <= 1uA, no active discharge} -700 -750 0 0 0.3 0.3 {}

* ---- VIN (tied to the corner runner's supply) ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

* ---- EN: DC 0 for the static legs, a full enable->shutdown cycle for the tran leg ----
C {devices/vsource.sym} -400 -300 0 0 {name=VEN value="dc 0 pwl(0 0 100u 0 101u 'vsup' 2m 'vsup' 2.001m 0 10 0)" savecurrent=true}
C {devices/lab_pin.sym} -400 -330 0 0 {name=p3 lab=EN}
C {devices/lab_pin.sym} -400 -270 0 0 {name=p4 lab=0}
T {EN carries BOTH a DC value (0 -- used by the three `op` legs, which
measure the static disabled state) and a PWL (used by the transient leg,
which starts DISABLED at t = 0, is enabled at t = 100us, regulates, and is
disabled again by the falling edge at t = 2ms). The transient leg is what
proves the block REACHES the disabled state from a live one, not merely
that such a state exists -- and starting it disabled means it reaches the
enabled state the same way sim/startup does, instead of depending on the
t = 0 DC solve landing on the regulating branch (which it does not at the
ff/sf 125C corners -- design/README.md mechanism 1, issue #69).} -360 -300 0 0 0.2 0.2 {}

* ---- VREF (fixed placeholder, see design/README.md interface caveat) ----
C {devices/vsource.sym} -200 -300 0 0 {name=VVREF value=1.2 savecurrent=true}
C {devices/lab_pin.sym} -200 -330 0 0 {name=p5 lab=VREF}
C {devices/lab_pin.sym} -200 -270 0 0 {name=p6 lab=0}

* ---- DUT: the LDO core regulation loop + EN-gated shutdown path ----
C {design/ldo_3v3in_1v8out.sym} 200 -300 0 0 {name=xldo}
C {devices/lab_pin.sym} 50 -320 0 0 {name=p7 lab=VREF}
C {devices/lab_pin.sym} 50 -300 0 0 {name=p8 lab=EN}
C {devices/lab_pin.sym} 50 -280 0 0 {name=p9 lab=VIN}
C {devices/lab_pin.sym} 350 -320 0 0 {name=p10 lab=VOUT}

* ---- output network: C_OUT + R_ESR (DR-002 proposed representative point) ----
C {devices/capa.sym} 600 -400 0 0 {name=COUT m=1 value=1u footprint=1206 device="ceramic capacitor (DR-002 proposed nominal)"}
C {devices/lab_pin.sym} 600 -430 0 0 {name=p11 lab=VOUT}
C {devices/lab_pin.sym} 600 -370 0 0 {name=p12 lab=VESR}
C {devices/res.sym} 600 -250 0 0 {name=RESR value=10m m=1}
C {devices/lab_pin.sym} 600 -280 0 0 {name=p13 lab=VESR}
C {devices/lab_pin.sym} 600 -220 0 0 {name=p14 lab=0}
T {C_OUT is load-bearing for the no-active-discharge check: with the block
disabled and no external load, VOUT decays only through the ~3.1MOhm
feedback divider, i.e. with a multi-second time constant. Any active
pull-down would empty this capacitor in microseconds instead.} 640 -300 0 0 0.2 0.2 {}

* ---- load: none (0mA) -- the disabled-state claims are all no-load claims ----
C {devices/res.sym} 900 -300 0 0 {name=RLOAD value=1e12 m=1}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {R_LOAD: 1e12 ("0mA"). An external load would discharge C_OUT on its own
and mask exactly what the no-active-discharge clause is about, so this
experiment holds the load at zero throughout and lets the block's own
feedback divider be the only preload.} 940 -300 0 0 0.2 0.2 {}

* ---- forcing branch: VFORCE + RFORCE (absent until the deck `alter`s RFORCE) ----
C {devices/res.sym} 1200 -300 0 0 {name=RFORCE value=1e12 m=1}
C {devices/lab_pin.sym} 1200 -330 0 0 {name=p17 lab=VOUT}
C {devices/lab_pin.sym} 1200 -270 0 0 {name=p18 lab=VF}
C {devices/vsource.sym} 1200 -180 0 0 {name=VFORCE value=0 savecurrent=true}
C {devices/lab_pin.sym} 1200 -210 0 0 {name=p19 lab=VF}
C {devices/lab_pin.sym} 1200 -150 0 0 {name=p20 lab=0}
T {RFORCE starts at 1e12 (branch effectively absent, so the transient leg
and the first `op` leg see a free-floating output) and the deck `alter`s it
to 1m for the two forced legs: VOUT held at 0V (the Vin->Vout leakage
measurement) and then at 1.8V (the disabled-state load at the nominal
output). i(vforce) > 0 means the block is delivering current into the
forced node.} 1250 -230 0 0 0.2 0.2 {}
