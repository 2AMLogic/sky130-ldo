v {xschem version=3.4.7 file_version=1.2
* sky130-ldo line-regulation testbench (issue #64, split 1/3 of #61).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym) at four discrete operating
* points (VIN in {2.97V, 3.63V} x I_LOAD in {1mA, 50mA}),
* per spec/target-spec.md's ratified "Line regulation" row: "< 5 mV/V over
* 2.97-3.63V, at 1mA and 50mA". That row is ratified by issue #1 / DR-006;
* the bound below cites it verbatim, not an invented final
* limit.
*
* Four discrete points, not a continuous .dc sweep (deliberate, found the
* hard way): a continuous 'dc vvin 2.97 3.63 ...' sweep at this schematic's
* current revision repeatedly hits gmin-stepping/singular-matrix
* non-convergence partway through the range (design/README.md's dated
* 2026-08-25 root-cause section, issue #60 mechanism 4, tracked by #71,
* documents the same DC-solution-multiplicity behavior for VIN sweeps at
* 50mA load) -- confirmed during this testbench's own bring-up: a 34-point
* sweep over this exact range did not complete in minutes of wall-clock
* time. Four independent solves at the ratified range's own two endpoints
* (matching design/README.md's own "DC operating grid" screening
* convention, which also uses discrete VIN points, not a sweep) reproduce
* that screening data's line-regulation numbers. VIN and I_LOAD are both
* 'alter'ed between points (mirrors sim/loop-gain's and sim/iq's
* multi-point-via-alter convention, #25) --
* see sim/line-regulation/experiment.json's "deck.analyses" for the exact
* sequence. line_reg_*_mv_per_v is computed as
* abs(1000*(vout_hi-vout_lo)/(3.63-2.97)), i.e. mV per V of VIN span over
* the ratified range's two endpoints -- the same convention design/README.md's
* own line-regulation screening numbers use.
*
* Initial-condition contract (issue #172; contract defined by #171 in
* sim/README.md). Each of the four points is a COLD-START, SETTLED transient
* ('tran 10u 200m uic' with VEN below stepping high at 101us, measured over
* its settled 199ms-200ms tail), not a bare unconstrained '.op'. Every node
* starts at its natural cold value, EN starts LOW (block disabled), and the
* block powers up through its own soft-start ramp -- the contract's
* 'uic' + EN-edge shape, and the same shape PR #170 landed for
* sim/mc-output-accuracy. No solve in this deck starts from ngspice's own
* from-nowhere guess, because with 'uic' there is no operating-point solve at
* all. This bench's previous revision was the worst case of the defect #164
* characterized: an unseeded '.op' chain, and all 45 corners of record
* 20260925-114251-1f54ca6 carry a solver diagnostic (44 'singular matrix',
* 1 'Dynamic gmin stepping failed' plus 'out of range for ^') on the same
* three sky130_fd_pr__res_xhigh_po instances (xldo.ea_cz, xldo.amp_enn,
* xldo.n_fbb). Measured under this shape instead: zero diagnostics on all 45
* corners of the superseding record -- see sim/README.md's "#172" section.
*
* Measured during #172's implementation, and the reason the four 'op' cards
* became four 'uic' transients rather than four seeded 'op' cards: a seeded
* DC solve does not close the gap in ngspice. '.ic' is applied only to the
* operating-point solve that PRECEDES a non-'uic' transient (its MODETRANOP
* solve) -- a bare 'op' command ignores it. '.nodeset' IS honoured by a bare
* 'op', but only as a first-iterations guess that is then released: with the
* full 11-node intended-branch node set of sim/ic-screen-125c-b applied as a
* '.nodeset' to this bench's and sim/load-regulation's old '.op' chains,
* 3 of 5 corners probed (tt/27C/3.30V, fs/125C/3.63V, ss/-40C/2.97V) still
* printed 'singular matrix' plus 'Dynamic gmin stepping failed'. A settled
* transient per point is therefore the only shape that actually satisfies
* this contract here.
*
* Measured evidence that the cold start is not steering the answer: an
* '.ic'-seeded non-'uic' settled transient (the contract's other shape, seeded
* from sim/ic-screen-125c-b's committed node set) reaches the SAME settled
* tail at every point cross-checked -- at tt/27C/3.30V all four points agree
* to six digits (1.80050 / 1.80071 / 1.79872 / 1.79892 V), and at
* tt/125C/2.97V both shapes return 31.2 / 43.9 mV/V. Two independent start
* states converging on one tail is the property the contract is really after.
*
* 199ms-200ms is a settled window, measured rather than assumed: all four of
* this bench's points carry a real load current (1mA or 50mA), so they settle
* fast -- v(vout) averaged over 0.8ms-1ms already equals the 199ms-200ms
* average to six digits at tt/27C/3.30V. The long transient is carried here
* anyway, for one convention across both regulation benches: the sibling
* sim/load-regulation bench's NO-LOAD point genuinely needs it (see that
* file's header -- at 0mA the feedback divider is the only discharge path.
* Corrected by issue #184: the sibling's own 'uic' deck is only ~11mV away
* from the settled value at 1ms there, not the ~57mV once documented; the
* long window is still carried because that bench's seeded, non-'uic'
* cross-check variant genuinely needs it to settle).
*
* VIN's own component value below (3.3V) is a placeholder the deck's first
* 'alter' immediately overwrites; it is never simulated as-is.
*
* VREF is a fixed 1.2V placeholder per design/README.md's "VREF interface
* caveat" -- matching the 1:2 feedback-divider ratio issue #22 revised the
* schematic to (VOUT = 1.5 x VREF).
*
* Known-risk note (not a testbench defect): design/README.md's dated
* 2026-08-25 "full 45-point PVT + Monte Carlo campaign" section (issue #60,
* mechanism 1) documents a thermal-shutdown (#29/DR-005) false-trip at the
* ff/sf process corners at 125C, independent of load current -- tracked by
* issue #69, which re-sized that shutdown. #172's seeded re-run is the first
* 45-corner record of this bench taken against the post-#69 DUT with a
* physically realizable start state; read its ff/sf 125C numbers as a fresh
* measurement rather than through the pre-#69 expectation of a false trip.
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
T {line-regulation testbench -- exercises design/ldo_3v3in_1v8out.sch (#14)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
VVIN 'alter'ed between 2.97V/3.63V by the deck (4 discrete cold-start settled
'uic' transients, not a sweep and not a bare .op -- see header)
EN: 0V until 101us, then 'vsup' (the contract's EN edge, #171/#172)
I_LOAD: 'alter'ed between 1mA/50mA by the deck} -700 -650 0 0 0.3 0.3 {}

* ---- VIN: independent of the corner runner's 'vsup'; 'alter'ed by the deck ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value=3.3 savecurrent=true}
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

* ---- load: current source, 'alter'ed by the deck between 1mA and 50mA ----
C {devices/isource.sym} 900 -300 0 0 {name=ILOAD value=1m}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {I_LOAD: 1mA is this schematic's placeholder component value; the deck's
own .control block 'alter's it between 1mA and 50mA across the four measured
points, per the ratified "Line regulation" row's own two test points} 940 -300 0 0 0.2 0.2 {}
