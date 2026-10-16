# signoff/ — this block's T1 state, graded rather than hand-read

`signoff/records/t1-tier-report.json` is **this block's verdict of record**
against the klayout-tools design-evidence ladder
([`docs/design-evidence-tiers.md`](https://github.com/2AMLogic/klayout-tools/blob/main/docs/design-evidence-tiers.md)).
It is not prose about where the block stands; it is the output of

```bash
klt signoff --manifest signoff/block-manifest.json --format json
```

re-run by CI on every push and pull request, so it cannot quietly go stale the
way a hand-maintained checkbox list does. Issue #114 — this repo's gap-to-T1
tracker — cites it as the item-level verdict and no longer keeps a parallel
checklist of its own.

**Today: `tier: null`, T1 5/11 items met** (items 3, 4, 6, 8 and 11). That is
the honest state of the block, not a placeholder. Read the per-item notes below
before reading anything into either the five `met` rows or the six `unmet`
ones — several of the `unmet` rows cover artifacts that *do* exist here, and
none of the five `met` rows means what it might look like it means.

## What is here

```
signoff/
  block-manifest.json                     the manifest: block, kind, per-item evidence
  artifact-pins.json                      what each citation is really about, by sha256
  evidence/characterization.generic.json  item 8's generic evidence envelope
  records/t1-tier-report.json             the verdict of record (generated)
  check.sh                                re-grade + freshness gate (CI runs this)
  verify-pins.py                          check.sh stage 1: re-hash every pinned artifact
  tests/test_verify_pins.py               mutation coverage for that stage (runs in check:ci)
```

- `block` is `"sky130-ldo"`. It is required: it is how this block's row is
  identified in the fleet roll-up (`klt signoff --fleet`, 2AMLogic/2am#956),
  which consumes exactly this manifest.
- `kind` is `"analog"` — confirmed against the block, not taken on faith. The
  whole design is one hand-captured xschem schematic
  (`design/ldo_3v3in_1v8out.sch`) plus the netlist derived from it; there is no
  RTL anywhere in the repo, no synthesis step, no place-and-route flow (the
  layout is generated device-by-device by `layout/bin/gen-ldo-blocks.py` from
  that same netlist), and no digital partition to declare a boundary for. The
  thermal-shutdown and enable logic are drawn as ordinary MOS devices in the
  same schematic, not as standard cells. So the **Analog** column of items 1,
  2, 5, 7 and 11 applies, and `mixed-signal`'s partition-boundary declaration
  does not arise.

## Running it

```bash
bash signoff/check.sh          # verify (what CI runs)
bash signoff/check.sh --write  # regenerate the verdict of record
```

`check.sh` pins the klayout-tools release it grades against
(`klayout-tools==0.6.0`) — see its header for why that pin is load-bearing:
T1 item 11 landed on 2026-09-17 (klayout-tools#2025), *after* the 0.5.0
release, so grading this block on 0.5.0 renders a ten-item checklist with no
item-11 row at all. That pin is deliberately independent of
`layout/requirements.txt`'s `klt` pin, which fixes the toolchain that
*produced* this repo's DRC/LVS/PEX evidence (klt 0.2.0) rather than the grader
that *reads* it.

It fails on three separable conditions, so a red build says which one:

1. **A pinned `content_hash` no longer matches the artifact it covers.** `klt
   signoff` compares a manifest's pin against the *cited envelope's own*
   `provenance.input.content_hash`; it never opens the underlying artifact, and
   says so on every pinned citation it prints (`input: not re-hashed …`). Two
   hand-written files agreeing with each other proves nothing by itself, so
   `signoff/artifact-pins.json` records the sha256 of the artifact behind every
   citation and `check.sh` re-hashes each one on disk. Regenerate
   `measurements/characterization.md`, or recompose the layout GDS, without
   re-pinning, and this fails — which is the point: a citation that cannot rot
   is a citation that proves nothing.

   Both directions of that cross-check — pin → manifest and manifest → pin —
   are correlated **by the file each side names** (a manifest citation's
   `file` against a pin's `cited_envelope`), not by whether the hash turns up
   anywhere under the same item (issue #222). This matters for item 11, whose
   compound citation has two halves with *legitimately identical*
   `content_hash` values because both read the same GDS: pooling the item's
   hashes let either half's pin satisfy the other half's check, so deleting
   one of the two pins outright still passed. Nothing was actually unchecked
   at the time — item 4's own pin independently covers the same LVS envelope
   — but the check now stands on its own. The stage lives in
   `verify-pins.py`, and `tests/test_verify_pins.py` performs that exact
   deletion and asserts it fails; because that stage needs only `python3`
   (no `klt`, no PDK, no network), its coverage runs in `npm run check:ci` on
   every push rather than only in the `klt`-gated job below.
2. **`klt signoff --manifest` could not run.** Exit 0 (T1 reached) and exit 3
   (ran fine, not yet T1) are both clean runs; 1 and 2 mean a broken manifest
   or a tier doc this `klt` cannot parse.
3. **The committed record no longer matches a fresh run.** Either this block's
   evidence moved or the checklist did. Both are real news; neither should be
   discoverable only by someone re-reading prose.

## Why each item reads the way it does

The grader's verdict is in `records/t1-tier-report.json`. This section is the
part the grader structurally *cannot* check — what was cited, what was
deliberately not cited, and the disclosures `design-evidence-tiers.md` requires
of the claimant rather than of the tool.

| # | Status | Reading |
|---|---|---|
| 1 | `unmet` / `no_evidence` | The artifacts exist — `design/ldo_3v3in_1v8out.sch` plus the headless xschem netlist every downstream flow re-derives from it. Uncited on purpose, see "Items 1, 2, 9 and 10" below. |
| 2 | `unmet` / `no_evidence` | The artifact exists — `layout/ldo-core/reports/20260825-123551-3b4e121/ldo_core.gds`, reproducibly generated by `layout/bin/gen-ldo-blocks.py` + `run-ldo-layout-flow.sh` from the same netlist, with the floorplan recorded in `layout/ldo-core/floorplan.md`. Uncited on purpose, same reason. |
| 3 | **`met`** | `klt drc` on that GDS, `status: clean`, `violation_count: 0`, pinned to the GDS's own sha256. **Read the coverage disclosure below before treating this as "DRC clean".** |
| 4 | **`met`** | `klt lvs`, `status: match`, layout vs. the schematic-derived reference netlist. **Three disclosed warnings below.** Re-pointed by issue #127 at a klt 0.6.0 re-run whose `provenance.input.content_hash` is non-null, so the manifest now pins this citation directly instead of relying only on `signoff/artifact-pins.json`. |
| 5 | `unmet` / `no_evidence` | The largest real gap, and not a presentation choice. `spec/target-spec.md` *is* ratified (issue #1, DR-006) and a full 45-point PVT campaign exists under `sim/*/`— but it reports **FAIL on 7 of the 13 graded rows** (the 13th, `Area`, gained its first graded verdict -- FAIL, 0.4468 mm² against the ratified < 0.1 mm² -- with issue #236 (re-measured by issue #318 on the current routed core: 0.4508 mm², still FAIL, capacitors not drawn), which moved no other row; before that it was 6 of 12 and `Area` was N/A; and 9 before issue #164 fixed the `mc-output-accuracy` bench's initial-condition contract, which moved `Output` to PASS, 8 before issue #189 corrected one value's supply classification in the `thermal` bench's `.nodeset` seed, which moved `Thermal` to PASS, and 7 before issue #196 / PR #205 fixed the `line-regulation` bench's EN convention, which moved `Line regulation` to PASS on record `20260926-200304-35b7392` — none of the three touched the DUT (`design/ldo_3v3in_1v8out.sch` is unchanged) or any ratified bound; see `design/README.md` → "#164", `sim/README.md` → "#189", and `sim/README.md` → "#196"), and the records are this repo's own Markdown/JSON format rather than `klt sim` envelopes, so there is nothing here that could render `met` even if the rows passed. Tracked as issues #114–#121. |
| 6 | **`met`** | Cites a real `klt yield` report (`sim/mc-output-accuracy/klt-responses/20260927-093538-227be3e.yield.json`) over the n=200 Monte Carlo campaign: empirical yield **at least 98.1725 % at 95 % confidence** (100 % of 200 samples inside the ratified ±2 % Output window, so the interval is bounded only from below), Cpk 1.34664, sigma-to-spec 4.04σ, sample size `sufficient`, and a deterministic **negative control graded `detected`** — a seeded known-bad variant (feedback divider mis-ratioed +10 %) whose 0/40 in-window draws the same statistics reject with non-overlapping intervals. Issue #203 minted the report (the evidence *kind* the checklist names, which this repo had none of until then); issue #211 added the negative control the item's text also asks for. **The payload status is `reported`, not `pass` — read "Item 6 is `met` — what it says, and the one thing it does not" below before reading anything into this row.** |
| 7 | `unmet` / `check_failed` | Cites the real `klt pex` run (`sim/pex-post-layout/klt-responses/20260825-125102-3b4e121.pex.json`), pinned to the same layout GDS items 3 and 4 were run on: `status: error`, **135 of 135 delta rows errored, 0 passed**. Item 7 accepts no other evidence kind, so nothing weaker could stand in. A newer `klt pex` record now exists that does *not* error — **and is deliberately still not cited**; see "Item 7 has a passing record that this manifest declines to cite" below. Tracked as issues #122 and #142. |
| 8 | **`met`** | Cites `evidence/characterization.generic.json`, a generic envelope wrapping `measurements/characterization.md`. **This says the rollup exists and is current — not that its rows pass.** See below. |
| 9 | `unmet` / `no_evidence` | Every claimed measurement's testbench *is* committed (`sim/*/testbench/`), with a documented cold-start invocation (`sim/README.md`, `docs/environment-setup.md`) and a pinned PDK revision (`sim/pdk.json`). Uncited on purpose, see below. |
| 10 | `unmet` / `no_evidence` | README with the spec table and reproduction instructions, an Apache-2.0 licence, and CI that keeps the harness and evidence formats valid, all exist. Uncited on purpose, see below. |
| 11 | **`met`** | Power delivery (structural). A compound citation, as `klt signoff` requires for this item. The first part is the `klt erc` supply-spec run `layout/ldo-core/reports/20260930-193715-dc2823f/erc_supply.json`, on the layout record `LATEST` names: both supplies are one island each, both ties are checked, and four falsification controls fired. The second part is item 4's own LVS report, on the byte-identical GDS. **Read "Item 11 is `met` — what it says, and what it does not" below; one of its two ties rests on an asserted substrate region, and the antenna half is `clean_partial`.** Issue #112. |

### Item 3 is `met`, and the coverage its "clean" was measured inside

`design-evidence-tiers.md` item 3 requires known deck coverage gaps to be
enumerated **in the claim**, and is explicit that this is claimant-enforced:
`klt signoff` grades item 3 on `status: "clean"` alone, so a `met` verdict is
not evidence that the gaps were disclosed. Quoted verbatim from the cited
envelope's own `coverage` block:

- `layers_checked` — `65/20` (diff), `66/20` (poly), `66/44` (licon1), `67/20`
  (li1), `67/44` (mcon), `68/20` (met1), `68/44` (via), `69/20` (met2). Eight
  layers; this block routes on met1/met2 only.
- `layers_in_stream_without_rules` — **seven layers are drawn in this stream
  that the deck has no rule for**: `64/20` (nwell), `65/44` (tap), `66/13`
  (poly.res marker), `68/5` (met1.pin), `79/20` (urpm), `86/20` (rpm), `94/20`
  (psdm). Concretely: **no n-well rule was evaluated at all** — not width, not
  spacing, not enclosure of the PMOS span the whole layout's body-tie strategy
  depends on — and neither were the implant masks or the poly-resistor marker
  that identify this block's precision resistors. A "clean" verdict says
  nothing about any of them.
- `rules_skipped` — empty: the deck did not carry a rule this run declined to
  evaluate.
- `deck_scope` — **absent**. This envelope was produced by klt 0.2.0, which
  predates the field, so the artifact makes no statement about which chapters
  of the sky130 DRM the deck transcribes at all. Per the checklist, an absent
  `deck_scope` is "this artifact reported no scope", never "the deck covers
  everything".
- `rule_counts` — **empty (`{}`)**, same vintage. The report states zero
  violations but names no rule inventory, so the artifact does not itself say
  how many rules ran.

Re-running DRC on a current `klt` would replace all three absences with real
values. It needs the PDK, so it is not something CI can do here; it is worth
doing the next time the layout is recomposed.

### Item 4 is `met`, and what that compare did and did not ask

`status: match`, 27/27 nets, 47/47 devices, 4/4 pins, engine `klayout`
0.30.12, layout vs. `reference.spice` (mechanically translated from the
schematic's own xschem netlist by `layout/bin/gen-ldo-reference-netlist.py`,
so both sides descend from the one schematic). Cited record:
[`20260924-221912-a947aa8`](../layout/ldo-core/reports/20260924-221912-a947aa8/record.md)
— re-pointed here by issue #127 from the original `klt` 0.2.0 record
(`20260825-123628-3b4e121`), which wrote `provenance.input: null` and so could
never be pinned by the manifest itself; this one carries a real
`provenance.input.content_hash`, so `signoff/block-manifest.json` now pins
item 4 directly instead of relying only on `signoff/artifact-pins.json`'s
repo-side re-hash. It is also the record
`layout/ldo-core/reports/LATEST-LVS` names — the **current** LVS run, not
merely the first klt-0.6.0 one. The intermediate klt-0.6.0 record
`20260924-181216-50554fe` (PR #155) satisfies the provenance requirement
identically, but it was minted before commit `0c65db2` (issue #163, VIN/VOUT
sized as spec-derived power rails) redrew the layout; `a947aa8` is the run
against that updated GDS, and citing `50554fe` would pin item 4 to a layout
revision `main` has already superseded. The two envelopes' `lvs.json` files
are byte-identical apart from the layout hash — same `status: match`, same
three warning-severity mismatches, same `power_connectivity` /
`body_verification` blocks — so this currency fix changes no verdict and no
disclosure below. The GDS this record compares is **not** the same revision
item 3's DRC was run on — re-running item 3 was not in #127's scope — so the
two items' composed-GDS hashes now legitimately differ; see
`signoff/artifact-pins.json`'s item-4 notes. Item 4 requires warnings-only
mismatches to be listed with the claim; there are three, all `severity:
warning`, unchanged from the superseded record:

- Two `device.bulk_reconciled` — the request added a `W` (bulk) terminal to the
  reference classes `RES_HIGH_PO` (1 instance) and `RES_XHIGH_PO` (3
  instances) and tied it to reference net `0`. **That terminal's connectivity
  was asserted by the request, not read from the reference netlist**, so the
  resistor-body dimension of this compare is not independently verified.
- One `topology` — a device class with no counterpart on the other side, and no
  devices of that class extracted either; not a real topology mismatch.

Two further questions the superseded klt-0.2.0 record could never ask, and
this klt-0.6.0 record now answers, both weakly:

- **`power_connectivity.status` is `"unchecked"`** — the field itself is no
  longer absent, but its own `reason` says why it still does not apply:
  `reference.form` is `"plain-element"`, whose reference netlist "carries its
  own power/ground pins and nets" that "take part in the ordinary compare"
  instead. Per the checklist, `"unchecked"` means "the question was never
  asked", not "verified" — the same reading the prior absence required, just
  now stated by the tool instead of inferred from a missing field. It is still
  why item 11 cannot lean on this report.
- **`body_verification.status` is `"verified"`**, with `device_count: 0` and
  no findings — this compare has no device class needing a body check to
  verify, so the field reports the (trivial) all-clear rather than being
  silent about the question.

And one scope limit that is not a tooling artifact: **the schematic's four MiM
capacitors are dropped from both sides of the compare** — `klt gen` at this
repo's pinned commit has no capacitor generator (klayout-tools#1117), so they
are neither drawn nor referenced. A match over a netlist that excludes the
compensation and bypass capacitors is a match over the rest of the circuit.

### Item 6 is `met` — what it says, and the one thing it does not

Issue #203 minted this repo's first `klt yield` report and moved item 6
`unmet`/`wrong_kind` → **`met`** (`t1_met_count` 3 → 4 of 11). Issue #211 then
added the **deterministic negative control** the item's own text also asks for,
and item 6 now cites the report carrying it:
[`sim/mc-output-accuracy/klt-responses/20260927-093538-227be3e.yield.json`](../sim/mc-output-accuracy/klt-responses/20260927-093538-227be3e.yield.json),
summarised in
[`records/20260927-093538-227be3e.md`](../sim/mc-output-accuracy/records/20260927-093538-227be3e.md)
(it supersedes `20260927-030409-1a14401`, #203's report, which remains
committed). The verdict does not move — it was `met` before #211 and is `met`
now — but one of the two disclosures below closed, so this section is about
**one** remaining gap rather than two.

**What the report actually says**, over the same n=200 sample set the campaign
already committed (`20260925-131502-808cece`, seed `20260817`), against the
ratified 1.764–1.836 V Output window:

| | Reported |
|---|---|
| Empirical yield (Clopper-Pearson) | 100 % of 200 samples in window → **at least 98.1725 % at 95 % confidence** |
| Normal-fit yield (delta method) | 99.9968 % (CI 99.9911 %–100 %) |
| Normality (Anderson-Darling, 5 %) | `consistent` (A2\* 0.344 vs critical 0.787) |
| Capability | Cp 1.40797, **Cpk 1.34664** (CI 1.20651–1.48677) |
| Sigma-to-spec | **4.03992σ** (CI 3.61952–4.46032), limiting side `upper` |
| Sample size | **`sufficient`** — observed CI half-width 0.00913767 against the 0.01 target; `required_n` 183 |
| Negative control (#211) | **`detected`** — the seeded known-bad variant's own empirical yield is 0 % of 40 draws (CP CI 0 %–8.8097 %), an interval that does not overlap the nominal's 98.1725 %–100 % |

The "100 %" is deliberately not the headline. The tool refuses to print a bare
point estimate and says so in its own warning: with zero observed failures the
interval is bounded only from below, so *"at least 98.1725 % at 95 %
confidence, N = 200"* is the honest statement. The distribution-free
(empirical) and distribution-assuming (normal-fit) estimates agree, and the
normality verdict says the latter's assumption is not violated — which is the
useful part, since the two fail in opposite directions.

The nominal statistics involve no new simulation and no PDK access: `klt yield`
re-reads the per-sample values already committed in the campaign's response, and
what was missing for this item through #203 was never a measurement, only an
analysis of the right *kind* — see "How item 6 got here" below. The **negative
control** is the exception, and had to be: it is a second, deliberately degraded
campaign, and producing it meant really running ngspice against the pinned PDK.
See "The negative control, and what it found" below.

**The one thing `met` does not say: no yield claim was checked.** The payload
status is `reported`, not `pass`, and the report says why: *"no measurement
declared a `target_yield`, so no yield claim was checked — the estimates below
are reported, never failed"*. `klt signoff` accepts `reported` as passing on
exactly that ground (`docs/cli/signoff.md`: "no measurement declared a
`target_yield`, so nothing could fail"). **No `target_yield` is declared here
because `spec/target-spec.md` ratifies none** — this block's spec has no yield,
sigma or Cpk row, and a ratified table that deliberately carries no number is
left open rather than filled in by an agent (`CLAUDE.md`, "The spec is a
gate"). Picking, say, 99 % to make the row read `pass` would have been
inventing the standard and then grading against it. So read item 6's `met` as
*"statistical evidence of the required kind now exists, is sound, and is
pinned"* — not as *"the block met a yield target"*. Ratifying such a target is
a `spec/` decision record, not a manifest edit.

The remaining disclosure is also recorded in `signoff/artifact-pins.json`'s
item-6 note, so it travels with the pin rather than only with this prose. And it
is not a reading unique to this repo: the gap between what `klt signoff` grades
on a yield citation (the payload `status`) and what item 6's text actually asks
for is filed upstream as
[klayout-tools#2467](https://github.com/2AMLogic/klayout-tools/issues/2467) —
"`klt signoff` grades a yield citation on status alone, so an
admittedly-undersized campaign with no negative control renders T1 item 6
`met`". Whichever way that is resolved upstream, the honest statement about
*this* block is the one above, and it is written here rather than left to be
inferred from a `met` token.

**What CI now re-hashes for this item changed too.** A `klt yield` report
carries no `provenance` block, so `klt signoff` hashes the *samples document*
the report names (`report["samples"]`) and uses that both for the citation and
for the staleness pin. `sim/bin/yield-run.py` therefore invokes `klt yield`
from inside `klt-responses/`, so the `samples` field is a bare filename the
grader resolves report-relative. Since #211 that document is not the campaign
response itself but the **derived sample-set document**
`20260927-093538-227be3e.samples.json` (see below), so the manifest pin for
item 6 is that document's sha256 (`sha256:82988e25…`). Both campaign responses
underneath it, and both netlist snapshots, are re-hashed on disk by `check.sh`
as unpinned second claims — and the two responses are additionally cross-checked
against the derived document's own `provenance` block, so the pin cannot be
re-pointed at a different pair of runs than the report analysed. See
"Freshness, and the two independent places it is pinned" below.

#### The negative control, and what it found

Item 6's text asks for "a recorded seed, sample count, **a deterministic
negative control**, and results combined with (not instead of) process
corners". The seed and sample count were always recorded (`20260817`, N=200),
and the mismatch campaign has always sat alongside — not instead of — the PVT
matrix under `sim/*/`. Through #203 the negative control did not exist, and the
report said so in a run-level warning: *"this campaign has no seeded, known-bad
variant demonstrating that the statistics above can actually detect a degraded
design"*. Issue #211 built one. **That warning is gone from the cited report**,
and the only run-level warning left is the `target_yield` one above.

**What was deliberately broken, and why that.** The control is
[`sim/mc-output-accuracy-negctl`](../sim/mc-output-accuracy-negctl/experiment.json):
the nominal bench *verbatim* — same testbench schematic (referenced, not
copied), same tt_mm/27 °C/V<sub>IN</sub>=3.3 V mismatch point, same #164 `uic`
initial-condition contract, same `vout_ss` measurement, same **unrelaxed**
ratified 1.764–1.836 V window, same seed — with exactly one declared defect: the
feedback divider's top leg `XR_FB_A` lengthened 180 µm → 198 µm (+10 %).

That choice is the point of the exercise, so the reasoning is on the record
rather than implied. A divider ratio error is *the* canonical accuracy defect
for an LDO and is precisely what a ratified ±2 % Output row exists to catch, so
a control that this window failed to reject would be indicting the window. The
divider is three nominally identical `res_xhigh_po` legs tapping FB at 2/3 of
V<sub>OUT</sub>, so +10 % on the top leg moves the ideal regulation point
1.2 V·3/2 = 1.8 V → 1.2 V·558/360 = **1.86 V**: +3.33 %, i.e. 1.67× the ratified
window. The magnitude is deliberate in *both* directions — large enough that a
statistic with any detection power must reject it, small enough that the loop
still regulates so every draw stays measurable and the control tests *detection*
rather than producing an avalanche of `errored` samples. It degrades the design
(the on-chip divider), not the testbench stimulus. And it does not depend on
resistor-family mismatch being sampled — `klt sim` reports resistor mismatch as
`unconfirmed` for sky130 — so the defect is deterministic and the only
stochastic ingredient is the same MOS mismatch the nominal campaign draws.

**How it is expressed.** As a `netlist_patch` block in the control's own
manifest: an exact-string substitution with an **asserted occurrence count**,
applied by `sim/bin/mc-run.py` to the netlisted deck between xschem and
`klt sim`. `design/ldo_3v3in_1v8out.sch` is untouched — it stays the single
source of truth for the design under test — and no frozen duplicate of it is
introduced to rot alongside. If the divider in the real design ever changes, the
count stops matching and **the campaign refuses to run** rather than quietly
sampling an undegraded circuit and reporting it as a negative control.

**What it found.** `detected`.

| | Nominal (campaign of record) | Negative control |
|---|---|---|
| N | 200 | 40 |
| Mean `vout_ss` | 1.801568 V | **1.860065 V** |
| Std dev | 8.5229 mV | 8.8530 mV |
| In the ratified window | 200 / 200 | **0 / 40** |
| Empirical yield (Clopper-Pearson, 95 %) | ≥ 98.1725 % | ≤ 8.8097 % |

The two exact intervals do not overlap, which is what `detected` means — a gap
too large to be sampling noise, not merely a lower point estimate
(`docs/cli/yield.md#negative-control`). The control's mean sits 24.07 mV, or
2.72 σ of its own spread, above the window's upper edge, and its σ is within
4 % of the nominal's: the defect moved the distribution without deforming it,
which is the behaviour a divider ratio error should produce and a sign the
control is testing what it claims to.

**So: these statistics can reject a degraded design of this block.** That is
now a measurement, not an assumption — which was the entire point of the
clause. It bounds the claim narrowly and honestly, though: it shows the
`vout_ss` window catches a **mean shift** of this size. It says nothing about
sensitivity to a defect that widens the *spread* without moving the mean, and
nothing about how small a mean shift this statistic could still resolve. A
`not_detected` result would have been an equally reportable finding; this one
simply is not that.

**One confound, measured rather than waved away.** The campaign of record ran on
the EC2 batch fleet (`engine_version` 42, Linux x86_64). The control could not:
`klt sim --backend batch` has no resolvable submit credential on this host
(`aws sts get-caller-identity --profile batch-runner-submit` → `NoCredentials`),
so it ran locally on ngspice 47 / Darwin arm64. An executor difference sits
underneath any control-vs-nominal comparison, so it gets its own committed
campaign:
[`sim/mc-output-accuracy-engine-check`](../sim/mc-output-accuracy-engine-check/experiment.json)
runs the nominal bench **undegraded** — a netlisted deck byte-identical to the
campaign of record's committed snapshot — at the same point, same seed, on the
host and engine that produced the control. Result: mean 1.800071 V (σ 8.4753 mV,
40/40 in window) against the campaign of record's 1.801568 V (σ 8.5229 mV). The
executor's own contribution to the mean is **−1.50 mV**; the seeded defect's is
**+59.99 mV**, **40×** larger. The σ agree to within 0.6 %.

Two smaller findings fell out of that cross-check and are worth recording:

- **The seed contract does not survive an engine change.** On byte-identical
  decks with the same seed, per-sample values differ by ±6–12 mV (mc0: 1.797838
  vs 1.807250 V; mc1: 1.798959 vs 1.790570 V). The two engines do not reproduce
  each other's per-instance AGAUSS draws, so the sample sets are **independent
  draws from the same distribution**, not a paired series — which is exactly why
  the comparison above is made distribution-to-distribution.
- **A PDK-provenance bug in this repo's own harness, now fixed.** `klt sim`'s
  request names `models.lib` by a relative path, so `klt` resolved the PDK root
  itself, and `mc-run.py` passed it no `PDK_ROOT`. On this host that meant
  `mc-run.py` verified `~/.volare/sky130A` against `sim/pdk.json`'s pin and
  recorded `matches_pin: true` while `klt sim` actually read `~/.ciel/sky130A` —
  a different open_pdks build whose `models_fet.spice` is not byte-identical to
  the pinned root's. A record naming a commit the simulation never read is a
  false provenance claim, and for a negative control it would have meant the
  control and the nominal differing by model build as well as by the declared
  defect. `mc-run.py` now passes `PDK_ROOT` explicitly **and** asserts after the
  run that `klt`'s own `provenance.pdk.version` names the pinned commit, so this
  fails loudly instead of silently. All three campaigns above record
  `open_pdks c6d73a35…`, the pin. (Measured aside: re-running against the pinned
  root reproduced the other build's values exactly, so the divergence was
  immaterial *to this measurement* — the provenance claim was wrong, the numbers
  were not. That is luck, not a reason to leave it unfixed.) Filed generically
  upstream as
  [klayout-tools#2564](https://github.com/2AMLogic/klayout-tools/issues/2564).

**Why the analysed artifact is a derived document.** `klt yield` reads a
`negative_control` from either input shape it accepts, but `klt sim` has no
request-side field for one and never emits one on its response rollup — so a
`klt sim` response can carry a negative control only if a committed response is
hand-edited, which this repo's append-only `sim/` discipline forbids outright.
`sim/bin/yield-run.py --negative-control` therefore mints a **sample-set
document** carrying both campaigns' own per-sample values, and `klt yield`
analyses that. Nothing in it is a new number: every value is copied out of a
committed `klt sim` response by the same rule `klt yield` applies to a sim
report itself. That copy is not taken on trust either — the runner re-runs
`klt yield` directly over the nominal response alone and requires the nominal
`distribution`, `capability`, `sample_size` and `yield.empirical` blocks to be
**byte-equal**, aborting rather than recording on any difference. The cited
record reports that check as `IDENTICAL`. The tool gap behind the whole
arrangement is filed generically upstream as
[klayout-tools#2563](https://github.com/2AMLogic/klayout-tools/issues/2563).

#### How item 6 got here

Issue #127 set out to re-point item 6 at a fresh, non-`provenance.input: null`
Monte Carlo envelope the same way it re-pointed item 4, and found the campaign
itself had moved, not just its provenance metadata. The record this manifest
cited until now, `20260825-083111-4cb27f8` (`status: fail`, 177/200), is
**twice superseded** — `20260925-110312-8280915` supersedes it and
`20260925-131502-808cece` supersedes that, each by its own record's
`Supersedes` field — so it had stopped being this block's campaign of record
before this change, and `measurements/characterization.md`'s Output row
already cited `808cece`. The three candidates:

- **`20260825-083111-4cb27f8`** (klt 0.2.0, `status: fail`, 177/200) — the
  outgoing citation. Unpinnable by the manifest (`provenance.input: null`),
  and measured by the bench issue #164 later showed was handing 11–12 of its
  200 mismatch draws a start state that is not a circuit state. Its 177/200
  is a bench artefact, not this block's statistical result.
- **`20260925-110312-8280915`** — an intermediate klt 0.6.0 re-run: `klt sim`
  grades it `status: error` (185 pass / 12 fail / 3 error of 200). Citing it
  would have held `klt signoff`'s graded reason at `check_failed` — but only
  by pointing signoff at a record its own successor replaces. Citing a
  superseded record to keep a reason token steady is the opposite of a
  freshness pin, and `sim/README.md`'s append-only discipline exists so the
  *current* record is always identifiable, not so an old one stays quotable.
- **`20260925-131502-808cece`** — the current record, and the one now cited:
  `status: pass`, 200/200, `vout_ss` mean 1.80157 V inside the ratified
  1.764–1.836 V window, 3σ window [1.776, 1.82714]. Its
  `provenance.input.content_hash` is real, so the manifest pins it directly.

**What changed and what did not, at that point.** Item 6 was `unmet` before
#127 and was still `unmet` after it; `t1_met_count` stayed 3 and `tier` stayed
`null`. The one field that moved in `records/t1-tier-report.json` was item 6's
`reason`:
`check_failed` → `wrong_kind`. Per `docs/cli/signoff.md`, `check_failed`
means the cited check ran and failed; `wrong_kind` means the cited check did
not fail on its own terms but is not the kind this item asks for. Both
sentences are true of the respective records, and the new one is the more
informative statement of where this block stood at that point: **a passing
n=200 campaign with no yield report over it**, where before it was a failing
campaign measured on a bench with a known, since-fixed defect. `wrong_kind`
there meant "the gap is the missing `klt yield` report", not "the wrong file
got cited" — and that reading is what issue #203 then acted on.

That interval is worth keeping on the record rather than folding away: issue
#127's own acceptance criteria asked for item 6's verdict to be unaffected by
the re-pointing, and it was — but its reason token was not, and no citation of
a *current* record could have left it unchanged. Naming the gap precisely is
what made it closable: the missing piece was an analysis of the committed
samples, not a new campaign, and #203 closed it without running a single new
simulation. The campaign response `20260925-131502-808cece` is still the
evidence underneath item 6; it is now cited *through* the yield report rather
than directly, and still pinned on disk by `check.sh`.

### Item 7 has a passing record that this manifest declines to cite

Issue #142 closed the last blocker under "What would move the needle" item 2:
`layout/bin/gen-ldo-blocks.py` now draws sky130's `hvi` (75/20)
voltage-domain marker on every MOS block, so `klt extract --pdk` binds the
schematic's own `sky130_fd_pr__{n,p}fet_g5v0d10v5` models instead of
substituting the 1.8 V core flavour. The resulting record,
[`20260924-181248-50554fe`](../sim/pex-post-layout/records/20260924-181248-50554fe.md),
reports `status: pass, passed: 135, failed: 0, errored: 0` — the erroring
this section previously said had to stop has stopped.

**It was not cited then, on purpose**, for two reasons:

- **The `pass` was ungraded.** `tb_pex_post_layout.request.json` declared no
  limits on any of its three measurements, so `klt pex` graded every `delta[]`
  row against nothing; `pass` meant only "both legs produced a number", not
  "the extracted values agree with the schematic values".
- **The full-load rows were non-physical.** 44 of the 45 full-load corners
  returned a *negative* extracted `VOUT` at 50 mA — the spread ran from
  +1.6 V (`ff/3.630V/-40C`, the one non-negative row) down to −61.9 V
  (`ss/3.300V/-40C`), median |delta| 385 %, max 3543 % — attributed at the
  time to `gen-ldo-blocks.py` drawing every net, power rails included, as a
  0.30 µm met1 signal trunk. Tracked as #154.

**Update (issue #154): the first reason is closed, the second is not — and
its cause turned out not to be this repo's.** The current record,
[`20260924-230726-a947aa8`](../sim/pex-post-layout/records/20260924-230726-a947aa8.md),
was cut against a layout whose `VIN`/`VOUT` are strapped, spec-sized power
rails rather than 0.30 µm signal trunks (still DRC-`clean` and LVS-`match`),
and against a request that now declares limits on all three measurements. Its
verdict is `status: fail` (39 passed / 96 failed, exit 3): it grades, and it
does not pass.

The full-load rows are still non-physical — **45 of 45** corners now return a
negative extracted `VOUT`, median −5.141 V. Extracting the before and after
GDS with `--parasitics` and reading the per-level breakdown shows why the
routing fix could not have moved it: **98–99 % of the modelled per-net
resistance is the li1 term** (`VOUT` total 165 901 Ω → 154 538 Ω, of which
165 467 Ω → 153 677 Ω is li1), and the metal levels the layout flow controls
are under 1 % of the total — and went *up* when the rails were strapped onto a
second level, because the model sums levels in series. The lumped-R model
reduces each level's merged geometry to one equivalent rectangle, so N
parallel device fingers read as one N-times-longer series wire. Both facets
are filed at the tool, generically, per `CLAUDE.md`'s friction protocol:
[klayout-tools#2391](https://github.com/2AMLogic/klayout-tools/issues/2391)
(cross-confirmed, not re-filed) and
[#2458](https://github.com/2AMLogic/klayout-tools/issues/2458). Full evidence:
`sim/pex-post-layout/README.md`, the 2026-09-24/#154 update.

So item 7 remains *substantiable in kind but not in substance*, and the
blocker has **moved out of this repo**: there is no longer a known layout
change that would make those rows physical at this `klt` pin. Citing a row
over non-physical numbers is exactly the failure mode the items-1/2/9/10 note
below refuses ("a `MET` row the tool has no basis to object to and that would
mean nothing"), and `CLAUDE.md`'s "no claim without a testbench" rule reads the
same way. The citation should move when a `klt` build whose parasitic-R model
can distinguish the two GDS files above produces a record whose full-load rows
are physical — not before. That is tracked as **#162**, blocked on the two
upstream issues.

### Item 8 is `met`, and what that verdict does and does not say

`measurements/characterization.md` is the one aggregated, current,
per-spec-row rollup this item asks for, and it names the `sim/<slug>/records/`
(or `layout/ldo-core/reports/`) evidence record behind every verdict. It is
generated by `measurements/build_characterization_report.py`, never
hand-edited, byte-reproducible against an unchanged tree, and carries its own
`--check` mode.

Item 8 asks for that aggregation artifact to exist and be current. It does
**not** ask for every row in it to pass, and this `met` verdict must not be
read as if it did: the report currently reads **FAIL on 7 of the 13 rows that
carry a graded verdict** — Dropout, Load regulation, Load transient, PSRR, Iq,
Area (issue #236 first measured 0.4468 mm²; issue #318 re-measured the current
routed core at 0.4508 mm², capacitors not drawn, against the ratified < 0.1 mm²) and
Stability — and PASS on six (Output, Line regulation, Current
limit, Startup/soft-start, Enable/shutdown, Thermal). Those FAILs are item 5's
subject matter, and item 5 is `unmet` above. Three `met` T1 rows out of eleven is
not a claim about this block's performance.

`Output` moved FAIL → PASS with issue #164, and the move is a *bench* fix, not
a result getting better: no ratified bound was touched and
`design/ldo_3v3in_1v8out.sch` is unchanged. #164 measured that the
`mc-output-accuracy` bench's unconstrained operating-point solve was handing 12
of its 200 mismatch draws a start state that is not a circuit state — `FB`
hundreds of volts *above* the `VOUT` node that is the only thing feeding it
through a passive divider — and that with any physically realizable initial
condition all 200 draws regulate inside the ratified ±2 % window. See
`design/README.md` → "#164".

`Line regulation` moved FAIL → PASS with issue #196, on the same footing and
for a closely related reason: no ratified bound was touched and
`design/ldo_3v3in_1v8out.sch` is unchanged. That bench drove `EN` at the corner
runner's `'vsup'` label while its own `VVIN` was `alter`-ed 2.97–3.63 V *inside*
every corner, so the VIN = 3.63 V point of every `*_2.97v` corner ran with `EN`
0.66 V **below** VIN — the enable-headroom geometry #187 root-caused on
`sim/dropout-vs-load`, against shutdown clamps whose sources are VIN. With `EN`
at the instantaneous VIN the full 45-corner matrix is 45/45 PASS (worst
0.595 mV/V at 1 mA, 0.368 mV/V at 50 mA against the ratified 5 mV/V), and the
superseded record's five FAILs were exactly the `*_125c_2.97v` column. See
`sim/README.md` → "#196".

Item 8 is also the only T1 item a `generic` envelope may satisfy. Every other
item rejects `"kind": "generic"` outright, so this hand-rolled wrapper cannot
be pointed at items 3–7 to make their rows go green.

### Item 11 is `met` — what it says, and what it does not

Item 11 went `unmet`/`no_evidence` → **`met`** (`t1_met_count` 4 → 5 of 11)
when issue #112's `klt erc` supply spec landed. The manifest entry is a
**list** of two citations, the compound shape `klt signoff` grades this item
from:

1. `layout/ldo-core/reports/20260930-193715-dc2823f/erc_supply.json`. This is
   the `klt erc` run of `layout/ldo-core/erc-supply-spec.json` against layout
   record `20260924-221821-a947aa8`. `erc_status` is `clean` with 0 findings.
   `VIN` and `0` are both declared `kind: supply` and each resolves to exactly
   one electrical island. Both `ties[]` are checked, none skipped as
   degenerate. The record's four falsification controls each fire the rule
   the clean verdict claims the absence of (`record.md` there).
2. `layout/ldo-core/reports/20260924-221912-a947aa8/lvs.json`, item 4's own
   report, `status: match`, with `VIN` and `0` both paired in
   `net_correspondence` against the schematic-derived reference.

Both parts are pinned to one GDS hash (`sha256:3e7f504b…`): the ERC run and
the LVS compare are provably about the same layout revision.
`input_verified: true` — the grader re-hashed that GDS itself, which works
from any checkout because `run-ldo-erc-flow.sh` records repo-relative paths.

What it does **not** say:

- **One tie rests on an assertion.** sky130 NMOS sit in the native
  p-substrate and this stream draws no pwell, so `substrate_tie` declares the
  region as `well_boxes` (klayout-tools#2255). The grader reports it
  separately (`ties_checked_by_well_assertion: erc.missing_tie:["substrate_tie"]`).
  The box is re-derived from the GDS before every run, and control C1 moves it
  off its tap and gets `erc.missing_tie`. It is still the caller's word about
  where the substrate is.
- **Connectivity, not robustness.** The block draws exactly one substrate tap
  and one n-well tap across ~2.4 mm. Item 11 asks whether each region's tap
  reaches its net. It asks nothing about tap density or latch-up.
- **The antenna half is `clean_partial`**, not `clean`. Declaring met3 (which
  #154's VIN rail is drawn on) adds 18 gate × met3 pairs that `klt` has no
  sky130 limit for, so they are skipped as `missing_antenna_limit`. Item 11
  does not grade antenna (klayout-tools#1994). The grader carries the
  skip list in the citation's `coverage_qualification` rather than hiding it.
- **Not IR-drop or EM.** `klt power` stays outside this item by design; see
  the current-density note in `layout/README.md`.
- **`power_connectivity` in the LVS part is still `"unchecked"`** (see item 4
  above). `unchecked` would fail item 11 for a digital block that cites a
  PDN. With no PDN cited, the grader instead requires every declared supply
  to be paired in the LVS `net_correspondence`, and `VIN` and `0` both are.

### Items 1, 2, 9 and 10 are uncited on purpose

`klt signoff` grades these four on "some passing envelope was cited at all",
not on whether the cited evidence is topically relevant — they name no `klt`
verb, so there is no right artifact to restrict them to. Citing this block's
clean DRC report for item 10 would produce a `MET` row the tool has no basis
to object to and that would mean nothing.

All four are, in substance, satisfied by this repo: the schematic and its
netlist (1), the composed GDS and its floorplan (2), the testbenches and their
cold-start invocation (9), the README/spec/licence/CI (10). They are still
left `unmet`/`no_evidence`, because that is the accurate machine-readable
statement: *no check backs this claim*. `klt signoff`'s own documentation names
this as the safest default and the shipped `examples/signoff/` follows it.

### Freshness, and the two independent places it is pinned

**Every one of the six citations now carries a manifest `content_hash`**
(item 11's compound entry pins both of its parts).
Items 4 and 6 were the two that could not: both were produced by `klt` 0.2.0,
which wrote `provenance.input: null`, and a manifest pin against an envelope
that claims no input hash renders the item `unmet`/`stale_evidence` — a false
negative, not a stronger claim. Issue #127 re-pointed both at klt 0.6.0
records whose `provenance.input.content_hash` is real (see "Item 4 is `met`"
and "Item 6 is `met`" above), so the manifest now pins
items 3, 4, 6, 7, 8 and 11 — all of them.

Item 6 is pinned by a different mechanism since issue #203 re-pointed it at a
`klt yield` report: a yield report carries no `provenance` block, so
`klt signoff` hashes the *samples document the report names* and uses that for
the citation and the pin alike (`docs/cli/signoff.md`). It is the one citation
here whose `content_hash` the grader computes by reading a file rather than by
quoting an envelope's claim — so for this item the two checks below agree by
construction (`input_verified: true`), and the independent on-disk claims are the
other item-6 rows instead. Since issue #211 the hashed document is the *derived
sample-set document* rather than the campaign response, because a
`negative_control` cannot be carried on a `klt sim` response at all — see "The
negative control, and what it found" above.

The manifest pin is the weaker of the two checks, though, and it did not
replace the stronger one. `klt signoff` grades a manifest pin against the
*cited envelope's own* claim about its input and never opens the artifact
(items 6 and 11 excepted, which the grader re-hashes itself), so **all
thirteen artifacts behind all six citations are also pinned in
`signoff/artifact-pins.json` and re-hashed on disk by `check.sh`**:

| Item | Artifact re-hashed by CI | Hash claim cross-checked against |
|---|---|---|
| 3 | `…/20260825-123551-3b4e121/ldo_core.gds` | envelope `provenance.input.content_hash` + manifest pin |
| 4 | `…/20260924-221912-a947aa8/ldo_core.gds` | envelope `environment.layout_sha256` + manifest pin |
| 4 | `…/20260924-221912-a947aa8/reference.spice` | envelope `environment.reference_sha256` |
| 6 | `…/klt-responses/20260927-093538-227be3e.samples.json` | the samples document the cited `klt yield` report names + manifest pin (no envelope claim to cross-check — a yield report makes none) |
| 6 | `sim/mc-output-accuracy/klt-responses/20260925-131502-808cece.json` | derived sample-set document `provenance.nominal.sha256` |
| 6 | `sim/mc-output-accuracy/netlist-snapshots/20260925-131502-808cece.spice` | campaign envelope `provenance.input.content_hash` (== `environment.netlist_sha256`) |
| 6 | `sim/mc-output-accuracy-negctl/klt-responses/20260927-092313-227be3e.json` | derived sample-set document `provenance.negative_control.sha256` |
| 6 | `sim/mc-output-accuracy-negctl/netlist-snapshots/20260927-092313-227be3e.spice` | negative-control envelope `provenance.input.content_hash` — the DEGRADED deck |
| 7 | `…/20260825-123551-3b4e121/ldo_core.gds` | envelope `provenance.input.content_hash` + manifest pin |
| 7 | `sim/pex-post-layout/netlist-snapshots/20260825-125102-3b4e121.pex.extract.spice` | envelope `extraction.netlist_sha256` |
| 8 | `measurements/characterization.md` | envelope `provenance.input.content_hash` + manifest pin |
| 11 | `…/20260924-221821-a947aa8/ldo_core.gds` | ERC envelope `provenance.input.content_hash` + manifest pin (part 1) |
| 11 | `…/20260924-221912-a947aa8/ldo_core.gds` | LVS envelope `environment.layout_sha256` + manifest pin (part 2) |

Neither half is redundant: the manifest pin is what the *grader* (and the
fleet roll-up that consumes this manifest) can verify without this repo's
cooperation, and the on-disk re-hash is what keeps two hand-written files
from merely agreeing with each other.

### Disclosures the claimant owes, not the grader

- **Item 3's DRC coverage** is *reported* by `klt signoff`, never graded — see
  the item-3 section above for all five fields, including the two the artifact
  does not carry.
- **Item 7's `body_bias`** is likewise reported and not graded: a `klt pex`
  citation whose `body_bias.status` is `"unbiased"` still renders `met`, and a
  resimulation of an unbiased extracted netlist is physically wrong rather than
  merely imprecise. This repo's `pex` envelope carries **no `body_bias` block
  at all** (klt 0.2.0 predates it), which per the checklist means "this
  artifact made no body-bias statement", never "every device body was biased".
  Moot for the *cited* run — it errored on all 135 rows, so there are no
  post-layout numbers to qualify — but it must be stated with any future
  item-7 claim. The uncited 2026-09-24 record does carry the block, and it
  reads `status: biased, unbiased_device_count: 0, unbiased_nets: []`, so the
  physically-wrong-resimulation hazard would not bite for that layout.
- **Item 4's `power_connectivity`** reads `"unchecked"` (not absent, since
  issue #127's re-pointing) and **`body_verification`** reads `"verified"`
  (trivially — `device_count: 0`); `"unchecked"` is not `"verified"` either
  way. See the item-4 section.

## What would move the needle

In dependency order, not effort order:

1. **Item 5** is the block's real gap and the largest one: nine ratified rows
   FAIL. That is a design program (issues #115–#121), not a manifest problem,
   and no citation here can shortcut it. Emitting the PVT campaign as `klt sim`
   envelopes is a second, separate prerequisite for the row ever grading `met`.
2. **Item 7** no longer needs the `klt pex` leg to stop erroring (issue #142
   did that), nor the request to declare limits (issue #154 did that), nor the
   power rails to stop being drawn as 0.30 µm signal trunks (#154 did that
   too, and the layout is still DRC-clean and LVS-matched). What it needs now
   is **not in this repo**: a `klt` build whose `--parasitics` lumped-R model
   can tell a sized power rail from a signal trunk at all —
   [klayout-tools#2391](https://github.com/2AMLogic/klayout-tools/issues/2391)
   and [#2458](https://github.com/2AMLogic/klayout-tools/issues/2458). At this
   repo's pin, 98–99 % of the modelled per-net resistance on the load-current
   nets is the device generator's own local-interconnect pads, which no knob
   this flow has can change. Tracked as #162. See "Item 7 has a passing record
   that this manifest declines to cite" above.
3. **Item 11** needs a `klt erc` supply spec and report (issue #112).
4. **Item 6** is `met` as of issue #203, and as of issue #211 the
   **deterministic negative control** this list previously asked for exists,
   ran, and is cited: `detected`, on a seeded +10 % divider mis-ratio the
   ratified window rejects 40/40 (see "The negative control, and what it found"
   above). Nothing about that was needed for the grader — it is what the item's
   own text asks for and `klt signoff` cannot check — which is exactly why it
   was worth building. One disclosure remains on that row, and it is **not** a
   build task: the report's status is `reported` rather than `pass` because this
   block's spec ratifies no yield target. That moves only through a `spec/`
   decision record, and a number invented to make the row read `pass` would be
   worse than the honest `reported`. See "Item 6 is `met` — what it says, and
   the one thing it does not" above.
5. **Items 1, 2, 9 and 10** need nothing built. They stay `unmet` by choice,
   not by gap.

Filing the tool-side friction this surfaces belongs at
`2AMLogic/klayout-tools`, per this repo's friction protocol in `CLAUDE.md` —
generically, describing the tool gap and not this design.

## Note from #230 (regenerative thermal comparator integrated)

`design/ldo_3v3in_1v8out.sch` changed (trip comparator replaced). The pins for
items 3, 4 and 11 still hash-match, but the DRC/LVS/ERC/area records they cite
describe the pre-#230 schematic and are STALE against it (the regenerated
`measurements/characterization.md` says so for DRC and LVS). Only item 8's pin
was moved (that file was regenerated). The tier stays `null`, 5/11. The full
inventory is in `sim/README.md`, "Stale artifacts caused by the schematic change";
re-running them belongs to #231.
