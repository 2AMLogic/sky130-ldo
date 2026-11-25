"""Item 5 envelopes (issue #449) must agree with the rollup they wrap.

Needs nothing but python3: on a host with `klt` + store access a store-held
record's currency check fetches its twin from the broker; without them the
store-backed citation chain is verified structurally instead (no fetch), so a
missing binary is never a silent skip.
 Checks that signoff/make_item5_envelope.py's
committed output is current, that each envelope cites the record
measurements/characterization.md cites, and that each envelope's verdict equals
that record's verdict there -- a wrap must never grade a row differently from
the evidence it copies.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "signoff"))
import make_item5_envelope as m  # noqa: E402

# characterization.md verdict -> envelope status. A PVT-subset FAIL is still fail.
_ROW_BENCH = {
    "Dropout @ 50 mA": "dropout-vs-load", "Line regulation": "line-regulation",
    "Load regulation (0–50 mA)": "load-regulation", "Load transient": "load-transient",
    "PSRR": "psrr-dc", "Iq (excl. load current)": "iq", "Current limit": "current-limit",
    "Startup / soft-start": "startup", "Enable / shutdown": "enable-shutdown",
    "Thermal": "thermal", "Stability": "loop-gain",
}


def _rollup() -> dict[str, tuple[str, str]]:
    out = {}
    for line in (ROOT / "measurements" / "characterization.md").read_text().splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 4 and cells[0] in _ROW_BENCH:
            # `/records/<id>.md` (harness record) or `/<bench>/hysteresis/<id>/` (directory record)
            rec = re.search(r"/records/([\w-]+)\.md|/hysteresis/([\w-]+)/", cells[3])
            out[_ROW_BENCH[cells[0]]] = (rec.group(1) or rec.group(2), "fail" if "FAIL" in cells[2] else "pass")
    return out


class Item5Envelopes(unittest.TestCase):
    def test_committed_envelopes_are_current(self):
        if shutil.which("klt") is None:
            # Headless CI (no klt, no store access): records committed on
            # disk still get the full byte-exact rebuild, and the store-held
            # records get their manifest digest chain verified instead of a
            # fetch -- real coverage of the store-backed citation path, not a
            # skip (issue #503 pattern).
            problems = m.offline_check()
            self.assertEqual(problems, [], "\n".join(problems))
            return
        for bench, rid in m.RECORDS:
            path = m.output_path(bench, rid)
            self.assertTrue(path.is_file(), path)
            self.assertEqual(path.read_text(), m.envelope_text(bench, rid), path.name)

    def test_records_and_verdicts_match_characterization(self):
        rollup = _rollup()
        self.assertEqual(set(rollup), set(_ROW_BENCH.values()))
        for bench, rid in m.RECORDS:
            char_rid, verdict = rollup[bench]
            self.assertEqual(rid, char_rid, bench)
            env = json.loads(m.output_path(bench, rid).read_text())
            self.assertEqual(env["status"], verdict, bench)

    def test_tagged_measurements_carry_ratified_bounds(self):
        # The ratified row's own fields must match exactly; a record may add
        # its own extra guards (iq's `min: 0`, kept verbatim by the wrapper).
        for bench, rid in m.RECORDS:
            env = json.loads(m.output_path(bench, rid).read_text())
            for meas in env["measurements"]:
                if "spec_row" in meas:
                    row, bound = m.RATIFIED[bench][meas["name"]]
                    self.assertEqual(meas["spec_row"], row)
                    lim = meas["limits"] or {}
                    for k, v in bound.items():
                        self.assertEqual(lim.get(k), v, f"{bench}/{meas['name']}:{k}")

    def test_every_citation_has_its_own_manifest_pin(self):
        man = json.loads((ROOT / "signoff" / "block-manifest.json").read_text())
        pins = json.loads((ROOT / "signoff" / "artifact-pins.json").read_text())["pins"]
        cited = {c["file"]: c["content_hash"] for c in man["evidence"]["5"]}
        self.assertEqual(set(cited), {m.output_path(b, r).relative_to(ROOT).as_posix() for b, r in m.RECORDS})
        for f, h in cited.items():
            self.assertTrue(
                any(p["item"] == "5" and p["cited_envelope"] == f and p["sha256"] == h and p["manifest_pinned"] for p in pins), f)

    def test_subset_record_is_never_a_full_pass(self):
        env = json.loads(m.output_path("dropout-vs-load", "20261011-092557-7a4e0cc").read_text())
        self.assertTrue(env["source_record"]["matrix_is_subset"])
        self.assertNotEqual(env["status"], "pass")

    def test_limit_disagreeing_with_ratified_bound_is_refused(self):
        orig = m.RATIFIED["iq"]["iq_no_load_ua"]
        m.RATIFIED["iq"]["iq_no_load_ua"] = ("iq", {"max": 29})
        try:
            with self.assertRaises(m.WrapError):
                m.build_envelope("iq", "20260910-034648-6c0436d")
        finally:
            m.RATIFIED["iq"]["iq_no_load_ua"] = orig


class StoreHeldRecordFetchContract(unittest.TestCase):
    """A store-held record is fetched exactly once per artifact (issue #729).

    `build_envelope()` used to fetch the record JSON twice -- `_load()`
    parsed and discarded the bytes, then the caller fetched them again solely
    to hash them -- and hashed an on-disk netlist snapshot with
    `read_bytes()` instead of leaving `_envelope()`'s chunked
    `sha256_file_prefixed` default to do it. These tests pin the
    single-fetch contract headlessly: `fetch_entry_bytes` and the manifest
    lookup are mocked, so no `klt` or store access is needed.
    """

    BENCH = "test-bench"
    RID = "20260101-000000-deadbeef"
    REC_NAME = f"sim/{BENCH}/records/{RID}.json"
    SNAP_REL = f"sim/{BENCH}/netlist-snapshots/{RID}.spice"
    SNAP_BYTES = b"* test netlist snapshot\n"

    def _record(self) -> dict:
        return {
            "links": {"netlist_snapshot": self.SNAP_REL},
            "tools": {"ngspice": "test", "platform": "test"},
            "pdk": {"pinned_commit": "test"},
            "overall_pass": True,
            "corners": [{
                "corner_id": "tt_1v98", "process": "tt", "supply_v": 1.98,
                "temperature_c": 27, "pass": True,
                "measurements": [{
                    "name": "probe_v", "value": 1.8, "unit": "V",
                    "min": 1.764, "max": 1.836, "pass": True,
                }],
            }],
        }

    def _build(self, snapshot_on_disk: bool) -> tuple[dict, list[str], str, str]:
        """Wrap a store-held record against a throwaway tree; returns
        (envelope, fetched entry names, expected record sha, expected
        snapshot sha)."""
        rec_raw = (json.dumps(self._record()) + "\n").encode()
        manifest = Path(f"manifests/artifacts/{self.BENCH}-{self.RID}.manifest.json")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            snap = root / self.SNAP_REL
            snap.parent.mkdir(parents=True)
            expected_snap = "sha256:" + hashlib.sha256(self.SNAP_BYTES).hexdigest()
            if snapshot_on_disk:
                snap.write_bytes(self.SNAP_BYTES)
                expected_snap = m.sha256_file_prefixed(snap)
            fetch = mock.Mock(side_effect=lambda _m, name: {
                self.REC_NAME: rec_raw, self.SNAP_REL: self.SNAP_BYTES}[name])
            with mock.patch.object(m, "REPO_ROOT", root), \
                 mock.patch.object(m._report, "_store_manifest_entry",
                                   return_value=(manifest, self.REC_NAME)), \
                 mock.patch.object(m, "fetch_entry_bytes", fetch), \
                 mock.patch.dict(m.RATIFIED, {self.BENCH: {
                     "probe_v": ("output", {"min": 1.764, "max": 1.836})}}):
                env = m.build_envelope(self.BENCH, self.RID)
            names = [c.args[1] for c in fetch.call_args_list]
            return (env, names, "sha256:" + hashlib.sha256(rec_raw).hexdigest(),
                    expected_snap)

    def test_store_held_record_and_snapshot_fetch_once_each(self):
        env, names, rec_sha, snap_sha = self._build(snapshot_on_disk=False)
        self.assertEqual(names.count(self.REC_NAME), 1)  # never re-fetched just to hash it
        self.assertEqual(names.count(self.SNAP_REL), 1)
        self.assertEqual(env["source_record"]["sha256"], rec_sha)
        self.assertEqual(env["provenance"]["input"]["content_hash"], snap_sha)

    def test_store_held_record_with_on_disk_snapshot_fetches_once(self):
        env, names, rec_sha, snap_sha = self._build(snapshot_on_disk=True)
        self.assertEqual(names, [self.REC_NAME])  # only the JSON twin; snapshot hashed from disk
        self.assertEqual(env["source_record"]["sha256"], rec_sha)
        self.assertEqual(env["provenance"]["input"]["content_hash"], snap_sha)


if __name__ == "__main__":
    unittest.main()
