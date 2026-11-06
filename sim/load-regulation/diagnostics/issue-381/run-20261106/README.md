# Issue #381 — paired local/fleet load-regulation check, NEW RUN 2026-11-06 (tt / 27 °C / 3.30 V)

Append-only diagnostic. **This is a new run, not the original 2026-11-05 run**
(`../README.md`, `../comparison.json`), which stays as recorded. It mints no
`records/` entry and moves no `LATEST` pointer; ratified targets are unchanged.
Scope: one corner, `--no-write`, both halves at commit
`9042a88a4e1da10fae44b0a099a18616b1b66e2f` (the PR head this run started from).
Run per operator ruling r7-q22: the evidence is what is committed here; the
original uncommitted logs are not recovered.

## Result: same-engine pair, equivalent at this corner

- Preflight (`sim/bin/batch-preflight.py`): ACCEPTED, job `klt-sim-a638ed20ef4d`,
  runner klt 0.9.0 / client 0.9.2.dev119+gaa798644c611, compatibility `match`.
- Remote (`corner-run.py --backend batch`, log `remote/corner-run.log`): endpoint
  jobs `tran1` (0 A) and `tran2` (50 mA), **ngspice 46** (`remote/tranN/response.json`).
- Local: `ngspice -b` on `local/deck.spice`, host **ngspice-46** (the host
  engine now equals the runner's; the original run had 42). Log: `local/ngspice.log`.
- Both halves graded PASS (execution parity only, not spec compliance).
- `comparison.json` verdict: **`equivalent`**: all six endpoint values and both
  derived differences agree, Δ = 0, inside the 1 µV / 2 µV tolerances.
- Resolution caveat: the remote values are returned at 7 significant digits
  (1 µV). The local log also holds `print` values at `numdgt=10`, and they land
  on the same 1 µV grid. Agreement below 1 µV is not shown.
- Single corner only. This does not establish equivalence across the 45-corner
  matrix. Tolerances were not widened.

## Differences from the original run's quoted numbers

None. The six raw values and both derived differences equal those the original
README reported (`vout_0ma` 1.802385 V, `vout_50ma` 1.798832 V,
`load_reg_v` 3.553 mV, `load_reg_pct` 0.1974 %). What changed is the local engine
(42 → 46), so the engine-mismatch qualification no longer applies to this pair.

## `local/deck.spice`

The klt-generated corner deck for this corner (`.param vsup`, `.lib`, `.subckt`,
`.control` with both `tran 10u 200m uic` points and the `meas` cards), runnable as
committed. Run it from `local/` with the sibling `.spiceinit`:

    cd sim/load-regulation/diagnostics/issue-381/run-20261106/local
    ngspice -b -o ngspice.log deck.spice

Two diagnostic-only changes versus the generated deck: `set numdgt=10` and two
`print` lines (after the `meas` cards) so the log carries values beyond ngspice's
6-digit `meas` echo. The `.lib` path is the dispatch worker's volare PDK
(`~/.volare/sky130A`). The original `local/deck.spice` one level up was a raw
xschem netlist and does not run as committed.

## Reproduce the comparison

    python3 -I sim/bin/compare_load_regulation_paired.py \
        sim/load-regulation/diagnostics/issue-381/run-20261106 --local-engine 46 \
        --remote-pass PASS --local-pass PASS \
        --out sim/load-regulation/diagnostics/issue-381/run-20261106/comparison.json

Layout: `remote/tranN/{request.json,request.spice,response.json,batch-receipt.json,ngspice.log}`,
`remote/corner-run.log`, `local/{deck.spice,.spiceinit,ngspice.log}`. The `.log`
files are force-added (`.gitignore` ignores `*.log`). Host paths inside artifacts
are the dispatch worker's worktree.
