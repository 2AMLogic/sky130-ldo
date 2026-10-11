# Issue #360 -- missing -180 deg crossings: diagnosis of the loop-gain GM scalar

Status: bounded diagnostic, **two single-condition local probes (tt / 27 C / 3.30 V), 3 legs each**. No spec row,
DR status, production schematic, production target or existing diagnostic is changed; the #349 / #338 evidence is
untouched and the invalid-to-no-pass classification stays as is. Nothing here qualifies the Stability window.

## 1. What was run (and what was not)

| run id | circuit | legs | where | ngspice |
|---|---|---|---|---|
| `runs/base_tt` | baseline | 4.7u/500m/1mA (reported missing), 4.7u/500m/50mA, 4.7u/10m/50mA | local, one `ngspice -b` | exit 0, no solver diagnostic |
| `runs/r1_tt` | #349 candidate R1 (`--ra-frac 0.5 --tap-w 6`) | same three | local, one `ngspice -b` | exit 0, no solver diagnostic |

Local use is the host-permitted "single corner debug probe" (15 s each). **No fleet job was submitted and the
ss/-40C/2.97 V and ff/125C/3.63 V conditions named in the #349 README section 3 were NOT re-run**: the driver is a
custom single-deck `ngspice -b`, and running the other conditions would be a multi-condition grid for the batch fleet.
So every conclusion below is for tt/27C/3.30V only; the missing results at ss and ff remain **unresolved (not
reproduced here)**. Reproduce further conditions with `crossing_probe.py --process ss --temp -40 --supply 2.97`
(etc.) as separate bounded invocations, or wrap the driver as a `klt sim` request when fleet access is arranged.

Control: leg 3 (4.7u/10m/50mA) has a finite GM in the existing scalar extraction; leg 2 (4.7u/500m/50mA) is finite
at baseline and missing under R1, as reported. Solver and regulation gates are the unchanged #349 `classify_ac`
(vout within window, no solver diagnostic); all six points pass those gates, so each `invalid` below is solely the
missing-crossing reason.

## 2. Sweep, convention, selection (per probe; all recorded in `result.json`)

- Sweep: `ac dec 30 0.01 Hz .. 1e12 Hz` (421 points); the production sweep stops at 1e9. Loop gain
  `T = v(fb)/(1-v(fb))` exactly as in the #349 deck; complex T saved per leg via `wrdata` (`resp_leg{1,2,3}.txt`,
  frequency, then Re, Im), operating point (vout, supply current) printed ahead of each AC.
- Phase convention: arg(T) in degrees, unwrapped continuous in f, first sample in (-180, 180]; PM = 180 + phase at
  the first falling 0 dB crossing; GM = -|T|dB at a crossing of the **negative real axis** (Im T changes sign with
  Re T < 0, equivalent to every odd multiple of 180 deg and independent of the unwrap branch).
- Crossing selection: first crossing (the repo's `cross=1` rule); `worst_gm_db` over all crossings and the count of
  crossings are also recorded. The original scalar `meas ... when lgph=-180 cross=1` is run in the same deck on the
  extended sweep for a like-for-like comparison (`legacy_gm_db`, `meas_gm`).
- Statuses (`crossing_extract.py`): `finite`, `multiple_crossings`, `truncated_range` (no crossing, but one just past
  the sweep end cannot be excluded), `absent_in_range`, `starts_past_180`, `no_unity_crossing`. Only the first two
  carry a GM number (`gm_supported`); every other status has `gm_db = None`. A missing GM is never mapped to infinity
  or PASS, and the pass flags are not emitted unless a crossing exists.

## 3. Results (tt/27C/3.30V; numbers from the saved responses)

| run | leg | #349 valid | status | PM (deg) @ fc | min phase (deg) @ f | phase @ 1e12 Hz | scalar GM (`meas`) | response GM |
|---|---|---|---|---|---|---|---|---|
| base | 4.7u/500m/1mA | no (GM missing) | absent_in_range | 54.37 @ 3.21 kHz | -133.7 @ 1.47 kHz | -52.2 | none | none |
| base | 4.7u/500m/50mA | yes | finite | 102.31 @ 23.5 kHz | unwrapped -412 | -412.2 | 50.68 dB | 57.05 dB (notch-like, see below) |
| base | 4.7u/10m/50mA | yes | finite | 83.26 @ 24.5 kHz | unwrapped -412 | -412.2 | 30.23 dB | 30.23 dB @ 250.5 kHz |
| R1 | 4.7u/500m/1mA | no | absent_in_range | 54.35 @ 3.21 kHz | -133.7 @ 1.47 kHz | -52.4 | none | none |
| R1 | 4.7u/500m/50mA | no (GM missing) | absent_in_range | 96.87 @ 12.4 kHz | -88.8 @ 0.79 kHz | -52.4 | none | none |
| R1 | 4.7u/10m/50mA | yes | finite | 88.64 @ 13.2 kHz | unwrapped -412 | -412.4 | 33.67 dB | 33.71 dB @ 277.4 kHz |

(DC loop gain 71.5 dB at 1 mA, 62.9 dB at 50 mA; PM numbers equal the #349 scalar PMs to the displayed digits.)

Findings, each scoped to tt/27C/3.30V and these three legs:

1. **Reproduced.** Baseline 4.7u/500m/1mA and R1 4.7u/500m/50mA have no -180 crossing, and the missing result is
   not a measurement artifact of the original 1e9 Hz limit: extending to 1e12 Hz and testing the negative real axis
   (not only `lgph = -180`) still finds none. The phase of these legs dips to -133.7 / -88.8 deg (ESR zero lifting
   the phase) and then settles back to -52 deg; the response never reaches the axis (see item 4 for the high-frequency region). Status: **extraction is not the cause; the
   absent crossing is a property of the simulated response over 0.01 Hz - 1 THz at this one condition.**
2. **The control legs differ qualitatively.** Legs with a finite GM reach the axis at 0.25 - 0.8 MHz, where the
   phase continues to -412 deg (~ -52 deg after one full turn); the missing legs never make that excursion. The
   existing scalar and the response-level extraction agree on which legs are missing (3 of 3 consistent).
3. **A numeric caveat on the scalar itself.** For base 4.7u/500m/50mA the crossing sits on a sharp feature (adjacent
   samples change phase by 123 deg, gain dips ~4 dB below the crossing value within two samples; `notch_like = true`). Interpolating across
   it gives 50.68 dB (log-f interpolation of gain, scalar `meas`) vs 57.05 dB (linear Re/Im interpolation); the
   value is interpolation-limited by ~6 dB. Smooth crossings agree to < 0.1 dB. Both are far above 10 dB, but any
   qualification claim should either refine the grid locally or quote the notch flag.
4. **High-frequency feed-through region.** For baseline 4.7u/500m/1mA the loop gain does not roll off
   monotonically: -27.2 dB at 1 MHz, -9.2 dB at 10 MHz, -8.9 dB at 100 MHz (phase -16 deg), -13.5 dB at 1 GHz,
   -25.8 dB at 1 THz (phase -52 deg). Such a gain re-rise with near-zero phase looks like a parasitic feed-through
   path in the linearised netlist (cause not investigated). In the saved data the phase stays far from -180 deg
   there, so it neither creates nor hides a crossing, but gain above 10 MHz is a model property and not
   interpreted. The upper decades of the 1e12 sweep are therefore of limited physical meaning; they were
   kept only to exclude a distant crossing.
5. **What is NOT established.** `absent_in_range` means no crossing in the inspected range of the simulated model.
   It is not evidence of unlimited margin, and it is not a pass: the ratified GM >= 10 dB cannot be demonstrated for
   these legs from this data. No margin is reported for them. The ss and ff results for the same legs are
   unresolved (section 1).

## 4. Extraction recommendation (for review; production grading unchanged)

1. Keep treating a missing crossing as **invalid / not graded**; report it as `absent_in_range` or
   `truncated_range` rather than a bare "missing".
2. Detect GM on the negative real axis of the saved complex response (immune to unwrap-branch dependence),
   record the sweep limits and the crossing count, and take `worst_gm_db` over all crossings when more than one
   exists (`first` remains the legacy `cross=1` selection).
3. Flag `notch_like` crossings and refine the local grid before quoting a number from them.
4. If a future rule wants to accept an absent crossing (e.g. "no axis crossing and |T| < 0 dB wherever phase
   is beyond -135 deg"), that is a new qualification rule: it needs its own review and decision record, with a
   phase-margin-like bound that does not rely on the sweep end. Not proposed or applied here.

Follow-up before full qualification: run the same three legs at ss/-40C/2.97V and ff/125C/3.63V (fleet), and
the 4.7u/500m/50mA R1 pair near the 3 mA transition, before any statement about those legs beyond tt.

## 5. Files and tests

- `crossing_probe.py` (driver; re-uses the #349 helpers read-only), `crossing_extract.py` (pure-python extraction).
- `runs/<id>/`: `deck.spice`, raw + edited netlists, `ngspice.log`, `resp_leg*.txt` (raw complex responses),
  `result.json` (inputs, hashes of driver/extractor/experiment/schematics/netlists/deck, PDK commit and tool versions).
  Provenance caveat: the recorded `on_baseline: false` means the installed ngspice (46) and xschem (3.4.7) differ from
  the declared 42 / 3.4.4, so absolute numbers carry that unquantified tool-version uncertainty.
- Evidence is append-only: `crossing_probe.py` refuses an existing run id.
- `sim/tests/test_missing_crossing_360.py`: synthetic finite-crossing, finite-passing, multiple-crossing,
  wrapped-phase, truncated-range and no-crossing fixtures plus the `wrdata` parser; no ngspice needed.
