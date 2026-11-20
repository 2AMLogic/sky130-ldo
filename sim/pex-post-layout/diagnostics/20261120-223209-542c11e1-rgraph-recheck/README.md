# Resistance-graph recheck with per-net fallback reasons (issue #690)

First re-run of the `klt pex --resistance-graph` recheck on a build carrying
2AMLogic/klayout-tools#6130 (per-net `fallback_reason`), answering the question
the 2026-11-14 diagnostic (`20261114-193718-fabcb0c6-rgraph-recheck/`) could
not: **why each of the 27 legacy nets falls back**, and specifically what
blocks `VIN` / `VOUT`.

## Result (reason census, 28 nets — sums to the prior diagnostic's net count)

| `fallback_reason` (pex echo) | nets | which |
|---|---|---|
| *(none — `resistance_source: graph`)* | 1 | `N_FBB` |
| `terminal_count_not_two` | 22 | all remaining small/internal signal nets |
| `graph_too_large` | 3 | **`VIN`**, **`VOUT`**, `EA_OUT` |
| `graph_status_skipped` | 1 | `EA_CZ` |
| `pair_resistance_unavailable` | 1 | `VREF` |

**VIN and VOUT fall back with `graph_too_large`, not
`terminal_count_not_two`.** The extract leg's diagnostics name the exceeded
caps exactly:

- `VIN`: "77 terminals exceed the 64 cap" (`MAX_GRAPH_TERMINALS = 64`) —
  the cap fires before geometry is examined.
- `VOUT`: did **not** trip the terminal cap (no such diagnostic; it has ≤ 64
  terminals); its `metal1` polygon 0 needs up to **85,680 mesh cells** and its
  `metal2` polygon 0 up to **12,876** against `DEFAULT_MAX_DECOMPOSITION_CELLS
  = 4096` (the strapped/poured-rail geometry class).
- `EA_OUT`: "108 terminals exceed the 64 cap".

So the issue-#690 premise "a rail with gates plus current terminals stays
`legacy` even after #5894 lands" is right in outcome but not in mechanism for
the rails: VIN/VOUT never reach the two-terminal selection check — the build
caps refuse their graphs first. The 22 `terminal_count_not_two` nets do
confirm that selection rule as inferred (their graphs are all `ok`).

## Mapping: each reason → the upstream issue whose scope removes it

All states verified open via `gh api` at 2026-11-20T22:41Z (links are full
`2AMLogic/klayout-tools#N` references):

- **`terminal_count_not_two` (22 nets) → 2AMLogic/klayout-tools#6899** — the
  opt-in netlist mode that writes a multi-terminal net's resistance from the
  resistance graph (terminal-equivalent network reproducing
  `pair_resistance_ohm`), with "Make it reachable from `klt pex`" in its scope
  and an AC that `klt pex` accepts the mode. That is exactly "use the
  terminal-pair path resistance for nets with three or more terminals" for
  `klt pex`, so **no new issue is filed for this reason** (per the curator's
  absorbed check: #6899's scope does cover `klt pex`, not only `klt extract`).
  Caveats recorded there: #6899 is parked blocked by #6917 (deck cut values —
  needed when no `--resistance-graph-r-cut` is supplied; this diagnostic
  supplies 9.3, which is why **no `via_resistance_unknown` appears in this
  table**), and its mode composes with #6964 (below) — a >64-terminal net
  stays unsupported under it until the caps move.
  2AMLogic/klayout-tools#5894 / PR 2AMLogic/klayout-tools#6053 (echo and docs
  only) are related but explicitly do **not** remove this reason.
- **`graph_too_large` (3 nets: VIN, VOUT, EA_OUT) → 2AMLogic/klayout-tools#6964
  (newly filed from this diagnostic)** — the graph build caps
  (`MAX_GRAPH_TERMINALS=64`, `DEFAULT_MAX_DECOMPOSITION_CELLS=4096`,
  `MAX_GRAPH_NODES=5000`, `MAX_GRAPH_EDGES=20000`) are keyword-only parameters
  on `build_resistance_graph` that no `klt extract`/`klt pex` flag reaches,
  while `klt power` got `max_decomposition_cells` in #3124. #6964 carries a
  layout-free reproduction (kept in `upstream-repro/`). **This is the gap that
  actually blocks VIN/VOUT.**
- **`graph_status_skipped` (1 net: `EA_CZ`) → no issue, by design**: the net's
  graph has a single device terminal (`too_few_terminals`; 53 nodes, 82 edges)
  — a one-terminal net has no terminal pair to compute, so no upstream scope
  can or should "remove" this fallback. Stated here rather than filed.
- **`pair_resistance_unavailable` (1 net: `VREF`) → no issue filed; documented
  behavior, see below**: the graph is `ok` with 2 device terminals (98 nodes,
  156 edges) but reports `terminals_disconnected` — the terminals fall in 2
  disconnected groups, so the cross pair is `null`, exactly the
  `TerminalResistanceMatrix` contract. Whether the missing link is an
  extractor artifact or a path the graph deliberately excludes (e.g. through a
  device body) is not distinguishable from the report alone, and a
  block-independent reproduction of a *false* disconnection cannot be built
  from this private layout — so nothing is filed; if a future shareable case
  shows a genuinely-connected pair reported disconnected, file it then. (The
  same `terminals_disconnected` diagnostic appears informationally on 17 of
  the 22 `ok` multi-terminal nets without affecting their status.)

Cross-confirmation posted on 2AMLogic/klayout-tools#5894 (comment
`issuecomment-7052398788`, 2026-11-20): the census table without this block's
resistance values.

## Re-mint condition for the item-7 `klt pex` record

No record under `sim/pex-post-layout/records/` was minted or re-pointed by
this diagnostic. The exact condition for re-minting (per issue #690): **a klt
build on which `VIN` and `VOUT` are graph-derived and the 45 full-load rows
return a physical extracted `VOUT`.** Against today's upstream state that
requires, at minimum:

1. 2AMLogic/klayout-tools#6964 — caps raisable from the CLI (VIN: 77
   terminals > 64; VOUT: 85,680 mesh cells > 4,096), and
2. 2AMLogic/klayout-tools#6899 — a graph-derived value for a ≥3-terminal net
   reaches the written netlist (both rails have ≥3 device terminals, so the
   current two-terminal scalar selection can never pick them), with
3. the per-cut resistance supplied as here (`--resistance-graph-r-cut 9.3` or
   #6917's deck values) so no `via_resistance_unknown` intervenes.

Then the 45-corner `klt pex` re-mint runs via the batch backend (sharded per
closed issue #623), minting a **new** append-only record and re-pointing the
item-7 citation through its own issue — not here.

## Legs

| dir | leg |
|---|---|
| `main-6bd18bbc/` | `klt pex --extract-only` at 2AMLogic/klayout-tools `main` @ `6bd18bbc8637` (klt 0.9.3.dev2575+g6bd18bbc8637) — the #690 method leg; exit 4 (documented `--extract-only` success), 0-byte stderr |
| `extract-main-6bd18bbc/` | companion `klt extract --parasitics --resistance-graph`, same build/GDS/r-cut — carries the per-net `resistance_graph.diagnostics` the pex echo collapses; exit 0, stderr is one benign progress line |
| `upstream-repro/` | the layout-free `build_resistance_graph` reproduction behind 2AMLogic/klayout-tools#6964, with its output at the pinned build |

Input (read-only): `layout/ldo-core/reports/LATEST` → `20261112-110205-820ba8b3`,
`ldo_core.gds` sha256 `5e6171873b24b8d4c7af6f55d59600d84099cd13790c8320d8ccf074e657c1ca`
— byte-identical to the 2026-11-14 diagnostic's input, so the comparison to it
is build-only. Nothing under `records/` or any earlier diagnostic was touched;
this directory is append-only evidence.
