# Folded-resistor PVT / mismatch qualification -- record 20261010-050239-509c688

Issue #263. Isolated passive devices only (PDK resistor model chains plus the measured li1 joint resistance). **Not** a full-core compliance claim and not a layout record. The matrix, the equivalence criterion (unchanged from #253) and the mismatch gates M1/M2 were committed in `layout/folded-res-qual/pvt/matrix.json` before any run.

## Status: BLOCKED

```
det: klt sim --backend batch failed (rc 1): {
  "schema_version": 1,
  "error": {
    "command": "sim",
    "message": "batch backend failed: batch-fleet-provision.sh launch failed (exit 1): error: no capacity in any of the 30 pools after 3 attempt(s) \u2014 this is the capacity-refusal case, and it is now visible instead of silent"
  }
}
```

No local fallback was run (host rule: grids go to the batch fleet). The matrix and request files in this directory are the supportable deliverable; **no segment-count recommendation is made from this record.**
