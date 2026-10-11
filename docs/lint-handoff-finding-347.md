# Finding: pinned Ruff F failures reaching Judge (#311, #312, #344)

Issue #347. Verdict: **no enforcement change in this repo.**

## Was the pinned command run on the submitted tree?

Evidence from the PR histories and bodies:

| PR | Rejection class | Lint fix landed | Validation cited in the PR body |
|----|-----------------|-----------------|----------------------------------|
| #311 | F541 | 2026-10-10 21:14:54Z, after the first push (21:13:10Z) | `unittest discover` only |
| #312 | F401 | 21:15:49Z, after the first push (21:14:21Z) | "Full sim/tests suite passes" only |
| #344 | F841 in `sim/loop-gain/diagnostics/.../mitigation_probe.py` | 10:54:40Z, after the first push (10:52:54Z) | `python3 -I sim/tests/test_mitigation_probe.py` only |

In all three, the first-submitted tree was never linted. The PR bodies report
unit-test passes and no `npm run test:lint-py` result. The most likely cause is
that a targeted unit-test pass was taken as sufficient. This is an inference
from PR text and commit order, not a log of what each Builder ran.

## Were diagnostic Python files covered?

Yes. `test:lint-py` is
`git ls-files -z -- '*.py' ':!.loom' ':!.claude' | xargs -0 uvx --from ruff==0.17.0 ruff check --isolated --no-cache --select F`.
It covers every tracked `*.py`, including `sim/**/diagnostics/**`
(`mitigation_probe.py` is tracked). Only the managed `.loom/` and `.claude/`
trees are excluded. The command's scope is not what failed.

## Synthetic confirmation (no simulations)

Three `git add -N` fixtures under a scratch `sim/_fx/` (removed afterward):
`import os`, `print(f"hello")`, and a function with an unused local.
`npm run test:lint-py` reported F401, F541 and F841, one per fixture, and exited
non-zero ("Found 3 errors"). The existing command catches all three classes.

## Where the prompt lives

`.loom/roles/builder.md` (about line 1099) and `.loom/roles/doctor.md` are
tracked here, but their history is "chore: resync installed Loom surfaces". They
are installed copies of upstream Loom (rjwalters/loom), and a local edit would be
overwritten on the next resync. The Builder sentence already requires running the
project's linter before committing. Any wording change belongs upstream. The
upstream point would be that a unit-test pass is not lint validation, and that
the lint command should be named in the PR's validation list. No local copy was
edited.

## Repo-local note

The repo-native check is `npm run check:ci`, which includes `npm run test`, which
includes `test:lint-py`. Running it, not a targeted `unittest` run, is what
validates lint before handoff.
