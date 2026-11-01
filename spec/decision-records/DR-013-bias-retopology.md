# DR-013: bias re-topology — `R_BIAS` as a single straight `res_xhigh_po` body, so no folded long resistor sets the core area

- **Status**: **proposed** — drafted per #467. It does not ratify itself. Ratification
  needs the two-key step (EE and market keys) and then operator ratification
  (2am#5346), which are human gates outside this PR. #461 (layout) stays parked
  until that completes.
- **Date**: 2026-10-29
- **Author**: Builder agent (#467)
- **Ratifies against / input to**: #467 (operator ruling 2026-10-29 on #461: fix the
  design, not the spec); #458 / #459 (area study); #263 / #416 (`R_BIAS` fold
  mismatch gates); DR-007 and DR-009 (both `proposed`, coordinated below).
- **Supersedes**: none. Edits no earlier record and changes no spec row.

## Context

The #459 study (`layout/area-study/20261028-study-459/report.md`) found the routed
`ldo_core` meets the ratified `Area < 0.1 mm²` row (0.0831 mm², 16.9 % margin) only
with all four capacitors overlaid **and** `R_BIAS` (`res_high_po` W=0.42 L=1500,
≈1.22 MΩ) folded to N=4. #263's mismatch gate M2 fails for that fold (sigma ratio
1.1316 > 1.1; already 1.1114 at N=2). Straight, `res_high_po` costs 0.2765 mm².
The operator ruled: no gate waived, no target lowered; redesign the bias so no
long straight resistor is needed.

Fact the argument rests on (sky130A, `sim/pdk.json` pin): the PDK's
`sky130_fd_pr__res_xhigh_po` has a sheet resistance roughly 6x that of
`res_high_po`, so the same ≈1.22 MΩ is a ≈211 µm body instead of 1500 µm.

## Decision

Propose replacing `R_BIAS` with `res_xhigh_po` W=0.42 **L=211**, drawn as one
straight body (no fold, so #263's folded-vs-unsplit criteria have nothing to
compare). The rest of the bias generator (`M_BIASN1/N2/P1`, `M_ENN`) is unchanged.
This is a **geometric** estimate plus screening simulation, **not** a qualified
design: the Iq row is not shown met (see Consequences). The schematic of record
is unchanged by this PR; the candidate is `sim/bias-retopo/20261029-fullloop-467/candidate-R_BIAS.patch`.

## Alternatives considered

- **(a) Smaller `R_BIAS` plus a mirror ratio** (the issue's suggested first
  candidate). Case for it: cuts R length by about the ratio at the same branch
  current, with no new resistor type. Not chosen: it adds a branch whose leakage
  must be re-checked against the EN=0 ≈150 pA floor, it moves current-ratio
  matching onto `M_BIASN1/N2`, and it is a topology change that moves DR-007's
  capacitor/Iq budget, whereas the resistor-type change leaves the circuit
  identical. **It was not simulated**; if the candidate below is rejected on Iq,
  this is the next one to evaluate, not a settled loser.
- **(b) A different reference generation** (VBE / bandgap-derived bias). Case for
  it: removes the large R and the supply-proportional current. Rejected for now:
  DR-012 records there is no in-tree reference block and no `reuse.lock.json`
  entry; adopting one is a larger scope than a bias fix and would reopen DR-007/DR-009.
- **(c) Segmented / switched resistor qualifying under #263.** Case for it: keeps
  `res_high_po`. Rejected: it is the fold problem again — #263 already shows
  the segment fold failing M2 at N=2 (1.1114) and N=4 (1.1316), and a switch adds
  series-resistance error and leakage.
- **(d) Re-run Monte Carlo at larger n (#416) to argue the N=4 fold passes.**
  Rejected by the operator ruling (fix the design, not the gate).
- **(e) Single straight `res_xhigh_po` (recommended).**

## Consequences

**Area (geometric).** `layout/area-study/20261029-study-467/report.md` (script
`layout/bin/ldo-area-budget-dr013.py`, same inputs as #459, new append-only record):
0.0831 mm² with stacked 4 fF capacitors, 16.9 % margin, `< 0.1`; the counterfactual
single-2 fF-density cases are 0.0944 / 0.0962 mm² (`< 0.1`, thin). The figure equals
#459's because `R_BIAS` is charged the same full-width strip, so the gain here is
removing the unqualified fold, not shrinking the rectangle. Not established: a
drawn core (DRC/LVS/PEX), MiM-over-MOS coupling, real routing. W=0.42 on
`res_xhigh_po` is the same drawn width the record design uses on `res_high_po`;
it is not DRC-checked for this device here.

**Bias current across PVT** (`sim/bias-retopo/20261029-bias-grid-467/record.md`, batch):
bias-pair current shifts −5.6 % … +8.4 % vs the design of record, worst at 125 °C, 0 unusable points.

**Iq (DR-009, `< 30 µA`).** `sim/bias-retopo/20261029-fullloop-467/record.md`: full 45-point
matrix on the full LDO. No-load Iq 10.5–17.2 µA, all in budget. **Full-load Iq 23.3–31.9 µA,
6 of 45 points over 30 µA** (all ff or fs, VIN 3.30–3.63 V, mostly hot). This is
reported, not loosened. No same-method baseline was run, so whether the candidate
causes it, or the design of record already has it, is **unattributed**; the +8.4 % hot
bias shift points the same way. DR-009 must not ratify `< 30 µA` on this candidate's
evidence without resolving this. Not a no-qualified-candidate verdict: alternative
(a) is unevaluated.

**PSRR and stability (DR-007).** Only one corner (tt / 27 °C / 3.30 V), because
`corner-run.py` refuses batch for `psrr-dc`/`loop-gain` and local grids are not
permitted on this host: PSRR and PM/GM are indistinguishable from the design of
record (e.g. PM 40.54° vs 40.48°; PSRR 100 kHz @ 50 mA 11.31 vs 11.32 dB). The
existing DR-007 gaps remain exactly as they were. **PVT evidence for these rows
does not exist for this candidate**; a batch adapter for `psrr-dc`/`loop-gain` is a
tool gap to be filed generically on `2AMLogic/klayout-tools`.
The candidate does not change the topology, so DR-007's capacitor and Iq budget move
only through the bias-current shift above.

**Left to design / later steps.** Full-load Iq at ff/fs high-VIN; PVT PSRR/stability;
the #263 criteria re-stated for a single-body `res_xhigh_po`; layout (#461);
two-key and operator ratification.

## Status notes

`proposed`. Stays `proposed` until the two-key step and operator ratification. The
schematic of record changes only on ratification, not with this PR. A `sim/iq`
batch attempt (`sim/iq/records/20261029-063823-5ba605f.md`) is a recorded FAIL
(per-unit 300 s cap), kept as append-only evidence; the `psrr-dc` / `loop-gain`
records of this date are single-corner debug probes.

## Evidence update (2026-11-01, issue #467)

Additive; the decision text and Status line above are unchanged. Ratification stays a human step.
All three records below are new and append-only, run with the candidate `R_BIAS`
(`candidate-R_BIAS.patch`, applied for netlisting/running only) on the batch fleet (no local grid).

- **PSRR, 45 PVT points x {1 mA, 50 mA}**: `sim/bias-retopo/20261101-psrr-pvt-467/`.
  Worst PSRR at 1 kHz is 20.64 dB (1 mA) / 20.79 dB (50 mA) against the unchanged `> 50 dB` bound,
  and at 100 kHz 31.81 dB (1 mA, passes `> 20 dB`) / 10.38 dB (50 mA, fails). No point meets the 1 kHz
  bound and none meets the 50 mA 100 kHz bound: these are the DR-007 gaps already recorded for the design of
  record, not new failures attributable to this candidate. At tt/27 C/3.30 V the values match the earlier local
  single-corner record (23.21 / 33.52 dB at 1 mA; 23.31 / 11.28 dB at 50 mA).
- **Stability, 45 PVT points x 18 legs (C_out x ESR x load)**: `sim/bias-retopo/20261101-loop-pvt-467/`.
  GM stays above 10 dB wherever it is defined (min 14.84 dB). PM `< 45 deg` at 197 of 810 points, concentrated in the
  0.33 uF legs at 50 mA and 0 mA and the 4.7 uF / 0 mA legs; worst 15.18 deg (0.33 uF, 0 mA, ss/-40 C/2.97 V).
  GM is not defined at 51 points and PM at 6 (`no_downward_phase_crossing` and similar): those are listed as
  not established, never counted as passes. Method note: PM/GM/fc come from klt `transfer` metrics, not the local
  ngspice `meas` cards, and differ slightly (tt/27 C/3.30 V, 0.33 uF / 10 mOhm / 50 mA: PM 40.15 vs 40.54 deg local
  candidate, 40.48 deg local baseline; the 0 mA and 1 mA legs agree to 0.02 deg). A same-method design-of-record
  baseline was NOT run, so a candidate-vs-baseline delta over PVT is not claimed; the only same-method evidence
  of "no movement" remains the single tt/27 C/3.30 V comparison in `20261029-fullloop-467/record.md`.
- **Iq, 45 points, minted**: `sim/iq/records/20261101-205815-8db2f9c4.md` (manifest
  `manifests/artifacts/iq-20261101-205815-8db2f9c4.manifest.json`), replacing the hand aggregate `iq-graded.json`
  as the citable artifact (the 20261029 FAIL record stays). Overall FAIL: the same 6 of 45 points exceed 30 uA at
  full load (30.2 to 31.9 uA, all at VIN >= 3.30 V in ff/fs), reproduced exactly. The cause is still **not
  attributed**: no same-method design-of-record run was made at those points.

Alternative (a) (mirror ratio) was not simulated. The candidate fails spec rows (PSRR, stability, Iq), but the
PSRR and stability failures are pre-existing DR-007 gaps, and the Iq exceedance is unattributed, so this update does
not claim the candidate alone is the cause and does not declare a no-qualified-candidate verdict. That follow-up is
left to a human decision after #478's attribution lands.
