from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from morocco26.agent_society_v4.behavioral_environment_v8 import (
    build_behavioral_environment,
    read_json,
    validate_behavioral_environment,
)
from morocco26.agent_society_v4.behavioral_mind_v8 import (
    behavioralize_voter,
    build_subjective_electoral_world,
    derive_voter_mind_state,
    sha256_json,
)

PARTIES = ["PAM", "RNI", "PI"]


def voter(**updates):
    value = {
        "weighted_archetype_id": "A001",
        "cell_id": "CELL_A001",
        "political_discussion": 0.62,
        "localism": 0.78,
        "education_level": "SECONDARY",
        "prior_vote_or_abstention": "PI",
        "population_weight": 100.0,
        "registered_electorate_weight": 80.0,
        "information_diet": {"profile": {"attention": 0.62, "localism": 0.78, "program_literacy": 0.58, "social_reliance": 0.61}},
        "known_electoral_surface": {
            "territory_id": "ain-chock",
            "ballot_party_ids": PARTIES,
            "ballot_cards": [
                {"party_id": "PAM", "party_name": "Parti PAM", "candidate_id": "C1", "candidate_name": "Candidate One", "candidate_verification_state": "OFFICIAL_CONFIRMED", "candidate_familiarity": "KNOWN", "candidate_verified_profile": {"former_mp": {"value": True}}, "programme_axes": {"health": {"priority": "HIGH"}}, "local_viability_band": "MEDIUM", "source_url": "https://must-not-be-visible.example"},
                {"party_id": "RNI", "party_name": "Parti RNI", "candidate_id": "UNKNOWN_C2", "candidate_name": None, "candidate_verification_state": "UNKNOWN_AS_OF_SNAPSHOT", "candidate_familiarity": "UNKNOWN", "candidate_verified_profile": {}, "programme_axes": {"employment": {"priority": "MEDIUM"}}, "local_viability_band": None},
                {"party_id": "PI", "party_name": "Parti PI", "candidate_id": "C3", "candidate_name": "Candidate Three", "candidate_verification_state": "DECLARED_BY_PARTY", "candidate_familiarity": "LOW", "candidate_verified_profile": {}, "programme_axes": {"housing": {"priority": "MEDIUM"}}, "local_viability_band": "UNKNOWN"},
            ],
        },
    }
    value.update(updates)
    return value


class BehavioralMindTests(unittest.TestCase):
    def test_unknown_psychopolitical_anchors_stay_unknown(self):
        state, audit = derive_voter_mind_state(voter(), snapshot_id="S1", party_ids=PARTIES)
        anchors = state["before_this_election"]["anchors"]
        self.assertEqual(anchors["government_evaluation"]["band"], "UNKNOWN")
        self.assertEqual(anchors["political_efficacy"]["band"], "UNKNOWN")
        self.assertEqual(anchors["institutional_trust"]["band"], "UNKNOWN")
        self.assertIn("government_evaluation", audit["unknown_anchors"])
        self.assertFalse(state["invented_personal_relationships"])
        self.assertFalse(state["invented_clientelism_or_notability"])
        self.assertFalse(state["invented_party_rejection"])
        self.assertFalse(state["invented_candidate_valence"])

    def test_party_memory_only_uses_explicit_prior(self):
        state, _ = derive_voter_mind_state(voter(), snapshot_id="S1", party_ids=PARTIES)
        self.assertEqual(state["before_this_election"]["party_memory"]["PI"], "PRIOR_SUPPORTED")
        self.assertEqual(state["before_this_election"]["party_memory"]["PAM"], "UNSPECIFIED")
        self.assertEqual(state["before_this_election"]["party_memory"]["RNI"], "UNSPECIFIED")

    def test_demographics_do_not_change_political_mind_derivation(self):
        base = voter(prior_vote_or_abstention="")
        a = {**base, "sex": "F", "religion": "X", "age_band": "18_24", "income_band": "LOW"}
        b = {**base, "sex": "M", "religion": "Y", "age_band": "65_PLUS", "income_band": "HIGH"}
        sa, _ = derive_voter_mind_state(a, snapshot_id="S1", party_ids=PARTIES)
        sb, _ = derive_voter_mind_state(b, snapshot_id="S1", party_ids=PARTIES)
        sa["identity"] = {}; sb["identity"] = {}
        self.assertEqual(sa, sb)

    def test_local_candidate_is_stripped_from_regional_default(self):
        state, _ = derive_voter_mind_state(voter(), snapshot_id="S1", party_ids=PARTIES)
        world, audit = build_subjective_electoral_world(voter(), mind_state=state)
        self.assertEqual(audit["regional_surface_source"], "PARTY_PROGRAMME_ONLY_LOCAL_CANDIDATE_STRIPPED")
        for option in world["REGIONAL"]["options"]:
            self.assertNotIn("candidate_name", option); self.assertNotIn("candidate_id", option); self.assertNotIn("local_viability_band", option)
        self.assertEqual(world["LOCAL"]["options"][0]["candidate_name"], "Candidate One")

    def test_explicit_regional_surface_is_retained(self):
        row = voter()
        row["known_electoral_surface"]["regional_ballot_cards"] = [{"party_id": p, "party_name": f"Party {p}", "regional_candidate": {"candidate_name": f"Regional {p}"}} for p in PARTIES]
        state, _ = derive_voter_mind_state(row, snapshot_id="S1", party_ids=PARTIES)
        world, audit = build_subjective_electoral_world(row, mind_state=state)
        self.assertEqual(audit["regional_surface_source"], "EXPLICIT_REGION_SPECIFIC_SURFACE")
        self.assertEqual(world["REGIONAL"]["options"][0]["regional_candidate"]["candidate_name"], "Regional PAM")

    def test_behavioralized_voter_removes_technical_diet_and_weights(self):
        visible, audit = behavioralize_voter(voter(), snapshot_id="S1", party_ids=PARTIES)
        self.assertNotIn("information_diet", visible); self.assertNotIn("known_electoral_surface", visible)
        self.assertNotIn("population_weight", visible); self.assertNotIn("registered_electorate_weight", visible)
        self.assertIn("voter_mind_state", visible); self.assertIn("electoral_world_as_seen", visible)
        self.assertIn("information_diet", audit["technical_input_fields_removed_from_model_view"])
        self.assertNotIn("source_url", json.dumps(visible))

    def test_explicit_party_affinity_and_rejection_are_preserved_not_invented(self):
        row = voter(party_affinity={"PAM": 0.8, "PI": 0.3}, party_rejection={"RNI": 0.9}, party_attachment_strength=0.7)
        state, _ = derive_voter_mind_state(row, snapshot_id="S1", party_ids=PARTIES)
        before = state["before_this_election"]
        self.assertEqual(before["party_affinity"]["values"]["PAM"]["band"], "HIGH")
        self.assertEqual(before["party_affinity"]["values"]["RNI"]["band"], "UNKNOWN")
        self.assertEqual(before["party_rejection"]["values"]["RNI"]["band"], "HIGH")
        self.assertEqual(before["party_attachment_strength"]["band"], "HIGH")

    def test_low_information_voter_can_have_candidate_name_masked(self):
        row = voter(political_discussion=0.05, localism=0.05, education_level="NONE", information_diet={"profile": {"attention": 0.05, "localism": 0.05, "program_literacy": 0.08, "social_reliance": 0.8}})
        state, _ = derive_voter_mind_state(row, snapshot_id="S1", party_ids=PARTIES)
        world, audit = build_subjective_electoral_world(row, mind_state=state)
        pam = next(item for item in world["LOCAL"]["options"] if item["party_id"] == "PAM")
        self.assertFalse(pam["candidate_known_to_voter"]); self.assertNotIn("candidate_name", pam)
        self.assertEqual(audit["candidate_awareness_audit"]["PAM"]["status"], "EXPERIMENTAL_DETERMINISTIC_AWARENESS_UNVALIDATED")

    def test_explicit_zero_attention_and_localism_are_not_defaulted_to_half(self):
        row = voter(political_discussion=0.0, localism=0.0, education_level="NONE", information_diet={"profile": {"attention": 0.0, "localism": 0.0, "program_literacy": 0.0, "social_reliance": 0.8}})
        state, _ = derive_voter_mind_state(row, snapshot_id="S1", party_ids=PARTIES)
        world, audit = build_subjective_electoral_world(row, mind_state=state)
        pam = next(item for item in world["LOCAL"]["options"] if item["party_id"] == "PAM")
        self.assertFalse(pam["candidate_known_to_voter"])
        awareness = audit["candidate_awareness_audit"]["PAM"]
        self.assertEqual(awareness["attention_band"], "LOW")
        self.assertLess(awareness["score"], 0.1)

    def test_mind_state_is_deterministic(self):
        first, first_audit = behavioralize_voter(voter(), snapshot_id="S1", party_ids=PARTIES)
        second, second_audit = behavioralize_voter(voter(), snapshot_id="S1", party_ids=PARTIES)
        self.assertEqual(first, second); self.assertEqual(first_audit, second_audit)
        self.assertEqual(first_audit["model_visible_voter_sha256"], sha256_json(first))

    def test_environment_overlay_keeps_base_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp); base = root / "base"; out = root / "behavioral"
            (base / "voter_batches" / "ain-chock").mkdir(parents=True); (base / "contexts" / "C_TRUE").mkdir(parents=True); (base / "packets" / "C_TRUE" / "ain-chock").mkdir(parents=True)
            base_manifest = {"status": "PASS_REALISTIC_2026_NAMED_ENVIRONMENT_READY", "regime": "REALISTIC_2026_NAMED", "main_commit_sha": "a" * 40, "target_outcomes_present": False, "candidate_fabrication_used": False, "per_voter_information_diets_present": True, "source_input_sha256": "f" * 64}
            (base / "named_2026_environment_manifest.json").write_text(json.dumps(base_manifest), encoding="utf-8")
            batch = {"anonymous_election_id": "MOROCCO_2026_CURRENT", "anonymous_territory_id": "ain-chock", "batch_id": "B01", "available_party_ids": PARTIES, "voter_archetypes": [voter()]}
            (base / "voter_batches" / "ain-chock" / "B01.json").write_text(json.dumps(batch), encoding="utf-8")
            context = {"anonymous_election_id": "MOROCCO_2026_CURRENT", "anonymous_territory_id": "ain-chock", "condition_id": "C_TRUE", "available_party_ids": PARTIES}
            (base / "contexts" / "C_TRUE" / "ain-chock.json").write_text(json.dumps(context), encoding="utf-8")
            packet = {"anonymous_election_id": "MOROCCO_2026_CURRENT", "anonymous_territory_id": "ain-chock", "condition_id": "C_TRUE", "batch_id": "B01", "voter_batch": batch}
            (base / "packets" / "C_TRUE" / "ain-chock" / "B01.json").write_text(json.dumps(packet), encoding="utf-8")
            (base / "work_manifest.json").write_text(json.dumps({"work_items": [{"anonymous_territory_id": "ain-chock", "batch_id": "B01"}]}), encoding="utf-8")
            original = (base / "voter_batches" / "ain-chock" / "B01.json").read_bytes()
            schema = {"type": "object", "additionalProperties": False, "required": ["weighted_archetype_id", "turnout_probability", "local_party_probabilities", "regional_party_probabilities", "pov_fr"], "properties": {"weighted_archetype_id": {"type": "string"}, "turnout_probability": {"type": "number"}, "local_party_probabilities": {"type": "object"}, "regional_party_probabilities": {"type": "object"}, "pov_fr": {"type": "string"}}}
            manifest = build_behavioral_environment(base, out, prompt_text="Incarne le votant à la première personne; les faits absents restent inconnus.", output_schema=schema)
            self.assertEqual(manifest["status"], "PASS_BEHAVIORAL_MIND_V8_ENVIRONMENT_READY"); self.assertFalse(manifest["scale_allowed"])
            self.assertEqual((base / "voter_batches" / "ain-chock" / "B01.json").read_bytes(), original)
            built = read_json(out / "voter_batches" / "ain-chock" / "B01.json"); row = built["voter_archetypes"][0]
            self.assertIn("voter_mind_state", row); self.assertIn("electoral_world_as_seen", row); self.assertNotIn("information_diet", row)
            validated = validate_behavioral_environment(out); self.assertEqual(validated["startup_work_item_cap"], 1)


if __name__ == "__main__":
    unittest.main()
