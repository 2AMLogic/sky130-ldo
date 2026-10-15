# Commands that produced this record (issue #341)

Run from the repository root of the `feature/issue-341` worktree. `PDK_ROOT=$HOME/.volare`.

```bash
R=layout/cap-study/20261015-195114-5a3705a
python3 sim/bin/batch-preflight.py                                          # ACCEPTED, exit 0
python3 layout/cap-study/run-cap-study.py prepare --record $R
python3 layout/cap-study/run-cap-study.py op      --record $R               # 5/6 passed; v3.63_50ma refused (fleet instance cap); driver stopped
python3 layout/cap-study/run-cap-study.py cv      --record $R --backend batch   # refused (fleet instance cap)
python3 layout/cap-study/run-cap-study.py matrix  --record $R
```

No `op-local` or `cv --backend local` runs were made.
