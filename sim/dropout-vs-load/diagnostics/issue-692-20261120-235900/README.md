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
79.8 mV of margin). Rev2 passes Iq at **44/45 corners**. At ff/125C/3.63 V,
full-load Iq reads **30.0 uA** at 0.1 uA resolution. The strict < 30 uA row
remains unproven there. Production-adoption review #702 owns the remeasurement.

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
~2 significant digits (voltages at 7); that is the tool's report resolution and is
recorded as such. The batch harness records job completion, runner compatibility
and engine diagnostics in each leg. The campaign grades a dropout crossing only
when the settled VOUT at the top of the sweep is within 1.764–1.836 V. Iq requires
VOUT in that same window at both load endpoints. A missing required value,
non-regulating point, timeout, batch error or solver diagnostic yields `INVALID`.
The full-load VIN current is printed to 0.1 uA at 50 mA. The analysis compares
the load-subtracted Iq at that resolution. A full-load reading of 30.0 uA with
an otherwise passing endpoint pair receives `AT_BOUND`, with `pass: false`.
The no-load channel retains its own precision. Counts in `verdict.json` are
mutually exclusive, and extrema use valid measurements.

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

The paired table in `tables/dropout_pair.csv` retains all 45 measurements per design.
The baseline exceeds the dropout bound at every corner (#114). The minimum and
binding dropout below use valid crossings.

| design | min valid [V] | binding corner | binding dropout [V] | valid passes / corners |
|---|---|---|---|---|
| baseline | 0.3300 | ff/125C/3.63 V | 0.6731 | 0/45 |
| **rev1** | 0.1551 | ff/-40C/2.97 V | **0.2192** | **44/45** |
| **rev2** | 0.1547 | ff/-40C/2.97 V | **0.2202** | **45/45** |

Across valid crossings, EA_OUT spans 0.586–1.195 V for the baseline,
0.058–0.455 V for rev1 and 0.055–0.457 V for rev2. Baseline tail current reaches
a minimum of 0.11 uA. Rev1 spans 2.16–3.64 uA and rev2 spans 1.24–2.14 uA.
M_CLIM peaks at 0.582 uA for rev1 and 0.357 uA for rev2, both at ff/-40C/3.63 V.

The excluded rev1 crossing at ss/-40C/3.30 V reads 0.077944 V. VOUT started
at 3.143523 V, outside the regulation window. At the crossing EA_OUT was
−0.898949 V and M_CLIM carried 607 uA. At the 0.300 V edge the clamp carried
0.95 mA (Vsg 2.01 V, VOUT 1.991 V). This clamp-mediated crossing is `INVALID`.
Rev2 starts in regulation at the same corner and measures 0.1548 V dropout.

## 5. The #357 section-7 limits over PVT (issue step 3)

- **Iq at 0 and 50 mA.** The baseline measures 10.81–16.72 uA at no load and
  23.9–31.3 uA at full load, with five failures at 3.63 V across ff and fs.
  Across rev1's 43 regulating corners the corresponding ranges are 11.78–18.48 uA
  and 24.4–33.2 uA. The two excluded corners include a −663.129 uA no-load reading
  and a 59.4 uA full-load reading (section 6). Rev2 spans 9.73–15.15 uA at no load
  and 22.3–30.0 uA at full load. At ff/125C/3.63 V the reported VIN current
  magnitude is 0.0500300 A. Subtracting 50 mA gives 30.0 uA, exactly the strict
  bound at the channel's 0.1 uA resolution. The paired Iq table records 44 passes
  and this one at-bound corner.
- **Clamp margin at the 0.300 V edge** (dropout-bench extras): at ss/125C (the corner
  #357 named unmeasured) the clamp is OFF at the edge at every supply: Vsg(M_CLIM)
  0.050-0.051 V, M_CLIM current ~4e-11 A, VOUT still regulating at 1.786-1.790 V.
  Rev2 reaches its highest edge Vsg of 0.412 V at ff/-40C/2.97 V, with M_CLIM
  carrying 1.4e-12 A. The
  one edge-clamp engagement is rev1's ss/-40C/3.30 V anomaly above.
- **VREF-referenced V-to-I spread**: I_R spans 0.485–1.000 uA for rev1 and
  0.486–1.002 uA for rev2 across the 45 corners (2.06x for both), against the baseline
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

The rev1 Iq table records 30 passes, 13 measured failures and two invalid corners.

- 13 current excesses (30.2-33.2 uA vs the strict < 30), the mechanism #357 predicted
  (the candidate's bias overhead) — worst ff/125C/3.63 V at 33.2 uA where the baseline
  reads 30.7 uA. The 31.3 uA quoted in the archived `candidate.py` sizing comment
  is the baseline maximum at ff/-40C and ff/27C, both at 3.63 V.
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
probe: dropout 0.16351 V (rev1 0.16324), tail 1.838 uA, full-load Iq 26.2 uA
from the recorded VIN current of −0.0500262 A. The re-run covered the full matrix
again on both benches
(exceeding the issue's failing-corners + three-worst-passing minimum, at fewer fleet
jobs than 25 singleton requests): dropout 45/45 (binding ff/-40C/2.97 V 0.2202 V, +
0.94 mV over rev1), Iq 44/45 pass and one at bound. Both previously invalid Iq
corners now regulate. Rev2 measures 24.9 uA at ss/125C/3.30 V under full load
and 11.65 uA at ff/27C/2.97 V at no load.

## 7. Decision (issue step 5): **ADOPT-REVIEW**

Rev2 meets the issue's decision criterion of a valid dropout below 300 mV at every
corner. Rev1 has one invalid crossing. Rev2's Iq result at ff/125C/3.63 V requires
higher-resolution measurement. Per step 5 rev2 advances to **production-adoption
review #702** (loop gain, PM/GM, load transient, PSRR, start-up, MC accuracy), which
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
klt-sim-e5966d7b1353`. `provenance.json` lists the SHA-256 digest of every other
Git-tracked file in this directory, including the per-corner decks, logs and
response files. The graded evidence is the batch legs; the local probes
(`runs/local-syntax*`, `runs/dbg-*`) are syntax checks and mechanism diagnosis only.
Lint: `ruff check --select F` clean on all `.py` files here.

## Reproduce

```bash
cd sim/dropout-vs-load/diagnostics/issue-692-20261120-235900
python3 -B analyze.py # regenerate the tables and verdict from the committed batch results
```

The original fleet invocation is recorded in `commands.sh`. Verify the archived bytes
from the campaign directory with the following command.

```bash
jq -r 'to_entries[] | "\(.value)  \(.key)"' provenance.json | sha256sum --check --quiet
```
