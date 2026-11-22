# Issue #704: paired dynamic-response evidence — baseline vs #692 rev2

This is a diagnostic, not a record: nothing under any `sim/*/records/` is minted and no
production file changes. It supplies the loop-gain, load-step and PSRR evidence for the
#702 rev2 adoption review, as paired measurements of the pinned production schematic
(HEAD `cd7a9d60`, `design/ldo_3v3in_1v8out.sch` sha256 `1378c2d4…`) and the same
schematic's netlist with the #692 overlay applied (`apply_candidate(raw, 2)` from
`sim/dropout-vs-load/diagnostics/issue-692-20261120-235900/candidate.py`, sha256
`a08e93dc…`; rev 2 = NTAIL W 7 µm / nf 2, VREF-referenced bias + NMOS-input OTA).
`check_candidate(raw, edited)` returned an empty problem list on every paired deck.
Compensation is byte-identical in every pair (`C_COMP VOUT EA_CZ 150p`,
`XR_CZ … res_xhigh_po W=0.42 L=52`); the recorded netlist digests are

| bench | variant | netlist sha256 (raw / edited) |
|---|---|---|
| loop-gain | base | `2c8d2816ea36…` / `2c8d2816ea36…` |
| loop-gain | rev2 | `2c8d2816ea36…` / `d698ea5dd6a5…` |
| psrr | base | `396104ea9904…` / `396104ea9904…` |
| psrr | rev2 | `396104ea9904…` / `699509b25a67…` |
| load-step | base | see `runs/loadstep/base/leg.json` |
| load-step | rev2 | see `runs/loadstep/rev2/leg.json` (edited `bdb9c1334bed…`) |

Everything multi-corner ran on the batch fleet through `klt sim --backend batch`
(146 jobs; ids in `verdict.json`, each response dir and `leg.json`); the only local
ngspice runs are the six single-corner syntax probes under `runs/syntax-probe/`
(not campaign evidence). Batch preflight job `klt-sim-75351f414433`, compatibility
`match`. One deliberate bench adaptation, disclosed: the load-transient bench's
11-token `.ic` seed names three nodes the overlay removes (`EA_TAIL`, `EA_D1`,
`EA_D2`), and ngspice rejects the whole `.ic` card once any named node is gone
(observed on the pre-adaptation deck during probing; that failing run was not
retained). The retained evidence for the adaptation: the candidate decks drop
exactly those three tokens and keep the other eight byte-identical to the
baseline deck's first eight (`runs/syntax-probe/loadstep-{base,rev2}/deck.spice:22`),
and all 18 candidate leg-corners passed the `vout_pre_v` gate (1.764–1.836 V;
`runs/loadstep/rev2/leg.json`) before the first step.

## Verdict for #702 (summary)

**Both designs miss the stability, load-step and PSRR targets. Rev2 adds three
phase-margin failures at zero load and six falling load steps that exceed the
150 mV peak-deviation limit.**

| row (ratified bound) | baseline | rev2 | paired verdict |
|---|---|---|---|
| Stability PM ≥ 45° (tt/27 °C/3.30 V, 42 legs) | 23/42 below (worst 17.45° at 4.7 µF, 0 mΩ ESR, 30 µA) | 26/42 below (worst 14.27° at 4.7 µF, 0 mΩ ESR, 10 µA) | 23 legs fail both, 16 pass both. **3 regressions** at 4.7 µF and 0 mA, one at each ESR (PM drops by about 14.75°). Mean ΔPM across all 42 legs is −1.9°. The six 50 mA legs gain 0.76° to 4.08° (mean +3.33°). |
| Stability GM ≥ 10 dB | 0/37 below (worst 16.95 dB @ 0.33 µF·ESR0·50 mA) | 0/38 below (worst 16.65 dB, same leg; 16.17 dB after the extraction correction below) | no GM regressions; 5 pairs GM-unavailable on ≥1 side |
| Load step peak ≤ 150 mV (6 legs × quick PVT) | 11/36 direction-legs above (worst 215 mV, 0.33 µF·ESR0 rising, ff/125 °C/3.63 V) | 17/36 above (worst 242 mV, same leg) | rise: 9 fail both; **fall: 2 → 8 (6 new failing legs)**; paired peak deltas ≤ +42 mV |
| Load step recovery ≤ 20 µs (±1 %) | 36/36 above 20 µs (worst 651.9 µs, 4.7 µF·ESR0, ff/125 °C/3.63 V) | 36/36 above (worst 733.7 µs, same leg) | Both designs recover within the measurement window and miss the 20 µs limit in both directions at every condition. |
| PSRR > 50 dB @ 1 kHz | 0/86 valid pass (worst 20.30 dB @ 1 mA, fs/125 °C/2.97 V) | 0/84 valid pass (worst 20.10 dB, same corner) | both fail everywhere (pre-existing shortfall) |
| PSRR > 20 dB @ 100 kHz | 1 mA: 43/43 pass; 50 mA: 0/43 pass (worst 10.46 dB @ fs/−40 °C/2.97 V) | 1 mA: 42/42 pass; 50 mA: 0/42 pass (worst 9.79 dB @ fs/−40 °C/3.30 V) | structure unchanged; paired deltas −3.3…+0.1 dB (1 kHz, mean −1.5) and −2.1…+0.03 dB (100 kHz, mean −0.4) |

The baseline already misses the light-load PM, recovery and PSRR targets.
DR-006 documents the 0 mA stability gap. At the 0.33 µF, 50 mA condition
from #349/#691, both designs meet the 10 dB gain-margin target at all three
ESRs. Both reach 45° phase margin only at 500 mΩ.

| ESR | Baseline PM | Baseline GM | Rev2 PM | Rev2 GM |
|---:|---:|---:|---:|---:|
| 0 mΩ | 39.82° | 16.95 dB | 43.74° | 16.65 dB |
| 10 mΩ | 40.09° | 17.16 dB | 43.99° | 16.86 dB |
| 500 mΩ | 52.26° | 27.22 dB | 55.54° | 26.07 dB |

## Loop-gain extraction check (rev2's VREF-driven bias)

The loop-gain bench injects at VREF and recovers T = X/(1−X), X = v(fb). In rev2,
VREF additionally gates the bias V-to-I (`XM_VRF`), a second entry for the
injection. Check: six legs re-run with `XM_VRF`'s gate moved to an internal
DC-1.2 V / AC-0 source (`VVREFB`; single-entry condition restored; the edit is
`runs/loop/rev2-decoupled/netlist.decoupled.diff`):

| leg | as-drawn PM/GM | decoupled PM/GM | ΔPM | ΔGM |
|---|---|---|---|---|
| c47-esr0-10uA (worst PM) | 14.27° / 68.72 dB | 14.26° / 67.73 dB | −0.01° | −0.99 dB |
| c033-esr0-0mA (0.33 µF, no load) | 14.63° / 69.02 dB | 14.62° / 67.49 dB | −0.01° | −1.53 dB |
| c033-esr0-50mA (worst GM) | 43.74° / 16.65 dB | 43.77° / 16.17 dB | +0.03° | −0.49 dB |
| c47-esr0-0mA (regression leg) | 38.37° / 72.42 dB | 38.33° / 70.43 dB | −0.04° | −2.00 dB |
| c033-esr0-1mA (passing control) | 86.31° / 28.38 dB | 86.27° / 27.63 dB | −0.04° | −0.75 dB |
| c47-esr500m-30uA (GM-unavailable) | 15.34° / unav. | 15.33° / unav. | −0.01° | n/a |

The extraction check changes PM by at most 0.041° across the six legs and
preserves their PM grades. Gain margins as-drawn read 0.5–2.0 dB optimistic
against the single-entry extraction; after the correction the worst GM is
16.17 dB — still above the 10 dB bound, so no GM verdict changes, but rev2's GM
column carries that disclosed optimism. GM `transfer_metric_unavailable`
(`no_downward_phase_crossing`) on 4.7 µF·500 mΩ light-load legs — 5 base, 4 rev2 —
is reported as unavailable, never as a pass.

The low-frequency (`dc`) loop gain is far more extraction-sensitive, in the
opposite direction: on the c47-esr0-10uA leg, rev2's as-drawn `dc` of 650.12
reads 1818.23 under the single-entry extraction (×2.80, +8.9 dB), so rev2's
as-drawn `dc` is ~9 dB pessimistic and the paired `dc` column in
`tables/loop_pair.csv` is not like-for-like — the apparent 14.8 dB paired
DC-gain deficit on that leg is ~5.9 dB after the correction. No graded quantity
uses DC gain (`verdict.json`'s `pair_classification` carries only `d_pm`/`d_gm`,
deliberately no `d_dc`), so no verdict in this report changes.

## Coverage, gaps and invalid results

- **Loop gain**: exactly the issue's pinned grid — tt/27 °C/3.30 V, loads
  {0, 10, 30, 100, 300 µA, 1, 50 mA} × C_out {0.33, 4.7 µF} × ESR {0, 10 mΩ,
  500 mΩ} = 42 conditions per DUT, all 84 measured with a regulating operating
  point (op-gate VOUT 1.62–1.98 V, one 7-step op request per DUT). The manifest's
  other 44 PVT corners were **not** attempted.
- **Load step** covers six cap/ESR legs at the three `quick_subset` corners
  (tt/27/3.30, ss/−40/2.97, ff/125/3.63). That gives 18 leg-corners per DUT,
  each measured on the rising and falling step (36 direction-legs per DUT).
  The campaign omitted the other 42 PVT corners. No leg showed the
  window-ceiling ambiguity (max recovery 733.7 µs <
  the 998 µs ceiling), so every "above 20 µs" reading is a real missed recovery,
  not a no-crossing artifact.
- **PSRR**: the full 45-corner matrix × both loads per DUT, at the bench's own
  load network (C_out 1 µF / ESR 10 mΩ). Invalid (solver-diagnostic contract,
  recorded not suppressed): 4 base corners (ff/27/3.30 and fs/−40/3.30, gmin
  stepping) and 6 rev2 corners (1 mA: `xr_cz.t1` singular matrix at tt/−40/2.97
  and ff/−40/3.30, `xr_fb_b.t2` singular matrix at tt/3.63; 50 mA: gmin-stepping
  failure at tt/−40/2.97 and ff/−40/3.30, `xr_fb_b.t2` singular matrix at
  tt/3.63). Each is listed in `verdict.json` and excluded from grading rather
  than counted either way.

## Files

| path | content |
|---|---|
| `campaign.py` | driver: netlist once per bench, apply the rev2 overlay + preservation checks, write/submit the batch requests (fc pattern for loop/psrr, corner-run batch backend for load-step), local syntax probes |
| `analyze.py` | paired tables, per-metric grading, worst cases, classification, `verdict.json` |
| `commands.sh` | the as-executed sequence |
| `runs/loop/{base,rev2}/` | 43 requests + responses each (42 AC legs + op gate), netlists, diff, provenance |
| `runs/loop/rev2-decoupled/` | the 6-leg extraction-check requests/responses and the decoupling diff |
| `runs/psrr/{base,rev2}/` | 9 requests + responses each (2 loads × 3 supplies + 3 op gates), 15 corners per request |
| `runs/loadstep/{base,rev2}/` | 18 requests each (6 legs × 3 quick corners), `klt-requests/`, `klt-out/`, `leg.json` (graded results + execution/job ids), engine logs |
| `runs/syntax-probe/` | six local single-corner probes (both variants × three benches) — debug, not evidence |
| `tables/{loop,psrr,loadstep}_pair.csv` | the paired values the README numbers come from |
| `verdict.json` | machine-readable stats, classifications, coverage, invalid lists |

Reproduce the report from the evidence with `python3 analyze.py`; the paired
values are recomputed from the raw responses, never copied from this README.
