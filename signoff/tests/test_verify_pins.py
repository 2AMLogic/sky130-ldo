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
# Item 5 (issue #449) is a list of per-bench `klt sim` citations, each with
# its own pin; the per-file correlation is covered by test_item5_envelopes.py.
MULTI_ITEMS = (COMPOUND_ITEM, "5")
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
            if item in MULTI_ITEMS:
                continue
            with self.subTest(item=item):
                self.assertIsInstance(entry, dict)
                self.assertIn("file", entry)

    def test_each_single_object_item_verifies_on_its_own(self):
        manifest = _manifest()
        pins = _pins()
        for item in sorted(manifest["evidence"]):
            if item in MULTI_ITEMS:
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


class TestAttestedItems(unittest.TestCase):
    """Items 1, 2, 9, 10 (issue #423): tool-produced envelopes stay pinned."""

    def test_attested_items_are_pinned_and_cited(self):
        for item in ("1", "2", "9", "10"):
            self.assertIn(item, _manifest()["evidence"])
            self.assertTrue([p for p in _pins() if p["item"] == item])

    def test_wrong_input_set_pin_fails(self):
        pins = _pins()
        for pin in pins:
            if pin["item"] == "1":
                pin["sha256"] = "sha256:" + "0" * 64
        self.assertTrue(_verify(_manifest(), pins))

    def test_drifted_input_set_member_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pin = next(p for p in _pins() if p["item"] == "1")
            env = json.loads((REPO_ROOT / pin["cited_envelope"]).read_text())
            (root / Path(pin["cited_envelope"])).parent.mkdir(parents=True)
            (root / pin["cited_envelope"]).write_text(json.dumps(env))
            for m in env["provenance"]["input"]["paths"]:
                dst = root / m["path"]["path"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes((REPO_ROOT / m["path"]["path"]).read_bytes())
            expected = verify_pins.normalize_sha256(pin["sha256"])
            self.assertEqual(
                verify_pins.verify_input_set(pin, "1", expected, root), [])
            (root / "design/ldo_3v3in_1v8out.sch").write_bytes(b"drift")
            self.assertTrue(
                verify_pins.verify_input_set(pin, "1", expected, root))


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


class TestDigestContract(unittest.TestCase):
    """This stage reads recorded hashes through the repo's ONE normalizer (#589).

    It used to carry its own `norm`, strictly weaker than
    `measurements/build_characterization_report.py`'s `normalize_sha256`
    despite that function's docstring claiming parity: `norm` passed
    `"sha256:TBD"` through as the comparable string `"TBD"`, and left an
    uppercase or whitespace-padded digest un-canonicalised -- inside the gate
    that is the verdict of record. The full case-by-case contract is pinned in
    `layout/tests/test_digest.py`; what matters here is that this stage uses
    that same function object and nothing else.
    """

    def test_stage_uses_the_shared_normalizer(self):
        sys.path.append(str(REPO_ROOT / "layout" / "bin"))
        import _digest

        self.assertIs(verify_pins.normalize_sha256, _digest.normalize_sha256)
        self.assertIs(verify_pins.sha256_file, _digest.sha256_file)

    def test_the_weaker_normalizer_is_gone(self):
        self.assertFalse(hasattr(verify_pins, "norm"))

    def test_both_spellings_still_read_as_the_same_digest(self):
        sha = "a" * 64
        self.assertEqual(verify_pins.normalize_sha256(sha), sha)
        self.assertEqual(verify_pins.normalize_sha256("sha256:" + sha), sha)

    def test_malformed_recorded_hashes_are_not_comparable(self):
        for bad in ("sha256:TBD", "sha256:", "deadbeef", None, 7):
            self.assertIsNone(verify_pins.normalize_sha256(bad), bad)


class TestMalformedProvenanceIsUnverified(unittest.TestCase):
    """A hash that is not a digest must be reported as such, not compared.

    Both halves of the pin/manifest correlation are covered: a malformed pin
    (`artifact-pins.json`) and a malformed manifest citation. Under `norm`
    these did not pass silently -- `norm("sha256:TBD")` returned the truthy
    string `"TBD"`, which then failed some *other* comparison -- but they were
    diagnosed as drift or as a missing backing pin, which sends a reader
    looking for the wrong defect. The assertions below pin the diagnosis, not
    just the exit status.
    """

    def test_a_pin_whose_sha256_is_a_placeholder_fails(self):
        pins = _pins()
        target = next(p for p in pins if not p.get("input_set"))
        target["sha256"] = "sha256:TBD"
        failures = _verify(_manifest(), pins)
        self.assertTrue(
            any("not a sha256 digest" in f for f in failures), failures)

    def test_a_pin_whose_sha256_is_truncated_fails(self):
        pins = _pins()
        target = next(p for p in pins if not p.get("input_set"))
        target["sha256"] = target["sha256"][:20]
        self.assertTrue(_verify(_manifest(), pins))

    def test_a_manifest_citation_with_a_malformed_hash_fails(self):
        manifest = _manifest()
        item = next(
            i for i, e in sorted(manifest["evidence"].items())
            if isinstance(e, dict) and "content_hash" in e
        )
        manifest["evidence"][item] = {
            **manifest["evidence"][item],
            "content_hash": "sha256:TBD",
        }
        failures = _verify(manifest, _pins())
        self.assertTrue(
            any("not a sha256 digest" in f for f in failures), failures)

    def test_an_uppercase_pin_still_matches_its_artifact(self):
        """Canonicalisation, not weakening: same bytes, different typing.

        `norm` compared an uppercase pin verbatim against a lowercase
        `hexdigest()`, so this spelling used to be reported as drift.
        """
        pins = _pins()
        for pin in pins:
            pin["sha256"] = pin["sha256"].upper().replace("SHA256:", "sha256:")
        manifest = _manifest()
        self.assertEqual(_verify(manifest, pins), [])


if __name__ == "__main__":
    unittest.main()
