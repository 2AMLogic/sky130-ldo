# Issue #327 — standalone 45-corner schematic leg on the batch fleet, compared with baseline

Append-only diagnostic backing record `20261115-133911-1caff9b9`
(`records/20261115-133911-1caff9b9.{json,md}`, minted by
`bin/run-pex.sh` at commit `1caff9b9`, `feature/issue-327` = `main`
`4746bc4b` + the harness capacity-wait commit). It supersedes
`20261022-232148-56dd87fe` (the auto supersede rule). Ratified targets are
unchanged; nothing here relaxes a spec line.

## Result: the leg completes on the fleet — zero parse / undefined-parameter errors

- **Route.** `run-pex.sh` with `KLT_SIM_BACKEND=batch`: the standalone
  schematic leg ran as fleet job **`klt-sim-8a464d7721aa`** (spot
  m6i.4xlarge, us-east-1c), `--wait-for-capacity 600` carried per worker-host
  policy (the harness change on this branch passes it to both legs). Both
  legs exited 3 = declared-limit failures only (`docs/cli/pex.md` exit
  codes); AWS Batch's job `state: failed / exit_code: 3` is that same
  non-zero exit, not a crash.
- **The issue's gate.** 45/45 corners simulated on both legs, **0 errored**,
  and a grep of both response envelopes for `Undefined parameter` /
  `parse error` finds **0 hits** — the `swx_nrds` failure class #277
  diagnosed and repaired (xschem 3.4.4 `expr('...')` normalization) does not
  reappear at full-matrix scale, and the three earlier
  `batch_runner_version_mismatch` submit failures (evidence records
  `20261010-193154-0c8ccf6`, `20261016-161847-854ab16`; runner klt 0.5.0 vs
  client 0.7.0, exit 87) are closed by the fleet image update verified in
  #375 / PR #612 (`runner_compatibility: match`, job
  `klt-sim-1d3242e701fb`).
- **Acceptance criterion 1** (2-corner batch probe, `runner_compatibility`
  no longer `mismatch`) needs no new work here: PR #612 minted exactly that
  evidence and the Champion unblock verified it.

## Comparison with baseline `20260924-230726-a947aa8` (criterion 3)

Machine-readable form: `comparison.json` alongside this README.

| leg        | baseline 38/7/0 → record | deltas |
|------------|--------------------------|--------|
| schematic  | 38 pass / 7 fail / 0 err → **42 / 3 / 0** | +4 pass, −4 fail, 0 err |
| pex delta  | 39 pass / 96 fail / 0 err → **41 / 94 / 0** | +2 pass, −2 fail, 0 err |

**Read honestly, not flattered:**

- The record's three failing corners are **electrical limit failures, not
  harness artifacts** — `vout_full_load_v` and `vin_minus_vout_full_load_v`
  out of their declared limits at `ss/2.970V/27C` (2.77719 V),
  `ff/2.970V/27C` (2.64591 V), `sf/2.970V/125C` (2.68576 V) against the
  1.764–1.836 V window: the LDO leaves regulation at full load / low supply
  there. This is the schematic-side Output-row gap
  `measurements/characterization.md` already tracks; the issue explicitly
  allows these to remain.
- The baseline→record delta is **not** an apples-to-apples electrical
  regression claim: layout record moved (`20260924-221912-a947aa8` →
  `20261112-110237-820ba8b3`, the #267 official-DRC via fixes merged
  2026-10-16 in between), schematic state moved (baseline `feature/issue-154`
  `a947aa8` dirty; record `main` + harness commit), and backend moved (local
  → fleet). The comparison evidences **route completion plus drift**, which
  is what the acceptance criterion asks this record to carry.
- **Fleet-run reproducibility** (free corroboration from the supersede
  target `20261022-232148-56dd87fe` — which is itself a **fleet** record,
  job `klt-sim-6c1a144ebdb0`, runner klt 0.7.0, m7i.4xlarge — not a local
  run): the fleet leg reproduces that run's failing corners and values
  exactly — same three corners, same values to the response's print
  resolution. That is **fleet-vs-fleet reproducibility across runner
  versions** (klt 0.7.0 → 0.9.0; m7i → m6i) — a worthwhile result, but a
  different one from backend parity.
- **PDK-stamp caveat, disclosed:** this record's envelope carries
  `environment.remote.worker_environment.pdk_stamp_comparison.status =
  mismatch` — the worker's sky130A PDK revision stamp differs from the one
  the submitter resolved locally (the 10-22 predecessor's stamp was
  `match`). Per the envelope's own warning, results may differ from a
  local run, so **fleet-vs-local agreement is unestablished** for this
  record; no claim is made here that the batch route is not skewing
  results.

## Provenance

- Record `20261115-133911-1caff9b9`: repo `feature/issue-327` @ `1caff9b9`
  (`main` = `4746bc4b`), layout `20261112-110237-820ba8b3`, GDS per
  `layout/ldo-core/reports/LATEST-LVS`, engine ngspice-47 (fleet worker),
  client klt `0.9.3.dev3+gd5d57daf9a14`, backend `batch` (env), job
  `klt-sim-8a464d7721aa`.
- Baseline `20260924-230726-a947aa8`: repo `feature/issue-154` @ `a947aa8`
  (dirty), layout `20260924-221912-a947aa8`, engine ngspice-47 (per its
  response envelope), local backend.
- Scratch per-corner decks/logs under `sim/build/pex-post-layout/` are
  gitignored; the committed evidence is the request/response envelopes,
  netlist snapshots, and the record pair, per this experiment's README.
