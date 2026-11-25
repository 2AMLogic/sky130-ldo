"""The shared store-manifest read contract: layout/bin/_store_manifest.py (issue #675).

`_store_manifest.py` is the ONE read-side contract for the committed
artifact-store manifests, load-bearing for three trees, and its docstring
makes explicit behavioral promises: `manifest_entries` answers every
"unreadable" shape with `[]` instead of raising, and `fetch_entry_bytes`
maps every fetch failure to the one `StoreFetchError`. Before this file
those branches were pinned by prose alone (the only coverage was one call
site's happy path); each branch is pinned below.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import _store_manifest  # noqa: E402

LONG_STDERR = b"A" * 100 + b"B" * 299 + b"Z"  # 400 bytes; tail [-300:] drops the A's


class TestManifestEntries(unittest.TestCase):
    """Every docstring'd "unreadable" shape returns [] -- no exception escapes."""

    def _manifest(self, raw) -> Path:
        """A manifest file from str (text mode) or bytes (binary) content."""
        f = tempfile.NamedTemporaryFile(
            mode="wb" if isinstance(raw, bytes) else "w", suffix=".json"
        )
        self.addCleanup(f.close)
        f.write(raw)
        f.flush()
        return Path(f.name)

    def test_happy_path_returns_the_entries(self):
        path = self._manifest(json.dumps({"entries": [{"name": "a"}, {"name": "b"}]}))
        self.assertEqual(
            _store_manifest.manifest_entries(path), [{"name": "a"}, {"name": "b"}]
        )

    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                _store_manifest.manifest_entries(Path(tmp) / "absent.manifest.json"),
                [],
            )

    def test_undecodable_json_is_empty(self):
        path = self._manifest("this is not json {{{")
        self.assertEqual(_store_manifest.manifest_entries(path), [])

    def test_non_utf8_bytes_are_empty(self):
        """Non-UTF-8 file content is unreadable, not a crash.

        `read_text()` decodes before `json.loads` ever sees the bytes, so
        the decode error -- not a JSON error -- is the failure mode here.
        """
        path = self._manifest(b"\xff\xfe")
        self.assertEqual(_store_manifest.manifest_entries(path), [])

    def test_top_level_list_is_empty(self):
        """JSON that parses but is not an object has no `entries` to read."""
        path = self._manifest(json.dumps([1, 2, 3]))
        self.assertEqual(_store_manifest.manifest_entries(path), [])

    def test_absent_entries_is_empty(self):
        path = self._manifest(json.dumps({"other": []}))
        self.assertEqual(_store_manifest.manifest_entries(path), [])

    def test_entries_as_dict_is_empty(self):
        path = self._manifest(json.dumps({"entries": {"a": 1}}))
        self.assertEqual(_store_manifest.manifest_entries(path), [])

    def test_entries_as_string_is_empty(self):
        path = self._manifest(json.dumps({"entries": "nope"}))
        self.assertEqual(_store_manifest.manifest_entries(path), [])

    def test_non_dict_members_are_filtered(self):
        """Non-objects are dropped from an otherwise readable list."""
        path = self._manifest(json.dumps(
            {"entries": [{"name": "ok"}, "stray", 7, None, ["nested"]]}
        ))
        self.assertEqual(_store_manifest.manifest_entries(path), [{"name": "ok"}])


class TestFetchEntryBytes(unittest.TestCase):
    """Every fetch failure maps to StoreFetchError; success returns the bytes.

    All via a patched `subprocess.run` -- no live store, no `klt` needed,
    so the suite stays runnable headless (the CI shape).
    """

    MANIFEST = Path("block-manifest.json")
    NAME = "snap.spice"

    def _run(self, *, return_value=None, side_effect=None):
        """Call fetch_entry_bytes over a patched subprocess.run."""
        with mock.patch.object(
            _store_manifest.subprocess, "run",
            return_value=return_value, side_effect=side_effect,
        ) as run:
            with self.assertRaises(_store_manifest.StoreFetchError) as ctx:
                _store_manifest.fetch_entry_bytes(self.MANIFEST, self.NAME)
        return run, ctx.exception

    def test_success_returns_stdout_verbatim(self):
        proc = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"evidence bytes")
        with mock.patch.object(
            _store_manifest.subprocess, "run", return_value=proc
        ) as run:
            self.assertEqual(
                _store_manifest.fetch_entry_bytes(self.MANIFEST, self.NAME),
                b"evidence bytes",
            )
        (args, kwargs) = run.call_args
        self.assertEqual(
            list(args[0]),
            ["klt", "artifact", "get", f"{self.MANIFEST}#{self.NAME}", "-o", "-"],
        )
        self.assertTrue(kwargs.get("capture_output"))

    def test_nonzero_exit_raises_with_trimmed_stderr(self):
        """The message carries only the last 300 chars of stderr."""
        proc = subprocess.CompletedProcess(
            args=[], returncode=1, stdout=b"", stderr=LONG_STDERR
        )
        run, exc = self._run(return_value=proc)
        self.assertIn("(1)", str(exc))
        self.assertIn(f"{self.MANIFEST}#{self.NAME}", str(exc))
        self.assertNotIn(b"A" * 100, str(exc).encode())
        self.assertIn((b"B" * 299 + b"Z").decode(errors="replace"), str(exc))
        self.assertEqual(run.call_count, 1)

    def test_oserror_raises(self):
        """No `klt` on PATH is a fetch failure, not a crash."""
        _, exc = self._run(side_effect=OSError("no klt"))
        self.assertIn("cannot run", str(exc))
        self.assertIn("no klt", str(exc))

    def test_timeout_raises(self):
        _, exc = self._run(side_effect=subprocess.TimeoutExpired(cmd="klt", timeout=120))
        self.assertIn("cannot run", str(exc))


if __name__ == "__main__":
    unittest.main()
