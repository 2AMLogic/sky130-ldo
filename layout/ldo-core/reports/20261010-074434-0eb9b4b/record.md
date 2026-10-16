# LDO core area record: 20261010-074434-0eb9b4b

Measures the routed `ldo_core` layout against the ratified Area row (`spec/target-spec.md`: < 0.1 mm^2 total core area, pass FET included, excluding pads and sealring), issue #236. The target is unchanged; this record reports where the current layout stands against it.

## Overall verdict: FAIL

- Core footprint: 2451.870 um x 183.870 um = 450825.3 um^2 = **0.450825 mm^2**
- Limit: 0.1 mm^2, strict (`area < limit` passes; exactly the limit fails)
- Ratio to limit: 4.51x

## Measured artifact (content-pinned)

- Routed GDS: `layout/ldo-core/reports/20261010-074336-0eb9b4b/ldo_core.gds` (layout record `20261010-074336-0eb9b4b`, the `LATEST` DRC record when this was minted)
- SHA-256: `80f98681debd11e46c0a9fdb4fd307314db07198dbc485b31973ba2d5531c726`
- Cell: `ldo_core`; database unit 0.001 um (from the stream's UNITS record)
- Bounding box (um): (-0.190, -23.160) to (2451.680, 160.710)

## Geometry convention

Top-cell flattened bounding rectangle over all layers/datatypes (hierarchy, SREF/AREF transforms and path widths included; TEXT and NODE excluded); area = width x height in um^2 converted to mm^2 from the stream's own UNITS record; PASS iff area < 0.1 mm^2 (strict).

Details: the whole instantiated hierarchy counts (routing, rails, taps, well and marker layers, and the pass device); a bounding rectangle is conservative because it charges empty corners and the routing channel to the block; TEXT labels are excluded; PATH shapes grow by half their width; a non-Manhattan transform can only over-count. The core cell contains no pads or sealring, so nothing further is carved out for the row's exclusion clause. This is a measurement of the current routed layout, not a statement about what a compacted floorplan could reach -- compaction is a separate task.

## Independent cross-check

`{"tool": "klt 0.6.0+g040f3406b485", "command": "klt stats <gds> --format json", "bbox_width_um": "2451.87", "bbox_height_um": "183.87", "status": "agrees", "tolerance_um": "0.002"}`

## Freshness

`measurements/build_characterization_report.py` compares this record's GDS SHA-256 with the current routed GDS named by `layout/ldo-core/reports/LATEST`. A re-routed layout makes this record STALE until a new area record is minted (this one is never edited).

## Reproduce

```bash
python3 layout/bin/render-ldo-area-record.py
```

Provenance: repo state `0eb9b4bbdd763572d4e717010c3904cc31db630d`.
