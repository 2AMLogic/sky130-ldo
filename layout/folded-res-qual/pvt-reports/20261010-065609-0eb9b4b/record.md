# Folded-resistor PVT / mismatch qualification -- record 20261010-065609-0eb9b4b

Issue #263. Isolated passive devices only (PDK resistor model chains plus the measured li1 joint resistance). **Not** a full-core compliance claim and not a layout record. The matrix, the equivalence criterion (unchanged from #253) and the mismatch gates M1/M2 were committed in `layout/folded-res-qual/pvt/matrix.json` before any run.

## Status: BLOCKED

```
det: klt sim --backend batch failed (rc 4): 63 units failed: batch job klt-sim-0d2e93937003 finished 'failed' (job command exited 87): the job's klt reported: the fleet runner runs klt 0.5.0 but the submitting client is 0.7.0+g8eec069c7576 -- the request was not run (update the runner image or use a compatible client)
```

No local fallback was run (host rule: grids go to the batch fleet). The matrix and request files in this directory are the supportable deliverable; **no segment-count recommendation is made from this record.**
