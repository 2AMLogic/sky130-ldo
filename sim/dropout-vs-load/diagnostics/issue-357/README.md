# Issue #357: physical low-headroom amplifier + re-referenced clamp candidate (dropout screen)

This is a diagnostic, not a record. It is not part of any characterization selection and makes no
spec, DR or production change. The electrical condition is **tt / 27 C** throughout. Two supplies
are used: the dropout bench's own 3.30 V start, and 2.10 V as the candidate's claimed low-VIN
operating point (1.8 V + the 0.300 V target). Thermal runs impose the device temperatures listed
in section 3. There is no PVT, no Monte Carlo and no fleet: every run is one local `ngspice -b`,
executed sequentially. The ratified `< 300 mV` dropout row and its PVT gap (#114) are unchanged.
**A tt pass here does not qualify dropout over PVT.** The candidate exists only as a
netlist-level edit of bench copies: `design/ldo_3v3in_1v8out.sch`, every `experiment.json`,
`spec/` and all earlier diagnostics (`../issue-323/`, `../issue-339/`) are untouched.

## 1. Files

| file | purpose |
|---|---|
| `candidate.py` | the candidate as an exact-card-matched DUT transformation (`apply_candidate`) plus structural invariants (`check_candidate`); revision table `REV` |
| `probe.py` | one bench, one condition, one `ngspice -b` per call. Netlists the repo testbench with the repo xschem flow (`corner-run.py` via `sim/bin/_probe_common.py`), applies the candidate, writes `runs/<id>/` |
| `analyze.py` | dropout validity gates (#339's `analyze_tran`, imported read-only) + run-level gates + derived measurements + pair/repeat checks |
| `summarize.py` | manifest grading and pre-existing / REGRESSION / fixed / INVALID classification, producing `summary.txt` |
| `sizing.py` | isolated DC device benches used to derive the bias numbers (never graded) |
| `replay339.py` | replays a committed #339 deck verbatim (tool-version anchor) |
| `commands.sh` | the declared, as-executed command sequence, including deviations |
| `runs/<id>/` | per run: `netlist.raw.spice`, `netlist.edited.spice`, `netlist.diff`, `deck.spice`, `ngspice.log`, `result.json` (hashes, tools, PDK, command); dropout runs also have `data.dat.gz`, `data.columns.json`, `analysis.{json,txt}` |
| `summary.txt`, `pair_dropout_r{0,1}.txt`, `repeat_*.txt` | generated tables |
| `../../../tests/test_dropout_candidate_357.py` | 40 fixtures (transformation, invariants, validity, classification, byte-identical regeneration of every committed candidate netlist) |

## 2. The candidate circuit (clean-room, derived from #339's measured mechanism)

#339 identified the mechanism. The PMOS-input pair has its gates at VREF = 1.2 V, so the tail
node sits at about VREF + |Vgs_p| = 2.53 V (measured pre-ramp, 3.3 V). The PMOS tail therefore
needs VIN >~ 2.6 V, and at the baseline crossing (VIN 2.16 V) it has collapsed: Vds - Vdsat =
-0.068 V and 0.31 uA instead of 3.27 uA. In addition, the clamp reference XM_CLP is mirrored from
the VIN-scaled R_BIAS current, so the clamp threshold falls with VIN. Both changes are applied
together (#339: neither alone suffices).

**A. NMOS-input symmetrical OTA.** This replaces XM_TAIL, XM_IN1, XM_IN2, XM_IN2S, XM_MIR1-4 and
XM_MIRP1/2. The tail node sits below the input common mode (NTAIL about VREF - Vgs_n = 0.26 V,
measured), so the amplifier's compliance no longer involves VIN - VREF.

| device | type | W/L [um], nf | D G S B | role |
|---|---|---|---|---|
| XM_NTAIL | nfet_g5v0d10v5 | 12/2, 3 | NTAIL NBR AMP_ENN 0 | tail sink |
| XM_NIN1 / XM_NIN2 | nfet | 10/2, 2 | NX1 FB NTAIL 0 / NX2 VREF NTAIL 0 | input pair |
| XM_NIN2S | nfet | 10/1, 2 | ND2 SS NX2 0 | soft-start, in **series** on the VREF side |
| XM_NIN1C | nfet | 10/1, 2 | ND1 VIN NX1 0 | matching series device on the FB side |
| XM_PD1 / XM_PO1 | pfet | 20/4, 4 | ND1 ND1 VIN VIN / EA_OUT ND1 VIN VIN | FB-side mirror; PO1 pulls EA_OUT **up** |
| XM_PD2 / XM_PO2 | pfet | 20/4, 4 | ND2 ND2 VIN VIN / NM ND2 VIN VIN | VREF-side mirror |
| XM_NMD / XM_NMO | nfet | 10/4, 2 | NM NM AMP_ENN 0 / EA_OUT NM AMP_ENN 0 | NMO pulls EA_OUT **down** |

Polarity: FB up raises the XM_NIN1 current, PO1 pulls up harder, EA_OUT rises and the pass turns
off. With NMOS inputs a parallel SS device would select max(VREF, SS). A **series** SS device
starves the reference side while SS < VREF, so the loop tracks about min(VREF, SS) as the PMOS
parallel device did. Once SS has charged to about VIN, both series devices are triode switches.
XM_ENP5 keeps its role, the EN-low pull-up of the pull-up mirror's gate, on the renamed node ND1.

**B. VREF-referenced bias + re-referenced clamp.** The relationship is I_R = (VREF -
Vgs(XM_VRF)) / R_VR; VREF drives gates only. XM_CLP keeps its drain, source and geometry, but its
gate moves from BIASP (the VIN-scaled R_BIAS mirror) to PBR.

| device | rev0 | rev1 | D G S B |
|---|---|---|---|
| XM_VRF nfet | 10/1, nf 2 | same | PBR VREF NVR 0 |
| XR_VR res_high_po W=0.42 | L=169 um (137 kOhm) | L=550 um (~424 kOhm) | NVR AMP_ENN |
| XM_PBR pfet (diode) | 10/1, nf 2 (= XM_BIASP1) | 2.5/1, nf 1 | PBR PBR VIN VIN |
| XM_PBN pfet | 5/1, nf 1 | 1.75/1, nf 1 | NBR PBR VIN VIN |
| XM_NBR nfet (diode) | 4/2, nf 1 | 2.5/2, nf 1 | NBR NBR AMP_ENN 0 |
| XM_CLP (existing) | gate BIASP -> PBR | same | CL_CMP PBR VIN VIN |
| XM_ENP6 / XM_ENP7 | (none) | copies of XM_ENP5 | PBR EN VIN VIN / ND2 EN VIN VIN |

**Unchanged, verified by `check_candidate` in every run** (byte-identical cards): XM_PASS
(`pfet_g5v0d10v5` L=0.5 W=100 nf=25 m=50, `VOUT EA_OUT VIN VIN`); every DUT port; R_BIAS, NB and
BIASP; XM_SENSE, XM_CLN1, XM_CLN2, XM_CLIM, XM_ENP3 and C_CL; the whole thermal block plus XM_TSHUT
and XM_ENP4; soft-start (XM_SSCHG, XM_SSDIS, C_SS); EN gating; C_COMP and R_CZ; the divider. Every
new device is a sky130 g5v0d10v5 device, bodies are tied to VIN or 0, and power comes only from
VIN, returning to the EN-gated AMP_ENN. There is no auxiliary rail, and VREF, FB, SS and EN are
gate-only. Each run's `netlist.diff` is the retained diff.

**Expected compliance (sizing benches, `runs/sz0*`, DC, tt/27 C).** The bias chain is flat down
to VIN = 1.6 V. For rev1 (sz06): tail 3.25 uA at 3.3 V vs 2.94 uA at 1.9 V; clamp reference
(into 1.0 V) 2.37 vs 2.12 uA. For the amplifier, with ND = VIN - |Vgs_PD| (about 1.13 V at
1.6 uA), NX about ND, and NTAIL 0.26 V, the input devices keep Vds of about VIN - 1.4 V. That is
0.48 V at the rev1 crossing (VIN 1.927), measured.

**Current budget (rev1, measured in-circuit at the pre-ramp 3.3 V / 50 mA point, d05).** Tail
3.16 uA (pair 1.60 / 1.55 uA). Output stage: PO2 to NMD 1.60 uA, plus PO1/NMO 1.61 uA. V-to-I I_R
0.73 uA. XM_PBN to XM_NBR 0.68 uA. Against the baseline amplifier (tail 3.27 + MIRP1 branch 1.65
+ output 1.65 uA), the candidate adds about 1.2 uA, all of it inside the Iq measurement (VIN is the
only supply). rev0 added about 3.2 uA (I_R 2.07 + XM_PBN 1.14 uA).

## 3. Declared before execution (committed in c2ecfeb before any loop run)

- **Dropout stimulus**: the `sim/dropout-vs-load` manifest deck, regenerated fresh: cold-start
  `tran 10u 14m uic`, EN at 100 us, ILOAD 0 -> 50 mA over 2.5-2.6 ms, VIN 3.3 -> 1.17 V over
  6-14 ms, crossing `v(vout)=1.764 fall=1 td=6m`. The only additions are `save` and `wrdata`
  instrumentation (tested).
- **Validity gates**: #339's, plus ngspice exit 0, `corner-run.py`'s solver-diagnostic markers, and
  data present and parseable. Derived measurements exist only for valid runs.
- **Tolerances**: repeat |d dropout| <= 0.5 mV (#339 precedent) and |d EA_OUT@x| <= 1.0 mV. VREF
  settled DC current <= 1 nA. Thermal pass-off: |Id(M_PASS)| < 1 uA while tripped.
- **Protection, Iq and EN**: the manifest decks, verbatim. Current-limit uses forced-output DC +
  held short. Iq uses the 0/50 mA 200 ms settled transients. EN uses the full cycle + static
  disabled legs. Current-limit and Iq run at 3.30 V and at 2.10 V; enable-shutdown at 3.30 V.
- **Thermal stimulus**: `run_hysteresis.py`'s two-state transient (`cold`, `hot` = +0.5 uA sink on
  TS_SNS at 20-40 us, `cold_exc` = -0.5 uA, `en` = EN dip 101-115 us). The device temperatures are
  **imposed by `.temp`**: 27, 150, 166 and 185 C. They are chosen around the recorded tt/3.3 V
  window (reset 159.2 C, trip 172.3 C, `sim/thermal/hysteresis/20261008-190150-0275a8b-dev1`).
  Both supplies are used, and the electrical corner stays tt. No new trip, hysteresis or
  current-limit bound is imposed.

## 4. Results

Full tables: `summary.txt` (generated), `pair_dropout_r0.txt` and `pair_dropout_r1.txt`.

**Tool anchor.** The committed #339 `probe0` deck, replayed verbatim on this host's ngspice-46,
gives 0.397658197 V, identical to #339's ngspice-42 result to the last printed digit. The `.dat`
bytes differ (wrdata formatting), but the numbers do not. A fresh xschem-3.4.7 netlist differs
from #339's 3.4.4 deck only in line wrapping and in the printed precision of five nrd/nrs values
(for example 0.690476 vs 0.69047619047619). Exact-card matching is therefore token-level
(wrap-independent, tested).

**Dropout (all VALID; every repeat byte-identical, d = 0.0000 mV).** "x" is the crossing.

| run | dropout [V] | VIN@x [V] | EA_OUT@x [V] | tail Id@x | tail Vds-Vdsat@x [V] | pull-down Vds-Vdsat@x [V] | M_CLIM Id@x | VOUT @ VIN=2.064 V |
|---|---|---|---|---|---|---|---|---|
| d01b_base (current DUT) | **0.397658** (FAIL) | 2.1617 | 0.711 | 0.31 uA | -0.068 | +0.653 | 49 nA | 1.607 V |
| d02_cand_r0 | **0.166674** (< 0.300) | 1.9307 | 0.124 | 2.92 uA | +0.156 | +0.003 | 259 nA | 1.793 V |
| d05_cand_r1 | **0.163237** (< 0.300) | 1.9272 | 0.103 | 2.83 uA | +0.159 | -0.016 | 141 nA | 1.793 V |
| #339 ideal-tail + no-clamp (reference only) | 0.164028 | 1.9280 | 0.107 | ideal | - | - | 0.004 nA | - |

The physical candidate reaches the dropout that #339's ideal combination reached, but with real
devices, VIN-only power and functioning protection. At VIN = 2.064 V (the edge a passing part must
hold) the candidate still regulates at 1.793 V, with the clamp off (Vsg(M_CLIM) = 0.062 V). The
baseline has already dropped to 1.607 V there. The **new floor at the crossing has two causes**:
(i) gate range: the pull-down XM_NMO is in triode at EA_OUT = 0.10 V, the same floor #339 saw;
(ii) clamp onset: in deep dropout the saturated sense FET over-reports load current (28 uA sense
current at 50 mA, vs 12.8 uA in regulation), so the comparator reaches its threshold (CLN2 =
CLP = 2.02 uA) and M_CLIM starts to conduct. VREF draws no settled DC current (3.5e-17 A).
VOUT in regulation shifts by +3.7 mV (1.8026 vs 1.7988 V at 3.3 V / 50 mA), from the new pair's
systematic offset. It stays inside the ratified window.

**Manifest grading (unchanged bounds; `summary.txt`).** Classification is relative to the paired
baseline at the same supply:

| bench @ supply | rev0 | rev1 |
|---|---|---|
| current-limit 3.3 V | all pass; short 147.4 mA (base 153.3), knee 119.4 (123.7) | all pass; short **152.5**, knee **123.7** |
| current-limit 2.1 V | `vout_50ma_v` and `ilim_knee_ma` **fixed** (base 1.712 V* / 45.4 mA*); short 159.6 mA (base 73.7) | same: fixed; short 165.5 mA, knee 88.6 mA |
| iq 3.3 V | `iq_full_load_ua` 30.86* **REGRESSION** (base 27.61); no-load 17.16 (13.87) | full-load **28.82**, no-load **15.09**: pass |
| iq 2.1 V | full-load 30.51* **REGRESSION** (base 19.45); `vout_full_load_v` fixed (base 1.661*) | full-load 28.61: pass; `vout_full_load_v` fixed |
| enable-shutdown 3.3 V | **INVALID**: `Warning: singular matrix: check node xldo.ea_cz` | all pass (shutdown Iq 0.0003 uA, leakage 0.00018 uA, VOUT pre-disable 1.811 V) |
| thermal 3.3 / 2.1 V, 8 states each | state pattern identical to baseline in 16/16 | identical in 16/16 |

`*` = fails its bound. In the protection, Iq and EN benches there are **no pre-existing failures at tt/27 C/3.3 V**; the only pre-existing tt/27 C/3.3 V failure is the dropout row itself (baseline 0.397658 V).
At 2.1 V (outside the ratified 2.97-3.63 V input range, so a paired-comparison condition only) the
baseline fails `vout_50ma_v`, `ilim_knee_ma` and `vout_full_load_v`. The candidate fixes all
three. The thermal set shows trip action, hold, and EN re-enable from the tripped state: at 185 C,
a forced trip holds, an untripped start trips, and the tripped runs read 0.2-0.37 uA at 165 us (comparator-state evidence only; the actuator
witness is the settled pair below). At 166 C (inside the window) both states hold at 3.3 V. At 2.1 V, the baseline
and both revisions share the same shift: at 166 C a forced trip no longer holds. That is a
pre-existing low-VIN property of the unchanged thermal block, not a regression. Thermal trip
temperatures were not re-bisected.

**Thermal pass-off witness, disclosed deviation.** The declared witness (pass Id < 1 uA at 90 us
while tripped) does not discriminate. At 90 us the 170 us bench is still inside its soft-start
transient, so the pass is off in untripped runs too (base 27 C: 0.0001 uA). The 165 us
supplementary reading is **not** sufficient either (review of e7f01f0): the untripped baseline
conducts there (7.5 mA), but the untripped candidate does not (`th_cand_r1_3p3_027_cold`: 0 uA,
VOUT 1.31 V; the 166 C `coldexc` control: 0.44 uA), because the candidate's start-up is slower than
the 170 us window. The 90/165 us pass-off readings stay in each `result.json` as
**comparator-state agreement only**; they are not evidence of actuator action for the candidate.

**Thermal actuator witness (added after review; `summary.txt`, last table).** A new bounded
`thermal-settled` bench (`probe.py`) pairs a settled, loaded, actively conducting **untripped
control** with a **forced-trip** run, same variant, supply, 150 C device temperature and timing; the
two differ only in the TS_SNS disturbance (`ctl` 0 vs `trip` +0.5 uA). Declared gate, written before
the `thl_*` runs: the control must be untripped, conduct >= 100 uA (RLOAD 1.8 k draws about
1 mA), have VOUT >= 1.5 V and move <= 10 mV over the 50 us before the sample; the tripped run must
be tripped with |Id(M_PASS)| < 1 uA. Anything else is NOT DEMONSTRATED / FAILED / INVALID, and a
witness that is off in both states cannot pass (fixture `test_off_in_both_states_rejected`).
**Timing/stimulus extension to the two-state contract**: the bench runs to 1500 us (not 170 us)
and the disturbance is moved from 20..40 us to 1300..1340 us, sampled at 1335 us inside the pulse.
Attempt 1 (`ths_*`, stop 1000 us, pulse 800..840 us) was too short at 2.1 V: both 2.1 V controls
were still starting up (+44 mV candidate, +60 mV baseline over the settle window), so the gate
returned NOT DEMONSTRATED there and the runs are retained unchanged. Attempt 2 (`thl_*`) result:

| supply | variant | control Ipass / VOUT / settle | tripped Ipass | verdict |
|---|---|---|---|---|
| 3.3 V | candidate rev1 | 1004.2 uA / 1.8064 V / +0.01 mV | 0.0421 uA | DEMONSTRATED |
| 2.1 V | candidate rev1 | 1005.1 uA / 1.8021 V / +0.19 mV | 0.0240 uA | DEMONSTRATED |
| 3.3 V | baseline | 1001.2 uA / 1.8011 V / 0.00 mV | 0.0421 uA | DEMONSTRATED |
| 2.1 V | baseline | 1000.6 uA / 1.8003 V / -0.02 mV | 0.0236 uA | DEMONSTRATED |

Scope: a single 150 C / tt point per supply, with the trip forced by the existing sense-node
disturbance during the pulse (at 150 C the tripped state does not hold after the pulse is released,
as in the existing `hot` row, so the witness is taken inside the pulse). It shows the thermal
comparator overriding the new OTA while the loaded candidate conducts about 1 mA; it is not a trip
or reset temperature measurement and not PVT.

**Start-up (from the dropout traces; no new run).** Time to 98% VOUT after the EN edge is 332 us
(base), 321 us (rev0) and 323 us (rev1). Start-up is monotonic in all three, and overshoot is
+0.75%, +0.64% and +0.65% (row limit +2%). The candidate's ramp shape differs: it reaches 50% at
213 vs 162 us. That is why the candidate pass is still off at 165 us in the 27 C / 3.3 V thermal
cold start (base 7.5 mA). The `sim/startup` bench itself was not run.

## 5. The one revision (rev0 -> rev1), driven by rev0 evidence only

1. `iq_cand_r0_3p3`: full-load Iq 30.86 uA > 30 uA. rev1 cuts the bias overhead from 3.2 to
   1.4 uA. XM_PBR goes from 10 to 2.5 um, so the unchanged XM_CLP mirrors I_R up by about 3x
   (measured, not the nominal 4x). That keeps rev0's ~2.3 uA clamp reference, and with it the
   3.3 V trip: 152.5 vs base 153.3 mA. XM_PBN/XM_NBR were re-sized and XM_NTAIL is unchanged.
2. `en_cand_r0_3p3`: singular-matrix diagnostic. A merged-stream replay (`runs/inv01_*`) located
   it in enable-shutdown leg 1 (non-`uic` `tran`): at its disabled-state op solve, and again after
   EN falls. The new PMOS gate nodes PBR and ND2 float when disabled. rev1 adds the EN-low pull-up
   that every PMOS gate node of the committed design already has. Result: no diagnostic.

The rev1 sizing came from DC benches before any rev1 loop run. sz03 (CLP 1.65 uA, too low), sz04
(tail 4.10 uA, too high) and sz05 (a 1 um PMOS carried 0.59 uA from a narrow-width effect, giving
a 4.85 uA tail) were rejected. sz06 is the configuration computed from the measured sz04 ratios,
and it was locked. This is the complete list; it is not a broad search.

## 6. All attempts, including failed and invalid ones (retained in `runs/`)

- `d01_base`: **INVALID**. The instrumentation asked for `i(iload)`, which ngspice rejects, so no
  data was written. Rerun as `d01b_base`.
- `en_cand_r0_3p3`: **INVALID** (solver diagnostic). Its numbers sit inside the bounds and are
  still never counted.
- `iq_cand_r0_3p3` and `iq_cand_r0_2p1`: valid, **FAIL** (the regression that drove rev1).
- `sz03`-`sz05`: rejected sizing tries. They were generated by intermediate states of `REV[1]`;
  each deck is kept verbatim.
- `ths_*` (8 runs): thermal-settled attempt 1 (pulse at 800..840 us). Valid runs; the 2.1 V controls
  had not settled, so those two pairs are NOT DEMONSTRATED. Superseded by `thl_*`, not overwritten.
- `inv01_en_cand_r0_merged`: investigation replay. It has no `result.json`; its log is
  `ngspice.merged.log`.

## 7. Decision: **ADVANCE** (to a production-adoption review issue, not to adoption)

At tt/27 C the physical rev1 candidate gives a valid **0.163237 V** dropout, against 0.397658 V
for the baseline (repeatable to 0.0000 mV). It keeps the pass device unchanged and is powered only
from VIN. Its current limit matches the baseline at 3.3 V (152.5 vs 153.3 mA) and becomes
VIN-independent at 2.1 V (165.5 mA, where the baseline collapses to 73.7 mA). Thermal trip, hold
and EN re-enable comparator-state behaviour is identical to the baseline, and the settled, loaded
actuator witness (section 4) shows pass-off when tripped from a conducting untripped control at
3.3 V and 2.1 V (150 C, tt). Iq, shutdown Iq and leakage pass, and no
row that passes for the baseline fails for rev1. This is a single-condition screen. **Measured
limits that a later qualification must address:**

- **Iq margin is thin**: 28.82 uA vs < 30 uA at full load (baseline 27.61). The candidate adds
  about 1.2 uA. A PVT Iq failure is likely, and the baseline itself already failed
  `iq_full_load_ua` at 9 corners in the last (stale) Iq record.
- **The clamp engages in deep dropout** (sense-FET saturation mismatch). Its margin at the 0.300 V
  edge is roughly 1.32 / 2.15 uA, i.e. about 62% of trip at tt. The clamp threshold and the
  dropout floor will move together over PVT; ss/125 C is unmeasured.
- **The VREF-referenced V-to-I runs on (VREF - Vgs) of only about 0.33 V**, so I_R tracks Vth and
  temperature strongly (about 3% per 10 mV of Vth). Tail, clamp threshold and Iq inherit that
  spread. This is unmeasured beyond tt/27 C.
- The soft-start ramp shape changed (50% point +51 us), and the regulation offset is +3.7 mV.
  Loop gain, phase margin, load transient and PSRR with the new OTA (different gm and pole
  placement) have not been measured. #349 covers compensation separately.

## 8. Later work (explicitly not done here)

1. **Production adoption review**: a human-approved issue to move the candidate into
   `design/ldo_3v3in_1v8out.sch`, with loop-gain/PM/GM, load-transient, PSRR, line/load
   regulation, start-up and MC output-accuracy benches. No pass-device or DR change is indicated.
2. **Dropout batch-adapter qualification**: `dropout-vs-load` is still not in `corner-run.py`'s
   `BATCH_ALLOWLIST`.
3. **The paired 45-point PVT campaign** (baseline vs candidate, same commit) on the fleet, with
   current-limit, Iq and thermal re-bisection over PVT. None of it runs on this host.

## 9. Provenance

- Source commits at run time (in each `result.json`): `3a48429` (sz01, sz02), `c2ecfeb` (declared
  plan; rev0 and baseline runs, sz03-sz06) and `ddc5705` (rev1 runs). Some scripts were edited
  between commits: the `i(iload)` fix, the REV[1] sizing states, docstrings. Each run therefore
  also records `driver_sha256` and `candidate_py_sha256`. Every committed candidate
  `netlist.edited.spice` regenerates byte-identically from its `netlist.raw.spice` with the final
  `candidate.py` (test `test_committed_edited_netlists_regenerate_byte_identically`).
- Tools: **ngspice-46** (KLU) and **xschem 3.4.7**. The pin `sim/pdk.json` declares 42 and 3.4.4,
  so this is host drift (worker spec), not changed here; the anchor above shows identical numbers.
  Python 3.12.3. PDK sky130A open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b` (matches the pin),
  lib sha256 `48de7c67...`. `.spiceinit` = `sim/spiceinit`.
- Hashes: `provenance.json` holds the sha256 of every file in this directory, and each
  `result.json` holds the sha256 of its raw/edited netlists, deck, inputs and uncompressed data.

## Reproduce

```bash
cd sim/dropout-vs-load/diagnostics/issue-357
sh commands.sh       # strictly sequential, about 40 min on a shared worker; run ids must not already exist
python3 -B ../../../tests/test_dropout_candidate_357.py
```
