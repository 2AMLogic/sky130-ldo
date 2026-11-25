# Issue #757 — loop-gain batch adapter live verification

Live evidence for the three criteria of #757, produced on the dispatch worker
`loom-worker` (8-vCPU shared host; all multi-corner work on the batch fleet,
per host rules) at repo commit `d0bee518b7566a932b896051969efba693762b95`.

## Environment disclosure (read this first)

- **PDK**: this host has no `~/.volare`; the worker-spec PDK store is
  `~/.ciel` (`PDK_ROOT=$HOME/.ciel`, variant `sky130A`, open_pdks
  `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`). `sim/pdk.json` still pins the
  volare layout `c6d73a35…`, so every run here was made with
  `--allow-pdk-mismatch`, which the harness records in the record header
  ("**MISMATCH vs sim/pdk.json pin**"). The same `PDK_ROOT` was passed to
  BOTH backends of the pair, and klt's own provenance names
  `open_pdks f6eeac7…` on both halves — the pair is same-build. The pinned
  fleet AMI's ciel store is the same `f6eeac7…` family. The repo-pin vs
  worker-store drift is the same class as the ngspice/xschem pin drift
  (#645, #639); migrating `sim/pdk.json` to the ciel pin is NOT part of this
  issue (out of scope: no spec/pin change).
- **Engines**: local `ngspice-47` (KLU); fleet `ngspice-47` (KLU) — the
  engine version agrees across the pair (`environment.engine_version` = 47
  in all three responses). The repo's declared tools pin (`ngspice 42`,
  `xschem 3.4.4`) is a recorded drift, WARN-only, that never gates a
  measurement (#291's contract).
- Absolute values here differ slightly from the `20261029-092024` local
  record (e.g. tt/27C/3.30V `pm_c033_50ma` 40.477 vs 40.535 deg): that
  record ran volare `c6d73a35…` under ngspice-42. The shift is attributable
  to the PDK build + engine change, not to the backend split — the pair
  below bounds the backend split itself at |Δ| ≤ 5e-4.

## 1. Baseline pins — VERIFIED, no drift

`klt netlist sim/loop-gain/testbench/tb_loop_gain.sch --rcfile sim/xschemrc`
with `PDK_ROOT=$HOME/.ciel PDK=sky130A` (full netlist kept beside this
README: `pin-check-tb_loop_gain.spice`, content hash
`sha256:e58412ce…`). The seven `BATCH_ALLOWLIST["loop-gain"]["stimulus"]`
cards and `batch_loop_gain.NODESET_CARD` match the generated netlist
byte-for-byte:

```
VVIN VIN 0 'vsup'
VEN EN 0 'vsup'
VVREF VREF 0 DC 1.2 AC 1
COUT VOUT VESR 0.33u m=1
VESRSENSE VESR VESRS 0
HESR VESRS 0 VESRSENSE 10m
RLOAD VOUT 0 36 m=1
.nodeset v(VOUT)=1.8 v(xldo.FB)=1.2 v(xldo.N_FBB)=0.6
```

No `_batch_backend.py` / `batch_loop_gain.py` pin changes were needed.

## 2. Paired single-corner comparison — VERDICT: equivalent

Commands (this worktree, both with `PDK_ROOT=$HOME/.ciel PDK=sky130A` and
`--allow-pdk-mismatch`):

```bash
python3 sim/bin/corner-run.py sim/loop-gain --backend local --process tt --temp 27 --supply 3.30 --subset-reason 'issue 757 paired comparison' --no-write --allow-pdk-mismatch
python3 sim/bin/corner-run.py sim/loop-gain --backend batch --process tt --temp 27 --supply 3.30 --subset-reason 'issue 757 paired comparison' --no-write --allow-pdk-mismatch
python3 sim/bin/compare_loop_gain_paired.py sim/loop-gain/diagnostics/issue-757/paired --local-engine 47 --remote-pass FAIL --local-pass FAIL
```

- Fleet jobs: `klt-sim-9d4d6cd7fdbd` (esr10m, c7i.4xlarge), `klt-sim-d13566008b43`
  (esr500m), `klt-sim-6f88f842de47` (esr0); batch preflight ACCEPTED
  (`klt-sim-2a630ddc89e1`, runner klt 0.9.0, compatibility match).
- All 56 named results compared from artifacts (`paired/` beside this
  README): remote from the three `response.json` + retained `ngspice.log`
  per group; local from `local/values.json`, assembled from the FULL
  precision `print meas_*` lines of the retained corner log
  (`local/tt_27c_3.30v.fail.log`) — never the `.6g` console summary
  (Judge note on #757). 54 finite rows agree with max |Δ| = 5e-4
  (tolerances: vseed 1e-6 V, PM 1e-3 deg, GM 1e-3 dB, DCG 1e-3 dB,
  fc 1e-3 Hz — both engines print ≥7 significant digits, so the tolerances
  are at or below one printed ULP; agreement is digit-level).
- `gm11` (`c47_esr500m_1ma`) is a **confirmed non-crossing on both sides**:
  the local ngspice measurement failed with `out of interval`; the fleet
  engine log carries the same `out of interval` + `failed!` pattern for
  that exact step/card, but the batch runner graded it `status: "error"`
  instead of `not_reached` — klayout-tools#7770. The comparator now reads
  the retained engine log to confirm such a result (a narrowly-scoped,
  artifact-derived bridge; missing logs or non-matching patterns still
  count as missing evidence).
- **Legs 7 and 13 (solver continuation)**: local continues across ESR-group
  boundaries, batch restarts per group. Measured together —
  leg 7: vseed 1.798832/1.798832 V, PM 52.637/52.6368 deg (Δ 2e-4),
  GM 27.4256/27.42559 dB (Δ 1e-5); leg 13: vseed 1.798832/1.798832 V,
  PM 82.8065/82.8065 deg, GM 29.144/29.14401 dB. The continuation
  difference is not observable at these tolerances.
- Grades: FAIL both sides (PM below the 45 deg minimum at several legs — a
  bench grade, unchanged in kind from the 20261029 record); engines 47/47.
  Verdict: **equivalent** (`paired/comparison-report.json`).

## 3. Full 45-corner fleet run — record `20261124-051830-d0bee518`

```bash
PDK_ROOT=$HOME/.ciel PDK=sky130A python3 sim/bin/corner-run.py sim/loop-gain --backend batch --allow-pdk-mismatch
```

45 corners over 9 requests, one new append-only record
(`sim/loop-gain/records/20261124-051830-d0bee518.md`) and its manifest
(`manifests/artifacts/loop-gain-20261124-051830-d0bee518.manifest.json`,
74 evidence entries pushed to the artifact store: per-corner logs, the nine
requests/responses, request netlists, netlist snapshot, and the record's
JSON twin). Overall grade: **FAIL** (measurement grade; PM below 45 deg at
several legs per corner — same posture as every prior loop-gain record).
Job IDs: `klt-sim-e5418aa21893`, `klt-sim-453e6d464413`, `klt-sim-73d14c13b00a`
(2.97 V), `klt-sim-da799b1ed7c4`, `klt-sim-482de3a5b89c`, `klt-sim-3b4eb63ddd06`
(3.30 V), `klt-sim-cb5b1025f8d4`, `klt-sim-f7aa4fb3560a`, `klt-sim-870698df871d`
(3.63 V). The `ac11.gmdb` non-crossing and the klt #7770 misgrade diagnostic
are carried verbatim in each corner's record entry.

No spec, DR-005, schematic, or prior-record file was changed.
