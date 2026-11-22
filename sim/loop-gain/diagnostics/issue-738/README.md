# Issue #738: erratum to the issue-704 loop-gain diagnostic

This is an erratum, not a record and not a measurement. It runs no simulation, adds no run
files, and moves no graded value. It **supersedes in part** (never overwrites) the report at
`../issue-704/README.md`, whose committed files stay byte-identical: that directory is
append-only evidence, so each correction below is recorded here and the earlier text is left
as committed. Where the two disagree, this file governs. No verdict in `../issue-704/` changes
(`verdict.json` there is untouched and still correct as graded).

## 1. Extraction bias on the low-frequency (`dc`) loop gain: disclosure

The `issue-704` report discloses the extraction-sensitivity of the phase-margin column. It does
not disclose that the low-frequency (`dc`) loop gain is far more extraction-sensitive, in the
opposite direction.

On the `c47-esr0-10uA` leg, rev2's as-drawn `dc` of 650.12 reads 1818.23 under the
single-entry extraction (x2.80, +8.9 dB). rev2's as-drawn `dc` is therefore about 9 dB
pessimistic, and the paired `dc` column in `../issue-704/tables/loop_pair.csv` is not
like-for-like. The apparent 14.8 dB paired DC-gain deficit on that leg is about 5.9 dB after
the correction.

No graded quantity uses DC gain: `verdict.json`'s `pair_classification` carries only `d_pm` and
`d_gm`, deliberately no `d_dc`. No verdict in the `issue-704` report changes.

## 2. Citation repair: the load-transient `.ic` adaptation

`../issue-704/README.md` (the paragraph on the one deliberate bench adaptation) cites
`runs/syntax-probe/loadstep-rev2/` as the measurement that ngspice rejects the whole `.ic` card
once any named node is gone. That citation is not supported by retained evidence: the failing
run on the pre-adaptation deck was observed during probing and **was not retained**. The
claim stands as an observation, not as a cited artifact.

What the retained evidence does support:

- The candidate decks drop exactly the three tokens `EA_TAIL`, `EA_D1`, `EA_D2` from the
  11-token `.ic` seed and keep the other eight byte-identical to the baseline deck's first
  eight (`../issue-704/runs/syntax-probe/loadstep-{base,rev2}/deck.spice:22`).
- All 18 candidate leg-corners passed the `vout_pre_v` gate (1.764 to 1.836 V) before the
  first step (`../issue-704/runs/loadstep/rev2/leg.json`).

## 3. PSRR invalid-corner enumeration

`../issue-704/README.md` (Coverage section, PSRR) lists the 6 invalid rev2 corners
incompletely: it names tt/-40/2.97 and tt/3.63 for the singular-matrix diagnostics "plus the
two gmin pairs". The full enumeration of the 6 rev2 invalid corners (and their two loads) is:

| load | corner | failure |
|---|---|---|
| 1 mA | tt/-40/2.97 | singular matrix on `xr_cz.t1` |
| 1 mA | ff/-40/3.30 | singular matrix on `xr_cz.t1` |
| 1 mA | tt/3.63 | singular matrix on `xr_fb_b.t2` |
| 50 mA | tt/-40/2.97 | gmin-stepping failure |
| 50 mA | ff/-40/3.30 | gmin-stepping failure |
| 50 mA | tt/3.63 | singular matrix on `xr_fb_b.t2` |

The 4 base invalid corners (ff/27/3.30 and fs/-40/3.30, gmin stepping) are unchanged. Each
invalid corner is listed in `../issue-704/verdict.json` and was excluded from grading rather
than counted either way; that handling is unchanged.

## 4. `analyze.py` docstring

The module docstring of `../issue-704/analyze.py` says the script "Writes tables/*.csv,
tables.md and verdict.json". It does not write `tables.md`: it writes `tables/loop_pair.csv`,
`tables/psrr_pair.csv`, `tables/loadstep_pair.csv` and `verdict.json` only. The docstring
is inaccurate in that one word; the code is correct and the committed `tables/` directory
holds exactly those three CSVs.

Disposition: **recorded here only**. The archived copy cannot be corrected in place, and no
corrected copy is landed alongside it, so nothing re-runnable is forked from the archived
script. If that script is later meant to be re-run going forward, the docstring fix goes in
with that change.
