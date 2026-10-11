#!/bin/sh
# Issue #339 -- exact command sequence (all local, single condition tt / 27 C / 3.30 V / 50 mA,
# strictly sequential, one ngspice at a time; no grid, no background jobs, no Monte Carlo).
# Run from this directory (.spiceinit lives here). Source commit: see provenance.json / README.
set -e
python3 -I make_probe_deck.py probe probe0.deck.spice  probe0.dat
python3 -I make_probe_deck.py probe probeA.deck.spice  probeA.dat  ideal_tail
python3 -I make_probe_deck.py probe probeB.deck.spice  probeB.dat  no_clamps
python3 -I make_probe_deck.py probe probeAB.deck.spice probeAB.dat ideal_tail no_clamps
ngspice -b probe0.deck.spice  > probe0.stdout.txt  2>&1
ngspice -b probeA.deck.spice  > probeA.stdout.txt  2>&1
ngspice -b probeB.deck.spice  > probeB.stdout.txt  2>&1
ngspice -b probeAB.deck.spice > probeAB.stdout.txt 2>&1
# reproduction pair: byte-identical re-runs of the baseline and the combined probe
sed 's/probe0.dat/probe0r.dat/'   probe0.deck.spice  > probe0r.deck.spice;  cp probe0.dat.columns.json  probe0r.dat.columns.json
sed 's/probeAB.dat/probeABr.dat/' probeAB.deck.spice > probeABr.deck.spice; cp probeAB.dat.columns.json probeABr.dat.columns.json
ngspice -b probe0r.deck.spice  > probe0r.stdout.txt  2>&1
ngspice -b probeABr.deck.spice > probeABr.stdout.txt 2>&1
for n in probe0 probe0r probeA probeB probeAB probeABr; do python3 -I analyze.py tran $n >/dev/null; done
python3 -I analyze.py compare probe0 probe0r probeA probeB probeAB probeABr > compare.table.txt
# isolated M_PASS bench: calibration replay, 50 mA contour (+ refinement + VIN=2.064 V supplement)
python3 -I analyze.py calib-points probe0 calib_points.json
python3 -I make_probe_deck.py pass-calib pass_calib.deck.spice pass_calib.dat calib_points.json
ngspice -b pass_calib.deck.spice > pass_calib.stdout.txt 2>&1
python3 -I analyze.py calib pass_calib.dat calib_points.json pass_calib.analysis.txt
python3 -I make_probe_deck.py pass-contour pass_contour_2p160.deck.spice pass_contour_2p160.dat 2.16 0.005
python3 -I make_probe_deck.py pass-contour pass_refine_2p160.deck.spice  pass_refine_2p160.dat  2.16 0.0005 0.357
python3 -I make_probe_deck.py pass-contour pass_contour_2p064.deck.spice pass_contour_2p064.dat 2.064 0.005
ngspice -b pass_contour_2p160.deck.spice > pass_contour_2p160.stdout.txt 2>&1
ngspice -b pass_refine_2p160.deck.spice  > pass_refine_2p160.stdout.txt  2>&1
ngspice -b pass_contour_2p064.deck.spice > pass_contour_2p064.stdout.txt 2>&1
python3 -I analyze.py rounded pass_calib.dat pass_refine_2p160.dat pass_rounded.analysis.txt
python3 -I analyze.py contour pass_contour_2p160.dat "source=2.160V" pass_contour_2p160.analysis.txt
python3 -I analyze.py contour pass_refine_2p160.dat "refine source=2.160V" pass_refine_2p160.analysis.txt
python3 -I analyze.py contour pass_contour_2p064.dat "source=2.064V" pass_contour_2p064.analysis.txt
# probe C (frozen R_BIAS-derived bias) is only run if the valid combined residual is >= 0.300 V:
# NOT triggered (combined residual 0.164 V), so no probeC deck exists.
