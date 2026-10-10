## Integrated regenerative comparator (#230)

Development evidence, tt / 3.30 V, `sim/thermal/hysteresis/20261008-190150-0275a8b-dev1` (append-only;
`run_hysteresis.py` refuses to reuse a record directory). Not PVT, not a
signoff claim.

**Why a staircase and not `dc temp`.** A DC continuation follows one branch and
cannot establish a window (#189; the pre-#230 record `20260926-095154-f6ab418`
read trip == reset at every corner). ngspice has no time-varying `TEMP`, so
`sim/thermal/run_hysteresis.py` runs 50 independent `tran 400n 170u uic` decks of
the **real LDO** bench `sim/thermal/testbench/tb_thermal_trip.sch`, each at a
fixed `.temp`, strictly serial (no pool, no grid, no background jobs):

| Scenario | Initial state, physically realised | Question |
|---|---|---|
| `cold` | every node 0, `EN` rises 2-3 us; latch starts from the symmetric `EN` = 0 state | what does a power-up resolve to at this T? |
| `hot` | `EN` high, `IX` = +0.5 uA sink at `xldo.TS_SNS` for 20-40 us (sense looks hotter, `TS_SNS` pulled to ~0.7 V), then removed | is the **tripped** state still held at 90 us with zero disturbance? -> `T_reset` |
| `cold_exc` | the same with -0.5 uA (looks colder) | is the **untripped** state still held? -> `T_trip` |
| `en` | `hot`, then `EN` low 101-115 us and re-enabled | state while disabled and after re-enable |

`T_reset` = lowest T at which the tripped state is held, `T_trip` = highest T
at which the untripped state is held; 10 C coarse grid, then bisection to a
0.3125 C bracket.

```bash
python3 sim/thermal/run_hysteresis.py --tag dev1      # ~50 runs, ~3 s each, ~3 min
```

| Quantity | Value |
|---|---|
| `T_reset` (falling) | 159.22 C, bracket [159.06, 159.38] |
| `T_trip` (rising) | 172.34 C, bracket [172.19, 172.50] |
| **Hysteresis** | **13.1 C** (12.8 to 13.4 C); old grid resolution 2 C |
| Solver diagnostics (`sim/bin` #171 gate plus `Error:`, `timestep too small`, `Transient op`) | 0 of 50 runs |
| Disturbance-amplitude robustness (0.25 / 0.5 / 1.0 uA, both signs) | both flip brackets identical |
| Reset | tripped state seeded at 150 C is released by 90 us (`hot` run at 130-150 C), at 160 C+ it holds |
| `EN` low (101-115 us) | `TS_CMP` = `VIN` (3.30 V) at 151-180 C; re-enable returns the state the input demands (untripped at 151/158 C, tripped at 161-180 C): nothing latched across the cycle |
| Cold start | untripped at 151/158 C, tripped at 161-180 C (an `EN` rise inside the window resolves to the safe, tripped side, so cold start tracks `T_reset`, not `T_trip`) |
| Clamp | tripped: `M_TSHUT` Vsg 3.297 V and `EA_OUT` 3.2999 V (= `VIN`, pass gate off); untripped: Vsg 0.05 V |

**Limitations, stated.**
- The window is short (170 us) so `VOUT` decays at the load RC (1.8 kOhm x 1 uF
  = 1.8 ms) rather than collapsing; the clamp is shown by `M_TSHUT`/`EA_OUT`, and
  the tripped `VOUT` decay rate matches the RC. The first ~microseconds of a
  `uic` start include a power-up inrush (VOUT briefly ~1 V) that is a feature
  of starting every node at 0, not of the clamp.
- The bench's `IC_SEED` `.nodeset` card is dropped by the runner for these `uic`
  runs (ngspice 42 treats it as an initial condition under `uic`, which would
  pre-charge `VOUT` to 1.8 V); the `dc temp` decks still use it.
- Observation is at one instant (90 us, 50 us after release); slow drift beyond
  that is not excluded. `tran` step 400 ns; no systematic time-step sweep of
  the flip points.
- Hysteresis in C scales with the sense/reference tempco (~4 mV/C) and the
  comparator width ratio; it will move over PVT. Mismatch not run.
- **Tool versions.** This record was produced on a dispatch worker with
  XSCHEM 3.4.4 and ngspice 42 rather than the 3.4.7 / 46 the earlier records
  name (`result.json` `tools`). XSCHEM 3.4.4 writes the sky130 symbols' raw
  `expr('...')` geometry templates that ngspice 42 cannot evaluate, so the runner
  evaluates them with the PDK symbol's own formulae (`eval_xschem_exprs`; 288
  substitutions, recorded). The numbers equal what 3.4.7 writes (checked against
  the committed snapshots). The result matches the standalone #229 record from
  the pinned toolchain to within 0.4 C; PVT work should still be re-run on the
  pinned toolchain. The same host difference makes the per-`sim/` Freshness
  column of `measurements/characterization.md` read STALE for every LDO bench
  even on an unmodified tree, which is why the rows below are listed from the
  schematic dependency and not only from that column.

### Stale artifacts caused by the schematic change (inventory for #231)

Nothing below was re-run or edited by #230 (records are append-only).

1. **Every `sim/` experiment that instantiates `design/ldo_3v3in_1v8out.sym`**
   (17): `current-limit`, `dropout-vs-load`, `enable-shutdown`,
   `ic-screen-125c-b`, `ic-screen-125c-c`, `ic-screen-125c-v`, `iq`,
   `line-regulation`, `load-regulation`, `load-transient`, `loop-gain`,
   `mc-ic-screen-a`, `mc-ic-screen-b`, `mc-output-accuracy`, `psrr-dc`,
   `startup`, `thermal`. Their netlist snapshots no longer match a live
   re-netlist. Rows of `measurements/characterization.md` that went
   `fresh` -> `STALE`: Output, Dropout, Line regulation, Load regulation, Load
   transient, PSRR, Thermal, Stability (Iq, Current limit, Startup, Enable were
   already STALE). `sim/thermal`'s experiment inputs also changed
   (`deck.params`), and its record is the one the new comparator affects most
   (trip/reset/hysteresis values are of the old comparator).
2. **`sim/pex-post-layout`** (schematic-side leg of the post-layout PEX
   compare) and **`sim/mc-ic-screen-*`/`ic-screen-*`** (screening, not signoff).
3. **Layout evidence for the old netlist:** DRC `layout/ldo-core/reports/20260924-221821-a947aa8`,
   LVS (`LATEST-LVS`, `20260924-221912-a947aa8`; its `reference.spice` still lists
   `M_TC*`/`M_TSHYS*`), ERC `20260930-221337-cbfbb54`, area `20261008-161046-f4fbb86`
   (routed-core area FAIL measurement), and the composed `ldo_core.gds`. The layout
   itself must be regenerated (`layout/bin/gen-ldo-blocks.py` derives devices from
   the netlist; the new `M_RC*` devices are placed, nothing is hard-coded) and
   DRC/LVS/ERC/area re-run; DRC/LVS rows read STALE in the regenerated report.
4. **Signoff:** `signoff/block-manifest.json` items 3, 4 (DRC, LVS) and 11 cite
   the layout records of item 3 above; their pins are unchanged and still
   hash-clean, but they describe the pre-#230 schematic. Only item 8's pin
   (`measurements/characterization.md`) was re-pinned, because that file was
   regenerated; `t1-tier-report.json` moved by that hash only (T1 stays 5/11).
5. **Derived documents:** the numbers in `design/README.md`'s #29/#69/#77/#91
   thermal text (old comparator), `spec`-facing claims quoting 150 C trip
   behaviour, and the `Iq` row (comparator branch current changed).
6. **Not stale, by construction:** `sim/thermal-regen-cmp` (standalone cell and
   its replica bench) and the `spec/` tables.

