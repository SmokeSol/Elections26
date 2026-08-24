from __future__ import annotations

import copy
import json
import unittest

from morocco26.agent_society_v4.current_population_2026_v1 import (
    RAKING_DIMENSIONS,
    CurrentPopulationError,
    assert_no_electoral_raking,
    build_population_certificate,
    strip_political_memory,
    territory_specs_from_named_input,
    validate_labour_context,
)
from morocco26.agent_society_v4.empirical_mind_v9_1 import (
    ENGINE_DERIVED_COMPOSITE,
    apply_registry_amendment,
    build_empirical_mind_v9_1,
)
from morocco26.agent_society_v4.empirical_validation_v9_1 import audit_empirical_mind_v9_1
from morocco26.agent_society_v4.tests.test_p3_remediation import DATA, load, named_input


class EngineDerivedCompositeTests(unittest.TestCase):
    """attention_score is the information-diet engine's own composite.

    Verified exactly on the 2944 rows of the named 2026 input:
    0.45*political_discussion + 0.30*education_score + 0.15*0.4 + 0.10*localism.
    """

    @classmethod
    def setUpClass(cls):
        cls.base = load("EMPIRICAL_MIND_DIMENSIONS_V1.json")
        cls.amendment = load("EMPIRICAL_MIND_DIMENSIONS_V9_1_AMENDMENT.json")
        cls.sources = load("EMPIRICAL_SOURCE_REGISTRY_V1.json")
        cls.registry = apply_registry_amendment(cls.base, cls.amendment)

    def _build(self, voter):
        return build_empirical_mind_v9_1(
            voter=voter,
            dimension_registry=self.registry,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_id="S",
            snapshot_date="2026-08-24",
        )

    def test_the_declared_formula_reproduces_attention_score(self):
        education = {"NONE": .1, "PRIMARY": .3, "SECONDARY": .55, "HIGH_SCHOOL": .65, "TERTIARY": .9}
        declaration = self.amendment["engine_derived_composite_fields"]["attention_score"]
        constant = declaration["constant_inputs"]["digital_news_exposure"]
        for level, discussion, localism, expected in (
            ("NONE", 0.0, 0.0, 0.09),
            ("NONE", 0.75, 0.0, 0.4275),
            ("PRIMARY", 0.15, 0.25, 0.2425),
            ("SECONDARY", 0.3, 0.5, 0.41),
            ("HIGH_SCHOOL", 0.45, 0.75, 0.5325),
        ):
            value = .45 * discussion + .30 * education[level] + .15 * constant + .10 * localism
            self.assertAlmostEqual(value, expected, places=9)

    def test_attention_score_is_not_evidence(self):
        mind, audit = self._build(
            {
                "weighted_archetype_id": "A001",
                "attention_score": 0.4275,
                "education_level": "NONE",
                "political_discussion": 0.75,
                "localism": 0.0,
            }
        )
        state = mind["dimensions"]["political_attention"]
        self.assertEqual(state["epistemic_status"], ENGINE_DERIVED_COMPOSITE)
        self.assertFalse(state["individual_fact_claimed"])
        self.assertIsNone(state["value"])
        self.assertEqual(state["model_visibility"], "HIDDEN_CALIBRATION_ONLY")
        self.assertEqual(
            state["redundant_with"],
            ["political_discussion", "education_level", "territorial_local_orientation"],
        )
        self.assertEqual(audit["populated_dimensions"], 4)
        self.assertEqual(audit["independent_evidence_dimensions"], 3)
        self.assertNotIn("vie politique", " ".join(mind["model_visible_human_context_fr"]))

    def test_the_engine_value_never_reaches_the_model_view(self):
        from morocco26.agent_society_v4.empirical_mind_v9_1 import (
            empiricalize_behavioral_voter_v9_1,
        )

        visible, _ = empiricalize_behavioral_voter_v9_1(
            {"weighted_archetype_id": "A001", "attention_score": 0.42, "voter_mind_state": {}},
            dimension_registry=self.registry,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_id="S",
            snapshot_date="2026-08-24",
        )
        states = visible["empirical_moroccan_mind"]["dimensions"].values()
        self.assertTrue(all("engine_value" not in state for state in states))
        self.assertTrue(
            visible["empirical_mind_contract"]["engine_derived_composites_are_not_evidence"]
        )

    def test_a_genuinely_measured_attention_variable_still_counts(self):
        mind, audit = self._build({"weighted_archetype_id": "A001", "political_attention": 0.7})
        state = mind["dimensions"]["political_attention"]
        self.assertEqual(state["epistemic_status"], "OBSERVED_INDIVIDUAL")
        self.assertEqual(audit["independent_evidence_dimensions"], 1)

    def test_em13_catches_an_engine_composite_promoted_to_evidence(self):
        mind, _ = self._build({"weighted_archetype_id": "A001", "attention_score": 0.42})
        tampered = copy.deepcopy(mind)
        state = tampered["dimensions"]["political_attention"]
        state["epistemic_status"] = "OBSERVED_INDIVIDUAL"
        state["individual_fact_claimed"] = True
        report = audit_empirical_mind_v9_1(
            tampered,
            dimension_registry=self.registry,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_date="2026-08-24",
        )
        self.assertFalse(report["gates"]["EM13_NO_ENGINE_COMPOSITE_COUNTED_AS_EVIDENCE"])
        self.assertFalse(report["gates"]["EM2_NO_POPULATION_OR_ECOLOGICAL_TO_INDIVIDUAL_OVERCLAIM"])


class CurrentPopulation2026Tests(unittest.TestCase):
    def test_raking_accepts_only_demographic_dimensions(self):
        targets = {name: {"X": 1.0} for name in RAKING_DIMENSIONS}
        assert_no_electoral_raking(targets)
        with self.assertRaises(CurrentPopulationError):
            assert_no_electoral_raking({**targets, "prior_vote_or_abstention": {"ABSTAIN": 1.0}})
        with self.assertRaises(CurrentPopulationError):
            assert_no_electoral_raking({**targets, "party_memory": {"X": 1.0}})

    def test_an_unknown_dummy_marginal_is_still_an_electoral_dimension(self):
        targets = {name: {"X": 1.0} for name in RAKING_DIMENSIONS}
        with self.assertRaises(CurrentPopulationError):
            assert_no_electoral_raking({**targets, "prior_vote_or_abstention": {"UNKNOWN": 1.0}})

    def test_political_memory_is_stripped_from_records(self):
        record = {"age_band": "25_34", "prior_vote_or_abstention": "ABSTAIN", "party_memory": "X"}
        self.assertEqual(strip_political_memory(record), {"age_band": "25_34"})

    def test_the_shipped_labour_template_refuses_to_build(self):
        template = json.loads(
            (DATA / "LABOUR_CONTEXT_2026_TEMPLATE.json").read_text(encoding="utf-8")
        )
        with self.assertRaises(CurrentPopulationError):
            validate_labour_context(template, snapshot_date="2026-08-24")

    def test_a_sourced_labour_context_validates(self):
        report = validate_labour_context(
            {
                "schema_version": "ATLAS_CURRENT_VINTAGE_LABOUR_CONTEXT_2026_V1",
                "publisher": "HCP",
                "source_url": "https://example.invalid/emploi",
                "known_as_of": "2026-07-01",
                "rates": {
                    "unemployment": 0.126,
                    "youth_unemployment": 0.359,
                    "female_unemployment": 0.19,
                    "underemployment": 0.093,
                },
            },
            snapshot_date="2026-08-24",
        )
        self.assertEqual(report["status"], "PASS_LABOUR_CONTEXT_2026")

    def test_a_labour_context_known_after_the_snapshot_is_refused(self):
        with self.assertRaises(CurrentPopulationError):
            validate_labour_context(
                {
                    "schema_version": "ATLAS_CURRENT_VINTAGE_LABOUR_CONTEXT_2026_V1",
                    "publisher": "HCP",
                    "source_url": "https://example.invalid/emploi",
                    "known_as_of": "2026-09-01",
                    "rates": {
                        "unemployment": 0.126,
                        "youth_unemployment": 0.359,
                        "female_unemployment": 0.19,
                        "underemployment": 0.093,
                    },
                },
                snapshot_date="2026-08-24",
            )

    def test_territory_specs_read_only_identifiers(self):
        specs = territory_specs_from_named_input(named_input())
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["constituency_id"], "t1")
        self.assertNotIn("candidacies", specs[0])

    def test_certificate_declares_a_politically_empty_population(self):
        certificate = build_population_certificate(
            territories=[
                {
                    "geography_confidence": "DIRECT_MICRODATA_ADMIN",
                    "quality": {
                        "effective_archetype_count": 150.0,
                        "max_single_archetype_weight": 0.03,
                        "raking_max_abs_error": 1e-9,
                    },
                }
            ],
            failures=[],
            archetypes_per_constituency=256,
            labour_report={"status": "PASS_LABOUR_CONTEXT_2026"},
            source_hashes={"ind": "a" * 64},
            named_input_sha256="b" * 64,
            expected_territories=1,
        )
        self.assertEqual(certificate["status"], "PASS_CURRENT_VINTAGE_POPULATION_2026")
        for name in (
            "historical_outcome_read",
            "prior_election_raking_dimension",
            "sealed_mapping_read",
            "atlas_prior_reinjected",
            "dummy_unknown_marginal_used",
        ):
            self.assertIs(certificate[name], False, name)
        self.assertEqual(certificate["political_memory_population_source"], "NONE")
        self.assertEqual(
            certificate["consequences"]["BR5_PARTY_MEMORY"], "NOT_TESTABLE_MISSING_DATA"
        )

    def test_certificate_fails_when_the_raking_did_not_converge(self):
        certificate = build_population_certificate(
            territories=[
                {
                    "geography_confidence": "DIRECT_MICRODATA_ADMIN",
                    "quality": {
                        "effective_archetype_count": 40.0,
                        "max_single_archetype_weight": 0.4,
                        "raking_max_abs_error": 0.2,
                    },
                }
            ],
            failures=[{"constituency_id": "t1", "reason": "IPF_GATE"}],
            archetypes_per_constituency=256,
            labour_report={"status": "PASS_LABOUR_CONTEXT_2026"},
            source_hashes={},
            named_input_sha256=None,
        )
        self.assertEqual(certificate["status"], "FAIL_CURRENT_VINTAGE_POPULATION_2026")


class R3DesignTests(unittest.TestCase):
    def test_protocol_is_a_2x2_with_replication(self):
        protocol = json.loads(
            (DATA / "P3_R3_LOCAL_ONLY_PILOT_PROTOCOL_V1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(protocol["protocol_revision"], 2)
        self.assertEqual(
            sorted(protocol["design"]["cells"]), ["A_batch", "A_solo", "B_batch", "B_solo"]
        )
        self.assertIn("interaction", protocol["contrasts"])
        self.assertGreaterEqual(protocol["replication"]["batch_replicates_default"], 2)
        self.assertEqual(protocol["promotion_rule"]["name"], "R3_PROMOTION_THRESHOLD")
        self.assertEqual(protocol["promotion_rule"]["noise_rule"]["name"], "R3_NOISE_MULTIPLE")
        self.assertIn("R3_FAIL_does_not_prove", protocol["failure_semantics"])

    def test_ci_freeze_gate_has_no_path_filter(self):
        import pathlib

        text = pathlib.Path(".github/workflows/morocco26-p3-remediation-gates.yml").read_text(
            encoding="utf-8"
        )
        head = text.split("jobs:")[0]
        keys = [line.strip() for line in head.splitlines() if not line.strip().startswith("#")]
        self.assertNotIn("paths:", keys)
        self.assertIn("morocco26-agent-society-v2-front-vote-llm", head)


if __name__ == "__main__":
    unittest.main()
