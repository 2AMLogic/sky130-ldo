# Issue #755 — paired local/fleet enable-shutdown check (tt / 27 °C / 3.30 V)

Append-only diagnostic. **Not an evidence record:** it mints no `records/`
entry and moves no `LATEST` pointer; ratified targets are unchanged. Scope: one
corner, `--no-write`, both halves at the #755 branch (2026-11-24), re-run so
the AC 3 claim in `sim/README.md` has retrievable raw artifacts.

## Result: equivalent at print precision

- Local (default backend) and batch (`--backend batch`, job
  `klt-sim-5100f5d02ebc`, state `done`) both graded **PASS**.
- All eight scalars are identical at the harness's 6-significant-digit print
  precision (`comparison.json`, `all_identical: true`). The local half only
  retains `%.6g`, so agreement below that is not claimed.
- Engines: both ngspice-47, different builds (local binary sha256 `39ca1adb…`,
  fleet `e12148ba…`); `sky130.lib.spice` sha256 `48de7c677e2c…` on both sides.
  The fleet's PDK stamp differs from the volare pin (`c6d73a35…`) with
  byte-identical model libraries.
- Preflight for the 45-corner run is recorded in
  `sim/enable-shutdown/records/20261124-042548-d0bee518.md` (job
  `klt-sim-89e458932ca4`); this bundle did not re-run it.
- Response warning `batch_ngspice_init_unverified` (workers do not confirm
  `options.ngspice_init` was applied) is present in `remote/response.json`; it
  is a harness-reporting gap, not a result difference here.

## Alter carry-over

`remote/corner.cir` is the generated deck: ONE `.control` block, steps `tran`,
`op`, `alter rforce=0.001`, `op`, `alter rforce=0.001`, `alter vforce=1.8`,
`op`, with no `reset` between steps. The request (`remote/request.json`) itself
repeats `rforce` in `op3`, so this deck **cannot distinguish** klt carrying
`alter` state from resetting per step; it shows only that klt adds no reset and
that the adapter's repeat is idempotent either way.

## Reproduce

    python3 sim/bin/corner-run.py sim/enable-shutdown --process tt --temp 27 \
        --supply 3.3 --subset-reason "paired diagnostic" --no-write
    python3 sim/bin/corner-run.py sim/enable-shutdown --backend batch \
        --process tt --temp 27 --supply 3.3 --subset-reason "paired diagnostic" --no-write

Layout: `local/{deck.spice,corner-run.log}`,
`remote/{request.json,request.spice,response.json,batch-receipt.json,ngspice.log,corner.cir,corner-run.log}`.
Host paths were scrubbed to `<worktree>/` and `~`.
