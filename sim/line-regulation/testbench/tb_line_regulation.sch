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
* that screening data's line-regulation numbers. VIN, EN's high level and
* I_LOAD are all 'alter'ed between points (mirrors sim/loop-gain's and
* sim/iq's multi-point-via-alter convention, #25; EN joined the list in
* #196, see the "EN convention" section below) --
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
* 'alter' immediately overwrites; it is never simulated as-is. VEN's pwl high
* level carries the same 3.3V placeholder for the same reason (#196).
*
* EN convention (issue #196) -- EN TRACKS THE INSTANTANEOUS VIN.
* ==============================================================
* Through record 20260926-001833-228fbc7 this bench drove EN's high level at
* 'vsup', the corner runner's own supply label, while VVIN was this bench's
* OWN source being 'alter'ed between 2.97V and 3.63V. Those are different
* quantities here: at the *_2.97v corners the VIN=3.63V point therefore ran
* with EN 0.66V BELOW the instantaneous VIN. That is the geometry #187
* root-caused on sim/dropout-vs-load (see sim/README.md -> "#187"): EN gates
* five PMOS shutdown clamps whose SOURCES ARE VIN, so their gate drive is
* (VIN - EN), and at 0.66V down two of them out-drive the error amplifier's
* own tail current, EA_OUT is pulled to VIN and M_PASS turns off. It is a
* static headroom limit, not a start-up branch, and it leaves NO solver
* diagnostic -- which is why #171's gate never caught it.
*
* Chosen convention: EN's high level = the instantaneous VIN at every measured
* point. Why this one and not the alternatives #196 put up:
*   - It is the only one that honours the DOCUMENTED interface everywhere.
*     design/README.md -> "Enable/shutdown" specifies EN as "active-high,
*     full-rail (0V / VIN)"; the enable input is VIN-referenced by
*     construction, so EN = VIN is the contract at 2.97V and at 3.63V alike.
*     No spec line moves: this is a bench-convention fix, and #196 is
*     explicitly out of scope to touch design/ or spec/.
*   - "EN = 3.63V (the higher endpoint) at every corner" would put EN ABOVE
*     VIN at the 2.97V point. That direction is not the #187 failure (the
*     VIN-sourced PMOS clamps go HARDER off, not on, when EN rises above VIN),
*     but it is still not the documented interface, it over-drives the
*     EN-gated NMOS switches M_ENN/M_ENN2 relative to it, and it would leave
*     this bench the only one in sim/ whose low-VIN point is driven from a
*     rail the DUT does not have. Rejected as an unnecessary second departure,
*     not as a second collapse.
*   - "Collapse the supply axis for this row" is a manifest change to the
*     ratified corner matrix's meaning, which CLAUDE.md routes through a
*     decision record. Not taken here. Instead the full 45-corner matrix is
*     still run, and the axis's redundancy on THIS bench becomes a measured
*     result rather than an assumption -- see the next paragraph.
*
* Measured confirmation that the five FAILing corners of record
* 20260926-001833-228fbc7 were this artifact and nothing else (full numbers and
* method in sim/README.md -> "#196"): re-running all five *_125c_2.97v corners
* with EN at the instantaneous VIN takes every one of them from 6.7-12890 mV/V
* to 0.44-0.51 mV/V at 1mA and 0.34-0.37 mV/V at 50mA, i.e. into the same band
* the other 40 corners of that record already occupied. The VIN=2.97V points
* are untouched by the convention (EN = 'vsup' = 2.97V = VIN there already) and
* they reproduce the superseded record's own settled values; the entire change
* is at the VIN=3.63V points, which stop being driven with EN 0.66V down.
*
* What 'vsup' now means on this bench: nothing in the stimulus. It is a pure
* corner LABEL here. VVIN and VEN are both set from the deck's own per-point
* literal, so the decks for a corner's 2.97V / 3.30V / 3.63V variants differ
* only in the runner's '.param vsup=' line, which this bench no longer
* references. The three supply columns are therefore expected to be
* IDENTICAL, and that is the useful thing about keeping them: the 45-corner
* record's own supply axis is now a reproducibility check on the harness
* rather than a stimulus axis. (The previous convention is what made that axis
* appear to carry information -- the information it carried was the artifact.)
*
* Implementation, and why this shape rather than a behavioural source.
* VIN is piecewise-CONSTANT across the four measured points (the deck only
* moves it between transients), so EN's high level can simply be re-pointed
* alongside it: each point does `set vinpt = <v>` then `alter vvin = $vinpt`
* AND `alter @ven[pwl] = [ 0 0 100u 0 101u $vinpt 10 $vinpt ]` -- ONE literal
* per point feeding both sources, so the two can never drift apart in a later
* edit.
*
* The obvious alternative -- a behavioural source multiplying a dimensionless
* 0->1 enable ramp by v(VIN), `BEN EN 0 V='v(VIN)*v(ENRAMP)'` -- expresses the
* same intent continuously instead of per-point, and it was built and run as a
* CROSS-CHECK rather than shipped. At fs/125C/2.97V, the worst corner of the
* superseded record, that bsource deck returns line_reg_1ma = 0.595454 mV/V
* and line_reg_50ma = 0.353030 mV/V over the same four 200ms points
* (v(vout) = 1.80087 / 1.80126 / 1.79839 / 1.79862 V); the shipped vsource
* deck's own reading for that corner comes with the 45-corner re-run #196 left
* open (sim/README.md -> "#196" -> "Why the 45-corner matrix is not re-run
* here"). Two independent expressions of "EN = the instantaneous VIN"
* landing on one answer is the property worth having. The plain vsource ships
* because EN stays a plain `.save i(ven)`-able independent source in the same
* form sim/enable-shutdown and the #171/#172 contract describe, and because a
* bsource makes the start-up window markedly more expensive to solve.
*
* Evidence state after #196 (read this before citing a record): the newest
* committed 45-corner record, 20260926-001833-228fbc7, was taken under the OLD
* EN convention, and #196 did not re-run the matrix -- on the sweep host it ran
* on, one corner of this deck takes ~579s against 41.7s in that record, i.e.
* ~7h for 45 corners. So this bench's committed matrix evidence is stale by
* construction until one `corner-run.py sim/line-regulation --supersedes
* 20260926-001833-228fbc7` completes; the five-corner confirmation above is
* deliberately NOT minted as a record, because an incomplete matrix must not
* be. sim/README.md -> "#196" has the numbers and the same reasoning #177
* applied to sim/current-limit; the re-run itself is tracked by #200.
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
EN: 0V until 101us, then the INSTANTANEOUS VIN -- 'alter'ed alongside VVIN from
the same per-point literal (#196); the contract's EN edge shape (#171/#172)
I_LOAD: 'alter'ed between 1mA/50mA by the deck} -700 -650 0 0 0.3 0.3 {}

* ---- VIN: independent of the corner runner's 'vsup'; 'alter'ed by the deck ----
C {devices/vsource.sym} -600 -300 0 0 {name=VVIN value=3.3 savecurrent=true}
C {devices/lab_pin.sym} -600 -330 0 0 {name=p1 lab=VIN}
C {devices/lab_pin.sym} -600 -270 0 0 {name=p2 lab=0}

* ---- EN: 0V (disabled) until 100us, then the INSTANTANEOUS VIN (issue #196).
*      The high level below (3.3V) is a PLACEHOLDER, exactly like VVIN's own
*      3.3V above, and exactly like VVIN's it is overwritten by the deck's
*      first 'alter' and never simulated as-is. The deck's .control block
*      re-points this pwl's high level at every 'alter vvin', from the SAME
*      single literal, so EN's high level is the instantaneous VIN at all four
*      measured points by construction -- see experiment.json's
*      "deck.analyses" and the header's #196 section. It used to read
*      'vsup' (the corner runner's own supply label), which on this bench is
*      NOT VIN: that is what #196 fixed. Edge shape and timing are unchanged
*      from #172 -- 0V until 100us, 1us linear ramp, then held. ----
C {devices/vsource.sym} -400 -300 0 0 {name=VEN value="dc 0 pwl(0 0 100u 0 101u 3.3 10 3.3)" savecurrent=true}
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
