"""Shared helpers for `layout/bin/render-*.py` (issue #41).

Standard library only, matching every `render-*.py` script's own convention.
`_load()`/`_git()` and the `klt`-version/PDK-info/git-provenance block were
byte-identical across `render-record.py`, `render-ldo-record.py`, and
`render-ldo-lvs-record.py` before this module existed -- pure extraction, no
behavior change.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


def _load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@dataclass(frozen=True)
class Provenance:
    sha: str
    branch: str
    dirty: bool
    klt_version: str
    pdk_info: dict


def provenance(repo_root: Path, klt: str, pdk_variant: str) -> Provenance:
    """Gather the git-state + `klt`/PDK-version block every `render-*.py`
    script's `main()` puts in its record.md's "Provenance" section."""
    sha = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = _git(repo_root, "status", "--porcelain") != ""

    klt_version = subprocess.run(
        [klt, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    pdk_info_raw = subprocess.run(
        [klt, "pdk", "find", "--pdk", pdk_variant, "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pdk_info = json.loads(pdk_info_raw)

    return Provenance(
        sha=sha,
        branch=branch,
        dirty=dirty,
        klt_version=klt_version,
        pdk_info=pdk_info,
    )
