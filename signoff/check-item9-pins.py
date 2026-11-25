#!/usr/bin/env python3
"""Fail if item 9's PDK/tools pins disagree with sim/pdk.json.

`sim/pdk.json` is the harness's authoritative declaration of the PDK
(`variant`, `open_pdks_commit`) and toolchain (`tools`) every simulation
record is pinned against. T1 item 9's evidence hardcodes the same values in
three more places -- `signoff/evidence/item9-inventory.json` (`pins`), the
`{"check": "pin"}` entries of the `klt signoff --attest 9` envelope
`signoff/evidence/item9-attestation.generic.json`, and item 9's row in
`signoff/README.md` -- and `klt` never reads `sim/pdk.json`, so nothing in
`klt signoff --attest 9 --check` notices when the two sides drift (issue
#780: a PDK re-pin moved `sim/pdk.json` and edited the README row while the
envelope kept attesting the old revision, with `check:ci` green the whole
way).

This closes that loop the same way `check-t1-headline.py` closes the
headline loop: compare the committed sources against each other and fail
with the re-mint command on stderr. The klayout-tools version in that
command is read from `signoff/check.sh`'s `KLT_VERSION` pin, never
duplicated here.

Reads only committed files; no klt, no PDK, no network.

Exit codes:
  0  all four sources agree
  1  pin drift -- every mismatch named on stderr, with the remediation
  2  missing, unreadable or malformed input -- never fails open
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PDK_JSON = "sim/pdk.json"
INVENTORY = "signoff/evidence/item9-inventory.json"
ATTESTATION = "signoff/evidence/item9-attestation.generic.json"
README = "signoff/README.md"
CHECK_SH = "signoff/check.sh"

KLT_VERSION_RE = re.compile(r'^KLT_VERSION="([^"]+)"', re.M)
ITEM9_ROW_RE = re.compile(r"^\|\s*9\s*\|")
# item 9's row declares its pins in one fixed phrase:
#   the PDK (`<variant>`, `<hex prefix>…`) and tools (<name> <ver>, ...)
# Both are parsed structurally -- never searched for anywhere in the row -- so
# a pin mentioned in other prose ("Previous evidence ...") cannot satisfy them.
ROW_PDK_RE = re.compile(
    r"\bPDK \(`([^`]+)`,\s*`([0-9a-f]{7,64})(?:\.\.\.|…)?`\)"
)
ROW_TOOLS_RE = re.compile(r"\btools \(([^()]*)\)")
# fullmatch, never `$`: `$` also matches before a trailing newline.
COMMIT_RE = re.compile(r"[0-9a-f]{7,64}")


class InputError(Exception):
    """An input is missing, unreadable or malformed -- exit 2, fail closed."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"{path}: unreadable: {exc}") from exc


def _load_json(path: Path):
    try:
        return json.loads(_read_text(path))
    except ValueError as exc:
        raise InputError(f"{path}: not valid JSON: {exc}") from exc


def _check_pdk_pin(value, where: str) -> dict:
    """A `{"name", "revision"}` pin value must be well-typed, not just present."""
    if not isinstance(value, dict):
        raise InputError(f"{where}: must be an object")
    name = value.get("name")
    revision = value.get("revision")
    if not isinstance(name, str) or not name:
        raise InputError(f"{where}.name: must be a non-empty string")
    if not isinstance(revision, str) or not COMMIT_RE.fullmatch(revision):
        raise InputError(f"{where}.revision: must be a lowercase hex string")
    return value


def _check_tools_pin(value, where: str) -> dict:
    if not isinstance(value, dict):
        raise InputError(f"{where}: must be an object")
    for tool, version in value.items():
        if not isinstance(tool, str) or not tool:
            raise InputError(f"{where}: keys must be non-empty strings")
        if not isinstance(version, str) or not version:
            raise InputError(f"{where}.{tool}: must be a non-empty string")
    return value


def parse_pdk(doc, path: Path) -> tuple[str, str, dict[str, str]]:
    """Return (variant, open_pdks_commit, tools) from sim/pdk.json's shape."""
    if not isinstance(doc, dict):
        raise InputError(f"{path}: not a JSON object")
    variant = doc.get("variant")
    commit = doc.get("open_pdks_commit")
    tools = doc.get("tools")
    if not isinstance(variant, str) or not variant:
        raise InputError(f"{path}: 'variant' must be a non-empty string")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise InputError(
            f"{path}: 'open_pdks_commit' must be a non-empty lowercase hex string"
        )
    if not isinstance(tools, dict) or not tools:
        raise InputError(f"{path}: 'tools' must be a non-empty object")
    for name, version in tools.items():
        if not isinstance(name, str) or not name:
            raise InputError(f"{path}: 'tools' keys must be non-empty strings")
        if not isinstance(version, str) or not version:
            raise InputError(f"{path}: 'tools.{name}' must be a non-empty string")
    return variant, commit, tools


def parse_inventory_pins(doc, path: Path) -> tuple[dict, dict]:
    """Return (pins.pdk, pins.tools) from the item 9 inventory's shape."""
    if not isinstance(doc, dict):
        raise InputError(f"{path}: not a JSON object")
    pins = doc.get("pins")
    if not isinstance(pins, dict):
        raise InputError(f"{path}: 'pins' must be an object")
    pdk = pins.get("pdk")
    tools = pins.get("tools")
    return (
        _check_pdk_pin(pdk, f"{path}: 'pins.pdk'"),
        _check_tools_pin(tools, f"{path}: 'pins.tools'"),
    )


def attestation_pin_entries(doc, path: Path, role: str) -> list[dict]:
    """Return the envelope's `{"check": "pin", "role": role}` entries."""
    if not isinstance(doc, dict):
        raise InputError(f"{path}: not a JSON object")
    att = doc.get("attestation")
    if not isinstance(att, dict):
        raise InputError(f"{path}: 'attestation' must be an object")
    checks = att.get("checks")
    if not isinstance(checks, list):
        raise InputError(f"{path}: 'attestation.checks' must be a list")
    entries = []
    for entry in checks:
        if not isinstance(entry, dict):
            raise InputError(f"{path}: 'attestation.checks' entries must be objects")
        if entry.get("check") == "pin" and entry.get("role") == role:
            where = f"{path}: pin/{role} entry"
            if not isinstance(entry.get("passed"), bool):
                raise InputError(f"{where}: 'passed' must be a boolean")
            check = _check_pdk_pin if role == "pdk" else _check_tools_pin
            check(entry.get("value"), f"{where} 'value'")
            entries.append(entry)
    return entries


def item9_row(text: str, path: Path) -> str:
    """Return the single `| 9 |` table row from signoff/README.md."""
    rows = [
        (n, ln) for n, ln in enumerate(text.splitlines(), 1) if ITEM9_ROW_RE.match(ln)
    ]
    if not rows:
        raise InputError(
            f"{path}: no '| 9 |' table row -- the row this check keeps honest "
            "was removed or renumbered"
        )
    if len(rows) > 1:
        raise InputError(
            f"{path}: {len(rows)} '| 9 |' table rows (lines "
            + ", ".join(str(n) for n, _ in rows)
            + "); expected exactly one"
        )
    return rows[0][1]


def parse_klt_version(check_sh_text: str, path: Path) -> str:
    m = KLT_VERSION_RE.search(check_sh_text)
    if m is None:
        raise InputError(
            f"{path}: no KLT_VERSION=\"...\" pin -- cannot print the re-mint command"
        )
    return m.group(1)


def row_mismatches(row: str, variant: str, commit: str, tools: dict[str, str]) -> list[str]:
    """Every way item 9's README row can disagree with the attested pins."""
    bad = []
    pdk_decls = ROW_PDK_RE.findall(row)
    if len(pdk_decls) != 1:
        bad.append(
            f"{README}: item 9's row has {len(pdk_decls)} 'PDK (`variant`, "
            "`hex…`)' declarations; expected exactly one"
        )
        decl_variant, prefix = None, None
    else:
        decl_variant, prefix = pdk_decls[0]
    if decl_variant != variant:
        bad.append(
            f"{README}: item 9's row does not name the PDK variant in backticks "
            f"(expected '`{variant}`' in its PDK declaration, found "
            f"{decl_variant!r})"
        )
    if prefix is None or not commit.startswith(prefix):
        bad.append(
            f"{README}: item 9's row cites no backticked hex prefix of "
            f"open_pdks_commit {commit} in its PDK declaration (found: "
            f"{prefix if prefix else 'none'})"
        )
    tool_decls = ROW_TOOLS_RE.findall(row)
    declared: dict[str, str] = {}
    if len(tool_decls) != 1:
        bad.append(
            f"{README}: item 9's row has {len(tool_decls)} 'tools (name "
            "version, ...)' declarations; expected exactly one"
        )
    else:
        for item in tool_decls[0].split(","):
            parts = item.split(None, 1)
            if len(parts) == 2:
                declared[parts[0]] = parts[1].strip()
            else:
                bad.append(
                    f"{README}: item 9's row has a malformed tool entry "
                    f"{item.strip()!r} (expected 'name version')"
                )
    for name in sorted(tools):
        if declared.get(name) != tools[name]:
            bad.append(
                f"{README}: item 9's row does not declare the pinned tool "
                f"'{name} {tools[name]}' (row declares "
                f"{declared.get(name, 'no version')!r})"
            )
    for name in sorted(set(declared) - set(tools)):
        bad.append(
            f"{README}: item 9's row declares tool '{name} {declared[name]}' "
            f"that {PDK_JSON} does not pin"
        )
    return bad


def _dumps(value) -> str:
    return json.dumps(value, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check item 9's PDK/tools pins against sim/pdk.json."
    )
    parser.add_argument(
        "--root",
        default=str(ROOT),
        help="repository root to check (default: this checkout)",
    )
    args = parser.parse_args(argv[1:] if argv is not None else None)
    root = Path(args.root).resolve()

    pdk_path = root / PDK_JSON
    inv_path = root / INVENTORY
    att_path = root / ATTESTATION
    readme_path = root / README
    check_sh_path = root / CHECK_SH

    # A check that cannot read its own inputs must never look like one that
    # passed. Shape problems are exit 2; well-formed-but-wrong values below
    # are exit 1.
    try:
        variant, commit, tools = parse_pdk(_load_json(pdk_path), pdk_path)
        inv_pdk, inv_tools = parse_inventory_pins(_load_json(inv_path), inv_path)
        att_doc = _load_json(att_path)
        pdk_entries = attestation_pin_entries(att_doc, att_path, "pdk")
        tools_entries = attestation_pin_entries(att_doc, att_path, "tools")
        row = item9_row(_read_text(readme_path), readme_path)
        klt_version = parse_klt_version(_read_text(check_sh_path), check_sh_path)
    except InputError as exc:
        print(f"check-item9-pins: {exc}", file=sys.stderr)
        return 2

    expected_pdk = {"name": variant, "revision": commit}
    mismatches: list[str] = []

    if inv_pdk != expected_pdk:
        mismatches.append(
            f"{INVENTORY}: pins.pdk is {_dumps(inv_pdk)} but {PDK_JSON} "
            f"declares {_dumps(expected_pdk)}"
        )
    if inv_tools != tools:
        mismatches.append(
            f"{INVENTORY}: pins.tools is {_dumps(inv_tools)} but {PDK_JSON} "
            f"declares {_dumps(tools)}"
        )
    # The envelope is minted from the inventory, so that is what its pin
    # values are compared against -- an inventory updated without a re-mint
    # is exactly the drift this must name.
    for role, entries, inv_value, auth_value in (
        ("pdk", pdk_entries, inv_pdk, expected_pdk),
        ("tools", tools_entries, inv_tools, tools),
    ):
        if not entries:
            mismatches.append(
                f'{ATTESTATION}: no {{"check": "pin", "role": "{role}"}} entry -- '
                "the envelope does not carry the pin check"
            )
        elif len(entries) > 1:
            mismatches.append(
                f"{ATTESTATION}: {len(entries)} pin/{role} entries; expected "
                "exactly one"
            )
        else:
            entry = entries[0]
            if entry.get("passed") is not True:
                mismatches.append(
                    f"{ATTESTATION}: pin/{role} entry is not 'passed': true"
                )
            if entry.get("value") != inv_value:
                mismatches.append(
                    f"{ATTESTATION}: pin/{role} value is "
                    f"{_dumps(entry.get('value'))} but {INVENTORY} pins "
                    f"{_dumps(inv_value)}"
                )
            # ...and independently against sim/pdk.json, so a stale envelope is
            # named even when the inventory it was minted from is stale too.
            if entry.get("value") != auth_value:
                mismatches.append(
                    f"{ATTESTATION}: pin/{role} value is "
                    f"{_dumps(entry.get('value'))} but {PDK_JSON} declares "
                    f"{_dumps(auth_value)}"
                )
    mismatches.extend(row_mismatches(row, variant, commit, tools))

    if not mismatches:
        return 0

    print(
        f"check-item9-pins: item 9's pins disagree with {PDK_JSON} "
        "(the harness's authoritative declaration):",
        file=sys.stderr,
    )
    for msg in mismatches:
        print(f"  - {msg}", file=sys.stderr)
    print(
        "  sim/pdk.json is the authority. To re-align item 9 after moving it:\n"
        "    1. update 'pins' (and the cold-start 'description' if the host\n"
        f"       tooling disclosure moved) in {INVENTORY}\n"
        "    2. re-mint the envelope:\n"
        f"         uvx --from klayout-tools=={klt_version} klt signoff --attest 9 \\\n"
        f"           --inventory {INVENTORY} \\\n"
        f"           -o {ATTESTATION}\n"
        f"    3. update item 9's row in {README} to what the new run reported\n"
        "    4. re-pin signoff/artifact-pins.json and signoff/block-manifest.json\n"
        "       for the re-minted envelope, then: bash signoff/check.sh --write",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
