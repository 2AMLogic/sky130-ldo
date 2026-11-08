# Issue #384 — paired local/fleet line-regulation check (tt / 27 °C / 3.30 V)

Append-only diagnostic. **Not an evidence record and not a full-matrix refresh:**
it mints no `records/` entry and moves no `LATEST` pointer. Ratified targets
are unchanged. Scope: one corner, `--no-write`, both halves at commit
`bf6ee67234be7221d10bc4b8a0495b2e983e12bc` (2026-11-04).

## Result: equivalence NOT established (engine mismatch + tolerance breach)

- Preflight (`sim/bin/batch-preflight.py`): ACCEPTED, job `klt-sim-90981796865f`,
  runner klt 0.8.0 / client 0.8.1.dev1317+ga2804ab99263, compatibility `match`.
- Remote (`--backend batch`): 4 endpoint jobs `klt-sim-e52f23c0d388`,
  `-d3b65e630876`, `-3cd6979aec7e`, `-334d09838d3c` (tran1..tran4), all `done`,
  **ngspice 46**, no diagnostics. Request netlist sha256 per endpoint in each
  `remote/tranN/response.json` (`environment.netlist_sha256`).
- Local (default backend): host **ngspice-42**. Engine versions differ, so
  equivalence cannot be claimed regardless of the deltas.
- Both halves graded PASS (spec verdicts match; this is execution parity only).
- `comparison.json` (from `sim/bin/compare_line_regulation_paired.py`) verdict:
  `rejected`. Slopes agree (|Δ| < 1e-6 mV/V). Endpoint deltas:
  `vout_50ma_hi_min` +62 µV and `vout_50ma_hi_max` −65 µV exceed 1 µV and are
  larger than the local print resolution, so they are genuine differences
  (the 50 mA / 3.63 V tail envelope differs between engines 42 and 46;
  cause not investigated). The other flagged rows
  (|Δ| ≤ 4 µV on `vout_1ma_lo*`, `vout_50ma_hi`) are within the **local
  half's 6-significant-digit print resolution** (`corner-run.py` prints `%.6g`),
  so they are inconclusive, not demonstrated breaches.
- Tolerances were not widened.

## What a follow-up needs

1. A local ngspice 46 (same as the runner) — this worker has 42 and host tools
   may not be changed — or a way to read the runner's engine version up front.
2. Full-precision local endpoint values (the local harness only retains
   `%.6g`); a diagnostic-only extra precision would settle the sub-5 µV rows.

## Reproduce the comparison

    python3 -I sim/bin/compare_line_regulation_paired.py \
        sim/line-regulation/diagnostics/issue-384 --local-engine 42 \
        --remote-pass PASS --out sim/line-regulation/diagnostics/issue-384/comparison.json

Layout: `remote/tranN/{request.json,request.spice,response.json,batch-receipt.json,ngspice.log}`,
`remote/corner-run.log`, `local/deck.spice`, `local/corner-run.log`.
Host paths inside the artifacts are the dispatch worker's worktree.
