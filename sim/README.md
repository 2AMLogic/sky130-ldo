# sim/ — the simulation harness and its evidence records

This directory holds the reproducible xschem + ngspice + sky130 harness and the
results it produces. Two rules from the root `CLAUDE.md` shape everything here:

- **Verification is the product.** No claim without a testbench. Every recorded
  result carries a PVT corner matrix unless the record states why a subset was
  used — the runner *enforces* that by refusing to write a subset record
  without a `--subset-reason`.
- **`sim/` is append-only evidence.** Records are never edited or deleted. A
  re-run — even one that corrects a mistake — mints a new record id; a
  correction points at what it replaces via a `Supersedes` field. The runner
  refuses to start if the record id it would mint already exists on disk.

The directory layout, record-id scheme and summary-record fields are ported
from the sibling [`sky130-bandgap`](https://github.com/2AMLogic/sky130-bandgap)
repo's harness (same PDK, same pin, issue #2), so the two evidence trails read
as one house style. `pdk-smoke` below is harness plumbing only (PDK/tool
liveness, not a spec claim). The block's own testbenches — `load-transient`,
`psrr-dc`, `dropout-vs-load` (issue #18) and `loop-gain` (issue #25) — each
exercise the LDO core-regulation-loop schematic from issue #14
(`design/ldo_3v3in_1v8out.sch`, instantiated via its companion subcircuit
symbol `design/ldo_3v3in_1v8out.sym`) against a DRAFT row of
`spec/target-spec.md`. `spec/target-spec.md` is not yet ratified (issue #1
still open), so every measurement bound these testbenches use cites a DRAFT
spec row directly rather than an invented "final" number, and each
experiment's `claim` says so. Issues #18 and #25 stood the harness up with
explicit `--quick` subsets (3 corners, `--subset-reason` cited in the record);
issue #19 ran the full 45-point PVT matrix declared in each experiment's
`experiment.json` for `load-transient`, `psrr-dc` and `dropout-vs-load`, plus a
Monte Carlo/mismatch experiment (`mc-output-accuracy/`, see "Monte Carlo /
mismatch experiments" below) for the one DRAFT row that carries a statistical
(population) claim rather than a PVT-corner claim. **All four testbenches still
record `FAIL`** against their DRAFT bounds — an honest, expected finding given
this schematic's remaining known gaps (see `design/README.md`'s "Known gaps /
follow-on scope"), not a harness defect. Per issue #19's own guardrail, none of
this is a final pass/fail verdict against a *ratified* spec — issue #1 (spec
ratification) is still open, so every record here cites the current DRAFT row
only.

---

## Quick start (cold machine)

```bash
# 1. install the pinned PDK (~1 min; see sim/pdk.json for the pin)
volare enable --pdk sky130 c6d73a35f524070e85faff4a6a9eef49553ebc2b

# 2. sanity-check the toolchain and PDK resolution
python3 sim/bin/corner-run.py --check-env

# 3. run the harness acceptance test (unit tests + a quick PVT subset)
sim/selftest.sh --quick

# 4. run the harness smoke test over the full PVT matrix (45 points, ~4 min)
python3 sim/bin/corner-run.py sim/pdk-smoke
```

Prerequisites, all machine-level (not vendored here): `ngspice`, `xschem`,
`volare`, `python3` (3.9+, standard library only). See
`docs/environment-setup.md` for the full reproducible bring-up.

### Driving the tools by hand

```bash
source sim/bin/pdk-env.sh      # exports PDK_ROOT, PDK, SKY130_MODEL_LIB, XSCHEM_RCFILE
xschem --rcfile "$XSCHEM_RCFILE" sim/pdk-smoke/testbench/tb_pdk_smoke.sch
cp sim/spiceinit ./.spiceinit  # ngspice needs these settings to read PDK libs
```

`sim/bin/pdk-env.sh` is a thin wrapper around `corner-run.py --print-env`, so
interactive sessions and the runner resolve the PDK identically.

---

## How the harness is wired

| Piece | File | Role |
|---|---|---|
| PDK pin | `sim/pdk.json` | open_pdks commit, variant, model-library path, the process-corner names that actually exist in the PDK library |
| ngspice settings | `sim/spiceinit` | `ngbehavior=hsa` etc. required to read the sky130 libs; copied into the scratch run dir as `.spiceinit` |
| xschem config | `sim/xschemrc` | project-local rc that sources the PDK's own xschemrc (so `sky130_fd_pr/*.sym` resolves) and keeps generated netlists out of the tracked tree |
| corner runner | `sim/bin/corner-run.py` | netlist → deck → ngspice → parse → record; also `--check-env` / `--print-env` |
| Monte Carlo runner | `sim/bin/mc-run.py` | netlist → `klt sim` mismatch request → record; see "Monte Carlo / mismatch experiments" below |
| env helper | `sim/bin/pdk-env.sh` | `source` it for interactive xschem/ngspice work |
| acceptance test | `sim/selftest.sh` | unit tests + `--check-env` + an end-to-end PVT run; see below |
| unit tests | `sim/tests/` | PDK-free coverage of the runner's pure helper functions |
| experiment | `sim/<slug>/experiment.json` | what is being claimed, which corners, which measurements and their limits |

**PDK resolution order**: `$PDK_ROOT` → `volare path` → `default_pdk_root` from
`sim/pdk.json`; variant from `$PDK` → `variant` in `sim/pdk.json`. The runner
resolves the PDK directory symlink back to its volare version hash and
**refuses to run against a version other than the pin** unless
`--allow-pdk-mismatch` is passed — in which case the record says so.

**What the runner injects** (so one testbench serves the whole matrix): the
`.lib <models> <corner>` include, `.temp`, `.param vsup=<supply>`, `.option`s
from the manifest, and the `.control` block that runs the analyses, evaluates
each measurement expression into a `meas_<name>` vector and prints it. The
testbench schematic therefore contains no corner, no temperature, no numeric
supply and no analysis block.

**Per-corner artifacts**: each corner's `.log` embeds the exact deck that was
fed to ngspice (prefixed with `|`) plus raw stdout/stderr, so a record is
auditable without regenerating anything. Scratch decks and xschem output live
in the gitignored `sim/build/`; only the netlist snapshot, the per-corner logs
and the record are committed.

---

## Directory / naming convention

```
sim/
  README.md                          # this file
  pdk.json                           # PDK version pin
  spiceinit                          # ngspice init settings
  xschemrc                           # project-local xschem config
  selftest.sh                        # harness acceptance test (issue #2)
  bin/
    corner-run.py                    # PVT corner runner (+ --check-env / --print-env)
    mc-run.py                        # Monte Carlo (mismatch) runner, via `klt sim`
    pdk-env.sh                       # `source` for interactive use
  tests/
    test_corner_run.py               # PDK-free unit tests for corner-run.py's helpers
  build/                             # gitignored scratch (decks, xschem netlists)
  <experiment-slug>/                 # e.g. pdk-smoke (PVT), mc-output-accuracy (Monte Carlo)
    experiment.json                  # manifest: claim, corners, measurements, limits
    testbench/                       # xschem schematic(s) for this experiment
    netlist-snapshots/
      <record-id>.spice              # frozen netlist used for this record
    corners/                         # PVT experiments only
      <record-id>/
        <corner-id>.log              # deck + raw ngspice output per PVT point
    klt-requests/                    # Monte Carlo experiments only
      <record-id>.json               # the `klt sim` request actually submitted
    klt-responses/                   # Monte Carlo experiments only
      <record-id>.json               # `klt sim`'s full per-sample response (the raw evidence)
    records/
      <record-id>.md                 # append-only summary record (human)
      <record-id>.json               # same record, machine-readable
```

- **`<experiment-slug>`** — kebab-case name for the claim under test. One
  directory per distinct claim, not per run.
- **`<record-id>`** — `<YYYYMMDD>-<HHMMSS>-<short-git-sha>` in UTC. The same id
  ties together the netlist snapshot, the per-corner logs and both record
  files for one run. Re-runs mint a new id.
- **`<corner-id>`** — `<process>_<temp>c_<supply>v`, e.g. `ss_-40c_1.62v`,
  `tt_27c_1.80v`, `ff_125c_1.98v`.
- **`testbench/`** is not versioned per record. If a testbench change could
  affect comparability across records, say so in the new record (the frozen
  netlist snapshot is what actually pins what ran).

## Summary record fields

Each run writes `records/<record-id>.md` (and a `.json` twin with every parsed
number, limit and verdict, for tooling):

| Field | Meaning |
|---|---|
| Record ID | matches the filename, the snapshot and the `corners/` subdirectory |
| Experiment | slug + title from the manifest |
| Claim | which spec parameter/line this substantiates (`spec/target-spec.md#<row>` once the spec is ratified — see issue #1); `pdk-smoke` is harness-only, not a spec claim |
| Netlist provenance | `schematic` (`design/…`, `sim/…/testbench/…`) or `extracted` (post-layout) — required so post-layout re-runs are distinguishable |
| PDK | variant + open_pdks commit actually used, whether it matches `sim/pdk.json`, and the model library path |
| Tools | ngspice / xschem / OS / python versions used |
| Repo state | short sha, branch, and whether the working tree was dirty at run time |
| Corner matrix run | the (process, temperature, supply) points actually executed; must be the full PVT matrix unless a subset reason is recorded |
| Statistical convention | N samples and sigma level for distribution claims; `N/A` for corner-matrix claims |
| Result | per-corner pass/fail with measured values, plus an overall verdict |
| Links | testbench, manifest, netlist snapshot, raw logs, json record |
| Timestamp / author | UTC timestamp and who (human or agent) ran it |
| Supersedes | prior `<record-id>` this corrects or re-runs; `(none)` otherwise |

### Append-only rule

`records/*` files are never edited or deleted after creation — this applies
even to typo fixes, because the append-only guarantee is the whole point of an
evidence trail. Corrections mint a new record that references the prior one via
**Supersedes**.

---

## Writing a new experiment

1. `mkdir -p sim/<slug>/{testbench,netlist-snapshots,corners,records}`
2. Draw the testbench in xschem (`--rcfile sim/xschemrc`). Leave out the
   corner include, `.temp`, the numeric supply (use `'vsup'`) and any
   `.control` block — the runner owns those. Name the nets you intend to
   measure; connectivity by `lab_pin` label is fine.
3. Write `sim/<slug>/experiment.json` — see `sim/pdk-smoke/experiment.json`
   for a worked example. Process-corner names must appear in `sim/pdk.json`
   `process_corners`.
4. Run it: `python3 sim/bin/corner-run.py sim/<slug>`
5. Commit the produced record, netlist snapshot and per-corner logs. (The
   root `.gitignore` ignores `*.log` globally but un-ignores
   `sim/*/corners/**/*.log`, which is committed evidence.)

### Runner options

| Flag | Effect |
|---|---|
| `--check-env` | check ngspice/xschem/volare/PDK are usable and exit (0 if all OK) |
| `--print-env` | print PDK env exports and exit |
| `--process tt,ss` / `--temp 27` / `--supply 1.8` | override a matrix axis (marks the run a subset) |
| `--quick` | run the manifest's `quick_subset` only |
| `--subset-reason "…"` | **required** for any subset; recorded verbatim |
| `--supersedes <record-id>` | record which prior record this replaces |
| `--author`, `--timeout` | record author (default `git config user.email`), per-corner ngspice timeout |
| `--allow-pdk-mismatch` | run against a non-pinned PDK; the record flags it |
| `--dry-run` | netlist, print the corner list and one deck, run nothing, write nothing |
| `--no-write` | run every corner for real (ngspice included) but skip writing an evidence record — for CI/selftest liveness runs that should not mint new evidence on every push |

Exit status: `0` all checks passed, `2` a record was written (or would have
been, under `--no-write`) but something failed, `1` harness/setup error (no
record written).

### Writing a new Monte Carlo experiment

Same testbench-authoring rule as above (no corner include, no numeric supply,
no `.control` block), but the manifest and runner differ — see "Monte Carlo /
mismatch experiments" below for the mechanism, and `sim/mc-output-accuracy/`
for a worked example manifest (`mc_corner`, `mc_analysis`, `mc_measurements`,
`monte_carlo_defaults` keys instead of `corners`/`deck`/`measurements`/
`quick_subset`). Run it with `python3 sim/bin/mc-run.py sim/<slug> --n <N>
--seed <seed>` (`--seed` is required and recorded verbatim — the seed
contract is what makes an MC record reproducible); commit the produced
record, netlist snapshot, and the `klt-requests/`/`klt-responses/` JSON.

---

## `pdk-smoke` — the harness's own testbench

`sim/pdk-smoke/` is not a spec claim. A 1 MΩ resistor biases a diode-connected
sky130 core `nfet_01v8` and the runner measures `vgs` and the supply current.
Both quantities are strongly process- and temperature-dependent, so this
experiment proves four things at once: the PDK models load, xschem netlists
headlessly, ngspice parses the deck, and the corner/temperature/supply knobs
actually reach the simulator (asserted by the `vgs` spread check, not just
eyeballed).

It deliberately uses the 1.8 V **core** device family (`nfet_01v8`), not
either candidate pass-device flavor from the still-open "sky130 porting
question" in `spec/target-spec.md` (`pfet_g5v0d10v5` under framing A, the 1.8 V
core devices under framing B) — this testbench is harness plumbing, standing
up ahead of and independent of that ratification decision (issue #1), not a
prejudgment of it.

Keep it green: it is the first thing to run when a testbench misbehaves, to
tell "my circuit is wrong" apart from "my harness is broken".

## The LDO's own testbenches (issues #18 and #25)

Each testbench below instantiates `design/ldo_3v3in_1v8out.sch` (issue #14,
including the current-limit and soft-start circuitry issue #22 added and the
current-mirror-OTA output stage plus sized compensation issue #25 added)
hierarchically, via its companion subcircuit symbol
`design/ldo_3v3in_1v8out.sym` (see `design/README.md` for why the symbol has
to be co-located with the schematic). All three share the same VIN/EN/VREF
stimulus convention (VIN and/or EN carry the corner runner's `'vsup'`; VREF is
a fixed 1.2 V placeholder — see `design/README.md`'s "VREF interface
caveat, and the reference common mode", which explains why 1.2 V/1:2-divider
is the value that actually regulates, unlike the earlier 0.6 V/2:1
convention) and the same output network (1 µF `C_OUT` + 10 mΩ `R_ESR`, a
representative point inside DR-002's *proposed* 0–500 mΩ window, not a sweep
of it). Full detail — exact stimulus, measurement expressions, and which
DRAFT spec row each bound cites — lives in each experiment's own
`experiment.json` `claim` field, per this directory's own convention; this
section is a map, not a duplicate of that detail.

- **`load-transient/`** — `I_LOAD` steps 1↔50 mA (1 µs edges) at `VOUT`;
  measures undershoot/overshoot against `spec/target-spec.md`'s DRAFT "Load
  transient" row (peak excursion ≤150 mV). Latest quick-subset record
  (`20260818-014345-01b7905`, supersedes `20260817-212623-66b28fc`):
  **PASS** at `tt_27c_3.30v` and `ss_-40c_2.97v` (undershoot 0.136 V /
  0.125 V, improved from 0.146 V / 0.137 V), **FAIL** at `ff_125c_3.63v`
  (undershoot 0.156 V) — overall `FAIL`, but that corner improved from
  0.941 V to 0.156 V, i.e. from six times the bound to four percent over it.
  Full 45-point PVT records (issue #19) are listed under "Full PVT matrix
  records (issue #19)" below.
- **`psrr-dc/`** — small-signal AC sweep on VIN (1 kHz, 100 kHz) at a single
  ~1 mA load point; measures PSRR against the DRAFT "PSRR" row (>50 dB @
  1 kHz, >20 dB @ 100 kHz). Characterizes one load point, not both 1 mA and
  50 mA the DRAFT row names — see the testbench schematic's header for why.
  Latest quick-subset record (`20260818-015127-01b7905`, supersedes
  `20260817-212331-66b28fc`): `FAIL` at all three corners (1 kHz PSRR
  23.3 dB / 23.6 dB / 22.4 dB, all below the 50 dB bound). This is the one
  place the issue-#25 revision is a mixed result rather than an improvement.
  The `ff_125c_3.63v` corner went from **−1.2 dB** (the loop was *amplifying*
  1 kHz supply ripple, because that corner had no valid regulating operating
  point) to 22.4 dB; but the `tt`/`ss` 1 kHz figures fell from 26.1 dB /
  39.1 dB, and 100 kHz fell from 36.7 dB / 35.6 dB / 33.1 dB to 32.9 dB /
  31.7 dB / 34.6 dB. Lower 1 kHz PSRR is the expected price of a deliberately
  lower loop crossover — PSRR at a given frequency tracks loop gain at that
  frequency — and it is recorded rather than glossed, since neither the old
  nor the new number meets the row. Buying it back is coupled to the same
  Iq-budget question `design/README.md` and the DR-002 append both land on.
- **`dropout-vs-load/`** — DC VIN sweep at a fixed 50 mA load (the DRAFT
  spec row's own gf180-mirrored "sweep Vin toward Vout" method); measures the
  Vin–Vout margin against the DRAFT "Dropout @ 50 mA" row (<300 mV). Latest
  quick-subset record (`20260818-014918-01b7905`, supersedes
  `20260817-212426-66b28fc`):
  `FAIL` at all three corners (dropout 0.531 V / 0.365 V / 1.274 V, versus
  0.613 V / 0.365 V / 1.354 V before). Both records also carry a
  `vout_at_max_vin_v` sanity measurement that lands on a non-regulating
  branch at exactly one corner — `ss` in the older record (3.40 V), `tt` in
  this one (3.34 V) — while the same operating point regulates correctly in
  a plain `.op` (see `design/README.md`'s DC grid). That is a DC-sweep
  continuation artifact of this testbench, pre-dating and surviving the #25
  revision rather than caused by it; chasing it belongs with #19's fuller
  characterization.

- **`loop-gain/`** (issue #25) — AC loop gain, phase margin and gain margin
  against `spec/target-spec.md`'s DRAFT "Stability" row (PM ≥ 45°, GM ≥ 10 dB
  worst corner). Unlike the three above it walks its own second axis: each
  PVT point runs **seven** AC sweeps, `alter`-ing `C_OUT`/`R_ESR`/`R_LOAD`
  across DR-002's *proposed* window (`C_eff` ∈ {0.33 µF, 4.7 µF} × load ∈
  {0, 1, 50 mA} at 10 mΩ, plus the 500 mΩ ESR ceiling), so the C_out/ESR axis
  is complete even in a `--quick` record. Because the block's feedback
  divider is internal — the LDO has no port a testbench can cut — the loop
  gain is recovered from closed-loop injection at `VREF` as `T = X/(1−X)`
  with `X = v(xldo.fb)`; the testbench header derives that and states the one
  approximation it makes. First record (`20260818-014128-01b7905`): `PASS` at
  `ff_125c_3.63v`, `FAIL` at `tt_27c_3.30v` and `ss_-40c_2.97v` — overall
  `FAIL`, and the failures are confined to the **0 mA** window points
  (15.6–19.3° at 0.33 µF, 38.1° at 4.7 µF/`ss`). DR-002's own low-`C_eff`
  corner measures 55.6–64.5° with 18.7–19.9 dB of gain margin. See the append
  this issue added to DR-002 for what the 0 mA shortfall does and does not
  settle.

None of the four fully meets its DRAFT bound yet. This is an honest,
expected finding, not a harness bug — and the reason has moved. The #18
records were dominated by two gaps issue #25 has now closed: an unsized
placeholder compensation and a five-transistor error amplifier whose output
could not swing to `VIN`. With those closed, `load-transient` passes two of
three corners and misses the third by 4%, `dropout-vs-load` and `psrr-dc`
still miss by a wide margin, and `loop-gain` fails only at the no-load end of
DR-002's window. What remains is documented in `design/README.md`'s "Known
gaps / follow-on scope" and in the DR-002 append: the pass device's own
`gm_pass/(2π·C_out)` pole at no load, an Iq budget that does not exist yet,
and the fact that every record here is still a 3-corner subset rather than
the 45-point matrix that would license a worst-corner claim (#19).

## Monte Carlo / mismatch experiments

Of the DRAFT spec rows, **Output** (1.8 V ±2%, i.e. 1.764–1.836 V) is the one
that names a population/statistical bound rather than a PVT-corner limit, so
it is the one that gets a Monte Carlo mismatch experiment (issue #19) rather
than (or in addition to) a PVT corner sweep. Every other DRAFT row (dropout,
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
  fixed 1 mA load, VIN=3.3 V/27 °C/`tt_mm`) against the DRAFT "Output" row's
  1.764–1.836 V window. First record (`20260817-235656-e500d71`): N=200
  samples, seed `20260817`, k_sigma=3 — **194/200 individual-sample PASS**,
  but the mean±3σ sigma-window check **FAILS** (mean 1.854 V, stddev 0.232 V,
  window [1.157 V, 2.550 V] vs. the 1.764–1.836 V bound; worst single sample
  3.312 V at `mc188`) — overall `FAIL`. Same known-immaturity caveat as the
  PVT experiments above (unsized `C_COMP`/`C_CL`, light-load/high-`VIN`
  output-swing ceiling) — an honest finding at this design stage, not a
  harness defect.
- This experiment's directory layout adds `klt-requests/` and
  `klt-responses/` (the raw `klt sim` request/response JSON, which *is* the
  append-only evidence for an MC run — see the script's docstring for why no
  per-sample `.log` files are kept by default) alongside the same
  `testbench/`, `netlist-snapshots/` and `records/` convention the PVT
  experiments use.

## `sim/selftest.sh` — the harness acceptance test

Mirrors the sibling `gf180-ldo` repo's `sim/selftest.sh` (same three-stage
shape, adapted to this harness's single-script `corner-run.py` convention
instead of a `sim/harness/` package):

1. **Unit tests** (`sim/tests/`) — PDK-free, always run.
2. **Environment** (`corner-run.py --check-env`) — skips stage 3 (exit 0) if
   the toolchain/PDK are missing, unless `--require-pdk` is passed.
3. **End-to-end PVT run** against `pdk-smoke` — real xschem + ngspice, not a
   stub. `--quick` runs a 3-point subset instead of the full 45-point matrix;
   `--record` mints a real evidence record instead of using `--no-write`.

CI (`npm run check:ci`) runs `sim/selftest.sh --quick` without `--record`, so
every push exercises the real toolchain without minting new append-only
evidence on every commit.
