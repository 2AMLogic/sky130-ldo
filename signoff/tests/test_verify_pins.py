"""Mutation coverage for signoff/verify-pins.py, stage 1 of signoff/check.sh.

The point of these tests is the one thing reading the script cannot establish:
that each half of a **compound** citation is verified against its *own* pin.
T1 item 11 ("Power delivery (structural)") cites two files -- the `klt erc`
supply-spec run and item 4's LVS report -- and both legitimately carry the
same `content_hash`, because both read the same GDS. Before issue #222 the
verification pooled an item's hashes into one set, so either half's pin
satisfied the other half's check and **deleting one of the two pins outright
still passed**. `test_deleting_item_11_lvs_half_pin_fails` is that exact
mutation; it fails (as it should) only because the correlation is now keyed on
the file each side names.

Runs against the repo's real signoff/block-manifest.json +
signoff/artifact-pins.json, mutating in-memory copies written to a tempdir --
the committed files are never touched. Needs nothing but python3: no `klt`, no
PDK, no network, so `npm run check:ci` runs it on every push even though
check.sh's later `klt signoff --manifest` stages cannot run there.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SIGNOFF_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIGNOFF_DIR.parent
SCRIPT = SIGNOFF_DIR / "verify-pins.py"
MANIFEST = SIGNOFF_DIR / "block-manifest.json"
PINS = SIGNOFF_DIR / "artifact-pins.json"

# Loaded by file path, not `import verify_pins`: the CLI convention in this
# repo keeps hyphenated script filenames (cf. sim/tests/test_corner_run.py).
_spec = importlib.util.spec_from_file_location("verify_pins", SCRIPT)
verify_pins = importlib.util.module_from_spec(_spec)
sys.modules["verify_pins"] = verify_pins
_spec.loader.exec_module(verify_pins)

# The compound-citation item this issue is about, and the half whose pin the
# mutation deletes.
COMPOUND_ITEM = "11"
LVS_HALF_SUFFIX = "lvs.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def _pins() -> list[dict]:
    return json.loads(PINS.read_text())["pins"]


def _verify(manifest: dict, pins: list[dict]) -> list[str]:
    return verify_pins.verify(manifest, pins, REPO_ROOT)


class TestCommittedTreeIsClean(unittest.TestCase):
    """The unmutated tree must pass -- otherwise every mutation below is noise."""

    def test_committed_manifest_and_pins_verify(self):
        self.assertEqual(_verify(_manifest(), _pins()), [])

    def test_script_exits_zero_on_the_committed_tree(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(MANIFEST), str(PINS)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("pinned artifact(s) match their citations", proc.stdout)

    def test_the_premise_holds_item_11_is_compound_with_two_equal_hashes(self):
        """Guard the fixture the mutation test depends on.

        If item 11 ever stops being a two-part citation whose halves share one
        content_hash, the mutation below stops exercising the pooled-hash bug
        and this test says so instead of silently passing.
        """
        entry = _manifest()["evidence"][COMPOUND_ITEM]
        self.assertIsInstance(entry, list)
        self.assertEqual(len(entry), 2)
        self.assertEqual(
            len({part["content_hash"] for part in entry}),
            1,
            "item 11's two halves no longer share one content_hash -- the "
            "pooled-hash mutation below no longer reproduces #222",
        )


class TestCompoundCitationCorrelation(unittest.TestCase):
    """Each half of item 11's compound citation must rest on its own pin."""

    def _lvs_half_pins(self, pins: list[dict]) -> list[dict]:
        return [
            p for p in pins
            if str(p["item"]) == COMPOUND_ITEM
            and p.get("manifest_pinned")
            and str(p["cited_envelope"]).endswith(LVS_HALF_SUFFIX)
        ]

    def test_deleting_item_11_lvs_half_pin_fails(self):
        """The #222 regression: this silently passed before per-file correlation."""
        pins = _pins()
        doomed = self._lvs_half_pins(pins)
        self.assertEqual(
            len(doomed), 1,
            f"expected exactly one manifest_pinned item-{COMPOUND_ITEM} pin "
            f"citing *{LVS_HALF_SUFFIX}, found {len(doomed)}",
        )
        mutated = [p for p in pins if p is not doomed[0]]

        failures = _verify(_manifest(), mutated)
        self.assertTrue(
            failures,
            "deleting item 11's LVS-half pin must fail the check; it passed, "
            "which is exactly the pooled-hash gap in issue #222",
        )
        self.assertTrue(
            any(LVS_HALF_SUFFIX in f for f in failures),
            f"the failure must name the uncovered file; got {failures!r}",
        )

    def test_deleting_item_11_erc_half_pin_fails(self):
        """The other half, for symmetry -- neither may lean on its sibling."""
        pins = _pins()
        doomed = [
            p for p in pins
            if str(p["item"]) == COMPOUND_ITEM
            and p.get("manifest_pinned")
            and not str(p["cited_envelope"]).endswith(LVS_HALF_SUFFIX)
        ]
        self.assertEqual(len(doomed), 1)
        mutated = [p for p in pins if p is not doomed[0]]

        failures = _verify(_manifest(), mutated)
        self.assertTrue(failures)
        self.assertTrue(
            any("erc_supply.json" in f for f in failures),
            f"the failure must name the uncovered file; got {failures!r}",
        )

    def test_repointing_item_11_lvs_half_pin_at_the_erc_envelope_fails(self):
        """A pin may not cover a file the manifest does not cite for its item.

        The subtler shape of the same bug: keep both pins, but point the LVS
        half's `cited_envelope` at the *other* half's file. The hashes still
        all agree, so the pooled check saw nothing wrong; per-file correlation
        sees one manifest citation with no backing pin.
        """
        pins = _pins()
        erc_file = next(
            part["file"]
            for part in _manifest()["evidence"][COMPOUND_ITEM]
            if not part["file"].endswith(LVS_HALF_SUFFIX)
        )
        mutated = []
        for pin in pins:
            if (
                str(pin["item"]) == COMPOUND_ITEM
                and pin.get("manifest_pinned")
                and str(pin["cited_envelope"]).endswith(LVS_HALF_SUFFIX)
            ):
                pin = {**pin, "cited_envelope": erc_file}
            mutated.append(pin)

        failures = _verify(_manifest(), mutated)
        self.assertTrue(
            failures,
            "an item-11 pin re-pointed at its sibling's envelope must fail",
        )
        self.assertTrue(any(LVS_HALF_SUFFIX in f for f in failures), failures)

    def test_script_exit_status_reflects_the_mutation(self):
        """Drive the real CLI, the way signoff/check.sh stage 1 does."""
        pins = _pins()
        mutated = {
            "pins": [
                p for p in pins
                if not (
                    str(p["item"]) == COMPOUND_ITEM
                    and p.get("manifest_pinned")
                    and str(p["cited_envelope"]).endswith(LVS_HALF_SUFFIX)
                )
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            pins_path = Path(tmp) / "artifact-pins.json"
            pins_path.write_text(json.dumps(mutated, indent=2))
            proc = subprocess.run(
                [
                    sys.executable, str(SCRIPT), str(MANIFEST), str(pins_path),
                    "--root", str(REPO_ROOT),
                ],
                cwd=tmp,
                capture_output=True,
                text=True,
            )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("pinned-hash verification FAILED", proc.stderr)
        self.assertIn(LVS_HALF_SUFFIX, proc.stderr)


class TestSingleObjectItemsStillVerify(unittest.TestCase):
    """The non-compound items (3, 4, 6, 7, 8) must not regress.

    `manifest_parts()` normalises the single-object shape into a one-element
    list, so the per-file correlation has to hold for them too -- each of them
    carries a `file` field today, and these tests keep it that way.
    """

    def test_every_non_compound_item_is_a_single_object_with_a_file(self):
        for item, entry in sorted(_manifest()["evidence"].items()):
            if item == COMPOUND_ITEM:
                continue
            with self.subTest(item=item):
                self.assertIsInstance(entry, dict)
                self.assertIn("file", entry)

    def test_each_single_object_item_verifies_on_its_own(self):
        manifest = _manifest()
        pins = _pins()
        for item in sorted(manifest["evidence"]):
            if item == COMPOUND_ITEM:
                continue
            with self.subTest(item=item):
                sliced = {
                    **manifest,
                    "evidence": {item: manifest["evidence"][item]},
                }
                self.assertEqual(
                    _verify(sliced, [p for p in pins if str(p["item"]) == item]),
                    [],
                )

    def test_dropping_a_single_object_item_manifest_pin_fails(self):
        """The same mutation applied to a non-compound item, e.g. item 3."""
        manifest = _manifest()
        pins = _pins()
        for item in sorted(manifest["evidence"]):
            if item == COMPOUND_ITEM:
                continue
            with self.subTest(item=item):
                mutated = [
                    p for p in pins
                    if not (str(p["item"]) == item and p.get("manifest_pinned"))
                ]
                self.assertTrue(_verify(manifest, mutated))

    def test_renaming_a_cited_file_breaks_its_own_pin(self):
        """A manifest citation re-pointed at an unpinned file must fail."""
        manifest = _manifest()
        manifest["evidence"]["3"] = {
            **manifest["evidence"]["3"],
            "file": "layout/ldo-core/reports/nope/drc.json",
        }
        failures = _verify(manifest, _pins())
        self.assertTrue(any("item 3" in f for f in failures), failures)


class TestManifestParts(unittest.TestCase):
    """The shape normaliser both loops depend on."""

    def test_single_object(self):
        entry = {"file": "a.json", "content_hash": "sha256:ab"}
        self.assertEqual(verify_pins.manifest_parts(entry), [entry])

    def test_list(self):
        entries = [{"file": "a.json"}, {"file": "b.json"}]
        self.assertEqual(verify_pins.manifest_parts(entries), entries)

    def test_non_objects_are_dropped(self):
        self.assertEqual(verify_pins.manifest_parts(None), [])
        self.assertEqual(verify_pins.manifest_parts(["a.json", 7]), [])

    def test_norm_accepts_both_hash_spellings(self):
        self.assertEqual(verify_pins.norm("sha256:abc"), "abc")
        self.assertEqual(verify_pins.norm("abc"), "abc")
        self.assertIsNone(verify_pins.norm(None))


if __name__ == "__main__":
    unittest.main()
