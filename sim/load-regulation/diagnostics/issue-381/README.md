# Issue #381 — paired local/fleet load-regulation check (tt / 27 °C / 3.30 V)

Append-only diagnostic. **Not an evidence record and not a full-matrix refresh:**
it mints no `records/` entry and moves no `LATEST` pointer. Ratified targets
are unchanged. Scope: one corner, `--no-write`, both halves at commit
`a45f37b0651a2c38f3f4f073995c2d5ecda3c6c1` (2026-11-05).

## Result: equivalence NOT established (engine mismatch)

- Preflight (`sim/bin/batch-preflight.py`): ACCEPTED, job `klt-sim-3608eb5bf00a`,
  runner klt 0.9.0 / client 0.9.1.dev17+gd76e6fe1cb7a, compatibility `match`.
- Remote (`--backend batch`): 2 endpoint jobs `klt-sim-f92949db3af3` (tran1,
  0 A) and `klt-sim-45598ccfd812` (tran2, 50 mA), both `done`, **ngspice 46**,
  no diagnostics. Request netlist sha256: tran1 `60109fc6…ad0ab6`, tran2
  `9200317a…2848a2` (full values in `remote/tranN/response.json`).
- Local (default backend): host **ngspice-42**. Engine versions differ, so
  equivalence cannot be claimed regardless of the deltas. Local deck sha256
  `d12e01d1…f197e`.
- Both halves graded PASS (execution parity only, not spec compliance).
- `comparison.json` (from `sim/bin/compare_load_regulation_paired.py`) verdict:
  `engine_mismatch`. All six raw endpoint values and both derived differences
  agree with Δ = 0 at the printed resolution (7 significant digits = 1 µV at
  1.8 V, equal to the raw tolerance, so sub-µV agreement is not demonstrated).
  Tolerances were not widened.
- Unlike #384 (where the 50 mA tail envelope differed by ~62 µV between
  engines), no engine-dependent difference is visible here at 1 µV resolution.

## What a follow-up needs

A local ngspice 46 (host tools may not be changed) or a runner whose engine
matches the local one, plus higher print precision (e.g. `set numdgt`) as a
diagnostic-only change to settle sub-µV agreement. Handoff for #231: **defer**
the 45-corner campaign until a same-engine pair exists.

## Reproduce the comparison

    python3 -I sim/bin/compare_load_regulation_paired.py \
        sim/load-regulation/diagnostics/issue-381 --local-engine 42 \
        --remote-pass PASS --local-pass PASS \
        --out sim/load-regulation/diagnostics/issue-381/comparison.json

Layout: `remote/tranN/{request.json,request.spice,response.json,batch-receipt.json,ngspice.log}`,
`remote/corner-run.log`, `local/{deck.spice,ngspice.log,corner-run.log}`
(local `ngspice.log` is a hand run of the same generated deck, for full-precision
`meas` lines). Host paths inside artifacts are the dispatch worker's worktree.
