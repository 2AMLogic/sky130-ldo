# Issue #704 campaign, as executed (sequential stages; two submit workers each).
# Host: shared dispatch worker; every multi-corner leg goes through
# `klt sim --backend batch` (the requests carry batch.capacity_wait_s = 3 h and
# the fc/corner-run submit paths add a caller-side fleet-cap retry). The only
# local ngspice runs are the single-corner syntax/debug probes (one
# `ngspice -b` per bench per variant), which are not campaign evidence.
set -e
cd "$(dirname "$0")"

# 0. batch-runner compatibility preflight (job klt-sim-75351f414433, match)
python3 ../../../bin/batch-preflight.py

# 1. local single-corner syntax probes of both variants on all three benches
#    (loop-gain at its 0.33u/10m/50mA leg, psrr at 1mA, load-step full deck)
python3 -B campaign.py syntax-probe

# 2. loop-gain: the issue's pinned 42-condition tt/27C/3.30V grid + the
#    7-load op gate, one variant at a time (43 single-corner requests each)
python3 -B campaign.py loop base
python3 -B campaign.py loop rev2

# 3. PSRR: full 45-corner matrix x {1mA,50mA} at the bench's own load network,
#    plus one op-gate request per supply (9 requests per variant)
python3 -B campaign.py psrr base
python3 -B campaign.py psrr rev2

# 4. load step: the 6-leg window grid at the manifest's quick_subset PVT
#    (18 single-corner requests per variant)
python3 -B campaign.py loadstep base
python3 -B campaign.py loadstep rev2

# 5. loop-gain extraction check on rev2's VREF-driven bias: the worst legs of
#    step 2 re-run with XM_VRF's gate on an internal DC-1.2V/AC-0 source
python3 -B campaign.py loop-decoupled --legs c47-esr0-10uA c033-esr0-0mA c033-esr0-50mA c47-esr0-0mA c033-esr0-1mA c47-esr500m-30uA

# 6. paired tables + verdict.json
python3 -B analyze.py
