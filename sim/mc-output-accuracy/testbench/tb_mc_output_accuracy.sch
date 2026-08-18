v {xschem version=3.4.7 file_version=1.2
* sky130-ldo mc-output-accuracy testbench (issue #19).
*
* Exercises the LDO core-regulation-loop schematic landed by #14
* (design/ldo_3v3in_1v8out.sch, instantiated below via its companion
* subcircuit symbol design/ldo_3v3in_1v8out.sym) at a single, fixed DC
* operating point -- nominal VIN, light load -- so that a Monte Carlo
* sampler (klt sim's request.monte_carlo, vary="mismatch") can re-run this
* same circuit N times with a fresh per-instance AGAUSS mismatch draw each
* time and report the VOUT spread, per spec/target-spec.md's DRAFT "Output"
* row (1.8V +-2%, i.e. 1.764V-1.836V). That row is DRAFT (issue #1 not yet
* ratified) -- the bound cited by this experiment's klt sim request cites it
* directly, not an invented final limit, and needs re-verification once #1
* rules.
*
* I_LOAD is fixed at 1mA (light load) -- the same light-load convention
* sim/psrr-dc/ already uses as its single characterized load point (see
* that experiment's testbench header): light load is the binding case for
* output accuracy on a single-stage OTA error amp whose output swing
* ceiling is a known open item (design/README.md "Known open item"), so a
* fixed 1mA point is a representative, not exhaustive, output-accuracy
* check -- it does not sweep the full 0-50mA load-regulation range (a
* separate DRAFT spec row, not this testbench's job).
*
* Deliberately NOT in this schematic (the corner runner / klt sim request
* injects them, so this schematic stays PVT- and MC-agnostic): the .lib
* model corner include, .temp, .param vsup default, and the
* .control/analysis/measurement block. VIN/EN's numeric value comes from
* 'vsup', same convention as every other testbench in this directory --
* the klt sim request's netlist wrapper step (sim/bin/mc-run.py) prepends
* a `.param vsup=<value>` default so the raw netlist body parses standalone
* (klt sim's `corners.supply_v` alters an existing `.param`, it does not
* define one -- see docs/cli/sim.md "Corner axes" in 2AMLogic/klayout-tools).
}
G {}
K {}
V {}
S {}
E {}
T {mc-output-accuracy testbench -- exercises design/ldo_3v3in_1v8out.sch (#14)
via its companion subcircuit symbol design/ldo_3v3in_1v8out.sym
VIN/EN = 'vsup'; VREF = 1.2V placeholder (see design/README.md)
I_LOAD: fixed 1mA (light load, same convention as sim/psrr-dc)
C_OUT/R_ESR: DR-002 proposed 1uF / representative ESR point (DR-002 is proposed, not ratified)
Monte Carlo mismatch sampling is driven externally by klt sim (sim/bin/mc-run.py), not by this schematic} -700 -650 0 0 0.3 0.3 {}

* ---- VIN / EN (tied to the corner runner's / klt sim request's supply) ----
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

* ---- output network: C_OUT + R_ESR (DR-002 proposed starting point) ----
C {devices/capa.sym} 600 -400 0 0 {name=COUT m=1 value=1u footprint=1206 device="ceramic capacitor (DR-002 proposed nominal)"}
C {devices/lab_pin.sym} 600 -430 0 0 {name=p11 lab=VOUT}
C {devices/lab_pin.sym} 600 -370 0 0 {name=p12 lab=VESR}
C {devices/res.sym} 600 -250 0 0 {name=RESR value=10m m=1}
C {devices/lab_pin.sym} 600 -280 0 0 {name=p13 lab=VESR}
C {devices/lab_pin.sym} 600 -220 0 0 {name=p14 lab=0}
T {R_ESR: 10mOhm -- a representative point inside DR-002's proposed
0-500mOhm window (no minimum ESR); not a sweep of the window itself} 640 -300 0 0 0.2 0.2 {}

* ---- load: fixed 1mA (light load, same convention as sim/psrr-dc) ----
C {devices/isource.sym} 900 -300 0 0 {name=ILOAD value=1m}
C {devices/lab_pin.sym} 900 -330 0 0 {name=p15 lab=VOUT}
C {devices/lab_pin.sym} 900 -270 0 0 {name=p16 lab=0}
T {I_LOAD: fixed 1mA -- light-load, same convention as sim/psrr-dc} 940 -300 0 0 0.2 0.2 {}
