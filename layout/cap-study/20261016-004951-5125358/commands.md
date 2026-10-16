# Commands that produced this record (issue #341)

Run from the repository root of the `feature/issue-341` worktree. `PDK_ROOT=$HOME/.volare`.

```bash
R=layout/cap-study/20261016-004951-5125358
python3 sim/bin/batch-preflight.py                                          # ACCEPTED, exit 0 (job klt-sim-e86ce5fc2f5a)
python3 layout/cap-study/run-cap-study.py prepare --record $R
python3 layout/cap-study/run-cap-study.py op      --record $R               # 6/6 passed (resumed twice, see record.md)
python3 layout/cap-study/run-cap-study.py cv      --record $R --backend batch   # passed
python3 layout/cap-study/run-cap-study.py matrix  --record $R
```

No `op-local` or `cv --backend local` runs were made.
