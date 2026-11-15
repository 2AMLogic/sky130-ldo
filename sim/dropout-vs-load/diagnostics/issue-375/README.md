# Issue #375 — paired local/fleet dropout cold-start check (tt / 27 °C / 3.30 V)

Append-only diagnostic. **Not an evidence record and not a full-matrix
refresh:** it mints no `records/` entry and moves no `LATEST` pointer.
Ratified targets are unchanged. Scope: one corner, `--no-write`, both legs at
commit `f0108fabe16c5f1dbe3141cef563e172526be2a6` (2026-11-14).

## Result: same-engine pair (both ngspice-47), equivalent at this corner

- Preflight (`sim/bin/batch-preflight.py`): ACCEPTED, job `klt-sim-724db05b8a1c`,
  runner klt 0.9.0 / client 0.9.2.dev1029+g76f47afa48f1, compatibility `match`.
- Remote (`--backend batch`, one request `v3.30`): job `klt-sim-1d3242e701fb`
  (`remote/v3.30/batch-receipt.json`), `done`, **ngspice 47** — the fleet
  image has moved past the ngspice-46 the pre-#375 records carried; the
  response's `worker_environment.simulator.version_banner` confirms it and
  `engine_build_comparison` is `match`. Request netlist sha256
  `b26290c1bf8f1a41906b9d0b6a245ff1e71558cf859589b7f280c885a114f129`
  (`environment.netlist_sha256`). `runner_compatibility: match`.
- Local (default backend): host **ngspice-47**. The engines match, so the
  issue's tolerance rule (|Δ| ≤ 1 µV, equivalence claimable) applies.
- Both legs graded **FAIL** (`dropout_v` 0.397658 V against the ratified
  < 0.3 V bound) — matching FAIL verdicts support execution parity only;
  this is the known gap tracked in #114, not a new electrical result.
- `comparison.json` (from `sim/bin/compare_dropout_paired.py`) verdict:
  **`equivalent`** — `dropout_vin_x`, `vout_at_max_vin_v` and the derived
  `dropout_v = dropout_vin_x - 1.764` agree with Δ = 0, inside the 1 µV
  tolerances. Tolerances were not widened.
- Resolution caveat, recorded not absorbed: the remote values are returned at
  7 significant digits (1 µV at the ~1.8 V endpoint — exactly the tolerance),
  so agreement is demonstrated at the tolerance's resolution; sub-µV
  agreement is not shown (`print_resolution_v` in the report). The local log
  carries full precision (`set numdgt=10`); the ~0.4 V metrics resolve to
  1e-7 V even at default precision.
- Caveat recorded, not absorbed: the worker's PDK revision stamp differs from
  the submitter's (`worker_environment.pdk_stamp_comparison: mismatch`
  warning in `response.json` — "a matching stamp would not prove identical
  models"). `runner_compatibility` is nevertheless `match` (the adapter's
  gate) and `models_lib_comparison` is `match`. The stamp difference is part
  of this pair's provenance; the values still agreed to 1 µV.
- Local log: zero solver-diagnostic markers; the cold start engaged
  ("Operating point simulation skipped by 'uic'").

## What this supplies

The paired check `sim/README.md` requires before the 45-corner campaign has
passed at one corner with a same-engine pair, and the preflight fact #327,
#345 and #177 are sequenced behind is re-established. The campaign itself
(`corner-run.py sim/dropout-vs-load --backend batch` without the subset
flags) remains separate work (#375 Out of Scope; PR #561 carries such a
record whose ordering is held on that PR).

## local/deck.spice

The corner-run-generated corner deck with diagnostic-only changes versus the
generated deck: `set numdgt=10` and a `let`/`print` pair for the raw
crossing card (`meas_dropout_vin_x`), so the log carries all three metrics
beyond ngspice's 6-digit `meas` echo (the same technique as #381's
run-20261106). The headline values are unchanged from the committed
corner-run leg (`dropout_v` 0.397658 V, `vout_at_max_vin_v` 1.798832 V).
Run it from `local/` with the sibling `.spiceinit` (both inputs matter,
issue #190):

    cd sim/dropout-vs-load/diagnostics/issue-375/local
    ngspice -b -o ngspice.log deck.spice

## Reproduce the comparison

    python3 sim/bin/compare_dropout_paired.py \
        sim/dropout-vs-load/diagnostics/issue-375 --local-engine 47 \
        --remote-pass FAIL --local-pass FAIL \
        --out sim/dropout-vs-load/diagnostics/issue-375/comparison.json

Layout: `remote/v3.30/{request.json,request.spice,response.json,batch-receipt.json,ngspice.log}`,
`remote/corner-run.log`, `local/{deck.spice,ngspice.log,corner-run.log,.spiceinit}`.
Host paths inside the artifacts are the dispatch worker's worktree.
(`remote/v3.30/ngspice.log` is the engine log klt retained for the corner;
`local/ngspice.log` is the hand diagnostic run of the deck above.)
