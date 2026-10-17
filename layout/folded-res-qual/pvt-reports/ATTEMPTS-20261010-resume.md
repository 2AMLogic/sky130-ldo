# #263 resume attempts, 2026-10-10 (append-only)

All runs batch-only (`KLT_SIM_BACKEND=batch`), no local grid.

| record | client | result |
|---|---|---|
| 20261010-053334-24f4faf | klt 0.6.0, .meas form | det batch job klt-sim-e47f924ea292: 63/63 pass (raw `det.report.json`). Session killed by a daemon version roll before the MC request and summary; no summary.json. |
| 20261010-065609-0eb9b4b | klt 0.7.0 | BLOCKED: fleet runner klt 0.5.0, all 63 units `batch_runner_version_mismatch` (job klt-sim-0d2e93937003). |
| 20261010-065704-0eb9b4b | klt 0.6.0, .meas form | det batch job klt-sim-9ba5cf558fc7: 63/63 pass (raw `det.report.json`). Run was cut off by a tool timeout before MC; no summary.json. |
| 20261010-070658-0eb9b4b | klt 0.6.0, .meas form | BLOCKED: no capacity in any of the 30 pools after 3 attempts. |

The seeded-mismatch (Monte Carlo) request has not completed in any attempt, so gates M1/M2
are unevaluated and no segment-count recommendation or no-qualified-candidate verdict is made.
The raw deterministic reports are kept as evidence only; they have not been analysed against the gates.
Re-run `python3 layout/bin/run-folded-res-pvt.py` once the fleet runner matches the client and has capacity.

## 2026-10-16 attempt (append-only)

| record | client | result |
|---|---|---|
| 20261016-232214-f75b799 | klt 0.6.0, .meas form | det batch job klt-sim-d2357cebc786: 63/63 pass (raw `det.report.json`, 209 s). MC batch job klt-sim-020e3593f469 (one 3000-unit request): fleet job timeout at 3604 s (`exit_code 124`), all 3000 units errored (`mc.report.json.gz`). No summary.json; no gate evaluated. The timeout implies ~3.3 s per unit per slot, so a single 3000-unit job needs ~2.7 h. Next attempt shards MC per process section (5 x 600 units, each ~35 min); seed and n are unchanged. |

## 2026-10-17 attempt (append-only)

| record | client | result |
|---|---|---|
| 20261017-002843-ec09282 | klt 0.6.0, .meas form | det batch job klt-sim-b76e6b9561f9: 63/63 pass (395 s), raw `det.report.json` kept. MC sharded per process section (`mc-{tt,ss,ff,hh,ll}_mm.request.json`, 5 x 600 units). The `tt_mm` shard was submitted to the batch fleet at 00:36 UTC; the driver and its klt client then exited at about 01:15 UTC with no MC report written and no `summary.json` (the previous builder session ended while the client was waiting; no exit code was captured). No gate evaluated; no local fallback was run. Re-run `python3 layout/bin/run-folded-res-pvt.py` from a session that can wait ~3 h for five shards. |

## 2026-10-17 second attempt: async submit (append-only)

The five MC shards of record 20261017-002843-ec09282 were submitted with `klt sim --backend batch --submit-only`
(host klt, request files unchanged) so job ids survive a killed session; results are collected later with `--attach`.

| shard | batch job | launched (UTC) | request sha256 |
|---|---|---|---|
| tt_mm | klt-sim-4f36cb8f4b25 | 2026-10-17T01:52:16Z | a0bbd23ca53444bc11ab14ae06ec51d31c34304c5fcdac05be462be92e79cb98 |
| ss_mm | klt-sim-d41aeddd4798 | 2026-10-17T01:52:38Z | c2479a30f5147e0873b611347c153aadbf1e8dcf650594a4c7db6a5a0f3ab97c |
| ff_mm | klt-sim-fbb24b3a5c80 | 2026-10-17T01:52:55Z | d43837f1461f2b7a426aad9f16a63453cc4b658173919777b605e73a0d3aa853 |
| hh_mm | klt-sim-7c4e4b516200 | 2026-10-17T01:53:13Z | 0d8c9afc54a32f6fcba1fac3ee2c1a97201714f92fc1fd5c94764aa38f1e2ef0 |
| ll_mm | klt-sim-63f01180686b | 2026-10-17T01:53:30Z | 32a4601758f9f23fc411bf726d83f763a342877ec33c2bdb14b13f46dbe05a06 |

## 2026-10-17 collected: COMPLETE record (append-only)

| record | client | result |
|---|---|---|
| 20261017-031511-76e0ba72 | klt 0.7.1.dev (runner 0.7.0, match) | `run-folded-res-pvt.py --resume-from 20261017-002843-ec09282` re-attached (`--attach`) to the five shard jobs above, all `exit_code 0`, 600 units each (843-1137 s), and reused that record's raw 63/63 det report. summary.json status COMPLETE; all gates evaluated. Verdict: R_BIAS no qualified fold (n4 passes the deterministic band at +0.2226 % but fails M2, sigma ratio 1.13 at n=200 draws/point); R_FB_A qualified through N=6. Control R_BIAS N=16 correctly NOT EQUIVALENT. Caveat: M2 sigma ratios use n=200 per point (predeclared), so the ratio's sampling error is roughly 5 %. |
