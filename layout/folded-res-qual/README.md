# layout/folded-res-qual/ -- folded series resistors, qualified in isolation (issue #253)

The #246 area study (`layout/area-study/20261009-study-246/report.md`) found
that the straight `R_BIAS` body (L = 1500 um) by itself forces the LDO core to
be at least 1500.8 um wide. It proposed folding long resistors into N equal
series segments stacked as a bank, but left DRC, LVS and electrical
equivalence unverified. This directory checks that proposal **on
resistor-only test blocks** before anyone changes the core floorplan.

What this directory does **not** claim:

- It is not a full-core layout, and it says nothing about whether the LDO
  meets the ratified Area row (< 0.1 mm^2). That row is not touched.
- No schematic value changes. Every folded bank keeps the schematic `W`, and
  its segment lengths add up exactly to the schematic `L`.
- It is not a PVT qualification. The electrical comparison runs at one
  stated operating point (`tt`, 27 C), as issue #253 asks. The champion
  review did not authorise a PVT campaign. The record says this, and the
  remaining PVT/Monte Carlo work is listed below.

The evidence is in `reports/<record-id>/record.md`; `reports/LATEST` names
the newest record. Records are append-only, the same as `sim/`.

## Reproduce

```bash
layout/bin/setup-venv.sh                                   # pinned klt (layout/requirements.txt)
layout/.venv/bin/python layout/bin/run-folded-res-qual-flow.py
```

Inputs are `cases.json` (the cases and the operating point) and the PDK
pinned in `sim/pdk.json`. The flow runs one step at a time (no parallel
fan-out) and takes about 40 s:

1. `layout/bin/gen-folded-res-qual.py` writes four streams per case:
   - `<case>_unsplit`: `klt gen res_array num=1` at the schematic L. This is
     exactly what the core flow draws today.
   - `<case>_folded`: `res_array num=N rows=N` (one L/N segment per row, in
     boustrophedon order). Caller-owned li1 straps join segment i's `R<i>_B`
     pad to segment i+1's `R<i+1>_A` pad. The per-row psdm/rpm/urpm markers
     are merged into one rectangle over the bank.
   - `<case>_broken`: the folded bank with one strap left out. This is the
     LVS negative control.
   - `<case>_unmerged`: the folded bank with every strap, but with the
     per-row markers left as `res_array` draws them (no merge). This is the
     expected-to-fail DRC control for the marker merge. It gets no
     extraction or LVS.

   Each stream also gets a substrate tie labelled `SUB` and the chain-end
   labels `A`/`B`. `res_array` cannot chain its own units in series. That
   generic gap was already filed by #246 as 2AMLogic/klayout-tools#2997, so
   it was not filed again.
2. DRC runs `klt drc --deck sky130` on every stream. This is the same gate the
   core records use. As a coverage cross-check, the PDK's own KLayout signoff
   runset (`libs.tech/klayout/drc/sky130A_mr.drc`, FEOL+BEOL) also runs on the
   unsplit, folded and unmerged streams. The flow fails unless the runset
   reports at least one rule class on the unmerged stream that it does not
   report on the folded stream.
3. `klt extract` runs once with defaults, once with
   `--defer-resistor-fixed-offset`, and once with `--parasitics`. The
   parasitics run gives the measured lumped resistance of each joint's li1
   strap.
4. `klt lvs` runs with `options.combine_devices: true`. Every stream is
   compared against a one-element reference for the **unsplit** schematic
   resistor. A perturbed reference (R x 1.001) is the parameter-sensitivity
   negative control.
5. One ngspice `.op` deck runs the PDK compact model (the
   `libs.tech/combined/sky130.lib.spice` library `sim/` uses) as the unsplit
   device and as N-segment chains. Each chain is run with and without the
   measured li1 joint resistance. There is one corner and one temperature;
   the bulk is at 0 V. The voltage across each resistor comes from
   `cases.json`. `R_BIAS` gets 2.0 V, inside the ~1.2-2.4 V that its ~1-2 uA
   bias current puts across about 1.2 Mohm (`design/README.md`). `R_FB_A`
   gets 0.6 V, one third of the 1.8 V output across the three equal
   feedback units. The `res_high_po` model has no voltage coefficient, so
   `R_BIAS`'s result does not depend on that choice. The `res_xhigh_po`
   model does have one, which is why its voltage is stated.

## Equivalence tolerance (fixed before any result was computed)

A folded bank counts as **EQUIVALENT** to the unsplit schematic resistor if
its effective resistance at the operating point is within **3 x the
local-mismatch sigma of the unsplit device**. Sigma is
`sw_mm_<model> * mismatch_factor / sqrt(W*L)`, read at run time from the
model library itself (not transcribed). A deterministic shift inside that
band cannot be told apart from drawing a second copy of the same schematic
device. A larger shift is a real electrical change: it has to be requalified
or compensated, not assumed away. The record also shows the global
sheet-rho corner spread and the process Monte Carlo sigma for context. They
do not affect the verdict.

## Findings (record `20261010-033502-704005c`)

This record supersedes `20261010-032804-ea209d2`, which stays in place
unchanged (records are append-only). The new record adds the unmerged-marker
DRC control. Every other number in it is identical to the earlier record.

| case | layout | klt DRC | LVS vs unsplit | negative controls | R_eff shift | tolerance | verdict |
|---|---|---|---|---|---|---|---|
| `rbias_n16`: R_BIAS, 16 x 93.75 um (the #246 100 um bank) | 94.59 x 12.72 um | clean | match | both mismatch | **+1.060 %** | 0.246 % | **NOT EQUIVALENT** |
| `rbias_n4`: R_BIAS, 4 x 375 um | 375.84 x 2.88 um | clean | match | both mismatch | +0.212 % | 0.246 % | EQUIVALENT |
| `rfb_n2`: R_FB_A, 2 x 90 um (xhigh) | 90.84 x 1.24 um | clean | match | both mismatch | -0.017 % | 1.601 % | EQUIVALENT |

1. **LVS does not detect the electrical difference.** With
   `combine_devices`, `klt lvs` folds the N segments into one device and
   charges the deck's fixed head offset once, so the fold matches the
   unsplit reference exactly. The compare is tight: the 0.1 % perturbed
   reference fails it. The match therefore proves topology and the deck's
   resistance convention. It does not prove electrical equivalence. The
   report gave no hint that anything was absorbed, so this was filed
   generically as **2AMLogic/klayout-tools#3017**. Secondary resistor
   parameters (L, P) never cause a mismatch by themselves. The 16-segment
   fold's combined P is 3013.44 um against the reference's 3000.84 um, and
   the unperturbed fold still matches. A `p` difference is listed only in
   the perturbed report, on a device that has already failed on `r`.
2. **End/contact effects were measured, not assumed.**
   - In the PDK model, each extra `res_high_po` segment adds about
     **+821 ohm**: one more head term plus the model's +0.247 um effective
     length. Each extra `res_xhigh_po` segment changes R by about
     **-210 ohm**. That is the net of two more head terms, the model's
     -0.0592 um effective-length correction, and its length-dependent
     voltage coefficient at 0.6 V. See the N sweep in the record's
     electrical table.
   - Each li1 strap adds a measured **37.79 ohm** per joint (`--parasitics`).
   - The klt extraction deck's own convention differs from the model: it
     charges 379.7 ohm per `res_high_po` body and 0 for `res_xhigh_po`.
     Naively summing the per-segment extracted R gives +0.491 % for N=16.
     The model plus straps gives +1.060 %.
   - The R_BIAS shift scales roughly linearly with N (N-1 joints). It stays
     inside tolerance up to N=4 and is outside from N=8 on.
3. **DRC: the klt gate is clean, but its coverage on these blocks is
   narrow.** Only 7 rules had geometry to check (li1, licon enclosure,
   poly width, tap). The PDK signoff runset reports:
   - `licon.1` on the unsplit *and* folded streams. `res_array` at this
     repo's pin draws 0.22 um square cuts on precision poly. This is
     pre-existing: the core's resistors have it too. Upstream fixed it under
     klayout-tools#2449, after this repo's pin.
   - `rpm.1a` / `urpm.1a` (marker width) on every unsplit stream. This is
     also pre-existing.
   - The merged bank markers clear the marker-width rule for N >= 4. The
     2-row bank is still 1.24 um tall, under the 1.27 um minimum.
   - With the markers merged, folding added no new rule class. The
     unmerged control shows what the merge removes. In `rbias_n16` the
     runset adds `rpm.2` x15 (marker spacing, one per row gap) and
     `rpm.1a` x16 (marker width, one per row). In `rbias_n4` it adds
     `rpm.2` x3 and `rpm.1a` x4. In `rfb_n2` it adds `urpm.2` x1, and
     `urpm.1a` rises from x1 to x2. This is why the folded stream merges
     its markers.
4. **Area.** The 16-row R_BIAS bank is 94.59 x 12.72 um = 1203 um^2. The
   routed bbox is the same, because the straps sit inside the pad columns
   and add no bbox growth. They are 7.81 um^2 of li1. The #246 study
   estimated 4960 um^2 for this bank with a conservative pitch and
   1472 um^2 with an optimistic one. The equivalent 4-row bank is
   1082 um^2 but still 375.84 um wide.
5. **Observation, not qualified and not in the record.** A newer
   `klt 0.7.0+g8eec069c7576` build installed on the host, outside this
   repo's pin (`layout/requirements.txt`), draws `res_array` high/xhigh with 0.19 x 2.0 um
   precision-poly contacts and per-row markers that abut at a 2.6 um row
   pitch, instead of 0.82 um at the pin. A 16-row bank from that generator
   would be about 41.6 um tall (about 4000 um^2). Nothing from that build
   is in the record: these figures come from an unrecorded look at that
   build's output. Any future pin bump has to re-mint this record before its
   area figures are reused.

**Verdict for the floorplan question.** Folding works for DRC (on the repo's
gate) and LVS (by klt's fold convention) for both resistor flavours. Folding
the feedback resistors is electrically equivalent. The 16-segment R_BIAS bank
the #246 study priced is **not** a drop-in replacement for the schematic
device: it is 1.06 % high, about 4x the tolerance. Equivalent R_BIAS folds
stop at about 4 segments. Further compaction needs one of two things, and
both are design decisions outside this issue: length compensation (the drawn
L would then differ from the schematic L, and the LVS reference would need
the matching treatment), or an electrical requalification of the shifted
value.

## Remaining work (separate from this issue)

- **Full-core integration** (#231 owns the layout refresh):
  - Teach `gen-ldo-blocks.py` to place and route a resistor bank instead of
    one straight body per resistor, and decide N per resistor (`R_BIAS`,
    `R_FB_A/B/C`, `R_CZ`).
  - Re-mint the core DRC/LVS/area records (append-only), and only then
    compare against the Area row.
  - Check the substrate-tie reach across a bank, and check the bank's
    placement against the MOS wells and rails.
- **Electrical qualification of the chosen fold:**
  - Run PVT corners: the head term scales with `sw_poly_head_res` and with
    corners differently from the body, so the shift measured here at `tt`
    will move.
  - Run Monte Carlo: an N-segment chain carries N head-mismatch terms.
  - If R_BIAS keeps N > 4, requalify the bias current or compensate the
    length. Either way, the decision has to go through the design/spec
    process.
- **Tooling:**
  - A klt pin bump that includes the upstream `res_array` precision-contact
    fix (klayout-tools#2449) would clear the PDK-signoff `licon.1` findings.
    It also changes the bank's row pitch (finding 5).
  - klayout-tools#2997 (series-chain generation) and #3017 (fold-offset
    disclosure) are open upstream.

## PVT / mismatch qualification (issue #263) -- BLOCKED on the batch fleet

#263 extends the single-point comparison above to a predeclared process x
temperature x voltage matrix plus seeded mismatch Monte Carlo. Everything
needed to run it is committed; **the run itself has not produced results**, so
this README makes no new equivalence claim and no segment-count
recommendation. The #253 findings above (tt / 27 C only) are unchanged.

- `pvt/matrix.json` -- the matrix, the equivalence criterion (the unchanged
  0.246 % / 1.601 % tolerance, applied to the worst shift over every point),
  the new mismatch gates M1 (|mean shift| within the same tolerance) and M2
  (sigma ratio <= 1.10), the candidate N lists (R_BIAS 1,2,3,4,5,6,8,10,12,16 with
  N=16 the known nonequivalent control; R_FB 1..6) and the declared limitations.
  It was committed before any run (see git history).
- `bin/_folded_res_pvt.py`, `bin/run-folded-res-pvt.py`,
  `tests/test_folded_res_pvt.py` -- deck/request generation, analysis and the
  record writer. `python3 layout/bin/run-folded-res-pvt.py` goes to the batch
  fleet and never falls back to a local grid; a failed submit mints a BLOCKED
  record.
- `pvt-reports/20261010-050239-509c688/` -- the BLOCKED record: deck, both
  `klt sim` requests (63 deterministic points, 3000 Monte Carlo units), and
  `ATTEMPTS.md` with every attempt and its outcome (runner/client version skew
  `klt 0.5.0` vs `0.7.0` on the fleet, then fleet capacity refusal).

To complete the study once the fleet accepts the client (runner updated, or
capacity available): run `python3 layout/bin/run-folded-res-pvt.py` (add
`--measure-form meas --klt "uvx --from klayout-tools==<runner version> klt"` for an
older runner); it mints a new record and `pvt-reports/LATEST`.
