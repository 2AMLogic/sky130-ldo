"""The ONE content-digest contract this repo's verdicts are judged by (issue #589).

Every freshness and signoff verdict in this repo *is* a content-hash
comparison, so "what counts as a digest" is load-bearing. Before this module
there were five independent file-SHA-256 sites (two of them returning a
differently *spelled* digest under the same name `sha256_file`) and two
read-side normalizers that disagreed about which recorded strings are digests
at all -- with the weaker of the two inside the signoff pin gate. This module
is the single place that answers both questions.

Standard library only, so it runs under the repo's plain `python3` with no
`klayout`/`klt` install -- the same property `_gds_area.py` and
`measurements/build_characterization_report.py` rely on. It lives beside
`_gds_area.py` because that is already the cross-tree import target the repo
established (`measurements/build_characterization_report.py` imported
`sha256_file` from here via a `sys.path` insert, and its line reading
``_sha256_of = sha256_file  # one chunked-SHA-256 helper`` recorded the
decision that there should be exactly one); this module finishes extending
that decision to the trees it never reached.

Write side -- two spellings, two explicitly named functions
-----------------------------------------------------------
Both on-disk spellings are deliberate and are NOT changed by this module:

- **bare lowercase hex** -- `layout/.../lvs.json`'s `layout_sha256`, this
  repo's own `area.json`/manifest digests: `sha256_file`.
- **`sha256:`-prefixed** -- `klt` provenance's `content_hash` and the
  envelopes this repo mints to sit beside it: `sha256_file_prefixed`.

What is forbidden is the old state where one *name* meant both: a caller now
has to say which spelling it is writing. Records are append-only evidence, so
no committed record's stored format changes -- only which function produces
it.

Read side -- one strict normalizer
----------------------------------
`normalize_sha256` reduces either spelling to bare lowercase hex and returns
`None` for anything that is not a 64-hex digest. The `None` is the point:
malformed provenance is a thing a caller must report as *unverified*, never
coerce into a comparison that could accidentally match. The permissive
`signoff/verify-pins.py` `norm` this replaces returned `"TBD"` for
`"sha256:TBD"`, `""` for `"sha256:"`, and left an uppercase or
whitespace-padded digest un-canonicalised -- so inside the pin gate a
malformed hash was compared as if it were a digest.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

#: The prefix `klt` provenance uses on a recorded content hash.
SHA256_PREFIX = "sha256:"

#: A digest in this repo's canonical read-side form: bare lowercase hex.
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

# Read in chunks rather than `read_bytes()` so a multi-hundred-MB GDS does not
# have to fit in memory; 1 MiB is what the pre-consolidation chunked helpers
# used, and the digest is identical either way.
_CHUNK_BYTES = 1 << 20


def sha256_file(path: Path) -> str:
    """The file's SHA-256 as bare lowercase hex (no `sha256:` prefix).

    Raises `OSError` if the file cannot be read -- callers that treat an
    unreadable artifact as *unverified* rather than as drift must catch it.
    """
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_BYTES), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_file_prefixed(path: Path) -> str:
    """The same digest in the `sha256:`-prefixed spelling `klt` provenance uses.

    For the envelope-writing callers only. A reader never needs this:
    `normalize_sha256` accepts both spellings.
    """
    return SHA256_PREFIX + sha256_file(path)


def normalize_sha256(value: object) -> str | None:
    """A recorded sha256 reduced to bare lowercase hex, or None if malformed.

    Accepts both spellings this repo's records use -- bare hex (`lvs.json`'s
    `layout_sha256`) and the `sha256:`-prefixed form (`klt` provenance's
    `content_hash`) -- tolerating surrounding whitespace and upper-case hex,
    since those name the same bytes. Anything else (another algorithm's
    prefix, a truncated digest, `"TBD"`, a non-string) is malformed
    provenance, which a caller must report as unverified, never coerce into a
    match.
    """
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v.startswith(SHA256_PREFIX):
        v = v[len(SHA256_PREFIX):]
    return v if SHA256_HEX_RE.match(v) else None
