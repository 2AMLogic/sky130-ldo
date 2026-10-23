#!/usr/bin/env python3
"""CI guard for artifact-store manifests (issue #436).

Validates every `manifests/artifacts/*.manifest.json`:
  * schema_version 1 with an `entries` list;
  * each entry has a 64-hex `sha256`, a non-negative int `size`, a `name`, and
    a `uri` that starts with `artifact:` (never a bucket URL or ARN);
and fails when a stored object's sha256 equals a tracked file under `sim/` or
`layout/` -- the bytes must live in the store OR in git, not both.

Standard library only. Usage: check_artifact_manifests.py [--root DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
TREES = ("sim", "layout")
FORBIDDEN = ("s3://", "arn:aws:")


def validate_manifest(path: Path) -> tuple[list[str], list[dict]]:
    errors: list[str] = []
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError) as err:
        return [f"{path}: unreadable manifest ({err})"], []
    text = path.read_text()
    for bad in FORBIDDEN:
        if bad in text:
            errors.append(f"{path}: contains '{bad}' (store identifiers must not be committed)")
    if doc.get("schema_version") != 1:
        errors.append(f"{path}: schema_version must be 1")
    entries = doc.get("entries")
    if not isinstance(entries, list):
        return errors + [f"{path}: `entries` must be a list"], []
    for i, e in enumerate(entries):
        where = f"{path}: entries[{i}]"
        if not isinstance(e, dict):
            errors.append(f"{where}: not an object")
            continue
        if not isinstance(e.get("sha256"), str) or not SHA_RE.match(e["sha256"]):
            errors.append(f"{where}: sha256 must be 64 lowercase hex chars")
        size = e.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errors.append(f"{where}: size must be a non-negative integer")
        if not isinstance(e.get("name"), str) or not e["name"]:
            errors.append(f"{where}: name is required")
        uri = e.get("uri")
        if not isinstance(uri, str) or not uri.startswith("artifact:"):
            errors.append(f"{where}: uri must start with 'artifact:'")
    return errors, [e for e in entries if isinstance(e, dict)]


def tracked_files(root: Path) -> list[Path]:
    res = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", *TREES],
        capture_output=True, text=True, check=True,
    )
    return [root / p for p in res.stdout.split("\0") if p]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(root: Path) -> list[str]:
    manifests = sorted((root / "manifests" / "artifacts").glob("*.manifest.json"))
    errors: list[str] = []
    stored: dict[str, tuple[Path, dict]] = {}
    for m in manifests:
        errs, entries = validate_manifest(m)
        errors += errs
        for e in entries:
            # Empty objects would match any empty tracked file; not meaningful.
            if SHA_RE.match(str(e.get("sha256", ""))) and e.get("size") != 0:
                stored[e["sha256"]] = (m, e)
    if stored:
        for f in tracked_files(root):
            if not f.is_file() or f.stat().st_size == 0:
                continue
            digest = sha256_file(f)
            if digest in stored:
                m, e = stored[digest]
                errors.append(
                    f"{f.relative_to(root)}: committed bytes duplicate stored object "
                    f"{e.get('name')} ({m.name}); keep bytes in the store only"
                )
    return errors


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    errors = check(args.root)
    for e in errors:
        print(f"check-artifact-manifests: {e}", file=sys.stderr)
    if errors:
        return 1
    print("check-artifact-manifests: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
