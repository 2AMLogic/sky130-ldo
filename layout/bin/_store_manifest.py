"""The ONE read-side contract for the committed artifact-store manifests (issue #671).

Store-held evidence (the batch backend's record JSON twins and netlist
snapshots) is addressed by a committed `manifests/artifacts/*.manifest.json`
entry and fetched through `klt artifact get <manifest>#<name> -o -`, which
emits bytes only when their sha256 matches the entry's digest. Before this
module three trees each carried their own guarded manifest parse and/or
their own `klt artifact get` subprocess call, with drifted signatures and
error types, so a fix to the timeout or the error handling had to be made
in each. This module is the single place that answers both questions;
per-site lookup *policy* (a manifest named from its slug in one tree, a
glob over all manifests in another) stays with the caller.

Standard library only, so it runs under the repo's plain `python3` with no
`klayout`/`klt` install -- the same property `_digest.py` (beside which
this module lives) and `measurements/build_characterization_report.py`
rely on. Actually fetching bytes obviously needs a `klt` with store
access; reading manifests does not.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_FETCH_TIMEOUT_S = 120


class StoreFetchError(RuntimeError):
    """`klt artifact get` could not deliver the entry's bytes.

    One error type for every fetch failure -- missing `klt`, nonzero exit,
    timeout -- so a caller has exactly one thing to catch and wrap into its
    own report framing.
    """


def manifest_entries(path: Path) -> list[dict]:
    """A manifest's `entries` as a list of its objects; `[]` when unreadable.

    "Unreadable" is the union every caller must tolerate: missing file,
    undecodable JSON, JSON that is not an object, an `entries` that is not
    a list -- plus non-object members dropped from an otherwise readable
    list. An empty result is the caller's signal to report the evidence as
    unverified / not held rather than crash; a caller that wants to say
    *why* names the path in its own message.
    """
    try:
        entries = json.loads(Path(path).read_text()).get("entries", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return []
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict)]


def fetch_entry_bytes(manifest: Path, name: str) -> bytes:
    """`klt artifact get <manifest>#<name> -o -` -- the manifest-verified bytes.

    `klt` emits bytes only if their sha256 matches the manifest entry's
    digest, so a successful return is itself the integrity check; callers
    never re-hash a fetch. Any failure raises `StoreFetchError`.
    """
    ref = f"{manifest}#{name}"
    try:
        proc = subprocess.run(
            ["klt", "artifact", "get", ref, "-o", "-"],
            capture_output=True,
            timeout=_FETCH_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise StoreFetchError(f"cannot run `klt artifact get`: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace").strip()[-300:]
        raise StoreFetchError(f"`klt artifact get {ref}` failed ({proc.returncode}): {detail}")
    return proc.stdout
