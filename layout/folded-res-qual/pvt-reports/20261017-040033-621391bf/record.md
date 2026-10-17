# Folded-resistor PVT / mismatch qualification -- record 20261017-040033-621391bf

Issue #263. Isolated passive devices only (PDK resistor model chains plus the measured li1 joint resistance). **Not** a full-core compliance claim and not a layout record. The matrix, the equivalence criterion (unchanged from #253) and the mismatch gates M1/M2 were committed in `layout/folded-res-qual/pvt/matrix.json` before any run.

## Status: BLOCKED

```
det: klt sim --backend batch failed (rc 4): 63 units failed: batch job klt-sim-29583e39102c finished 'failed' without a usable report: job command exited 2 [output recovery: collected outputs hold no report.json (/tmp/klt-batch-outputs-uqyhvz9d/report.json) -- the job command never wrote its report; collected outputs hold no stderr.log -- see harness.log under the job's S3 prefix] [engine log unavailable: no ngspice.log/xyce.log in the collected outputs (engine logs are retrieved only when artifacts are kept)]
```

No local fallback was run (host rule: grids go to the batch fleet). The matrix and request files in this directory are the supportable deliverable; **no segment-count recommendation is made from this record.**
