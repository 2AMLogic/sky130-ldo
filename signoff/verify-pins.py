#!/usr/bin/env python3
"""Stage 1 of signoff/check.sh: pinned hashes vs. the artifacts they cover.

`klt signoff` compares a manifest's pin against the *cited envelope's own*
`provenance.input.content_hash` -- it never opens the underlying artifact, and
klt 0.6.0 says so on every pinned citation it prints ("input: not re-hashed
... the artifact itself was not read"). Two hand-written files agreeing with
each other proves nothing on its own, so this stage re-hashes every artifact
named in signoff/artifact-pins.json and cross-checks it against the envelope's
own claim and against the manifest's pin.

Split out of the `python3 - <<'PY'` heredoc that used to live inside
signoff/check.sh so that signoff/tests/test_verify_pins.py can drive it
directly -- the mutation coverage issue #222 asks for needs to run the real
verification stage against a *mutated* pin file, which a heredoc can only
offer to a test willing to `sed` it back out of the shell script.

Every pin/manifest correlation here is keyed on **the file each side names**,
never on "this hash appears somewhere under this item" (issue #222). T1 item
11 ("Power delivery (structural)") is graded from a compound citation -- a
LIST of ordinary entries, the `klt erc` run plus the LVS report -- and both of
its halves legitimately carry the *same* content_hash, because both read the
same GDS. Pooling an item's hashes into one set therefore made either half's
pin satisfy the other half's check, and deleting one of the two pins outright
still passed. Correlating `manifest entry["file"]` with `pin["cited_envelope"]`
is what makes each half stand on its own.

Usage:
    python3 signoff/verify-pins.py <manifest.json> <artifact-pins.json> [--root DIR]

`--root` is the directory the `artifact` / `cited_envelope` paths are resolved
against; it defaults to the current working directory (signoff/check.sh cds to
the repo root before calling this).

Exit status: 0 = every pin agrees with what it claims to cover, 1 = at least
one disagreement (each printed on its own line), 2 = usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys


def norm(value):
    """Both hash spellings this repo's envelopes use, reduced to bare hex."""
    if not isinstance(value, str):
        return None
    return value[len("sha256:"):] if value.startswith("sha256:") else value


def manifest_parts(entry):
    """A manifest evidence entry as a list of citation objects.

    An entry is normally one object; T1 item 11 ("Power delivery
    (structural)") is graded from a compound entry -- a LIST of ordinary
    entries (the `klt erc` run plus the LVS report) -- so both shapes are read
    the same way here. Anything that is not an object is dropped, so a
    malformed entry cannot masquerade as a citation.
    """
    parts = entry if isinstance(entry, list) else [entry]
    return [p for p in parts if isinstance(p, dict)]


def dotted(doc, path):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def verify(manifest, pins, root: pathlib.Path) -> list[str]:
    """Every way this block's pins can disagree with what they claim to cover."""
    failures: list[str] = []
    evidence = manifest.get("evidence") or {}

    # Every item the manifest cites must appear in the pin file, so a new
    # citation cannot be added without also declaring what artifact it is
    # really about.
    cited_items = set(evidence)
    pinned_items = {str(p["item"]) for p in pins}
    for item in sorted(cited_items - pinned_items):
        failures.append(
            f"manifest item {item}: cited, but signoff/artifact-pins.json declares "
            f"no artifact for it -- a citation with no re-hashable artifact behind "
            f"it cannot be freshness-checked by CI"
        )
    for item in sorted(pinned_items - cited_items):
        failures.append(
            f"artifact-pins.json item {item}: pinned, but the manifest cites no "
            f"evidence for that item -- a stale pin for a dropped citation"
        )

    for pin in pins:
        item = str(pin["item"])
        artifact = root / pin["artifact"]
        expected = norm(pin["sha256"])

        if not artifact.is_file():
            failures.append(f"item {item}: artifact {pin['artifact']!r} does not exist")
            continue
        actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if actual != expected:
            failures.append(
                f"item {item}: {pin['artifact']!r} hashes to sha256:{actual} today, "
                f"but signoff/artifact-pins.json pins {pin['sha256']} -- the cited "
                f"evidence moved and the citation was not re-pinned"
            )
            continue

        envelope_path = root / pin["cited_envelope"]
        if not envelope_path.is_file():
            failures.append(
                f"item {item}: cited envelope {pin['cited_envelope']!r} does not exist"
            )
            continue
        envelope = json.loads(envelope_path.read_text())

        field = pin.get("envelope_field")
        if field:
            claimed = norm(dotted(envelope, field))
            if claimed != expected:
                failures.append(
                    f"item {item}: {pin['cited_envelope']!r} claims {field}="
                    f"{dotted(envelope, field)!r}, but {pin['artifact']!r} is "
                    f"sha256:{expected} -- the envelope is about a different "
                    f"revision than the artifact committed here"
                )

        # A manifest pin is graded by `klt signoff` against the envelope's own
        # claim; re-pinning only one of the two files must not pass silently.
        #
        # Correlated by file, not by hash-set membership (#222): this pin is
        # about ONE envelope, so it is graded against the manifest citation
        # that names that same envelope -- never against whatever else the
        # same item happens to cite.
        if not pin.get("manifest_pinned"):
            continue

        cited = pin.get("cited_envelope")
        parts = manifest_parts(evidence.get(item))
        own = [p for p in parts if p.get("file") == cited]
        if not own:
            named = ", ".join(repr(p.get("file")) for p in parts) or "nothing"
            failures.append(
                f"item {item}: artifact-pins.json says manifest_pinned for "
                f"{cited!r}, but the manifest's evidence for that item cites "
                f"{named} -- no manifest citation names this pin's envelope, so "
                f"nothing the manifest pins is actually backed by this artifact"
            )
            continue
        if any(norm(p.get("content_hash")) is None for p in own):
            failures.append(
                f"item {item}: artifact-pins.json says manifest_pinned for "
                f"{cited!r}, but the manifest's citation of that file pins no "
                f"content_hash"
            )
            continue
        wrong = sorted({
            h for h in (norm(p.get("content_hash")) for p in own) if h != expected
        })
        if wrong:
            failures.append(
                f"item {item}: the manifest's {cited!r} citation pins "
                + ", ".join(f"sha256:{h}" for h in wrong)
                + f"; artifact-pins.json pins sha256:{expected} for that same file"
            )

    # Conversely: a manifest pin must be backed by a pin declared
    # `manifest_pinned` for the same item AND naming the same file, so the
    # manifest cannot pin a hash nothing on disk covers -- and a compound
    # citation cannot lean on its sibling half's pin (#222).
    for item, entry in sorted(evidence.items()):
        for part in manifest_parts(entry):
            manifest_hash = norm(part.get("content_hash"))
            if manifest_hash is None:
                continue
            part_file = part.get("file")
            backing = [
                p for p in pins
                if str(p["item"]) == item and p.get("manifest_pinned")
                and p.get("cited_envelope") == part_file
                and norm(p["sha256"]) == manifest_hash
            ]
            if not backing:
                failures.append(
                    f"manifest item {item}: its {part_file!r} citation pins "
                    f"sha256:{manifest_hash}, which no manifest_pinned entry in "
                    f"signoff/artifact-pins.json covers for that same file"
                )

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-hash every pinned artifact and cross-check it against "
                    "the envelope and manifest citation that name it.",
    )
    parser.add_argument("manifest", type=pathlib.Path)
    parser.add_argument("pins", type=pathlib.Path)
    parser.add_argument(
        "--root",
        type=pathlib.Path,
        default=None,
        help="directory the pinned artifact/envelope paths resolve against "
             "(default: the current working directory)",
    )
    args = parser.parse_args(argv)

    root = (args.root or pathlib.Path.cwd()).resolve()
    manifest = json.loads(args.manifest.read_text())
    pins = json.loads(args.pins.read_text())["pins"]

    failures = verify(manifest, pins, root)
    if failures:
        print("signoff/check.sh: pinned-hash verification FAILED", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"signoff/check.sh: {len(pins)} pinned artifact(s) match their citations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
