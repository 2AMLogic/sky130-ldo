# Issue #705 campaign, as executed (paired legs; base and cand submitted as
# two batch legs at a time). Host: shared dispatch worker; every multi-corner
# leg goes through `klt sim --backend batch` (run_batch sets
# batch.capacity_wait_s in the request, plus the caller-side fleet-cap retry;
# mc_pair passes --wait-for-capacity 600). The only local work is netlisting
# (one headless xschem per bench) and grading -- no local ngspice grid.
set -e
cd "$(dirname "$0")"

# 0. batch-runner compatibility preflight (issue #356 probe)
python3 ../../../bin/batch-preflight.py

# 1. overlay verification at the pinned commit (submits nothing)
python3 -B campaign.py verify-overlay

# 2. startup grid: 45 corners x 12 cold-enable legs per DUT (one scalar-tran
#    batch request per supply x leg, waveform artifacts returned and graded)
python3 -B campaign.py startup-base &
python3 -B campaign.py startup-cand &
wait

# 3. line regulation: 45 corners x 4 cold-start endpoints per DUT
python3 -B campaign.py line-base &
python3 -B campaign.py line-cand &
wait

# 4. load regulation: 45 corners x 2 cold-start endpoints per DUT
python3 -B campaign.py load-base &
python3 -B campaign.py load-cand &
wait

# 5. mismatch accuracy: 200 mismatch-only draws per DUT, same base seed
#    (mc-run.py request builder, klt sim --backend batch)
python3 -B mc_pair.py base &
python3 -B mc_pair.py cand &
wait

# 6. paired tables + verdict.json
python3 -B analyze.py
