# Folded-resistor qualification record `20261010-033502-704005c` (issue #253)

Resistor-only test blocks. **Not** a full-core layout, **not** an area-compliance claim for the LDO (the ratified Area row is untouched), and no schematic value is changed: every folded bank keeps the schematic `W`, and its segment lengths sum to the schematic `L`.

## Provenance

- git: `704005c84d8adeb5f72f15ba526be1d498c8801a`; schematic last changed at `a09aa83`
- klt: `klt 0.6.0+g040f3406b485` (pin: `klayout-tools @ git+https://github.com/2AMLogic/klayout-tools@040f3406b4858ac7a5b8faa8df5327fd62a65afa`)
- KLayout (PDK signoff runset engine): `KLayout 0.28.16`; runset `libs.tech/klayout/drc/sky130A_mr.drc (feol=true beol=true)`
- ngspice: `ngspice-46 : Circuit level simulation program`; model library `libs.tech/combined/sky130.lib.spice` section `tt`, 27 C
- PDK: `sky130A` `open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b` (repo pin `c6d73a35f524070e85faff4a6a9eef49553ebc2b`)

## Equivalence tolerance (rule fixed before any result was computed)

A folded bank is **EQUIVALENT** to the unsplit schematic resistor when its effective resistance at the stated operating point differs from the unsplit device's by no more than **3 x the local-mismatch sigma of the unsplit device**, read from the same PDK model library the sim harness uses (`rbody *= 1 + sw_mm * mismatch_factor * AGAUSS / sqrt(W*L)`). Rationale: a deterministic shift inside that band is indistinguishable from drawing a second copy of the same schematic device; anything larger is a real electrical change that would have to be requalified (or compensated) rather than assumed away. The global sheet-rho spread is shown for context only and does not gate the verdict.

| device | W x L (um) | sw_mm | 1 sigma local | **tolerance (3 sigma)** | context: sheet rho low / nom / high (ohm/sq), process MC sigma |
|---|---|---|---|---|---|
| R_BIAS | 0.42 x 1500 | 0.0206 | 0.082% | **0.246%** | 277 / 325 / 370, 3.5% |
| R_FB_A | 0.42 x 180 | 0.0464 | 0.534% | **1.601%** | 1700 / 2000 / 2300, 4% |

(The corner sheet-rho values assume `corner_factor = 1`, as each `parameters_res_<corner>.spice` line is written.)

## Verdicts (drawn configurations)

| case | device | N x segment L | DRC (klt gate) | LVS folded vs unsplit ref | negative controls | R_eff shift (model + li1 joints) | tolerance | electrical verdict |
|---|---|---|---|---|---|---|---|---|
| `rbias_n16` | R_BIAS (res_high_po) | 16 x 93.75 um | clean | match | broken: mismatch; folded_perturbed: mismatch | +1.060% (+12885.1 ohm) | 0.246% | **NOT EQUIVALENT** |
| `rbias_n4` | R_BIAS (res_high_po) | 4 x 375 um | clean | match | broken: mismatch; folded_perturbed: mismatch | +0.212% (+2577.0 ohm) | 0.246% | **EQUIVALENT** |
| `rfb_n2` | R_FB_A (res_xhigh_po) | 2 x 90 um | clean | match | broken: mismatch; folded_perturbed: mismatch | -0.017% (-172.4 ohm) | 1.601% | **EQUIVALENT** |

## Case `rbias_n16` -- R_BIAS as 16 series segments

- Schematic: `res_high_po` W=0.42 um, L=1500 um. Drawn: 16 segments x 93.75 um (sum 1500 um), W unchanged.
- Connections: segment i's `R<i>_B` pad joined to segment i+1's `R<i+1>_A` pad by one li1 strap spanning the row gap (15 straps, 7.812 um^2 li1); chain ends labelled `A` (segment 0 `R0_A`) and `B`; one substrate tie labelled `SUB`. Exact strap coordinates: `geometry.json`.

**Area** (bounding rectangle, um / um^2)

| | width | height | area |
|---|---|---|---|
| unsplit device (as the core draws it) | 1500.84 | 0.42 | 630.353 |
| folded bank, generated | 94.59 | 12.72 | 1203.18 |
| folded bank, routed (straps + merged markers) | 94.59 | 12.72 | 1203.18 |
| unsplit + test substrate tie | 1500.84 | 2.92 | 4382.45 |
| folded + test substrate tie | 94.59 | 15.22 | 1439.66 |

Width reduced by 1406.25 um; folded/unsplit device-bbox area ratio 1.9087. Routing overhead: strap bbox growth 0 um^2 (straps sit inside the pad columns), strap li1 7.812 um^2. The test tie is a harness artefact (the core already has one substrate tie), not part of the bank's cost.

**DRC**

| stream | klt drc --deck sky130 | PDK signoff runset (sky130A_mr.drc) |
|---|---|---|
| unsplit | clean (0) | licon.1 x8, rpm.1a x1 |
| folded | clean (0) | licon.1 x128 |
| broken | clean (0) | not run |
| unmerged | clean (0) | licon.1 x128, rpm.1a x16, rpm.2 x15 |

`unmerged` is an expected-to-fail DRC control: the folded bank with every strap but with the per-row psdm/rpm/urpm markers left as `res_array` draws them (no merge). It is not gated on the klt deck and gets no extraction or LVS. Rule classes the PDK signoff runset reports on it and not on `folded`: rpm.1a x16, rpm.2 x15.

klt deck rules that had geometry to check: `li1.enclosing.licon1.1`, `li1.space.1`, `li1.width.1`, `poly.enclosing.licon.1`, `poly.width.1`, `tap.enclosing.licon.1`, `tap.width.1`.

**LVS** (reference = one unsplit element, `options.combine_devices: true`)

| layout | status | devices L/R/matched | property errors |
|---|---|---|---|
| unsplit | match | 1/1/1 | - |
| folded | match | 1/1/1 | - |
| folded_perturbed | mismatch | 1/1/0 | r: layout 1.16048e+06 vs ref 1.16164e+06; p: layout 3013.44 vs ref 3000.84 |
| broken | mismatch | 2/1/0 | - |

**Extraction-side resistance** (klt deck: R = rho*L/W + fixed offset per drawn body)

- deck rho 324.827 ohm/sq, fixed offset 379.705 ohm
- unsplit: deck formula 1160477.0 ohm, extracted 1160477.0 ohm
- folded, per-primitive extraction summed: 1166172.6 ohm (+0.491% vs unsplit: (N-1) extra fixed offsets)
- folded, `--defer-resistor-fixed-offset` sum + one offset: 1160477.0 ohm (the convention `klt lvs` applies once per post-combine device)
- 15 internal joint net(s), `--parasitics` lumped R each: li1 37.79 ohm; poly head outside the body 280.93 ohm (the head is already represented by the PDK model's own head term, so only the li1 strap is added in the electrical comparison)

## Case `rbias_n4` -- R_BIAS as 4 series segments

- Schematic: `res_high_po` W=0.42 um, L=1500 um. Drawn: 4 segments x 375 um (sum 1500 um), W unchanged.
- Connections: segment i's `R<i>_B` pad joined to segment i+1's `R<i+1>_A` pad by one li1 strap spanning the row gap (3 straps, 1.5624 um^2 li1); chain ends labelled `A` (segment 0 `R0_A`) and `B`; one substrate tie labelled `SUB`. Exact strap coordinates: `geometry.json`.

**Area** (bounding rectangle, um / um^2)

| | width | height | area |
|---|---|---|---|
| unsplit device (as the core draws it) | 1500.84 | 0.42 | 630.353 |
| folded bank, generated | 375.84 | 2.88 | 1082.42 |
| folded bank, routed (straps + merged markers) | 375.84 | 2.88 | 1082.42 |
| unsplit + test substrate tie | 1500.84 | 2.92 | 4382.45 |
| folded + test substrate tie | 375.84 | 5.38 | 2022.02 |

Width reduced by 1125 um; folded/unsplit device-bbox area ratio 1.7172. Routing overhead: strap bbox growth 0 um^2 (straps sit inside the pad columns), strap li1 1.5624 um^2. The test tie is a harness artefact (the core already has one substrate tie), not part of the bank's cost.

**DRC**

| stream | klt drc --deck sky130 | PDK signoff runset (sky130A_mr.drc) |
|---|---|---|
| unsplit | clean (0) | licon.1 x8, rpm.1a x1 |
| folded | clean (0) | licon.1 x32 |
| broken | clean (0) | not run |
| unmerged | clean (0) | licon.1 x32, rpm.1a x4, rpm.2 x3 |

`unmerged` is an expected-to-fail DRC control: the folded bank with every strap but with the per-row psdm/rpm/urpm markers left as `res_array` draws them (no merge). It is not gated on the klt deck and gets no extraction or LVS. Rule classes the PDK signoff runset reports on it and not on `folded`: rpm.1a x4, rpm.2 x3.

klt deck rules that had geometry to check: `li1.enclosing.licon1.1`, `li1.space.1`, `li1.width.1`, `poly.enclosing.licon.1`, `poly.width.1`, `tap.enclosing.licon.1`, `tap.width.1`.

**LVS** (reference = one unsplit element, `options.combine_devices: true`)

| layout | status | devices L/R/matched | property errors |
|---|---|---|---|
| unsplit | match | 1/1/1 | - |
| folded | match | 1/1/1 | - |
| folded_perturbed | mismatch | 1/1/0 | r: layout 1.16048e+06 vs ref 1.16164e+06; p: layout 3003.36 vs ref 3000.84 |
| broken | mismatch | 2/1/0 | - |

**Extraction-side resistance** (klt deck: R = rho*L/W + fixed offset per drawn body)

- deck rho 324.827 ohm/sq, fixed offset 379.705 ohm
- unsplit: deck formula 1160477.0 ohm, extracted 1160477.0 ohm
- folded, per-primitive extraction summed: 1161616.1 ohm (+0.098% vs unsplit: (N-1) extra fixed offsets)
- folded, `--defer-resistor-fixed-offset` sum + one offset: 1160477.0 ohm (the convention `klt lvs` applies once per post-combine device)
- 3 internal joint net(s), `--parasitics` lumped R each: li1 37.79 ohm; poly head outside the body 280.93 ohm (the head is already represented by the PDK model's own head term, so only the li1 strap is added in the electrical comparison)

## Case `rfb_n2` -- R_FB_A as 2 series segments

- Schematic: `res_xhigh_po` W=0.42 um, L=180 um. Drawn: 2 segments x 90 um (sum 180 um), W unchanged.
- Connections: segment i's `R<i>_B` pad joined to segment i+1's `R<i+1>_A` pad by one li1 strap spanning the row gap (1 straps, 0.5208 um^2 li1); chain ends labelled `A` (segment 0 `R0_A`) and `B`; one substrate tie labelled `SUB`. Exact strap coordinates: `geometry.json`.

**Area** (bounding rectangle, um / um^2)

| | width | height | area |
|---|---|---|---|
| unsplit device (as the core draws it) | 180.84 | 0.42 | 75.9528 |
| folded bank, generated | 90.84 | 1.24 | 112.642 |
| folded bank, routed (straps + merged markers) | 90.84 | 1.24 | 112.642 |
| unsplit + test substrate tie | 180.84 | 2.92 | 528.053 |
| folded + test substrate tie | 90.84 | 3.74 | 339.742 |

Width reduced by 90 um; folded/unsplit device-bbox area ratio 1.483. Routing overhead: strap bbox growth 0 um^2 (straps sit inside the pad columns), strap li1 0.5208 um^2. The test tie is a harness artefact (the core already has one substrate tie), not part of the bank's cost.

**DRC**

| stream | klt drc --deck sky130 | PDK signoff runset (sky130A_mr.drc) |
|---|---|---|
| unsplit | clean (0) | licon.1 x8, urpm.1a x1 |
| folded | clean (0) | licon.1 x16, urpm.1a x1 |
| broken | clean (0) | not run |
| unmerged | clean (0) | licon.1 x16, urpm.1a x2, urpm.2 x1 |

`unmerged` is an expected-to-fail DRC control: the folded bank with every strap but with the per-row psdm/rpm/urpm markers left as `res_array` draws them (no merge). It is not gated on the klt deck and gets no extraction or LVS. Rule classes the PDK signoff runset reports on it and not on `folded`: urpm.2 x1.

klt deck rules that had geometry to check: `li1.enclosing.licon1.1`, `li1.space.1`, `li1.width.1`, `poly.enclosing.licon.1`, `poly.width.1`, `tap.enclosing.licon.1`, `tap.width.1`.

**LVS** (reference = one unsplit element, `options.combine_devices: true`)

| layout | status | devices L/R/matched | property errors |
|---|---|---|---|
| unsplit | match | 1/1/1 | - |
| folded | match | 1/1/1 | - |
| folded_perturbed | mismatch | 1/1/0 | r: layout 857143 vs ref 858000; p: layout 361.68 vs ref 360.84 |
| broken | mismatch | 2/1/0 | - |

**Extraction-side resistance** (klt deck: R = rho*L/W + fixed offset per drawn body)

- deck rho 2000 ohm/sq, fixed offset 0 ohm
- unsplit: deck formula 857142.9 ohm, extracted 857142.9 ohm
- folded, per-primitive extraction summed: 857142.9 ohm (-0.000% vs unsplit: (N-1) extra fixed offsets)
- folded, `--defer-resistor-fixed-offset` sum + one offset: 857142.9 ohm (the convention `klt lvs` applies once per post-combine device)
- 1 internal joint net(s), `--parasitics` lumped R each: li1 37.79 ohm; poly head outside the body 280.93 ohm (the head is already represented by the PDK model's own head term, so only the li1 strap is added in the electrical comparison)

## Electrical comparison (single operating point)

One ngspice `.op`, `tt`, 27 C, bulk at 0 V, DC voltage forced across each variant (see `cases.json`). N=1 is the unsplit schematic device; `+li1` variants insert the measured per-joint li1 strap resistance (R_BIAS: 37.79 ohm, R_FB_A: 37.79 ohm) at each joint. Deck: `electrical/op.cir`; log: `electrical/op.log`.

| device | N | segment L (um) | joints | V | R_eff (ohm) | delta (ohm) | delta | tolerance | verdict |
|---|---|---|---|---|---|---|---|---|---|
| R_BIAS | 1 | 1500 | model only | 2 | 1215106.7 | +0.0 | +0.000% | 0.246% | EQUIVALENT |
| R_BIAS | 2 | 750 | model only | 2 | 1215927.9 | +821.2 | +0.068% | 0.246% | EQUIVALENT |
| R_BIAS | 2 | 750 | +li1 | 2 | 1215965.7 | +859.0 | +0.071% | 0.246% | EQUIVALENT |
| R_BIAS | 4 | 375 | model only | 2 | 1217570.4 | +2463.7 | +0.203% | 0.246% | EQUIVALENT |
| R_BIAS | 4 | 375 | +li1 | 2 | 1217683.7 | +2577.0 | +0.212% | 0.246% | EQUIVALENT |
| R_BIAS | 8 | 187.5 | model only | 2 | 1220855.2 | +5748.5 | +0.473% | 0.246% | NOT EQUIVALENT |
| R_BIAS | 8 | 187.5 | +li1 | 2 | 1221119.8 | +6013.1 | +0.495% | 0.246% | NOT EQUIVALENT |
| R_BIAS | 16 | 93.75 | model only | 2 | 1227425.0 | +12318.3 | +1.014% | 0.246% | NOT EQUIVALENT |
| R_BIAS | 16 | 93.75 | +li1 | 2 | 1227991.8 | +12885.1 | +1.060% | 0.246% | NOT EQUIVALENT |
| R_BIAS | 32 | 46.875 | model only | 2 | 1240564.5 | +25457.8 | +2.095% | 0.246% | NOT EQUIVALENT |
| R_BIAS | 32 | 46.875 | +li1 | 2 | 1241736.0 | +26629.3 | +2.192% | 0.246% | NOT EQUIVALENT |
| R_FB_A | 1 | 180 | model only | 0.6 | 1040766.4 | +0.0 | +0.000% | 1.601% | EQUIVALENT |
| R_FB_A | 2 | 90 | model only | 0.6 | 1040556.2 | -210.2 | -0.020% | 1.601% | EQUIVALENT |
| R_FB_A | 2 | 90 | +li1 | 0.6 | 1040594.0 | -172.4 | -0.017% | 1.601% | EQUIVALENT |
| R_FB_A | 3 | 60 | model only | 0.6 | 1040400.8 | -365.6 | -0.035% | 1.601% | EQUIVALENT |
| R_FB_A | 3 | 60 | +li1 | 0.6 | 1040476.3 | -290.0 | -0.028% | 1.601% | EQUIVALENT |
| R_FB_A | 4 | 45 | model only | 0.6 | 1040259.0 | -507.4 | -0.049% | 1.601% | EQUIVALENT |
| R_FB_A | 4 | 45 | +li1 | 0.6 | 1040372.4 | -394.0 | -0.038% | 1.601% | EQUIVALENT |
| R_FB_A | 6 | 30 | model only | 0.6 | 1039989.1 | -777.2 | -0.075% | 1.601% | EQUIVALENT |
| R_FB_A | 6 | 30 | +li1 | 0.6 | 1040178.1 | -588.3 | -0.057% | 1.601% | EQUIVALENT |

## Reproduce

```bash
layout/bin/setup-venv.sh
layout/.venv/bin/python layout/bin/run-folded-res-qual-flow.py
```
