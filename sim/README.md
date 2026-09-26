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
| Claim | which spec parameter/line this substantiates (`spec/target-spec.md#<row>`, ratified by issue #1 / DR-006); `pdk-smoke` is harness-only, not a spec claim |
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

## Initial-condition contract (issue #171)

**A bench's `.op`/`.tran`/`.ac`/`.dc` analysis chain must start from a
physically realizable state of the circuit — never from ngspice's own
unconstrained `.op` solve.** Three shapes satisfy this:

- **`uic` + an EN edge** — every node starts at its natural cold-start value
  (0 V unless a source forces otherwise), `EN` starts low (block disabled),
  and the deck's first analysis is a `tran … uic` (or a `.dc`/`.op` chained
  off one) whose stimulus brings `EN` high at some later time so the block
  powers up through its own soft-start ramp, exactly like a real power-on
  event. `sim/mc-output-accuracy` (post-#164) uses this convention; see its
  `experiment.json`'s `mc_analysis.note` for the worked example. A bench
  whose analysis never leaves the disabled (`EN = 0`) state before the
  measurement window it cares about — e.g. `sim/startup`'s cold-enable legs,
  which measure the ramp *through* the EN edge itself rather than a settled
  ON-state — can rely on an ordinary (non-`uic`) `.op`/`.tran` seed instead,
  because the disabled state has no closed feedback loop to disambiguate; the
  hazard this contract exists for is specific to seeding a solve that must
  land on the loop's **regulating** operating point.
- **An `.ic`-seeded `.op`** — every node the loop needs to disambiguate is
  given an explicit `.ic` value close to the block's expected operating
  point (a `.ic v(node)=<value> …` card in the netlist body), and the `.op`
  solve is released from that seed rather than from ngspice's own guess.
  `sim/ic-screen-125c-b` (`tran 10u 3m` — no `uic` — with an `.ic` card
  constraining every node the loop needs) is a worked example of this shape
  (see design/README.md "#164" for the multi-variant screen that established
  it as equivalent to `uic` + EN edge for this circuit).
- **A `.nodeset`-seeded `.ac`/`.op`** — the same constrain-then-release seed
  as the shape above, written with the card an **`ac`** analysis's own
  operating-point solve actually honours. `sim/loop-gain` and `sim/psrr-dc`
  (post-#179) are the worked examples; both carry a
  `.nodeset v(VOUT)=1.8 v(xldo.FB)=1.2 v(xldo.N_FBB)=0.6` card in the
  testbench schematic (`devices/code_shown.sym`, exactly as
  `sim/ic-screen-125c-b` carries its `.ic`), and both record `v(vout)` from
  an `op` taken at every bias point as evidence the seeded solve landed on
  the regulating branch.

  **Seed only the branch-defining nodes.** A `.nodeset` card is a *single
  static card* applied to every operating-point solve in the deck, while
  both of these benches walk several load points via `alter`. So the card
  may only constrain nodes whose value says *which branch* the solve is on
  — here `VOUT` and the two feedback-divider taps `FB`/`N_FBB` — and must
  leave every node whose value is set by the operating **current**
  (`EA_OUT`, `EA_CZ`, `EA_TAIL`, `EA_D1/D2`, `BIASP`, `NB`, `SS`) to the
  solver. Seeding those too is actively harmful, and #179 measured how
  (see "#179" below): `sim/ic-screen-125c-b`'s eleven-node seed, whose
  values are its 125 °C/50 mA operating point, drags the *1 mA* point of
  `ss/−40 °C/3.63 V` onto a non-regulating branch (`VOUT = 3.633 V = VIN`)
  in both benches. This is the `.ac` counterpart of the `.ic` rule, not a
  contradiction of it: `sim/ic-screen-125c-b` seeds eleven nodes correctly
  because it is a *single-operating-point* transient screen.

  **Why `.nodeset` rather than `.ic` for an `ac` deck** (measured during
  #179, ngspice-46, not inferred from the manual):

  1. **`.ic` is inert in an ac-only deck.** ngspice applies `.ic` to the
     *transient* operating point only. Adding an eleven-node `.ic` card to
     `sim/psrr-dc`'s deck changed neither a measurement nor a solver
     diagnostic; adding it to a deck with a leading `op` instead *introduced*
     two `Warning: singular matrix: check node xldo.xr_fb_b.t2` lines — i.e.
     the `.ic` shape is the wrong tool here, and forcing it would have
     tripped the FAIL gate rather than satisfied the contract.
  2. **Each `ac` re-solves its operating point from scratch, so a seed
     carried by a preceding analysis does not survive.** On `sim/loop-gain`'s
     seven-point deck the baseline logs one Newton continuation per `ac`
     (seven); prepending a bare `op` produces *eight*, not a reuse of the
     first. A per-point `.ic`/`op` seed is therefore impossible to chain,
     which is the specific question #179 raised about the `alter`-reached
     points — and the reason the seed has to be a card the *analysis itself*
     honours rather than a preceding analysis.
  3. **`.nodeset` is applied to every operating-point solve the deck
     performs**, including the one inside each `ac`, so a single card covers
     all seven `alter`-reached points. That it is genuinely applied (not
     silently dropped on hierarchical node names) is visible in the result:
     on the current DUT it takes `sim/loop-gain` from three corners whose
     `ac` linearized about `VOUT = VIN` down to none, and `sim/psrr-dc` from
     one to none, while *releasing* to bit-identical measurements at every
     corner that was already on the regulating branch — the seed is a basin
     hint, not a forced result. Per-variant counts: "#179" below.

**An EN edge alone does not satisfy the first shape — a non-`uic` `tran`
still solves an operating point first, and it reads a source's `dc` keyword
value there (issue #177).** This is the one mechanical detail the contract's
first shape depends on, and it was stated wrongly here and in #174's audit
until #177 measured it. Before the first timestep of a `tran` **without**
`uic`, ngspice computes a transient operating point; for an independent
source written with *both* a `dc` value and a transient function
(`dc <X> pwl(…)`, `dc <X> PULSE(…)`), that solve uses the **`dc` value**, not
the transient function's t = 0 value. ngspice announces it on stderr, once
per such source, on every run:

```
Note: <source>: dc value used for op instead of transient time=0 value.
```

The transient *waveform* afterwards does start from the transient function's
t = 0 value — so a deck can look correctly cold-started in its own waveforms
while its operating-point solve was the fully-enabled, loop-closed,
from-nowhere Newton start this contract exists to forbid. A minimal repro
settles both halves: `V1 n1 0 dc 3.3 pwl(0 0 100u 0 …)` feeding `R1 n1 n2 1k`
/ `C1 n2 0 1u` prints `v(n1) = v(n2) = 0` at t = 0 under `tran` (τ = 1 ms, so
a 3.3 V seed could not have decayed away by then), while ngspice still prints
the note above for the op it performed.

**The practical rule, therefore: write `uic` on the transient.** `uic` skips
that operating-point solve outright, which is what makes the EN edge the
*only* thing establishing the start state. The consequence is per-source, not
per-bench, and depends entirely on what the `dc` value is:

| `VEN` form | Transient op solves with | Exposed? |
|---|---|---|
| `dc 'vsup' pwl(0 0 …)` | `EN = 'vsup'` — **enabled, loop closed** | **Yes** — needs `uic` |
| `dc 0 pwl(0 0 …)` | `EN = 0` — disabled | No (the carve-out above) |
| `PULSE(0 'vsup' …)`, no `dc` keyword | `EN = 0` (the pulse's initial value) | No (the carve-out above) |
| `'vsup'` (a plain DC source) | `EN = 'vsup'` — enabled, loop closed | **Yes** |

`sim/current-limit` is the only bench in `sim/` whose dual-form `VEN` carries
an *enabled* `dc` value, so it is the only bench this correction moves;
`sim/enable-shutdown` (`dc 0 pwl(…)`) and `sim/startup` /
`sim/mc-output-accuracy` / `sim/ic-screen-125c-c` (`PULSE(…)`, no `dc`
keyword) keep their **Clear** verdicts on their own merits, and the benches
with a plain `'vsup'` `VEN` were already verdicted **Exposed**.

**Why an unconstrained `.op` is not acceptable for a claim against
`spec/target-spec.md`:** ngspice's Newton solver on a from-nowhere `.op` is
not guaranteed to land on the circuit's actual operating point — it can
converge to a numerically spurious branch instead, and it does not always
tell you when it has. Issue #164 (closed via PR #170, merged `3a7d2bc6`) is
the precedent: `mc-output-accuracy`'s original testbench seeded its transient
from an unconstrained `.op`, and on the committed N=200 sample sequence, 12
of the 200 draws settled with `FB` at up to 1.3e15 V while `VOUT` sat at
`VIN` — a state that violates the passive feedback divider's own algebra
(`FB` is a tap fed only by `VOUT` through a resistor string, so `FB` can
never exceed `VOUT`). The mechanism was `sky130_fd_pr__res_xhigh_po`'s
non-monotone voltage-coefficient extrapolation admitting a numerical "solution"
thousands of volts off the physical range; a nominal-device `.nodeset`
reproduces it with no mismatch involved, so it is a solver-seeding defect, not
a device-mismatch finding. The fix was to seed the transient from a
physically realizable state (`uic`, `EN` as an edge) instead — see
`sim/mc-output-accuracy/experiment.json`'s `mc_analysis.note` and
design/README.md "#164" for the full measurement.

**The harness now detects the hazard mechanically, not just by testbench
convention.** When an unconstrained (or otherwise poorly seeded) `.op` chain
hits this failure mode, ngspice's Newton solver falls back to gmin/source
stepping before it gives up, and — whether or not that fallback itself
"succeeds" — it prints one or more diagnostic lines to stdout/stderr:

- `Warning: singular matrix:  check node <node>`
- `Warning: Dynamic gmin stepping failed` (also catches `Warning: True gmin
  stepping failed` — both contain the substring `gmin stepping failed`)
- `Error: <value>, 2 out of range for ^` — the solver evaluated an expression
  (e.g. a poly-resistor's voltage-coefficient term) at a value so far outside
  its intended domain that `pow()` itself errors

`sim/bin/corner-run.py`'s `SOLVER_DIAGNOSTIC_MARKERS` is deliberately the
three forms above, confirmed against real committed logs at the time of
writing (issue #171) — not an attempt at an exhaustive catalog of every
ngspice non-convergence message. In particular, `Warning: source stepping
failed` (a fourth ngspice fallback, seen in some already-committed 125 °C
corners of `sim/dropout-vs-load` and `sim/thermal`) is evidence of the same
underlying class of hazard but is **not yet matched** — widening the marker
set is a small, low-risk follow-up, not a blocker for this contract.

Critically, ngspice does **not** treat any of these as fatal — the run still
exits `0` and still prints what looks like a converged `.op`/`.meas` result,
so a harness that only checks the exit code and the measurement bounds grades
the corner as a clean PASS even though the state it measured may not be a
circuit state at all. `sim/bin/corner-run.py`'s `run_corner()` scans the raw
ngspice stdout+stderr for these markers on every corner and forces the corner
to **FAIL** — regardless of whether its measurements happen to land inside
their bounds — with a `reason` of the form `solver diagnostic: <the matched
line>`, distinct from an ordinary measurement-bound failure. The raw
stdout/stderr (where the diagnostic came from) is always written unchanged to
the corner's `.log` file, so the diagnostic that triggered the FAIL is visible
in the committed evidence, not just summarized.

This detection mechanism lives entirely inside `sim/bin/corner-run.py` — it
covers every bench that runner drives (`sim/pdk-smoke`, `sim/dropout-vs-load`,
`sim/loop-gain`, `sim/line-regulation`, `sim/load-regulation`,
`sim/ic-screen-125c-*`, etc.), not `sim/bin/mc-run.py`'s Monte Carlo/`klt sim`
benches (`sim/mc-output-accuracy`, `sim/mc-ic-screen-*`) — those already carry
their own per-sample `diagnostics` field in the `klt sim` response, which this
issue does not touch (the equivalent capability at that tool layer is tracked
by `2AMLogic/klayout-tools#2489`, not this repo's issue).

**#171 was the detection mechanism only — it did not convert any bench's own
analysis chain.** `sim/line-regulation` and `sim/load-regulation` chained
four (respectively two) `.op` solves via `alter` cards with no `uic`/`.ic`
seed at all (`experiment.json` → `deck.analyses`), which did **not** meet
this contract; their 45-corner records up to and including
`20260925-114251-1f54ca6` / `20260925-111601-7701e7e` predate the check and
were graded before it existed. **Issue #172 converted both** — see
"Line regulation and load regulation re-run under the #171 contract
(issue #172)" below for the conversion, the settling measurement behind it,
and the verdict changes. `sim/iq` (#173) is still unconverted, and the
remaining benches' audit is #174 (verdict table below). `sim/ic-screen-125c-*`
(`uic` or `.ic`-seeded, per above) and `sim/startup` (disabled-state seed,
per above) already meet this contract: re-running them under the new check
should report no diagnostic and leave their verdict unchanged.

**Issue #178 converted the two benches whose exposed analysis was a bare `dc`
sweep** — `sim/dropout-vs-load` (a VIN sweep) and `sim/thermal` (two `dc temp`
sweeps). That turned out to be a case neither #170 nor #172 could have covered,
because ngspice honours `.ic` only for the operating-point solve preceding a
non-`uic` transient: a `dc` analysis cannot be given either of the two seed
shapes this contract names. See "#178: dropout-vs-load and thermal" below for
the measurement behind that statement and for what each bench did instead.

**#174 audited the remaining benches (`current-limit`, `dropout-vs-load`,
`loop-gain`, `load-transient`, `psrr-dc`, `thermal`, plus a re-confirmation
of `startup`/`enable-shutdown`) against this contract, read-only — no
bench's `experiment.json`/`testbench/*.sch` was changed by that issue.**
Verdicts (verified against `origin/main` @ `2a2c0e6`, 2026-09-25 — see #174
for the full evidence trail and #177/#178/#179/#180 for the follow-up
conversions):

| Bench | Verdict | Mechanism |
|---|---|---|
| `current-limit` | **Exposed** — on **all** of legs 1 and 3, not just leg 1 (corrected by #177, see below) | Leg 1's `op` (`experiment.json:24`) runs with `VEN`'s `dc` value (`'vsup'`, fully enabled) per `testbench/tb_current_limit.sch:145` — an unconstrained, loop-closed solve. ~~(Leg 3's `tran` is *not* exposed: ngspice's non-`uic` transient uses the source's PWL value at t=0, which starts at 0/disabled, per the same line's comment.)~~ **That parenthesis is wrong**, and #177 measured it wrong: a non-`uic` `tran` performs an operating-point solve first and reads the `dc` keyword value there, so leg 3's `tran` was exposed by the same mechanism as leg 1's `op` — see "An EN edge alone does not satisfy the first shape" above. Run per-leg at `tt_27c_3.30v` with no `uic`, legs 1 and 3 each tripped `Warning: Dynamic gmin stepping failed`; leg 2's `dc` sweep did not. Converted by #177: both transient legs now carry `uic`. |
| `dropout-vs-load` | **Exposed** → **converted (#178)** | Its only analysis, `dc VVIN 3.63 1.5 -0.02` (`experiment.json:23`), ran with `VEN` held at a constant `'vsup'` (`testbench/tb_dropout_vs_load.sch:108`, no PWL/PULSE at all) — unconstrained, loop-closed. **#178 replaced the `dc` sweep with a cold-start `uic` transient whose VIN is a quasi-static down-ramp** — see "#178: dropout-vs-load and thermal" below. |
| `loop-gain` | **Exposed** → **converted (#179)** | Its first analysis, `ac dec 30 1e-2 1e9` (`experiment.json:24` as audited), ran with `VEN` held at a constant `'vsup'` (`testbench/tb_loop_gain.sch:102`) — the implicit linearization-point solve ngspice performs before an `ac` analysis is unconstrained, and it is redone from scratch for each of the deck's seven `alter`-reached points. **Converted by #179** to the `.nodeset`-seeded `.ac` shape above. |
| `load-transient` | **Exposed → CONVERTED (#180)** | Was `tran 200n 3m` with no `uic`, with `VEN` held at a constant `'vsup'` (`testbench/tb_load_transient.sch`) — the same "`tran` with no `uic`" defect `#164` fixed for `mc-output-accuracy`. **#180 converted it** to the `.ic`-seeded shape (variant B): `testbench/tb_load_transient.sch`'s `IC_SEED` card constrains the operating-point solve to the loop's regulating branch at the pre-step 1 mA load and the (still non-`uic`) transient is released from it. See "`load-transient` after #180" below. |
| `psrr-dc` | **Exposed** → **converted (#179)** | Its first analysis, `ac lin 3 1e3 1e5` (`experiment.json:24` as audited), ran with `VEN` held at a constant `'vsup'` (`testbench/tb_psrr_dc.sch:67`), for both its 1 mA and its `alter`-reached 50 mA point. **Converted by #179** to the `.nodeset`-seeded `.ac` shape above. |
| `thermal` | **Exposed** → **seeded (#178)** | Its first analysis, `dc temp 80 180 2` (`experiment.json:48`), ran with `VEN` held at a constant `'vsup'` (`testbench/tb_thermal_trip.sch:78`). **#178 seeded both `dc temp` sweeps with a `.nodeset` measured from a settled cold-start transient** — the only mechanism available to a temperature sweep, see "#178: dropout-vs-load and thermal" below. |
| `startup` | **Clear** | `VEN` is `PULSE(0 'vsup' 100u 1u 1u 100 200)` (`testbench/tb_startup.sch:89`) — no separate `dc` keyword, so its `.op`/`.tran` default DC value is the pulse's own initial level (0 V, disabled). The disabled state has no closed feedback loop to disambiguate, per this contract's own carve-out above. |
| `enable-shutdown` | **Clear** | `VEN` is `dc 0 pwl(0 0 100u 0 101u 'vsup' 2m 'vsup' 2.001m 0 10 0)` (`testbench/tb_enable_shutdown.sch:117`) — the **`dc 0`** is what earns this verdict (not the PWL's t=0 value: #177 showed a non-`uic` `tran`'s op reads the `dc` keyword, so an enabled `dc` value would have exposed it). Leg 1's `tran` therefore solves its op at `EN = 0`, disabled, and reaches regulation through an EN edge (the contract's `uic` + EN-edge shape, informally: no `uic` keyword is present, but the disabled start makes the distinction moot the same way it does for `startup`); legs 2-4's `op`s carry the same `dc 0`, landing on the same disabled state. |

### #178: dropout-vs-load and thermal — and what a `dc` analysis can and cannot be seeded with

Both benches #178 owns ran a bare `dc` sweep as their only (`dropout-vs-load`)
or first (`thermal`) analysis. Converting them measured something the contract
above did not yet say, and that the other conversions (#170, #172) never had to
find out, because none of them had a `dc` sweep to keep:

- **`.ic` does not reach a `dc` analysis at all.** ngspice applies `.ic` to the
  operating-point solve that precedes a *non-`uic` transient*; a `dc`/`op`
  solve ignores it. Measured directly on `dropout-vs-load` (tt/125 °C/3.30 V,
  one corner): adding the eleven-node `.ic` card copied verbatim from
  `sim/ic-screen-125c-b` left the sweep's flail completely intact — `singular
  matrix` ×6, `Dynamic gmin stepping failed` ×16, `out of range for ^` ×13,
  with iterates at 1e155–1e188 V on the `sky130_fd_pr__res_xhigh_po` body
  expressions (`xr_fb_b`, `xr_fb_c`, `xr_cz`) — i.e. indistinguishable from the
  unseeded run. #172 had already measured the other half on the regulation
  benches: `.nodeset`, which a bare solve *does* honour, still printed
  `singular matrix` plus `Dynamic gmin stepping failed` at 3 of 5 corners
  probed there.
- **A seed can only ever fix a sweep's first point.** `dropout-vs-load`'s
  superseded record carries *thousands* of diagnostics per corner log, not one
  each: the continuation re-derives — and repeatedly re-loses — the regulating
  branch all the way down the sweep. Seeding the start cannot address that.

So the two benches took different routes, for a reason that is about ngspice's
capabilities, not about taste:

- **`dropout-vs-load` stopped being a `dc` sweep.** VIN is now a PWL ramp
  inside one cold-start `uic` transient (`tran 10u 26m uic`): 0 → 3.63 V by
  100 µs with `VEN` stepping high at 100 µs, the ideal 50 mA sink ramped on
  over 2.5–2.6 ms once the loop is up (`sim/ic-screen-125c-c`'s own cold-start
  convention, verbatim — an ideal sink on a disabled, discharged output is not
  a realizable state), settled by 5.5 ms, then VIN walked down 3.63 → 1.5 V
  over 6–26 ms at 106.5 V/s. There is no operating-point solve in the deck at
  all: the contract's `uic` + EN-edge shape, the same one #170 and #172 landed.
  **Quasi-static, measured not assumed** (tt/27 °C/3.30 V): the 20 ms ramp
  reads `dropout_v` = 0.397295 V, a 3× slower 60 ms ramp reads 0.398492 V, and
  the superseded `dc` record — the zero-rate limit of the same experiment —
  reads 0.399743 V. ~1.2 mV per 3× rate change, moving *toward* the DC answer
  as the ramp slows, 2.4 mV of total span against a 300 mV ratified bound. The
  supply axis keeps its pre-#178 meaning exactly: VIN starts at 3.63 V for
  every corner (as the `dc` sweep's own first point did, independently of
  `'vsup'`) and `'vsup'` still sets `EN`'s rail alone.
- **`thermal` could not stop being a `dc` sweep.** ngspice has no
  time-varying `TEMP`, so a temperature sweep cannot be a transient, and the
  `uic` + EN-edge shape is unavailable to this bench — a `dc` analysis
  evaluates a time-dependent source at t = 0, so giving `VEN` a PULSE edge
  would hold `EN` at 0 and disable the block for the whole sweep. That leaves
  `.nodeset` as the only seed mechanism that reaches the solve at all. The card
  seeds the **ascending** sweep's own 80 °C starting point with the node set of
  a settled cold-start `uic` transient of that same testbench at
  tt/80 °C/3.30 V (V(VOUT) 1.80076 V, regulating, zero solver diagnostics), so
  the values are a *measured* realizable state rather than a guess. Two limits
  are recorded in the testbench header rather than papered over: `.nodeset` is
  a netlist card, so both sweeps share it (right at 80 °C ascending, a
  deliberately wrong — but first-guess-only — state at the descending sweep's
  180 °C start, where the block is expected to be tripped; ngspice offers no
  per-analysis nodeset), and this bench's `trip == reset` degeneracy is the
  pre-existing DC-continuation limitation #77 found and #91 carries forward,
  which #178 neither fixes nor worsens.

Because `.nodeset` is the weaker mechanism (a first-iteration constraint that
is then released, not a held state), `thermal`'s conformance is established by
the measured absence of solver diagnostics in its post-#178 record, not by the
mechanism's pedigree.

#### What `dropout-vs-load`'s re-run found (record `20260926-043132-eba96ae`)

**Zero solver diagnostics on all 45 corners, and zero timeouts** — against
**45 of 45** corner logs carrying one in the superseded `20260923-123440-d71f4b3`
(7070 marker hits in total there, plus `source stepping failed` on 3 of them;
the new record has 0 of each, that fourth marker included). The `#171` gate is
therefore satisfied mechanically, not by assertion.

**The verdict changed, and not in the flattering direction: 6/45 → 0/45 PASS.**
All six of the superseded record's PASSes were `ss`/−40 °C and `ss`/27 °C
(0.268–0.298 V against the 300 mV bound); those same corners now read 0.513 V
and 0.400 V. The rest of the matrix mostly *agrees* with the old numbers —
`tt`/27 °C to 2 mV, `ff`/−40 °C and `ff`/27 °C to 7 mV, `sf`/125 °C and
`fs`/125 °C (3.30/3.63 V) to 4 mV — so this is not a wholesale shift; it is the
`ss` column moving.

**That flip is validated at zero ramp rate, at the exact corner, rather than
argued.** A static two-point hold at `ss`/−40 °C/2.97 V (cold start, settle at
3.63 V, step to a held VIN, 6 ms of settling at each hold, no ramp anywhere
near the measurement) reads:

| Held VIN | Settled V(VOUT) | Regulating (≥ 1.764 V)? |
|---|---|---|
| 2.28 V | 1.79746 V | yes, by 33 mV |
| 2.10 V | 1.73008 V | **no** |

So the static crossing lies just below 2.28 V — i.e. `dropout_v` just under
0.516 V, within 3 mV of the ramp's own 0.5134 V — and the superseded record's
0.268 V would require regulation to hold at VIN = 2.032 V, where this test
shows the block is already 34 mV out of regulation at 2.10 V. **The old PASSes
were an artifact of the unseeded sweep, not a capability the design has.**

**The 125 °C caution this bench has carried since #71/#81 is discharged for
`dropout_v`.** The five corners the superseded record returned as obvious
garbage — `ss_125c_*` at 1.41–1.83 V, `ff_125c_2.97v` at 1.82 V,
`fs_125c_2.97v` at 1.83 V — now read 0.330 V, 0.673 V and 0.432 V, i.e. in
family with their own process/temperature siblings to within a few mV, and the
whole matrix now spans a tight **0.330–0.673 V** with supply scatter below
1 mV (as it should: VIN is the same ramp at every corner, and `'vsup'` only
sets `EN`'s rail). `ff_-40c_3.63v`, a 300 s timeout with no measurement at all
in the superseded record, now completes and reads 0.6585 V.

**One residual, reported rather than suppressed**: `fs_125c_2.97v`'s
`vout_at_max_vin_v` sanity measurement reads **−7.45 V** (it was −14.06 V in
the superseded record) while its `dropout_v` reads a perfectly in-family
0.432 V. It is the only one of the 45 corners outside the sanity band — the
superseded record had 7 (six on a non-regulating 3.17–3.49 V branch, plus that
−14 V) — and it carries **no** solver diagnostic, so it is not the seeding
defect: the block is not coming up at all at that corner, and the ideal 50 mA
sink then drags the discharged output negative. Note what is peculiar to it:
`'vsup'` = 2.97 V sets `EN` 0.66 V *below* the 3.63 V VIN the ramp starts from,
which is this bench's own pre-#178 convention (see "SUPPLY AXIS" in the
testbench header), and the `*_125c_2.97v` column is where both records put
their worst `vout_at_max_vin_v` outliers. That is a finding for a follow-up,
not something #178 fixes.

**Ramp-rate caveat, stated because it is real**: rate independence was measured
at tt/27 °C (1.2 mV over a 7.5× rate range) and confirmed against a static hold
at ss/−40 °C (3 mV). It is *not* rate-independent everywhere: a 765 V/s hold
probe at ss/−40 °C read 0.581 V against the 266 V/s matrix's 0.513 V, so at the
cold/slow corners a faster ramp does inflate the number. 266 V/s is inside the
validated window at both corners checked; a bench-wide per-corner rate sweep
was not run.

#### What `thermal`'s re-run found (record `20260926-052517-eba96ae`)

**Not zero diagnostics — 2 of 15 corners still trip the `#171` gate, and that is
reported rather than suppressed.** The count falls from **14 of 15** corner logs
(132 marker hits) in the superseded `20260825-104426-933dfdd` to **2 of 15**
(18 hits): `ss_27c_2.97v` and `sf_27c_2.97v`, both on
`Dynamic gmin stepping failed` → `True gmin stepping failed` →
`source stepping failed`, each time recovered by ngspice's own "Transient op"
fallback. `corner-run.py` forces both to `FAIL` with
`solver diagnostic: Warning: Dynamic gmin stepping failed`, which is the gate
working as designed.

**The residual is not the one-card seeding limitation.** Re-running the
**ascending** sweep *alone* at `ss_27c_2.97v` — the sweep whose own 80 °C start
point the `.nodeset` describes exactly — still prints 6 `gmin stepping failed`
plus 3 `source stepping failed`, and returns `trip_temp_c` = 150.6582 °C, the
same value to four decimals as the full two-sweep run. So the descending sweep's
deliberately-wrong 180 °C seed is *not* what produces them: a correctly seeded
ascending sweep flails too, somewhere along its own path rather than at its
start. Two candidate mechanisms, neither isolated here:

1. **The trip transition itself.** A `dc` continuation has no continuous branch
   to follow across a comparator threshold with positive feedback around it —
   VOUT collapses and the comparator latches over, so the solver has to jump. A
   *start* seed cannot help with a difficulty located at the crossing. This
   would make the residual a methodology limit of `dc temp` continuation, of the
   same family as (though distinct from) the `trip == reset` degeneracy #77
   found and #91 carries.
2. **The seed being derived at one supply.** Both surviving corners are
   `*_2.97v`, and the `.nodeset`'s VIN-relative values were measured at
   `vsup` = 3.30 V. A per-supply seed would settle this; 3.63 V is equally far
   from 3.30 V and is clean, which argues against it, but not decisively.

**Verdict: 12/15 → 13/15 PASS**, with three corners changing in each direction's
favour: `tt_27c_3.63v` and `ff_27c_3.63v` go FAIL → PASS (their −2.00 °C and
−8.00 °C hysteresis readings are now 0.00 °C), and `sf_27c_2.97v` goes
PASS → FAIL (0.00 °C → −12.00 °C, alongside its diagnostic). `ss_27c_2.97v`
stays FAIL with its negative hysteresis deepening from −2.37 °C to −12.34 °C.

**Every trip temperature moved up, substantially and consistently**: +13 to
+16 °C at eleven of the fifteen corners (e.g. `ss_27c_3.63v` 138.914 → 155.001,
`sf_27c_3.63v` 138.769 → 155.001, `tt_27c_3.30v` 150.587 → 165.001), while the
two corners that still carry a diagnostic barely moved (`ss_27c_2.97v` 150.632 →
150.658, `sf_27c_2.97v` 149.000 → 149.000). The whole matrix now trips between
**149.0 °C and 171.0 °C**, i.e. every corner above the 125 °C `min` bound and
closer to DR-005's 150 °C nominal target than the superseded record's
138.8–163.0 °C suggested.

**That shift must NOT be attributed to the seeding.** This record is also this
bench's **first run against the current DUT**: `thermal` was one of the four
benches deliberately left out of #69's re-run generation (see the 2026-08-25
record-generation note above) and was not part of #116's either, so its
superseded record was reported `STALE` in `measurements/characterization.md`
precisely because its netlist snapshot no longer matched the schematic — and #69
**re-sized the thermal-shutdown circuit this bench measures**, while #116
re-sized the pass device. The Thermal row's freshness goes `STALE` → `fresh`
with this record. Seeding and two DUT re-sizes changed together here; the two
effects are not separable from these two records, and this section does not
claim they are. (`dropout-vs-load` has no such confound: its superseded record
*was* #116's own re-run, i.e. the same DUT.)

**The `trip == reset` degeneracy is untouched, as #178 said it would be**:
hysteresis reads exactly 0.00 °C at thirteen corners and negative at the two
diagnosed ones. That is #77's finding, carried by #91, and a seed at the
sweep's start was never going to address it.

**Both benches' bullets under "The LDO's own testbenches" carry the same
numbers.**

Every "Exposed" verdict above is corroborated by the bench's own latest
committed corner logs already carrying a `singular matrix` / `gmin stepping
failed` / `out of range for ^` / `source stepping failed` diagnostic on a
majority of corners (see #174/#177/#178/#179/#180 for the exact counts) —
the same fingerprint `#164`/`#171` used to characterize the hazard, not just
an inference from the deck/testbench text.

**#177's correction to the two "Clear" rows is a strengthening, not a
weakening.** Both were graded on the wrong reason (the PWL's t = 0 value) and
both survive re-grading on the right one (`dc 0`, and no `dc` keyword at
all) — see the per-source table in "An EN edge alone does not satisfy the
first shape" above for the full four-way case split. No bench's verdict
changes except `current-limit`'s, which gains leg 3.

### `load-transient` after #180

**Shape chosen: variant B (`.ic`-constrained `.op`, released into a non-`uic`
transient)**, not `uic` + an EN-edge preamble. Both shapes satisfy this
contract; this bench picks the `.ic` one for two reasons specific to what it
measures:

- It steps the **load**, not `EN` (`PULSE(1m 50m 1m 1u 1u 1m 4m)` on
  `I_LOAD`), at an already-regulating condition, and both clauses of the
  ratified row are referred to the *pre-step* steady state. An EN-edge
  preamble would shift the deck's whole time axis and with it every `meas`
  timestamp.
- More importantly, an EN preamble makes `C_OUT`'s pre-step charge state a
  function of the soft-start ramp. `#119` root-caused this bench's
  peak-excursion clause as **charge-limited** (`Q = C·dV` against the loop's
  finite large-signal response time, not phase-margin-limited), so the
  pre-step charge state is precisely the variable the bench must hold fixed.
  The `.ic` seed leaves the 1 mA pre-step operating point, the 1.000 ms /
  2.001 ms step edges and the 3 ms span exactly where they were — **no
  `meas`/`let` timestamp moved.**

The seed itself is the eleven-node `IC_SEED` card in
`sim/load-transient/testbench/tb_load_transient.sch` (same eleven nodes and
the same `vsup`-relative convention as `sim/ic-screen-125c-b`). Its values are
not invented: they come from a local probe of *this* circuit cold-started
through its own EN edge (`VEN` as a `PULSE`, `tran 200n 1m uic`) sampled at
t = 0.9 ms — settled at the pre-step 1 mA load, before the step — at
tt / 27 °C / 3.30 V. The schematic's header records the raw numbers and the
rounding. The seeded state satisfies the passive divider's own algebra
(`FB = VOUT/1.5`, `N_FBB = FB/2`), which is the realizability check `#164`
showed an unconstrained solve can violate.

**Two measurement expressions were re-expressed, and it is a consequence of
the seed, not a bound change.** Under an `.ic` seed, `v(vout)[0]` is the seed
value (`VOUT` clamped to 1.8 exactly), not the corner's own settled 1 mA
point, and the seed's relaxation toward that point during 0–1 ms is not a
load-step excursion. So the pre-step reference became a 0.800–0.999 ms average
(`v_pre`) and the peak searches became windowed (`v_post_min` / `v_post_max`
over 1.000–2.999 ms, matching `w_fall`'s own end). `undershoot_v` and
`overshoot_v` measure the same physical quantity against the same ratified
150 mV bound; only the reference sample and the search window changed. No
bound, stimulus, `C_out`/ESR point or measured quantity was touched.

**Isolation probe (local, three corners, same DUT and manifest, control deck
identical but with the `.ic` line deleted):**

| corner | unseeded control (under / over / rise / fall) | seeded | unseeded diagnostics |
|---|---|---|---|
| tt/27 °C/3.30 V | 0.084470 V / 0.065478 V / 99.5 µs / 606.1 µs | 0.084470 / 0.065478 / 99.5 / 606.1 | `singular matrix: xldo.xr_fb_b.t2` |
| ss/−40 °C/2.97 V | 0.076325 / 0.059782 / 91.3 / 546.1 | 0.076322 / 0.059784 / 91.3 / 546.1 | none |
| ff/125 °C/3.63 V | 0.098869 / 0.074635 / 113.7 / 651.5 | 0.098793 / 0.074678 / 113.5 / 651.3 | `singular matrix: xldo.xr_cz.t1` ×2, `Dynamic gmin stepping failed` |

Every measurement agrees with the unseeded control to ≤0.1 %, and both corners
that emitted a solver diagnostic unseeded emit none seeded — the seed removes
the numerical hazard without moving the physics. (The residual `Eta0 is
negative` lines are PDK model-card warnings, not one of `corner-run.py`'s
`SOLVER_DIAGNOSTIC_MARKERS`.)

**The 45-corner re-run: `20260926-013955-6449a98`** (supersedes
`20260825-081255-4cb27f8`; the superseded record and its logs are untouched,
per the append-only rule).

- **The hazard is gone: 0 of 45 corner logs carry a solver-diagnostic marker**,
  against **23 of 45** in the superseded record (`grep -lE 'singular
  matrix|gmin stepping failed|out of range for \^|source stepping failed'` over
  each record's `corners/*.log`). No corner was forced to `FAIL` by `#171`'s
  gate — every `solver_diagnostic` field in the new record's `.json` is empty.
  (The superseded record's JSON has no `solver_diagnostic` field at all: it was
  written before `#171` landed, which is exactly why its 23 hazard corners were
  graded on their measurement bounds alone.)
- **Verdict: 0/45 PASS, against the superseded record's 25/45.** Twenty-five
  corners moved `PASS` → `FAIL`; twenty were already `FAIL` and stayed `FAIL`;
  none moved `FAIL` → `PASS`.

**That verdict change is not caused by the seed, and reading it as such would
be wrong.** The two records do not measure the same manifest:

| | superseded `…-4cb27f8` (2026-08-25) | new `…-6449a98` |
|---|---|---|
| measurements | `undershoot_v`, `overshoot_v` only | + `recovery_rise_us`, `recovery_fall_us` (added by `#119`), + `settle_err_50ma_pct` |
| `C_out` | 1 µF | 4.7 µF (`#119`) |
| failing measurements | `undershoot_v` ×20, `overshoot_v` ×4 | `recovery_rise_us` ×45, `recovery_fall_us` ×45 |
| peak excursion (ratified ≤150 mV) | 0.102–0.393 V — **20 corners over** | 0.063–0.119 V — **every corner inside** |

So the **peak-excursion clause now passes at all 45 corners** (it failed at 20
before), and every one of the 45 new failures is the **recovery-time clause**
(`recovery_rise_us` 74.7–132.1 µs and `recovery_fall_us` 425.7–796.1 µs against
the ratified ≤20 µs) — a clause the superseded record never measured. Both
movements are the expected, already-documented sign of `#119`'s `C_out`
1 µF → 4.7 µF change: the peak excursion is charge-limited (`Q = C·dV`, so more
`C_out` helps it) and the recovery time runs the opposite way against the same
capacitor. `#119` recorded that tradeoff from a 3-corner subset; **this is the
first full 45-corner record of the post-`#119` manifest**, so it also completes
the re-verification `#166` was filed to get. The `.ic` seed's own contribution
is bounded by the three-corner isolation probe above: ≤0.1 %, which cannot move
a 74.7 µs measurement across a 20 µs bound.

`0/45 PASS` is therefore an honest design finding against a ratified row, not a
harness regression — the recovery-time gap is real and was previously
under-measured. No bound in `spec/target-spec.md` was touched.

Two incidental differences between the two records, neither affecting the
comparison above: the new record ran on a different host (`ngspice-46` /
`Darwin 27.0.0` vs the superseded record's `ngspice-47` / `Darwin 25.6.0`), and
`measurements/characterization.md`'s "Load transient" row moves from `STALE` to
`fresh` because the new netlist snapshot again matches a live re-netlist of the
current testbench.

### `#179` — converting `sim/loop-gain` and `sim/psrr-dc` (the two `ac` benches)

`#179` converted the two `ac`-analysis benches the table above lists as
**Exposed**. Both now carry the `.nodeset`-seeded `.ac` shape defined above,
and both new records supersede their predecessor:

| Bench | New record | Supersedes | Verdict | Corners PASS |
|---|---|---|---|---|
| `loop-gain` | [`20260926-040338-4a9ec09`](loop-gain/records/20260926-040338-4a9ec09.md) | `20260825-081257-4cb27f8` | **FAIL** (unchanged) | 7/45 (was 7/45) |
| `psrr-dc` | [`20260926-033606-4a9ec09`](psrr-dc/records/20260926-033606-4a9ec09.md) | `20260923-125412-d71f4b3` | **FAIL** (unchanged) | 0/45 (was 0/45) |

**Neither row's verdict changed, and neither row's verdict is comparable
corner-for-corner with its predecessor** — both superseded records were cut
*before* `#116`/`#139` re-sized the shared DUT's pass device, so their
netlist snapshots were `STALE` and their numbers are "against the 2500 µm
pass device". `loop-gain` lands on 7/45 again but on a *different* seven
corners (`tt_125c_2.97v`, `ss_125c_3.30v` and `ff_125c_2.97v` in, and
`tt_125c_3.63v`, `ss_125c_3.63v` and `ff_125c_3.63v` out). That movement is
the pass-device resize, not the seed — see the seeded/unseeded control
below, in which every measurement that both variants can compute agrees to
five or six digits.

**Why three seeded nodes and not eleven.** All four variants below were run
over the full 45-corner matrix on the *same* committed decks (extracted from
the new records' own corner logs, with only the `.nodeset` card swapped) and
with `sim/spiceinit` in place, so they are harness-equivalent and directly
comparable. "non-regulating points" counts `vout_seed_*` measurements that
did not land within 50 mV of 1.8 V — i.e. `ac` analyses that linearized
about a state where the pass device is simply full-on (`VOUT = VIN`):

| Seed | `loop-gain` diag. corners | `loop-gain` non-reg. corners / points | `psrr-dc` diag. corners | `psrr-dc` non-reg. corners / points |
|---|---|---|---|---|
| none (the pre-`#179` shape) | 13 / 45 | 3 / 6 | 2 / 45 | 1 / 1 |
| **three nodes (`VOUT`, `FB`, `N_FBB`) — shipped** | **3 / 45** | **0 / 0** | **2 / 45** | **0 / 0** |
| six nodes (the three + `SS`, `NB`, `BIASP`) | 2 / 45 | 2 / 4 | 1 / 45 | 1 / 1 |
| eleven nodes (`sim/ic-screen-125c-b`'s seed verbatim) | 9 / 45 | 2 / 4 | 6 / 45 | 1 / 1 |

The three-node seed is the only variant that leaves **no** `ac` analysis
linearized about a non-circuit state, in either bench. The six-node variant
shaves one more solver diagnostic but leaves four non-regulating points
standing, and diagnostic count is not the thing the contract is for —
landing on the regulating branch is. The eleven-node variant is worse on
both axes, for the reason the contract section states: its values *are*
`ic-screen`'s 125 °C/50 mA operating point, and a `.nodeset` card is one
static card applied to every bias point in the deck.

**What the seed actually bought, in measurements.** Three corners the
unseeded deck got wrong on the current DUT:

| Bench / corner | Point | Unseeded | Three-node seed |
|---|---|---|---|
| `psrr-dc` `ss/−40 °C/3.63 V` | 1 mA | `VOUT` = 3.6333 V → PSRR 0.017 dB @ 1 kHz, 5.20 dB @ 100 kHz | `VOUT` = 1.8004 V → 25.66 dB, 31.88 dB |
| `loop-gain` `ss/−40 °C/3.63 V` | 1 mA (pts 2, 5) | `VOUT` = 3.6333 V → `pm_c033_1ma_deg` / `pm_c47_1ma_deg` unmeasurable | `VOUT` = 1.8004 V → 74.39° |
| `loop-gain` `ff/27 °C/3.30 V` | 0 mA (pts 3, 6) | `VOUT` = 3.2870 V → `pm_c033_0ma_deg` / `pm_c47_0ma_deg` unmeasurable | `VOUT` = 1.8025 V → 20.58° / 55.58° |
| `loop-gain` `ff/−40 °C/3.63 V` | 0 mA (pts 3, 6) | `VOUT` = 3.6402 V → both unmeasurable | `VOUT` = 1.8019 V → 18.54° / 46.87° |

The `psrr-dc` row is the sharpest illustration of why `#171` exists: 5.20 dB
at 100 kHz is a *number*, it is inside the record, and it is not a PSRR — it
is the small-signal response of a circuit with no loop closed around it.
Everywhere else the seeded and unseeded numbers are identical to five or six
digits, which is the reassuring half of the same result: the unconstrained
solve was landing on the right branch at 42 of 45 corners, and the contract
exists because "usually" is not a property you can cite.

**FINDING — the seed does NOT clear `#171`'s solver-diagnostic FAIL gate,
and that is reported rather than suppressed.** Three `loop-gain` corners
(`tt_-40c_2.97v`, `tt_-40c_3.63v`, `ss_-40c_3.30v`) and two `psrr-dc`
corners (`tt_-40c_2.97v`, `tt_-40c_3.63v`) still raise
`Warning: singular matrix:  check node xldo.ea_cz` and are therefore forced
to **FAIL** by the gate. Four facts about that residue, all measured:

1. **It is not made worse by the conversion.** Unseeded, the same matrices
   raise 13 and 2; seeded, 3 and 2. The `loop-gain` count *improved* by a
   factor of four.
2. **No corner's verdict turns on it.** Every one of those five corners
   already fails at least one ratified measurement bound, so removing the
   gate would not turn any of them into a PASS. The gate is currently
   reporting, not deciding, on these two benches.
3. **The node it names is a poly-resistor terminal inside the
   compensation network (`EA_CZ`), not a node the feedback loop
   disambiguates** — the same `sky130_fd_pr__res_*` family whose
   voltage-coefficient extrapolation `#164` identified as the mechanism. A
   node-voltage seed cannot reach it; `.nodeset` only constrains node
   voltages, and this is a device-model-domain problem.
4. **It is not reproducible from the committed deck alone.** Re-running a
   corner's embedded deck by hand in a directory *without* `.spiceinit`
   emits no warning and produces bit-identical measurements; the same deck
   run with `sim/spiceinit` present (i.e. with `option klu`) emits it. Any
   attempt to reproduce one of these diagnostics must copy `sim/spiceinit`
   to `.spiceinit` first, exactly as `sim/bin/corner-run.py` does.

Fact 3 is why `#179` does not attempt to fix it: the residue belongs to the
resistor-model mechanism `#164` characterized, not to the initial-condition
contract, and closing it is a separate piece of work.

**Reproducing the control (no PDK-side setup beyond the usual pin).** Every
number in the two tables above comes from the committed corner logs, which
embed the exact deck ngspice was given:

```bash
# extract one corner's deck, strip (or swap) its .nodeset card, re-run it
python3 - <<'EOF'
txt = open("sim/loop-gain/corners/20260926-040338-4a9ec09/ff_27c_3.30v.log").read()
i = txt.index("# ==== deck (exact input given to ngspice) ====")
deck = []
for line in txt[i:].split("\n")[1:]:
    if not line.startswith("| "):
        break
    deck.append(line[2:])
deck = [l for l in deck if not l.startswith(".nodeset")]   # <- the "none" variant
open("/tmp/ab/ff_27c_3.30v.spice", "w").write("\n".join(deck) + "\n")
EOF
cp sim/spiceinit /tmp/ab/.spiceinit     # REQUIRED -- see fact 4 above
cd /tmp/ab && ngspice -b ff_27c_3.30v.spice < /dev/null | grep -E "^meas_|singular"
```

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
representative point inside DR-002's ratified 0–500 mΩ window, not a sweep
of it). Full detail — exact stimulus, measurement expressions, and which
spec row each bound cites — lives in each experiment's own
`experiment.json` `claim` field, per this directory's own convention; this
section is a map, not a duplicate of that detail.

- **`load-transient/`** — `I_LOAD` steps 1↔50 mA (1 µs edges) at `VOUT`;
  measures undershoot/overshoot against `spec/target-spec.md`'s ratified
  "Load transient" row (peak excursion ≤150 mV). Latest quick-subset record
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
- **`psrr-dc/`** — small-signal AC sweep on VIN (1 kHz, 100 kHz) at **both**
  ratified load points (~1 mA and 50 mA, swept in one deck via
  `alter rload = 36`); measures PSRR against the "PSRR" row (>50 dB @ 1 kHz,
  >20 dB @ 100 kHz, at 1 mA and at 50 mA). Until #117 the deck measured only
  the ~1 mA point, because the pre-#25 amplifier had no regulating 50 mA
  operating point to linearize around; #25's output-stage rebuild removed
  that ceiling and #117 retired the simplification — see the testbench
  schematic's header. History below predates that change.
  Earlier quick-subset record (`20260818-015127-01b7905`, supersedes
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
  **Current record, both load points** (`20260923-125412-d71f4b3`, issue
  #117, supersedes `20260825-082845-4cb27f8`): **0/45 PASS**. The two 1 mA
  sub-metrics reproduce the superseded record digit-for-digit at every
  corner, so the deck change is a pure extension. Per sub-metric:
  `psrr_1khz_1ma_db` 20.31–25.68 dB (0/45), `psrr_100khz_1ma_db`
  31.53–34.77 dB (**45/45 PASS**), `psrr_1khz_50ma_db` 20.25–25.70 dB
  (0/45), `psrr_100khz_50ma_db` **13.80–16.06 dB (0/45)** — the last is the
  condition the one-load-point deck was not measuring, and it is the row's
  second failing sub-metric. The 1 kHz half is loop-bandwidth-bound and the
  100 kHz/50 mA half is supply-feedthrough-bound; both diagnoses, the
  measured `C_COMP` PSRR-vs-phase-margin frontier, and three screened-and-
  rejected circuit candidates are written up in `design/README.md` §"#117".
  **Superseded by `#179`** (`20260926-033606-4a9ec09`): the paragraph above
  is kept as written because its analysis is what that record actually says,
  but it is no longer the current record — `#179` seeded the deck's `ac`
  linearization points per the initial-condition contract and re-ran the
  matrix against the post-`#116`/`#139` DUT. Still **0/45 PASS**; current
  per-sub-metric numbers and the seeded/unseeded control are in "#179" above.
- **`dropout-vs-load/`** — DC VIN sweep at a fixed 50 mA load (the ratified
  spec row's own gf180-mirrored "sweep Vin toward Vout" method); measures the
  Vin–Vout margin against the ratified "Dropout @ 50 mA" row (<300 mV). Latest
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
  **Current record** (`20260926-043132-eba96ae`, issue #178, supersedes
  `20260923-123440-d71f4b3`, first run under the #171 initial-condition
  contract — the `dc VVIN` sweep is gone, replaced by a cold-start `uic`
  transient with a 266 V/s VIN down-ramp): **0/45 PASS, down from 6/45**, with
  **zero solver diagnostics on all 45 corners** (the superseded record carried
  one on all 45, 7070 hits in total). The six lost PASSes are exactly the
  superseded record's `ss`/−40 °C and `ss`/27 °C corners, and a static
  zero-rate hold test at `ss`/−40 °C confirms the new, larger numbers (VOUT
  settles at 1.7301 V with VIN held at 2.10 V, where the old 0.268 V reading
  would need regulation to hold at 2.032 V). The matrix is now a tight
  **0.330–0.673 V**: the five 125 °C corners the superseded record returned as
  1.41–1.83 V garbage now read in family with their siblings, so this bench's
  125 °C caution is discharged for `dropout_v`. One residual outlier remains,
  `fs_125c_2.97v`'s `vout_at_max_vin_v` at −7.45 V with no solver diagnostic.
  See "#178: dropout-vs-load and thermal" above for the full accounting.

- **`loop-gain/`** (issue #25) — AC loop gain, phase margin and gain margin
  against `spec/target-spec.md`'s ratified "Stability" row (PM ≥ 45°, GM ≥ 10 dB
  worst corner). Unlike the three above it walks its own second axis: each
  PVT point runs **seven** AC sweeps, `alter`-ing `C_OUT`/`R_ESR`/`R_LOAD`
  across DR-002's ratified window (`C_eff` ∈ {0.33 µF, 4.7 µF} × load ∈
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
  **Superseded by `#179`** (`20260926-040338-4a9ec09`): kept as written for
  the same reason as the `psrr-dc` paragraph above. Still **7/45 PASS**, but
  on a different seven corners — `#179` was this bench's first run against
  the post-`#116`/`#139` pass device, and it seeded all seven `ac` points per
  the initial-condition contract. See "#179" above.

- **`thermal/`** (issue #66) — trip/reset temperature and hysteresis for the
  thermal-shutdown circuit (#29/DR-005) against the spec's ratified "Thermal"
  row. Unlike the four above, it does not select `temperature_c` from the
  standard PVT corner axis — `TEMP` itself is the swept analysis variable
  (a continuous ngspice `.dc temp` sweep, 80→180 °C ascending then 180→80 °C
  descending in one session, DC continuation so the descending leg starts
  from the ascending leg's final operating point), walked across the full
  `process × supply_v` matrix. This required its own corner-coverage
  decision first (DR-005's 150 °C nominal trip target sits above DR-004's
  `{−40, 27, 125} °C` characterized axis) — see DR-005's `2026-08-25
  addendum` for the decision and `design/README.md`'s dated "Thermal-shutdown
  trip/hysteresis testbench" section for the full per-corner results and
  interpretation. First (and authoritative) full 15-point record
  (`20260825-054043-6fac47d`, supersedes `20260825-050729-6fac47d` — an
  ngspice `.meas`-interpolation artifact, not a circuit finding, see the
  experiment's own comments): **5/15 PASS** — `ff`/`sf` trip below the 125 °C
  operating ceiling at every supply corner (confirming and quantifying
  issue #69), and measured hysteresis is non-positive at every one of the
  15 corners (a new finding, filed as issue #77).
  **Current record** (`20260926-052517-eba96ae`, issue #178, supersedes
  `20260825-104426-933dfdd`, first run with both `dc temp` sweeps seeded from a
  measured untripped state): **13/15 PASS, up from 12/15**, and solver
  diagnostics down from **14 of 15** corner logs (132 hits) to **2 of 15**
  (18 hits) — `ss_27c_2.97v` and `sf_27c_2.97v`, which the #171 gate correctly
  forces to FAIL and which an ascending-sweep-only probe shows are *not* the
  shared-`.nodeset` limitation. Every trip temperature moved up 13–16 °C at the
  eleven undiagnosed corners (matrix now 149.0–171.0 °C, all above the 125 °C
  bound) — but this is *also* this bench's first run against the post-#69/#116
  DUT (its Thermal row goes `STALE` → `fresh`), and #69 re-sized the very
  thermal-shutdown circuit measured here, so that shift is not attributable to
  the seeding alone. The `trip == reset` degeneracy (#77/#91) is unchanged, as
  expected. See "#178: dropout-vs-load and thermal" above.

None of the four fully meets its spec bound yet. This is an honest,
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

Three more benches cover the spec rows whose *circuitry* landed with issue
#22 but which had no testbench of their own, so
`measurements/characterization.md` reported them `N/A` — a coverage gap by
that report's own Limitations section, neither substantiated nor refuted.
They share the four benches' stimulus and output-network conventions above;
what is new is that two of them drive the DUT through an **event** (a held
short, an enable edge) rather than a steady condition, so each states in its
own `experiment.json` `claim` how the event is applied and which clause of
the ratified row it grades. First records are `--quick` subsets, same as #18/#25;
issue #74 then ran the full 45-point matrix each manifest declares for all
three (see each bullet's "Full 45-point PVT record" below).

Two of these rows carry clauses with **no number in them at all** ("window
TBD over PVT", "survives", "monotonic"). Where a clause has a number, it is
bounded; where it does not, the quantity is measured and reported **without**
a bound rather than graded against a limit nobody has ratified — inventing
one would be exactly the fabricated-settled-number the root `CLAUDE.md`
forbids. Issue #1 / DR-006 ratified these rows *with* those clauses left
numberless, so the missing bounds are a deliberate, ratified property of the
spec rather than a pending ratification — only a future decision record can
supply a number. Each such measurement's `note` says so explicitly, and says
what would have to change if such a record lands.

- **`current-limit/`** — forces `VOUT` through a `VFORCE`/`RFORCE` branch
  (`RFORCE` starts at 1e12 and the deck `alter`s it to 1 mΩ) in three legs:
  a settled 50 mA operating point at a 36 Ω load with the branch open
  (leg 1), a DC characteristic from a dead short up to the 1.75 V knee
  (leg 2), and a `Vout = 0` short applied as a transient event and **held for
  2 ms** (leg 3) — a sustained fault of defined duration, not one sampled
  instant, since "survives" is a claim about holding the fault. Legs 1 and 3
  are both `tran … uic` riding the same `EN` edge at t = 100 µs (a dual
  `dc 'vsup'` + rising `pwl` source); leg 2 is the one `dc` analysis, and the
  one that still solves with `EN` at its `dc` value, which is correct there
  because the forcing branch pins `VOUT` at every swept point. Leg 1 reads
  its 50 mA point from t = 0.9–1.0 ms, after the soft-start ramp settles, and
  leg 3's fault at t = 1.0 ms likewise lands on a block that reached
  regulation through a real enable edge rather than an already-enabled t = 0
  DC solve — see the harness-lesson paragraph below, and the
  initial-condition contract's "An EN edge alone does not satisfy the first
  shape" for why `uic` (added to both legs by **#177**, which also converted
  leg 1 from a bare `op`) is load-bearing on top of that edge. Bounded:
  `vout_50ma_v`
  inside the ratified Output row's ±2% window (the operative form of "never
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
  which is what issue #76 fixed. **Full 45-point PVT record**
  (`20260825-085216-64c17cb`, issue #74, `--timeout 600` — the default 300 s
  budget genuinely wasn't enough at `tt_-40c_2.97v`/`tt_-40c_3.30v`, which
  needed 260–300 s+ even at their neighboring corners; re-run with the longer
  budget instead of accepting a timeout as the result, per this directory's
  own append-only-but-not-lazy convention. Supersedes `20260825-070327-d0bb614`,
  which supersedes the original `20260825-045313-703a889` — a two-hop chain
  now, both hops kept on disk): **39/45 PASS**. All 39 tt/ss/ff/sf/fs corners
  outside 125 °C regulate cleanly (short-circuit levels 108–236 mA against
  85–204 mA knees, −15.6%–−30.2% droop, all brickwall-shaped, <0.05% supply
  ripple through the full 2 ms hold). The six `ff_125c`/`sf_125c` corners
  **FAIL** legs 1–2 exactly as the quick subset's `ff_125c_3.63v` point
  showed — mechanism 1 (#69), not fixed here. Leg 3 (the held short, fixed by
  #76's EN ramp) is conclusive at all six of those corners now, but the two
  process corners tell different stories: `ff_125c` leg 3 reaches a genuine
  current-limiting state and sustains 108–148 mA through the short (in range
  with the neighboring corners), while `sf_125c` leg 3 shows the *same*
  thermal-shutdown collapse as its own legs 1–2 — sub-µA sustained short
  current (0.012–0.016 mA) rather than the 100+ mA the other corners show.
  That is a real, converged measurement (`ngspice` exit 0, well inside the
  600 s budget), not the pre-#76 stuck-branch artifact: the EN ramp does let
  `sf_125c` attempt soft-start, but the same mechanism-1 trip that kills
  legs 1–2 also kills the ramp before it reaches regulation, so leg 3 never
  gets a fault to "survive" at that corner. `ff_125c`'s escape from that
  trip during leg 3 (while legs 1–2 do not escape it) is a real,
  bench-observed asymmetry between the two process corners, filed as #93
  (why `sf` is more susceptible than `ff` to mechanism 1 during a ramped
  enable) rather than chased here — out of this issue's scope.
  **Record note (#177): every record above predates #177's deck change, and
  no re-run has replaced them.** The latest,
  `20260825-105322-933dfdd` (45/45 PASS, the authoritative one per "Which
  record set is authoritative" below), was graded before `corner-run.py`
  acquired #171's solver-diagnostic FAIL gate, and 16 of its 45 corner logs
  carry a `gmin stepping failed` / `singular matrix` diagnostic — under the
  gate as it now stands those 16 corners would be forced to **FAIL**
  regardless of their measured values. #177 fixed the deck that produced
  them (legs 1 and 3 to `tran … uic`; see the harness-lesson paragraph
  below), but **did not re-run the matrix**: `corner-run.py` has no
  remote/batch execution mode (`klt sim` has one, but this bench's
  multi-solve-per-corner `alter` chain is not expressible as a `klt sim`
  request — 2AMLogic/klayout-tools#2482), and the sweep host it would have
  run on forbids hand-launched local `ngspice` grids. So the committed
  records are evidence about the **pre-#177 deck only**, and this row's
  verdict against the current deck is **not established**. Closing that gap
  needs one `python3 sim/bin/corner-run.py sim/current-limit
  --supersedes 20260825-105322-933dfdd` on a host allowed to run it; the
  partial evidence #177 did gather (4 of the 45 corners, plus a per-leg probe
  at a 5th) is in its PR, not on disk here, precisely because an incomplete
  matrix must not be minted as a record.
- **`startup/`** — four independent **cold** enables in one deck (`C_out`
  0.33/4.7 µF × load 0/50 mA, the corners of the two ranges the ratified row
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
  witness. **Full 45-point PVT record** (`20260825-073320-64c17cb`, issue
  #74, supersedes `20260825-044139-703a889`): **42/45 PASS** — the three
  quick-subset points still pass, `ff_125c` passes cleanly at all three
  supplies (its own worst peak 1.827 V against the 1.836 V ceiling, worst
  floor 1.796 V, ramp times 0.42–0.58 ms — comparable to the rest of the
  matrix), and 39 non-125 °C corners are inside bounds throughout. The full
  matrix surfaces a new failure the 3-point subset never reached:
  **`sf_125c` fails at all three supplies** — `VOUT` collapses to 7–11 mV
  instead of settling into the regulation window (`vpk`/`vfloor` both ≈ the
  collapsed value, `tramp` `n/a` since the settle threshold is never
  crossed). This is the same mechanism-1 thermal-shutdown false-trip (#69)
  documented for `ff`/`sf_125c` in the four core-regulation testbenches, now
  confirmed to reach `startup/`'s cold-enable path at the `sf` process corner
  specifically (`ff_125c` escapes it here, matching `current-limit/`'s leg-3
  finding above) — filed as #93.
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
  the ratified bounds, which is as much a statement about that row's own
  "pending sky130 device data" note as about the design — the models'
  subthreshold/junction leakage is what sets these numbers. **Full 45-point
  PVT record** (`20260825-073259-64c17cb`, issue #74, supersedes
  `20260825-044140-703a889`): **42/45 PASS** — across the 42 passing corners,
  static shutdown Iq 0.13 nA–65.4 nA, post-edge worst-case 0.24 nA–32.3 nA,
  `VIN`→`VOUT` leakage 0.074 nA–75.8 nA, and `VOUT` 1.806–1.820 V two
  milliseconds after disable — the same orders-of-magnitude-inside-bound
  picture the quick subset showed, now confirmed everywhere the design
  actually reaches regulation. The three `sf_125c` corners **FAIL**: `EN`'s
  rising edge cannot bring the block into regulation there (`vout_pre_disable_v`
  ≈ 7–11 mV, not the ~1.8 V the other 42 corners settle to), so the static/
  post-edge Iq and leakage numbers at those three corners describe a block
  that was never on, not a real shutdown measurement — the same mechanism-1
  false-trip (#69) `startup/`'s full-matrix record hits at the identical
  three corners, and the flip side of `current-limit/`'s leg-3 finding
  above: `sf_125c` does not survive a ramped `EN` edge at all in this
  design's current state, `ff_125c` does — filed as #93.

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
bench**: as of #76 the enable-edge lesson applied only to leg 3 — the `tran`
that applies and holds the `Vout = 0` short. Legs 1 and 2 were `op`/`dc`
analyses; an enable ramp cannot help a DC solve reach a different branch than
it otherwise would (there is no "before" state for a ramp to start from), so
their `ff_125c_3.63v` collapse is the design defect (#69) the record honestly
reports, not a bench artifact that fix was ever going to touch.

**#177 then moved leg 1 across that line, and added the missing half of the
lesson.** Leg 1 is no longer an `op`: it is a `tran … uic` that reaches the
50 mA point through the same enable edge leg 3 uses, so the enable-edge
lesson now covers legs 1 *and* 3, and only leg 2 remains a DC analysis it
cannot reach. The missing half is that an enable edge is **not sufficient on
its own** — a non-`uic` `tran` performs an operating-point solve before its
first timestep and reads a dual-form source's `dc` keyword there, so with
`VEN = dc 'vsup' pwl(…)` both transient legs were still solving the
fully-enabled loop from nowhere. Measured per-leg at `tt_27c_3.30v`: legs 1
and 3 each tripped `Warning: Dynamic gmin stepping failed` without `uic` and
neither does with it, at bit-identical measured values (leg 1
`vout_50ma` = 1.79883 V, leg 3 `ish_avg` = −1.53348e−01 A both ways). Whether
this changes any corner's PASS/FAIL verdict is **not yet established**: the
45-corner re-run that would settle it has not been performed — see the
`current-limit/` record note above.

### Which record set is authoritative (issue #19)

There are now **two generations** of full 45-point records on disk, and only
the newer one characterizes the design as it stands:

| Generation | Record ids | Pinned schematic | Status |
|---|---|---|---|
| Pre-#36 | `…-879f035` (`load-transient`, `psrr-dc`, `dropout-vs-load`) | `879f035` — before #35 (thermal shutdown) and #36 (rail-to-rail EA output stage + sized compensation) | **Superseded.** Kept per the append-only rule; do not cite. |
| Current *as of #19* | `…-81dc232` (all four testbenches) | `81dc232` — `main` at the time plus the `M_ENP4`/`M_ENP5` fix below | **Authoritative for issue #19's acceptance criteria**, and superseded since — see "part 2" below. |

> **Superseded again by issue #69 (2026-08-25).** The `…-81dc232` set is no
> longer authoritative for the design as it stands: #69's thermal-shutdown
> re-sizing changed the shared DUT, and a `…-4cb27f8` generation replaced all
> four of these records plus the four other experiments'. The table below is
> retained because it is the record of #19's own deliverable. See "Which
> record set is authoritative, part 2 (issue #69)".

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

### The six degenerate `ff`/`sf` 125 °C corners — diagnosed, and fixed in #69

`ff_125c_*` and `sf_125c_*` (six of the 45 points) returned values that are not
physically meaningful — 8.4–22.3 V of "undershoot" on a 1.8 V output, 32.6 V of
"dropout" from a ≤3.63 V supply, `vout_at_max_vin_v` of −19 V / −29 V, `n/a`
loop-gain measurements, and the only six 1 kHz PSRR "passes" in the matrix.
That is one signature seen four ways: at those corners the solve did not land
on a valid regulating operating point, so the number the measurement expression
extracted described the solver's excursion, not the circuit's behaviour. They
are recorded as `FAIL`/`n/a` rather than dropped (per this directory's own
rule), and they are excluded from the "worst plausible corner" figures quoted
above.

**Issue #60 root-caused this to a nuisance trip of the thermal shutdown
(#29/DR-005) inside the rated `Tj ≤ 125 °C` range, and issue #69 fixed it**
(re-sized CTAT sense/reference pair — see `design/README.md`'s "Sizing the
trip: what is a knob and what is not"). Every experiment that instantiates
`design/ldo_3v3in_1v8out.sch` was re-run against the fixed schematic on
2026-08-25; the `…-4cb27f8` record generation below is the result, and **none
of the six corners produces an out-of-range value in any experiment any
more**. The `…-81dc232` / `…-703a889` records that show the signature stay on
disk per the append-only rule and point forward via the new records'
`Supersedes` field.

### Which record set is authoritative, part 2 (issue #69, 2026-08-25)

There is now a **third generation** of records on disk. For the eight
experiments #69 re-ran it is the authoritative one, and the only generation
whose netlist snapshots match the current `design/ldo_3v3in_1v8out.sch`:

| Generation | Record ids | Pinned schematic | Status |
|---|---|---|---|
| Pre-#36 | `…-879f035` | before #35/#36 | **Superseded** (do not cite) |
| Pre-#69 | `…-81dc232` (four PVT + MC), `…-703a889` (the three #65 benches) | `81dc232` / `703a889` — thermal shutdown as first sized in #29 | **Superseded.** Contains the six degenerate corners above. |
| Post-#90 merge (#95) | `…-933dfdd` (`thermal`, `line-regulation`, `load-regulation`, `iq`, `current-limit`, `startup`, `enable-shutdown`) | `933dfdd` — post-#69/#90, on `main` after the merge conflicts that left these seven `STALE` | **Authoritative for these seven.** Closes the "parallel landings" gap below — see "#95: closing the parallel-landings gap" further down. |
| Current | `…-4cb27f8` (the eight experiments #69 re-ran) | `4cb27f8` — #69's thermal-shutdown re-sizing | **Authoritative.** |

**"Third generation" is not the same thing as "every record on disk".** Six
records that landed on `main` while #69's branch was open are *not* part of
the `…-4cb27f8` generation, and each is stale in a different, disclosed way:

| Record | Landed by | Why it is not `…-4cb27f8` | Freshness now |
|---|---|---|---|
| `sim/thermal/20260825-054043-6fac47d` | #66/#80 | Bench did not exist when #69 was cut; measures the **pre-#69** trip points | `STALE` at merge time. **Superseded by `…-933dfdd` (#95)** — see below. |
| `sim/line-regulation/20260825-040532-6fac47d` | #64/#73 | Bench did not exist when #69 was cut | `STALE` at merge time. **Superseded by `…-933dfdd` (#95)** — see below. |
| `sim/load-regulation/20260825-040748-6fac47d` | #64/#73 | Bench did not exist when #69 was cut | `STALE` at merge time. **Superseded by `…-933dfdd` (#95)** — see below. |
| `sim/iq/20260825-040934-6fac47d` | #64/#73 | Bench did not exist when #69 was cut | `STALE` at merge time. **Superseded by `…-933dfdd` (#95)** — see below. |
| `sim/current-limit/20260825-070327-d0bb614` | #76/#86 | Superseded by `…-4cb27f8`, but #86 revised `tb_current_limit.sch` **after** #69's re-run | `…-4cb27f8` reported `STALE`; the chain is now superseded further by `…-933dfdd` (#95, full 45-point matrix, fresh against the current deck) — see below. |
| `sim/dropout-vs-load/20260825-055423-c000414` | #71/#83 | Superseded by `…-4cb27f8`, but #83 revised the `dropout_v` deck **after** #69's re-run | see the methodology caveat below — **not** re-run by #95 (no further deck change since; the freshness-check blind spot itself remains open). |
| `sim/current-limit/20260825-085216-64c17cb`, `sim/startup/20260825-073320-64c17cb`, `sim/enable-shutdown/20260825-073259-64c17cb` | #74/#94 | The full 45-point matrices for the three #65 benches, run against the **pre-#69** DUT | `STALE` at merge time, and they collided with #69's 3-point re-runs — see "#74 and #69 crossed" below. **All three re-run at full breadth by #95, closing the collision** — see "#95: closing the parallel-landings gap" below. |

Two of those need reading carefully, because the re-run and the parallel
landing crossed:

- **`current-limit`.** #76/#86 gave leg 3 a cold `EN` ramp and moved the
  fault past soft-start, changing `tb_current_limit.sch` itself. #69's
  `…-4cb27f8` re-run predates that change, so its netlist snapshot no longer
  matches the current testbench and the report marks the row `STALE` — the
  freshness check catching exactly what it exists to catch. Its **3/3 overall
  PASS** therefore stands only for the pre-#86 deck.
- **`dropout-vs-load`.** #71/#83 rewrote the `dropout_v` measurement in
  `experiment.json` (downward `VIN` sweep, `.meas ... fall=1` at the −2%
  departure point) but touched only *comments* in the testbench schematic.
  The netlist-freshness check compares schematic netlists, not decks, so it
  reports `…-4cb27f8` as `fresh` even though that record was measured with
  the **superseded pre-#71 fixed-endpoint method**. Both records read 0/45
  `FAIL`, so no verdict turns on it — but the 45-corner `dropout_v` *numbers*
  to cite are #83's `20260825-055423-c000414` (0.310–0.554 V at −40/27 °C),
  not `…-4cb27f8`'s. This is a freshness-check blind spot, not a defect in
  either record; it is called out here rather than left for a reader to trip
  over.

#### #74 and #69 crossed: breadth on the old DUT vs. freshness on the new one

Issue #74 ran the full 45-point matrix for the three #65 benches against
`64c17cb` — i.e. against the **pre-#69** thermal shutdown — at the same time
#69 was re-running the 3-point subset against the re-sized one. Neither set
dominates the other, and `measurements/build_characterization_report.py`
picks per bench by record id (which sorts by run timestamp), so the merged
report lands on a mix:

| Bench | #74's full matrix | #69's 3-point re-run | Report cites | Why |
|---|---|---|---|---|
| `current-limit` | `20260825-085216-64c17cb`, **39/45** | `20260825-082847-4cb27f8`, 3/3 | #74's — **FAIL, `STALE`** | #74's run is later (08:52 vs 08:28) |
| `startup` | `20260825-073320-64c17cb`, **42/45** | `20260825-082906-4cb27f8`, 3/3 | #69's — **PASS (PVT subset), fresh** | #69's run is later (08:29 vs 07:33) |
| `enable-shutdown` | `20260825-073259-64c17cb`, **42/45** | `20260825-082908-4cb27f8`, 3/3 | #69's — **PASS (PVT subset), fresh** | #69's run is later (08:29 vs 07:33) |

Two consequences worth stating plainly rather than leaving to be inferred:

- **`startup` and `enable-shutdown` lose matrix breadth in the report.**
  Their rows revert from a 45-point verdict to a 3-point `(PVT subset)` one,
  and the subset reason those records carry — "the full 45-point matrix …
  remains issue #74's unit of work" — is now out of date, since #74
  delivered it. The narrower row is nonetheless the *fresher* one: it is the
  only measurement of these two benches against the schematic actually in
  the tree.
- **The `sf_125c` failures #74 found are #69's mechanism 1, unretested.**
  #74's full matrices fail exactly at `sf_125c` (all three supplies, in all
  three benches) and attribute it to the same nuisance trip #69 fixes —
  which is the strongest single argument for the re-run these tables point
  at. #93 (why `sf` is more susceptible than `ff` during a ramped enable) is
  posed entirely on pre-#69 evidence and should be re-read after it.

Per-experiment before/after (old → new record id, and the verdict change):

| Experiment | Superseded | Current | Verdict |
|---|---|---|---|
| `dropout-vs-load` | `20260818-032811-81dc232` | `20260825-081240-4cb27f8` | 0/45 → 0/45 PASS |
| `load-transient` | `20260818-032755-81dc232` | `20260825-081255-4cb27f8` | 23/45 → **25/45** PASS |
| `psrr-dc` | `20260818-032803-81dc232` | `20260825-082845-4cb27f8` | 6/45 → **0/45** PASS (a correction, see below) |
| `loop-gain` | `20260818-032819-81dc232` | `20260825-081257-4cb27f8` | 3/45 → **7/45** PASS |
| `current-limit` | `20260825-045313-703a889` | `20260825-082847-4cb27f8` | 2/3 → **3/3, overall PASS** |
| `startup` | `20260825-044139-703a889` | `20260825-082906-4cb27f8` | 3/3 → 3/3 PASS |
| `enable-shutdown` | `20260825-044140-703a889` | `20260825-082908-4cb27f8` | 3/3 → 3/3 PASS |
| `mc-output-accuracy` | `20260818-032827-81dc232` | `20260825-083111-4cb27f8` | 181/200 → 177/200 samples PASS |

**`psrr-dc`'s 6/45 → 0/45 is the evidence trail getting more honest, not a
regression.** All six of its old "passes" were the falsely-tripped corners
— AC gain measured around a collapsed bias point, which this file and #60
both already flagged as not-real PSRR. With the trip gone, the 1 kHz column
collapses from 20.31–76.79 dB to **20.31–25.68 dB** against the 50 dB spec
bound: PSRR now demonstrably fails everywhere, which is what #60 inferred
and #69's re-run measures. The underlying PSRR shortfall is issue #70's, and
is untouched by #69.

Full before/after detail, including the two `load-transient` corners that
changed verdict for a mechanism-(4) reason rather than a transient one, is
in `design/README.md` → "What the #69 re-run changed".

#### #95: closing the parallel-landings gap (2026-08-25)

Issue #95 re-ran the seven benches the "parallel landings" table above left
`STALE` (or, for `startup`/`enable-shutdown`, breadth-losing) after PR #90
merged #69 into `main`. Each new record is pinned to `933dfdd` — the merge
commit's `design/ldo_3v3in_1v8out.sch` — and carries a `Supersedes` field
back to the record it replaces:

| Bench | Superseded | New (`933dfdd`) | Verdict |
|---|---|---|---|
| `thermal` | `20260825-054043-6fac47d` | `20260825-104426-933dfdd` | 5/15 FAIL → **12/15 FAIL** |
| `line-regulation` | `20260825-040532-6fac47d` | `20260825-104914-933dfdd` | 2/3 FAIL → **1/3 FAIL** |
| `load-regulation` | `20260825-040748-6fac47d` | `20260825-105113-933dfdd` | 2/3 FAIL → **3/3 PASS** |
| `iq` | `20260825-040934-6fac47d` | `20260825-105157-933dfdd` | 3/3 PASS → **3/3 PASS** |
| `current-limit` | `20260825-085216-64c17cb` (#74's full matrix) | `20260825-105322-933dfdd` | 39/45 FAIL → **45/45 PASS** |
| `startup` | `20260825-082906-4cb27f8` (#69's 3-point re-run — the record the merged report was actually citing) | `20260825-110456-933dfdd` | 3/3 PASS (subset) → **45/45 PASS** |
| `enable-shutdown` | `20260825-082908-4cb27f8` (#69's 3-point re-run — the record the merged report was actually citing) | `20260825-111526-933dfdd` | 3/3 PASS (subset) → **45/45 PASS** |

`startup` and `enable-shutdown` point their `Supersedes` field at the
`…-4cb27f8` record rather than #74's `…-64c17cb` one, because `…-4cb27f8` is
what `measurements/characterization.md` was actually citing at merge time (a
straight replacement of the currently-cited evidence); the collision this
section documents above is resolved regardless, since the new record is both
fresher and carries #74's full 45-point breadth.

**This closes the "#74 and #69 crossed" collision above and confirms #74's
diagnosis.** `current-limit`, `startup` and `enable-shutdown` all read a
clean 45/45 `PASS` against the post-#69 schematic — the `sf_125c`/`ff_125c`
corners #74's pre-#69 matrices failed at (attributed to mechanism 1) now
pass, so #93's question (posed on that pre-#69 evidence) is answered: those
corners were mechanism 1, and #69 fixed them.

**`thermal` turns #69's `.op`-screened trip estimate into a measured
15-corner `sim/` record, and corroborates rather than changes #91's manual
re-screen** (`design/README.md` → "#91"): `trip_temp_c`/`reset_temp_c`/
`hysteresis_c` at all 15 corners match #91's table to three significant
figures, so the same three corners (`tt_27c_3.63v`, `ss_27c_2.97v`,
`ff_27c_3.63v`) still read a small negative hysteresis post-resize.
`20260825-054043-6fac47d` is no longer the authoritative `sim/thermal`
record; `20260825-104426-933dfdd` is.

**`line-regulation`'s failing corner moved, not just its count — flagged
here rather than silently absorbed into a lower FAIL count.** Pre-#69, only
`ff_125c_3.63v` failed (~1005–1010 mV/V, the mechanism-1 signature); post-#69
that corner now passes cleanly (~0.4–0.5 mV/V), but `tt_27c_3.30v` newly
fails both legs (~1739/1317 mV/V) and `ss_-40c_2.97v` newly fails its 50 mA
leg (~2477 mV/V). The magnitude matches this schematic's documented
DC-solution-multiplicity signature on sequential `alter`-based `.op` points
(the "six degenerate corners" above), now apparently landing on a different
corner subset post-resize — the most likely explanation, not a confirmed
root cause, since diagnosing it was outside #95's re-run scope. Worth a
follow-up issue if pursued further. `load-regulation` and `iq` show no
comparable new failure; both improve or hold cleanly at the same three
points.

`measurements/characterization.md` is regenerated against these seven new
records; `python3 measurements/build_characterization_report.py --check`
passes.

#### #104: full 45-point matrix for `line-regulation`/`load-regulation`/`iq`

Issue #104 ran the full 45-point PVT matrix that `line-regulation`,
`load-regulation` and `iq`'s manifests have always declared, closing the one
full-matrix gap these three benches still shared with the #65 protection
benches after #95. The schematic has not changed since `933dfdd` (the #90
merge commit those records are pinned to, `b53a8e7`), so each new record
supersedes #95's 3-point re-run directly and the fresh netlist snapshots
match the superseded records' byte-for-byte:

| Bench | Superseded | New (full matrix) | Verdict |
|---|---|---|---|
| `line-regulation` | `20260825-104914-933dfdd` (3-point subset) | `20260910-030557-6c0436d` | 1/3 FAIL (subset) → **18/45 PASS** |
| `load-regulation` | `20260825-105113-933dfdd` (3-point subset) | `20260910-032854-6c0436d` | 3/3 PASS (subset) → **34/45 PASS** |
| `iq` | `20260825-105157-933dfdd` (3-point subset) | `20260910-034648-6c0436d` | 3/3 PASS (subset) → **36/45 PASS** |

`load-regulation` and `iq` both lose their subset-era overall `PASS`
verdict: the narrow 3-point subset happened to sample only corners where the
DUT regulates, and the wider matrix finds 11 and 9 further corners
respectively where it does not — see each bench's own bullet below for the
failing-corner lists and, for `line-regulation`, the DC-solution-
multiplicity-vs-physical-reading split its 27 failing corners break into.

## Line regulation, load regulation and Iq (issue #64)

Three more testbenches against the same DUT (`design/ldo_3v3in_1v8out.sch`),
covering three spec rows `measurements/characterization.md` reported N/A
until this issue: **Line regulation** (<5 mV/V over 2.97–3.63 V, at 1 mA and
50 mA), **Load regulation (0–50 mA)** (<1%/18 mV) and **Iq (excl. load
current)** (<30 µA at no load and full load). The first two rows are ratified
(issue #1 / DR-006); the Iq row is the one DR-006 left open and is set by
`DR-009`, still `proposed` — `sim/iq/experiment.json`'s `claim` says so, and
cites DR-009's number rather than a ratified one. Same VIN/EN/VREF stimulus
convention and output network (1 µF `C_OUT`/10 mΩ `R_ESR`) as the four
testbenches above.

**All three use discrete `.op` points at each row's own named test
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
`.op` solves at each row's own endpoints — `alter`-ing VIN and/or the
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
  above (thermal-shutdown false-trip, #69), not a new finding. #95 re-ran the
  same subset against #69/#90's re-sized DUT (`20260825-104914-933dfdd`,
  supersedes the record above): **1/3 PASS** — `tt_27c_3.30v`
  (1739/1317 mV/V) and `ss_-40c_2.97v`'s 50 mA leg (2477 mV/V) newly fail,
  `ff_125c_3.63v` now passes cleanly (0.500/0.422 mV/V) — see "`line-regulation`'s
  failing corner moved" above. **Full 45-point PVT record**
  (`20260910-030557-6c0436d`, issue #104, supersedes `20260825-104914-933dfdd`):
  **18/45 PASS**. Of the 27 failing corners, 25 show the same
  DC-solution-multiplicity signature described above — values ≥100 mV/V, up
  to 26186 mV/V at `fs_125c_2.97v`, three to four orders of magnitude over
  the 5 mV/V bound — while 2 are modest, physically plausible overshoots
  close to the bound rather than solver excursions: `tt_125c_2.97v`
  (32.5/50.5 mV/V) and `sf_125c_2.97v` (7.1/10.9 mV/V). The two corners the
  #95 subset flagged as "newly failing" both land in the multiplicity
  bucket here (`tt_27c_3.30v` 1739/1317 mV/V, `ss_-40c_2.97v`
  0.217/2477 mV/V), and `ff_125c_3.63v` again passes cleanly
  (0.500/0.422 mV/V), confirming rather than changing the subset's own
  result. As the #95 section above already notes, diagnosing why this
  signature lands on a different, wider corner set than the pre-#69 six
  degenerate `ff`/`sf`-125 °C corners is explicitly out of this issue's
  scope — recorded here as an observation, not root-caused.
  **Current record** (`20260925-114251-1f54ca6`, issue #118, supersedes
  `20260910-030557-6c0436d`, first run against the post-#116 5000 µm pass
  device): **24/45 PASS**, up from 18/45. #118 also root-caused the signature
  the paragraph above declined to: **this bench's `supply_v` corner axis is a
  negative control.** The testbench wires VIN to a fixed literal
  (`VVIN VIN 0 3.3`) and only EN to `'vsup'`, and the deck `alter`s VIN to
  2.97 V/3.63 V at all four measured points — so the corner's own supply
  cannot reach the measurement, and the three supply points inside one
  (process, temperature) group must return the same number. **22 of 30
  (group × measurement) cells vary by more than 2× across it, 21 of them by
  more than 10×**, while the one fully self-consistent group (`ff_-40c`)
  agrees to four significant figures. On the regulating branch the row is
  **0.017–1.62 mV/V** at 1 mA and **0.093–3.14 mV/V** at 50 mA against the
  5 mV/V bound; the five intermediate readings (6.7–85.2 mV/V) all sit at
  `*_125c_2.97v`. Read this bench's per-corner verdicts as branch-selection
  outcomes, not as supply-rejection measurements — see `design/README.md`
  → "#118: the three DC-accuracy rows do share one mechanism…".
  **Current record** (`20260926-001833-228fbc7`, issue #172, supersedes
  `20260925-114251-1f54ca6`, first run under the #171 initial-condition
  contract): **40/45 PASS**, up from 24/45, with **zero solver diagnostics on
  all 45 corners** (the superseded record carried one on all 45). Sixteen
  corners changed verdict, all FAIL → PASS, and every one of them read a gross
  branch-selection number in the superseded record (1042–2785 mV/V) that now
  reads 0.109–0.705 mV/V. The five survivors are all `*_125c_2.97v`, i.e. the
  same bucket #118 called "intermediate". See "…re-run under the #171 contract
  (issue #172)" below.
- **`load-regulation/`** — `I_LOAD` ∈ {0 mA, 50 mA} at each corner's own VIN
  (`'vsup'`), two `.op` solves; `load_reg_v` = `abs(vout@50mA - vout@0mA)`.
  First record (`--quick`, `20260825-040748-6fac47d`): **PASS** at
  `tt_27c_3.30v` (4.2 mV / 0.23%) and `ss_-40c_2.97v` (3.3 mV / 0.18%),
  **FAIL** at `ff_125c_3.63v` (19.3 V) — overall `FAIL`, same degenerate
  corner. #95 re-ran the same subset against the re-sized DUT
  (`20260825-105113-933dfdd`, supersedes the record above): **3/3 PASS** —
  `ff_125c_3.63v` now regulates cleanly too. **Full 45-point PVT record**
  (`20260910-032854-6c0436d`, issue #104, supersedes `20260825-105113-933dfdd`):
  **34/45 PASS**. The 11 failing corners (`tt_27c_2.97v`, `tt_125c_3.63v`,
  `ss_-40c_3.30v`, `ss_27c_2.97v`, `ss_27c_3.30v`, `ff_-40c_2.97v`,
  `sf_-40c_3.63v`, `sf_27c_3.30v`, `sf_27c_3.63v`, `fs_-40c_3.63v`,
  `fs_27c_2.97v`) read `load_reg_v` of 0.31–1.62 V (17–90%) against the
  18 mV/1% bound — an order of magnitude smaller than line-regulation's
  multiplicity signature but still far outside plausible load-regulation
  behaviour, and none of them are the pre-#69 `ff`/`sf`-125 °C corners
  (those all pass here). This reads as the same family of non-regulating
  operating points the DC-solution-multiplicity note documents, but that is
  an observation, not a root cause — diagnosing it is out of this issue's
  scope.
  **Current record** (`20260925-111601-7701e7e`, issue #118, supersedes
  `20260910-032854-6c0436d`, first run against the post-#116 5000 µm pass
  device): **37/45 PASS**, up from 34/45 — and the distribution now separates
  into three groups, not two. **37 corners read 2.62–14.50 mV** against the
  18 mV bound; **7 read 881 mV–1.62 V**, with a **44× empty band** between
  19.93 mV and 881 mV that no continuum mechanism produces; and **one corner,
  `fs_125c_3.63v`, reads 19.93 mV (1.107 %)** — a marginal 11 % overshoot
  whose own group is monotone in VIN (10.99 / 14.50 / 19.93 mV). That single
  corner is the only genuine load-regulation shortfall in the matrix. Of the
  five (process, temperature) groups containing a gross failure, **four are
  non-monotonic in VIN** (a higher-headroom supply fails while a lower one
  passes), which a loop-gain-bound DC error cannot be. #118 attributes the
  seven gross failures to the non-regulating-branch family rather than to
  loop gain — see `design/README.md` → "#118: the three DC-accuracy rows do
  share one mechanism…".
  **Current record** (`20260926-010432-228fbc7`, issue #172, supersedes
  `20260925-111601-7701e7e`, first run under the #171 initial-condition
  contract): **44/45 PASS**, up from 37/45, with **zero solver diagnostics on
  all 45 corners** (the superseded record carried one on 44 of 45). Exactly
  the seven gross-failure corners changed verdict, all FAIL → PASS, and the
  44× empty band is gone: the 44 passing corners are a continuum from
  **2.62 mV to 14.50 mV** against the 18 mV bound. **The single survivor is
  `fs_125c_3.63v` at 19.94 mV (1.108 %)** — the same corner, to within
  0.01 mV of the same number, #118 had already isolated as "the only genuine
  DC-accuracy gap the three rows contain". #118's decomposition is confirmed
  here by an instrument that shares none of its seeding. See "…re-run under
  the #171 contract (issue #172)" below.
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
  caution the PSRR "passes" above already need. #95 re-ran the same subset
  against the re-sized DUT (`20260825-105157-933dfdd`, supersedes the record
  above): **3/3 PASS** — same three corners, all now genuinely regulating
  (`vout_no_load_v`/`vout_full_load_v` both ≈1.80 V at all three). **Full
  45-point PVT record** (`20260910-034648-6c0436d`, issue #104, supersedes
  `20260825-105157-933dfdd`): **36/45 PASS**. The 9 failing corners
  (`tt_27c_2.97v`, `tt_125c_3.63v`, `ss_27c_2.97v`, `ss_27c_3.30v`,
  `sf_-40c_3.63v`, `sf_27c_3.30v`, `sf_27c_3.63v`, `fs_-40c_3.63v`,
  `fs_27c_2.97v`) all fail on the full-load leg, with `vout_full_load_v`
  reading 2.67–3.43 V instead of ≈1.80 V (one, `sf_27c_3.30v`, also fails its
  no-load leg at `vout_no_load_v` = 3.32 V) — the same "operating point
  isn't really regulating" signature this testbench's own unbounded
  `vout_*` sanity measurements exist to catch, now visible at 9 of 45 points
  instead of the one degenerate corner the quick subset ever reached.
  `iq_full_load_ua` at those 9 corners reads 3454–3582 µA against the 30 µA
  bound — obviously non-physical, not a genuine Iq measurement. None of the
  9 are the pre-#69 `ff`/`sf`-125 °C corners (all pass here); root-causing
  which corners this lands on is out of this issue's scope, same as
  line/load regulation above. **The 36/45 tally is not 36 genuine passes**:
  two corners marked PASS — `ss_-40c_3.30v` (`vout_no_load_v` = 3.31 V,
  `iq_no_load_ua` = −3348.6 µA) and `ff_-40c_2.97v` (`vout_full_load_v` =
  2.71 V, `iq_full_load_ua` = −3357.9 µA) — show the same non-regulating
  collapse signature as the 9 above with the sign flipped, and pass only
  because this bench's `iq_*_ua` measurements are bounded one-sided
  (`max: 30`, `min: null`) rather than `abs()`-wrapped the way
  line-regulation's and load-regulation's are, so a large negative excursion
  slips under the ceiling instead of tripping it. Both are independently
  confirmed genuinely non-regulating by this same issue's `load-regulation`
  record, where they are 2 of its 11 real FAILs (`load_reg_v` = 1.51 V and
  0.91 V) — so at most 34 of 45 corners here have a plausible regulating
  operating point, matching load-regulation's own 34/45. (A third corner,
  `sf_27c_3.30v`, reads the same negative no-load figure, −3350.0 µA, but is
  already counted among the 9 FAILs via its full-load leg.) The record and
  its raw data are correct as recorded and are left as-run — re-bounding the
  Iq measurement, re-classifying the tally, and root-causing the collapse are
  all out of this issue's scope; this note exists so the headline count is
  not read as 36 clean corners.

**Quick-subset first, by design, matching issue #18's own original
precedent** for newly-shipped testbenches (`load-transient`/`psrr-dc`/
`dropout-vs-load` also shipped `--quick`-only before #19's later full
45-point pass). Issue #104 then ran the full 45-point matrix each manifest
declares for all three, mirroring issue #74's extension of the #65
protection benches — see each bullet's "Full 45-point PVT record" above for
the per-bench tallies.

### Line regulation and load regulation re-run under the #171 contract (issue #172)

Both regulation benches' `alter`+`op` chains were the worst case of the
unconstrained-`.op` defect `#164` characterized: no transient, no `uic`, no
`.ic`, so **every** measured point was read straight off ngspice's own
from-nowhere Newton solve. `#172` converted both to the
"Initial-condition contract" above and re-ran both full 45-corner matrices
under `#171`'s new solver-diagnostic FAIL gate.

**Which contract shape, and why.** Both benches now use the contract's
**`uic` + EN edge** shape (`tran 10u 200m uic`, each bench's `VEN` changed
from a constant `'vsup'` to `dc 0 pwl(0 0 100u 0 101u 'vsup' 10 'vsup')`,
`v(vout)` averaged over the settled 199–200 ms tail), one transient per
measured point, exactly as PR #170 landed for `sim/mc-output-accuracy`. The
`alter` chain itself is unchanged — the points, the bounds and the
`abs(1000*Δv/0.66)` / `abs(Δv)` expressions are the same as before; only the
`opN.` plot prefixes become `tranN.`. The contract's *other* shape (an
`.ic`-seeded `.op`) was tried first and **cannot be expressed in ngspice for
this deck**, measured rather than assumed:

- `.ic` is applied only to the operating-point solve that *precedes* a
  non-`uic` transient (ngspice's MODETRANOP solve). A bare `op` command
  ignores it entirely.
- `.nodeset` *is* honoured by a bare `op`, but only as a first-iterations
  guess that is then released. With `sim/ic-screen-125c-b`'s full 11-node
  intended-branch node set applied as a `.nodeset` to the old `.op` chains,
  3 of 5 corners probed (`tt_27c_3.30v`, `fs_125c_3.63v`, `ss_-40c_2.97v`)
  still printed `singular matrix` *and* `Dynamic gmin stepping failed` — the
  exact markers `#171`'s gate fails on.

So a settled transient per point is the only shape that satisfies the
contract here. An `.ic`-seeded **non-`uic`** transient (the third possibility)
does work and was run as a cross-check — see "not steering the answer" below.

**Why the transient is 200 ms, and why that is `load-regulation`'s number
rather than a round one.** At the ratified load-regulation row's **0 mA**
endpoint the feedback divider is the only discharge path out of the 1 µF
`C_OUT`, so any start state above the no-load operating point bleeds down
through a high-impedance path. **Corrected by issue #184** (surfaced during
review of PR #182; the original numbers below do not reproduce on the deck
that shipped): the `uic` cold-start deck that actually ships here measures,
at `tt/27C/3.30V`, `v(vout)` = **1.81337 V** averaged over 0.8–1 ms, already
settled to **1.80239 V** by ~50 ms (flat to six digits from there through
200/300/400 ms) — an **11.0 mV** 1 ms-window artifact against the 18 mV
bound, i.e. a PASS, not a FAIL. The **1.85985 V / 1.83245 V / 1.80332 V**
trajectory and the "57 mV, 3× the bound, would fail all 45 corners"
conclusion this section originally stated were measured on the
`.ic`/`op`-seeded, non-`uic` cross-check variant tried first (see the table
below), not on this deck. 200 ms is nonetheless still the right window: that
seeded cross-check variant genuinely needs the long window to settle, and
every corner probed keeps margin under 200 ms even at the shipped deck's own
largest observed 1 ms-window artifact (1.75 mV at `fs_125c_3.63v`). The
50 mA endpoint, by contrast, settles inside 1 ms at every corner probed.
`line-regulation`'s four points all carry a real load current (1 mA or
50 mA) and likewise settle inside 1 ms — its 0.8–1 ms and 199–200 ms tail
averages agree to six digits at `tt/27C/3.30V` — but it carries the same
200 ms window anyway, so both benches share one convention.

**Errata (issue #184).** The `20260926-010432-228fbc7` (`load-regulation`)
and `20260926-001833-228fbc7` (`line-regulation`) records below, and this
section's prose as originally landed by #172, carried the uncorrected
1.85985 V / 1.83245 V / 1.80332 V / "57 mV, 3× the bound" trajectory above,
plus a "≤0.1 mV" figure for the three hottest corners' 99–100 ms vs.
199–200 ms tail-average agreement that is actually **0.13 mV** (worst case,
`fs_125c_3.63v`: 1.81869 V vs. 1.81856 V). Both records are append-only and
are not re-cut for a prose correction — no measurement, corner verdict, or
row verdict in either record is affected; see issue #184 for the full
before/after and how the corrected numbers were reproduced.

**Measured evidence the start state is not steering the answer** (the
property the contract is actually after — two independent start states
converging on one tail):

| Probe | `.ic`-seeded, non-`uic` | `uic` + EN edge | Agreement |
|---|---|---|---|
| `line-regulation`, `tt_27c_3.30v`, all four points | 1.80050 / 1.80071 / 1.79872 / 1.79892 V | identical to six digits | exact |
| `line-regulation`, `tt_125c_2.97v` | 31.2 / 43.9 mV/V | 31.2 / 43.9 mV/V | exact |
| `load-regulation` 0 mA, `tt_27c_3.30V` | 1.80239 V (400 ms) | 1.80239 V (200 ms) | exact |
| `load-regulation` 0 mA, `ff_125c_3.63V` | 1.81042 V (400 ms) | 1.81042 V (200 ms) | exact |
| `load-regulation` 0 mA, `fs_125c_3.63V` | 1.81860 V (400 ms) | 1.81856 V (200 ms) | 0.04 mV |

**Result — both matrices, re-run and re-graded under `#171`'s gate.**

| Bench | Superseded record | Corners with a solver diagnostic | New record | Corners with a solver diagnostic | PASS |
|---|---|---|---|---|---|
| `line-regulation` | `20260925-114251-1f54ca6` | 45 / 45 | `20260926-001833-228fbc7` | **0 / 45** | 24/45 → **40/45** |
| `load-regulation` | `20260925-111601-7701e7e` | 44 / 45 | `20260926-010432-228fbc7` | **0 / 45** | 37/45 → **44/45** |

Zero corners in either matrix trip the new gate. Both rows' **overall verdict
is still FAIL** against the ratified spec row, so
`measurements/characterization.md`'s row-level verdicts do not move (only the
cited record ids and the per-row corner tallies) — the conversion removed
non-circuit artifacts, it did not make either row pass.

**Per-corner verdict changes — this is `#118`'s open question, answered.**
`#118` concluded both matrices' corner verdicts were branch-selection
outcomes rather than regulation quality, and left open whether excluding
those branches would change the verdicts. It does, and in exactly the
direction `#118` predicted:

- **`line-regulation`: 16 corners changed, all FAIL → PASS.** Every one of
  them read a gross branch-selection number in the superseded record
  (1042–2785 mV/V) and now reads **0.109–0.705 mV/V** against the 5 mV/V
  bound. Nothing regressed. The 40 passing corners span 0.017–1.62 mV/V
  at 1 mA and 0.092–3.14 mV/V at 50 mA.
- **`line-regulation`'s five survivors are all `*_125c_2.97v`** — the same
  five cells `#118` had already separated out as the "intermediate readings"
  bucket (6.7–85.2 mV/V), and they reproduce: 6.7 / 13.1 / 31.2 / 85.2 mV/V
  at 1 mA for `sf` / `ss` / `tt` / `ff`, plus `fs_125c_2.97v`. Their
  mechanism is visible in the logs: at 125 °C the VIN = 2.97 V point
  regulates (1.8008 V) while the VIN = 3.63 V point droops (1.780 V at `tt`,
  1.745 V at `ff`) or, at `fs_125c_2.97v`, diverges outright to a
  **negative** `v(vout)` (−6.71 V at 1 mA, −14.06 V at 50 mA). Note what
  that `fs` corner means for the gate: a transient that diverges to a
  non-physical state is simulated without any solver complaint, so `#171`'s
  diagnostic gate does not see it — the **bounds** catch it (24026 mV/V vs
  5 mV/V). A solver-diagnostic gate is a floor, not a regulation check;
  `#118`/`#133`'s "was the DUT regulating?" gate is still unbuilt and still
  the right follow-up. This bench also still wires `EN` to the corner's
  `'vsup'` while `alter`-ing `VIN` independently (the negative-control
  wiring `#118` documented), so all five survivors are measured with `EN`
  660 mV *below* `VIN`; read them as a real, reproducible DUT behaviour
  under that stimulus, not as a clean supply-rejection number.
- **`load-regulation`: exactly the 7 gross-failure corners changed, all
  FAIL → PASS**, and `#118`'s "44× empty band between 19.93 mV and 881 mV
  that no continuum mechanism produces" is gone — the 44 passing corners are
  now a single continuum from **2.62 mV to 14.50 mV**.
- **`load-regulation`'s one survivor is `fs_125c_3.63v` at 19.94 mV
  (1.108 %)** against the 18 mV bound. `#118` had called that exact corner
  "the only genuine DC-accuracy gap the three rows contain" at 19.93 mV — an
  instrument sharing *none* of the superseded record's seeding lands within
  **0.01 mV** of it. That is the real remaining spec gap for this row, and
  it is a design question (`#118`'s own follow-up), not a harness one.

**What did not change, deliberately:** no bound in `spec/target-spec.md`, no
measurement expression, no `design/ldo_3v3in_1v8out.sch`, and no superseded
record file. `sim/iq`'s conversion is `#173`; the remaining benches' audit is
`#174` (verdict table in the contract section above).

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
