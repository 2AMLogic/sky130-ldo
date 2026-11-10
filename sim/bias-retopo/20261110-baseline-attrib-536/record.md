# DR-013 Iq exceedance attribution against a measured baseline: 20261110-baseline-attrib-536

Issue #536 (operator ruling 2026-11-10, follow-up to #467 / #478 / DR-013). Append-only; evidence only. **No spec row, bound,
or DR-013 text is changed** (bound stays full-load Iq < 30 uA, DR-009).

## Method

- Baseline = the schematic of record (pre-DR-013 `R_BIAS`, `res_high_po` L=1500), unmodified. `git log 2f5f4d72..origin/main --
  design/ldo_3v3in_1v8out.sch sim/iq/testbench sim/iq/experiment.json sim/spiceinit` was empty at `f66373a0`, so the 45-point
  baseline record (minted at `2f5f4d72`) is still valid for the current design; `design/` was clean at run time.
- 45 points (tt/ss/ff/sf/fs x 3 T x 3 VIN): `sim/iq/records/20261105-052332-05df7a01.md` (not re-run).
- 18 points (ll/hh x 3 T x 3 VIN): new record `sim/iq/records/20261110-223334-f66373a0.md`, from
  `python3 sim/bin/corner-run.py sim/iq --backend batch --process ll,hh --timeout 1500 --subset-reason "..."`
  (6 `klt sim` batch requests, same method as #478 minus the candidate patch and without `--no-write`). 18 points, 0 errored, no local fallback.
  The runner exited FAIL because ll at 3.63 V exceeds 30 uA.
- Candidate = `../20261101-llhh-478/record.md` merged 63-point table (same deck, same bounds).
- Engine is ngspice-46 on the batch worker for all rows (differs from the `ngspice: 42` pin; same caveat as DR-013's receipts).

## Classification rule

Full-load Iq is quantised at ~0.1 uA (`../20261101-llhh-478/record.md` line 18), so tol = 0.1 uA.
**pre-existing** = baseline > 30 uA. **caused** = baseline <= 30 uA and candidate - baseline > 0.1 uA.
**marginal** = baseline and candidate both within 0.1 uA of 30 uA (and neither pre-existing / caused).

## Result: the candidate's 10 failing points (full-load Iq, uA)

| point | baseline | candidate | delta (cand - base) | class | baseline source |
|---|---|---|---|---|---|
| ff / -40C / 3.63 V | 31.3 | 31.2 | -0.1 | pre-existing | 20261105-052332-05df7a01 |
| ff / 27C / 3.63 V | 31.3 | 31.6 | +0.3 | pre-existing | 20261105-052332-05df7a01 |
| ff / 125C / 3.63 V | 30.7 | 31.9 | +1.2 | pre-existing | 20261105-052332-05df7a01 |
| ff / 125C / 3.30 V | 29.1 | 30.2 | +1.1 | **caused** | 20261105-052332-05df7a01 |
| fs / 27C / 3.63 V | 30.2 | 30.2 | 0.0 | pre-existing | 20261105-052332-05df7a01 |
| fs / 125C / 3.63 V | 29.6 | 30.4 | +0.8 | **caused** | 20261105-052332-05df7a01 |
| ll / -40C / 3.63 V | 31.8 | 31.3 | -0.5 | pre-existing | 20261110-223334-f66373a0 |
| ll / 27C / 3.63 V | 31.9 | 31.9 | 0.0 | pre-existing | 20261110-223334-f66373a0 |
| ll / 125C / 3.63 V | 31.4 | 32.4 | +1.0 | pre-existing | 20261110-223334-f66373a0 |
| ll / 125C / 3.30 V | 29.5 | 30.3 | +0.8 | **caused** | 20261110-223334-f66373a0 |

No point is marginal: every baseline value is either > 30.1 or <= 29.6.

## Verdict

**7 pre-existing, 3 caused, 0 marginal.** The 3 caused points are ff/125C/3.30 V, fs/125C/3.63 V and ll/125C/3.30 V (all hot,
all with a positive bias-pair shift in the #478 bias-only table). So per the ruling's "any caused" branch the verdict is **not**
"all 10 pre-existing"; the choice of next step is the operator's, not this record's.

Context the table does not show:
- Worst baseline full-load Iq across all 63 points: **31.9 uA** (ll / 27C / 3.63 V); the baseline itself fails at 8 of 63 points
  (ff x3, fs x2 at 3.63 V from the 45-point record: ff -40/27/125 and fs -40/27; ll x3 at 3.63 V). Worst candidate: 32.4 uA.
- The inference in DR-013 that 4 points are not candidate-caused is confirmed (all 4 are pre-existing). Its other 6 resolve to 3 pre-existing, 3 caused.
- fs / -40C / 3.63 V is a baseline failure (30.4) that the candidate brings into budget (29.9); it is not among the candidate's 10.
