#!/bin/sh
# Issue #357 -- declared command sequence (ALL local, strictly sequential, one ngspice at a time;
# no grid, no pool, no background jobs, no Monte Carlo, no fleet). Run from this directory.
# Electrical condition everywhere: process tt, 27 C. Supplies: 3.30 V (nominal) and 2.10 V
# (the candidate's claimed low-VIN operating condition = 1.8 V + 0.300 V dropout target).
# Thermal runs impose the DEVICE temperature listed per run (.temp) -- that is the thermal
# stimulus, declared separately from the 27 C electrical screening condition.
# Declared tolerances (analyze.py): repeat |d dropout| <= 0.5 mV, |d EA_OUT@x| <= 1.0 mV;
# VREF settled DC current <= 1 nA; thermal pass-off witness |Id(M_PASS)| < 1 uA at 90 us.
set -e
P="python3 -B probe.py"

# --- 0. sizing derivation (isolated device benches, DC, tt/27C) ---
python3 -B sizing.py vref-vi        runs/sz01_vref_vi
python3 -B sizing.py headroom-rev0  runs/sz02_headroom_rev0

# --- 1. tool-version anchor: #339's probe0 deck replayed verbatim ---
python3 -B replay339.py probe0 d00_replay339_probe0

# --- 2. dropout pair + repeat pair (dropout-vs-load manifest deck, VIN start 3.30 V) ---
$P --bench dropout --variant base           --supply 3.3 --run-id d01_base
$P --bench dropout --variant cand --rev 0   --supply 3.3 --run-id d02_cand_r0
$P --bench dropout --variant base           --supply 3.3 --run-id d03_base_rep
$P --bench dropout --variant cand --rev 0   --supply 3.3 --run-id d04_cand_r0_rep
python3 -B analyze.py pair   runs/d01_base runs/d02_cand_r0 > pair_dropout_r0.txt
python3 -B analyze.py repeat runs/d01_base runs/d03_base_rep        > repeat_base.txt     || true
python3 -B analyze.py repeat runs/d02_cand_r0 runs/d04_cand_r0_rep  > repeat_cand_r0.txt  || true

# --- 3. protection / Iq / EN, paired, existing bench contracts verbatim ---
$P --bench current-limit   --variant base         --supply 3.3 --run-id cl_base_3p3
$P --bench current-limit   --variant cand --rev 0 --supply 3.3 --run-id cl_cand_r0_3p3
$P --bench current-limit   --variant base         --supply 2.1 --run-id cl_base_2p1
$P --bench current-limit   --variant cand --rev 0 --supply 2.1 --run-id cl_cand_r0_2p1
$P --bench iq              --variant base         --supply 3.3 --run-id iq_base_3p3
$P --bench iq              --variant cand --rev 0 --supply 3.3 --run-id iq_cand_r0_3p3
$P --bench iq              --variant base         --supply 2.1 --run-id iq_base_2p1
$P --bench iq              --variant cand --rev 0 --supply 2.1 --run-id iq_cand_r0_2p1
$P --bench enable-shutdown --variant base         --supply 3.3 --run-id en_base_3p3
$P --bench enable-shutdown --variant cand --rev 0 --supply 3.3 --run-id en_cand_r0_3p3

# --- 4. thermal two-state (run_hysteresis.py stimulus), imposed device temperatures ---
#   27 C cold start (must stay untripped); 150 C (below the recorded tt/3.3 V reset ~159 C:
#   forced trip must NOT hold, untripped must hold); 166 C (inside the recorded window: both
#   states hold); 185 C (above the recorded trip ~172 C: forced trip holds, untripped does not);
#   `en` at 185 C: EN dropped and re-enabled from the tripped state.
$P --bench thermal --variant base         --supply 3.3 --temp 27  --scenario cold     --run-id th_base_3p3_027_cold
$P --bench thermal --variant base         --supply 3.3 --temp 150 --scenario cold_exc --run-id th_base_3p3_150_coldexc
$P --bench thermal --variant base         --supply 3.3 --temp 150 --scenario hot      --run-id th_base_3p3_150_hot
$P --bench thermal --variant base         --supply 3.3 --temp 166 --scenario cold_exc --run-id th_base_3p3_166_coldexc
$P --bench thermal --variant base         --supply 3.3 --temp 166 --scenario hot      --run-id th_base_3p3_166_hot
$P --bench thermal --variant base         --supply 3.3 --temp 185 --scenario cold_exc --run-id th_base_3p3_185_coldexc
$P --bench thermal --variant base         --supply 3.3 --temp 185 --scenario hot      --run-id th_base_3p3_185_hot
$P --bench thermal --variant base         --supply 3.3 --temp 185 --scenario en       --run-id th_base_3p3_185_en
$P --bench thermal --variant cand --rev 0 --supply 3.3 --temp 27  --scenario cold     --run-id th_cand_r0_3p3_027_cold
$P --bench thermal --variant cand --rev 0 --supply 3.3 --temp 150 --scenario cold_exc --run-id th_cand_r0_3p3_150_coldexc
$P --bench thermal --variant cand --rev 0 --supply 3.3 --temp 150 --scenario hot      --run-id th_cand_r0_3p3_150_hot
$P --bench thermal --variant cand --rev 0 --supply 3.3 --temp 166 --scenario cold_exc --run-id th_cand_r0_3p3_166_coldexc
$P --bench thermal --variant cand --rev 0 --supply 3.3 --temp 166 --scenario hot      --run-id th_cand_r0_3p3_166_hot
$P --bench thermal --variant cand --rev 0 --supply 3.3 --temp 185 --scenario cold_exc --run-id th_cand_r0_3p3_185_coldexc
$P --bench thermal --variant cand --rev 0 --supply 3.3 --temp 185 --scenario hot      --run-id th_cand_r0_3p3_185_hot
$P --bench thermal --variant cand --rev 0 --supply 3.3 --temp 185 --scenario en       --run-id th_cand_r0_3p3_185_en
$P --bench thermal --variant base         --supply 2.1 --temp 27  --scenario cold     --run-id th_base_2p1_027_cold
$P --bench thermal --variant base         --supply 2.1 --temp 150 --scenario cold_exc --run-id th_base_2p1_150_coldexc
$P --bench thermal --variant base         --supply 2.1 --temp 150 --scenario hot      --run-id th_base_2p1_150_hot
$P --bench thermal --variant base         --supply 2.1 --temp 166 --scenario cold_exc --run-id th_base_2p1_166_coldexc
$P --bench thermal --variant base         --supply 2.1 --temp 166 --scenario hot      --run-id th_base_2p1_166_hot
$P --bench thermal --variant base         --supply 2.1 --temp 185 --scenario cold_exc --run-id th_base_2p1_185_coldexc
$P --bench thermal --variant base         --supply 2.1 --temp 185 --scenario hot      --run-id th_base_2p1_185_hot
$P --bench thermal --variant base         --supply 2.1 --temp 185 --scenario en       --run-id th_base_2p1_185_en
$P --bench thermal --variant cand --rev 0 --supply 2.1 --temp 27  --scenario cold     --run-id th_cand_r0_2p1_027_cold
$P --bench thermal --variant cand --rev 0 --supply 2.1 --temp 150 --scenario cold_exc --run-id th_cand_r0_2p1_150_coldexc
$P --bench thermal --variant cand --rev 0 --supply 2.1 --temp 150 --scenario hot      --run-id th_cand_r0_2p1_150_hot
$P --bench thermal --variant cand --rev 0 --supply 2.1 --temp 166 --scenario cold_exc --run-id th_cand_r0_2p1_166_coldexc
$P --bench thermal --variant cand --rev 0 --supply 2.1 --temp 166 --scenario hot      --run-id th_cand_r0_2p1_166_hot
$P --bench thermal --variant cand --rev 0 --supply 2.1 --temp 185 --scenario cold_exc --run-id th_cand_r0_2p1_185_coldexc
$P --bench thermal --variant cand --rev 0 --supply 2.1 --temp 185 --scenario hot      --run-id th_cand_r0_2p1_185_hot
$P --bench thermal --variant cand --rev 0 --supply 2.1 --temp 185 --scenario en       --run-id th_cand_r0_2p1_185_en

# --- 4b. as-executed deviations from the list above (retained, append-only) ---
#   d01_base: INVALID attempt -- instrumentation requested i(iload), which ngspice rejects
#   ("no such function as i"), so no wrdata was written. Fixed in probe.py; rerun as d01b_base.
#   inv01_en_cand_r0_merged: investigation copy of runs/en_cand_r0_3p3/deck.spice with `echo`
#   leg markers, run once as `ngspice -b deck.spice > ngspice.merged.log 2>&1` to locate the
#   singular-matrix warning (enable-shutdown leg 1, disabled state).

# --- 5. rev 1 (the single evidence-driven revision; README section 5) ---
python3 -B sizing.py headroom-rev1  runs/sz03_headroom_rev1   # (run with L=805, PBN 1.75, NBR 2.0 -- rejected)
python3 -B sizing.py headroom-rev1  runs/sz04_headroom_rev1   # (L=550, PBN 1.75, NBR 2.0 -- rejected)
python3 -B sizing.py headroom-rev1  runs/sz05_headroom_rev1   # (L=550, PBN 1.0,  NBR 1.5 -- rejected)
python3 -B sizing.py headroom-rev1  runs/sz06_headroom_rev1   # (L=550, PBN 1.75, NBR 2.5 -- locked rev1)
#   (sz03-sz05 were generated by earlier states of candidate.py REV[1]; only sz06 matches the
#    committed table. Their decks are retained verbatim in runs/.)
$P --bench dropout --variant cand --rev 1   --supply 3.3 --run-id d05_cand_r1
$P --bench dropout --variant cand --rev 1   --supply 3.3 --run-id d06_cand_r1_rep
python3 -B analyze.py pair   runs/d01b_base runs/d05_cand_r1 > pair_dropout_r1.txt
python3 -B analyze.py repeat runs/d05_cand_r1 runs/d06_cand_r1_rep  > repeat_cand_r1.txt  || true
$P --bench current-limit   --variant cand --rev 1 --supply 3.3 --run-id cl_cand_r1_3p3
$P --bench current-limit   --variant cand --rev 1 --supply 2.1 --run-id cl_cand_r1_2p1
$P --bench iq              --variant cand --rev 1 --supply 3.3 --run-id iq_cand_r1_3p3
$P --bench iq              --variant cand --rev 1 --supply 2.1 --run-id iq_cand_r1_2p1
$P --bench enable-shutdown --variant cand --rev 1 --supply 3.3 --run-id en_cand_r1_3p3
$P --bench thermal --variant cand --rev 1 --supply 3.3 --temp 27  --scenario cold     --run-id th_cand_r1_3p3_027_cold
$P --bench thermal --variant cand --rev 1 --supply 3.3 --temp 150 --scenario cold_exc --run-id th_cand_r1_3p3_150_coldexc
$P --bench thermal --variant cand --rev 1 --supply 3.3 --temp 150 --scenario hot      --run-id th_cand_r1_3p3_150_hot
$P --bench thermal --variant cand --rev 1 --supply 3.3 --temp 166 --scenario cold_exc --run-id th_cand_r1_3p3_166_coldexc
$P --bench thermal --variant cand --rev 1 --supply 3.3 --temp 166 --scenario hot      --run-id th_cand_r1_3p3_166_hot
$P --bench thermal --variant cand --rev 1 --supply 3.3 --temp 185 --scenario cold_exc --run-id th_cand_r1_3p3_185_coldexc
$P --bench thermal --variant cand --rev 1 --supply 3.3 --temp 185 --scenario hot      --run-id th_cand_r1_3p3_185_hot
$P --bench thermal --variant cand --rev 1 --supply 3.3 --temp 185 --scenario en       --run-id th_cand_r1_3p3_185_en
$P --bench thermal --variant cand --rev 1 --supply 2.1 --temp 27  --scenario cold     --run-id th_cand_r1_2p1_027_cold
$P --bench thermal --variant cand --rev 1 --supply 2.1 --temp 150 --scenario cold_exc --run-id th_cand_r1_2p1_150_coldexc
$P --bench thermal --variant cand --rev 1 --supply 2.1 --temp 150 --scenario hot      --run-id th_cand_r1_2p1_150_hot
$P --bench thermal --variant cand --rev 1 --supply 2.1 --temp 166 --scenario cold_exc --run-id th_cand_r1_2p1_166_coldexc
$P --bench thermal --variant cand --rev 1 --supply 2.1 --temp 166 --scenario hot      --run-id th_cand_r1_2p1_166_hot
$P --bench thermal --variant cand --rev 1 --supply 2.1 --temp 185 --scenario cold_exc --run-id th_cand_r1_2p1_185_coldexc
$P --bench thermal --variant cand --rev 1 --supply 2.1 --temp 185 --scenario hot      --run-id th_cand_r1_2p1_185_hot
$P --bench thermal --variant cand --rev 1 --supply 2.1 --temp 185 --scenario en       --run-id th_cand_r1_2p1_185_en

# --- 5b. thermal actuator witness (review rework of the pass-off witness; README section 4) ---
#   thermal-settled bench: same testbench, loaded (RLOAD 1.8 k), 150 C, tt. `ctl` = no disturbance
#   (settled, conducting, untripped control); `trip` = +0.5 uA TS_SNS sink, sampled inside the pulse.
#   Attempt 1 (ths_*): stop 1000 us, pulse 800..840 us, sample 835 us (settle ref 785 us). The 2.1 V
#   controls were still starting up (VOUT +44 / +60 mV over the settle window) -> NOT DEMONSTRATED
#   at 2.1 V; retained. Attempt 2 (thl_*): stop 1500 us, pulse 1300..1340 us, sample 1335 us (ref 1285 us).
#   Attempt 1 was run with S_STOP_US/S_PULSE_*/T_S_* = 1000/800/840/785/835 (the previous probe.py constants).
for v in "cand --rev 1:cand_r1" "base:base"; do
  var=${v%%:*}; tag=${v##*:}
  for s in 3.3 2.1; do
    q=$(echo $s | tr . p)
    for sc in ctl trip; do
      $P --bench thermal-settled --variant $var --supply $s --temp 150 --scenario $sc --run-id thl_${tag}_${q}_150_$sc
    done
  done
done

# --- 6. tables ---
python3 -B summarize.py > summary.txt
