from __future__ import annotations

import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "morocco26" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import p3_fetch_microdata as fetcher  # noqa: E402


class SourceMicrodataDigestTests(unittest.TestCase):
    """The recorded digests must stay readable without importing the builder.

    `agent_society_v2_build_rich_populations` imports pyreadstat at module level,
    so importing it to read three constants would make the fetcher unrunnable
    anywhere the reader is absent. The digests are parsed out of its source
    instead, which keeps that file the single place they are declared.
    """

    def test_digests_are_read_from_the_builder_source(self):
        digests = fetcher.expected_digests()
        self.assertEqual(sorted(digests), ["encdm", "hh", "ind"])
        for key, value in digests.items():
            self.assertRegex(value, r"^[0-9a-f]{64}$", key)

    def test_the_declared_digests_are_the_builder_s_own(self):
        source = fetcher.BUILDER.read_text(encoding="utf-8")
        for value in fetcher.expected_digests().values():
            self.assertIn(value, source)

    def test_every_source_has_a_file_name_and_an_url(self):
        for key, (name, url) in fetcher.SOURCES.items():
            self.assertTrue(name.endswith((".dta", ".sav")), key)
            self.assertTrue(url.startswith("https://"), key)

    def test_the_two_failure_modes_are_distinguished(self):
        """A short read is retried; a complete file with the wrong digest is not.

        Conflating them is what made runs 32742167166 and 32742873701 look like
        the same opaque exit 2.
        """
        source = pathlib.Path(fetcher.__file__).read_text(encoding="utf-8")
        self.assertIn("TRUNCATED_TRANSFER", source)
        self.assertIn("UPSTREAM_DIGEST_CHANGED", source)
        self.assertIn("received bytes == Content-Length", source)


if __name__ == "__main__":
    unittest.main()
