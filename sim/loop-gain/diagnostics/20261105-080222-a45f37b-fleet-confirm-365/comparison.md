# Fleet confirmation of the #365 baseline / R_CZ x16 loop-gain pairs (issue #370)

tt / 27 C / 3.30 V only (the corner #365 ran); one `klt sim --backend batch` request per design x leg, no local fallback. Fleet = klt batch runner; PM/GM/fc via klt `transfer` metrics of v(fb)/v(lg_den) (LG = v(fb)/(1-v(fb))). #365 = its provisional local run (committed `result.json`). Agreement bands are +-2 deg PM and +-2 dB GM (a reporting convenience, not a spec bound).

| design | leg | fleet PM | #365 PM | fleet GM | #365 GM | fleet fc (Hz) | #365 fc | status | PM>=45 | GM>=10 | PM/GM agree |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 0.33u/10m/0mA | 19.7 | 19.7 | 68.6 | 68.6 | 282 | 282 | pass | FAIL | PASS | yes |
| baseline | 4.7u/10m/0mA | 53.1 | 53.1 | 72.4 | 72.4 | 60 | 60 | pass | PASS | PASS | yes |
| baseline | 0.33u/0/0mA | 19.7 | 19.7 | 68.6 | 68.6 | 282 | 282 | pass | FAIL | PASS | yes |
| baseline | 4.7u/0/0mA | 53.1 | 53.1 | 72.3 | 72.3 | 60 | 60 | pass | PASS | PASS | yes |
| baseline | 0.33u/500m/0mA | 19.7 | 19.7 | 69.0 | 69.0 | 282 | 282 | pass | FAIL | PASS | yes |
| baseline | 4.7u/500m/0mA | 53.2 | 53.2 | 73.6 | 73.6 | 60 | 60 | pass | PASS | PASS | yes |
| baseline | 0.33u/10m/1mA | 82.5 | 82.6 | 28.1 | 28.2 | 30915 | 30915 | pass | PASS | PASS | yes |
| baseline | 4.7u/10m/1mA | 51.9 | 51.9 | 42.0 | 42.0 | 3221 | 3221 | pass | PASS | PASS | yes |
| baseline | 0.33u/10m/50mA | 40.1 | 40.5 | 17.2 | 17.5 | 178117 | 178142 | pass | FAIL | PASS | yes |
| baseline | 4.7u/10m/50mA | 83.2 | 83.3 | 30.1 | 30.2 | 24470 | 24470 | pass | PASS | PASS | yes |
| rcz16 | 0.33u/10m/0mA | 65.0 | 65.0 | 49.0 | 49.0 | 332 | 332 | pass | PASS | PASS | yes |
| rcz16 | 4.7u/10m/0mA | 60.1 | 60.1 | 62.4 | 62.5 | 56 | 56 | pass | PASS | PASS | yes |
| rcz16 | 0.33u/0/0mA | 65.0 | 65.0 | 49.0 | 49.0 | 332 | 332 | pass | PASS | PASS | yes |
| rcz16 | 4.7u/0/0mA | 60.1 | 60.1 | 62.4 | 62.4 | 56 | 56 | pass | PASS | PASS | yes |
| rcz16 | 0.33u/500m/0mA | 65.0 | 65.0 | 49.4 | 49.4 | 332 | 332 | pass | PASS | PASS | yes |
| rcz16 | 4.7u/500m/0mA | 60.1 | 60.1 | 64.6 | 64.7 | 56 | 56 | pass | PASS | PASS | yes |
| rcz16 | 0.33u/10m/1mA | 9.5 | 9.6 | 15.8 | 16.2 | 58967 | 59061 | pass | FAIL | PASS | yes |
| rcz16 | 4.7u/10m/1mA | 30.8 | 30.9 | 29.0 | 29.1 | 14573 | 14593 | pass | FAIL | PASS | yes |
| rcz16 | 0.33u/10m/50mA | 10.1 | 10.5 | 10.7 | 11.3 | 175855 | 176088 | pass | FAIL | PASS | yes |
| rcz16 | 4.7u/10m/50mA | 10.8 | 10.9 | 20.0 | 20.4 | 46777 | 46835 | pass | FAIL | PASS | yes |

Submit errors: 0

All 20 pairs present and agreeing with #365 within the bands: **yes**.
