# Issue #692 campaign, as executed (sequential legs; two batch legs at a time).
# Host: shared dispatch worker; every multi-corner leg goes through
# `klt sim --backend batch` (run_klt_batch sets batch.capacity_wait_s in the
# request, plus the caller-side fleet-cap retry). The only local ngspice runs
# are the single-corner syntax/debug probes, which are one `ngspice -b` each.
set -e
cd "$(dirname "$0")"

# 0. batch-runner compatibility preflight (issue #356 probe; job klt-sim-a75577b5c820)
python3 ../../../bin/batch-preflight.py

# 1. local single-corner syntax probe of the extra meas cards + deck-level .save
#    cards at tt / 27 C / 3.30 V, both variants (not campaign evidence)
python3 -B campaign.py syntax-probe            # rev1
python3 -B campaign.py syntax-probe --rev 2    # rev2 (after REV[2] was added)

# 2. tt / 27 C / 3.30 V pair reproduction, batch (two single-corner requests)
python3 -B campaign.py pair

# 3. full 45-point matrices, batch (one request per supply per leg;
#    iq legs are one request per supply x endpoint)
python3 -B campaign.py dropout-base &
python3 -B campaign.py dropout-cand &
wait
python3 -B campaign.py iq-base &
python3 -B campaign.py iq-cand &
wait

# 4. local single-corner debug probes for the two non-regulating iq corners
#    (one ngspice -b each; traces retained)
python3 -B debug_probe.py --variant cand --process ss --temp 125 --supply 3.30 --run-id dbg-ss125c-cand
python3 -B debug_probe.py --variant cand --process ff --temp 27 --supply 2.97 --run-id dbg-ff27c-cand
python3 -B debug_probe.py --variant cand --rev 2 --process tt --temp 27 --supply 3.30 --run-id dbg-tt27c-cand-r2

# 5. the ONE evidence-driven revision (candidate.py REV[2]: NTAIL 12/3 -> 7/2),
#    then both benches again over the full matrix, batch
python3 -B campaign.py dropout-cand-r2 &
python3 -B campaign.py iq-cand-r2 &
wait

# 6. paired tables + verdict.json
python3 -B analyze.py
