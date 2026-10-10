## Monte Carlo / mismatch experiments

Of the spec rows, **Output** (1.8 V ±2%, i.e. 1.764–1.836 V) is the one
that names a population/statistical bound rather than a PVT-corner limit, so
it is the one that gets a Monte Carlo mismatch experiment (issue #19) rather
than (or in addition to) a PVT corner sweep. Every other row (dropout,
PSRR, load transient, …) is itself a PVT-corner claim, already covered by the
corner-matrix experiments above.

`sim/bin/mc-run.py` is a **separate script from `corner-run.py`**, not an
extension of it (see the script's own module docstring for the full
rationale). It drives `klt sim`'s native `request.monte_carlo` field
(`{"n", "seed", "vary": "mismatch", "k_sigma"}` — see `docs/cli/sim.md` in
`2AMLogic/klayout-tools`) rather than reimplementing per-instance mismatch
sampling in this repo: `klt sim` re-runs one PVT point `n` times, each time
drawing a fresh per-instance `AGAUSS` mismatch term from sky130A's `tt_mm`
`.lib` section (confirmed present for both `nfet_g5v0d10v5` and
`pfet_g5v0d10v5` — the two device families this schematic instantiates — by
inspecting `libs.tech/combined/continuous/models_fet.spice` at the pinned PDK
commit), and reports per-measurement mean/stddev/quantiles/sigma-window
statistics plus a per-device-family "was mismatch actually active" report.

- **`mc-output-accuracy/`** — samples `vout_ss` (steady-state VOUT under a
  fixed 1 mA load, VIN=3.3 V/27 °C/`tt_mm`) against the ratified "Output" row's
  1.764–1.836 V window. **Current record** (`20260818-032827-81dc232`,
  supersedes the pre-#36 `20260817-235656-e500d71`): N=200 samples, seed
  `20260817`, k_sigma=3 — **181/200 individual-sample PASS**, and the mean±3σ
  sigma-window check **FAILS** (mean 1.717 V, stddev 2.154 V, window
  [−4.745 V, 8.180 V] vs. the 1.764–1.836 V bound) — overall `FAIL`. The
  median sample is well inside the window (p50 = 1.802 V, p5 = 1.787 V), so
  the distribution's *centre* meets the ratified row and the failure is entirely
  in its tail: p95 = 3.300 V, i.e. the top few percent of draws rail to `VIN`,
  and the worst sample (`mc147`, −19.345 V) is a non-convergent solve rather
  than a physical output — the same non-regulating-operating-point signature
  as the six degenerate PVT corners above. Reported mean/stddev are therefore
  dominated by those tail samples; the honest reading is "most of the
  population regulates, a tail does not", not "the mean output is 1.717 V".
  Same known-remaining-gaps caveat as the PVT experiments above — an honest
  finding at this design stage, not a harness defect.
- The pre-#36 record (`20260817-235656-e500d71`, 194/200, mean 1.854 V,
  stddev 0.232 V) is kept on disk per the append-only rule but is **not** the
  current evidence: it was sampled against the schematic as it stood before
  #35/#36 and before the `M_ENP4`/`M_ENP5` fix.
- **Current record (issue #118, 2026-09-25): `20260925-110312-8280915`**,
  supersedes `20260825-083111-4cb27f8` — same N=200 and seed `20260817` (so
  the same sample sequence), re-run against the post-#116 5000 µm pass device
  and **executed on the batch fleet** rather than locally. **185/200 PASS**
  (up from 177/200), 12 out of window, 3 errored — overall `ERROR`. Two
  things about this record are new and load-bearing:
  - It carries a **nominal-vs-spread decomposition** that `mc-run.py` now
    computes for every two-sided measurement, so a statistical row's record
    says *why* it missed instead of only how often. Here it reports the
    in-window population centred **+0.093 %** with stddev **8.33 mV** in a
    ±36 mV window (nearer edge **4.12σ** out, a ≈99.998 % yield on its own),
    and the nearest out-of-window sample **174σ** past that edge. Read it as
    the function's docstring in `sim/bin/mc-run.py` explains: order-1 means a
    contiguous tail (matching/centring is the lever), order-100 means a
    separate mode (matching is not).
  - It therefore **settles** the "distribution centre vs. tail" reading the
    `20260818-032827-81dc232` bullet above reached qualitatively. It is not a
    tail: 11 of the 12 misses sit at 3.284–3.308 V with VOUT pinned at the
    input rail, nothing lands between 1.825 V and 3.284 V, and that has been
    true in **all four** MC generations (exactly one sample in 800 has ever
    missed by a genuine distribution tail). The **Output** row is not a
    matching problem and never has been — see `design/README.md` → "#118: the
    three DC-accuracy rows do share one mechanism…", and **#164** for the
    design campaign that owns the rail mode.
- **`--backend`** (added in #118) selects the `klt sim` execution backend:
  `local`/`local-parallel` run `ngspice` on this machine, `remote`/`batch`
  hand the expanded sample grid to `klt`'s own remote/EC2-batch backends. A
  shared dispatch host that forbids hand-launched local `ngspice` grids needs
  `--backend batch`; the record then names the backend, the remote job id and
  the **remote** engine version, because the `Tools:` line describes this
  machine, which on a remote backend ran no samples at all. `corner-run.py`
  has no equivalent and cannot easily get one — see
  2AMLogic/klayout-tools#2482.
- This experiment's directory layout adds `klt-requests/` and
  `klt-responses/` (the raw `klt sim` request/response JSON, which *is* the
  append-only evidence for an MC run — see the script's docstring for why no
  per-sample `.log` files are kept by default) alongside the same
  `testbench/`, `netlist-snapshots/` and `records/` convention the PVT
  experiments use.
- **`mc-ic-screen-a/`, `mc-ic-screen-b/`, `mc-ic-screen-d/`** (issue #164) —
  three **diagnostic** MC slugs, not spec claims: variants A, B and D of the
  four-variant initial-condition screen that showed the `mc-output-accuracy`
  bench's rail mode is its own unconstrained `.op`, not a second equilibrium of
  the loop (variant C is the shipped bench itself, i.e. `mc-output-accuracy`).
  All three run the *same* single point (`tt_mm`, 27 °C, 3.3 V, 1 mA) and the
  same `vout_ss` card against the same ratified window, so their tallies are
  directly comparable with `mc-output-accuracy`'s records; all three add 14
  hierarchical `.meas` **node-dump** cards, which are unbounded on purpose
  (a `.meas` card with no `limits` gets a distribution but no verdict — see the
  `margin n/a` rendering in `mc-run.py`). A freezes the *pre-#164* bench (EN a
  DC level, no `uic`); D shares A's testbench file byte-for-byte and differs
  only by `uic`; B is A plus one `.ic` card seeding the `.op` at regulation.
  **Why separate slugs:** `measurements/build_characterization_report.py` maps
  the `Output` row to `mc-output-accuracy` and reads the *lexicographically
  last* record under the mapped slug, so a later-timestamped screen variant
  filed there would silently become the row's evidence. Nothing maps a spec row
  to these three (same as `pdk-smoke`), so they are inert to that pipeline.
  Full write-up, record ids and re-derivation recipes: `design/README.md` →
  "#164".
- **`mc-output-accuracy-negctl/`, `mc-output-accuracy-engine-check/`** (issue
  #211) — two MC slugs that exist only to give `mc-output-accuracy`'s `klt yield`
  report a **negative control**, and neither of which claims anything about the
  LDO. `-negctl/` is the seeded, known-bad variant (feedback divider mis-ratioed
  +10 % via a declared `netlist_patch`); its `FAIL` is the intended result.
  `-engine-check/` is the *undegraded* bench re-run on the host that ran the
  control, to measure the executor difference between the two rather than assume
  it small. **Why separate slugs**, same reason as the `mc-ic-screen-*` group
  above: nothing in `measurements/build_characterization_report.py` maps a spec
  row to them, so a later-timestamped deliberately-broken record can never
  become the `Output` row's evidence. Full write-up: "`--negative-control`"
  under "`klt yield` records" below, and `signoff/README.md` → "The negative
  control, and what it found".
- **`ic-screen-125c-v/`, `-f/`, `-b/`, `-c/`, `-h/`** (issue #169) — five
  **diagnostic** `corner-run.py` slugs, not spec claims, filed apart from
  `dropout-vs-load/` for the same `EVIDENCE_MAP` reason as the `mc-ic-screen-*`
  slugs above. They re-test `#81` item 2 (a reported second equilibrium at
  125 °C/50 mA) under four initial-condition contracts on the current DUT — V
  `#81`'s own (`.ic v(vout)` only + `uic`), F the full eleven-node `.ic` +
  `uic`, B the same `.ic` without `uic`, C a cold EN-edged start — plus H, V's
  deck on a frozen copy of `#81`'s DUT under `ic-screen-125c-h/dut/`. F and B
  share one testbench file (byte-identical netlist snapshots). Each dumps 14
  internal nodes and grades `0 ≤ V(N_FBB) ≤ V(FB) ≤ V(VOUT) ≤ VIN` as four
  `min = 0` slacks. Result: every variant regulates everywhere (H's one `FAIL`
  is the pre-#90 thermal-shutdown trip at `sf`), and `#81` item 2 is withdrawn
  — the second equilibrium had been these benches' ordinary 125 °C regulating
  state all along (#118's blockquote above, which calls the #60/#71/#81 family a
  "second-stable-equilibrium" family, predates both #164 and #169). Write-up:
  `design/README.md` → "#169".

### `klt yield` records — a *derived* record kind (issue #203)

`sim/bin/yield-run.py` mints the first record kind in this directory that
measures nothing. It takes an **already-committed** `klt sim` Monte Carlo
response as its input, re-reads the per-sample values in it, and asks
`klt yield` (`docs/cli/yield.md` in `2AMLogic/klayout-tools`, epic #710) for a
yield estimate with its confidence interval, a distribution/normality fit,
Cpk/sigma-to-spec and a sample-size verdict. It runs no `ngspice`, resolves no
PDK, and cannot change a measured number — which is why it is safe to run
anywhere, including on a machine with no PDK install, and why it can never be
the thing that supersedes a campaign.

```
mc-output-accuracy/
  klt-requests/
    <record-id>.yield-limits.json    the spec-limits document klt yield was given
  klt-responses/
    <record-id>.yield.json           the klt yield report (the raw evidence)
  records/
    <record-id>.{json,md}            summary record, same fields as any other
```

The `.yield.json` / `.yield-limits.json` suffixes follow
`sim/pex-post-layout/`'s precedent for a derived `klt` report
(`<record-id>.pex.json` beside the `<record-id>.sim-schematic.json` it was
derived from) rather than inventing a second evidence directory. The record id
is minted the usual way (`<YYYYMMDD>-<HHMMSS>-<short-sha>`) and is **its own**
id, not the source campaign's — a derived analysis of a frozen sample set is a
new record, and re-running it later against the same samples mints another one
rather than overwriting this one.

Three conventions worth knowing before reading such a record:

- **Two provenance blocks, on purpose.** The record's `Tools`/`Repo state`
  lines describe the `klt`/`klt_yield_native`/host that did the *arithmetic*;
  the `Source campaign` block quotes the ngspice/PDK/host that produced the
  *samples* from that campaign's own record. Conflating them would claim a PDK
  this run never touched.
- **The spec-limits document is derived, not retyped.** `klt yield` needs
  min/max for every measurement it grades, and the document it is given wins
  over whatever the samples carry. `yield-run.py` builds it from the
  experiment's own `experiment.json` (`mc_measurements[].limits`) so there is
  exactly one place in the repo stating a ratified bound, then commits the
  document it actually used under `klt-requests/`.
- **No `target_yield` is ever synthesised.** `spec/target-spec.md` ratifies no
  yield, sigma or Cpk target for this block, so none is declared, and
  `klt yield` reports `status: "reported"` — *"no measurement declared a
  target_yield, so no yield claim was checked"* — rather than `pass`/`fail`.
  That is the honest shape: the estimates are evidence, and the standard they
  would be graded against does not exist yet. Ratifying one is a `spec/`
  decision record, not a runner flag.

**Reproducing one** (no PDK, no ngspice — but see the caveat):

```bash
sim/bin/yield-run.py \
  sim/mc-output-accuracy/klt-responses/20260925-131502-808cece.json \
  --author "you@example.com"
```

The caveat is `klt`'s: the statistics run in `klt_yield_native`, a Rust
extension that is **not published as a wheel**, so it is unreachable from
`pip install klayout-tools` / `uv tool install klayout-tools` (including the
git-pinned form) and `klt yield` exits 1 with a message saying so. Getting it
needs a `klayout-tools` repo checkout plus a Rust toolchain —
`maturin develop --release` inside `native/yield/`, or `uv sync --extra dev
--group yield`; to add it to an *existing* `klt` install rather than a checkout
venv, `maturin build --release --interpreter <that klt's python>` and install
the resulting wheel into it. Filed upstream, per this repo's friction protocol,
as [klayout-tools#2531](https://github.com/2AMLogic/klayout-tools/issues/2531)
(and previously #1061 / #2466) — so this is a known tool-distribution gap, not
a step this repo can remove. It is also why `signoff/check.sh`, which runs on
every PR, does **not** re-run `klt yield`: the committed report is the evidence,
and CI grades it with `klt signoff` (which needs no Rust).

First record: `mc-output-accuracy/records/20260927-030409-1a14401.md`, over the
`20260925-131502-808cece` campaign (n=200, seed `20260817`) — empirical yield
*at least* 98.1725 % at 95 % confidence (100 % of 200 samples in window, so the
interval is bounded only from below), Cpk 1.34664, sigma-to-spec 4.03992σ,
sample size `sufficient`.

**Current record: `20260927-093538-227be3e`** (supersedes the above; issue
#211), which adds the one thing a yield estimate cannot supply about itself.

#### `--negative-control` — and the one case where this record kind *does* need a simulation (issue #211)

A yield statistic that has never been shown to reject a bad design is an
assumption, not evidence. `klt yield` takes a **seeded, known-bad variant's own
samples** as a `negative_control` on a measurement and checks that the
deliberate defect shows up as a *statistically distinguishable* drop in yield —
non-overlapping Clopper-Pearson intervals, not merely a lower point estimate
(`docs/cli/yield.md#negative-control`). T1 signoff item 6's checklist text asks
for exactly that.

Supplying it needs a second, deliberately degraded **campaign**, so this is the
one leg of the `klt yield` story that is a real ngspice run. Two experiments
under `sim/` exist only to serve it, and neither makes any claim about the LDO:

- **`mc-output-accuracy-negctl/`** — the known-bad variant. `mc-output-accuracy`'s
  bench verbatim (same testbench schematic, *referenced* not copied; same
  `tt_mm`/27 °C/3.3 V mismatch point; same `uic` + 100 µs EN edge
  initial-condition contract; same `vout_ss` measurement against the same
  **unrelaxed** ratified window; same seed) with exactly one declared defect:
  the feedback divider's top leg `XR_FB_A` lengthened 180 µm → 198 µm (+10 %),
  moving the ideal regulation point 1.8 V → 1.86 V. Its aggregate status is
  `FAIL` **by design** — a control exists to be rejected. Result: mean
  1.860065 V, **0 of 40 draws in window**, so the nominal's `≥ 98.1725 %` and
  the control's `≤ 8.8097 %` intervals do not overlap → `detected`.
- **`mc-output-accuracy-engine-check/`** — the executor cross-check. The
  campaign of record ran on the EC2 batch fleet; the control could not (no
  resolvable batch submit credential on the host that ran it), so it ran on
  local ngspice. That executor difference sits underneath any control-vs-nominal
  comparison, so it is *measured* rather than asserted small: the nominal bench
  **undegraded** (deck byte-identical to the campaign of record's snapshot),
  same point, same seed, on the host and engine that produced the control.
  Result: the executor moves the mean by −1.50 mV where the seeded defect moves
  it by +59.99 mV — 40× — and the two σ agree to 0.6 %. It also measured that
  the **seed contract does not survive an engine change** (per-sample values
  differ by ±6–12 mV on byte-identical decks), so the two sample sets are
  independent draws from the same distribution, not a paired series.

`experiment.json` gained a **`netlist_patch`** block for this: an exact-string
substitution list with an **asserted occurrence count**, applied by `mc-run.py`
to the netlisted deck between xschem and `klt sim`. That keeps `design/` the
single source of truth (no frozen duplicate of the design schematic to rot
alongside it, the drift the `mc-ic-screen-*` FROZEN COPY headers have to warn
about in prose), and the count assertion means a design change makes the
campaign **refuse to run** rather than quietly sample an undegraded circuit and
report it as a negative control. The patched deck is what the record's netlist
snapshot contains, so the committed evidence is the deck that ran.

```bash
# 1. run the degraded variant as its own append-only campaign
sim/bin/mc-run.py sim/mc-output-accuracy-negctl --seed 20260817

# 2. mint a yield record over the NOMINAL campaign, carrying that control
sim/bin/yield-run.py \
  sim/mc-output-accuracy/klt-responses/20260925-131502-808cece.json \
  --negative-control sim/mc-output-accuracy-negctl/klt-responses/<record-id>.json
```

Two consequences of step 2 worth knowing, both of which follow from a tool gap
rather than a choice made here:

- **It mints a fourth artifact: `klt-responses/<record-id>.samples.json`.**
  `klt yield` reads a `negative_control` from either input shape it accepts, but
  `klt sim` has no request-side field for one and never emits one on its
  response rollup — so a `klt sim` response can carry a negative control only if
  a committed response is hand-edited, which this directory's append-only
  discipline forbids outright. So `yield-run.py` mints a **sample-set document**
  instead, carrying both campaigns' own per-sample values, and runs `klt yield`
  against that. Nothing in it is a new number: every value is copied out of a
  committed `klt sim` response by the same rule `klt yield` applies to a sim
  report itself. Filed generically upstream as
  [klayout-tools#2563](https://github.com/2AMLogic/klayout-tools/issues/2563).
- **That copy is cross-checked, not trusted.** `yield-run.py` re-runs
  `klt yield` a second time directly over the nominal response alone (the
  pre-#211 input shape) and requires the nominal `distribution`, `capability`,
  `sample_size` and `yield.empirical` blocks to be **byte-equal**, aborting
  rather than recording on any difference. The record reports the verdict
  (`IDENTICAL`), so the assertion is auditable after the fact. It also shifts
  what `klt signoff` hashes for an item-6 citation, since a yield citation is
  hashed by the artifact its `samples` field names — see `signoff/README.md`.

See `signoff/README.md` → "Item 6 is `met` — what it says, and the one thing it
does not" → "The negative control, and what it found" for the full reading,
including what the `detected` verdict does *not* establish.

