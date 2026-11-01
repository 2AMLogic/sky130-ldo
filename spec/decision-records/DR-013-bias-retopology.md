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

*Addendum (#478, additive; the text above is unchanged).* That 45-point matrix omitted the `ll`/`hh`
resistor-skew corners. `sim/bias-retopo/20261101-llhh-478/record.md` adds them
(18 points, batch, same deck and same `< 30 µA` bound) and re-tabulates all 63: **10 of 63 points exceed
30 µA at full load**, the original 6 plus 4 at `ll` (31.3 @ −40 °C/3.63 V, 31.9 @ 27 °C/3.63 V,
30.3 @ 125 °C/3.30 V, 32.4 @ 125 °C/3.63 V); `hh` is 9/9 in budget; no-load Iq is in budget at all 63.
The worst full-load figure is now 32.4 µA (`ll`/125 °C/3.63 V). The carried FAIL stands at the unchanged bound.

*Attribution of the exceedances (#478).* The candidate changes only `R_BIAS`, so it can change Iq only
through the bias current; the bias-only grid (`sim/bias-retopo/20261029-bias-grid-467/record.md`) gives
the pair-current shift at every point. At **ff / −40 °C / 3.63 V (31.2 µA)** the shift is −0.45 %
(4.6346 → 4.6137 µA) and at **fs / 27 °C / 3.63 V (30.2 µA)** it is −0.34 % (4.5480 → 4.5325 µA): the
candidate lowers bias current there, so **these two of the six cannot be caused by it**, and the design of
record is **inferred** to be at or marginally above the same value (already over 30 µA); the two `ll`
points at 3.63 V cold/room (−2.85 %, −0.08 %) are likewise not candidate-caused. This is an inference
from the bias-only grid, **not a measured baseline** (none was run). The remaining six exceedances all
have a positive bias shift (+2.4 % … +8.4 %, five of them hot), which is consistent with, not proof of,
the candidate contributing; they stay **unattributed**.

*Departure from gf180-ldo DR-0033 (#478; port parity, CLAUDE.md).* `2AMLogic/gf180-ldo`
`DR-0033-poly-resistor-flavour-is-set-by-dc-current-not-by-area.md` rules that a poly resistor which sets a
**DC current** keeps the low-spread flavour (its `Rbias` stays `ppolyf_u_1k`; only resistors with no DC
current in their branch, `Rz`/`Rza`/`Rbufb`, move to the dense, high-spread `ppolyf_u_3k`), because the
wider-spread flavour costs +1.97 µA of Iq at the hot/fast corner where the ratified 30 µA row already
binds. This record does the opposite for the same role: `R_BIAS`, the resistor that sets the bias current,
goes from `res_high_po` to the denser `res_xhigh_po`. It is forced by the area gate here: the straight
`res_high_po` body costs 0.2765 mm² and its fold fails #263's M2, while `res_xhigh_po` (≈6x sheet
resistance) makes the same ≈1.22 MΩ a ≈211 µm straight body, and gf180's option of leaving that resistor
alone does not close the core-area row on sky130. The consequence is the one DR-0033 warns about: more
spread on the Iq-setting resistor, hence on Iq at its worst corner. That spread is what the bias-only grid
and the `ll`/`hh` Iq points above measure (bias-pair current −5.6 % … +8.4 % vs the design of record), and
it is why the Iq FAIL is carried here rather than waived. It does not change the ratified decision.

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
