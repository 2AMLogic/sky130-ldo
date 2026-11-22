v {xschem version=3.4.7 file_version=1.2
* sky130-ldo current-limit testbench (issue #65).
*
* Exercises the current-limit clamp issue #22 added to the LDO core
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym), against
* spec/target-spec.md's ratified "Current limit" row:
*
*   "constant-current (brickwall) clamp, window TBD over PVT; never engages
*    for I_load <= 50 mA; survives continuous Vout = 0 short at Vin_max"
*
* That row is ratified by issue #1 / DR-006 and it deliberately
* carries NO numeric clamp window -- the window is "TBD over PVT". This
* testbench therefore does two different things with the row's two halves,
* and says which is which rather than blurring them:
*
*   - the clauses that DO carry a number ("never engages for I_load <=
*     50 mA", plus the +-2% Output row that "not engaging" means at 50 mA)
*     are checked as bounds in experiment.json;
*   - the clause that does NOT ("window TBD over PVT", and "survives") is
*     MEASURED and reported without a bound, because establishing that
*     window over PVT is what the row asks for at this stage. Inventing a
*     ceiling here would be exactly the "invented settled number" CLAUDE.md
*     forbids. Once #1 ratifies a window these reported values acquire
*     bounds; nothing else about the testbench has to change.
*
* ---------------------------------------------------------------------
* How VOUT is forced (the load-bearing part of this testbench)
* ---------------------------------------------------------------------
* A current limit is a property of the block's OUTPUT CURRENT at a FORCED
* output voltage, so the output cannot be modelled by a load resistor here:
* at any load light enough to regulate, the clamp is inactive by
* construction, and at any load heavy enough to engage it, the operating
* point is set by the clamp itself and not by the sweep. So VOUT is driven
* by a forcing source instead:
*
*   VFORCE (node VF, ground-referred) --> RFORCE (1 mOhm) --> VOUT
*
* RFORCE starts at 1e12 (the forcing branch effectively absent, so the LDO
* regulates into RLOAD normally) and the deck `alter`s it to 1 mOhm for the
* forced legs -- the same "walk one element with `alter` instead of drawing
* several testbenches" convention sim/loop-gain already uses for the
* C_out/ESR window. 1 mOhm rather than 0 Ohm because the current through it
* is what i(vforce) reads, and because a hard short in silicon is a
* milliohm-class path, not an ideal one.
*
* Sign convention, stated because it is easy to get backwards: i(vforce) is
* positive when current flows from VOUT into the forcing source, i.e. when
* the LDO is DELIVERING current into the forced node. That is the sense the
* limit is measured in.
*
* The deck's three legs (see experiment.json "analyses"):
*
*   1. `tran 5u 1.0m uic` with RFORCE open and RLOAD = 36 Ohm (~50 mA, the
*      ratified Load row's ceiling), measured over its last 100 us: the clamp
*      must be fully OFF and the loop must still regulate inside the ratified
*      Output row's +-2% window. This is the "never engages for I_load <=
*      50 mA" clause.
*      This leg was a bare `op` until issue #177. That `op` saw VEN's DC
*      value -- i.e. the block already fully enabled -- and had no `.ic` /
*      `.nodeset` seed and no preceding `uic` transient, so it asked
*      ngspice's Newton solver to find the loop's REGULATING operating point
*      from its own unconstrained guess. sim/README.md's "Initial-condition
*      contract (issue #171)" forbids exactly that (the precedent is #164 /
*      PR #170: an unconstrained `.op` can settle on a numerically spurious
*      branch and not say so). The leg is now a cold-start transient: every
*      node begins at 0 V (`uic`), EN's PWL edge at t = 100 us powers the
*      block up through its own soft-start ramp, and the 50 mA point is read
*      from t = 0.9-1.0 ms, after that ramp has settled (worst case
*      ~0.553 ms) -- so the state measured is one the circuit actually
*      walked to, not one the solver guessed.
*      The `uic` keyword is load-bearing, not belt-and-braces on top of the
*      PWL's 0 V start -- see the VIN/EN block below for the measurement
*      that establishes why.
*   2. `dc vforce 0 -> 1.75` with RFORCE = 1 mOhm and RLOAD open: the DC
*      limit characteristic. Its two end points are the dead short
*      (Vout = 0) and the knee just below the regulation point
*      (Vout = 1.75 V); the pair is what says "brickwall" rather than
*      "foldback" -- a foldback limiter's short-circuit current is well
*      BELOW its knee current, a constant-current clamp's is not.
*   3. `tran ... uic` with the short APPLIED AS AN EVENT and then HELD: RLOAD
*      is back at 36 Ohm and VFORCE is a PWL that sits at 1.8 V until
*      t = 1.0 ms, falls to 0 V in 1 us, and stays at 0 V until the end of
*      the run. Pre-fault the output node therefore sits at the nominal
*      1.8 V with the loop live and delivering into it -- note that RFORCE
*      is still 1 mOhm from leg 2, so the forcing source and the LDO SHARE
*      the 36 Ohm load's ~50 mA and the LDO's own share (isup_pre_short_ma)
*      is a few mA, not 50 mA. What the leg needs is that the fault is
*      applied to a live loop at its regulation target, which it is; the
*      pre-fault current split is documented rather than bounded.
*      This is deliberately a sustained short of a defined duration (2 ms
*      of continuous Vout = 0), not a single sampled point: "survives" is a
*      claim about holding the fault, so a testbench that only sampled the
*      instant of the fault would not exercise it.
*      "at Vin_max" is covered by the corner runner's own supply axis (the
*      3.63 V column of the PVT matrix), not by a hard-coded VIN here.
*
*      The fault time (t = 1.0 ms) is deliberately AFTER the soft-start
*      ramp completes, not at an arbitrary round number: EN itself now
*      rises from a disabled start (see the VIN/EN block below) at
*      t = 100 us, and sim/startup's record (20260825-044139-703a889)
*      measures that ramp completing 0.26-0.45 ms after an enable edge
*      across the PVT matrix (worst case ff_125c_3.63v: ~0.453 ms). Fault
*      time 1.0 ms therefore sits comfortably after even the worst-case
*      ramp (100 us + 0.453 ms =~ 0.553 ms), so the pre-fault leg 3
*      measures (isup_pre_short_ma, vout_short_mv) reflect a block that
*      actually reached regulation before the short, not a t = 0 DC solve
*      that may or may not have landed on the regulating branch (issue #76;
*      the mechanism is the same one issue #65's sim/enable-shutdown and
*      sim/startup testbenches were fixed against, ff/sf 125C thermal-clamp
*      nuisance trip, issue #69).
*
* The transient's clamped current is read from i(vvin), not i(vforce):
* i(vforce) also carries C_OUT's discharge into the short (a ~2 A spike
* lasting microseconds, which is the capacitor's energy and not the pass
* device's current), whereas the supply current is the pass device plus a
* few tens of uA of Iq -- the quantity the "survives" clause is about.
*
* VIN is tied to the corner runner's 'vsup' parameter. EN (active-high,
* full-rail 0/VIN per design/README.md) is written as
* `dc 'vsup' pwl(0 0 100u 0 101u 'vsup' 10 'vsup')`, the same dual DC + PWL
* form sim/enable-shutdown's tb_enable_shutdown.sch uses. The DC value
* ('vsup', i.e. fully enabled) is what leg 2's `dc` sweep needs -- an enable
* ramp would be meaningless there, and the sweep source pins VOUT at every
* point through RFORCE = 1 mOhm, so the loop has no free regulating branch
* for the solver to choose between and each point after the first continues
* from the previous point's converged solution. The PWL, rising from 0 at
* t = 100 us to 'vsup' by t = 101 us, is what legs 1 and 3's transients ride:
* both start disabled and reach regulation through a soft-start ramp exactly
* as sim/startup's cold-enable legs do, instead of depending on a t = 0 DC
* solve landing on the regulating branch -- which it does not at the ff/sf
* 125C corners (issue #69; see also sim/enable-shutdown's and sim/startup's
* testbench comments, and issue #76, which gave leg 3 its edge after PR #75
* shipped the same fix in those two sibling benches, and issue #177, which
* gave leg 1 one).
*
* ---------------------------------------------------------------------
* Leg 2's dc sweep is SEEDED and runs FIRST (issue #647, contract #171)
* ---------------------------------------------------------------------
* Issue #177's 45-corner fleet re-run (record 20261117-173516-d843d914)
* measured leg 2 -- alone of the three legs -- tripping corner-run.py's
* #171 solver-diagnostic gate at 4 of 45 corners, every one on the 3.63 V
* (Vin_max) column: tt_27c/ff_27c `Warning: singular matrix: check node
* xldo.ea_cz`, fs_27c `... xldo.n_fbb`, fs_125c `Warning: Dynamic gmin
* stepping failed`. ngspice recovered every point via true gmin stepping and
* every measured value stayed inside its bounds -- the FAILs were
* solver-graded, not electrical -- but the #171 gate grades them FAIL
* regardless, which is the gate working as designed. Localized (issue #647,
* tt/27C/3.63V, this testbench netlisted and run one corner at a time): the
* flail is the sweep's own first continuation steps, at the dead-short end
* of the characteristic (the round between `Reference value : 0` and the
* next point's solve), not a mid-sweep crossing and not the knee; the
* 2.97 V and 3.30 V columns solve clean from ngspice's own guess. The fix
* is the initial-condition contract's `.nodeset` shape (#178/#189, the
* thermal precedent), with two measured facts shaping it:
*
* 1. THE CARD. A `.nodeset` re-applied as the first-iteration guess at
*    every dc sweep point (measured, #189) whose values are a MEASURED
*    realizable state of this testbench: the settled held-short end state
*    of leg 3's own transient (cold-start uic, EN edge at 100us, VOUT=0
*    short held from t=1.0ms, node voltages read at t=2.95ms) at the
*    matrix's nominal corner tt/27C/vsup=3.30V -- the sweep's own starting
*    point (vforce = 0, the dead short, clamp engaged) is exactly that
*    state, and the whole 0->1.75V characteristic lives on the same
*    clamp-engaged branch, so the seed biases the continuation onto the
*    branch it measures. Supply classification per #189's method: the
*    settled short state was measured at all three supplies (2.97/3.30/
*    3.63V) and each node written `{vsup-x}` only where its measured
*    slope is ~1 V/V (EA_OUT=EA_CZ 0.82, BIASP 0.97, CL_CMP 0.98, SS
*    1.00); EA_TAIL (slope 0.21 -- the PMOS input pair's source node, one
*    |Vgs| above the ground-referenced gates, exactly #189's finding) and
*    every other node stay absolute. The clamp state IS the branch here,
*    so the card seeds the current-limit comparator's own nodes (CL_CMP,
*    CL_SNS) alongside the set the thermal card uses.
* 2. THE ORDER. The seeded dc sweep leads the deck (leg 2, then leg 1,
*    then leg 3 -- the conceptual numbering is unchanged, only the run
*    order moves). Measured, not stylistic: with the same card, chained
*    after leg 1's transient, fs_125c_3.63v still tripped `Dynamic gmin
*    stepping failed` at the sweep's first point (the card is ~250mV from
*    fs/125C's own short state on BIASP/CL_CMP, and the post-transient
*    solve needs the guess more than a cold one does); with the dc first,
*    the identical card solves all four failing corners -- and the matrix
*    extremes ss/-40C and ff/125C at both supply rails -- with zero
*    diagnostics. This also puts the deck in the same shape as every
*    other seeded bench in sim/ (#178 thermal, #179 loop-gain/psrr-dc,
*    #180 load-transient): the seeded analysis leads, and the two
*    `tran ... uic` legs follow it -- they are order-independent by
*    construction (`uic` starts every node at 0; the deck restores each
*    leg's element values with `alter` before it runs), which the
*    before/after measurements confirm: all ten graded values at the
*    probed corners match the superseded record to 4-5 significant
*    digits.
*
* The card is a first-iteration constraint that is then released (a basin
* hint, not a held state): it may only bias WHICH branch the solve lands
* on, and the branch it names is the one the sweep measures. Conformance
* is the measured absence of the #171 markers in the record, not the
* mechanism's pedigree -- see sim/docs/initial-condition-contract.md's
* current-limit section (issue #647) for the localization probes and the
* per-corner before/after.
*
* CORRECTION, measured by issue #177 -- the EN edge alone is NOT sufficient,
* which is why legs 1 and 3 now carry `uic`. Both this comment and issue
* #174's audit previously held that a non-`uic` transient seeds its own t = 0
* operating point from the PWL's t = 0 value (0 V, disabled), so that neither
* transient leg was exposed to the initial-condition hazard. That is wrong
* about the operating point. ngspice runs a transient operating-point solve
* BEFORE the first timestep of a non-`uic` `tran`, and for a source carrying
* both a dc value and a transient function it uses the DC VALUE there. It
* says so itself, on stderr, on every run of this deck:
*
*   Note: ven: dc value used for op instead of transient time=0 value.
*
* i.e. that solve is the fully-enabled, loop-closed, from-nowhere Newton
* start sim/README.md's initial-condition contract (issue #171) forbids --
* even though the transient WAVEFORM afterwards does start from the PWL's
* 0 V. Run per-leg at tt/27C/3.30V, non-`uic`, legs 1 and 3 each tripped
* `Warning: Dynamic gmin stepping failed` (corner-run.py's solver-diagnostic
* FAIL gate); leg 2's `dc` sweep did not (its gmin stepping completes).
* Adding `uic` skips the offending solve and leaves every measurement
* unchanged (leg 1 vout_50ma = 1.79883 V, leg 3 ish_avg = -1.53348e-01 A,
* both identical with and without it).
*
* sim/enable-shutdown is NOT exposed by the same mechanism even though it
* uses the same dual form, because its dc value is `dc 0` -- its transient
* operating point is solved with EN already low, which is the disabled state
* the contract's own carve-out covers. sim/startup's `PULSE(...)` carries no
* separate dc keyword at all, so its op takes the pulse's initial 0 V. This
* bench is the only one in sim/ whose dual-form source has an ENABLED dc
* value, and therefore the only one this correction moves.
*
* VREF is a fixed 1.2 V placeholder
* per design/README.md's "VREF interface caveat, and the reference common
* mode" -- matching the 1:2 feedback divider (VOUT = 1.5 x VREF). No
* reference-generator block exists yet.
*
* C_OUT (1 uF) + R_ESR (10 mOhm) are the same representative point inside
* DR-002's *proposed* 0-500 mOhm / 0.33-4.7 uF window that sim/load-transient
* and sim/dropout-vs-load use, not a sweep of that window (DR-002 is
* proposed, not ratified).
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
T {current-limit testbench -- exercises design/ldo_3v3in_1v8out.sch (#14/#22)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
VIN = 'vsup' (corner runner); EN = dc 'vsup' for leg 2's dc sweep, PWL 0 -> 'vsup'
at 100us for legs 1 and 3's `tran ... uic`s (issues #76, #177); VREF = 1.2V placeholder (see design/README.md)
VFORCE + RFORCE force VOUT: DC limit characteristic, then a held Vout=0 short
ratified "Current limit" row: brickwall window TBD over PVT; never engages at 50mA} -700 -750 0 0 0.3 0.3 {}

* ---- VIN / EN (tied to the corner runner's supply) ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

C {devices/vsource.sym} -400 -300 0 0 {name=VEN value="dc 'vsup' pwl(0 0 100u 0 101u 'vsup' 10 'vsup')" savecurrent=true}
C {devices/lab_pin.sym} -400 -330 0 0 {name=p3 lab=EN}
C {devices/lab_pin.sym} -400 -270 0 0 {name=p4 lab=0}
T {EN carries BOTH a DC value ('vsup' -- used by leg 2's `dc` sweep, which is
unaffected by an enable ramp and whose VOUT is pinned by the forcing branch
anyway) and a PWL rising from 0 at t=100us to 'vsup' by t=101us, which is the
waveform legs 1 and 3's transients ride up through a soft-start ramp the same
way sim/startup's cold-enable legs do.
Fixes issue #76: an earlier draft tied VEN to a plain DC 'vsup' source, so
leg 3's transient started already-enabled and depended on ngspice's t=0 DC
solve landing on the regulating branch, which it does not at the ff/sf 125C
corners (issue #69) -- the same mechanism PR #75 fixed in
sim/enable-shutdown and sim/startup. Issue #177 then converted leg 1 from a
bare `op` (which did see this source's DC value, i.e. a fully enabled block,
with no seed at all) to the same cold-enable transient, per sim/README.md's
initial-condition contract (issue #171).
CAREFUL -- the PWL does NOT protect the transient's OPERATING POINT. ngspice
solves a transient op before a non-`uic` `tran`, and for a source carrying
both forms it uses the DC value there ("Note: ven: dc value used for op
instead of transient time=0 value", printed on stderr every run), i.e. the
fully-enabled loop-closed solve the contract forbids. #177 measured legs 1
and 3 each tripping `Warning: Dynamic gmin stepping failed` on that solve;
both legs therefore now carry `uic`, which skips it and changes no measured
value. See the deck notes in experiment.json and the header comment above.} -360 -230 0 0 0.2 0.2 {}

* ---- VREF (fixed placeholder, see design/README.md interface caveat) ----
C {devices/vsource.sym} -200 -300 0 0 {name=VVREF value=1.2 savecurrent=true}
C {devices/lab_pin.sym} -200 -330 0 0 {name=p5 lab=VREF}
C {devices/lab_pin.sym} -200 -270 0 0 {name=p6 lab=0}

* ---- DUT: the LDO core regulation loop + protection (#14/#22) ----
C {design/ldo_3v3in_1v8out.sym} 200 -300 0 0 {name=xldo}
C {devices/lab_pin.sym} 50 -320 0 0 {name=p7 lab=VREF}
C {devices/lab_pin.sym} 50 -300 0 0 {name=p8 lab=EN}
C {devices/lab_pin.sym} 50 -280 0 0 {name=p9 lab=VIN}
C {devices/lab_pin.sym} 350 -320 0 0 {name=p10 lab=VOUT}
T {xldo: instance name is load-bearing -- the deck reads the internal
current-limit comparison node as v(xldo.cl_cmp). Renaming this instance
breaks the clamp-engagement measurement in experiment.json.} 240 -300 0 0 0.2 0.2 {}

* ---- output network: C_OUT + R_ESR (DR-002 proposed representative point) ----
C {devices/capa.sym} 600 -400 0 0 {name=COUT m=1 value=1u footprint=1206 device="ceramic capacitor (DR-002 proposed nominal)"}
C {devices/lab_pin.sym} 600 -430 0 0 {name=p11 lab=VOUT}
C {devices/lab_pin.sym} 600 -370 0 0 {name=p12 lab=VESR}
C {devices/res.sym} 600 -250 0 0 {name=RESR value=10m m=1}
C {devices/lab_pin.sym} 600 -280 0 0 {name=p13 lab=VESR}
C {devices/lab_pin.sym} 600 -220 0 0 {name=p14 lab=0}
T {R_ESR: 10mOhm -- a representative point inside DR-002's proposed
0-500mOhm window (no minimum ESR); not a sweep of the window itself} 640 -300 0 0 0.2 0.2 {}

* ---- load: 36 Ohm (~50mA, the ratified Load row's ceiling) ----
C {devices/res.sym} 900 -300 0 0 {name=RLOAD value=36 m=1}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {R_LOAD: 36 Ohm (~50mA at the 1.8V ratified output target) for the
"clamp must not engage at 50mA" leg; the deck `alter`s it to 1e12
("0mA") for the forced-VOUT DC characteristic, where the forcing
source, not the load, sets the operating point.} 940 -300 0 0 0.2 0.2 {}

* ---- forcing branch: VFORCE + RFORCE (absent until the deck `alter`s RFORCE) ----
C {devices/res.sym} 1200 -300 0 0 {name=RFORCE value=1e12 m=1}
C {devices/lab_pin.sym} 1200 -330 0 0 {name=p17 lab=VOUT}
C {devices/lab_pin.sym} 1200 -270 0 0 {name=p18 lab=VF}
C {devices/vsource.sym} 1200 -180 0 0 {name=VFORCE value="dc 1.8 pwl(0 1.8 1m 1.8 1.001m 0 10 0)" savecurrent=true}
C {devices/lab_pin.sym} 1200 -210 0 0 {name=p19 lab=VF}
C {devices/lab_pin.sym} 1200 -150 0 0 {name=p20 lab=0}
T {RFORCE starts at 1e12 (branch effectively absent) and the deck `alter`s
it to 1m for the two forced legs. VFORCE carries BOTH a DC value (1.8V,
overridden by `dc vforce ...` in leg 2 and irrelevant in leg 1, where
RFORCE is still 1e12 and leg 3, which is `uic`) and a PWL that
drops the forced output to 0V at t=1.0ms and HOLDS it there to the end
of the run -- the "continuous Vout=0 short" of the ratified row, applied as
an event of defined duration rather than sampled at one instant. t=1.0ms
(issue #76) is deliberately after the EN PWL's soft-start ramp completes
(worst case ~0.553ms: 100us enable edge + sim/startup's measured 0.453ms
ff_125c ramp), so the fault lands on a block that has actually reached
regulation, not on an inconclusive t=0 DC solve.
i(vforce) > 0 means the LDO is delivering current into the forced node.} 1250 -230 0 0 0.2 0.2 {}

* ---- the dc sweep's own starting state: the settled held short (issue #647, contract #171) ----
C {devices/code_shown.sym} -700 -100 0 0 {name=IC_SEED only_toplevel=false value=".nodeset v(VOUT)=0.00015 v(xldo.FB)=0.0001 v(xldo.N_FBB)=0.00005 v(xldo.EA_OUT)=\{vsup-1.6915\} v(xldo.EA_CZ)=\{vsup-1.6915\} v(xldo.EA_TAIL)=1.6169 v(xldo.SS)=\{vsup-0.0001\} v(xldo.BIASP)=\{vsup-1.0637\} v(xldo.NB)=0.8641 v(xldo.CL_CMP)=\{vsup-0.9038\} v(xldo.CL_SNS)=0.9447 v(xldo.AMP_ENN)=0.0087"}
T {IC_SEED: the settled held-short state of THIS testbench at tt/27C/vsup=3.30V
-- leg 2's own starting point (vforce = 0, dead short, clamp engaged) --
measured from leg 3's cold-start uic transient at t=2.95ms (issue #647; see
the header for the supply-slope classification, for why the seeded dc sweep
leads the deck, and for why .nodeset and not .ic: a dc analysis ignores .ic,
measured in #178). EA_TAIL is absolute, not 'vsup'-relative: slope 0.21 V/V,
#189's finding. The card is re-applied at every sweep point (measured, #189)
and only biases which branch the solve lands on -- the clamp-engaged branch
this sweep measures} -700 -140 0 0 0.2 0.2 {}
