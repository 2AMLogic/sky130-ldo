# `sim/thermal-regen-cmp/` — standalone regenerative thermal comparator (issue #229)

**Development evidence only.** One process corner (`tt`), one supply (3.30 V),
one device-temperature axis. It is **not** PVT qualification (that belongs to the
verification child of #131) and it does **not** prove DR-005's `>= 150 °C`
worst-corner trip floor: the trip/reset temperatures below are properties of the
`tt`/3.30 V sense and reference stacks (which this issue did not change), and
the worst-case floor must be re-established over PVT when the comparator is
integrated.

Parent: #131. Design cell: `design/thermal_cmp_regen.sch` (topology, sizing and
integration interface: `design/README.md`, "Regenerative thermal comparator
(#229)").

## Layout

| Path | What |
|---|---|
| `testbench/tb_thermal_regen_cmp.sch` | DUT + replicas of the bias generator and the #29 CTAT sense/reference (sizes copied unchanged from `design/ldo_3v3in_1v8out.sch`) + the real `M_TSHUT` into a 100 kohm / 2.4 V stub standing in for `EA_OUT` |
| `run_demo.py` | The bounded driver (strictly serial `ngspice -b`, no pools/background jobs/corner grid) |
| `records/<UTC>-<sha>-<tag>/` | Append-only evidence: `result.json`, `netlist.spice`, per-run `runs/*.log` + decimated `runs/*.csv` |

Records are never overwritten: the runner refuses to reuse a record directory
(`mkdir(exist_ok=False)`); a later run mints a new directory.

## Command

```bash
python3 sim/thermal-regen-cmp/run_demo.py --tag dev1     # ~50 serial ngspice runs, ~20-25 s each
```

Tools: ngspice-46, XSCHEM 3.4.7, Python 3.12.3; PDK `sky130A`, open_pdks
`c6d73a35f524070e85faff4a6a9eef49553ebc2b` (the `sim/pdk.json` pin; installed
commit equals the pin); `sim/spiceinit` settings; `.lib ... tt`; transient
`tran 400n 110u uic`.

## Method (what "independent" means here)

ngspice has no time-varying `TEMP`, so the staircase is a set of separate
transient runs, each at a fixed `.temp`, each starting from its own seeded state
(sim/README.md #189: a `dc temp` continuation cannot discriminate hysteresis):

| Scenario | Seed | Question |
|---|---|---|
| `cold` | `uic`, every node 0, `EN` rises 2-3 us: the latch starts from the symmetric `EN=0` state (both latch nodes at `VIN`) | which state does the cell resolve to at this temperature? |
| `hot` | EN high, a physical -0.25 V disturbance in series with the sense (looks hotter) for 20-40 us, then **removed** | is the *tripped* state held with zero disturbance at this temperature? (`T_reset`) |
| `cold_exc` | the same with +0.25 V (looks colder) | is the *untripped* state held? (`T_trip`) |
| `en` | `hot`, then `EN` dropped 61-75 us and re-enabled | is state latched across an EN cycle? |

`T_reset` (falling) = lowest temperature at which the tripped state is still
held; `T_trip` (rising) = highest temperature at which the untripped state is
still held; both located by 10 °C coarse grid then bisection to a 0.3125 °C
bracket. Hysteresis = `T_trip - T_reset`.

## Result: record `20261008-130329-19114c8-dev1` (tt / 3.30 V)

| Quantity | Value |
|---|---|
| `T_reset` (falling) | 158.906 °C, bracket [158.75, 159.062] |
| `T_trip` (rising) | 172.031 °C, bracket [171.875, 172.188] |
| **Hysteresis** | **13.1 °C** (bracket-limited range 12.8 to 13.4 °C); the existing grid resolution is 2 °C |
| Solver diagnostics (`singular matrix`, `gmin/source stepping failed`, `Transient op`, ...) | **0 of 50 runs** |
| Disturbance-amplitude robustness | both flip points identical for 0.15 / 0.25 / 0.40 V seeds (state held one bracket end, lost at the other) |
| EN disable/re-enable | `TS_CMP` = `VIN` (not tripped) while EN low at every temperature; re-enable returns the state the input demands (untripped at 151/158 °C, tripped at 161-180 °C) — nothing latched across the cycle |
| Cold start (EN rise from `uic`-zero) | untripped at 151/158 °C, tripped at 161-180 °C |

Temperature points actually run: coarse 130..190 °C in 10 °C steps (both seeds),
bisection points 150-172.19 °C, amplitude checks at the bracket ends, cold/EN
points 151, 158, 161, 165, 170, 173, 180 °C; see `result.json` `runs`.

### Uncertainty and limitations (stated, not hidden)

- **Bracket**: +-0.16 °C on each flip point from the bisection tolerance, so the
  hysteresis is 13.1 +- 0.3 °C from that source alone. The positive window is
  ~6x the 2 °C grid.
- **Observation window**: state is judged at one instant (59 us, ~19 us after
  the disturbance ends); slow drift beyond that is not excluded. The `uic`
  transient lets the sense nodes settle in <= 9 us (see CSVs).
- **Timestep**: runs use `tran 400n`; an early probe at 100 n of the 150 °C
  `hot` point agreed (tripped under disturbance, untripped held). No systematic
  time-step sweep of the thresholds was done.
- **Seeding is by a physical input disturbance for the `hot`/`cold_exc` states**,
  and by the symmetric EN-rise for `cold`. The cold-start *does not* locate
  `T_trip`: inside the window (≈159-172 °C) an EN-rise resolves to the
  **tripped** state (the safe side), so cold start follows `T_reset`, not
  `T_trip`. A true "resume from a cold die" is far below the window and
  unaffected.
- **Sense/reference tempco** (≈4 mV/°C of `TS_SNS - TS_REF` near the window, from the record's
  `sns_minus_ref_mv_at_hold`: +29.4 mV at 158 °C, -30.9 mV at 173 °C) converts
  the comparator's input window to °C. The window is ≈ 53 mV of input
  difference (reset near +26 mV, trip near -27 mV of `TS_SNS - TS_REF`, read
  off the same run values); it converts to ~13 °C only at that tempco and will
  move with the sense/reference over process/supply/temperature.
- `repo.dirty` is `true` in `result.json`: the record was minted before the
  commit that adds it (the cell, bench and runner are in that same commit).
- Single corner. Mismatch (comparator offset moves both thresholds together;
  the window is set by the width ratio) and the other corners are not covered.
- The absolute trip (~172 °C rising) is set by the unchanged #29 sense/reference
  stacks at `tt`/3.30 V, and is *above* the DR-005 150 °C nominal; this issue
  does not re-centre it.
