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


class LabourInjectionTests(unittest.TestCase):
    """The preflight has to reproduce the frozen builder's LABOR injection.

    b.labour_multiplier reads b.LABOR[year]; V1 populates it inside its own
    main(), so a preflight that calls the multiplier without injecting first
    raises KeyError - which is what run 32827184796 did.
    """

    def test_the_preflight_mapping_matches_the_frozen_builder(self):
        v1 = (SCRIPTS / "agent_society_v2_build_current_population_2026.py").read_text(
            encoding="utf-8"
        )
        block = v1.split("b.LABOR[TARGET_YEAR] = {", 1)[1].split("}", 1)[0]
        declared = {line.split('"')[1] for line in block.splitlines() if '"' in line}
        self.assertEqual(declared, set(preflight.LABOUR_RATE_KEYS))

    def test_injection_populates_the_target_year(self):
        holder = type("B", (), {"LABOR": {}})()
        injected = preflight.inject_labour_context(
            holder, {"rates": {"unemployment": 0.095, "activity": 0.422}}
        )
        self.assertEqual(holder.LABOR[preflight.TARGET_YEAR], injected)
        self.assertEqual(injected["unemployment"], 0.095)
        self.assertIsNone(injected["urban_unemployment"])
        self.assertEqual(sorted(injected), sorted(preflight.LABOUR_RATE_KEYS))


class MarginCoverageTests(unittest.TestCase):
    """b.ipf dies the moment a target category has mass but no sampled row.

    Run 32826524442 lost 49 of 92 territories that way while the 43 that built
    were comfortable on every quality gate, so the diagnosis has to name the
    unreachable category rather than report non-convergence.
    """

    class _Builder:
        @staticmethod
        def labour_multiplier(activity, milieu, year, base_rates):
            return 1.0

        @staticmethod
        def margins(pool, weights):
            return {
                "age_band": {"18_24": 0.5, "60_PLUS": 0.4999, "RARE": 0.0001},
                "sex": {"M": 0.5, "F": 0.5},
                "not_a_raking_dimension": {"X": 0.00001},
            }

    def _pool(self, size=300):
        import pandas as pd

        return pd.DataFrame(
            {
                "pro_norm": ["p"] * size,
                "pds": [1.0] * size,
                "activity_status": ["ACTIVE_EMPLOYED"] * size,
                "urban_rural": ["URBAN"] * size,
            }
        )

    def test_a_category_too_rare_to_draw_is_named(self):
        rows = [
            {"constituency_id": "t1", "resolved_rgph_parent": "p"},
            {"constituency_id": "t2", "resolved_rgph_parent": "p"},
        ]
        coverage = preflight.margin_coverage(
            self._pool(), rows, sample_size=256, attempts=48, b=self._Builder
        )
        self.assertEqual(coverage["territories_at_risk"], ["t1", "t2"])
        self.assertIn("age_band=RARE", coverage["culprit_categories"])
        record = coverage["culprit_categories"]["age_band=RARE"]
        self.assertAlmostEqual(record["min_mass"], 0.0001)
        self.assertGreater(record["max_probability_all_attempts_miss"], 0.2)

    def test_well_populated_categories_are_not_flagged(self):
        rows = [{"constituency_id": "t1", "resolved_rgph_parent": "p"}]
        coverage = preflight.margin_coverage(
            self._pool(), rows, sample_size=256, attempts=48, b=self._Builder
        )
        flagged = set(coverage["culprit_categories"])
        self.assertNotIn("age_band=18_24", flagged)
        self.assertNotIn("sex=M", flagged)

    def test_only_the_five_raking_dimensions_are_examined(self):
        rows = [{"constituency_id": "t1", "resolved_rgph_parent": "p"}]
        coverage = preflight.margin_coverage(
            self._pool(), rows, sample_size=256, attempts=48, b=self._Builder
        )
        self.assertNotIn("not_a_raking_dimension=X", coverage["culprit_categories"])
        self.assertEqual(
            preflight.RAKING_DIMENSIONS,
            ("age_band", "sex", "urban_rural", "education_band", "activity_status"),
        )

    def test_a_pool_smaller_than_the_sample_is_skipped_not_crashed(self):
        rows = [{"constituency_id": "t1", "resolved_rgph_parent": "p"}]
        coverage = preflight.margin_coverage(
            self._pool(size=10), rows, sample_size=256, attempts=48, b=self._Builder
        )
        self.assertEqual(coverage["territories_at_risk"], [])


if __name__ == "__main__":
    unittest.main()
