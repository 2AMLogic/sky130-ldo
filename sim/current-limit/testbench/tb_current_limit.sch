v {xschem version=3.4.7 file_version=1.2
* sky130-ldo current-limit testbench (issue #65).
*
* Exercises the current-limit clamp issue #22 added to the LDO core
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym), against
* spec/target-spec.md's DRAFT "Current limit" row:
*
*   "constant-current (brickwall) clamp, window TBD over PVT; never engages
*    for I_load <= 50 mA; survives continuous Vout = 0 short at Vin_max"
*
* That row is DRAFT (issue #1 is not yet ratified) and it deliberately
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
*   1. `op` with RFORCE open and RLOAD = 36 Ohm (~50 mA, the DRAFT Load
*      row's ceiling): the clamp must be fully OFF and the loop must still
*      regulate inside the DRAFT Output row's +-2% window. This is the
*      "never engages for I_load <= 50 mA" clause.
*   2. `dc vforce 0 -> 1.75` with RFORCE = 1 mOhm and RLOAD open: the DC
*      limit characteristic. Its two end points are the dead short
*      (Vout = 0) and the knee just below the regulation point
*      (Vout = 1.75 V); the pair is what says "brickwall" rather than
*      "foldback" -- a foldback limiter's short-circuit current is well
*      BELOW its knee current, a constant-current clamp's is not.
*   3. `tran` with the short APPLIED AS AN EVENT and then HELD: RLOAD is
*      back at 36 Ohm and VFORCE is a PWL that sits at 1.8 V until
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
* form sim/enable-shutdown's tb_enable_shutdown.sch uses: ngspice uses the DC
* value ('vsup', i.e. fully enabled) for legs 1-2 (`op`/`dc`, unaffected by
* an enable ramp), and the PWL for leg 3's `tran` (including its own t = 0
* operating point), which therefore starts DISABLED and rises through a
* soft-start ramp exactly as sim/startup's cold-enable legs do, instead of
* depending on ngspice's t = 0 DC solve landing on the regulating branch --
* which it does not at the ff/sf 125C corners (issue #69; see also
* sim/enable-shutdown's and sim/startup's testbench comments, and issue #76,
* which applied this same fix here after PR #75 shipped it in those two
* sibling benches). VREF is a fixed 1.2 V placeholder
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
VIN = 'vsup' (corner runner); EN = dc 'vsup' for legs 1-2, PWL 0 -> 'vsup'
at 100us for leg 3's tran (issue #76); VREF = 1.2V placeholder (see design/README.md)
VFORCE + RFORCE force VOUT: DC limit characteristic, then a held Vout=0 short
DRAFT "Current limit" row: brickwall window TBD over PVT; never engages at 50mA} -700 -750 0 0 0.3 0.3 {}

* ---- VIN / EN (tied to the corner runner's supply) ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

C {devices/vsource.sym} -400 -300 0 0 {name=VEN value="dc 'vsup' pwl(0 0 100u 0 101u 'vsup' 10 'vsup')" savecurrent=true}
C {devices/lab_pin.sym} -400 -330 0 0 {name=p3 lab=EN}
C {devices/lab_pin.sym} -400 -270 0 0 {name=p4 lab=0}
T {EN carries BOTH a DC value ('vsup' -- used by legs 1-2, the `op`/`dc`
analyses, which are unaffected by an enable ramp) and a PWL rising from 0 at
t=100us to 'vsup' by t=101us (used by leg 3's `tran`, which therefore starts
DISABLED and reaches regulation through a soft-start ramp the same way
sim/startup's cold-enable legs do). Fixes issue #76: an earlier draft tied
VEN to a plain DC 'vsup' source, so leg 3's transient started
already-enabled and depended on ngspice's t=0 DC solve landing on the
regulating branch, which it does not at the ff/sf 125C corners (issue #69) --
the same mechanism PR #75 fixed in sim/enable-shutdown and sim/startup.} -360 -230 0 0 0.2 0.2 {}

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

* ---- load: 36 Ohm (~50mA, the DRAFT Load row's ceiling) ----
C {devices/res.sym} 900 -300 0 0 {name=RLOAD value=36 m=1}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {R_LOAD: 36 Ohm (~50mA at the 1.8V DRAFT output target) for the
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
used by the `op` leg and overridden by `dc vforce ...`) and a PWL that
drops the forced output to 0V at t=1.0ms and HOLDS it there to the end
of the run -- the "continuous Vout=0 short" of the DRAFT row, applied as
an event of defined duration rather than sampled at one instant. t=1.0ms
(issue #76) is deliberately after the EN PWL's soft-start ramp completes
(worst case ~0.553ms: 100us enable edge + sim/startup's measured 0.453ms
ff_125c ramp), so the fault lands on a block that has actually reached
regulation, not on an inconclusive t=0 DC solve.
i(vforce) > 0 means the LDO is delivering current into the forced node.} 1250 -230 0 0 0.2 0.2 {}
