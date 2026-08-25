from __future__ import annotations

import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "morocco26" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import agent_society_v2_build_current_population_2026_geo_v2 as geo_v2  # noqa: E402
from morocco26.agent_society_v4.current_population_2026_v1 import (  # noqa: E402
    CurrentPopulationError,
)


class CurrentPopulationGeometryTests(unittest.TestCase):
    def _named_from_geometry(self):
        index, _, _ = geo_v2.load_geometry()
        return {
            "territories": [
                {
                    "territory_id": cid,
                    "territory_name": row["repo_name"],
                    "region_name": None,
                }
                for cid, row in sorted(index.items())
            ]
        }

    def test_geometry_certificate_is_complete_and_hashed(self):
        index, digest, value = geo_v2.load_geometry()
        self.assertEqual(value["gate"], "PASS")
        self.assertEqual(len(index), 92)
        self.assertEqual(len(digest), 64)

    def test_split_constituencies_use_certified_admin_parent(self):
        index, _, _ = geo_v2.load_geometry()
        specs = geo_v2.territory_specs_from_certified_geometry(
            self._named_from_geometry(), geometry_index=index
        )
        parents = {row["constituency_id"]: row["prefecture_or_province"] for row in specs}
        self.assertEqual(parents["karia-ghafsay"], "Taounate")
        self.assertEqual(parents["el-gharb"], "Kénitra")
        self.assertEqual(parents["bzou-ouaouizeght"], "Azilal")
        self.assertEqual(parents["rabat-ocean"], "Rabat")

    def test_named_geometry_name_mismatch_fails_closed(self):
        index, _, _ = geo_v2.load_geometry()
        named = self._named_from_geometry()
        named["territories"][0]["territory_name"] = "WRONG TERRITORY"
        with self.assertRaises(CurrentPopulationError):
            geo_v2.territory_specs_from_certified_geometry(named, geometry_index=index)


class CertificateReportingTests(unittest.TestCase):
    """V1 is frozen and returns 2 without saying why; the wrapper republishes it."""

    def test_failures_are_grouped_by_reason_with_examples(self):
        text = geo_v2.summarize_failures(
            [
                {"constituency_id": "menara", "reason": "IPF_GATE",
                 "best": {"err": 1.2e-05, "ess": 96.4, "max_weight": 0.071}},
                {"constituency_id": "fes-nord", "reason": "IPF_GATE",
                 "best": {"err": 3.1e-06, "ess": 118.2, "max_weight": 0.055}},
                {"constituency_id": "tarfaya", "reason": "INSUFFICIENT_PARENT_POOL",
                 "parent": "tarfaya", "rows": 180},
            ]
        )
        self.assertIn("IPF_GATE x2", text)
        self.assertIn("INSUFFICIENT_PARENT_POOL x1", text)
        self.assertIn("menara", text)
        self.assertIn("ess=96", text)
        self.assertIn("rows=180", text)

    def test_an_empty_failure_list_still_produces_a_sentence(self):
        self.assertIn("no per-territory failure", geo_v2.summarize_failures([]))

    def test_more_search_effort_never_relaxes_a_quality_threshold(self):
        """A marginal pool is answered by drawing more samples, not a lower bar."""
        import agent_society_v2_build_current_population_2026 as v1

        self.assertGreater(geo_v2.IPF_ATTEMPTS_FOR_MARGINAL_POOLS, v1.IPF_ATTEMPTS)
        self.assertEqual(v1.MIN_ESS, 128.0)
        self.assertEqual(v1.MAX_WEIGHT, 0.05)
        self.assertEqual(v1.MAX_RAKING_ERROR, 5e-06)

    def test_a_missing_certificate_is_reported_not_swallowed(self):
        import io
        import contextlib
        import os
        import tempfile

        previous = os.environ.get("GITHUB_ACTIONS")
        os.environ["GITHUB_ACTIONS"] = "true"
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                geo_v2.report_certificate(
                    pathlib.Path(tempfile.mkdtemp()) / "absent.json", 2
                )
        finally:
            if previous is None:
                os.environ.pop("GITHUB_ACTIONS", None)
            else:
                os.environ["GITHUB_ACTIONS"] = previous
        self.assertIn("::error", buffer.getvalue())
        self.assertIn("certificate missing", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
