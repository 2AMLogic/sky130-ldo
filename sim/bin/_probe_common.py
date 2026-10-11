"""Shared scaffolding for single-corner ngspice diagnostic probes (issue #353).

Every probe under `sim/*/diagnostics/` (mitigation_probe.py, adaptive_probe.py,
sense_probe.py, ...) re-implemented the same pieces: loading `corner-run.py` as
a module, `sha()`, the `logical_lines` netlist walker, the `ngspice -b` call and
`git rev-parse HEAD` provenance. New probes import them from here instead:

    sys.path.insert(0, str(SIM / "bin"))
    import _probe_common as pc
    cr = pc.load_corner_run()

Forward-only: existing diagnostics run-id directories are append-only evidence
and keep their own copies, byte-for-byte. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

import _record_common

BIN_DIR = Path(__file__).resolve().parent


def load_corner_run():
    """Return the `corner-run.py` module (registered as `corner_run`)."""
    return _record_common.load_corner_run_module(BIN_DIR)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _as_lines(text_or_lines) -> list[str]:
    if isinstance(text_or_lines, str):
        return text_or_lines.splitlines()
    return list(text_or_lines)


def logical_lines(text_or_lines) -> list[tuple[int, int]]:
    """[(start, end)] line-index spans of each logical line (a physical line
    plus its `+` continuations). Accepts a string or a list of lines."""
    lines = _as_lines(text_or_lines)
    spans, start = [], None
    for i, ln in enumerate(lines):
        if not ln.startswith("+"):
            if start is not None:
                spans.append((start, i))
            start = i
    if start is not None:
        spans.append((start, len(lines)))
    return spans


def find_card(text_or_lines, prefix: str) -> tuple[int, int]:
    """Span of the single logical line starting with `prefix`; asserts exactly one."""
    lines = _as_lines(text_or_lines)
    hits = [(s, e) for s, e in logical_lines(lines) if lines[s].startswith(prefix)]
    assert len(hits) == 1, f"expected exactly one card starting {prefix!r}, found {len(hits)}"
    return hits[0]


def run_ngspice_deck(run_dir, timeout: float | None = None, deck: str = "deck.spice"):
    """Run `ngspice -b <deck>` in `run_dir`; write `ngspice.log` there.

    Returns (log, elapsed_s, returncode). `log` is stdout + "\\n" + stderr.
    """
    run_dir = Path(run_dir)
    t0 = time.monotonic()
    p = subprocess.run(["ngspice", "-b", deck], cwd=run_dir, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=timeout)
    elapsed = time.monotonic() - t0
    log = p.stdout + "\n" + p.stderr
    (run_dir / "ngspice.log").write_text(log)
    return log, elapsed, p.returncode


def git_provenance(repo=None) -> str:
    """`git rev-parse HEAD` of `repo` (default: this checkout); "" on failure."""
    repo = Path(repo) if repo is not None else BIN_DIR.parents[1]
    return _record_common.git(repo, "rev-parse", "HEAD")


def load_results(diag_dir) -> dict:
    """{run_id: result.json dict} for every `<diag_dir>/runs/*/result.json`."""
    out = {}
    for f in sorted((Path(diag_dir) / "runs").glob("*/result.json")):
        r = json.loads(f.read_text())
        out[r["run_id"]] = r
    return out
