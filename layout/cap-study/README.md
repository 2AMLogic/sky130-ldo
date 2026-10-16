# `layout/cap-study/`: capacitor-implementation comparison (issue #319)

This is a **study**, not a layout. It compares on-chip ways to build the schematic's four capacitors against the ratified Area row. The capacitors are C_COMP 150 pF, C_SS 10 pF, C_CL 1 pF and C_TS 1 pF, 162 pF in total. The options are:

- one-level MiM;
- stacked MiM;
- the PDK's fixed vertical-parallel-plate (`cap_vpp`) cells;
- MOS varactors (`cap_var_lvt` / `cap_var_hvt`).

It extends #246 (`layout/area-study/`), which evaluated MiM density only. It cites #254 (`layout/cap-rail-demo/`), which drew stacked MiM over the rails, and does not redo that work. It changes nothing in `spec/`, `design/` or any other record.

Records: `<YYYYMMDD-HHMMSS>-<sha>/`. Each one holds:

- `record.md` (read first);
- `matrix.json` (machine-readable; schema in the record);
- `commands.md`;
- `op/`: the operating-point requests, the netlist snapshot and every `klt sim` run;
- `cv/`: the varactor C(V) netlist and runs.

Records are append-only: a new measurement mints a new directory.

| Record | Outcome | Note |
|---|---|---|
| [`20261011-094917-7a4e0cc`](20261011-094917-7a4e0cc/record.md) | (c) inconclusive/unmeasured | Operating-point matrix 2/126 measured. The batch runner refuses this client (klayout-tools#2948). Completion is tracked in #341 |
| [`20261015-195114-5a3705a`](20261015-195114-5a3705a/record.md) | (c) inconclusive/unmeasured | Operating-point matrix 105/126 measured on the batch fleet. `v3.63_50ma` and the C(V) grid were refused by the fleet instance cap. Completion is tracked in #341 |
| [`20261016-004951-5125358`](20261016-004951-5125358/record.md) | (c) inconclusive/unmeasured | Operating-point matrix 126/126 and varactor C(V) 21/21 measured on the batch fleet. Open: one-level MiM mixed placement, varactor footprint, C_SS outside the varactor SOA. Completes the measurement runs tracked in #341 |

## Rules the study follows

- Each number comes from one of three places: a named file and parameter in the pinned PDK (`sim/pdk.json`: `sky130A` at open_pdks `c6d73a35...`), a `klt sim` run in the record, or an existing repo record. Anything else is the literal `unmeasured`, with a reason.
- Area accounting is the #246 convention: drawn area = C / density, and "beside" = scenario D + drawn area. A keep-out-inclusive figure appears only where a drawn record measured one.
- Capacitor terminals come from the xschem netlist, which identifies terminals only. Their voltages come from cold-start settled operating points (#171) through `klt sim`. A multi-corner grid goes to `--backend batch`. Only single units run locally, and a failed batch job is recorded, never replaced by a local grid.
- Outcomes:
  - (a) needs a fitting option **and** complete evidence;
  - (b) "no option fits" needs complete evidence with every option failing on a lower bound;
  - otherwise the outcome is (c). Missing data never becomes (b).

## Run

```bash
export PDK_ROOT=$HOME/.volare          # the pinned volare install
R=layout/cap-study/$(date -u +%Y%m%d-%H%M%S)-$(git rev-parse --short=7 HEAD)
python3 layout/cap-study/run-cap-study.py prepare  --record $R
python3 layout/cap-study/run-cap-study.py op       --record $R      # batch fleet
python3 layout/cap-study/run-cap-study.py cv       --record $R --backend batch
python3 layout/cap-study/run-cap-study.py matrix   --record $R
python3 -m unittest discover --start-directory layout/tests --pattern 'test_cap_study_*.py'
```

`_cap_study.py` holds the pure, stdlib-only parsing and arithmetic, and it is unit-tested. `run-cap-study.py` is the driver. It needs `xschem`, `klt` and the PDK, and nothing is installed host-wide.
