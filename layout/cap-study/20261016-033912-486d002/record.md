# Probe: non-reproducible cold-start point at ff / 27 C / 2.97 V / 50 mA

Issue #398. **Measurement probe only.** Nothing in `spec/`, `design/` or any prior record changes. The records `20261015-195114-5a3705a/` and `20261016-004951-5125358/` are untouched (append-only).

**Finding: (c) not resolved, with evidence.** The point has one settled state under every local variant tried. That state matches the later batch record. The earlier record's state could not be reproduced, and no cause was found.

## Provenance

- Minted 2026-10-16 on top of `486d002`. Deck: `op/requests/v2.97_50ma.spice` of `20261016-004951-5125358` (byte-identical copy at `probe/v2.97_50ma.spice`). Request: that record's `v2.97_50ma.json` narrowed to `ff` / 27 C, same measurements, same `.spiceinit` text, `tran 10u 200m uic`.
- Both batch records ran this deck through the same `ngspice-46` and runner klt `0.7.0`. Their generated `corner.cir` files differ only in the include path (checked with `diff`).
- Local probe: `klt sim --backend local`, one corner per run, `ngspice-42`, `PDK_ROOT=$HOME/.volare` (sky130A). klt warned that a second sky130A install exists under `~/.ciel`; it read `$PDK_ROOT`, as the warning says.
- No grid was run. Nine single-corner local runs in total.

## Result

Plate voltages are `C_CL = VIN - CL_CMP`, `C_COMP = VOUT - EA_CZ` (the `terminals.json` convention of the cap study).

| Run | VOUT (V) | EA_CZ (V) | CL_CMP (V) | C_CL (V) | C_COMP (V) |
|---|---|---|---|---|---|
| batch `20261015-195114-5a3705a` | 2.71690 | 1.52072 | 2.12748 | 0.84252 | 1.19618 |
| batch `20261016-004951-5125358` | 1.79879 | 1.65917 | 2.89077 | 0.07923 | 0.13962 |
| local default, run 1 | 1.798794 | 1.659172 | 2.890772 | 0.07923 | 0.13962 |
| local default, run 2 | 1.798794 | 1.659172 | 2.890772 | 0.07923 | 0.13962 |
| local `reltol=1e-4 abstol=1e-13 vntol=1e-7` | 1.798794 | 1.659172 | 2.890772 | 0.07923 | 0.13962 |
| local `method=gear` | 1.798794 | 1.659172 | 2.890772 | 0.07923 | 0.13962 |
| local `tran 1u 200m uic` | 1.798794 | 1.659172 | 2.890772 | 0.07923 | 0.13962 |
| local `.ic v(vout)=2.7` | 1.798794 | 1.659172 | 2.890772 | 0.07923 | 0.13962 |
| local `.ic v(vout)=0.5` | 1.798794 | 1.659172 | 2.890772 | 0.07923 | 0.13962 |
| local `.ic` set to the earlier record's state (VOUT, EA_CZ, CL_CMP, TS_CMP, SS) | 1.798794 | 1.659172 | 2.890772 | 0.07923 | 0.13962 |

All nine local runs agree to the printed precision. Starting the transient from the earlier record's state still settles to the later one. The other probe nodes (`v_ss`, `v_ts_cmp`) agree as well; see each `ngspice.log`.

At the other two temperatures of `ff / 2.97 V / 50 mA` the earlier record has `v_vout` = 1.79846 V (125 C) and 1.79895 V (-40 C), the regulated value. The 2.717 V reading at 27 C is the odd one out in its own row of corners.

## Finding

**(c) not resolved.** What the evidence supports:

- The deck has one settled state under default settings, tighter tolerances, a different integration method, a finer timestep and three different initial conditions. There is no sign of a second stable solution.
- That state is the one in `20261016-004951-5125358` and is the regulated one (VOUT about 1.8 V). The cap study's `matrix.json` for that record therefore already carries it.
- The earlier record's value (VOUT 2.717 V) was not reproduced and no cause is named. The decks, runner version and ngspice version were the same, so a deck mismatch is ruled out. A cause tied to the fleet instance (hardware, scratch state) is possible but untested and untestable from this host.
- Limits of this probe: local ngspice is 42, the batch runs used 46, and one corner was probed. A fleet-side repeat of the single point was not made, because a one-point repeat is not a local run and no fleet repeat was requested.

## Effect on the cap study

None of the verdicts change. The C_CL and C_COMP plate voltages of both readings stay inside the varactor SOA (|V| <= 2.301 V), and the later record already reports the lower maxima. If a reader prefers the conservative bound, the earlier record's higher C_CL (0.84252 V) and C_COMP (1.19618 V) at this corner remain recorded there. The outcome class and Area-row evidence are unchanged. No decision record is needed.

## Tool gap

None found. `klt sim` ran each single corner locally; the tolerance, method and initial-condition variants were made by editing the netlist, which is the intended route. No `klayout-tools` issue was filed.
