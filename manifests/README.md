# manifests/ — artifact-store manifests

New `sim/` campaign bytes (JSON twin, netlist snapshot, per-corner logs, batch
request/response files) are not committed. `sim/bin/corner-run.py`,
`mc-run.py` and `yield-run.py` push them to the artifact store with
`klt artifact put` and commit only:

- `manifests/artifacts/<bench>-<run-id>.manifest.json` — one entry per object
  (`name`, `size`, `sha256`, `uri` starting `artifact:`), and
- `sim/<bench>/records/<run-id>.md` — the human summary, which lists
  name/size/sha256 per stored object.

Verify a run's objects with `klt artifact verify manifests/artifacts/<file>`.

Configuration is environment-only: `$KLT_ARTIFACT_BROKER` (no default; never
commit it, and no bucket/account identifier belongs in this repo). A runner
fails closed — nonzero exit, nothing written under `manifests/` or `sim/` — when
the variable is unset, `klt artifact put` is missing (needs klayout-tools
>= `7e3561f`), or the broker is unreachable. There is no fallback that commits
bytes. Staging happens under the git-ignored `sim/.work/`.

`scripts/check_artifact_manifests.py` (part of `npm run check:ci`) rejects a
manifest `uri` that is not `artifact:` and any committed `sim/` or `layout/`
file whose bytes also appear in a manifest. Evidence committed before issue #436
stays where it is (append-only).

Not yet covered: the `layout/` flows, and feeding a store-only MC response to
`yield-run.py` (its source samples must still be a committed file).
