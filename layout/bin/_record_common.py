"""Shared helpers for `layout/bin/render-*.py` (issue #41).

Standard library only, matching every `render-*.py` script's own convention.
`_load()`/`git()` and the `klt`-version/PDK-info/git-provenance block were
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


def git(repo_root: Path, *args: str) -> str:
    """`git -C <repo_root> <args>`, stripped stdout; raises on non-zero exit."""
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def run_klt_json(
    klt: str, *args: str, error_cls: type[Exception] = RuntimeError
) -> dict:
    """Run `klt <args> --format json` and return the parsed JSON report.

    A non-zero exit raises `error_cls("klt <args> failed: <stderr>")`, so every
    generator reports a failing `klt` identically (issue #273).
    """
    proc = subprocess.run(
        [klt, *args, "--format", "json"], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise error_cls(f"klt {' '.join(args)} failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


@dataclass(frozen=True)
class Provenance:
    sha: str
    branch: str
    dirty: bool
    klt_version: str
    pdk_info: dict


def provenance(
    repo_root: Path, klt: str, pdk_variant: str | None = None
) -> Provenance:
    """Gather the git-state + `klt`/PDK-version block every `render-*.py`
    script's `main()` puts in its record.md's "Provenance" section.

    `pdk_variant=None` skips the `klt pdk find` lookup and leaves
    `pdk_info` empty -- for a flow that genuinely needs no PDK install
    (issue #112's `klt erc` run reads its antenna-limit table from `klt`'s
    own built-in transcription, not from a local PDK tree), where insisting
    on a resolvable variant would be a fabricated dependency.
    """
    sha = git(repo_root, "rev-parse", "HEAD")
    branch = git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = git(repo_root, "status", "--porcelain") != ""

    klt_version = subprocess.run(
        [klt, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    pdk_info: dict = {}
    if pdk_variant is not None:
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
