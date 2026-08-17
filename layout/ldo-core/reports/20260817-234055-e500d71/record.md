# LDO core layout record: 20260817-234055-e500d71

Placed floorplan skeleton for the sky130 LDO's core regulation loop (issue #15), one `klt gen` block per active device in `design/ldo_3v3in_1v8out.sch` (issue #14). **Not** an extraction/LVS-verified result -- inter-block routing and LVS are explicitly out of scope here, see `layout/ldo-core/floorplan.md`.

## Overall verdict: PASS

- [x] DRC on the composed ldo-core floorplan is clean
- [x] Every schematic active device has exactly one placed klt gen block

## Flow

1. `layout/bin/gen-ldo-blocks.py` runs `klt gen mos_array`/`klt gen res_array` once per schematic device (13 MOS + 2 resistor blocks covering all 4 resistor instances = 15 blocks total), computes an explicit row-packed floorplan (see `layout/ldo-core/floorplan.md`), and runs `klt gen-compose` to place every block into one composed GDS.
2. `klt drc ldo_core.gds --deck sky130`

## Composed cell

- Cell name: `ldo_core`
- Block count: 15
- Composed bbox (um): {'x0': 0.0, 'y0': 0.0, 'x1': 1500.84, 'y1': 214.20000000000002}
- Composed size: 1500.84um x 214.20um

### Floorplan rows (bottom to top)

| Row | Blocks | y_base (um) | height (um) | width (um) |
| --- | --- | --- | --- | --- |
| bias_resistor | R_BIAS | 0.00 | 0.42 | 1500.84 |
| fb_resistor | R_FB | 20.42 | 0.42 | 906.20 |
| bias_enable | M_BIASN1, M_ENN, M_BIASN2, M_BIASP1, M_ENP2 | 40.84 | 11.12 | 30.22 |
| error_amp | M_TAIL, M_IN1, M_IN2, M_MIR1, M_MIR2, M_ENN2, M_ENP | 71.96 | 21.12 | 51.02 |
| output_pass | M_PASS | 113.08 | 101.12 | 23.72 |

## Results

| Stage | Status | Detail |
| --- | --- | --- |
| DRC | clean | violation_count=0 |

**Extraction/LVS not run here** -- issue #17's job. `layout/README.md`'s "Known klt-deck limitations" section documents two caveats a future LVS reference netlist needs to account for (no NMOS substrate-tap extraction, no voltage-flavor distinction on MOS devices).

## Known gap: `C_COMP` not drawn

The schematic's Miller compensation cap (`C_COMP`, MiM, `2p`, itself a placeholder value pending DR-002) has no corresponding `klt gen` device generator at this repo's pinned `klt` commit -- see `layout/ldo-core/floorplan.md`'s "Known gap" section and https://github.com/2AMLogic/klayout-tools/issues/1117 (filed per CLAUDE.md's friction protocol).

## Provenance

- Record ID: `20260817-234055-e500d71`
- `klt` version: `klt 0.2.0` (pinned commit, see `layout/requirements.txt`)
- KLayout engine version: `0.30.10`
- PDK: `sky130A`, `open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b`
- PDK pin cross-check: compare `version` above against `sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself enforce the pin (unlike `sim/bin/corner-run.py`), consistent with `layout/README.md`'s trivial-cell flow.
- Schematic freshness: `design/ldo_3v3in_1v8out.sch` as of commit `de276ad` (see `design/README.md`'s own Freshness note).
- Repo state: `e500d71072c02f1e39a3cabe4e0793e8a997609c` on `feature/issue-16` (dirty)

## Links

- [`floorplan.json`](floorplan.json) -- the resolved row-packing this run produced
- [`compose.request.json`](compose.request.json), [`compose.json`](compose.json)
- [`ldo_core.gds`](ldo_core.gds) -- the composed layout
- [`drc.json`](drc.json)
- `gen.<device>.json` / `<device>.gds` -- per-device `klt gen` report and standalone cell, one pair per schematic device
- [`report.md`](report.md) -- `klt report --format github-summary` rendering of `drc.json`

