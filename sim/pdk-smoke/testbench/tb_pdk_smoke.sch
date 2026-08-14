v {xschem version=3.4.7 file_version=1.2
* sky130-ldo harness smoke testbench (issue #2).
*
* NOT an LDO. This schematic exists only to prove the harness path
* xschem -> netlist -> ngspice (with sky130 device models) -> parsed results
* round-trips, and that the process/voltage/temperature knobs the corner
* runner injects actually move the answer.
*
* Circuit: a 1 Mohm ideal resistor biases a diode-connected sky130 core
* nFET (nfet_01v8) from the supply rail. Deliberately uses the 1.8 V CORE
* device family, not either candidate pass-device flavor from the open
* "sky130 porting question" in spec/target-spec.md (pfet_g5v0d10v5 under
* framing A, or the 1.8 V core devices under framing B) -- this testbench
* is harness plumbing, not a design decision, and must not be read as
* prejudging that still-open ratification question (issue #1). The two
* measured quantities are strongly corner- and temperature-dependent, so a
* record that shows identical numbers across corners means the harness is
* not actually applying corners:
*   vgs  = v(vg)   -- gate-source voltage of the diode-connected device
*   isup = -i(v1)  -- current drawn from the supply
*
* Deliberately NOT in this schematic (the corner runner injects them, so one
* schematic serves the whole PVT matrix):
*   - the .lib model corner include (no sky130_fd_pr/corner.sym instance)
*   - .temp
*   - the numeric supply value: V1 is 'vsup', a .param the runner sets
*   - the .control analysis/measurement block
}
G {}
K {}
V {}
S {}
E {}
T {harness smoke testbench -- not the LDO
connectivity is by net label (lab_pin on every device pin), no wires
supply value comes from .param vsup (corner runner)
corner (.lib) and .temp are injected by the corner runner} 0 -300 0 0 0.4 0.4 {}
C {devices/vsource.sym} 0 -100 0 0 {name=V1 value='vsup' savecurrent=true}
C {devices/lab_pin.sym} 0 -130 0 0 {name=pv1 lab=VDD}
C {devices/lab_pin.sym} 0 -70 0 0 {name=pv2 lab=0}
C {devices/res.sym} 200 -200 0 0 {name=R1 value=1meg m=1}
C {devices/lab_pin.sym} 200 -230 0 0 {name=pr1 lab=VDD}
C {devices/lab_pin.sym} 200 -170 0 0 {name=pr2 lab=VG}
C {sky130_fd_pr/nfet_01v8.sym} 300 -100 0 0 {name=M1
L=0.5
W=2
nf=1
mult=1
model=nfet_01v8
spiceprefix=X}
C {devices/lab_pin.sym} 320 -130 0 0 {name=pm1 lab=VG}
C {devices/lab_pin.sym} 280 -100 0 0 {name=pm2 lab=VG}
C {devices/lab_pin.sym} 320 -70 0 0 {name=pm3 lab=0}
C {devices/lab_pin.sym} 320 -100 0 0 {name=pm4 lab=0}
