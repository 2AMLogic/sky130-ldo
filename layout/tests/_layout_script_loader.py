"""Load a hyphenated (non-importable) script as a module, for the layout tests.

Named per tree so `sim/tests` and `layout/tests` helpers never collide in
`sys.modules` when both trees run in one process.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_script(name: str, path: Path, register: bool = False):
    """Exec `path` as module `name`; with `register`, also put it in `sys.modules`."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    if register:
        sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
