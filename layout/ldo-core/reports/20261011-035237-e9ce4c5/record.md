# LDO core area record: 20261011-035237-e9ce4c5

Measures the routed `ldo_core` layout against the ratified Area row (`spec/target-spec.md`: < 0.1 mm^2 total core area, pass FET included, excluding pads and sealring), issue #236. The target is unchanged; this record reports where the current layout stands against it.

## Overall verdict: FAIL

- Core footprint: 2451.870 um x 183.860 um = 450800.8 um^2 = **0.450801 mm^2**
- Limit: 0.1 mm^2, strict (`area < limit` passes; exactly the limit fails)
- Ratio to limit: 4.51x

## Measured artifact (content-pinned)

- Routed GDS: `layout/ldo-core/reports/20261010-045715-e17e713/ldo_core.gds` (layout record `20261010-045715-e17e713`, the `LATEST` layout record when this was minted)
- SHA-256: `c9d35b881073201286313d4009cf281441bf897085a7cd88d95702c462310a74`
- Cell: `ldo_core`; database unit 0.001 um (from the stream's UNITS record)
- Bounding box (um): (-0.190, -23.150) to (2451.680, 160.710)

## Geometry convention

Top-cell flattened bounding rectangle over all layers/datatypes (hierarchy, SREF/AREF transforms and path widths included; TEXT and NODE excluded); area = width x height in um^2 converted to mm^2 from the stream's own UNITS record; PASS iff area < 0.1 mm^2 (strict).

Details: the whole instantiated hierarchy counts (routing, rails, taps, well and marker layers, and the pass device); a bounding rectangle is conservative because it charges empty corners and the routing channel to the block; TEXT labels are excluded; PATH shapes grow by half their width; a non-Manhattan transform can only over-count. The core cell contains no pads or sealring, so nothing further is carved out for the row's exclusion clause. This is a measurement of the current routed layout, not a statement about what a compacted floorplan could reach -- compaction is a separate task.

## Independent cross-check

`{"tool": "klt 0.7.0+g0d0312b30708", "command": "klt stats <gds> --format json", "bbox_width_um": "2451.87", "bbox_height_um": "183.86", "status": "agrees", "tolerance_um": "0.002"}`

## Coverage limitations (issue #318)

The measured footprint omits 4 schematic element(s) that are not drawn in this layout (C_COMP, C_CL, C_SS, C_TS). It is not evidence that a complete, capacitor-inclusive core meets the Area row.

- Drawn inventory (from `layout/ldo-core/reports/20261010-045715-e17e713/floorplan.json`): 48 MOS + 5 resistor blocks (53 blocks)
- Widest MOS (the pass device): `M_PASS` W_total 5000.0 um drawn as 50 x 100.0 um parallel units, L 0.5 um
- Not drawn: `C_COMP`, `C_CL`, `C_SS`, `C_TS` -- absent from both the layout and the LVS reference
- Official-deck DRC (`sky130A_mr.drc`) for this exact layout record (`layout/ldo-core/reports/20261010-045715-e17e713/record.md`): **FAIL** -- 15060 markers in 7 rule families; attribution is in that record. This area record does not change it.
- LVS: **STALE** -- `LATEST-LVS` record `20260924-221912-a947aa8` (status `match`) checked layout sha256 `3e7f504b56ea85cdd733ecf456650b6f08c72540ec4a6ad38b73f3a0369beb9a`, not the measured GDS. No LVS result covers this layout; its earlier verdict must not be read as current coverage.
- Standalone capacitor/rail demonstrator, cited separately: [`layout/cap-rail-demo/reports/20261010-033947-80bc87e/record.md`](../../../../layout/cap-rail-demo/reports/20261010-033947-80bc87e/record.md) -- standalone MiM-capacitor + supply-rail overlay; no MOS device, resistor or signal route drawn. Its results are about that demonstrator only and do not certify this core.

## Freshness

`measurements/build_characterization_report.py` compares this record's GDS SHA-256 with the current routed GDS named by `layout/ldo-core/reports/LATEST`. A re-routed layout makes this record STALE until a new area record is minted (this one is never edited).

## Reproduce

```bash
python3 layout/bin/render-ldo-area-record.py --gds layout/ldo-core/reports/20261010-045715-e17e713/ldo_core.gds
```

Provenance: repo state `e9ce4c58f0db9b32a0289749130423f9797de18e`.
