# Capacitor-implementation comparison: 20261011-094917-7a4e0cc

Issue #319. This is a **study only**. It changes nothing in `spec/target-spec.md`, `design/`, or any existing `layout/` or `sim/` record. The ratified Area row (`< 0.1 mm^2`, strict) is unchanged. This record does not claim that the core meets it.

**Outcome: (c) inconclusive/unmeasured.** See the last section.

`matrix.json` is the machine-readable form of everything below. `python3 layout/cap-study/run-cap-study.py matrix --record <this dir>` regenerates it byte for byte from the pinned PDK and the evidence in this directory. The file holds no timestamps.

## Provenance

- Minted 2026-10-11 09:49 UTC, on top of `7a4e0cc` (branch `feature/issue-319`).
- PDK: `sky130A` at open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b`, which matches the pin in `sim/pdk.json` (`matrix.json` `pdk.matches_pin: true`). No cross-variant evidence is used. PDK files are cited as `sky130A/...`, relative to `$PDK_ROOT`.
- Schematic: `design/ldo_3v3in_1v8out.sch` at `a09aa83`. It is netlisted through the unchanged testbench `sim/load-regulation/testbench/tb_load_regulation.sch` by xschem with the repo's `sim/xschemrc`. The snapshot is `op/netlist.spice`.
- Tools: klt `0.7.0+g612109ec5754` (host). Local ngspice `ngspice-42`, which matches the `tools.ngspice` pin. ngspice init lines come from `sim/spiceinit`.
- Read-only inputs:
  - `layout/area-study/20261009-study-246/budget.json`: scenario D, and E1/E2 at 0.1464 / 0.1059 mm^2.
  - `layout/cap-rail-demo/reports/20261010-033947-80bc87e/summary.json`: #254, the `LATEST` record.
  - `sim/loop-gain/records/20260926-040338-4a9ec09.json`: loop crossover frequency.

## Conventions

- **Cells.** Every number in `matrix.json` is `{"value", "unit", "source"}`. The `source` names a PDK file and parameter, a run directory in this record, or an existing repo record. Anything that was not measured and is not stated by a PDK file is `{"value": "unmeasured", "reason": ...}`. No density is estimated.
- **Area accounting** is the #246 convention, so the figures compare directly with E1/E2:
  - Drawn-capacitor area = C / areal density. This leaves out spacing, routing, the MiM perimeter/`dw` term and keep-out.
  - "Beside" total = scenario D (65400.3 um^2, the core without capacitors) + drawn area.
  - A keep-out-inclusive figure is reported only where a drawn record measured one. That is the #254 stacked-MiM blocks, which include straps and taps.
- **Budget.** C_COMP 150 pF + C_SS 10 pF + C_CL 1 pF + C_TS 1 pF = 162 pF. These values and terminals are read from the netlist (`op/terminals.json`), not typed in:

| Cap | Terminals (netlist) | Value |
|---|---|---|
| C_COMP | VOUT - EA_CZ | 150 pF |
| C_SS | SS - 0 | 10 pF |
| C_CL | VIN - CL_CMP | 1 pF |
| C_TS | VIN - TS_CMP | 1 pF |

- **Corners.** The capacitance-skew corners are `ll`/`hh` (`sim/pdk.json` `process_corners`). For MiM and vpp they come from the PDK's own `cap_low`/`cap_high` parameter files.

## Comparison matrix (162 pF)

| Option | Density tt / ll / hh (fF/um^2) | Drawn area tt / ll / hh (um^2) | Beside the core, tt (um^2) | Metal levels | Over the core (#254 rails) | Requalification | Verdict |
|---|---|---|---|---|---|---|---|
| MiM `cap_mim_m3_1`, one level | 2.00 / 1.78 / 2.23 | 81000 / 91011 / 72646 | 146400 (= E1), >= limit | met3, capm, via3, met4 | Conflicts: met3 is the VIN-rail column. One level needs 89038 um^2 of blocks, more than the 71492 um^2 overlay area (#254 arithmetic) | Parasitics of the final placement only | not-established |
| Stacked MiM `cap_mim_m3_1` + `cap_mim_m3_2` | 4.00 / 3.56 / 4.46 | 40500 / 45506 / 36323 | 105900 (= E2), >= limit | met3, capm, via3, met4, capm2, via4, met5 | **Drawn by #254**: DRC clean (klt + official `sky130A_mr.drc`), LVS match. Blocks 44830 um^2 (3.61 fF/um^2 incl. straps/taps) inside a 76813 um^2 planned core rectangle | Required. Plate coupling and full-core parasitics are owned by #231 | fits (conditional, see below) |
| `cap_vpp`, densest cell `44p7x23p1_pol1m1m2m3m4m5_noshield` | 1.43 / 1.14 / 1.71 | 113420 / 141775 / 94517 | 178820, >= limit | poly, li1, met1-met5 | Conflicts: every evaluated cell uses li1/met1/met2, the device and rail levels | Required (new device, plate-to-substrate C, series R) | does-not-fit |
| MOS varactor `cap_var_lvt`/`_hvt`, gate area only | 8.18-8.22 accumulation; 0.74-1.25 depletion (w=l=10, tt/27 C) / ll, hh **unmeasured** | 19713 at Cmax, 129107 at Cmin (tt) / ll, hh **unmeasured** | 85114 at Cmax, gate area only. Footprint **unmeasured** | nwell, diff, poly, li1, met1 | Conflicts: front-end device, cannot sit over the MOS rows | Required (C(V), SOA, junction to substrate, series R) | not-established |

How each number is sourced:

- **MiM.** The density is `sw_cap_mim_ca` from `sky130A/libs.tech/combined/continuous/parameters_cap_{nom,low,high}.spice`. It is evaluated at `corner_factor=1` with the Monte Carlo switches off.
  - The subcircuit law in `continuous/models_capacitors.spice` is checked by the script to be `C = sw_cap_mim_ca*(w+dw)*(l+dw)` for both `cap_mim_m3_1` and `cap_mim_m3_2`. Both classes use the **same** `sw_cap_mim_ca`.
  - This settles the issue's open question: by the pinned model, two levels in one footprint give 4.00 fF/um^2. The "4 fF/um^2" that #246 E2 assumed is the model value. The drawn #254 arrays reach 3.61 fF/um^2 once straps and taps are counted.
  - The model has no voltage or temperature term.
  - Per-capacitor split at tt: one level is 75000 / 5000 / 500 / 500 um^2; stacked is 37500 / 2500 / 250 / 250 um^2.
- **vpp.**
  - The density is the model's `ctot_a` evaluated with the per-cell corner factors of `combined/rescap/res_{typical__cap_typical,low__cap_low,high__cap_high}__lin.spice`, divided by the bounding box of the PDK's own flat `.mag` cell (`libs.ref/sky130_fd_pr/mag/`).
  - For every cell, the model's `rat_*` split is checked to sum to 1, so `ctot_a` is the whole plate-to-plate capacitance.
  - 46 vpp models are included by the pinned combined library. 39 have both an evaluable `ctot_a` and a flat `.mag` cell, and all 39 are listed in `matrix.json` (`options[vpp].cells_evaluated`). The other 7 are recorded `unmeasured` with their reason.
  - Selection rule: the densest cell by tt `ctot_a` / bounding-box area. That is `sky130_fd_pr__cap_vpp_44p7x23p1_pol1m1m2m3m4m5_noshield`: 1.47 pF in 44.65 x 23.05 um, with 111 cells for 162 pF.
  - The densest cell that leaves met3-met5 free is `11p5x11p7_l1m1m2_noshield` at 0.71 fF/um^2.
- **Varactor.** The density comes from the C(V) sweep below. "Gate area" is w x l. The device needs nwell, diffusion, contacts and a tap around the gate. That footprint is **unmeasured**: the PDK ships no fixed layout cell for it, and klt has no generator (klayout-tools#3100). So 19713 um^2 is a lower bound, not a footprint.

### What the verdicts mean

- **Stacked MiM, "fits".** A drawn, DRC/LVS-checked record (#254) holds all four capacitors over a planned core rectangle that is 23% below the limit. This study adds no new layout to that. The verdict carries #254's own conditions:
  - the MOS domain keeps its measured width;
  - #253's folded resistors add at most about 2039 um^2 (the core rectangle becomes about 0.0789 mm^2);
  - coupling to the device row and its electrical effect are not quantified (#231);
  - the planned core is not the real full-core layout.

  At the `ll` corner the same drawn arrays are about 11% low in value. Holding 162 pF at `ll` would take 45506 um^2 of capacitor instead of 40500. That is about 5000 um^2 more of the 71492 um^2 overlay area, and it is arithmetic, not drawn.
- **One-level MiM, "not-established" rather than "does-not-fit".** Beside the core it is 146400 um^2, and it cannot all go over the core. But part of the budget over the core and the rest beside it is geometrically possible, and no record has drawn or priced that. Missing evidence is not a no-fit.
- **vpp, "does-not-fit".** The drawn-area lower bound beside the core breaks the limit even at the `hh` (high-C) corner: 65400 + 94517 = 159917 um^2. Every cell occupies the device and rail levels, so it cannot go over the core.
  - Not evaluated, and recorded as unmeasured: a li1-met2 vpp with a stacked MiM above it, beside the core. That arithmetic is 4.00 + 0.71 = 4.71 fF/um^2, so 34400 um^2 + D = 99800 um^2, which is marginal before any keep-out. The combination has no drawn cell, DRC or model-coupling evidence.
- **Varactor, "not-established".** The operating-point matrix behind its C(V) is 2/126 complete, and its footprint is unmeasured. Even so, the measured point already rules it out for one capacitor (next section).

## Operating points (terminal voltages)

**Contract.** Each point is the repo's cold-start settled operating point (#171): `tran 10u 200m uic` with EN stepping high at 101 us, and every terminal averaged over 199-200 ms. It is not a bare `.op`, which is not a physically realisable state of this block (#164). The xschem netlist identifies terminals only. Voltages come from these simulations. Requests: `op/requests/v<supply>_<load>.{json,spice}`, each covering 7 process corners x 3 temperatures.

**Matrix status: 2 of 126 points measured.** The full table is in `matrix.json` `operating_points`.

- **Batch.** `v2.97_0ma` was submitted with `klt sim --backend batch` as job `klt-sim-b5af2f44739e` (`op/batch/v2.97_0ma/`). The fleet runner refused it before simulating: exit 87, `batch_runner_version_mismatch`, runner klt 0.5.0 vs client 0.7.0+g612109ec5754 (klayout-tools#2948, still open; reproduction added there). Its 21 points are `unmeasured` ("not simulated").
  - A second request (`v2.97_50ma`) was started and then stopped by this Builder before it returned, because the same runner would refuse it. Its client process was killed, it left no artifacts, and no job id was captured.
  - The other four requests were not submitted.
  - **No local fallback**: the grid was not run on this host (host rules).
- **Local.** Two single-unit probes were run with `klt sim --backend local` at the nominal point (`op/local/`). Both converged (`status: pass`, no solver diagnostics), each in about 6 s:

| Point | VOUT | EA_CZ | SS | CL_CMP | TS_CMP | C_COMP plate (VOUT-EA_CZ) | C_SS | C_CL (VIN-CL_CMP) | C_TS (VIN-TS_CMP) |
|---|---|---|---|---|---|---|---|---|---|
| tt / 27 C / 3.30 V / 0 mA | 1.80239 | 2.76571 | 3.29999 | 3.30000 | 3.26895 | -0.963 V | 3.300 V | 0.000 V | 0.031 V |
| tt / 27 C / 3.30 V / 50 mA | 1.79883 | 1.93854 | 3.29999 | 3.25775 | 3.26955 | -0.140 V | 3.300 V | 0.042 V | 0.030 V |

VOUT at 0 mA (1.80239 V) agrees with the 199-200 ms value the load-regulation bench documents for this point. That is a consistency check on the deck, not new spec evidence.

The other 124 points are `unmeasured`. 103 of them were never submitted, and 21 were submitted but not simulated. No plate voltage has been inferred from connectivity.

## Varactor C(V)

**Deck.** `cv/netlist.spice` puts each (flavor, geometry, bias) point on its own device:
- c0 is the plate under test, with c1 and b at 0.
- The DC bias comes through 1 Tohm, and the device is driven by a 1 A AC current source, so C = -1 / (2 pi f Im V).
- The bias steps by 0.1 V across -2.3 V to +2.3 V. That is the model's own SOA, `sky130_fd_pr__cap_var_{lvt,hvt}__vgs_{min,max}` = -/+2.301 V.
- It is reported at 1 kHz and at 178273 Hz, the loop crossover frequency below.

**Run.** Only tt / 27 C was run, as a single unit through `klt sim --backend local` (`cv/local_tt_27c/`). The corner x temperature grid was **not submitted**, because the batch runner refuses this client (see above), so ll/hh and the other corners are `unmeasured`.

From the PDK files, not simulated:
- the `ll`/`hh` library sections include `corners/tt.spice`, so they carry the tt varactor parameters;
- the ss/ff/sf/fs corners scale `cnwvc_tox` by +6%/-4.8%;
- the charge equation has no `temper` term, and only the series resistance has one (`rg_tcmult`).

| Device (w x l um) | Cmax (fF/um^2 of gate) | Cmin (fF/um^2) | C at 178 kHz vs 1 kHz |
|---|---|---|---|
| lvt 10 x 10 | 8.18 | 0.74 | < 1e-5 relative |
| hvt 10 x 10 | 8.22 | 1.25 | < 1e-5 relative |
| lvt 5 x 0.5 (model default) | 8.86 | 1.71 | 1.4e-3 |
| hvt 5 x 0.5 | 8.89 | 2.17 | 8.6e-4 |

**At the measured bias** (tt/27 C, the 2 measured points only). The density at the measured plate voltage is listed for each capacitor, for both choices of which plate is the gate (`matrix.json` `options[mos_varactor].cv_tt_27c.*.at_bias`):

- **C_SS: outside the varactor SOA in both orientations.** SS sits at 3.30 V, above the 2.301 V model limit. This is a measured exclusion at this point, not an inference: a 1.8 V-oxide varactor cannot implement C_SS as connected, so C_SS would need another device.
- **C_COMP: strongly load-dependent.** With the gate on EA_CZ (accumulation side), hvt 10 x 10 gives 8.13 fF/um^2 at 0 mA and 3.55 fF/um^2 at 50 mA, a factor of 2.3 between the two loads at one corner. With the gate on VOUT it stays near depletion (1.58-1.87 fF/um^2).

  The loop's unity-gain frequency is Gm/(2 pi C_COMP) (`design/ldo_3v3in_1v8out.sch`). So a varactor C_COMP would shift the loop crossover with load, and that needs a stability requalification. Whether any orientation holds over all 126 points is **unmeasured**.
- **C_CL, C_TS**: the plates sit within 0.05 V of each other, in the steep part of the curve. The 10 x 10 devices give 0.9-2.6 fF/um^2, depending on flavor and orientation. These are inside the SOA at the measured points.

**Loop crossover frequency.** It comes from `sim/loop-gain/records/20260926-040338-4a9ec09.json`, measurement `fc_c033_50ma_hz`: 178273 Hz at tt/27 C/3.30 V, and 136-221 kHz over its 45 corners. That record predates the schematic's current revision (`a09aa83`, #230), so the frequency is cited, not re-measured. Over this range the varactor, MiM and vpp models are effectively frequency-independent.

## Overlay with the #254 rail plan

#254 already drew stacked MiM over the rails. This study does not redo that. It says only what the other options change against the #254 metal assignment (`layout/cap-rail-demo/README.md`):

- **One-level MiM.** Same levels as #254's lower MiM (met3 bottom plate). It frees met5 but does not fit in the overlay area by itself.
- **vpp.** Every included cell uses li1/met1/met2. Those levels carry the device pads, signal trunks, risers and the VOUT/VIN rail levels over the pass device, so a vpp cannot overlay the core in the #254 plan. The densest cells also use met3-met5, which collides with the MiM levels. A li1-met2-only cell (0.71 fF/um^2 or less) would leave met3-met5 free, but only beside the core.
- **Varactor.** No metal-stack conflict above met1. But it needs substrate area (nwell + diffusion) beside the MOS rows, so it cannot reuse the core footprint the way the MiM overlay does.

## Tool friction (filed generically, no design content)

- [2AMLogic/klayout-tools#3100](https://github.com/2AMLogic/klayout-tools/issues/3100) (new) covers three gaps:
  - `klt gen` cannot place or array a PDK's fixed-layout capacitor cells (the vpp cells);
  - it has no varactor primitive;
  - `--list-pdk-pcells` loads no sky130A PCells without `gdsfactory`.
- [2AMLogic/klayout-tools#2948](https://github.com/2AMLogic/klayout-tools/issues/2948): the batch runner/client version mismatch, reproduced again here and commented with the job id.
- Related, already open: [#2953](https://github.com/2AMLogic/klayout-tools/issues/2953) (no MOS-capacitor primitive) and [#3022](https://github.com/2AMLogic/klayout-tools/issues/3022) (`cap_array` has no stacked mode).

## matrix.json schema (`sky130-ldo/cap-study-matrix/1`)

| Key | Content |
|---|---|
| `pdk` | variant, pinned and installed open_pdks commit, `matches_pin` |
| `capacitors`, `total_f` | budget read from the netlist |
| `reference` | limit, scenario D / E1 / E2 and their sources, the area convention |
| `loop_unity_gain` | crossover frequency and its source record |
| `options[]` | one row per option: `density_f_per_um2`, `area_162pf_um2`, `beside_total_um2` (per corner, as cells), `split_area_tt_um2`, `metal_levels`, `overlay`, `requalification`, `verdict`, `verdict_reason` |
| `options[vpp].cells_evaluated` | every included vpp model: `ctot_f`, `bbox`, `density_f_per_um2`, `rat_sum` |
| `options[mim_stacked].drawn_evidence` | the #254 record's measured figures |
| `options[mos_varactor]` | `plate_voltage_range`, `cv_tt_27c` (`at_bias` by orientation), `soa`, `soa_excluded_at_measured_points` |
| `operating_points` | all 126 points (measured or `unmeasured` with a reason), plus `submissions` (backend, job ids, runner versions) |
| `varactor_cv` | every C(V) curve run (bias, C at each frequency) |
| `verdicts`, `evidence_gaps`, `outcome` | the outcome rule's inputs and result |

Verdict rule (`layout/cap-study/_cap_study.py` `fit_verdict` / `outcome`, unit-tested):

- `fits` needs a drawn overlay record below the limit.
- `does-not-fit` needs the drawn-area lower bound to break the limit **and** no overlay possibility.
- Anything else is `not-established`.
- Outcome (a) or (b) needs complete evidence, and (b) additionally needs every option to be `does-not-fit`. Missing evidence always gives (c).

## Reproduce

See `commands.md` in this directory. In short, `prepare` -> `op` (batch) / `op-local` (one point) -> `cv` -> `matrix`. Re-running `matrix` reproduces `matrix.json` byte for byte. That was checked: the sha256 was identical across two runs.

## Outcome: (c) inconclusive/unmeasured

**Missing evidence:**

1. The operating-point matrix: 124 of 126 points are unmeasured. The fleet runner refuses this client (klayout-tools#2948), and the host rules forbid running the grid locally.
2. The varactor C(V) over process and temperature, including ll/hh.
3. The varactor cell footprint: the PDK has no fixed cell and klt has no generator (klayout-tools#3100).
4. A priced mixed placement for one-level MiM.

**Next measurement:** when the batch runner matches the client, run this record's prepared `op` requests and the `cv --backend batch` grid in a **new** record directory, then re-run `matrix`. Tracked in #341 (`loom:triage`).

**Provisional, not a recommendation:**
- Stacked MiM over the core is the only option with drawn, DRC/LVS-clean evidence below the limit (#254, conditional on that record's assumptions).
- vpp cannot reach the limit by drawn-area lower bound, even at `hh`.
- A varactor cannot implement C_SS at the measured nominal point (SOA), and as C_COMP it would vary about 2.3x with load at that point.

No option is declared to fit or to not fit beyond the cells above. No decision record is proposed, because outcome (b) is not supported. Nothing in the spec is changed.
