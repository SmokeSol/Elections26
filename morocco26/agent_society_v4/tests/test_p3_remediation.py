from __future__ import annotations

import copy
import json
import pathlib
import unittest

from morocco26.agent_society_v4.behavioral_mind_v8 import derive_voter_mind_state
from morocco26.agent_society_v4.behavioral_mind_v8_1 import (
    build_strict_subjective_world,
    suppress_programme_scaffold,
)
from morocco26.agent_society_v4.behavioral_realism_v8_1 import audit_rows_v8_1
from morocco26.agent_society_v4.electoral_offer_2026_v1 import (
    ElectoralOfferError,
    ingest_programmes,
    regional_cards_for_region,
    validate_programme_dataset,
    validate_regional_dataset,
)
from morocco26.agent_society_v4.empirical_mind_v9 import build_empirical_mind
from morocco26.agent_society_v4.empirical_mind_v9_1 import (
    MATCHED_DONOR_LATENT_STATE,
    SURVEY_STRATUM_PRIOR,
    EmpiricalMindV91Error,
    apply_field_transform,
    apply_registry_amendment,
    build_empirical_mind_v9_1,
    empiricalize_behavioral_voter_v9_1,
)
from morocco26.agent_society_v4.empirical_validation_v9_1 import audit_empirical_mind_v9_1
from morocco26.agent_society_v4.p3_data_layers_v1 import (
    NOT_TESTABLE,
    TESTABLE,
    P3DataLayerError,
    assert_no_placeholder_is_model_visible,
    build_cell_census,
    build_certificate,
    measure_local_candidates,
    measure_party_programmes,
    measure_regional_ballot,
    measure_rich_voter_state,
)
from morocco26.agent_society_v4.rich_named_bridge_v1 import (
    RichNamedBridgeError,
    bridge_rich_population,
    partition_fields,
    select_archetypes,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "morocco26" / "frontends" / "agent_society_opus" / "source_v2" / "chatgpt_baseline"
DATA = ROOT / "morocco26" / "data" / "goal100" / "agent_society_v2"

CANONICAL_AXES = [
    "civil_liberties", "culture", "decentralization", "digital_transition",
    "economic_sovereignty", "education", "employment", "environment_transition",
    "fiscal_relief", "gender_equality", "governance_rule_of_law", "health",
    "housing", "industrial_competitiveness", "private_investment_sme",
    "public_state_role", "social_protection", "territorial_equity",
]
PARTIES = ["FGD", "MP", "PAM", "PI", "PJD", "PPS", "RNI", "UC", "USFP"]


def load(name):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def scaffold_programmes():
    """Reproduce the alphabetical-rotation scaffold found in the 2026 input."""
    offsets = {"PJD": 3, "RNI": 8, "PAM": 11, "PI": 14, "PPS": 17, "USFP": 4, "UC": 14, "FGD": 6, "MP": 11}
    rows = []
    for party, offset in offsets.items():
        axes = {}
        for rank, position in enumerate(range(len(CANONICAL_AXES)), 1):
            axis = CANONICAL_AXES[(position + offset) % len(CANONICAL_AXES)]
            axes[axis] = {
                "direction": "VERIFIED_POSITION_AVAILABLE",
                "national_salience_rank": rank,
                "verification_state": "PUBLISHED_PARTY_PROGRAMME",
            }
        rows.append({"party_id": party, "axes": axes})
    return rows


def named_input(*, programmes=None, voters=None, regional=None):
    return {
        "artifact_id": "TEST_NAMED_INPUT",
        "snapshot_known_as_of": "2026-08-22",
        "regime_gate": "P3_CURRENT_VINTAGE_2026",
        "territories": [
            {"territory_id": "t1", "region_name": "R", "ballot_party_ids": PARTIES}
        ],
        "candidacies": [
            {
                "territory_id": "t1",
                "party_id": party,
                "candidate_id": f"C_{party}",
                "candidate_name": "Nom" if index < 6 else None,
                "verification_state": "OFFICIAL_CONFIRMED" if index < 6 else "UNKNOWN_AS_OF_SNAPSHOT",
            }
            for index, party in enumerate(PARTIES)
        ],
        "programmes": scaffold_programmes() if programmes is None else programmes,
        "voter_population": {
            "known_as_of": "2026-08-22",
            "batches": [
                {
                    "batch_id": "B01",
                    "territory_id": "t1",
                    "voters": voters
                    or [
                        {
                            "weighted_archetype_id": f"A{index:03d}",
                            "attention_score": 0.3,
                            "education_level": "NONE",
                            "information_diet_tier": "LOW",
                            "localism": 0.2,
                            "political_discussion": 0.4,
                            "prior_vote_or_abstention": None,
                            **({"known_electoral_surface": {"regional_ballot_cards": regional}} if regional else {}),
                        }
                        for index in range(1, 5)
                    ],
                }
            ],
        },
    }


class DataLayerCertificateTests(unittest.TestCase):
    def test_alphabetical_rotation_scaffold_is_a_placeholder(self):
        report = measure_party_programmes(scaffold_programmes())
        self.assertEqual(report["state"], "PLACEHOLDER")
        self.assertTrue(report["all_programmes_are_alphabetical_rotations"])
        self.assertEqual(report["substantive_position_cells"], 0)
        self.assertEqual(report["distinct_axis_orderings"], 7)
        self.assertEqual(report["direction_census"], {"VERIFIED_POSITION_AVAILABLE": 162})

    def test_measured_positions_make_the_layer_real(self):
        rows = [
            {
                "party_id": party,
                "axes": {
                    "employment": {
                        "direction": "EXPANSION",
                        "national_salience_rank": 1,
                        "actual_position_summary": "Le parti propose X sur l'emploi.",
                    }
                },
            }
            for party in PARTIES
        ]
        self.assertEqual(measure_party_programmes(rows)["state"], "REAL")

    def test_missing_programmes(self):
        self.assertEqual(measure_party_programmes([])["state"], "MISSING")

    def test_local_candidates_partial_real_and_fabrication_detection(self):
        value = named_input()
        report = measure_local_candidates(value["candidacies"])
        self.assertEqual(report["state"], "PARTIAL_REAL")
        self.assertEqual(report["resolved_cells"], 6)
        self.assertEqual(report["unknown_cells"], 3)
        fabricated = copy.deepcopy(value["candidacies"])
        fabricated[-1]["candidate_name"] = "Inventé"
        self.assertEqual(measure_local_candidates(fabricated)["state"], "PLACEHOLDER")

    def test_regional_ballot_missing_then_real(self):
        self.assertEqual(measure_regional_ballot(named_input())["state"], "MISSING")
        cards = [{"party_id": party} for party in PARTIES]
        self.assertEqual(measure_regional_ballot(named_input(regional=cards))["state"], "REAL")

    def test_rich_voter_state_disconnected_then_real(self):
        certificate = {"status": "PASS"}
        report = measure_rich_voter_state(named_input(), rich_population_certificate=certificate)
        self.assertEqual(report["state"], "DISCONNECTED")
        self.assertTrue(report["named_pipeline_baseline_only"])
        rich_voters = [
            {
                "weighted_archetype_id": f"A{index:03d}",
                **{f"field_{position}": position for position in range(25)},
                "household_context": {"household_size": 4},
                "survey_stratum": {"latent_attitude_x_mean": 0.4, "latent_attitude_x_sd": 0.1},
                "territory_context": {"target_year_unemployment_rate": 0.12},
            }
            for index in range(1, 5)
        ]
        report = measure_rich_voter_state(
            named_input(voters=rich_voters), rich_population_certificate=certificate
        )
        self.assertEqual(report["state"], "REAL")
        self.assertEqual(report["voters_with_survey_stratum_block"], 4)

    def test_gate_testability_and_lineage(self):
        value = named_input()
        census = build_cell_census(named_input=value, named_input_sha256="sha")
        certificate = build_certificate(
            named_input=value,
            named_input_sha256="sha",
            cell_census=census,
            cell_census_path="census.json",
            coverage_snapshot={"as_of": "2026-08-22", "active_local_records": 6, "regional_records": 0},
            coverage_path="coverage.json",
            rich_population_certificate={"status": "PASS"},
        )
        self.assertEqual(certificate["status"], "PASS_P3_DATA_LAYERS_CERTIFIED")
        self.assertEqual(certificate["gate_testability"]["BR1_LOCAL"], TESTABLE)
        self.assertEqual(certificate["gate_testability"]["BR1_REGIONAL"], NOT_TESTABLE)
        self.assertEqual(certificate["gate_testability"]["BR4_PROGRAMME"], NOT_TESTABLE)
        self.assertEqual(certificate["gate_testability"]["BR5_PARTY_MEMORY"], NOT_TESTABLE)
        self.assertFalse(certificate["dual_ballot_simulation_allowed"])
        assert_no_placeholder_is_model_visible(certificate)

    def test_lineage_blocks_on_a_stale_census_and_advises_on_stale_coverage(self):
        value = named_input()
        stale = build_cell_census(named_input=value, named_input_sha256="other-sha")
        blocked = build_certificate(
            named_input=value, named_input_sha256="sha", cell_census=stale, cell_census_path="c.json"
        )
        self.assertEqual(blocked["status"], "BLOCKED_P3_DATA_LAYER_LINEAGE")
        self.assertTrue(blocked["blocking_findings"])

        census = build_cell_census(named_input=value, named_input_sha256="sha")
        advised = build_certificate(
            named_input=value,
            named_input_sha256="sha",
            cell_census=census,
            cell_census_path="c.json",
            coverage_snapshot={"as_of": "2026-08-16", "active_local_records": 413, "regional_records": 12},
            coverage_path="coverage.json",
        )
        self.assertEqual(advised["status"], "PASS_P3_DATA_LAYERS_CERTIFIED_WITH_LINEAGE_ADVISORY")
        self.assertEqual(len(advised["advisory_findings"]), 3)

    def test_placeholder_may_not_be_declared_model_visible(self):
        value = named_input()
        census = build_cell_census(named_input=value, named_input_sha256="sha")
        certificate = build_certificate(
            named_input=value, named_input_sha256="sha", cell_census=census, cell_census_path="c.json"
        )
        certificate["model_visibility"]["PARTY_PROGRAMMES"] = "MODEL_VISIBLE_AS_ELECTORAL_INFORMATION"
        with self.assertRaises(P3DataLayerError):
            assert_no_placeholder_is_model_visible(certificate)


class StrictSurfaceTests(unittest.TestCase):
    def _voter(self, regional=None):
        cards = [
            {
                "party_id": party,
                "party_name": party,
                "candidate_name": "Nom" if index < 6 else None,
                "candidate_verification_state": "OFFICIAL_CONFIRMED" if index < 6 else "UNKNOWN_AS_OF_SNAPSHOT",
                "programme_axes": {
                    "employment": {
                        "direction": "VERIFIED_POSITION_AVAILABLE",
                        "national_salience_rank": 1,
                    }
                },
            }
            for index, party in enumerate(PARTIES)
        ]
        surface = {"territory_id": "t1", "ballot_party_ids": PARTIES, "ballot_cards": cards}
        if regional:
            surface["regional_ballot_cards"] = regional
        return {"weighted_archetype_id": "A001", "political_discussion": 0.4, "known_electoral_surface": surface}

    def test_no_silent_regional_fallback(self):
        voter = self._voter()
        mind, _ = derive_voter_mind_state(voter, snapshot_id="S", party_ids=PARTIES)
        world, audit = build_strict_subjective_world(voter, mind_state=mind)
        self.assertEqual(world["REGIONAL"]["REGIONAL_SURFACE_STATUS"], "MISSING")
        self.assertFalse(world["REGIONAL"]["REGIONAL_SIMULATION_ALLOWED"])
        self.assertEqual(world["REGIONAL"]["options"], [])
        self.assertFalse(audit["regional_fallback_used"])
        self.assertEqual(world["ballots_available_to_this_voter"], ["LOCAL"])

    def test_explicit_regional_surface_is_used(self):
        cards = [{"party_id": party, "regional_candidate": None} for party in PARTIES]
        voter = self._voter(regional=cards)
        mind, _ = derive_voter_mind_state(voter, snapshot_id="S", party_ids=PARTIES)
        world, _ = build_strict_subjective_world(voter, mind_state=mind)
        self.assertEqual(world["REGIONAL"]["REGIONAL_SURFACE_STATUS"], "EXPLICIT_REGION_SPECIFIC_SURFACE")
        self.assertEqual(len(world["REGIONAL"]["options"]), 9)

    def test_programme_scaffold_is_withheld(self):
        card = {"programme_axes": {"employment": {"direction": "VERIFIED_POSITION_AVAILABLE"}}}
        result, has_content = suppress_programme_scaffold(card)
        self.assertFalse(has_content)
        self.assertEqual(result["programme_axes"], {})
        self.assertEqual(result["programme_information_state"], "NOT_COLLECTED_AS_OF_SNAPSHOT")

    def test_real_programme_positions_survive(self):
        card = {
            "programme_axes": {
                "employment": {"direction": "EXPANSION", "actual_position_summary": "Le parti propose X."}
            }
        }
        result, has_content = suppress_programme_scaffold(card)
        self.assertTrue(has_content)
        self.assertEqual(result["programme_information_state"], "COLLECTED_AND_SOURCED")


class TestabilityAwareAuditTests(unittest.TestCase):
    def _rows(self, count=4, regional=False):
        rows = []
        for index in range(1, count + 1):
            share = round(1.0 / len(PARTIES), 6)
            vector = {party: share for party in PARTIES}
            vector["FGD"] = round(1.0 - share * (len(PARTIES) - 1) + index * 0.0, 6)
            vector["PAM"] = round(vector["PAM"] + index * 0.001, 6)
            vector["FGD"] = round(vector["FGD"] - index * 0.001, 6)
            row = {
                "weighted_archetype_id": f"A{index:03d}",
                "turnout_probability": 0.3 + index * 0.05,
                "local_party_probabilities": vector,
                "pov_fr": f"Je ne connais pas encore les listes de mon quartier, je verrai plus tard ({index}).",
            }
            if regional:
                row["regional_party_probabilities"] = vector
            rows.append(row)
        return rows

    def test_local_only_rows_do_not_fail_on_a_missing_regional_simplex(self):
        certificate = {"gate_testability": {"BR1_REGIONAL": NOT_TESTABLE, "BR4_PROGRAMME": NOT_TESTABLE}}
        report = audit_rows_v8_1(self._rows(), expected_rows=4, certificate=certificate)
        self.assertEqual(report["BR1_regional_heterogeneity"]["status"], NOT_TESTABLE)
        self.assertEqual(report["BR4_programme_sensitivity"]["status"], NOT_TESTABLE)
        self.assertEqual(report["split_ticket"]["status"], NOT_TESTABLE)
        self.assertTrue(report["pilot_pass_over_testable_gates"])
        self.assertEqual(report["ballots_audited"], ["LOCAL"])

    def test_a_regional_vote_on_a_missing_surface_fails_integrity(self):
        certificate = {"gate_testability": {"BR1_REGIONAL": NOT_TESTABLE}}
        report = audit_rows_v8_1(self._rows(regional=True), expected_rows=4, certificate=certificate)
        self.assertEqual(report["BR0_integrity"]["status"], "FAIL_REGIONAL_VOTE_ON_MISSING_SURFACE")
        self.assertFalse(report["pilot_pass_over_testable_gates"])


class EmpiricalMindV91Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = load("EMPIRICAL_MIND_DIMENSIONS_V1.json")
        cls.amendment = load("EMPIRICAL_MIND_DIMENSIONS_V9_1_AMENDMENT.json")
        cls.sources = load("EMPIRICAL_SOURCE_REGISTRY_V1.json")
        cls.registry = apply_registry_amendment(cls.base, cls.amendment)

    def _build(self, voter, household=None, **kwargs):
        return build_empirical_mind_v9_1(
            voter=voter,
            dimension_registry=self.registry,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_id="S",
            snapshot_date="2026-08-24",
            household=household,
            **kwargs,
        )

    def test_amendment_is_additive_and_does_not_mutate_the_frozen_registry(self):
        before = json.dumps(self.base, sort_keys=True)
        registry = apply_registry_amendment(self.base, self.amendment)
        self.assertEqual(before, json.dumps(self.base, sort_keys=True))
        self.assertEqual(len(registry["dimensions"]), 121)
        self.assertEqual(registry["version"], "V9.1")
        ids = {row["dimension_id"] for row in registry["dimensions"]}
        self.assertTrue({"political_attention", "territorial_local_orientation", "turnout_memory"} <= ids)

    def test_em2_v9_claims_an_individual_fact_and_v9_1_does_not(self):
        voter = {
            "weighted_archetype_id": "A001",
            "latent_attitude_democracy_satisfaction_mean": 0.31,
            "latent_attitude_democracy_satisfaction_sd": 0.28,
            "attitude_posterior_stratum_n": 29,
        }
        old, _ = build_empirical_mind(
            voter=voter,
            dimension_registry=self.base,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_id="S",
            snapshot_date="2026-08-24",
        )
        old_state = old["dimensions"]["democracy_satisfaction"]
        self.assertEqual(old_state["epistemic_status"], "OBSERVED_INDIVIDUAL")
        self.assertTrue(old_state["individual_fact_claimed"])

        new, _ = self._build(voter)
        state = new["dimensions"]["democracy_satisfaction"]
        self.assertEqual(state["epistemic_status"], SURVEY_STRATUM_PRIOR)
        self.assertFalse(state["individual_fact_claimed"])
        self.assertIsNone(state["value"])
        self.assertEqual(state["stratum_sd"], 0.28)
        self.assertEqual(state["stratum_support_n"], 29)
        self.assertNotEqual(state["model_visibility"], "DIRECT_STATEMENT")

    def test_manifest_assertion_is_measured_not_declared(self):
        mind, audit = self._build({"weighted_archetype_id": "A001", "education_level": "SECONDARY"})
        self.assertTrue(mind["epistemic_audit"]["measured"])
        self.assertFalse(mind["population_prior_relabelled_as_individual_fact"])
        report = audit_empirical_mind_v9_1(
            mind,
            dimension_registry=self.registry,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_date="2026-08-24",
        )
        self.assertTrue(report["gates"]["EM12_MANIFEST_ASSERTIONS_MEASURED"])
        self.assertTrue(report["gates"]["EM2_NO_POPULATION_OR_ECOLOGICAL_TO_INDIVIDUAL_OVERCLAIM"])

    def test_em2_gate_catches_an_injected_relabelling(self):
        mind, _ = self._build(
            {
                "weighted_archetype_id": "A001",
                "latent_attitude_institutional_trust_mean": 0.5,
                "latent_attitude_institutional_trust_sd": 0.1,
            }
        )
        tampered = copy.deepcopy(mind)
        state = tampered["dimensions"]["institutional_trust"]
        state["epistemic_status"] = "OBSERVED_INDIVIDUAL"
        state["individual_fact_claimed"] = True
        report = audit_empirical_mind_v9_1(
            tampered,
            dimension_registry=self.registry,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_date="2026-08-24",
        )
        self.assertFalse(report["gates"]["EM2_NO_POPULATION_OR_ECOLOGICAL_TO_INDIVIDUAL_OVERCLAIM"])
        self.assertIn("institutional_trust", report["diagnostics"]["stratum_overclaims"])

    def test_encdm_donor_field_is_not_an_observation(self):
        mind, _ = self._build({"weighted_archetype_id": "A001", "latent_ses_decile": 0.3})
        state = mind["dimensions"]["material_living_standard_position"]
        self.assertEqual(state["epistemic_status"], MATCHED_DONOR_LATENT_STATE)
        self.assertFalse(state["individual_fact_claimed"])
        self.assertIsNone(state["value"])

    def test_named_pipeline_fields_now_land_somewhere(self):
        mind, audit = self._build(
            {
                "weighted_archetype_id": "A001",
                "attention_score": 0.42,
                "localism": 0.8,
                "prior_vote_or_abstention": "ABSTAIN",
                "education_level": "NONE",
                "political_discussion": 0.5,
                "information_diet_tier": "LOW",
            }
        )
        self.assertEqual(mind["dimensions"]["political_attention"]["value"], 0.42)
        self.assertEqual(mind["dimensions"]["territorial_local_orientation"]["value"], 0.8)
        self.assertEqual(mind["dimensions"]["turnout_memory"]["value"], "PRIOR_ABSTENTION")
        self.assertEqual(audit["populated_dimensions"], 5)
        # information_diet_tier is an engine rule, deliberately not a dimension
        ids = {row["dimension_id"] for row in self.registry["dimensions"]}
        self.assertNotIn("information_diet_tier", ids)

    def test_declared_transforms(self):
        self.assertEqual(apply_field_transform(2.5, "PERSONS_PER_ROOM_TO_CROWDING", {}), 0.5)
        self.assertEqual(
            apply_field_transform(1, "UNEMPLOYED_COUNT_TO_BURDEN", {"household_adult_count": 4}), 0.25
        )
        self.assertIsNone(apply_field_transform(1, "UNEMPLOYED_COUNT_TO_BURDEN", {}))
        self.assertEqual(apply_field_transform("Propriétaire", "TENURE_LABEL_TO_HOUSING_SECURITY", {}), 0.9)
        self.assertIsNone(apply_field_transform("Autre chose", "TENURE_LABEL_TO_HOUSING_SECURITY", {}))
        self.assertEqual(
            apply_field_transform("ACTIVE_EMPLOYED", "ACTIVITY_STATUS_TO_EMPLOYMENT", {}), "EMPLOYED"
        )
        self.assertEqual(
            apply_field_transform("Secondaire collégial", "EDUCATION_LABEL_TO_LEVEL", {}), "SECONDARY"
        )
        self.assertEqual(apply_field_transform("Oui", "YES_NO_LABEL_TO_BOOLEAN", {}), "YES")
        with self.assertRaises(EmpiricalMindV91Error):
            apply_field_transform(1, "NO_SUCH_TRANSFORM", {})

    def test_raw_stratum_and_donor_values_never_reach_the_model_view(self):
        voter = {
            "weighted_archetype_id": "A001",
            "voter_mind_state": {},
            "latent_attitude_institutional_trust_mean": 0.5,
            "latent_attitude_institutional_trust_sd": 0.1,
            "latent_ses_decile": 0.3,
        }
        visible, _ = empiricalize_behavioral_voter_v9_1(
            voter,
            dimension_registry=self.registry,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_id="S",
            snapshot_date="2026-08-24",
        )
        states = visible["empirical_moroccan_mind"]["dimensions"].values()
        self.assertTrue(all("stratum_mean" not in state for state in states))
        self.assertTrue(all("donor_value" not in state for state in states))
        self.assertTrue(visible["empirical_mind_contract"]["survey_stratum_priors_are_not_individual_facts"])

    def test_hidden_stratum_visibility_keeps_the_audit_and_drops_the_sentence(self):
        voter = {
            "weighted_archetype_id": "A001",
            "latent_attitude_institutional_trust_mean": 0.5,
            "latent_attitude_institutional_trust_sd": 0.1,
        }
        shown, _ = self._build(voter, stratum_visibility="context")
        hidden, _ = self._build(voter, stratum_visibility="hidden")
        self.assertTrue(shown["model_visible_human_context_fr"])
        self.assertFalse(hidden["model_visible_human_context_fr"])
        self.assertEqual(
            hidden["dimensions"]["institutional_trust"]["epistemic_status"], SURVEY_STRATUM_PRIOR
        )


class RichNamedBridgeTests(unittest.TestCase):
    def _rich(self, count=8):
        return {
            "population_id": "TEST-RICH",
            "territories": [
                {
                    "constituency_id": "t1",
                    "geography_confidence": "DIRECT_MICRODATA_ADMIN",
                    "archetypes": [
                        {
                            "archetype_id": f"t1_R{index:03d}",
                            "weight": 0.01 + index * 0.001,
                            "prior_vote_or_abstention": "ABSTAIN",
                            "age_band": "25_34",
                            "urban_rural": "URBAN",
                            "activity_status": "UNEMPLOYED",
                            "education_level": "Superieur",
                            "household_size": 4,
                            "persons_per_room": 2.0,
                            "tenure_status": "Locataire",
                            "household_adult_count": 2,
                            "household_unemployed_count": 1,
                            "latent_ses_decile": 0.4,
                            "target_year_unemployment_rate": 0.126,
                        }
                        for index in range(count)
                    ],
                }
            ],
        }

    def test_field_partition(self):
        record = self._rich()["territories"][0]["archetypes"][0]
        partition = partition_fields(record)
        self.assertIn("age_band", partition["individual"])
        self.assertIn("household_size", partition["household"])
        self.assertIn("target_year_unemployment_rate", partition["territory_context"])
        self.assertEqual(partition["prior_election_anchor"], ["prior_vote_or_abstention"])
        self.assertEqual(partition["forbidden"], [])

    def test_prior_election_anchor_is_dropped_by_default(self):
        result, certificate = bridge_rich_population(
            named_input=named_input(),
            rich_population=self._rich(),
            voters_per_territory=4,
            snapshot_id="S",
        )
        voter = result["voter_population"]["batches"][0]["voters"][0]
        self.assertIsNone(voter["prior_vote_or_abstention"])
        self.assertEqual(certificate["prior_election_anchors_dropped"], 4)
        self.assertFalse(certificate["prior_election_anchor_allowed"])

        kept, _ = bridge_rich_population(
            named_input=named_input(),
            rich_population=self._rich(),
            voters_per_territory=4,
            allow_prior_election_anchor=True,
            snapshot_id="S",
        )
        self.assertEqual(kept["voter_population"]["batches"][0]["voters"][0]["prior_vote_or_abstention"], "ABSTAIN")

    def test_forbidden_identity_field_is_a_hard_error(self):
        rich = self._rich()
        rich["territories"][0]["archetypes"][0]["religion"] = "X"
        with self.assertRaises(RichNamedBridgeError):
            bridge_rich_population(
                named_input=named_input(), rich_population=rich, voters_per_territory=4, snapshot_id="S"
            )

    def test_selection_is_deterministic_and_distinct(self):
        archetypes = self._rich(count=16)["territories"][0]["archetypes"]
        first = select_archetypes(archetypes, count=6, territory_id="t1", snapshot_id="S")
        second = select_archetypes(archetypes, count=6, territory_id="t1", snapshot_id="S")
        self.assertEqual([row["archetype_id"] for row in first], [row["archetype_id"] for row in second])
        self.assertEqual(len({row["archetype_id"] for row in first}), 6)
        other = select_archetypes(archetypes, count=6, territory_id="t2", snapshot_id="S")
        self.assertEqual(len({row["archetype_id"] for row in other}), 6)

    def test_layers_are_separated(self):
        overlay = [
            {
                "constituency_id": "t1",
                "archetype_id": f"t1_R{index:03d}",
                "attitude_posterior_stratum_n": 29,
                "latent_attitude_democracy_satisfaction_mean": 0.3,
                "latent_attitude_democracy_satisfaction_sd": 0.2,
            }
            for index in range(8)
        ]
        result, certificate = bridge_rich_population(
            named_input=named_input(),
            rich_population=self._rich(),
            attitude_overlay_rows=overlay,
            voters_per_territory=4,
            snapshot_id="S",
        )
        voter = result["voter_population"]["batches"][0]["voters"][0]
        self.assertIn("household_context", voter)
        self.assertIn("survey_stratum", voter)
        self.assertIn("territory_context", voter)
        self.assertNotIn("latent_attitude_democracy_satisfaction_mean", voter)
        self.assertGreater(certificate["survey_stratum_fields_per_voter"], 0)


class ElectoralOfferTests(unittest.TestCase):
    def test_shipped_datasets_are_empty_and_valid(self):
        programmes = json.loads((DATA / "party_programme_2026.json").read_text(encoding="utf-8"))
        regional = json.loads((DATA / "regional_ballot_2026.json").read_text(encoding="utf-8"))
        programme_report = validate_programme_dataset(programmes, snapshot_date="2026-08-24")
        regional_report = validate_regional_dataset(regional, snapshot_date="2026-08-24")
        self.assertEqual(programme_report["dataset_status"], "NOT_COLLECTED_PARTY_PROGRAMME_2026")
        self.assertEqual(programme_report["substantive_2026_position_cells"], 0)
        self.assertEqual(regional_report["dataset_status"], "MISSING_REGIONAL_BALLOT_2026")
        self.assertEqual(regional_report["rows"], 0)

    def test_a_position_cell_must_carry_the_position(self):
        dataset = {
            "schema_version": "ATLAS_PARTY_PROGRAMME_2026_V1",
            "status": "PASS_PARTY_PROGRAMME_2026_COLLECTED",
            "rows": [
                {
                    "party_id": "PAM",
                    "programme_2026_status": "PUBLISHED_2026_PROGRAMME",
                    "source_document": "programme.pdf",
                    "source_url": "https://example.invalid/p.pdf",
                    "publication_date": "2026-07-01",
                    "document_sha256": "a" * 64,
                    "axes": {"employment": {"direction": "VERIFIED_POSITION_AVAILABLE"}},
                }
            ],
        }
        with self.assertRaises(ElectoralOfferError):
            validate_programme_dataset(dataset)

    def test_a_collected_programme_needs_a_source(self):
        dataset = {
            "schema_version": "ATLAS_PARTY_PROGRAMME_2026_V1",
            "status": "PASS_PARTY_PROGRAMME_2026_COLLECTED",
            "rows": [
                {
                    "party_id": "PAM",
                    "programme_2026_status": "PUBLISHED_2026_PROGRAMME",
                    "axes": {
                        "employment": {
                            "actual_position_summary": "Le parti propose X.",
                            "evidence_ids": ["E1"],
                        }
                    },
                }
            ],
        }
        with self.assertRaises(ElectoralOfferError):
            validate_programme_dataset(dataset)

    def test_rejected_local_rows_may_not_become_regional_candidacies(self):
        dataset = {
            "schema_version": "ATLAS_REGIONAL_BALLOT_2026_V1",
            "status": "PASS_REGIONAL_BALLOT_2026_COLLECTED",
            "rows": [
                {
                    "region_id": "casablanca-settat",
                    "party_id": "PAM",
                    "verification_state": "OFFICIAL_CONFIRMED",
                    "provenance_label": "REGIONAL_OR_MISSING",
                    "sources": ["S1"],
                    "list_head_name": "Nom",
                }
            ],
        }
        with self.assertRaises(ElectoralOfferError):
            validate_regional_dataset(dataset)

    def test_ingest_replaces_the_scaffold_with_emptiness_when_nothing_is_collected(self):
        value = named_input()
        dataset = json.loads((DATA / "party_programme_2026.json").read_text(encoding="utf-8"))
        result, report = ingest_programmes(value, dataset, snapshot_date="2026-08-24")
        self.assertTrue(all(not row["axes"] for row in result["programmes"]))
        self.assertTrue(report["synthetic_rotation_removed"])
        self.assertEqual(report["parties_with_positions_injected"], 0)

    def test_regional_cards_mark_unknown_parties_explicitly(self):
        dataset = {
            "schema_version": "ATLAS_REGIONAL_BALLOT_2026_V1",
            "status": "PASS_REGIONAL_BALLOT_2026_COLLECTED",
            "rows": [
                {
                    "region_id": "R",
                    "party_id": "PAM",
                    "verification_state": "OFFICIAL_CONFIRMED",
                    "list_head_name": "Nom",
                    "sources": ["S1"],
                }
            ],
        }
        cards = regional_cards_for_region(dataset, region_id="R", ballot_party_ids=PARTIES)
        self.assertEqual(len(cards), 9)
        pam = next(card for card in cards if card["party_id"] == "PAM")
        self.assertTrue(pam["region_specific_candidate_information_present"])
        other = next(card for card in cards if card["party_id"] == "PJD")
        self.assertFalse(other["region_specific_candidate_information_present"])
        self.assertEqual(other["regional_list_state"], "UNKNOWN_AS_OF_SNAPSHOT")


if __name__ == "__main__":
    unittest.main()
