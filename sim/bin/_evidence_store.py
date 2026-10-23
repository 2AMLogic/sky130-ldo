"""Artifact-store evidence writer shared by the sim runners (issue #436).

New campaign bytes (JSON twin, netlist snapshot, per-corner logs, batch
request/response files) are stored through `klt artifact put`; git keeps only a
manifest (`manifests/artifacts/<bench>-<run-id>.manifest.json`) naming each
object by sha256, plus the human-readable `records/<rid>.md` summary.

Fail-closed: `preflight()` runs before any simulation and raises
`EvidenceStoreError` when the broker env var is unset, the `klt artifact put`
verb is missing, or the broker is unreachable. There is no flag that falls back
to committing bytes. Staged bytes live under a git-ignored scratch dir, and the
manifest is only moved into `manifests/` after every `put` succeeded, so a
failure leaves nothing under `manifests/` or `sim/`.

Standard library only. The broker URL comes from `$KLT_ARTIFACT_BROKER` and is
never placed in argv, output, or the repo.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

BROKER_ENV = "KLT_ARTIFACT_BROKER"
STAGE_REL = Path("sim") / ".work" / ".stage"
MANIFEST_REL = Path("manifests") / "artifacts"


class EvidenceStoreError(RuntimeError):
    pass


def preflight(klt: str | None = None, timeout: float = 10.0) -> str:
    """Return the klt binary path, or raise if evidence cannot be stored."""
    broker = os.environ.get(BROKER_ENV, "").strip()
    if not broker:
        raise EvidenceStoreError(
            f"${BROKER_ENV} is not set: new sim evidence is stored in the artifact "
            "store and there is no fallback that commits bytes"
        )
    klt = klt or shutil.which("klt")
    if not klt:
        raise EvidenceStoreError("klt not found on PATH (needed for `klt artifact put`)")
    try:
        probe = subprocess.run(
            [klt, "artifact", "put", "--help"], capture_output=True, text=True, timeout=60
        )
    except (subprocess.SubprocessError, OSError) as err:
        raise EvidenceStoreError(f"cannot run `klt artifact put`: {err}") from err
    if probe.returncode != 0:
        raise EvidenceStoreError(
            "this klt has no `artifact put` verb (needs klayout-tools >= 7e3561f)"
        )
    try:
        urllib.request.urlopen(broker, timeout=timeout).close()
    except urllib.error.HTTPError:
        pass  # the broker answered; any HTTP status proves reachability
    except (urllib.error.URLError, OSError, ValueError) as err:
        # Name the failure class only: the URL itself must not be echoed.
        raise EvidenceStoreError(
            f"artifact broker unreachable ({type(err).__name__})"
        ) from None
    return klt


class EvidenceRun:
    """Stages one run's evidence, stores it, and writes the manifest."""

    def __init__(self, repo_root: Path, bench: str, run_id: str, klt: str):
        self.repo_root = Path(repo_root)
        self.bench = bench
        self.run_id = run_id
        self.klt = klt
        self.stage = self.repo_root / STAGE_REL / bench / run_id
        self.manifest_path = self.repo_root / MANIFEST_REL / f"{bench}-{run_id}.manifest.json"

    def stage_text(self, rel: str, text: str) -> Path:
        """Stage `text` under the run's scratch dir as store name `sim/<bench>/<rel>`."""
        path = self.stage / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def stage_file(self, rel: str, src: Path) -> Path:
        path = self.stage / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, path)
        return path

    def uri_label(self, rel: str) -> str:
        """Store name a staged `rel` will carry, for use in record links."""
        return f"sim/{self.bench}/{rel}"

    def commit(self) -> list[dict]:
        """`klt artifact put` every file under the stage dir; publish the manifest.

        Walking the dir (rather than a registry) also picks up files a runner
        wrote there directly, e.g. a per-corner log's sibling trace files.
        """
        if self.manifest_path.exists():
            raise EvidenceStoreError(f"{self.manifest_path} already exists — append-only")
        tmp_manifest = self.stage / "manifest.json"
        if tmp_manifest.exists():
            tmp_manifest.unlink()
        files = sorted(
            p for p in self.stage.rglob("*") if p.is_file() and p != tmp_manifest
        )
        for path in files:
            name = self.uri_label(path.relative_to(self.stage).as_posix())
            try:
                res = subprocess.run(
                    [self.klt, "artifact", "put", "--name", name,
                     "--manifest", str(tmp_manifest), str(path)],
                    capture_output=True, text=True, timeout=600,
                )
            except (subprocess.SubprocessError, OSError) as err:
                raise EvidenceStoreError(f"klt artifact put failed for {name}: {err}") from err
            if res.returncode != 0:
                tail = (res.stderr or res.stdout).strip().splitlines()[-1:] or [""]
                raise EvidenceStoreError(
                    f"klt artifact put failed for {name} (exit {res.returncode}): {tail[0]}"
                )
        if not files:
            return []
        entries = json.loads(tmp_manifest.read_text())["entries"]
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tmp_manifest, self.manifest_path)
        return entries

    def manifest_rel(self) -> str:
        return str(self.manifest_path.relative_to(self.repo_root))


def render_summary(entries: list[dict], manifest_rel: str) -> list[str]:
    """Markdown block listing name / size / sha256 per stored object."""
    lines = [
        "## Stored evidence (artifact store)",
        "",
        f"Bytes are not committed; manifest: `{manifest_rel}` "
        "(verify with `klt artifact verify`).",
        "",
        "| name | size (bytes) | sha256 |",
        "|---|---|---|",
    ]
    for e in sorted(entries, key=lambda e: e["name"]):
        lines.append(f"| `{e['name']}` | {e['size']} | `{e['sha256']}` |")
    lines.append("")
    return lines
