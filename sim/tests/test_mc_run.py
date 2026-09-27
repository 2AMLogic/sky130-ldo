"""Unit coverage for sim/bin/mc-run.py's pure helper functions.

PDK-free by design (no ngspice/xschem/volare/klt required) so this runs on
every `npm run check:ci` invocation, including in CI where the sky130 PDK is
not installed -- see sim/selftest.sh stage 1/3, and the sibling
test_corner_run.py this file mirrors.

mc-run.py is loaded by file path (not `import mc_run`) because the CLI
convention keeps the hyphenated `mc-run.py` filename, exactly as
test_corner_run.py does for `corner-run.py`.

Scope (issue #217): the three pure helpers PR #216 grew without coverage --
`validate_netlist_patch`, `apply_netlist_patch` and
`assert_klt_read_the_pinned_pdk`. The first two are the `netlist_patch`
negative-control machinery from issue #211, whose whole value is that it
refuses to run rather than quietly sampling an undegraded circuit; the third
asserts `klt sim`'s own provenance names the pinned PDK. Each one's job is to
raise, so each `HarnessError` branch is covered here rather than just the
happy path.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR / "bin"))  # mc-run.py imports _record_common (issue #46)
_spec = importlib.util.spec_from_file_location("mc_run", SIM_DIR / "bin" / "mc-run.py")
mc_run = importlib.util.module_from_spec(_spec)
sys.modules["mc_run"] = mc_run
_spec.loader.exec_module(mc_run)

MANIFEST = Path("sim/mc-fixture/experiment.json")


def _patch(**overrides) -> dict:
    """A minimal well-formed `netlist_patch` block, with overrides applied."""
    patch = {
        "purpose": "negative control",
        "rationale": "halve the pass device width so the loop cannot regulate",
        "substitutions": [{"match": "W=10u", "replace": "W=5u", "count": 1}],
    }
    patch.update(overrides)
    return patch


class TestValidateNetlistPatch(unittest.TestCase):
    def test_none_is_a_no_op(self):
        self.assertIsNone(mc_run.validate_netlist_patch(None, MANIFEST))

    def test_well_formed_patch_passes(self):
        self.assertIsNone(mc_run.validate_netlist_patch(_patch(), MANIFEST))

    def test_multiple_substitutions_pass(self):
        patch = _patch(
            substitutions=[
                {"match": "W=10u", "replace": "W=5u", "count": 2},
                {"match": "L=0.5u", "replace": "L=1u", "count": 1},
            ]
        )
        self.assertIsNone(mc_run.validate_netlist_patch(patch, MANIFEST))

    def test_non_dict_patch_rejected(self):
        with self.assertRaisesRegex(mc_run.HarnessError, "must be an object"):
            mc_run.validate_netlist_patch(["not", "a", "dict"], MANIFEST)

    def test_missing_purpose_rejected(self):
        patch = _patch()
        del patch["purpose"]
        with self.assertRaisesRegex(mc_run.HarnessError, "missing 'purpose'"):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_missing_rationale_rejected(self):
        patch = _patch()
        del patch["rationale"]
        with self.assertRaisesRegex(mc_run.HarnessError, "missing 'rationale'"):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_empty_rationale_rejected(self):
        # A declared defect with a blank rationale is exactly the prose-free
        # patch the manifest convention exists to prevent.
        with self.assertRaisesRegex(mc_run.HarnessError, "missing 'rationale'"):
            mc_run.validate_netlist_patch(_patch(rationale=""), MANIFEST)

    def test_missing_substitutions_rejected(self):
        patch = _patch()
        del patch["substitutions"]
        with self.assertRaisesRegex(mc_run.HarnessError, "missing 'substitutions'"):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_empty_substitutions_rejected(self):
        with self.assertRaisesRegex(mc_run.HarnessError, "missing 'substitutions'"):
            mc_run.validate_netlist_patch(_patch(substitutions=[]), MANIFEST)

    def test_non_list_substitutions_rejected(self):
        patch = _patch(substitutions={"match": "a", "replace": "b", "count": 1})
        with self.assertRaisesRegex(mc_run.HarnessError, "substitutions must be an array"):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_non_dict_substitution_entry_rejected(self):
        patch = _patch(substitutions=["W=10u -> W=5u"])
        with self.assertRaisesRegex(
            mc_run.HarnessError, r"substitutions\[0\] must be an object"
        ):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_missing_match_rejected(self):
        patch = _patch(substitutions=[{"replace": "W=5u", "count": 1}])
        with self.assertRaisesRegex(
            mc_run.HarnessError, r"substitutions\[0\]\.match must be a non-empty string"
        ):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_empty_match_rejected(self):
        patch = _patch(substitutions=[{"match": "", "replace": "W=5u", "count": 1}])
        with self.assertRaisesRegex(
            mc_run.HarnessError, r"substitutions\[0\]\.match must be a non-empty string"
        ):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_non_string_match_rejected(self):
        patch = _patch(substitutions=[{"match": 10, "replace": "W=5u", "count": 1}])
        with self.assertRaisesRegex(
            mc_run.HarnessError, r"substitutions\[0\]\.match must be a non-empty string"
        ):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_missing_replace_rejected(self):
        patch = _patch(substitutions=[{"match": "W=10u", "count": 1}])
        with self.assertRaisesRegex(
            mc_run.HarnessError, r"substitutions\[0\]\.replace must be a non-empty string"
        ):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_empty_replace_rejected(self):
        patch = _patch(substitutions=[{"match": "W=10u", "replace": "", "count": 1}])
        with self.assertRaisesRegex(
            mc_run.HarnessError, r"substitutions\[0\]\.replace must be a non-empty string"
        ):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_no_op_substitution_rejected(self):
        # "a declared defect that changes nothing is worse than no defect at
        # all" -- the reason match == replace is a hard error, not a warning.
        patch = _patch(substitutions=[{"match": "W=10u", "replace": "W=10u", "count": 1}])
        with self.assertRaisesRegex(mc_run.HarnessError, r"is a no-op \(match == replace\)"):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_missing_count_rejected(self):
        patch = _patch(substitutions=[{"match": "W=10u", "replace": "W=5u"}])
        with self.assertRaisesRegex(
            mc_run.HarnessError, r"substitutions\[0\]\.count must be a positive integer"
        ):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_zero_count_rejected(self):
        patch = _patch(substitutions=[{"match": "W=10u", "replace": "W=5u", "count": 0}])
        with self.assertRaisesRegex(
            mc_run.HarnessError, r"substitutions\[0\]\.count must be a positive integer"
        ):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_negative_count_rejected(self):
        patch = _patch(substitutions=[{"match": "W=10u", "replace": "W=5u", "count": -1}])
        with self.assertRaisesRegex(
            mc_run.HarnessError, r"substitutions\[0\]\.count must be a positive integer"
        ):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_non_integer_count_rejected(self):
        patch = _patch(substitutions=[{"match": "W=10u", "replace": "W=5u", "count": 1.0}])
        with self.assertRaisesRegex(
            mc_run.HarnessError, r"substitutions\[0\]\.count must be a positive integer"
        ):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_second_substitution_is_reported_by_its_own_index(self):
        patch = _patch(
            substitutions=[
                {"match": "W=10u", "replace": "W=5u", "count": 1},
                {"match": "L=0.5u", "replace": "L=0.5u", "count": 1},
            ]
        )
        with self.assertRaisesRegex(mc_run.HarnessError, r"substitutions\[1\] is a no-op"):
            mc_run.validate_netlist_patch(patch, MANIFEST)

    def test_error_message_names_the_manifest(self):
        with self.assertRaises(mc_run.HarnessError) as ctx:
            mc_run.validate_netlist_patch(_patch(purpose=""), MANIFEST)
        self.assertIn(str(MANIFEST), str(ctx.exception))


DECK = "\n".join(
    [
        "* fixture deck",
        "XM1 vout vg vin vin pfet_g5v0d10v5 W=10u L=0.5u",
        "XM2 vout vg vin vin pfet_g5v0d10v5 W=10u L=0.5u",
        ".end",
    ]
)


class TestApplyNetlistPatch(unittest.TestCase):
    def test_none_patch_passes_text_through_unchanged(self):
        text, report = mc_run.apply_netlist_patch(DECK, None)
        self.assertEqual(text, DECK)
        self.assertIsNone(report)

    def test_substitution_is_applied_to_every_asserted_occurrence(self):
        patch = _patch(substitutions=[{"match": "W=10u", "replace": "W=5u", "count": 2}])
        text, report = mc_run.apply_netlist_patch(DECK, patch)
        self.assertNotIn("W=10u", text)
        self.assertEqual(text.count("W=5u"), 2)
        self.assertIsNotNone(report)

    def test_applied_report_records_purpose_rationale_and_substitutions(self):
        patch = _patch(substitutions=[{"match": "W=10u", "replace": "W=5u", "count": 2}])
        _text, report = mc_run.apply_netlist_patch(DECK, patch)
        self.assertEqual(report["purpose"], patch["purpose"])
        self.assertEqual(report["rationale"], patch["rationale"])
        self.assertEqual(
            report["substitutions"],
            [{"match": "W=10u", "replace": "W=5u", "count": 2}],
        )

    def test_applied_report_hashes_the_deck_before_and_after(self):
        patch = _patch(substitutions=[{"match": "W=10u", "replace": "W=5u", "count": 2}])
        text, report = mc_run.apply_netlist_patch(DECK, patch)
        self.assertEqual(
            report["netlist_sha256_before"],
            "sha256:" + hashlib.sha256(DECK.encode()).hexdigest(),
        )
        self.assertEqual(
            report["netlist_sha256_after"],
            "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        )
        self.assertNotEqual(report["netlist_sha256_before"], report["netlist_sha256_after"])

    def test_multiple_substitutions_are_all_reported(self):
        patch = _patch(
            substitutions=[
                {"match": "W=10u", "replace": "W=5u", "count": 2},
                {"match": "L=0.5u", "replace": "L=1u", "count": 2},
            ]
        )
        text, report = mc_run.apply_netlist_patch(DECK, patch)
        self.assertIn("W=5u", text)
        self.assertIn("L=1u", text)
        self.assertEqual([s["match"] for s in report["substitutions"]], ["W=10u", "L=0.5u"])
        self.assertEqual([s["count"] for s in report["substitutions"]], [2, 2])

    def test_undercount_is_refused(self):
        # The count assertion is the whole point: a patch whose stated
        # occurrence count no longer matches the deck must abort the run
        # rather than sample a differently-degraded circuit.
        patch = _patch(substitutions=[{"match": "W=10u", "replace": "W=5u", "count": 1}])
        with self.assertRaises(mc_run.HarnessError) as ctx:
            mc_run.apply_netlist_patch(DECK, patch)
        message = str(ctx.exception)
        self.assertIn("asserts 1 occurrence(s)", message)
        self.assertIn("has 2", message)

    def test_overcount_is_refused(self):
        patch = _patch(substitutions=[{"match": "W=10u", "replace": "W=5u", "count": 3}])
        with self.assertRaisesRegex(mc_run.HarnessError, "asserts 3 occurrence"):
            mc_run.apply_netlist_patch(DECK, patch)

    def test_match_absent_from_the_deck_is_refused(self):
        patch = _patch(substitutions=[{"match": "W=99u", "replace": "W=5u", "count": 1}])
        with self.assertRaisesRegex(mc_run.HarnessError, "the design this patch degrades"):
            mc_run.apply_netlist_patch(DECK, patch)

    def test_count_mismatch_in_a_later_substitution_is_refused(self):
        patch = _patch(
            substitutions=[
                {"match": "W=10u", "replace": "W=5u", "count": 2},
                {"match": "L=0.5u", "replace": "L=1u", "count": 1},
            ]
        )
        with self.assertRaisesRegex(
            mc_run.HarnessError, r"substitutions\[1\] asserts 1 occurrence"
        ):
            mc_run.apply_netlist_patch(DECK, patch)

    def test_byte_identical_deck_after_patching_is_refused(self):
        # The defensive guard behind "refusing to record an undegraded deck as
        # a patched one": reachable only with a substitution list that changes
        # nothing, which validate_netlist_patch() rejects up front -- so it is
        # exercised here directly rather than through the manifest path.
        patch = _patch(substitutions=[])
        with self.assertRaisesRegex(mc_run.HarnessError, "byte-identical afterwards"):
            mc_run.apply_netlist_patch(DECK, patch)


PIN = {"open_pdks_commit": "cd1748bb197f9b7af62a5507a29b6a6a1b7b3b1e"}


def _pdk(installed_commit: str = PIN["open_pdks_commit"]):
    """A resolve_pdk()-shaped Pdk with no PDK on disk (nothing reads it)."""
    return mc_run.corner_run.Pdk(
        pin=PIN,
        root=Path("/tmp/pdk-root"),
        variant="sky130A",
        dir=Path("/tmp/pdk-root/sky130A"),
        installed_commit=installed_commit,
        lib_file=Path("/tmp/pdk-root/sky130A/libs.tech/combined/sky130.lib.spice"),
    )


def _response(version) -> dict:
    return {"provenance": {"pdk": {"version": version}}}


class TestAssertKltReadThePinnedPdk(unittest.TestCase):
    """issue #211: a record could name the pinned open_pdks commit while the
    simulation behind it read a different build's FET cards. Passing PDK_ROOT
    fixed the cause; this function asserts the effect."""

    def test_exact_pin_match_passes(self):
        self.assertIsNone(
            mc_run.assert_klt_read_the_pinned_pdk(
                _response(PIN["open_pdks_commit"]), _pdk(), PIN, False
            )
        )

    def test_pin_embedded_in_a_longer_version_string_passes(self):
        # klt reports e.g. "sky130A open_pdks <commit>"; the check is a
        # substring test against the pin, not string equality.
        version = f"sky130A open_pdks {PIN['open_pdks_commit']}"
        self.assertIsNone(
            mc_run.assert_klt_read_the_pinned_pdk(_response(version), _pdk(), PIN, False)
        )

    def test_different_commit_raises(self):
        with self.assertRaises(mc_run.HarnessError) as ctx:
            mc_run.assert_klt_read_the_pinned_pdk(
                _response("sky130A open_pdks deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"),
                _pdk(),
                PIN,
                False,
            )
        message = str(ctx.exception)
        self.assertIn(PIN["open_pdks_commit"], message)
        self.assertIn("/tmp/pdk-root/sky130A", message)

    def test_missing_provenance_block_raises(self):
        with self.assertRaisesRegex(mc_run.HarnessError, "provenance.pdk.version is ''"):
            mc_run.assert_klt_read_the_pinned_pdk({}, _pdk(), PIN, False)

    def test_null_provenance_pdk_raises_rather_than_crashing(self):
        # `klt` emitting an explicit null here must be an explained
        # HarnessError, not an AttributeError traceback.
        with self.assertRaisesRegex(mc_run.HarnessError, "provenance.pdk.version is ''"):
            mc_run.assert_klt_read_the_pinned_pdk(
                {"provenance": {"pdk": None}}, _pdk(), PIN, False
            )

    def test_mismatch_is_downgraded_to_a_stderr_warning_when_allowed(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = mc_run.assert_klt_read_the_pinned_pdk(
                _response("sky130A open_pdks deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"),
                _pdk(),
                PIN,
                True,
            )
        self.assertIsNone(result)
        self.assertIn("WARNING:", stderr.getvalue())
        self.assertIn(PIN["open_pdks_commit"], stderr.getvalue())

    def test_matching_pin_emits_no_warning_even_when_mismatch_is_allowed(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            mc_run.assert_klt_read_the_pinned_pdk(
                _response(PIN["open_pdks_commit"]), _pdk(), PIN, True
            )
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
