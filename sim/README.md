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
symbol `design/ldo_3v3in_1v8out.sym`) against a row of
`spec/target-spec.md`. That table is **RATIFIED** (issue #1 / DR-006; the Iq
row is the one row DR-006 left open, and is set by `DR-009`, which is still
`proposed` and ratifies on its own PR merge), so every measurement bound
these testbenches use cites a ratified spec row verbatim rather than an
invented "final" number, and each experiment's `claim` says so. Records
minted before ratification quote the manifest `claim` as it then read, in
DRAFT wording — `sim/` evidence is append-only, so that wording stays as
history rather than being rewritten in place. Issues #18 and #25 stood the
harness up with explicit `--quick` subsets (3 corners, `--subset-reason`
cited in the record);
issue #19 ran the full 45-point PVT matrix declared in each experiment's
`experiment.json` for all four (`load-transient`, `psrr-dc`,
`dropout-vs-load`, `loop-gain`), plus a Monte Carlo/mismatch experiment
(`mc-output-accuracy/`, see "Monte Carlo / mismatch experiments" below) for the
one spec row that carries a statistical (population) claim rather than a
PVT-corner claim. Those full-matrix records are pinned to the *current*
schematic (post-#35/#36); the earlier `…-879f035` full-matrix set is superseded
— see "Which record set is authoritative" below. **All four testbenches still
record `FAIL`** against their spec bounds — an honest, expected finding given
this schematic's remaining known gaps (see `design/README.md`'s "Known gaps /
follow-on scope"), not a harness defect. Issue #65's three benches follow the
same two-step shape one issue later: their first records are `--quick`
subsets, and issue #74 then ran the full 45-point matrix each of their
manifests declares (39-42/45 PASS across the three; see "The protection /
transient testbenches (issue #65)" below for per-bench results and #93 for
a new finding the full matrix surfaced). Issue #19's own guardrail — that
none of this was a pass/fail verdict against a *ratified* spec, because #1 was
still open — has since been overtaken: issue #1 ratified the table (DR-006)
and closed 2026-09-18. Records minted before that date cite the row in its
then-current DRAFT wording; records minted since cite the same numbers as
ratified. Ratification fixes the targets — it does not turn any of the
`FAIL`s below into passes. Three further testbenches — `line-regulation`,
`load-regulation` and `iq` (issue #64) — landed later against the three rows
the four above don't cover; they still use discrete `.op` points rather than
the corner runner's usual `.dc`/`.tran` sweep style. They shipped
`--quick`-only at first; issue #104 then ran the full 45-point PVT matrix
each manifest declares for all three, mirroring issue #74's extension of the
#65 benches — see "Line regulation, load regulation and Iq (issue #64)"
below for why the
discrete-point convention was chosen and for the full results.

> **Record-generation note (2026-08-25, issue #69).** Issue #69 re-sized the
> thermal shutdown in the shared DUT schematic and re-ran **eight**
> experiments against it, minting a `…-4cb27f8` generation that supersedes
> the `…-81dc232` (the four PVT benches plus `mc-output-accuracy`) and
> `…-703a889` (the three #65 benches) record ids several per-testbench
> sections below still name. Those sections are kept as written because their
> *analysis* is what the superseded records actually say; for the current
> numbers and the old→new mapping, read "Which record set is authoritative,
> part 2 (issue #69)" below. One verdict changed outright: `current-limit`
> went **overall PASS** on its 3-point subset — though issue #74's later
> full-matrix record now supersedes that subset for the report's purposes,
> see part 2's parallel-landings table.
>
> **Four benches were deliberately *not* part of that re-run, because they
> landed on `main` in parallel with #69's branch and did not exist when it was
> cut**: `line-regulation`, `load-regulation` and `iq` (issue #64) and
> `thermal` (issue #66). All four instantiate the same DUT, so #69's re-sizing
> makes their committed netlist snapshots stale, and
> `measurements/characterization.md` now reports all four `STALE` — correctly,
> and by design rather than by oversight. `sim/thermal`'s 15-point record in
> particular characterizes the **pre-#69** trip points, so its 5/15 verdict
> and every trip/reset number in it must be re-read as "before the fix" until
> that bench is re-run. Two further parallel landings interact with #69's
> re-run the same way — #83's `dropout-vs-load` methodology fix and #76/#86's
> `current-limit` leg-3 enable ramp — and are spelled out in
> `design/README.md` → "Parallel landings on `main`, and what they leave
> stale".

> **Record-generation note (2026-09-23, issue #116).** #116 re-sized the shared
> DUT's **pass device** (`M_PASS` `W_total` 2500 µm → 5000 µm, and `M_SENSE`
> with it to hold the current-limit sense ratio) after DR-011 found DR-003's
> sizing derivation was taken at the wrong bias point — see
> `spec/decision-records/DR-011-pass-device-resize.md` (including its
> 2026-09-23 correction note: an early single-`.op`-point screen claimed a
> clean closure that does not reproduce — trust the full-matrix record below,
> not that screen). It re-ran **one** experiment against the re-sized DUT:
> `dropout-vs-load`, the row it was filed against. New record
> `20260923-123440-d71f4b3` supersedes `20260825-081240-4cb27f8`: **0/45 →
> 6/45 PASS** (best case 268 mV, was 365 mV) — real, substantial improvement at
> `−40 °C`/`27 °C` (all five process corners), but 125 °C corners are
> additionally volatile (5 of 15 points get numerically *worse*, consistent
> with the pre-existing mechanism-4 dc-solution-multiplicity finding
> `design/README.md` already documents, apparently made more pervasive by the
> resize) — read 125 °C `dropout-vs-load` numbers with that same caution, not
> as literal measurements.
>
> **Every other bench here instantiates the same DUT and was deliberately not
> re-run**, exactly as the #69 note above describes: their committed netlist
> snapshots are stale by construction and `measurements/characterization.md`
> reports them `STALE` — correctly, and by design rather than by oversight.
> Read every non-`dropout-vs-load` verdict in this directory as
> **"against the 2500 µm pass device"** until its bench is re-run. The
> `Stability` row deserves particular caution: a wider pass device moves the
> output pole and raises `gm_pass`, `C_COMP`/`R_CZ` were **not** re-derived,
> and `sim/loop-gain`'s 7/45 is a pre-#116 number. A follow-up issue owns the
> campaign re-run; #116's PR names it.

> **Record-generation note (2026-09-25, issue #118).** Three more of the benches
> the #116 note above leaves `STALE` have now been re-run against the re-sized
> DUT, and all three are `fresh` again:
> `mc-output-accuracy` (`20260925-110312-8280915`, supersedes
> `20260825-083111-4cb27f8`: **177/200 → 185/200**),
> `load-regulation` (`20260925-111601-7701e7e`, supersedes
> `20260910-032854-6c0436d`: **34/45 → 37/45**) and
> `line-regulation` (`20260925-114251-1f54ca6`, supersedes
> `20260910-030557-6c0436d`: **18/45 → 24/45**). Every row improved; every row
> still reports `FAIL`. `design/ldo_3v3in_1v8out.sch` is **unchanged** by #118.
>
> **More important than the counts is what #118 found underneath them**, and it
> changes how every number in these three records should be read: the failures
> are not accuracy failures at all. They are points where the circuit is not on
> its intended regulating branch — the mechanism-4 / second-stable-equilibrium
> family `#60`/`#71`/`#81` root-caused, which this issue shows binds all three
> rows and is reachable under **mismatch alone at 27 °C/1 mA**, not only at
> `#81`'s 125 °C/50 mA. Two consequences for reading this directory:
>
> - **Line regulation's own `supply_v` axis is a negative control** — the deck
>   `alter`s VIN itself, so that axis cannot reach the measured quantity — and
>   22 of 30 (group × measurement) cells disagree across it by more than 2×.
>   Its corner-level verdicts are branch-selection outcomes, not measurements.
>   (**#196 named what that axis was reaching instead**: `EN`'s high level,
>   which the bench keyed off `'vsup'` while `VIN` moved independently. With
>   `EN` at the instantaneous VIN the axis is inert by construction, and the
>   45-corner re-run under that convention — record `20260926-200304-35b7392`
>   — brings all 30 of those cells back **identical to every stored digit**:
>   the axis disagreed with itself because it was a stimulus axis after all,
>   through `EN`. See "#196" below.)
> - **On the regulating branch all three rows are inside their bounds**, with
>   exactly one exception in the whole set: `load-regulation`'s
>   `fs_125c_3.63v` at 19.93 mV against 18 mV. That single corner is the only
>   genuine DC-accuracy gap the three rows contain.
>
> The full decomposition, with the per-record numbers behind each claim, is in
> `design/README.md` → "#118: the three DC-accuracy rows do share one
> mechanism…". The design campaign it leaves open is **#164**; the `klt sim`
> request-shape gap that keeps both regulation matrices off the batch fleet is
> 2AMLogic/klayout-tools#2482.

---

## Contents

This file is the harness reference and index. The per-experiment and
per-topic sections below were moved verbatim to `sim/docs/`:

- [Initial-condition contract (issue #171)](docs/initial-condition-contract.md)
- [The LDO's own testbenches (issues #18 and #25)](docs/ldo-testbenches.md)
- [Line regulation, load regulation and Iq (issue #64)](docs/line-load-regulation-iq.md)
- [Monte Carlo / mismatch experiments](docs/monte-carlo-mismatch.md)
- [`sim/selftest.sh` — the harness acceptance test](docs/selftest.md)
- [`check:ci` vs. netlisting the LDO core (issue #38)](docs/check-ci-vs-netlisting.md)
- [Standalone regenerative thermal comparator (#229)](docs/thermal-regen-comparator.md)
- [Integrated regenerative comparator (#230)](docs/integrated-regen-comparator.md)
- [Experiment and solver freshness (#237)](docs/freshness.md)

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
                               # -- and to pick the same linear solver the
                               # records were produced with (see "Reproducing
                               # a corner by hand" below)
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

> **The root the runner resolves is also the root `klt` reads** — which took a
> fix to be true (issue #211). A `klt sim` request names `models.lib` by a
> *relative* path, so `klt` resolves the PDK root itself if nothing says
> otherwise, and `mc-run.py` used to pass it no `PDK_ROOT`. On a host carrying
> two sky130A installs (e.g. a `volare` root and a `ciel` one, an ordinary state
> after following the tooling's own migration) that meant `mc-run.py` could
> verify one root against the pin and record `matches_pin: true` while `klt sim`
> read the *other* — a different open_pdks build whose
> `libs.tech/combined/continuous/models_fet.spice`, the FET cards a mismatch
> campaign draws from, is not byte-identical. A record naming a commit the
> simulation never read is a false provenance claim, and it is silent: the
> numbers look fine. `mc-run.py` now passes `PDK_ROOT` explicitly **and**
> asserts after the run that `klt`'s own `provenance.pdk.version` names the
> pinned commit (`--allow-pdk-mismatch` downgrades that to a warning, the same
> escape hatch the pre-run check offers), so this fails loudly instead. Any
> local `mc-output-accuracy*` record minted before #211 should be read with
> that in mind — check its response's `provenance.pdk` rather than only the
> record's `pdk` block. Filed generically upstream as
> [klayout-tools#2564](https://github.com/2AMLogic/klayout-tools/issues/2564).

**What the runner injects** (so one testbench serves the whole matrix): the
`.lib <models> <corner>` include, `.temp`, `.param vsup=<supply>`, `.option`s
from the manifest, and the `.control` block that runs the analyses, evaluates
each measurement expression into a `meas_<name>` vector and prints it. The
testbench schematic therefore contains no corner, no temperature, no numeric
supply and no analysis block.

**Per-corner artifacts**: each corner's `.log` embeds **both** inputs ngspice
was given (each prefixed with `|`) — the deck, and the `.spiceinit` that was in
the run directory, with its `sha256` — plus raw stdout/stderr, so a record is
auditable without regenerating anything. Scratch decks and xschem output live
in the gitignored `sim/build/`; only the netlist snapshot, the per-corner logs
and the record are committed.

### Reproducing a corner by hand (issue #190)

**The deck is only half the input. `.spiceinit` is the other half, and it is
not optional.** ngspice reads `.spiceinit` from its working directory at
startup; `sim/spiceinit` sets `option klu` (the KLU direct linear solver)
alongside the `ngbehavior=hsa` settings needed to read the PDK libraries. A
different linear solver can reach a different judgement about matrix
singularity on the same circuit — so a deck re-run **without** `.spiceinit` can
produce bit-identical measurements and yet emit none of the solver diagnostics
that the `#171` gate turned into the corner's recorded `FAIL` (measured; see
the `#179` section below). Reproducing a corner without it is therefore not
reproducing the corner.

The general recipe, for any corner of any record:

```bash
mkdir -p /tmp/repro && cd /tmp/repro
# 1. extract the `|`-prefixed deck from the corner log into <corner>.spice
#    (the log's own header block spells this out, including the ngspice line)
# 2. put the ngspice init settings in place -- REQUIRED, not a convenience:
cp "$REPO/sim/spiceinit" ./.spiceinit    # or the `|`-prefixed .spiceinit
                                         # block embedded in the same log
source "$REPO/sim/bin/pdk-env.sh"        # PDK_ROOT etc., same as the runner
ngspice -b <corner>.spice < /dev/null
```

Prefer the `.spiceinit` **embedded in that corner's log** over today's
`sim/spiceinit` when reproducing an older record: the log holds the settings
that record actually ran under, and the record's own `ngspice init settings`
field carries their `sha256` so you can tell whether the tree has moved since.
Logs written before `#190` embed only the deck — for those, `sim/spiceinit`
at the record's `Repo state` sha is the right source.

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
    yield-run.py                     # yield/capability analysis of a committed MC response, via `klt yield`
    pdk-env.sh                       # `source` for interactive use
  tests/
    test_corner_run.py               # PDK-free unit tests for corner-run.py's helpers
    test_mc_run.py                   # PDK-free unit tests for mc-run.py's helpers
    test_yield_run.py                # PDK-free unit tests for yield-run.py's helpers
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
      <record-id>.yield-limits.json  # `klt yield` runs only (issue #203)
    klt-responses/                   # Monte Carlo experiments only
      <record-id>.json               # `klt sim`'s full per-sample response (the raw evidence)
      <record-id>.yield.json         # `klt yield` runs only — a *derived* report (issue #203)
    records/
      <record-id>.md                 # append-only summary record (human)
      <record-id>.json               # same record, machine-readable
```

- **`<experiment-slug>`** — kebab-case name for the claim under test. One
  directory per distinct claim, not per run.
- **`<record-id>`** — `<YYYYMMDD>-<HHMMSS>-<short-git-sha>` in UTC. The same id
  ties together the netlist snapshot, the per-corner logs and both record
  files for one run. Re-runs mint a new id. A **derived** record (a `klt yield`
  analysis of an already-committed sample set — see "`klt yield` records"
  below) mints its *own* id and names the source campaign's id in its
  `Source campaign` block, rather than reusing it.
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
| Claim | which spec parameter/line this substantiates (`spec/target-spec.md#<row>`, ratified by issue #1 / DR-006); `pdk-smoke` is harness-only, not a spec claim |
| Netlist provenance | `schematic` (`design/…`, `sim/…/testbench/…`) or `extracted` (post-layout) — required so post-layout re-runs are distinguishable |
| PDK | variant + open_pdks commit actually used, whether it matches `sim/pdk.json`, and the model library path |
| Tools | ngspice / xschem / OS / python versions used |
| ngspice init settings | `sim/spiceinit` and its `sha256` — the second input ngspice was given (copied into the run directory as `.spiceinit`); it selects the linear solver, so reproducing a corner by hand requires it (issue #190). Absent from records minted before `#190`. |
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

It deliberately uses the 1.8 V **core** device family (`nfet_01v8`), not the
pass-device flavor the "sky130 porting question" in `spec/target-spec.md`
settled (framing A — `pfet_g5v0d10v5` — ratified per DR-001 / issue #1, over
framing B's 1.8 V core devices) — this testbench is harness plumbing, stood up
ahead of and independent of that ratification decision, and its device choice
neither implements nor revisits it.

Keep it green: it is the first thing to run when a testbench misbehaves, to
tell "my circuit is wrong" apart from "my harness is broken".

