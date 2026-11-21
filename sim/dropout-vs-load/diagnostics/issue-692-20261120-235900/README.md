# Issue #692: paired 45-point PVT campaign for the #357 rev1 dropout candidate

This is a diagnostic, not a record: nothing under `sim/dropout-vs-load/records/` is
minted, and no production file changes. It is the #357 screen's section 8 item 3: the
baseline-vs-candidate paired campaign over the dropout bench's full 45-point PVT matrix
(5 process x 3 temperature x 3 supply), both designs at one commit (`218e3e99`, clean),
executed on the fleet through `klt sim --backend batch` (the validated #374 cold-start
crossing adapter and the #213/#381 iq endpoint adapter, driven through corner-run.py's
own batch backend library). The ratified rows are unchanged: dropout @ 50 mA < 300 mV
(strict) and Iq < 30 uA (strict, 0 and 50 mA).

**Verdict: ADOPT-REVIEW** — with the single permitted revision (rev2) the candidate
holds < 300 mV at **all 45 corners** (binding corner **ff/-40C/2.97 V at 0.2202 V**,
80 mV of margin) and the Iq row passes at all 45 corners, one of them with **zero
effective margin** (ff/125C/3.63 V, 29.999999999995 uA). It goes to a separate
production-adoption review issue, not to adoption here.

## 1. Files

| file | purpose |
|---|---|
| `candidate.py` | the candidate, copied from `../issue-357/candidate.py` and re-based on the current netlist; `REV[2]` added (the one revision). rev0/rev1 card output is byte-identical to #357's module (verified at run time) |
| `campaign.py` | batch campaign driver: netlists each bench with the repo xschem flow, applies the variant, builds the validated requests via `prepare_batch_requests`, appends the extra read-only `meas` step measurements + deck-level `.save` device-current cards, runs `run_batch`, extracts per-corner extras |
| `debug_probe.py` | ONE local `ngspice -b` per call at one corner, with loop-node traces, for the two non-regulating iq corners and the rev2 tt check |
| `analyze.py` | paired tables + `verdict.json` (per-corner machine-readable verdicts + decision) |
| `commands.sh` | the declared, as-executed sequence |
| `runs/<leg>/` | per batch leg: `leg.json` (graded results, execution block with remote job ids, provenance), `klt-requests/` (request netlists + JSONs), `klt-out/<group>/` (klt stdout/stderr, `response.json`, per-corner artifacts), `logs/` (per-corner engine logs), `netlist.diff` (candidate legs) |
| `runs/local-syntax*/`, `runs/dbg-*` | local single-corner probes (not campaign evidence) |
| `tables/dropout_pair.csv`, `tables/iq_pair.csv` | the 45-row paired tables |
| `verdict.json` | machine-readable verdicts |

## 2. Re-base onto the current design (issue step 1)

`design/ldo_3v3in_1v8out.sch` last changed at `a09aa83f` (2026-10-08, the #230
regenerative thermal comparator integration), which PREDATES the #357 screen
(2026-10-11): the netlist the campaign netlisted at `218e3e99` is card-for-card the one
#357 screened, **integrated thermal comparator included** (its whole device set is in
the candidate's byte-identical PRESERVED list; `check_candidate` passed on every run).
`apply_candidate(raw, 1)` therefore applies unchanged: the re-based rev1 candidate IS
#357's rev1, verified two ways — every EXPECTED card matched exactly at run time, and
this directory's `candidate.py` regenerates the identical edited netlist as #357's
committed module (`rev1 identical to issue-357 module: OK`).

**tt / 27 C / 3.30 V pair reproduction** (batch jobs `klt-sim-19ce82bf9de6` baseline /
`klt-sim-e4fbe79a5654` candidate, remote ngspice-47, runner_compatibility `match`):
baseline dropout_v **0.397658 V** (#357: 0.397658), candidate **0.163237 V** (#357:
0.163237) — identical to all six printed digits, zero delta. EA_OUT at the crossing
0.7114 / 0.1028 V, tail 0.31 / 2.83 uA, M_CLIM at the crossing 0 / 0.14 uA, VOUT at the
0.300 V edge 1.607 / 1.793 V: every quantity reproduces #357's table.

## 3. Method

Both benches run under their own ratified manifests, verbatim, through the batch
adapters #375's paired check validated: `dropout-vs-load` as one single-step
cold-start `tran 10u 14m uic` request per supply (15 corners per request), `iq` as two
cold-start endpoint requests per supply. Per-corner observables beyond the graded
manifest measurements are added as **extra read-only `meas tran` step measurements**
(`find ... when v(vout)=1.764 fall=1 td=6m` at the crossing; `find ... when
v(vin)=2.064 fall=1 td=6m` at the 0.300 V edge; `avg ... from=5.5m to=6m` settled
windows) plus deck-level `.save` cards for the device currents they read. The
validated request shape (analysis, stimulus, graded cards) is untouched; the extras
ride along in the same single step. klt reports device-current step measurements at
~2 significant digits (voluges at 7); that is the tool's report resolution and is
recorded as such. Validity gates are the harness's own: remote job done, runner
compatibility `match`, corner status completed, no solver diagnostic in the engine
log, finite graded values. A missing crossing, non-regulating start or diagnostic is
INVALID, never a pass.

Grid actually run (both benches, both variants): process {tt,ss,ff,sf,fs} x
temperature {-40, 27, 125} C x supply {2.97, 3.30, 3.63} V = the manifest's full
45-point matrix; every leg's `leg.json` lists its 45 corner ids.

Batch route: `python3 sim/bin/batch-preflight.py` first (exit 0 accepted; job
`klt-sim-a75577b5c820`, runner klt 0.9.0, client klt 0.9.3.dev2575+g6bd18bbc8637,
compatibility match). Every leg then ran through `run_klt_batch`, which sets
`batch.capacity_wait_s` in the request (3 h budget) plus the caller-side fleet-cap
retry; no `batch_no_capacity` was hit. Remote engine ngspice-47 on every job; PDK
sky130A open_pdks `c6d73a35...` matches the `sim/pdk.json` pin (klt's own provenance
checked per response). Local tools: ngspice-47, xschem 3.4.7 (pin declares 42/3.4.4 —
the same host drift #357 recorded; the tt pair above shows the numbers are unaffected).

## 4. Dropout results (issue step 2)

Full table: `tables/dropout_pair.csv`. All 45 corners valid for all three designs; the
baseline fails its ratified row at every corner (known T1 gap, #114).

| design | min [V] | binding corner | binding dropout [V] | n < 300 mV |
|---|---|---|---|---|
| baseline | 0.3300 | ff/125C/3.63 V | 0.6731 | 0/45 |
| **rev1** | 0.0779 | ff/-40C/2.97 V | **0.2192** | **45/45** |
| **rev2** | 0.1547 | ff/-40C/2.97 V | **0.2202** | **45/45** |

EA_OUT at the crossing: baseline 0.586-1.195 V (the collapsed tail), rev1 0.058-0.455 V,
rev2 0.055-0.457 V. Tail current at the crossing: rev1 2.16-3.64 uA, rev2 1.24-2.14 uA
(baseline's PMOS tail collapses to 0.11 uA at its crossing). M_CLIM at the crossing:
rev1 <= 0.58 uA, rev2 <= 0.36 uA (worst ff/-40C/3.63 V — the deep-dropout clamp onset
#357 named as floor mechanism (ii); it conducts, it does not gate the crossing).

One rev1 anomaly, recorded as measured: at ss/-40C/3.30 V rev1 reads dropout
0.077944 V with the clamp FULLY on at the edge (Vsg 2.01 V, 0.95 mA) and VOUT@edge
1.991 V — that crossing is clamp-mediated (its 2.97/3.63 V siblings read 0.155 V with
the clamp off). rev2 at the same corner is clean: 0.1548 V, edge Vsg 0.048 V.

## 5. The #357 section-7 limits over PVT (issue step 3)

- **Iq, 0 and 50 mA vs < 30 uA** (full table `tables/iq_pair.csv`, batch endpoint
  adapter): baseline 10.81-16.72 uA no-load / 23.90-**31.30** uA full-load (fails its
  own row at the five 3.63 V ff/fs corners — the row is not met by the production
  design either). rev1: 15.09-**18.48** / 24.40-**59.40** uA — fails at 15 corners
  (below). rev2: 9.73-15.15 / 22.30-**29.999999999995** uA — 45/45 pass, but the
  ff/125C/3.63 V corner sits at the bound to 11 decimal places: **zero effective
  margin**, recorded as an at-bound finding for the adoption review, not headroom.
- **Clamp margin at the 0.300 V edge** (dropout-bench extras): at ss/125C (the corner
  #357 named unmeasured) the clamp is OFF at the edge at every supply: Vsg(M_CLIM)
  0.050-0.051 V, M_CLIM current ~4e-11 A, VOUT still regulating at 1.786-1.790 V.
  Tightest margin over the matrix: ff/-40C/2.97 V, Vsg 0.412 V (rev2) with M_CLIM at
  1.4e-12 A — off by ~10 orders of magnitude in current, ~0.2 V of Vsg margin. The
  one edge-clamp engagement is rev1's ss/-40C/3.30 V anomaly above.
- **VREF-referenced V-to-I spread**: I_R = 0.486-1.00 uA over the 45 corners (2.06x)
  for rev1 and rev2 alike (the revision does not touch it), against the baseline
  BIASP reference's 1.73-2.48 uA (1.44x). #357's warning that I_R tracks Vth and
  temperature strongly is confirmed and quantified; tail, clamp threshold and Iq
  inherit it.
- **Current-limit engagement**: measured on the dropout bench as M_CLIM conduction at
  the crossing and at the edge (above). The dedicated `current-limit` bench
  (forced-output DC + held short) is **not** batch-validated (`BATCH_ALLOWLIST`), so
  its trip point and knee were NOT re-run over PVT — a recorded scope limit, handed to
  the adoption review together with the thermal re-bisection (#357 section 8.3). No
  local multi-corner grid was run to work around it.

## 6. rev1's Iq failures and the one revision (issue step 4)

rev1 fails the Iq row at 15 corners, recorded unedited in `tables/iq_pair.csv`:

- 13 current excesses (30.2-33.2 uA vs the strict < 30), the mechanism #357 predicted
  (the candidate's bias overhead) — worst ff/125C/3.63 V at 33.2 uA where the baseline
  itself reads 31.3 uA;
- **two non-regulating states**, diagnosed with single-corner local traces
  (`runs/dbg-*`):
  - `ss/125C/3.30 V`, 50 mA: the current-limit clamp LATCHES during the cold 50 mA
    start and never releases — settled state VOUT 3.152 V, EA_OUT 1.093 V held by
    M_CLIM (CL_CMP 0.856 V), pass in triode at 48.7 mA so the saturated sense FET
    over-reports while the ss/125C-weakened CLP reference collapses; Iq reads 59.4 uA;
  - `ff/27C/2.97 V`, no load: settles non-physically at VOUT 3.421 V ABOVE VIN with
    NTAIL at -0.10 V and the pass drain-body junction back-conducting ~1.1 mA into
    VIN (net Iq -663 uA). A robustness failure of the rev1 start-up at low VIN/no
    load, not an Iq value.

**The one revision (rev2)** is evidence-driven from that set alone: the whole
amplifier current is set by the tail mirror, so `NTAIL W 12/nf 3 -> W 7/nf 2` (tail
4.8x -> 2.8x of NBR; ~3.16 -> ~1.84 uA at tt, the amplifier ~6.4 -> ~3.7 uA) cuts Iq
everywhere WITHOUT touching the clamp reference chain (I_R / PBR / CLP unchanged,
preserving the 3.3 V trip) or any preserved device. Nothing else changed. Local tt
probe: dropout 0.16351 V (rev1 0.16324), tail 1.838 uA, full-load Iq 26.26 uA
(baseline 27.61). The re-run then covered the FULL matrix again on both benches
(exceeding the issue's failing-corners + three-worst-passing minimum, at fewer fleet
jobs than 25 singleton requests): dropout 45/45 (binding ff/-40C/2.97 V 0.2202 V, +
1.0 mV over rev1), Iq 45/45 — and both non-regulating states are gone (ss/125C/3.30 V
full-load 24.9 uA, VOUT in window; ff/27C/2.97 V no-load 11.65 uA, VOUT in window).

## 7. Decision (issue step 5): **ADOPT-REVIEW**

The issue's own criterion — dropout < 300 mV at every corner — is met by rev1 AND
rev2. rev2 additionally clears the Iq row at every corner (one at zero effective
margin). Per step 5 the candidate goes to a **separate production-adoption review
issue, #702** (loop gain, PM/GM, load transient, PSRR, start-up, MC accuracy), which
must also weigh: the ff/125C/3.63 V at-bound Iq corner, rev1's two non-regulating states
(cleared by rev2's weaker tail, but the start-up/robustness mechanism is not
re-qualified here), the 2.06x V-to-I spread, the current-limit and thermal PVT
re-checks, and the bias re-topology interaction (#467 — this campaign screens against
the committed bias; every conclusion above depends on it). No spec row, threshold or
decision record is changed; the production schematic is untouched.

## 8. Provenance

Source commit `218e3e99` (worktree `feature/issue-692`, clean; the campaign runs are
all at this commit, recorded per leg in each `leg.json`). PDK sky130A, open_pdks
`c6d73a35f524070e85faff4a6a9eef49553ebc2b` (matches pin; klt's provenance asserted per
response). Remote engine ngspice-47, runner klt 0.9.0, client klt
0.9.3.dev2575+g6bd18bbc8637; local ngspice-47 / xschem 3.4.7 / Python 3.12.3. Batch
job ids: preflight `klt-sim-a75577b5c820`; pair `klt-sim-19ce82bf9de6` /
`klt-sim-e4fbe79a5654`; dropout-base `klt-sim-51ef20128e0f, klt-sim-eb9e13381aff,
klt-sim-e9e50ca9bc12`; dropout-cand `klt-sim-b79572650788, klt-sim-2e8bf239457b,
klt-sim-29e6fd3a6022`; iq-base `klt-sim-9547da5f525c, klt-sim-5143b7e003e4,
klt-sim-4c86ed4f72d0, klt-sim-eae777b62c45, klt-sim-b180241ccd32,
klt-sim-8d2fcfde40bb`; iq-cand `klt-sim-cff8604a732b, klt-sim-81b53403b92c,
klt-sim-18c6e44ea618, klt-sim-fdee5150ee8a, klt-sim-60ca4f01634c,
klt-sim-1f1978d50346`; dropout-cand-r2 `klt-sim-262eff193861, klt-sim-723d25d5235f,
klt-sim-1233d69429b5`; iq-cand-r2 `klt-sim-5e93d60a3b85, klt-sim-18937a46e444,
klt-sim-b0e32805e76c, klt-sim-d029a0c0be29, klt-sim-7d252db741d5,
klt-sim-e5966d7b1353`. `provenance.json` holds the sha256 of every file in this
directory. The graded evidence is the batch legs; the local probes
(`runs/local-syntax*`, `runs/dbg-*`) are syntax checks and mechanism diagnosis only.
Lint: `ruff check --select F` clean on all `.py` files here.

## Reproduce

```bash
cd sim/dropout-vs-load/diagnostics/issue-692-20261120-235900
sh commands.sh        # batch legs need the fleet; ~2 h wall total
python3 -B analyze.py # regenerates tables/ and verdict.json
```
