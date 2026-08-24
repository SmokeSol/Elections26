from __future__ import annotations

import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "morocco26" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import p3_ci_annotate as annotate  # noqa: E402
import p3_fetch_microdata as fetcher  # noqa: E402
import p3_population_2026_preflight as preflight  # noqa: E402


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


class PreflightColumnTests(unittest.TestCase):
    """b.age2014 reads five columns; asking for four crashed run 32743858862."""

    def test_the_preflight_reads_every_column_age2014_touches(self):
        builder = (SCRIPTS / "agent_society_v2_build_rich_populations.py").read_text(encoding="utf-8")
        body = builder.split("def age2014(row):", 1)[1].split("def age_band", 1)[0]
        needed = {name for name in ("AGE1", "AGE5", "pro", "MEN_PRO", "NOR_MEN") if f"row.{name}" in body}
        self.assertEqual(needed, {"AGE1", "AGE5", "pro", "MEN_PRO", "NOR_MEN"})
        source = pathlib.Path(preflight.__file__).read_text(encoding="utf-8")
        usecols = source.split("usecols=[", 1)[1].split("]", 1)[0]
        for column in sorted(needed):
            self.assertIn(f'"{column}"', usecols, column)


class AnnotationTests(unittest.TestCase):
    """Actions logs and artifacts need auth; check-run annotations do not."""

    def test_an_escape_becomes_a_public_annotation(self):
        import io
        import contextlib
        import os

        def boom(argv=None):
            raise AttributeError("no attribute MEN_PRO")

        buffer = io.StringIO()
        previous = os.environ.get("GITHUB_ACTIONS")
        os.environ["GITHUB_ACTIONS"] = "true"
        try:
            with contextlib.redirect_stdout(buffer):
                code = annotate.run_guarded(boom)
        finally:
            if previous is None:
                os.environ.pop("GITHUB_ACTIONS", None)
            else:
                os.environ["GITHUB_ACTIONS"] = previous
        self.assertEqual(code, 1)
        emitted = buffer.getvalue()
        self.assertTrue(emitted.startswith("::error title="))
        self.assertIn("AttributeError", emitted)
        # A raw newline would split the workflow command and lose the traceback.
        self.assertNotIn(chr(10), emitted.rstrip(chr(10)))

    def test_a_clean_run_emits_nothing(self):
        import io
        import contextlib

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = annotate.run_guarded(lambda argv=None: 0)
        self.assertEqual(code, 0)
        self.assertNotIn("::error", buffer.getvalue())

    def test_workflow_command_delimiters_are_escaped(self):
        self.assertEqual(annotate._escape("a:b,c" + chr(10) + "d"), "a%3Ab%2Cc%0Ad")


if __name__ == "__main__":
    unittest.main()
