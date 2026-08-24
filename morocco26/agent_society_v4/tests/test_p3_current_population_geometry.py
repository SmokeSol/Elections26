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


if __name__ == "__main__":
    unittest.main()
