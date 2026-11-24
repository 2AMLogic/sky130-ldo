"""Item 9's pins must mirror sim/pdk.json across inventory, envelope, README.

Covers signoff/check-item9-pins.py (issue #780): every way the four sources
(`sim/pdk.json`, `signoff/evidence/item9-inventory.json`,
`signoff/evidence/item9-attestation.generic.json`, `signoff/README.md` row 9)
can drift apart (exit 1, every mismatch named on stderr, remediation reading
`KLT_VERSION` from `signoff/check.sh`), and the cases where the check must
fail loudly rather than pass silently (exit 2).

`klt signoff --attest 9 --check` only compares the inventory with the
envelope and never reads `sim/pdk.json`, so a re-pinned pdk.json with a
stale envelope is exactly the drift this suite must catch.

Needs nothing but python3 -- no klt, no PDK, no network.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "check_item9_pins", ROOT / "signoff" / "check-item9-pins.py"
)
assert _spec is not None and _spec.loader is not None
m = importlib.util.module_from_spec(_spec)
sys.modules["check_item9_pins"] = m
_spec.loader.exec_module(m)

VARIANT = "sky130A"
COMMIT = "c0ffee15f524070e85faff4a6a9eef49553ebc2b"
ALT_COMMIT = "deadbeefdad085ffcc829ccfd721f7b4ce39edcf"
TOOLS = {"ngspice": "42", "xschem": "3.4.4"}
CHECK_SH = 'KLT_VERSION="0.9.0"\n'


def _pdk(variant=VARIANT, commit=COMMIT, tools=None):
    return {
        "variant": variant,
        "open_pdks_commit": commit,
        "tools": dict(TOOLS if tools is None else tools),
    }


def _inventory(variant=VARIANT, commit=COMMIT, tools=None):
    return {
        "t1_item": 9,
        "pins": {
            "pdk": {"name": variant, "revision": commit},
            "tools": dict(TOOLS if tools is None else tools),
        },
    }


def _attestation(variant=VARIANT, commit=COMMIT, tools=None, passed=True, dup_pdk=False):
    checks = [
        {
            "check": "pin",
            "role": "pdk",
            "passed": passed,
            "value": {"name": variant, "revision": commit},
        },
        {
            "check": "pin",
            "role": "tools",
            "passed": passed,
            "value": dict(TOOLS if tools is None else tools),
        },
    ]
    if dup_pdk:
        checks.append(dict(checks[0]))
    return {"attestation": {"checks": checks}}


def _readme(variant=VARIANT, commit=COMMIT, tools=None, prefix_len=8, ellipsis="…"):
    tools = dict(TOOLS if tools is None else tools)
    tool_text = ", ".join(f"{n} {v}" for n, v in sorted(tools.items()))
    return (
        "# Signoff\n\n| # | Status | Reading |\n|---|---|---|\n"
        f"| 9 | **`met`** | `klt signoff --attest 9`: the PDK (`{variant}`, "
        f"`{commit[:prefix_len]}{ellipsis}`) and tools ({tool_text}) are pinned. |\n"
        "\nSome prose.\n"
    )


class RunMixin:
    """Materialize a temp repo root and run the check against it."""

    def run_root(self, *, pdk=None, inventory=None, attestation=None, readme=None,
                 check_sh=None, omit=()):
        files = {
            "sim/pdk.json": _pdk() if pdk is None else pdk,
            "signoff/evidence/item9-inventory.json": _inventory() if inventory is None else inventory,
            "signoff/evidence/item9-attestation.generic.json": _attestation() if attestation is None else attestation,
            "signoff/README.md": _readme() if readme is None else readme,
            "signoff/check.sh": CHECK_SH if check_sh is None else check_sh,
        }
        with tempfile.TemporaryDirectory() as d:
            for rel, content in files.items():
                if rel in omit:
                    continue
                path = Path(d) / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                text = json.dumps(content) if isinstance(content, (dict, list)) else content
                path.write_text(text, encoding="utf-8")
            return m.main(["check-item9-pins.py", "--root", d])

    def run_root_stderr(self, **kwargs):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = self.run_root(**kwargs)
        return code, err.getvalue()


class TestAgreement(RunMixin, unittest.TestCase):
    def test_synthetic_agreeing_sources_pass(self):
        self.assertEqual(self.run_root(), 0)

    def test_no_value_is_hardcoded(self):
        """A different-but-consistent pin set must pass too."""
        tools = {"ngspice": "44", "xschem": "3.4.6"}
        self.assertEqual(
            self.run_root(
                pdk=_pdk(variant="sky130B", commit=ALT_COMMIT, tools=tools),
                inventory=_inventory(variant="sky130B", commit=ALT_COMMIT, tools=tools),
                attestation=_attestation(variant="sky130B", commit=ALT_COMMIT, tools=tools),
                readme=_readme(variant="sky130B", commit=ALT_COMMIT, tools=tools),
            ),
            0,
        )

    def test_shortest_and_ascii_prefixes_pass(self):
        self.assertEqual(self.run_root(readme=_readme(prefix_len=7)), 0)
        self.assertEqual(self.run_root(readme=_readme(ellipsis="...")), 0)


class TestPdkJsonDrift(RunMixin, unittest.TestCase):
    """sim/pdk.json moving without the item 9 envelope following (the #780 case)."""

    def test_commit_drift_names_every_stale_source(self):
        """pdk.json moved, inventory+envelope still the old pair: both named."""
        code, err = self.run_root_stderr(pdk=_pdk(commit=ALT_COMMIT))
        self.assertEqual(code, 1)
        self.assertIn("pins.pdk", err)
        self.assertIn(ALT_COMMIT, err)
        self.assertIn("cites no backticked hex prefix", err)
        # the envelope is stale against the authority too, independently of the
        # inventory comparison and the re-mint instructions
        mismatch_lines = [ln for ln in err.splitlines() if ln.startswith("  - ")]
        self.assertTrue(
            any("item9-attestation.generic.json: pin/pdk value" in ln
                and "sim/pdk.json declares" in ln for ln in mismatch_lines),
            err,
        )

    def test_variant_drift(self):
        code, err = self.run_root_stderr(pdk=_pdk(variant="sky130B"))
        self.assertEqual(code, 1)
        self.assertIn("pins.pdk", err)
        self.assertIn("does not name the PDK variant", err)

    def test_tool_version_drift(self):
        code, err = self.run_root_stderr(
            pdk=_pdk(tools={"ngspice": "42", "xschem": "3.4.5"})
        )
        self.assertEqual(code, 1)
        self.assertIn("pins.tools", err)
        self.assertIn("'xschem 3.4.5'", err)

    def test_tool_added_to_pdk_json(self):
        code, _ = self.run_root_stderr(
            pdk=_pdk(tools={"ngspice": "42", "xschem": "3.4.4", "klayout": "0.29"})
        )
        self.assertEqual(code, 1)


class TestInventoryRemint(RunMixin, unittest.TestCase):
    def test_inventory_updated_without_reminting_envelope(self):
        """The exact #767/#777 shape: pdk.json+inventory+README moved, envelope stale."""
        code, err = self.run_root_stderr(
            pdk=_pdk(commit=ALT_COMMIT),
            inventory=_inventory(commit=ALT_COMMIT),
            readme=_readme(commit=ALT_COMMIT),
        )
        self.assertEqual(code, 1)
        self.assertIn("pin/pdk value", err)
        self.assertNotIn("pins.pdk is", err)

    def test_inventory_disagreeing_with_everything_else(self):
        code, err = self.run_root_stderr(inventory=_inventory(commit=ALT_COMMIT))
        self.assertEqual(code, 1)
        self.assertIn("pins.pdk is", err)
        self.assertIn("pin/pdk value", err)
        self.assertNotIn("cites no backticked hex prefix", err)


class TestReadmeDrift(RunMixin, unittest.TestCase):
    def test_wrong_commit_prefix_alone_fails(self):
        """Editing only the README row's commit prefix is drift, not a re-pin."""
        wrong = (ALT_COMMIT)[:8]
        readme = _readme().replace(COMMIT[:8], wrong)
        code, err = self.run_root_stderr(readme=readme)
        self.assertEqual(code, 1)
        self.assertIn("cites no backticked hex prefix", err)

    def test_variant_backticks_removed(self):
        code, err = self.run_root_stderr(readme=_readme().replace(f"`{VARIANT}`", VARIANT))
        self.assertEqual(code, 1)
        self.assertIn("does not name the PDK variant", err)

    def test_tool_version_edited(self):
        code, err = self.run_root_stderr(readme=_readme().replace("xschem 3.4.4", "xschem 3.4.5"))
        self.assertEqual(code, 1)
        self.assertIn("does not declare the pinned tool", err)
        self.assertIn("'xschem 3.4.4'", err)

    def test_tool_name_or_version_variants_fail(self):
        """Only a complete name+version token pair satisfies the declaration."""
        for old, new in (
            ("xschem 3.4.4", "xschem 3.4.4-rc1"),
            ("xschem 3.4.4", "custom-xschem 3.4.4"),
            ("xschem 3.4.4", "xschem 3.4.40"),
            ("ngspice 42", "ngspice 42.1"),
        ):
            with self.subTest(new=new):
                code, err = self.run_root_stderr(readme=_readme().replace(old, new))
                self.assertEqual(code, 1, err)
                self.assertIn("does not declare the pinned tool", err)

    def test_extra_unpinned_tool_in_row_fails(self):
        code, err = self.run_root_stderr(
            readme=_readme().replace("xschem 3.4.4", "xschem 3.4.4, klayout 0.29")
        )
        self.assertEqual(code, 1)
        self.assertIn("klayout 0.29", err)

    def test_pin_text_outside_the_declaration_does_not_count(self):
        """A stale declaration plus the right prefix in later prose is drift."""
        readme = _readme().replace(COMMIT[:8], ALT_COMMIT[:8])
        readme = readme.replace(
            " are pinned. |", f" are pinned. Previous evidence: `{COMMIT[:8]}…`. |"
        )
        code, err = self.run_root_stderr(readme=readme)
        self.assertEqual(code, 1)
        self.assertIn("cites no backticked hex prefix", err)

    def test_variant_only_in_prose_does_not_count(self):
        readme = _readme(variant="sky130B").replace(
            " are pinned. |", f" are pinned. Was `{VARIANT}`. |"
        )
        code, err = self.run_root_stderr(readme=readme)
        self.assertEqual(code, 1)
        self.assertIn("does not name the PDK variant", err)

    def test_longer_prefix_of_same_commit_passes(self):
        self.assertEqual(self.run_root(readme=_readme(prefix_len=40, ellipsis="")), 0)


class TestAttestationShape(RunMixin, unittest.TestCase):
    def test_pin_check_not_passed(self):
        code, err = self.run_root_stderr(attestation=_attestation(passed=False))
        self.assertEqual(code, 1)
        self.assertIn("is not 'passed': true", err)

    def test_duplicate_pin_entries(self):
        code, err = self.run_root_stderr(attestation=_attestation(dup_pdk=True))
        self.assertEqual(code, 1)
        self.assertIn("pin/pdk entries; expected", err)

    def test_missing_pin_role_entry(self):
        att = _attestation()
        att["attestation"]["checks"] = [
            c for c in att["attestation"]["checks"] if c.get("role") != "tools"
        ]
        code, err = self.run_root_stderr(attestation=att)
        self.assertEqual(code, 1)
        self.assertIn('"role": "tools"', err)


class TestMalformedInputs(RunMixin, unittest.TestCase):
    def test_missing_each_input_fails_loudly(self):
        for rel in (
            "sim/pdk.json",
            "signoff/evidence/item9-inventory.json",
            "signoff/evidence/item9-attestation.generic.json",
            "signoff/README.md",
            "signoff/check.sh",
        ):
            with self.subTest(missing=rel):
                self.assertEqual(self.run_root(omit=(rel,)), 2)

    def test_malformed_json_fails_loudly(self):
        for kw in ("pdk", "inventory", "attestation"):
            with self.subTest(file=kw):
                self.assertEqual(self.run_root(**{kw: "{not json"}), 2)

    def test_pdk_shape_rejected(self):
        for bad in (
            _pdk(variant=""),
            _pdk(commit="not-a-sha"),
            _pdk(tools={}),
            _pdk(tools={"ngspice": ""}),
            {"variant": True, "open_pdks_commit": COMMIT, "tools": dict(TOOLS)},
        ):
            with self.subTest(bad=bad):
                self.assertEqual(self.run_root(pdk=bad), 2)

    def test_inventory_shape_rejected(self):
        for bad in ({"t1_item": 9}, {"pins": "none"},
                    {"pins": {"pdk": "sky130A", "tools": {}}}):
            with self.subTest(bad=bad):
                self.assertEqual(self.run_root(inventory=bad), 2)

    def test_attestation_shape_rejected(self):
        self.assertEqual(self.run_root(attestation={"attestation": []}), 2)
        self.assertEqual(
            self.run_root(attestation={"attestation": {"checks": ["nope"]}}), 2
        )

    def test_trailing_newline_in_commit_rejected(self):
        nl = COMMIT + "\n"
        self.assertEqual(
            self.run_root(
                pdk=_pdk(commit=nl),
                inventory=_inventory(commit=nl),
                attestation=_attestation(commit=nl),
            ),
            2,
        )
        for kw, doc in (
            ("pdk", _pdk(commit=nl)),
            ("inventory", _inventory(commit=nl)),
            ("attestation", _attestation(commit=nl)),
        ):
            with self.subTest(file=kw):
                self.assertEqual(self.run_root(**{kw: doc}), 2)

    def test_nested_pin_types_rejected(self):
        att_bad_value = _attestation()
        att_bad_value["attestation"]["checks"][0]["value"] = "sky130A"
        att_bad_passed = _attestation()
        att_bad_passed["attestation"]["checks"][1]["passed"] = "true"
        att_bad_tools = _attestation()
        att_bad_tools["attestation"]["checks"][1]["value"] = {"ngspice": ""}
        cases = {
            "inventory revision bool": {"inventory": _inventory(commit=True)},
            "inventory empty tool version": {
                "inventory": _inventory(tools={"ngspice": "", "xschem": "3.4.4"})
            },
            "inventory non-string tool version": {
                "inventory": _inventory(tools={"ngspice": 42, "xschem": "3.4.4"})
            },
            "attestation non-object value": {"attestation": att_bad_value},
            "attestation string passed": {"attestation": att_bad_passed},
            "attestation empty tool version": {"attestation": att_bad_tools},
        }
        for name, kw in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.run_root(**kw), 2)

    def test_undecodable_text_inputs_fail_loudly(self):
        """Invalid UTF-8 in README / check.sh is an input error, not a crash."""
        with tempfile.TemporaryDirectory() as d:
            for rel, content in (
                ("sim/pdk.json", json.dumps(_pdk())),
                ("signoff/evidence/item9-inventory.json", json.dumps(_inventory())),
                ("signoff/evidence/item9-attestation.generic.json",
                 json.dumps(_attestation())),
                ("signoff/README.md", _readme()),
                ("signoff/check.sh", CHECK_SH),
            ):
                path = Path(d) / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            for rel in ("signoff/README.md", "signoff/check.sh"):
                path = Path(d) / rel
                good = path.read_bytes()
                path.write_bytes(good + b"\xff\xfe\n")
                with self.subTest(file=rel):
                    with contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(
                            m.main(["check-item9-pins.py", "--root", d]), 2
                        )
                path.write_bytes(good)

    def test_readme_row_missing_or_duplicated(self):
        self.assertEqual(self.run_root(readme="# no table at all\n"), 2)
        self.assertEqual(self.run_root(readme=_readme() + _readme()), 2)

    def test_check_sh_without_klt_version(self):
        self.assertEqual(self.run_root(check_sh="# no pin here\n"), 2)


class TestRemediation(RunMixin, unittest.TestCase):
    def test_klt_version_is_read_not_hardcoded(self):
        code, err = self.run_root_stderr(
            check_sh='KLT_VERSION="9.9.9"\n', pdk=_pdk(commit=ALT_COMMIT)
        )
        self.assertEqual(code, 1)
        self.assertIn("klayout-tools==9.9.9", err)
        self.assertNotIn("klayout-tools==0.9.0", err)

    def test_remediation_names_the_remint_and_regrade(self):
        _, err = self.run_root_stderr(pdk=_pdk(commit=ALT_COMMIT))
        self.assertIn("klt signoff --attest 9", err)
        self.assertIn("check.sh --write", err)
        self.assertIn("sim/pdk.json is the authority", err)


class TestCommittedTree(unittest.TestCase):
    """The committed sources must agree -- this is the check on `main`."""

    def test_committed_tree_passes(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = m.main(["check-item9-pins.py"])
        self.assertEqual(code, 0, err.getvalue())


if __name__ == "__main__":
    unittest.main()
