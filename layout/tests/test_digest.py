"""The repo's one content-digest contract: layout/bin/_digest.py (issue #589).

Every freshness and signoff verdict here is a content-hash comparison, so the
cases that matter are the ones the two pre-consolidation normalizers
*disagreed* on. `signoff/verify-pins.py`'s `norm` -- the weaker twin, and the
one inside the signoff pin gate -- returned `"TBD"` for `"sha256:TBD"`, `""`
for `"sha256:"`, passed a truncated digest straight through, and left an
uppercase or whitespace-padded digest un-canonicalised. Each of those is
pinned below against the strict normalizer that replaced it.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import _digest  # noqa: E402
import _gds_area  # noqa: E402

# sha256("abc"), the canonical test vector.
ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
SHA = "a" * 64


class TestSha256File(unittest.TestCase):
    """The hasher: bare lowercase hex, and the prefixed spelling beside it."""

    def test_bare_hex(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"abc")
            f.flush()
            self.assertEqual(_digest.sha256_file(Path(f.name)), ABC)

    def test_prefixed_is_the_same_digest(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"abc")
            f.flush()
            path = Path(f.name)
            self.assertEqual(_digest.sha256_file_prefixed(path), "sha256:" + ABC)
            self.assertEqual(
                _digest.sha256_file_prefixed(path),
                _digest.SHA256_PREFIX + _digest.sha256_file(path),
            )

    def test_chunking_does_not_change_the_digest(self):
        """A file larger than the 1 MiB read chunk hashes as the whole bytes do.

        The consolidated helper is the chunked one, replacing two call sites
        that used `read_bytes()`; the digests must be indistinguishable or the
        envelopes those sites wrote would stop verifying.
        """
        blob = bytes(range(256)) * 8192  # 2 MiB, spanning the chunk boundary
        with tempfile.NamedTemporaryFile() as f:
            f.write(blob)
            f.flush()
            self.assertEqual(
                _digest.sha256_file(Path(f.name)), hashlib.sha256(blob).hexdigest()
            )

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile() as f:
            f.flush()
            self.assertEqual(
                _digest.sha256_file(Path(f.name)), hashlib.sha256(b"").hexdigest()
            )

    def test_unreadable_file_raises_rather_than_returning_a_digest(self):
        """Callers report an unreadable artifact as *unverified*, not as drift."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(OSError):
                _digest.sha256_file(Path(tmp) / "does-not-exist")


class TestNormalizeSha256(unittest.TestCase):
    """The read side: both spellings in, bare lowercase hex or None out."""

    def test_accepts_both_spellings(self):
        self.assertEqual(_digest.normalize_sha256(SHA), SHA)
        self.assertEqual(_digest.normalize_sha256("sha256:" + SHA), SHA)

    def test_accepts_uppercase_and_padding(self):
        """Same bytes, different typing -- canonicalised, not rejected.

        `norm` left both of these alone, so an uppercase pin failed against a
        lowercase `hexdigest()` and a padded one kept its `sha256:` prefix.
        """
        self.assertEqual(_digest.normalize_sha256(SHA.upper()), SHA)
        self.assertEqual(_digest.normalize_sha256("sha256:" + SHA.upper()), SHA)
        self.assertEqual(_digest.normalize_sha256("  sha256:" + SHA + "  "), SHA)
        self.assertEqual(_digest.normalize_sha256("\tSHA256:" + SHA.upper() + "\n"), SHA)

    def test_rejects_placeholder_and_empty(self):
        """`norm` returned "TBD" and "" here -- strings a comparison can match."""
        self.assertIsNone(_digest.normalize_sha256("sha256:TBD"))
        self.assertIsNone(_digest.normalize_sha256("TBD"))
        self.assertIsNone(_digest.normalize_sha256("sha256:"))
        self.assertIsNone(_digest.normalize_sha256(""))

    def test_rejects_truncated_and_overlong(self):
        self.assertIsNone(_digest.normalize_sha256("deadbeef"))
        self.assertIsNone(_digest.normalize_sha256(SHA[:63]))
        self.assertIsNone(_digest.normalize_sha256(SHA + "a"))
        self.assertIsNone(_digest.normalize_sha256("sha256:" + SHA[:63]))

    def test_rejects_non_hex_and_another_algorithm(self):
        self.assertIsNone(_digest.normalize_sha256("z" * 64))
        self.assertIsNone(_digest.normalize_sha256("sha512:" + SHA))
        self.assertIsNone(_digest.normalize_sha256("md5:" + SHA))

    def test_rejects_non_strings(self):
        for bad in (None, 7, 1.0, True, b"sha256:" + SHA.encode(), ["sha256:" + SHA], {}):
            self.assertIsNone(_digest.normalize_sha256(bad), bad)

    def test_normalized_output_is_a_digest(self):
        """Whatever comes back out is accepted by the same contract."""
        for spelling in (SHA, SHA.upper(), "sha256:" + SHA, "  sha256:" + SHA + " "):
            out = _digest.normalize_sha256(spelling)
            self.assertIsNotNone(out)
            self.assertTrue(_digest.SHA256_HEX_RE.match(out))
            self.assertEqual(_digest.normalize_sha256(out), out)


class TestOneDefinition(unittest.TestCase):
    """The point of the consolidation: one object, not two same-named bodies."""

    def test_gds_area_reexports_the_shared_hasher(self):
        self.assertIs(_gds_area.sha256_file, _digest.sha256_file)


if __name__ == "__main__":
    unittest.main()
