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
`psrr-dc`, `dropout-vs-load` (issue #18), `loop-gain` (issue #25) and the three
protection/transient benches `current-limit`, `startup`, `enable-shutdown`
(issue #65) — each
exercise the LDO core-regulation-loop schematic from issue #14
(`design/ldo_3v3in_1v8out.sch`, instantiated via its companion subcircuit
symbol `design/ldo_3v3in_1v8out.sym`) against a DRAFT row of
`spec/target-spec.md`. `spec/target-spec.md` is not yet ratified (issue #1
still open), so every measurement bound these testbenches use cites a DRAFT
spec row directly rather than an invented "final" number, and each
experiment's `claim` says so. Issues #18 and #25 stood the harness up with
explicit `--quick` subsets (3 corners, `--subset-reason` cited in the record);
issue #19 ran the full 45-point PVT matrix declared in each experiment's
`experiment.json` for all four (`load-transient`, `psrr-dc`,
`dropout-vs-load`, `loop-gain`), plus a Monte Carlo/mismatch experiment
(`mc-output-accuracy/`, see "Monte Carlo / mismatch experiments" below) for the
one DRAFT row that carries a statistical (population) claim rather than a
PVT-corner claim. Those full-matrix records are pinned to the *current*
schematic (post-#35/#36); the earlier `…-879f035` full-matrix set is superseded
— see "Which record set is authoritative" below. **All four testbenches still
record `FAIL`** against their DRAFT bounds — an honest, expected finding given
this schematic's remaining known gaps (see `design/README.md`'s "Known gaps /
follow-on scope"), not a harness defect. Issue #65's three benches follow the
same two-step shape one issue later: their first records are `--quick`
subsets, and the full 45-point matrix each of their manifests declares is
tracked in issue #74. Per issue #19's own guardrail, none of
this is a final pass/fail verdict against a *ratified* spec — issue #1 (spec
ratification) is still open, so every record here cites the current DRAFT row
only. Three further testbenches — `line-regulation`, `load-regulation` and
`iq` (issue #64) — landed later against the three DRAFT rows the four above
don't cover; they still use discrete `.op` points rather than the corner
runner's usual `.dc`/`.tran` sweep style, and are `--quick`-only so far — see
"Line regulation, load regulation and Iq (issue #64)" below for why and for
their results.

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
  **Full 45-point PVT record** (`20260818-032755-81dc232`, issue #19,
  supersedes the pre-#36 `20260818-005853-879f035`): **23/45 PASS** — all five
  process corners pass at `-40 °C`/2.97 V, `27 °C`/3.30 V and `27 °C`/3.63 V,
  4/5 at `-40 °C`/3.30 V and 3/5 at `-40 °C`/3.63 V, and **0/15 at 125 °C**.
  The 22 failures split into 16 that miss by a plausible margin (0.150–0.311 V
  against the 0.15 V bound, worst `ff_27c_2.97v`) and the six degenerate
  `ff`/`sf` 125 °C corners described below — overall `FAIL`.
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
  **Full 45-point PVT record** (`20260818-032803-81dc232`, issue #19,
  supersedes the pre-#36 `20260818-014410-879f035`): **6/45 PASS** — the
  100 kHz bound (>20 dB) is met at **every** corner (31.5–105.3 dB), and the
  1 kHz bound (>50 dB) is met at only six (20.3 dB worst, `fs_125c_2.97v`).
  All six 1 kHz "passes" (76.6–76.8 dB) are `ff`/`sf` 125 °C corners — the same six
  that are degenerate in the other three testbenches, so they are not evidence
  of real PSRR headroom. No corner timed out (the two 300 s timeouts in the
  superseded pre-#36 record are gone) — overall `FAIL`.
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
  characterization. **Full 45-point PVT record** (`20260818-032811-81dc232`,
  issue #19, supersedes the pre-#36 `20260818-022803-879f035`): **0/45 PASS** —
  the best corner is 0.365 V (`ss`/−40 °C, all three supplies) against the
  300 mV bound, 33 of 45 corners land under 1 V, `ff`/−40 °C is ~1.55 V, and
  the three `sf_125c_*` corners return a nonsensical 32.6 V (see below) —
  overall `FAIL`. The `vout_at_max_vin_v` sanity measurement lands on a
  non-regulating branch at 6 of 45 corners, the same `ff`/`sf` 125 °C
  cluster.

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
  settle. **Full 45-point PVT record** (`20260818-032819-81dc232`, issue #19,
  first full matrix for this experiment, supersedes nothing): **3/45 PASS** —
  and the full matrix confirms the quick record's shape rather than changing
  it. The dominant failure is still the **0 mA** window point
  (`pm_c033_0ma_deg` fails at 41 of 45 corners, `pm_c47_0ma_deg` at 20); the
  loaded points are healthy nearly everywhere (`pm_c033_50ma_deg` 45.9–78.9°
  with 17.0–21.7 dB of gain margin, failing only at the six degenerate
  corners) — overall `FAIL`.

None of the four fully meets its DRAFT bound yet. This is an honest,
expected finding, not a harness bug — and the reason has moved. The #18
records were dominated by two gaps issue #25/#36 has now closed: an unsized
placeholder compensation and a five-transistor error amplifier whose output
could not swing to `VIN`. With those closed, `load-transient` passes 23 of 45
corners, `loop-gain`'s loaded points are comfortable everywhere the operating
point is valid, and `psrr-dc` meets its 100 kHz bound at every corner — while
`dropout-vs-load` still misses at every corner and both `psrr-dc`'s 1 kHz bound
and `loop-gain`'s 0 mA window point still fail widely. What remains is
documented in `design/README.md`'s "Known gaps / follow-on scope" and in the
DR-002 append: the pass device's own `gm_pass/(2π·C_out)` pole at no load and
an Iq budget that does not exist yet.

### The protection / transient testbenches (issue #65)

Three more benches cover the DRAFT rows whose *circuitry* landed with issue
#22 but which had no testbench of their own, so
`measurements/characterization.md` reported them `N/A` — a coverage gap by
that report's own Limitations section, neither substantiated nor refuted.
They share the four benches' stimulus and output-network conventions above;
what is new is that two of them drive the DUT through an **event** (a held
short, an enable edge) rather than a steady condition, so each states in its
own `experiment.json` `claim` how the event is applied and which clause of
the DRAFT row it grades. First records are `--quick` subsets, same as #18/#25;
the full 45-point matrix each manifest declares is issue #74.

Two of these rows carry clauses with **no number in them at all** ("window
TBD over PVT", "survives", "monotonic"). Where a clause has a number, it is
bounded; where it does not, the quantity is measured and reported **without**
a bound rather than graded against a limit nobody has ratified — inventing
one would be exactly the fabricated-settled-number the root `CLAUDE.md`
forbids. Each such measurement's `note` says so explicitly, and says what
would have to change once issue #1 rules.

- **`current-limit/`** — forces `VOUT` through a `VFORCE`/`RFORCE` branch
  (`RFORCE` starts at 1e12 and the deck `alter`s it to 1 mΩ) in three legs:
  an `op` at a 36 Ω (~50 mA) load with the branch open (leg 1), a DC
  characteristic from a dead short up to the 1.75 V knee (leg 2), and a
  `Vout = 0` short applied as a transient event and **held for 2 ms** (leg 3)
  — a sustained fault of defined duration, not one sampled instant, since
  "survives" is a claim about holding the fault. Legs 1–2 are `op`/`dc`
  analyses; leg 3 is a `tran`, and its `EN` is a dual `dc 'vsup'` + rising
  `pwl` (t = 100 µs) so the fault (t = 1.0 ms, after `startup/`'s measured
  soft-start ramp) lands on a block that reached regulation through a real
  enable edge rather than an already-enabled t = 0 DC solve — see the
  harness-lesson paragraph below for why, and its scope note for which legs
  of this bench that fix does and does not reach. Bounded: `vout_50ma_v`
  inside the DRAFT Output row's ±2% window (the operative form of "never
  engages for I_load ≤ 50 mA") and both limit levels above 50 mA. Reported
  unbounded: the limit window itself, its brickwall-vs-foldback shape, and
  the sustained short current. Current record (`20260825-070327-d0bb614`,
  3-point subset, supersedes `20260825-045313-703a889` — issue #76):
  **2/3 PASS** — `tt_27c_3.30v` regulates at 1.798 V with a 162 mA
  short-circuit level against a 135 mA knee, `ss_-40c_2.97v` 1.798 V / 180 mA
  / 149 mA, and both hold the short for its full 2 ms with <0.1% supply-
  current ripple. The negative droop (−20%/−21%: more current into a dead
  short than at the knee) is the brickwall signature, not a foldback one.
  `ff_125c_3.63v` **FAILs** legs 1–2: the `op`/`dc` output collapses to ~2 µV
  and ~0 mA of limit current — the same thermal-clamp nuisance trip
  `design/README.md` root-causes as mechanism 1 (issue #69), read here
  through a resistive load instead of an ideal current sink, so the output
  sits at 0 V rather than at a non-physical negative voltage. Leg 3 at that
  same corner, by contrast, is now conclusive rather than inconclusive: with
  the enable-ramp fix, the block reaches a genuine current-limiting state
  before the fault and sustains 148 mA through the held short — in the same
  100–200 mA range as the other two corners' leg-3 results, not the ~0 mA
  the pre-#76 record showed. Overall `FAIL` is unchanged from the prior
  record, driven entirely by legs 1–2's design defect (none of leg 3's
  measurements carry a bound to begin with), but leg 3's `ff_125c_3.63v`
  result changed from inconclusive (a stuck, non-regulating branch reporting
  ~0 everywhere) to a real measurement of the clamp holding the short —
  which is what issue #76 fixed.
- **`startup/`** — four independent **cold** enables in one deck (`C_out`
  0.33/4.7 µF × load 0/50 mA, the corners of the two ranges the DRAFT row
  quantifies over), each starting from `EN = 0` with `C_OUT` discharged and
  the soft-start ramp held down, with `EN` rising at t = 100 µs. Bounded:
  peak `VOUT` against the row's own overshoot ≤ +2%, and the *minimum* over
  the settled window (from 3 ms after the edge) against its "inside ±2%
  within a few ms" — a minimum, not a sample, so a ramp that reaches the
  window and sags back out of it fails. First record
  (`20260825-044139-703a889`, 3-point subset): **3/3 PASS** — worst peak
  1.826 V against the 1.836 V ceiling (the 4.7 µF/0 mA leg), worst settled
  floor 1.798 V, and ramp times 0.26–0.45 ms into all four load/C_out points,
  consistent with the ~290 µs soft-start screening in `design/README.md`.
  Note the honest limit stated in the manifest's own `claim`: a sample-by-
  sample monotonicity predicate is **not** computed — the peak/floor bounds
  capture the numeric consequence of a non-monotonic ramp (an excursion
  outside ±2%), and the ramp time is reported as the "controlled ramp"
  witness.
- **`enable-shutdown/`** — one transient leg running a full enable →
  shutdown **cycle** (`EN` low at t = 0, rising at 100 µs, falling again at
  2 ms) plus three static `op` legs with `EN` held at 0. Bounded: shutdown Iq
  against the row's < 3 µA both statically and after the falling edge,
  `VIN`→`VOUT` leakage against its ≤ 1 µA with `VOUT` forced to 0 V, and the
  "no active discharge" clause as the residual output 2 ms after the disable
  edge (an active pull-down would empty `C_OUT` in microseconds; the
  divider's own R×C is seconds). First record
  (`20260825-044140-703a889`, 3-point subset): **3/3 PASS** — static
  shutdown Iq 0.13 nA–49 nA, post-edge worst-case 0.6 nA–21 nA,
  `VIN`→`VOUT` leakage 0.07 nA–52 nA, and `VOUT` still at 1.808–1.819 V two
  milliseconds after disable. All are two to four orders of magnitude inside
  the DRAFT bounds, which is as much a statement about that row's own
  "pending sky130 device data" note as about the design — the models'
  subthreshold/junction leakage is what sets these numbers.

The transient leg's *rising* edge in `enable-shutdown` is load-bearing, and
worth recording as a harness lesson: an earlier draft started that transient
already enabled and relied on ngspice's t = 0 DC solve landing on the
regulating branch. At `ff_125c_3.63v` it does not (mechanism 1 again), so the
draft failed that corner for a reason having nothing to do with the enable/
shutdown path. Ramping `EN` up from a disabled start lets the block reach
regulation the same way `startup/` shows it does, and the corner then passes —
the failure really was the solve, not the shutdown path. Issue #76 found the
same gap in `current-limit/`'s leg 3 (its `tran`) after this fix had already
landed in `enable-shutdown/` and `startup/`, and applied the identical fix
there. **Scope note, since `current-limit/` is not uniformly a transient
bench**: the enable-edge lesson applies only to leg 3 — the `tran` that
applies and holds the `Vout = 0` short. Legs 1 and 2 are `op`/`dc` analyses;
an enable ramp cannot help a DC solve reach a different branch than it
otherwise would (there is no "before" state for a ramp to start from), so
their `ff_125c_3.63v` collapse is the design defect (#69) the record honestly
reports, not a bench artifact this fix was ever going to touch.

### Which record set is authoritative (issue #19)

There are now **two generations** of full 45-point records on disk, and only
the newer one characterizes the design as it stands:

| Generation | Record ids | Pinned schematic | Status |
|---|---|---|---|
| Pre-#36 | `…-879f035` (`load-transient`, `psrr-dc`, `dropout-vs-load`) | `879f035` — before #35 (thermal shutdown) and #36 (rail-to-rail EA output stage + sized compensation) | **Superseded.** Kept per the append-only rule; do not cite. |
| Current | `…-81dc232` (all four testbenches) | `81dc232` — current `main` plus the `M_ENP4`/`M_ENP5` fix below | **Authoritative** for issue #19's acceptance criteria. |

The first generation was run before #35/#36 landed and blamed its failures on
gaps those two commits then closed, so re-running was a correctness matter, not
a refresh: the newer set is what issue #19's "full PVT + Monte Carlo
verification" deliverable rests on. Both sets stay on disk — the superseded
records point forward via the new records' `Supersedes` field, never by
deletion.

The re-run also turned up a defect in `main` itself: #35 and #36 each added an
EN-gated clamp named `M_ENP4` (on `TS_CMP` and `PB` respectively), so the
merged schematic netlisted two devices with the same instance name and ngspice
refused every deck outright (`device already exists, bail out` → "no
simulations run!"). No LDO simulation could run on `main` at `d0b244d` at all.
The minimal rename (#36's `PB` clamp → `M_ENP5`) is carried by this issue's
branch; issue #38 tracks the reason nothing caught it (nothing in
`npm run check:ci` netlists the LDO core).

### The six degenerate `ff`/`sf` 125 °C corners

`ff_125c_*` and `sf_125c_*` (six of the 45 points) return values that are not
physically meaningful — 8.4–22.3 V of "undershoot" on a 1.8 V output, 32.6 V of
"dropout" from a ≤3.63 V supply, `vout_at_max_vin_v` of −19 V / −29 V, `n/a`
loop-gain measurements, and the only six 1 kHz PSRR "passes" in the matrix.
That is one signature seen four ways: at those corners the solve does not land
on a valid regulating operating point, so the number the measurement expression
extracts describes the solver's excursion, not the circuit's behaviour. They
are recorded as `FAIL`/`n/a` rather than dropped (per this directory's own
rule), and they are excluded from the "worst plausible corner" figures quoted
above; diagnosing them is design/harness follow-on work, not something this
record resolves.

## Line regulation, load regulation and Iq (issue #64)

Three more testbenches against the same DUT (`design/ldo_3v3in_1v8out.sch`),
covering three DRAFT rows `measurements/characterization.md` reported N/A
until this issue: **Line regulation** (<5 mV/V over 2.97–3.63 V, at 1 mA and
50 mA), **Load regulation (0–50 mA)** (<1%/18 mV) and **Iq (excl. load
current)** (<30 µA at no load and full load). Same VIN/EN/VREF stimulus
convention and output network (1 µF `C_OUT`/10 mΩ `R_ESR`) as the four
testbenches above.

**All three use discrete `.op` points at the DRAFT row's own named test
conditions, not a continuous `.dc` sweep** — a deliberate choice, not the
original plan. A continuous `dc vvin 2.97 3.63 ...` sweep (for line
regulation) and a continuous `dc iload 0 50m ...` sweep (for load regulation)
were both tried first and both hit this schematic's already-documented
DC-solution-multiplicity behavior (the "six degenerate corners" section
above, and design/README.md's dated 2026-08-25 root-cause section, issue #60
mechanism 4, tracked by #71): the VIN sweep repeatedly hit
gmin-stepping/singular-matrix non-convergence and did not complete in
minutes of wall-clock time per corner, and the `I_LOAD` sweep measured a
1.46 V peak-to-peak `vout` excursion at `tt`/27 °C — a solver-continuation
artifact, not a real 81%-of-target load regulation number (design/README.md's
own screening data puts the same two endpoints ~4 mV apart). Four (line
regulation: VIN × I_LOAD) or two (load regulation: I_LOAD only) independent
`.op` solves at the DRAFT row's own endpoints — `alter`-ing VIN and/or the
load current source between them, mirroring `loop-gain`'s and `iq`'s
multi-point convention — complete in well under a second each and reproduce
`design/README.md`'s own screening numbers for the same points (its "DC
operating grid" and "Quiescent and shutdown current" sections both already
use discrete points, not a sweep, for exactly this reason).

- **`line-regulation/`** — VIN ∈ {2.97 V, 3.63 V} × `I_LOAD` ∈ {1 mA, 50 mA},
  four `.op` solves; `line_reg_<n>ma_mv_per_v` = `abs(1000*(vout_hi-vout_lo)/
  0.66)`. First record (`--quick`, 3-corner subset, `20260825-040532-6fac47d`):
  **PASS** at `tt_27c_3.30v` (0.295/0.378 mV/V) and `ss_-40c_2.97v`
  (0.217/0.369 mV/V), **FAIL** at `ff_125c_3.63v` (1005.8/1010.2 mV/V, three
  orders of magnitude over the 5 mV/V bound) — overall `FAIL`. The
  `ff_125c_3.63v` failure is the same degenerate-corner signature described
  above (thermal-shutdown false-trip, #69), not a new finding.
- **`load-regulation/`** — `I_LOAD` ∈ {0 mA, 50 mA} at each corner's own VIN
  (`'vsup'`), two `.op` solves; `load_reg_v` = `abs(vout@50mA - vout@0mA)`.
  First record (`--quick`, `20260825-040748-6fac47d`): **PASS** at
  `tt_27c_3.30v` (4.2 mV / 0.23%) and `ss_-40c_2.97v` (3.3 mV / 0.18%),
  **FAIL** at `ff_125c_3.63v` (19.3 V) — overall `FAIL`, same degenerate
  corner.
- **`iq/`** — `I_LOAD` ∈ {0 mA (no load), 50 mA (full load)} at each corner's
  own VIN, two `.op` solves; `iq_<point>_ua` = `-i(vvin)` minus the known
  load-current constant, per `design/README.md`'s own "Iq = total VIN
  current minus load current" convention. First record (`--quick`,
  `20260825-040934-6fac47d`): **PASS at all three corners**
  (13.3/25.5 µA at `tt_27c_3.30v`, 11.4/22.3 µA at `ss_-40c_2.97v`,
  14.7/8.8 µA at `ff_125c_3.63v`) — overall `PASS`. The `ff_125c_3.63v`
  point is the same degenerate corner as above (confirmed directly: `TS_CMP`
  = 0.39 V, tripped; `vout` collapses to 0.14 V at no load and −19.2 V at
  full load), but unlike line/load regulation the raw `-i(vvin)` figure there
  still happens to land inside the 30 µA budget rather than reading as an
  obviously non-physical number — so this testbench also records
  `vout_no_load_v`/`vout_full_load_v` (unbounded) alongside the Iq figures,
  specifically so a reader can see that corner's operating point is not
  really regulating before trusting its in-budget Iq "PASS", the same
  caution the PSRR "passes" above already need.

**Quick-subset only, by design, matching issue #18's own original
precedent** for newly-shipped testbenches (`load-transient`/`psrr-dc`/
`dropout-vs-load` also shipped `--quick`-only before #19's later full
45-point pass). Extending these three to the full PVT matrix is follow-on
work, not part of this issue's scope.

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
  1.764–1.836 V window. **Current record** (`20260818-032827-81dc232`,
  supersedes the pre-#36 `20260817-235656-e500d71`): N=200 samples, seed
  `20260817`, k_sigma=3 — **181/200 individual-sample PASS**, and the mean±3σ
  sigma-window check **FAILS** (mean 1.717 V, stddev 2.154 V, window
  [−4.745 V, 8.180 V] vs. the 1.764–1.836 V bound) — overall `FAIL`. The
  median sample is well inside the window (p50 = 1.802 V, p5 = 1.787 V), so
  the distribution's *centre* meets the DRAFT row and the failure is entirely
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

`sim/selftest.sh --quick --require-pdk` (without `--record`) runs in the
PDK-gated `pdk-smoke` CI job (nightly / `workflow_dispatch` / opt-in
`run-pdk-smoke` PR label) so it exercises the real toolchain without minting
new append-only evidence on every run — but it does **not** run on every
push. `npm run check:ci` (the headless, no-PDK job that *does* run on every
push/PR) never invokes `sim/selftest.sh` at all, and `sim/selftest.sh`'s own
`pdk-smoke` end-to-end stage netlists a standalone diode-tied device
testbench, not `design/ldo_3v3in_1v8out.sch` — so neither one is a liveness
check for the LDO core's own netlist. See "check:ci vs. netlisting the LDO
core" below for the check that is.

## `check:ci` vs. netlisting the LDO core (issue #38)

`#35` and `#36` were developed in parallel and each added an EN-gated PMOS
clamp instance named `M_ENP4` on different nets. Merged, `design/
ldo_3v3in_1v8out.sch` netlisted two devices with the same instance name, and
ngspice refused every deck outright (`device already exists, bail out` — see
the "Which record set is authoritative" note above). Nothing in `npm run
check:ci` caught it, because nothing headless ever netlisted the LDO core's
own schematic.

`npm run check:ci` now runs
`.loom/scripts/check-xschem-duplicate-instance-names.sh` — a static regex
lint (no PDK/xschem/ngspice) over tracked `design/*.sch` files that flags any
two component instances sharing the same `name=` value, following
`.loom/scripts/check-xschem-embedded-quotes.sh`'s existing pattern (see
`.github/workflows/ci.yml`'s self-check-inventory header comment). This
closes the fast, per-push feedback gap completely for the class of hazard
that bit #35/#36 (a duplicate instance name), with a clear message naming
the file and the duplicated name instead of ngspice's confusing
netlist-line-number error.

**Whether `corner-run.py --dry-run` also catches this (a second,
PDK-gated liveness layer) was verified empirically while implementing this
check: it does not.** `--dry-run` only netlists via xschem and prints the
deck — xschem's netlister emits the duplicate-`name=` deck silently (exit 0,
no stderr) without rejecting it; the "device already exists, bail out" error
is raised only once ngspice elaborates the deck. A real corner run (e.g.
`corner-run.py sim/load-transient --quick --no-write`) does reproduce the
exact original failure (every corner returns `FAIL` with `n/a`
measurements, and the underlying ngspice run hits the same "device already
exists, bail out" error the incident report shows). Wiring one of the
LDO-instantiating testbenches (`load-transient`, `psrr-dc`,
`dropout-vs-load`) into the PDK-gated `pdk-smoke` job as a second liveness
layer therefore remains a legitimate follow-up (defense-in-depth, catching
the same class of hazard again at PDK-run time), but it would need a real
`--no-write` run, not `--dry-run` — and it is not needed to close this
issue's gap, since the headless lint above already catches every push,
including on machines with no PDK.
