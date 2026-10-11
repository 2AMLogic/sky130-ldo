# Issue #365 -- zero-load Stability: phase-dip mechanism and a bounded light-load lever screen

Status: diagnostic at **one PVT point (tt / 27 C / 3.30 V)**, from multi-leg local decks run as an exception after
the batch preflight failed (section 1); the lever-B result and the handoff are **PROVISIONAL until a fleet re-run**. No spec row, decision record, production
schematic, production target, PASS count or existing diagnostic is changed; the invalid-to-no-pass rule for missing
crossings is unchanged. Nothing here qualifies the Stability window. Baseline = unmodified `design/ldo_3v3in_1v8out.sch`
at source commit `860f93f` (no dropout-candidate revision from #357 is in this baseline; if #357 changes the circuit,
re-baseline before using any number below).

## 1. What was run, and what was deferred

| run id | what | where | result |
|---|---|---|---|
| `runs/base_tt` | baseline, 10 loop-gain legs (below), complex T and 6 node transfers saved | local, one `ngspice -b` (17 s) | exit 0, no solver diagnostic |
| `runs/tail2_tt` | lever A: `M_TAIL` W x2 (40 -> 80 um) | local, one `ngspice -b` (16 s) | exit 0, no diagnostic |
| `runs/rcz16_tt` | lever B: `R_CZ` L x16 (52 -> 832 um, ~4.8 MOhm) | local, one `ngspice -b` (17 s) | exit 0, no diagnostic |
| `runs/base_lt_tt`, `runs/rcz16_lt_tt` | repo `sim/load-transient` manifest verbatim (6 C/ESR legs x rise/fall), baseline vs lever B | local, one `ngspice -b` each (243 s / 171 s) | exit 0, no diagnostic |

Legs per loop-gain run (stimulus verbatim in `result.json["stimulus"]`, `ac dec 30 0.01 Hz .. 1 GHz`, explicit
`alter cout/hesr/rload` + `op` before each AC): C_out {0.33, 4.7} uF x ESR {0, 10 mOhm, 500 mOhm} at 0 mA (`RLOAD`
1e12), plus 1 mA (1.8 k) and 50 mA (36 ohm) regression controls at 10 mOhm for both capacitances. Loop gain
`T = v(fb)/(1-v(fb))` exactly as the repo deck.

**Fleet / batch: NOT used.** `sim/bin/batch-preflight.py` was run twice (start and end of the work; `batch-preflight.txt`
is the second): **exit 3, version mismatch** (runner klt 0.5.0, client 0.7.0). No PVT grid was started locally.

**Host-rule disclosure.** The five local `ngspice -b` runs above were **not** single-condition debug probes. Each was a
**multi-leg local deck at one PVT point (tt / 27 C / 3.30 V)**: the three loop-gain runs are 10 C_out / ESR / load
legs each, and the two load-transient runs are 12 legs each (about 4 minutes of host time each pass). They were run
locally **as an exception, after the batch preflight failed** (exit 3, klt version mismatch). The host rule and
#365's own criterion allow only a single-condition probe locally and send multi-condition grids to the batch path
(deferring if it is unavailable); the #349/#360 precedent does not override that.
- **Mechanism evidence:** `runs/base_tt` (the unmodified baseline) is the mechanism probe for sections 2 and 3.
- **Lever screens:** `runs/tail2_tt` (lever A), `runs/rcz16_tt` (lever B) and the transient pair
  `runs/base_lt_tt` / `runs/rcz16_lt_tt` are lever screens. These lever and transient legs would normally have gone
  through the batch path.
- Consequently the lever-B result and the qualification handoff (sections 4-6) are **PROVISIONAL**: local-only
  evidence pending a fleet re-run of the same legs once a compatible preflight passes. They were not trimmed or re-run.

**Deferred (unrun), to be requested through `klt sim` corners once a compatible preflight passes:**
- every PVT point other than tt/27 C/3.30 V ({tt,ss,ff,sf,fs} x {-40,27,125 C} x {2.97,3.30,3.63 V}), for baseline and both levers;
- the remaining 8 of the #338 18-leg grid (ESR 0 / 500 mOhm at 1 and 50 mA) and any ESR other than the three ratified values;
- load-transient for lever A (it was rejected on Iq and margins before spending 4 minutes of host time) and for any
  other condition than tt; `iq` bench cross-check (Iq here comes from the per-leg operating point, VIN current minus load current);
- pole/zero extraction by a rational fit (see section 3 caveats) and any intermediate R_CZ value or load-adaptive realisation.

Tool note: the host has ngspice 46 / xschem 3.4.7 (`result.json` provenance `on_baseline: false` vs the declared
42 / 3.4.4); the PDK commit matches the pin. The host tools are shared and cannot be changed from here; the baseline
numbers reproduce the earlier #324/#349/#360 values to the digit (0.33u/0mA 19.7 deg, 4.7u/0mA 53.1, 0.33u/50mA 40.5,
4.7u/50mA 83.3), so no solver-version drift is visible, but it is not excluded.
`lightload_probe.py` / `lightload_extract.py` had two dead-code lines (unused import/variables) removed after the runs to
satisfy pinned `ruff==0.17.0 --select F`; the `driver_sha256`/`extract_sha256` in `result.json` therefore refer to the
pre-cleanup files. Behaviour is unchanged: re-deriving every leg's corners and phase-dip from the saved `resp_leg*.txt`
with the cleaned code reproduces the stored values (0 mismatches).

## 2. Baseline mechanism evidence (`runs/base_tt`, `tables.md`)

All 10 legs are valid: VOUT 1.8024 V (0 mA), 1.8006 V (1 mA), 1.7988 V (50 mA), all inside 1.7-1.9 V; each has a finite
negative-real-axis crossing (GM 68-74 dB at 0 mA, so missing crossings are not the failure here).

- 0 mA, 0.33 uF: DC gain 70.1 dB, crossover 282 Hz at phase -160.3 deg (PM 19.7). 4.7 uF: crossover 60 Hz, phase -126.9
  (PM 53.1). Iq at 0 mA is 13.87 uA (VIN current; no load).
- The 0 mA gain magnitude has slope corners at ~0.3 Hz (pole-like) and ~79 Hz (pole-like), then a zero-like corner
  at 21.5 kHz (0.33 uF) / 5.8 kHz (4.7 uF). The 0.33 uF crossover (282 Hz) sits **above both low-frequency
  corners and 75x below the zero-like corner**; the 4.7 uF crossover (60 Hz) sits just under the 79 Hz corner. So
  the 0 mA margin is set by where the unity-gain crossing lands relative to those corners: it is a plain
  two-low-frequency-poles-before-a-late-zero shape, with the phase still near -160 deg at crossover. The phase
  does recover later (to about -129 deg near 10 kHz, then a ~16 kHz notch-like feature), but that is far above the
  crossover and cannot help the margin.
- **The "doublet" hypothesis is not supported at 0 mA.** The corner detector finds no pole-like/zero-like pair within one
  decade at 0 mA, 10 mOhm (the one 0.33u/500m pair at 117 kHz/21.5 kHz is a ripple-level detection far above crossover,
  disclosed but not meaningful), and `phase_dip.dip_present` is false (no >20 deg recovery of the continuous phase
  before the crossover region). The earlier non-monotone PM vs bleed / C_COMP behaviour is therefore not shown to be a
  doublet; this data points to a crossover-position effect against fixed low-frequency poles instead. This is an
  inference from magnitude slopes and phase, **not a pole/zero identification**: no rational fit or `pz` analysis was run.
- Node transfers from VREF at the 0.33 uF / 0 mA crossover: `EA_OUT` 46.3 dB, `EA_CZ` 46.2 dB (4.7 deg apart in
  phase), `VOUT` 12.6 dB. The R_CZ branch carries almost no voltage drop at crossover (the C_COMP impedance is ~4 MOhm
  there vs R_CZ = 0.3 MOhm), i.e. the designed R_CZ-C_COMP zero (~3.5 kHz) is not yet active at 0 mA crossover. That
  explains why one-factor C_COMP changes did little at 0 mA (#324) and shows why only a much larger R_CZ can act there.
- Ambiguity kept honest: the ~79 Hz corner is not attributed to a single element. Its position changed with R_CZ in
  the lever-B run (section 4), so it is not purely the pass-gate/EA output pole; and `ea_d1`/`ea_tail` contribution
  numbers in `tables.md` are single-frequency phase changes, not an attribution of phase to nodes.

## 3. Levers (at most two), why each can act at light load

- **A: tail current (`M_TAIL` W x2).** Hypothesis: the EA output pole scales with tail current while the crossover scales
  weaker, so more tail current should improve 0 mA PM. Cost is counted: Iq +4.84 uA at every load.
- **B: R_CZ x16 (zero near ~220 Hz, i.e. near the 0 mA crossover).** From the node evidence above: the stock zero is
  ~12x above the 0.33 uF crossover, so only a much larger R_CZ (C_COMP unchanged, no current) can bring phase lead to
  where the 0 mA crossover sits. x16 was chosen to put the zero at about the 0.33 uF crossover; no other multiplier
  was tried (a different multiplier is a follow-up, see section 6).

## 4. Results, tt / 27 C / 3.30 V (full tables: `tables.md`; PM deg, `F` = below 45)

| leg | baseline | A: tail x2 | B: R_CZ x16 |
|---|---|---|---|
| 0.33u 0 mA (ESR 0 / 10m / 500m) | 19.7 F / 19.7 F / 19.7 F | 25.6 F x3 | **65.0 x3** |
| 4.7u 0 mA (ESR 0 / 10m / 500m) | 53.1 / 53.1 / 53.2 | 65.8 x3 | 60.1 x3 |
| 0.33u 1 mA | 82.6 | 74.4 | **9.6 F** |
| 4.7u 1 mA | 51.9 | 56.3 | **30.9 F** |
| 0.33u 50 mA | 40.5 F | 32.4 F | **10.5 F** |
| 4.7u 50 mA | 83.3 | 75.1 | **10.9 F** |
| Iq 0 / 1 / 50 mA (uA) | 13.87 / 14.55 / 27.60 | 18.71 / 19.39 / 32.44 | 13.87 / 14.55 / 27.60 |

GM (worst over crossings) stays >= 15.7 dB for A and >= 11.3 dB for B at every leg; every GM crossing is finite. No
missing crossing occurred in any of the 30 loop-gain legs, so no leg is excused as infinite margin.

- **A is rejected**: it does not repair 0.33 uF at 0 mA (25.6 deg), it worsens both 50 mA points, and its full-load
  Iq (32.44 uA) exceeds the 30 uA target while adding 4.8 uA (35%) at no load.
- **B (PROVISIONAL, local-only pending a fleet re-run) shows the 0 mA failure is repairable by a passive, zero-Iq change**: both capacitance endpoints and all three
  ratified ESR values pass PM >= 45 and GM >= 10 dB at 0 mA. But it wrecks the loaded legs: 1 mA and 50 mA PM drops
  to 9.6-30.9 deg (4.7 uF at 1 and 50 mA passed in the baseline). A fixed R_CZ x16 is therefore not adoptable.
- Paired transient (`runs/base_lt_tt` vs `runs/rcz16_lt_tt`, same session, bounds peak <= 0.15 V, recovery <= 20 us):
  B introduces **no new bound violation and no worsened violation** (13 improved violations, 0 new). The baseline
  already violates 0.33 uF undershoot (0.192 V) and every recovery bound; B reduces most of them (e.g. rise recovery
  96.7 -> 48.5 us, 4.7 uF fall recovery 607 -> 94 us) but also adds rising-edge overshoot (0 -> 0.134 V at 0.33 uF /
  10 mOhm, still < 0.15 V) -- a disclosed behavioural change, not a regression of a bound. The transient at 1 <-> 50 mA
  does not exercise the 0 mA state and the PM collapse at 1/50 mA means the ring/settling behaviour is
  not demonstrated beyond this one condition. Transient shape at the other PVT corners is untested.

## 5. Recommendation: **REVISE** (neither lever advances alone)

- Lever A (tail current): **reject** -- insufficient at 0.33 uF, over-budget Iq.
- Lever B (large R_CZ): **revise, PROVISIONAL** (local multi-leg deck run as an exception after the preflight failed;
  pending a fleet re-run) -- the mechanism is confirmed (a zero placed at the 0 mA crossover repairs the 0 mA
  margin on both endpoints and ESR boundaries at zero Iq) but it must act only at light load, and must not regress
  1 mA / 50 mA, where the stock R_CZ (and the #349/#324 smaller-R_CZ results) are right. This points to a
  **load-dependent R_CZ**, the opposite polarity of the #349 switch (large R_CZ at light load, ~0.5x at heavy load),
  not to a retuned fixed value. The 1 mA legs show a fixed intermediate value cannot serve both.
- Machine verdicts in `tables.md` (`lightload_extract.verdict`): A reject, B revise.
- Open and not claimed: whether a sense signal exists that is still discriminating at 0 vs 1 mA (a few tens of uA of
  pass current) and costs less than the Iq headroom (30 - 13.87 = ~16 uA at no load, but only ~2.4 uA at 50 mA/tt and
  none at ff/125 C per #324); whether the transition region (0-1 mA) is stable; PVT behaviour of the large poly resistor.

## 6. PROVISIONAL qualification handoff (nothing here certifies the window)

**PROVISIONAL until a fleet re-run.** This handoff rests on the lever-B screen, which is local-only evidence from a
multi-leg deck run as an exception after the batch preflight failed (section 1). It is not just "a bounded result":
the first step of any follow-up is to re-run the `runs/rcz16_tt` and `runs/rcz16_lt_tt` legs (and the baseline
pair) through the batch path and confirm or revise the numbers in section 4 before building on them.

A follow-up (design) issue should: (1) wait for a compatible `batch-preflight.py` result (exit 0) before any grid,
and re-run the lever-B legs above on the fleet;
(2) specify a load-adaptive R_CZ whose light-load state (< ~0.1 mA, to be scanned) approaches the x16 value and whose
loaded state keeps today's or a smaller R_CZ, with its sense/gate current counted in Iq at 0 mA and 50 mA at tt and
at ff/125 C; (3) run, through `klt sim` corners, baseline vs candidate over the full 45-point PVT matrix and the
18-leg (#338) grid plus load steps between 0 and 1 mA; (4) run the transient at each PVT point; (5) rebaseline if #357
changes the circuit; (6) leave the full qualification to #231.

## Files

- `lightload_probe.py` (driver), `lightload_extract.py` (phase-dip, slope-corner, transient-regression and verdict
  helpers; pure python), `compare.py` (writes `tables.md`), `tables.md`, `batch-preflight.txt`, `hashes.sha256`
  (sha256 of every committed file in this directory except itself; `__pycache__` is not committed or
  listed), `runs/<run-id>/{result.json,deck.spice,netlist.raw.spice,
  netlist.edited.spice,ngspice.log,.spiceinit,resp_leg*.txt}` (`resp_leg*.txt` = raw complex responses: frequency, then
  Re/Im of T and of each of 6 node transfers).
- Tests: `sim/tests/test_lightload_365.py` (16 headless tests: slope corners, doublet pairing, phase dip, parse width,
  transient bound regression classification, verdict never advancing on missing/untested/invalid data).
- Reproduce one run: `python3 -I lightload_probe.py --outdir <dir> --run-id X --process tt --temp 27 --supply 3.3
  [--tail-scale S] [--rcz-scale S] [--ccomp-scale S] [--bench load-transient]` (one invocation at a time).
- Tool friction: none requiring a klayout-tools issue (in-repo harness, xschem and ngspice only). The batch
  version mismatch is already tracked (klayout-tools#2948 per the preflight docstring).
