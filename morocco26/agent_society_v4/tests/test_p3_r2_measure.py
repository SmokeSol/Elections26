"""R2 measured on a real population instead of a fixture.

The bridge and the V9.1 overlay were both exercised on a shape-faithful
synthetic population, which reported 30 of 121 dimensions populated per voter.
That figure was always labelled as a fixture result, and it is about to be
replaced by an observed one. These tests pin the two things that decide whether
the observed figure means anything: that the measurement runs on exactly the
territory it claims to, and that a missing data layer lowers the count rather
than being quietly filled in.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "morocco26" / "scripts"
for _candidate in (str(REPO_ROOT), str(SCRIPTS)):
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from morocco26.agent_society_v4.rich_named_bridge_v1 import (  # noqa: E402
    RichNamedBridgeError,
    bridge_rich_population,
)

def _named_input(territory_ids):
    return {
        "schema_version": "M26_NAMED_INPUT_TEST",
        "artifact_id": "TEST",
        "territories": [
            {"territory_id": item, "territory_name": item, "seats": 3} for item in territory_ids
        ],
        "candidacies": [
            {"territory_id": item, "candidate_id": f"{item}-c1", "party_id": "p1"}
            for item in territory_ids
        ],
        "parties": [{"party_id": "p1", "party_name": "Party One"}],
        "voter_population": {"batches": []},
    }


def _rich_population(territory_ids, *, with_stratum: bool):
    territories = []
    for item in territory_ids:
        archetypes = []
        for index in range(4):
            record = {
                "archetype_id": f"{item}-a{index}",
                "weight": 0.25,
                "age_years": 30 + index,
                "sex": "female" if index % 2 else "male",
                "education_level": "secondary",
                "urban_rural": "urban",
                "activity_status": "employed",
                "hh_size": 4,
                "hh_dwelling_type": "apartment",
                "latent_ses_decile": 5,
            }
            if with_stratum:
                record["latent_attitude_political_interest_mean"] = 0.4
                record["latent_attitude_institutional_trust_mean"] = 0.3
            archetypes.append(record)
        territories.append(
            {
                "constituency_id": item,
                "constituency_name": item,
                "geography_confidence": "DIRECT_MICRODATA_ADMIN",
                "archetypes": archetypes,
            }
        )
    return {
        "schema_version": "M26_ASV2_CURRENT_POPULATION_TEST",
        "population_id": "TEST-POP",
        "status": "PASS",
        "territories": territories,
    }


class TerritoryFilterTests(unittest.TestCase):
    """R3 runs in one territory, so R2 must be able to measure exactly that one."""

    def test_only_territories_restricts_the_bridge(self):
        named = _named_input(["ain-chock", "agadir-ida-outanane", "al-haouz"])
        rich = _rich_population(
            ["ain-chock", "agadir-ida-outanane", "al-haouz"], with_stratum=False
        )
        result, certificate = bridge_rich_population(
            named_input=named,
            rich_population=rich,
            attitude_overlay_rows=[],
            voters_per_territory=4,
            only_territories=["ain-chock"],
        )
        self.assertEqual(certificate["matched_territories"], ["ain-chock"])
        self.assertEqual(certificate["voter_rows"], 4)
        surviving = {str(item["territory_id"]) for item in result["territories"]}
        self.assertEqual(surviving, {"ain-chock"})
        candidacy_territories = {str(item["territory_id"]) for item in result["candidacies"]}
        self.assertEqual(candidacy_territories, {"ain-chock"})

    def test_an_empty_filter_keeps_every_territory(self):
        named = _named_input(["ain-chock", "al-haouz"])
        rich = _rich_population(["ain-chock", "al-haouz"], with_stratum=False)
        _, certificate = bridge_rich_population(
            named_input=named,
            rich_population=rich,
            attitude_overlay_rows=[],
            voters_per_territory=4,
        )
        self.assertEqual(certificate["matched_territories"], ["ain-chock", "al-haouz"])

    def test_a_typo_in_the_territory_id_is_refused_not_silently_empty(self):
        """Measuring zero voters and calling it a result is the failure to avoid."""
        named = _named_input(["ain-chock"])
        rich = _rich_population(["ain-chock"], with_stratum=False)
        with self.assertRaises(RichNamedBridgeError) as caught:
            bridge_rich_population(
                named_input=named,
                rich_population=rich,
                attitude_overlay_rows=[],
                voters_per_territory=4,
                only_territories=["ain-chok"],
            )
        self.assertIn("ain-chok", str(caught.exception))


class MissingLayerLowersTheCountTests(unittest.TestCase):
    """No 2026 attitude overlay exists, and the count must show that.

    The historical overlay derives stratum posteriors from Afrobarometer R6 and
    R8, for 2016 and 2021. Nothing equivalent has been collected for the current
    vintage, so the twelve SURVEY_STRATUM_PRIOR dimensions the fixture carried
    have no source here. The correct behaviour is a smaller number, not a
    substituted one.
    """

    def test_the_stratum_layer_is_empty_without_an_overlay(self):
        named = _named_input(["ain-chock"])
        rich = _rich_population(["ain-chock"], with_stratum=False)
        _, certificate = bridge_rich_population(
            named_input=named,
            rich_population=rich,
            attitude_overlay_rows=[],
            voters_per_territory=4,
        )
        self.assertEqual(certificate["survey_stratum_fields_per_voter"], 0)
        self.assertEqual(certificate["attitude_overlay_rows_matched"], 0)
        self.assertGreater(certificate["individual_fields_per_voter"], 0)

    def test_stratum_fields_never_enter_the_individual_layer(self):
        named = _named_input(["ain-chock"])
        rich = _rich_population(["ain-chock"], with_stratum=True)
        result, certificate = bridge_rich_population(
            named_input=named,
            rich_population=rich,
            attitude_overlay_rows=[],
            voters_per_territory=4,
        )
        self.assertGreater(certificate["survey_stratum_fields_per_voter"], 0)
        voter = result["voter_population"]["batches"][0]["voters"][0]
        for key in (
            "latent_attitude_political_interest_mean",
            "latent_attitude_institutional_trust_mean",
        ):
            self.assertNotIn(key, voter)
            self.assertIn(key, voter["survey_stratum"])


class WorkflowWiringTests(unittest.TestCase):
    """Two edits in this repo matched nothing and failed silently.

    Both cost a CI run to discover. The population artifact needs a signed-in
    session to download, so R2 has to run inside the job that builds it; if that
    step is not wired, the fixture figure survives by default and nobody notices.
    """

    def setUp(self):
        self.workflow = (
            REPO_ROOT
            / ".github"
            / "workflows"
            / "morocco26-agent-society-v2-current-population-2026-v2.yml"
        ).read_text(encoding="utf-8")

    def test_the_workflow_runs_r2_on_the_population_it_just_built(self):
        steps = self.workflow.split("- name: ")
        step = next(s for s in steps if s.startswith("R2 - bridge"))
        self.assertIn("p3_r2_measure.py", step)
        self.assertIn("--rich-population /tmp/pop2026/out/2026_current_population_v1.json", step)
        self.assertIn("--territory ain-chock", step)
        self.assertIn('$(cat /tmp/pop2026/named_path.txt)', step)

    def test_r2_runs_after_the_population_is_asserted_politically_empty(self):
        assertion = self.workflow.index("Assert politically empty population")
        measurement = self.workflow.index("R2 - bridge")
        self.assertLess(assertion, measurement)

    def test_the_measurement_is_uploaded_with_the_population(self):
        self.assertIn("/tmp/pop2026/r2/p3_r2_measurement.json", self.workflow)
        self.assertIn("/tmp/pop2026/r2/rich_named_bridge_certificate.json", self.workflow)


class MeasurementScriptTests(unittest.TestCase):
    def test_the_script_reports_the_measured_count_not_the_fixture_one(self):
        source = (SCRIPTS / "p3_r2_measure.py").read_text(encoding="utf-8")
        self.assertIn("mean_populated_dimensions_per_voter", source)
        self.assertIn("no_attitude_overlay_for_2026", source)
        # The fixture number may be carried for contrast, never as the result.
        self.assertIn("fixture_figure_superseded", source)
        self.assertNotIn('"mean_populated_dimensions_per_voter": 30', source)

    def test_the_script_fails_when_a_stratum_prior_surfaces_as_an_individual_fact(self):
        source = (SCRIPTS / "p3_r2_measure.py").read_text(encoding="utf-8")
        self.assertIn("population_prior_relabelled_as_individual_fact", source)
        self.assertIn("EM2 violated on the real population", source)


if __name__ == "__main__":
    unittest.main()
