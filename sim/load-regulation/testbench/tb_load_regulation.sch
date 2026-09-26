v {xschem version=3.4.7 file_version=1.2
* sky130-ldo load-regulation testbench (issue #64, split 1/3 of #61).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym) at two discrete operating
* points (I_LOAD in {0mA, 50mA}) at a fixed VIN, per
* spec/target-spec.md's ratified "Load regulation (0-50mA)" row: "< 1% (18mV),
* counted inside the +-2% window". That row is ratified by issue #1 / DR-006;
* the bound below cites it verbatim, not an invented final
* limit.
*
* Two discrete points, not a continuous .dc sweep (deliberate, found the hard
* way): a continuous 'dc iload 0 50m ...' sweep at this schematic's current
* revision does not track a single regulating branch across the whole
* range -- confirmed during this testbench's own bring-up (a full 51-point
* sweep at tt/27C/VIN=3.3V measured a 1.46V peak-to-peak vout excursion,
* over 80% of the 1.8V target, vs. the ~4mV design/README.md's own screening
* data reports at these endpoints). This is the same DC-solution-
* multiplicity family design/README.md's dated 2026-08-25 root-cause section
* documents for VIN sweeps (issue #60 mechanism 4, tracked by #71), now
* also observed load-current-side. Two independent solves at the ratified
* row's own endpoints (matching design/README.md's own "Load regulation"
* screening convention, which also uses discrete no-load/full-load points,
* not a sweep) reproduce that screening
* data. VIN is tied directly to the corner runner's 'vsup' (same convention
* load-transient/psrr-dc already use) -- this row's ratified bound is a
* function of load current at a given supply, not a function of VIN itself
* (that is the "Line regulation" row, see sim/line-regulation). EN also ties
* to 'vsup'. The load current source ILOAD is 'alter'ed between 0 and 50mA
* by the deck (mirrors sim/loop-gain's and sim/iq's multi-point-via-alter
* convention, #25).
*
* VREF is a fixed 1.2V placeholder per design/README.md's "VREF interface
* caveat" -- matching the 1:2 feedback-divider ratio issue #22 revised the
* schematic to (VOUT = 1.5 x VREF).
*
* Initial-condition contract (issue #172; contract defined by #171 in
* sim/README.md). Each of the two points is a COLD-START, SETTLED transient
* ('tran 10u 200m uic' with VEN below stepping high at 101us, measured over
* its settled 199ms-200ms tail), not a bare unconstrained '.op'. Every node
* starts at its natural cold value, EN starts LOW (block disabled), and the
* block powers up through its own soft-start ramp -- the contract's
* 'uic' + EN-edge shape, and the same shape PR #170 landed for
* sim/mc-output-accuracy. No solve in this deck starts from ngspice's own
* from-nowhere guess, because with 'uic' there is no operating-point solve at
* all. This bench's previous revision was the worst case of the defect #164
* characterized: an unseeded '.op' chain, and 44 of the 45 corners of record
* 20260925-111601-7701e7e carry a solver diagnostic (40 'singular matrix',
* 4 'out of range for ^') on the same three sky130_fd_pr__res_xhigh_po
* instances (xldo.ea_cz, xldo.amp_enn, xldo.n_fbb).
*
* Measured during #172's implementation, and the reason the two 'op' cards
* became two 'uic' transients rather than two seeded 'op' cards: a seeded DC
* solve does not close the gap in ngspice. '.ic' is applied only to the
* operating-point solve that PRECEDES a non-'uic' transient (its MODETRANOP
* solve) -- a bare 'op' command ignores it. '.nodeset' IS honoured by a bare
* 'op', but only as a first-iterations guess that is then released: with the
* full 11-node intended-branch node set of sim/ic-screen-125c-b applied as a
* '.nodeset' to this bench's old '.op' chain, 3 of 5 corners probed
* (tt/27C/3.30V, fs/125C/3.63V, ss/-40C/2.97V) still printed 'singular
* matrix' plus 'Dynamic gmin stepping failed'. A settled transient per point
* is therefore the only shape that actually satisfies this contract here.
*
* WHY THE TRANSIENT IS 200ms AND NOT 1ms -- this bench's own hard-won number,
* and the reason it differs from the sibling sim/line-regulation bench's
* otherwise identical deck. At the ratified row's 0mA endpoint the ONLY
* discharge path out of the 1uF C_OUT is the feedback divider, so any start
* state above the no-load operating point bleeds down through a
* high-impedance path. CORRECTED by issue #184 (surfaced reviewing PR #182;
* does not reproduce on this deck): this 'uic' cold-start deck itself, at
* tt/27C/3.30V, reads v(vout) = 1.81337V averaged over 0.8ms-1ms and is
* already settled to 1.80239V by ~50ms (flat to six digits from there
* through 100ms, 200ms, 300ms and 400ms) -- an 11.0mV 1ms-window artifact
* against the 18mV bound, i.e. a PASS, not a FAIL. The 1.85985V/1.83245V/
* 1.80332V trajectory and the "57mV, 3x the bound, would fail all 45
* corners" conclusion once documented here were measured on the
* '.ic'/'op'-seeded, non-'uic' cross-check variant tried first (see below),
* not on this deck. 200ms is nonetheless still the right window: that
* seeded cross-check variant genuinely needs the long window to settle, and
* every corner probed keeps margin under 200ms even at this deck's own
* largest observed 1ms-window artifact (1.75mV at fs/125C/3.63V). The 50mA
* endpoint, by contrast, settles inside 1ms at every corner probed (it has
* 50mA with which to discharge), and the 199ms-200ms tail average equals
* the 0.8ms-1ms one to six digits there.
*
* 199ms-200ms is therefore a measured settled window, not an assumed one:
* at the three hottest/slowest corners probed (tt/125C/3.63V, ff/125C/3.63V,
* fs/125C/3.63V) the 99ms-100ms and 199ms-200ms tail averages agree to
* <=0.13mV (corrected by issue #184 from a previously documented <=0.1mV),
* and an independently seeded ('.ic', non-'uic') 400ms transient lands on
* the same tail at all three (1.81042V vs 1.81042V at ff/125C/3.63V;
* 1.81860V vs 1.81856V at fs/125C/3.63V) -- two different start states
* converging on one answer, which is the property this contract is really
* after.
*
* Known-risk note (not a testbench defect): design/README.md's dated
* 2026-08-25 "full 45-point PVT + Monte Carlo campaign" section (issue #60,
* mechanism 1) documents a thermal-shutdown (#29/DR-005) false-trip at the
* ff/sf process corners at 125C, independent of load current -- tracked by
* issue #69, which re-sized that shutdown. #172's seeded re-run is this
* bench's first 45-corner record against the post-#69 DUT with a physically
* realizable start state; read its ff/sf 125C numbers as a fresh measurement
* rather than through the pre-#69 expectation of a false trip.
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
T {load-regulation testbench -- exercises design/ldo_3v3in_1v8out.sch (#14)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
VIN = 'vsup' (corner runner)
EN: 0V until 101us, then 'vsup' (the contract's EN edge, #171/#172)
I_LOAD: 'alter'ed between 0mA/50mA by the deck (2 discrete cold-start settled
'uic' transients, not a sweep and not a bare .op -- see header)} -700 -650 0 0 0.3 0.3 {}

* ---- VIN: tied to the corner runner's 'vsup' ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value='vsup' savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

* ---- EN: 0V (disabled) until 101us, then the corner runner's supply. This is
*      the initial-condition contract's own EN edge (#171, converted by #172):
*      with 'tran ... uic' every node starts cold and the block powers up
*      through its own soft-start ramp, so no measured point is read off an
*      unconstrained DC solve. Same 'dc 0 pwl(...)' form sim/enable-shutdown
*      already uses -- the explicit 'dc 0' pins the disabled state. ----
C {devices/vsource.sym} -400 -300 0 0 {name=VEN value="dc 0 pwl(0 0 100u 0 101u 'vsup' 10 'vsup')" savecurrent=true}
C {devices/lab_pin.sym} -400 -330 0 0 {name=p3 lab=EN}
C {devices/lab_pin.sym} -400 -270 0 0 {name=p4 lab=0}

* ---- VREF (fixed placeholder, see design/README.md interface caveat) ----
C {devices/vsource.sym} -200 -300 0 0 {name=VVREF value=1.2 savecurrent=true}
C {devices/lab_pin.sym} -200 -330 0 0 {name=p5 lab=VREF}
C {devices/lab_pin.sym} -200 -270 0 0 {name=p6 lab=0}

* ---- No '.ic'/'.nodeset' card here, deliberately (#172): this bench uses the
*      initial-condition contract's OTHER shape -- 'uic' plus the EN edge
*      above -- so there is no operating-point solve to seed. See the header
*      for the measurement that ruled a seeded 'op' out. ----

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

* ---- load: 'alter'ed by the deck between 0A (no load) and 50mA (full load) ----
C {devices/isource.sym} 900 -300 0 0 {name=ILOAD value=0}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {I_LOAD: 0A is this schematic's placeholder component value (no load); the
deck's own .control block 'alter's it to 50mA (full load) for the second
point, per the ratified "Load regulation (0-50mA)" row's own two endpoints} 940 -300 0 0 0.2 0.2 {}
